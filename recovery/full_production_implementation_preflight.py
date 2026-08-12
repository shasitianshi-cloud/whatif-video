"""No-provider full production implementation preflight.

This is not a production run and is not a provider-runtime gate. It proves the
recovered same-run boundaries interoperate from Anchor through the first host
asset action, while statically verifying the completed execution/render half.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT / "recovery"
VP_SRC = ROOT / "video-production" / "src"
sys.path.insert(0, str(RECOVERY))
sys.path.insert(0, str(VP_SRC))

from production_upstream_host_bridge import run_upstream_host_managed  # noqa: E402
from production_narration import synthesize_narration  # noqa: E402
from production_visual_planner import run_visual_planner  # noqa: E402
from prepare_production_execution import prepare_or_advance  # noqa: E402
from orchestrator import verify_upstream_freeze  # noqa: E402

RUN_ID = "full-production-implementation-preflight-v1"
RUN_ROOT = ROOT / "runs" / RUN_ID
FIXTURE = ROOT / "counterfactual-reasoning" / "tests" / "smoke_fixture.json"


class MockTTSAdapter:
    def __init__(self, config: dict):
        self.config = config

    def synthesize(self, text: str, output_path: Path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = ("preflight-audio:" + text).encode("utf-8")
        output_path.write_bytes(payload)
        return SimpleNamespace(
            request_id="preflight-" + output_path.stem,
            provider_status=200,
            provider_code=20000000,
            provider_message="fixture",
            provider_log_id="preflight-log-" + output_path.stem,
            audio_path=output_path.as_posix(),
            audio_sha256=hashlib.sha256(payload).hexdigest(),
            provider_duration_ms=1200,
            measured_duration_ms=1200,
        )


def required_files() -> list[str]:
    return [
        "counterfactual-reasoning/src/counterfactual_reasoning.py",
        "video-master/src/video_master.py",
        "video-production/src/production_narration.py",
        "video-production/src/production_visual_planner.py",
        "video-production/src/validate_production_script.py",
        "video-production/src/build_asset_dispatch.py",
        "video-production/src/prepare_production_execution.py",
        "video-production/src/run_asset_executor.py",
        "video-production/src/asset_executor_recovery.py",
        "video-production/happyhorse/runtime/happyhorse-t2v-runner.mjs",
        "video-production/happyhorse/runtime/happyhorse-media-upload.mjs",
        "video-production/happyhorse/runtime/happyhorse-i2v-runner.mjs",
        "video-production/src/prepare_happyhorse_reference.py",
        "video-production/src/finalize_render_closure.py",
        "video-production/src/build_asset_manifest.py",
        "video-production/src/build_render_input.py",
        "video-production/src/hyperframes-render-compiler.js",
        "video-production/src/build-hyperframes-composition.js",
        "video-production/src/render_final_video.py",
        "video-production/runtime/run-hyperframes-local.sh",
        "video-production/runtime/materialize-hyperframes-runtime.sh",
        "video-production/prompts/visual-material-planner-v1.md",
        "video-production/schemas/production-script.recovery-v1.schema.json",
    ]


def assert_static_contracts() -> dict:
    missing = [rel for rel in required_files() if not (ROOT / rel).is_file()]
    if missing:
        raise RuntimeError("IMPLEMENTATION_FILE_MISSING:" + ",".join(missing))
    old_probe = (ROOT / "video-production/src/orchestrator.py").read_text(encoding="utf-8")
    if "SEGMENT_COUNT must remain 10" not in old_probe:
        raise RuntimeError("HISTORICAL_PROBE_UNEXPECTEDLY_MODIFIED")
    narration = (ROOT / "video-production/src/production_narration.py").read_text(encoding="utf-8")
    if "segment_count_dynamic" not in narration or "historical_probe_segment_count_binding" not in narration:
        raise RuntimeError("DYNAMIC_NARRATION_ENTRYPOINT_MISSING")
    execution = (ROOT / "video-production/src/prepare_production_execution.py").read_text(encoding="utf-8")
    if "execute_provider: bool = False" not in execution or '"latest_discovery_used": False' not in execution:
        raise RuntimeError("SERIAL_EXECUTION_BOUNDARY_INVALID")
    finalizer = (ROOT / "video-production/src/finalize_render_closure.py").read_text(encoding="utf-8")
    if "expected_dispatch = build_asset_dispatch(script)" not in finalizer or "ASSET_DISPATCH_DRIFT" not in finalizer:
        raise RuntimeError("RENDER_CLOSURE_DISPATCH_BINDING_MISSING")
    renderer = (ROOT / "video-production/src/render_final_video.py").read_text(encoding="utf-8")
    if "relative_to(PROJECT_ROOT)" not in renderer or '"FINAL_VIDEO_GATE"' not in renderer:
        raise RuntimeError("FINAL_RENDER_ENTRYPOINT_INVALID")
    materializer = (ROOT / "video-production/runtime/materialize-hyperframes-runtime.sh").read_text(encoding="utf-8")
    for token in ("HYPERFRAMES_VERSION=\"0.7.106\"", "CHROMIUM_VERSION=\"152.0.7928.2\"", "NODE_VERSION=\"24.14.0\""):
        if token not in materializer:
            raise RuntimeError("PINNED_RENDER_RUNTIME_DRIFT")
    return verify_upstream_freeze()


def candidate_for_manifest(manifest: dict) -> dict:
    segments = []
    for item in manifest["segments"]:
        duration = int(item["duration_ms"])
        sid = item["segment_id"]
        segments.append({
            "segment_id": sid,
            "audio_asset_id": f"audio-{sid}",
            "visual_assets": [{
                "asset_id": f"visual-{sid}-01",
                "visual_intent": "show the described consequence in an ordinary visible scene",
                "scene": "an ordinary everyday interior with one person performing a routine action",
                "asset_strategy": "image",
                "render_treatment": "static_image",
                "generation_route": "gpt-image-2",
                "prompt": "Asian adult performing an ordinary daily routine in a realistic interior, natural lighting, documentary photography",
                "start_offset_ms": 0,
                "duration_ms": duration,
                "transition_intent": "cut",
                "continuity": {"kind": "none"},
            }],
        })
    return {
        "schema_version": 1,
        "run_id": RUN_ID,
        "recovery_schema_reconstructed": True,
        "historical_schema_byte_identical": False,
        "downstream_creative_replanning_required": False,
        "execution_references": [],
        "segments": segments,
    }


def main() -> None:
    shutil.rmtree(RUN_ROOT, ignore_errors=True)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    counts = {"reasoning": 0, "video_master": 0, "planner": 0, "tts": 0}
    try:
        upstream_freeze = assert_static_contracts()

        def reasoning_host_call(stage: str, prompt: str, inputs: dict):
            assert inputs["run_id"] == RUN_ID and prompt.strip()
            counts["reasoning"] += 1
            return fixture[stage]

        def video_master_model_call(prompt: str) -> str:
            assert prompt.strip()
            counts["video_master"] += 1
            if counts["video_master"] == 1:
                return "如果所有人永久失去痛觉，损伤不会消失。人会更晚发现伤口。医院会增加主动检查。家庭也会增加日常检查。"
            return "所有人永久失去痛觉后，损伤仍会发生。人会更晚发现伤口和疾病。医院会从因痛就诊转向主动检查。家庭和工作场所也会增加日常检查。"

        upstream = run_upstream_host_managed(
            run_id=RUN_ID,
            anchor="人类突然永久失去痛觉",
            reasoning_host_call=reasoning_host_call,
            video_master_model_call=video_master_model_call,
            reasoning_model_name="preflight-host-reasoning",
            video_master_model_name="preflight-host-video-master",
        )
        if upstream["status"] != "HOST_UPSTREAM_READY_FOR_TTS" or not upstream["same_run_lineage_verified"]:
            raise RuntimeError("UPSTREAM_HOST_BRIDGE_PREFLIGHT_FAILED")

        narration_result = synthesize_narration(RUN_ID, adapter_factory=MockTTSAdapter)
        if narration_result["gate_data"]["narration_completeness_gate"] != "PASS":
            raise RuntimeError("NARRATION_PREFLIGHT_FAILED")
        manifest_path = RUN_ROOT / "video-production/narration/narration-audio-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        counts["tts"] = len(manifest["segments"])
        if manifest["segment_count"] < 2:
            raise RuntimeError("DYNAMIC_SEGMENTATION_NOT_EXERCISED")

        def planner_model_call(prompt: str) -> dict:
            assert prompt.strip()
            counts["planner"] += 1
            return candidate_for_manifest(manifest)

        ps_gate = run_visual_planner(
            RUN_ID,
            planner_model_call=planner_model_call,
            model_name="preflight-host-visual-planner",
        )
        if ps_gate["status"] != "PASS":
            raise RuntimeError("VISUAL_PLANNER_PREFLIGHT_FAILED")
        execution = prepare_or_advance(RUN_ID, execute_provider=False)
        if execution["status"] != "HOST_ACTION_REQUIRED":
            raise RuntimeError("HOST_IMAGE_BOUNDARY_NOT_REACHED")
        if execution["provider_execution_authorized"] is not False or execution["latest_discovery_used"] is not False:
            raise RuntimeError("PROVIDER_EXECUTION_BOUNDARY_BROKEN")

        expected_counts = {"reasoning": 3, "video_master": 2, "planner": 1}
        for key, expected in expected_counts.items():
            if counts[key] != expected:
                raise RuntimeError(f"MODEL_CALL_COUNT_INVALID:{key}")

        result = {
            "schema_version": 1,
            "full_production_implementation_preflight": "PASS",
            "production_run_created": False,
            "preflight_fixture_run_id": RUN_ID,
            "preflight_fixture_cleaned_after_run": True,
            "same_run_lineage_verified": True,
            "dynamic_narration_verified": True,
            "visual_planner_boundary_verified": True,
            "production_script_validation_verified": True,
            "serial_executor_boundary_verified": True,
            "host_image_action_boundary_reached": True,
            "happyhorse_execution_modules_present": True,
            "render_closure_modules_present": True,
            "final_video_gate_entrypoint_present": True,
            "pinned_hyperframes_runtime_contract_present": True,
            "real_tts_provider_call_executed": False,
            "real_happyhorse_provider_call_executed": False,
            "real_image_generation_executed": False,
            "credits_consumed": False,
            "latest_discovery_used": False,
            "model_call_counts": counts,
            "upstream_freeze_observed": upstream_freeze,
            "next_stage": "REAL_PRODUCTION_RUNTIME_PREFLIGHT",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        shutil.rmtree(RUN_ROOT, ignore_errors=True)


if __name__ == "__main__":
    main()
