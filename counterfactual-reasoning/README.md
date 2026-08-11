# counterfactual-reasoning

同步、单 `run_id` 的反事实推演流程：External Anchor → Premise Discovery → Deep Counterfactual Reasoning → Counterfactual Master。

入口接受显式 `mode`、`run_id`、`anchor` 与可选模型名称元数据。`test` 模式必须显式注入 fixture；`real` 模式禁止 fixture，由当前 ChatGPT Work 模型通过 model-agnostic 的 Work-hosted callable 依次执行三个 Prompt。项目不绑定 subprocess、模型可执行文件或 API；无法稳定取得模型名称时记录 `host-managed`。模型名称不参与 Gate。流程不查找最近运行，不读取其他 run，不回读 Evidence，不写知识库。

```bash
python3 src/counterfactual_reasoning.py \
  --mode test \
  --run-id smoke-painless-human-001 \
  --anchor "人类突然永久失去痛觉" \
  --model-fixture tests/smoke_fixture.json
```

真实执行由 Work 宿主调用 Python `execute(..., mode="real", host_call=<current-work-model>)`；CLI 不建立或发现模型宿主。`host_call` 只接收 stage、Prompt 与输入并返回 JSON object，不包含模型选择、切换或可用性 Gate。

Test 成功只认定 `ORCHESTRATOR_REGRESSION_SMOKE=PASS`，不认定真实 Gate。Semantic `STOP` 才能进入 Master Finalization；`INVALID` 直接失败；`CONTINUE` 以 `ERROR=REASONING_NOT_CLOSED` 停止且不创建 Master 或 Gate。只有 real 模式完整闭合后才可认定 `COUNTERFACTUAL_MASTER_GATE=PASS` 与 `REAL_EXECUTION_VERIFIED=true`。后续视频流程不在本模块范围内。

## Baseline graph + perturbation overlay

Premise Source 的 relation graph 表示现实基线中的关系结构，`perturbation` 是施加在该基线上的显式反事实 delta；两者合起来才定义推演输入。因此，当 perturbation 改变某条 baseline relation 的反事实有效状态时，原 baseline edge 仍可保留，这不构成冲突。Operator Evidence 记录的是“baseline graph + counterfactual perturbation overlay”的运算过程，不应被解释为已经原地改写并完全物化的 post-intervention world graph；不得通过修改冻结 Operator 来消除这种显示差异。
