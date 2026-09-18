# 单人分阶段盲化复标：详细操作步骤

本工作包用于只有一名真人时，对 R01–R12 执行“冻结首轮 → 时间隔离 → 隐藏旧答案复标 → 解封比较 → 冲突查证 → 最终冻结”。它能形成可复现的单人质量控制证据，但**不构成双人独立核验，也不能报告标注者间一致率**。

## 1. 先理解边界

- 本批目的为 `output_review`：你需要看到待评价的系统断言、风险和建议，但不应看到首轮标签或理由。
- 你以前已经看过 AI 初标，所以第二轮只能称“单人时间隔离复标”，不能称独立第二人盲审。
- 本流程规定至少冷却 72 小时，建议实际等待 3～7 天。
- 冷却和复标期间不要打开 `ai-draft.json`、`human-confirmation.json`、`human-amendment-r05.json`、`second-ai-review.json` 或历史总结。
- 许可证信息不足时选择 `uncertain`。人工复标不是法律结论，也不能把 `review_required` 自动升级为许可通过。
- `benchmark_gold` 必须另用不暴露 Detector 预测的流程；本工作包不能冒充 gold 盲标。

## 2. 准备隔离工作目录

在仓库根目录打开 PowerShell：

```powershell
$toolDir = "benchmarks/annotations/real-resource-20260911-ai-assisted/single-human-rereview"
$reviewDir = Join-Path $env:USERPROFILE "OpenGuard-single-review"
New-Item -ItemType Directory -Path $reviewDir -ErrorAction Stop
```

目录必须是新的私有目录。不要把历史标签文件复制进去；所有生成器都采用“目标文件已存在即失败”的写入方式，防止静默覆盖。

## 3. 第1天：生成盲化包和空白复标表

```powershell
node "$toolDir/prepare-rereview-packet.mjs" --output "$reviewDir/rereview-packet.json"
node "$toolDir/prepare-review-form.mjs" --packet "$reviewDir/rereview-packet.json" --output "$reviewDir/rereview-response.json"
Get-FileHash "$reviewDir/rereview-packet.json" -Algorithm SHA256
```

记录输出的 SHA-256 和生成时间，然后关闭工作目录。盲化包应有12条记录，且不应出现 `judgments`、`human_review_status` 或 `issue_codes`。

## 4. 等待至少72小时

从 `rereview-packet.json` 的 `generated_at` 开始计算。等待期间：

1. 不查看首轮标签、R05修订和AI二次复核；
2. 不运行两轮比较脚本；
3. 不依据历史 Precision/Recall 猜测什么答案对系统更有利；
4. 可以阅读通用标签字典，但不要阅读本批旧答案。

校验器会比较 `generated_at` 与 `rereview_started_at`，不足72小时将拒绝提交。

## 5. 第4天或以后：填写第二轮复标

只打开隔离目录里的 `rereview-packet.json` 和 `rereview-response.json`。

顶部字段需要填写：

- `status`：改为 `submitted`；
- `reviewer.reviewer_id`：稳定匿名编号，例如 `reviewer-self-01`，不要填写姓名、学校或联系方式；
- 五项 `attestation`：只有确实满足时才能填 `true`；
- `rereview_started_at`、`submitted_at`：填写真实 ISO-8601 时间，例如 `2026-09-20T20:00:00+08:00`。

逐条填写五个维度：

| 维度 | 允许值 |
| --- | --- |
| `resource` | `correct`、`partially_correct`、`incorrect`、`uncertain`、`not_applicable` |
| `evidence` | `correct`、`partially_correct`、`incorrect`、`uncertain`、`not_applicable` |
| `license` | `correct`、`partially_correct`、`incorrect`、`uncertain`、`not_applicable` |
| `risk` | `accept`、`revise`、`reject`、`uncertain`、`not_applicable` |
| `suggestion` | `actionable`、`too_generic`、`incorrect`、`uncertain`、`not_applicable` |

每个维度都必须填写独立理由，不能只写“同意”“没问题”或占位文本。每条记录至少填写一个具体 `evidence_locators`，例如：

