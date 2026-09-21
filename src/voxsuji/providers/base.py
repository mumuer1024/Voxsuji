"""ASR provider abstraction (deliberately thin).

Each adapter turns an audio file that is already reachable at a public URL into a
list of normalized ``Segment`` objects.  Anything provider-specific that is worth
keeping is returned separately and stored in the ``raw`` sidecar.
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Config
from ..models import Segment, Word
from ..util import CommandError, log

# Documented category/model metadata returned by providers lands in `provider_meta`.
REGISTRY: dict[str, str] = {}


@dataclass
class AsrResult:
    provider: str
    model: str
    segments: list[Segment]
    language: str | None = None
    duration: float | None = None
    provider_meta: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


class ProviderError(RuntimeError):
    """Raised for provider-side failures; message must stay diagnostic-only."""


def _http_json(url: str, *, data: bytes | None = None, headers: dict | None = None,
               method: str | None = None, timeout: float = 60) -> tuple[int, dict]:
    status, body, _ = _http_json_ex(url, data=data, headers=headers, method=method, timeout=timeout)
    return status, body


def _http_json_ex(
    url: str,
    *,
    data: bytes | None = None,
    headers: dict | None = None,
    method: str | None = None,
    timeout: float = 60,
) -> tuple[int, dict, dict]:
    """Return (status, parsed_body, response_headers).

    Some providers (Volcengine) carry the real status in HTTP headers, so the
    full header map is needed by those adapters.
    """
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            resp_headers = {k.lower(): v for k, v in response.headers.items()}
            body = raw.decode("utf-8", "replace")
            try:
                return response.status, json.loads(body), resp_headers
            except json.JSONDecodeError:
                return response.status, {"_raw_body": body[:2000]}, resp_headers
    except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
        body = exc.read()[:800].decode("utf-8", "replace")
        raise ProviderError(f"HTTP {exc.code} from {url}: {body}") from exc
    except urllib.error.URLError as exc:  # type: ignore[attr-defined]
        raise ProviderError(f"could not reach {url}: {exc.reason}") from exc


def _download_json(url: str, *, timeout: float = 120) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "voxsuji/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
        raise ProviderError(f"HTTP {exc.code} while downloading transcription result") from exc
    except urllib.error.URLError as exc:  # type: ignore[attr-defined]
        raise ProviderError(f"could not download transcription result: {exc.reason}") from exc


class BaseProvider:
    name = "base"
    models: tuple[str, ...] = ()

    def __init__(self, config: Config) -> None:
        self.config = config

    @property
    def model(self) -> str:
        return self.models[0] if self.models else ""

    def missing_config(self) -> list[str]:
        return self.config.missing_provider_env(self.name)

    def available(self) -> bool:
        return not self.missing_config()

    def configured_model(self) -> str:
        return self.config.setting(f"provider.{self.name}", "model", self.model) or self.model

    def transcribe(self, audio_url: str, *, language: str | None = None,
                   audio_path: Path | None = None) -> AsrResult:
        raise NotImplementedError


def _poll(deadline_seconds: float, interval: float, fetch, *, describe: str) -> dict:
    """Poll `fetch()` until it signals completion or the deadline passes."""
    started = time.monotonic()
    attempt = 0
    while True:
        attempt += 1
        state, payload = fetch()
        if state == "done":
            return payload
        if state == "failed":
            raise ProviderError(f"{describe} failed: {json.dumps(payload, ensure_ascii=False)[:600]}")
        if time.monotonic() - started > deadline_seconds:
            raise ProviderError(
                f"{describe} did not finish within {int(deadline_seconds)}s "
                f"(last status: {payload.get('status') if isinstance(payload, dict) else payload})"
            )
        if attempt == 1 or attempt % 6 == 0:
            status = payload.get("status") if isinstance(payload, dict) else ""
            log(f"  ... {describe} status={status or 'pending'} ({int(time.monotonic() - started)}s)")
        time.sleep(interval)


def get_provider(name: str, config: Config) -> BaseProvider:
    """Look up an adapter lazily so one broken module cannot break the others."""
    import importlib

    supported = {
        "aliyun": "aliyun",
        "volcengine": "volcengine",
        "tencent": "tencent",
    }
    if name not in supported:
        raise CommandError(f"unknown provider {name!r}; known: {', '.join(sorted(supported))}")
    module = importlib.import_module(f".{supported[name]}", package=__package__)
    return module.PROVIDER(config)
