"""Configuration + secret loading.

Secrets are read from environment variables, optionally populated from a
git-ignored ``.env`` file at the project root.  Non-secret settings live in
``config.ini``.  Values already present in the real environment always win.
"""

from __future__ import annotations

import configparser
import os
import stat
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("VOXSUJI_DATA_DIR", PROJECT_ROOT)).expanduser()

DEFAULT_PROVIDER = "aliyun"
KNOWN_PROVIDERS = ("aliyun", "volcengine", "tencent")

# Providers whose adapter has completed a real end-to-end run against the live
# service (async submit -> poll -> result -> normalization). Kept here so the CLI
# status report cannot drift from the documentation.
VERIFIED_PROVIDERS = ("aliyun", "volcengine", "tencent")

# Env vars each ASR provider needs.  Names only — values are never logged.
PROVIDER_ENV = {
    "aliyun": ("DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL"),
    "volcengine": ("VOLC_API_KEY", "VOLC_APP_ID", "VOLC_ACCESS_TOKEN", "VOLC_RESOURCE_ID"),
    "tencent": ("TENCENT_SECRET_ID", "TENCENT_SECRET_KEY", "TENCENT_REGION", "TENCENT_TOKEN"),
}

STORAGE_ENV = (
    "STORAGE_ENDPOINT",
    "STORAGE_REGION",
    "STORAGE_BUCKET",
    "STORAGE_ACCESS_KEY",
    "STORAGE_SECRET_KEY",
)


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            out[key] = value
    return out


PLACEHOLDERS = {"", "CHANGE_ME", "changeme", "your_key_here", "sk-xxx", "xxx"}


def _is_real(value: str | None) -> bool:
    return bool(value) and value.strip() not in PLACEHOLDERS


class Config:
    """Merged view of ``.env``, the real environment and ``config.ini``."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else DATA_DIR
        self.env_file = self.root / ".env"
        self.settings_file = self.root / "config.ini"
        # .env first so that the real environment can still override it.
        self._env = _parse_env_file(self.env_file)
        self._settings = configparser.ConfigParser()
        if self.settings_file.is_file():
            self._settings.read(self.settings_file, encoding="utf-8")

    def get(self, key: str, default: str | None = None) -> str | None:
        value = os.environ.get(key)
        if value is None:
            value = self._env.get(key)
        return default if value is None or value == "" else value

    def setting(self, section: str, option: str, default: str | None = None) -> str | None:
        if self._settings.has_option(section, option):
            value = self._settings.get(section, option).strip()
            return value or default
        return default

    @property
    def default_provider(self) -> str:
        return self.setting("asr", "default_provider", DEFAULT_PROVIDER) or DEFAULT_PROVIDER

    def provider_settings(self, provider: str) -> dict[str, str]:
        section = f"provider.{provider}"
        if not self._settings.has_section(section):
            return {}
        return {k: v.strip() for k, v in self._settings.items(section)}

    # -- credential presence (names only, never values) -------------------
    def missing_provider_env(self, provider: str) -> list[str]:
        required = PROVIDER_ENV.get(provider, ())
        optional = {
            "DASHSCOPE_BASE_URL",
            "TENCENT_REGION",
            "TENCENT_TOKEN",
            "VOLC_RESOURCE_ID",
        }
        present = [name for name in required if _is_real(self.get(name))]
        if provider == "volcengine":
            # Either the new-console API key or the classic app id + token pair.
            if present:
                return []
            return ["VOLC_API_KEY (or VOLC_APP_ID + VOLC_ACCESS_TOKEN)"]
        return [name for name in required if name not in optional and not _is_real(self.get(name))]

    def missing_storage_env(self) -> list[str]:
        return [name for name in STORAGE_ENV if not self.get(name)]

    # -- paths ------------------------------------------------------------
    @property
    def cache_dir(self) -> Path:
        return Path(self.setting("paths", "cache_dir", str(self.root / "cache")) or "")

    @property
    def ytdlp_bin(self) -> str:
        configured = self.setting("tools", "ytdlp")
        if configured:
            return configured
        local = self.root / ".venv" / "bin" / "yt-dlp"
        if local.is_file():
            return str(local)
        return "yt-dlp"

    @property
    def ffmpeg_bin(self) -> str:
        return self.setting("tools", "ffmpeg", "ffmpeg") or "ffmpeg"

    @property
    def ffprobe_bin(self) -> str:
        return self.setting("tools", "ffprobe", "ffprobe") or "ffprobe"

    @property
    def cookies_file(self) -> Path | None:
        """Configured cookie file, or None when `[cookies] file` is unset.

        `[cookies] file` is the single source of truth: unset / empty /
        commented-out keeps the tool anonymous. There is deliberately no
        implicit detection of a `cookies.txt` lying around.
        """
        configured = self.setting("cookies", "file")
        if not configured:
            return None
        return Path(configured).expanduser()

    @property
    def http_timeout(self) -> float:
        return float(self.setting("network", "http_timeout", "60") or 60)

    @property
    def poll_interval(self) -> float:
        return float(self.setting("asr", "poll_interval", "5") or 5)

    @property
    def poll_timeout(self) -> float:
        # MEDIA_POLL_TIMEOUT overrides config.ini, which makes the timeout path
        # testable without waiting for the real 30-minute budget.
        return float(self.get("MEDIA_POLL_TIMEOUT") or self.setting("asr", "poll_timeout", "1800") or 1800)


def cookies_file_problem(path: Path) -> str | None:
    """Return a human-readable problem with a configured cookie file, else None.

    Used both by the yt-dlp wrapper (fail fast instead of silently pretending
    cookies are in use) and by `voxsuji doctor` (report the same facts). Only
    local file checks — never touches the network or the file's contents.
    """
    if not path.exists():
        return f"cookies file not found: {path}"
    if not path.is_file():
        return f"cookies path is not a regular file: {path}"
    # Mode-bits check (not os.access) so it behaves the same for root.
    if not stat.S_IMODE(path.stat().st_mode) & 0o444:
        return f"cookies file is not readable: {path}"
    return None


def cookies_permission_warning(path: Path) -> str | None:
    """Warning when the cookie file is group/other-accessible (advise chmod 600)."""
    if not path.is_file():
        return None
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        return f"cookies file permissions are too open (mode {mode:04o}); chmod 600 {path}"
    return None
