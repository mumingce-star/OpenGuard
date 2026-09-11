# OpenGuard 项目进度台账

## 2026-09-10 23:05 诊断记录发布

用户授权将此前仅保存在本地的Docker状态更正、扫描耗时分析、B4–B7/前端核查上传GitHub。Root仅发布本进度、共享日志及AI记录三份文档到codex/scan-reliability-integration；目标分支fetch后与本地基线82c16d1一致。产品代码与main不变，测试失败和人工待验门禁保留；提交及推送回执追加于本轮收工记录。

发布回执：7504b5e已普通推送成功，三份文档69行新增；差异检查、敏感模式检查和清单审阅通过。累计调查记录已上传，未关闭B4/B5衔接、Linux/浏览器闭环与人工复核；本回执另随文档提交推送。负责人Root；下一步Terra/Luna/Sol按核查建议继续，上传不等于产品验收。

2026-09-10 21:07，Root/GPT-6扫描耗时只读分析：5611c00代码确认ScanCode/Syft串行、ScanCode总预算360秒及有限逐文件补扫、AI分组串行且每次30秒、进程内缓存及API2CPU/4GiB限制。历史耗时不是当前慢任务实测；本机无运行容器，缺用户任务阶段数据，实际主因待定位。未修改产品或实施性能优化，仅三份本地协作记录，不推送；下一步收集一条实际慢任务后由Root定向分析。

## 2026-09-10 20:42 Docker状态复核（Root/GPT-6，以此为当前环境状态）

只读实测Engine已恢复，Server29.7.2、linux/amd64、WSL内核6.18.33.2；日志20:34起有engine is running。本轮未实施修复，恢复触发未知；先前阻塞记录是历史结果。docker ps -a及compose ls为空，8081拒绝连接，现在缺少的是OpenGuard构建启动和后续真实扫描验收。暂不需要安全模式/重装；Root下一步按用户部署指令使用5611c00副本与8081运行现有验收。当前仅更新三份本地诊断记录，不推送；不改产品或系统，未将Engine可用当成异机通过。

## 2026-09-10 Windows异机实测（19:53，Root/GPT-6）

用户已确认当前Windows就是异机，无需再提供另一台设备。固定团队集成版5611c00独立副本，源码未改；Compose静态检查通过，真实up退出1（Docker Engine管道缺失），smoke退出1（首个网页请求10061），尚未提交扫描。异机验收状态为阻塞，不是通过；Git/ZIP、工具输出、报告及重建仍未执行。详见[异机实测回执](2026-09-10-windows-portability-acceptance.md)。

累计Python/pnpm/WSL等工具可用不等于完整Web可演示；Root后续在引擎恢复后续测，用户仅需配合本机Docker恢复。报名资格/权属、完整交付闭环、独立评测竞争力门禁保持待验。四份验收/协作文档经审查发布当前功能分支，测试副本和环境产物不上传，main不变。

## 2026-09-10 代码同步（19:50，Root/GPT-6）

- 本轮完成：fetch成功；当前codex/scan-reliability-integration在f7308ed执行pull --ff-only返回Already up to date，上游0/0。协作记录随后单独提交推送该分支。
- 团队更新：origin/integration/p0已获取至5611c00（原e323509）；没有切换、合并或更新手册固定副本，新功能未在本轮运行验收。
- 累计/未完成：此前工具安装和局部扫描验证保持历史状态；Docker系统阻塞、完整部署、真实扫描报告与异机、竞赛材料和独立评测门禁未由本次Git同步关闭。下一步由用户选择团队分支切换或集成，Root执行。
- GitHub范围：仅本日志状态、共享工作日志、AI记录三份文档；main和产品源码未改。

## 2026-09-10 重启后环境配置（以本节为最新状态）

