"""Transcript orchestration: cache -> platform subtitles -> ASR fallback."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from . import storage
from .audio import to_asr_audio
from .cache import Cache, store_transcript
from .config import Config
from .models import Segment, Transcript, VideoMeta, Word
from .providers.base import ProviderError, get_provider
from .subtitles import find_tracks, parse_track
from .urls import VideoRef
from .util import CommandError, ConfigurationError, log, random_id, temp_workdir
from .ytdlp import YtDlp


@dataclass
class TranscriptOutcome:
    payload: dict
    files: dict[str, str]
    cached: bool
    transcript: Transcript


def _video_meta(ref: VideoRef, info: dict, fallback_title: str | None = None) -> VideoMeta:
    return VideoMeta(
        id=str(info.get("id") or ref.video_id),
        title=info.get("title") or fallback_title,
        uploader=info.get("uploader") or info.get("channel") or info.get("uploader_id"),
        duration=info.get("duration"),
        webpage_url=info.get("webpage_url") or ref.canonical_url,
    )


def _preferred_languages(config: Config) -> list[str]:
    configured = config.setting("subtitles", "preferred_languages", "zh-Hans,zh-CN,zh,en")
    return [lang.strip() for lang in (configured or "").split(",") if lang.strip()]


def background_steps(config: Config, ref: VideoRef, workdir: Path, info: dict) -> tuple[list[Segment], str, str | None, dict]:
    """Try platform subtitles. Returns (segments, source_label, language, debug)."""
    tracks = find_tracks(workdir, info, _preferred_languages(config))
    debug = {
        "subtitle_tracks_found": [
            {"lang": t.lang, "format": t.fmt, "automatic": t.automatic, "file": t.path.name} for t in tracks
        ]
    }
    for track in tracks:
        try:
            segments = parse_track(track)
        except Exception as exc:  # noqa: BLE001 - a bad track must not kill the run
            log(f"  subtitle {track.path.name} could not be parsed: {exc}")
            continue
        if segments:
            label = "subtitle:automatic" if track.automatic else "subtitle"
            return segments, label, track.lang, debug
    return [], "", None, debug


def run_transcript(
    ref: VideoRef,
    config: Config,
    *,
    provider_name: str | None = None,
    force_asr: bool = False,
    refresh: bool = False,
    language: str | None = None,
    quiet: bool = False,
) -> TranscriptOutcome:
    cache = Cache(config.cache_dir)

    if not refresh:
        cached = cache.read_transcript(ref)
        if cached and cached.get("segments"):
            transcript = _from_payload(cached)
            files = _existing_files(cache, ref)
            log(f"cache hit: {cache.transcript_path(ref)}", quiet=quiet)
            return TranscriptOutcome(
                payload=transcript.summary(files=files), files=files, cached=True, transcript=transcript
            )

    ytdlp = YtDlp(config)
    if not ytdlp.available():
        raise ConfigurationError(
            f"yt-dlp not found at {config.ytdlp_bin!r}; install it with "
            f"`python3 -m venv .venv && .venv/bin/pip install yt-dlp` in the project root"
        )

    log(f"probing metadata for {ref.canonical_url}", quiet=quiet)
    info = ytdlp.probe(ref.canonical_url)
    video = _video_meta(ref, info)
    has_subs = bool(info.get("subtitles") or info.get("automatic_captions"))

    segments: list[Segment] = []
    source = "asr"
    detected_language = language
    debug: dict = {}
    provider_result = None

    if not force_asr and has_subs:
        with temp_workdir() as work:
            workdir = Path(work)
            log("platform subtitles available; downloading (no ASR call)", quiet=quiet)
            sub_info = ytdlp.download_subtitles(ref.canonical_url, workdir) or info
            segments, source, detected_language, debug = background_steps(
                config, ref, workdir, sub_info or info
            )

    if not segments:
        if has_subs and not force_asr:
            log("subtitle files were unusable; falling back to ASR", quiet=quiet)
        segments, source, provider_result, debug = _run_asr(
            ref, config, video, provider_name, language, quiet=quiet
        )
        detected_language = provider_result.language or detected_language

    duration = video.duration
    if provider_result is not None and provider_result.duration:
        duration = provider_result.duration

    transcript = Transcript(
        source_url=ref.canonical_url,
        platform=ref.platform,
        video=video,
        transcript_source=source,
        language=detected_language,
        duration=duration,
        provider=provider_result.provider if provider_result else None,
        model=provider_result.model if provider_result else None,
        segments=segments,
        extra={"detection": debug},
    )

    files = store_transcript(cache, ref, transcript)
    if provider_result is not None:
        raw_path = cache.raw_path(ref, f"asr_{provider_result.provider}.json")
        from .util import write_json

        write_json(
            raw_path,
            {"provider_meta": provider_result.provider_meta, "response": provider_result.raw},
        )
        files["raw"] = str(raw_path)
        transcript.extra["provider_meta"] = provider_result.provider_meta

    payload = transcript.summary(files=files)
    payload["provider_meta"] = (provider_result.provider_meta if provider_result else None)
    return TranscriptOutcome(payload=payload, files=files, cached=False, transcript=transcript)


def _run_asr(ref, config: Config, video: VideoMeta, provider_name: str | None, language: str | None, *, quiet: bool):
    provider_name = provider_name or config.default_provider
    provider = get_provider(provider_name, config)
    missing = provider.missing_config()
    if missing:
        raise ConfigurationError(
            f"provider {provider_name!r} is not configured; missing environment variables: "
            + ", ".join(missing)
            + " (see .env.example)"
        )
    client = storage.build_client(config)

    ytdlp = YtDlp(config)
    debug: dict = {}
    object_url = None
    with temp_workdir() as work:
        workdir = Path(work)
        asr_audio = workdir / "audio.mp3"

        log("downloading audio (no platform subtitles available)", quiet=quiet)
        ytdlp.download_audio(ref.canonical_url, asr_audio)
        size = asr_audio.stat().st_size
        debug["audio_bytes"] = size
        log(f"  ASR audio: {size / 1024 / 1024:.2f} MiB", quiet=quiet)

        key = f"asr-tmp/{random_id()}.mp3"
        try:
            object_url = client.put_file(key, asr_audio, "audio/mpeg")
            log(f"  uploaded temporary object: {object_url}", quiet=quiet)
            check = storage.verify_public_read(object_url, timeout=60)
            debug["public_read"] = check
            log(
                f"  anonymous read OK ({check['content_type']}, {check['content_length']} bytes)",
                quiet=quiet,
            )
            log(f"calling ASR provider {provider_name} ({provider.configured_model()})", quiet=quiet)
            result = provider.transcribe(object_url, language=language, audio_path=asr_audio)
            debug["provider_config"] = {"provider": provider_name, "model": result.model}
            return result.segments, "asr", result, debug
        finally:
            if object_url is not None:
                try:
                    client.delete(key)
                    log("  removed temporary object", quiet=quiet)
                except Exception as exc:  # noqa: BLE001 - cleanup must not mask the real error
                    log(f"  WARNING: could not delete temporary object {key}: {exc}", quiet=quiet)


def _from_payload(payload: dict) -> Transcript:
    video = payload.get("video") or {}
    segments: list[Segment] = []
    for seg in payload.get("segments") or []:
        words = None
        if seg.get("words"):
            words = [
                Word(
                    start=word.get("start", 0.0),
                    end=word.get("end", 0.0),
                    text=word.get("text", ""),
                    punctuation=word.get("punctuation", "") or "",
                )
                for word in seg["words"]
            ]
        segments.append(
            Segment(
                start=seg.get("start", 0.0),
                end=seg.get("end", 0.0),
                text=seg.get("text", ""),
                speaker=seg.get("speaker"),
                words=words,
            )
        )
    return Transcript(
        source_url=payload.get("source_url", ""),
        platform=payload.get("platform", "other"),
        video=VideoMeta(
            id=video.get("id"),
            title=video.get("title"),
            uploader=video.get("uploader"),
            duration=video.get("duration"),
            webpage_url=video.get("webpage_url"),
        ),
        transcript_source=payload.get("transcript_source", "unknown"),
        language=payload.get("language"),
        duration=payload.get("duration"),
        provider=payload.get("provider"),
        model=payload.get("model"),
        segments=segments,
        created_at=payload.get("created_at", ""),
        extra=payload.get("extra") or {},
    )


def _existing_files(cache: Cache, ref: VideoRef) -> dict[str, str]:
    files = {"json": str(cache.transcript_path(ref)), "markdown": str(cache.markdown_path(ref))}
    if cache.srt_path(ref).is_file():
        files["srt"] = str(cache.srt_path(ref))
    raw_dir = cache.transcript_path(ref).parent / "raw"
    if raw_dir.is_dir():
        raws = sorted(raw_dir.glob("asr_*.json"))
        if raws:
            files["raw"] = str(raws[0])
    return files
