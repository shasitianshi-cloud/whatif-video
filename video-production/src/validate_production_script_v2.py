"""Global V2 fail-closed Production Script validator.

V1 structural/lineage checks remain intact; this layer adds machine-enforced
quality floors for HappyHorse usage, first-three-second hook, and cover title.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from validate_production_script import validate_production_script

PROJECT_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = PROJECT_ROOT / "video-production" / "config" / "visual-planning-policy.v2.json"

HOOK_FIELDS = (
    "visible_event",
    "dominant_subject",
    "state_change",
    "real_motion",
    "camera_relationship",
    "first_3s_visible_fact",
    "why_static_is_insufficient",
)
COVER_TEXT_PROMPT_MARKERS = ("文字", "文案", "写着", "写上", "text overlay", "title text", "caption text")


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _read_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def validate_production_script_v2(
    script: dict,
    narration_manifest: dict,
    *,
    expected_display_title: str,
) -> dict:
    validate_production_script(script, narration_manifest)

    _require(script.get("contract_version") == 2, "PRODUCTION_SCRIPT_V2_REQUIRED")
    display_title = str(expected_display_title).strip()
    _require(bool(display_title), "COUNTERFACTUAL_DISPLAY_TITLE_REQUIRED")

    policy = _read_policy()
    hh = policy["happyhorse"]
    segments = script["segments"]
    narration_by_id = {x["segment_id"]: x for x in narration_manifest.get("segments", [])}
    _require(len(narration_by_id) == len(segments), "NARRATION_SEGMENT_COVERAGE_COMPLETE=false")

    primary: list[str] = []
    coverage: dict[str, float] = {}
    for segment in segments:
        sid = segment["segment_id"]
        expected_ms = int(narration_by_id[sid]["duration_ms"])
        generated_ms = sum(
            int(v["duration_ms"])
            for v in segment["visual_assets"]
            if v.get("asset_strategy") == "generated_video" and v.get("generation_route") == "happyhorse"
        )
        ratio = generated_ms / expected_ms
        coverage[sid] = ratio
        if ratio > float(hh["primary_segment_threshold_exclusive"]):
            primary.append(sid)

    required = math.ceil(len(segments) * float(hh["minimum_segment_ratio"]))

    first = segments[0]
    _require(first["segment_id"] in primary, "FIRST_SEGMENT_HAPPYHORSE_REQUIRED")
    first_visual = first["visual_assets"][0]
    _require(first_visual.get("start_offset_ms") == 0, "FIRST_THREE_SECOND_HOOK_REQUIRED")
    _require(first_visual.get("asset_strategy") == "generated_video", "FIRST_THREE_SECOND_HOOK_REQUIRED")
    _require(first_visual.get("generation_route") == "happyhorse", "FIRST_THREE_SECOND_HOOK_REQUIRED")
    _require(int(first_visual.get("duration_ms") or 0) >= 3000, "FIRST_THREE_SECOND_HOOK_REQUIRED")
    hook = first_visual.get("hook_contract")
    _require(isinstance(hook, dict), "FIRST_THREE_SECOND_HOOK_CONTRACT_REQUIRED")
    for field in HOOK_FIELDS:
        _require(bool(str(hook.get(field, "")).strip()), "FIRST_THREE_SECOND_HOOK_CONTRACT_REQUIRED")

    _require(len(primary) >= required, "HAPPYHORSE_RATIO_BELOW_MINIMUM")

    cover = script.get("cover")
    _require(isinstance(cover, dict), "COVER_REQUIRED")
    _require(cover.get("in_content_timeline") is False, "COVER_MUST_NOT_ENTER_CONTENT_TIMELINE")
    _require(str(cover.get("title_text", "")).strip() == display_title, "COVER_TITLE_EXACT_SOURCE_REQUIRED")
    prompt = str(cover.get("prompt", ""))
    _require(display_title not in prompt, "GENERATED_COVER_TEXT_FORBIDDEN")
    low = prompt.lower()
    _require(not any(marker.lower() in low for marker in COVER_TEXT_PROMPT_MARKERS), "GENERATED_COVER_TEXT_FORBIDDEN")

    return {
        "visual_planning_policy_id": policy["policy_id"],
        "segment_count": len(segments),
        "happyhorse_required_segments": required,
        "happyhorse_primary_segments": len(primary),
        "happyhorse_primary_segment_ids": primary,
        "happyhorse_coverage_ratio_by_segment": coverage,
        "first_segment_happyhorse_primary": True,
        "first_three_second_hook_contract": "PASS",
        "cover_required": True,
        "cover_title_exact": True,
    }
