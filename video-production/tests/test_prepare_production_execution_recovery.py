from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "video-production" / "src"
sys.path.insert(0, str(SRC))

from prepare_production_execution import prepare_or_advance  # noqa: E402

RUN_ID = "prepare-production-execution-regression-v1"
RUN_ROOT = ROOT / "runs" / RUN_ID


def main() -> None:
    shutil.rmtree(RUN_ROOT, ignore_errors=True)
    try:
        vp = RUN_ROOT / "video-production"
        ps_root = vp / "production-script"
        narration_root = vp / "narration"
        ps_root.mkdir(parents=True)
        narration_root.mkdir(parents=True)
        narration = {
            "run_id": RUN_ID,
            "segment_count": 1,
            "segments": [{
                "segment_id": "seg-001",
                "order": 1,
                "text": "测试旁白。",
                "audio_path": f"runs/{RUN_ID}/video-production/narration/audio/seg-001.mp3",
                "audio_sha256": "1" * 64,
                "duration_ms": 1200,
                "request_id": "fixture",
            }],
        }
        narration_path = narration_root / "narration-audio-manifest.json"
        narration_path.write_text(json.dumps(narration, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (narration_root / "narration-completeness-gate.json").write_text(
            json.dumps({"run_id": RUN_ID, "narration_completeness_gate": "PASS"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        script = {
            "schema_version": 1,
            "run_id": RUN_ID,
            "recovery_schema_reconstructed": True,
            "historical_schema_byte_identical": False,
            "downstream_creative_replanning_required": False,
            "execution_references": [],
            "segments": [{
                "segment_id": "seg-001",
                "audio_asset_id": "audio-seg-001",
                "visual_assets": [{
                    "asset_id": "visual-seg-001-01",
                    "visual_intent": "show one ordinary scene",
                    "scene": "an ordinary room",
                    "asset_strategy": "image",
                    "render_treatment": "static_image",
                    "generation_route": "gpt-image-2",
                    "prompt": "ordinary room with natural light, no overlay text",
                    "start_offset_ms": 0,
                    "duration_ms": 1200,
                    "transition_intent": "cut",
                    "continuity": {"kind": "none"},
                }],
            }],
        }
        script_path = ps_root / "production-script.json"
        script_path.write_text(json.dumps(script, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        script_sha = hashlib.sha256(script_path.read_bytes()).hexdigest()
        (ps_root / "production-script-gate.json").write_text(
            json.dumps({"run_id": RUN_ID, "status": "PASS", "sha256": script_sha}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        first = prepare_or_advance(RUN_ID, execute_provider=False)
        assert first["status"] == "HOST_ACTION_REQUIRED"
        assert first["serial_execution"] is True
        assert first["latest_discovery_used"] is False
        assert first["provider_execution_authorized"] is False
        assert first["host_action_task_id"] == "dispatch-visual-seg-001-01"
        dispatch_path = ROOT / first["asset_dispatch"]
        dispatch = json.loads(dispatch_path.read_text(encoding="utf-8"))
        assert len(dispatch["tasks"]) == 1
        assert dispatch["tasks"][0]["generation_route"] == "gpt-image-2"
        assert dispatch["creative_replanning"] is False
        assert first["asset_dispatch_sha256"] == hashlib.sha256(dispatch_path.read_bytes()).hexdigest()
        request_path = ROOT / first["host_action_request_path"]
        assert request_path.is_file()

        second = prepare_or_advance(RUN_ID, execute_provider=False)
        assert second["status"] == "HOST_ACTION_REQUIRED"
        assert second["asset_dispatch_sha256"] == first["asset_dispatch_sha256"]
        assert second["next_task_index"] == first["next_task_index"] == 0
        print("PREPARE_PRODUCTION_EXECUTION_RECOVERY_REGRESSION=PASS")
        print("SERIAL_EXECUTION=true")
        print("LATEST_DISCOVERY_USED=false")
        print("PROVIDER_EXECUTION_AUTHORIZED=false")
    finally:
        shutil.rmtree(RUN_ROOT, ignore_errors=True)


if __name__ == "__main__":
    main()
