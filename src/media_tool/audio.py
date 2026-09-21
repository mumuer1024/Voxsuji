"""FFmpeg based audio inspection and conversion."""

from __future__ import annotations

import json
from pathlib import Path

from .config import Config
from .util import CommandError, run


def probe_duration(path: Path, config: Config, *, timeout: float = 120) -> float | None:
    proc = run(
        [
            config.ffprobe_bin,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        return None
    try:
        value = json.loads(proc.stdout)["format"]["duration"]
        return float(value)
    except (KeyError, ValueError, json.JSONDecodeError):
        return None


def to_asr_audio(source: Path, target: Path, config: Config, *, timeout: float = 3600) -> Path:
    """Convert any input media into mono 16 kHz mp3, which every ASR accepts."""
    target.parent.mkdir(parents=True, exist_ok=True)
    proc = run(
        [
            config.ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "64k",
            str(target),
        ],
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
        raise CommandError(
            "ffmpeg failed to produce ASR audio: " + (proc.stderr or "").strip()[-500:]
        )
    return target


def verify_audio(path: Path, config: Config) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise CommandError(f"audio file is missing or empty: {path}")
