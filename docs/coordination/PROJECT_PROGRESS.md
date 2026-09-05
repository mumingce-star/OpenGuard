# OpenGuard 项目进度台账

更新时间：2026-09-05 21:35（Asia/Shanghai）

维护规则：每个任务点通过模型收工、Root 验收、测试、目录检查、提交和 GitHub 推送后更新。状态只使用 `已完成`、`进行中`、`未开始`、`阻塞`。完成度以可复现证据为准，不以代码行数估算。

优先级口径：以《OpenGuard AI 详细项目规划与 Codex 交接执行书 V1.0》第3节和第15节为P0边界与最终DoD。产品P1包括Resource Graph、Model/Dataset Card增强、LICENSE/NOTICE草稿、整改任务、批量Bench、历史扫描和更丰富报告；P2为更多生态、完整兼容矩阵、自动PR、私有仓库和高级协作。本轮及后续默认不实施P1/P2。下方历史全景包含完整竞赛目标，不能全部反推为P0硬门禁。共享日志中的缺陷严重度P1/P2与产品路线优先级不同。

### 项目负责人P0收工口径

每次收工仅展示用户负责的A1-A8，区分本轮/累计完成、进行中、未开始、阻塞、验证证据、责任角色和发布状态。组员模块只列作这些任务的输入依赖，不算作用户尚未完成的独立工作包。
P0结束依据：公开Git/ZIP、真实ScanCode/Syft、模型/数据/API带Evidence样例、首批许可证规则及可追溯风险、AI结构化降级、核心前端真实API、HTML/JSON/CSV、首批golden cases与指标、Compose陌生机复现、第三方与AI使用记录。完整竞赛材料及获奖竞争力证据另列。
I2已获明确授权；Git恢复、lease/heartbeat和业务retry不自动成为下一任务。I2通过后先回到上述DoD的真实分析模块接线与Web/部署闭环，不扩张队列架构。2026-09-05最新用户要求：优先简单可运行第一版，最小适配，不新建包装性产物；当前核查结论见第8节。

## 0. 真人责任边界（模型角色不能替代真人主责）

| 真人角色 | 负责范围 | 本轮处理 |
|---|---|---|
| 项目负责人（用户） | A1领域、A2输入、A3 API/注册表、A4 Pipeline、A5 AI、A6报告、A7部署、A8集成与材料 | 本轮完成A3/A4-3a-I2，Terra实现、Luna独立验证、Root审查与发布；不代做B线、前端或部署 |
| 扫描分析组员 | B1-B7：依赖解析、ScanCode、Syft、SPDX、许可证规则、AI 资产检测与 Bench 基础 | 远端 `codex/p0-external-tools-sync` 仍为 `f8bedfd`；本轮只读取当前分支已原样引入的 B5 公共输出，不改写组员引擎、规则、扫描器、测试或分支 |
| 前端组员 | React/Vite 与 New Scan、Progress、Dashboard、Risk Detail、Resource List、Report 页面 | 本轮未修改；远端前端分支新提交保持组员在途状态 |

Sol/Terra/Luna 是 Codex 的设计、实现、独立测试角色，不代表三位真人的任务归属。后续选题必须先按上表确定真人主责，再分派模型。

## 1. 当前任务点

最新状态见第11节：最小Compose与ScanCode/Syft真实运行环境已完成，Chrome插件完成部署页面的上传、报告与刷新；Chrome文件保存确认仍未完成。当前功能分支`feat/a7-minimal-compose`，下一任务为复用组员适配器把工具事实接入现有ZIP Pipeline。
以下历史里程碑表保留原证据，不能替代第11节的当前状态；不扩展P1/P2。

