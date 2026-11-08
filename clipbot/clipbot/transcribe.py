from __future__ import annotations


class Transcriber:
    def __init__(self, cfg: dict) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:  # pragma: no cover
            raise SystemExit("faster-whisper fehlt: pip install -r requirements.txt") from e
        self.lang = cfg["language"]
        self.model = WhisperModel(cfg["model"], device=cfg["device"], compute_type=cfg["compute_type"])

    def run(self, path: str) -> tuple[list, list]:
        """Gibt (words, segments) zurueck; Zeiten relativ zum Dateianfang."""
        segs, _ = self.model.transcribe(path, language=self.lang, word_timestamps=True,
                                        vad_filter=True, beam_size=1)
        words, segments = [], []
        for s in segs:
            segments.append((s.start, s.end, s.text.strip()))
            for w in s.words or []:
                words.append((w.start, w.end, w.word.strip()))
        return words, segments
