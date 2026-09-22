# B03/B04 真实事实库存 v3

该包将根项目、三个真实工程清单中的直接依赖，以及 B01 固定的 Hugging Face 模型/数据集快照，转换为仅供审阅的事实候选。

- `facts.json` 由 `generate.mjs` 确定性生成；`node tests/notice_license_facts_v3.test.mjs` 会检查它没有漂移。
- 每个事实以 `fact_provenance_evidence_ids` 绑定至少一项来源证据；证据同时保存文件 Hash、选中内容 Hash、定位符、采集时间、生产者及版本。仅 JSON 字段使用 JSON Pointer；TOML/XML 使用语义 locator，不伪造 JSON Pointer。
- 根 `LICENSE` 仅记录为文本已观察；依赖清单只证明其声明存在；AI 卡片的 license 值仅为 `provider_declared_unverified`。未发现 NOTICE/copyright 时是 `gap`，不等于违规。
- 所有 `authorization_status` 均为 `pending`，所有 `license_expression_id` 均为 `null`。本包不构成授权、许可证解释、兼容性或合规结论。
- v3 不替换 B02 所冻结的 v2 检测输入；接入 B02 前须另行冻结适配器和评审契约。
