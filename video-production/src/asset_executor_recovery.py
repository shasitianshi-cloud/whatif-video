"""Provider-independent Asset Executor recovery boundary.

This module never substitutes a provider route. Builtin image generation is host-managed:
we emit an exact request and validate a returned receipt. HappyHorse execution artifacts are
validated here after a provider-specific runner executes them.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def make_host_image_request(task: dict) -> dict:
    if task.get("generation_route") != "gpt-image-2" or task.get("expected_asset_kind") != "image":
        raise RuntimeError("HOST_IMAGE_REQUEST_ROUTE_MISMATCH")
    prompt = str(task.get("prompt", ""))
    if not prompt:
        raise RuntimeError("HOST_IMAGE_REQUEST_PROMPT_REQUIRED")
    return {
        "schema_version": 1,
        "run_id": task["run_id"],
        "task_id": task["task_id"],
        "asset_id": task["asset_id"],
        "status": "HOST_ACTION_REQUIRED",
        "generation_route": "gpt-image-2",
        "execution_route": "builtin_image_generation",
        "asset_kind": "image",
        "role": task["role"],
        "in_content_timeline": bool(task["in_content_timeline"]),
        "prompt_sha256": sha256_text(prompt),
        "host_action_request": {
            "capability": "builtin_image_generation",
            "prompt": prompt,
            "prompt_passthrough": True,
            "refine_prompt": False,
            "expected_asset_kind": "image",
        },
        "recovery_executor_reconstructed": True,
        "historical_executor_byte_identical": False,
    }


def validate_host_image_receipt(task: dict, receipt: dict, project_root: Path) -> dict:
    request = make_host_image_request(task)
    required_equal = {
        "run_id": task["run_id"],
        "task_id": task["task_id"],
        "asset_id": task["asset_id"],
        "generation_route": "gpt-image-2",
        "execution_route": "builtin_image_generation",
        "asset_kind": "image",
        "role": task["role"],
        "in_content_timeline": bool(task["in_content_timeline"]),
        "prompt_sha256": request["prompt_sha256"],
    }
    for key, expected in required_equal.items():
        if receipt.get(key) != expected:
            raise RuntimeError(f"HOST_IMAGE_RECEIPT_MISMATCH:{key}")
    if receipt.get("status") != "SUCCESS":
        raise RuntimeError("HOST_IMAGE_EXECUTION_NOT_SUCCESS")
    local_path = str(receipt.get("local_path", "")).strip()
    if not local_path:
        raise RuntimeError("HOST_IMAGE_LOCAL_PATH_REQUIRED")
    path = (project_root / local_path).resolve()
    root = project_root.resolve()
    if path != root and root not in path.parents:
        raise RuntimeError("HOST_IMAGE_PATH_OUTSIDE_PROJECT")
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError("HOST_IMAGE_ARTIFACT_MISSING")
    observed_sha = sha256_file(path)
    if receipt.get("sha256") != observed_sha:
        raise RuntimeError("HOST_IMAGE_SHA_MISMATCH")
    if int(receipt.get("file_size_bytes") or 0) != path.stat().st_size:
        raise RuntimeError("HOST_IMAGE_SIZE_MISMATCH")
    if int(receipt.get("width") or 0) <= 0 or int(receipt.get("height") or 0) <= 0:
        raise RuntimeError("HOST_IMAGE_DIMENSIONS_REQUIRED")
    out = dict(receipt)
    out["model_identity"] = str(receipt.get("model_identity") or "host-managed")
    out["recovery_executor_reconstructed"] = True
    out["historical_executor_byte_identical"] = False
    return out


def validate_happyhorse_artifact(task: dict, artifact: dict, project_root: Path) -> dict:
    if task.get("generation_route") != "happyhorse" or task.get("expected_asset_kind") != "video":
        raise RuntimeError("HAPPYHORSE_EXECUTION_ROUTE_MISMATCH")
    expected = {
        "run_id": task["run_id"],
        "task_id": task["task_id"],
        "asset_id": task["asset_id"],
        "generation_route": "happyhorse",
        "execution_route": "happyhorse",
        "asset_kind": "video",
        "role": task["role"],
        "in_content_timeline": bool(task["in_content_timeline"]),
        "prompt_sha256": sha256_text(str(task.get("prompt", ""))),
    }
    for key, value in expected.items():
        if artifact.get(key) != value:
            raise RuntimeError(f"HAPPYHORSE_ARTIFACT_MISMATCH:{key}")
    if artifact.get("status") != "SUCCESS":
        raise RuntimeError("HAPPYHORSE_EXECUTION_NOT_SUCCESS")
    meta = artifact.get("provider_metadata") or {}
    if meta.get("project_reuse") is not False:
        raise RuntimeError("HAPPYHORSE_PROJECT_REUSE_FORBIDDEN")
    if meta.get("watermarked") is not False or meta.get("aiWater") is not True:
        raise RuntimeError("HAPPYHORSE_DOWNLOAD_POLICY_MISMATCH")
    if meta.get("ambiguous_task_submission") is True:
        raise RuntimeError("AMBIGUOUS_TASK_SUBMISSION")
    local_path = str(artifact.get("local_path", "")).strip()
    if not local_path:
        raise RuntimeError("HAPPYHORSE_LOCAL_PATH_REQUIRED")
    path = (project_root / local_path).resolve()
    root = project_root.resolve()
    if path != root and root not in path.parents:
        raise RuntimeError("HAPPYHORSE_PATH_OUTSIDE_PROJECT")
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError("HAPPYHORSE_ARTIFACT_MISSING")
    if artifact.get("sha256") != sha256_file(path):
        raise RuntimeError("HAPPYHORSE_SHA_MISMATCH")
    if int(artifact.get("file_size_bytes") or 0) != path.stat().st_size:
        raise RuntimeError("HAPPYHORSE_SIZE_MISMATCH")
    if int(artifact.get("duration_ms") or 0) <= 0:
        raise RuntimeError("HAPPYHORSE_DURATION_REQUIRED")
    out = dict(artifact)
    out["recovery_executor_reconstructed"] = True
    out["historical_executor_byte_identical"] = False
    return out


def execution_completeness(dispatch: dict, artifacts: list[dict]) -> dict:
    tasks = dispatch.get("tasks", [])
    if not isinstance(tasks, list):
        raise RuntimeError("INVALID_DISPATCH")
    by_task = {}
    for artifact in artifacts:
        task_id = artifact.get("task_id")
        if not task_id or task_id in by_task:
            raise RuntimeError("DUPLICATE_OR_MISSING_EXECUTION_ARTIFACT")
        by_task[task_id] = artifact
    expected_ids = [x["task_id"] for x in tasks]
    unexpected = sorted(set(by_task) - set(expected_ids))
    missing = [x for x in expected_ids if x not in by_task]
    successful = [x for x in expected_ids if by_task.get(x, {}).get("status") == "SUCCESS"]
    blocked = [x for x in expected_ids if by_task.get(x, {}).get("status") == "BLOCK"]
    host_required = [x for x in expected_ids if by_task.get(x, {}).get("status") == "HOST_ACTION_REQUIRED"]
    complete = not missing and not unexpected and not blocked and not host_required and len(successful) == len(tasks)
    return {
        "dispatch_task_count": len(tasks),
        "executed_task_count": len([x for x in expected_ids if x in by_task]),
        "success_task_count": len(successful),
        "missing_task_ids": missing,
        "unexpected_task_ids": unexpected,
        "blocked_task_ids": blocked,
        "host_action_required_task_ids": host_required,
        "asset_execution_completeness_pass": complete,
    }