| 范围 | 状态/验证 | 责任与下一步 |
|---|---|---|
| 本轮完成 | WSL2.7.13.0官方签名MSI安装退出0，内核6.18.33.2-2；两个Windows组件均已启用 | Root保留版本回执 |
| 累计工具 | Python3.12.10、Node26.2.0、pnpm10.30.0可用；Docker/Compose已安装，配置静态验证通过 | 安装不等于Engine可用 |
| Docker阻塞 | 第一个残留套接字目录已备份；第二个engine.sock错误1920，管理员目录改名仍被拒绝，Handle未发现占用 | 用户配合安全模式/离线诊断，Root随后继续；未自动重启或重置 |
| 网页入口 | 8080被其他程序占用；本机启动助手配置8081，目前正式网页未启动 | Docker恢复后Root验证8081真实页面 |
| 未完成 | Compose构建/健康、真实Git/ZIP、四报告/持久化、异机回执 | Root及第二机器操作者逐项实测 |
| GitHub | 本轮五份环境/协作文档在当前功能分支检查后提交推送，最终SHA见Git；本机工具不上传 | main仍须PR |

详见[环境续配回执](2026-09-10-environment-followup.md)。历史Mock演示和局部扫描测试不能当成本轮完整部署。报名资格/权属、完整交付闭环、独立评测质量门禁均未由环境安装自动关闭。

## 2026-09-09 按说明书安装部署

| 项目 | 实际状态 | 下一步/责任 |
|---|---|---|
| 说明书指定源码 | 已固定450b8ebe3381a6a27ca333ed78c9a7ad572ba65b，独立部署副本干净 | Root继续使用该版本，保留开发分支 |
| Docker安装 | Desktop4.90.0、CLI29.7.2、Compose5.5.1已安装并验证；签名Valid | 用户保存工作并重启Windows |
| WSL/虚拟机平台 | DISM启用成功，明确Reboot required=yes | 重启后Root复验WSL运行时与Linux引擎 |
| Compose | 静态配置通过，默认api/web；引擎stopped，hello-world失败 | 引擎就绪后Root构建并验证真实扫描/报告 |

详见[本轮部署回执](2026-09-09-manual-deployment.md)。当前8080正式服务尚未运行，不把5173演示页当作部署成功。本轮仅公开五份文档/台账，源码副本与安装产物保持忽略。

2026-09-09 网页协议排障（Root/GPT-6）：HTTP localhost:5173/app/new-scan成功，Chrome独立环境实际渲染工作台，已用Edge打开正确HTTP地址；HTTPS同端口失败，Vite只提供HTTP。未改变浏览器安全策略或业务代码；真实API/异机验收未由本轮完成，三份协作记录发布当前功能分支。

2026-09-09 本机演示启动（Root/GPT-6）：当前功能分支前端Vite已在 `http://127.0.0.1:5173/` 后台运行，首页与 `/app/new-scan` 实测HTTP200。仅Mock演示，非真实扫描或异机验收；无产品文件变更，本轮上传三份协作记录。

2026-09-09 Git拉取复核（Root/GPT-6）：截图在父级独立master仓库执行，未使用子项目已配置的SSH443。进入实际OpenGuard仓库执行 `git pull --ff-only` 成功，当前分支与上游0/0；父级仓库保留。团队integration/p0已更新至e323509，本轮未合并/复验其产品功能；仅上传三份协作记录。

## 2026-09-09 前后端与异机核查

| 范围 | 状态与证据 | 下一步/责任 |
|---|---|---|
| 当前开发分支 `d2ffe4c` | 真实接线未完成：Mock前端构建通过，HTTP API路径返回HTML；后端67项局部回归通过，但正常ZIP受Windows POSIX门禁拒绝 | Root/主线实现审查集成差异；测试通过不等于HTTP闭环 |
| 团队集成版 `5ad0073` | 代码已含真实API、前端请求及Compose；共同验收源码固定 `b86658e`，本轮仅静态审查 | 使用该固定源码独立部署，避免从旧本地分支验收 |
| 异机运行 | 阻塞：本机Docker/WSL未就绪，第二机器执行条件/回执尚缺 | 设备操作者准备环境；Root核验实际Git/ZIP、报告及重建回执 |

