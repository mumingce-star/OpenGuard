# B05 detector development 输入集 v1

这是 Bench 2.0 的 development 级执行输入契约，不是一次 detector 运行，也不包含正式 Gold、预测准确率、召回率、F1 或可报告结果。

每个 artifact 都以 manifest 中的大小和 SHA-256 固定；artifact 内容统一携带 `source_commit`、`source_sha256`、`split=dev` 与 `source_index_artifact_id`。`source-index.json` 将输入定位到固定的 B03/B04 v2 facts 文件；`detector-artifact.json` 仅记录待运行 detector 的代码入口。`prediction.json` 和 `result.json` 的 `execution_status/result_status` 均为 `not_executed`，metrics 为 `null`，且 `formal_metrics_claimed=false`。

`gold.json` 是 development placeholder，不是人工 Gold。manifest 只请求 `development`，任何高于该等级的请求都必须由 Bench 2 校验器拒绝。校验不会联网、执行 detector 或写入 Assessment/Report。
