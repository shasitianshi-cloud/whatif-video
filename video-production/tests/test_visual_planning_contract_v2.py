from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "video-production" / "src"
sys.path.insert(0, str(SRC))

from validate_production_script_v2 import validate_production_script_v2  # noqa: E402

RUN_ID = "visual-planning-contract-v2-regression"
TITLE = "如果月球永久消失"


def visual_video(i: int, *, hook: bool = False) -> dict:
    item = {
        "asset_id": f"video-{i:03d}",
        "visual_intent": "show real changed-world motion",
        "scene": f"scene-{i:03d}",
        "asset_strategy": "generated_video",
        "render_treatment": "direct_video",
        "generation_route": "happyhorse",
        "generation_mode": "T2V",
        "prompt": "realistic changed-world scene with visible physical motion and no graphic overlays",
        "start_offset_ms": 0,
        "duration_ms": 6000,
        "transition_intent": "cut",
        "continuity": {"kind": "none"},
    }
    if hook:
        item["hook_contract"] = {
            "visible_event": "the changed world is immediately visible",
            "dominant_subject": "moving coastal environment",
            "state_change": "familiar lunar state is absent",
            "real_motion": "water and boats move visibly",
            "camera_relationship": "wide stable view",
            "first_3s_visible_fact": "the changed state is visible from frame one",
            "why_static_is_insufficient": "physical motion carries the hook"
        }
    return item


def visual_image(i: int, start: int, duration: int) -> dict:
    return {
        "asset_id": f"image-{i:03d}-{start}",
        "visual_intent": "show a stable visual state",
        "scene": f"scene-{i:03d}",
        "asset_strategy": "image",
        "render_treatment": "static_image",
        "generation_route": "gpt-image-2",
        "prompt": "realistic wide changed-world scene, clean visual composition, no graphic overlays",
        "start_offset_ms": start,
        "duration_ms": duration,
        "transition_intent": "continue_scene",
        "continuity": {"kind": "none"},
    }


def build_script() -> tuple[dict, dict]:
    segments = []
    manifest_segments = []
    for i in range(1, 9):
        sid = f"seg-{i:03d}"
        if i <= 4:
            visuals = [visual_video(i, hook=(i == 1)), visual_image(i, 6000, 4000)]
        else:
            visuals = [visual_image(i, 0, 10000)]
        segments.append({
            "segment_id": sid,
            "audio_asset_id": f"audio-{sid}",
            "visual_assets": visuals,
        })
        manifest_segments.append({"segment_id": sid, "duration_ms": 10000})
    script = {
        "schema_version": 1,
        "contract_version": 2,
        "run_id": RUN_ID,
        "recovery_schema_reconstructed": True,
        "historical_schema_byte_identical": False,
        "downstream_creative_replanning_required": False,
        "execution_references": [],
        "segments": segments,
        "cover": {
            "asset_id": "cover-main",
            "visual_intent": "theme background",
            "prompt": "Earth in deep space with an empty nearby region, strong simple composition, realistic light",
            "title_text": TITLE,
            "in_content_timeline": False,
        },
    }
    manifest = {"run_id": RUN_ID, "segments": manifest_segments}
    return script, manifest


def must_fail(script: dict, manifest: dict, code: str) -> None:
    try:
        validate_production_script_v2(script, manifest, expected_display_title=TITLE)
    except RuntimeError as exc:
        assert str(exc) == code, (str(exc), code)
    else:
        raise AssertionError(f"expected failure: {code}")


def main() -> None:
    script, manifest = build_script()
    summary = validate_production_script_v2(script, manifest, expected_display_title=TITLE)
    assert summary["happyhorse_required_segments"] == 4
    assert summary["happyhorse_primary_segments"] == 4
    assert summary["happyhorse_primary_segment_ids"] == ["seg-001", "seg-002", "seg-003", "seg-004"]

    ratio_fail = copy.deepcopy(script)
    ratio_fail["segments"][3]["visual_assets"] = [visual_image(4, 0, 10000)]
    must_fail(ratio_fail, manifest, "HAPPYHORSE_RATIO_BELOW_MINIMUM")

    hook_fail = copy.deepcopy(script)
    hook_fail["segments"][0]["visual_assets"][0].pop("hook_contract")
    must_fail(hook_fail, manifest, "FIRST_THREE_SECOND_HOOK_CONTRACT_REQUIRED")

    first_fail = copy.deepcopy(script)
    first_fail["segments"][0]["visual_assets"] = [visual_image(1, 0, 10000)]
    must_fail(first_fail, manifest, "FIRST_SEGMENT_HAPPYHORSE_REQUIRED")

    cover_fail = copy.deepcopy(script)
    cover_fail["cover"]["title_text"] = "月球消失了会怎样"
    must_fail(cover_fail, manifest, "COVER_TITLE_EXACT_SOURCE_REQUIRED")

    print("VISUAL_PLANNING_CONTRACT_V2_REGRESSION=PASS")
    print("HAPPYHORSE_REQUIRED_FOR_8_SEGMENTS=4")
    print("FIRST_SEGMENT_HAPPYHORSE_REQUIRED=true")
    print("COVER_TITLE_EXACT_SOURCE_REQUIRED=true")


if __name__ == "__main__":
    main()
