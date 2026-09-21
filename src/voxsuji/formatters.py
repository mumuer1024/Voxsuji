"""Transcript renderers: Markdown and SRT."""

from __future__ import annotations

from .models import Transcript


def _clock(seconds: float, *, decimal: str = ",") -> str:
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    hours, rem = divmod(total_ms, 3600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{decimal}{millis:03d}"


def _human(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def to_markdown(transcript: Transcript) -> str:
    video = transcript.video
    lines = [
        f"# {video.title or video.id or transcript.source_url}",
        "",
        "| field | value |",
        "| --- | --- |",
        f"| source_url | {transcript.source_url} |",
        f"| platform | {transcript.platform} |",
        f"| video_id | {video.id or ''} |",
        f"| uploader | {video.uploader or ''} |",
        f"| duration | {_human(transcript.duration if transcript.duration is not None else video.duration)} |",
        f"| transcript_source | {transcript.transcript_source} |",
        f"| provider | {transcript.provider or ''} |",
        f"| model | {transcript.model or ''} |",
        f"| language | {transcript.language or ''} |",
        f"| segments | {len(transcript.segments)} |",
        f"| created_at | {transcript.created_at} |",
        "",
        "## Transcript",
        "",
    ]
    for segment in transcript.segments:
        prefix = f"[{_clock(segment.start, decimal='.')}]"
        speaker = f" {segment.speaker}:" if segment.speaker else ""
        lines.append(f"{prefix}{speaker} {segment.text.strip()}")
    lines.append("")
    return "\n".join(lines)


def to_srt(transcript: Transcript) -> str:
    if not transcript.segments:
        return ""
    blocks = []
    for index, segment in enumerate(transcript.segments, start=1):
        text = segment.text.strip()
        if segment.speaker:
            text = f"{segment.speaker}: {text}"
        blocks.append(
            f"{index}\n{_clock(segment.start)} --> {_clock(segment.end)}\n{text}\n"
        )
    return "\n".join(blocks)


def to_plain_text(transcript: Transcript) -> str:
    parts = []
    for segment in transcript.segments:
        if segment.speaker:
            parts.append(f"{segment.speaker}: {segment.text.strip()}")
        else:
            parts.append(segment.text.strip())
    return "\n".join(part for part in parts if part)