本轮仅发布四份协作/诊断文档，详情见[联调与异机报告](2026-09-09-connectivity-portability-audit.md)。未改变产品代码或main，未将远端历史实测算作本轮异机通过。

## 2026-09-09 GitHub 连接复核

- Root（GPT-6）：当前仓库 origin 已关联 `git@github.com:mumingce-star/OpenGuard.git`。默认 SSH 22 连接失败，改用仓库级 GitHub SSH 443 后实际读取通过，严格主机密钥校验保留。
- 分支 `codex/scan-reliability-integration` 的本轮起始本地/远端 HEAD 均为 `be855ac`；本轮上传范围仅连接验收的工作日志、进度与 AI 记录。产品实现和竞赛门禁沿用下方历史记录，本轮未复验。

## 2026-09-06 真实样例与评测证据更新

| 工作包 | 状态 | 新增可复现证据 | 仍未关闭的门禁 |
|---|---|---|---|
| B6 | 进行中 | 5 个版本化源代码样例（模型、数据集、API、ModelScope、负样例）；真实 detector 输出含 AIAsset、Evidence locator 与 SHA-256；已修复 HF 数据集 URL 被重复识别为模型的问题 | AST、误报基线、人工许可/授权核验与 A4 接入 |
| B7 | 进行中 | `benchmarks/run_static_assets.py` 从 case 运行 detector，`evaluate_scan_result` 从实际 JSON 计算 TP/FP/FN；记录输出哈希与运行命令 | 3–5 个独立项目或固定公开提交、双人标注、Linux ZIP 全链路、规模化公开仓库 |
| Python 运行时 | 已完成 | 本机 Python 3.12.10 与 `.venv` 已恢复，`backend[dev]` / pytest 8.4.2 可运行 | 不纳入 Git；使用 `py -3.12` 或 `.venv\\Scripts\\python.exe` |
| 本机开发工具 | 进行中 | pnpm 10.30.0 已通过 Node.js 全局安装并可执行；Docker Desktop 官方安装器正在下载 | Docker Desktop 仍须下载完成；当前会话无 Windows 管理员提升权限，WSL/VirtualMachinePlatform 启用与重启后 Docker daemon/Compose 验收尚未关闭 |
| 当前集成分支发布 | 已完成 | `codex/scan-reliability-integration` 已推送至 GitHub，首个远端 HEAD 为 `c0e8ca1`；上传范围仅为既有源码历史和协作记录 | 待以 PR 审查后合并；Docker/WSL、A2-A7 安全整合与真实 Compose 验收不因本次推送而完成 |

更新时间：2026-09-04 10:45（Asia/Shanghai）

维护规则：每个任务点通过模型收工、Root 验收、测试、目录检查、提交和 GitHub 推送后更新。状态只使用 `已完成`、`进行中`、`未开始`、`阻塞`。完成度以可复现证据为准，不以代码行数估算。

优先级口径：本台账当前展示的是截至提交日必须闭合的 **P0 竞赛主线**，尚未建立产品功能的 P1/P2 增强路线表。共享日志中出现的 P1/P2 通常表示缺陷严重度（P1 阻止任务证据批准，P2 为非阻断债务），不能与产品路线优先级混用。

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

## 2. P0 工作包全景

