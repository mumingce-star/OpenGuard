# OpenGuard 项目进度台账

更新时间：2026-09-02 13:48（Asia/Shanghai）

维护规则：每个任务点通过模型收工、Root 验收、测试、目录检查、提交和 GitHub 推送后更新。状态只使用 `已完成`、`进行中`、`未开始`、`阻塞`。完成度以可复现证据为准，不以代码行数估算。

## 1. 当前任务点

| 任务点 | P级 | 主责模型 | 状态 | 已完成/当前证据 | 未完成/下一步 | GitHub状态 |
|---|---|---|---|---|---|---|
| S1a/A1 P0领域契约 | P0 | Sol | 已完成 | 契约 v0.1.1、唯一公共模型、6个API、风险四态、证据与provenance；历史提交 `02c3d46` | 后续仅通过变更流程新增 ADR，不再并行维护第二套模型 | 已推送 `feat/p0-domain-contract` |
| A1 领域模型实现 | P0 | Terra | 已完成 | Pydantic模型、Draft 2020-12 Schema、sample和 AI producer 条件字段；历史提交 `b2fd061` | 进入 A2 前保持兼容性回归 | 已推送 `feat/p0-domain-contract` |
| L-A1 独立边界审计 | P0 | Luna | 已完成 | 46项测试全部通过；覆盖路径脱敏、partial语义及 AI producer 正反边界 | 进入 A2 后扩展输入安全测试 | 已推送 `feat/p0-domain-contract` |
| A1.1 AI ProducerRef | P0 | Sol→Terra→Luna | 已完成 | `provider`、`model_id`、`prompt_schema_digest` 已完成契约、实现、Schema、sample和独立测试闭环 | 后续变更走 ADR 和回归门禁 | 已推送 `43493fb` |
| 协作与发布治理 | P0 | Root | 已完成 | 进度表、目录规则、统一验收、每任务点GitHub推送和上传范围复核已固化 | 每个后续任务点持续执行 | 已推送 `43493fb` |
| S0 竞赛规则与评分证据治理 | P0 | Sol→Root | 已完成 | 三份正式文件映射、官方100分评分追踪、提交清单、九章27项主张与非目标已形成 | 随竞赛通知变更复核；最终材料仍需按证据状态逐项冻结 | 已推送 `ffa9390` |
| S2 条件性安全设计基线 | P0 | Sol→Terra→Luna | 已完成 | 20项安全控制、5项正向/36项负面设计；Terra 12/6/2实现审查与Luna逐项可测性审计完成 | 这只是设计任务完成；TrustedEgress、Linux profile、依赖台账和真实运行证据归 A2，不能声称控制已生效 | 已推送 `ffa9390` |
| A2-0/A2-1 本地 ZIP 安全纵切 | P0 | Terra→Luna→Sol→Root | 已完成 | 服务端限额/POSIX能力探测、descriptor-safe流式解压、central/local header核验、稳定inventory/root digest与失败清理；独立36项、Terra 19项、P0 46项、全量101项通过；`EVD-A2-ZIP-IMPL-001` 已绑定 `53499ea` | A2总包仍缺完整ZIP corpus、inventory并发完整性、cleanup隔离、Git/TrustedEgress、Linux profile、registry/API映射；本地绿灯不得外推 | 已推送 `53499ea`；待PR合并 |
| A2-1D 本地 ZIP CLI 演示 | P0 | Terra→Luna→Sol→Root | 进行中 | `python -m app.cli LOCAL_ZIP` 已实现稳定 JSON、0/1/2 退出语义、错误脱敏和临时清理；Terra 5项、Luna独立5项、当前全量111项通过；Sol实现终审通过，文档追踪阻塞已由 Luna 更正关闭 | Root 正在真实复跑、冻结提交和 `verified-local-demo` 证据；这不是完整Web、依赖/许可证扫描或A2总门禁 | 本地分支 `feat/a2-zip-cli-demo`；待提交推送 |

## 2. P0 工作包全景

