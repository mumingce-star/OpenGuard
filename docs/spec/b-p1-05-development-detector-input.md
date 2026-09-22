# P1B05 Detector development 执行输入

`benchmarks/examples/v2/development-detector-v1/` 补充 Bench 2.0 的离线 detector 输入闭环：source index、detector 描述、输入、matching policy、run config、prediction 和 result 均为独立 artifact，并由 manifest 固定大小和 SHA-256。

所有 artifact payload 绑定 `source_commit`、`source_sha256`、`split=dev` 与 `source_index_artifact_id`；其中 source index 以相同字段声明自身并列出实际输入路径。输入当前引用 B03/B04 v2 facts 的固定 SHA；这是可复算输入来源，不是授权、许可证或业务结果。

`prediction.json` 的 `execution_status` 和 `result.json` 的 `result_status` 均为 `not_executed`，prediction 为空、result 的 `metrics=null`，且 `formal_metrics_claimed=false`。`gold.json` 只是 development placeholder，不是人工 Gold。因此 manifest 仅能请求并达到 `smoke`，不得用它宣称准确率、召回率、F1、真人标注或 reportable 指标。

## B05 运行准备门禁

该 fixture 的 `governance.freeze.status` 必须为 `draft`，且 `gold.json.human_gold_frozen=false`；该状态表示没有冻结人工 Gold，不是一个可绕过的占位冻结。因此本 revision 的 evaluation 只能请求 `smoke`。真实运行必须在新的不可变 revision 中绑定已冻结的人工 Gold，不能修改本 development artifact。

artifact 执行闭包固定为 detector → input → config → prediction → result。manifest 对每个 artifact 的 `size_bytes` 和 `sha256` 是运行前必验条件；`config.json.artifact_hash_verification=required_before_execution`，而未运行的 prediction/result 只记录 `not_run`，不把未尝试误报为校验成功。

错误分类入口为 `config.json.error_classification` 和 `result.json.error_classification`，仅允许 `artifact_hash_mismatch`、`input_validation_failed`、`detector_unavailable`、`detector_execution_failed`、`result_validation_failed`、`gold_not_frozen`。当前结果为 `not_observed` 和空 errors：它不表示无错误，只表示 detector 尚未执行。

在 `human_gold_frozen=false` 时，`metrics` 必须为 `null`、`metrics_visibility=blocked_until_human_gold_freeze`、`formal_metrics_claimed=false`。artifact 不得计算、写入或展示 Precision、Recall、F1；这些字段和结论仅能在后续人工 Gold 冻结后的独立 revision 中出现。

本包不联网、不执行 detector、不修改 Assessment/Report/API。后续真实执行必须生成新的 immutable revision，并由 B06 的人工 Gold/FN 治理和 Bench 2 的等级门禁决定能否请求更高 tier。
