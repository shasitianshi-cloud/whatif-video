# Counterfactual Reasoning Index

## Entry

- `src/counterfactual_reasoning.py` — 显式 real/test 模式、Work-hosted 且 model-agnostic 的三阶段 Prompt 执行、Premise retry、Semantic CONTINUE 阻断与同步单 Run 主入口；不包含 subprocess、可执行文件或 API 模型绑定。

## Prompts

- `prompts/premise-discovery.md` — 从 External Anchor 形成唯一 Premise。
- `prompts/deep-reasoning.md` — 对唯一 Premise 做充分反事实推演。
- `prompts/master-finalization.md` — 从 reasoning source 与 operator audit 整理正式母稿。

## Operator

- `../shared/operator-baseline/whatif-minimal-operator-v1/src/relation_operator.py` — 冻结 Minimal Operator。
- `../shared/operator-baseline/whatif-minimal-operator-v1-portable.zip` — 原始基线包。

## Config

- `config/runtime.json` — 时区、语言、重试与基线哈希配置。

## Tests

- `tests/smoke_fixture.json` — 仅供 test mode 使用的三阶段显式模型响应 fixture。
- `tests/test_smoke.py` — 端到端 Gate 与边界验证。
- `tests/verify_index.py` — active path 一致性检查。

## Runtime Artifact Layout

- `../runs/<run_id>/input/anchor.json`
- `../runs/<run_id>/counterfactual-reasoning/work/`
- `../runs/<run_id>/counterfactual-reasoning/evidence/`
- `../runs/<run_id>/counterfactual-reasoning/counterfactual-master.md`
- `../runs/<run_id>/counterfactual-reasoning/counterfactual-master-gate.json`

Semantic `CONTINUE` 的失败 run 只保留 reasoning 与 `evidence/semantic-continue-block.json`，不会创建 Master 或 Gate。

## Formal Artifact

- `../runs/<run_id>/counterfactual-reasoning/counterfactual-master.md`

## Gate

- `ORCHESTRATOR_REGRESSION_SMOKE` — test mode，只验证接线与回归。
- `COUNTERFACTUAL_MASTER_GATE` — real mode 完整通过后唯一正式 Gate。
