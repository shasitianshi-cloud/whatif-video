from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "video-production" / "src"
sys.path.insert(0, str(SRC))

from production_visual_planner import run_visual_planner  # noqa: E402

RUN_ID = "production-visual-planner-regression-v1"
RUN_ROOT = ROOT / "runs" / RUN_ID


def candidate() -> dict:
    return {
        "schema_version": 1,
        "run_id": RUN_ID,
        "recovery_schema_reconstructed": True,
        "historical_schema_byte_identical": False,
        "downstream_creative_replanning_required": False,
        "execution_references": [],
        "segments": [
            {
                "segment_id": "seg-001",
                "audio_asset_id": "audio-seg-001",
                "visual_assets": [
                    {
                        "asset_id": "visual-seg-001-01",
                        "visual_intent": "show the changed daily routine directly",
                        "scene": "an apartment kitchen at morning with one person preparing breakfast",
                        "asset_strategy": "image",
                        "render_treatment": "static_image",
                        "generation_route": "gpt-image-2",
                        "prompt": "Asian adult preparing breakfast in a normal apartment kitchen in morning light, realistic everyday scene, no overlay text",
                        "start_offset_ms": 0,
                        "duration_ms": 1200,
                        "transition_intent": "cut",
                        "continuity": {"kind": "none"},
                    }
                ],
            }
        ],
    }


def main() -> None:
    shutil.rmtree(RUN_ROOT, ignore_errors=True)
    try:
        vm_root = RUN_ROOT / "video-master"
        narration_root = RUN_ROOT / "video-production" / "narration"
        vm_root.mkdir(parents=True)
        narration_root.mkdir(parents=True)
        vm = vm_root / "video-master.md"
        vm.write_text("早晨的生活节奏发生变化。\n", encoding="utf-8")
        vm_sha = hashlib.sha256(vm.read_bytes()).hexdigest()
        (vm_root / "video-master-gate.json").write_text(
            json.dumps({"run_id": RUN_ID, "status": "PASS", "sha256": vm_sha}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        manifest = {
            "schema_version": 1,
            "run_id": RUN_ID,
            "source_video_master_sha256": vm_sha,
            "segment_count": 1,
            "total_duration_ms": 1200,
            "segments": [
                {
                    "segment_id": "seg-001",
                    "order": 1,
                    "text": "早晨的生活节奏发生变化。\n",
                    "audio_path": f"runs/{RUN_ID}/video-production/narration/audio/seg-001.mp3",
                    "audio_sha256": "1" * 64,
                    "duration_ms": 1200,
                    "request_id": "fixture",
                }
            ],
        }
        (narration_root / "narration-audio-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (narration_root / "narration-completeness-gate.json").write_text(
            json.dumps({"run_id": RUN_ID, "narration_completeness_gate": "PASS"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        calls = []
        def planner_model_call(prompt: str) -> dict:
            calls.append(prompt)
            assert "visual-material-planner-v1" in prompt
            assert "production_script_schema" in prompt
            assert "1200" in prompt
            return candidate()

        gate = run_visual_planner(RUN_ID, planner_model_call=planner_model_call, model_name="fixture-host-planner")
        assert len(calls) == 1
        assert gate["status"] == "PASS"
        assert gate["provider_generation_executed"] is False
        artifact = ROOT / gate["artifact"]
        persisted = json.loads(artifact.read_text(encoding="utf-8"))
        assert persisted == candidate()
        evidence = json.loads((artifact.parent / "evidence" / "visual-planner-model-call.json").read_text(encoding="utf-8"))
        assert evidence["model_calls"] == 1
        assert evidence["prompt_refinement_after_model"] is False
        assert evidence["downstream_creative_replanning_required"] is False
        assert evidence["production_script_sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
        print("PRODUCTION_VISUAL_PLANNER_RECOVERY_REGRESSION=PASS")
        print("HOST_MODEL_CALL_COUNT=1")
        print("PROMPT_REFINEMENT_AFTER_MODEL=false")
        print("PROVIDER_GENERATION_EXECUTED=false")
    finally:
        shutil.rmtree(RUN_ROOT, ignore_errors=True)


if __name__ == "__main__":
    main()
