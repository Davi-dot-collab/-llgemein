from __future__ import annotations

import copy
import json
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
    "live": {
        "threshold": 0.9, "audio_only_threshold": 0.6, "history_s": 600, "min_history_s": 120,
        "buffer_min": 20, "segment_s": 10, "poll_s": 3, "webhook": "", "mood_weight": 2.0,
    },
    "transcribe": {"model": "small", "device": "cpu", "compute_type": "int8", "language": "de"},
    "render": {
        "layout": "blur",
        "facecam": {"x": 0.0, "y": 0.7, "w": 0.25, "h": 0.3},
        "subtitles": True, "font": "Arial", "font_size": 76,
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


def _v(x) -> str:
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, (int, float)):
        return repr(x)
    if isinstance(x, str):
        return json.dumps(x, ensure_ascii=False)
    if isinstance(x, list):
        return "[" + ", ".join(_v(i) for i in x) + "]"
    if isinstance(x, dict):
        return "{ " + ", ".join(f"{k} = {_v(v)}" for k, v in x.items()) + " }"
    raise TypeError(type(x))


def dumps(cfg: dict) -> str:
    out = []
    for section, vals in cfg.items():
        out.append(f"[{section}]")
        out += [f"{k} = {_v(v)}" for k, v in vals.items()]
        out.append("")
    return "\n".join(out)


def coerce(defaults: dict, incoming: dict) -> dict:
    """Uebernimmt nur bekannte Schluessel aus `incoming` und wandelt auf den Typ des Standardwerts."""
    out = {}
    for k, dv in defaults.items():
        if k not in incoming:
            out[k] = copy.deepcopy(dv)
            continue
        v = incoming[k]
        if isinstance(dv, dict):
            out[k] = coerce(dv, v if isinstance(v, dict) else {})
        elif isinstance(dv, bool):
            out[k] = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "on", "ja")
        elif isinstance(dv, int):
            out[k] = int(float(v))
        elif isinstance(dv, float):
            out[k] = float(v)
        elif isinstance(dv, list):
            items = v if isinstance(v, list) else str(v).split(",")
            out[k] = [str(i).strip() for i in items if str(i).strip()]
        else:
            out[k] = str(v)
    return out


def save(cfg: dict, path: str | Path) -> None:
    clean = coerce(DEFAULTS, cfg)
    Path(path).write_text(dumps(clean), encoding="utf-8")