| 任务点 | P级 | 主责模型 | 状态 | 已完成/当前证据 | 未完成/下一步 | GitHub状态 |
|---|---|---|---|---|---|---|
| A3/A4-3a-S ZIP 持久派发规格 | P0 | Root/Astra→Sol/Terra/Luna | 已完成 | 单机flock、prepared/ready、原profile幂等、queued恢复、managed running零重放收敛及DZ-01..15规格审查通过 | 规格已发布；I1/I2已验收；Git恢复/lease/heartbeat/业务retry不自动列入P0 | `docs/a3-a4-durable-zip-spec` 已推送，规格提交 `f9a59fa`；未创建/合并PR |
| A3/A4-3a-I1 ZIP持久存储协议 | P0 | Terra→Luna→Root | 已完成 | 实现16项、独立29项、原并发P1闭合、受控全量952 passed,3 skipped；EVD-A3-DURABLE-ZIP-STORAGE-001绑定272f5cf | I2已另行验收，默认0、精确1启用单机ZIP派发 | `feat/a3-durable-zip-storage` 已推送，远端完整对象已核对；未创建/合并PR |
| S1a/A1 P0领域契约 | P0 | Sol | 已完成 | 契约 v0.1.1、唯一公共模型、6个API、风险四态、证据与provenance；历史提交 `02c3d46` | 后续仅通过变更流程新增 ADR，不再并行维护第二套模型 | 已推送 `feat/p0-domain-contract` |
| A1 领域模型实现 | P0 | Terra | 已完成 | Pydantic模型、Draft 2020-12 Schema、sample和 AI producer 条件字段；历史提交 `b2fd061` | 进入 A2 前保持兼容性回归 | 已推送 `feat/p0-domain-contract` |
| L-A1 独立边界审计 | P0 | Luna | 已完成 | 46项测试全部通过；覆盖路径脱敏、partial语义及 AI producer 正反边界 | 进入 A2 后扩展输入安全测试 | 已推送 `feat/p0-domain-contract` |
| A1.1 AI ProducerRef | P0 | Sol→Terra→Luna | 已完成 | `provider`、`model_id`、`prompt_schema_digest` 已完成契约、实现、Schema、sample和独立测试闭环 | 后续变更走 ADR 和回归门禁 | 已推送 `43493fb` |
| 协作与发布治理 | P0 | Root | 已完成 | 进度表、目录规则、统一验收、每任务点GitHub推送和上传范围复核已固化 | 每个后续任务点持续执行 | 已推送 `43493fb` |
| S0 竞赛规则与评分证据治理 | P0 | Sol→Root | 已完成 | 三份正式文件映射、官方100分评分追踪、提交清单、九章27项主张与非目标已形成 | 随竞赛通知变更复核；最终材料仍需按证据状态逐项冻结 | 已推送 `ffa9390` |
| S2 条件性安全设计基线 | P0 | Sol→Terra→Luna | 已完成 | 20项安全控制、5项正向/36项负面设计；A2-3a 已在 macOS/POSIX profile 实现 TrustedEgress 并完成真实公开仓库纵切 | 条件性设计任务完成；Linux profile、完整攻击语料和部署级复验仍未关闭，不能声称 S2/A2 总门禁完成 | 已推送 `ffa9390`；A2-3a 已推送本分支 |
| A2-0/A2-1 本地 ZIP 安全纵切 | P0 | Terra→Luna→Sol→Root | 已完成 | 服务端限额/POSIX能力探测、descriptor-safe流式解压、central/local header核验、稳定inventory/root digest与失败清理；独立36项、Terra 19项、P0 46项、全量101项通过；`EVD-A2-ZIP-IMPL-001` 已绑定 `53499ea` | Git/TrustedEgress/API 后由 A2-3a/A3 关闭；A2总包仍缺完整ZIP corpus、inventory并发完整性、cleanup隔离与 Linux profile，本地绿灯不得外推 | 已推送 `53499ea`；待PR合并 |
| A2-1D 本地 ZIP CLI 演示 | P0 | Terra→Luna→Sol→Root | 已完成 | `python -m app.cli LOCAL_ZIP` 已实现稳定 JSON、0/1/2 退出语义、错误脱敏和临时清理；Terra 5项、Luna独立5项、当前全量111项通过；Sol终审与追踪更正闭环；`EVD-A2-ZIP-CLI-001` 绑定 `910f745` | 这不是完整Web、依赖/许可证扫描或A2总门禁；后续由A2/B1等任务继续 | 已推送 `feat/a2-zip-cli-demo`；待PR合并 |
| A2-2 安全只读扫描会话 | P0 | Sol→Terra/Root→Luna→Sol→Root | 已完成 | 生命周期绑定 `ReadOnlyScanSession`、inventory 精确白名单、逐层 dirfd/no-follow identity seal、SHA-256 前后复验、2 MiB/16 MiB 默认配额、过期/线程/重入/异常/cleanup 失败关闭；Luna 独立46项、定向unit42项、全量175项、P0 46项通过；`EVD-A2-READONLY-SESSION-001` 已绑定 `1f03ce0` | 仅允许可信非执行性 parser；公开 Git 已在 A2-3a 复用该能力，完整ZIP corpus、cleanup worker/orphan、Linux profile 和 A2 总门禁仍未完成 | 已推送 `feat/a2-readonly-scan-session`；待PR合并 |
| A2-3a 公开 Git/TrustedEgress 纵切 | P0 | Terra/Root | 已完成 | 公共 HTTPS URL/全地址公网门禁、固定 TLS DoH、逐连接 CONNECT 出口、Git no-checkout object 物化、revision/inventory/provenance、API→B1/A4→A6 接线；PyPA 真实仓库通过，受控完整 `872 passed`；`EVD-A2-PUBLIC-GIT-EGRESS-001` 绑定 `f6aea1e` | 仅批准当前 macOS/POSIX profile；A2 总包仍缺完整攻击 corpus、cleanup orphan/quarantine、Linux namespace/seccomp/cgroup 与陌生机部署复验 | 已推送 `feat/a2-public-git-egress`；未创建/合并 PR |
| B1-1 Python manifest 解析纵切 | P0 | Sol→Terra→Luna→Sol→Root | 已完成 | 仅通过只读会话发现/解析 `requirements*.txt`、`pyproject.toml`；PEP 508/440、字段/行级证据草稿、确定性去重/冲突/partial、URL与配额门禁；Terra 40项、Luna独立63项、全量278项、P0 46项通过；`EVD-B1-PYTHON-MANIFEST-001` 已绑定 `7c0d365` | B1-2 已另行闭环；JS/TS与lockfile仍未开始 | 已推送 `feat/b1-python-manifest-parser`；待PR合并 |
| B1-2 Python P0映射与CLI纵切 | P0 | Sol→Terra→Luna→Sol→Root | 已完成 | 冻结DTO映射为P0 `Component/Evidence`；UUIDv5稳定ID、证据定位/哈希/时间、exact pin、direct/VCS、partial诊断、固定时钟与旧CLI兼容；Sol终审发现并关闭2项P1；Terra 45项、Luna独立32项、全量355项、P0 46项通过；`EVD-B1-PYTHON-P0-CLI-001` 已绑定 `daee8a8` | B1总包下一步进入 JS/TS manifest 与选定 lockfile；本纵切不代表许可证、依赖求解或完整报告 | 已推送 `feat/b1-p0-mapper-cli`；待PR合并 |
| B1-3/B1-4 JavaScript manifest、P0与CLI | P0 | Sol/Root→Terra→Luna→Terra→Luna→Root | 已完成 | 支持根 `package.json` 四类直接依赖与 `package-lock.json` v2/v3 enrichment；严格JSON、稳定Evidence/UUID/purl/URL、partial与新CLI；Luna首次发现5项P1，连同Root 4类探针均已关闭；Terra 37项、Luna独立32项、JS合计69项、全量424项通过；`EVD-B1-JAVASCRIPT-P0-CLI-001` 已绑定 `80ee2a9` | B1仍缺选定Python lockfile、Yarn/pnpm/workspace/传递依赖；本纵切不代表许可证或安装事实 | 已推送 `feat/b1-js-manifest-p0-cli`；待PR合并 |
| A3-0 持久 ScanRun 注册表 | P0 | Sol→Terra→Luna→Terra→Luna→Sol→Root | 已完成 | 单机 POSIX SQLite canonical ScanRun、revision/CAS、跨实例/重启幂等、状态单向性、稳定分页、私有路径权限、损坏Schema与额外table/view/trigger失败关闭；两轮审计P1均已关闭；Terra32项、Luna45项、A3合计77项、全量501项通过；`EVD-A3-DURABLE-SCAN-REGISTRY-001` 已绑定 `d2b26b0` | A3仍缺FastAPI、OpenAPI、HTTP错误映射、ZIP/Git创建请求、worker与A4编排；不得外推多机容灾或exactly-once副作用 | 已推送 `feat/a3-durable-scan-registry`；实现 `d2b26b0`，证据 `0cadbbe`；待PR合并 |
| A3-1 FastAPI Git API 纵切 | P0 | Root→Luna→Sol | 已完成 | FastAPI 六路由、Git queued 持久幂等、结果读取/过滤与统一脱敏错误；Luna 独立发现的404/405信封、控制字符、UTF-8字节上限三项P1已关闭；A3-1实现+独立48项、全量549项通过；证据绑定 `aedf65c` | ZIP/worker/A4/公开 Git 后由 A3-2/A4-1/A2-3a 关闭；本纵切自身仍只代表 API 契约，不外推 Linux 或完整扫描 | 已推送 `feat/a3-fastapi-api`；实现/独立证据 `aedf65c`，绑定 `68163de`；待PR合并 |
| A4-0 显式单进程 Pipeline Worker | P0 | Sol→Terra→Luna→Root | 已完成 | 七阶段/固定进度、A3 CAS认领、Adapter聚合持久化、completed/partial/failed/cancelled与脱敏错误；Terra 21项、Luna独立25项，A4合计46项；Root定向169项、完整集合595项通过；`EVD-A4-PIPELINE-WORKER-001` 已绑定 `66fc2ae`；无开放P0/P1/P2 | A4父任务仍缺真实Adapter接线、API队列自动消费、重试/超时、lease/heartbeat、stale-running恢复与系统集成；stub结果不得外推真实扫描 | 已推送 `feat/a4-pipeline-worker`；实现证据 `66fc2ae`；待PR合并 |
| A4-1 本地 ZIP 依赖 Pipeline 接线 | P0 | Sol→Terra→Root→Luna→Root | 已完成 | 本地 ZIP 经单次 A2 只读会话调用既有 B1 Python/JavaScript parser/mapper，持久化真实 P0 Component/Evidence、digest、producer与summary；规则未接线时诚实为partial；实现29项、Luna独立20项、A4-1合计49项、完整集合644项通过；`EVD-A4-LOCAL-ZIP-DEPENDENCY-PIPELINE-001` 已绑定 `fbed364`，无开放P0/P1/P2 | A4父任务继续接许可证规则、API/后台消费、AI与报告；A4-1不包含这些能力 | 已推送 `feat/a4-local-zip-pipeline`；待PR合并 |
| A4-2 B5 许可证规则阶段接线 | P0 | Root/Astra | 已完成 | 原样引入组员 B5 引擎、15条规则、fixture/spec，并以薄适配器接入 A4 rules 阶段；verified 产生稳定义务/风险/整改，pending 保持证据门禁且不产生整改；A4+B5 聚焦 `68 passed`，受控完整 `888 passed, 2 skipped`，Schema 等值；`EVD-A4-B5-RULE-INTEGRATION-001` 绑定 `4752f2b` | 当前 ZIP/Git 尚未产生 B2/B3/B4 许可证事实，真实输入仍为 `partial/rules/70`；后续 A5-1c 已消费其公共 finding，不改变 B5 | 已推送 `feat/a4-b5-rule-integration`；未创建/合并 PR |
| A3-2 ZIP HTTP 与进程内后台扫描 | P0 | Sol/Root→Luna→Root | 已完成 | 同一 POST 路径支持 Git JSON 与 ZIP multipart；请求/上传限额、私有暂存、摘要/幂等、queued→BackgroundTask→A4-1、清理与 OpenAPI 已实现；实现20项、Luna独立22项、完整集合等价686项通过；`EVD-A3-ZIP-BACKGROUND-SCAN-001` 已绑定 `530e930` | 当前 `partial/rules/70` 表示依赖结果可用但上游许可证事实未进入已接入的 B5；公开 Git 已由 A2-3a 接入，A3父任务仍缺持久队列/恢复 | 已推送 `feat/a3-zip-background-scan`；待PR合并 |
| A5-0 可注入 AI Provider 与降级核心 | P0 | Sol→Terra/Root→Luna→Root | 已完成 | local/remote 统一接口、finding/evidence/license canonical 输入、64 KiB 严格 JSON、引用/敏感门禁、pending Remediation、稳定 ID、P0 入口重校验与 generated/skipped/disabled/degraded 原子语义；实现30项、Luna独立16项、完整非回环734项通过；`EVD-A5-AI-PROVIDER-001` 绑定 `2c824bf` | A5父任务继续 A5-1：真实 Qwen3/Ollama transport、超时、A4 AI_ASSIST 接线与消融；必须消费组员 B5 的真实 finding，不代做规则 | 已推送；PR #2 待团队审核 |
| A5-1a Qwen3/Ollama 本地 Transport | P0 | Sol→Terra/Root→Luna→Root | 已完成 | 锁定 Ollama `0.33.3`、Qwen3 4B Instruct Q4_K_M 与完整 manifest；字面量回环、禁代理、版本/模型摘要校验、三步 HTTP、总 deadline、严格封装和稳定降级；实现60项、Luna独立17项，A5组合123项、完整非回环794项通过；`EVD-A5-OLLAMA-TRANSPORT-001` 绑定 `e4d8e2e` | A5-1b 已另行闭环；B5 pending finding 已可供下一项 A5-1c 接入 A4，不代做规则 | 已推送 `feat/a5-ollama-transport`；PR #2 待团队审核 |
| A5-1b Ollama/Qwen3 本机真实运行 | P0 | Sol→Terra/Root→Luna→Root | 已完成 | 官方 Ollama `0.33.3` DMG 的 SHA-256、Developer ID、Gatekeeper、公证与 arm64 均通过；锁定 Qwen3 manifest/API/disk/blob 摘要一致；Root 探针与 Luna 独立脚本各完成真实 `3/3`，冷轮约 4.34/3.88 秒、热轮约 2.73/2.77 秒，均验证 generated、pending、来源绑定、事实保持和稳定 ID；加载约 3.175 GB、100% GPU、context 4096；runtime probe unit `5 passed`、A5 `128 passed`、全量 `818 passed`；`EVD-A5-OLLAMA-REAL-RUN-001` 已绑定不可变实现 `ca0c3ed` | 仅为当前 Apple-silicon 和单一样例实测，不是 Bench；A5-1c 可开始消费 B5 pending finding 并接 A4 AI_ASSIST，不代做规则；真实输入端到端仍需上游许可证事实 | 已推送 `feat/a5-ollama-transport`；PR #2 待团队审核 |
| A5-1c Pipeline `AI_ASSIST` 接线 | P0 | Root/Astra→Luna→Root | 已完成 | shared plan、ZIP/Git runtime 与默认应用已接 A5；默认关闭，`OPENGUARD_ENABLE_AI=1` 才注入锁定 Ollama；B5 pending 生成待复核整改、verified 不重复、失败保留规则并进入 A6；实现与独立合计 `19 passed, 1 skipped`、真实 Ollama 单项 `1 passed, 10 deselected`、受控完整 `907 passed, 3 skipped`；`EVD-A5-PIPELINE-INTEGRATION-001` 绑定 `3237ab0` | 真实 ZIP/Git 仍因上游无许可证事实停在 `rules/70`，不等于完整 Web 端到端；多项目效果需 Bench | 已推送 `feat/a5-pipeline-integration`；未创建/合并 PR |
| A6-0 确定性报告导出核心 | P0 | Terra/Root | 已完成 | 终态 `ScanRun` 可导出稳定 JSON、竞赛七字段 CSV/资源清单和安全静态 HTML；阶段性报告不补写缺失事实；专项 `12 passed`、A6+P0 `58 passed`、受控全量 `830 passed`，Schema/compileall/静态门禁通过；实现 `fda4ce6` | 内存核心由 A6-1 继续消费；真实许可证内容仍等待上游事实进入已接入 B5 | 已推送 `feat/a6-report-export-core`，远端实现 HEAD 已核对 |
| A6-1 报告安全持久化与只读下载 | P0 | Terra/Root | 已完成 | 私有 `0700/0600` 内容寻址存储、原子 metadata 提交、重启/摘要/篡改验证、P0 `ReportLink`、同一冻结 GET 的只读下载和安全响应头已实现；A6-1 `16 passed`、受控全量 `846 passed` | A6-2 已完成 Pipeline 接线；前端接线归前端组员，完整许可证报告继续等待真实许可证事实 | 已推送 `feat/a6-report-delivery`；实现 `9ce9535`；`EVD-A6-REPORT-DELIVERY-001` 已绑定 |
| A6-2 Pipeline 终态报告发布 | P0 | Terra/Root | 已完成 | publisher 在首次 terminal CAS 前发布四格式并只允许增加完整 `ReportLink`；ZIP HTTP 自动得到带链接的诚实 `partial/rules/70`；registry 是可见性门禁，orphan/元数据不一致/篡改均失败关闭；专项 `10 passed`、A6/A4/A3/P0 联合 `177 passed`、受控全量 `856 passed` | 前端真实下载接线归前端组员；A4-2 可把实际 B5 输出交给报告，但真实主链仍缺上游许可证事实；持久队列仍属 A3/A4 后续 | 已推送 `feat/a6-pipeline-publish`；实现 `eec66a6`；`EVD-A6-PIPELINE-PUBLISH-001` 已绑定 |
| A8-1a P0团队集成基线 | P0 | Root/Sol | 已完成 | `integration/p0` 已汇合项目负责人六层后端纵切、前端组员壳和扫描组员B2/B3 Adapter候选；后端688项非回环+2项真实回环通过，前端锁文件供应链检查和生产构建通过；Schema不变；`EVD-P0-TEAM-INTEGRATION-001` 绑定 `f486ead` | 前端仍为mock；B2/B3仍缺本机真实工具和主链接线；不外推完整产品 | 已推送 `integration/p0`；团队后续从此创建短分支 |
| A8-1b 冗余远端分支清理 | P0治理 | Root | 阻塞 | 已证明13个旧项目负责人任务分支均被 `integration/p0` 完整包含且零独有提交；组员两分支明确排除 | 远端删除被安全审批拒绝，需用户明确批准下方13个具体分支；本轮没有删除任何分支 | 待用户确认；不影响 `integration/p0` 使用 |
| A8-1c A5 团队集成 PR | P0治理 | Root/Sol | 进行中 | 隔离 worktree 合并无冲突；沙箱原样 `807 passed, 11 failed, 1 warning` 的 11 项均为回环 bind 权限限制，受控环境原样 `818 passed, 1 warning`；P0 `46 passed`，Schema、compileall、diff、敏感/路径/大文件/上传范围门禁通过；PR #2 已创建且 GitHub 显示可自动合并 | 等待团队代码审核与明确合并决定；本任务不自动请求组员评审、不自动合并 | [PR #2](https://github.com/mumingce-star/OpenGuard/pull/2) 已打开，base=`integration/p0`、head=`feat/a5-ollama-transport` |
| A8-1d VS Code 本机复现演示 | P0治理 | Root/Sol | 已完成 | Python 3.12.14 启动 FastAPI；动态 ZIP POST `202`，SQLite 终态 `partial/rules/70`，得到 React/FastAPI/Pydantic 3 个组件和 3 条 verified evidence；Ollama/Qwen3 聚合探针 `2/2` 且全部校验通过；Vite 页面可见并明确 `MOCK MODE` | 该次演示只覆盖当时纵切；后续 A5-1c 已接 Pipeline，但前端仍未接真实 API、真实输入仍缺许可证事实，需另做更新后的完整演示 | 治理证据已推送当前 PR 分支；临时脚本、ZIP、SQLite、prompt/response 未上传 |
| F0-0 前端应用壳 | P0 | 前端组员→Root验证 | 进行中 | React/Vite/Tailwind应用壳、基础页面与动效已由组员提交；Root按锁文件安装并完成TypeScript+Vite生产构建 | 当前仍使用mock，未接真实API；页面功能与视觉验收归前端组员 | 来源 `feat/xzb-frontend`，已纳入本地集成候选 |

