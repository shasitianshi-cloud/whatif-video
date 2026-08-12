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

from render_cover import render_cover  # noqa: E402

RUN_ID = "cover-render-regression-v2"
RUN_ROOT = ROOT / "runs" / RUN_ID
TITLE = "如果月球永久消失"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    shutil.rmtree(RUN_ROOT, ignore_errors=True)
    try:
        execution = RUN_ROOT / "video-production" / "execution" / "cover-main"
        ps_root = RUN_ROOT / "video-production" / "production-script"
        render_root = RUN_ROOT / "video-production" / "render"
        execution.mkdir(parents=True)
        ps_root.mkdir(parents=True)
        render_root.mkdir(parents=True)
        background = execution / "cover-main.png"
        proc = subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=0x101820:s=1280x720",
            "-frames:v", "1", "-y", str(background)
        ], capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr)

        script = {
            "run_id": RUN_ID,
            "cover": {
                "asset_id": "cover-main",
                "visual_intent": "moonless Earth theme background",
                "prompt": "Earth in space with empty nearby region",
                "title_text": TITLE,
                "in_content_timeline": False,
            },
        }
        manifest = {
            "run_id": RUN_ID,
            "assets": [{
                "run_id": RUN_ID,
                "asset_id": "cover-main",
                "asset_kind": "image",
                "role": "cover",
                "local_path": background.relative_to(ROOT).as_posix(),
                "sha256": sha(background),
                "in_content_timeline": False,
            }],
        }
        (ps_root / "production-script.json").write_text(json.dumps(script, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (render_root / "asset-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        gate = render_cover(RUN_ID)
        assert gate["status"] == "PASS"
        assert gate["width"] == 1280
        assert gate["height"] == 2276
        assert gate["title_text"] == TITLE
        assert gate["font_size_px"] == 96
        assert gate["title_region"] == "bottom_black_bar"
        assert gate["generated_background_text_used"] is False
        assert gate["provider_generation_executed_during_cover_render"] is False
        cover = ROOT / gate["artifact"]
        assert cover.is_file() and cover.stat().st_size > 0
        assert gate["sha256"] == sha(cover)
        print("COVER_RENDER_V2_REGRESSION=PASS")
        print("COVER_CANVAS=1280x2276")
        print("COVER_TITLE_FONT_SIZE=96")
        print("COVER_TITLE_EXACT=true")
    finally:
        shutil.rmtree(RUN_ROOT, ignore_errors=True)


if __name__ == "__main__":
    main()
