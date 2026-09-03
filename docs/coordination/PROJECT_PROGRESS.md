# OpenGuard 项目进度台账

更新时间：2026-09-03 11:09（Asia/Shanghai）

维护规则：每个任务点通过模型收工、Root 验收、测试、目录检查、提交和 GitHub 推送后更新。状态只使用 `已完成`、`进行中`、`未开始`、`阻塞`。完成度以可复现证据为准，不以代码行数估算。

优先级口径：本台账当前展示的是截至提交日必须闭合的 **P0 竞赛主线**，尚未建立产品功能的 P1/P2 增强路线表。共享日志中出现的 P1/P2 通常表示缺陷严重度（P1 阻止任务证据批准，P2 为非阻断债务），不能与产品路线优先级混用。

## 0. 真人责任边界（模型角色不能替代真人主责）

| 真人角色 | 负责范围 | 本轮处理 |
|---|---|---|
| 项目负责人（用户） | A1 领域、A2 输入、A3 API/注册表、A4 Pipeline、A5 AI Provider、A6 报告、A7 部署、A8 集成与材料 | 仅推进其 A3-0 持久 ScanRun 注册表 |
| 扫描分析组员 | B1-B7：依赖解析、ScanCode、Syft、SPDX、许可证规则、AI 资产检测与 Bench 基础 | 本轮不修改；既有 B1 分支归该角色复核/接续 |
| 前端组员 | React/Vite 与 New Scan、Progress、Dashboard、Risk Detail、Resource List、Report 页面 | 本轮不修改 |

Sol/Terra/Luna 是 Codex 的设计、实现、独立测试角色，不代表三位真人的任务归属。后续选题必须先按上表确定真人主责，再分派模型。

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
| A2-1D 本地 ZIP CLI 演示 | P0 | Terra→Luna→Sol→Root | 已完成 | `python -m app.cli LOCAL_ZIP` 已实现稳定 JSON、0/1/2 退出语义、错误脱敏和临时清理；Terra 5项、Luna独立5项、当前全量111项通过；Sol终审与追踪更正闭环；`EVD-A2-ZIP-CLI-001` 绑定 `910f745` | 这不是完整Web、依赖/许可证扫描或A2总门禁；后续由A2/B1等任务继续 | 已推送 `feat/a2-zip-cli-demo`；待PR合并 |
| A2-2 安全只读扫描会话 | P0 | Sol→Terra/Root→Luna→Sol→Root | 已完成 | 生命周期绑定 `ReadOnlyScanSession`、inventory 精确白名单、逐层 dirfd/no-follow identity seal、SHA-256 前后复验、2 MiB/16 MiB 默认配额、过期/线程/重入/异常/cleanup 失败关闭；Luna 独立46项、定向unit42项、全量175项、P0 46项通过；`EVD-A2-READONLY-SESSION-001` 已绑定 `1f03ce0` | 仅允许可信非执行性 parser；完整ZIP corpus、cleanup worker/orphan、Git/TrustedEgress、Linux profile、registry/API、B1和A2总门禁仍未完成 | 已推送 `feat/a2-readonly-scan-session`；待PR合并 |
| B1-1 Python manifest 解析纵切 | P0 | Sol→Terra→Luna→Sol→Root | 已完成 | 仅通过只读会话发现/解析 `requirements*.txt`、`pyproject.toml`；PEP 508/440、字段/行级证据草稿、确定性去重/冲突/partial、URL与配额门禁；Terra 40项、Luna独立63项、全量278项、P0 46项通过；`EVD-B1-PYTHON-MANIFEST-001` 已绑定 `7c0d365` | B1-2 已另行闭环；JS/TS与lockfile仍未开始 | 已推送 `feat/b1-python-manifest-parser`；待PR合并 |
| B1-2 Python P0映射与CLI纵切 | P0 | Sol→Terra→Luna→Sol→Root | 已完成 | 冻结DTO映射为P0 `Component/Evidence`；UUIDv5稳定ID、证据定位/哈希/时间、exact pin、direct/VCS、partial诊断、固定时钟与旧CLI兼容；Sol终审发现并关闭2项P1；Terra 45项、Luna独立32项、全量355项、P0 46项通过；`EVD-B1-PYTHON-P0-CLI-001` 已绑定 `daee8a8` | B1总包下一步进入 JS/TS manifest 与选定 lockfile；本纵切不代表许可证、依赖求解或完整报告 | 已推送 `feat/b1-p0-mapper-cli`；待PR合并 |
| B1-3/B1-4 JavaScript manifest、P0与CLI | P0 | Sol/Root→Terra→Luna→Terra→Luna→Root | 已完成 | 支持根 `package.json` 四类直接依赖与 `package-lock.json` v2/v3 enrichment；严格JSON、稳定Evidence/UUID/purl/URL、partial与新CLI；Luna首次发现5项P1，连同Root 4类探针均已关闭；Terra 37项、Luna独立32项、JS合计69项、全量424项通过；`EVD-B1-JAVASCRIPT-P0-CLI-001` 已绑定 `80ee2a9` | B1仍缺选定Python lockfile、Yarn/pnpm/workspace/传递依赖；本纵切不代表许可证或安装事实 | 已推送 `feat/b1-js-manifest-p0-cli`；待PR合并 |
| A3-0 持久 ScanRun 注册表 | P0 | Sol→Terra→Luna→Terra→Luna→Sol→Root | 已完成 | 单机 POSIX SQLite canonical ScanRun、revision/CAS、跨实例/重启幂等、状态单向性、稳定分页、私有路径权限、损坏Schema与额外table/view/trigger失败关闭；两轮审计P1均已关闭；Terra32项、Luna45项、A3合计77项、全量501项通过；`EVD-A3-DURABLE-SCAN-REGISTRY-001` 已绑定 `d2b26b0` | A3仍缺FastAPI、OpenAPI、HTTP错误映射、ZIP/Git创建请求、worker与A4编排；不得外推多机容灾或exactly-once副作用 | 已推送 `feat/a3-durable-scan-registry`；实现 `d2b26b0`，证据 `0cadbbe`；待PR合并 |
| A3-1 FastAPI Git API 纵切 | P0 | Root | 已完成 | FastAPI 应用工厂、六条冻结 OpenAPI 业务路径、Git JSON 创建、SQLite queued 持久化/幂等、状态与结果读取、资源/风险过滤、统一脱敏错误；A3-1 17项、A3/P0联合140项、全量518项通过；真实 Uvicorn 返回202并在重启后读到同一 queued记录；本机证据绑定 `b8d3b63` | A3父任务仍缺ZIP multipart、安全Git物化/worker与A4编排；结果读取只消费已有终态 ScanRun，不生成结果；最终报告证据仍待独立复核 | 已推送 `feat/a3-fastapi-api`；实现 `b8d3b63`，绑定 `53c196f`；待PR合并 |

