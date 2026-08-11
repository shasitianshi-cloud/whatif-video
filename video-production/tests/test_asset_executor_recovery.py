from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from asset_executor_recovery import (
    execution_completeness,
    make_host_image_request,
    validate_happyhorse_artifact,
    validate_host_image_receipt,
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run():
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        image_bytes = b"synthetic-image-fixture"
        video_bytes = b"synthetic-video-fixture"
        image_path = project / "runs/r1/image.png"
        video_path = project / "runs/r1/video.mp4"
        image_path.parent.mkdir(parents=True)
        image_path.write_bytes(image_bytes)
        video_path.write_bytes(video_bytes)

        image_task = {
            "task_id": "dispatch-img-001", "run_id": "r1", "asset_id": "img-001",
            "role": "content_visual", "generation_route": "gpt-image-2",
            "expected_asset_kind": "image", "prompt": "literal prompt",
            "in_content_timeline": True,
        }
        video_task = {
            "task_id": "dispatch-vid-001", "run_id": "r1", "asset_id": "vid-001",
            "role": "content_visual", "generation_route": "happyhorse",
            "expected_asset_kind": "video", "prompt": "literal video prompt",
            "in_content_timeline": True,
        }
        dispatch = {"run_id": "r1", "tasks": [image_task, video_task]}

        pending = make_host_image_request(image_task)
        assert pending["status"] == "HOST_ACTION_REQUIRED"
        assert pending["host_action_request"]["prompt"] == "literal prompt"
        assert pending["host_action_request"]["refine_prompt"] is False
        assert execution_completeness(dispatch, [pending])["asset_execution_completeness_pass"] is False

        image_receipt = {
            "schema_version": 1, "run_id": "r1", "task_id": "dispatch-img-001",
            "asset_id": "img-001", "status": "SUCCESS", "generation_route": "gpt-image-2",
            "execution_route": "builtin_image_generation", "asset_kind": "image",
            "role": "content_visual", "in_content_timeline": True,
            "prompt_sha256": pending["prompt_sha256"],
            "local_path": "runs/r1/image.png", "sha256": sha(image_bytes),
            "file_size_bytes": len(image_bytes), "width": 1280, "height": 720,
            "model_identity": "host-managed",
        }
        image_artifact = validate_host_image_receipt(image_task, image_receipt, project)
        assert image_artifact["status"] == "SUCCESS"

        video_artifact_raw = {
            "schema_version": 1, "run_id": "r1", "task_id": "dispatch-vid-001",
            "asset_id": "vid-001", "status": "SUCCESS", "generation_route": "happyhorse",
            "execution_route": "happyhorse", "asset_kind": "video",
            "role": "content_visual", "in_content_timeline": True,
            "prompt_sha256": hashlib.sha256(b"literal video prompt").hexdigest(),
            "local_path": "runs/r1/video.mp4", "sha256": sha(video_bytes),
            "file_size_bytes": len(video_bytes), "width": 1280, "height": 720,
            "duration_ms": 3000,
            "provider_metadata": {
                "project_reuse": False, "watermarked": False, "aiWater": True,
                "ambiguous_task_submission": False,
            },
        }
        video_artifact = validate_happyhorse_artifact(video_task, video_artifact_raw, project)
        result = execution_completeness(dispatch, [image_artifact, video_artifact])
        assert result["dispatch_task_count"] == 2
        assert result["executed_task_count"] == 2
        assert result["success_task_count"] == 2
        assert result["asset_execution_completeness_pass"] is True

        bad = dict(image_receipt)
        bad["prompt_sha256"] = "0" * 64
        try:
            validate_host_image_receipt(image_task, bad, project)
        except RuntimeError as exc:
            assert "HOST_IMAGE_RECEIPT_MISMATCH:prompt_sha256" in str(exc)
        else:
            raise AssertionError("prompt substitution must block")

        ambiguous = dict(video_artifact_raw)
        ambiguous["provider_metadata"] = dict(video_artifact_raw["provider_metadata"], ambiguous_task_submission=True)
        try:
            validate_happyhorse_artifact(video_task, ambiguous, project)
        except RuntimeError as exc:
            assert "AMBIGUOUS_TASK_SUBMISSION" in str(exc)
        else:
            raise AssertionError("ambiguous task submission must block")

    print("BUILTIN_IMAGE_ROUTE_SUBSTITUTED=false")
    print("HOST_IMAGE_ACTION_REQUIRED_UNTIL_RECEIPT=true")
    print("PROMPT_LITERAL_BINDING_BY_SHA=true")
    print("AMBIGUOUS_TASK_SUBMISSION_FAIL_CLOSED=true")
    print("DISPATCH_EXECUTED_SUCCESS_COUNTS_EQUAL=true")
    print("ASSET_EXECUTOR_RECOVERY_REGRESSION=PASS")


if __name__ == "__main__":
    run()
