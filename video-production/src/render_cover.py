"""Deterministically render the required short-video cover.

The image provider supplies only a pure visual 1280x720 background. Exact title
text is added locally with FFmpeg using the pinned CJK font and global format
policy. No LLM or provider call occurs here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VP_ROOT = PROJECT_ROOT / "video-production"
FORMAT_PATH = VP_ROOT / "config" / "video-format.json"
FONT_PATH = VP_ROOT / "assets" / "fonts" / "NotoSansCJKsc-Regular.otf"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_project_path(relative_path: str) -> Path:
    root = PROJECT_ROOT.resolve()
    path = (PROJECT_ROOT / relative_path).resolve()
    if path != root and root not in path.parents:
        raise RuntimeError("COVER_ASSET_OUTSIDE_PROJECT")
    return path


def _wrap_title(title: str, max_chars_per_line: int = 12) -> str:
    value = title.strip()
    if not value:
        raise RuntimeError("COVER_TITLE_REQUIRED")
    if len(value) <= max_chars_per_line:
        return value
    lines = [value[i:i + max_chars_per_line] for i in range(0, len(value), max_chars_per_line)]
    if len(lines) > 3:
        raise RuntimeError("COVER_TITLE_TOO_LONG")
    return "\n".join(lines)


def _ffprobe(path: Path) -> tuple[int, int]:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "json", str(path)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError("COVER_FFPROBE_FAILED")
    data = json.loads(proc.stdout)
    stream = (data.get("streams") or [{}])[0]
    return int(stream.get("width") or 0), int(stream.get("height") or 0)


def render_cover(run_id: str) -> dict:
    run_root = PROJECT_ROOT / "runs" / run_id / "video-production"
    script_path = run_root / "production-script" / "production-script.json"
    manifest_path = run_root / "render" / "asset-manifest.json"
    if not script_path.is_file() or not manifest_path.is_file():
        raise RuntimeError("COVER_RENDER_INPUT_MISSING")
    if not FONT_PATH.is_file():
        raise RuntimeError("COVER_FONT_MISSING")

    script = _read(script_path)
    manifest = _read(manifest_path)
    if script.get("run_id") != run_id or manifest.get("run_id") != run_id:
        raise RuntimeError("CROSS_RUN_COVER_RENDER_FORBIDDEN")

    cover = script.get("cover")
    if not isinstance(cover, dict) or cover.get("in_content_timeline") is not False:
        raise RuntimeError("COVER_REQUIRED")
    title = str(cover.get("title_text", "")).strip()
    wrapped_title = _wrap_title(title)

    background = next(
        (x for x in manifest.get("assets", []) if x.get("asset_id") == cover.get("asset_id")),
        None,
    )
    if not background or background.get("asset_kind") != "image":
        raise RuntimeError("COVER_BACKGROUND_ASSET_REQUIRED")
    background_path = _safe_project_path(str(background.get("local_path", "")))
    if not background_path.is_file():
        raise RuntimeError("COVER_BACKGROUND_FILE_MISSING")

    policy = _read(FORMAT_PATH)
    canvas = policy["final_canvas"]
    stage = policy["cover"]["background_stage"]
    title_policy = policy["cover"]["title"]
    if (
        canvas["width"] != 1280
        or canvas["height"] != 2276
        or stage != {"x": 0, "y": 778, "width": 1280, "height": 720}
        or title_policy["font_size_px"] != 96
        or title_policy["center_y_px"] != 1887
    ):
        raise RuntimeError("COVER_LAYOUT_POLICY_INVALID")

    render_root = run_root / "render"
    title_file = render_root / "cover-title.txt"
    output_path = render_root / "cover.png"
    gate_path = render_root / "cover-gate.json"
    if output_path.exists() or gate_path.exists():
        raise RuntimeError("COVER_RENDER_ALREADY_EXISTS")

    title_file.write_text(wrapped_title + "\n", encoding="utf-8")
    filter_graph = (
        f"scale={stage['width']}:{stage['height']}:force_original_aspect_ratio=decrease,"
        f"pad={stage['width']}:{stage['height']}:(ow-iw)/2:(oh-ih)/2:black,"
        f"pad={canvas['width']}:{canvas['height']}:{stage['x']}:{stage['y']}:black,"
        "drawtext="
        f"fontfile='{FONT_PATH.as_posix()}':"
        f"textfile='{title_file.as_posix()}':"
        f"fontsize={title_policy['font_size_px']}:"
        "fontcolor=white:"
        "line_spacing=16:"
        "borderw=1:bordercolor=black@0.6:"
        "x=(w-text_w)/2:"
        f"y={title_policy['center_y_px']}-text_h/2"
    )
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", str(background_path),
            "-vf", filter_graph,
            "-frames:v", "1",
            "-y", str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        title_file.unlink(missing_ok=True)
    finally:
        pass
    if proc.returncode != 0:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(f"COVER_RENDER_FAILED:{proc.stderr.strip()[-1000:]}")
    if not output_path.is_file() or output_path.stat().st_size <= 0:
        raise RuntimeError("COVER_OUTPUT_MISSING")

    width, height = _ffprobe(output_path)
    if (width, height) != (canvas["width"], canvas["height"]):
        raise RuntimeError("COVER_DIMENSIONS_INVALID")

    gate = {
        "schema_version": 1,
        "run_id": run_id,
        "gate": "COVER_GATE",
        "status": "PASS",
        "artifact": output_path.relative_to(PROJECT_ROOT).as_posix(),
        "sha256": _sha(output_path),
        "file_size_bytes": output_path.stat().st_size,
        "width": width,
        "height": height,
        "background_asset_id": cover["asset_id"],
        "background_sha256": background.get("sha256"),
        "title_text": title,
        "title_source": "production_script.cover.title_text",
        "font_family": title_policy["font_family"],
        "font_size_px": title_policy["font_size_px"],
        "title_region": title_policy["region"],
        "generated_background_text_used": False,
        "provider_generation_executed_during_cover_render": False,
        "creative_replanning_performed_during_cover_render": False,
    }
    _write(gate_path, gate)
    return gate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    print(json.dumps(render_cover(args.run_id), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