| ID | 模块 | 主责 | 状态 | 已完成 | 未完成/验收标准 | 计划阶段 |
|---|---|---|---|---|---|---|
| S0 | 竞赛要求与评分追踪 | Sol | 已完成 | 正式来源、硬约束、官方评分、提交/补正/匿名/AI披露、27项报告主张与非目标均已映射 | 随正式通知复核；真实需求、实验、用户反馈和最终链接继续保持 planned/blocked | 9月3日前 |
| S1/A1 | 领域模型与公共契约 | Sol/Terra/Luna | 已完成 | v0.1.1契约、实现、Schema、sample及46项测试完成 | 后续变更需 ADR；A2 不得破坏本契约 | 9月3日前 |
| S2 | 威胁模型与安全验收 | Sol/Terra/Luna | 进行中 | 条件性设计基线已完成：20 SEC、5 POS、36 NEG，含实现审查、可测性审计和证据模板 | 最终安全验收需在 A2 关闭 TrustedEgress、Linux profile、阈值拆分、依赖台账与全量真实测试；当前不得写成控制已生效 | 9月3日前设计，A2实现 |
| A2 | Git/ZIP安全输入与Inventory | Terra | 进行中 | A2-0/A2-1本地ZIP、A2-1D CLI 和 A2-2 只读扫描会话已完成；后续可信 parser 已可在清理前受限读取 inventory 文件；B1-2 已证明该会话可承载 Python parser/mapper | 继续完成完整ZIP corpus、cleanup隔离/清道夫、本地Git物化、受控公网Git、Linux隔离、registry/API与系统级证据冻结 | 9月4日-11日 |
| B1 | Python/JS依赖解析 | Terra | 进行中 | Python requirements/pyproject 与 P0 CLI 已完成；根 package.json 四类直接依赖、package-lock v2/v3 enrichment 与 JS P0 CLI 已完成；当前全量424项通过 | 选定 Python lockfile；Yarn/pnpm/workspace/传递依赖列后续增强；再进入多来源合并 | 9月4日-11日 |
| B2 | ScanCode适配器 | Terra | 进行中 | 安全 JSON 适配、描述符受控 ZIP 接入、许可证证据候选映射；2026-09-03 定向 5通过/1 Linux跳过，ScanCode 32.5.0 最小 MIT fixture 真实 JSON→Evidence 已验证 | 在 Linux 受控环境运行完整 ZIP→ScanCode 集成回归、固定运行 provenance；B4 规范化候选 SPDX | 9月4日-11日 |
| B3 | Syft适配器 | Terra | 进行中 | 安全 JSON 适配、SBOM Component/Evidence 映射、跨来源合并、密封 ZIP 调用代码；新增 Syft 1.51.0 公开 npm fixture 的真实 JSON→P0 opt-in 回归 | 在受控 Linux 环境复跑 ZIP→descriptor→Syft，固定运行 provenance/二进制校验，并接入 A4 编排入口 | 9月4日-11日 |
| B4 | SPDX标准化 | Sol/Terra | 未开始 | LicenseExpression契约已具备 | SPDX数据版本、别名、复合表达式、LicenseRef及测试 | 9月4日-20日 |
| B5/S3 | 15种许可证义务规则 | Sol/Terra/Luna | 进行中 | YAML 数据驱动 B5 引擎已覆盖 MIT、Apache-2.0、BSD-3-Clause、GPL-3.0-only、CC-BY-4.0、CC-BY-NC-4.0；有逐规则 fixture、证据门禁、稳定 Obligation/RiskFinding/Remediation 输出；2026-09-04 在恢复的 Python 3.12 `.venv` 中定向 pytest 10/10 通过 | 补齐其余常见许可证、官方原文证据台账、复合 SPDX（B4）和 A4 集成 | 9月12日-20日 |
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
| 2026-09-02 | A2-1D 本地 ZIP CLI 演示 | `feat/a2-zip-cli-demo` | `910f745`（实现证据提交） | CLI、Terra/Luna两组测试、运行说明、终审/AI/协作/进度与源文档上传忽略规则 | 已推送；待PR合并 |
| 2026-09-02 | A2-2 安全只读扫描会话 | `feat/a2-readonly-scan-session` | `1f03ce0`（证据实现HEAD；主体`abb6630`） | 只读会话、identity/hash seal、descriptor回收、限额、规格、Terra/Root unit、Luna独立测试、审计、AI/协作/进度和运行说明 | 已推送；待PR合并 |
| 2026-09-02 | B1-1 Python manifest 解析纵切 | `feat/b1-python-manifest-parser` | `7c0d365`（证据实现提交；绑定`bb83e6b`） | Python parser、依赖锁版/台账、40项实现测试、63项独立测试、规格/审计/运行说明、AI/协作与进度记录 | 已推送；待PR合并 |
| 2026-09-02 | B1-2 Python P0映射与CLI纵切 | `feat/b1-p0-mapper-cli` | `daee8a8`（不可变实现提交；绑定提交`69ca38c`） | Python P0 mapper、新依赖CLI、45项实现测试、32项独立测试、规格/终审、运行说明、AI/协作与进度记录 | 已推送；待PR合并 |
| 2026-09-02 | B1-3/B1-4 JavaScript manifest、P0与CLI | `feat/b1-js-manifest-p0-cli` | `80ee2a9`（不可变实现提交；绑定提交`708bc08`） | JS parser、P0 mapper、JS CLI、37项实现测试、32项独立测试、规格/缺陷闭环、运行说明与协作证据 | 已推送；待PR合并 |
| 2026-09-04 | B2/B3 外部扫描器 JSON 适配与跨来源合并 | `codex/p0-external-tools-sync` | `e244588`、`293c52b`、`9c504f4`、`79d887c` | 受限工具调用、ScanCode 密封 ZIP 接入、Syft 密封 ZIP 接入草案、跨来源合并与回归 | 已推送；待 PR 合并。ScanCode Linux ZIP、Syft 真实工具/fixture 与 A4 集成未完成 |

