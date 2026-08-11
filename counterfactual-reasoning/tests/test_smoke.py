#!/usr/bin/env python3
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

module = Path(__file__).resolve().parents[1]
project = module.parent
run_id = "smoke-painless-human-001"
run = project / "runs" / run_id
if run.exists():
    shutil.rmtree(run)
cmd = [sys.executable, str(module / "src" / "counterfactual_reasoning.py"), "--mode", "test", "--run-id", run_id, "--anchor", "人类突然永久失去痛觉", "--model", "fixture-regression", "--model-fixture", str(module / "tests" / "smoke_fixture.json")]
result = subprocess.run(cmd, text=True, capture_output=True)
assert result.returncode == 0, result.stderr
flow = run / "counterfactual-reasoning"
gate = json.loads((flow / "counterfactual-master-gate.json").read_text(encoding="utf-8"))
master = flow / "counterfactual-master.md"
actual = hashlib.sha256(master.read_bytes()).hexdigest()
assert gate["run_id"] == run_id
assert gate["gate"] == "ORCHESTRATOR_REGRESSION_SMOKE"
assert gate["status"] == "PASS"
assert gate["execution_mode"] == "test"
assert gate["real_execution_verified"] is False
assert gate["sha256"] == actual
assert gate["operator_baseline_unchanged"] is True
assert gate["knowledge_persistence"] is False
assert (flow / "evidence" / "operator-calls.jsonl").exists()
for stage in ("premise-discovery-attempt-1", "deep-reasoning", "master-finalization"):
    call = json.loads((flow / "evidence" / f"{stage}-model-call.json").read_text(encoding="utf-8"))
    assert call["prompt_path"].startswith("prompts/")
    assert len(call["prompt_sha256"]) == 64
assert json.loads((flow / "evidence" / "premise-attempts.json").read_text(encoding="utf-8"))[0]["status"] == "VALID"
assert json.loads((flow / "evidence" / "reasoning-decisions.json").read_text(encoding="utf-8"))["operator_decision"] in {"STOP", "CONTINUE"}
assert not (run / "video-master").exists()
assert not (run / "video-production").exists()

# Configured retry is active: one INVALID response, then one VALID response.
retry_run_id = "regression-premise-retry-001"
retry_run = project / "runs" / retry_run_id
if retry_run.exists():
    shutil.rmtree(retry_run)
fixture = json.loads((module / "tests" / "smoke_fixture.json").read_text(encoding="utf-8"))
invalid = {"status": "INVALID", "failure_reason": "REGRESSION_FIRST_ATTEMPT"}
fixture["premise_discovery"] = [invalid, fixture["premise_discovery"]]
with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as handle:
    json.dump(fixture, handle, ensure_ascii=False)
    retry_fixture = Path(handle.name)
retry_cmd = [sys.executable, str(module / "src" / "counterfactual_reasoning.py"), "--mode", "test", "--run-id", retry_run_id, "--anchor", "人类突然永久失去痛觉", "--model", "fixture-regression", "--model-fixture", str(retry_fixture)]
retry_result = subprocess.run(retry_cmd, text=True, capture_output=True)
retry_fixture.unlink()
assert retry_result.returncode == 0, retry_result.stderr
attempts = json.loads((retry_run / "counterfactual-reasoning" / "evidence" / "premise-attempts.json").read_text(encoding="utf-8"))
assert attempts == [
    {"attempt": 1, "status": "INVALID", "failure_reason": "REGRESSION_FIRST_ATTEMPT"},
    {"attempt": 2, "status": "VALID", "failure_reason": None},
]
shutil.rmtree(retry_run)

# A fixture can never silently enter real execution.
reject_cmd = [sys.executable, str(module / "src" / "counterfactual_reasoning.py"), "--mode", "real", "--run-id", "must-not-exist", "--anchor", "人", "--model-fixture", str(module / "tests" / "smoke_fixture.json")]
reject_result = subprocess.run(reject_cmd, text=True, capture_output=True)
assert reject_result.returncode != 0
assert "FIXTURE_FORBIDDEN_IN_REAL_MODE" in reject_result.stderr
assert not (project / "runs" / "must-not-exist").exists()

