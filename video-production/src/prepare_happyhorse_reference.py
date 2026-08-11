"""Prepare HappyHorse I2V reference media without creative decisions.

- previous_asset_frame: extract exactly at prior duration - 150 ms.
- generated_reference: validate and forward the already generated same-run image artifact.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _inside(root: Path, rel: str) -> Path:
    root = root.resolve()
    p = (root / rel).resolve()
    if p != root and root not in p.parents:
        raise RuntimeError("REFERENCE_PATH_OUTSIDE_PROJECT")
    return p


def _probe_image(path: Path) -> tuple[int, int]:
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    data = json.loads(p.stdout)
    width = int(data["streams"][0]["width"])
    height = int(data["streams"][0]["height"])
    if width <= 0 or height <= 0:
        raise RuntimeError("REFERENCE_IMAGE_UNREADABLE")
    return width, height


def validate_success_artifact(artifact: dict, *, run_id: str, asset_id: str, kind: str, project_root: Path) -> Path:
    if artifact.get("status") != "SUCCESS":
        raise RuntimeError("REFERENCE_SOURCE_NOT_SUCCESS")
    if artifact.get("run_id") != run_id:
        raise RuntimeError("CONTINUITY_CROSS_RUN_FORBIDDEN")
    if artifact.get("asset_id") != asset_id:
        raise RuntimeError("REFERENCE_ASSET_ID_MISMATCH")
    if artifact.get("asset_kind") != kind:
        raise RuntimeError("REFERENCE_ASSET_KIND_MISMATCH")
    local_path = str(artifact.get("local_path", ""))
    p = _inside(project_root, local_path)
    if not p.is_file() or p.stat().st_size <= 0:
        raise RuntimeError("REFERENCE_SOURCE_MISSING")
    if artifact.get("sha256") != sha256_file(p):
        raise RuntimeError("REFERENCE_SOURCE_SHA_MISMATCH")
    return p


def prepare_reference(task: dict, source_artifact: dict, project_root: Path) -> dict:
    continuity = task.get("continuity") or {"kind": "none"}
    kind = continuity.get("kind")
    run_id = str(task.get("run_id", ""))
    if task.get("generation_route") != "happyhorse" or task.get("generation_mode") not in {"I2V", "R2V"}:
        raise RuntimeError("REFERENCE_PREPARATION_ROUTE_MISMATCH")

    if kind == "generated_reference":
        ref_id = str(continuity.get("reference_asset_id", ""))
        p = validate_success_artifact(source_artifact, run_id=run_id, asset_id=ref_id, kind="image", project_root=project_root)
        width, height = _probe_image(p)
        return {
            "schema_version": 1,
            "run_id": run_id,
            "dependent_asset_id": task["asset_id"],
            "source_type": "generated_reference",
            "source_asset_id": ref_id,
            "local_path": p.relative_to(project_root.resolve()).as_posix(),
            "sha256": sha256_file(p),
            "file_size_bytes": p.stat().st_size,
            "width": width,
            "height": height,
            "created_by_frame_extraction": False,
            "in_content_timeline": False,
        }

    if kind == "previous_asset_frame":
        prev_id = str(continuity.get("previous_asset_id", ""))
        source = validate_success_artifact(source_artifact, run_id=run_id, asset_id=prev_id, kind="video", project_root=project_root)
        duration_ms = int(source_artifact.get("duration_ms") or 0)
        if duration_ms <= 150:
            raise RuntimeError("PREVIOUS_ASSET_DURATION_TOO_SHORT")
        extract_ms = duration_ms - 150
        out_dir = project_root.resolve() / "runs" / run_id / "video-production" / "execution" / task["asset_id"] / "references"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{prev_id}-end-minus-150ms.png"
        if out.exists():
            raise RuntimeError("REFERENCE_FRAME_ALREADY_EXISTS")
        subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{extract_ms / 1000:.3f}", "-i", str(source), "-frames:v", "1", "-y", str(out)],
            check=True,
        )
        if not out.is_file() or out.stat().st_size <= 0:
            raise RuntimeError("REFERENCE_FRAME_EXTRACTION_FAILED")
        width, height = _probe_image(out)
        return {
            "schema_version": 1,
            "run_id": run_id,
            "dependent_asset_id": task["asset_id"],
            "source_type": "previous_asset_frame",
            "source_asset_id": prev_id,
            "source_video_sha256": source_artifact["sha256"],
            "extraction_offset_ms": extract_ms,
            "extraction_rule": "duration_ms-150",
            "local_path": out.relative_to(project_root.resolve()).as_posix(),
            "sha256": sha256_file(out),
            "file_size_bytes": out.stat().st_size,
            "width": width,
            "height": height,
            "created_by_frame_extraction": True,
            "in_content_timeline": False,
        }

    raise RuntimeError("I2V_REFERENCE_REQUIRED")
