# CAPABILITY_BOUNDARY

固化 `WHATIF_MINIMAL_OPERATOR_PROJECTION_V1` 的真实能力边界。
本文件只**记录**边界，不修改代码，不修复边界。

模块定位：

```
Typed-relation structural computation layer
```

承担：`VALIDATE` / `INFER` / `TRANSFORM` / `WALK` / `TRACE`

明确不是：`Knowledge source` / `World model` / `Counterfactual reasoner`
/ `Content generator` / `Persistent knowledge runtime`

---

## 1. Structural operator only

该模块只能运算**调用方显式提供**的：

```
nodes
typed relations
roles
attributes
```

它自身不是现实知识源。

具体含义：

- 图里没有的关系，运算子不会知道，也不会去找；
- 运算子不判断一条关系在现实中是否为真，只判断它在受控词表与端点角色下是否**结构合法**；
- `reached_nodes` / `terminal_nodes` 是图上的可达性结论，不是关于现实世界的断言；
- 任何「这个后果在现实中会发生」的判断，责任在上层调用方，不在本模块。

因此：**结构合法 ≠ 事实成立**。审计时不得把运算子输出当作事实来源。

---

## 2. `archetype_role` hatch —— KNOWN FROZEN-SOURCE BOUNDARY

真实发现（只读审查所得）：

`shared-envelope.schema.json` 的 `record_type_semantic_roles` 当前 canonical record types
**无法直接覆盖**以下语义角色：

```
Aspect
Part
Whole
Subtype
Supertype
```

后果：涉及这些角色的受控关系，用纯 canonical `record_type` 声明端点必然被
`endpoint_ok` 判为 `ENDPOINT_ROLE_REJECTED`。受影响的关系包括
`affects` / `measures` / `part_of` / `has_part` / `specializes`。

处置：使用冻结源 `resolve_roles()` 中**已有的官方** `archetype_role` escape hatch 显式声明角色。
包内 `tests/test-input.human.json` 即按此方式声明。

定性：

```
KNOWN FROZEN-SOURCE BOUNDARY
```

这**不是**本项目的缺陷修复项。本包不修复它，也不得因为它反向修改冻结动力池。
后续若要消除该边界，属于冻结源自身版本演进范畴（Knowledge Runtime V2），不属于本项目。

---

## 3. Structural transition —— `regime_change` 的语义边界

当前代码在 `_walk()` 的每层输出中保留字段 `regime_change`，
以及汇总字段 `regime_change_depths`。其判据是确定性的结构判据：

> 在深度 > 1 的某一层，出现了此前层级没有使用过的**关系类型**或没有进入过的**语义角色**。

必须明确：

> 当前该信号表示图传播过程中出现新的关系类型或语义角色等**结构变化**；
> 它不能单独证明现实世界中的「主导机制接管」。

换言之：

- `regime_change=true` 是一个**图结构层面的提示**，用于把注意力引向可能的机制切换点；
- 它不度量机制强度、不比较作用量级、不判断哪个机制在现实中先接管；
- 真正的「主导机制接管」判定必须由上层（完整 Counterfactual 推演）以领域论证给出。

本包不修改该字段的实现或命名，仅在此登记其语义边界，避免下游误读。

---

## 4. `set_attribute` —— 领域语义不由本层承载

冻结池的知识模型只有「节点 + 受控类型化边」，**没有数值属性层**。
因此运算子只提供 3 个结构算子：`remove_edge` / `reverse_edge` / `set_attribute`。

记录：

> 属性、数量、尺度、速度、时长、同步等具体反事实变化在底层可统一由结构化 attribute mutation
> (`set_attribute`) 承载，但其**领域语义必须由上层输入保留**。

具体含义：

- `set_attribute` 只在本次调用的返回值中产生一条 `ATTRIBUTE_DELTA` notice，
  不写回节点、不改变图拓扑、不参与后续游走；
- 「体重翻倍」与「反应延迟 ×8」在本层是同一种操作，二者的区别完全由
  调用方在 `attribute` / `value` / `mode` 字段中携带的领域语义决定；
- 运算子不校验属性值的物理合理性，也不推导属性变化的量纲后果。

映射关系（记录用）：

| 上层反事实变化 | 本层算子 |
|---|---|
| 属性改变 / 数量改变 / 比例改变 / 尺度改变 / 速度改变 / 持续时间改变 / 状态改变 / 同步关系改变 | `set_attribute` |
| 关系断开 / 约束移除 | `remove_edge` |
| 关系反转 | `reverse_edge` |

---

## 5. 其他既有边界（记录）

- **无状态**：`lru_cache` 只缓存不可变的冻结契约内容，不构成跨调用知识状态；
  同一输入换 `run_id` 重跑，结果对象逐字节相同（已由 `evidence/objects/` 两个 run 目录佐证）。
- **Evidence 单向**：trace 只写不读，运算子任何路径都不会回读 `operator-calls.jsonl`；
  Evidence 不是继续运行的输入，也不得自动回灌下一阶段 LLM context。
- **run 生命周期不归本模块**：`run_id` 缺失直接抛 `RUN_ID_REQUIRED`，运算子不自动生成。
- **写冻结源守卫**：evidence 目录若落在冻结源内部，抛 `EVIDENCE_DIR_INSIDE_FROZEN_SOURCE`。
- **字节码守卫**：模块顶部设 `sys.dont_write_bytecode = True`，
  import 冻结源代码不会在冻结目录生成 `__pycache__`（实测 `PYC=0`）。
- **决策三态无评分**：`INVALID`（存在 invalid_reasons）/ `CONTINUE`（frontier 未耗尽）/
  `STOP`（frontier 耗尽）。不存在评分体系、阈值或权重。
