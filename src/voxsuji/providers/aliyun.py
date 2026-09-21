"""Aliyun Bailian (DashScope) file transcription adapter.

Verified against the live API during development.
"""

from __future__ import annotations

import json

from ..models import Segment, Word
from ..util import log
from .base import AsrResult, BaseProvider, ProviderError, _download_json, _http_json, _poll

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"


class AliyunProvider(BaseProvider):
    name = "aliyun"
    models = ("qwen-audio-3.0-asr-flash-filetrans",)

    @property
    def base_url(self) -> str:
        return (self.config.get("DASHSCOPE_BASE_URL", DEFAULT_BASE_URL) or DEFAULT_BASE_URL).rstrip("/")

    def _headers(self, *, async_submit: bool = False) -> dict[str, str]:
        key = self.config.get("DASHSCOPE_API_KEY")
        if not key:
            raise ProviderError("DASHSCOPE_API_KEY is not configured (see .env.example)")
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        # X-DashScope-Async is a submit-only header. Sending it on the task query
        # makes the service reject the call with
        # "current user api does not support asynchronous calls" (HTTP 403).
        if async_submit:
            headers["X-DashScope-Async"] = "enable"
        return headers

    def transcribe(self, audio_url: str, *, language: str | None = None,
                   audio_path=None) -> AsrResult:
        model = self.configured_model()
        body: dict = {"model": model, "input": {"file_urls": [audio_url]}}
        parameters: dict = {"channel_id": [0]}
        if language:
            parameters["language_hints"] = [language]
        body["parameters"] = parameters

        status, payload = _http_json(
            f"{self.base_url}/services/audio/asr/transcription",
            data=json.dumps(body).encode("utf-8"),
            headers=self._headers(async_submit=True),
            method="POST",
            timeout=self.config.http_timeout,
        )
        task_id = ((payload.get("output") or {}).get("task_id")) if isinstance(payload, dict) else None
        if not task_id:
            raise ProviderError(
                f"submit did not return a task_id (HTTP {status}): "
                f"{json.dumps(payload, ensure_ascii=False)[:600]}"
            )
        log(f"  submitted ASR task {task_id}")

        def fetch():
            _, state = _http_json(
                f"{self.base_url}/tasks/{task_id}",
                headers=self._headers(),
                method="GET",
                timeout=self.config.http_timeout,
            )
            output = (state.get("output") or {}) if isinstance(state, dict) else {}
            task_status = output.get("task_status") or state.get("task_status")
            if task_status == "SUCCEEDED":
                return "done", state
            if task_status in ("FAILED", "UNKNOWN"):
                return "failed", state
            return "pending", {"status": task_status, "raw": state}

        completed = _poll(
            self.config.poll_timeout,
            self.config.poll_interval,
            fetch,
            describe=f"aliyun task {task_id}",
        )
        return self._normalize(completed, model=model, task_id=task_id)

    # -- response mapping -------------------------------------------------
    def _normalize(self, completed: dict, *, model: str, task_id: str) -> AsrResult:
        output = completed.get("output") or {}
        results = output.get("results") or []
        if not results:
            raise ProviderError(f"task {task_id} succeeded but returned no results")
        result = results[0]
        subtask_status = result.get("subtask_status")
        if subtask_status and subtask_status != "SUCCEEDED":
            raise ProviderError(
                f"subtask failed ({subtask_status}): {json.dumps(result, ensure_ascii=False)[:600]}"
            )
        url = result.get("transcription_url")
        if not url:
            raise ProviderError(f"no transcription_url in task result: {json.dumps(result)[:400]}")

        raw = _download_json(url)
        return self._normalize_from_raw(
            raw, model=model, task_id=task_id, completed=completed
        )

    def _normalize_from_raw(
        self, raw: dict, *, model: str, task_id: str, completed: dict | None = None
    ) -> AsrResult:
        completed = completed or {}
        segments: list[Segment] = []
        transcripts = raw.get("transcripts") or []
        channel = transcripts[0] if transcripts else {}
        for sentence in channel.get("sentences") or []:
            words = None
            if sentence.get("words"):
                words = [
                    Word(
                        start=_ms(word.get("begin_time")),
                        end=_ms(word.get("end_time")),
                        text=word.get("text", ""),
                        punctuation=word.get("punctuation", "") or "",
                    )
                    for word in sentence["words"]
                ]
            speaker = sentence.get("speaker") or sentence.get("speaker_id")
            segments.append(
                Segment(
                    start=_ms(sentence.get("begin_time")),
                    end=_ms(sentence.get("end_time")),
                    text=(sentence.get("text") or "").strip(),
                    speaker=str(speaker) if speaker not in (None, "") else None,
                    words=words,
                )
            )
        if not segments and channel.get("text"):
            segments = [Segment(start=0.0, end=_ms(channel.get("content_duration_in_milliseconds")),
                                text=channel["text"].strip())]

        properties = raw.get("properties") or {}
        duration_ms = properties.get("original_duration_in_milliseconds")
        meta = {
            "task_id": task_id,
            "request_id": completed.get("request_id"),
            "audio_format": properties.get("audio_format"),
            "sampling_rate": properties.get("original_sampling_rate"),
            "channels": properties.get("channels"),
            "file_url": raw.get("file_url"),
            "usage": completed.get("usage"),
        }
        return AsrResult(
            provider=self.name,
            model=model,
            segments=segments,
            language=channel.get("language") or properties.get("language"),
            duration=float(duration_ms) / 1000.0 if duration_ms else None,
            provider_meta={k: v for k, v in meta.items() if v is not None},
            raw=raw,
        )


def _ms(value) -> float:
    try:
        return float(value) / 1000.0
    except (TypeError, ValueError):
        return 0.0

PROVIDER = AliyunProvider

