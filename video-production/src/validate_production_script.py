"""Fail-closed validator for the reconstructed canonical Production Script contract."""
from __future__ import annotations

FORBIDDEN_VISUAL_TOKENS = (
    "subtitle", "字幕", "title", "标题", "编号", "角标", "箭头",
    "camera icon", "相机图标", "infographic", "信息图", "UI", "运镜说明"
)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _prompt_visual_purity(prompt: str) -> bool:
    low = prompt.lower()
    return not any(token.lower() in low for token in FORBIDDEN_VISUAL_TOKENS)


def validate_production_script(script: dict, narration_manifest: dict | None = None) -> None:
    _require(script.get("schema_version") == 1, "PRODUCTION_SCRIPT_SCHEMA_VALID=false")
    _require(bool(script.get("run_id")), "PRODUCTION_SCRIPT_SCHEMA_VALID=false")
    _require(script.get("recovery_schema_reconstructed") is True, "RECOVERY_SCHEMA_RECONSTRUCTED_REQUIRED")
    _require(script.get("historical_schema_byte_identical") is False, "HISTORICAL_SCHEMA_IDENTITY_MUST_NOT_BE_CLAIMED")
    _require(script.get("downstream_creative_replanning_required") is False, "DOWNSTREAM_CREATIVE_REPLANNING_REQUIRED")

    segments = script.get("segments")
    _require(isinstance(segments, list) and segments, "PRODUCTION_SCRIPT_SCHEMA_VALID=false")
    seen_segments: set[str] = set()
    seen_assets: set[str] = set()
    narration = None
    if narration_manifest is not None:
        _require(narration_manifest.get("run_id") == script["run_id"], "CROSS_RUN_PRODUCTION_SCRIPT_FORBIDDEN")
        narration = {x["segment_id"]: x for x in narration_manifest.get("segments", [])}

    for segment in segments:
        sid = str(segment.get("segment_id", "")).strip()
        _require(bool(sid) and sid not in seen_segments, "DUPLICATE_OR_MISSING_SEGMENT_ID")
        seen_segments.add(sid)
        _require(bool(str(segment.get("audio_asset_id", "")).strip()), "AUDIO_ASSET_ID_REQUIRED")
        visuals = segment.get("visual_assets")
        _require(isinstance(visuals, list) and visuals, "VISUAL_ASSET_REQUIRED")
        expected_duration = None
        if narration is not None:
            _require(sid in narration, "MISSING_NARRATION_SEGMENT")
            expected_duration = int(narration[sid].get("duration_ms") or 0)
            _require(expected_duration > 0, "NARRATION_DURATION_REQUIRED")

        cursor = 0
        for visual in visuals:
            aid = str(visual.get("asset_id", "")).strip()
            _require(bool(aid) and aid not in seen_assets, "DUPLICATE_OR_MISSING_ASSET_ID")
            seen_assets.add(aid)
            _require(bool(str(visual.get("visual_intent", "")).strip()), "VISUAL_INTENT_REQUIRED")
            _require(bool(str(visual.get("scene", "")).strip()), "SCENE_REQUIRED")
            strategy = visual.get("asset_strategy")
            treatment = visual.get("render_treatment")
            _require(strategy in {"image", "image_motion", "generated_video"}, "UNSUPPORTED_ASSET_STRATEGY")
            expected_treatment = {
                "image": "static_image",
                "image_motion": "image_motion",
                "generated_video": "direct_video",
            }[strategy]
            _require(treatment == expected_treatment, "ASSET_STRATEGY_RENDER_TREATMENT_MISMATCH")
            route = visual.get("generation_route")
            if strategy in {"image", "image_motion"}:
                _require(route == "gpt-image-2", "IMAGE_MUST_DISPATCH_IMAGE_GENERATION")
            else:
                _require(route == "happyhorse", "GENERATED_VIDEO_MUST_DISPATCH_HAPPYHORSE")
            prompt = str(visual.get("prompt", "")).strip()
            _require(bool(prompt), "VISUAL_PROMPT_REQUIRED")
            _require(_prompt_visual_purity(prompt), "VIDEO_BOUND_VISUAL_PURITY=false")
            start = visual.get("start_offset_ms")
            duration = visual.get("duration_ms")
            _require(isinstance(start, int) and isinstance(duration, int) and duration > 0, "MISSING_VISUAL_TIMING_CONTRACT")
            _require(start == cursor, "TIMELINE_DISORDER")
            cursor += duration
            _require(visual.get("transition_intent") in {"continue_scene", "cut"}, "TRANSITION_INTENT_REQUIRED")

            continuity = visual.get("continuity", {"kind": "none"})
            kind = continuity.get("kind")
            _require(kind in {"none", "previous_asset_frame", "generated_reference"}, "INVALID_CONTINUITY_CONTRACT")
            if kind == "previous_asset_frame":
                _require(bool(str(continuity.get("previous_asset_id", "")).strip()), "PREVIOUS_ASSET_ID_REQUIRED")
                _require(visual.get("generation_mode") == "I2V", "PREVIOUS_FRAME_REQUIRES_I2V")
            elif kind == "generated_reference":
                _require(bool(str(continuity.get("reference_asset_id", "")).strip()), "REFERENCE_ASSET_ID_REQUIRED")
                _require(visual.get("generation_mode") in {"I2V", "R2V"}, "GENERATED_REFERENCE_REQUIRES_I2V_OR_R2V")
            elif strategy == "generated_video":
                _require(visual.get("generation_mode") == "T2V", "NO_CONTINUITY_GENERATED_VIDEO_REQUIRES_T2V")

            if strategy == "image_motion":
                _require(bool(str(visual.get("motion_intent", "")).strip()), "MOTION_INTENT_REQUIRED")
                params = visual.get("motion_parameters")
                if params is not None:
                    _require(isinstance(params, dict) and isinstance(params.get("from"), dict) and isinstance(params.get("to"), dict), "INVALID_MOTION_PARAMETERS")

        if len(visuals) > 1:
            _require(all(v.get("duration_ms") is not None for v in visuals), "MISSING_VISUAL_TIMING_CONTRACT")
        if expected_duration is not None:
            _require(cursor == expected_duration, "VISUAL_COVERAGE_MISMATCH")

    if narration is not None:
        _require(list(narration) == [x["segment_id"] for x in segments], "NARRATION_SEGMENT_COVERAGE_COMPLETE=false")

    cover = script.get("cover")
    if cover is not None:
        _require(cover.get("in_content_timeline") is False, "COVER_MUST_NOT_ENTER_CONTENT_TIMELINE")
        _require(bool(str(cover.get("asset_id", "")).strip()), "COVER_ASSET_ID_REQUIRED")
        _require(_prompt_visual_purity(str(cover.get("prompt", ""))), "VIDEO_BOUND_VISUAL_PURITY=false")