## 2. P0 工作包全景

| ID | 模块 | 主责 | 状态 | 已完成 | 未完成/验收标准 | 计划阶段 |
|---|---|---|---|---|---|---|
| S0 | 竞赛要求与评分追踪 | Sol | 已完成 | 正式来源、硬约束、官方评分、提交/补正/匿名/AI披露、27项报告主张与非目标均已映射 | 随正式通知复核；真实需求、实验、用户反馈和最终链接继续保持 planned/blocked | 9月3日前 |
| S1/A1 | 领域模型与公共契约 | Sol/Terra/Luna | 已完成 | v0.1.1契约、实现、Schema、sample及46项测试完成 | 后续变更需 ADR；A2 不得破坏本契约 | 9月3日前 |
| S2 | 威胁模型与安全验收 | Sol/Terra/Luna | 进行中 | 条件性设计基线已完成；A2-3a 已关闭当前 macOS/POSIX profile 的 TrustedEgress/公开 Git 纵切，并登记 Git/DoH | 最终安全验收仍需 Linux profile、完整阈值/攻击语料、cleanup 隔离与陌生机全量真实测试；当前不得外推为部署级安全完成 | 9月3日前设计，A2实现 |
| A2 | Git/ZIP安全输入与Inventory | Terra | 进行中 | 本地 ZIP、CLI、只读会话及 A2-3a 公开 HTTPS Git/TrustedEgress 已完成；两种输入均可进入 B1/A4/A6；真实公开仓库及受控完整 `872 passed` | 继续完成完整 ZIP/Git 攻击 corpus、cleanup orphan/quarantine、Linux namespace/seccomp/cgroup profile、陌生机部署与 A2 总证据冻结 | 9月4日-11日 |
| B1 | Python/JS依赖解析 | Terra | 进行中 | Python requirements/pyproject 与 P0 CLI 已完成；根 package.json 四类直接依赖、package-lock v2/v3 enrichment 与 JS P0 CLI 已完成；当前全量424项通过 | 选定 Python lockfile；Yarn/pnpm/workspace/传递依赖列后续增强；再进入多来源合并 | 9月4日-11日 |
| B2 | ScanCode适配器 | Terra | 进行中 | 安全 JSON 适配、超时/失败对象、许可证证据候选映射和单测已实现 | 在受控运行环境固定实际工具版本/校验并完成真实工具回归；B4 规范化候选 SPDX | 9月4日-11日 |
| B3 | Syft适配器 | Terra | 进行中 | 安全 JSON 适配、SBOM Component/Evidence 映射、跨来源合并和单测已实现 | 在受控运行环境固定实际工具版本/校验并完成真实工具回归 | 9月4日-11日 |
| B4 | SPDX标准化 | 扫描组员 / Sol/Terra | 进行中 | 组员分支已有显式别名与复合表达式标准化回归，未知值保持 pending；本轮未导入或修改 | SPDX 官方数据版本台账、完整表达式语法、LicenseRef、人工复核及与许可证事实生产链集成 | 9月4日-20日 |
| B5/S3 | 15种许可证义务规则 | 扫描组员 / Sol/Terra/Luna | 进行中 | 组员分支已有 15 条 JSON-subset YAML 规则、逐规则 fixture、证据门禁和稳定 P0 输出；其公共实现已由项目负责人 A4-2 原样消费，组员 B5 定向 `10 passed` | 官方许可证原文证据台账、人工复核状态和更完整冲突样例仍缺；不得因 A4 接线而标为 B5 完成 | 9月12日-20日 |
| B6 | 模型/数据/API检测 | 扫描组员 / Terra | 进行中 | 组员分支已有离线 HF/ModelScope/API 静态识别与 Evidence 定位回归；本轮未导入或修改 | AST 覆盖、误报评测、授权/许可证人工核验与主链接入 | 9月12日-20日 |
| A3 | FastAPI扫描API | 项目负责人 / Root | 进行中 | 6个端点、SQLite、Git JSON、ZIP multipart 与两种输入的进程内 BackgroundTask 已验证；公开 Git 需管理员显式开启，ZIP/Git 都可产生可查询终态 | ZIP持久派发及queued/running恢复已由I2完成；剩余核心Web联调与部署验收。Git恢复、lease/retry不自动排入P0 | 9月21日-28日 |
| A4 | Pipeline编排 | 项目负责人 / Terra | 进行中 | A4 worker、ZIP/公开 Git 依赖接线、A6-2 报告发布、A4-2 B5 规则适配及 A5-1c AI 阶段接线已完成；注入合法许可证事实时可持久化 B5 与 AI 输出 | I2持久ZIP消费与恢复已完成；剩余真实许可证/AI资产事实接线及端到端证据，不继续扩张lease/retry | 9月21日-28日 |
| A5/S4 | AI Provider与降级 | Sol/Terra/Luna | 已完成 | A5-0 Provider、A5-1a transport、A5-1b 本机真实运行和 A5-1c Pipeline 接线均已绑定不可变证据；已有 B5 pending→真实 Qwen3→SQLite→A6 单项证据，且 verified 确定性整改不重复、失败可降级 | 普通 Web 端到端仍需上游许可证事实，多项目质量需 Bench；这些属于集成/效果门禁，不回退 A5 P0 子系统完成状态 | 9月12日-28日 |
| F0 | P0前端核心页面 | Terra/团队前端 | 进行中 | React/Vite/Tailwind 应用壳已提交并通过锁文件安装、TypeScript与Vite生产构建 | 当前仍为mock；继续完成 New Scan、Progress、Dashboard、Risk Detail、Resource List、Report 的真实API接线 | 9月21日-28日 |
| A6 | HTML/JSON/CSV与资源清单 | 项目负责人 / Terra/Luna | 进行中 | 四格式渲染、私有持久化/下载与 Pipeline 发布已完成；A4-2 的实际 B5 输出可由既有报告器呈现；受控完整 `888 passed, 2 skipped` | 前端下载接线和最终匿名化验收；真实许可证内容仍需上游事实进入 B5 | 9月21日-28日 |
| S5/B7 | OpenGuard-Bench | 扫描组员 / Sol/Luna/Terra | 进行中 | 组员分支已有版本化合成 smoke cases 与 TP/FP/FN/Precision/Recall/F1 评测器回归；本轮未导入或修改，smoke 不等于完整 Bench | 3–5 个独立复现 case、人工标注、20–30 公开仓库、50–100 合成样例、基线/消融与误差分析 | 9月29日-10月5日 |
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
| 2026-09-04 | A6-1 报告持久化与只读下载 | `feat/a6-report-delivery` | `9ce9535`（不可变实现/测试/证据） | 内容寻址私有存储、原子 metadata、ReportLink、同一路由只读下载、16项专项测试、规格与治理记录；不含生成报告文件、B5、Pipeline 或前端 | 已推送；远端完整对象 `9ce9535436372295eaf1598a9805ec415b79db86` 已核对；未创建/合并 PR |
| 2026-09-04 | A6-2 Pipeline 终态报告发布 | `feat/a6-pipeline-publish` | `eec66a6`（不可变实现/测试/证据） | Pipeline publisher、worker/ZIP/default factory 接线、API 可见性一致性、10项专项测试、规格与治理记录；不含生成报告文件、B5、A5、前端或部署 | 已推送；远端完整对象 `eec66a6aa0458abdbadd912f17c6c9d54ce3a247` 已核对；未创建/合并 PR |
| 2026-09-04 | A2-3a 公开 Git/TrustedEgress | `feat/a2-public-git-egress` | `f6aea1e`（不可变实现/测试/证据） | URL/DNS/CONNECT/Git object 安全摄取、公共依赖 Pipeline、API/A6 接线、实现与真实公网测试、规格/资源/治理记录；不含目标仓库内容、B5、A5、前端或部署 | 已推送；远端完整对象 `f6aea1eb2db1475be489f9ce8afc517e10f3c0e2` 已核对；未创建/合并 PR |
| 2026-09-05 | A4-2 B5 许可证规则阶段接线 | `feat/a4-b5-rule-integration` | `4752f2b`（不可变实现/测试/证据） | 原样引入组员 B5 公共实现/15条规则/测试/规格；新增项目负责人 A4 薄适配器、8项集成测试和运行/治理说明；不含 B4/B6/B7、前端、部署或运行产物 | 已推送；远端完整对象 `4752f2b11252870c1b33306583390321c8d24397` 已核对；未创建/合并 PR |
| 2026-09-05 | A5-1c Pipeline `AI_ASSIST` 接线 | `feat/a5-pipeline-integration` | `3237ab0`（不可变实现/测试/证据） | A5 plan/runtime/default factory 接线、9项实现测试、11项独立安全测试实例（含1项显式真实模型门禁）、规格与运行/AI/协作记录；不含 B4/B5/B6/B7、前端、部署或模型内容 | 已推送；远端完整对象 `3237ab0e8634ba5f0c62535100ef97785bd611a6` 已核对；未创建/合并 PR |