## 4. 目录健康检查

| 检查项 | 当前状态 | 规则 |
|---|---|---|
| 顶层目录 | 通过 | 使用既有工程目录，不新增含糊或重复目录 |
| 临时环境/缓存 | 通过（Git层） | `.pytest_cache`、`__pycache__`、虚拟环境不纳入提交 |

## 5. 2026-09-05 B1–B7 本轮更新

| 工作包 | 状态 | 本轮可复现证据 | 仍未关闭的门禁 |
|---|---|---|---|
| B1 | 进行中 | 原有 Python/JavaScript parser 与 mapper 定向 133 项通过；Windows 上 POSIX ZIP CLI 用例准确跳过 | Python lockfile、Yarn/pnpm/workspace、传递依赖与 Linux ZIP 链路 |
| B2/B3 | 进行中 | ScanCode 32.5.0、Syft 1.51.0 版本可用；真实输出回归 5 项通过 | POSIX descriptor ZIP→工具端到端、运行 provenance 与 A4 接入 |
| B4 | 进行中 | 显式别名/复合表达式标准化回归通过，未知值保持 pending | SPDX 官方数据版本台账、完整表达式语法及 A4 接入 |
| B5 | 进行中 | 15 条 JSON-subset YAML 规则、证据门禁与定向回归通过 | 官方原文证据台账、人工复核和 A4 接入 |
| B6 | 进行中 | 本地静态 HF/ModelScope/API 识别和 Evidence 定位回归通过 | AST 覆盖、误报评测、授权/许可证人工核验 |
| B7 | 进行中 | 版本化合成 smoke cases 与 TP/FP/FN/Precision/Recall/F1 评测器回归通过 | 3–5 个独立复现 case、人工标注、公开仓库扩展、基线/消融 |
| 竞赛原始附件 | 通过 | 原始PDF/DOCX不复制进公开仓库，正式要求以脱敏规范文档表达 |
| 敏感信息 | 本轮推送复核通过 | 不上传密钥、账号、本机绝对路径、学校/教师/成员隐私 |
| 第三方资源 | 持续 | 首次真实引入时锁版本并更新 `third_party/` 与资源清单 |

## 2026-09-10 图片五项交付核查（已获取集成版5611c00）

- 本轮只读代码与测试，未将集成版合入当前codex/scan-reliability-integration；本轮记录尚未上传。
- B4基础标准化已接入，但AGPL-3.0-only与B5规则覆盖不一致；括号/WITH未支持。B5已有15规则及fixture，B6已有静态识别和可定位证据，B7已有5个合成case的真实检测评测链；12条独立人工复核未完成。
- 后端定向54通过/1失败（Windows os.geteuid缺失，持久化初始化失败）；前端真实API代码存在，但隔离副本缺typescript导致测试未启动。本机容器与浏览器闭环仍待验收。责任建议：Terra衔接/部署，Luna回归/标注，Sol语义审核。

