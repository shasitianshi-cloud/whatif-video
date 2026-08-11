"""Deterministic Production Script -> Asset Dispatch projection for recovery V1."""
from __future__ import annotations


def _task_id(asset_id: str) -> str:
    return f"dispatch-{asset_id}"


def build_asset_dispatch(production_script: dict) -> dict:
    run_id = str(production_script.get("run_id", "")).strip()
    if not run_id:
        raise RuntimeError("run_id required")
    if production_script.get("downstream_creative_replanning_required") is not False:
        raise RuntimeError("DOWNSTREAM_CREATIVE_REPLANNING_REQUIRED")

    tasks: list[dict] = []
    seen: set[str] = set()

    def add(task: dict) -> None:
        aid = task["asset_id"]
        if aid in seen:
            raise RuntimeError("duplicate dispatch asset identity")
        seen.add(aid)
        tasks.append(task)

    for ref in production_script.get("execution_references", []):
        if ref.get("kind") != "generated_reference" or ref.get("generation_route") != "gpt-image-2":
            raise RuntimeError("INVALID_EXECUTION_REFERENCE_CONTRACT")
        if ref.get("in_content_timeline") is not False:
            raise RuntimeError("EXECUTION_REFERENCE_NOT_AUTOMATIC_RENDER_ASSET")
        aid = str(ref.get("asset_id", "")).strip()
        add({
            "task_id": _task_id(aid),
            "run_id": run_id,
            "asset_id": aid,
            "role": "execution_reference",
            "generation_route": "gpt-image-2",
            "expected_asset_kind": "image",
            "prompt": ref["prompt"],
            "in_content_timeline": False,
        })

    for segment in production_script.get("segments", []):
        sid = segment.get("segment_id")
        for visual in segment.get("visual_assets", []):
            aid = str(visual.get("asset_id", "")).strip()
            route = visual.get("generation_route")
            strategy = visual.get("asset_strategy")
            if strategy in {"image", "image_motion"}:
                if route != "gpt-image-2":
                    raise RuntimeError("IMAGE_MUST_DISPATCH_IMAGE_GENERATION")
                expected_kind = "image"
            elif strategy == "generated_video":
                if route != "happyhorse":
                    raise RuntimeError("GENERATED_VIDEO_MUST_DISPATCH_HAPPYHORSE")
                expected_kind = "video"
            else:
                raise RuntimeError("UNSUPPORTED_ASSET_STRATEGY")

            task = {
                "task_id": _task_id(aid),
                "run_id": run_id,
                "asset_id": aid,
                "role": "content_visual",
                "generation_route": route,
                "expected_asset_kind": expected_kind,
                "prompt": visual["prompt"],
                "duration_ms": int(visual["duration_ms"]),
                "segment_id": sid,
                "render_treatment": visual["render_treatment"],
                "continuity": dict(visual.get("continuity", {"kind": "none"})),
                "in_content_timeline": True,
            }
            if visual.get("generation_mode") is not None:
                task["generation_mode"] = visual["generation_mode"]
            if visual.get("motion_intent") is not None:
                task["motion_intent"] = visual["motion_intent"]
            if isinstance(visual.get("motion_parameters"), dict):
                task["motion_parameters"] = dict(visual["motion_parameters"])
            add(task)

    cover = production_script.get("cover")
    if cover is not None:
        if cover.get("in_content_timeline") is not False:
            raise RuntimeError("COVER_MUST_NOT_ENTER_CONTENT_TIMELINE")
        aid = str(cover.get("asset_id", "")).strip()
        add({
            "task_id": _task_id(aid),
            "run_id": run_id,
            "asset_id": aid,
            "role": "cover",
            "generation_route": "gpt-image-2",
            "expected_asset_kind": "image",
            "prompt": cover["prompt"],
            "in_content_timeline": False,
        })

    return {
        "schema_version": 1,
        "run_id": run_id,
        "recovery_schema_reconstructed": True,
        "creative_replanning": False,
        "tasks": tasks,
    }


def validate_asset_dispatch(dispatch: dict) -> None:
    if dispatch.get("schema_version") != 1 or not dispatch.get("run_id"):
        raise RuntimeError("ASSET_DISPATCH_SCHEMA_VALID=false")
    if dispatch.get("creative_replanning") is not False:
        raise RuntimeError("ASSET_DISPATCH_SCHEMA_VALID=false")
    seen = set()
    for task in dispatch.get("tasks", []):
        if task.get("run_id") != dispatch["run_id"]:
            raise RuntimeError("CROSS_RUN_DISPATCH_FORBIDDEN")
        aid = task.get("asset_id")
        if not aid or aid in seen:
            raise RuntimeError("ASSET_DISPATCH_SCHEMA_VALID=false")
        seen.add(aid)
        route = task.get("generation_route")
        kind = task.get("expected_asset_kind")
        if route == "gpt-image-2" and kind != "image":
            raise RuntimeError("ASSET_DISPATCH_SCHEMA_VALID=false")
        if route == "happyhorse" and kind != "video":
            raise RuntimeError("ASSET_DISPATCH_SCHEMA_VALID=false")
        if task.get("role") in {"execution_reference", "cover"} and task.get("in_content_timeline") is not False:
            raise RuntimeError("ASSET_DISPATCH_SCHEMA_VALID=false")
