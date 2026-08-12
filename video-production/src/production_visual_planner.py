"""Host-managed Visual Planner -> globally bounded Production Script V2.

The host LLM retains semantic planning freedom. Machine contracts own the
minimum HappyHorse usage, first-three-second hook, cover title, timing,
visual-purity and downstream determinism.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Callable

from validate_production_script_v2 import validate_production_script_v2

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VIDEO_PRODUCTION_ROOT = PROJECT_ROOT / "video-production"
PLANNER_PROMPT = VIDEO_PRODUCTION_ROOT / "prompts" / "visual-material-planner-v2.md"
PRODUCTION_SCHEMA = VIDEO_PRODUCTION_ROOT / "schemas" / "production-script.recovery-v2.schema.json"
VISUAL_POLICY = VIDEO_PRODUCTION_ROOT / "config" / "visual-planning-policy.v2.json"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_inputs(run_id: str) -> tuple[Path, dict, Path, dict, dict]:
    run_root = PROJECT_ROOT / "runs" / run_id
    vm_path = run_root / "video-master" / "video-master.md"
    vm_gate_path = run_root / "video-master" / "video-master-gate.json"
    premise_source_path = run_root / "counterfactual-reasoning" / "work" / "premise-source.json"
    narration_root = run_root / "video-production" / "narration"
    manifest_path = narration_root / "narration-audio-manifest.json"
    narration_gate_path = narration_root / "narration-completeness-gate.json"

    if not vm_path.is_file() or not vm_gate_path.is_file():
        raise RuntimeError("VIDEO_MASTER_INPUT_MISSING")
    if not premise_source_path.is_file():
        raise RuntimeError("COUNTERFACTUAL_PREMISE_SOURCE_MISSING")
    if not manifest_path.is_file() or not narration_gate_path.is_file():
        raise RuntimeError("NARRATION_INPUT_MISSING")

    vm_gate = _read_json(vm_gate_path)
    premise_source = _read_json(premise_source_path)
    manifest = _read_json(manifest_path)
    narration_gate = _read_json(narration_gate_path)
    vm_sha = sha256_file(vm_path)

    if vm_gate.get("run_id") != run_id or vm_gate.get("status") != "PASS" or vm_gate.get("sha256") != vm_sha:
        raise RuntimeError("VIDEO_MASTER_GATE_INVALID")
    if premise_source.get("run_id") != run_id:
        raise RuntimeError("COUNTERFACTUAL_PREMISE_RUN_ID_MISMATCH")
    display_title = str(premise_source.get("raw_premise", "")).strip()
    if not display_title or len(display_title) > 40:
        raise RuntimeError("COUNTERFACTUAL_DISPLAY_TITLE_INVALID")
    if manifest.get("run_id") != run_id or manifest.get("source_video_master_sha256") != vm_sha:
        raise RuntimeError("NARRATION_MANIFEST_LINEAGE_INVALID")
    if narration_gate.get("run_id") not in {None, run_id} or narration_gate.get("narration_completeness_gate") != "PASS":
        raise RuntimeError("NARRATION_COMPLETENESS_GATE_INVALID")

    manifest_ids = [x.get("segment_id") for x in manifest.get("segments", [])]
    if not manifest_ids or manifest.get("segment_count") != len(manifest_ids) or len(set(manifest_ids)) != len(manifest_ids):
        raise RuntimeError("NARRATION_MANIFEST_SEGMENTS_INVALID")
    return vm_path, manifest, manifest_path, narration_gate, premise_source


def build_planner_request(run_id: str) -> tuple[str, dict]:
    vm_path, manifest, manifest_path, narration_gate, premise_source = _assert_inputs(run_id)
    prompt_text = PLANNER_PROMPT.read_text(encoding="utf-8")
    schema = _read_json(PRODUCTION_SCHEMA)
    visual_policy = _read_json(VISUAL_POLICY)
    capabilities = {
        "image_generation": {
            "logical_route": "gpt-image-2",
            "physical_provider_selection": "deterministic_runtime",
        },
        "image_motion": {"source_kind": "image", "render_executor": "HyperFrames"},
        "generated_video": {
            "logical_route": "happyhorse",
            "generation_modes": ["T2V", "I2V", "R2V"],
            "duration_ms": {"minimum": 3000, "maximum": 15000, "whole_seconds_only": True},
            "physical_provider_selection": "deterministic_runtime",
        },
        "continuity": ["none", "previous_asset_frame", "generated_reference"],
        "cover_in_content_timeline": False,
    }
    inputs = {
        "run_id": run_id,
        "counterfactual_display_title": str(premise_source["raw_premise"]).strip(),
        "video_master": vm_path.read_text(encoding="utf-8"),
        "video_master_sha256": sha256_file(vm_path),
        "narration_manifest": manifest,
        "narration_manifest_sha256": sha256_file(manifest_path),
        "narration_gate": narration_gate,
        "content_frame_policy": {
            "generic_person_default": "Asian person",
            "generated_visible_text_language": "Simplified Chinese",
            "proactive_overlay_text": False,
        },
        "execution_capabilities": capabilities,
        "visual_planning_policy": visual_policy,
        "cost_policy": {
            "static_preference_applies_only_after_hard_video_quota": True,
        },
        "production_script_schema": schema,
    }
    request = (
        prompt_text
        + "\n\n---\n\nCURRENT RUN INPUTS (JSON):\n"
        + json.dumps(inputs, ensure_ascii=False, indent=2)
    )
    return request, inputs


def run_visual_planner(
    run_id: str,
    *,
    planner_model_call: Callable[[str], dict],
    model_name: str = "host-managed",
) -> dict:
    if not callable(planner_model_call):
        raise RuntimeError("VISUAL_PLANNER_HOST_CALLBACK_REQUIRED")

    request, inputs = build_planner_request(run_id)
    candidate = planner_model_call(request)
    if not isinstance(candidate, dict):
        raise RuntimeError("VISUAL_PLANNER_OUTPUT_NOT_OBJECT")
    if candidate.get("run_id") != run_id:
        raise RuntimeError("VISUAL_PLANNER_CROSS_RUN_OUTPUT")

    _, manifest, manifest_path, _, _ = _assert_inputs(run_id)
    validation = validate_production_script_v2(
        candidate,
        manifest,
        expected_display_title=inputs["counterfactual_display_title"],
    )

    out_root = PROJECT_ROOT / "runs" / run_id / "video-production" / "production-script"
    if out_root.exists():
        raise RuntimeError("PRODUCTION_SCRIPT_ALREADY_EXISTS")
    evidence_root = out_root / "evidence"
    evidence_root.mkdir(parents=True)
    artifact = out_root / "production-script.json"
    artifact.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    artifact_sha = sha256_file(artifact)

    evidence = {
        "schema_version": 1,
        "contract_version": 2,
        "run_id": run_id,
        "planner_prompt": PLANNER_PROMPT.relative_to(PROJECT_ROOT).as_posix(),
        "planner_prompt_sha256": sha256_file(PLANNER_PROMPT),
        "production_script_schema": PRODUCTION_SCHEMA.relative_to(PROJECT_ROOT).as_posix(),
        "production_script_schema_sha256": sha256_file(PRODUCTION_SCHEMA),
        "visual_planning_policy": VISUAL_POLICY.relative_to(PROJECT_ROOT).as_posix(),
        "visual_planning_policy_sha256": sha256_file(VISUAL_POLICY),
        "narration_manifest_sha256": sha256_file(manifest_path),
        "video_master_sha256": inputs["video_master_sha256"],
        "counterfactual_display_title": inputs["counterfactual_display_title"],
        "model": model_name,
        "model_calls": 1,
        "prompt_refinement_after_model": False,
        "downstream_creative_replanning_required": False,
        "physical_provider_selected_by_llm": False,
        "production_script_sha256": artifact_sha,
        "validation_summary": validation,
        "recovery_boundary_reconstructed": True,
        "historical_boundary_byte_identical": False,
    }
    evidence_path = evidence_root / "visual-planner-model-call.json"
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    gate = {
        "schema_version": 1,
        "contract_version": 2,
        "run_id": run_id,
        "gate": "PRODUCTION_SCRIPT_VALIDATION_V2",
        "status": "PASS",
        "artifact": artifact.relative_to(PROJECT_ROOT).as_posix(),
        "sha256": artifact_sha,
        "narration_manifest_sha256": evidence["narration_manifest_sha256"],
        "video_master_sha256": evidence["video_master_sha256"],
        "happyhorse_required_segments": validation["happyhorse_required_segments"],
        "happyhorse_primary_segments": validation["happyhorse_primary_segments"],
        "first_segment_happyhorse_primary": validation["first_segment_happyhorse_primary"],
        "first_three_second_hook_contract": validation["first_three_second_hook_contract"],
        "cover_required": validation["cover_required"],
        "cover_title_exact": validation["cover_title_exact"],
        "creative_replanning_performed": False,
        "physical_provider_selected_by_llm": False,
        "provider_generation_executed": False,
    }
    gate_path = out_root / "production-script-gate.json"
    gate_path.write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return gate


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bounded Visual Planner V2: host must inject planner_model_call; CLI performs input preflight only."
    )
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    request, inputs = build_planner_request(args.run_id)
    print(json.dumps({
        "run_id": args.run_id,
        "status": "HOST_ACTION_REQUIRED",
        "action": "VISUAL_PLANNER_MODEL_CALL_V2",
        "request_sha256": hashlib.sha256(request.encode("utf-8")).hexdigest(),
        "counterfactual_display_title": inputs["counterfactual_display_title"],
        "provider_generation_executed": False,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
