from __future__ import annotations

import subprocess

import numpy as np

SR = 16000


def duration(path: str) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], text=True)
    return float(out.strip())


def loudness_per_second(path: str) -> np.ndarray:
    """RMS-Pegel in dB pro Sekunde, gestreamt ueber ffmpeg (RAM-schonend auch bei 8h-VODs)."""
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    levels: list[float] = []
    buf = b""
    step = SR * 2  # Bytes pro Sekunde
    chunk = step * 60
    assert proc.stdout is not None
    while True:
        data = proc.stdout.read(chunk)
        if not data:
            break
        buf += data
        n = len(buf) // step
        if n:
            arr = np.frombuffer(buf[: n * step], dtype=np.int16).astype(np.float32) / 32768.0
            arr = arr.reshape(n, SR)
            rms = np.sqrt((arr ** 2).mean(axis=1) + 1e-12)
            levels.extend((20 * np.log10(rms)).tolist())
            buf = buf[n * step:]
    proc.stdout.close()
    proc.wait()
    if proc.returncode:
        raise RuntimeError(f"ffmpeg beim Audio-Lesen fehlgeschlagen ({proc.returncode})")
    return np.asarray(levels, dtype=np.float32)
