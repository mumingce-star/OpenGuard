# OpenGuard 项目进度台账

更新时间：2026-09-01 23:48（Asia/Shanghai）

维护规则：每个任务点通过模型收工、Root 验收、测试、目录检查、提交和 GitHub 推送后更新。状态只使用 `已完成`、`进行中`、`未开始`、`阻塞`。完成度以可复现证据为准，不以代码行数估算。

## 1. 当前任务点

| 任务点 | P级 | 主责模型 | 状态 | 已完成/当前证据 | 未完成/下一步 | GitHub状态 |
|---|---|---|---|---|---|---|
| S1a/A1 P0领域契约 | P0 | Sol | 已完成 | 契约 v0.1.1、唯一公共模型、6个API、风险四态、证据与provenance；历史提交 `02c3d46` | 后续仅通过变更流程新增 ADR，不再并行维护第二套模型 | 本分支待推送 |
| A1 领域模型实现 | P0 | Terra | 已完成 | Pydantic模型、Draft 2020-12 Schema、sample和 AI producer 条件字段；历史提交 `b2fd061` | 进入 A2 前保持兼容性回归 | 本分支待推送 |
| L-A1 独立边界审计 | P0 | Luna | 已完成 | 46项测试全部通过；覆盖路径脱敏、partial语义及 AI producer 正反边界 | 进入 A2 后扩展输入安全测试 | 本分支待推送 |
| A1.1 AI ProducerRef | P0 | Sol→Terra→Luna | 已完成 | `provider`、`model_id`、`prompt_schema_digest` 已完成契约、实现、Schema、sample和独立测试闭环 | Root提交并推送后登记远端提交 | 待推送 |
| 协作与发布治理 | P0 | Root | 已完成 | 进度表、目录规则、统一验收、每任务点GitHub推送和上传范围复核已固化 | 每个后续任务点持续执行 | 待推送 |

## 2. P0 工作包全景

| ID | 模块 | 主责 | 状态 | 已完成 | 未完成/验收标准 | 计划阶段 |
|---|---|---|---|---|---|---|
| S0 | 竞赛要求与评分追踪 | Sol | 进行中 | 已有评委章程、架构、资源、模型路由、交付计划 | 补 competition requirements、scoring traceability、submission checklist、report evidence map、non-goals | 9月3日前 |
| S1/A1 | 领域模型与公共契约 | Sol/Terra/Luna | 已完成 | v0.1.1契约、实现、Schema、sample及46项测试完成 | 后续变更需 ADR；A2 不得破坏本契约 | 9月3日前 |
| S2 | 威胁模型与安全验收 | Sol/Luna | 未开始 | README已有安全原则 | 威胁模型、ZIP穿越/炸弹/SSRF/命令注入/脱敏负面要求 | 9月3日前设计，A2实现 |
| A2 | Git/ZIP安全输入与Inventory | Terra | 未开始 | 仅有契约与安全边界 | 浅克隆、安全解压、文件/大小限制、SHA256、临时目录生命周期及测试 | 9月4日-11日 |
| B1 | Python/JS依赖解析 | Terra | 未开始 | 统一Component契约已具备 | requirements/pyproject/package.json/package-lock解析、fixtures、去重 | 9月4日-11日 |
| B2 | ScanCode适配器 | Terra | 未开始 | 第三方候选已登记 | 锁定版本、超时/失败对象、License/Evidence映射及测试 | 9月4日-11日 |
| B3 | Syft适配器 | Terra | 未开始 | 第三方候选已登记 | 锁定版本、SBOM映射、与解析器结果合并及测试 | 9月4日-11日 |
| B4 | SPDX标准化 | Sol/Terra | 未开始 | LicenseExpression契约已具备 | SPDX数据版本、别名、复合表达式、LicenseRef及测试 | 9月4日-20日 |
| B5/S3 | 15种许可证义务规则 | Sol/Terra/Luna | 未开始 | Obligation/RiskFinding结构已具备 | 规则Schema、原文证据、正反未知冲突样例、人工核验状态 | 9月12日-20日 |
| B6 | 模型/数据/API检测 | Terra | 未开始 | AIAsset/Evidence结构已具备 | HF/ModelScope/API/服务规则与AST检测、误报控制及证据定位 | 9月12日-20日 |
| A3 | FastAPI扫描API | Terra | 未开始 | 6个端点契约已冻结 | OpenAPI、统一错误、状态查询、资源/风险/证据/报告接口 | 9月21日-28日 |
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
| 2026-09-01 | S1a/A1/A1.1 | `feat/p0-domain-contract` | 待本轮提交 | 契约、领域模型、Schema、sample、测试、治理与进度文档 | 待推送 |

## 4. 目录健康检查

| 检查项 | 当前状态 | 规则 |
|---|---|---|
| 顶层目录 | 通过 | 使用既有工程目录，不新增含糊或重复目录 |
| 临时环境/缓存 | 通过（Git层） | `.pytest_cache`、`__pycache__`、虚拟环境不纳入提交 |
| 竞赛原始附件 | 通过 | 原始PDF/DOCX不复制进公开仓库，正式要求以脱敏规范文档表达 |
| 敏感信息 | 待每次推送复核 | 不上传密钥、账号、本机绝对路径、学校/教师/成员隐私 |
| 第三方资源 | 持续 | 首次真实引入时锁版本并更新 `third_party/` 与资源清单 |
