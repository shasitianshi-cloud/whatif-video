#!/usr/bin/env python3
"""Synchronous, explicit-mode, single-run counterfactual orchestrator."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

sys.dont_write_bytecode = True

MODULE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = MODULE_ROOT.parent
CONFIG_PATH = MODULE_ROOT / "config" / "runtime.json"
PROMPTS = {
    "premise_discovery": MODULE_ROOT / "prompts" / "premise-discovery.md",
    "deep_reasoning": MODULE_ROOT / "prompts" / "deep-reasoning.md",
    "master_finalization": MODULE_ROOT / "prompts" / "master-finalization.md",
}
OPERATOR_ROOT = PROJECT_ROOT / "shared" / "operator-baseline" / "whatif-minimal-operator-v1"
OPERATOR_ZIP = PROJECT_ROOT / "shared" / "operator-baseline" / "whatif-minimal-operator-v1-portable.zip"


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def now(config: dict[str, Any]) -> str:
    return datetime.now(ZoneInfo(config["timezone"])).isoformat(timespec="seconds")


def validate_run_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
        raise ValueError("RUN_ID_INVALID")
    return value


def load_operator():
    os.environ["KR_FROZEN_SOURCE_ROOT"] = str(OPERATOR_ROOT / "frozen-source-reference")
    spec = importlib.util.spec_from_file_location("whatif_relation_operator", OPERATOR_ROOT / "src" / "relation_operator.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("OPERATOR_LOAD_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot_hashes(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): sha256(p) for p in sorted(root.rglob("*")) if p.is_file()}


class PromptExecutor:
    """Model-agnostic prompt executor: fixtures in test, Work-hosted callable in real."""

    def __init__(
        self,
        mode: str,
        model: str,
        fixture: Path | None,
        host_call: Callable[[str, str, dict[str, Any]], dict[str, Any]] | None,
    ):
        self.mode = mode
        self.model = model
        self.host_call = host_call
        self.calls: dict[str, int] = {}
        self.fixture = read_json(fixture) if fixture else None
        if mode == "test" and self.fixture is None:
            raise ValueError("TEST_MODE_REQUIRES_FIXTURE")

    def call(self, stage: str, prompt: str, inputs: dict[str, Any]) -> tuple[dict[str, Any], str]:
        ordinal = self.calls.get(stage, 0)
        self.calls[stage] = ordinal + 1
        if self.mode == "test":
            value = self.fixture[stage]
            if isinstance(value, list):
                if ordinal >= len(value):
                    raise RuntimeError(f"FIXTURE_RESPONSE_EXHAUSTED:{stage}")
                value = value[ordinal]
            raw = json.dumps(value, ensure_ascii=False)
            return value, raw
        if self.host_call is None:
            raise RuntimeError("WORK_HOST_PROMPT_EXECUTION_REQUIRED")
        value = self.host_call(stage, prompt, inputs)
        if not isinstance(value, dict):
            raise RuntimeError(f"MODEL_OUTPUT_NOT_OBJECT:{stage}")
        raw = json.dumps(value, ensure_ascii=False)
        return value, raw


def record_model_call(
    evidence: Path,
    stage: str,
    attempt: int,
    prompt_path: Path,
    model: str,
    input_ref: str,
    output_ref: str,
    raw: str,
) -> None:
    suffix = f"-attempt-{attempt}" if stage == "premise-discovery" else ""
    raw_path = evidence / f"{stage}{suffix}-model-raw.txt"
    raw_path.write_text(raw.rstrip() + "\n", encoding="utf-8")
    write_json(
        evidence / f"{stage}{suffix}-model-call.json",
        {
            "prompt_path": str(prompt_path.relative_to(MODULE_ROOT)),
            "prompt_sha256": sha256(prompt_path),
            "model": model,
            "input_ref": input_ref,
            "output_ref": output_ref,
        },
    )


def run_operator(operator: Any, intent: str, payload: dict[str, Any], trace: Any, evidence: Path, name: str) -> dict[str, Any]:
    result = operator.operate(intent, payload, trace=trace)
    write_json(evidence / f"{name}-operator-result.json", result)
    return result


def premise_shape_error(premise: dict[str, Any]) -> str | None:
    if premise.get("status", "VALID") != "VALID":
        return str(premise.get("failure_reason") or "MODEL_MARKED_INVALID")
    required = ("anchor", "nodes", "edges", "perturbation", "raw_premise", "premise", "seed")
    missing = [name for name in required if name not in premise]
    if missing:
        return "MISSING_FIELDS:" + ",".join(missing)
    if not premise["nodes"] or not premise["edges"] or not premise["premise"].strip():
        return "EMPTY_PREMISE_STRUCTURE"
    if premise["perturbation"].get("kind") not in {"remove_edge", "reverse_edge", "set_attribute"}:
        return "PERTURBATION_KIND_UNSUPPORTED"
    if not premise["perturbation"].get("rationale"):
        return "NATURAL_STRUCTURAL_ALIGNMENT_NOT_DECLARED"
    return None


def execute(
    run_id: str,
    anchor: str,
    mode: str,
    model: str = "host-managed",
    fixture_path: Path | None = None,
    host_call: Callable[[str, str, dict[str, Any]], dict[str, Any]] | None = None,
) -> Path:
    run_id = validate_run_id(run_id)
    if mode not in {"real", "test"}:
        raise ValueError("MODE_INVALID")
    if mode == "real" and fixture_path is not None:
        raise ValueError("FIXTURE_FORBIDDEN_IN_REAL_MODE")
    if mode == "test" and host_call is not None:
        raise ValueError("WORK_HOST_CALL_FORBIDDEN_IN_TEST_MODE")
    if not anchor.strip():
        raise ValueError("ANCHOR_REQUIRED")
    config = read_json(CONFIG_PATH)
    if sha256(OPERATOR_ZIP) != config["operator_zip_sha256"]:
        raise RuntimeError("OPERATOR_BASELINE_SHA256_MISMATCH")
    prompts = {name: path.read_text(encoding="utf-8") for name, path in PROMPTS.items()}
    before = snapshot_hashes(OPERATOR_ROOT)
    executor = PromptExecutor(mode, model, fixture_path, host_call)

    run_root = PROJECT_ROOT / "runs" / run_id
    if run_root.exists():
        raise FileExistsError("RUN_ID_ALREADY_EXISTS")
    input_root = run_root / "input"
    flow_root = run_root / "counterfactual-reasoning"
    work = flow_root / "work"
    evidence = flow_root / "evidence"
    work.mkdir(parents=True)
    evidence.mkdir(parents=True)
    anchor_input = {"run_id": run_id, "anchor": anchor, "timezone": config["timezone"], "language": config["language"], "mode": mode, "created_at": now(config)}
    write_json(input_root / "anchor.json", anchor_input)
    write_json(evidence / "anchor-input.json", anchor_input)

    operator = load_operator()
    trace = operator.EvidenceTrace(evidence, run_id)
    premise: dict[str, Any] | None = None
    premise_audit: dict[str, Any] | None = None
    perturb_audit: dict[str, Any] | None = None
    attempt_records = []
    for attempt in range(1, int(config["max_premise_retry"]) + 2):
        premise, raw = executor.call("premise_discovery", prompts["premise_discovery"], {"run_id": run_id, "anchor": anchor, "language": config["language"], "attempt": attempt})
        output_ref = f"evidence/premise-discovery-attempt-{attempt}-model-raw.txt"
        record_model_call(evidence, "premise-discovery", attempt, PROMPTS["premise_discovery"], model, "input/anchor.json", output_ref, raw)
        write_json(evidence / f"premise-source-attempt-{attempt}.json", premise)
        failure = premise_shape_error(premise)
        if failure is None:
            graph = {"nodes": premise["nodes"], "edges": premise["edges"], "seed": premise["seed"], "max_depth": 5}
            premise_audit = run_operator(operator, "expand", graph, trace, evidence, f"premise-attempt-{attempt}-expand")
            perturb_audit = run_operator(operator, "perturb", {**graph, "perturbation": premise["perturbation"]}, trace, evidence, f"premise-attempt-{attempt}-perturb")
            if premise_audit["decision"].upper() == "INVALID" or perturb_audit["decision"].upper() == "INVALID":
                failure = "OPERATOR_INVALID"
        status = "VALID" if failure is None else "INVALID"
        attempt_records.append({"attempt": attempt, "status": status, "failure_reason": failure})
        if failure is None:
            break
    write_json(evidence / "premise-attempts.json", attempt_records)
    if not premise or attempt_records[-1]["status"] != "VALID":
        raise RuntimeError("PREMISE_RETRY_EXHAUSTED")
    write_json(work / "premise-source.json", {"run_id": run_id, **premise})
    write_json(evidence / "premise-source.json", {"run_id": run_id, **premise})
    (work / "premise.md").write_text(premise["premise"].strip() + "\n", encoding="utf-8")
    write_json(evidence / "operator-premise-audit.json", {"expand": premise_audit, "perturb": perturb_audit, "natural_premise": premise["premise"], "structural_perturbation": premise["perturbation"]})
    (evidence / "final-premise.md").write_text(premise["premise"].strip() + "\n", encoding="utf-8")

    reasoning_input = {"run_id": run_id, "anchor": anchor, "premise": premise, "operator_premise_audit": {"expand": premise_audit, "perturb": perturb_audit}}
    reasoning, raw = executor.call("deep_reasoning", prompts["deep_reasoning"], reasoning_input)
    record_model_call(evidence, "deep-reasoning", 1, PROMPTS["deep_reasoning"], model, "work/premise-source.json", "evidence/deep-reasoning-model-raw.txt", raw)
    if reasoning.get("decision") not in {"CONTINUE", "STOP", "INVALID"}:
        raise ValueError("REASONING_DECISION_INVALID")
    if reasoning["decision"] == "INVALID":
        raise RuntimeError("COUNTERFACTUAL_REASONING_INVALID")
    if not reasoning.get("reasoning_source") or not reasoning.get("reasoning_graph"):
        raise RuntimeError("REASONING_OUTPUT_INCOMPLETE")
    (work / "reasoning-source.md").write_text(reasoning["reasoning_source"].rstrip() + "\n", encoding="utf-8")
    write_json(work / "reasoning-graph.json", reasoning["reasoning_graph"])
    (evidence / "reasoning-source.md").write_text(reasoning["reasoning_source"].rstrip() + "\n", encoding="utf-8")
    write_json(evidence / "reasoning-graph.json", reasoning["reasoning_graph"])
    final_audit = run_operator(operator, "expand", reasoning["reasoning_graph"], trace, evidence, "reasoning-expand")
    propagation = run_operator(operator, "propagate", reasoning["reasoning_graph"], trace, evidence, "reasoning-propagate")
    if final_audit["decision"].upper() == "INVALID":
        raise RuntimeError("REASONING_OPERATOR_INVALID")
    decisions = {
        "run_id": run_id,
        "operator_decision": propagation["decision"],
        "operator_stop_meaning": "graph_frontier_exhausted_only",
        "semantic_decision": reasoning["decision"],
        "semantic_stop_meaning": "main_mechanisms_closed_and_further_expansion_does_not_materially_change_terminal",
        "regime_change_meaning": "structural_transition_hint_only",
    }
    write_json(evidence / "operator-reasoning-audit.json", {"expand": final_audit, "propagate": propagation, **decisions})
    write_json(evidence / "reasoning-decisions.json", decisions)

    if reasoning["decision"] == "CONTINUE":
        write_json(
            evidence / "semantic-continue-block.json",
            {
                "run_id": run_id,
                "error": "REASONING_NOT_CLOSED",
                "master_finalization_not_executed": True,
                "counterfactual_master_not_created": True,
                "counterfactual_master_gate_not_passed": True,
            },
        )
        raise RuntimeError("REASONING_NOT_CLOSED")

    finalization_input = {"run_id": run_id, "reasoning_source": reasoning["reasoning_source"], "operator_audit": {"expand": final_audit, "propagate": propagation}, "semantic_decision": reasoning["decision"]}
    finalization, raw = executor.call("master_finalization", prompts["master_finalization"], finalization_input)
    record_model_call(evidence, "master-finalization", 1, PROMPTS["master_finalization"], model, "work/reasoning-source.md + evidence/operator-reasoning-audit.json", "evidence/master-finalization-model-raw.txt", raw)
    master_text = finalization.get("counterfactual_master")
    if not isinstance(master_text, str) or not master_text.strip():
        raise RuntimeError("MASTER_FINALIZATION_OUTPUT_INVALID")
    master = flow_root / "counterfactual-master.md"
    master.write_text(master_text.rstrip() + "\n", encoding="utf-8")
    (evidence / "counterfactual-master.md").write_text(master_text.rstrip() + "\n", encoding="utf-8")
    digest = sha256(master)
    unchanged = before == snapshot_hashes(OPERATOR_ROOT)
    if not unchanged:
        raise RuntimeError("OPERATOR_BASELINE_CHANGED")
    real = mode == "real"
    gate = {
        "run_id": run_id,
        "gate": "COUNTERFACTUAL_MASTER_GATE" if real else "ORCHESTRATOR_REGRESSION_SMOKE",
        "status": "PASS",
        "execution_mode": mode,
        "real_execution_verified": real,
        "artifact": str(master.relative_to(PROJECT_ROOT)),
        "sha256": digest,
        "operator_baseline_sha256": config["operator_zip_sha256"],
        "operator_baseline_unchanged": unchanged,
        "knowledge_persistence": False,
        "completed_at": now(config),
    }
    write_json(flow_root / "counterfactual-master-gate.json", gate)
    write_json(evidence / "gate-record.json", gate)
    return flow_root


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("real", "test"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--anchor", required=True)
    parser.add_argument("--model", default="host-managed")
    parser.add_argument("--model-fixture", type=Path)
    args = parser.parse_args()
    try:
        result = execute(args.run_id, args.anchor, args.mode, args.model, args.model_fixture.resolve() if args.model_fixture else None)
    except Exception as exc:
        print(f"COUNTERFACTUAL_REASONING=FAIL\nERROR={exc}", file=sys.stderr)
        return 1
    if args.mode == "real":
        print(f"COUNTERFACTUAL_REASONING_IMPLEMENTED=true\nCOUNTERFACTUAL_MASTER_GATE=PASS\nREAL_EXECUTION_VERIFIED=true\nRUN_ROOT={result}")
    else:
        print(f"ORCHESTRATOR_REGRESSION_SMOKE=PASS\nREAL_EXECUTION_VERIFIED=false\nRUN_ROOT={result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
