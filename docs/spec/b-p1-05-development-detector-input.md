# P1B05 Detector development 执行输入

`benchmarks/examples/v2/development-detector-v1/` 补充 Bench 2.0 的离线 detector 输入闭环：source index、detector 描述、输入、matching policy、run config、prediction 和 result 均为独立 artifact，并由 manifest 固定大小和 SHA-256。

所有 artifact payload 绑定 `source_commit`、`source_sha256`、`split=dev` 与 `source_index_artifact_id`；其中 source index 以相同字段声明自身并列出实际输入路径。输入当前引用 B03/B04 v2 facts 的固定 SHA；这是可复算输入来源，不是授权、许可证或业务结果。

`prediction.json` 的 `execution_status` 和 `result.json` 的 `result_status` 均为 `not_executed`，prediction 为空、result 的 `metrics=null`，且 `formal_metrics_claimed=false`。`gold.json` 只是 development placeholder，不是人工 Gold。因此 manifest 仅能请求并达到 `development`，不得用它宣称准确率、召回率、F1、真人标注或 reportable 指标。

本包不联网、不执行 detector、不修改 Assessment/Report/API。后续真实执行必须生成新的 immutable revision，并由 B06 的人工 Gold/FN 治理和 Bench 2 的等级门禁决定能否请求更高 tier。
