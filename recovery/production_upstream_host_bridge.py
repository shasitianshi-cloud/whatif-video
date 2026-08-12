"""Same-run Work-host bridge for the frozen upstream production libraries.

The bridge does not implement model/provider calls. Work injects host-managed
callbacks. It only binds Anchor -> Counterfactual Master -> Video Master ->
dynamic Narration Plan with explicit SHA lineage.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Callable

sys.dont_write_bytecode = True
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"MODULE_LOAD_FAILED:{name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_upstream_host_managed(
    *,
    run_id: str,
    anchor: str,
    reasoning_host_call: Callable[[str, str, dict[str, Any]], dict[str, Any]],
    video_master_model_call: Callable[[str], str],
    reasoning_model_name: str = "host-managed",
    video_master_model_name: str = "host-managed",
    expected_counterfactual_contract: str | None = None,
) -> dict[str, Any]:
    if not callable(reasoning_host_call) or not callable(video_master_model_call):
        raise RuntimeError("HOST_MODEL_CALLBACK_REQUIRED")
    if expected_counterfactual_contract is not None and not expected_counterfactual_contract.strip():
        raise RuntimeError("EXPECTED_COUNTERFACTUAL_CONTRACT_INVALID")

    reasoning = _load(
        "whatif_counterfactual_reasoning",
        PROJECT_ROOT / "counterfactual-reasoning" / "src" / "counterfactual_reasoning.py",
    )
    video_master = _load(
        "whatif_video_master",
        PROJECT_ROOT / "video-master" / "src" / "video_master.py",
    )
    video_src = PROJECT_ROOT / "video-production" / "src"
    if str(video_src) not in sys.path:
        sys.path.insert(0, str(video_src))
    production_narration = _load(
        "whatif_production_narration",
        video_src / "production_narration.py",
    )

    reasoning_root = reasoning.execute(
        run_id,
        anchor,
        "real",
        model=reasoning_model_name,
        host_call=reasoning_host_call,
    )
    reasoning_gate_path = reasoning_root / "counterfactual-master-gate.json"
    reasoning_gate = json.loads(reasoning_gate_path.read_text(encoding="utf-8"))
    if (
        reasoning_gate.get("run_id") != run_id
        or reasoning_gate.get("status") != "PASS"
        or reasoning_gate.get("execution_mode") != "real"
        or reasoning_gate.get("real_execution_verified") is not True
    ):
        raise RuntimeError("COUNTERFACTUAL_MASTER_GATE_INVALID")

    premise_source_path = reasoning_root / "work" / "premise-source.json"
    if not premise_source_path.is_file():
        raise RuntimeError("PREMISE_SOURCE_MISSING")
    premise_source = json.loads(premise_source_path.read_text(encoding="utf-8"))
    if premise_source.get("anchor") != anchor:
        raise RuntimeError("PREMISE_SOURCE_ANCHOR_MISMATCH")
    if expected_counterfactual_contract is not None:
        if premise_source.get("raw_premise") != expected_counterfactual_contract:
            raise RuntimeError("COUNTERFACTUAL_CONTRACT_MISMATCH")

    master_path = PROJECT_ROOT / reasoning_gate["artifact"]

    vm_gate = video_master.run_video_master(
        run_id=run_id,
        counterfactual_master_path=master_path,
        expected_counterfactual_master_sha256=reasoning_gate["sha256"],
        model_call=video_master_model_call,
        model_name=video_master_model_name,
    )
    if vm_gate.get("run_id") != run_id or vm_gate.get("status") != "PASS":
        raise RuntimeError("VIDEO_MASTER_GATE_INVALID")
    vm_path = PROJECT_ROOT / vm_gate["artifact"]

    narration = production_narration.prepare_narration(run_id, vm_path, vm_gate["sha256"])
    plan = narration["plan_data"]
    if plan.get("run_id") != run_id or plan.get("source_video_master_sha256") != vm_gate["sha256"]:
        raise RuntimeError("NARRATION_PLAN_LINEAGE_INVALID")

    return {
        "schema_version": 1,
        "run_id": run_id,
        "anchor": anchor,
        "status": "HOST_UPSTREAM_READY_FOR_TTS",
        "counterfactual_master": reasoning_gate["artifact"],
        "counterfactual_master_sha256": reasoning_gate["sha256"],
        "video_master": vm_gate["artifact"],
        "video_master_sha256": vm_gate["sha256"],
        "narration_plan": narration["plan"].relative_to(PROJECT_ROOT).as_posix(),
        "narration_segment_count": plan["segment_count"],
        "segment_count_dynamic": plan["segment_count_dynamic"],
        "same_run_lineage_verified": True,
        "host_model_callbacks_injected": True,
        "expected_counterfactual_contract_verified": expected_counterfactual_contract is not None,
        "provider_generation_executed": False,
        "recovery_bridge_reconstructed": True,
        "historical_bridge_byte_identical": False,
    }