## 2. P0 工作包全景

| ID | 模块 | 主责 | 状态 | 已完成 | 未完成/验收标准 | 计划阶段 |
|---|---|---|---|---|---|---|
| S0 | 竞赛要求与评分追踪 | Sol | 已完成 | 正式来源、硬约束、官方评分、提交/补正/匿名/AI披露、27项报告主张与非目标均已映射 | 随正式通知复核；真实需求、实验、用户反馈和最终链接继续保持 planned/blocked | 9月3日前 |
| S1/A1 | 领域模型与公共契约 | Sol/Terra/Luna | 已完成 | v0.1.1契约、实现、Schema、sample及46项测试完成 | 后续变更需 ADR；A2 不得破坏本契约 | 9月3日前 |
| S2 | 威胁模型与安全验收 | Sol/Terra/Luna | 进行中 | 条件性设计基线已完成：20 SEC、5 POS、36 NEG，含实现审查、可测性审计和证据模板 | 最终安全验收需在 A2 关闭 TrustedEgress、Linux profile、阈值拆分、依赖台账与全量真实测试；当前不得写成控制已生效 | 9月3日前设计，A2实现 |
| A2 | Git/ZIP安全输入与Inventory | Terra | 进行中 | A2-0/A2-1本地ZIP、A2-1D CLI、A2-2只读扫描会话已完成；A3-0已提供独立持久ScanRun/CAS底座，但尚未接HTTP输入；B1-2已证明会话可承载Python parser/mapper | 继续完成完整ZIP corpus、cleanup隔离/清道夫、本地Git物化、受控公网Git、Linux隔离、API映射与系统级证据冻结 | 9月4日-11日 |
| B1 | Python/JS依赖解析 | Terra | 进行中 | Python requirements/pyproject 与 P0 CLI 已完成；根 package.json 四类直接依赖、package-lock v2/v3 enrichment 与 JS P0 CLI 已完成；当前全量424项通过 | 选定 Python lockfile；Yarn/pnpm/workspace/传递依赖列后续增强；再进入多来源合并 | 9月4日-11日 |
| B2 | ScanCode适配器 | Terra | 未开始 | 第三方候选已登记 | 锁定版本、超时/失败对象、License/Evidence映射及测试 | 9月4日-11日 |
| B3 | Syft适配器 | Terra | 未开始 | 第三方候选已登记 | 锁定版本、SBOM映射、与解析器结果合并及测试 | 9月4日-11日 |
| B4 | SPDX标准化 | Sol/Terra | 未开始 | LicenseExpression契约已具备 | SPDX数据版本、别名、复合表达式、LicenseRef及测试 | 9月4日-20日 |
| B5/S3 | 15种许可证义务规则 | Sol/Terra/Luna | 未开始 | Obligation/RiskFinding结构已具备 | 规则Schema、原文证据、正反未知冲突样例、人工核验状态 | 9月12日-20日 |
| B6 | 模型/数据/API检测 | Terra | 未开始 | AIAsset/Evidence结构已具备 | HF/ModelScope/API/服务规则与AST检测、误报控制及证据定位 | 9月12日-20日 |
| A3 | FastAPI扫描API | Terra | 进行中 | 6个端点契约已冻结；A3-0 SQLite注册表已闭环；A3-1 已实现FastAPI/OpenAPI、统一HTTP错误、Git JSON创建以及状态/资源/风险/证据/报告读取；全量518项通过，真实Uvicorn 202/200与重启读取通过 | 仍缺ZIP multipart创建、A2安全摄取接线和worker；stage编排归A4。当前只能创建并查询queued，不能宣称已扫描 | 9月21日-28日 |
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
| 2026-09-02 | A2-1D 本地 ZIP CLI 演示 | `feat/a2-zip-cli-demo` | `910f745`（实现证据提交） | CLI、Terra/Luna两组测试、运行说明、终审/AI/协作/进度与源文档上传忽略规则 | 已推送；待PR合并 |
| 2026-09-02 | A2-2 安全只读扫描会话 | `feat/a2-readonly-scan-session` | `1f03ce0`（证据实现HEAD；主体`abb6630`） | 只读会话、identity/hash seal、descriptor回收、限额、规格、Terra/Root unit、Luna独立测试、审计、AI/协作/进度和运行说明 | 已推送；待PR合并 |
| 2026-09-02 | B1-1 Python manifest 解析纵切 | `feat/b1-python-manifest-parser` | `7c0d365`（证据实现提交；绑定`bb83e6b`） | Python parser、依赖锁版/台账、40项实现测试、63项独立测试、规格/审计/运行说明、AI/协作与进度记录 | 已推送；待PR合并 |
| 2026-09-02 | B1-2 Python P0映射与CLI纵切 | `feat/b1-p0-mapper-cli` | `daee8a8`（不可变实现提交；绑定提交`69ca38c`） | Python P0 mapper、新依赖CLI、45项实现测试、32项独立测试、规格/终审、运行说明、AI/协作与进度记录 | 已推送；待PR合并 |
| 2026-09-02 | B1-3/B1-4 JavaScript manifest、P0与CLI | `feat/b1-js-manifest-p0-cli` | `80ee2a9`（不可变实现提交；绑定提交`708bc08`） | JS parser、P0 mapper、JS CLI、37项实现测试、32项独立测试、规格/缺陷闭环、运行说明与协作证据 | 已推送；待PR合并 |
| 2026-09-03 | A3-0 持久 ScanRun 注册表 | `feat/a3-durable-scan-registry` | `d2b26b0`（不可变实现提交；绑定提交 `0cadbbe`） | SQLite registry、32项实现测试、45项独立测试、冻结规格、两项P1闭环、运行/AI/协作说明与真人责任边界 | 已推送；待PR合并 |
| 2026-09-03 | A3-1 FastAPI Git API 纵切 | `feat/a3-fastapi-api` | `b8d3b63`（不可变实现提交；本机绑定 `53c196f`） | FastAPI应用、六路由、Git queued 创建、状态/结果读取、统一错误、17项测试、规格/依赖/运行/AI/协作与进度说明 | 已推送；待独立复核与PR合并 |

## 4. 目录健康检查

| 检查项 | 当前状态 | 规则 |
|---|---|---|
| 顶层目录 | 通过 | 使用既有工程目录，不新增含糊或重复目录 |
| 临时环境/缓存 | 通过（Git层） | `.pytest_cache`、`__pycache__`、虚拟环境不纳入提交 |
| 竞赛原始附件 | 通过 | 原始PDF/DOCX不复制进公开仓库，正式要求以脱敏规范文档表达 |
| 敏感信息 | 本轮推送复核通过 | 不上传密钥、账号、本机绝对路径、学校/教师/成员隐私 |
| 第三方资源 | 持续 | 首次真实引入时锁版本并更新 `third_party/` 与资源清单 |
