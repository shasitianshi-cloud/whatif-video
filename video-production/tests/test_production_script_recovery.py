from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from validate_production_script import validate_production_script


def base_script():
    return {
        "schema_version": 1,
        "run_id": "recovery-regression-001",
        "recovery_schema_reconstructed": True,
        "historical_schema_byte_identical": False,
        "downstream_creative_replanning_required": False,
        "execution_references": [
            {
                "asset_id": "ref-001",
                "kind": "generated_reference",
                "role": "execution_reference",
                "generation_route": "gpt-image-2",
                "prompt": "同一人物正面中景，亚洲人物，真实摄影感，干净背景，无额外图形叠加",
                "in_content_timeline": False
            }
        ],
        "segments": [
            {
                "segment_id": "seg-001",
                "audio_asset_id": "audio-seg-001",
                "visual_assets": [
                    {
                        "asset_id": "img-001",
                        "visual_intent": "建立稳定城市全景以承载当前叙事",
                        "scene": "城市天际线",
                        "asset_strategy": "image_motion",
                        "render_treatment": "image_motion",
                        "generation_route": "gpt-image-2",
                        "prompt": "亚洲城市清晨天际线，真实摄影感，稳定宽幅构图，无额外图形叠加",
                        "start_offset_ms": 0,
                        "duration_ms": 4000,
                        "transition_intent": "cut",
                        "continuity": {"kind": "none"},
                        "motion_intent": "slow_push",
                        "motion_parameters": {
                            "from": {"x_percent": 0, "y_percent": 0, "scale": 1.0},
                            "to": {"x_percent": 0, "y_percent": 0, "scale": 1.05}
                        }
                    }
                ]
            },
            {
                "segment_id": "seg-002",
                "audio_asset_id": "audio-seg-002",
                "visual_assets": [
                    {
                        "asset_id": "vid-001",
                        "visual_intent": "表现人物延续同一状态并开始动作",
                        "scene": "室内人物场景",
                        "asset_strategy": "generated_video",
                        "render_treatment": "direct_video",
                        "generation_route": "happyhorse",
                        "generation_mode": "I2V",
                        "prompt": "同一亚洲人物在室内开始向前走动，环境与人物外观保持一致，真实动作",
                        "start_offset_ms": 0,
                        "duration_ms": 3000,
                        "transition_intent": "cut",
                        "continuity": {"kind": "generated_reference", "reference_asset_id": "ref-001"}
                    },
                    {
                        "asset_id": "img-002",
                        "visual_intent": "展示动作后的稳定结果状态",
                        "scene": "同一室内场景",
                        "asset_strategy": "image",
                        "render_treatment": "static_image",
                        "generation_route": "gpt-image-2",
                        "prompt": "同一室内环境的稳定结果状态，真实摄影感，无额外图形叠加",
                        "start_offset_ms": 3000,
                        "duration_ms": 2000,
                        "transition_intent": "continue_scene",
                        "continuity": {"kind": "none"}
                    }
                ]
            }
        ],
        "cover": {
            "asset_id": "cover-001",
            "visual_intent": "独立封面视觉",
            "prompt": "简洁真实摄影场景，主体明确，无额外图形叠加",
            "in_content_timeline": False
        }
    }


def narration():
    return {
        "run_id": "recovery-regression-001",
        "segments": [
            {"segment_id": "seg-001", "text": "一", "duration_ms": 4000},
            {"segment_id": "seg-002", "text": "二", "duration_ms": 5000}
        ]
    }


def expect_block(mutator, code):
    script = base_script()
    mutator(script)
    try:
        validate_production_script(script, narration())
    except RuntimeError as exc:
        assert code in str(exc), (code, str(exc))
    else:
        raise AssertionError(f"expected block: {code}")


def run():
    validate_production_script(base_script(), narration())

    expect_block(lambda s: s["segments"][1]["visual_assets"][1].pop("duration_ms"), "MISSING_VISUAL_TIMING_CONTRACT")
    expect_block(lambda s: s["segments"][0]["visual_assets"][0].update(generation_route="happyhorse"), "IMAGE_MUST_DISPATCH_IMAGE_GENERATION")
    expect_block(lambda s: s["segments"][1]["visual_assets"][0].update(generation_route="gpt-image-2"), "GENERATED_VIDEO_MUST_DISPATCH_HAPPYHORSE")
    expect_block(lambda s: s["segments"][0]["visual_assets"][0].update(prompt="城市画面，添加字幕和标题"), "VIDEO_BOUND_VISUAL_PURITY=false")
    expect_block(lambda s: s["segments"][0]["visual_assets"][0].update(start_offset_ms=1), "TIMELINE_DISORDER")
    expect_block(lambda s: s.update(historical_schema_byte_identical=True), "HISTORICAL_SCHEMA_IDENTITY_MUST_NOT_BE_CLAIMED")
    expect_block(lambda s: s["cover"].update(in_content_timeline=True), "COVER_MUST_NOT_ENTER_CONTENT_TIMELINE")
    expect_block(lambda s: s.update(execution_references=[]), "GENERATED_REFERENCE_NOT_DECLARED")
    expect_block(lambda s: s["execution_references"][0].update(in_content_timeline=True), "EXECUTION_REFERENCE_NOT_AUTOMATIC_RENDER_ASSET")

    print("PRODUCTION_SCRIPT_RECOVERY_SCHEMA_RECONSTRUCTED=true")
    print("HISTORICAL_SCHEMA_BYTE_IDENTICAL=false")
    print("GENERATED_REFERENCE_EXPLICITLY_DECLARED=true")
    print("PRODUCTION_SCRIPT_RECOVERY_REGRESSION=PASS")


if __name__ == "__main__":
    run()
