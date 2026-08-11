from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "video-production/src"))

from run_asset_executor import advance, ingest_host_receipt


def write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def receipt(task: dict, rel: str, raw: bytes) -> dict:
    return {
        "schema_version": 1,
        "run_id": task["run_id"],
        "task_id": task["task_id"],
        "asset_id": task["asset_id"],
        "status": "SUCCESS",
        "generation_route": "gpt-image-2",
        "execution_route": "builtin_image_generation",
        "asset_kind": "image",
        "role": task["role"],
        "in_content_timeline": task["in_content_timeline"],
        "prompt_sha256": hashlib.sha256(task["prompt"].encode()).hexdigest(),
        "local_path": rel,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "file_size_bytes": len(raw),
        "width": 1280,
        "height": 720,
        "model_identity": "host-managed",
    }


def run():
    run_id = "serial-executor-regression-001"
    run_root = ROOT / "runs" / run_id
    if run_root.exists():
        shutil.rmtree(run_root)
    ref = {
        "task_id": "dispatch-ref-001", "run_id": run_id, "asset_id": "ref-001",
        "role": "execution_reference", "generation_route": "gpt-image-2",
        "expected_asset_kind": "image", "prompt": "literal reference prompt",
        "in_content_timeline": False,
    }
    vid = {
        "task_id": "dispatch-vid-001", "run_id": run_id, "asset_id": "vid-001",
        "role": "content_visual", "generation_route": "happyhorse",
        "expected_asset_kind": "video", "generation_mode": "I2V",
        "prompt": "literal dependent video prompt", "duration_ms": 3000,
        "continuity": {"kind": "generated_reference", "reference_asset_id": "ref-001"},
        "in_content_timeline": True,
    }
    dispatch = {"schema_version": 1, "run_id": run_id, "tasks": [ref, vid]}

    state = advance(dispatch, execute_provider=False)
    assert state["status"] == "HOST_ACTION_REQUIRED"
    assert state["host_action_task_id"] == ref["task_id"]
    assert state["next_task_index"] == 0

    raw = b"synthetic-host-image"
    rel = f"runs/{run_id}/video-production/execution/ref-001/host-image.png"
    image = ROOT / rel
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(raw)
    receipt_path = image.with_name("host-image-receipt.external.json")
    write(receipt_path, receipt(ref, rel, raw))
    artifact = ingest_host_receipt(dispatch, ref["task_id"], receipt_path)
    assert artifact["status"] == "SUCCESS"

    state = advance(dispatch, execute_provider=False)
    assert state["status"] == "PROVIDER_EXECUTION_REQUIRED"
    assert state["provider_task_id"] == vid["task_id"]
    assert state["next_task_index"] == 1
    assert state["serial_execution"] is True
    assert state["latest_discovery_used"] is False

    # Separate image-only run proves exact three-count completeness after explicit receipts.
    run2 = "serial-executor-regression-002"
    root2 = ROOT / "runs" / run2
    if root2.exists():
        shutil.rmtree(root2)
    t1 = dict(ref, task_id="dispatch-img-a", run_id=run2, asset_id="img-a", role="content_visual", in_content_timeline=True)
    t2 = dict(ref, task_id="dispatch-img-b", run_id=run2, asset_id="img-b", role="cover", in_content_timeline=False)
    d2 = {"schema_version": 1, "run_id": run2, "tasks": [t1, t2]}
    for task in [t1, t2]:
        s = advance(d2, execute_provider=False)
        assert s["status"] == "HOST_ACTION_REQUIRED" and s["host_action_task_id"] == task["task_id"]
        data = (task["asset_id"] + "-bytes").encode()
        local_rel = f"runs/{run2}/video-production/execution/{task['asset_id']}/{task['asset_id']}.png"
        p = ROOT / local_rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        rp = p.with_suffix(".receipt.json")
        write(rp, receipt(task, local_rel, data))
        ingest_host_receipt(d2, task["task_id"], rp)
    final = advance(d2, execute_provider=False)
    assert final["status"] == "COMPLETE"
    c = final["completeness"]
    assert c["dispatch_task_count"] == 2
    assert c["executed_task_count"] == 2
    assert c["success_task_count"] == 2
    assert c["asset_execution_completeness_pass"] is True

    print("ASSET_EXECUTOR_SERIAL=true")
    print("BUILTIN_IMAGE_HOST_ACTION_BOUNDARY=true")
    print("HAPPYHORSE_PROVIDER_EXECUTION_NOT_IMPLICIT=true")
    print("LATEST_DISCOVERY_USED=false")
    print("DISPATCH_EXECUTED_SUCCESS_COUNTS_EQUAL=true")
    print("SERIAL_ASSET_EXECUTOR_RECOVERY_REGRESSION=PASS")


if __name__ == "__main__":
    run()
