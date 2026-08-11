from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from build_asset_manifest import build_asset_manifest, validate_asset_manifest
from build_render_input import build_render_input, validate_render_input


def _write(root: Path, rel: str, data: bytes) -> tuple[str, str]:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return rel, hashlib.sha256(data).hexdigest()


def _asset(run_id: str, asset_id: str, kind: str, role: str, rel: str, sha: str, *, duration=None, timeline=True):
    return {
        "run_id": run_id, "asset_id": asset_id, "asset_kind": kind, "role": role,
        "source_artifact_path": rel, "local_path": rel, "sha256": sha,
        "width": 1280 if kind != "audio" else None,
        "height": 720 if kind != "audio" else None,
        "duration_ms": duration,
        "created_at": "2026-08-11T00:00:00Z", "in_content_timeline": timeline,
    }


def test_normalization_projection_and_boundaries(tmp_path):
    run_id = "production-test-001"
    vrel, vsha = _write(tmp_path, "runs/x/video.mp4", b"video")
    irel, isha = _write(tmp_path, "runs/x/image.png", b"image")
    arel1, asha1 = _write(tmp_path, "runs/x/a1.mp3", b"audio1")
    arel2, asha2 = _write(tmp_path, "runs/x/a2.mp3", b"audio2")
    crel, csha = _write(tmp_path, "runs/x/cover.png", b"cover")
    manifest = build_asset_manifest(
        run_id=run_id, project_root=tmp_path,
        execution_assets=[
            _asset(run_id, "video-1", "video", "content", vrel, vsha, duration=1000),
            _asset(run_id, "image-1", "image", "content", irel, isha),
            _asset(run_id, "cover-1", "image", "cover", crel, csha, timeline=False),
        ],
        narration_assets=[
            _asset(run_id, "audio-seg-001", "audio", "narration", arel1, asha1, duration=1000, timeline=False),
            _asset(run_id, "audio-seg-002", "audio", "narration", arel2, asha2, duration=1000, timeline=False),
        ],
    )
    validate_asset_manifest(manifest)
    assert next(x for x in manifest["assets"] if x["asset_id"] == "image-1")["asset_kind"] == "image"
    assert next(x for x in manifest["assets"] if x["asset_id"] == "cover-1")["in_content_timeline"] is False

    narration = {"run_id": run_id, "segments": [
        {"segment_id": "seg-001", "text": "一", "duration_ms": 1000},
        {"segment_id": "seg-002", "text": "二", "duration_ms": 1000},
    ]}
    production = {"run_id": run_id, "segments": [
        {"segment_id": "seg-001", "audio_asset_id": "audio-seg-001", "visual_assets": [
            {"asset_id": "video-1", "render_treatment": "direct_video"}
        ]},
        {"segment_id": "seg-002", "audio_asset_id": "audio-seg-002", "visual_assets": [
            {"asset_id": "image-1", "render_treatment": "image_motion", "motion_intent": "pan"}
        ]},
    ]}
    render_input = build_render_input(run_id=run_id, asset_manifest=manifest, production_script=production, narration_manifest=narration)
    validate_render_input(render_input)
    assert render_input["timeline"][0]["start_ms"] == 0
    assert render_input["timeline"][1]["start_ms"] == 1000
    assert render_input["timeline"][1]["visual_assets"][0]["render_treatment"] == "image_motion"
    assert render_input["timeline"][1]["visual_assets"][0]["motion_intent"] == "pan"
    assert render_input["timeline"][1]["visual_assets"][0]["fit"]["stretch_allowed"] is False
    assert [x["text"] for x in render_input["subtitles"]] == ["一", "二"]


def test_missing_multi_asset_timing_blocks(tmp_path):
    run_id = "production-test-002"
    rows = []
    for aid in ("i1", "i2"):
        rel, sha = _write(tmp_path, f"{aid}.png", aid.encode())
        rows.append(_asset(run_id, aid, "image", "content", rel, sha))
    rel, sha = _write(tmp_path, "a.mp3", b"a")
    manifest = build_asset_manifest(run_id=run_id, project_root=tmp_path, execution_assets=rows,
        narration_assets=[_asset(run_id, "audio-seg-001", "audio", "narration", rel, sha, duration=1000, timeline=False)])
    narration = {"run_id": run_id, "segments": [{"segment_id": "seg-001", "text": "x", "duration_ms": 1000}]}
    production = {"run_id": run_id, "segments": [{"segment_id": "seg-001", "audio_asset_id": "audio-seg-001",
        "visual_assets": [{"asset_id": "i1", "render_treatment": "static_image"}, {"asset_id": "i2", "render_treatment": "static_image"}]}]}
    try:
        build_render_input(run_id=run_id, asset_manifest=manifest, production_script=production, narration_manifest=narration)
    except RuntimeError as exc:
        assert "MISSING_VISUAL_TIMING_CONTRACT" in str(exc)
    else:
        raise AssertionError("missing explicit multi-asset timing must block")


def test_cross_run_and_sha_mismatch_block(tmp_path):
    rel, sha = _write(tmp_path, "x.png", b"x")
    wrong = _asset("other-run", "x", "image", "content", rel, sha)
    try:
        build_asset_manifest(run_id="run-a", execution_assets=[wrong], narration_assets=[], project_root=tmp_path)
    except RuntimeError as exc:
        assert "CROSS_RUN" in str(exc)
    else:
        raise AssertionError("cross-run must block")
    wrong_sha = _asset("run-a", "x", "image", "content", rel, "0" * 64)
    try:
        build_asset_manifest(run_id="run-a", execution_assets=[wrong_sha], narration_assets=[], project_root=tmp_path)
    except RuntimeError as exc:
        assert "SHA mismatch" in str(exc)
    else:
        raise AssertionError("SHA mismatch must block")
