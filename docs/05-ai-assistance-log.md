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
| 2026-09-02 | GPT-5.6 Sol | 逐页核验三份正式竞赛 PDF，并基于冻结 P0 v0.1.1 设计 S0 评分证据治理与 S2/A2 安全门禁 | 竞赛要求、评分追踪、提交清单、九章证据映射、P0 非目标、威胁模型和 `SEC-A2-*` 验收基线 | 明确区分硬约束/评分/建议/内部决策；删除无证据效果主张；默认限额均标为尚未实现；不进入 A2 代码、不改变公共 Schema/API | PDF 全文/表格/逐页渲染核验；跨文档 ID/状态、来源页码、Markdown、敏感信息、本机路径和 `git diff --check`；待 Terra 可实现性和 Luna 负面测试独立审计 | 是 |
| 2026-09-02 | GPT-5.6 Terra | 从主线实现角度审查 S2 的 20 项 A2 安全验收，不编写 A2 业务代码 | 可实现性结论、模块边界、Linux 部署前置条件、错误/清理映射和未来测试接口 | 未修改公共 Schema/API 或 Sol 安全语义；将 Git DNS-to-connect/transfer 配额和扫描器隔离标为部署级阻塞或修订建议 | 文档交叉引用、SEC 覆盖、Markdown、敏感信息/绝对路径与 diff 检查；未运行 A2 安全实现测试 | 是 |
| 2026-09-02 | GPT-5.6 Sol | 根据 Terra 可实现性审查精确回修 A2 设计，不进入代码或 fixture | 直接 Git 零重定向、TrustedEgress 字节/连接证据、Linux 完成 profile、实际供应链范围、durable registry 条件和 ZIP 未知属性策略 | 保持 P0 v0.1.1、20 个 SEC、5 个 POS、36 个 NEG 不变；报告证据明确 Terra 已审、Luna 待审；未把设计或审查写成实现效果 | 审查文档逐项映射、SEC/POS/NEG 计数、`git diff --check`、敏感信息/绝对路径检查；A2 实现和 Luna 独立审计仍待执行 | 是 |
| 2026-09-02 | GPT-5.6 Luna | 独立审计 A2 POS/NEG 设计的可测性、边界、错误/状态、真实集成和证据条件 | `docs/security/a2-test-audit.md`：逐 ID 判定、阈值拆分、TrustedEgress/Linux/durable registry 阻塞项、fixture 授权匿名脱敏模板与 S2 冻结结论 | 未修改 A2 实现、fixture、公共 Schema/API、PROJECT_PROGRESS 或安全语义文档；明确本轮未运行 A2 实现测试 | 文档交叉核对 Terra 12 ACCEPT/6 ADJUST/2 BLOCK 与 Sol 回修；ID/状态/Markdown/diff/敏感信息/绝对路径检查已完成 | 是 |
| 2026-09-02 | GPT-5.6 Terra | 在冻结 A2 安全基线内实现本地 ZIP 安全输入纵切；输入为 A2 验收、实现审查和既有 P0 代码，不读取或运行不可信目标仓库内容 | POSIX 能力失败关闭、服务器端 ZIP 限额、dirfd workspace、ZIP 路径/类型/配额预检、流式物化、稳定 inventory/root digest 和实现侧动态 ZIP 测试 | 未修改 P0 v0.1.1 Schema/API、sample 或 Sol 规范；普通未知 ZIP 属性只作为新普通文件字节，未恢复元数据；不实现 Git、TrustedEgress、Linux 隔离或 durable registry | 聚焦 A2 ZIP pytest 16/16、全量 pytest 62/62；人工复核 root digest 字节格式、成功/失败清理与稳定错误 code/reason；后续由 Luna 独立扩展 TOCTOU、ZIP64/header corpus 和 Linux/egress 证据 | 是 |
| 2026-09-02 | GPT-5.6 Luna | 独立运行 A2-0/A2-1 本地 ZIP 安全测试；仅使用现有实现与安全验收作为输入，不修改 Terra backend 或既有 unit 测试 | `tests/security/test_a2_zip_security_independent.py` 与 `tests/security/README.md`：标准库动态 ZIP、ZIP64/data descriptor/header、路径/类型/配额/清理/inventory/no-follow 边界 | 保留按冻结 reason 断言的失败测试，不为通过而放宽期望；未修改 P0 模型、Schema/sample、backend、既有 tests 或 PROJECT_PROGRESS | 独立测试 35 项：21 passed、14 failed；全量 97 项：83 passed、14 failed。失败已按稳定 reason 漂移和 local/central header mismatch 分类升级；`git diff --check`、敏感信息和绝对路径检查待本轮收尾完成；未运行目标项目代码 | 是 |
| 2026-09-02 | GPT-5.6 Luna | 按 Sol 裁决复测 A2-0/A2-1；仅将深度/UTF-8 路径长度两项测试 code 期望改为 `archive_limit_exceeded`，复核 Terra 的 13 项 reason 与 local/central header 修复 | 保留同一标准库动态 ZIP、ZIP64/data descriptor/header 与文件系统安全测试；未新增不透明 fixture | 未修改 backend、Terra unit、P0/Schema/sample 或 PROJECT_PROGRESS；未弱化安全边界 | 独立测试 `35 passed`；Terra ZIP unit `18 passed`；当前全量 `99 passed`；排除 Terra 本轮新增 2 项单测后，历史可比的 97 项为 `97 passed`、`2 deselected`；`git diff --check`、敏感信息和绝对路径检查随后完成 | 是 |
| 2026-09-02 | GPT-5.6 Luna | 独立补测 SEC-A2-009 home shorthand 路径边界；仅增加首段 `~`/`~user` 拒绝与后续普通文件名波浪号允许的安全回归 | `tests/security/test_a2_zip_security_independent.py` 新增动态 ZIP/ inventory 用例；无第三方或不透明二进制 fixture | 未修改 backend、Terra unit、P0/Schema/sample 或 PROJECT_PROGRESS；不扩大“仅首段”窄规则 | 独立测试 `36 passed`；Terra ZIP unit `19 passed`；当前全量 `101 passed`；P0 `46 passed`；`git diff --check`、尾随空白、敏感信息与本机绝对路径检查通过 | 是 |