## 3.1 当前远端分支入口

- 团队日常入口：`integration/p0`；里程碑发布目标：`main`。
- 项目负责人当前短分支：`feat/a3-zip-dispatcher-recovery`，基线`2368d91`；I2发布记录见第7节。既有PR、main/integration及组员分支均未自动修改或合并。
- 组员在途分支：`feat/xzb-frontend`、`codex/p0-external-tools-sync`，均保留。
- 待明确授权清理的项目负责人历史分支：`feat/p0-domain-contract`、`feat/s0-s2-design-gates`、`feat/a2-zip-ingestion`、`feat/a2-zip-cli-demo`、`feat/a2-readonly-scan-session`、`feat/b1-python-manifest-parser`、`feat/b1-p0-mapper-cli`、`feat/b1-js-manifest-p0-cli`、`feat/a3-durable-scan-registry`、`feat/a3-fastapi-api`、`feat/a4-pipeline-worker`、`feat/a4-local-zip-pipeline`、`feat/a3-zip-background-scan`。
- 上述待清理分支的提交均已从 `integration/p0` 可达，删除分支引用不会删除集成线中的代码和证据；未获明确授权前保持现状。

## 4. 目录健康检查

| 检查项 | 当前状态 | 规则 |
|---|---|---|
| 顶层目录 | 通过 | 使用既有工程目录，不新增含糊或重复目录 |
| 临时环境/缓存 | 通过（Git层） | `.pytest_cache`、`__pycache__`、虚拟环境不纳入提交 |
| 竞赛原始附件 | 通过 | 原始PDF/DOCX不复制进公开仓库，正式要求以脱敏规范文档表达 |
| 敏感信息 | I2 发布复核通过 | 不上传密钥、账号、本机绝对路径、学校/教师/成员隐私或目标仓库内容 |
| 第三方资源 | 持续 | 首次真实引入时锁版本并更新 `third_party/` 与资源清单 |

