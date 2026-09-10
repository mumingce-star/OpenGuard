# B5 许可证义务规则引擎

状态：`IMPLEMENTED_LOCAL_RUNTIME_VERIFIED`

## 边界

`app.rules.evaluate(resource, license_expression, evidence)` 只消费已关联的 P0
`Component`/`AIAsset`、`LicenseExpression` 和 `Evidence`，输出
`Obligation`、`RiskFinding` 与 `Remediation`。它是确定性的合规提示工具，不提供
法律意见，也不根据名称、扫描器候选文本或 AI 输出猜测许可证。

规则存放在 `rules/license-obligations.yaml`。文件采用 JSON 子集 YAML，避免引入
可执行 YAML 标签、锚点、include 或插值能力；加载器严格拒绝未知字段。当前覆盖：
MIT、Apache-2.0、BSD-2-Clause、BSD-3-Clause、ISC、MPL-2.0、EPL-2.0、LGPL-2.1-only、GPL-2.0-only、GPL-3.0-only、AGPL-3.0-only、CC0-1.0、Unlicense、CC-BY-4.0、CC-BY-NC-4.0。

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

## V4 项目级决策表增量（2026-09-10）

原B5引擎与规则资料继续产出事实/提醒，未修改其VERIFIED门槛。A线assessment.engine在其结果之上作有限用途评估：

| 情境 | 必须前提 | 项目级表达 |
| --- | --- | --- |
| 精确MIT | 精确资源版本、对应许可原文及绑定均VERIFIED，独立scope证据绑定资源/版本/许可；相关资源全部支持且无覆盖缺口，用途明确 | 对应维度可按条件使用；版权/许可声明义务仍待落实 |
| 精确GPL-3.0-only交付 | 同样许可/范围证据，明确项目或运行交付对象，distributed=true且source_disclosure=false | 闭源交付存在限制；未知事项同时保留，不自动认定违法 |
| 明确不实施某用途 | 已核实范围/全部相关资源支持、无覆盖缺口，用户明确该用途false | 仅该用途不适用；用途变更需要重评估 |
| 版本/范围/许可未核实，复合表达式/独立AI资产，失败/partial | 不满足上述门槛 | 未知并列具体补证步骤；根LICENSE不继承给依赖、模型或数据 |

来源：[MIT正式文本](https://opensource.org/license/mit)、[GPLv3正式文本](https://opensource.org/license/gpl-3.0)第5/6节。源码RULE_SOURCES/规则版本保留引用。其他许可仍不可判；这不是全部法律语义实现。受控正例/限制例用于分支验证，未把真实扫描记录改VERIFIED；独立人工金标准、cz规则复核尚待。
