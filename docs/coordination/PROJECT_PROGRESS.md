# OpenGuard 项目进度台账

更新时间：2026-09-04 18:36（Asia/Shanghai）

维护规则：每个任务点通过模型收工、Root 验收、测试、目录检查、提交和 GitHub 推送后更新。状态只使用 `已完成`、`进行中`、`未开始`、`阻塞`。完成度以可复现证据为准，不以代码行数估算。

优先级口径：本台账当前展示的是截至提交日必须闭合的 **P0 竞赛主线**，尚未建立产品功能的 P1/P2 增强路线表。共享日志中出现的 P1/P2 通常表示缺陷严重度（P1 阻止任务证据批准，P2 为非阻断债务），不能与产品路线优先级混用。

## 0. 真人责任边界（模型角色不能替代真人主责）

| 真人角色 | 负责范围 | 本轮处理 |
|---|---|---|
| 项目负责人（用户） | A1 领域、A2 输入、A3 API/注册表、A4 Pipeline、A5 AI Provider、A6 报告、A7 部署、A8 集成与材料 | 本轮只推进项目负责人 A6-1 报告安全持久化与只读下载；不实现 B5，不修改 B1-B7、Pipeline 或前端，不合并既有 PR |
| 扫描分析组员 | B1-B7：依赖解析、ScanCode、Syft、SPDX、许可证规则、AI 资产检测与 Bench 基础 | 本轮未修改；远端 B2/B3 分支新提交保持组员在途状态 |
| 前端组员 | React/Vite 与 New Scan、Progress、Dashboard、Risk Detail、Resource List、Report 页面 | 本轮未修改；远端前端分支新提交保持组员在途状态 |

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
| A3-1 FastAPI Git API 纵切 | P0 | Root→Luna→Sol | 已完成 | FastAPI 六路由、Git queued 持久幂等、结果读取/过滤与统一脱敏错误；Luna 独立发现的404/405信封、控制字符、UTF-8字节上限三项P1已最小关闭；A3-1实现+独立48项、A3-0 77项、P0 46项、全量549项通过；真实Uvicorn 202/200并可重启读取；证据绑定 `aedf65c` | A3父任务仍缺ZIP multipart、安全Git物化、worker与A4编排；结果读取只消费已有终态ScanRun，不生成结果；本机证据不得外推Linux/TrustedEgress或完整扫描 | 已推送 `feat/a3-fastapi-api`；实现/独立证据 `aedf65c`，绑定 `68163de`；待PR合并 |
| A4-0 显式单进程 Pipeline Worker | P0 | Sol→Terra→Luna→Root | 已完成 | 七阶段/固定进度、A3 CAS认领、Adapter聚合持久化、completed/partial/failed/cancelled与脱敏错误；Terra 21项、Luna独立25项，A4合计46项；Root定向169项、完整集合595项通过；`EVD-A4-PIPELINE-WORKER-001` 已绑定 `66fc2ae`；无开放P0/P1/P2 | A4父任务仍缺真实Adapter接线、API队列自动消费、重试/超时、lease/heartbeat、stale-running恢复与系统集成；stub结果不得外推真实扫描 | 已推送 `feat/a4-pipeline-worker`；实现证据 `66fc2ae`；待PR合并 |
| A4-1 本地 ZIP 依赖 Pipeline 接线 | P0 | Sol→Terra→Root→Luna→Root | 已完成 | 本地 ZIP 经单次 A2 只读会话调用既有 B1 Python/JavaScript parser/mapper，持久化真实 P0 Component/Evidence、digest、producer与summary；规则未接线时诚实为partial；实现29项、Luna独立20项、A4-1合计49项、完整集合644项通过；`EVD-A4-LOCAL-ZIP-DEPENDENCY-PIPELINE-001` 已绑定 `fbed364`，无开放P0/P1/P2 | A4父任务继续接许可证规则、API/后台消费、AI与报告；A4-1不包含这些能力 | 已推送 `feat/a4-local-zip-pipeline`；待PR合并 |
| A3-2 ZIP HTTP 与进程内后台扫描 | P0 | Sol/Root→Luna→Root | 已完成 | 同一 POST 路径支持 Git JSON 与 ZIP multipart；请求/上传限额、私有暂存、摘要/幂等、queued→BackgroundTask→A4-1、清理与 OpenAPI 已实现；实现20项、Luna独立22项、完整集合等价686项通过；`EVD-A3-ZIP-BACKGROUND-SCAN-001` 已绑定 `530e930`，无开放P0/P1/P2 | `partial/rules/70` 表示依赖结果可用、规则待接入；A3父任务仍缺公开 Git 物化和持久队列/恢复 | 已推送 `feat/a3-zip-background-scan`；待PR合并 |
| A5-0 可注入 AI Provider 与降级核心 | P0 | Sol→Terra/Root→Luna→Root | 已完成 | local/remote 统一接口、finding/evidence/license canonical 输入、64 KiB 严格 JSON、引用/敏感门禁、pending Remediation、稳定 ID、P0 入口重校验与 generated/skipped/disabled/degraded 原子语义；实现30项、Luna独立16项、完整非回环734项通过；`EVD-A5-AI-PROVIDER-001` 绑定 `2c824bf` | A5父任务继续 A5-1：真实 Qwen3/Ollama transport、超时、A4 AI_ASSIST 接线与消融；必须消费组员 B5 的真实 finding，不代做规则 | 已推送；PR #2 待团队审核 |
| A5-1a Qwen3/Ollama 本地 Transport | P0 | Sol→Terra/Root→Luna→Root | 已完成 | 锁定 Ollama `0.33.3`、Qwen3 4B Instruct Q4_K_M 与完整 manifest；字面量回环、禁代理、版本/模型摘要校验、三步 HTTP、总 deadline、严格封装和稳定降级；实现60项、Luna独立17项，A5组合123项、完整非回环794项通过；`EVD-A5-OLLAMA-TRANSPORT-001` 绑定 `e4d8e2e` | A5-1b 已另行闭环；A5-1c 等待组员 B5 真实 finding 后再接 A4，不代做规则 | 已推送 `feat/a5-ollama-transport`；PR #2 待团队审核 |
| A5-1b Ollama/Qwen3 本机真实运行 | P0 | Sol→Terra/Root→Luna→Root | 已完成 | 官方 Ollama `0.33.3` DMG 的 SHA-256、Developer ID、Gatekeeper、公证与 arm64 均通过；锁定 Qwen3 manifest/API/disk/blob 摘要一致；Root 探针与 Luna 独立脚本各完成真实 `3/3`，冷轮约 4.34/3.88 秒、热轮约 2.73/2.77 秒，均验证 generated、pending、来源绑定、事实保持和稳定 ID；加载约 3.175 GB、100% GPU、context 4096；runtime probe unit `5 passed`、A5 `128 passed`、全量 `818 passed`；`EVD-A5-OLLAMA-REAL-RUN-001` 已绑定不可变实现 `ca0c3ed` | 仅为当前 Apple-silicon 和单一样例实测，不是 Bench；A5-1c 必须等待扫描组员 B5 提供真实 finding/license facts 后再接 A4 AI_ASSIST，不代做规则 | 已推送 `feat/a5-ollama-transport`；PR #2 待团队审核 |
| A6-0 确定性报告导出核心 | P0 | Terra/Root | 已完成 | 终态 `ScanRun` 可导出稳定 JSON、竞赛七字段 CSV/资源清单和安全静态 HTML；`partial/rules/70` 明示规则缺失；专项 `12 passed`、A6+P0 `58 passed`、受控全量 `830 passed`，Schema/compileall/静态门禁通过；实现 `fda4ce6` | 内存核心由 A6-1 继续消费；完整许可证内容仍等待 B5 事实 | 已推送 `feat/a6-report-export-core`，远端实现 HEAD 已核对 |
| A6-1 报告安全持久化与只读下载 | P0 | Terra/Root | 已完成 | 私有 `0700/0600` 内容寻址存储、原子 metadata 提交、重启/摘要/篡改验证、P0 `ReportLink`、同一冻结 GET 的只读下载和安全响应头已实现；A6-1 `16 passed`、A6+A3 定向 `51 passed`、P0联合 `97 passed`、受控全量 `846 passed` | A6-2 再接 Pipeline REPORT 与终态 link 一致性；前端接线归前端组员；完整许可证报告继续等待 B5 | `feat/a6-report-delivery` 待不可变提交与推送；候选 `EVD-A6-REPORT-DELIVERY-001` |
| A8-1a P0团队集成基线 | P0 | Root/Sol | 已完成 | `integration/p0` 已汇合项目负责人六层后端纵切、前端组员壳和扫描组员B2/B3 Adapter候选；后端688项非回环+2项真实回环通过，前端锁文件供应链检查和生产构建通过；Schema不变；`EVD-P0-TEAM-INTEGRATION-001` 绑定 `f486ead` | 前端仍为mock；B2/B3仍缺本机真实工具和主链接线；不外推完整产品 | 已推送 `integration/p0`；团队后续从此创建短分支 |
| A8-1b 冗余远端分支清理 | P0治理 | Root | 阻塞 | 已证明13个旧项目负责人任务分支均被 `integration/p0` 完整包含且零独有提交；组员两分支明确排除 | 远端删除被安全审批拒绝，需用户明确批准下方13个具体分支；本轮没有删除任何分支 | 待用户确认；不影响 `integration/p0` 使用 |
| A8-1c A5 团队集成 PR | P0治理 | Root/Sol | 进行中 | 隔离 worktree 合并无冲突；沙箱原样 `807 passed, 11 failed, 1 warning` 的 11 项均为回环 bind 权限限制，受控环境原样 `818 passed, 1 warning`；P0 `46 passed`，Schema、compileall、diff、敏感/路径/大文件/上传范围门禁通过；PR #2 已创建且 GitHub 显示可自动合并 | 等待团队代码审核与明确合并决定；本任务不自动请求组员评审、不自动合并 | [PR #2](https://github.com/mumingce-star/OpenGuard/pull/2) 已打开，base=`integration/p0`、head=`feat/a5-ollama-transport` |
| A8-1d VS Code 本机复现演示 | P0治理 | Root/Sol | 已完成 | Python 3.12.14 启动 FastAPI；动态 ZIP POST `202`，SQLite 终态 `partial/rules/70`，得到 React/FastAPI/Pydantic 3 个组件和 3 条 verified evidence；Ollama/Qwen3 聚合探针 `2/2` 且全部校验通过；Vite 页面可见并明确 `MOCK MODE` | 演示只覆盖当前可验证纵切；A5 尚未接 Pipeline，前端尚未接真实 API，许可证规则仍依赖 B5 | 治理证据已推送当前 PR 分支；临时脚本、ZIP、SQLite、prompt/response 未上传 |
| F0-0 前端应用壳 | P0 | 前端组员→Root验证 | 进行中 | React/Vite/Tailwind应用壳、基础页面与动效已由组员提交；Root按锁文件安装并完成TypeScript+Vite生产构建 | 当前仍使用mock，未接真实API；页面功能与视觉验收归前端组员 | 来源 `feat/xzb-frontend`，已纳入本地集成候选 |

