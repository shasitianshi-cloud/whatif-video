"""Deterministic normalized Asset Manifest builder for the frozen video-production contract."""
from __future__ import annotations

import hashlib
from pathlib import Path

ALLOWED_KINDS = {"video", "image", "audio"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_asset(*, run_id: str, item: dict, project_root: Path) -> dict:
    if item.get("run_id") != run_id:
        raise RuntimeError("CROSS_RUN_PRODUCTION_RENDER_FORBIDDEN")
    asset_id = str(item.get("asset_id", "")).strip()
    if not asset_id:
        raise RuntimeError("missing asset_id")
    kind = item.get("asset_kind")
    if kind not in ALLOWED_KINDS:
        raise RuntimeError(f"unsupported asset_kind: {kind}")
    local_path = str(item.get("local_path", "")).strip()
    if not local_path:
        raise RuntimeError(f"asset reference missing: {asset_id}")
    path = (project_root / local_path).resolve()
    root = project_root.resolve()
    if path != root and root not in path.parents:
        raise RuntimeError(f"asset path outside project: {asset_id}")
    if not path.is_file():
        raise RuntimeError(f"asset reference missing: {asset_id}")
    observed_sha = sha256_file(path)
    expected_sha = str(item.get("sha256", ""))
    if observed_sha != expected_sha:
        raise RuntimeError(f"SHA mismatch: {asset_id}")
    role = str(item.get("role", "")).strip()
    if not role:
        raise RuntimeError(f"missing role: {asset_id}")
    in_timeline = bool(item.get("in_content_timeline", role != "cover"))
    if role == "cover" and in_timeline:
        raise RuntimeError("cover cannot enter content timeline by default")
    out = {
        "run_id": run_id,
        "asset_id": asset_id,
        "asset_kind": kind,
        "role": role,
        "source_artifact_path": str(item.get("source_artifact_path", local_path)),
        "local_path": local_path,
        "sha256": observed_sha,
        "file_size_bytes": path.stat().st_size,
        "width": item.get("width"),
        "height": item.get("height"),
        "duration_ms": item.get("duration_ms"),
        "created_at": str(item.get("created_at", "UNKNOWN_RECOVERED_IDENTITY")),
        "in_content_timeline": in_timeline,
    }
    if item.get("provider_metadata") is not None:
        out["provider_metadata"] = dict(item["provider_metadata"])
    return out


def build_asset_manifest(*, run_id: str, execution_assets: list[dict], narration_assets: list[dict], project_root: Path) -> dict:
    if not run_id:
        raise RuntimeError("run_id required")
    normalized = [normalize_asset(run_id=run_id, item=x, project_root=project_root)
                  for x in [*execution_assets, *narration_assets]]
    ids = [x["asset_id"] for x in normalized]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate asset identity")
    return {"schema_version": 1, "run_id": run_id, "assets": normalized}


def validate_asset_manifest(manifest: dict) -> None:
    if manifest.get("schema_version") != 1 or not manifest.get("run_id"):
        raise RuntimeError("ASSET_MANIFEST_SCHEMA_VALID=false")
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        raise RuntimeError("ASSET_MANIFEST_SCHEMA_VALID=false")
    seen = set()
    for a in assets:
        required = {"run_id", "asset_id", "asset_kind", "role", "source_artifact_path", "local_path",
                    "sha256", "file_size_bytes", "width", "height", "duration_ms", "created_at", "in_content_timeline"}
        if not required.issubset(a) or a["asset_kind"] not in ALLOWED_KINDS:
            raise RuntimeError("ASSET_MANIFEST_SCHEMA_VALID=false")
        if a["run_id"] != manifest["run_id"] or a["asset_id"] in seen:
            raise RuntimeError("ASSET_MANIFEST_SCHEMA_VALID=false")
        seen.add(a["asset_id"])
        if a["role"] == "cover" and a["in_content_timeline"]:
            raise RuntimeError("ASSET_MANIFEST_SCHEMA_VALID=false")
