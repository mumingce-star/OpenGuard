# B06 错误分析与规则消融

`error-analysis.json` 是正式 P1 评测前的空白、失败关闭台账，不含虚构的 FN、FP、Gold、holdout 或规则改善结论。

真实评测后的每项误差必须记录为：

- FN：`tier=A/B/C`，原因依次固定为 `static_direct`、`rule_extension`、`dynamic_or_unsafe`；
- FP：`sdk_name_collision`、`example_code`、`comment_or_documentation`、`invalid_url` 或 `irrelevant_configuration`；
- 规则修改：关联被解决的 FN、引入的 FP、规则版本，及 holdout 的 before/after。

Gold 未由人工冻结时，holdout 只能是 `blocked_until_human_gold_freeze`，before/after 必须为 null。不得删除失败样本或把 train/dev 结果写成 holdout 改善。
