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

RUN_ID = "production-visual-planner-regression-v2"
RUN_ROOT = ROOT / "runs" / RUN_ID
TITLE = "如果月球永久消失"


def candidate() -> dict:
    return {
        "schema_version": 1,
        "contract_version": 2,
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
                        "visual_intent": "immediately show the changed world in motion",
                        "scene": "moonless coast with visibly altered moving water and active harbor foreground",
                        "asset_strategy": "generated_video",
                        "render_treatment": "direct_video",
                        "generation_route": "happyhorse",
                        "generation_mode": "T2V",
                        "prompt": "Moonless coastal harbor, moving water around pilings, boats shifting gently, immediate changed-world atmosphere, wide realistic scene",
                        "start_offset_ms": 0,
                        "duration_ms": 8000,
                        "transition_intent": "cut",
                        "continuity": {"kind": "none"},
                        "hook_contract": {
                            "visible_event": "moonless coast and visibly changed moving water are present immediately",
                            "dominant_subject": "coastal harbor water and boats",
                            "state_change": "the familiar Moon is absent while the coast remains active",
                            "real_motion": "water moves around pilings and boats shift",
                            "camera_relationship": "wide stable view close enough to read water motion",
                            "first_3s_visible_fact": "the changed moonless coastal state is visible from frame one",
                            "why_static_is_insufficient": "water and boat motion must establish an active changed environment"
                        }
                    }
                ]
            }
        ],
        "cover": {
            "asset_id": "cover-main",
            "visual_intent": "theme-aligned moonless Earth background",
            "prompt": "Earth in deep space with a conspicuously empty nearby region where the Moon would normally appear, realistic sunlight, strong simple composition",
            "title_text": TITLE,
            "in_content_timeline": False
        }
    }


def main() -> None:
    shutil.rmtree(RUN_ROOT, ignore_errors=True)
    try:
        vm_root = RUN_ROOT / "video-master"
        cf_root = RUN_ROOT / "counterfactual-reasoning" / "work"
        narration_root = RUN_ROOT / "video-production" / "narration"
        vm_root.mkdir(parents=True)
        cf_root.mkdir(parents=True)
        narration_root.mkdir(parents=True)

        vm = vm_root / "video-master.md"
        vm.write_text("月球消失后，海岸仍在运动，但熟悉的夜空已经改变。\n", encoding="utf-8")
        vm_sha = hashlib.sha256(vm.read_bytes()).hexdigest()
        (vm_root / "video-master-gate.json").write_text(
            json.dumps({"run_id": RUN_ID, "status": "PASS", "sha256": vm_sha}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (cf_root / "premise-source.json").write_text(
            json.dumps({"run_id": RUN_ID, "raw_premise": TITLE}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        manifest = {
            "schema_version": 1,
            "run_id": RUN_ID,
            "source_video_master_sha256": vm_sha,
            "segment_count": 1,
            "total_duration_ms": 8000,
            "segments": [
                {
                    "segment_id": "seg-001",
                    "order": 1,
                    "text": "月球消失后，海岸仍在运动，但熟悉的夜空已经改变。\n",
                    "audio_path": f"runs/{RUN_ID}/video-production/narration/audio/seg-001.mp3",
                    "audio_sha256": "1" * 64,
                    "duration_ms": 8000,
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
            assert "visual-material-planner-v2" in prompt
            assert "counterfactual_display_title" in prompt
            assert TITLE in prompt
            assert "minimum_segment_ratio" in prompt
            return candidate()

        gate = run_visual_planner(RUN_ID, planner_model_call=planner_model_call, model_name="fixture-host-planner")
        assert len(calls) == 1
        assert gate["status"] == "PASS"
        assert gate["happyhorse_required_segments"] == 1
        assert gate["happyhorse_primary_segments"] == 1
        assert gate["first_three_second_hook_contract"] == "PASS"
        assert gate["cover_title_exact"] is True
        assert gate["provider_generation_executed"] is False
        artifact = ROOT / gate["artifact"]
        assert json.loads(artifact.read_text(encoding="utf-8")) == candidate()
        evidence = json.loads((artifact.parent / "evidence" / "visual-planner-model-call.json").read_text(encoding="utf-8"))
        assert evidence["contract_version"] == 2
        assert evidence["physical_provider_selected_by_llm"] is False
        assert evidence["prompt_refinement_after_model"] is False
        print("PRODUCTION_VISUAL_PLANNER_V2_REGRESSION=PASS")
        print("HOST_MODEL_CALL_COUNT=1")
        print("PROVIDER_GENERATION_EXECUTED=false")
    finally:
        shutil.rmtree(RUN_ROOT, ignore_errors=True)


if __name__ == "__main__":
    main()
