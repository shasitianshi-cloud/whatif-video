from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from build_asset_dispatch import build_asset_dispatch, validate_asset_dispatch


def script():
    return {
        "schema_version": 1,
        "run_id": "dispatch-recovery-001",
        "recovery_schema_reconstructed": True,
        "historical_schema_byte_identical": False,
        "downstream_creative_replanning_required": False,
        "execution_references": [
            {
                "asset_id": "ref-001",
                "kind": "generated_reference",
                "role": "execution_reference",
                "generation_route": "gpt-image-2",
                "prompt": "亚洲人物中景参考图，真实摄影感，无额外图形叠加",
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
                        "visual_intent": "静态场景",
                        "scene": "城市",
                        "asset_strategy": "image_motion",
                        "render_treatment": "image_motion",
                        "generation_route": "gpt-image-2",
                        "prompt": "城市宽幅真实摄影场景，无额外图形叠加",
                        "start_offset_ms": 0,
                        "duration_ms": 4000,
                        "transition_intent": "cut",
                        "continuity": {"kind": "none"},
                        "motion_intent": "slow_push",
                        "motion_parameters": {
                            "from": {"x_percent": 0, "y_percent": 0, "scale": 1.0},
                            "to": {"x_percent": 0, "y_percent": 0, "scale": 1.04}
                        }
                    },
                    {
                        "asset_id": "vid-001",
                        "visual_intent": "人物真实动作",
                        "scene": "室内",
                        "asset_strategy": "generated_video",
                        "render_treatment": "direct_video",
                        "generation_route": "happyhorse",
                        "generation_mode": "I2V",
                        "prompt": "同一亚洲人物在室内开始行走，真实动作",
                        "start_offset_ms": 4000,
                        "duration_ms": 3000,
                        "transition_intent": "cut",
                        "continuity": {"kind": "generated_reference", "reference_asset_id": "ref-001"}
                    }
                ]
            }
        ],
        "cover": {
            "asset_id": "cover-001",
            "visual_intent": "独立封面",
            "prompt": "独立封面真实摄影场景，无额外图形叠加",
            "in_content_timeline": False
        }
    }


def run():
    dispatch = build_asset_dispatch(script())
    validate_asset_dispatch(dispatch)
    assert [x["asset_id"] for x in dispatch["tasks"]] == ["ref-001", "img-001", "vid-001", "cover-001"]
    assert [x["generation_route"] for x in dispatch["tasks"]] == ["gpt-image-2", "gpt-image-2", "happyhorse", "gpt-image-2"]
    assert dispatch["tasks"][1]["expected_asset_kind"] == "image"
    assert dispatch["tasks"][1]["render_treatment"] == "image_motion"
    assert dispatch["tasks"][2]["generation_mode"] == "I2V"
    assert dispatch["tasks"][2]["continuity"]["reference_asset_id"] == "ref-001"
    assert dispatch["tasks"][0]["in_content_timeline"] is False
    assert dispatch["tasks"][3]["in_content_timeline"] is False
    assert dispatch["creative_replanning"] is False
    print("ASSET_DISPATCH_DETERMINISTIC=true")
    print("IMAGE_MOTION_DISPATCHES_IMAGE_GENERATION=true")
    print("EXECUTION_REFERENCE_DISPATCHED_BEFORE_DEPENDENT_VIDEO=true")
    print("COVER_IN_CONTENT_TIMELINE=false")
    print("ASSET_DISPATCH_RECOVERY_REGRESSION=PASS")


if __name__ == "__main__":
    run()
