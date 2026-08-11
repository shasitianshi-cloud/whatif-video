# Counterfactual Master Finalization

只使用 reasoning source 与必要的 operator audit result，整理唯一正式 Counterfactual Master。不得重新进行世界推理。删除执行元信息、operator 元语言、rejected relation 与重复内容；按因果顺序保留必要事实、机制竞争、真正的状态变化、Terminal 与不确定性。

`CLAIM_STRENGTH_CONSERVATION`：下游结论的确定性不得高于支撑它的关键上游事实或机制。推演性结论使用“可能”“很可能”“在长期适应成功的情况下”等匹配强度的表达，不建立 confidence scoring。

Finalization 只负责 organize / prune / calibrate，不得自行修补 Deep Reasoning 未处理的重大 Counterfactual Contract 或 material mechanism 缺口。若上游 reasoning 不闭合，应由上游返回 `CONTINUE` 或 `INVALID`，而不是在本阶段补做 Deep Reasoning。

Threshold / regime change 只在真实存在并影响结果时保留；无法合理确定时允许明确“未发现可可靠确定的单一阈值”，不得机械补齐。

不得加入新事实、Hook、视频脚本、60–75 秒压缩、镜头、画面、音效、字幕、Happy Horse Prompt 或 CTA。只输出 JSON object：`{"counterfactual_master":"..."}`。
