"""Volcengine (火山引擎) Doubao recording-file ASR adapter.

VERIFIED end-to-end against the live service (2026-09-20) with the new-console
API key: submit -> poll -> result -> normalization, using
``X-Api-Resource-Id: volc.seedasr.auc`` (豆包录音文件识别模型2.0 标准版).

Auth is header-based and the service documents two styles, both supported here:

* new console (``VOLC_API_KEY``) -> ``X-Api-Key``
* legacy console (``VOLC_APP_ID`` + ``VOLC_ACCESS_TOKEN``) ->
  ``X-Api-App-Key`` / ``X-Api-Access-Key``
  (docs.volcengine.com/docs/6561/2534847, section 语音识别)

``X-Api-Resource-Id`` doubles as the model selector; ``volc.seedasr.auc`` is
模型2.0 标准版 and ``volc.bigasr.auc`` is the older 模型1.0. Entitlement is
per-model: an unopened model answers HTTP 403 ``code 45000030``.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from ..models import Segment, Word
from ..util import log
from .base import AsrResult, BaseProvider, ProviderError, _http_json_ex, _poll

SUBMIT_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
QUERY_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"

STATUS_OK = "20000000"
STATUS_PROCESSING = {"20000001", "20000002"}


class VolcengineProvider(BaseProvider):
    name = "volcengine"
    models = ("volc.seedasr.auc", "volc.bigasr.auc")

    @property
    def resource_id(self) -> str:
        # `VOLC_RESOURCE_ID` is the env-var form advertised by .env.example;
        # `[provider.volcengine] model` in config.ini is the non-secret override.
        return (
            self.config.get("VOLC_RESOURCE_ID")
            or self.config.setting("provider.volcengine", "model", self.models[0])
            or self.models[0]
        )

    def _headers(self, task_id: str, *, submit: bool) -> dict[str, str]:
        api_key = self.config.get("VOLC_API_KEY")
        app_id = self.config.get("VOLC_APP_ID")
        access_token = self.config.get("VOLC_ACCESS_TOKEN")
        headers = {
            "Content-Type": "application/json",
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Request-Id": task_id,
        }
        if api_key:
            headers["X-Api-Key"] = api_key
        elif app_id and access_token:
            headers["X-Api-App-Key"] = app_id
            headers["X-Api-Access-Key"] = access_token
        else:
            raise ProviderError(
                "volcengine is not configured: set VOLC_API_KEY, or VOLC_APP_ID + VOLC_ACCESS_TOKEN"
            )
        if submit:
            headers["X-Api-Sequence"] = "-1"
        return headers

    def transcribe(self, audio_url: str, *, language: str | None = None,
                   audio_path: Path | None = None) -> AsrResult:
        task_id = str(uuid.uuid4())
        audio_format = (audio_path.suffix.lstrip(".") if audio_path else "mp3") or "mp3"
        payload = {
            "user": {"uid": self.config.get("VOLC_UID", "voxsuji") or "voxsuji"},
            "audio": {"url": audio_url, "format": audio_format},
            "request": {
                "model_name": "bigmodel",
                "enable_punc": True,
                "show_utterances": True,
            },
        }
        if language:
            payload["audio"]["language"] = language

        _, _, headers = _http_json_ex(
            SUBMIT_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(task_id, submit=True),
            method="POST",
            timeout=self.config.http_timeout,
        )
        self._check_status(headers, stage="submit")
        log(f"  submitted ASR task {task_id}")

        def fetch():
            _, body, resp_headers = _http_json_ex(
                QUERY_URL,
                data=b"{}",
                headers=self._headers(task_id, submit=False),
                method="POST",
                timeout=self.config.http_timeout,
            )
            code = resp_headers.get("x-api-status-code", "")
            if code == STATUS_OK:
                return "done", body
            if code in STATUS_PROCESSING:
                return "pending", {"status": code}
            return "failed", {"status_code": code, "message": resp_headers.get("x-api-message"), "body": body}

        completed = _poll(
            self.config.poll_timeout,
            self.config.poll_interval,
            fetch,
            describe=f"volcengine task {task_id}",
        )
        return self._normalize(completed, task_id=task_id)

    def _check_status(self, headers: dict[str, str], *, stage: str) -> None:
        code = headers.get("x-api-status-code", "")
        if code and code != STATUS_OK:
            raise ProviderError(
                f"volcengine {stage} failed: status={code} message={headers.get('x-api-message')} "
                f"logid={headers.get('x-tt-logid')}"
            )

    def _normalize(self, body: dict, *, task_id: str) -> AsrResult:
        result = body.get("result") or {}
        utterances = result.get("utterances") or []
        segments: list[Segment] = []
        for item in utterances:
            additions = item.get("additions") or {}
            speaker = additions.get("speaker")
            # Whitespace separators come back with start_time/end_time == -1, the
            # service's "no timing" sentinel; keeping them would put -0.001 s
            # timestamps into the schema. They carry no text of their own.
            timed = [word for word in (item.get("words") or []) if _is_timed(word)]
            words = (
                [
                    Word(
                        start=_ms(word.get("start_time")),
                        end=_ms(word.get("end_time")),
                        text=word.get("text", ""),
                    )
                    for word in timed
                ]
                if timed
                else None
            )
            segments.append(
                Segment(
                    start=_ms(item.get("start_time")),
                    end=_ms(item.get("end_time")),
                    text=(item.get("text") or "").strip(),
                    speaker=str(speaker) if speaker not in (None, "") else None,
                    words=words,
                )
            )
        if not segments and result.get("text"):
            segments = [Segment(start=0.0, end=0.0, text=result["text"].strip())]

        audio_info = body.get("audio_info") or {}
        duration_ms = audio_info.get("duration")
        provider_meta = {
            "task_id": task_id,
            "resource_id": self.resource_id,
            "duration_ms": duration_ms,
            "audio_info": audio_info,
        }
        return AsrResult(
            provider=self.name,
            model=self.resource_id,
            segments=segments,
            language=audio_info.get("language"),
            duration=float(duration_ms) / 1000.0 if duration_ms else None,
            provider_meta={k: v for k, v in provider_meta.items() if v is not None},
            raw=body,
        )


def _ms(value) -> float:
    """Milliseconds -> seconds.

    Negative values are the service's "no timing" sentinel (-1); they must never
    reach the normalized schema as a negative timestamp.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number / 1000.0 if number >= 0 else 0.0


def _is_timed(word: dict) -> bool:
    """True when a word token carries a real (non-sentinel) timestamp."""
    try:
        return float(word.get("start_time")) >= 0 and float(word.get("end_time")) >= 0
    except (TypeError, ValueError):
        return False


PROVIDER = VolcengineProvider
