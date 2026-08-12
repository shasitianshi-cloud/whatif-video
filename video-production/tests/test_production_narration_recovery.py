from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "video-production" / "src"
sys.path.insert(0, str(SRC))

from production_narration import prepare_narration, synthesize_narration  # noqa: E402

RUN_ID = "production-narration-recovery-regression-v1"
RUN_ROOT = ROOT / "runs" / RUN_ID


class MockAdapter:
    def __init__(self, config: dict):
        self.config = config

    def synthesize(self, text: str, output_path: Path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = ("mock-audio:" + text).encode("utf-8")
        output_path.write_bytes(payload)
        return SimpleNamespace(
            request_id="mock-" + output_path.stem,
            provider_status=200,
            provider_code=20000000,
            provider_message="ok",
            provider_log_id="mock-log-" + output_path.stem,
            audio_path=output_path.as_posix(),
            audio_sha256=hashlib.sha256(payload).hexdigest(),
            provider_duration_ms=1200,
            measured_duration_ms=1200,
        )


def main() -> None:
    shutil.rmtree(RUN_ROOT, ignore_errors=True)
    try:
        vm_root = RUN_ROOT / "video-master"
        vm_root.mkdir(parents=True)
        source = vm_root / "video-master.md"
        # Dynamic count is intentionally three, proving the production path is
        # not bound to the historical ten-segment probe fixture.
        source.write_text("第一段进入城市。第二段来到工厂。第三段回到家庭。\n", encoding="utf-8")
        sha = hashlib.sha256(source.read_bytes()).hexdigest()
        (vm_root / "video-master-gate.json").write_text(
            json.dumps({"run_id": RUN_ID, "status": "PASS", "sha256": sha}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        try:
            prepare_narration(RUN_ID, source, "0" * 64)
        except RuntimeError as exc:
            assert str(exc) == "VIDEO_MASTER_SHA256_MISMATCH"
        else:
            raise AssertionError("wrong SHA was accepted")
        assert not (RUN_ROOT / "video-production" / "narration").exists()

        prepared = prepare_narration(RUN_ID, source, sha)
        plan = prepared["plan_data"]
        assert plan["segment_count"] == 3
        assert plan["segment_count_dynamic"] is True
        assert plan["historical_probe_segment_count_binding"] is False
        assert plan["recovery_entrypoint_reconstructed"] is True
        assert plan["historical_entrypoint_byte_identical"] is False
        assert "".join(x["text"] for x in plan["segments"]) == source.read_text(encoding="utf-8")
        assert all(x["utf8_byte_length"] <= 1024 for x in plan["segments"])

        result = synthesize_narration(RUN_ID, adapter_factory=MockAdapter)
        assert result["gate_data"]["narration_completeness_gate"] == "PASS"
        narration_root = RUN_ROOT / "video-production" / "narration"
        manifest = json.loads((narration_root / "narration-audio-manifest.json").read_text(encoding="utf-8"))
        gate = json.loads((narration_root / "narration-completeness-gate.json").read_text(encoding="utf-8"))
        evidence = json.loads((narration_root / "evidence.json").read_text(encoding="utf-8"))
        assert manifest["segment_count"] == 3
        assert [x["segment_id"] for x in manifest["segments"]] == ["seg-001", "seg-002", "seg-003"]
        assert all((ROOT / x["audio_path"]).is_file() for x in manifest["segments"])
        assert gate["segment_count_dynamic"] is True
        assert gate["narration_completeness_gate"] == "PASS"
        assert evidence["duration_resplit_applied"] is False
        assert evidence["narration_plan_sha256"] == hashlib.sha256((narration_root / "narration-plan.json").read_bytes()).hexdigest()
        assert evidence["narration_audio_manifest_sha256"] == hashlib.sha256((narration_root / "narration-audio-manifest.json").read_bytes()).hexdigest()
        print("PRODUCTION_NARRATION_RECOVERY_REGRESSION=PASS")
        print("SEGMENT_COUNT_DYNAMIC=true")
        print("HISTORICAL_TEN_SEGMENT_PROBE_BYPASSED=true")
        print("PROVIDER_CALL_EXECUTED=false")
    finally:
        shutil.rmtree(RUN_ROOT, ignore_errors=True)


if __name__ == "__main__":
    main()
