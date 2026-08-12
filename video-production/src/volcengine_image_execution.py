from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from volcengine_image_adapter import AdapterError, VolcengineImageAdapter, image_dimensions, load_access_key

EXECUTION_ADAPTER = "volcengine_general3_t2i_api"
PROVIDER = "volcengine"
PROVIDER_MODEL = "通用3.0-文生图"
DEFAULT_CREDENTIAL_FILE = Path(".runtime-auth/volcengine-image/credential.txt")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "video-production" / "config" / "volcengine-image.json"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_runtime_adapter(project_root: Path, credential_file: Path | None = None) -> VolcengineImageAdapter:
    source = credential_file or (project_root / DEFAULT_CREDENTIAL_FILE)
    if not source.is_absolute():
        source = project_root / source
    if not source.is_file():
        raise AdapterError("VOLCENGINE_IMAGE_CREDENTIAL_MISSING", "runtime image credential file missing")
    ak, sk = load_access_key(source)
    return VolcengineImageAdapter(ak, sk)


def _image_config() -> dict:
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if (
        data.get("provider") != PROVIDER
        or data.get("width") != 1280
        or data.get("height") != 720
        or data.get("max_concurrency") != 1
        or data.get("parallel_requests") is not False
    ):
        raise RuntimeError("VOLCENGINE_IMAGE_GLOBAL_FORMAT_CONTRACT_INVALID")
    return data


def execute_volcengine_image_task(task: dict, adapter: VolcengineImageAdapter, project_root: Path) -> tuple[Path, dict]:
    if task.get("generation_route") != "gpt-image-2" or task.get("expected_asset_kind") != "image":
        raise RuntimeError("VOLCENGINE_IMAGE_TASK_ROUTE_MISMATCH")
    prompt = str(task.get("prompt", ""))
    if not prompt:
        raise RuntimeError("VOLCENGINE_IMAGE_PROMPT_REQUIRED")

    config = _image_config()
    requested_width = int(config["width"])
    requested_height = int(config["height"])
    result = adapter.generate(
        prompt,
        width=requested_width,
        height=requested_height,
        poll_interval=int(config["poll_interval_seconds"]),
        max_polls=int(config["max_polls"]),
    )
    data = result.image_bytes
    if not data:
        raise AdapterError("EMPTY_IMAGE", "provider returned zero image bytes")
    width, height = image_dimensions(data)
    if width != requested_width or height != requested_height:
        raise RuntimeError("VOLCENGINE_IMAGE_DIMENSIONS_MISMATCH")

    suffix = ".png" if data.startswith(b"\x89PNG\r\n\x1a\n") else ".jpg"
    out_dir = project_root / "runs" / task["run_id"] / "video-production" / "execution" / task["asset_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    image_path = out_dir / f"{task['asset_id']}{suffix}"
    tmp = image_path.with_suffix(image_path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, image_path)

    artifact = {
        "schema_version": 1,
        "run_id": task["run_id"],
        "task_id": task["task_id"],
        "asset_id": task["asset_id"],
        "status": "SUCCESS",
        "generation_route": task["generation_route"],
        "execution_route": EXECUTION_ADAPTER,
        "asset_kind": "image",
        "role": task["role"],
        "in_content_timeline": bool(task["in_content_timeline"]),
        "prompt_sha256": sha256_text(prompt),
        "prompt_passthrough": True,
        "provider": PROVIDER,
        "provider_model": PROVIDER_MODEL,
        "provider_task_id": result.task_id,
        "provider_request_id": result.request_id,
        "provider_response_redacted": result.redacted_response,
        "local_path": image_path.relative_to(project_root).as_posix(),
        "sha256": sha256_file(image_path),
        "file_size_bytes": image_path.stat().st_size,
        "width": width,
        "height": height,
        "requested_width": requested_width,
        "requested_height": requested_height,
        "max_concurrency_observed": adapter.max_in_flight,
        "control_returned_to_caller": True,
        "ambiguous_task_submission": False,
        "recovery_executor_reconstructed": True,
        "historical_executor_byte_identical": False,
    }
    if artifact["sha256"] != hashlib.sha256(data).hexdigest() or artifact["file_size_bytes"] != len(data):
        raise RuntimeError("VOLCENGINE_IMAGE_READBACK_MISMATCH")
    return out_dir / f"{task['asset_id']}.artifact.json", artifact
