"""Volcengine V3 HTTP Chunked unidirectional TTS adapter."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


SUCCESS_FRAME_CODE = 0
TERMINAL_FRAME_CODE = 20000000


class TTSProviderError(RuntimeError):
    def __init__(self, message: str, *, code=None, log_id=None, http_status=None):
        super().__init__(message)
        self.code = code
        self.log_id = log_id
        self.http_status = http_status


@dataclass(frozen=True)
class TTSResult:
    request_id: str
    provider_status: int
    provider_code: int
    provider_message: str | None
    provider_log_id: str | None
    audio_path: str
    audio_sha256: str
    provider_duration_ms: int | None
    measured_duration_ms: int


def load_api_key() -> str:
    value = os.environ["VOLCENGINE_TTS_API_KEY"].strip()
    if not value:
        raise RuntimeError("VOLCENGINE_TTS_API_KEY is empty")
    return value


def new_request_id() -> str:
    return str(uuid.uuid4())


def measure_duration_ms(audio_path: Path) -> int:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        check=False, capture_output=True, text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError("ffprobe could not measure generated audio")
    duration_ms = round(float(proc.stdout.strip()) * 1000)
    if duration_ms <= 0:
        raise RuntimeError("ffprobe returned a non-positive duration")
    return duration_ms


def _header(headers, name: str):
    return headers.get(name) if headers else None


class VolcengineTTSAdapter:
    def __init__(self, config: dict, opener: Callable = urllib.request.urlopen):
        self.config = config
        self.opener = opener
        required = {
            "provider": "volcengine",
            "protocol": "v3_http_chunked_unidirectional",
            "endpoint": "https://openspeech.bytedance.com/api/v3/tts/unidirectional",
            "resource_id": "seed-tts-2.0",
            "speaker": "zh_female_vv_uranus_bigtts",
            "audio_format": "mp3",
            "sample_rate": 24000,
            "speech_rate": 15,
            "loudness_rate": 0,
            "concurrency_max": 5,
        }
        for key, expected in required.items():
            if config.get(key) != expected:
                raise ValueError(f"fixed TTS configuration mismatch: {key}")
        if "speed_ratio" in config:
            raise ValueError("speed_ratio is not permitted")

    def synthesize(self, text: str, output_path: Path) -> TTSResult:
        if not text or not text.strip():
            raise ValueError("TTS segment must contain non-whitespace text")
        if len(text.encode("utf-8")) > int(self.config["max_text_utf8_bytes"]):
            raise ValueError("segment exceeds provider UTF-8 byte limit")

        request_id = new_request_id()
        body = {
            "user": {"uid": "whatif-video"},
            "req_params": {
                "text": text,
                "speaker": self.config["speaker"],
                "audio_params": {
                    "format": self.config["audio_format"],
                    "sample_rate": self.config["sample_rate"],
                    "speech_rate": self.config["speech_rate"],
                    "loudness_rate": self.config["loudness_rate"],
                },
            },
        }
        request = urllib.request.Request(
            self.config["endpoint"],
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": load_api_key(),
                "X-Api-Resource-Id": self.config["resource_id"],
                "X-Api-Request-Id": request_id,
            },
        )
        try:
            response = self.opener(request, timeout=120)
            http_status = getattr(response, "status", 200)
            headers = response.headers
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            message = raw.decode("utf-8", "replace")[:1000]
            try:
                payload = json.loads(message)
                code = payload.get("code")
                message = payload.get("message") or message
            except json.JSONDecodeError:
                code = None
            raise TTSProviderError(message, code=code,
                log_id=_header(exc.headers, "X-Tt-Logid"), http_status=exc.code) from None

        if not 200 <= http_status < 300:
            raise TTSProviderError("provider returned non-success HTTP status",
                log_id=_header(headers, "X-Tt-Logid"), http_status=http_status)

        audio_parts: list[bytes] = []
        terminal = None
        provider_duration_ms = None
        for raw_line in response:
            line = raw_line.strip()
            if not line:
                continue
            try:
                frame = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise TTSProviderError("provider returned an invalid chunked JSON frame",
                    log_id=_header(headers, "X-Tt-Logid"), http_status=http_status) from exc
            code = frame.get("code")
            if code == SUCCESS_FRAME_CODE:
                encoded = frame.get("data")
                # V3 also emits successful metadata frames (for example a
                # sentence event) with data=null. They are not audio and are
                # safe to ignore while waiting for the terminal frame.
                if encoded is None:
                    continue
                if not isinstance(encoded, str) or not encoded:
                    raise TTSProviderError("audio frame contained invalid data", code=code,
                        log_id=_header(headers, "X-Tt-Logid"), http_status=http_status)
                try:
                    audio_parts.append(base64.b64decode(encoded, validate=True))
                except ValueError as exc:
                    raise TTSProviderError("audio frame data was not valid base64", code=code) from exc
            elif code == TERMINAL_FRAME_CODE:
                terminal = frame
                addition = frame.get("addition") or {}
                duration = addition.get("duration") if isinstance(addition, dict) else None
                provider_duration_ms = round(float(duration)) if duration is not None else None
                break
            else:
                raise TTSProviderError(frame.get("message") or "provider rejected synthesis",
                    code=code, log_id=_header(headers, "X-Tt-Logid"), http_status=http_status)

        if terminal is None:
            raise TTSProviderError("chunked response ended without success terminal frame",
                log_id=_header(headers, "X-Tt-Logid"), http_status=http_status)
        audio = b"".join(audio_parts)
        if not audio:
            raise TTSProviderError("successful terminal frame had no audio data",
                code=TERMINAL_FRAME_CODE, log_id=_header(headers, "X-Tt-Logid"))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        partial_path = output_path.with_suffix(output_path.suffix + ".partial")
        try:
            partial_path.write_bytes(audio)
            measured = measure_duration_ms(partial_path)
            partial_path.replace(output_path)
        except Exception:
            partial_path.unlink(missing_ok=True)
            raise
        return TTSResult(
            request_id=request_id, provider_status=http_status,
            provider_code=TERMINAL_FRAME_CODE,
            provider_message=terminal.get("message"),
            provider_log_id=_header(headers, "X-Tt-Logid"),
            audio_path=output_path.as_posix(), audio_sha256=hashlib.sha256(audio).hexdigest(),
            provider_duration_ms=provider_duration_ms, measured_duration_ms=measured,
        )
