# Premise Discovery

输入一个 External Anchor，从现实中与它直接相关的关系开始展开，再选择一项单一主要扰动，形成唯一一个仍有传播空间、不会显然一步终止的 What-if Premise。不得把 Anchor 当作已经完成的 Premise，不得生成候选、排名或分数。

形成最终 Premise / Counterfactual Contract 时，在当前调用内消除足以改变长期推演结果的作用域与持续性歧义：确认改变作用于谁（WHO）、从何时开始（WHEN）、是瞬时事件、一次性改变还是持续规则（PERSISTENCE），以及在作用对象是持续变化集合时，改变发生后新进入该集合的成员是否继承（FUTURE MEMBERS）。这是一项轻量内部检查，不要求固定四段输出，也不生成 score、judge 或新 Gate。未来成员是否继承必须服从题目语义，不得机械设为继承；但“永久”“从此”“不再”“以后都”等持续规则作用于人类、物种、人口、组织成员、城市居民、机器类别或生态种群时，必须明确处理。例如“人类永久不再需要睡眠”通常应同时说明现存人口何时改变，以及此后出生的人是否同样不再具有该需求，不能无意中把范围缩成当前活着的人。若能在当前调用内消歧，直接修正后输出；只有核心反事实仍无法确定时才返回 `INVALID`。

用模型的现实知识建立本题实际需要的最小 `nodes`、受控 typed `edges` 与一个 `perturbation`。结构合法不等于事实成立；Operator 不是知识源。自然语言 Premise 与结构扰动必须表达同一项变化；若现有 `remove_edge`、`reverse_edge`、`set_attribute` 无法表达，调整结构表示，不扩展 Operator ontology。

只输出 JSON object，至少包含：`status`、`failure_reason`、`anchor`、`raw_premise`、`premise`、`nodes`、`edges`、`perturbation`、`seed`。合法时 `status=VALID`；无法形成合法 Premise 时 `status=INVALID` 并给出 `failure_reason`。