| ID | 模块 | 主责 | 状态 | 已完成 | 未完成/验收标准 | 计划阶段 |
|---|---|---|---|---|---|---|
| S0 | 竞赛要求与评分追踪 | Sol | 已完成 | 正式来源、硬约束、官方评分、提交/补正/匿名/AI披露、27项报告主张与非目标均已映射 | 随正式通知复核；真实需求、实验、用户反馈和最终链接继续保持 planned/blocked | 9月3日前 |
| S1/A1 | 领域模型与公共契约 | Sol/Terra/Luna | 已完成 | v0.1.1契约、实现、Schema、sample及46项测试完成 | 后续变更需 ADR；A2 不得破坏本契约 | 9月3日前 |
| S2 | 威胁模型与安全验收 | Sol/Terra/Luna | 进行中 | 条件性设计基线已完成：20 SEC、5 POS、36 NEG，含实现审查、可测性审计和证据模板 | 最终安全验收需在 A2 关闭 TrustedEgress、Linux profile、阈值拆分、依赖台账与全量真实测试；当前不得写成控制已生效 | 9月3日前设计，A2实现 |
| A2 | Git/ZIP安全输入与Inventory | Terra | 进行中 | A2-0运行前置与A2-1本地ZIP最小纵切已完成；A2-1D CLI 演示已实现并经 Terra/Luna/Sol 复核，当前全量111项通过 | 继续完成完整ZIP corpus、inventory并发完整性、cleanup隔离/清道夫、本地Git物化、受控公网Git、Linux隔离与系统级证据冻结 | 9月4日-11日 |
| B1 | Python/JS依赖解析 | Terra | 未开始 | 统一Component契约已具备 | requirements/pyproject/package.json/package-lock解析、fixtures、去重 | 9月4日-11日 |
| B2 | ScanCode适配器 | Terra | 未开始 | 第三方候选已登记 | 锁定版本、超时/失败对象、License/Evidence映射及测试 | 9月4日-11日 |
| B3 | Syft适配器 | Terra | 未开始 | 第三方候选已登记 | 锁定版本、SBOM映射、与解析器结果合并及测试 | 9月4日-11日 |
| B4 | SPDX标准化 | Sol/Terra | 未开始 | LicenseExpression契约已具备 | SPDX数据版本、别名、复合表达式、LicenseRef及测试 | 9月4日-20日 |
| B5/S3 | 15种许可证义务规则 | Sol/Terra/Luna | 未开始 | Obligation/RiskFinding结构已具备 | 规则Schema、原文证据、正反未知冲突样例、人工核验状态 | 9月12日-20日 |
| B6 | 模型/数据/API检测 | Terra | 未开始 | AIAsset/Evidence结构已具备 | HF/ModelScope/API/服务规则与AST检测、误报控制及证据定位 | 9月12日-20日 |
| A3 | FastAPI扫描API | Terra | 未开始 | 6个端点契约已冻结；Root决定 durable task registry 归入 A3 前置 | 持久任务注册表、跨worker/重启幂等、OpenAPI、统一错误、状态与资源/风险/证据/报告接口 | 9月21日-28日 |
| A4 | Pipeline编排 | Terra | 未开始 | ScanRun状态机已具备 | ingestion→scan→normalize→rules→AI→report，阶段错误与partial | 9月21日-28日 |
| A5/S4 | AI Provider与降级 | Sol/Terra/Luna | 未开始 | AI边界与A1.1字段方案已确定 | Qwen3/Ollama锁版、结构化输出、证据引用、失败降级、消融 | 9月12日-28日 |
| F0 | P0前端核心页面 | Terra/团队前端 | 未开始 | sample可作为共同数据 | New Scan、Progress、Dashboard、Risk Detail、Resource List、Report接真实API | 9月21日-28日 |
| A6 | HTML/JSON/CSV与资源清单 | Terra/Luna | 未开始 | ScanRun与ReportLink结构已具备 | 报告模板、七字段资源清单映射、导出验证与脱敏 | 9月21日-28日 |
| S5/B7 | OpenGuard-Bench | Sol/Luna/Terra | 未开始 | 只有A1边界fixture，不等于Bench | 3-5个首批case→20-30公开仓库、50-100合成样例、指标/基线/消融 | 9月29日-10月5日 |
| A7 | Docker与一键部署 | Terra | 未开始 | deploy目录说明存在 | Compose、固定镜像版本、陌生机器复现与Demo仓库全链 | 9月21日-10月5日 |
| S7/L10/L11 | 技术报告与材料证据 | Sol/Luna | 未开始 | 交接文档已有九章/匿名/资源表规则 | 证据映射、15页报告、3-5分钟视频、资源表、AI记录、匿名审计 | 10月6日-13日 |
| FINAL | 提交前审计与上传 | Sol/Root/全员 | 未开始 | GitHub公开仓库已建立 | 100分模拟评审、链接/部署/视频复核、10月14日正式上传 | 10月11日-14日 |

## 3. GitHub 发布记录

| 日期 | 任务点 | 分支 | 提交 | 上传范围 | 状态 |
|---|---|---|---|---|---|
| 2026-09-01 | 仓库基础骨架 | `main` | `476d954`及以前 | README、协作、安全、目录骨架、交接与第三方工作区 | 已在GitHub |
| 2026-09-01 | S1a/A1/A1.1 | `feat/p0-domain-contract` | `43493fb`（首轮发布HEAD） | 契约、领域模型、Schema、sample、测试、治理与进度文档 | 已推送；待PR合并 |
| 2026-09-02 | S0/S2设计门禁 | `feat/s0-s2-design-gates` | `ffa9390`（首轮发布HEAD） | 正式规则/评分/提交/报告证据/非目标、威胁模型、安全验收、实现审查、测试审计及协作记录 | 已推送；待PR合并 |
| 2026-09-02 | A2-0/A2-1 本地 ZIP 安全纵切 | `feat/a2-zip-ingestion` | `53499ea`（实现证据提交） | ZIP安全输入实现、实现侧与独立测试、终审、AI记录、协作日志和进度 | 已推送；待PR合并 |

## 4. 目录健康检查

| 检查项 | 当前状态 | 规则 |
|---|---|---|
| 顶层目录 | 通过 | 使用既有工程目录，不新增含糊或重复目录 |
| 临时环境/缓存 | 通过（Git层） | `.pytest_cache`、`__pycache__`、虚拟环境不纳入提交 |
| 竞赛原始附件 | 通过 | 原始PDF/DOCX不复制进公开仓库，正式要求以脱敏规范文档表达 |
| 敏感信息 | 本轮推送复核通过 | 不上传密钥、账号、本机绝对路径、学校/教师/成员隐私 |
| 第三方资源 | 持续 | 首次真实引入时锁版本并更新 `third_party/` 与资源清单 |
