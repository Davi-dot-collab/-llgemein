import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clipbot import audio, config, detect, live, render  # noqa: E402


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


class LiveTests(unittest.TestCase):
    def _hist(self, spike_at, n=400, chat=True):
        rng = np.random.default_rng(1)
        a = rng.normal(-35, 1.5, n).astype(np.float32)
        c = rng.poisson(3, n).astype(np.float32)
        a[spike_at:spike_at + 4] += 20
        if chat:
            c[spike_at - 1:spike_at + 6] += 40
        return a, c

    def test_trigger_after_postroll(self):
        a, c = self._hist(350)
        pk, v = detect.live_peak(a, c, 1000, 1, 1.5, 0.9, 0.6, 10, 90, -1e9)
        self.assertIsNotNone(pk)
        self.assertLess(abs(pk - 1353), 6)

    def test_no_trigger_while_fresh(self):
        a, c = self._hist(395, n=400)
        pk, _ = detect.live_peak(a, c, 1000, 1, 1.5, 0.9, 0.6, 10, 90, -1e9)
        self.assertIsNone(pk)

    def test_no_trigger_in_quiet_or_cooldown(self):
        rng = np.random.default_rng(2)
        a = rng.normal(-35, 1.5, 400).astype(np.float32)
        c = rng.poisson(3, 400).astype(np.float32)
        self.assertIsNone(detect.live_peak(a, c, 1000, 1, 1.5, 0.9, 0.6, 10, 90, -1e9)[0])
        a, c = self._hist(350)
        self.assertIsNone(detect.live_peak(a, c, 1000, 1, 1.5, 0.9, 0.6, 10, 90, 1340)[0])

    def test_audio_only_fallback(self):
        a, c = self._hist(350, chat=False)
        pk, _ = detect.live_peak(a, np.zeros(400, dtype=np.float32), 1000, 1, 1.5, 0.9, 0.6, 10, 90, -1e9)
        self.assertIsNotNone(pk)

    def test_irc_classify(self):
        self.assertEqual(live.classify("PING :tmi.twitch.tv"), "ping::tmi.twitch.tv")
        self.assertEqual(live.classify(":a!a@a.tmi.twitch.tv PRIVMSG #x :KEKW"), "msg")
        self.assertEqual(live.classify(":tmi.twitch.tv 001 x :Welcome"), "other")

    @unittest.skipUnless(hasattr(__import__('time'), 'tzset'), 'tzset nur unter Unix')
    def test_seg_start_is_local_time(self):
        import os, time
        old = os.environ.get("TZ")
        os.environ["TZ"] = "Europe/Berlin"
        time.tzset()
        try:
            t = live.seg_start(Path("seg_20260115_120000.ts"))
            self.assertEqual(time.strftime("%H:%M:%S", time.localtime(t)), "12:00:00")
        finally:
            if old is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = old
            time.tzset()

    def test_segments_concat(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            for i in range(3):
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=320x240:r=15:d=4",
                                "-f", "lavfi", "-i", "sine=d=4", "-shortest", "-pix_fmt", "yuv420p",
                                "-f", "mpegts", str(td / f"seg_20260101_0000{i * 4:02d}.ts")], check=True)
            segs = sorted((live.seg_start(p), p) for p in td.glob("seg_*.ts"))
            first = live.concat_segments(segs, segs[0][0] + 1, segs[2][0] + 1, 4, td / "cut.ts")
            self.assertEqual(first, segs[0][0])
            self.assertAlmostEqual(audio.duration(str(td / "cut.ts")), 12.0, delta=0.6)


class ConfigTests(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(config.load("/nonexistent.toml")["twitch"]["channel"], "gtasty")


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
