import http.client
import json
import socket
import sys
import tempfile
import threading
import time
import tomllib
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clipbot import chatmood, config, live, ui  # noqa: E402


class MoodTests(unittest.TestCase):
    def test_classify(self):
        self.assertIn("laugh", chatmood.classify_text("HAHAHAHAHA"))
        self.assertIn("laugh", chatmood.classify_text("KEKW"))
        self.assertIn("laugh", chatmood.classify_text("ahahahaha"))
        self.assertIn("shock", chatmood.classify_text("WTF?!?"))
        self.assertIn("shock", chatmood.classify_text("was???"))
        self.assertIn("clip", chatmood.classify_text("CLIP IT"))
        for neutral in ("hallo zusammen", "gg", "Hannah", "hahn"):
            self.assertEqual(chatmood.classify_text(neutral), set(), neutral)

    def test_parse_privmsg(self):
        self.assertEqual(chatmood.parse_privmsg(":n!n@n.tmi.twitch.tv PRIVMSG #gtasty :HAHA gut"), ("n", "HAHA gut"))
        self.assertIsNone(chatmood.parse_privmsg(":tmi.twitch.tv 001 x :Welcome"))

    def test_counter_tags_and_spam(self):
        c = live.ChatCounter("x")
        c.add("HAHAHA", now=100)
        c.add("hahaha", now=102)      # gleicher Text kurz danach -> Spam
        c.add("wtf", now=103)
        a = c.arrays(100, 5)
        self.assertEqual(a["msg"].sum(), 3)
        self.assertEqual(a["laugh"].sum(), 2)
        self.assertEqual(a["spam"].sum(), 1)
        self.assertEqual(a["shock"].sum(), 1)
        self.assertEqual(c.recent_messages()[-1]["tags"], ["shock"])

    def test_reason(self):
        n = 60
        arrs = {k: np.zeros(n, dtype=np.float32) for k in chatmood.CATS}
        arrs["msg"][:] = 2
        arrs["msg"][30:36] = 20
        arrs["laugh"][30:36] = 15
        why = chatmood.reason(arrs, 32)
        self.assertIn("Lachen", why)
        self.assertIn("schneller", why)


class ConfigTests(unittest.TestCase):
    def test_roundtrip_and_coerce(self):
        cfg = config.load("/nonexistent.toml")
        self.assertEqual(tomllib.loads(config.dumps(cfg)), cfg)
        inc = {"twitch": {"channel": "abc", "use_chat": "false"}, "detect": {"min_gap": "45.0", "hype_words": "a, b ,,c"},
               "evil": {"x": 1}}
        out = config.coerce(config.DEFAULTS, inc)
        self.assertEqual(out["twitch"]["channel"], "abc")
        self.assertIs(out["twitch"]["use_chat"], False)
        self.assertEqual(out["detect"]["min_gap"], 45)
        self.assertEqual(out["detect"]["hype_words"], ["a", "b", "c"])
        self.assertNotIn("evil", out)


