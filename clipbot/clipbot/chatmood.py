"""Chat-Stimmung: erkennt Lachen, Schock, Clip-Rufe und Spam in einzelnen Chatnachrichten."""
from __future__ import annotations

import re

import numpy as np

LAUGH = re.compile(
    r"(?:\b(?:h[aeä]){2,}|(?:j[aä]){3,}|\ba(?:ha){2,}|\bl+o+l+\b|\blmf?ao+\b|\bkekw?\w*|\blul\w*|"
    r"\bomegalul\b|\bicant\b|\bxd+\b|😂|🤣|\bwheeze\b|\bdead\b|\bam tot\b|\bich kann nicht mehr\b)", re.I)
SHOCK = re.compile(
    r"(?:\bomg\b|\bwtf\b|\bwth\b|\bwas\s*\?+|\bwie\s*\?+|\bh[aä]+\s*\?+|\bwas\s+(?:zur|geht|ist\s+das)\b|"
    r"\bpog\w*|\bsheesh\b|\bwahnsinn\b|\bkrass\b|\bno\s*way\b|\bmonka\w*|\bwut\b|\bcrazy\b|\bwhat\b\s*\?*|"
    r"😱|😮|🤯|😳|[?!]{3,}|\bnein{2,}\b|\bnooo+\b)", re.I)
CLIP = re.compile(r"\bclip\w*\b", re.I)
PRIVMSG = re.compile(r"^(?:@\S+ )?:([^!\s]+)![^ ]+ PRIVMSG #\S+ :(.*)$")


def parse_privmsg(line: str) -> tuple[str, str] | None:
    m = PRIVMSG.match(line.strip())
    return (m.group(1), m.group(2)) if m else None


def classify_text(text: str) -> set[str]:
    tags = set()
    if LAUGH.search(text):
        tags.add("laugh")
    if SHOCK.search(text):
        tags.add("shock")
    if CLIP.search(text):
        tags.add("clip")
    return tags


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


CATS = ("msg", "laugh", "shock", "clip", "spam")
LABELS = {"laugh": "Lachen", "shock": "Schock", "clip": "Clip-Rufe", "spam": "Spam"}


def chat_signal(arrs: dict[str, np.ndarray], mood_weight: float) -> np.ndarray:
    """Ein Wert pro Sekunde: Nachrichtentempo + Stimmung (Lachen/Schock) + Clip-Rufe + Spam."""
    return (arrs["msg"] + mood_weight * (arrs["laugh"] + arrs["shock"])
            + 3.0 * arrs["clip"] + 0.5 * arrs["spam"]).astype(np.float32)


def reason(arrs: dict[str, np.ndarray], idx: int, span: int = 6) -> str:
    """Kurze Erklaerung, was der Bot im Chat gesehen hat (um den Index herum, gegen den Normalwert)."""
    lo, hi = max(0, idx - span), min(len(arrs["msg"]), idx + span + 1)
    parts = []
    base = max(float(np.median(arrs["msg"])), 0.5)
    rate = float(arrs["msg"][lo:hi].mean())
    if rate / base >= 1.5:
        parts.append(f"Chat {rate / base:.1f}x schneller als normal")
    for cat, label in LABELS.items():
        n = int(arrs[cat][lo:hi].sum())
        if n >= 3:
            parts.append(f"{label} x{n}")
    return ", ".join(parts)
