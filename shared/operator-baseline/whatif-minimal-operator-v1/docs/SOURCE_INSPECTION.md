# SOURCE_INSPECTION

固化 `WHATIF_MINIMAL_OPERATOR_PROJECTION_V1` 阶段已完成的冻结源只读审查结论。
本文件为**记录**，不重新扩展审计范围，不提出修复项。

冻结源身份：

```
FROZEN_SOURCE            : knowledge-runtime-prototype
FROZEN_SOURCE_RELEASE_ID : kr-prototype-v1-20260807T100805Z
FROZEN_SOURCE_DIGEST     : 0d61e8cadf9900620e738b917ac6d1f4289cfd1f0f9c9bbf8b037b875b663278
FROZEN_SOURCE_FILE_COUNT : 128
INSPECTION_MODE          : READ-ONLY（仅 open("r")，无任何写路径）
```

---

## 1. 实际复用

### 1.1 代码：`audit/relation_audit.py`

它是冻结池中唯一的运行时代码。本项目按**函数级**复用其中 5 个函数，不复制实现、不重写。

| 函数 | 提供的能力 | 在运算子中的落点 |
|---|---|---|
| `registry_index` | 20 个受控关系及其元数据（`direction` / `reciprocity` / `semantic_transitivity` / `inference_policy`） | `_registry()`，供词表校验、邻接方向、传递闭包、反转裁决共用 |
| `resolve_roles` | `record_type` → 语义角色映射（唯一 canonical 角色权威），未知类型 fail-closed | `_roles()`，seed 合法性与层级角色统计 |
| `endpoint_ok` | 端点角色合法性判定（多角色交集感知） | `_partition_edges()`，legal / rejected 二分 |
| `reciprocity_violations` | 反向边违例检测（`A R B ∧ B R A`） | `_perturb()` 的 `reverse_edge` 分支，反转后自检 |
| `transitive_inference` | 受控语义传递闭包 | `_derived_view()`，仅作推断视图返回，不写回、不参与游走 |

### 1.2 契约：间接读取，未单独投影

上述函数在自身模块内解析并读取：

```
ontology-core/typed-relations.schema.json     relation_registry[]  （关系元数据权威）
ontology-core/shared-envelope.schema.json     record_type_semantic_roles （端点角色权威，唯一）
```

`relation_audit.py` 的 `ROOT` 由 `__file__` 向上探测 `ontology-core/typed-relations.schema.json` 得到，
因此只要保持 `audit/` 与 `ontology-core/` 的相对结构，加载即成立。
包内 `frozen-source-reference/` 刻意保留了该结构。

---

## 2. 明确未带入

以下均为完整动力知识系统运行所需，但本项目不需要，因此未投影、未复制：

| 未带入 | 原因 |
|---|---|
| 8 个 archetype schema | 重型 schema 层；运算子只需「类型化边 + 端点角色」这一层 |
| `composition/` | 组合引擎，属知识实例组装，本项目不生成知识实例 |
| `routing/` | 动态发现/路由；本项目要求「能静态引用就不动态发现」 |
| `projections/` | 下游输出投影，属 Video Master 阶段 |
| `runtime-records/` | 知识写回与运行记录，明令禁止 |
| `domain-connector/` | 领域接入，本项目无真实领域 onboarding |
| `external-contract/` | 外部系统契约，本项目无外部集成 |
| `examples/abstract/validate_prototype.py` | 冻结池自检器，是治理工具而非运行时能力 |
| 治理文档（77 份） | 记录性资产，不参与运算 |

上述目录/文件在包内**不存在任何副本**。

---

## 3. 为什么这已经是最小集

本项目所需的四类能力——关系展开、关系扰动、因果传播、状态变化与关系接管——
全部落在同一层抽象上：**类型化边 + 端点语义角色 + 关系元数据**。

- 展开与传播共用同一个图游走核心，差别只在 seed 与 `max_depth`；
- 状态变化 / 关系接管 / 终态是游走的输出字段，不需要独立 State Engine；
- 扰动是对边集与属性的结构变更，不需要独立 Intervention Framework；
- CONTINUE / STOP / INVALID 由三行布尔给出，不需要 Evaluation / Decision Gate。

再删除 5 个函数中的任意一个，其能力就必须在项目侧重新实现——那是**复制**，不是**投影**，
与「优先抽已有实现，不重新发明」直接冲突。因此当前集合是满足需求的最小集合。

---

## 4. 审查过程中确认的冻结源事实

（记录性质，不是缺陷单，详见 `CAPABILITY_BOUNDARY.md` §2）

`shared-envelope.schema.json` 的 `record_type_semantic_roles` 共 16 个 canonical record type，
其中**没有任何一个**映射到 `Aspect` / `Part` / `Whole` / `Subtype` / `Supertype`。
20 个受控关系中，只有 15 个可以用纯 canonical `record_type` 通过端点校验；
其余 5 个（`affects` / `measures` / `part_of` / `has_part` / `specializes`）
必须使用 `resolve_roles()` 中冻结源官方保留的 `archetype_role` escape hatch。

这是冻结源在 `FROZEN` 状态下的既有边界，本项目按官方 hatch 使用，未修改、未绕过、未修复。
