# Video Master Index

## Entry

- `src/video_master.py` — 显式接收同一 `run_id`、上游正式产物路径及预期 SHA256；依次执行内容构造与语言降维，不发现 latest，不读取上游 work/evidence，不绑定模型。

## Prompt

- `prompts/video-master-polish.md` — 负责选择主语义、保留高价值观点、构造语义场景与主线，并生成 `video-master-source.md`；不承担极限词汇简化。
- `prompts/video-master-language-lowering.md` — 只对 `video-master-source.md` 做局部抽象语言降维；不得改变内容、顺序、场景、因果、Terminal 或结论强度。

## Config

- `config/runtime.json` — 时区、语言、模型元数据默认值与知识持久化边界。

## Tests

- `tests/test_smoke.py` — Formal Artifact identity、单次转换、边界、Gate 与上游冻结回归。
- `tests/verify_index.py` — 本 INDEX 的 active path 一致性验证。

## Runtime Artifacts

- `../runs/<run_id>/video-master/work/video-master-source.md` — Polish 原始转换结果，仅为当前 stage 内部 work artifact。
- `../runs/<run_id>/video-master/evidence/formal-input.json`
- `../runs/<run_id>/video-master/evidence/polish-model-call.json`
- `../runs/<run_id>/video-master/evidence/language-lowering-model-call.json`
- `../runs/<run_id>/video-master/evidence/final-artifact.json`
- `../runs/<run_id>/video-master/video-master.md`
- `../runs/<run_id>/video-master/video-master-gate.json`

## Upstream Formal Input

- `../runs/<run_id>/counterfactual-reasoning/counterfactual-master.md` — 只允许显式传入，并在执行前核验 expected/actual SHA256；不得自动读取上游 `work/` 或 `evidence/`。

## Formal Artifact

- `../runs/<run_id>/video-master/video-master.md`

## Gate

- `VIDEO_MASTER_GATE` — 同一 `run_id`、上游 SHA256、两步职责分离、边界 Evidence 与 INDEX 一致后唯一正式 Gate；只登记最终 `video-master.md` 的 SHA256。