class UiServerTests(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        (self.td / "out" / "live").mkdir(parents=True)
        (self.td / "out" / "live" / "clip_001.mp4").write_bytes(bytes(range(100)))
        (self.td / "out" / "live" / "manifest.json").write_text(
            json.dumps([{"file": "clip_001.mp4", "title": "Test", "reason": "Lachen x9"}]))
        (self.td / "secret.mp4").write_bytes(b"geheim")
        s = socket.socket(); s.bind(("127.0.0.1", 0)); self.port = s.getsockname()[1]; s.close()
        mgr = ui.Manager(self.td / "config.toml", self.td / "work", self.td / "out")
        html = Path(ui.__file__).with_name("ui.html").read_bytes()
        self.srv = ThreadingHTTPServer(("127.0.0.1", self.port), ui.make_handler(mgr, html, self.port))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.mgr = mgr

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close()

    def req(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = dict(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body); h.setdefault("Content-Type", "application/json")
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        try:
            return r.status, r.read(), dict(r.getheaders())
        finally:
            c.close()

    def test_pages_and_state(self):
        st, body, _ = self.req("GET", "/")
        self.assertEqual(st, 200)
        self.assertIn(b"Clipbot", body)
        st, body, _ = self.req("GET", "/api/state")
        j = json.loads(body)
        self.assertEqual(j["config"]["twitch"]["channel"], "gtasty")
        self.assertFalse(j["running"])

    def test_post_needs_header_and_host(self):
        st, _, _ = self.req("POST", "/api/config", {"twitch": {"channel": "x"}})
        self.assertEqual(st, 403)
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", "/api/state", headers={"Host": "evil.example"})
        self.assertEqual(c.getresponse().status, 403)
        c.close()

    def test_save_config(self):
        st, body, _ = self.req("POST", "/api/config", {"twitch": {"channel": "neuerstreamer"}}, {"X-Clipbot": "1"})
        self.assertEqual(st, 200)
        saved = tomllib.loads((self.td / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual(saved["twitch"]["channel"], "neuerstreamer")
        self.assertIn("detect", saved)

    def test_clips_and_range(self):
        st, body, _ = self.req("GET", "/api/clips")
        items = json.loads(body)
        self.assertEqual(items[0]["url"], "/media/live/clip_001.mp4")
        st, body, h = self.req("GET", "/media/live/clip_001.mp4", headers={"Range": "bytes=10-19"})
        self.assertEqual((st, body), (206, bytes(range(10, 20))))
        self.assertEqual(h["Content-Range"], "bytes 10-19/100")
        self.assertEqual(self.req("GET", "/media/live/clip_001.mp4")[1], bytes(range(100)))
        self.assertEqual(self.req("GET", "/media/../secret.mp4")[0], 404)
        self.assertEqual(self.req("GET", "/media/%2e%2e/secret.mp4")[0], 404)

    def test_unknown_mode(self):
        st, body, _ = self.req("POST", "/api/start", {"mode": "quatsch"}, {"X-Clipbot": "1"})
        self.assertFalse(json.loads(body)["ok"])


class _FakeChat(live.ChatCounter):
    def run(self):  # kein Netzwerk
        self.connected = True


class ChatOnlyRunTest(unittest.TestCase):
    def test_burst_is_reported_with_reason(self):
        td = Path(tempfile.mkdtemp())
        cfg = config.load("/nonexistent.toml")
        cfg["live"].update(min_history_s=6, history_s=60, poll_s=0.5)
        cfg["detect"].update(post_roll=3, min_gap=30)
        orig = live.ChatCounter
        holder = {}

        def make(channel):
            holder["c"] = _FakeChat(channel)
            return holder["c"]
        live.ChatCounter = make
        try:
            t = threading.Thread(target=live.run_live, args=(cfg, "test", td / "w", td / "o"),
                                 kwargs={"chat_only": True}, daemon=True)
            t.start()
            while "c" not in holder:
                time.sleep(0.05)
            chat = holder["c"]
            status = td / "w" / "live_status.json"
            t0 = time.time()
            i = 0
            peaks = []
            while time.time() - t0 < 60 and not peaks:
                el = time.time() - t0
                for _ in range(25 if 14 <= el < 18 else 2):
                    chat.add("HAHAHA" if 14 <= el < 18 and i % 2 else f"nachricht {i}")
                    i += 1
                time.sleep(1 / 25 if 14 <= el < 18 else 0.5)
                if status.exists():
                    try:
                        peaks = json.loads(status.read_text(encoding="utf-8")).get("peaks", [])
                    except ValueError:
                        pass
            (td / "w" / "live.stop").write_text("stop")
            t.join(15)
            self.assertTrue(peaks, "kein Highlight gemeldet")
            self.assertEqual(peaks[0]["action"], "nur gemeldet")
            self.assertIn("Lachen", peaks[0]["reason"])
            self.assertEqual(json.loads(status.read_text(encoding="utf-8"))["state"], "stopped")
        finally:
            live.ChatCounter = orig


if __name__ == "__main__":
    unittest.main()