## 2026-09-11 扫描结果人工标签方案（设计产物）

- Root/GPT-6新增[详细方案](../spec/scan-result-human-annotation-plan.md)：五个评价维度、独立标签记录、两阶段真人复核、网页与持久化建议、指标口径、H1～H5工作包和16项验收用例。
- 已核对集成副本5611c00：真实API模式人工处理选择器禁用，不能称为已具备标签保存功能。12条候选已有机器关联检查，人工24份记录仍未由本轮填写。
- 本轮仅文档，未改变产品接口/Schema/规则，无新增依赖；方案一致性及diff检查通过，未运行业务测试、未启动服务、未提交推送。累计CLI/合成Bench及历史团队演示沿用既有证据，本机完整Web闭环未复验。
- 下一步：真人负责人/Sol冻结标签与范围，两名真人完成首批；Luna整理复核与评测，Terra实现后续保存/页面，Root验收发布。标注专项剩余5个工作包；报名资格/权属、完整交付和真实评测竞争力门禁不因方案生成而关闭。

## 2026-09-11 扫描结果AI辅助初标

- 已生成[12条初标结果](../../benchmarks/annotations/real-resource-20260911-ai-assisted/README.md)、结构化JSON、批次manifest、来源获取回执及真人待复核表，共5份文件；作者明确为GPT-6，已接触系统输出，真人0份。
- 初标范围为12条既有候选的60项判断：资源引用10正确/2部分正确，许可12不确定，风险摘要9接受/3需修改，AI建议12过于笼统；均为草稿分布，不是准确率。优先补证R08数据集标识差异、R11类型导入、R12兼容性引用。
- 上游原文12条获取未成功，浏览重试3条也未成功；基于既有表内片段标注，未重新认证上游hash、原始附件或全部额外AI引用。原始复核表hash保持不变，JSON/ID/60维标签/空真人签名校验通过；本轮不改产品或启动服务，无新依赖，未提交推送。
- 下一步：真人补取原文与附件并复核；Luna整理差异、Sol审查语义、Terra按确认缺陷处理、Root验收发布。正式双人标注、完整gold、网页保存及整体作品门禁仍未关闭。既有CLI/合成Bench能力未变，本机完整Web未由本轮复验。

## 2026-09-11 第一位真人复核确认

- 用户明确确认12条AI辅助初标无误；已新增结构化 `human-confirmation.json` 并填写真人复核表。12条、60个维度均确认无修改，分歧数为0。
- 本次复核发生在AI初标和系统结果已展示之后，状态登记为“单人AI辅助复核已确认”。不登记为盲标或双人独立复核，不把许可维度的12个 `uncertain` 提升为许可通过。
- 批次 manifest 的人工复核数由0更新为1；原 `ai-draft.json` 保持AI作者与创建时状态，原扫描结果和固定复核表不变。
- 标注专项当前完成AI初标和第一位真人确认；第二位独立复核、原文/原始附件补证、最终裁决冻结、完整gold和Web保存仍待完成。文件仅在本地，未提交或推送。

## 2026-09-11 人工标签完整性审计

- 内容完整性通过：12个唯一候选、每条5个评价维度，共60项；判断值和理由齐全，资源/任务/风险/主证据关联齐全；真人表12行无占位符，确认回执覆盖12/12且分歧0。
- 批次一致性通过：manifest显示1份真人确认和 `confirmed_single_human_review`；固定复核表SHA与批次记录一致；12条许可继续为 `uncertain`，未被误升为许可通过。`ai-draft.json`中的pending和0份真人是创建时不可变快照，最终状态由manifest和人类回执表达。
- 最终验收未通过：第二位独立真人复核仍待完成；12/12上游原文重取状态为unavailable；原始JSON附件和全部额外Evidence未复核；该批次尚未成为完整漏检gold，不能计算召回率；标注目录仍未被Git跟踪或发布。
- 本轮仅执行审计并追加协作记录，未修改标签值、产品接口/Schema/规则或运行服务。下一步由第二位真人、Luna、Sol及Root依次完成复核、补证、冻结和发布。

