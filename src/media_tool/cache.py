"""Filesystem cache layout.

    <cache>/<platform>/<video_id>/transcript.json      normalized transcript
    <cache>/<platform>/<video_id>/transcript.md        readable full text
    <cache>/<platform>/<video_id>/transcript.srt       optional subtitles
    <cache>/<platform>/<video_id>/meta.json            video metadata
    <cache>/<platform>/<video_id>/raw/<name>.json      raw provider/subtitle data
"""

from __future__ import annotations

from pathlib import Path

from .models import Transcript
from .urls import VideoRef
from .util import read_json, write_json


class Cache:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def dir(self, ref: VideoRef) -> Path:
        safe_id = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in ref.video_id)[:120]
        return self.root / ref.platform / (safe_id or "unknown")

    def meta_path(self, ref: VideoRef) -> Path:
        return self.dir(ref) / "meta.json"

    def transcript_path(self, ref: VideoRef) -> Path:
        return self.dir(ref) / "transcript.json"

    def markdown_path(self, ref: VideoRef) -> Path:
        return self.dir(ref) / "transcript.md"

    def srt_path(self, ref: VideoRef) -> Path:
        return self.dir(ref) / "transcript.srt"

    def raw_path(self, ref: VideoRef, name: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)
        return self.dir(ref) / "raw" / safe

    # -- read / write -----------------------------------------------------
    def read_transcript(self, ref: VideoRef) -> dict | None:
        path = self.transcript_path(ref)
        return read_json(path) if path.is_file() else None

    def write_transcript(self, ref: VideoRef, payload: dict) -> Path:
        path = self.transcript_path(ref)
        write_json(path, payload)
        return path

    def write_meta(self, ref: VideoRef, payload: dict) -> Path:
        path = self.meta_path(ref)
        write_json(path, payload)
        return path

    def read_meta(self, ref: VideoRef) -> dict | None:
        path = self.meta_path(ref)
        return read_json(path) if path.is_file() else None


def store_transcript(cache: Cache, ref: VideoRef, transcript: Transcript) -> dict[str, str]:
    """Persist normalized transcript + markdown (+ srt) and return their paths."""
    from .formatters import to_markdown, to_srt

    payload = transcript.to_dict()
    cache.write_transcript(ref, payload)

    md_path = cache.markdown_path(ref)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(to_markdown(transcript), encoding="utf-8")
    files = {"json": str(cache.transcript_path(ref)), "markdown": str(md_path)}

    srt = to_srt(transcript)
    if srt:
        srt_path = cache.srt_path(ref)
        srt_path.write_text(srt, encoding="utf-8")
        files["srt"] = str(srt_path)

    meta = cache.read_meta(ref) or {}
    meta.update(
        {
            "video_id": transcript.video.id,
            "title": transcript.video.title,
            "uploader": transcript.video.uploader,
            "duration": transcript.duration if transcript.duration is not None else transcript.video.duration,
            "platform": transcript.platform,
            "source_url": transcript.source_url,
        }
    )
    cache.write_meta(ref, meta)
    return files
