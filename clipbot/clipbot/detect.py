"""Highlight-Erkennung: reine numpy-Logik ohne Netzwerk, daher gut testbar."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Candidate:
    peak: float
    start: float
    end: float
    score: float
    signals: dict = field(default_factory=dict)
    words: list = field(default_factory=list)      # (start, end, text), relativ zum Abschnitt
    segments: list = field(default_factory=list)   # (start, end, text), relativ zum Abschnitt
    section_start: float = 0.0                     # VOD-Zeit, bei der die Abschnittsdatei beginnt
    text: str = ""
    title: str = ""


def robust_z(x: np.ndarray, block: int = 300) -> np.ndarray:
    """Z-Score gegen die lokale Grundlinie (Median/MAD pro Block, interpoliert).
    So zaehlt ein Peak relativ zur gerade herrschenden Stimmung im Stream."""
    x = np.asarray(x, dtype=np.float32)
    n = len(x)
    if n == 0:
        return x
    nb = max(1, n // block)
    edges = np.linspace(0, n, nb + 1, dtype=int)
    centers, med, mad = [], [], []
    for a, b in zip(edges[:-1], edges[1:]):
        seg = x[a:b]
        m = float(np.median(seg))
        centers.append((a + b) / 2)
        med.append(m)
        mad.append(float(np.median(np.abs(seg - m))) * 1.4826)
    idx = np.arange(n)
    base = np.interp(idx, centers, med)
    spread = np.maximum(np.interp(idx, centers, mad), 1e-3)
    return (x - base) / spread


def smooth(x: np.ndarray, win: int) -> np.ndarray:
    if win <= 1 or len(x) == 0:
        return x
    k = np.ones(win, dtype=np.float32) / win
    return np.convolve(x, k, mode="same")


def clip_bumps(offsets: list[float], n: int, sigma: float = 6.0) -> np.ndarray:
    """Gauss-Huegel um jeden Zeitpunkt, an dem Zuschauer einen Twitch-Clip erstellt haben."""
    out = np.zeros(n, dtype=np.float32)
    idx = np.arange(n)
    for o in offsets:
        out += np.exp(-0.5 * ((idx - o) / sigma) ** 2).astype(np.float32)
    return np.minimum(out, 2.0)


def chat_rate(timestamps: list[float], n: int) -> np.ndarray:
    out = np.zeros(n, dtype=np.float32)
    for t in timestamps:
        i = int(t)
        if 0 <= i < n:
            out[i] += 1
    return out


def combine(audio_db: np.ndarray, chat: np.ndarray | None, clip_offsets: list[float],
            w_audio: float, w_chat: float, w_clip: float) -> tuple[np.ndarray, dict]:
    n = len(audio_db)
    # Lautstaerke: kurze Peaks (1-3 s) sind Lachen/Schreien -> leicht glaetten
    za = np.clip(smooth(robust_z(audio_db), 3), 0, 8) / 8
    zc = np.zeros(n, dtype=np.float32)
    if chat is not None and chat.sum() > 0:
        c = chat[:n] if len(chat) >= n else np.pad(chat, (0, n - len(chat)))
        zc = np.clip(smooth(robust_z(smooth(c, 5)), 5), 0, 8) / 8
    zk = clip_bumps(clip_offsets, n) / 2
    total = w_audio * za + w_chat * zc + w_clip * zk
    return total, {"audio": za, "chat": zc, "clips": zk}


def pick_peaks(score: np.ndarray, count: int, min_gap: int) -> list[int]:
    s = smooth(score, 7).copy()
    peaks: list[int] = []
    while len(peaks) < count:
        i = int(np.argmax(s))
        if s[i] <= 0:
            break
        peaks.append(i)
        s[max(0, i - min_gap): i + min_gap + 1] = -1
    return peaks


def make_candidates(score: np.ndarray, parts: dict, total: float, count: int, pre: float, post: float,
                    min_gap: int) -> list[Candidate]:
    out = []
    smoothed = smooth(score, 7)
    for p in pick_peaks(score, count, min_gap):
        sig = {k: round(float(v[max(0, p - 3): p + 4].max()), 3) for k, v in parts.items()}
        out.append(Candidate(peak=float(p), start=max(0.0, p - pre), end=min(total, p + post),
                             score=float(smoothed[p]), signals=sig))
    return out


def text_rescore(c: Candidate, hype_words: list[str], min_words_per_sec: float) -> float:
    """Neu bewerten, nachdem der Abschnitt transkribiert wurde: Sprache + Ausrufe zaehlen."""
    dur = max(c.end - c.start, 1.0)
    in_clip = [w for w in c.words if c.start - c.section_start <= w[0] <= c.end - c.section_start]
    toks = [w[2].lower().strip(".,!?\"' ") for w in in_clip]
    hits = sum(1 for t in toks if t in {h.lower() for h in hype_words})
    rate = len(toks) / dur
    factor = 1.0 + 0.12 * min(hits, 5)
    if rate < min_words_per_sec:
        factor *= 0.5   # fast stumm: selten ein guter Clip
    return c.score * factor


def snap_bounds(c: Candidate, min_len: float, max_len: float, tol: float = 6.0) -> None:
    """Schnitt an Satzgrenzen ausrichten, damit nichts mitten im Wort beginnt/endet."""
    if not c.segments:
        return
    off = c.section_start
    for s, e, _ in c.segments:
        s, e = s + off, e + off
        if s <= c.start <= e and c.start - s <= tol:
            c.start = s
        if s <= c.end <= e and e - c.end <= tol:
            c.end = e
    if c.end - c.start > max_len:
        c.start = c.end - max_len
    if c.end - c.start < min_len:
        c.end = c.start + min_len
