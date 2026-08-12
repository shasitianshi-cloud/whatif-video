from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "recovery"))

from production_upstream_host_bridge import run_upstream_host_managed  # noqa: E402

RUN_ID = "production-upstream-host-bridge-regression-v1"
RUN_ROOT = ROOT / "runs" / RUN_ID
FIXTURE = ROOT / "counterfactual-reasoning" / "tests" / "smoke_fixture.json"


def main() -> None:
    shutil.rmtree(RUN_ROOT, ignore_errors=True)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    calls = {"reasoning": [], "video_master": 0}

    def reasoning_host_call(stage: str, prompt: str, inputs: dict):
        assert prompt.strip()
        assert inputs["run_id"] == RUN_ID
        calls["reasoning"].append(stage)
        return fixture[stage]

    def video_master_model_call(prompt: str) -> str:
        assert prompt.strip()
        calls["video_master"] += 1
        if calls["video_master"] == 1:
            return "如果所有人永久失去痛觉，受伤本身不会消失。人们会更晚发现损伤，医院会从因痛就诊转向主动检查，家庭和工作场所也会增加日常检查。"
        return "所有人永久失去痛觉后，损伤仍会发生，只是警报消失。人会更晚发现伤口和疾病，医疗会转向主动检查，家庭和工作场所也会把日常检查变成常规。"

    try:
        result = run_upstream_host_managed(
            run_id=RUN_ID,
            anchor="人类突然永久失去痛觉",
            reasoning_host_call=reasoning_host_call,
            video_master_model_call=video_master_model_call,
            reasoning_model_name="fixture-host-reasoning",
            video_master_model_name="fixture-host-video-master",
        )
        assert result["status"] == "HOST_UPSTREAM_READY_FOR_TTS"
        assert result["run_id"] == RUN_ID
        assert result["same_run_lineage_verified"] is True
        assert result["segment_count_dynamic"] is True
        assert result["provider_generation_executed"] is False
        assert calls["reasoning"] == ["premise_discovery", "deep_reasoning", "master_finalization"]
        assert calls["video_master"] == 2

        cf_gate = json.loads((RUN_ROOT / "counterfactual-reasoning" / "counterfactual-master-gate.json").read_text(encoding="utf-8"))
        vm_gate = json.loads((RUN_ROOT / "video-master" / "video-master-gate.json").read_text(encoding="utf-8"))
        plan = json.loads((RUN_ROOT / "video-production" / "narration" / "narration-plan.json").read_text(encoding="utf-8"))
        assert cf_gate["execution_mode"] == "real"
        assert cf_gate["real_execution_verified"] is True
        assert vm_gate["input_sha256"] == cf_gate["sha256"]
        assert plan["source_video_master_sha256"] == vm_gate["sha256"]
        assert plan["run_id"] == RUN_ID
        print("PRODUCTION_UPSTREAM_HOST_BRIDGE_REGRESSION=PASS")
        print("SAME_RUN_LINEAGE_VERIFIED=true")
        print("HOST_MODEL_CALLBACKS_INJECTED=true")
        print("PROVIDER_GENERATION_EXECUTED=false")
    finally:
        shutil.rmtree(RUN_ROOT, ignore_errors=True)


if __name__ == "__main__":
    main()
