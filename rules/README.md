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