## 5. A3/A4-3a 实施进展与下一任务（2026-09-05）

唯一规格：[ZIP持久派发与中断收敛](../spec/a3-a4-durable-zip-dispatch.md)。
Sol完成架构审查，Terra确认可实现性，Luna批准15项独立oracle；Root关闭报告links可见性和配额预留歧义。
I1存储和I2自动派发/恢复已分别验收，运行证据见规格第12–13节。
未新增依赖或改变公共契约；本轮新增I1实现与独立测试，已有保护测试未放宽。

| 范围 | 状态 | 责任 | 下一项可验证门禁 |
|---|---|---|---|
| 本轮规格门禁 | 已完成 | Root/Sol/Terra/Luna | 四文件范围、append-only、P0回归、DZ唯一ID通过；规格提交f9a59fa与远端完整对象一致 |
| I1 descriptor与输入生命周期 | 已完成 | Terra→Luna→Root | 实现16项、独立29项、受控全量952 passed,3 skipped；已推送272f5cf并绑定证据 |
| I2 dispatcher与恢复接线 | 已完成 | Terra→Luna→Root | 真实锁/kill/restart/零重放，独立70、完整1005 passed/3 skipped |
| Git恢复、lease/heartbeat与业务retry | 未开始 | 项目负责人A线 | 不自动排入P0；本轮不承诺任意阶段续跑或exactly-once |
| 前端与B线候选接入 | 进行中 | 各组员→Root集成 | 组员分支已有候选；前端拟定接口须适配冻结六API，B4/B6/B7不得重复生成 |

现有可演示能力仍为安全ZIP/公开Git依赖纵切、持久查询与阶段性报告；普通输入仍为
`partial/rules/70`，当前主控前端仍为mock。最新组员分支有请求/轮询与检测/Bench候选，
不等于已完成主控真实Web联调。团队集成线尚未自动合入本轮工作，不以功能分支推送代替团队联调或合并。

报名/参赛资格门禁：Owner落实平台、缴费、主体和权属确认。完整作品门禁：上游许可证事实、
前端契约对齐与真实Web链、部署/陌生机、安全与Bench、报告视频/资源表/匿名及Release。
获奖竞争力门禁：真实案例、基线/消融、误差分析和稳定演示。不得由规格或P0回归推出完成率。

文档发布证据：规格提交 `f9a59fa3eb722c2eb1eb0ec939bda5efe8587b78` 已推送并以
`git ls-remote` 核对一致；规格轮仅上传上述四个文档，随后同分支回填发布记录。
未创建/合并PR，未修改main、integration/p0或组员分支。该提交不是持久worker实现证据。


