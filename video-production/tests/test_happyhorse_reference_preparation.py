from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from prepare_happyhorse_reference import prepare_reference


def sh(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        media = root / "runs/r1/source"
        media.mkdir(parents=True)
        video = media / "prior.mp4"
        image = media / "ref.png"
        subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","testsrc=size=1280x720:rate=30","-t","1","-pix_fmt","yuv420p",str(video)],check=True)
        subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","color=c=black:s=1280x720","-frames:v","1",str(image)],check=True)

        prior = {"status":"SUCCESS","run_id":"r1","asset_id":"vid-prev","asset_kind":"video","local_path":"runs/r1/source/prior.mp4","sha256":sh(video),"duration_ms":1000}
        task = {"run_id":"r1","asset_id":"vid-next","generation_route":"happyhorse","generation_mode":"I2V","continuity":{"kind":"previous_asset_frame","previous_asset_id":"vid-prev"}}
        out = prepare_reference(task, prior, root)
        assert out["source_type"] == "previous_asset_frame"
        assert out["extraction_offset_ms"] == 850
        assert out["width"] == 1280 and out["height"] == 720
        assert out["created_by_frame_extraction"] is True
        assert out["in_content_timeline"] is False
        assert (root / out["local_path"]).is_file()

        ref_artifact = {"status":"SUCCESS","run_id":"r1","asset_id":"ref-001","asset_kind":"image","local_path":"runs/r1/source/ref.png","sha256":sh(image)}
        task2 = {"run_id":"r1","asset_id":"vid-ref","generation_route":"happyhorse","generation_mode":"I2V","continuity":{"kind":"generated_reference","reference_asset_id":"ref-001"}}
        out2 = prepare_reference(task2, ref_artifact, root)
        assert out2["source_type"] == "generated_reference"
        assert out2["created_by_frame_extraction"] is False
        assert out2["sha256"] == sh(image)

        bad = dict(ref_artifact, run_id="other")
        try:
            prepare_reference(task2, bad, root)
        except RuntimeError as e:
            assert "CONTINUITY_CROSS_RUN_FORBIDDEN" in str(e)
        else:
            raise AssertionError("cross-run reference must block")

    print("PREVIOUS_ASSET_FRAME_OFFSET=duration_ms-150")
    print("CONTINUITY_SAME_RUN_ONLY=true")
    print("GENERATED_REFERENCE_REGENERATION=false")
    print("EXECUTION_REFERENCE_IN_CONTENT_TIMELINE=false")
    print("HAPPYHORSE_REFERENCE_PREPARATION_REGRESSION=PASS")

if __name__ == "__main__":
    run()
