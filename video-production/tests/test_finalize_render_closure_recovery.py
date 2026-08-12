from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "video-production" / "src"
sys.path.insert(0, str(SRC))

from asset_executor_recovery import execution_completeness, sha256_text  # noqa: E402
from build_asset_dispatch import build_asset_dispatch  # noqa: E402
from finalize_render_closure import finalize_render_closure  # noqa: E402

RUN_ID = "finalize-render-closure-regression-v1"
RUN_ROOT = ROOT / "runs" / RUN_ID


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    shutil.rmtree(RUN_ROOT, ignore_errors=True)
    try:
        vp = RUN_ROOT / "video-production"
        ps_root = vp / "production-script"
        narration_root = vp / "narration"
        execution_root = vp / "execution"
        ps_root.mkdir(parents=True)
        (narration_root / "audio").mkdir(parents=True)
        execution_root.mkdir(parents=True)

        audio_bytes = b"fake-audio"
        audio_path = narration_root / "audio" / "seg-001.mp3"
        audio_path.write_bytes(audio_bytes)
        narration = {
            "run_id": RUN_ID,
            "segment_count": 1,
            "total_duration_ms": 1200,
            "segments": [{
                "segment_id": "seg-001",
                "order": 1,
                "text": "测试旁白。",
                "audio_path": audio_path.relative_to(ROOT).as_posix(),
                "audio_sha256": sha_bytes(audio_bytes),
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
                    "visual_intent": "show a room",
                    "scene": "ordinary room",
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

        dispatch = build_asset_dispatch(script)
        dispatch_path = execution_root / "asset-dispatch.json"
        dispatch_path.write_text(json.dumps(dispatch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        task = dispatch["tasks"][0]
        image_bytes = b"fake-image"
        image_path = execution_root / "visual-seg-001-01" / "visual-seg-001-01.png"
        image_path.parent.mkdir(parents=True)
        image_path.write_bytes(image_bytes)
        artifact = {
            "schema_version": 1,
            "run_id": RUN_ID,
            "task_id": task["task_id"],
            "asset_id": task["asset_id"],
            "status": "SUCCESS",
            "generation_route": "gpt-image-2",
            "execution_route": "builtin_image_generation",
            "asset_kind": "image",
            "role": "content_visual",
            "in_content_timeline": True,
            "prompt_sha256": sha256_text(task["prompt"]),
            "local_path": image_path.relative_to(ROOT).as_posix(),
            "sha256": sha_bytes(image_bytes),
            "file_size_bytes": len(image_bytes),
            "width": 1280,
            "height": 720,
            "duration_ms": None,
            "model_identity": "fixture-host-image",
            "recovery_executor_reconstructed": True,
            "historical_executor_byte_identical": False,
        }
        artifact_path = image_path.with_suffix(".artifact.json")
        artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        completeness = execution_completeness(dispatch, [artifact])
        assert completeness["asset_execution_completeness_pass"] is True
        state = {
            "schema_version": 1,
            "run_id": RUN_ID,
            "serial_execution": True,
            "project_reuse": False,
            "latest_discovery_used": False,
            "next_task_index": 1,
            "artifact_paths_by_task_id": {task["task_id"]: artifact_path.relative_to(ROOT).as_posix()},
            "artifact_paths_by_asset_id": {task["asset_id"]: artifact_path.relative_to(ROOT).as_posix()},
            "status": "COMPLETE",
            "block_code": None,
            "completeness": completeness,
            "recovery_executor_reconstructed": True,
            "historical_executor_byte_identical": False,
        }
        (execution_root / "asset-executor-state.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        gate = finalize_render_closure(RUN_ID)
        assert gate["status"] == "READY_FOR_HYPERFRAMES_RENDER"
        assert gate["latest_discovery_used"] is False
        assert gate["provider_generation_executed"] is False
        assert gate["creative_replanning_performed"] is False
        manifest = json.loads((ROOT / gate["asset_manifest"]).read_text(encoding="utf-8"))
        render_input = json.loads((ROOT / gate["render_input"]).read_text(encoding="utf-8"))
        render_plan = json.loads((ROOT / gate["render_plan"]).read_text(encoding="utf-8"))
        assert {x["asset_id"] for x in manifest["assets"]} == {"visual-seg-001-01", "audio-seg-001"}
        assert render_input["timeline"][0]["audio_asset_id"] == "audio-seg-001"
        assert render_input["timeline"][0]["visual_assets"][0]["asset_id"] == "visual-seg-001-01"
        assert render_plan["composition"]["duration_ms"] == 1200
        assert render_plan["layers"][0]["treatment"] == "static_image"
        assert render_plan["audio"][0]["asset_id"] == "audio-seg-001"
        print("FINALIZE_RENDER_CLOSURE_RECOVERY_REGRESSION=PASS")
        print("READY_FOR_HYPERFRAMES_RENDER=true")
        print("PROVIDER_GENERATION_EXECUTED=false")
        print("LATEST_DISCOVERY_USED=false")
    finally:
        shutil.rmtree(RUN_ROOT, ignore_errors=True)


if __name__ == "__main__":
    main()
