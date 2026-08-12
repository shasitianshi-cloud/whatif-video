"""Dynamic production narration entrypoint reconstructed from frozen runtime contracts.

This module deliberately does not modify or reuse the historical 10-segment probe entrypoint.
Historical byte identity is not claimed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from orchestrator import enforce_narration_duration, narration_completeness_gate, verify_upstream_freeze
from segment_video_master import read_canonical_text, segment_text, verify_lossless
from tts_adapter import VolcengineTTSAdapter

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VIDEO_PRODUCTION_ROOT = PROJECT_ROOT / "video-production"
TTS_CONFIG_PATH = VIDEO_PRODUCTION_ROOT / "config/tts.json"
# UTF-8 code points may occupy up to 4 bytes. This conservative character
# ceiling guarantees an initially segmented unit cannot exceed the frozen
# provider limit solely because of multibyte Unicode.
SAFE_INITIAL_CHARACTER_LIMIT = 256


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _paths(run_id: str) -> tuple[Path, Path, Path, Path]:
    narration = PROJECT_ROOT / "runs" / run_id / "video-production" / "narration"
    return narration, narration / "narration-plan.json", narration / "narration-audio-manifest.json", narration / "audio"


def _assert_video_master(run_id: str, source_path: Path, expected_sha256: str) -> tuple[Path, str]:
    expected = (PROJECT_ROOT / "runs" / run_id / "video-master" / "video-master.md").resolve()
    actual = source_path.resolve()
    if actual != expected:
        raise RuntimeError("VIDEO_MASTER_RUN_ID_MISMATCH")
    if not actual.is_file():
        raise RuntimeError("VIDEO_MASTER_NOT_FOUND")
    observed = sha256_file(actual)
    if observed != expected_sha256:
        raise RuntimeError("VIDEO_MASTER_SHA256_MISMATCH")
    gate_path = expected.parent / "video-master-gate.json"
    if not gate_path.is_file():
        raise RuntimeError("VIDEO_MASTER_GATE_MISSING")
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    if gate.get("run_id") != run_id or gate.get("status") != "PASS" or gate.get("sha256") != observed:
        raise RuntimeError("VIDEO_MASTER_GATE_INVALID")
    return actual, observed


def prepare_narration(run_id: str, source_path: Path, expected_sha256: str) -> dict:
    verify_upstream_freeze()
    source, observed_sha = _assert_video_master(run_id, source_path, expected_sha256)
    narration, plan_path, _, _ = _paths(run_id)
    if narration.exists():
        raise RuntimeError("PRODUCTION_NARRATION_ALREADY_EXISTS")
    text = read_canonical_text(source)
    if not text.strip():
        raise RuntimeError("VIDEO_MASTER_EMPTY")
    segments = segment_text(text, max_text_characters=SAFE_INITIAL_CHARACTER_LIMIT)
    lossless = verify_lossless(text, segments)
    if not lossless["segment_reconstruction_match"]:
        raise RuntimeError("NARRATION_SEGMENTATION_NOT_LOSSLESS")
    config = json.loads(TTS_CONFIG_PATH.read_text(encoding="utf-8"))
    max_bytes = int(config["max_text_utf8_bytes"])
    if any(segment.utf8_byte_length > max_bytes for segment in segments):
        raise RuntimeError("NARRATION_SEGMENT_EXCEEDS_TTS_UTF8_LIMIT")
    narration.mkdir(parents=True)
    plan = {
        "schema_version": 1,
        "run_id": run_id,
        "source_video_master_path": source.relative_to(PROJECT_ROOT).as_posix(),
        "source_video_master_sha256": observed_sha,
        "segment_count": len(segments),
        "segment_count_dynamic": True,
        "historical_probe_segment_count_binding": False,
        "recovery_entrypoint_reconstructed": True,
        "historical_entrypoint_byte_identical": False,
        "segmentation": {
            "lossless": True,
            "safe_initial_character_limit": SAFE_INITIAL_CHARACTER_LIMIT,
            "provider_max_text_utf8_bytes": max_bytes,
        },
        "segments": [segment.to_dict() for segment in segments],
    }
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"plan": plan_path, "plan_data": plan}


def _synthesize_one(config: dict, audio_dir: Path, segment: dict, adapter_factory):
    adapter = adapter_factory(config)
    result = adapter.synthesize(segment["text"], audio_dir / f"{segment['segment_id']}.mp3")
    return segment, result


def synthesize_narration(run_id: str, *, adapter_factory=VolcengineTTSAdapter) -> dict:
    observed = verify_upstream_freeze()
    narration, plan_path, manifest_path, audio_dir = _paths(run_id)
    if not plan_path.is_file():
        raise RuntimeError("PRODUCTION_NARRATION_PLAN_MISSING")
    if manifest_path.exists():
        raise RuntimeError("PRODUCTION_NARRATION_MANIFEST_ALREADY_EXISTS")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("run_id") != run_id or plan.get("segment_count_dynamic") is not True:
        raise RuntimeError("PRODUCTION_NARRATION_PLAN_INVALID")
    source_path = PROJECT_ROOT / plan["source_video_master_path"]
    _assert_video_master(run_id, source_path, plan["source_video_master_sha256"])
    config = json.loads(TTS_CONFIG_PATH.read_text(encoding="utf-8"))
    segments = plan.get("segments", [])
    if not segments or plan.get("segment_count") != len(segments):
        raise RuntimeError("PRODUCTION_NARRATION_SEGMENT_COVERAGE_INVALID")
    expected_ids = [f"seg-{i:03d}" for i in range(1, len(segments) + 1)]
    if [x.get("segment_id") for x in segments] != expected_ids:
        raise RuntimeError("PRODUCTION_NARRATION_SEGMENT_ORDER_INVALID")
    audio_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(int(config["concurrency_max"]), len(segments))) as pool:
        futures = [pool.submit(_synthesize_one, config, audio_dir, segment, adapter_factory) for segment in segments]
        for future in as_completed(futures):
            segment, result = future.result()
            results[segment["segment_id"]] = {
                "segment": segment,
                "request_id": result.request_id,
                "audio_path": Path(result.audio_path).relative_to(PROJECT_ROOT).as_posix(),
                "audio_sha256": result.audio_sha256,
                "provider_duration_ms": result.provider_duration_ms,
                "duration_ms": result.measured_duration_ms,
                "provider_log_id": result.provider_log_id,
            }
    manifest_segments = []
    for segment in segments:
        item = results[segment["segment_id"]]
        manifest_segments.append({
            "segment_id": segment["segment_id"],
            "order": segment["order"],
            "text": segment["text"],
            "audio_path": item["audio_path"],
            "audio_sha256": item["audio_sha256"],
            "duration_ms": item["duration_ms"],
            "request_id": item["request_id"],
        })
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "source_video_master_sha256": plan["source_video_master_sha256"],
        "tts_provider": config["provider"],
        "tts_protocol": config["protocol"],
        "resource_id": config["resource_id"],
        "speaker": config["speaker"],
        "audio_format": config["audio_format"],
        "sample_rate": config["sample_rate"],
        "speech_rate": config["speech_rate"],
        "loudness_rate": config["loudness_rate"],
        "concurrency_max": config["concurrency_max"],
        "segment_count": len(manifest_segments),
        "total_duration_ms": sum(x["duration_ms"] for x in manifest_segments),
        "segments": manifest_segments,
        "recovery_entrypoint_reconstructed": True,
        "historical_entrypoint_byte_identical": False,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    gate = narration_completeness_gate(plan, manifest, audio_dir)
    gate.update({
        "run_id": run_id,
        "segment_count_dynamic": True,
        "upstream_freeze_observed": observed,
        "recovery_entrypoint_reconstructed": True,
    })
    gate_path = narration / "narration-completeness-gate.json"
    gate_path.write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence = {
        "run_id": run_id,
        "tts_config_sha256": sha256_file(TTS_CONFIG_PATH),
        "narration_plan_sha256": sha256_file(plan_path),
        "narration_audio_manifest_sha256": sha256_file(manifest_path),
        "upstream_freeze_observed": observed,
        "provider_metadata": [
            {
                "segment_id": key,
                "provider_duration_ms": value["provider_duration_ms"],
                "provider_log_id": value["provider_log_id"],
            }
            for key, value in sorted(results.items())
        ],
        "historical_entrypoint_byte_identical": False,
    }
    (narration / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # The frozen duration policy remains authoritative. This may losslessly
    # replace only oversized units and regenerate only their child audio.
    if gate["narration_completeness_gate"] == "PASS" and any(
        x["duration_ms"] >= 15000 for x in manifest_segments
    ):
        return enforce_narration_duration(run_id)
    return {"manifest": manifest_path, "gate": gate_path, "gate_data": gate}


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument("--video-master", required=True, type=Path)
    prepare.add_argument("--expected-sha256", required=True)
    synth = sub.add_parser("synthesize")
    synth.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare_narration(args.run_id, args.video_master, args.expected_sha256)
    else:
        result = synthesize_narration(args.run_id)
    print(json.dumps({k: v.as_posix() if isinstance(v, Path) else v for k, v in result.items() if not k.endswith("_data")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
