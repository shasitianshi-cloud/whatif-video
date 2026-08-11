import base64
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import tts_adapter


CONFIG = {
    "provider": "volcengine",
    "protocol": "v3_http_chunked_unidirectional",
    "endpoint": "https://openspeech.bytedance.com/api/v3/tts/unidirectional",
    "resource_id": "seed-tts-2.0", "speaker": "zh_female_vv_uranus_bigtts",
    "audio_format": "mp3", "sample_rate": 24000, "speech_rate": 15,
    "loudness_rate": 0, "concurrency_max": 5, "max_text_utf8_bytes": 1024,
}


class FakeResponse:
    status = 200
    headers = {"X-Tt-Logid": "safe-log-id"}
    def __init__(self, frames): self.frames = frames
    def __iter__(self):
        return iter((json.dumps(frame).encode() + b"\n") for frame in self.frames)


class TTSContractTests(unittest.TestCase):
    def test_credential_from_environment(self):
        with patch.dict(os.environ, {"VOLCENGINE_TTS_API_KEY": "runtime-only"}):
            self.assertEqual(tts_adapter.load_api_key(), "runtime-only")

    def test_fixed_config_and_no_credential_or_speed_ratio(self):
        actual = json.loads((Path(__file__).parents[1] / "config/tts.json").read_text())
        self.assertEqual(actual, CONFIG)
        self.assertFalse(any("key" in k.lower() or "token" in k.lower() for k in actual))
        self.assertNotIn("speed_ratio", actual)

    def test_request_ids_unique(self):
        self.assertNotEqual(tts_adapter.new_request_id(), tts_adapter.new_request_id())

    def test_request_shape_and_headers(self):
        captured = {}
        def opener(request, **_kwargs):
            captured["request"] = request
            return FakeResponse([
                {"code": 0, "data": base64.b64encode(b"fake-mp3").decode()},
                {"code": 0, "data": None, "sentence": {"text": "metadata"}},
                {"code": 20000000, "message": "ok"},
            ])
        adapter = tts_adapter.VolcengineTTSAdapter(CONFIG, opener=opener)
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(os.environ, {"VOLCENGINE_TTS_API_KEY": "runtime-only"}), \
             patch.object(tts_adapter, "measure_duration_ms", return_value=1234):
            adapter.synthesize("测试。", Path(tmp) / "audio.mp3")
        request = captured["request"]
        body = json.loads(request.data)
        self.assertEqual(body["req_params"]["speaker"], CONFIG["speaker"])
        self.assertEqual(body["req_params"]["audio_params"], {
            "format": "mp3", "sample_rate": 24000,
            "speech_rate": 15, "loudness_rate": 0,
        })
        self.assertEqual(request.headers["X-api-resource-id"], "seed-tts-2.0")
        self.assertNotIn("model", body)
        self.assertNotIn("text_prompt", body)

    def test_provider_error_does_not_write_audio(self):
        adapter = tts_adapter.VolcengineTTSAdapter(CONFIG,
            opener=lambda *_a, **_k: FakeResponse([{"code": 55000000, "message": "no"}]))
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"VOLCENGINE_TTS_API_KEY": "x"}):
            output = Path(tmp) / "audio.mp3"
            with self.assertRaises(tts_adapter.TTSProviderError):
                adapter.synthesize("测试。", output)
            self.assertFalse(output.exists())

    def test_incomplete_stream_does_not_write_audio(self):
        audio = base64.b64encode(b"partial").decode()
        adapter = tts_adapter.VolcengineTTSAdapter(CONFIG,
            opener=lambda *_a, **_k: FakeResponse([{"code": 0, "data": audio}]))
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"VOLCENGINE_TTS_API_KEY": "x"}):
            output = Path(tmp) / "audio.mp3"
            with self.assertRaises(tts_adapter.TTSProviderError):
                adapter.synthesize("测试。", output)
            self.assertFalse(output.exists())

    def test_ffprobe_required_for_success(self):
        frames = [
            {"code": 0, "data": base64.b64encode(b"not-audio").decode()},
            {"code": 20000000, "message": "ok"},
        ]
        adapter = tts_adapter.VolcengineTTSAdapter(CONFIG,
            opener=lambda *_a, **_k: FakeResponse(frames))
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"VOLCENGINE_TTS_API_KEY": "x"}):
            output = Path(tmp) / "audio.mp3"
            with self.assertRaises(RuntimeError):
                adapter.synthesize("测试。", output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
