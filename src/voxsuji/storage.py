"""Object storage wiring for the temporary ASR upload."""

from __future__ import annotations

import urllib.error
import urllib.request

from .config import Config
from .s3 import S3Client, StorageError


def storage_configured(config: Config) -> bool:
    return not storage_missing(config)


def storage_missing(config: Config) -> list[str]:
    """Secret-kind settings only; endpoint/region have non-secret defaults."""
    from .config import _is_real

    missing = []
    if not _is_real(_setting_or_env(config, "bucket")):
        missing.append("STORAGE_BUCKET (or config.ini [storage] bucket)")
    if not _is_real(config.get("STORAGE_ACCESS_KEY")):
        missing.append("STORAGE_ACCESS_KEY")
    if not _is_real(config.get("STORAGE_SECRET_KEY")):
        missing.append("STORAGE_SECRET_KEY")
    return missing


def _setting_or_env(config: Config, name: str, default: str | None = None) -> str | None:
    return config.get(f"STORAGE_{name.upper()}") or config.setting("storage", name, default)


def build_client(config: Config) -> S3Client:
    missing = storage_missing(config)
    if missing:
        raise StorageError(
            "object storage is not configured; missing: "
            + ", ".join(missing)
            + " (copy .env.example to .env and fill it in)"
        )
    return S3Client(
        endpoint=_setting_or_env(config, "endpoint", "") or "",
        bucket=_setting_or_env(config, "bucket", "") or "",
        access_key=config.get("STORAGE_ACCESS_KEY", "") or "",
        secret_key=config.get("STORAGE_SECRET_KEY", "") or "",
        region=_setting_or_env(config, "region", "us-east-1") or "us-east-1",
        path_style=(_setting_or_env(config, "path_style", "") or "").lower() in ("1", "true", "yes"),
        public_base_url=config.get("STORAGE_PUBLIC_BASE_URL"),
        timeout=float(config.setting("network", "upload_timeout", "300") or 300),
    )


def verify_public_read(url: str, *, timeout: float = 60, expect_prefix: bytes | None = None) -> dict:
    """Anonymous GET/HEAD check — proves the ASR service can fetch the object."""
    request = urllib.request.Request(url, headers={"User-Agent": "voxsuji/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            content_type = response.headers.get("Content-Type")
            length = response.headers.get("Content-Length")
            head = response.read(1024)
    except urllib.error.HTTPError as exc:
        raise StorageError(
            f"anonymous read of {url} failed with HTTP {exc.code}; the bucket must be publicly readable"
        ) from exc
    except urllib.error.URLError as exc:
        raise StorageError(f"anonymous read of {url} failed: {exc.reason}") from exc
    if status != 200:
        raise StorageError(f"anonymous read of {url} returned HTTP {status}")
    if expect_prefix and not head.startswith(expect_prefix[: len(head)]):
        # ID3 tag or mp3 frame sync are the expected first bytes for our encoding.
        raise StorageError(
            f"anonymous read of {url} did not look like an audio file (first bytes: {head[:16]!r})"
        )
    return {"status": status, "content_type": content_type, "content_length": length}
