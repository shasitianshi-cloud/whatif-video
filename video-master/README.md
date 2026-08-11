# Video Master

本流程只将已经冻结的 Counterfactual Master 转换为普通观众可连续理解的内容母稿。它回答“讲什么”，不重新回答“会发生什么”，也不进入镜头、声音或视频执行。

正式入口必须由调用方显式提供同一 `run_id`、`counterfactual-master.md` 路径和 Gate A 登记的 SHA256。入口不会发现 latest，不读取上游内部 work/evidence，不建立模型绑定。Work 宿主先执行 Video Master Polish，将结果冻结为 stage 内部的 `work/video-master-source.md`；再执行极简 Language Lowering，只降低局部抽象表达并生成正式 `video-master.md`。

`VIDEO_MASTER_GATE` 通过后，唯一正式产物为 `video-master.md`。下游只能显式消费同一 run 的产物路径与 Gate B SHA256。