## 6. I1 历史验收与发布（当前状态以第7节为准）

- 本轮：私有ZIP/descriptor、实际摘要与身份绑定、prepared/ready协议、首字节前容量、原profile幂等、健康清理已验收；原跨线程P1及测试fsync定位误标均保留历史并闭环。
- 累计：A1与A5 P0子系统完成；A2/A3/A4/A6已有可运行纵切但父包仍进行中，A7部署与完整材料未完成。
- 阻塞/依赖：本轮技术缺陷已关闭；完整Web仍依赖B线真实许可证事实、前端契约对齐与团队集成。最终Release未发布。
- 验证：Terra16、Luna29、受控全量952 passed/3 skipped；OpenAPI精确等值、Schema/sample、编译与前端构建通过。发布前再检查新增内容、敏感信息和append-only前缀。
- 当前演示：既有安全ZIP/公开Git依赖扫描、持久查询与阶段性报告；I1仅内部注入时生成queued+ready，不运行worker。普通输入仍可诚实partial/rules/70，主控前端仍mock。
- 紧接任务：A3/A4-3a-I2生命周期锁、dispatcher与中断收敛；继续复用当前store/registry/worker/A5/A6，不新建第二套实现。
- 报名/参赛：Owner核对平台、主体及权属等资格事项；完整作品：真实许可证链、Web联调、部署/安全/Bench、报告视频/资源表/匿名及Release；获奖竞争力：真实案例、基线/消融、误差分析与稳定演示。
- 发布：实现`272f5cfed49c88b0bea4063b22d3cce5a8a9a6ee`已推送功能分支，远端完整哈希核对一致，EVD已绑定；本轮共12项文件，不修改main、不创建或合并PR、不发布Release。

I1不可变实现证据：`272f5cfed49c88b0bea4063b22d3cce5a8a9a6ee`；功能分支已发布，随后仅回填本轮发布治理记录。

## 7. I2 最终验收与项目负责人P0状态

本轮I2已验收并推送`feat/a3-zip-dispatcher-recovery`；不可变实现`f48108f6da32ea36e6e757a3cd80a2b42baa0767`已与远端完整哈希核对。EVD-A3-DURABLE-ZIP-DISPATCH-001；unit28、独立70、受控完整1005 passed/3 skipped。OpenAPI/Schema/sample、编译及保护范围通过。Root承担本轮架构终审，未唤醒已停用Sol任务；Terra实现、Luna独立验证均已停止写入。
下表仅计用户本人A1–A8，组员代码作为集成输入，不重复计作用户实现责任。

| 用户任务 | 累计状态 | 本轮完成 / 累计完成 | 未完成、依赖或阻塞 | 责任角色 | 证据与发布 |
|---|---|---|---|---|---|
| A1 领域契约 | 已完成 | 本轮兼容复核；模型/Schema/六API已冻结 | 后续保持兼容 | 用户 / Root | OpenAPI精确等值、Schema/sample；既有提交已推送 |
| A2 安全输入 | 进行中 | 既有ZIP/公开Git安全纵切 | 目标部署安全、完整攻击语料及清理隔离复验 | 用户 / Terra→Luna→Root | 既有真实输入证据；已推送 |
| A3 API/注册表 | 进行中 | 本轮生命周期锁、queued恢复；已有六API/SQLite幂等 | 核心Web与目标环境总验收 | 用户 / Terra→Luna→Root | I2独立70；本轮发布绑定见下 |
| A4 Pipeline | 进行中 | 本轮dispatcher及running零重放收敛；已有规则/AI/报告接线 | 真实scanner/SPDX/AI资产事实集成，依赖组员候选验证 | 用户 / Root集成 | 完整1005 passed/3 skipped；真实输入仍partial/rules/70 |
| A5 AI辅助 | 已完成（子系统） | 既有Provider/Ollama/降级与Pipeline接线 | 全产品真实案例效果随P0总验收，不能由隔离测试外推 | 用户 / Root | 历史真实模型证据已发布；本轮仅隔离Provider计数 |
| A6 报告 | 进行中 | 既有四格式导出、持久化与安全下载；本轮恢复可见性验证 | 真实许可证内容、Web下载和最终匿名验收 | 用户 / Root集成 | 四格式真实GET/摘要验证；实现已推送 |
| A7 集成部署 | 进行中 | 已有集成基线和本机演示 | 真实Web适配、Compose/陌生机验收未开始；依赖前端候选契约对齐 | 用户 / Root集成 | 当前主控仍mock；最终部署未发布 |
| A8 协调验收/材料 | 进行中 | 本轮独立证据、P0范围纠偏与进度治理 | 首批golden指标、资源/版本记录冻结与完整材料；最终Release未开始 | 用户 / Root | 既有记录已推送，本轮发布绑定见下 |

当前可独立演示：安全ZIP/公开Git依赖纵切与阶段报告；显式durable ZIP可重启消费queued，中断running只收敛事实而不重放。缺少真实资源→许可证风险→AI→Web完整链和陌生机部署，不称完整P0成品。本轮无开放阻断I2的缺陷；剩余依赖是候选模块与目标环境验收。

P0剩余5个验收工作包：①A4真实scanner/SPDX/AI资产事实接线；②A7核心页面真实六API与报告下载；③A2/A7部署安全、Compose及陌生机；④A8首批golden cases、可计算指标与真实全链演示；⑤A8资源/版本/许可证/AI记录及P0冻结。此前30–50小时/7–14工作日估计依据不足，已撤回；以第8节基于候选代码核查的分项估算为当前参考。下一轮仅先做①的可验收窄切片。
报名/参赛仍需Owner核实平台资格与权属；完整作品还需上述P0、报告/视频/资源表/匿名与Release；竞争力还需真实案例、基线/消融、误差分析和稳定演示。此处不授权实施产品P1批量Bench等扩展。

本次运行精确 token 数不可获得；开工非硬估算20k–35k，I2功能范围完整完成，实际是否在区间内不可确认；验证补证未扩大产品范围。

I2发布：精确11个源文件/测试/运行及治理文档；未上传运行产物、模型或凭据。功能分支已推送，未合并main/integration、未创建PR或发布Release；随后仅回填本次发布绑定记录。

## 8. 第一版简单产品缺口核查（2026-09-05）

本轮完成核查，不宣称新增产品能力。代码基线5679113；fetch后组员扫描候选f8bedfd6bd823b7459ffbffda9d38c2903984a6c、前端83e89281e941801e1a62f0661d3def6de77f9a8b未变化。只更新既有三份治理文件；无新架构、规格或重复代码。

| 顺序 | 已有可复用代码 | 实测缺口与最小动作 | 有效工程小时估计 |
|---|---|---|---|
| 1 真实扫描链 | 候选scan_sealed_tree、normalize_license、detect_ai_assets；当前A4/B5/A5/A6 | 在现有输入会话内调用；Syft尚丢弃artifact licenses、ScanCode仅全局候选，需准确资源绑定；规则适配不能因一个未知资源阻断整批。修复dataset误识别及重复Evidence ID，不重写检测器 | 7–12 |
| 2 核心Web | 已有NewScan/Progress/Overview/Risks/EvidenceReader与轮询 | 改为冻结请求字段和202→状态/资源/风险/证据读取，下载已有后端报告；不新增仓库validate或PATCH处理状态接口，不引入Graph等P1页面 | 4–7 |
| 3 部署 | 已有API工厂、私有data目录、前端build；deploy仅说明 | 最小Compose/启动说明，固定工具版本与数据卷，目标Linux运行实际受限工具并验证一次重启与全链 | 3–5 |
| 4 P0收口 | 候选指标计算器、已有资源与AI记录 | 从真实扫描结果产首批golden预测而非手填predicted，核验Git/ZIP与四类资源样例、AI降级及资源记录 | 2–4 |

