"""Render a closed current-run plan through the pinned HyperFrames runtime and gate the MP4."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VP_ROOT = PROJECT_ROOT / "video-production"
FORMAT_PATH = VP_ROOT / "config" / "video-format.json"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ffprobe(path: Path) -> dict:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"FINAL_VIDEO_FFPROBE_FAILED:{proc.stderr.strip()[-1000:]}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("FINAL_VIDEO_FFPROBE_JSON_INVALID") from exc


def render_final_video(run_id: str) -> dict:
    run_root = PROJECT_ROOT / "runs" / run_id / "video-production"
    render_root = run_root / "render"
    closure_path = render_root / "render-closure-gate.json"
    plan_path = render_root / "render-plan.json"
    if not closure_path.is_file() or not plan_path.is_file():
        raise RuntimeError("FINAL_RENDER_INPUT_MISSING")
    closure = _read(closure_path)
    if closure.get("run_id") != run_id or closure.get("status") != "READY_FOR_HYPERFRAMES_RENDER":
        raise RuntimeError("RENDER_CLOSURE_GATE_INVALID")
    if closure.get("render_plan_sha256") != _sha(plan_path):
        raise RuntimeError("RENDER_PLAN_SHA256_MISMATCH")
    if closure.get("provider_generation_executed") is not False or closure.get("creative_replanning_performed") is not False:
        raise RuntimeError("RENDER_CLOSURE_BOUNDARY_INVALID")
    render_plan = _read(plan_path)
    if render_plan.get("run_id") != run_id:
        raise RuntimeError("CROSS_RUN_FINAL_RENDER_FORBIDDEN")
    composition = render_plan.get("composition") or {}
    fmt = _read(FORMAT_PATH)["video"]
    if composition.get("width") != fmt["width"] or composition.get("height") != fmt["height"]:
        raise RuntimeError("FINAL_VIDEO_FORMAT_POLICY_MISMATCH")
    expected_duration = int(composition.get("duration_ms") or 0)
    if expected_duration <= 0:
        raise RuntimeError("FINAL_VIDEO_DURATION_REQUIRED")

    composition_dir = render_root / "hyperframes-composition"
    if composition_dir.exists():
        raise RuntimeError("FINAL_RENDER_COMPOSITION_ALREADY_EXISTS")
    builder = VP_ROOT / "src" / "build-hyperframes-composition.js"
    build = subprocess.run(
        ["node", str(builder), str(plan_path), str(PROJECT_ROOT), str(composition_dir)],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    if build.returncode != 0:
        raise RuntimeError(f"HYPERFRAMES_COMPOSITION_BUILD_FAILED:{build.stderr.strip()[-1000:]}")
    index_path = composition_dir / "index.html"
    if not index_path.is_file():
        raise RuntimeError("HYPERFRAMES_COMPOSITION_MISSING")

    final_path = render_root / "final.mp4"
    if final_path.exists():
        raise RuntimeError("FINAL_VIDEO_ALREADY_EXISTS")
    launcher = VP_ROOT / "runtime" / "run-hyperframes-local.sh"
    render_result_path = render_root / "hyperframes-render-result.json"
    render_stderr_path = render_root / "hyperframes-render-stderr.txt"
    composition_arg = index_path.relative_to(PROJECT_ROOT).as_posix()
    output_arg = final_path.relative_to(PROJECT_ROOT).as_posix()
    proc = subprocess.run(
        ["bash", str(launcher), "render", "-c", composition_arg, "-o", output_arg],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    render_result_path.write_text((proc.stdout or "").strip() + "\n", encoding="utf-8")
    render_stderr_path.write_text(proc.stderr or "", encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"HYPERFRAMES_FINAL_RENDER_FAILED:{proc.stderr.strip()[-1000:]}")
    if not final_path.is_file() or final_path.stat().st_size <= 0:
        raise RuntimeError("FINAL_VIDEO_MISSING")

    probe = _ffprobe(final_path)
    streams = probe.get("streams") or []
    video_stream = next((x for x in streams if x.get("codec_type") == "video"), None)
    audio_streams = [x for x in streams if x.get("codec_type") == "audio"]
    if video_stream is None:
        raise RuntimeError("FINAL_VIDEO_STREAM_MISSING")
    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    if width != fmt["width"] or height != fmt["height"]:
        raise RuntimeError("FINAL_VIDEO_DIMENSIONS_INVALID")
    if not audio_streams:
        raise RuntimeError("FINAL_VIDEO_AUDIO_TRACK_MISSING")
    try:
        duration_ms = round(float((probe.get("format") or {})["duration"]) * 1000)
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("FINAL_VIDEO_DURATION_UNREADABLE") from exc
    tolerance_ms = 150
    if abs(duration_ms - expected_duration) > tolerance_ms:
        raise RuntimeError("FINAL_VIDEO_DURATION_MISMATCH")

    ffprobe_path = render_root / "final.ffprobe.json"
    _write(ffprobe_path, probe)
    gate = {
        "schema_version": 1,
        "run_id": run_id,
        "gate": "FINAL_VIDEO_GATE",
        "status": "PASS",
        "artifact": final_path.relative_to(PROJECT_ROOT).as_posix(),
        "sha256": _sha(final_path),
        "file_size_bytes": final_path.stat().st_size,
        "width": width,
        "height": height,
        "duration_ms": duration_ms,
        "expected_duration_ms": expected_duration,
        "duration_tolerance_ms": tolerance_ms,
        "audio_track_present": True,
        "render_plan_sha256": closure["render_plan_sha256"],
        "render_closure_gate_sha256": _sha(closure_path),
        "hyperframes_composition": index_path.relative_to(PROJECT_ROOT).as_posix(),
        "hyperframes_render_result": render_result_path.relative_to(PROJECT_ROOT).as_posix(),
        "hyperframes_render_stderr": render_stderr_path.relative_to(PROJECT_ROOT).as_posix(),
        "ffprobe": ffprobe_path.relative_to(PROJECT_ROOT).as_posix(),
        "provider_generation_executed_during_render": False,
        "creative_replanning_performed_during_render": False,
        "latest_discovery_used": False,
        "recovery_entrypoint_reconstructed": True,
        "historical_entrypoint_byte_identical": False,
    }
    _write(render_root / "final-video-gate.json", gate)
    return gate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    print(json.dumps(render_final_video(args.run_id), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
