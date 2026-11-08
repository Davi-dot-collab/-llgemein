from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np

from . import audio, config, detect, render, tiktok, twitch


def log(msg: str) -> None:
    print(f"[clipbot] {msg}", flush=True)


def _title(c: detect.Candidate) -> str:
    off = c.peak - c.section_start
    best = min(c.segments, key=lambda s: abs((s[0] + s[1]) / 2 - off), default=None)
    text = re.sub(r"\s+", " ", best[2]).strip() if best else ""
    return (text[:70].rsplit(" ", 1)[0] + "...") if len(text) > 70 else text


def cmd_run(a: argparse.Namespace) -> None:
    cfg = config.load(a.config)
    d, tw = cfg["detect"], cfg["twitch"]
    work, out_root = Path(a.workdir), Path(a.out)
    work.mkdir(parents=True, exist_ok=True)

    local = Path(a.source).exists() if a.source else False
    helix = None
    vod: dict = {}
    if not local:
        helix = twitch.Helix()
        vod = helix.latest_vod(tw["channel"]) if a.latest else helix.vod(twitch.parse_vod_id(a.source) or "")
        vod_id = vod["id"]
        log(f"VOD {vod_id}: {vod.get('title', '')} ({vod.get('duration', '?')})")
        src_audio = str(twitch.download_audio(vod_id, work))
    else:
        vod_id = a.vod_id or Path(a.source).stem
        src_audio = a.source
        if a.vod_id and not a.no_twitch:
            helix = twitch.Helix()
            vod = helix.vod(a.vod_id)

    log("Analysiere Audio ...")
    level = audio.loudness_per_second(src_audio)
    total = float(len(level))

    chat = None
    if tw["use_chat"] and vod and not a.no_twitch:
        try:
            log("Lade Chat-Replay ...")
            chat = detect.chat_rate(twitch.chat_timestamps(vod["id"]), len(level))
            log(f"{int(chat.sum())} Chatnachrichten")
        except Exception as e:  # inoffizielle Schnittstelle: nie hart scheitern
            log(f"Chat nicht verfuegbar ({e}); weiter ohne Chat.")
    offsets: list[float] = []
    if tw["use_twitch_clips"] and helix and vod:
        try:
            offsets = helix.vod_clip_offsets(vod)
            log(f"{len(offsets)} Zuschauer-Clips aus diesem VOD")
        except Exception as e:
            log(f"Twitch-Clips nicht verfuegbar ({e}).")

    score, parts = detect.combine(level, chat, offsets, d["weight_audio"], d["weight_chat"], d["weight_clip"])
    n_cand = int(a.count * d["overgenerate"])
    cands = detect.make_candidates(score, parts, total, n_cand, d["pre_roll"], d["post_roll"], d["min_gap"])
    log(f"{len(cands)} Kandidaten gefunden, transkribiere ...")

    from .transcribe import Transcriber
    tr = Transcriber(cfg["transcribe"])
    pad = 10.0
    for c in cands:
        s0, s1 = max(0.0, c.start - pad), min(total, c.end + pad)
        dest = work / f"{vod_id}_{int(c.peak)}.mp4"
        if local:
            twitch.cut_local(a.source, s0, s1, dest)
        else:
            twitch.download_section(vod_id, s0, s1, tw["video_format"], dest)
        c.section_start = s0
        c.words, c.segments = tr.run(str(dest))
        c.score = detect.text_rescore(c, d["hype_words"], d["min_words_per_sec"])

    best = sorted(cands, key=lambda c: c.score, reverse=True)[: a.count]
    out_dir = out_root / vod_id
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for i, c in enumerate(sorted(best, key=lambda c: c.peak), 1):
        detect.snap_bounds(c, d["min_len"], d["max_len"])
        section = work / f"{vod_id}_{int(c.peak)}.mp4"
        dest = out_dir / f"clip_{i:02d}.mp4"
        rel_start, rel_end = c.start - c.section_start, c.end - c.section_start
        log(f"Render {dest.name}: {c.start:.0f}s-{c.end:.0f}s (Score {c.score:.2f})")
        render.render(str(section), rel_start, rel_end, dest, c.words, cfg["render"])
        manifest.append({"file": dest.name, "vod_start": round(c.start, 1), "vod_end": round(c.end, 1),
                         "score": round(c.score, 3), "signals": c.signals, "title": _title(c),
                         "uploaded": False})
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    log(f"Fertig: {out_dir} ({len(manifest)} Clips). Titel in manifest.json anpassen, dann: clipbot upload {out_dir}")


