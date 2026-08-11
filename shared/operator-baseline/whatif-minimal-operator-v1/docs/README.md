# whatif-minimal-operator-v1

## What this is

What-if 项目从冻结动力池中抽取的最小、无状态、只读关系结构运算投影。

- Package ID：`whatif-minimal-operator-v1`
- Source projection：`WHATIF_MINIMAL_OPERATOR_PROJECTION_V1`
- Status：`FUNCTIONAL_PASS`
- 定位：Typed-relation structural computation layer

这是一个**审计基线快照**，不是部署包，也不是完整动力系统发布包。

## What it does

- relation validation —— 受控词表 + 端点语义角色合法性，未知一律 fail-closed
- semantic role resolution —— `record_type` → 语义角色，含冻结源官方 `archetype_role` hatch
- controlled inference —— 受控语义传递闭包，只作为推断视图返回
- relation perturbation —— `remove_edge` / `reverse_edge` / `set_attribute`
- relation walk / propagation —— 单核心 `_walk`，输出层级、结构变化信号、终态节点
- evidence trace —— append-only `operator-calls.jsonl` + 每次调用的输入/输出对象

## What it does NOT do

- 不提供世界知识（图完全由调用方显式提供）
- 不主动发现现实事实（无检索、无外部数据源）
- 不生成 Counterfactual Master
- 不生成内容（无文案、无叙事、无视频相关产物）
- 不保存知识（无 store / 无 memory / 无跨调用学习）
- 不写回动力池（对冻结源只有 `open("r")`）

## Entry point

```
operate(intent, payload, trace=None)
```

`intent ∈ {"expand", "perturb", "propagate"}`；返回 `decision ∈ {CONTINUE, STOP, INVALID}`。
`trace` 为可选旁路 Evidence 记录器，`None` 时运算子行为完全不变。

`src/relation_operator.py` 另附一个 CLI 驱动（`--input` / `--run-id` / `--evidence-dir`），
它只是最小验证驱动，不属于模块能力。

## Runtime

```
Python 3.13.14   （实测复核值；开发与验收环境同版本）
Third-party dependencies: none
```

仅使用标准库：`argparse` / `importlib.util` / `json` / `os` / `sys` / `functools`。

## Frozen source

运行时只读依赖冻结动力池 3 个文件。包内 `frozen-source-reference/` 提供逐字节参考副本
（`REFERENCE COPY ONLY`，见该目录 `NOTICE.txt`）。

```
FROZEN_SOURCE_RELEASE_ID : kr-prototype-v1-20260807T100805Z
FROZEN_SOURCE_DIGEST     : 0d61e8cadf9900620e738b917ac6d1f4289cfd1f0f9c9bbf8b037b875b663278
```

指定冻结源根目录：

```
KR_FROZEN_SOURCE_ROOT=<冻结动力池原件路径>            # 优先
KR_FROZEN_SOURCE_ROOT=<包路径>/frozen-source-reference # 独立审计时
```

未设置时，运算子按原有逻辑回退到 `<模块父目录>/knowledge-runtime-prototype`。

## Verify

```
python verification/verify_package.py
```

通过时输出：

```
PACKAGE_INTEGRITY=true
OPERATOR_LOADABLE=true
SMOKE_TEST_PASS=true
FROZEN_SOURCE_UNCHANGED=true
KNOWLEDGE_PERSISTENCE=false
```

验证脚本把 smoke test 的 Evidence 写入临时目录，**不会污染包内已验收 Evidence**。

## Layout

```
src/                      运算子本体（唯一项目自有源码）
tests/                    smoke test 显式输入
evidence/                 实际验收运行产生的 Evidence（原件，未重新生成）
frozen-source-reference/  冻结源 3 个最小依赖的只读参考副本
verification/             包完整性 + 功能复核脚本
docs/                     本文档 + 来源审查 + 能力边界 + 依赖闭包
manifest.json             包身份与文件 SHA256
SHA256SUMS.txt            包内文件校验清单
```

## Scope

本包不包含也不实现：Premise Engine、Counterfactual Master、Video Master、
AV Compiler、Happy Horse、HyperFrames、完整 pipeline。
