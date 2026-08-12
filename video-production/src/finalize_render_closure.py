"""Finalize completed execution into Asset Manifest, Render Input, and Render Plan.

Fail-closed and explicit-state only. No provider calls, no directory/latest discovery,
no regeneration, and no creative replanning.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from asset_executor_recovery import (
    execution_completeness,
    validate_happyhorse_artifact,
    validate_host_image_receipt,
)
from build_asset_dispatch import build_asset_dispatch, validate_asset_dispatch
from build_asset_manifest import build_asset_manifest, validate_asset_manifest
from build_render_input import build_render_input, validate_render_input
from validate_production_script import validate_production_script

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VP_ROOT = PROJECT_ROOT / "video-production"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _explicit_artifact(path_value: str) -> tuple[Path, dict]:
    if not path_value:
        raise RuntimeError("EXECUTION_ARTIFACT_PATH_MISSING")
    path = (PROJECT_ROOT / path_value).resolve()
    root = PROJECT_ROOT.resolve()
    if path != root and root not in path.parents:
        raise RuntimeError("EXECUTION_ARTIFACT_PATH_OUTSIDE_PROJECT")
    if not path.is_file():
        raise RuntimeError("EXECUTION_ARTIFACT_MISSING")
    return path, _read(path)


def finalize_render_closure(run_id: str) -> dict:
    run_root = PROJECT_ROOT / "runs" / run_id / "video-production"
    ps_root = run_root / "production-script"
    narration_root = run_root / "narration"
    execution_root = run_root / "execution"
    script_path = ps_root / "production-script.json"
    script_gate_path = ps_root / "production-script-gate.json"
    narration_path = narration_root / "narration-audio-manifest.json"
    narration_gate_path = narration_root / "narration-completeness-gate.json"
    dispatch_path = execution_root / "asset-dispatch.json"
    state_path = execution_root / "asset-executor-state.json"
    required = (script_path, script_gate_path, narration_path, narration_gate_path, dispatch_path, state_path)
    if not all(path.is_file() for path in required):
        raise RuntimeError("RENDER_CLOSURE_INPUT_MISSING")

    script = _read(script_path)
    script_gate = _read(script_gate_path)
    narration = _read(narration_path)
    narration_gate = _read(narration_gate_path)
    dispatch = _read(dispatch_path)
    state = _read(state_path)
    if any(obj.get("run_id") != run_id for obj in (script, narration, dispatch, state)):
        raise RuntimeError("CROSS_RUN_RENDER_CLOSURE_FORBIDDEN")
    if script_gate.get("run_id") != run_id or script_gate.get("status") != "PASS" or script_gate.get("sha256") != _sha(script_path):
        raise RuntimeError("PRODUCTION_SCRIPT_GATE_INVALID")
    if narration_gate.get("run_id") not in {None, run_id} or narration_gate.get("narration_completeness_gate") != "PASS":
        raise RuntimeError("NARRATION_COMPLETENESS_GATE_INVALID")
    validate_production_script(script, narration)
    validate_asset_dispatch(dispatch)
    expected_dispatch = build_asset_dispatch(script)
    if dispatch != expected_dispatch:
        raise RuntimeError("ASSET_DISPATCH_DRIFT")
    if state.get("status") != "COMPLETE" or state.get("serial_execution") is not True or state.get("latest_discovery_used") is not False:
        raise RuntimeError("ASSET_EXECUTION_NOT_COMPLETE")

    by_task = state.get("artifact_paths_by_task_id")
    by_asset = state.get("artifact_paths_by_asset_id")
    if not isinstance(by_task, dict) or not isinstance(by_asset, dict):
        raise RuntimeError("EXECUTOR_EXPLICIT_STATE_INVALID")
    validated_artifacts: list[dict] = []
    execution_assets: list[dict] = []
    for task in dispatch.get("tasks", []):
        rel = by_task.get(task["task_id"])
        artifact_path, artifact = _explicit_artifact(rel)
        if by_asset.get(task["asset_id"]) != rel:
            raise RuntimeError("EXECUTOR_TASK_ASSET_MAP_MISMATCH")
        if task.get("generation_route") == "gpt-image-2":
            validated = validate_host_image_receipt(task, artifact, PROJECT_ROOT)
        elif task.get("generation_route") == "happyhorse":
            validated = validate_happyhorse_artifact(task, artifact, PROJECT_ROOT)
        else:
            raise RuntimeError("UNSUPPORTED_GENERATION_ROUTE")
        validated_artifacts.append(validated)
        execution_assets.append({
            "run_id": run_id,
            "asset_id": validated["asset_id"],
            "asset_kind": validated["asset_kind"],
            "role": validated["role"],
            "source_artifact_path": artifact_path.relative_to(PROJECT_ROOT).as_posix(),
            "local_path": validated["local_path"],
            "sha256": validated["sha256"],
            "width": validated.get("width"),
            "height": validated.get("height"),
            "duration_ms": validated.get("duration_ms"),
            "created_at": validated.get("created_at", "UNKNOWN_RECOVERED_IDENTITY"),
            "in_content_timeline": bool(validated["in_content_timeline"]),
            **({"provider_metadata": validated["provider_metadata"]} if validated.get("provider_metadata") is not None else {}),
        })

    completeness = execution_completeness(dispatch, validated_artifacts)
    if completeness.get("asset_execution_completeness_pass") is not True:
        raise RuntimeError("ASSET_EXECUTION_COMPLETENESS_FAILED")
    if state.get("completeness") is not None and state["completeness"] != completeness:
        raise RuntimeError("EXECUTOR_COMPLETENESS_STATE_DRIFT")

    script_by_segment = {x["segment_id"]: x for x in script["segments"]}
    narration_assets: list[dict] = []
    audio_ids: set[str] = set()
    for segment in narration.get("segments", []):
        sid = segment["segment_id"]
        ps_segment = script_by_segment.get(sid)
        if ps_segment is None:
            raise RuntimeError("NARRATION_SEGMENT_COVERAGE_COMPLETE=false")
        audio_id = str(ps_segment.get("audio_asset_id", "")).strip()
        if not audio_id or audio_id in audio_ids:
            raise RuntimeError("DUPLICATE_OR_MISSING_AUDIO_ASSET_ID")
        audio_ids.add(audio_id)
        narration_assets.append({
            "run_id": run_id,
            "asset_id": audio_id,
            "asset_kind": "audio",
            "role": "narration",
            "source_artifact_path": segment["audio_path"],
            "local_path": segment["audio_path"],
            "sha256": segment["audio_sha256"],
            "width": None,
            "height": None,
            "duration_ms": int(segment["duration_ms"]),
            "created_at": "PROVIDER_GENERATED_NARRATION",
            "in_content_timeline": False,
        })

    asset_manifest = build_asset_manifest(
        run_id=run_id,
        execution_assets=execution_assets,
        narration_assets=narration_assets,
        project_root=PROJECT_ROOT,
    )
    validate_asset_manifest(asset_manifest)
    render_input = build_render_input(
        run_id=run_id,
        asset_manifest=asset_manifest,
        production_script=script,
        narration_manifest=narration,
    )
    validate_render_input(render_input)

    render_root = run_root / "render"
    if render_root.exists():
        raise RuntimeError("RENDER_CLOSURE_ALREADY_EXISTS")
    render_root.mkdir(parents=True)
    asset_manifest_path = render_root / "asset-manifest.json"
    render_input_path = render_root / "render-input.json"
    render_plan_path = render_root / "render-plan.json"
    _write(asset_manifest_path, asset_manifest)
    _write(render_input_path, render_input)
    compiler = VP_ROOT / "src" / "hyperframes-render-compiler.js"
    proc = subprocess.run(
        ["node", str(compiler), str(render_input_path), str(asset_manifest_path), str(render_plan_path)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not render_plan_path.is_file():
        raise RuntimeError(f"HYPERFRAMES_RENDER_PLAN_COMPILE_FAILED:{proc.stderr.strip()[:240]}")
    render_plan = _read(render_plan_path)
    if render_plan.get("run_id") != run_id or render_plan.get("schema_version") != 1:
        raise RuntimeError("HYPERFRAMES_RENDER_PLAN_INVALID")

    gate = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "READY_FOR_HYPERFRAMES_RENDER",
        "asset_manifest": asset_manifest_path.relative_to(PROJECT_ROOT).as_posix(),
        "asset_manifest_sha256": _sha(asset_manifest_path),
        "render_input": render_input_path.relative_to(PROJECT_ROOT).as_posix(),
        "render_input_sha256": _sha(render_input_path),
        "render_plan": render_plan_path.relative_to(PROJECT_ROOT).as_posix(),
        "render_plan_sha256": _sha(render_plan_path),
        "execution_completeness": completeness,
        "latest_discovery_used": False,
        "provider_generation_executed": False,
        "creative_replanning_performed": False,
        "recovery_closure_reconstructed": True,
        "historical_closure_byte_identical": False,
    }
    _write(render_root / "render-closure-gate.json", gate)
    return gate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    result = finalize_render_closure(args.run_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