记录原则：

- 不记录密钥、账号、未公开代码或个人信息；
- 说明模型参与环节，不把 AI 生成内容当然视为团队知识产权；
- 代码必须记录测试、人工审查或修改；
- 报告和图表必须核对原始数据；
- 最终整理为技术报告中的“AI 工具使用说明”。

## 追加记录

| 日期 | 工具/模型 | 任务 | 产出 | 人工复核与边界 | 验证方式 | 已脱敏 |
|---|---|---|---|---|---|---|
| 2026-09-02 | GPT-5.6 Terra | 修复 Luna A2 ZIP 独立测试揭示的稳定错误契约和 local/central header 完整性问题 | 统一重复、特殊类型和七类配额的内部 `code/reason`；加入 local header、ZIP64 尺寸与数据描述符交叉校验；补充实现侧回归和模块说明 | 未修改 Luna 独立测试、P0 Schema/sample 或 PROJECT_PROGRESS；路径深度和长度以冻结验收的 `archive_limit_exceeded` 为准，故 Luna 当前两个 `invalid_archive` 期望保留为契约冲突 | Terra ZIP 18/18；Luna 独立 33/35；全量 97 passed、2 failed；P0 Schema/sample/export 等值、diff、敏感信息与本机绝对路径检查 | 是 |
| 2026-09-02 | GPT-5.6 Sol | 终审 A2-0/A2-1 本地 ZIP 实现、冻结错误语义和证据边界 | 最小澄清 `SEC-A2-009` 的 invalid/limit 分流；新增模块映射、支持矩阵、测试演进、复现命令和待 Root 分配实现证据位的审计材料 | 未修改 backend、测试、P0 Schema/sample/API 或 PROJECT_PROGRESS；将 `~`、完整 ZIP corpus、inventory 并发改写和清理隔离列为开放差异，未把 99 项绿灯外推为 A2 总门禁完成 | 全量与聚焦 pytest、P0 零差异、稳定 ID、diff、敏感信息及本机绝对路径检查；`EVD-S2-DESIGN-001` 仅作设计追溯 | 是 |
| 2026-09-02 | GPT-5.6 Terra | 修复 Sol 终审指出的 `SEC-A2-009` home shorthand 缺口 | 首段 `~` 或 `~user` 失败关闭为 `invalid_archive/archive_path_unsafe`；`ordinary/file~.txt` 保持允许；补充实现侧回归和说明 | 未修改 Luna 独立测试、P0 Schema/sample、公开 API 或 PROJECT_PROGRESS；Luna 尚未覆盖此新增边界，须后续独立补测 | Terra ZIP 19/19、Luna 独立 35/35、全量 100/100、P0 46/46、Schema/sample/export 等值、diff 与敏感信息/绝对路径检查 | 是 |
| 2026-09-02 | GPT-5.6 Sol | 刷新 A2 ZIP 终审材料以接入 home shorthand 修复与独立回归闭环 | 将首段 `~`/`~user` 从开放差异移为已关闭，保留 21/14→35/0 历史链并追加当前 36/101 口径 | 未修改 backend、tests、P0 Schema/sample/API 或 PROJECT_PROGRESS；完整 ZIP corpus、inventory 并发、清理隔离和系统级门禁继续开放 | 文档计数/开放项一致性、diff、尾随空白、敏感信息与本机绝对路径检查；候选实现 evidence 仍待 Root 分配 | 是 |
