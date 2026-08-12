"""Deterministic Production Script -> frozen Asset Dispatch -> Serial Executor entrypoint."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_asset_dispatch import build_asset_dispatch, validate_asset_dispatch
from run_asset_executor import advance
from validate_production_script import validate_production_script

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_or_advance(
    run_id: str,
    *,
    execute_provider: bool = False,
    image_execution_adapter: str | None = None,
    image_credential_file: Path | None = None,
) -> dict:
    run_root = PROJECT_ROOT / "runs" / run_id / "video-production"
    ps_root = run_root / "production-script"
    script_path = ps_root / "production-script.json"
    script_gate_path = ps_root / "production-script-gate.json"
    narration_path = run_root / "narration" / "narration-audio-manifest.json"
    narration_gate_path = run_root / "narration" / "narration-completeness-gate.json"
    if not all(p.is_file() for p in (script_path, script_gate_path, narration_path, narration_gate_path)):
        raise RuntimeError("PRODUCTION_EXECUTION_INPUT_MISSING")
    script = _read(script_path)
    script_gate = _read(script_gate_path)
    narration = _read(narration_path)
    narration_gate = _read(narration_gate_path)
    if script.get("run_id") != run_id or narration.get("run_id") != run_id:
        raise RuntimeError("CROSS_RUN_PRODUCTION_EXECUTION_FORBIDDEN")
    if script_gate.get("run_id") != run_id or script_gate.get("status") != "PASS" or script_gate.get("sha256") != _sha(script_path):
        raise RuntimeError("PRODUCTION_SCRIPT_GATE_INVALID")
    if narration_gate.get("run_id") not in {None, run_id} or narration_gate.get("narration_completeness_gate") != "PASS":
        raise RuntimeError("NARRATION_COMPLETENESS_GATE_INVALID")
    validate_production_script(script, narration)

    dispatch = build_asset_dispatch(script)
    validate_asset_dispatch(dispatch)
    execution_root = run_root / "execution"
    dispatch_path = execution_root / "asset-dispatch.json"
    if dispatch_path.exists():
        existing = _read(dispatch_path)
        if existing != dispatch:
            raise RuntimeError("ASSET_DISPATCH_DRIFT")
    else:
        _write(dispatch_path, dispatch)
    dispatch_sha = _sha(dispatch_path)
    state = advance(
        dispatch,
        execute_provider=execute_provider,
        image_execution_adapter=image_execution_adapter,
        image_credential_file=image_credential_file,
    )
    result = {
        "schema_version": 1,
        "run_id": run_id,
        "production_script_sha256": _sha(script_path),
        "narration_manifest_sha256": _sha(narration_path),
        "asset_dispatch": dispatch_path.relative_to(PROJECT_ROOT).as_posix(),
        "asset_dispatch_sha256": dispatch_sha,
        "serial_execution": True,
        "latest_discovery_used": False,
        "provider_execution_authorized": bool(execute_provider),
        "image_execution_adapter": image_execution_adapter,
        "status": state["status"],
        "next_task_index": state["next_task_index"],
        "block_code": state.get("block_code"),
        "recovery_entrypoint_reconstructed": True,
        "historical_entrypoint_byte_identical": False,
    }
    if state.get("host_action_request_path"):
        result["host_action_request_path"] = state["host_action_request_path"]
        result["host_action_task_id"] = state.get("host_action_task_id")
    if state.get("provider_task_id"):
        result["provider_task_id"] = state["provider_task_id"]
    result_path = execution_root / "production-execution-status.json"
    _write(result_path, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--execute-provider", action="store_true")
    parser.add_argument("--image-execution-adapter")
    parser.add_argument("--image-credential-file", type=Path)
    args = parser.parse_args()
    result = prepare_or_advance(
        args.run_id,
        execute_provider=args.execute_provider,
        image_execution_adapter=args.image_execution_adapter,
        image_credential_file=args.image_credential_file,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] == "BLOCK":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
