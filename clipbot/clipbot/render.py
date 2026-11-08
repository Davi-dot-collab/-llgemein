from __future__ import annotations

import subprocess
from pathlib import Path

W, H = 1080, 1920
GAME_ASPECT = 1080 / 1280


def _ass_time(t: float) -> str:
    h, rem = divmod(max(t, 0.0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def build_ass(words: list, clip_start: float, clip_end: float, font: str, size: int) -> str:
    """Untertitel in 3-Wort-Haeppchen (TikTok-Stil). `words` relativ zur Videodatei."""
    ws = [(s - clip_start, e - clip_start, t) for s, e, t in words if clip_start <= s < clip_end]
    head = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
        "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BackColour,Bold,"
        "Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
        "Alignment,MarginL,MarginR,MarginV,Encoding\n"
        f"Style: Default,{font},{size},&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,6,2,2,60,60,520,1\n\n"
        "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    )
    lines, i = [], 0
    while i < len(ws):
        grp = ws[i: i + 3]
        i += 3
        end = max(grp[-1][1], grp[0][0] + 0.4)
        if i < len(ws):
            end = min(end + 0.15, ws[i][0])
        text = " ".join(t for _, _, t in grp).replace("\n", " ").replace("{", "(").replace("}", ")")
        lines.append(f"Dialogue: 0,{_ass_time(grp[0][0])},{_ass_time(end)},Default,,0,0,0,,{text.upper()}")
    return head + "\n".join(lines) + "\n"


def filter_graph(layout: str, facecam: dict, subs_file: str | None) -> str:
    if layout == "facecam":
        f = facecam
        g = (
            "[0:v]split=2[a][b];"
            f"[a]crop=iw*{f['w']}:ih*{f['h']}:iw*{f['x']}:ih*{f['y']},"
            f"scale={W}:640:force_original_aspect_ratio=increase,crop={W}:640[cam];"
            f"[b]crop=trunc(ih*{GAME_ASPECT}/2)*2:ih:(iw-trunc(ih*{GAME_ASPECT}/2)*2)/2:0,"
            f"scale={W}:1280[game];[cam][game]vstack[v0]"
        )
    else:
        g = (
            "[0:v]split=2[a][b];"
            f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:5[bg];"
            f"[b]scale={W}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[v0]"
        )
    if subs_file:
        return g + f";[v0]subtitles={subs_file}[v]"
    return g + ";[v0]null[v]"


def render(src: str, start: float, end: float, out: Path, words: list, rcfg: dict) -> Path:
    """Schneidet [start,end] (Sek. in `src`) auf 1080x1920 mit optionalen Untertiteln."""
    out = out.resolve()
    workdir = out.parent
    subs_name = None
    if rcfg["subtitles"] and words:
        subs_name = out.with_suffix(".ass").name
        (workdir / subs_name).write_text(build_ass(words, start, end, rcfg["font"], rcfg["font_size"]),
                                         encoding="utf-8")
    g = filter_graph(rcfg["layout"], rcfg["facecam"], subs_name)
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(Path(src).resolve()), "-ss", f"{start:.2f}",
           "-t", f"{end - start:.2f}", "-filter_complex", g, "-map", "[v]", "-map", "0:a?",
           "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out.name]
    subprocess.run(cmd, check=True, cwd=workdir)
    return out
