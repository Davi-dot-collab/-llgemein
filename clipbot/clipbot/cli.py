from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import numpy as np

from . import audio, config, detect, render, twitch


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
    have_keys = bool(os.environ.get("TWITCH_CLIENT_ID") and os.environ.get("TWITCH_CLIENT_SECRET"))
    if not local:
        if a.latest and not have_keys:
            raise SystemExit("--latest braucht Twitch-Keys. Ohne Keys: VOD-URL angeben.")
        vod_id = twitch.parse_vod_id(a.source) if a.source else None
        if have_keys:
            helix = twitch.Helix()
            vod = helix.latest_vod(tw["channel"]) if a.latest else helix.vod(vod_id or "")
            vod_id = vod["id"]
        elif not vod_id:
            raise SystemExit("Keine gueltige VOD-URL/ID oder Datei.")
        else:
            vod = {"id": vod_id}
        log(f"VOD {vod_id}: {vod.get('title', '')}")
        src_audio = str(twitch.download_audio(vod_id, work))
    else:
        vod_id = a.vod_id or Path(a.source).stem
        src_audio = a.source
        if a.vod_id:
            vod = {"id": a.vod_id}
            helix = twitch.Helix() if have_keys else None

    log("Analysiere Audio ...")
    level = audio.loudness_per_second(src_audio)
    total = float(len(level))

    chat = None
    if tw["use_chat"] and vod and not a.no_chat:
        try:
            log("Lade Chat-Replay ...")
            chat = detect.chat_rate(twitch.chat_timestamps(vod["id"]), len(level))
            log(f"{int(chat.sum())} Chatnachrichten")
        except Exception as e:  # inoffizielle Schnittstelle: nie hart scheitern
            log(f"Chat nicht verfuegbar ({e}); weiter ohne Chat.")
    offsets: list[float] = []
    if tw["use_twitch_clips"] and helix and vod.get("user_id"):
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
                         })
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    log(f"Fertig: {out_dir} ({len(manifest)} Clips). Titel/Scores stehen in manifest.json.")


def cmd_live(a: argparse.Namespace) -> None:
    from . import live
    cfg = config.load(a.config)
    live.run_live(cfg, a.channel or cfg["twitch"]["channel"], Path(a.workdir), Path(a.out) / "live",
                  source=a.source, dry_run=a.dry_run, threshold=a.threshold)


def cmd_clips(a: argparse.Namespace) -> None:
    from . import clipsmode
    cfg = config.load(a.config)
    ch = a.channel or cfg["twitch"]["channel"]
    clipsmode.run_clips(cfg, ch, a.days, a.count, Path(a.workdir), Path(a.out) / f"clips_{ch}")


def main() -> None:
    p = argparse.ArgumentParser(prog="clipbot")
    p.add_argument("--config", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="VOD analysieren, Clips schneiden")
    r.add_argument("source", nargs="?", help="Twitch-VOD-URL/ID oder lokale Videodatei")
    r.add_argument("--latest", action="store_true", help="neuestes VOD des konfigurierten Kanals")
    r.add_argument("--vod-id", help="bei lokaler Datei: zugehoerige Twitch-VOD-ID (fuer Chat/Clips)")
    r.add_argument("--no-chat", action="store_true", help="Chat-Replay nicht laden (nur Audio-Analyse)")
    r.add_argument("--count", type=int, default=None)
    r.add_argument("--workdir", default="work")
    r.add_argument("--out", default="out")
    r.set_defaults(fn=cmd_run)

    lv = sub.add_parser("live", help="Stream live mitschneiden und Highlights sofort schneiden")
    lv.add_argument("channel", nargs="?")
    lv.add_argument("--threshold", type=float)
    lv.add_argument("--dry-run", action="store_true", help="nur melden, nichts schneiden (zum Einstellen)")
    lv.add_argument("--source", help="Test: lokale Datei/URL statt Twitch-Stream")
    lv.add_argument("--workdir", default="work")
    lv.add_argument("--out", default="out")
    lv.set_defaults(fn=cmd_live)

    cl = sub.add_parser("clips", help="Zuschauer-Clips eines Kanals laden und hochkant rendern")
    cl.add_argument("channel", nargs="?")
    cl.add_argument("--days", type=int, default=7)
    cl.add_argument("--count", type=int, default=10)
    cl.add_argument("--workdir", default="work")
    cl.add_argument("--out", default="out")
    cl.set_defaults(fn=cmd_clips)

    a = p.parse_args()
    if a.cmd == "run":
        if not a.source and not a.latest:
            p.error("Quelle angeben oder --latest nutzen")
        if a.count is None:
            a.count = config.load(a.config)["detect"]["clips_per_vod"]
    a.fn(a)


if __name__ == "__main__":
    main()
