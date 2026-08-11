# Deep Counterfactual Reasoning

对唯一 Premise 做一次充分语义推演。实际检查契约、现实基线、改变变量、直接效应、相关系统、传播、竞争与补偿机制、时间尺度、适用的空间/尺度效应、高阶效应、可能的主导机制变化、边界分支、Terminal 与不确定性。不得看到一个 plausible outcome 就停止。

决定 Semantic STOP 前，执行一次 material adjacent mechanism 内部检查：被改变变量周围是否仍有一个与 intervention 紧密相连、现实中仍然存在、并可能成为新的主要约束、反馈、补偿或反作用的未处理机制。仅当它可能改变主因果方向、主要约束、dominant mechanism、重要状态转换、主要分支或 Terminal State 时才是 material；只能增加例子、细节、行业或相似后果的信息不构成继续理由。不得机械输出邻接机制清单，也不得借此无限扩展知识。若 material adjacent mechanism 会改变主链或 Terminal，必须处理它，并在 `reasoning_graph` 中用足够结构保持主链一致；Graph 不需要表达每句话。

Semantic STOP 仅在以下条件同时成立时允许：主因果链已闭合；重要竞争机制已处理；重要反馈与补偿已处理；不存在未处理的 material adjacent mechanism；继续扩展只会重复、举例或开启另一主题。否则输出 `CONTINUE`。例如睡眠需求消失不自动等于昼夜节律消失；若仍存在的昼夜节律足以改变全天候社会的长期结构，就必须先处理。Operator STOP 仅表示当前 graph frontier 耗尽，不能替代 Semantic STOP；`regime_change` 仅是 structural transition hint，不能单独证明 dominant mechanism takeover。

Threshold / regime change 只在真实存在并影响结果时输出；无法合理确定时明确“未发现可可靠确定的单一阈值”，不得为模板完整而创造阈值。

只输出 JSON object，包含 `decision`（CONTINUE、STOP 或 INVALID）、完整 `reasoning_source` 与最小 `reasoning_graph`。Graph 只表达真正重要的关系结构，但 Master 的主因果链、机制变化、补偿机制和 Terminal 不得整体悬空。不得输出私有 chain-of-thought，只输出可审计的正常推演材料。
