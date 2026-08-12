# Daily Anchor Candidate Generation

你只负责在给定 Weekly Scope 内生成“对象级 Anchor 候选”，不得生成 What-if、扰动、Counterfactual Contract、因果结论或视频脚本。

要求：
- 严格位于 `theme/include/subscopes` 定义的周作用域内；
- 排除 `exclude`；
- 生成恰好 6 个彼此不同的候选；
- 每个候选只包含 `anchor` 与 `subscope`；
- `anchor` 必须是普通观众可识别或可快速理解的现实对象、现象、系统或基础设施；
- 不得以“如果”“假如”“what if”等方式提前定义反事实；
- 不要为了显得新奇而选择几乎没有现实关系可展开的冷门名词；
- 不要评价，不要排序，不要给分。

只输出 JSON object：

{
  "candidates": [
    {"anchor": "...", "subscope": "..."}
  ]
}
