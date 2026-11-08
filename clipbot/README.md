# clipbot

Findet lustige/virale Momente in Twitch-VODs (z. B. GTasty), schneidet sie als 9:16-Clips mit Untertiteln und lädt sie zu TikTok hoch.

## Ablauf

1. **Audio-only-Download** des VODs (klein, schnell) und Lautstärke-Analyse pro Sekunde.
2. **Signale kombinieren:** Lautstärke-Spitzen (Lachen/Schreien), Chat-Aktivität, von Zuschauern erstellte Twitch-Clips.
3. **Kandidaten** (Peaks) werden gewählt, nur diese Abschnitte werden in Videoqualität geladen.
4. **faster-whisper** transkribiert die Abschnitte lokal. Neu-Ranking nach Sprache/Ausrufen, Schnitt an Satzgrenzen.
5. **ffmpeg** rendert 1080x1920 (Gameplay auf unscharfem Hintergrund oder Facecam oben / Game unten) mit eingebrannten Untertiteln.
6. **Upload** zu TikTok. Standard: als Entwurf in die App (`inbox`), dort prüfst und postest du.

## Setup

```bash
cd clipbot
pip install -r requirements.txt     # ffmpeg muss installiert sein
cp config.example.toml config.toml
export TWITCH_CLIENT_ID=... TWITCH_CLIENT_SECRET=...      # dev.twitch.tv/console
export TIKTOK_CLIENT_KEY=... TIKTOK_CLIENT_SECRET=...     # developers.tiktok.com (Content Posting API)
```

## Benutzung

```bash
python -m clipbot run --latest                      # neuestes VOD des Kanals
python -m clipbot run https://www.twitch.tv/videos/123456789 --count 8
python -m clipbot run stream.mp4 --no-chat          # lokale Datei, nur Audio-Analyse

python -m clipbot tiktok-auth --redirect-uri https://deine-seite.example/callback   # einmalig
python -m clipbot upload out/123456789 --dry-run
python -m clipbot upload out/123456789 --ids 1,3
```

Die Clips landen in `out/<vod-id>/`, Titel/Scores in `manifest.json` (Titel dort vor dem Upload anpassen).

## Hinweise

- **Rechte:** Clips aus fremden Streams nur mit Erlaubnis des Streamers hochladen.
- **TikTok:** Ohne App-Audit sind Direct Posts nur privat (`SELF_ONLY`); `inbox` funktioniert zum Testen.
- **Chat-Replay** nutzt die inoffizielle Twitch-GQL-Schnittstelle und fällt bei Fehlern still weg.
- **Kosten:** läuft komplett lokal/auf einem kleinen Server, keine Bezahl-APIs. Auf CPU ist `small` ein guter Kompromiss.
- **Tests:** `python3 -I -m unittest discover -s tests`
