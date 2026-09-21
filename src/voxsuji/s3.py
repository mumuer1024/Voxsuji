"""Minimal stdlib S3 client (AWS Signature V4) for S3-compatible object storage.

Only the three operations this tool needs are implemented: PUT, DELETE and HEAD.
Kept deliberately small so the project needs no vendor SDK; the S3-compatible
HTTP API is stable and documented.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

_ALGO = "AWS4-HMAC-SHA256"
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()

# Clients whose addressing style has already been auto-corrected (by id()).
_AUTO_STYLE_DISABLED: dict[int, bool] = {}


class StorageError(RuntimeError):
    pass


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


@dataclass
class S3Client:
    endpoint: str
    bucket: str
    access_key: str
    secret_key: str
    region: str = "us-east-1"
    path_style: bool = False
    public_base_url: str | None = None
    timeout: float = 120.0

    # Addressing note: the public base URL must match the style used for
    # requests, otherwise anonymous reads would 404. We do not try to derive
    # virtual-host vs path style from the endpoint hostname, because
    # "bucket.example.com" and "example.com" are indistinguishable; instead
    # STORAGE_PATH_STYLE (config: [storage] path_style) decides, and a fully
    # expanded STORAGE_PUBLIC_BASE_URL can be supplied to override the guess.
    def __post_init__(self) -> None:
        parsed = urllib.parse.urlsplit(self.endpoint)
        if not parsed.scheme or not parsed.netloc:
            raise StorageError(f"invalid STORAGE_ENDPOINT: {self.endpoint!r}")
        self._scheme = parsed.scheme
        self._netloc = parsed.netloc
        self._base_path = parsed.path.rstrip("/")
        if self.public_base_url:
            self.public_base_url = self.public_base_url.rstrip("/")
        elif self.path_style:
            self.public_base_url = f"{self._scheme}://{self._netloc}/{self.bucket}"
        else:
            self.public_base_url = f"{self._scheme}://{self._netloc}"

    # -- URL helpers ------------------------------------------------------
    def _host(self) -> str:
        return self._netloc

    def _object_path(self, key: str) -> str:
        quoted = urllib.parse.quote(key, safe="/~")
        if self.path_style:
            return f"{self._base_path}/{self.bucket}/{quoted}"
        return f"{self._base_path}/{quoted}"

    def public_url(self, key: str) -> str:
        return f"{self.public_base_url}/{urllib.parse.quote(key, safe='/~')}"

    # -- request signing --------------------------------------------------
    def _signed_headers(self, method: str, key: str, payload: bytes, content_type: str) -> dict[str, str]:
        now = _dt.datetime.now(_dt.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        datestamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(payload).hexdigest() if payload else _EMPTY_SHA256
        host = self._host()
        headers = {
            "host": host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        if content_type:
            headers["content-type"] = content_type

        signed_names = sorted(headers)
        canonical_headers = "".join(f"{name}:{headers[name].strip()}\n" for name in signed_names)
        signed_headers = ";".join(signed_names)
        canonical_request = "\n".join(
            [
                method,
                self._object_path(key),
                "",
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )
        scope = f"{datestamp}/{self.region}/s3/aws4_request"
        string_to_sign = "\n".join(
            [
                _ALGO,
                amz_date,
                scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signing_key = _sign(
            _sign(_sign(_sign(f"AWS4{self.secret_key}".encode("utf-8"), datestamp), self.region), "s3"),
            "aws4_request",
        )
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authorization = (
            f"{_ALGO} Credential={self.access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        out = {k: v for k, v in headers.items() if k != "host"}
        out["Host"] = host
        out["Authorization"] = authorization
        return out

    def _request(self, method: str, key: str, payload: bytes = b"", content_type: str = "") -> urllib.response.addinfourl:  # type: ignore[name-defined]
        try:
            return self._send(method, key, payload, content_type)
        except StorageError as exc:
            # A bucket-host endpoint paired with path-style addressing fails on
            # some S3-compatible services; auto-correct once for the whole client.
            if "AccessDenied" in str(exc) and not _AUTO_STYLE_DISABLED.get(id(self)):
                self.path_style = not self.path_style
                self.public_base_url = None
                self.__post_init__()
                _AUTO_STYLE_DISABLED[id(self)] = True
                return self._send(method, key, payload, content_type)
            raise

    def _send(self, method: str, key: str, payload: bytes, content_type: str):
        url = f"{self._scheme}://{self._netloc}{self._object_path(key)}"
        headers = self._signed_headers(method, key, payload, content_type)
        request = urllib.request.Request(url, data=payload if payload else None, headers=headers, method=method)
        try:
            return urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            body = exc.read()[:500].decode("utf-8", "replace")
            raise StorageError(f"{method} {url} -> HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise StorageError(f"{method} {url} -> {exc.reason}") from exc

    # -- public API -------------------------------------------------------
    def head(self, key: str) -> dict[str, str]:
        """HEAD the *object* with credentials (not the anonymous check)."""
        with self._request("HEAD", key) as response:
            return dict(response.headers)

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        with self._request("PUT", key, data, content_type) as response:
            if response.status not in (200, 201):
                raise StorageError(f"PUT {key} -> unexpected status {response.status}")
        return self.public_url(key)

    def put_file(self, key: str, path, content_type: str = "application/octet-stream") -> str:
        from pathlib import Path

        return self.put_bytes(key, Path(path).read_bytes(), content_type)

    def delete(self, key: str) -> None:
        with self._request("DELETE", key) as response:
            if response.status not in (200, 202, 204):
                raise StorageError(f"DELETE {key} -> unexpected status {response.status}")
