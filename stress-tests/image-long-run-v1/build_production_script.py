from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "video-production" / "src"))

from validate_production_script import validate_production_script  # noqa: E402

MOTION_PRESETS = {
    "push_in": ({"x_percent": 0, "y_percent": 0, "scale": 1.00}, {"x_percent": 0, "y_percent": 0, "scale": 1.05}),
    "zoom_in": ({"x_percent": 0, "y_percent": 0, "scale": 1.00}, {"x_percent": 0, "y_percent": 0, "scale": 1.05}),
    "zoom_out": ({"x_percent": 0, "y_percent": 0, "scale": 1.06}, {"x_percent": 0, "y_percent": 0, "scale": 1.00}),
    "pull_back": ({"x_percent": 0, "y_percent": 0, "scale": 1.06}, {"x_percent": 0, "y_percent": 0, "scale": 1.00}),
    "pan_left": ({"x_percent": 2, "y_percent": 0, "scale": 1.04}, {"x_percent": -2, "y_percent": 0, "scale": 1.04}),
    "pan_right": ({"x_percent": -2, "y_percent": 0, "scale": 1.04}, {"x_percent": 2, "y_percent": 0, "scale": 1.04}),
    "tilt_up": ({"x_percent": 0, "y_percent": 2, "scale": 1.04}, {"x_percent": 0, "y_percent": -2, "scale": 1.04}),
    "tilt_down": ({"x_percent": 0, "y_percent": -2, "scale": 1.04}, {"x_percent": 0, "y_percent": 2, "scale": 1.04}),
    "gentle_drift": ({"x_percent": -1.5, "y_percent": 0, "scale": 1.03}, {"x_percent": 1.5, "y_percent": 0, "scale": 1.03}),
    "aerial_push": ({"x_percent": 0, "y_percent": 1, "scale": 1.00}, {"x_percent": 0, "y_percent": -1, "scale": 1.05}),
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--fixture", required=True, type=Path)
    args = parser.parse_args()

    run_id = args.run_id
    fixture = read_json(args.fixture)
    narration_path = PROJECT_ROOT / "runs" / run_id / "video-production" / "narration" / "narration-audio-manifest.json"
    narration = read_json(narration_path)
    if fixture.get("run_id") != run_id or narration.get("run_id") != run_id:
        raise RuntimeError("CROSS_RUN_STRESS_INPUT_FORBIDDEN")

    fixture_segments = fixture.get("segments") or []
    narration_segments = narration.get("segments") or []
    if len(fixture_segments) != fixture.get("segment_count") or len(fixture_segments) != 36:
        raise RuntimeError("STRESS_FIXTURE_SEGMENT_COUNT_INVALID")
    if len(narration_segments) != len(fixture_segments):
        raise RuntimeError("STRESS_TTS_SEGMENT_COUNT_DRIFT")

    out_segments = []
    for expected, narr in zip(fixture_segments, narration_segments):
        sid = expected["segment_id"]
        if narr.get("segment_id") != sid:
            raise RuntimeError("STRESS_SEGMENT_ID_DRIFT")
        if str(narr.get("text", "")).strip() != expected["narration"]:
            raise RuntimeError("STRESS_NARRATION_TEXT_DRIFT")
        duration = int(narr.get("duration_ms") or 0)
        if duration <= 0 or duration >= 15000:
            raise RuntimeError("STRESS_SEGMENT_DURATION_INVALID")
        preset = expected["motion_preset"]
        if preset not in MOTION_PRESETS:
            raise RuntimeError("STRESS_MOTION_PRESET_INVALID")
        start, end = MOTION_PRESETS[preset]
        out_segments.append({
            "segment_id": sid,
            "audio_asset_id": f"audio-{sid}",
            "visual_assets": [{
                "asset_id": f"visual-{sid}-01",
                "visual_intent": expected["visual_intent"],
                "scene": expected["scene"],
                "asset_strategy": "image_motion",
                "render_treatment": "image_motion",
                "generation_route": "gpt-image-2",
                "prompt": expected["prompt"],
                "start_offset_ms": 0,
                "duration_ms": duration,
                "transition_intent": "cut",
                "continuity": {"kind": "none"},
                "motion_intent": preset,
                "motion_parameters": {"from": start, "to": end},
            }],
        })

    script = {
        "schema_version": 1,
        "run_id": run_id,
        "recovery_schema_reconstructed": True,
        "historical_schema_byte_identical": False,
        "downstream_creative_replanning_required": False,
        "execution_references": [],
        "segments": out_segments,
    }
    validate_production_script(script, narration)

    root = PROJECT_ROOT / "runs" / run_id / "video-production" / "production-script"
    root.mkdir(parents=True, exist_ok=True)
    script_path = root / "production-script.json"
    script_path.write_text(json.dumps(script, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    gate = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "PASS",
        "sha256": sha256(script_path),
        "source": "frozen_visual_fixture_plus_measured_tts",
        "visual_planner_executed": False,
        "image_only_stress_test": True,
        "segment_count": len(out_segments),
    }
    (root / "production-script-gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(gate, ensure_ascii=False))


if __name__ == "__main__":
    main()
