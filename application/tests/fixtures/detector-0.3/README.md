# Detector 0.3 固定离线工件

`cases.json` 是非 Gold 的 train/dev/holdout fixture。`manifest.json`（`openguard.detector-artifact-manifest/1`）固定 cases、detector、input、prediction、result 的相对路径、字节长度、SHA-256 与依赖边；下游 JSON 也回写其每个上游工件的路径和摘要。任何替换、截断或未同步更新引用的工件都必须被回归拒绝。

`detector.json`、`input.json`、`prediction.json` 与 `result.json` 同时固定本次检测器版本和未执行状态；因此它们不声称 Precision、Recall 或 F1。SDK 导入本身不是候选；AST 实际调用、Markdown 示例引用、以及明确 TOML/YAML/JSON 字段分别保留不同的检测方法与证据类型。
