# 许可证义务规则库

每条规则使用版本化 YAML/JSON，至少包含：

- SPDX ID；
- 官方来源和版本；
- 适用前提；
- 触发证据；
- 署名、LICENSE、NOTICE、源代码和网络使用义务；
- 风险等级；
- 解释模板；
- 人工复核状态；
- 测试用例。

规则库只生成风险提示，不生成法律裁决。

当前 P0 可执行规则位于 `license-obligations.yaml`（JSON 子集 YAML），由
`backend/app/rules/engine.py` 严格加载。每条规则必须在
`tests/fixtures/license-rules/cases.json` 中拥有可复现 fixture。

P0 表达式处理边界：

- 单许可证和纯 `AND` 表达式按已核验叶节点执行规则；任何未覆盖叶节点都会额外生成 `license-rule-coverage`，不会被已匹配分支隐藏；
- 含 `OR` 的表达式不会替用户选择许可证，也不会把所有备选义务误报为必需义务，而是生成 `license-choice-required` 供人工选择后复核；
- 缺失 Evidence 引用或 `expression` 与 `normalized_ids` 不一致时失败关闭，分别生成完整性诊断；
- 当前仍不解析括号、`WITH`、`+`、`LicenseRef` 等完整 SPDX 语法，这些输入保持待核验，不得解释为不存在义务。

`2026.09.2` 将上述失败关闭和选择语义纳入规则执行版本；报告中的
`provenance.ruleset_version` 可用于区分修复前后的评估结果。