估计依据是上述具体适配点，尚非实测开发速度：先看到简单真实Web约11–19有效小时；原执行书完整P0约16–28有效小时，工具环境准备暂另留2–4小时（合计参考18–32小时）。安装/权限/目标机器阻塞没有可靠上限，因此不再给固定工作日承诺。正式报告、视频、竞争力对照/消融不计入该P0开发估算。

核查证据：扫描候选原测试10 passed/2 skipped（真实工具两项跳过）；独立动态探针复现HF dataset URL额外model及同一行重复Evidence ID。前端候选原测试16 passed，但真实后端按候选multipart字段返回422，正确source_type=zip返回202，而候选validateSnapshot拒绝该真实202。故候选单测通过不等于联调通过。前端还请求冻结API不存在的repositories/validate与PATCH风险路径，报告页自行导出前端快照；应仅适配P0路径与既有报告，不扩后端契约。

环境边界：当前PATH未发现docker/scancode/syft，常用Docker socket未发现；不能据此断言全机未安装。候选工具入口使用/proc/self/fd，本机无该路径；组员历史真实工具测试不等于本轮ZIP→受限工具→A4完成。不得用模拟工具冒充此门禁。

下一任务只做第一行：复用组员候选接通一个ZIP样例，使已知与未知许可证资源都能诚实进入规则/AI降级/报告；不得把根LICENSE分配给全部依赖，也不得把pending自动提升verified。未知资源的处理需保持原公共模型和事实边界。按文件选择候选，避免覆盖旧ingestion导出而回退当前Git能力。

用户A1–A8状态沿用第7节：A1/A5子系统完成，A2/A3/A4/A6已有纵切，A7真实Web与部署未完成，A8首批指标及收口未完成。本轮完成的是A4/A7/A8缺口核查，无新增产品功能；Root主责、独立审计辅助。当前可演示仍为真实依赖扫描、持久查询与阶段报告；完整风险Web和陌生机尚不可宣称。
报名资格/权属由Owner核实；完整作品另需报告/视频/资源表/匿名与发布；竞争力另需案例对照、误差分析及稳定演示。这些不阻止先跑通简单产品，不作为当前扩展功能的理由。
发布范围：docs/p0-first-product-gap-check，仅PROJECT_PROGRESS、AGENT_WORKLOG、05-ai-assistance-log；不合并主线或改组员分支。本次运行精确 token 数不可获得；开工6k–12k估算，核查范围完成，实际区间不可确认，无范围扩张。

## 9. 一个真实ZIP到许可证风险报告（2026-09-05）

本轮A4最小接线已验收：原样复用扫描组员f8bedfd的licenses两文件，新增一个A4薄模块，现有ZIP回调/normalize最小接线。无新接口/Schema/依赖/队列、图谱、B6或Web扩展。分支feat/a4-zip-license-report；仅必要源码、原测试增量与既有运行/治理记录，Root统一提交推送。

动态ZIP真实Uvicorn/default factory：POST202→completed/100，2组件（MIT声明、NOASSERTION未知）、2条review_required；来源JSON pointer与SHA正确，声明保持pending，四格式GET摘要核对且重启后字节相同。没有可绑定许可证的旧输入仍partial/rules70。该完成是manifest扫描链，不是ScanCode/Syft真实工具验收或授权法律结论。
实现46 passed、独立23 passed、最终完整1025 passed/3 skipped/2 warnings。新增读取预算曾使大合法ZIP从partial变failed，独立实测后修复为读前保守跳过，不提高A2限额；原始失败与修复前1023全量结果保留，最终结果单列。两个warning为既有AnyIO与刻意fork提示；三个skip为原可选门禁。原unit/独立定义AST、OpenAPI、Schema/sample和组员SPDX原字节核对通过。

| 用户任务 | 累计状态 | 本轮完成／累计能力 | 未完成或依赖 | 责任／发布 |
|---|---|---|---|---|
| A1 | 已完成 | 本轮保持冻结契约 | 持续兼容 | 用户/Root；既有已推送 |
| A2 | 进行中 | ZIP/Git输入已有；本轮大ZIP不退化 | 目标部署安全复验 | 用户/Root；既有已推送 |
| A3 | 进行中 | 真实ZIP HTTP与重启报告已验 | 核心Web联调 | 用户/Root；既有已推送 |
| A4 | 进行中 | 本轮npm声明→标准化→风险→报告完成 | ScanCode/Syft真实环境与精确来源绑定、AI资产/Python许可证/Git事实仍缺 | 用户/实现→审查→Root；本轮功能分支 |
| A5 | 子系统已完成 | 本轮AI关闭仍完成报告 | 完整案例AI效果 | 用户/Root；既有已推送 |
| A6 | 进行中 | 本轮真实风险内容与四格式重启下载 | Web下载、最终匿名检查 | 用户/Root；本轮验证 |
| A7 | 进行中 | 前端候选和接口缺口已核清 | Web适配未完成；Compose/陌生机未开始 | 用户/Root集成；部署未发布 |
| A8 | 进行中 | 本轮证据与发布记录 | 首批真实指标及P0收口 | 用户/Root；本轮记录 |

当前可独立演示新增上述npm ZIP处理链，尚无完整真实扫描器/AI资产/Web/部署产品。下一步优先复用前端候选接现有六API和报告（此前估计4–7有效工程小时）；外部工具并行准备环境，剩余P0工期取决于该环境，不以本切片完成宣称P0完成。
需要扫描组员提供：Linux/Docker可运行方式、固定ScanCode/Syft版本及校验/命令；一个可再分发小样例的真实输出与组件许可证归属说明（不提供密码/令牌）。已有SPDX无需重写。前端组员需将提交/轮询/报告下载对齐冻结六API，不新建仓库validate、PATCH或Graph；可提交候选由Root复用。由用户决定并发送组员协作消息，本轮未擅自联系真人组员。
报名资格/权属仍由Owner核实；完整作品另需材料/匿名/发布；竞争力另需对照案例/误差分析。这些不计入当前简单产品开发。token开工非硬估算12k–22k；本次运行精确 token 数不可获得，manifest ZIP任务完整交付、实际区间不可确认；明确收窄到可实测声明链，外部工具门禁未关闭。

## 10. 简单真实Web已跑通（2026-09-05）

本轮A7 Web窄切片完成：选择复用组员83e8928核心页面，接当前8318f88后端；无新页面设计、Graph/React Flow、后端接口、运行依赖或锁文件变动。分支feat/a7-simple-web，Root验收后统一推送，未合并main/integration。
默认API，ZIP为默认输入。POST字段按冻结契约，202后仅轮询status，completed/partial才读资源/风险/证据；终态JSON报告补真实许可证/时间/整改。四格式直接下载后端已发布产物，不信任任意href。pending与info保持含义，真实结果只读，未提供时间显示未提供；失败不降mock。

