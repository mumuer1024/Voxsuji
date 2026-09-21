"""Tencent Cloud ASR adapter (录音文件识别 / CreateRecTask).

VERIFIED end-to-end against the live service (2026-09-20): CreateRecTask with
TC3-HMAC-SHA256 -> DescribeTaskStatus polling -> normalization, using
``EngineModelType=16k_zh`` and ``ResTextFormat=3`` (基础结果 + 词级时间戳 + 标点，
按标点分段). Sentence word offsets are relative to each sentence's ``StartMs``.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import json
from pathlib import Path

from ..models import Segment, Word
from ..util import log
from .base import AsrResult, BaseProvider, ProviderError, _http_json, _poll

HOST = "asr.tencentcloudapi.com"
SERVICE = "asr"
VERSION = "2019-06-14"
ALGORITHM = "TC3-HMAC-SHA256"


def _sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


class TencentProvider(BaseProvider):
    name = "tencent"
    models = ("16k_zh",)

    @property
    def region(self) -> str:
        return self.config.get("TENCENT_REGION", "ap-beijing") or "ap-beijing"

    def _credentials(self) -> tuple[str, str, str | None]:
        secret_id = self.config.get("TENCENT_SECRET_ID")
        secret_key = self.config.get("TENCENT_SECRET_KEY")
        if not secret_id or not secret_key:
            raise ProviderError("tencent is not configured: set TENCENT_SECRET_ID and TENCENT_SECRET_KEY")
        return secret_id, secret_key, self.config.get("TENCENT_TOKEN")

    def _authorization(self, payload: bytes) -> dict[str, str]:
        secret_id, secret_key, token = self._credentials()
        timestamp = int(_dt.datetime.now(_dt.timezone.utc).timestamp())
        date = _dt.datetime.fromtimestamp(timestamp, _dt.timezone.utc).strftime("%Y-%m-%d")
        content_type = "application/json; charset=utf-8"

        canonical_headers = f"content-type:{content_type}\nhost:{HOST}\n"
        signed_headers = "content-type;host"
        hashed_payload = hashlib.sha256(payload).hexdigest()
        canonical_request = "\n".join(
            ["POST", "/", "", canonical_headers, signed_headers, hashed_payload]
        )
        scope = f"{date}/{SERVICE}/tc3_request"
        string_to_sign = "\n".join(
            [
                ALGORITHM,
                str(timestamp),
                scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        secret_date = _sign(f"TC3{secret_key}".encode("utf-8"), date)
        secret_service = _sign(secret_date, SERVICE)
        secret_signing = _sign(secret_service, "tc3_request")
        signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        headers = {
            "Authorization": (
                f"{ALGORITHM} Credential={secret_id}/{scope}, "
                f"SignedHeaders={signed_headers}, Signature={signature}"
            ),
            "Content-Type": content_type,
            "Host": HOST,
            "X-TC-Action": "",
            "X-TC-Version": VERSION,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Region": self.region,
        }
        if token:
            headers["X-TC-Token"] = token
        return headers

    def _call(self, action: str, body: dict) -> dict:
        payload = json.dumps(body).encode("utf-8")
        headers = self._authorization(payload)
        headers["X-TC-Action"] = action
        _, response = _http_json(
            f"https://{HOST}", data=payload, headers=headers, method="POST",
            timeout=self.config.http_timeout,
        )
        envelope = response.get("Response") or {}
        if envelope.get("Error"):
            error = envelope["Error"]
            raise ProviderError(
                f"tencent {action} failed: {error.get('Code')} {error.get('Message')} "
                f"(request_id={envelope.get('RequestId')})"
            )
        return envelope

    def transcribe(self, audio_url: str, *, language: str | None = None,
                   audio_path: Path | None = None) -> AsrResult:
        model = self.configured_model()
        envelope = self._call(
            "CreateRecTask",
            {
                "EngineModelType": model,
                "ChannelNum": 1,
                # 3 = 基础结果 + 词粒度时间戳 + 标点，且按标点分段, i.e. the
                # documented subtitle/transcript shape. 1 (the previous value)
                # returned ~60 s unpunctuated chunks instead of sentences, which
                # does not match a sentence-level normalized schema. Neither 1 nor
                # 3 is a 【增值付费功能】 (only 4 and 5 are).
                "ResTextFormat": 3,
                "SourceType": 0,
                "Url": audio_url,
                "SpeakerDiarization": 0,
            },
        )
        task_id = ((envelope.get("Data") or {}).get("TaskId"))
        if not task_id:
            raise ProviderError(f"tencent CreateRecTask returned no TaskId: {json.dumps(envelope)[:400]}")
        log(f"  submitted ASR task {task_id}")

        def fetch():
            state = self._call("DescribeTaskStatus", {"TaskId": int(task_id)})
            data = state.get("Data") or {}
            status = data.get("Status")
            if status == 2:
                return "done", data
            if status == 3:
                return "failed", {"status": data.get("StatusStr"), "error": data.get("ErrorMsg")}
            return "pending", {"status": data.get("StatusStr") or status}

        completed = _poll(
            self.config.poll_timeout,
            self.config.poll_interval,
            fetch,
            describe=f"tencent task {task_id}",
        )
        return self._normalize(completed, model=model, task_id=task_id)

    def _normalize(self, data: dict, *, model: str, task_id: str) -> AsrResult:
        segments: list[Segment] = []
        for detail in data.get("ResultDetail") or []:
            text = (detail.get("FinalSentence") or detail.get("SliceSentence") or "").strip()
            if not text:
                continue
            start_ms = float(detail.get("StartMs") or 0)
            words = None
            if detail.get("Words"):
                words = [
                    Word(
                        start=(start_ms + float(word.get("OffsetStartMs") or 0)) / 1000.0,
                        end=(start_ms + float(word.get("OffsetEndMs") or 0)) / 1000.0,
                        text=word.get("Word", ""),
                    )
                    for word in detail["Words"]
                ]
            speaker = detail.get("SpeakerId")
            segments.append(
                Segment(
                    start=start_ms / 1000.0,
                    end=float(detail.get("EndMs") or 0) / 1000.0,
                    text=text,
                    speaker=str(speaker) if speaker not in (None, "", 0) else None,
                    words=words,
                )
            )
        if not segments and data.get("Result"):
            segments = [Segment(start=0.0, end=0.0, text=str(data["Result"]).strip())]

        audio_duration = data.get("AudioDuration")
        provider_meta = {
            "task_id": task_id,
            "request_id": data.get("RequestId"),
            "audio_duration": audio_duration,
        }
        return AsrResult(
            provider=self.name,
            model=model,
            segments=segments,
            duration=float(audio_duration) if audio_duration else None,
            provider_meta={k: v for k, v in provider_meta.items() if v is not None},
            raw=data,
        )


PROVIDER = TencentProvider
