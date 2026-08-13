from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--contract", type=Path, required=True)
    args = p.parse_args()

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    run_id = contract["run_id"]
    fixed = contract["fixed"]
    variants = contract["variants"]

    fixed_order = [
        fixed["character_identity"],
        fixed["style"],
        fixed["composition"],
        fixed["scene"],
        fixed["constraints"],
    ]
    fixed_text = " ".join(x.strip() for x in fixed_order)

    tasks = []
    compiled = []
    for i, variant in enumerate(variants, start=1):
        variant_id = variant["variant_id"]
        outfit = variant["outfit"].strip()
        prompt = f"{fixed_text} Outfit for this image: {outfit}"
        task_id = f"dispatch-character-{i:02d}-{variant_id}"
        asset_id = f"character-{i:02d}-{variant_id}"
        tasks.append({
            "task_id": task_id,
            "run_id": run_id,
            "asset_id": asset_id,
            "role": "character_consistency_test",
            "generation_route": "gpt-image-2",
            "expected_asset_kind": "image",
            "prompt": prompt,
            "duration_ms": 1000,
            "segment_id": f"test-{i:02d}",
            "render_treatment": "image",
            "continuity": {"kind": "none"},
            "in_content_timeline": False,
            "motion_intent": "none",
            "motion_parameters": {
                "from": {"x_percent": 0, "y_percent": 0, "scale": 1.0},
                "to": {"x_percent": 0, "y_percent": 0, "scale": 1.0},
            },
        })
        compiled.append({
            "variant_id": variant_id,
            "outfit": outfit,
            "prompt": prompt,
            "prompt_sha256": sha256_text(prompt),
        })

    assert len(tasks) == 6
    assert compiled[0]["prompt_sha256"] == compiled[1]["prompt_sha256"], "CONTROL_PROMPTS_NOT_IDENTICAL"

    out_root = PROJECT_ROOT / "runs" / run_id / "character-consistency-test"
    exec_root = PROJECT_ROOT / "runs" / run_id / "video-production" / "execution"
    out_root.mkdir(parents=True, exist_ok=True)
    exec_root.mkdir(parents=True, exist_ok=True)

    bundle = {
        "schema_version": 1,
        "run_id": run_id,
        "test_name": contract["test_name"],
        "fixed_character_contract_sha256": sha256_text(fixed["character_identity"]),
        "fixed_style_contract_sha256": sha256_text(fixed["style"]),
        "fixed_composition_contract_sha256": sha256_text(fixed["composition"]),
        "fixed_scene_contract_sha256": sha256_text(fixed["scene"]),
        "control_prompt_sha256": compiled[0]["prompt_sha256"],
        "compiled_prompts": compiled,
    }
    (out_root / "compiled-prompt-bundle.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    dispatch = {
        "schema_version": 1,
        "run_id": run_id,
        "recovery_schema_reconstructed": True,
        "creative_replanning": False,
        "test_only": True,
        "tasks": tasks,
    }
    (exec_root / "asset-dispatch.json").write_text(json.dumps(dispatch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "run_id": run_id, "task_count": len(tasks), "control_prompt_identical": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
