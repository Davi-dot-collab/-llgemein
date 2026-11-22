"""Live-Modus: Stream mitschneiden (Segmente), Chat + Lautstaerke beobachten, Highlights sofort schneiden."""
from __future__ import annotations

import collections
import json
import os
import queue
import re
import socket
import ssl
import subprocess
import threading
import time
from pathlib import Path

import numpy as np
import requests

from . import audio, chatmood, detect, render

SEG_RE = re.compile(r"seg_(\d{8})_(\d{6})\.ts$")


def log(msg: str) -> None:
    print(f"[live {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def seg_start(path: Path) -> int | None:
    m = SEG_RE.search(path.name)
    # ffmpeg schreibt die Dateinamen (strftime) in Ortszeit -> auch als Ortszeit lesen (Windows kennt kein TZ=UTC)
    return int(time.mktime(time.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S"))) if m else None


def classify(line: str) -> str:
    """'ping:<payload>' | 'msg' | 'other' fuer eine IRC-Zeile."""
    if line.startswith("PING"):
        return "ping:" + line[5:].strip()
    return "msg" if " PRIVMSG " in line else "other"


class ChatCounter(threading.Thread):
    """Liest den Chat ueber anonymen Twitch-IRC (kein Account noetig) und zaehlt pro Sekunde:
    Nachrichten, Lachen, Schock, Clip-Rufe und Spam (gleiche Nachricht kurz hintereinander)."""

    SPAM_WINDOW = 15

    def __init__(self, channel: str) -> None:
        super().__init__(daemon=True)
        self.channel = channel.lower().lstrip("#")
        self.counts = {c: collections.Counter() for c in chatmood.CATS}
        self.recent: dict[str, int] = {}
        self.messages: collections.deque = collections.deque(maxlen=60)
        self.lock = threading.Lock()
        self.connected = False

    def add(self, text: str, now: int | None = None) -> None:
        now = int(time.time()) if now is None else now
        tags = chatmood.classify_text(text)
        norm = chatmood.normalize(text)
        with self.lock:
            last = self.recent.get(norm)
            if last is not None and now - last <= self.SPAM_WINDOW:
                tags.add("spam")
            self.recent[norm] = now
            if len(self.recent) > 2000:
                self.recent = {k: v for k, v in self.recent.items() if now - v <= self.SPAM_WINDOW}
            self.counts["msg"][now] += 1
            for t in tags:
                self.counts[t][now] += 1
            self.messages.append({"t": now, "text": text[:120], "tags": sorted(tags)})

    def run(self) -> None:
        while True:
            try:
                self._session()
            except Exception as e:
                self.connected = False
                log(f"Chat getrennt ({e}); neuer Versuch in 10 s")
            time.sleep(10)

    def _session(self) -> None:
        raw = socket.create_connection(("irc.chat.twitch.tv", 6697), timeout=30)
        s = ssl.create_default_context().wrap_socket(raw, server_hostname="irc.chat.twitch.tv")
        s.settimeout(120)
        s.sendall(f"PASS SCHMOOPIIE\r\nNICK justinfan{int(time.time()) % 90000 + 10000}\r\n"
                  f"JOIN #{self.channel}\r\n".encode())
        self.connected = True
        buf = b""
        while True:
            data = s.recv(8192)
            if not data:
                raise ConnectionError("Verbindung geschlossen")
            buf += data
            *lines, buf = buf.split(b"\r\n")
            for raw_line in lines:
                line = raw_line.decode("utf-8", "replace")
                kind = classify(line)
                if kind == "msg":
                    parsed = chatmood.parse_privmsg(line)
                    if parsed:
                        self.add(parsed[1])
                elif kind.startswith("ping:"):
                    s.sendall(f"PONG {kind[5:]}\r\n".encode())

    def arrays(self, t0: int, n: int) -> dict[str, np.ndarray]:
        with self.lock:
            out = {c: np.array([self.counts[c].get(t0 + i, 0) for i in range(n)], dtype=np.float32)
                   for c in chatmood.CATS}
            for cnt in self.counts.values():
                for k in [k for k in cnt if k < t0 - 60]:
                    del cnt[k]
        return out

    def recent_messages(self, k: int = 25) -> list[dict]:
        with self.lock:
            return list(self.messages)[-k:]


class Recorder(threading.Thread):
    """Haelt ffmpeg am Laufen, das den Live-Stream in 10-s-Segmente (Dateinamen in Ortszeit) schreibt."""

    def __init__(self, channel: str, fmt: str, seg_dir: Path, seg_s: int, source: str | None) -> None:
        super().__init__(daemon=True)
        self.channel, self.fmt, self.dir, self.seg_s, self.source = channel, fmt, seg_dir, seg_s, source
        self.proc: subprocess.Popen | None = None
        self.live = False

    def _stream_url(self) -> str | None:
        if self.source:
            return self.source
        r = subprocess.run(["yt-dlp", "-g", "-f", self.fmt, f"https://www.twitch.tv/{self.channel}"],
                           capture_output=True, text=True)
        lines = r.stdout.strip().splitlines()
        return lines[0] if r.returncode == 0 and lines else None

    def run(self) -> None:
        while True:
            url = self._stream_url()
            if not url:
                self.live = False
                time.sleep(30)
                continue
            log("Stream ist live, nehme auf ...")
            self.live = True
            cmd = ["ffmpeg", "-v", "error", "-y"]
            if self.source and Path(self.source).exists():
                cmd += ["-re"]  # lokale Datei in Echtzeit abspielen (Test)
            cmd += ["-i", url, "-c", "copy", "-f", "segment", "-segment_time", str(self.seg_s),
                    "-segment_format", "mpegts", "-strftime", "1", str(self.dir / "seg_%Y%m%d_%H%M%S.ts")]
            self.proc = subprocess.Popen(cmd)
            self.proc.wait()
            self.live = False
            log("Aufnahme beendet (Stream offline?). Warte auf naechsten Stream.")
            time.sleep(30)

    def completed(self) -> list[tuple[int, Path]]:
        segs = sorted((seg_start(p), p) for p in self.dir.glob("seg_*.ts") if seg_start(p) is not None)
        running = self.proc is not None and self.proc.poll() is None
        return segs[:-1] if running and segs else segs


def concat_segments(segs: list[tuple[int, Path]], t0: float, t1: float, seg_s: int, dest: Path) -> int | None:
    """Schneidet alle Segmente zusammen, die [t0, t1] beruehren. Gibt Startzeit des ersten Segments zurueck."""
    use = [(s, p) for s, p in segs if s + seg_s + 1 >= t0 and s <= t1]
    if not use:
        return None
    lst = dest.with_suffix(".txt")
    lst.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for _, p in use))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", str(dest)], check=True)
    return use[0][0]


def notify(webhook: str, text: str) -> None:
    if webhook:
        try:
            requests.post(webhook, json={"content": text}, timeout=10)
        except Exception as e:
            log(f"Webhook fehlgeschlagen ({e})")


def _write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def run_live(cfg: dict, channel: str, workdir: Path, out_dir: Path, source: str | None = None,
             dry_run: bool = False, threshold: float | None = None, chat_only: bool = False) -> None:
    """chat_only: nur den Chat beobachten und Highlights melden (keine Aufnahme, keine Clips)."""
    d, lv, tw = cfg["detect"], cfg["live"], cfg["twitch"]
    workdir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    stop_flag = workdir / "live.stop"
    stop_flag.unlink(missing_ok=True)
    status_path = workdir / "live_status.json"
    thr = threshold if threshold is not None else lv["threshold"]
    started = time.time()
    no_clips = dry_run or chat_only

    rec = None
    seg_dir = workdir / f"live_{channel}"
    if not chat_only:
        seg_dir.mkdir(parents=True, exist_ok=True)
        rec = Recorder(channel, tw["video_format"], seg_dir, lv["segment_s"], source)
        rec.start()
    chat = ChatCounter(channel)
    chat.start()
    jobs: queue.Queue = queue.Queue()
    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    peaks_log: list[dict] = []

    def worker() -> None:
        tr = None
        while True:
            job = jobs.get()
            try:
                if tr is None:
                    from .transcribe import Transcriber
                    tr = Transcriber(cfg["transcribe"])
                c, section, why = job
                c.words, c.segments = tr.run(str(section))
                if detect.speech_rate(c) < d["min_words_per_sec"]:
                    log(f"Peak bei {time.strftime('%H:%M:%S', time.localtime(c.peak))}: zu wenig Sprache, verworfen")
                    continue
                detect.snap_bounds(c, d["min_len"], d["max_len"])
                name = f"clip_{len(manifest) + 1:03d}.mp4"
                render.render(str(section), c.start - c.section_start, c.end - c.section_start,
                              out_dir / name, c.words, cfg["render"])
                manifest.append({"file": name, "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(c.peak)),
                                 "score": round(c.score, 3), "title": _title(c), "reason": why})
                manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
                log(f"Neuer Clip: {out_dir / name}")
                notify(lv["webhook"], f"Neuer Clip: {name} ({manifest[-1]['title']}) {why}")
            except Exception as e:
                log(f"Fehler beim Verarbeiten: {e}")
            finally:
                jobs.task_done()

    if not no_clips:
        threading.Thread(target=worker, daemon=True).start()

    audio_db: dict[int, float] = {}
    seen: set[Path] = set()
    last_peak = -1e9

    def status(state: str, series: dict | None = None) -> None:
        _write_json(status_path, {
            "updated": time.time(), "channel": channel, "state": state, "chat_only": chat_only,
            "dry_run": dry_run, "threshold": thr, "pid": os.getpid(), "started": started,
            "stream_live": bool(rec and rec.live), "chat_connected": chat.connected,
            "queue": jobs.qsize(), "series": series or {}, "peaks": peaks_log[-20:],
            "messages": chat.recent_messages(), "clips": len(manifest)})

    log(f"Beobachte {channel} (Schwelle {thr}{', nur Chat' if chat_only else ''}). Strg+C zum Beenden.")
    try:
        while not stop_flag.exists():
            time.sleep(lv["poll_s"])
            segs: list = []
            if chat_only:
                now = int(time.time())
                t0 = max(int(started), now - lv["history_s"])
                n = now - t0
                a = np.zeros(max(n, 0), dtype=np.float32)
                w_audio = 0.0
            else:
                segs = rec.completed()
                for start, path in segs:
                    if path in seen:
                        continue
                    seen.add(path)
                    try:
                        for i, v in enumerate(audio.loudness_per_second(str(path))):
                            audio_db[start + i] = float(v)
                    except Exception as e:
                        log(f"Segment {path.name} nicht lesbar ({e})")
                cutoff = time.time() - lv["buffer_min"] * 60
                for start, path in segs:
                    if start < cutoff:
                        path.unlink(missing_ok=True)
                        seen.discard(path)
                for t in [t for t in audio_db if t < time.time() - lv["history_s"] * 2]:
                    del audio_db[t]
                if not audio_db:
                    status("waiting_stream")
                    continue
                end_t = max(audio_db) + 1
                t0 = max(min(audio_db), end_t - lv["history_s"])
                n = end_t - t0
                med = float(np.median(list(audio_db.values())))
                a = np.array([audio_db.get(t0 + i, med) for i in range(n)], dtype=np.float32)
                w_audio = d["weight_audio"]
            if n < lv["min_history_s"]:
                status("collecting")
                continue
            arrs = chat.arrays(t0, n)
            sig = chatmood.chat_signal(arrs, lv["mood_weight"])
            sm, _ = detect.live_series(a, sig, w_audio, d["weight_chat"])
            k = min(n, 300)
            series = {"t_end": t0 + n, **{c: arrs[c][-k:].astype(int).tolist() for c in chatmood.CATS},
                      "audio": np.round(a[-k:], 1).tolist(), "score": np.round(sm[-k:], 3).tolist()}
            peak, value = detect.live_peak(a, sig, t0, w_audio, d["weight_chat"], thr, lv["audio_only_threshold"],
                                           d["post_roll"], d["min_gap"], last_peak)
            if peak is None:
                status("watching", series)
                continue
            last_peak = peak
            why = chatmood.reason(arrs, int(peak - t0))
            when = time.strftime("%H:%M:%S", time.localtime(peak))
            log(f"Highlight bei {when} (Score {value:.2f}) {why}")
            peaks_log.append({"time": when, "score": round(value, 2), "reason": why,
                              "action": "nur gemeldet" if no_clips else "Clip wird erstellt"})
            status("watching", series)
            if no_clips:
                continue
            section = seg_dir / f"cut_{int(peak)}.ts"
            first = concat_segments(segs, peak - d["pre_roll"] - 10, peak + d["post_roll"] + 5,
                                    lv["segment_s"], section)
            if first is None:
                log("Segmente fuer den Peak nicht mehr vorhanden")
                continue
            cand = detect.Candidate(peak=peak, start=peak - d["pre_roll"], end=peak + d["post_roll"],
                                    score=value, section_start=float(first))
            jobs.put((cand, section, why))
    except KeyboardInterrupt:
        pass
    finally:
        log("Beende, warte auf laufende Clips ...")
        if not no_clips:
            jobs.join()
        if rec and rec.proc and rec.proc.poll() is None:
            rec.proc.terminate()
        status("stopped")
        stop_flag.unlink(missing_ok=True)


def _title(c: detect.Candidate) -> str:
    off = c.peak - c.section_start
    best = min(c.segments, key=lambda s: abs((s[0] + s[1]) / 2 - off), default=None)
    text = re.sub(r"\s+", " ", best[2]).strip() if best else ""
    return (text[:70].rsplit(" ", 1)[0] + "...") if len(text) > 70 else text
