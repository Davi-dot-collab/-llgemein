"""TikTok Content Posting API (https://developers.tiktok.com/doc/content-posting-api-get-started).

Wichtig: Ohne TikTok-Audit der App sind nur private Posts (SELF_ONLY) moeglich.
Der Modus "inbox" legt das Video als Entwurf in der TikTok-App ab - dort pruefst und postest du es.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
from pathlib import Path

import requests

from . import config

API = "https://open.tiktokapis.com"
TOKENS = Path("tokens.json")
CHUNK = 10 * 1024 * 1024


def auth_url(redirect_uri: str, scopes: str = "video.upload,video.publish") -> str:
    q = urllib.parse.urlencode({"client_key": config.env("TIKTOK_CLIENT_KEY"), "scope": scopes,
                                "response_type": "code", "redirect_uri": redirect_uri, "state": "clipbot"})
    return f"https://www.tiktok.com/v2/auth/authorize/?{q}"


def _token_request(data: dict) -> dict:
    data = {"client_key": config.env("TIKTOK_CLIENT_KEY"),
            "client_secret": config.env("TIKTOK_CLIENT_SECRET"), **data}
    r = requests.post(f"{API}/v2/oauth/token/", data=data, timeout=30)
    r.raise_for_status()
    tok = r.json()
    if "access_token" not in tok:
        raise SystemExit(f"TikTok-Token-Fehler: {tok}")
    tok["obtained_at"] = int(time.time())
    TOKENS.write_text(json.dumps(tok, indent=2))
    os.chmod(TOKENS, 0o600)
    return tok


def exchange_code(code: str, redirect_uri: str) -> dict:
    code = urllib.parse.unquote(code)
    return _token_request({"code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri})


def access_token() -> str:
    if not TOKENS.exists():
        raise SystemExit("Nicht eingeloggt. Erst: clipbot tiktok-auth")
    tok = json.loads(TOKENS.read_text())
    if time.time() > tok["obtained_at"] + tok.get("expires_in", 86400) - 300:
        tok = _token_request({"grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})
    return tok["access_token"]


def _post(path: str, body: dict, token: str) -> dict:
    r = requests.post(f"{API}{path}", json=body, timeout=60, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"})
    j = r.json()
    if r.status_code >= 400 or j.get("error", {}).get("code", "ok") != "ok":
        raise RuntimeError(f"TikTok {path}: {j}")
    return j["data"]


def _chunks(size: int) -> tuple[int, int]:
    if size <= CHUNK:
        return size, 1
    return CHUNK, size // CHUNK  # letzter Chunk nimmt den Rest auf (erlaubt bis 128 MB)


def upload(video: Path, tcfg: dict, title: str) -> str:
    token = access_token()
    size = video.stat().st_size
    chunk, total = _chunks(size)
    source = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk, "total_chunk_count": total}
    if tcfg["mode"] == "direct":
        post = {"title": title[:2200], "privacy_level": tcfg["privacy_level"],
                "disable_duet": False, "disable_comment": False, "disable_stitch": False}
        init = _post("/v2/post/publish/video/init/", {"post_info": post, "source_info": source}, token)
    else:
        init = _post("/v2/post/publish/inbox/video/init/", {"source_info": source}, token)
    url, pid = init["upload_url"], init["publish_id"]
    with video.open("rb") as f:
        for i in range(total):
            start = i * chunk
            data = f.read(chunk if i < total - 1 else size - start)
            end = start + len(data) - 1
            r = requests.put(url, data=data, timeout=300, headers={
                "Content-Type": "video/mp4", "Content-Length": str(len(data)),
                "Content-Range": f"bytes {start}-{end}/{size}"})
            if r.status_code not in (200, 201, 206):
                raise RuntimeError(f"Upload-Chunk {i + 1}/{total} fehlgeschlagen: {r.status_code} {r.text}")
    return pid


def status(publish_id: str) -> dict:
    return _post("/v2/post/publish/status/fetch/", {"publish_id": publish_id}, access_token())