## 2026-09-11 许可证规则专项审计

- Root核查4c9e16b及已获取5611c00，规则核心一致，产出[八组问题与方案](../spec/2026-09-11-license-rule-audit.md)。AND/OR、覆盖集合、输入校验及共享义务聚合存在已复现缺口；本轮只审计未修复。
- 本地10+5测试通过（后5含B6/B7）；集成纯规则17通过、1主动排除持久化。更正此前“每条规则有fixture”：15规则仅6条逐规则verified_cases，另9条未覆盖。
- 新审计文档与协作增量仅本地，未提交/推送；原有人工方案/标签修改保持不变。Terra接续实现，Luna补回归，Sol/真人审核来源与场景，Root最终验收。完整Web、竞赛材料/权属、端到端人工签收与真实质量门禁未关闭。

## 2026-09-11 人工标签缺口补证与召回率基线

- 已从三个公开仓库取得固定提交，12条记录对应11个唯一文件；使用 `git show HEAD:<path>` 原始对象字节计算SHA-256，11/11文件、12/12记录与既有复核表一致。旧 `source-checks.json` 作为首次联网失败回执保留，新结果见 `source-reverification.json`。
- 完整原文复核确认R01–R04、R06–R10的既有判断；R11/R12继续为部分正确；R05新增分歧：文档链接写FLUX.1-dev，实际 `Tool.from_space` 参数为FLUX.1-schnell。因此AI裁决分布改为资源/证据9正确、3部分正确，风险8接受、4需修改。第一位真人确认发生在该新证据之前，R05需重新确认。
- 新建真实来源完整gold：八个完整文件及一个固定窗口，共9个case、50个真值资源；按静态检测器0.1.0规则得到TP=11、FP=8、FN=39、Precision≈0.5789、Recall=0.22、F1≈0.3188。该结果解决候选集无法计算召回率的问题，并暴露docs/blog/papers链接误报及模型字符串、数据集参数漏检；gold仅由AI标注，不能外推整个扫描器或宣称独立人工质量。
- 三份旧扫描JSON按已知SHA在当前工作区、Git历史、常用下载目录和项目父目录均未恢复；Docker引擎未运行，本轮未启动服务。25个去重Evidence ID中，12个主Evidence的固定来源已复核；13个额外Evidence只有2026-09-09历史机器核对回执，缺少旧对象字节，不能本轮逐字段复算。
- 标注专项当前可验证新增产物为来源复核、AI二次复核、Evidence审计和召回率gold；仍有三个外部门禁：第二位真人、R05真人重新确认、三份旧附件/13份额外Evidence对象恢复。文件仍在本地，未暂存、提交或推送。

### GitHub发布回执（2026-09-11 17:14）

- 上述人工标注、来源复核、Evidence审计、召回率gold、标注方案和许可证审计已提交为`2269f0c`，推送至`origin/codex/scan-reliability-integration`；共15个文件。历史段落中的“仅本地/未推送”保留为当时状态，由本回执更新当前状态。
- 发布不改变剩余门禁：第二位独立真人、R05真人重新确认、3份旧扫描附件和13个额外Evidence直接复核仍未完成；未合并`main`或`integration/p0`。

## 2026-09-11 R05真人补充确认

- 第一位真人已人工核对固定原文第258–265行，确认R05修订：资源识别和主证据为部分正确，许可保持不确定，风险需修改，AI建议保持过于笼统；原因是FLUX.1-dev链接与FLUX.1-schnell实际调用参数不一致。
- 新增 `human-amendment-r05.json`，与原 `human-confirmation.json` 形成可追溯的补充关系。批次当前裁决标签已由第一位真人全部确认；同一复核人仍只计1名，不作为第二位独立真人。
- R05重新确认门禁已关闭。人工标注剩余门禁为第二位独立真人，以及三份旧扫描附件和13个额外Evidence对象恢复复核；本轮变更尚未提交或推送。