## 2. P0 工作包全景

| ID | 模块 | 主责 | 状态 | 已完成 | 未完成/验收标准 | 计划阶段 |
|---|---|---|---|---|---|---|
| S0 | 竞赛要求与评分追踪 | Sol | 已完成 | 正式来源、硬约束、官方评分、提交/补正/匿名/AI披露、27项报告主张与非目标均已映射 | 随正式通知复核；真实需求、实验、用户反馈和最终链接继续保持 planned/blocked | 9月3日前 |
| S1/A1 | 领域模型与公共契约 | Sol/Terra/Luna | 已完成 | v0.1.1契约、实现、Schema、sample及46项测试完成 | 后续变更需 ADR；A2 不得破坏本契约 | 9月3日前 |
| S2 | 威胁模型与安全验收 | Sol/Terra/Luna | 进行中 | 条件性设计基线已完成：20 SEC、5 POS、36 NEG，含实现审查、可测性审计和证据模板 | 最终安全验收需在 A2 关闭 TrustedEgress、Linux profile、阈值拆分、依赖台账与全量真实测试；当前不得写成控制已生效 | 9月3日前设计，A2实现 |
| A2 | Git/ZIP安全输入与Inventory | Terra | 进行中 | A2-0/A2-1本地ZIP、A2-1D CLI、A2-2只读扫描会话已完成；A3-0已提供独立持久ScanRun/CAS底座，但尚未接HTTP输入；B1-2已证明会话可承载Python parser/mapper | 继续完成完整ZIP corpus、cleanup隔离/清道夫、本地Git物化、受控公网Git、Linux隔离、API映射与系统级证据冻结 | 9月4日-11日 |
| B1 | Python/JS依赖解析 | Terra | 进行中 | Python requirements/pyproject 与 P0 CLI 已完成；根 package.json 四类直接依赖、package-lock v2/v3 enrichment 与 JS P0 CLI 已完成；当前全量424项通过 | 选定 Python lockfile；Yarn/pnpm/workspace/传递依赖列后续增强；再进入多来源合并 | 9月4日-11日 |
| B2 | ScanCode适配器 | Terra | 进行中 | 安全 JSON 适配、超时/失败对象、许可证证据候选映射和单测已实现 | 在受控运行环境固定实际工具版本/校验并完成真实工具回归；B4 规范化候选 SPDX | 9月4日-11日 |
| B3 | Syft适配器 | Terra | 进行中 | 安全 JSON 适配、SBOM Component/Evidence 映射、跨来源合并和单测已实现 | 在受控运行环境固定实际工具版本/校验并完成真实工具回归 | 9月4日-11日 |
| B4 | SPDX标准化 | Sol/Terra | 未开始 | LicenseExpression契约已具备 | SPDX数据版本、别名、复合表达式、LicenseRef及测试 | 9月4日-20日 |
| B5/S3 | 15种许可证义务规则 | Sol/Terra/Luna | 未开始 | Obligation/RiskFinding结构已具备 | 规则Schema、原文证据、正反未知冲突样例、人工核验状态 | 9月12日-20日 |
| B6 | 模型/数据/API检测 | Terra | 未开始 | AIAsset/Evidence结构已具备 | HF/ModelScope/API/服务规则与AST检测、误报控制及证据定位 | 9月12日-20日 |
| A3 | FastAPI扫描API | 项目负责人 / Root | 进行中 | 6个端点契约、A3-0 SQLite、A3-1 Git JSON 与读取、A3-2 ZIP multipart→进程内 BackgroundTask→A4-1 均已发布并独立验证；ZIP 可产生可查询的真实依赖 partial | A3父任务仍缺公开 Git 物化、持久队列、lease/retry/recovery、ZIP 进程重启恢复 | 9月21日-28日 |
| A4 | Pipeline编排 | 项目负责人 / Terra | 进行中 | A4-0 worker 与 A4-1 真实 ZIP 依赖接线已完成；A3-2 已在本地证明 HTTP ZIP 可触发进程内后台 A4-1 并产生可查询 partial；A5-0、A5-1a 与 A5-1b 均已完成但 AI 尚未接线；A6-0/A6-1 已可渲染、持久化和下载显式发布的终态报告 | 等待并消费组员 B5 的真实许可证规则，再接 A5 AI_ASSIST；A6-2 仍需 Pipeline REPORT Adapter 与终态 link 一致性；另需持久后台消费、超时/重试、lease/heartbeat、stale-running恢复和端到端证据 | 9月21日-28日 |
| A5/S4 | AI Provider与降级 | Sol/Terra/Luna | 进行中 | A5-0 可注入 Provider、A5-1a 回环 transport 与 A5-1b 官方 Ollama/Qwen3 本机真实运行均已完成；真实探针与独立脚本各 `3/3`，摘要、pending、来源、事实和稳定身份通过；受控 A5 `128 passed`、全量 `818 passed` | A5-1c 等待 B5 的真实 finding/license facts 后接 A4，并完成 AI 开关消融；A5-1b 单一样例不得外推为多项目质量 | 9月12日-28日 |
| F0 | P0前端核心页面 | Terra/团队前端 | 进行中 | React/Vite/Tailwind 应用壳已提交并通过锁文件安装、TypeScript与Vite生产构建 | 当前仍为mock；继续完成 New Scan、Progress、Dashboard、Risk Detail、Resource List、Report 的真实API接线 | 9月21日-28日 |
| A6 | HTML/JSON/CSV与资源清单 | 项目负责人 / Terra/Luna | 进行中 | A6-0 四格式确定性渲染与 A6-1 私有文件持久化、`ReportLink`、FastAPI 只读下载已完成；`partial/rules/70` 诚实披露；受控全量 `846 passed` | A6-2 Pipeline REPORT/终态 link 一致性、前端下载接线和最终匿名化验收；完整许可证内容仍需消费 B5 事实 | 9月21日-28日 |
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
| 2026-09-03 | A3-1 FastAPI Git API 纵切 | `feat/a3-fastapi-api` | `aedf65c`（独立复核/P1闭环实现；绑定 `68163de`） | FastAPI应用、六路由、Git queued 创建、状态/结果读取、统一错误、23项实现测试、25项Luna独立测试、规格/运行/AI/协作与进度说明 | 已推送；待PR合并 |
| 2026-09-03 | A4-0 显式单进程 Pipeline Worker | `feat/a4-pipeline-worker` | `66fc2ae`（不可变实现/独立证据；首轮发布 `b6311be`） | Pipeline worker、冻结规格、21项实现测试、25项Luna独立测试、运行/安全/AI/协作与进度说明 | 已推送；待PR合并 |
| 2026-09-03 | A4-1 本地 ZIP 依赖 Pipeline 接线 | `feat/a4-local-zip-pipeline` | `fbed364`（不可变实现/独立证据；绑定 `d79da6e`） | A4-1 pipeline/export、冻结规格、29项实现测试、20项Luna独立测试、运行/安全/AI/协作与进度说明 | 已推送；待PR合并 |
| 2026-09-03 | A3-2 ZIP HTTP 与进程内后台扫描 | `feat/a3-zip-background-scan` | `530e930`（不可变实现/独立证据；绑定 `bca0a2c`） | ZIP multipart API/runtime、进程内后台 A4-1、20项实现测试、22项Luna独立测试、精确依赖锁定及运行/安全/AI/协作与进度说明 | 已推送；待PR合并 |
| 2026-09-03 | A8-1a P0团队集成基线 | `integration/p0` | `f486ead`（首次验收发布HEAD） | 项目负责人后端纵切、前端组员应用壳、扫描组员B2/B3 Adapter候选、集成测试与分支治理说明 | 已推送；作为团队当前开发入口 |
| 2026-09-04 | A5-0 可注入 AI Provider 与降级核心 | `feat/a5-ai-provider` | `2c824bf`（不可变实现/独立证据） | A5 Provider、冻结规格、30项实现测试、16项Luna独立测试、P1闭环及根/后端/安全/AI/协作说明 | 已推送；待PR合并 |
| 2026-09-04 | A5-1a Qwen3/Ollama 本地 Transport | `feat/a5-ollama-transport` | `e4d8e2e`（不可变实现/独立证据） | 标准库 Ollama adapter、冻结规格、60项实现测试、17项Luna独立 TCP 测试、第三方资源锁定、运行/安全/AI/协作说明 | 已推送；待PR合并 |
| 2026-09-04 | A5-1b Ollama/Qwen3 本机真实运行 | `feat/a5-ollama-transport` | `ca0c3ed`（不可变实现/真实运行证据）；`26ebdc8`（治理记录） | 聚合 runtime probe、5项unit、官方运行时/模型摘要与本机聚合实测记录；不含安装包、权重、prompt 或完整 response | 已推送；远端已核对；不创建/合并PR |
| 2026-09-04 | A8-1c A5 团队集成 PR | `feat/a5-ollama-transport` → `integration/p0` | `ea2f45c`（创建 PR 时的远端 HEAD；后续治理提交自动进入同一 PR） | 已验收的 A5-0/A5-1a/A5-1b 实现、测试、规格与证据；不含 B4-B7、前端、安装包、模型权重或缓存 | [PR #2](https://github.com/mumingce-star/OpenGuard/pull/2) 已打开、无冲突、可自动合并；待审核，未合并 |
| 2026-09-04 | A8-1d VS Code 本机复现演示 | `feat/a5-ollama-transport` | `44c8cf1`（运行证据；本发布修正随后一并推送） | 仅运行证据、AI 辅助记录和协作日志；不含仓库外启动脚本、运行数据库、ZIP、模型内容或业务代码改动 | 已推送并进入 PR #2；演示终态保持 `partial/rules/70` 与前端 mock 边界 |
| 2026-09-04 | A6-0 确定性报告导出核心 | `feat/a6-report-export-core` | `fda4ce6`（不可变实现/测试/证据） | A6 报告源码、12项专项测试、规格、复现说明、AI/协作/进度记录；不含 B5、前端、临时环境或产物文件 | 已推送；远端完整对象 `fda4ce6ba4361efaa3dcdba2a04aae6cf6067338` 已核对；未创建/合并 PR |
| 2026-09-04 | A6-1 报告持久化与只读下载 | `feat/a6-report-delivery` | 待不可变实现提交 | 内容寻址私有存储、原子 metadata、ReportLink、同一路由只读下载、16项专项测试、规格与治理记录；不含生成报告文件、B5、Pipeline 或前端 | 发布前门禁通过，待提交和推送；未创建/合并 PR |

## 3.1 当前远端分支入口

- 团队日常入口：`integration/p0`；里程碑发布目标：`main`。
- 项目负责人当前短分支：`feat/a6-report-delivery`，堆叠于已发布 A6-0；A5 的 [PR #2](https://github.com/mumingce-star/OpenGuard/pull/2) 仍提交到 `integration/p0`，完成审核并获明确合并决定后再纳入集成线。A6-1 尚未创建或合并 PR。
- 组员在途分支：`feat/xzb-frontend`、`codex/p0-external-tools-sync`，均保留。
- 待明确授权清理的项目负责人历史分支：`feat/p0-domain-contract`、`feat/s0-s2-design-gates`、`feat/a2-zip-ingestion`、`feat/a2-zip-cli-demo`、`feat/a2-readonly-scan-session`、`feat/b1-python-manifest-parser`、`feat/b1-p0-mapper-cli`、`feat/b1-js-manifest-p0-cli`、`feat/a3-durable-scan-registry`、`feat/a3-fastapi-api`、`feat/a4-pipeline-worker`、`feat/a4-local-zip-pipeline`、`feat/a3-zip-background-scan`。
- 上述待清理分支的提交均已从 `integration/p0` 可达，删除分支引用不会删除集成线中的代码和证据；未获明确授权前保持现状。

## 4. 目录健康检查

| 检查项 | 当前状态 | 规则 |
|---|---|---|
| 顶层目录 | 通过 | 使用既有工程目录，不新增含糊或重复目录 |
| 临时环境/缓存 | 通过（Git层） | `.pytest_cache`、`__pycache__`、虚拟环境不纳入提交 |
| 竞赛原始附件 | 通过 | 原始PDF/DOCX不复制进公开仓库，正式要求以脱敏规范文档表达 |
| 敏感信息 | A6-1 候选发布复核通过 | 不上传密钥、账号、本机绝对路径、学校/教师/成员隐私 |
| 第三方资源 | 持续 | 首次真实引入时锁版本并更新 `third_party/` 与资源清单 |
