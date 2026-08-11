"""Lower normalized assets + frozen production timing into provider-independent Render Input."""
from __future__ import annotations


def _asset_index(manifest: dict) -> dict[str, dict]:
    return {x["asset_id"]: x for x in manifest["assets"]}


def build_render_input(*, run_id: str, asset_manifest: dict, production_script: dict, narration_manifest: dict) -> dict:
    if asset_manifest.get("run_id") != run_id or production_script.get("run_id") != run_id or narration_manifest.get("run_id") != run_id:
        raise RuntimeError("CROSS_RUN_PRODUCTION_RENDER_FORBIDDEN")
    assets = _asset_index(asset_manifest)
    narration = {x["segment_id"]: x for x in narration_manifest.get("segments", [])}
    script_segments = production_script.get("segments", [])
    if not script_segments:
        raise RuntimeError("Production Script missing")
    timeline = []
    subtitles = []
    cursor = 0
    seen_segments = set()
    for segment in script_segments:
        sid = segment.get("segment_id")
        if not sid or sid in seen_segments:
            raise RuntimeError("duplicate timeline identity")
        seen_segments.add(sid)
        narr = narration.get(sid)
        if not narr:
            raise RuntimeError(f"missing narration segment: {sid}")
        duration = int(narr.get("duration_ms") or 0)
        if duration <= 0:
            raise RuntimeError(f"missing required duration: {sid}")
        audio_id = str(segment.get("audio_asset_id") or f"audio-{sid}")
        audio = assets.get(audio_id)
        if not audio or audio["asset_kind"] != "audio":
            raise RuntimeError(f"audio missing: {sid}")
        visuals = segment.get("visual_assets")
        if not isinstance(visuals, list) or not visuals:
            raise RuntimeError(f"asset reference missing: {sid}")
        projected = []
        visual_total = 0
        for v in visuals:
            asset_id = v.get("asset_id")
            a = assets.get(asset_id)
            if not a or not a.get("in_content_timeline"):
                raise RuntimeError(f"asset reference missing: {asset_id}")
            treatment = v.get("render_treatment")
            if treatment not in {"direct_video", "image_motion", "static_image"}:
                raise RuntimeError(f"unsupported render treatment: {treatment}")
            if treatment == "direct_video" and a["asset_kind"] != "video":
                raise RuntimeError("direct_video requires video asset")
            if treatment in {"image_motion", "static_image"} and a["asset_kind"] != "image":
                raise RuntimeError(f"{treatment} requires image asset")
            if len(visuals) == 1 and v.get("duration_ms") is None:
                vdur = duration
            else:
                if v.get("duration_ms") is None:
                    raise RuntimeError("MISSING_VISUAL_TIMING_CONTRACT")
                vdur = int(v["duration_ms"])
            if vdur <= 0:
                raise RuntimeError("missing required duration")
            rel_start = int(v.get("start_offset_ms", visual_total))
            if rel_start != visual_total:
                raise RuntimeError("timeline disorder")
            visual_total = rel_start + vdur
            item = {
                "asset_id": asset_id,
                "render_treatment": treatment,
                "start_ms": cursor + rel_start,
                "duration_ms": vdur,
                "end_ms": cursor + rel_start + vdur,
            }
            if treatment in {"image_motion", "static_image"}:
                item["fit"] = {
                    "mode": "cover_crop",
                    "target_width": 1280,
                    "target_height": 720,
                    "preserve_aspect_ratio": True,
                    "stretch_allowed": False,
                }
            if treatment == "image_motion":
                item["motion_intent"] = str(v.get("motion_intent") or "DEFAULT_DETERMINISTIC")
            projected.append(item)
        if visual_total != duration:
            raise RuntimeError("timeline disorder")
        end = cursor + duration
        timeline.append({
            "segment_id": sid,
            "start_ms": cursor,
            "duration_ms": duration,
            "end_ms": end,
            "visual_assets": projected,
            "audio_asset_id": audio_id,
        })
        subtitles.append({
            "segment_id": sid,
            "text": narr.get("text", ""),
            "start_ms": cursor,
            "end_ms": end,
            "primary_color": "white",
        })
        cursor = end
    narration_ids = [x["segment_id"] for x in narration_manifest.get("segments", [])]
    if narration_ids != [x["segment_id"] for x in timeline]:
        raise RuntimeError("NARRATION_SEGMENT_COVERAGE_COMPLETE=false")
    return {
        "schema_version": 1,
        "run_id": run_id,
        "content_frame": {"width": 1280, "height": 720, "aspect_ratio": "16:9"},
        "timeline": timeline,
        "subtitles": subtitles,
    }


def validate_render_input(render_input: dict) -> None:
    if render_input.get("schema_version") != 1 or not render_input.get("run_id"):
        raise RuntimeError("RENDER_INPUT_SCHEMA_VALID=false")
    frame = render_input.get("content_frame") or {}
    if frame != {"width": 1280, "height": 720, "aspect_ratio": "16:9"}:
        raise RuntimeError("invalid content frame policy")
    timeline = render_input.get("timeline")
    subtitles = render_input.get("subtitles")
    if not isinstance(timeline, list) or not isinstance(subtitles, list) or len(timeline) != len(subtitles):
        raise RuntimeError("RENDER_INPUT_SCHEMA_VALID=false")
    cursor = 0
    ids = []
    for t in timeline:
        if t.get("start_ms") != cursor or t.get("end_ms") != t.get("start_ms") + t.get("duration_ms", 0):
            raise RuntimeError("timeline disorder")
        if not t.get("visual_assets"):
            raise RuntimeError("RENDER_INPUT_SCHEMA_VALID=false")
        cursor = t["end_ms"]
        ids.append(t.get("segment_id"))
    if ids != [s.get("segment_id") for s in subtitles] or len(ids) != len(set(ids)):
        raise RuntimeError("NARRATION_SEGMENT_COVERAGE_COMPLETE=false")
