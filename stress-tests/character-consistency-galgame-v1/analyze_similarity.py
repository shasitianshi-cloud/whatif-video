from __future__ import annotations

import json
from pathlib import Path
from PIL import Image
import imagehash

RUN_ID = "character-consistency-galgame-outfit-v1-20260814-001"
ROOT = Path("runs") / RUN_ID
EXEC = ROOT / "video-production" / "execution"
OUT = ROOT / "character-consistency-test"

ITEMS = [
    ("control-baseline-a", EXEC / "character-01-control-baseline-a" / "character-01-control-baseline-a.jpg"),
    ("control-baseline-b", EXEC / "character-02-control-baseline-b" / "character-02-control-baseline-b.jpg"),
    ("business", EXEC / "character-03-business" / "character-03-business.jpg"),
    ("weekend-casual", EXEC / "character-04-weekend-casual" / "character-04-weekend-casual.jpg"),
    ("date-dress", EXEC / "character-05-date-dress" / "character-05-date-dress.jpg"),
    ("winter", EXEC / "character-06-winter" / "character-06-winter.jpg"),
]


def crop_region(im: Image.Image, box_ratio: tuple[float, float, float, float]) -> Image.Image:
    w, h = im.size
    x1, y1, x2, y2 = box_ratio
    return im.crop((int(w*x1), int(h*y1), int(w*x2), int(h*y2))).resize((256, 256))


def hashes(im: Image.Image) -> dict[str, str]:
    return {
        "phash": str(imagehash.phash(im)),
        "dhash": str(imagehash.dhash(im)),
        "whash": str(imagehash.whash(im)),
    }


def dist(a: dict[str, str], b: dict[str, str]) -> dict[str, int]:
    return {k: imagehash.hex_to_hash(a[k]) - imagehash.hex_to_hash(b[k]) for k in a}


def main() -> None:
    # Test prompts request a centered three-quarter full-body character in 16:9.
    # Face and upper-body crops are deliberately fixed so the analysis itself does not
    # introduce per-image detection/reframing decisions.
    regions = {
        "face_center": (0.38, 0.04, 0.62, 0.40),
        "upper_body_center": (0.30, 0.02, 0.70, 0.62),
    }
    data = {}
    for name, path in ITEMS:
        im = Image.open(path).convert("RGB")
        data[name] = {
            "size": list(im.size),
            "regions": {r: hashes(crop_region(im, box)) for r, box in regions.items()},
        }

    anchor = data["control-baseline-a"]
    comparisons = {}
    for name, _ in ITEMS[1:]:
        comparisons[name] = {
            region: dist(anchor["regions"][region], data[name]["regions"][region])
            for region in regions
        }

    control = comparisons["control-baseline-b"]
    outfit_names = [x[0] for x in ITEMS[2:]]
    summary = {
        "schema_version": 1,
        "run_id": RUN_ID,
        "method": "fixed-region perceptual-hash comparison; heuristic diagnostic, not identity recognition",
        "regions": regions,
        "hashes": data,
        "comparisons_to_control_a": comparisons,
        "same_prompt_control_distance": control,
        "outfit_variant_distances": {n: comparisons[n] for n in outfit_names},
    }
    for region in regions:
        for metric in ("phash", "dhash", "whash"):
            vals = [comparisons[n][region][metric] for n in outfit_names]
            summary.setdefault("aggregate", {}).setdefault(region, {})[metric] = {
                "control_distance": control[region][metric],
                "outfit_min": min(vals),
                "outfit_max": max(vals),
                "outfit_mean": round(sum(vals)/len(vals), 2),
            }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "similarity-analysis.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary["aggregate"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
