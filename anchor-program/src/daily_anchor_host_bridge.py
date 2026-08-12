#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from daily_anchor_selector import append_history, load_history, select_daily_anchor

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / 'anchor-program' / 'config' / 'selection-policy.json'


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--scope', required=True, type=Path)
    p.add_argument('--history', required=True, type=Path)
    p.add_argument('--responses', required=True, type=Path)
    p.add_argument('--date', required=True)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()

    if args.output.exists():
        raise RuntimeError('DAILY_ANCHOR_GATE_ALREADY_EXISTS')
    today = datetime.strptime(args.date, '%Y-%m-%d').date()
    policy = read_json(POLICY_PATH)
    scope = read_json(args.scope)
    responses = read_json(args.responses)
    if responses.get('date') != args.date or responses.get('week_id') != scope.get('week_id'):
        raise RuntimeError('ANCHOR_HOST_RESPONSE_SCOPE_MISMATCH')
    candidate_response = responses.get('candidate_response')
    evaluation_response = responses.get('evaluation_response')
    if not isinstance(candidate_response, dict) or not isinstance(evaluation_response, dict):
        raise RuntimeError('ANCHOR_HOST_RESPONSE_INVALID')

    history = load_history(args.history, today=today, window_days=int(policy['history_window_days']))
    gate = select_daily_anchor(
        scope=scope,
        today=today,
        history=history,
        candidate_model_call=lambda _prompt: candidate_response,
        evaluation_model_call=lambda _prompt: evaluation_response,
        policy=policy,
    )
    gate['model'] = responses.get('model', 'host-managed')
    gate['candidate_model_calls'] = 1
    gate['evaluation_model_calls'] = 1
    gate['provider_generation_executed'] = False
    gate['counterfactual_generated'] = False
    gate['perturbation_generated'] = False
    gate['history_count_before'] = len(history)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(gate, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    append_history(args.history, gate)
    print(json.dumps(gate, ensure_ascii=False))


if __name__ == '__main__':
    main()
