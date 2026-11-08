from __future__ import annotations

import re
import subprocess
from pathlib import Path

import requests

from . import config

HELIX = "https://api.twitch.tv/helix"
GQL = "https://gql.twitch.tv/gql"
GQL_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"  # oeffentliche Web-Client-ID (inoffiziell)
COMMENTS_HASH = "b70a3591ff0f4e0313d126c6a1502d79a1c02baebb288227c582044aa76adf6a"


def parse_vod_id(s: str) -> str | None:
    m = re.search(r"videos/(\d+)", s) or re.fullmatch(r"(\d+)", s.strip())
    return m.group(1) if m else None


class Helix:
    def __init__(self) -> None:
        self.cid = config.env("TWITCH_CLIENT_ID")
        r = requests.post("https://id.twitch.tv/oauth2/token", data={
            "client_id": self.cid, "client_secret": config.env("TWITCH_CLIENT_SECRET"),
            "grant_type": "client_credentials"}, timeout=20)
        r.raise_for_status()
        self.h = {"Client-ID": self.cid, "Authorization": f"Bearer {r.json()['access_token']}"}

    def get(self, path: str, **params):
        r = requests.get(f"{HELIX}/{path}", headers=self.h, params=params, timeout=20)
        r.raise_for_status()
        return r.json()

    def latest_vod(self, channel: str) -> dict:
        user = self.get("users", login=channel)["data"][0]
        vids = self.get("videos", user_id=user["id"], type="archive", first=1)["data"]
        if not vids:
            raise SystemExit(f"Keine VODs fuer {channel} gefunden.")
        return vids[0]

    def vod(self, vod_id: str) -> dict:
        return self.get("videos", id=vod_id)["data"][0]

    def vod_clip_offsets(self, vod: dict) -> list[float]:
        """Offsets (Sek. im VOD) aller Zuschauer-Clips, die aus diesem VOD stammen."""
        offsets: list[float] = []
        cursor = None
        for _ in range(20):
            params = {"broadcaster_id": vod["user_id"], "first": 100}
            if cursor:
                params["after"] = cursor
            data = self.get("clips", **params)
            for c in data["data"]:
                if c.get("video_id") == vod["id"] and c.get("vod_offset") is not None:
                    offsets.append(float(c["vod_offset"]) + float(c.get("duration", 0)) / 2)
            cursor = data.get("pagination", {}).get("cursor")
            if not cursor:
                break
        return offsets


def chat_timestamps(vod_id: str, max_pages: int = 4000) -> list[float]:
    """Zeitpunkte aller Chatnachrichten (Sek. im VOD) ueber die inoffizielle GQL-Schnittstelle."""
    stamps: list[float] = []
    cursor = None
    s = requests.Session()
    s.headers["Client-ID"] = GQL_CLIENT_ID
    for _ in range(max_pages):
        variables = {"videoID": vod_id}
        variables.update({"cursor": cursor} if cursor else {"contentOffsetSeconds": 0})
        body = [{"operationName": "VideoCommentsByOffsetOrCursor", "variables": variables,
                 "extensions": {"persistedQuery": {"version": 1, "sha256Hash": COMMENTS_HASH}}}]
        r = s.post(GQL, json=body, timeout=20)
        r.raise_for_status()
        comments = r.json()[0]["data"]["video"]["comments"]
        for e in comments["edges"]:
            stamps.append(float(e["node"]["contentOffsetSeconds"]))
        info = comments["pageInfo"]
        if not info.get("hasNextPage") or not comments["edges"]:
            break
        cursor = comments["edges"][-1]["cursor"]
    return stamps


def _ytdlp(args: list[str]) -> None:
    subprocess.run(["yt-dlp", "--no-progress", "--quiet", "--no-warnings", *args], check=True)


def vod_url(vod_id: str) -> str:
    return f"https://www.twitch.tv/videos/{vod_id}"


def download_audio(vod_id: str, dest_dir: Path) -> Path:
    out = dest_dir / f"{vod_id}_audio.%(ext)s"
    existing = list(dest_dir.glob(f"{vod_id}_audio.*"))
    if existing:
        return existing[0]
    _ytdlp(["-f", "Audio_Only/worstaudio/worst", "-o", str(out), vod_url(vod_id)])
    return next(dest_dir.glob(f"{vod_id}_audio.*"))


def download_section(vod_id: str, start: float, end: float, fmt: str, dest: Path) -> Path:
    if dest.exists():
        return dest
    _ytdlp(["-f", fmt, "--download-sections", f"*{int(start)}-{int(end) + 1}",
            "--force-keyframes-at-cuts", "--merge-output-format", "mp4",
            "-o", str(dest), vod_url(vod_id)])
    return dest


def cut_local(src: str, start: float, end: float, dest: Path) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.2f}", "-i", src,
                    "-t", f"{end - start:.2f}", "-c", "copy", str(dest)], check=True)
    return dest
