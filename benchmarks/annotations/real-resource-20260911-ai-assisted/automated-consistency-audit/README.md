# 全自动标签一致性审计

该工具对 `real-resource-20260911-ai-assisted` 的既有人工确认标签执行无人干预审计。它不会修改原始标签，只检查：

- 12 条记录和 60 个判断维度是否完整、唯一且使用合法枚举；
- 人工确认、R05 修订、第二次 AI 对抗式审阅和最终分布是否相互一致；
- 固定 commit、来源 SHA-256、主证据定位和来源复核映射是否闭合；
- `license=uncertain` 是否继续绑定 `NOASSERTION/review_required`；
- 高风险记录的部分支持和风险修订边界是否保留；
- 召回率指标是否可以从 9 个 case 重新计算；
- 缺少第二真人、旧附件和真人 gold 等限制是否被明确披露。

运行：

```powershell
node benchmarks/annotations/real-resource-20260911-ai-assisted/automated-consistency-audit/run-audit.mjs `
  --output output/automated-label-audit-YYYYMMDD-HHMM
```

测试：

```powershell
node benchmarks/annotations/real-resource-20260911-ai-assisted/automated-consistency-audit/test-audit.mjs
```

结果状态 `human_labels_with_automated_consistency_audit` 只表示自动结构、证据链和内部一致性检查通过。不得改写为“双人独立核验”“第二真人复核”或“语义真值已证明”。
