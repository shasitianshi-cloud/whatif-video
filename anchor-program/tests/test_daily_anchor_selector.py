from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "anchor-program" / "src"
sys.path.insert(0, str(SRC))

from daily_anchor_selector import select_daily_anchor  # noqa: E402


def main() -> None:
    scope = {
        "scope_version": 1,
        "week_id": "2026-W33",
        "theme": "太空",
        "valid_from": "2026-08-10",
        "valid_until": "2026-08-16",
        "include": ["天体", "空间环境", "航天基础设施", "天文现象"],
        "exclude": ["纯科幻虚构对象"],
        "subscopes": ["celestial_body", "space_environment", "astronomical_phenomenon", "space_infrastructure"],
    }
    history = [
        {"date": "2026-08-10", "scope": "太空", "subscope": "celestial_body", "anchor": "月球"},
        {"date": "2026-08-11", "scope": "太空", "subscope": "celestial_body", "anchor": "火星"},
    ]
    candidates = {"candidates": [
        {"anchor": "月球", "subscope": "celestial_body"},
        {"anchor": "木星", "subscope": "celestial_body"},
        {"anchor": "太阳风", "subscope": "space_environment"},
        {"anchor": "国际空间站", "subscope": "space_infrastructure"},
        {"anchor": "日食", "subscope": "astronomical_phenomenon"},
        {"anchor": "小行星带", "subscope": "celestial_body"},
    ]}
    scores = {
        "月球": [5, 5, 5, 5, 3, True, True, True],
        "木星": [5, 5, 5, 5, 4, True, True, False],
        "太阳风": [4.5, 4, 5, 5, 4.5, True, True, False],
        "国际空间站": [4, 5, 4, 5, 4, True, True, False],
        "日食": [4, 5, 3.5, 5, 3.5, True, True, False],
        "小行星带": [4.5, 4, 4.5, 5, 4, True, True, False],
    }

    def candidate_call(_: str) -> dict:
        return candidates

    def eval_call(_: str) -> dict:
        items = []
        for anchor, values in scores.items():
            items.append({"anchor": anchor, "curiosity": values[0], "recognizability": values[1], "consequence_depth": values[2], "visual_potential": values[3], "non_obviousness": values[4], "propagation_viability": values[5], "scope_match": values[6], "duplicate_or_rephrase": values[7]})
        return {"evaluations": items}

    gate = select_daily_anchor(scope=scope, today=date(2026, 8, 12), history=history, candidate_model_call=candidate_call, evaluation_model_call=eval_call)
    assert gate["status"] == "PASS"
    assert gate["selected_anchor"] == "太阳风"
    assert gate["selected_subscope"] == "space_environment"
    assert gate["candidate_count"] == 6
    rejected = {x["anchor"]: x["reason"] for x in gate["rejected"]}
    assert rejected["月球"] in {"RECENT_EXACT_DUPLICATE", "RECENT_DUPLICATE_OR_REPHRASE"}
    assert rejected["木星"] == "SUBSCOPE_CONSECUTIVE_LIMIT"
    assert gate["anchor_selector_selects_object_only"] is True
    assert gate["premise_discovery_remains_separate"] is True
    print("ANCHOR_PROGRAM_V1_REGRESSION=PASS")
    print(json.dumps(gate, ensure_ascii=False))


if __name__ == "__main__":
    main()