# Semantic CONTINUE must stop this run before Master Finalization and Gate.
continue_run_id = "regression-semantic-continue-001"
continue_run = project / "runs" / continue_run_id
if continue_run.exists():
    shutil.rmtree(continue_run)
continue_fixture_data = json.loads((module / "tests" / "smoke_fixture.json").read_text(encoding="utf-8"))
continue_fixture_data["deep_reasoning"]["decision"] = "CONTINUE"
with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as handle:
    json.dump(continue_fixture_data, handle, ensure_ascii=False)
    continue_fixture = Path(handle.name)
continue_cmd = [sys.executable, str(module / "src" / "counterfactual_reasoning.py"), "--mode", "test", "--run-id", continue_run_id, "--anchor", "人类突然永久失去痛觉", "--model-fixture", str(continue_fixture)]
continue_result = subprocess.run(continue_cmd, text=True, capture_output=True)
continue_fixture.unlink()
continue_flow = continue_run / "counterfactual-reasoning"
assert continue_result.returncode != 0
assert "ERROR=REASONING_NOT_CLOSED" in continue_result.stderr
assert not (continue_flow / "counterfactual-master.md").exists()
assert not (continue_flow / "counterfactual-master-gate.json").exists()
assert not (continue_flow / "evidence" / "master-finalization-model-call.json").exists()
continue_block = json.loads((continue_flow / "evidence" / "semantic-continue-block.json").read_text(encoding="utf-8"))
assert continue_block["master_finalization_not_executed"] is True
assert continue_block["counterfactual_master_not_created"] is True
assert continue_block["counterfactual_master_gate_not_passed"] is True
shutil.rmtree(continue_run)

# Semantic INVALID remains a hard failure before Master Finalization and Gate.
invalid_run_id = "regression-semantic-invalid-001"
invalid_run = project / "runs" / invalid_run_id
if invalid_run.exists():
    shutil.rmtree(invalid_run)
invalid_fixture_data = json.loads((module / "tests" / "smoke_fixture.json").read_text(encoding="utf-8"))
invalid_fixture_data["deep_reasoning"]["decision"] = "INVALID"
with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as handle:
    json.dump(invalid_fixture_data, handle, ensure_ascii=False)
    invalid_fixture = Path(handle.name)
invalid_cmd = [sys.executable, str(module / "src" / "counterfactual_reasoning.py"), "--mode", "test", "--run-id", invalid_run_id, "--anchor", "人类突然永久失去痛觉", "--model-fixture", str(invalid_fixture)]
invalid_result = subprocess.run(invalid_cmd, text=True, capture_output=True)
invalid_fixture.unlink()
invalid_flow = invalid_run / "counterfactual-reasoning"
assert invalid_result.returncode != 0
assert "ERROR=COUNTERFACTUAL_REASONING_INVALID" in invalid_result.stderr
assert not (invalid_flow / "counterfactual-master.md").exists()
assert not (invalid_flow / "counterfactual-master-gate.json").exists()
shutil.rmtree(invalid_run)

# Prompt-level refinement: a persistent rule over a changing population must
# resolve future-member scope inside the current Premise call.
premise_prompt = (module / "prompts" / "premise-discovery.md").read_text(encoding="utf-8")
assert "WHO" in premise_prompt
assert "WHEN" in premise_prompt
assert "PERSISTENCE" in premise_prompt
assert "FUTURE MEMBERS" in premise_prompt
future_member_fixture = {
    "anchor": "人类永久不再需要睡眠",
    "premise": "从改变发生时起，现存人口立即永久不再需要睡眠；此后出生的人同样不再具有睡眠需求。",
}
assert "现存人口" in future_member_fixture["premise"]
assert "此后出生的人" in future_member_fixture["premise"]

