"""URL / platform identification helpers."""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}

_YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


@dataclass
class VideoRef:
    input_url: str
    platform: str  # "youtube" | "other"
    video_id: str
    canonical_url: str


def identify(url: str) -> VideoRef:
    raw = url.strip()
    if not raw:
        raise ValueError("empty URL")
    parsed = urllib.parse.urlsplit(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").lower()
    query = urllib.parse.parse_qs(parsed.query)

    if host in _YOUTUBE_HOSTS:
        vid = None
        if host == "youtu.be":
            vid = parsed.path.lstrip("/").split("/")[0]
        else:
            if parsed.path in ("/watch", "/watch/"):
                vid = (query.get("v") or [None])[0]
            elif parsed.path.startswith(("/embed/", "/shorts/", "/live/", "/v/")):
                parts = [p for p in parsed.path.split("/") if p]
                vid = parts[1] if len(parts) > 1 else None
        if not vid or not _YT_ID.match(vid):
            raise ValueError(f"could not extract a YouTube video id from: {raw}")
        return VideoRef(raw, "youtube", vid, f"https://www.youtube.com/watch?v={vid}")

    # Unknown platform: let yt-dlp try, key the cache on the URL host+path.
    fallback = f"{host}{parsed.path}".strip("/") or raw
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", fallback)[:120]
    return VideoRef(raw, "other", safe, raw)
