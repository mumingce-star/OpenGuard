# B5 许可证义务规则引擎

状态：`IMPLEMENTED_PENDING_RUNTIME_VERIFICATION`

## 边界

`app.rules.evaluate(resource, license_expression, evidence)` 只消费已关联的 P0
`Component`/`AIAsset`、`LicenseExpression` 和 `Evidence`，输出
`Obligation`、`RiskFinding` 与 `Remediation`。它是确定性的合规提示工具，不提供
法律意见，也不根据名称、扫描器候选文本或 AI 输出猜测许可证。

规则存放在 `rules/license-obligations.yaml`。文件采用 JSON 子集 YAML，避免引入
可执行 YAML 标签、锚点、include 或插值能力；加载器严格拒绝未知字段。当前覆盖：
MIT、Apache-2.0、BSD-3-Clause、GPL-3.0-only、CC-BY-4.0、CC-BY-NC-4.0。

## 证据门禁

- 资源必须链接传入的许可证对象；否则拒绝调用。
- 许可证和至少一个其引用的 Evidence 均为 `verified` 时，才产生该许可证的
  `review_required` 义务提示、风险提示和整改建议。
- 许可证或证据为 pending 时，仅产生 `license-evidence-gate` 的
  `review_required`；没有可用证据时产生 `unknown`。
- 未覆盖的已验证 SPDX ID 产生 `unknown`，不会伪造 pass。

每条规则均有 `tests/fixtures/license-rules/cases.json` fixture。稳定 UUIDv5 使用
资源、许可证、规则、版本和证据 ID 生成；规则集 SHA-256 记录为 rule-engine
producer 的 config digest。

## 未完成门禁

本模块尚未解析复合 SPDX 表达式（B4 负责标准化），也未接入 A4 ScanRun 编排。
所有 `review_required` 都需要人工核验原始许可证和实际使用/分发场景。
