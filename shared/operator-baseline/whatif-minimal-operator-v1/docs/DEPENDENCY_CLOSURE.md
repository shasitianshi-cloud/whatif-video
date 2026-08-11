# DEPENDENCY_CLOSURE

本项目运行时的**全部**依赖，无省略、无 graph、无传递展开。

```
Project:
  src/relation_operator.py

Frozen source (READ-ONLY):
  audit/relation_audit.py
  ontology-core/typed-relations.schema.json
  ontology-core/shared-envelope.schema.json

Runtime:
  Python standard library
```

---

## Project

| 文件 | 用途 |
|---|---|
| `src/relation_operator.py` | 唯一项目自有源码。单文件，477 行。提供唯一入口 `operate(intent, payload, trace=None)`，内含 `_walk`（展开+传播）、`_perturb`（3 个结构算子）、`EvidenceTrace`（旁路记录），以及一个最小验证 CLI 驱动。 |

无项目内部模块间依赖（单文件，无 package、无 `__init__.py`、无相对 import）。

## Frozen source（只读，3 个文件）

| 文件 | 用途 | 加载方式 |
|---|---|---|
| `audit/relation_audit.py` | 提供 5 个函数：`registry_index` / `resolve_roles` / `endpoint_ok` / `reciprocity_violations` / `transitive_inference` | `importlib.util.spec_from_file_location` 静态加载；`sys.dont_write_bytecode=True` 防止在冻结目录生成 `.pyc` |
| `ontology-core/typed-relations.schema.json` | `relation_registry[]`——20 个受控关系及元数据（direction / reciprocity / semantic_transitivity / inference_policy） | 由 `relation_audit.py` 内部 `open("r")` 读取，运算子不直接打开 |
| `ontology-core/shared-envelope.schema.json` | `record_type_semantic_roles`——`record_type` → 语义角色的唯一权威映射 | 同上 |

访问模式：**仅 `open("r")`**。运算子不存在任何指向冻结源的写路径；
`EvidenceTrace` 另有显式守卫，evidence 目录落在冻结源内部时直接抛错。

根目录解析优先级：

```
1. 环境变量 KR_FROZEN_SOURCE_ROOT
2. <relation_operator.py 所在目录的父目录>/knowledge-runtime-prototype
```

包内 `frozen-source-reference/` 是这 3 个文件的逐字节参考副本（`REFERENCE COPY ONLY`），
保留了 `audit/` 与 `ontology-core/` 的原始相对结构，可直接作为 `KR_FROZEN_SOURCE_ROOT` 使用。

## Runtime

| 依赖 | 用途 |
|---|---|
| `argparse` | 仅最小验证 CLI 驱动使用 |
| `importlib.util` | 静态加载冻结源模块 |
| `json` | 输入解析、Evidence 序列化 |
| `os` | 路径解析、目录创建、环境变量 |
| `sys` | `dont_write_bytecode`、CLI 退出码 |
| `functools.lru_cache` | 缓存不可变冻结契约（非跨调用知识状态） |

```
Third-party dependencies: none
Python: 3.13.14（实测复核值）
```

---

## 已删除 / 从未引入的依赖

以下依赖仅因完整动力知识系统的历史结构而存在，本项目不需要，因此**不在闭包内**：

```
8 archetype schemas
composition/
routing/
projections/
runtime-records/
domain-connector/
external-contract/
examples/abstract/validate_prototype.py
governance documents (77 files)
```

以及本项目**明令未引入**的工程设施：

```
registry / plugin system / workflow engine / state machine framework
generic agent / composition engine / evaluator framework
knowledge store / memory / runtime-record / event bus
dependency injection framework / 重型 schema layer / 测试框架
```
