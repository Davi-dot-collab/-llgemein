"""Clips-Modus: fertige Zuschauer-Clips eines Kanals laden und hochkant mit Untertiteln rendern."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from . import audio, render


def list_clips(channel: str, days: int, count: int) -> list[dict]:
    rng = {1: "24hr", 7: "7d", 30: "30d"}.get(days, "all" if days > 30 else "7d")
    url = f"https://www.twitch.tv/{channel}/clips?filter=clips&range={rng}"
    out = subprocess.check_output(["yt-dlp", "--flat-playlist", "-J", "--playlist-end", str(count), url],
                                  text=True)
    return [{"url": e.get("url") or e.get("webpage_url"), "title": e.get("title", ""), "id": e.get("id")}
            for e in json.loads(out).get("entries", [])]


def run_clips(cfg: dict, channel: str, days: int, count: int, workdir: Path, out_dir: Path) -> None:
    from .transcribe import Transcriber
    workdir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    clips = list_clips(channel, days, count)
    print(f"[clipbot] {len(clips)} Clips gefunden")
    tr = Transcriber(cfg["transcribe"])
    manifest = []
    for i, c in enumerate(clips, 1):
        src = workdir / f"clip_{c['id'] or i}.mp4"
        if not src.exists():
            subprocess.run(["yt-dlp", "--no-progress", "--quiet", "-f", cfg["twitch"]["video_format"],
                            "--merge-output-format", "mp4", "-o", str(src), c["url"]], check=True)
        words, _ = tr.run(str(src))
        name = f"clip_{i:02d}.mp4"
        render.render(str(src), 0.0, audio.duration(str(src)), out_dir / name, words, cfg["render"])
        title = re.sub(r"\s+", " ", c["title"]).strip()
        manifest.append({"file": name, "title": title, "source": c["url"]})
        print(f"[clipbot] {name}: {title}")
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"[clipbot] Fertig: {out_dir}")
