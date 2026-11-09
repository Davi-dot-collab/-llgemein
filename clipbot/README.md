# clipbot

Sucht lustige/virale Momente in Streams und schneidet sie als 9:16-Clips mit Untertiteln. Der Upload (z. B. TikTok) passiert von Hand, das Programm braucht **keine Accounts und keine API-Keys**.

## Modi

| Befehl | Wofür |
|---|---|
| `live <kanal>` | Stream live mitschneiden, Chat + Lautstärke beobachten, Highlights sofort schneiden (für Kanäle ohne VODs) |
| `clips <kanal>` | Fertige Zuschauer-Clips des Kanals laden und hochkant mit Untertiteln rendern |
| `run <vod-url\|datei>` | Eine VOD-URL oder Videodatei analysieren und die besten Stellen schneiden |

Gemeinsam: faster-whisper (lokal) für Untertitel und Schnitt an Satzgrenzen, ffmpeg für 1080x1920 (Gameplay auf unscharfem Hintergrund oder Facecam oben / Game unten).

## Setup

```bash
cd clipbot
pip install -r requirements.txt     # ffmpeg muss installiert sein
cp config.example.toml config.toml  # Kanal, Layout, Schwellen anpassen
```

## Benutzung

```bash
# Live: laeuft waehrend des Streams (wartet, bis der Kanal live geht)
python -m clipbot live gtasty --dry-run     # erst nur melden, nichts schneiden: Schwelle einstellen
python -m clipbot live gtasty               # Clips landen in out/live/
python -m clipbot live gtasty --threshold 1.1   # weniger, dafuer bessere Treffer

# Zuschauer-Clips der letzten 7 Tage
python -m clipbot clips gtasty --days 7 --count 10    # Ergebnis: out/clips_gtasty/

# VOD oder Datei
python -m clipbot run https://www.twitch.tv/videos/123456789 --count 5
python -m clipbot run aufnahme.mp4 --no-chat
```

Titel und Scores stehen in `manifest.json` neben den Clips.

## So arbeitet der Live-Modus

1. yt-dlp liefert die Stream-URL, ffmpeg schreibt 10-s-Segmente (Puffer ca. 20 min, Älteres wird gelöscht).
2. Chat-Nachrichten pro Sekunde kommen über anonymen Twitch-IRC. Die Lautstärke wird pro Segment gemessen.
3. Die Werte werden gegen die letzten 10 Minuten als „normal“ verglichen. Ein Peak löst aus, sobald er 10 s alt ist und nichts Höheres folgte.
4. Aus dem Puffer werden ca. 22 s davor und 10 s danach geschnitten, transkribiert, an Satzgrenzen ausgerichtet und gerendert. Clips ohne Sprache werden verworfen.
5. Optional meldet ein Discord-Webhook (`[live] webhook`) jeden neuen Clip.

Ohne Chat-Verbindung wird nur die Lautstärke genutzt (Schwelle `audio_only_threshold`).

## Hinweise

- **Rechte:** Clips aus fremden Streams nur mit Erlaubnis des Streamers veröffentlichen.
- Der Live-Modus braucht einen Rechner, der während des Streams läuft (Aufnahme ca. 1–3 GB/h, Auswertung ist leicht).
- Whisper auf CPU: Modell `small` ist ein guter Kompromiss, mit GPU `device = "cuda"` setzen.
- Die Schwellen müssen an den Kanal angepasst werden: erst mit `--dry-run` beobachten.
- Der Chat-Replay-Abruf im `run`-Modus nutzt eine inoffizielle Twitch-Schnittstelle und fällt bei Fehlern still weg.
- **Tests:** `python3 -I -m unittest discover -s tests`
