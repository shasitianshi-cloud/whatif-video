from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import re
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


ENDPOINT = "https://visual.volcengineapi.com"
HOST = "visual.volcengineapi.com"
REGION = "cn-north-1"
SERVICE = "cv"
VERSION = "2022-08-31"
REQ_KEY = "high_aes_general_v30l_zt2i"


class AdapterError(RuntimeError):
    def __init__(self, code: str, message: str, *, ambiguous: bool = False):
        super().__init__(message)
        self.code = code
        self.ambiguous = ambiguous


def load_access_key(path: Path) -> tuple[str, str]:
    lines = [x.strip() for x in path.read_text(encoding="utf-8-sig").splitlines() if x.strip()]
    if len(lines) != 2:
        raise AdapterError("CREDENTIAL_FORMAT_INVALID", "expected exactly two credential records")
    values: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^\s*(Access\s*Key(?:\s*ID)?|AccessKeyId|Secret\s*Access\s*Key|SecretAccessKey|Secret\s*Key)\s*[:=\t ]+\s*(\S+)\s*$", line, re.I)
        if not match:
            raise AdapterError("CREDENTIAL_FORMAT_INVALID", "unrecognized credential label")
        label = re.sub(r"[^a-z]", "", match.group(1).lower())
        kind = "sk" if label.startswith("secret") else "ak"
        if kind in values or not match.group(2):
            raise AdapterError("CREDENTIAL_FORMAT_INVALID", "duplicate or empty credential")
        values[kind] = match.group(2)
    if set(values) != {"ak", "sk"}:
        raise AdapterError("CREDENTIAL_TYPE_MISMATCH", "AccessKeyID/SecretAccessKey pair required")
    return values["ak"], values["sk"]


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def image_dimensions(data: bytes) -> tuple[int, int]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data.startswith(b"\xff\xd8"):
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            i += 2
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                continue
            if i + 2 > len(data):
                break
            length = int.from_bytes(data[i:i + 2], "big")
            if marker in range(0xC0, 0xC4) and i + 7 < len(data):
                return int.from_bytes(data[i + 5:i + 7], "big"), int.from_bytes(data[i + 3:i + 5], "big")
            i += length
    raise AdapterError("IMAGE_FORMAT_UNSUPPORTED", "unable to read image dimensions")


@dataclass
class CallResult:
    task_id: str
    request_id: str | None
    image_bytes: bytes
    redacted_response: dict


class VolcengineImageAdapter:
    def __init__(self, access_key: str, secret_key: str, *, timeout: int = 60):
        self._ak = access_key
        self._sk = secret_key
        self.timeout = timeout
        self.in_flight = 0
        self.max_in_flight = 0
        self.generation_requests = 0

    def _request(self, action: str, payload: dict, *, submission: bool) -> dict:
        if self.in_flight != 0:
            raise AdapterError("CONCURRENCY_VIOLATION", "only one request may be in flight")
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        now = dt.datetime.now(dt.timezone.utc)
        x_date = now.strftime("%Y%m%dT%H%M%SZ")
        short_date = now.strftime("%Y%m%d")
        body_hash = hashlib.sha256(body).hexdigest()
        query = urllib.parse.urlencode({"Action": action, "Version": VERSION})
        signed_headers = "content-type;host;x-content-sha256;x-date"
        canonical_headers = f"content-type:application/json\nhost:{HOST}\nx-content-sha256:{body_hash}\nx-date:{x_date}\n"
        canonical = f"POST\n/\n{query}\n{canonical_headers}\n{signed_headers}\n{body_hash}"
        scope = f"{short_date}/{REGION}/{SERVICE}/request"
        string_to_sign = f"HMAC-SHA256\n{x_date}\n{scope}\n{hashlib.sha256(canonical.encode()).hexdigest()}"
        k_date = _sign(self._sk.encode(), short_date)
        k_region = _sign(k_date, REGION)
        k_service = _sign(k_region, SERVICE)
        k_signing = _sign(k_service, "request")
        signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()
        authorization = f"HMAC-SHA256 Credential={self._ak}/{scope}, SignedHeaders={signed_headers}, Signature={signature}"
        req = urllib.request.Request(
            f"{ENDPOINT}/?{query}", data=body, method="POST",
            headers={"Content-Type": "application/json", "Host": HOST, "X-Content-Sha256": body_hash, "X-Date": x_date, "Authorization": authorization},
        )
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        if submission:
            self.generation_requests += 1
        try:
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    raw = response.read()
                    status = response.status
            except urllib.error.HTTPError as exc:
                raw = exc.read()
                status = exc.code
            except (TimeoutError, OSError) as exc:
                raise AdapterError("AMBIGUOUS_IMAGE_SUBMISSION" if submission else "NETWORK_RESULT_UNKNOWN", str(exc), ambiguous=submission) from exc
        finally:
            self.in_flight -= 1
        try:
            obj = json.loads(raw)
        except Exception as exc:
            raise AdapterError("PROVIDER_RESPONSE_INVALID", f"HTTP {status}: invalid JSON") from exc
        if status < 200 or status >= 300 or obj.get("code") not in (0, 10000):
            raise AdapterError(str(obj.get("code") or f"HTTP_{status}"), str(obj.get("message") or "provider rejection"))
        return obj

    def generate(self, prompt: str, *, width: int = 1024, height: int = 1024, poll_interval: int = 3, max_polls: int = 100) -> CallResult:
        submit = self._request("CVSync2AsyncSubmitTask", {"req_key": REQ_KEY, "prompt": prompt, "width": width, "height": height}, submission=True)
        task_id = str((submit.get("data") or {}).get("task_id") or "")
        if not task_id:
            raise AdapterError("TASK_ID_MISSING", "submit succeeded without task_id", ambiguous=True)
        last = None
        for _ in range(max_polls):
            last = self._request("CVSync2AsyncGetResult", {"req_key": REQ_KEY, "task_id": task_id}, submission=False)
            data = last.get("data") or {}
            urls = data.get("image_urls") or []
            encoded = data.get("binary_data_base64") or []
            if encoded or urls:
                if encoded:
                    image = base64.b64decode(encoded[0], validate=True)
                else:
                    try:
                        with urllib.request.urlopen(urls[0], timeout=self.timeout) as response:
                            image = response.read()
                    except (TimeoutError, OSError, urllib.error.URLError) as exc:
                        raise AdapterError("IMAGE_DOWNLOAD_FAILED", str(exc)) from exc
                redacted = {"code": last.get("code"), "message": last.get("message"), "request_id": last.get("request_id"), "data": {"status": data.get("status"), "task_id": task_id, "image_count": len(encoded) or len(urls)}}
                return CallResult(task_id, last.get("request_id") or submit.get("request_id"), image, redacted)
            status = str(data.get("status") or "").lower()
            if status in {"failed", "error", "cancelled", "canceled"}:
                raise AdapterError("PROVIDER_TASK_FAILED", str(last.get("message") or status))
            time.sleep(poll_interval)
        raise AdapterError("QUERY_POLL_LIMIT", "task did not complete within poll limit", ambiguous=True)
