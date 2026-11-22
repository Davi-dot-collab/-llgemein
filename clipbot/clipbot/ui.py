"""Lokale Weboberflaeche: Einstellungen, Start/Stopp, Live-Anzeige, Clip-Galerie.

Laeuft nur auf 127.0.0.1. Der Bot selbst laeuft als eigener Prozess (python -m clipbot live ...),
die Oberflaeche liest nur seine Status-Datei.
"""
from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import config


class Manager:
    """Startet/stoppt den Bot-Prozess."""

    def __init__(self, config_path: Path, workdir: Path, out: Path) -> None:
        self.config_path, self.workdir, self.out = config_path, workdir, out
        self.proc: subprocess.Popen | None = None
        self.mode = ""
        self.lock = threading.Lock()
        self.log_path = workdir / "bot.log"

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, mode: str, opts: dict) -> str:
        with self.lock:
            if self.running():
                return "Der Bot laeuft bereits."
            self.workdir.mkdir(parents=True, exist_ok=True)
            cmd = [sys.executable, "-m", "clipbot", "--config", str(self.config_path)]
            if mode == "live":
                cmd += ["live", "--workdir", str(self.workdir), "--out", str(self.out)]
                if opts.get("dry_run"):
                    cmd += ["--dry-run"]
            elif mode == "chat":
                cmd += ["live", "--chat-only", "--workdir", str(self.workdir), "--out", str(self.out)]
            elif mode == "clips":
                cmd += ["clips", "--days", str(int(opts.get("days", 7))), "--count", str(int(opts.get("count", 10))),
                        "--workdir", str(self.workdir), "--out", str(self.out)]
            else:
                return "Unbekannter Modus."
            (self.workdir / "live_status.json").unlink(missing_ok=True)
            log = open(self.log_path, "a", encoding="utf-8", buffering=1)
            log.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} Start: {mode} ===\n")
            env = {**os.environ, "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"}
            self.proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=env,
                                         cwd=str(self.config_path.resolve().parent))
            self.mode = mode
            return ""

    def stop(self) -> None:
        with self.lock:
            if not self.running():
                return
            if self.mode in ("live", "chat"):
                (self.workdir / "live.stop").write_text("stop")   # sauberes Beenden (ffmpeg, laufende Clips)
                try:
                    self.proc.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    pass
            if self.running():
                self.proc.terminate()

    def log_tail(self, n: int = 40) -> list[str]:
        try:
            return self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
        except OSError:
            return []


def list_clips(out: Path) -> list[dict]:
    items = []
    for mpath in out.rglob("manifest.json"):
        try:
            data = json.loads(mpath.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        folder = mpath.parent
        for m in data:
            f = folder / m.get("file", "")
            if f.exists():
                items.append({**m, "url": "/media/" + f.relative_to(out).as_posix(), "mtime": f.stat().st_mtime,
                              "folder": folder.relative_to(out).as_posix()})
    return sorted(items, key=lambda x: x["mtime"], reverse=True)[:60]


def make_handler(mgr: Manager, html: bytes, port: int):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a) -> None:  # leise
            pass

        def _send(self, code: int, body: bytes, ctype: str = "application/json", extra: dict | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

        def _host_ok(self) -> bool:
            return self.headers.get("Host", "") in allowed_hosts

        def do_GET(self) -> None:
            if not self._host_ok():
                return self._send(403, b"forbidden", "text/plain")
            path = urlparse(self.path).path
            if path == "/":
                return self._send(200, html, "text/html; charset=utf-8")
            if path == "/api/state":
                return self._json(self._state())
            if path == "/api/clips":
                return self._json(list_clips(mgr.out))
            if path.startswith("/media/"):
                return self._media(unquote(path[len("/media/"):]))
            self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:
            if not self._host_ok() or self.headers.get("X-Clipbot") != "1":
                self.close_connection = True   # Body wurde nicht gelesen
                return self._send(403, b"forbidden", "text/plain")
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self._json({"error": "ungueltiges JSON"}, 400)
            path = urlparse(self.path).path
            if path == "/api/config":
                try:
                    config.save(body, mgr.config_path)
                except (TypeError, ValueError) as e:
                    return self._json({"error": f"Ungueltige Eingabe: {e}"}, 400)
                return self._json({"ok": True, "config": config.load(mgr.config_path)})
            if path == "/api/start":
                err = mgr.start(str(body.get("mode", "")), body)
                return self._json({"ok": not err, "error": err})
            if path == "/api/stop":
                threading.Thread(target=mgr.stop, daemon=True).start()
                return self._json({"ok": True})
            self._send(404, b"not found", "text/plain")

        def _state(self) -> dict:
            status = None
            sp = mgr.workdir / "live_status.json"
            try:
                status = json.loads(sp.read_text(encoding="utf-8"))
                if mgr.running() is False and status.get("state") != "stopped":
                    status["state"] = "stopped"
            except (OSError, ValueError):
                pass
            return {"config": config.load(mgr.config_path), "running": mgr.running(), "mode": mgr.mode,
                    "status": status, "log": mgr.log_tail(), "now": time.time()}

        def _media(self, rel: str) -> None:
            f = (mgr.out / rel).resolve()
            if mgr.out.resolve() not in f.parents or f.suffix.lower() != ".mp4" or not f.is_file():
                return self._send(404, b"not found", "text/plain")
            size = f.stat().st_size
            start, end, code = 0, size - 1, 200
            rng = self.headers.get("Range", "")
            if rng.startswith("bytes="):
                a, _, b = rng[6:].partition("-")
                try:
                    start = int(a) if a else max(size - int(b), 0)
                    end = int(b) if (a and b) else size - 1
                    code = 206
                except ValueError:
                    pass
            end = min(end, size - 1)
            if start > end:
                return self._send(416, b"", "text/plain", {"Content-Range": f"bytes */{size}"})
            self.send_response(code)
            self.send_header("Content-Type", mimetypes.guess_type(f.name)[0] or "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if code == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with f.open("rb") as fh:
                fh.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = fh.read(min(1 << 20, left))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    left -= len(chunk)

    return H


def serve(port: int, config_path: Path, workdir: Path, out: Path, open_browser: bool = True) -> None:
    html = Path(__file__).with_name("ui.html").read_bytes()
    mgr = Manager(config_path, workdir, out)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(mgr, html, port))
    url = f"http://127.0.0.1:{port}/"
    print(f"[clipbot] Oberflaeche: {url}  (Strg+C beendet sie und den Bot)", flush=True)
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        mgr.stop()
        server.server_close()