验证：unit20 passed；TypeScript及Vite生产build通过；开发服务、生产preview各10项真实Chrome浏览器检查通过，含ZIP完成、资源/MIT/NOASSERTION、风险/Evidence、深链接刷新零重复POST、四格式SHA与后端相等、390px导航/无横向溢出、partial、无效ZIP异步failed、任务404、零未支持端点/运行异常。桌面与手机截图已人工查看，产物仅仓库外。
两项真实阻断已关闭：queued直接读取resources导致409并停轮询；partial无报告实际409 report_not_ready/not_generated不应整页失败。测试初稿把无效ZIP误期望为POST拒绝，已按原异步协议修正为202→failed；选择器文本与响应式渲染等待修正，不修改后端或降低断言。Root新增重复cancelled判断的TS错误已修复后重新检查。一次测试服务退出导致connection refused，重启后验收通过；不混记为产品缺陷。实现子任务状态异常后Root中止并接手，源码归属无并发覆盖。
后端源码/Schema/测试完全未变，未重复既有1025项后端全量；该计数仍属于8318f88历史验收，本轮证据是20前端测试和真实浏览器闭环。

| 用户任务 | 累计状态 | 本轮／累计完成 | 未完成或依赖 | 责任与发布 |
|---|---|---|---|---|
| A1 | 已完成 | 公共契约保持不变 | 持续兼容 | 用户/Root；既有已推送 |
| A2 | 进行中 | 真实ZIP上传、非法ZIP失败提示 | 目标部署安全复验 | 用户/Root；后端未改 |
| A3 | 已完成（当前单机API范围） | 本轮真实页面消费冻结六API | 部署总验收归A7 | 用户/Root；本轮功能分支 |
| A4 | 进行中 | npm声明风险报告已有，页面可查看 | 真实ScanCode/Syft及AI资产接线 | 用户/Root；后端未改 |
| A5 | 已完成（子系统） | AI关闭的真实链仍可用 | 完整案例效果验收 | 用户/Root；既有证据 |
| A6 | 已完成（本机报告链） | 本轮真实页面四格式下载及摘要一致 | 最终材料匿名检查归A8 | 用户/Root；本轮功能分支 |
| A7 | 进行中 | 本轮简单Web、生产build/preview完成 | Compose、目标环境与陌生机未开始验收 | 用户/Root集成；未发布部署 |
| A8 | 进行中 | 本轮复用来源、测试、运行和发布记录 | 首批真实golden指标及P0冻结 | 用户/Root；本轮记录 |

当前能独立演示浏览器ZIP→真实扫描→资源/待核验风险/Evidence→报告，含刷新与失败提示。尚非完整扫描器/AI资产/陌生机P0产品。剩余主包：真实扫描器及资产接线、最小部署验收、首批样例指标和资源记录收口；下一任务优先最小Compose并落实扫描工具运行环境，不增加服务治理或多机架构。部署本身沿用此前3–5有效工程小时估计，环境未确认前不承诺整体剩余天数。
报名资格/权属仍由Owner确认；完整作品另需材料/匿名/发布；竞争力另需对照案例与效果证据，均不扩张当前简单产品范围。token开工12k–22k非硬估算；本次运行精确 token 数不可获得，Web任务完整交付、实际区间不可确认，无功能范围扩张。

## 11. 最小Compose与真实工具环境（2026-09-05）

本轮分支`feat/a7-minimal-compose`，基线a1a710f。Root复核最新组员分支未变，没有重复部署代码；只增加既有deploy目录下必要配置和两个复现脚本、根.dockerignore，并更新既有运行/资源/治理文档。backend/frontend/Schema/规则/tests源码未改，未扩P1/P2。

最小部署已完成：web/api健康；Chrome extension插件真实ZIP→completed报告与刷新恢复；真实HTTP9项及重建API后四格式SHA相等。API UID10001/data0700、只读根、cap_drop ALL与唯一127.0.0.1:8080端口核验。scanner按需profile，非root/断网/只读linux/amd64：ScanCode32.5.0实际识别MIT，Syft1.51.0实际识别is-number@7.0.0及lock来源。官方工具包SHA、基础镜像manifest digest已固定，命令及版本见deploy/README.md。
Chrome JSON点击后download事件超时，下载管理页被插件策略禁止，未绕过；浏览器文件保存结果仍未确认，四格式下载内容由HTTP独立验证，不混为Chrome下载保存成功。此项不影响已运行部署和工具环境，但本轮浏览器下载验收项保持未完成。未运行历史1025后端全量，没有把工具原始输出映射成Web已使用工具。

| 用户任务 | 累计状态 | 本轮完成／累计完成 | 未完成、未开始或依赖 | 责任角色 | 证据／发布状态 |
|---|---|---|---|---|---|
| A1 | 已完成 | 领域与六API冻结契约保持 | 持续兼容 | 用户/Root | 保护目录不变；既有已推送 |
| A2 | 进行中 | 本轮Linux容器ZIP成功、路径穿越输入失败 | Linux公开Git与最终安全复验未完成 | 用户/Root | 真实HTTP，部署分支 |
| A3 | 已完成（单机范围） | 单worker与既有持久派发在容器运行 | 无新队列任务；部署总验归A7 | 用户/Root | API健康、容器重建后原状态保持 |
| A4 | 进行中 | 既有manifest链保留；本轮外部工具环境实跑 | 工具输出接主链与AI资产事实仍未完成 | 用户/Root，依赖组员适配器 | 两工具真实输出；未声称Web工具接线 |
| A5 | 已完成（子系统） | 本轮默认AI关闭不影响Web报告 | 完整案例效果、容器模型运行未验 | 用户/Root | 既有本机模型证据，本轮未调用 |
| A6 | 已完成（本机报告链） | 本轮四格式在容器重建后字节一致 | Chrome文件保存确认未完成；最终匿名归A8 | 用户/Root | HTTP四格式SHA通过 |
| A7 | 进行中（最小部署已完成） | Compose、Docker安装与工具环境、Chrome真实页面完成 | 陌生机复现未开始；完整P0部署待A4收口 | 用户/Root；只读审查子任务 | 构建/健康/权限/HTTP/工具通过；功能分支发布 |
| A8 | 进行中 | 本轮运行说明、来源、AI/验证记录 | 首批真实golden指标、P0冻结未完成 | 用户/Root | 本轮治理记录，未Release |

当前可独立演示容器Web ZIP→资源/待核验风险/Evidence→报告，并独立运行外部工具样例。仍无工具与AI资产的完整产品主链；当前Compose明确关闭Git/AI，不能把既有宿主机能力外推为容器已支持。
P0余下三包：①工具与AI资产接线及案例效果；②最终输入/容器安全与陌生机复现；③首批真实golden指标及资源记录冻结。下一任务只做①中的真实工具接现有ZIP Pipeline，预计4–8有效工程小时，先核准组员的精确来源绑定，继续不加新API/队列。
剩余整体仅作条件排期约16–28有效工程小时（按每天8有效小时约2–4集中工作日），包含上述三包，前提组员候选可复用、没有新的环境或证据绑定阻断；不是实测工期或保证。环境从未就绪变为已实跑，本次已完成部署不再计入剩余工作，不沿用旧7–14工作日。
报名/参赛仍须Owner核对平台、主体和权属；完整作品还需报告/视频/匿名/正式发布；竞争力另需对照案例、误差分析和稳定演示，不混入当前简单产品开发工期。
本次运行精确 token 数不可获得；开工非硬估算12k–22k，最小部署与工具环境交付完成，Chrome文件保存确认仍未完成，实际token是否落在区间不可确认；无产品功能范围扩大。

发布绑定：最小部署实现`a231d7273cf2e31da3b3d08bbcb3af5075a426a7`已推送`feat/a7-minimal-compose`并经远端完整哈希核对一致；本轮14文件，无业务源码改动，未合并/Release。随后仅追加发布记录。Chrome文件保存确认仍未完成，不改变本节限制。
