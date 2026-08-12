#!/usr/bin/env python3
"""Weekly-scope / daily-anchor selection boundary.

The selector owns deterministic validation, scoring, history filtering and final
selection. Host LLM calls only propose candidates and evaluate bounded fields.
It never creates a perturbation or counterfactual premise.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Any

MODULE_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = MODULE_ROOT / "config" / "selection-policy.json"
CANDIDATE_PROMPT_PATH = MODULE_ROOT / "prompts" / "daily-anchor-candidates.md"
EVALUATION_PROMPT_PATH = MODULE_ROOT / "prompts" / "daily-anchor-evaluation.md"

FORBIDDEN_COUNTERFACTUAL_MARKERS = ("如果", "假如", "what if", "what-if")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize_anchor(value: str) -> str:
    value = value.strip().lower()
    return re.sub(r"[\s\-_—–·,，。.!！?？:：;；'\"“”‘’()（）\[\]【】]+", "", value)


def _parse_day(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def load_history(path: Path | None, *, today: date, window_days: int) -> list[dict]:
    if path is None or not path.exists():
        return []
    floor = today - timedelta(days=window_days)
    out: list[dict] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        item = json.loads(raw)
        item_day = _parse_day(str(item["date"]))
        if floor <= item_day <= today:
            out.append(item)
    out.sort(key=lambda x: x["date"])
    return out


def _validate_scope(scope: dict, today: date) -> None:
    required = ("scope_version", "week_id", "theme", "valid_from", "valid_until", "subscopes")
    if any(k not in scope for k in required):
        raise RuntimeError("WEEKLY_SCOPE_INVALID")
    if scope["scope_version"] != 1 or not str(scope["theme"]).strip():
        raise RuntimeError("WEEKLY_SCOPE_INVALID")
    subscopes = scope.get("subscopes")
    if not isinstance(subscopes, list) or not subscopes or len(set(subscopes)) != len(subscopes):
        raise RuntimeError("WEEKLY_SCOPE_INVALID")
    if not (_parse_day(scope["valid_from"]) <= today <= _parse_day(scope["valid_until"])):
        raise RuntimeError("WEEKLY_SCOPE_NOT_ACTIVE")


def _validate_candidates(payload: dict, *, scope: dict, count: int) -> list[dict]:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != count:
        raise RuntimeError("DAILY_ANCHOR_CANDIDATE_COUNT_INVALID")
    seen: set[str] = set()
    out = []
    allowed = set(scope["subscopes"])
    for item in candidates:
        if not isinstance(item, dict) or set(item) != {"anchor", "subscope"}:
            raise RuntimeError("DAILY_ANCHOR_CANDIDATE_SCHEMA_INVALID")
        anchor = str(item["anchor"]).strip()
        subscope = str(item["subscope"]).strip()
        norm = _normalize_anchor(anchor)
        if not anchor or not norm or norm in seen:
            raise RuntimeError("DAILY_ANCHOR_CANDIDATE_DUPLICATE")
        if subscope not in allowed:
            raise RuntimeError("DAILY_ANCHOR_SUBSCOPE_INVALID")
        low = anchor.lower()
        if any(marker in low for marker in FORBIDDEN_COUNTERFACTUAL_MARKERS):
            raise RuntimeError("ANCHOR_SELECTOR_COUNTERFACTUAL_FORBIDDEN")
        seen.add(norm)
        out.append({"anchor": anchor, "subscope": subscope})
    return out


def _validate_evaluations(payload: dict, candidates: list[dict]) -> dict[str, dict]:
    values = payload.get("evaluations")
    if not isinstance(values, list) or len(values) != len(candidates):
        raise RuntimeError("DAILY_ANCHOR_EVALUATION_COUNT_INVALID")
    expected = {x["anchor"] for x in candidates}
    result: dict[str, dict] = {}
    metrics = ("curiosity", "recognizability", "consequence_depth", "visual_potential", "non_obviousness")
    for item in values:
        if not isinstance(item, dict):
            raise RuntimeError("DAILY_ANCHOR_EVALUATION_SCHEMA_INVALID")
        anchor = str(item.get("anchor", "")).strip()
        if anchor not in expected or anchor in result:
            raise RuntimeError("DAILY_ANCHOR_EVALUATION_IDENTITY_INVALID")
        for metric in metrics:
            score = item.get(metric)
            if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= float(score) <= 5:
                raise RuntimeError("DAILY_ANCHOR_EVALUATION_SCORE_INVALID")
        for flag in ("propagation_viability", "scope_match", "duplicate_or_rephrase"):
            if not isinstance(item.get(flag), bool):
                raise RuntimeError("DAILY_ANCHOR_EVALUATION_FLAG_INVALID")
        result[anchor] = item
    return result


def _subscope_blocked(candidate_subscope: str, history: list[dict], max_consecutive: int) -> bool:
    if max_consecutive <= 0 or len(history) < max_consecutive:
        return False
    tail = history[-max_consecutive:]
    return all(str(x.get("subscope", "")) == candidate_subscope for x in tail)


def _score(evaluation: dict, weights: dict[str, float]) -> float:
    value = sum(float(evaluation[k]) * float(weights[k]) for k in weights)
    return round(value, 4)


def select_daily_anchor(
    *,
    scope: dict,
    today: date,
    history: list[dict],
    candidate_model_call: Callable[[str], dict],
    evaluation_model_call: Callable[[str], dict],
    policy: dict | None = None,
) -> dict:
    policy = policy or _read_json(POLICY_PATH)
    _validate_scope(scope, today)
    if not callable(candidate_model_call) or not callable(evaluation_model_call):
        raise RuntimeError("ANCHOR_PROGRAM_HOST_CALLBACK_REQUIRED")

    candidate_prompt = CANDIDATE_PROMPT_PATH.read_text(encoding="utf-8")
    evaluation_prompt = EVALUATION_PROMPT_PATH.read_text(encoding="utf-8")
    candidate_request = candidate_prompt + "\n\n---\n\nWEEKLY SCOPE:\n" + json.dumps(scope, ensure_ascii=False, indent=2)
    candidates = _validate_candidates(
        candidate_model_call(candidate_request),
        scope=scope,
        count=int(policy["candidate_count"]),
    )

    evaluation_request = (
        evaluation_prompt
        + "\n\n---\n\nWEEKLY SCOPE:\n"
        + json.dumps(scope, ensure_ascii=False, indent=2)
        + "\n\nCANDIDATES:\n"
        + json.dumps(candidates, ensure_ascii=False, indent=2)
        + "\n\nRECENT HISTORY:\n"
        + json.dumps(history, ensure_ascii=False, indent=2)
    )
    evaluations = _validate_evaluations(evaluation_model_call(evaluation_request), candidates)

    recent_norm = {_normalize_anchor(str(x.get("anchor", ""))) for x in history}
    eligible: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    weights = policy["weights"]
    threshold = float(policy["minimum_interest_score"])
    max_consecutive = int(policy["max_consecutive_same_subscope"])

    for ordinal, candidate in enumerate(candidates):
        anchor = candidate["anchor"]
        ev = evaluations[anchor]
        reason = None
        if _normalize_anchor(anchor) in recent_norm:
            reason = "RECENT_EXACT_DUPLICATE"
        elif ev["duplicate_or_rephrase"]:
            reason = "RECENT_DUPLICATE_OR_REPHRASE"
        elif not ev["scope_match"]:
            reason = "SCOPE_MISMATCH"
        elif not ev["propagation_viability"]:
            reason = "PROPAGATION_VIABILITY_FAILED"
        elif _subscope_blocked(candidate["subscope"], history, max_consecutive):
            reason = "SUBSCOPE_CONSECUTIVE_LIMIT"
        else:
            interest = _score(ev, weights)
            if interest < threshold:
                reason = "INTEREST_SCORE_BELOW_MINIMUM"
            else:
                eligible.append({
                    "anchor": anchor,
                    "subscope": candidate["subscope"],
                    "interest_score": interest,
                    "ordinal": ordinal,
                    "evaluation": ev,
                })
        if reason:
            rejected.append({"anchor": anchor, "reason": reason})

    if not eligible:
        raise RuntimeError("DAILY_ANCHOR_SELECTION_NO_ELIGIBLE_CANDIDATE")

    eligible.sort(key=lambda x: (-x["interest_score"], x["ordinal"]))
    winner = eligible[0]
    return {
        "schema_version": 1,
        "gate": "DAILY_ANCHOR_SELECTION_GATE",
        "status": "PASS",
        "date": today.isoformat(),
        "week_id": scope["week_id"],
        "scope": scope["theme"],
        "candidate_count": len(candidates),
        "selected_anchor": winner["anchor"],
        "selected_subscope": winner["subscope"],
        "interest_score": winner["interest_score"],
        "propagation_viability": True,
        "recent_duplicate": False,
        "scope_match": True,
        "rejected": rejected,
        "candidate_prompt_sha256": _sha256(CANDIDATE_PROMPT_PATH),
        "evaluation_prompt_sha256": _sha256(EVALUATION_PROMPT_PATH),
        "policy_id": policy["policy_id"],
        "anchor_selector_selects_object_only": True,
        "premise_discovery_remains_separate": True,
    }


def append_history(path: Path, gate: dict) -> None:
    if gate.get("status") != "PASS":
        raise RuntimeError("ANCHOR_GATE_NOT_PASS")
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "date": gate["date"],
        "week_id": gate["week_id"],
        "scope": gate["scope"],
        "subscope": gate["selected_subscope"],
        "anchor": gate["selected_anchor"],
        "interest_score": gate["interest_score"],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare bounded daily anchor selection request.")
    parser.add_argument("--scope", required=True, type=Path)
    parser.add_argument("--history", type=Path)
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    scope = _read_json(args.scope)
    policy = _read_json(POLICY_PATH)
    today = _parse_day(args.date)
    _validate_scope(scope, today)
    history = load_history(args.history, today=today, window_days=int(policy["history_window_days"]))
    print(json.dumps({
        "status": "HOST_ACTION_REQUIRED",
        "action": "DAILY_ANCHOR_SELECTION",
        "date": today.isoformat(),
        "week_id": scope["week_id"],
        "scope": scope["theme"],
        "candidate_count": policy["candidate_count"],
        "recent_history_count": len(history),
        "anchor_selector_selects_object_only": True,
        "premise_discovery_remains_separate": True,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
