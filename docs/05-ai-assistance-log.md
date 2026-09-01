# AI 辅助开发记录

竞赛要求披露生成式 AI、智能体或自动化工具在代码、内容和报告中的用途，以及团队的审核、修改和验证工作。本文件从项目第一天开始维护。

| 日期 | 模型/工具 | 用途与输入范围 | 产生内容 | 团队修改 | 验证方式 | 是否纳入作品 |
|---|---|---|---|---|---|---|
| 2026-08-31 | GPT-5.6 Sol | 竞赛规则、架构和评分拆解 | 项目总体框架初稿 | 团队后续确认范围 | 对照正式附件逐项核对 | 是 |
| 2026-09-01 | GPT-5.6 Sol / Codex Root | 解析技术执行书并与正式材料、既有架构交叉核对 | P0 领域与 API 契约 v0.1.0 | 项目负责人需审核公共字段；Terra/Luna分别做实现与独立验证 | Markdown/敏感信息检查，后续以 Pydantic、JSON Schema 和负面 fixture 交叉验证 | 是 |
| 2026-09-01 | GPT-5.6 Terra | 仅使用冻结的 P0 契约 v0.1.0 实现领域模型、Schema、样例和单测 | Pydantic v2 领域模型、导出 JSON Schema、合成扫描样例与 11 项聚焦测试 | 未改变公共字段、枚举、风险语义或契约；AI 建议/候选保持待核验 | Pydantic、独立 JSON Schema、pytest、差异与敏感信息检查 | 是 |
| 2026-09-01 | GPT-5.6 Terra / Codex Root | 按冻结契约实现 A1 Pydantic 模型、Schema、样例和负面测试 | `backend/app/domain`、导出 Schema、sample 与 11 个单元测试 | Root 在隔离环境复核依赖与测试；Luna 后续独立审计边界 fixture | pytest 11/11、Pydantic/JSON Schema 双验证、Schema 导出一致性、敏感信息与 diff 检查 | 是 |
| 2026-09-01 | GPT-5.6 Luna | 独立审计 A1 P0 领域契约边界，生成聚焦测试、最小公开 fixture 和复现说明 | 跨对象引用、partial/error、locator、错误脱敏、AI pending、summary、终态时间、未知字段及公开材料检查 | 未修改公共契约或 backend；保留两项稳定实现失败，待 Terra 修复并由 Luna 回归 | pytest 33 项中 31 通过、2 项实现缺陷失败；sample Pydantic/JSON Schema 双验证与模型导出一致性通过；公开 fixture 敏感信息检查通过 | 是 |
| 2026-09-01 | GPT-5.6 Luna | 独立复核 Terra A1-fix1，验证两项运行时修订未改变公共 Schema | partial 必须含 recoverable error；Unix/Windows/UNC 路径拒绝；HTTPS 正常文本保留；Schema 导出一致和 fixture 去敏复核 | 未修改 backend、公共契约或测试预期；AI ProducerRef 字段缺口仍待 Sol 冻结 | 全量 pytest 33/33；独立 Pydantic/JSON Schema、路径/HTTPS 非回归、`git diff --check` 和公开 fixture 扫描均通过 | 是 |
| 2026-09-01 | GPT-5.6 Terra | 基于 Luna 的两项稳定 A1 边界失败，修复冻结 P0 模型的运行时语义校验 | `partial` 需包含可恢复结构化错误；错误消息拒绝嵌入式 Unix/Windows 绝对路径与凭据片段 | 仅修改 `backend/app/domain/models.py` 的内部验证逻辑；未变更字段、枚举或导出 Schema | 完整 pytest 33/33；存储 Schema 等于 `ScanRun.model_json_schema()`；人工路径边界、diff 与敏感信息扫描 | 是 |
| 2026-09-01 | GPT-5.6 Sol / Codex Root | 根据项目负责人确认冻结 AI producer 字段，并固化进度、目录与 GitHub 发布规则 | P0 契约 v0.1.1、跨模型协作规则、项目进度台账 | 项目负责人明确批准三个字段；Terra/Luna继续实现与独立验证 | 契约差异审查、全量测试、Schema一致性、目录/敏感信息和 GitHub 待提交清单检查 | 是 |
| 2026-09-01 | GPT-5.6 Terra | 实现已冻结的 v0.1.1 AI `ProducerRef` 条件字段，并重导公开 Schema | `provider`、`model_id`、`prompt_schema_digest` 的模型约束、合成 sample 版本迁移和 10 项字段边界测试 | 仅实现已批准字段；sample 保持 `ai_enabled=false`，不伪造产品 AI 运行事实 | 全量 pytest 43/43；Pydantic/JSON Schema/sample 三重验证；Schema 导出一致、diff 与敏感信息检查 | 是 |
| 2026-09-01 | GPT-5.6 Luna | 独立回归 A1.1 AI `ProducerRef` 三字段、sample v0.1.1 与公开材料边界 | 完整字段有效、逐字段缺失、非 AI 显式 null/携带字段、空白/凭据、无效 SHA-256、AI provenance 及版本事实测试 | 未修改 backend、契约、Schema 或 sample；将进度文档中的匿名化规则词条与实际身份信息区分 | 全量 pytest 46/46；Pydantic/Draft 2020-12、Schema 导出一致、fixture/进度文档凭据和本机路径扫描、`git diff --check` 均通过 | 是 |

记录原则：

- 不记录密钥、账号、未公开代码或个人信息；
- 说明模型参与环节，不把 AI 生成内容当然视为团队知识产权；
- 代码必须记录测试、人工审查或修改；
- 报告和图表必须核对原始数据；
- 最终整理为技术报告中的“AI 工具使用说明”。