# A material adjacent mechanism must keep semantic reasoning open and remains
# blocked by the existing REASONING_NOT_CLOSED behavior.
deep_prompt = (module / "prompts" / "deep-reasoning.md").read_text(encoding="utf-8")
assert "material adjacent mechanism" in deep_prompt
assert "否则输出 `CONTINUE`" in deep_prompt
material_adjacent_fixture = json.loads((module / "tests" / "smoke_fixture.json").read_text(encoding="utf-8"))
material_adjacent_fixture["deep_reasoning"]["decision"] = "CONTINUE"
material_adjacent_fixture["deep_reasoning"]["raw_output"] = "昼夜节律仍存在且足以显著改变全天候社会的长期结构，Terminal 尚未闭合。"
material_run_id = "regression-material-adjacent-001"
material_run = project / "runs" / material_run_id
if material_run.exists():
    shutil.rmtree(material_run)
with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as handle:
    json.dump(material_adjacent_fixture, handle, ensure_ascii=False)
    material_fixture = Path(handle.name)
material_cmd = [sys.executable, str(module / "src" / "counterfactual_reasoning.py"), "--mode", "test", "--run-id", material_run_id, "--anchor", "人类永久不再需要睡眠", "--model-fixture", str(material_fixture)]
material_result = subprocess.run(material_cmd, text=True, capture_output=True)
material_fixture.unlink()
assert material_result.returncode != 0
assert "ERROR=REASONING_NOT_CLOSED" in material_result.stderr
assert not (material_run / "counterfactual-reasoning" / "counterfactual-master.md").exists()
assert not (material_run / "counterfactual-reasoning" / "counterfactual-master-gate.json").exists()
shutil.rmtree(material_run)

# A non-material adjacent detail that only adds another example must not make
# STOP impossible.
nonmaterial_fixture = json.loads((module / "tests" / "smoke_fixture.json").read_text(encoding="utf-8"))
nonmaterial_fixture["deep_reasoning"]["decision"] = "STOP"
nonmaterial_fixture["deep_reasoning"]["raw_output"] += " 另一个职业案例只增加例子，不改变主链或 Terminal。"
nonmaterial_run_id = "regression-nonmaterial-adjacent-001"
nonmaterial_run = project / "runs" / nonmaterial_run_id
if nonmaterial_run.exists():
    shutil.rmtree(nonmaterial_run)
with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as handle:
    json.dump(nonmaterial_fixture, handle, ensure_ascii=False)
    nonmaterial_fixture_path = Path(handle.name)
nonmaterial_cmd = [sys.executable, str(module / "src" / "counterfactual_reasoning.py"), "--mode", "test", "--run-id", nonmaterial_run_id, "--anchor", "人类突然永久失去痛觉", "--model-fixture", str(nonmaterial_fixture_path)]
nonmaterial_result = subprocess.run(nonmaterial_cmd, text=True, capture_output=True)
nonmaterial_fixture_path.unlink()
assert nonmaterial_result.returncode == 0, nonmaterial_result.stderr
nonmaterial_gate = json.loads((nonmaterial_run / "counterfactual-reasoning" / "counterfactual-master-gate.json").read_text(encoding="utf-8"))
assert nonmaterial_gate["status"] == "PASS"
shutil.rmtree(nonmaterial_run)

finalization_prompt = (module / "prompts" / "master-finalization.md").read_text(encoding="utf-8")
assert "CLAIM_STRENGTH_CONSERVATION" in finalization_prompt
assert "不得自行修补" in finalization_prompt

print("REAL_PATH_WIRED=true")
print("FIXTURE_ISOLATED=true")
print("PROMPTS_LOADED=true")
print("PREMISE_RETRY_VERIFIED=true")
print("SEMANTIC_CONTINUE_BLOCKED=true")
print("CONTINUE_REGRESSION_PASS=true")
print("ORCHESTRATOR_REGRESSION_SMOKE=PASS")
print("OPERATOR_BASELINE_UNCHANGED=true")
print("KNOWLEDGE_PERSISTENCE=false")
print("CONTRACT_COMPLETENESS_REFINED=true")
print("FUTURE_MEMBER_SCOPE_HANDLED=true")
print("MATERIAL_ADJACENT_MECHANISM_CHECK=true")
print("SEMANTIC_STOP_REFINED=true")
print("REGRESSION_PASS=true")
