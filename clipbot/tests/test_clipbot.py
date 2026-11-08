import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clipbot import audio, config, detect, render, tiktok  # noqa: E402


class DetectTests(unittest.TestCase):
    def test_finds_audio_bursts(self):
        rng = np.random.default_rng(0)
        db = rng.normal(-35, 1.5, 1800).astype(np.float32)
        for t in (400, 1100):
            db[t:t + 3] += 22
        score, parts = detect.combine(db, None, [], 1, 1.5, 2)
        peaks = detect.pick_peaks(score, 2, 90)
        self.assertEqual(sorted(abs(p - t) <= 4 for p, t in zip(sorted(peaks), (400, 1100))), [True, True])

    def test_clip_offsets_dominate(self):
        db = np.full(1000, -30, dtype=np.float32)
        score, parts = detect.combine(db, None, [600.0], 1, 1.5, 2)
        self.assertLess(abs(detect.pick_peaks(score, 1, 60)[0] - 600), 3)

    def test_chat_spike(self):
        n = 1000
        stamps = [float(i) for i in range(n)] + [500.0 + i * 0.05 for i in range(200)]
        chat = detect.chat_rate(stamps, n)
        score, _ = detect.combine(np.full(n, -30, dtype=np.float32), chat, [], 1, 1.5, 2)
        self.assertLess(abs(detect.pick_peaks(score, 1, 60)[0] - 505), 8)

    def test_snap_and_limits(self):
        c = detect.Candidate(peak=100, start=88, end=110, score=1, section_start=70,
                             segments=[(14.0, 20.0, "a"), (30.0, 41.0, "b")])
        detect.snap_bounds(c, 15, 55)
        self.assertEqual((c.start, c.end), (84.0, 111.0))

    def test_rescore_penalises_silence(self):
        c = detect.Candidate(peak=50, start=40, end=60, score=1.0, section_start=30, words=[])
        self.assertLess(detect.text_rescore(c, ["alter"], 0.25), 1.0)
        c.words = [(10 + i * 0.5, 10.4 + i * 0.5, "Alter") for i in range(20)]
        self.assertGreater(detect.text_rescore(c, ["alter"], 0.25), 1.0)


class ConfigTests(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(config.load("/nonexistent.toml")["twitch"]["channel"], "gtasty")

    def test_chunks(self):
        self.assertEqual(tiktok._chunks(3_000_000), (3_000_000, 1))
        c, n = tiktok._chunks(25 * 1024 * 1024)
        self.assertEqual((c, n), (tiktok.CHUNK, 2))


class RenderTests(unittest.TestCase):
    def test_ass(self):
        ass = render.build_ass([(10.0, 10.3, "Hallo"), (10.3, 10.6, "du"), (10.6, 11.0, "Alter"),
                                (12.0, 12.4, "krass")], 9.0, 20.0, "Arial", 76)
        self.assertIn("HALLO DU ALTER", ass)
        self.assertIn("0:00:01.00", ass)

    def test_end_to_end_render(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=1280x720:r=30:d=12",
                            "-f", "lavfi", "-i", "sine=f=440:d=12", "-shortest", "-pix_fmt", "yuv420p", str(src)],
                           check=True)
            for layout in ("blur", "facecam"):
                cfg = dict(config.DEFAULTS["render"], layout=layout)
                out = Path(td) / f"o_{layout}.mp4"
                render.render(str(src), 2, 10, out, [(3.0, 3.4, "Test"), (3.4, 3.8, "Wort")], cfg)
                size = subprocess.check_output(
                    ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                     "-of", "csv=p=0", str(out)], text=True).strip()
                self.assertEqual(size, "1080,1920")
                self.assertAlmostEqual(audio.duration(str(out)), 8.0, delta=0.5)

    def test_loudness_stream(self):
        with tempfile.TemporaryDirectory() as td:
            wav = Path(td) / "a.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=440:d=5", str(wav)], check=True)
            lv = audio.loudness_per_second(str(wav))
            self.assertEqual(len(lv), 5)


if __name__ == "__main__":
    unittest.main()
