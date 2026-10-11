# B03/B04 真实事实库存 v3

该包将根项目、三个真实工程清单中的直接依赖，以及 B01 固定的 Hugging Face 模型/数据集快照，转换为仅供审阅的事实候选。

- 根目录 `facts.json` 是保留的历史包；2026-10-11 已确认其中 8 条 npm Evidence 的来源 commit/文件 Hash 错绑，不应作为新来源闭包验收输入。
- 修正版为 `revisions/source-binding-r2/facts.json`，由 `generate.mjs` 从固定 commit 的 Git blob 确定性生成，保持原 v3 Schema。当前工作树与 HEAD 不参与生成。
- 每个事实以 `fact_provenance_evidence_ids` 绑定至少一项来源证据；证据同时保存文件 Hash、选中内容 Hash、定位符、采集时间、生产者及版本。仅 JSON 字段使用 JSON Pointer；TOML/XML 使用语义 locator，不伪造 JSON Pointer。
- 根 `LICENSE` 仅记录为文本已观察；依赖清单只证明其声明存在；AI 卡片的 license 值仅为 `provider_declared_unverified`。未发现 NOTICE/copyright 时是 `gap`，不等于违规。
- 所有 `authorization_status` 均为 `pending`，所有 `license_expression_id` 均为 `null`。本包不构成授权、许可证解释、兼容性或合规结论。
- v3 不替换 B02 所冻结的 v2 检测输入；接入 B02 前须另行冻结适配器和评审契约。

`approved-archive-observations.json` 仅从既有 v1 固定 archive observations 引用四条已获许可的
License/NOTICE/copyright/source relationship 事实。它保存 source path、archive locator、内容与容器
Hash、来源版本和关系状态，但**不**保存 NOTICE 正文或 excerpt；`license_expression_id` 继续为 null，
许可证观察绝不被当作 NOTICE 正文或适用性结论。

## source-binding-r2 的生成与交接

```powershell
node tests/fixtures/notice-license-facts-v3/generate.mjs --check
node --test tests/notice_license_facts_v3.test.mjs tests/notice_license_facts_v3_revision.test.mjs
```

`--check` 验证修订的 facts/amendment/manifest 三个工件；`--stdout` 只读输出修正版。
不带参数时仅允许首次创建新修订，已存在则拒绝覆盖，根目录旧包始终不改。
Git 读取只接受完整 commit SHA 和安全相对路径，禁用对象替换及缺失对象自动联网获取；
普通 blob 身份/字节复验后才解析，不执行工程代码、Maven、npm 或远程来源。

`amendment.json` 绑定旧包与新包的 raw/canonical SHA，列出 8 项具体修正与下游失效要求。
`manifest.json` 固定 15 个来源文件的同一 Git commit、大小/Hash及工件摘要。
原 31 个 facts、关系/gap、31 项选定字段 Hash均保持；生成器版本更新为 3.0.1。
HF manifest 的来源版本现在也明确绑定同一 Git commit，provider Evidence 中的上游 revision
仍只是固定 fixture 声明，不提升为独立上游签收。

新包的独立审核、真人批准和 A 终态回执均为空。A 必须显式使用新 canonical package SHA
建立新 facts/Assessment/NOTICE/Draft/Report 绑定；不能静默替换旧 BOUND 或历史报告。
来源修正不改变 pending/许可证/授权语义，也不替代正式 Gold、性能或前端验收。
