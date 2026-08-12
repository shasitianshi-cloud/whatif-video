"""Serial recovery Asset Executor orchestrator.

Explicit-state only: no latest/mtime/directory discovery. Historical builtin image host-action
behavior remains available when no physical image adapter is selected. The recovered Volcengine
General 3.0 adapter is an explicit opt-in execution adapter and remains strictly serial.
HappyHorse tasks execute serially via the canonical reconstructed T2V/I2V runners. Any BLOCK
stops the run.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from asset_executor_recovery import (
    execution_completeness,
    make_host_image_request,
    validate_happyhorse_artifact,
    validate_host_image_receipt,
)
from prepare_happyhorse_reference import prepare_reference
from volcengine_image_adapter import AdapterError, VolcengineImageAdapter
from volcengine_image_execution import (
    EXECUTION_ADAPTER as VOLCENGINE_IMAGE_EXECUTION_ADAPTER,
    execute_volcengine_image_task,
    load_runtime_adapter,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _state_path(run_id: str) -> Path:
    return PROJECT_ROOT / "runs" / run_id / "video-production" / "execution" / "asset-executor-state.json"


def initialize_state(dispatch: dict) -> dict:
    run_id = str(dispatch.get("run_id", "")).strip()
    if not run_id:
        raise RuntimeError("DISPATCH_RUN_ID_REQUIRED")
    tasks = dispatch.get("tasks")
    if not isinstance(tasks, list):
        raise RuntimeError("INVALID_DISPATCH")
    for task in tasks:
        if task.get("run_id") != run_id:
            raise RuntimeError("CROSS_RUN_DISPATCH_FORBIDDEN")
    return {
        "schema_version": 1,
        "run_id": run_id,
        "serial_execution": True,
        "project_reuse": False,
        "latest_discovery_used": False,
        "next_task_index": 0,
        "artifact_paths_by_task_id": {},
        "artifact_paths_by_asset_id": {},
        "status": "READY",
        "block_code": None,
        "recovery_executor_reconstructed": True,
        "historical_executor_byte_identical": False,
    }


def load_or_initialize(dispatch: dict) -> tuple[Path, dict]:
    path = _state_path(dispatch["run_id"])
    if path.exists():
        state = _read(path)
        if state.get("run_id") != dispatch["run_id"]:
            raise RuntimeError("EXECUTOR_STATE_RUN_ID_MISMATCH")
        if state.get("serial_execution") is not True or state.get("latest_discovery_used") is not False:
            raise RuntimeError("EXECUTOR_STATE_CONTRACT_INVALID")
        return path, state
    state = initialize_state(dispatch)
    _write(path, state)
    return path, state


def _artifact_for_task(state: dict, task_id: str) -> dict | None:
    rel = state["artifact_paths_by_task_id"].get(task_id)
    return _read(PROJECT_ROOT / rel) if rel else None


def _artifact_for_asset(state: dict, asset_id: str) -> dict | None:
    rel = state["artifact_paths_by_asset_id"].get(asset_id)
    return _read(PROJECT_ROOT / rel) if rel else None


def _record_artifact(state: dict, artifact_path: Path, artifact: dict) -> None:
    rel = artifact_path.relative_to(PROJECT_ROOT).as_posix()
    state["artifact_paths_by_task_id"][artifact["task_id"]] = rel
    state["artifact_paths_by_asset_id"][artifact["asset_id"]] = rel


def _clear_pending_markers(state: dict) -> None:
    for key in ("host_action_task_id", "host_action_request_path", "provider_task_id", "image_execution_adapter"):
        state.pop(key, None)


def host_request_path(task: dict) -> Path:
    return PROJECT_ROOT / "runs" / task["run_id"] / "video-production" / "execution" / task["asset_id"] / "host-image-request.json"


def host_receipt_path(task: dict) -> Path:
    return PROJECT_ROOT / "runs" / task["run_id"] / "video-production" / "execution" / task["asset_id"] / "host-image-receipt.json"


def canonical_artifact_path(task: dict) -> Path:
    return PROJECT_ROOT / "runs" / task["run_id"] / "video-production" / "execution" / task["asset_id"] / f"{task['asset_id']}.artifact.json"


def ingest_host_receipt(dispatch: dict, task_id: str, receipt_source: Path) -> dict:
    task = next((x for x in dispatch["tasks"] if x["task_id"] == task_id), None)
    if task is None:
        raise RuntimeError("HOST_RECEIPT_TASK_NOT_IN_DISPATCH")
    if task.get("generation_route") != "gpt-image-2":
        raise RuntimeError("HOST_RECEIPT_FOR_NON_IMAGE_TASK")
    state_path, state = load_or_initialize(dispatch)
    if task_id in state["artifact_paths_by_task_id"]:
        raise RuntimeError("TASK_ALREADY_HAS_ARTIFACT")
    receipt = _read(receipt_source)
    validated = validate_host_image_receipt(task, receipt, PROJECT_ROOT)
    canonical = canonical_artifact_path(task)
    _write(canonical, validated)
    _record_artifact(state, canonical, validated)
    state["status"] = "READY"
    state["block_code"] = None
    _clear_pending_markers(state)
    _write(state_path, state)
    return validated


def _run_happyhorse(task: dict, state: dict) -> tuple[Path, dict]:
    runtime = PROJECT_ROOT / "video-production" / "happyhorse" / "runtime"
    if task.get("generation_mode") == "T2V":
        runner = runtime / "happyhorse-t2v-runner.mjs"
        task_file = canonical_artifact_path(task).with_name("dispatch-task.json")
        _write(task_file, task)
        proc = subprocess.run(["node", str(runner), str(task_file), str(PROJECT_ROOT)], capture_output=True, text=True)
    elif task.get("generation_mode") == "I2V":
        continuity = task.get("continuity") or {}
        kind = continuity.get("kind")
        if kind == "generated_reference":
            source_id = continuity.get("reference_asset_id")
        elif kind == "previous_asset_frame":
            source_id = continuity.get("previous_asset_id")
        else:
            raise RuntimeError("I2V_REFERENCE_REQUIRED")
        source_artifact = _artifact_for_asset(state, str(source_id))
        if source_artifact is None:
            raise RuntimeError("I2V_SOURCE_ARTIFACT_NOT_AVAILABLE")
        descriptor = prepare_reference(task, source_artifact, PROJECT_ROOT)
        descriptor_path = canonical_artifact_path(task).with_name("reference-descriptor.json")
        _write(descriptor_path, descriptor)
        task_file = canonical_artifact_path(task).with_name("dispatch-task.json")
        _write(task_file, task)
        runtime_dir = runtime
        proc = subprocess.run(["node", str(runtime / "happyhorse-i2v-runner.mjs"), str(task_file), str(descriptor_path), str(PROJECT_ROOT)], cwd=runtime_dir, capture_output=True, text=True)
    else:
        raise RuntimeError("UNSUPPORTED_HAPPYHORSE_GENERATION_MODE")
    if proc.returncode != 0:
        raise RuntimeError(f"HAPPYHORSE_RUNNER_BLOCK:{proc.stderr.strip()[:240]}")
    artifact_path = canonical_artifact_path(task)
    if not artifact_path.is_file():
        raise RuntimeError("HAPPYHORSE_ARTIFACT_MISSING")
    artifact = validate_happyhorse_artifact(task, _read(artifact_path), PROJECT_ROOT)
    return artifact_path, artifact


def advance(
    dispatch: dict,
    *,
    execute_provider: bool = False,
    image_execution_adapter: str | None = None,
    image_adapter: VolcengineImageAdapter | None = None,
    image_credential_file: Path | None = None,
) -> dict:
    state_path, state = load_or_initialize(dispatch)
    tasks = dispatch["tasks"]
    active_image_adapter = image_adapter
    while state["next_task_index"] < len(tasks):
        index = state["next_task_index"]
        task = tasks[index]
        task_id = task["task_id"]
        existing = _artifact_for_task(state, task_id)
        if existing is not None:
            if existing.get("status") != "SUCCESS":
                state["status"] = "BLOCK"
                state["block_code"] = existing.get("block_code") or "EXISTING_ARTIFACT_NOT_SUCCESS"
                _write(state_path, state)
                return state
            state["next_task_index"] = index + 1
            _write(state_path, state)
            continue

        if task.get("generation_route") == "gpt-image-2":
            if image_execution_adapter is None:
                request = make_host_image_request(task)
                request_path = host_request_path(task)
                _write(request_path, request)
                state["status"] = "HOST_ACTION_REQUIRED"
                state["host_action_task_id"] = task_id
                state["host_action_request_path"] = request_path.relative_to(PROJECT_ROOT).as_posix()
                _write(state_path, state)
                return state
            if image_execution_adapter != VOLCENGINE_IMAGE_EXECUTION_ADAPTER:
                state["status"] = "BLOCK"
                state["block_code"] = "UNSUPPORTED_IMAGE_EXECUTION_ADAPTER"
                _write(state_path, state)
                return state
            if not execute_provider:
                _clear_pending_markers(state)
                state["status"] = "PROVIDER_EXECUTION_REQUIRED"
                state["provider_task_id"] = task_id
                state["image_execution_adapter"] = image_execution_adapter
                _write(state_path, state)
                return state
            try:
                if active_image_adapter is None:
                    active_image_adapter = load_runtime_adapter(PROJECT_ROOT, image_credential_file)
                artifact_path, artifact = execute_volcengine_image_task(task, active_image_adapter, PROJECT_ROOT)
                _write(artifact_path, artifact)
            except AdapterError as exc:
                state["status"] = "BLOCK"
                state["block_code"] = exc.code
                state["image_execution_adapter"] = image_execution_adapter
                state["ambiguous_task_submission"] = bool(exc.ambiguous)
                _write(state_path, state)
                return state
            except Exception as exc:
                state["status"] = "BLOCK"
                state["block_code"] = str(exc)
                state["image_execution_adapter"] = image_execution_adapter
                _write(state_path, state)
                return state
            _record_artifact(state, artifact_path, artifact)
            state["next_task_index"] = index + 1
            state["status"] = "READY"
            state["block_code"] = None
            _clear_pending_markers(state)
            _write(state_path, state)
            continue

        if task.get("generation_route") == "happyhorse":
            if not execute_provider:
                _clear_pending_markers(state)
                state["status"] = "PROVIDER_EXECUTION_REQUIRED"
                state["provider_task_id"] = task_id
                _write(state_path, state)
                return state
            try:
                artifact_path, artifact = _run_happyhorse(task, state)
            except Exception as exc:
                state["status"] = "BLOCK"
                state["block_code"] = str(exc)
                _write(state_path, state)
                return state
            _record_artifact(state, artifact_path, artifact)
            state["next_task_index"] = index + 1
            state["status"] = "READY"
            _write(state_path, state)
            continue

        state["status"] = "BLOCK"
        state["block_code"] = "UNSUPPORTED_GENERATION_ROUTE"
        _write(state_path, state)
        return state

    artifacts = [_artifact_for_task(state, x["task_id"]) for x in tasks]
    completeness = execution_completeness(dispatch, [x for x in artifacts if x is not None])
    state["completeness"] = completeness
    state["status"] = "COMPLETE" if completeness["asset_execution_completeness_pass"] else "BLOCK"
    state["block_code"] = None if state["status"] == "COMPLETE" else "ASSET_EXECUTION_COMPLETENESS_FAILED"
    _clear_pending_markers(state)
    _write(state_path, state)
    return state


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dispatch", type=Path)
    parser.add_argument("--execute-provider", action="store_true")
    parser.add_argument("--image-execution-adapter")
    parser.add_argument("--image-credential-file", type=Path)
    parser.add_argument("--ingest-host-receipt", type=Path)
    parser.add_argument("--task-id")
    args = parser.parse_args()
    dispatch = _read(args.dispatch)
    if args.ingest_host_receipt:
        if not args.task_id:
            raise SystemExit("--task-id required with --ingest-host-receipt")
        artifact = ingest_host_receipt(dispatch, args.task_id, args.ingest_host_receipt)
        print(json.dumps({"ingested": artifact}, ensure_ascii=False))
        return
    state = advance(
        dispatch,
        execute_provider=args.execute_provider,
        image_execution_adapter=args.image_execution_adapter,
        image_credential_file=args.image_credential_file,
    )
    print(json.dumps(state, ensure_ascii=False, indent=2))
    if state["status"] == "BLOCK":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
