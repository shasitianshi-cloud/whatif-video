from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "video-production" / "src"
sys.path.insert(0, str(SRC))

from render_final_video import render_final_video  # noqa: E402

RUN_ID = "render-final-video-regression-v1"
RUN_ROOT = ROOT / "runs" / RUN_ID


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)


def main() -> None:
    shutil.rmtree(RUN_ROOT, ignore_errors=True)
    try:
        media = RUN_ROOT / "video-production" / "fixture-media"
        render = RUN_ROOT / "video-production" / "render"
        media.mkdir(parents=True)
        render.mkdir(parents=True)
        video = media / "visual.mp4"
        audio = media / "narration.wav"
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
            "-i", "color=c=black:s=1280x720:r=30:d=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(video),
        ])
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
            "-i", "sine=frequency=440:sample_rate=48000:duration=2",
            "-c:a", "pcm_s16le", "-y", str(audio),
        ])
        plan = {
            "schema_version": 1,
            "run_id": RUN_ID,
            "composition": {"width": 1280, "height": 720, "duration_ms": 2000},
            "layers": [{
                "type": "video",
                "treatment": "direct_video",
                "fit": "cover",
                "trim_mode": "deterministic",
                "asset_id": "visual-1",
                "local_path": video.relative_to(ROOT).as_posix(),
                "sha256": sha(video),
                "start_ms": 0,
                "duration_ms": 2000,
                "end_ms": 2000,
                "segment_id": "seg-001",
            }],
            "audio": [{
                "type": "audio",
                "asset_id": "audio-seg-001",
                "local_path": audio.relative_to(ROOT).as_posix(),
                "sha256": sha(audio),
                "start_ms": 0,
                "duration_ms": 2000,
                "end_ms": 2000,
                "segment_id": "seg-001",
            }],
            "subtitles": [{
                "type": "subtitle",
                "segment_id": "seg-001",
                "text": "最终渲染回归测试。",
                "start_ms": 0,
                "end_ms": 2000,
                "primary_color": "white",
                "font_family": "Noto Sans CJK SC",
            }],
            "identity": {"render_input_sha256": "fixture", "asset_manifest_sha256": "fixture"},
        }
        plan_path = render / "render-plan.json"
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        closure = {
            "schema_version": 1,
            "run_id": RUN_ID,
            "status": "READY_FOR_HYPERFRAMES_RENDER",
            "render_plan": plan_path.relative_to(ROOT).as_posix(),
            "render_plan_sha256": sha(plan_path),
            "provider_generation_executed": False,
            "creative_replanning_performed": False,
            "latest_discovery_used": False,
        }
        (render / "render-closure-gate.json").write_text(
            json.dumps(closure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        gate = render_final_video(RUN_ID)
        assert gate["gate"] == "FINAL_VIDEO_GATE"
        assert gate["status"] == "PASS"
        assert gate["width"] == 1280
        assert gate["height"] == 720
        assert gate["audio_track_present"] is True
        assert abs(gate["duration_ms"] - 2000) <= gate["duration_tolerance_ms"]
        assert gate["provider_generation_executed_during_render"] is False
        assert gate["creative_replanning_performed_during_render"] is False
        assert gate["latest_discovery_used"] is False
        final = ROOT / gate["artifact"]
        assert final.is_file() and final.stat().st_size > 0
        assert gate["sha256"] == sha(final)
        print("RENDER_FINAL_VIDEO_RECOVERY_REGRESSION=PASS")
        print("FINAL_VIDEO_GATE=PASS")
        print("PROVIDER_GENERATION_EXECUTED_DURING_RENDER=false")
        print("LATEST_DISCOVERY_USED=false")
    finally:
        shutil.rmtree(RUN_ROOT, ignore_errors=True)


if __name__ == "__main__":
    main()
