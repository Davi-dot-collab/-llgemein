from __future__ import annotations

import copy
import os
import tomllib
from pathlib import Path

DEFAULTS: dict = {
    "twitch": {
        "channel": "gtasty",
        "video_format": "720p60/720p/best[height<=720]/best",
        "use_chat": True,
        "use_twitch_clips": True,
    },
    "detect": {
        "weight_audio": 1.0, "weight_chat": 1.5, "weight_clip": 2.0,
        "pre_roll": 22, "post_roll": 10, "min_len": 15, "max_len": 55,
        "min_gap": 90, "clips_per_vod": 6, "overgenerate": 2.0,
        "min_words_per_sec": 0.25,
        "hype_words": ["alter", "digga", "bruder", "nein", "krass", "wtf", "lol", "haha"],
    },
    "transcribe": {"model": "small", "device": "cpu", "compute_type": "int8", "language": "de"},
    "render": {
        "layout": "blur",
        "facecam": {"x": 0.0, "y": 0.7, "w": 0.25, "h": 0.3},
        "subtitles": True, "font": "Arial", "font_size": 76,
    },
    "tiktok": {
        "mode": "inbox", "privacy_level": "SELF_ONLY",
        "hashtags": ["#gtasty", "#gta", "#fyp"], "title_template": "{title} {hashtags}",
    },
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path: str | Path | None = None) -> dict:
    p = Path(path) if path else Path("config.toml")
    if p.exists():
        with p.open("rb") as f:
            return _merge(DEFAULTS, tomllib.load(f))
    return copy.deepcopy(DEFAULTS)


def env(name: str) -> str:
    v = os.environ.get(name, "")
    if not v:
        raise SystemExit(f"Umgebungsvariable {name} fehlt.")
    return v