def cmd_upload(a: argparse.Namespace) -> None:
    cfg = config.load(a.config)
    t = cfg["tiktok"]
    d = Path(a.dir)
    mpath = d / "manifest.json"
    manifest = json.loads(mpath.read_text())
    ids = {int(x) for x in a.ids.split(",")} if a.ids else None
    for i, m in enumerate(manifest, 1):
        if m["uploaded"] or (ids and i not in ids):
            continue
        title = t["title_template"].format(title=m["title"], hashtags=" ".join(t["hashtags"])).strip()
        if a.dry_run:
            log(f"[dry-run] {m['file']}: {title}")
            continue
        pid = tiktok.upload(d / m["file"], t, title)
        m["uploaded"], m["publish_id"] = True, pid
        mpath.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        log(f"{m['file']} hochgeladen (publish_id {pid}, Modus {t['mode']})")


def cmd_auth(a: argparse.Namespace) -> None:
    if not a.code:
        print("Oeffne im Browser und erlaube den Zugriff:\n" + tiktok.auth_url(a.redirect_uri))
        print("\nDann den 'code'-Parameter aus der Redirect-URL kopieren und ausfuehren:\n"
              f"  clipbot tiktok-auth --redirect-uri {a.redirect_uri} --code <CODE>")
        return
    tiktok.exchange_code(a.code, a.redirect_uri)
    log("Login gespeichert (tokens.json).")


def cmd_status(a: argparse.Namespace) -> None:
    print(json.dumps(tiktok.status(a.publish_id), indent=2))


def main() -> None:
    p = argparse.ArgumentParser(prog="clipbot")
    p.add_argument("--config", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="VOD analysieren, Clips schneiden")
    r.add_argument("source", nargs="?", help="Twitch-VOD-URL/ID oder lokale Videodatei")
    r.add_argument("--latest", action="store_true", help="neuestes VOD des konfigurierten Kanals")
    r.add_argument("--vod-id", help="bei lokaler Datei: zugehoerige Twitch-VOD-ID (fuer Chat/Clips)")
    r.add_argument("--no-twitch", action="store_true", help="keine Twitch-APIs (nur Audio-Analyse)")
    r.add_argument("--count", type=int, default=None)
    r.add_argument("--workdir", default="work")
    r.add_argument("--out", default="out")
    r.set_defaults(fn=cmd_run)

    u = sub.add_parser("upload", help="Clips eines Ordners zu TikTok hochladen")
    u.add_argument("dir")
    u.add_argument("--ids", help="nur diese Clip-Nummern, z.B. 1,3")
    u.add_argument("--dry-run", action="store_true")
    u.set_defaults(fn=cmd_upload)

    t = sub.add_parser("tiktok-auth", help="TikTok-Login einrichten")
    t.add_argument("--redirect-uri", required=True)
    t.add_argument("--code")
    t.set_defaults(fn=cmd_auth)

    s = sub.add_parser("tiktok-status", help="Status eines Uploads abfragen")
    s.add_argument("publish_id")
    s.set_defaults(fn=cmd_status)

    a = p.parse_args()
    if a.cmd == "run":
        if not a.source and not a.latest:
            p.error("Quelle angeben oder --latest nutzen")
        if a.count is None:
            a.count = config.load(a.config)["detect"]["clips_per_vod"]
    a.fn(a)


if __name__ == "__main__":
    main()