```json
"evidence_locators": [
  "openai/openai-python@固定commit:pyproject.toml#L69"
]
```

判断顺序：

1. 核对资源名称、类别和版本；
2. 核对主 Evidence 能支持到什么范围；
3. 单独检查许可信息，不能用根项目 LICENSE 推断第三方资源许可；
4. 判断风险摘要是否准确表达“已知事实”和“不确定性”；
5. 判断建议是否包含对象、入口、动作和预期留存结果；
6. 证据冲突或不足时使用 `uncertain`，不要猜。

## 6. 提交前校验

```powershell
node "$toolDir/validate-rereview.mjs" --packet "$reviewDir/rereview-packet.json" --review "$reviewDir/rereview-response.json"
```

只有输出 `"valid": true` 才算第二轮完成。常见失败：冷却期不足、包哈希不一致、漏填标签、理由过短、占位文本、缺少证据定位或声明未确认。

## 7. 第二轮完成后再解封比较

此时才允许比较两轮：

```powershell
node "$toolDir/compare-rounds.mjs" --packet "$reviewDir/rereview-packet.json" --review "$reviewDir/rereview-response.json" --output "$reviewDir/round-comparison.json"
```

关注：

- `exact_agreement_rate`：60个维度中完全一致的比例；
- `disagreements`：不一致维度数量；
- `per_dimension`：每个维度的一致/不一致数量。

该指标只能称“同一标注者时间隔离一致率”，不能称 Cohen's Kappa 或标注者间一致率。

## 8. 生成并填写冲突复核表

```powershell
node "$toolDir/prepare-resolution.mjs" --comparison "$reviewDir/round-comparison.json" --output "$reviewDir/conflict-resolution.json"
```

如果没有差异，`records` 是空数组，但仍需填写顶部声明、真实时间和 `reviewer_id`。如果存在差异，对每一项：

1. 重新打开固定 revision 的原始来源；
2. 不看 Detector 指标，不以提高分数为目标；
3. 填写 `final_judgment`、具体 `decision_basis` 和 `evidence_locators`；
4. 如果证据仍不足，最终值保守选择该维度允许的 `uncertain`；
5. 将 `status` 改为 `submitted`，四项声明如实改为 `true`。

然后校验：

```powershell
node "$toolDir/validate-resolution.mjs" --comparison "$reviewDir/round-comparison.json" --resolution "$reviewDir/conflict-resolution.json"
```

## 9. 生成最终冻结快照

```powershell
node "$toolDir/finalize-rereview.mjs" `
  --packet "$reviewDir/rereview-packet.json" `
  --review "$reviewDir/rereview-response.json" `
  --comparison "$reviewDir/round-comparison.json" `
  --resolution "$reviewDir/conflict-resolution.json" `
  --output "$reviewDir/final-single-human-review.json"
Get-FileHash "$reviewDir/final-single-human-review.json" -Algorithm SHA256
```

最终文件必须满足：

- `status` 为 `single_human_time_separated_rereview_finalized`；
- `reviewer_count` 为1、`review_rounds` 为2；
- `independent_second_human` 为 `false`；
- 包含盲化包、复标、比较和冲突复核的哈希；
- 明确列出允许主张和禁止主张。

## 10. 对外披露模板

可以写：

> 本批由一名真人完成两阶段、至少72小时时间隔的盲化复标。第二轮填写期间不展示首轮标签；提交后计算同一标注者一致率，并对所有差异重新查阅固定来源，证据不足项保留为不确定。该流程不属于双人独立标注。

不能写“两名专家独立标注”“双人盲审通过”“标注者间一致率”“AI作为第二评审”或“许可证已经人工确认合法”。

## 11. 工具自测

```powershell
node "$toolDir/test-workflow.mjs"
```

自测只在系统临时目录创建合成回执，覆盖空白回执拒绝、72小时门禁、合法回执、60维比较、差异识别、未解决冲突拒绝、冲突解决和最终冻结。它不会生成或代填真实人工答案。
