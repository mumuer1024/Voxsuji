"""Command line interface: `media transcript <URL>` / `media doctor`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, storage
from .cache import Cache
from .config import (
    KNOWN_PROVIDERS,
    VERIFIED_PROVIDERS,
    Config,
    cookies_file_problem,
    cookies_permission_warning,
)
from .transcript import run_transcript
from .urls import identify
from .util import CommandError, ConfigurationError
from .ytdlp import YtDlp

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_UNCONFIGURED = 3


def _config() -> Config:
    return Config()


def _emit(payload: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


def _fail(message: str, *, kind: str, as_json: bool, code: int = EXIT_ERROR) -> int:
    if as_json:
        _emit({"ok": False, "error": {"type": kind, "message": message}}, True)
    else:
        print(f"error [{kind}]: {message}", file=sys.stderr)
    return code


# -- commands -------------------------------------------------------------
def cmd_transcript(args: argparse.Namespace) -> int:
    config = _config()
    try:
        ref = identify(args.url)
    except ValueError as exc:
        return _fail(str(exc), kind="invalid_url", as_json=args.json, code=EXIT_USAGE)
    provider = args.provider or config.default_provider
    if provider not in KNOWN_PROVIDERS:
        return _fail(
            f"unknown provider {provider!r}; choose one of: {', '.join(KNOWN_PROVIDERS)}",
            kind="invalid_provider",
            as_json=args.json,
            code=EXIT_USAGE,
        )
    try:
        outcome = run_transcript(
            ref,
            config,
            provider_name=provider,
            force_asr=args.force_asr,
            refresh=args.refresh,
            language=args.language,
            quiet=args.json,
        )
    except ConfigurationError as exc:
        return _fail(str(exc), kind="unconfigured", as_json=args.json, code=EXIT_UNCONFIGURED)
    except CommandError as exc:
        return _fail(str(exc), kind="command_failed", as_json=args.json)
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report, never traceback
        return _fail(f"{type(exc).__name__}: {exc}", kind="transcript_failed", as_json=args.json)

    payload = {"ok": True, "cached": outcome.cached, **outcome.payload}
    if args.json:
        _emit(payload, True)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return EXIT_OK


def _cookies_report(config: Config) -> dict:
    """Local-only cookie checks for `doctor`: never reads the file contents.

    status: not_configured | configured | problem. A problem or a permission
    warning is reported but never fails the doctor exit code.
    """
    path = config.cookies_file
    if path is None:
        return {
            "configured": False,
            "status": "not_configured",
            "file": None,
            "message": None,
            "warnings": [],
        }
    warnings = [w for w in [cookies_permission_warning(path)] if w]
    problem = cookies_file_problem(path)
    return {
        "configured": True,
        "status": "problem" if problem else "configured",
        "file": str(path),
        "message": problem,
        "warnings": warnings,
    }


def cmd_doctor(args: argparse.Namespace) -> int:
    """Show what is configured without ever printing a secret value."""
    config = _config()
    ytdlp = YtDlp(config)
    report = {
        "version": __version__,
        "data_dir": str(config.root),
        "yt_dlp": {
            "path": config.ytdlp_bin,
            "available": ytdlp.available(),
        },
        "ffmpeg": {"path": config.ffmpeg_bin},
        "cookies": _cookies_report(config),
        "default_provider": config.default_provider,
        "providers": {
            name: {
                "configured": not config.missing_provider_env(name),
                "missing": config.missing_provider_env(name),
                "model": config.setting(f"provider.{name}", "model") or "",
                "verified": name in VERIFIED_PROVIDERS,
                "status": (
                    "IMPLEMENTED+VERIFIED" if name in VERIFIED_PROVIDERS else "IMPLEMENTED+UNVERIFIED"
                ),
            }
            for name in KNOWN_PROVIDERS
        },
        "storage": {
            "configured": storage.storage_configured(config),
            "missing": storage.storage_missing(config),
            "endpoint": storage._setting_or_env(config, "endpoint"),
            "bucket": storage._setting_or_env(config, "bucket"),
        },
        "cache_dir": str(config.cache_dir),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return EXIT_OK


# -- parser ---------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="media",
        description=(
            "Turn an online video URL into structured, cacheable transcript text."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"media {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    t = sub.add_parser(
        "transcript",
        help="get the full transcript (platform subtitles first, ASR fallback)",
        description=(
            "Get the full transcript of an online video.\n\n"
            "Flow: cache -> platform subtitles -> (only if no usable subtitles) "
            "download audio -> ffmpeg -> temporary public object -> ASR provider -> poll "
            "-> download -> normalize -> cache -> delete temporary object.\n\n"
            "Long transcripts are written to files; stdout only carries a summary."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    t.add_argument("url", help="video URL (YouTube, or any other yt-dlp supported site)")
    t.add_argument(
        "--provider",
        choices=KNOWN_PROVIDERS,
        help="ASR provider; only used when no usable platform subtitles exist "
        "(default: config default_provider)",
    )
    t.add_argument("--language", help="language hint passed to the ASR provider (e.g. zh, en)")
    t.add_argument("--force-asr", action="store_true", help="ignore platform subtitles and use ASR")
    t.add_argument("--refresh", action="store_true", help="ignore the cache and fetch again")
    t.add_argument("--json", action="store_true", help="emit machine-readable JSON on stdout")
    t.set_defaults(func=cmd_transcript)

    d = sub.add_parser(
        "doctor",
        help="report configuration and dependency status (never prints secrets)",
        description="Show dependency paths, which providers are configured, and cache locations.",
    )
    d.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return EXIT_USAGE
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
