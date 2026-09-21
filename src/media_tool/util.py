"""Small shared helpers: random ids, subprocess running, JSON IO, logging."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path


def log(message: str, *, quiet: bool = False) -> None:
    if not quiet:
        print(message, file=sys.stderr, flush=True)


def random_id(nbytes: int = 16) -> str:
    """URL-safe, unpredictable identifier used for temporary object keys."""
    return secrets.token_urlsafe(nbytes).replace("-", "").replace("_", "")


class CommandError(RuntimeError):
    """A subprocess or pipeline step failed."""


class ConfigurationError(RuntimeError):
    """Required configuration / credentials are missing (recoverable by the user)."""


def _command_logline(cmd: list[str]) -> str:
    """Short log line for a command, with `--cookies` values redacted.

    Cookie file paths/contents must never reach the log; this holds no matter
    where the flag lands in the argument list.
    """
    pieces: list[str] = []
    i = 0
    while i < len(cmd):
        part = cmd[i]
        if part == "--cookies" and i + 1 < len(cmd):
            pieces += ["--cookies", "<redacted>"]
            i += 2
            continue
        pieces.append(part)
        i += 1
    shown = pieces[:4]
    return "$ " + " ".join(shown) + (" ..." if len(pieces) > 4 else "")


def run(cmd: list[str], *, timeout: float = 1800, check: bool = True, quiet: bool = False) -> subprocess.CompletedProcess:
    """Run a command, capturing output. Secrets are never passed via argv here."""
    if not quiet:
        log(_command_logline(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise CommandError(f"command timed out after {timeout}s: {cmd[0]}") from exc
    except FileNotFoundError as exc:
        raise CommandError(f"command not found: {cmd[0]}") from exc
    if check and proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-12:]
        raise CommandError(f"{cmd[0]} exited {proc.returncode}:\n" + "\n".join(tail))
    return proc


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def temp_workdir(prefix: str = "media-") -> tempfile.TemporaryDirectory:
    return tempfile.TemporaryDirectory(prefix=prefix)
