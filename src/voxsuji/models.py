"""Normalized transcript schemas.

The normalized transcript is the canonical output.  Provider-specific detail
that does not fit is preserved verbatim in the ``raw`` sidecar file.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import asdict, dataclass, field
from typing import Any


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Word:
    start: float
    end: float
    text: str
    punctuation: str = ""


@dataclass
class Segment:
    start: float
    end: float
    text: str
    speaker: str | None = None
    words: list[Word] | None = None


@dataclass
class VideoMeta:
    id: str | None = None
    title: str | None = None
    uploader: str | None = None
    duration: float | None = None
    webpage_url: str | None = None


@dataclass
class Transcript:
    source_url: str
    platform: str
    video: VideoMeta
    transcript_source: str  # "subtitle" | "asr"
    language: str | None = None
    duration: float | None = None
    provider: str | None = None
    model: str | None = None
    segments: list[Segment] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n".join(seg.text.strip() for seg in self.segments if seg.text.strip())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["text"] = self.text
        return data

    def summary(self, *, files: dict[str, str] | None = None) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "platform": self.platform,
            "video_id": self.video.id,
            "title": self.video.title,
            "duration": self.duration if self.duration is not None else self.video.duration,
            "transcript_source": self.transcript_source,
            "provider": self.provider,
            "model": self.model,
            "language": self.language,
            "segment_count": len(self.segments),
            "char_count": len(self.text),
            "word_timestamps": any(seg.words for seg in self.segments),
            "files": files or {},
            "created_at": self.created_at,
        }

