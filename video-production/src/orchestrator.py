"""Frozen narration plan -> V3 probe -> concurrent TTS -> completeness gate."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tts_adapter import VolcengineTTSAdapter


PROJECT_ROOT = Path(__file__).resolve().parents[2]
VIDEO_PRODUCTION_ROOT = PROJECT_ROOT / "video-production"
MAX_NARRATION_SEGMENT_DURATION_MS = 15000
MAX_SPLIT_DEPTH = 3
LOCAL_SPLIT_PUNCTUATION = ("；", "，", "：")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def implementation_digest(directory: Path) -> str:
    rows = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        rows.append(f"{path.relative_to(directory).as_posix()}\t{sha256_file(path)}\n")
    return hashlib.sha256("".join(rows).encode()).hexdigest()


def verify_upstream_freeze() -> dict:
    freeze = json.loads((PROJECT_ROOT / "shared/upstream-freeze-v1.json").read_text())
    observed = {
        "counterfactual_implementation_sha256": implementation_digest(PROJECT_ROOT / "counterfactual-reasoning"),
        "video_master_implementation_sha256": implementation_digest(PROJECT_ROOT / "video-master"),
        "operator_package_sha256": sha256_file(PROJECT_ROOT / "shared/operator-baseline/whatif-minimal-operator-v1-portable.zip"),
    }
    if freeze.get("upstream_freeze_v1") != "ACTIVE" or any(observed[k] != freeze[k] for k in observed):
        raise RuntimeError("UPSTREAM_FREEZE_DRIFT=true")
    return observed


def _paths(run_id: str):
    narration = PROJECT_ROOT / "runs" / run_id / "video-production/narration"
    return narration, narration / "narration-plan.json", narration / "audio"


def create_probe_run(run_id: str, source_plan: Path) -> dict:
    verify_upstream_freeze()
    narration, plan_path, audio_dir = _paths(run_id)
    if narration.exists():
        raise FileExistsError(f"run already exists: {run_id}")
    source = json.loads(source_plan.read_text(encoding="utf-8"))
    if source["segment_count"] != 10:
        raise RuntimeError("SEGMENT_COUNT must remain 10")
    expected_ids = [f"seg-{i:03d}" for i in range(1, 11)]
    if [x["segment_id"] for x in source["segments"]] != expected_ids:
        raise RuntimeError("narration plan segment order changed")
    narration.mkdir(parents=True)
    plan = dict(source)
    plan["run_id"] = run_id
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    config = json.loads((VIDEO_PRODUCTION_ROOT / "config/tts.json").read_text())
    segment = plan["segments"][0]
    result = VolcengineTTSAdapter(config).synthesize(
        segment["text"], audio_dir / f"{segment['segment_id']}.mp3")
    probe = {
        "run_id": run_id, "real_v3_tts_probe": "PASS",
        "segment_id": segment["segment_id"], "request_id": result.request_id,
        "audio_path": Path(result.audio_path).relative_to(PROJECT_ROOT).as_posix(),
        "audio_sha256": result.audio_sha256,
        "duration_ms": result.measured_duration_ms,
        "provider_duration_ms": result.provider_duration_ms,
        "provider_log_id": result.provider_log_id,
        "voice_matches_expected_vivi": None,
        "speech_rate_acceptable": None,
    }
    probe_path = narration / "probe-result.json"
    probe_path.write_text(json.dumps(probe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"probe": probe_path, "audio": Path(result.audio_path)}


def _synthesize_one(config, narration, segment):
    result = VolcengineTTSAdapter(config).synthesize(
        segment["text"], narration / "audio" / f"{segment['segment_id']}.mp3")
    return segment, result


def _child_ids(parent_id: str) -> tuple[str, str]:
    return f"{parent_id}a", f"{parent_id}b"


def split_oversized_unit(parent: dict) -> list[dict]:
    """Losslessly bisect one unit at the preferred punctuation nearest its midpoint."""
    depth = int(parent.get("split_depth", 0))
    if depth >= MAX_SPLIT_DEPTH:
        raise RuntimeError(f"MAX_SPLIT_DEPTH exceeded: {parent['segment_id']}")
    text = parent["text"]
    midpoint = len(text) / 2
    split_at = None
    for punctuation in LOCAL_SPLIT_PUNCTUATION:
        candidates = [i + 1 for i, char in enumerate(text) if char == punctuation]
        if candidates:
            split_at = min(candidates, key=lambda i: (abs(i - midpoint), i))
            break
    if split_at is None or split_at <= 0 or split_at >= len(text):
        raise RuntimeError(f"no allowed natural split point: {parent['segment_id']}")
    left_id, right_id = _child_ids(parent["segment_id"])
    common = {"parent_segment_id": parent["segment_id"], "split_depth": depth + 1}
    children = [
        {"segment_id": left_id, "text": text[:split_at], **common},
        {"segment_id": right_id, "text": text[split_at:], **common},
    ]
    if "source_start" in parent and "source_end" in parent:
        children[0].update(source_start=parent["source_start"], source_end=parent["source_start"] + split_at)
        children[1].update(source_start=parent["source_start"] + split_at, source_end=parent["source_end"])
    for child in children:
        child["utf8_byte_length"] = len(child["text"].encode("utf-8"))
    if "".join(child["text"] for child in children) != text:
        raise AssertionError("CHILD_TEXT_RECONSTRUCTION_MATCH_PARENT=false")
    return children


def enforce_narration_duration(run_id: str) -> dict:
    """Replace only oversized final units; never regenerate already-valid audio."""
    observed = verify_upstream_freeze()
    narration, plan_path, audio_dir = _paths(run_id)
    manifest_path = narration / "narration-audio-manifest.json"
    initial_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    initial_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    config = json.loads((VIDEO_PRODUCTION_ROOT / "config/tts.json").read_text())
    units = copy.deepcopy(initial_plan["segments"])
    artifacts = {x["segment_id"]: copy.deepcopy(x) for x in initial_manifest["segments"]}
    oversized_initial = [x["segment_id"] for x in initial_manifest["segments"]
                         if x["duration_ms"] >= MAX_NARRATION_SEGMENT_DURATION_MS]
    resplit_parents = []
    superseded = []
    max_depth_used = 0
    failure_reason = None

    while True:
        oversized = [u for u in units if artifacts[u["segment_id"]]["duration_ms"] >= MAX_NARRATION_SEGMENT_DURATION_MS]
        if not oversized:
            break
        parent = oversized[0]
        parent_id = parent["segment_id"]
        try:
            children = split_oversized_unit(parent)
        except RuntimeError as exc:
            failure_reason = str(exc)
            break
        resplit_parents.append(parent_id)
        superseded.append(artifacts[parent_id])
        max_depth_used = max(max_depth_used, children[0]["split_depth"])
        with ThreadPoolExecutor(max_workers=min(config["concurrency_max"], len(children))) as pool:
            futures = [pool.submit(_synthesize_one, config, narration, child) for child in children]
            child_artifacts = {}
            for future in as_completed(futures):
                child, result = future.result()
                child_artifacts[child["segment_id"]] = {
                    "segment_id": child["segment_id"], "text": child["text"],
                    "parent_segment_id": child["parent_segment_id"], "split_depth": child["split_depth"],
                    "audio_path": Path(result.audio_path).relative_to(PROJECT_ROOT).as_posix(),
                    "audio_sha256": result.audio_sha256, "duration_ms": result.measured_duration_ms,
                    "request_id": result.request_id,
                }
        index = next(i for i, unit in enumerate(units) if unit["segment_id"] == parent_id)
        units[index:index + 1] = children
        artifacts.pop(parent_id)
        artifacts.update(child_artifacts)

    for order, unit in enumerate(units, 1):
        unit["order"] = order
        artifacts[unit["segment_id"]]["order"] = order
    if "".join(x["text"] for x in units) != "".join(x["text"] for x in initial_plan["segments"]):
        raise AssertionError("final narration text reconstruction failed")

    final_plan = copy.deepcopy(initial_plan)
    final_plan["initial_segment_count"] = initial_plan["segment_count"]
    final_plan["segment_count"] = len(units)
    final_plan["segments"] = units
    final_manifest = copy.deepcopy(initial_manifest)
    final_manifest.update(
        segment_count=len(units), total_duration_ms=sum(artifacts[x["segment_id"]]["duration_ms"] for x in units),
        max_narration_segment_duration_ms=MAX_NARRATION_SEGMENT_DURATION_MS,
        max_split_depth=MAX_SPLIT_DEPTH,
        segments=[artifacts[x["segment_id"]] for x in units],
    )
    if superseded:
        initial_plan_path = narration / "narration-plan.initial.json"
        initial_manifest_path = narration / "narration-audio-manifest.initial.json"
        if not initial_plan_path.exists():
            initial_plan_path.write_text(json.dumps(initial_plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not initial_manifest_path.exists():
            initial_manifest_path.write_text(json.dumps(initial_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (narration / "superseded-parent-audio.json").write_text(
            json.dumps({"status": "SUPERSEDED_BY_DURATION_RESPLIT", "artifacts": superseded}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
    plan_path.write_text(json.dumps(final_plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(final_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    gate = narration_completeness_gate(final_plan, final_manifest, audio_dir)
    gate.update({
        "run_id": run_id,
        "initial_segment_count": initial_plan["segment_count"],
        "final_segment_count": len(units),
        "oversized_initial_segment_ids": oversized_initial,
        "resplit_parent_segment_ids": resplit_parents,
        "max_split_depth_used": max_depth_used,
        "child_text_reconstruction_match_parent": True,
        "upstream_freeze_observed": observed,
        "failure_reason": failure_reason,
        "next_stage_ready": "AV_COMPILER" if gate["narration_completeness_gate"] == "PASS" else False,
    })
    if failure_reason:
        gate["narration_completeness_gate"] = "FAIL"
        gate["next_stage_ready"] = False
    gate_path = narration / "narration-completeness-gate.json"
    gate_path.write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"manifest": manifest_path, "gate": gate_path, "gate_data": gate}


def complete_run(run_id: str) -> dict:
    observed = verify_upstream_freeze()
    narration, plan_path, audio_dir = _paths(run_id)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    probe_path = narration / "probe-result.json"
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    if probe.get("real_v3_tts_probe") != "PASS" or not probe.get("voice_matches_expected_vivi") or not probe.get("speech_rate_acceptable"):
        raise RuntimeError("manual V3 probe acceptance is required")
    config_path = VIDEO_PRODUCTION_ROOT / "config/tts.json"
    config = json.loads(config_path.read_text())
    results = {}
    first = plan["segments"][0]
    results[first["segment_id"]] = {
        "segment": first, "request_id": probe["request_id"],
        "audio_path": probe["audio_path"], "audio_sha256": probe["audio_sha256"],
        "provider_duration_ms": probe["provider_duration_ms"], "duration_ms": probe["duration_ms"],
        "provider_log_id": probe.get("provider_log_id"),
    }
    with ThreadPoolExecutor(max_workers=config["concurrency_max"]) as pool:
        futures = [pool.submit(_synthesize_one, config, narration, s) for s in plan["segments"][1:]]
        for future in as_completed(futures):
            segment, result = future.result()
            results[segment["segment_id"]] = {
                "segment": segment, "request_id": result.request_id,
                "audio_path": Path(result.audio_path).relative_to(PROJECT_ROOT).as_posix(),
                "audio_sha256": result.audio_sha256,
                "provider_duration_ms": result.provider_duration_ms,
                "duration_ms": result.measured_duration_ms,
                "provider_log_id": result.provider_log_id,
            }
    manifest_segments = []
    for segment in plan["segments"]:
        item = results[segment["segment_id"]]
        manifest_segments.append({
            "segment_id": segment["segment_id"], "order": segment["order"],
            "text": segment["text"], "audio_path": item["audio_path"],
            "audio_sha256": item["audio_sha256"], "duration_ms": item["duration_ms"],
            "request_id": item["request_id"],
        })
    manifest = {
        "run_id": run_id, "source_video_master_sha256": plan["source_video_master_sha256"],
        "tts_provider": config["provider"], "tts_protocol": config["protocol"],
        "resource_id": config["resource_id"], "speaker": config["speaker"],
        "audio_format": config["audio_format"], "sample_rate": config["sample_rate"],
        "speech_rate": config["speech_rate"], "loudness_rate": config["loudness_rate"],
        "concurrency_max": config["concurrency_max"], "segment_count": len(manifest_segments),
        "total_duration_ms": sum(x["duration_ms"] for x in manifest_segments),
        "segments": manifest_segments,
    }
    manifest_path = narration / "narration-audio-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    gate = narration_completeness_gate(plan, manifest, audio_dir)
    gate_path = narration / "narration-completeness-gate.json"
    gate_path.write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence = {
        "run_id": run_id, "tts_config_sha256": sha256_file(config_path),
        "narration_plan_sha256": sha256_file(plan_path),
        "narration_audio_manifest_sha256": sha256_file(manifest_path),
        "upstream_freeze_observed": observed,
        "provider_metadata": [{
            "segment_id": key, "provider_duration_ms": value["provider_duration_ms"],
            "provider_log_id": value["provider_log_id"],
        } for key, value in sorted(results.items())],
    }
    (narration / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # The final narration gate reuses valid audio and synthesizes only children
    # of units measured at or above the duration limit.
    return enforce_narration_duration(run_id)


def narration_completeness_gate(plan: dict, manifest: dict, audio_dir: Path) -> dict:
    plan_ids = [x["segment_id"] for x in plan["segments"]]
    manifest_ids = [x["segment_id"] for x in manifest["segments"]]
    # Superseded parent files may remain as evidence, so actual means the final unit set.
    actual_ids = sorted(x for x in plan_ids if (audio_dir / f"{x}.mp3").is_file()
                        and (audio_dir / f"{x}.mp3").stat().st_size > 0)
    duplicates = sorted({x for x in manifest_ids if manifest_ids.count(x) > 1})
    missing = sorted(set(plan_ids) - set(actual_ids))
    unexpected = sorted(set(manifest_ids) - set(plan_ids))
    durations_valid = all(x["duration_ms"] < MAX_NARRATION_SEGMENT_DURATION_MS for x in manifest["segments"])
    max_duration = max((x["duration_ms"] for x in manifest["segments"]), default=0)
    passed = (len(plan_ids) == len(actual_ids) and plan_ids == manifest_ids == actual_ids
              and not missing and not duplicates and not unexpected and durations_valid)
    return {
        "expected_audio_count": len(plan_ids), "actual_audio_count": len(actual_ids),
        "plan_segment_ids": plan_ids, "manifest_segment_ids": manifest_ids,
        "actual_audio_segment_ids": actual_ids, "missing_audio_segment_ids": missing,
        "duplicate_audio_segment_ids": duplicates, "unexpected_audio_segment_ids": unexpected,
        "all_audio_artifacts_present": not missing,
        "max_narration_segment_duration_ms": MAX_NARRATION_SEGMENT_DURATION_MS,
        "max_final_audio_duration_ms": max_duration,
        "all_audio_duration_ms_lt_15000": durations_valid,
        "narration_completeness_gate": "PASS" if passed else "FAIL",
    }


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    probe = sub.add_parser("probe")
    probe.add_argument("--run-id", required=True)
    probe.add_argument("--source-plan", required=True, type=Path)
    complete = sub.add_parser("complete")
    complete.add_argument("--run-id", required=True)
    duration_gate = sub.add_parser("enforce-duration")
    duration_gate.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if args.command == "probe":
        result = create_probe_run(args.run_id, args.source_plan.resolve())
    elif args.command == "complete":
        result = complete_run(args.run_id)
    else:
        result = enforce_narration_duration(args.run_id)
    print(json.dumps({key: value.as_posix() if isinstance(value, Path) else value for key, value in result.items() if key != "manifest_data"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
