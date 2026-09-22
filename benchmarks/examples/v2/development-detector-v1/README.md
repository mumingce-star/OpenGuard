# B05 detector development 输入集 v1

这是 Bench 2.0 的 development 输入准备契约；在人工 Gold 未冻结时，它只请求 `smoke`，不是一次 detector 运行，也不包含正式 Gold、预测准确率、召回率、F1 或可报告结果。

每个 artifact 都以 manifest 中的大小和 SHA-256 固定；artifact 内容统一携带 `source_commit`、`source_sha256`、`split=dev` 与 `source_index_artifact_id`。`source-index.json` 将输入定位到固定的 B03/B04 v2 facts 文件；`detector-artifact.json` 仅记录待运行 detector 的代码入口。`prediction.json` 和 `result.json` 的 `execution_status/result_status` 均为 `not_executed`，metrics 为 `null`，且 `formal_metrics_claimed=false`。

`gold.json` 是 development placeholder，不是人工 Gold。manifest 的 `governance.freeze.status` 固定为 `draft`，并且 `gold.json.human_gold_frozen=false`；因此 evaluation 只能请求 `smoke`，任何实际运行、指标计算或展示都必须等待独立的人工 Gold 冻结并创建新的 immutable revision。校验不会联网、执行 detector 或写入 Assessment/Report。

运行准备协议在不执行 detector 的前提下显式绑定 detector → input → config → prediction → result：所有 artifact 均须先通过 manifest 的大小和 SHA-256 校验。`config.json` 固定 `gold_gate=not_frozen`、Hash 校验前置条件和受控错误入口；可报告的错误码仅限输入/Hash/执行/结果验证/Gold 未冻结。`prediction.json` 与 `result.json` 因而均为 `not_executed`，`result.metrics=null` 且 `metrics_visibility=blocked_until_human_gold_freeze`。任何 artifact 均不存储或显示 Precision、Recall、F1。
