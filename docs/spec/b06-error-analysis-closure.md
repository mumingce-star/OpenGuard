# B06 错误分析闭环

## 状态边界

本规范服务于离线、非 Gold 的错误分析。`metrics=null`、`offline_non_gold` 与 `not_executed` 在 Gold freeze 前必须保持不变；这里的记录不是正式性能结论。

## FN 分级

- Tier A：已有静态证据契约可表达的遗漏，例如明确导入绑定、字面量调用或明确结构化字段。可在 train/dev 上回归，但不得据此报告 holdout 指标。
- Tier B：通用解析或证据关联能力不足，例如跨文件配置和 NOTICE 证据链接。改进前须记录边界、失败关闭行为和人工复核风险。
- Tier C：需要权利主体、许可证解释或上下文判断的遗漏。不得用自动规则消除，也不得把推测结果作为 Gold。

每个 FN 分类必须同时记录 `tier` 和 `tier_meaning`；B06 taxonomy 的当前最小集合须覆盖 A、B、C 三个 tier。

## FP 分类

每个 FP 必须给出稳定的 `classification`，至少区分：不支持的许可证推断、将许可证文本误作 NOTICE、证据或主体不匹配。禁止只以“误报”作为结论。

## 规则改进台账

每条规则改进必须进入 `benchmarks/taxonomies/b06-rule-improvement-ledger.json`，并包含：

- 通用且与仓库无关的 `generic_rule_id`；
- `improves`：预计减少的 FN/FP taxonomy code；
- `collateral_risk`：可能新增的 FN/FP taxonomy code；
- `holdout_validation`：明确 `split=holdout`、`family_policy=unseen_family` 和验证状态。

在双人盲审与 Gold freeze 完成前，holdout 的状态只能是 `blocked_until_human_gold_freeze`。不能把 train/dev 结果叙述为 holdout 验证，也不能生成正式指标。

## 禁止刷分

禁止按照仓库名、URL、提交、`repo_id` 或仅适用于单一候选仓库的白名单/allowlist/例外分支改变检测结果。允许的规则只能由公开、可复现的静态语法或结构化字段契约驱动，并应对未见仓库族同样适用。台账验证器会拒绝出现 repository、repo_id、whitelist 或 allowlist 等仓库专属表述的规则变更。

## 验收

运行：

```text
node benchmarks/taxonomies/validate-b06-fn-fp-taxonomy.mjs benchmarks/taxonomies/b06-fn-fp-taxonomy.json
node benchmarks/taxonomies/validate-b06-rule-improvement-ledger.mjs benchmarks/taxonomies/b06-fn-fp-taxonomy.json benchmarks/taxonomies/b06-rule-improvement-ledger.json
```

两个命令通过仅说明 schema 与治理门禁通过，不代表已经在 holdout 上验证，也不代表产生了 Gold 或正式指标。
