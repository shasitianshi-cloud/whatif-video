#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

MODULE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = MODULE_ROOT.parent
POLISH_PROMPT_PATH = MODULE_ROOT / "prompts" / "video-master-polish.md"
LANGUAGE_LOWERING_PROMPT_PATH = MODULE_ROOT / "prompts" / "video-master-language-lowering.md"
PROMPT_PATH = POLISH_PROMPT_PATH
CONFIG_PATH = MODULE_ROOT / "config" / "runtime.json"


class VideoMasterError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def now_taipei() -> str:
    return datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds")


def _assert_formal_input(run_id: str, artifact: Path, expected_sha256: str) -> tuple[bytes, str]:
    expected = (PROJECT_ROOT / "runs" / run_id / "counterfactual-reasoning" / "counterfactual-master.md").resolve()
    actual_path = artifact.resolve()
    if actual_path != expected:
        raise VideoMasterError("FORMAL_INPUT_RUN_ID_MISMATCH")
    if not actual_path.is_file():
        raise VideoMasterError("FORMAL_INPUT_NOT_FOUND")
    data = actual_path.read_bytes()
    actual_sha256 = sha256_bytes(data)
    if actual_sha256 != expected_sha256:
        raise VideoMasterError("FORMAL_INPUT_SHA256_MISMATCH")
    return data, actual_sha256


def _validate_output(output: str) -> str:
    value = output.strip()
    if not value:
        raise VideoMasterError("EMPTY_VIDEO_MASTER")
    if value.startswith("UPSTREAM_REASONING_DEFECT"):
        raise VideoMasterError(value)
    forbidden = ("镜头切到", "画面展示", "第5秒", "航拍", "特写", "Happy Horse", "HyperFrames", "BGM", "CTA:")
    hit = next((token for token in forbidden if token in value), None)
    if hit:
        raise VideoMasterError(f"AUDIOVISUAL_BOUNDARY_VIOLATION:{hit}")
    return value + "\n"


def run_video_master(
    *,
    run_id: str,
    counterfactual_master_path: Path,
    expected_counterfactual_master_sha256: str,
    model_call: Callable[[str], str],
    model_name: str = "host-managed",
) -> dict:
    source, actual_input_sha256 = _assert_formal_input(
        run_id, counterfactual_master_path, expected_counterfactual_master_sha256
    )
    polish_prompt = POLISH_PROMPT_PATH.read_text(encoding="utf-8")
    lowering_prompt = LANGUAGE_LOWERING_PROMPT_PATH.read_text(encoding="utf-8")
    polish_prompt_sha256 = sha256_bytes(polish_prompt.encode("utf-8"))
    lowering_prompt_sha256 = sha256_bytes(lowering_prompt.encode("utf-8"))
    run_root = PROJECT_ROOT / "runs" / run_id / "video-master"
    if run_root.exists():
        raise VideoMasterError("VIDEO_MASTER_RUN_ALREADY_EXISTS")

    polish_request = polish_prompt + "\n\n---\n\nCOUNTERFACTUAL MASTER INPUT:\n\n" + source.decode("utf-8")
    source_output = _validate_output(model_call(polish_request))
    lowering_request = lowering_prompt + "\n\n---\n\nVIDEO MASTER INPUT:\n\n" + source_output
    lowered_raw_output = model_call(lowering_request)
    final_output = _validate_output(lowered_raw_output)

    work_root = run_root / "work"
    evidence_root = run_root / "evidence"
    work_root.mkdir(parents=True)
    evidence_root.mkdir(parents=True)
    source_path = work_root / "video-master-source.md"
    artifact_path = run_root / "video-master.md"
    gate_path = run_root / "video-master-gate.json"
    source_path.write_text(source_output, encoding="utf-8")
    artifact_path.write_text(final_output, encoding="utf-8")
    artifact_sha256 = sha256_bytes(artifact_path.read_bytes())

    write_json(evidence_root / "formal-input.json", {
        "run_id": run_id,
        "counterfactual_master_path": str(counterfactual_master_path),
        "expected_sha256": expected_counterfactual_master_sha256,
        "actual_sha256": actual_input_sha256,
        "verification_result": "PASS",
    })
    write_json(evidence_root / "polish-model-call.json", {
        "input_path": str(counterfactual_master_path),
        "prompt_path": str(POLISH_PROMPT_PATH.relative_to(PROJECT_ROOT)),
        "prompt_sha256": polish_prompt_sha256,
        "model": model_name or "host-managed",
        "calls": 1,
        "output_path": str(source_path.relative_to(PROJECT_ROOT)),
    })
    write_json(evidence_root / "language-lowering-model-call.json", {
        "input_path": str(source_path.relative_to(PROJECT_ROOT)),
        "prompt_path": str(LANGUAGE_LOWERING_PROMPT_PATH.relative_to(PROJECT_ROOT)),
        "prompt_sha256": lowering_prompt_sha256,
        "model": model_name or "host-managed",
        "calls": 1,
        "output_path": str(artifact_path.relative_to(PROJECT_ROOT)),
    })
    write_json(evidence_root / "final-artifact.json", {
        "artifact": str(artifact_path.relative_to(PROJECT_ROOT)),
        "sha256": artifact_sha256,
        "frozen_at": now_taipei(),
        "knowledge_persistence": False,
    })
    gate = {
        "run_id": run_id,
        "gate": "VIDEO_MASTER_GATE",
        "status": "PASS",
        "input_artifact": str(counterfactual_master_path),
        "input_sha256": actual_input_sha256,
        "artifact": str(artifact_path.relative_to(PROJECT_ROOT)),
        "sha256": artifact_sha256,
        "completed_at": now_taipei(),
    }
    write_json(gate_path, gate)
    return gate | {
        "polish_prompt_sha256": polish_prompt_sha256,
        "language_lowering_prompt_sha256": lowering_prompt_sha256,
        "evidence_root": str(evidence_root),
    }
