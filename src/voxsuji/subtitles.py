"""Subtitle discovery and parsing.

Supported inputs: yt-dlp ``json3`` / WebVTT / SRT files.  Timestamps in the
normalized model are always float seconds.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .models import Segment, Word

# Language preference used when picking among several available tracks.
_LANG_PRIORITY = [
    "zh-hans", "zh-cn", "zh-hant", "zh-tw", "zh", "zh-hk",
    "en-us", "en-gb", "en", "ja", "ko",
]


@dataclass
class Track:
    path: Path
    lang: str
    automatic: bool
    fmt: str


def _lang_score(lang: str, preferred: list[str]) -> tuple[int, int]:
    low = lang.lower()
    for index, want in enumerate(preferred):
        if low == want.lower():
            return (0, index)
    for index, want in enumerate(preferred):
        if low.startswith(want.lower().split("-")[0]):
            return (1, index)
    return (2, _LANG_PRIORITY.index(low) if low in _LANG_PRIORITY else 99)


def find_tracks(workdir: Path, info: dict, preferred: list[str] | None = None) -> list[Track]:
    """Return subtitle files yt-dlp produced, best candidate first."""
    preferred = preferred or _LANG_PRIORITY
    auto_langs = set()
    for entry in info.get("automatic_captions") or {}:
        auto_langs.add(entry)
    manual_langs = set(info.get("subtitles") or {})

    tracks: list[Track] = []
    for path in sorted(workdir.glob("sub*")):
        if path.suffix.lower() not in (".json3", ".vtt", ".srt", ".json", ".xml"):
            continue
        name = path.name
        # yt-dlp naming: <template>.<lang>.<ext>
        parts = name.split(".")
        lang = parts[-2] if len(parts) >= 3 else "unknown"
        fmt = path.suffix.lower().lstrip(".")
        automatic = lang in auto_langs and lang not in manual_langs
        tracks.append(Track(path=path, lang=lang, automatic=automatic, fmt=fmt))

    tracks.sort(key=lambda t: (t.automatic, _lang_score(t.lang, preferred)))
    return tracks


# -- individual parsers ---------------------------------------------------
_TS = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})")


def _ts_to_seconds(match: re.Match) -> float:
    hours, minutes, seconds, millis = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis.ljust(3, "0")) / 1000.0


def parse_vtt(text: str) -> list[Segment]:
    segments: list[Segment] = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n"))
    for block in blocks:
        lines = [ln for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        timing_index = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if timing_index is None:
            continue
        start_match = _TS.search(lines[timing_index])
        end_match = _TS.search(lines[timing_index].split("-->")[-1])
        if not start_match or not end_match:
            continue
        payload = " ".join(lines[timing_index + 1 :]).strip()
        payload = re.sub(r"<[^>]+>", "", payload)
        payload = re.sub(r"\s+", " ", payload).strip()
        if not payload:
            continue
        start, end = _ts_to_seconds(start_match), _ts_to_seconds(end_match)
        if segments and segments[-1].text == payload:
            segments[-1].end = max(segments[-1].end, end)
            continue
        segments.append(Segment(start=start, end=end, text=payload))
    return segments


def parse_srt(text: str) -> list[Segment]:
    return parse_vtt(text)


def parse_json3(data: dict) -> list[Segment]:
    segments: list[Segment] = []
    for event in data.get("events") or []:
        segs = event.get("segs") or []
        payload = "".join(seg.get("utf8", "") for seg in segs)
        payload = re.sub(r"\s+", " ", payload).strip()
        if not payload:
            continue
        start = float(event.get("tStartMs", 0)) / 1000.0
        end = start + float(event.get("dDurationMs", 0)) / 1000.0
        seg_words: list[Word] = []
        for seg in segs:
            word = seg.get("utf8", "").strip()
            if not word:
                continue
            offset = float(seg.get("tOffsetMs", 0) or 0) / 1000.0
            seg_words.append(Word(start=start + offset, end=start + offset, text=word))
        if segments and segments[-1].text == payload:
            segments[-1].end = max(segments[-1].end, end)
            continue
        segments.append(Segment(start=start, end=end, text=payload, words=seg_words or None))
    return segments


def parse_track(track: Track) -> list[Segment]:
    raw = track.path.read_text(encoding="utf-8", errors="replace")
    if track.fmt in ("json", "json3"):
        data = json.loads(raw)
        if "events" in data:
            return parse_json3(data)
        raise ValueError(f"unrecognized subtitle JSON structure in {track.path.name}")
    return parse_vtt(raw)
