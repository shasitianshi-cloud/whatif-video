#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
ENTRY = ROOT / "src" / "video_master.py"
spec = importlib.util.spec_from_file_location("video_master", ENTRY)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)


def test_identity_guards() -> None:
    source = PROJECT / "runs" / "real-smoke-human-001" / "counterfactual-reasoning" / "counterfactual-master.md"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    data, actual = module._assert_formal_input("real-smoke-human-001", source, digest)
    assert data and actual == digest
    try:
        module._assert_formal_input("wrong-run", source, digest)
    except module.VideoMasterError as exc:
        assert str(exc) == "FORMAL_INPUT_RUN_ID_MISMATCH"
    else:
        raise AssertionError("run identity mismatch accepted")


def test_output_boundary() -> None:
    assert module._validate_output("世界先发生变化，随后原有约束接管局面。")
    for invalid in ("", "镜头切到城市", "UPSTREAM_REASONING_DEFECT: missing chain"):
        try:
            module._validate_output(invalid)
        except module.VideoMasterError:
            pass
        else:
            raise AssertionError(f"invalid output accepted: {invalid!r}")


def test_prompt_contract() -> None:
    polish_path = ROOT / "prompts" / "video-master-polish.md"
    lowering_path = ROOT / "prompts" / "video-master-language-lowering.md"
    assert polish_path.is_file() and lowering_path.is_file()
    prompt = polish_path.read_text(encoding="utf-8")
    lowering = lowering_path.read_text(encoding="utf-8")
    assert prompt.strip() and lowering.strip()
    assert module.POLISH_PROMPT_PATH.resolve() == polish_path.resolve()
    assert module.LANGUAGE_LOWERING_PROMPT_PATH.resolve() == lowering_path.resolve()
    for required in (
        "信息集合必须是输入信息集合的子集",
        "CLAIM_STRENGTH_CONSERVATION",
        "UPSTREAM_REASONING_DEFECT",
        "Video Master 只回答 WHAT IS TOLD",
        "不得输出镜头",
        "只输出连续正文",
    ):
        assert required in prompt
    for stable_lowering_responsibility in (
        "行业术语",
        "政策术语",
        "学术术语",
        "不增加事实",
        "不改变原义",
        "局部词语或短语级降维",
    ):
        assert stable_lowering_responsibility in lowering


def test_two_step_artifact_contract() -> None:
    source = PROJECT / "runs" / "real-smoke-human-001" / "counterfactual-reasoning" / "counterfactual-master.md"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    calls = []

    def model_call(request: str) -> str:
        calls.append(request)
        return "第一段保持不变。\n\n第二段保持不变。"

    with tempfile.TemporaryDirectory(dir=PROJECT / "runs") as temp_dir:
        run_id = Path(temp_dir).name
        upstream = PROJECT / "runs" / run_id / "counterfactual-reasoning" / "counterfactual-master.md"
        upstream.parent.mkdir(parents=True)
        upstream.write_bytes(source.read_bytes())
        gate = module.run_video_master(
            run_id=run_id,
            counterfactual_master_path=upstream,
            expected_counterfactual_master_sha256=digest,
            model_call=model_call,
        )
        run_root = PROJECT / "runs" / run_id / "video-master"
        assert len(calls) == 2
        assert (run_root / "work" / "video-master-source.md").is_file()
        assert (run_root / "evidence" / "polish-model-call.json").is_file()
        lowering_evidence = json.loads((run_root / "evidence" / "language-lowering-model-call.json").read_text())
        assert lowering_evidence["input_path"].endswith("work/video-master-source.md")
        assert lowering_evidence["output_path"].endswith("video-master.md")
        assert gate["artifact"].endswith("video-master.md")
        assert gate["sha256"] == hashlib.sha256((run_root / "video-master.md").read_bytes()).hexdigest()


def test_frozen_upstream() -> None:
    source = PROJECT / "runs" / "real-smoke-human-001" / "counterfactual-reasoning" / "counterfactual-master.md"
    gate_path = source.with_name("counterfactual-master-gate.json")
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    assert hashlib.sha256(source.read_bytes()).hexdigest() == gate["sha256"]
    assert gate["sha256"] == "125bd10c52180d0dfa798dd1b79450fb6fb617e2342dd2b937231c8e3277e449"


if __name__ == "__main__":
    test_identity_guards()
    test_output_boundary()
    test_prompt_contract()
    test_two_step_artifact_contract()
    test_frozen_upstream()
    print("VIDEO_MASTER_REGRESSION=PASS")
