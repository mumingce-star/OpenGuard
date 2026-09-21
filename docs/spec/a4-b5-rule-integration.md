# A4-2 B5 许可证规则阶段接线

状态：P0 实现纵切

范围：项目负责人 A4；消费扫描分析组员 B5，不修改 B5 规则语义

## 目标

`app.pipeline.apply_license_rules()` 把一个已经包含 P0 `Component`/`AIAsset`、
`LicenseExpression` 和 `Evidence` 的运行中 `ScanRun` 交给组员实现的
`app.rules.evaluate()`，并把返回的 `Obligation`、`RiskFinding` 和
`Remediation` 作为规则阶段事实写回聚合对象。

本接线不识别许可证、不补官方原文、不改变规则内容，也不把组件名称或扫描器候选文本
猜测为许可证。B2/B3/B4 仍负责产生和标准化许可证事实。

## 聚合边界

- 每个资源必须已经链接一个存在的许可证对象；否则规则阶段以可恢复的
  `license_facts_unavailable` 终止，保留依赖结果并形成 `partial/rules/70`。
- B5 的返回对象必须为精确 `RuleEvaluationResult`，全部 ID 必须唯一，并通过完整
  `ScanRun` 引用和 summary 校验。
- 已存在义务、风险或整改的运行不会被覆盖，固定失败为
  `license_rule_state_conflict`。
- B5 加载或执行异常统一为脱敏、不可恢复的 `license_rules_failed`。
- 成功时 `provenance.ruleset_version` 固定为实际加载的规则集版本。

## AI 和报告

本纵切尚未调用 Qwen3。规则成功后 AI 阶段显式保持关闭，随后由既有 A6 terminal
publisher 生成报告。B5 对 pending 许可证产生的 `license-evidence-gate` finding
没有绑定整改，可供下一独立任务 A5-1c 消费；B5 已提供确定性整改的 finding 不由
AI 重复生成。

当前 ZIP/Git 依赖主链还没有 B2/B3/B4 许可证事实，因此默认计划在调用适配器前仍以
兼容错误 `rules_stage_not_connected` 诚实停在 `partial/rules/70`。这保留既有 API、报告和
独立验证证据；一旦上游提供至少一个许可证聚合，计划才调用 B5 适配器。适配器被独立调用
但缺少完整资源许可证链接时使用更精确的 `license_facts_unavailable`。

## 非目标

- 不修改 `backend/app/rules/`、`rules/license-obligations.yaml` 或组员测试；
- 不接 ScanCode、Syft、SPDX 标准化或 AI 资源检测；
- 不改变 P0 Schema、API、SQLite 状态机、前端或部署；
- 不宣称 15 条规则已完成人工法律核验或官方原文证据台账。
