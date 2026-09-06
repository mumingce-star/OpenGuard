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
| A8-1b 冗余远端分支清理 | P0治理 | Root | 已完成 | 用户明确授权后复核并删除43个已被 `integration/p0` 完整包含、零独有提交的项目负责人历史远端分支；恢复SHA保留 | 以后只需按短分支策略随合并清理，不再保留每个发布记录分支 | GitHub仅保留 `main`、`integration/p0` 及两条组员分支；组员分支未修改 |
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

## 12. 真实 ZIP 工具接主链（2026-09-05）

分支 feat/a4-real-zip-scanners，基线2dc451d。复用组员f8bedfd现有适配器，补齐受控执行和来源绑定；无新公共API、Schema、队列架构或P1/P2。真实ScanCode32.5.0/Syft1.51.0已进入现有Web报告，两个依赖精确合并且保留原ID，Syft另识别项目自身；根Apache LICENSE未赋给MIT或未知依赖。工具失败保留partial/report/95。内部接受profile仅增加可选工具布尔值，旧任务默认关闭。

| 用户任务 | 累计状态 | 本轮完成／累计能力 | 未完成或未开始 | 责任角色 | 验证证据／发布状态 |
|---|---|---|---|---|---|
| A1 | 已完成 | 公共领域模型及六API保持 | 持续兼容 | 用户/Root | OpenAPI与基线等值、Schema等值；既有发布 |
| A2 | 进行中 | 本轮可信fd回调、同树封印与异常清理 | Linux公开Git、部署安全总验收未完成 | 用户/Root | 独立生命周期/穿越/哈希检查；本轮分支 |
| A3 | 已完成（单机范围） | 接受工具开关与恢复兼容 | 无新增队列任务 | 用户/Root；受限实现子任务 | 相关87项、全量通过；本轮分支 |
| A4 | 进行中 | 本轮真实ScanCode/Syft→许可证/证据/风险/报告 | 最小AI资产事实接线未完成 | 用户/Root；复用组员输入 | 独立36项、真实HTTP与Chrome；本轮分支 |
| A5 | 已完成（子系统） | 既有Provider/真实模型能力保留 | 完整产品案例效果与容器模型未验 | 用户/Root | 本轮AI关闭，未外推旧实测 |
| A6 | 已完成（本机报告链） | 本轮报告含工具来源，重建后四格式SHA不变 | Chrome文件保存确认仍未完成 | 用户/Root | 真实HTTP四格式、Chrome报告/刷新；本轮分支 |
| A7 | 进行中 | 两常驻容器健康，API共享工具层、独立venv | 陌生机复现未开始，完整P0部署待收口 | 用户/Root；部署子任务 | 构建、健康、Chrome通过；未Release |
| A8 | 进行中 | 来源/说明/AI记录与回归同步 | 首批golden指标和P0冻结未完成 | 用户/Root | 全量1103 passed/3 skipped；待Root推送绑定 |

当前可以独立演示Chrome ZIP→真实两工具→资源/待核验风险/来源证据→报告，并在API重建后恢复；没有把pending说成授权确认。仍无完整AI资产纵切，Compose关闭Git/AI，未完成陌生机复现和Chrome文件保存确认。三个skip是已有可选真实模型/公网门禁；本轮不重复前端构建，不宣称完整产品已验。

P0剩余三包：最小AI资产及案例效果、最终输入/部署安全与陌生机复现、首批golden指标与资源冻结。下一任务只接一个明确模型/数据集样例的现有识别结果到资源/风险/报告，先复核组员代码，不加图谱或新接口。条件排期约12–20有效工程小时（按每天8有效小时约2–3集中工作日）；前提候选可复用且无新的环境阻断，不是保证，不把已完成工具接线重复计入。

报名/参赛仍需Owner确认平台资格与权属；完整作品另需材料、视频、匿名与正式发布；竞争力另需对照效果与稳定演示。这些门禁不混入当前简单P0开发估算。本次运行精确 token 数不可获得；开工非硬估算12k–22k，技术范围交付完成、实际区间无法确认；范围仅补内部接受开关和真实格式修复，未扩大产品功能。发布绑定待Root补录。

发布绑定：e50f4ce4fe94f9ce98e169c43286d25a28c70f99 已上传 feat/a4-real-zip-scanners，远端完整哈希核对一致；EVD-A4-REAL-ZIP-SCANNERS-001绑定该实现。上述本轮分支/待推送项现为已推送功能分支，29文件，未合并/Release。工具接线任务完成，A4/P0父任务仍进行中。

## 13. 明确模型引用样例（2026-09-05）

分支feat/a4-ai-asset-report，基线6a832f3。按执行书A4只挂接组员B6；detector沿用f8bedfd并作必要修正。ZIP有限文本中的明确模型引用已进入原AIAsset/风险/Evidence/报告；没有软件依赖的模型ZIP也能完成。复用本机已安装Qwen3身份作为样例背景，不安装、不推理、不上传权重；实际扫描只消费ZIP文本，不读取操作者模型目录。

| 用户任务 | 累计状态 | 本轮完成／累计能力 | 未完成或未开始 | 责任角色 | 验证／发布状态 |
|---|---|---|---|---|---|
| A1 | 已完成 | 公共模型与六API保持 | 持续兼容 | 用户/Root | OpenAPI、Schema等值；既有发布 |
| A2 | 进行中 | 模型读取复用原封印、限额和清理 | Linux公开Git、部署安全总验收未完成 | 用户/Root | 独立边界+全量通过；未改A2实现 |
| A3 | 已完成（单机范围） | 现有资源/风险/报告直接返回模型 | 无新接口或队列 | 用户/Root | 真实HTTP通过；未改API实现 |
| A4 | 进行中（本任务完成） | Qwen3模型引用→资源/待核验风险/报告，保留软件许可 | 真实公开项目完整链与范围覆盖总验收未完成 | 用户/Root；复用组员，Luna验收 | 82实现/9独立；待Root推送 |
| A5 | 已完成（子系统） | 本机锁定manifest身份再次核对 | Compose模型推理与真实项目建议效果未验 | 用户/Root | 本轮AI关闭、未推理；保留旧证据 |
| A6 | 已完成（本机链） | 模型条目、来源行号、四格式和重建恢复 | Chrome文件保存确认仍未完成 | 用户/Root | HTTP四SHA、Chrome详情/报告/刷新通过 |
| A7 | 进行中 | 复用现有Compose，API/Web健康 | 陌生机复现未开始、完整部署待验 | 用户/Root | 仅API重建，无新服务；未Release |
| A8 | 进行中 | 复现脚本、来源、独立测试和治理同步 | 首批golden指标、P0冻结未完成 | 用户/Root | 全量1146 passed/3 skipped；待发布绑定 |

当前能独立演示软件依赖+明确模型引用→待核验风险→文件SHA/行号证据→现有报告；没有将引用当成实际使用或授权。静态链接保守匹配，未知许可证NOASSERTION；不会自动读取远程许可证、核验模型权重或证明完整B6覆盖。Git资产接线、Compose内AI、陌生机及Chrome保存仍未完成。

下一任务：按执行书验收一个真实公开项目的扫描→风险/证据→AI建议→报告，只修阻断主链的问题；先核对已有Git与A5部署差距，不自动加图谱、重试或新接口。P0剩余三包：真实项目完整链/部署差距、陌生机和安全复验、首批golden指标与资源冻结。条件排期8–16有效工程小时，约1–2个集中工作日，前提已有Git/AI实现可复用且无新阻断；不计完整材料和竞争力实验，不是保证。

可报名/参赛仍需Owner确认资格与权属；可提交完整作品另需报告、视频、匿名检查和正式发布；竞争力还需对照效果与稳定演示。无可靠分母，不报完成率。本次运行精确 token 数不可获得；开工10k–18k非硬估算，模型样例任务点完整完成，实际是否在区间无法确认；修复仅限候选接线缺陷，未扩P1/P2。发布绑定待补录。

发布绑定：2ccb75cbd09e7950aa0a98656daea6014dc0e3f9已上传feat/a4-ai-asset-report并核对远端完整哈希；EVD-A4-AI-ASSET-ZIP-001绑定实现，17文件，未合并/Release。上述本轮待发布项现为已推送功能分支；模型样例任务完成，P0父任务仍进行中。

公开项目选样（2026-09-05）：已只读核实huggingface/smolagents固定commit a3df1a21db6045aa9be15b4bdf2067041100e96a（v1.0.0），62文件、约1.20MiB展开，包含Python依赖、明确模型与数据集URL。作为下一轮真实ZIP端到端候选，尚未扫描验收，不改变本节A1–A8完成状态。选样来源与SHA见工作日志PublicSampleSelection；仅治理记录随feat/a4-ai-asset-report发布，未合并/Release。

## 14. 固定公开 ZIP 与真实 Qwen3 报告验收（2026-09-06）

复用分支 feat/a7-public-zip-qwen-acceptance，基线6ac3998。用户中断后检查原任务，发现后台已完成，继续验证原scan而未重新上传或扫描。仅修复 ScanCode 默认漏扫VCS文件、Docker Desktop本机模型连接和原结构校验拒绝的提示词问题；无新公共接口、Schema、队列或P1/P2。

| 用户任务 | 累计状态 | 本任务完成／累计能力 | 未完成、未开始或待验证 | 责任角色 | 验证证据与发布状态 |
|---|---|---|---|---|---|
| A1 | 已完成 | 公共领域及六API保持 | 持续兼容 | 用户/Root | OpenAPI与6ac3998等值；本分支不改契约 |
| A2 | 进行中 | 实际公开ZIP经原安全读取边界 | Linux公开Git与最终部署安全待验 | 用户/Root | 封印fd及预算回归；本分支待发布绑定 |
| A3 | 已完成（单机范围） | 原持久任务正常完成并重建恢复 | 无新增队列任务 | 用户/Root | 同一scan重建后completed；既有实现保留 |
| A4 | 进行中（本任务完成） | 227组件、4引用资产、283证据、231待核验提示进入报告 | 公开Git完整接线和覆盖总验收待完成 | 用户/Root，复用组员输入 | 真实两工具及原ZIP SHA；本分支待发布绑定 |
| A5 | 已完成（本机ZIP链） | Compose调用已有锁定Qwen3，231条pending建议 | 建议效果的golden评测归A8；不声称语义全部正确 | 用户/Root | 模型身份、证据引用、AI前后确定性事实对照通过 |
| A6 | 已完成（本机报告链） | Chrome正文及四格式持久化验收 | Chrome下载保存落盘确认仍待验证 | 用户/Root | 重建后四格式SHA不变；HTTP下载通过 |
| A7 | 进行中（本机部署通过） | API/Web健康，本机Compose+Qwen3运行 | 陌生机复现未开始；公开Git部署待验 | 用户/Root | Chrome原任务刷新恢复；未Release |
| A8 | 进行中 | 本任务复现说明、来源和AI记录同步 | 当前实现首批golden指标、P0最终资源/安全冻结未完成 | 用户/Root | 1200 passed、3 skipped、2既有warning；待发布绑定 |

证据 EVD-A7-PUBLIC-ZIP-QWEN-001：smolagents commit a3df1a21db6045aa9be15b4bdf2067041100e96a，ZIP SHA256 c486d41688b937e208393b95e70fc7293c555b046f4284a8fca7a925fe6ef4a9。AI关闭scan scn_be55489e-b1c1-4de5-81b9-1b8f1b37a4ae，29.33秒；成功AI scan scn_58822f0b-c0c5-47f2-825d-2206103cd597，963.30秒，无errors。保留前述失败报告。Chrome报告有231条AI解释、4引用及文件行号；复用原scan重建后四格式SHA一致。没有重复推理或提交原始报告、目标源码与权重。

当前可独立演示真实公开ZIP→两工具→软件和明确AI引用→待核验提示/证据→本机AI建议→Web与四格式报告。231条提示不等于231个已确认违规；引用不等于实际使用或授权。模型建议尚待人工复核和效果评测。三个skip仍是可选真实模型/公网测试门禁，未冒充通过。本轮真实模型链另有上述独立实跑证据。

P0剩余三包：①现有公开Git输入到部署的最小接线与安全验收；②陌生机复现及Chrome下载保存确认；③当前detector首批golden指标、资源记录与P0冻结。下一任务只核清并补①的具体阻断，不增加Git恢复或调度。条件排期约6–10有效工程小时，加陌生机可用性等待；依据复用既有实现、不扩识别范围，若公网/环境出现阻断再按缺口调整，不保证日历完工时间，不计额外竞赛材料。

可报名/参赛：Owner确认资格、平台与权属；可提交完整作品：上述P0门禁加正式材料、演示视频、匿名检查与正式发布；具备竞争力：还需真实对照、误差分析与稳定演示，不能由本次单案例推导获奖概率。仅列用户A线，不把组员B线算作用户完成项。

本次运行精确 token 数不可获得。恢复收口开工估算6k–12k，任务范围内验收完成，实际token是否落在区间不可确认；未扩展范围。功能分支发布绑定随后追加，未合并main或Release。

发布绑定：实现提交48f6267a27df792c8c248b45d54f4bc8b311346a已推送feat/a7-public-zip-qwen-acceptance，git ls-remote完整哈希与本地一致。19个源码/测试/既有说明文件；未合并main或Release。EVD-A7-PUBLIC-ZIP-QWEN-001绑定该实现，任务点完整交付，P0父任务仍进行中。 上表本轮待发布项现为已发布功能分支；随后提交仅补发布记录。

## 15. 扫描组员首批 Bench 集成验收（2026-09-06）

用户确认组员分支为codex/p0-external-tools-sync，fetch后HEAD=89c8ba2，增量实现1c7239e。保留本机0.1.1检测器和前轮真实ZIP/Qwen成果；精准复用既有组员bench目录/样例/评测代码，不整支覆盖。按执行书B7首批3–5例与第15节Bench、AI资源DoD推进用户A8集成验收，不将B7写成用户独立任务，不做P1批量Bench。

| 用户任务 | 累计状态 | 本轮完成／累计能力 | 未完成或待验证 | 责任角色 | 证据／发布状态 |
|---|---|---|---|---|---|
| A1 | 已完成 | 公共契约保持 | 持续兼容 | 用户/Root | 公共源码/Schema不变，领域回归通过；既有发布 |
| A2 | 进行中 | 5个源文本ZIP走原安全输入 | 公开Git部署与最终安全待验 | 用户/Root | 真实Compose HTTP；本轮分支待绑定 |
| A3 | 已完成（单机） | 复用原5个scan ID验收，无重复任务 | 无新增队列工作 | 用户/Root | 重建后原终态可读；既有发布 |
| A4 | 进行中（本轮验收完成） | 模型/数据集/API正例到Evidence/风险/四格式；普通链接负例不误识别 | 公开Git完整链仍待验 | 用户/Root，组员提供样例 | 5例检测器+动态ZIP+HTTP；不改业务检测器 |
| A5 | 已完成（本机ZIP链） | 本批AI关闭；恢复原Qwen配置，前轮报告四SHA保持 | 建议效果评测未完成，不计作本批识别指标 | 用户/Root | 原Qwen报告verify通过；未重复推理 |
| A6 | 已完成（本机报告链） | API资源在Chrome展示行号；4正例四报告通过 | Chrome保存落盘确认待验 | 用户/Root | Chrome src/client.py:1及真实四格式；本轮分支 |
| A7 | 进行中 | 原Compose复用并恢复AI配置 | 陌生机复现未开始，公开Git部署待验 | 用户/Root | API健康，旧报告保留；未Release |
| A8 | 进行中（首批Bench接入完成） | 复用5例、当前版本实测结果、可计算指标、来源/AI记录 | 标签独立人工复核、P0最终资源/安全冻结待完成 | 用户/Root，限定只读审查 | 159相关测试通过；待功能分支发布绑定 |

EVD-A8-SCANNER-BENCH-001：固定5例不改源片段或expected；当前detector0.1.1 TP=4/FP=0/FN=0，micro precision/recall/F1=1.0；负例自身TP/FP/FN均0，其零分母指标定义为0。结果文件benchmarks/results/static-ai-assets-v1.actual.json SHA a66320164f14741b843341e42d5e3c2c5d575199d6af3d3b5cb02c861731bd0f。组员旧0.1.0结果仍留在原提交历史，未混为当前结果。没有声称真实项目总体准确率、许可证准确率或AI质量得分。

部署实跑4正例全部completed/无errors，4种报告与证据SHA/行号通过；负例failed/scan/dependency_manifest_not_found，零资源summary及resources=409 scan_not_ready符合原契约，不生成报告。首次验收脚本误把负例响应当空列表，仅修正预期后复核同5个ID，未改API、未重复扫描。Chrome真实API条目openai、NOASSERTION及src/client.py第1行openai.responses可见。恢复AI配置后原Qwen报告四SHA通过；本轮正例原任务也再验证通过。完整原始HTTP输出保留仓库外，Git仅提交合成检测器结果及必要复现记录。

当前可独立演示原公开ZIP完整链，并补齐模型/数据集/API带Evidence的首批回归样例和可计算识别指标。P0尚余：公开Git输入/部署安全最小验收、陌生机及浏览器下载确认、最终资源/安全记录冻结与标签人工复核；不再把首批Bench脚本接入算作未完成。下一任务回到公开Git现有缺口，只修阻断。条件估计约4–8有效工程小时，另加异机和人工复核等待；无新环境阻断才适用，不是日历保证，不计额外材料或P1/P2。

报名/参赛仍由Owner核实平台资格及权属；完整作品提交还需材料/视频/匿名检查与正式发布；竞争力需更广真实样例、误差分析和对照效果，不由5例推导。当前任务无代码缺交阻塞，不要求扫描组员重复提交本批代码。

本次运行精确 token 数不可获得。开工8k–16k非硬估算，本轮范围确定为组员首批Bench集成验收并完整收口，未扩P1/P2；实际是否落入区间不可确认。分支feat/a8-scanner-bench-acceptance，发布绑定随后追加。

发布绑定：2f212dbd05079408e477ad7ebdd1e50d094af9eb已推送feat/a8-scanner-bench-acceptance，git ls-remote完整哈希一致；17个必要文件，EVD-A8-SCANNER-BENCH-001绑定该接入提交。首批Bench集成任务完整交付，P0父任务仍进行中，未合并main或Release。 上表本轮待发布项现为已推送功能分支；随后提交仅补发布事实。

## 16. 公开 Git 最小接线与部署验收（2026-09-06）

基线0dcca39，分支feat/a7-public-git-deploy-acceptance。按用户批准的下一任务和执行书P0输入DoD，只补三个缺口：API镜像Git包、Compose默认关闭但可显式开启、Git复用既有ZIP许可证/AI资产/真实工具处理。没有新接口/Schema、复制检测器、Git恢复/重试、图谱或P1/P2。

| 用户任务 | 累计状态 | 本轮完成／累计能力 | 尚未完成、未开始或待验证 | 责任角色 | 验证证据／发布 |
|---|---|---|---|---|---|
| A1 | 已完成 | 六API/领域保持 | 持续兼容 | 用户/Root | OpenAPI与0dcca39等值、Schema无diff；既有发布 |
| A2 | 进行中（Git/ZIP本机门禁通过） | Git实际HTTPS/对象物化/封印树；拒绝非法URL、失败清理 | 最终安全清单冻结、陌生机复验 | 用户/Root，受限实现子任务 | 真实公网+容器控制+Git边界测试；本轮分支待绑定 |
| A3 | 已完成（单机范围） | Git沿用原任务机制、ZIP成果保留 | Git中断自动恢复明确不在本任务范围 | 用户/Root | 原终态及报告重建后恢复；无新队列 |
| A4 | 已完成（P0样例链范围） | Git复用现有manifest许可/AI引用/真实两工具；9组件/11证据/9提示到报告 | 更广识别覆盖不由本样例证明；最终冻结待完成 | 用户/Root，复用组员输入 | 11条Evidence与独立同revision源文件SHA全部一致；本轮分支 |
| A5 | 已完成（本机ZIP链） | Git沿用原Provider参数，恢复本机AI配置 | 本次Git AI关闭，未宣称Git新增实测建议；质量评测仍未完成 | 用户/Root | 旧Qwen四格式SHA保持、Ollama0.33.3可用 |
| A6 | 已完成（本机报告链） | Chrome Git报告及四格式、重建留存通过 | Chrome下载落盘确认待验 | 用户/Root | Git及旧ZIP四格式字节保持；本轮分支 |
| A7 | 进行中（本机Git/ZIP部署完成） | Debian Git包、现有容器控制、显式开关 | 陌生机复现未开始 | 用户/Root | UID10001/只读/cap0/NoNewPrivs/Seccomp/4GiB/128进程；未Release |
| A8 | 进行中 | 运行说明、来源、测试与证据同步；既有首批Bench保留 | 资源/安全清单冻结、标签人工复核 | 用户/Root | 1221 passed/2 skipped/2既有warning；待功能分支发布 |

EVD-A7-PUBLIC-GIT-DEPLOY-001：Chrome创建scn_fed61b87-fc58-4e70-a7af-0d0e5ead9330，公开PyPA sampleproject实际revision621e4974ca25ce531773def586ba3ed8e736b3fc，与事先ls-remote记录相同。13.838659秒，completed/无errors，Git2.39.5、ScanCode32.5.0、Syft1.51.0。9资源/11Evidence/9待核验提示不等于9个已确认违规；根MIT不继承给peppercorn等依赖。实际调用仍跟随公开默认分支，没有暗增pin参数或声称URL永久固定。

HTTP/回环IP/元数据IP/query四类URL接收前422；example.invalid产生scn_8713935b-837a-4b05-8b59-eff6a7810110，failed/ingestion/invalid_source，报告409，工作目录为空。只允许named volume而非宿主目录；系统包来自Debian官方，具体版本与限额进入现有provenance。容器子进程仍共享API网络，不冒充逐进程网络隔离或完整攻击语料验收。

当前可独立演示Git和ZIP→真实扫描→资源/待核验风险/Evidence→Web报告；模型/数据集/API已有样例，ZIP本机Qwen和首批Bench已有证据。本次Git实跑关闭AI，保留原Qwen成果。完整P0尚须两包：①陌生机启动/扫描/下载复现及Chrome保存确认；②最终资源和安全清单冻结、标签人工复核。不再计入已完成Git接线，不开展P1/P2。下一任务优先①，先利用现有部署说明和验收脚本，不新造部署框架。

条件估计仍需约2–4有效工程小时用于复现与冻结准备，另加陌生机可用和人工复核等待；不能保证日历完工时间，遇实际阻断按缺口重估，不混入完整材料或竞争力实验。报名/参赛仍由Owner核对资格、平台及权属；完整作品另需报告/视频/匿名/正式发布；竞争力需更广真实案例、误差分析和对照，不由单案例推断。

本次运行精确 token 数不可获得；开工8k–16k非硬估算，任务范围内技术交付完成，无产品范围扩大，实际是否落入区间不可确认。发布绑定随后追加。

发布绑定：实现0f1bdcc22a01a5f1f91b666d1ae94040bd3929ae已推送feat/a7-public-git-deploy-acceptance并核对远端完整哈希一致；16个既有文件、无新增文件，EVD-A7-PUBLIC-GIT-DEPLOY-001绑定该实现。本任务完整交付，完整P0仍待陌生机及最终冻结；未合并main或Release。 上表本轮待发布项更新为已推送功能分支，随后提交仅补发布事实。

## 17. 异机复现准备与Chrome下载确认（2026-09-06）

基线341dc34，分支docs/a7-browser-download-handoff。用户明确回复目前没有另一台设备，因此真实异机验收尚无法执行，不能用同机容器替代。已在现有deploy/README.md补最短步骤：固定已有完整实现commit、现有Compose、ZIP/Git脚本、重建验证和最小匿名回传信息；不新增脚本、架构或重复样例。

| 用户任务 | 累计状态 | 本轮完成／保留能力 | 待完成或阻塞 | 责任角色 | 证据／发布状态 |
|---|---|---|---|---|---|
| A1 | 已完成 | 公共契约保留 | 持续兼容 | 用户/Root | 本轮无源码变化；既有发布 |
| A2 | 进行中（本机通过） | 原Git/ZIP安全证据保留 | 异机安全复验与最终冻结 | 用户/Root | 原证据不重算；无新增验收结论 |
| A3 | 已完成（单机） | 原任务与报告保留 | 无新队列任务 | 用户/Root | 未重建或重扫 |
| A4 | 已完成（P0样例链） | 原扫描、资产/风险/证据能力保留 | 更广覆盖非本轮范围 | 用户/Root | 原已发布实现 |
| A5 | 已完成（本机ZIP链） | 原Qwen与降级能力保留 | 异机AI未测试 | 用户/Root | 本轮未调用模型 |
| A6 | 已完成（本机报告链），下载待验 | Chrome点击原Git报告JSON链接 | 未确认实际落盘路径/摘要 | 用户/Root | 默认Downloads及桌面精确文件名未发现，已询问用户；不可称下载完成 |
| A7 | 进行中；异机门禁阻塞 | 已整理固定版本最小复现步骤 | 用户当前没有另一台设备 | 用户/Root及异机操作者 | 文档准备不是异机通过；待功能分支发布 |
| A8 | 进行中 | 本轮边界与回传要求同步 | 最终资源/安全冻结、标签人工复核 | 用户/Root | 文档范围，无需重跑原1221测试 |

当前仍可在本机演示Git/ZIP→扫描→资源/风险/Evidence→报告及已验收ZIP/Qwen；未新增异机或浏览器保存成功的主张。下一步取得实际下载文件路径做SHA比对；另一台设备可用后再执行既有复现步骤。设备等待无法给出可靠日历工期；此前2–4有效工程小时仅是复现/冻结准备估算，不包含设备与人工等待。

报名仍需Owner确认资格与权属；完整提交还需异机门禁、最终冻结、材料/视频/匿名及正式发布；竞争力需真实对照和误差分析。本次运行精确 token 数不可获得；开工6k–12k，受设备与下载落盘证据不足限制，本任务部分完成，实际token区间不可确认；未扩大范围。

发布绑定：四份既有文档提交e902c8dd23e2c41d0186592083e8ee3ed4bb8efc已推送docs/a7-browser-download-handoff，远端完整哈希一致；本节待发布项更新为文档已上传。异机及Chrome落盘门禁保持未完成，未合并main或Release。

## 18. Mac 下载修复与资源/安全清单核对（2026-09-06）

基线15b12ec，任务分支feat/a6-download-csp-fix。用户已确认有Windows电脑，异机状态更正为“设备已有、环境待确认”，本轮只在Mac操作。Chrome失败提示为“不符合安全政策”；发现报告下载响应CSP sandbox未允许下载，增加allow-downloads并保留其他安全限制，未修改Chrome设置。61项A6/API相关测试通过（1既有warning）；API重建后原Git和ZIP/Qwen四格式摘要分别verify通过。实际Chrome保存仍需最后落盘证据，不能仅依据HTTP通过结案。

| 用户任务 | 累计状态 | 本轮结果 | 未完成/阻塞 | 责任角色 | 验证及发布 |
|---|---|---|---|---|---|
| A1 | 已完成 | 无公共契约变更 | 持续兼容 | 用户/Root | 既有实现；本轮API回归 |
| A2 | 进行中 | 核对实际cgroup/UID/挂载/端口与原安全清单 | API无CPU配额、隔离与磁盘/fd限制覆盖、供应链锁定待收口 | 用户/Root | 只读运行证据；冻结未通过 |
| A3 | 单机已完成 | 原任务ID和报告重建留存 | 不增加队列/Git恢复 | 用户/Root | 两组原报告verify通过 |
| A4 | P0样例链已完成 | 原Git/ZIP/组员Bench保留 | 本轮无新增识别任务 | 用户/Root | 不重复扫描 |
| A5 | 本机ZIP链已完成 | 旧Qwen报告摘要不变 | 人工效果复核待做 | 用户/Root | 无新推理 |
| A6 | 报告链完成，浏览器验收进行中 | CSP最小修复、相关测试通过 | Chrome实际文件与摘要待确认 | 用户/Root | 本轮修复待发布 |
| A7 | 本机部署完成，异机未开始 | 原数据保留、API更新健康 | Windows环境待确认，本轮不操作 | 用户/Root及异机操作者 | 本机重建验收 |
| A8 | 清单核对完成，最终冻结未完成 | 现有资源/安全文档明确具体差距 | 包版本与声明登记、依赖锁定、安全缺口、人工复核 | 用户/Root | 本轮清单待发布 |

更正此前“主要只剩验收”的宽泛表述：本机演示链确已跑通，但本轮实际核对发现资源/安全冻结包内仍有上述实现和登记缺口，不能只签字关闭。既有2–4有效工程小时估算仅适用于复现/冻结准备，不能覆盖这些尚未完成的安全处理；先限定下一修复点再估时，不因此扩展P1/P2。

当前仍可演示Git/ZIP→真实工具→资源/风险/Evidence→报告和已有ZIP/Qwen；不宣称完整隔离、依赖全部锁定、异机通过或人工确认。报名资格/权属由Owner确认；完整作品另需最终冻结、异机、材料/视频/匿名与正式发布；竞争力需真实对照/误差分析，不由本轮测试推断。

18节结案补充：用户在修复后亲自点击，仍收到“贵组织屏蔽了该文件，因为它不符合安全政策”。A6实际落盘更新为组织策略阻塞；不改Chrome设置或借命令行绕过，待有权管理员处理或符合策略的异机验收。CSP缺失下载许可已最小修复，但不能据此称本机Chrome问题已解决。资源/安全检查已完成，完整任务PARTIAL；下一可在Mac执行的任务优先限定为API CPU配额最小修复与验收，其他隔离/供应链缺口分别按原清单推进，不新增架构。

本次运行精确 token 数不可获得；开工6k–12k，部分完成，实际消耗是否在估算区间不可确认。范围从清单检查增加一处下载CSP及原测试修复，属于已授权阻断排查；未扩P1/P2。

发布绑定：e90ba11466c112e8accd70c2237ec1fb0c22de7a已推送feat/a6-download-csp-fix，远端完整哈希一致，9个既有文件、无新增。上表本轮待发布项更新为任务分支已上传；Chrome组织策略及最终冻结差距保持未完成，未合并main或Release。

## 19. 真实下载策略确认与 API CPU 配额（2026-09-06）

基线d9a6aca，分支fix/a7-api-cpu-limit。Chrome原生下载详情直接确认组织屏蔽，未提供正常保存入口；演示JSON成功不能替代真实附件。本轮未修改组织策略或切换Blob/文件名等路径绕过。CPU配额最小修复仅Compose增加api.cpus:2，无新文件/接口/架构/扫描。

| 用户任务 | 状态 | 本轮完成与证据 | 待完成/阻塞 | 责任角色 | 发布状态 |
|---|---|---|---|---|---|
| A1 | 累计完成 | 公共代码/契约不变 | 保持兼容 | 用户/Root | 既有发布 |
| A2 | 进行中 | 2CPU实际cgroup与节流通过，原权限保持 | 网络隔离、磁盘/fd覆盖、供应链门禁 | 用户/Root | 本轮待绑定 |
| A3 | 单机累计完成 | API重建后旧任务和报告保持 | 无新增队列任务 | 用户/Root | 既有发布 |
| A4 | P0样例链累计完成 | 复用原Git/ZIP结果 | 本轮未复跑扫描性能 | 用户/Root | 既有发布 |
| A5 | 本机ZIP累计完成 | 旧Qwen四SHA保持，无推理 | 人工质量复核 | 用户/Root | 既有发布 |
| A6 | 报告链完成，下载阻塞 | Chrome原生详情直接验证组织屏蔽 | 正常策略环境下四格式落盘验收 | 用户/Root及有权管理员 | 旧修复已上传 |
| A7 | 本机配额任务完成；异机未开始 | Compose配置有效、API健康、真实cgroup=200000/100000 | Windows环境及异机验收 | 用户/Root | 本轮待绑定 |
| A8 | 进行中 | 本项实际结果和剩余边界记录 | 资源/间接依赖锁定、人工复核及最终冻结 | 用户/Root | 本轮待绑定 |

受控4进程各约4秒正常退出，nr_throttled增量41，CPU使用8272191微秒；无目标代码、无新扫描。Git与旧Qwen的smoke --verify各通过，8份报告摘要保持。Compose一行配置修复，验证配置、实际内核节流与报告持久性，无需重跑全部业务单测；未把此前61或1221测试算成本轮新通过。

当前仍能本机演示Git/ZIP→真实扫描→资源/风险/证据→报告及已有Qwen建议。未具备已验收的真实浏览器落盘、异机和完整隔离/供应链冻结。下一任务建议限定现有API Python间接依赖的锁定和重建复核；下载阻塞由有权管理员按组织政策处理或使用符合政策的异机，不能绕过。

可报名/参赛仍由Owner核对资格/权属；完整作品需剩余P0门禁、材料/视频/匿名和正式发布；竞争力另需真实对照/误差分析。没有据此宣称完成率或获奖概率。本次运行精确 token 数不可获得，开工6k–12k，CPU子任务完成、下载仍阻塞，整轮部分完成；无范围扩大，实际token是否在区间不可确认。

发布绑定：d70a1e55e89b0f903f68416823658d33ba3b7517已推送fix/a7-api-cpu-limit，远端完整哈希一致，6个既有文件、无新增。本节待发布更新为任务分支已上传；CPU子任务完成，下载/完整P0未完成，未合并main或Release。

## 20. API Python 间接依赖锁定与真实下载复核（2026-09-06）

基线1d11d01，分支fix/a7-api-python-lock。复用backend/pyproject.toml锁定当前CPython3.12/Linux amd64的15个API运行依赖，Docker从空venv按--no-deps精确安装，检查直接声明覆盖及pip check。实际安装层重建成功、15包集合严格等于重建前及锁定列表；API健康、2CPU保持，原Git/Qwen两组四格式摘要各verify通过。不升级依赖、不新增文件、不扫描/推理；不把API版本锁定外推为所有系统包/发行物hash/许可证已冻结。

AMENDMENT下载诊断：此前把Chrome“组织屏蔽”直接定为组织策略原因不充分。浏览器工具拒绝chrome://policy且要求不绕道，已交用户手动查看，用户确认没有下载相关政策。普通Chrome页面操作已触发真实JSON保存框，用户完成保存后原Downloads文件28846字节，SHA e5af6091ec26877045d7b8c8b68f0d92c422bb5b17ae08667f94ef789fc6a73a，与原receipt完全一致。未改安全设置/文件名/传输路径或使用Blob转存；具体历史拦截触发原因尚未证明。HTML/CSV/资源清单实际文件待本轮后续确认。

| 用户任务 | 累计状态 | 本轮完成/证据 | 未完成/阻塞 | 责任角色 | 发布状态 |
|---|---|---|---|---|---|
| A1 | 已完成 | 公共契约不变 | 保持兼容 | 用户/Root | 既有成果 |
| A2 | 进行中 | API间接版本漂移缺口关闭，2CPU保持 | Debian、隔离/磁盘/fd门禁 | 用户/Root | 本轮待绑定 |
| A3 | 单机已完成 | 原ID/报告重建保持 | 无新增队列任务 | 用户/Root | 既有成果 |
| A4 | P0样例链已完成 | 原链保留 | 本轮无新扫描性能结论 | 用户/Root | 既有成果 |
| A5 | 本机ZIP已完成 | 旧Qwen四SHA保持 | 人工质量复核 | 用户/Root | 既有成果 |
| A6 | JSON真实落盘通过 | 原文件可解析、SHA一致 | 其余三格式待确认 | 用户/Root | 本轮验收待绑定 |
| A7 | 本机依赖锁定完成，异机未开始 | 镜像重建/pip check/15包集合通过 | Windows环境与复现 | 用户/Root | 本轮待绑定 |
| A8 | 进行中 | 锁定边界与下载误判更正 | 来源/声明、剩余安全及人工冻结 | 用户/Root | 本轮待绑定 |

当前可演示原Git/ZIP→扫描→资源/风险/Evidence→报告和已有ZIP/Qwen，真实JSON已可保存。异机、人工复核及剩余资源/安全冻结不算通过。可报名/参赛仍需Owner确认资格/权属；完整作品另需剩余P0门禁、材料/视频/匿名和正式发布；竞争力需真实对照/误差分析，不混入本次工期。

20节最终验收：HTML/JSON/CSV/资源清单四份文件均已在用户Downloads实际保存。大小分别6722/28846/2024/2024字节，SHA全部等于原Git receipt；JSON真实scan_id通过、两CSV为7列9资源行。A6本机真实四格式下载门禁更新为完成，旧组织策略归因撤回为“历史拦截原因未证明”；未改安全设置或传输方式。依赖锁定和本机下载两项本轮均完成，完整P0仍待Debian/资源声明与隔离限制收口、人工和异机验收。

下一任务建议限定实际Debian Git包及其构建可复现性核对，优先复用现有镜像/说明；不把API版本锁定扩称全部供应链已冻结。本次运行精确 token 数不可获得；开工6k–12k，本轮范围完成，实际是否在估算区间不可确认；未新增接口、架构或扫描。

发布绑定：549d7c004c5288d9a443c866744399437b9e815e已推送fix/a7-api-python-lock，远端完整哈希一致。8个既有文件，无新增，本节待发布更新为任务分支已上传；两项本轮完成，完整P0未完成，未合并main或Release。

## 21. Debian Git 构建版本固定（2026-09-06）

基线1b5bb6b，分支fix/a7-debian-git-pin。仅在既有Dockerfile精确指定git与git-man均1:2.39.5-0+deb12u3，并分别检查安装后dpkg版本；默认签名验证保持，无新源、升级或无版本回退。实际安装层重建成功，API健康；运行Git2.39.5，Git二进制SHA2540879925a6881e3877ff7e3330746ba3027b04edf16a3a12dccd1644c4f32d、随包copyright SHA8ceacdebe13249ea8aba6e400418e2b503c83a1f19ad92377380fb32ecf48d0c均与原容器一致。15个API Python包集合与锁定列表相等、cpu.max200000/100000，旧Git与ZIP/Qwen两组四格式摘要各verify通过，无新扫描/推理。

| 用户任务 | 累计状态 | 本轮结果/证据 | 未完成/阻塞 | 责任角色 | 发布状态 |
|---|---|---|---|---|---|
| A1 | 已完成 | 公共契约不变 | 保持兼容 | 用户/Root | 既有成果 |
| A2 | 进行中 | Git版本漂移缺口关闭 | 隔离/磁盘/fd及剩余安全门禁 | 用户/Root | 本轮待绑定 |
| A3 | 单机已完成 | 原报告重建保持 | 无新增队列工作 | 用户/Root | 既有成果 |
| A4 | P0样例链已完成 | 工具原版本/二进制保持 | 本轮不重测新扫描性能 | 用户/Root | 既有成果 |
| A5 | 本机ZIP链已完成 | 旧Qwen四SHA通过 | 人工质量复核 | 用户/Root | 既有成果 |
| A6 | 本机四格式下载已完成 | 原内容保持；不重复下载 | 异机确认 | 用户/Root | 既有成果 |
| A7 | 本机Git固定完成，异机未开始 | 安装层重建、包版本/摘要、API健康通过 | Windows环境及复现 | 用户/Root | 本轮待绑定 |
| A8 | 进行中 | Git来源/版本/边界记录同步 | 资源声明、人工与最终安全冻结 | 用户/Root | 本轮待绑定 |

本轮任务完成不等于全部Debian依赖或镜像字节永久可复现；固定版本不可获取时构建失败，后续明确升级处理，不静默换版。未新增快照服务/文件/接口或P1/P2。当前仍可演示真实Git/ZIP扫描、资源/风险/Evidence、报告下载及已有ZIP/Qwen。下一任务优先核对现有运行资源的来源/许可证与必要声明，复用原台账；异机和其他安全限制分别保持未完成。

报名/参赛需Owner资格/权属确认；完整作品仍需剩余P0门禁、材料/视频/匿名和正式发布；竞争力需真实对照/误差分析。不开新评测范围，不编造完成率。本次运行精确 token 数不可获得；开工4k–8k，本轮范围完成，无范围调整，实际消耗是否在区间不可确认。

发布绑定：dbc0bf54c2e9ec959564d73aa88d2d11a51ee605已推送fix/a7-debian-git-pin，远端完整哈希一致，7个既有文件、无新增。本节待发布更新为任务分支已上传；本轮完成，完整P0仍待剩余门禁，未合并main或Release。

## 22. 运行资源声明核验与前端许可保留（2026-09-06）

基线39d062a，分支docs/a8-runtime-resource-audit。复用原台账核对15个API实际包与9个前端资源的官方固定版本元数据和随包许可，全部对应；纠正ScanCode检测数据CC-BY-4.0登记。发现浏览器产物缺完整版权许可，在原Vite配置从四个现有包自动读取全文生成部署附件；不手抄许可证、不增依赖或接口。构建附件不是新增源码清单。

| 用户任务 | 累计状态 | 本轮完成/证据 | 未完成/阻塞 | 责任角色 | 发布状态 |
|---|---|---|---|---|---|
| A1 | 已完成 | 公共契约保持 | 无本轮新增 | 用户/Root | 既有成果 |
| A2 | 进行中 | 不改变权限或安全配置 | 网络隔离、磁盘/fd及最终安全验收 | 用户/Root | 既有成果 |
| A3 | 单机已完成 | API未重建/未变更 | 无新增队列任务 | 用户/Root | 既有成果 |
| A4 | P0样例链已完成 | 原扫描链保留 | 本轮无新性能结论 | 用户/Root | 既有成果 |
| A5 | 本机ZIP链已完成 | 模型/权重不变 | 人工建议质量复核 | 用户/Root及Owner | 既有成果 |
| A6 | 本机真实四格式下载已完成 | 不重复扫描/下载 | 异机验收 | 用户/Root | 既有成果 |
| A7 | 本机Compose已完成；异机未开始 | web构建/更新成功，20前端测试通过 | Windows环境与复现 | 用户/Root | 本轮待绑定 |
| A8 | 本轮资源核验完成；最终冻结进行中 | 24版本官方元数据一致；4份浏览器原许可全文保留，HTTP200/SHA通过 | 镜像再分发逐包义务（若分发）、服务条款与人工最终确认；Chrome插件附件打开被客户端阻止 | 用户/Root及Owner | 本轮待绑定 |

实际本机与Docker各构建通过；HTML许可链接、部署附件4618字节及四份完整原文逐字包含断言通过，SHA见third_party。JS/CSS名称不变，未重建API、扫描或推理。Chrome插件ERR_BLOCKED_BY_CLIENT不外推为用户正常下载失败，不改保护、不称其可视验收通过。初次本机命令目录重复及PATH缺node失败，修正路径并使用已配置Node后原构建通过，未安装软件。

当前已可本机演示真实Git/ZIP→扫描→资源/许可证风险证据→现有报告，ZIP链已有Qwen建议，真实四格式下载既有验收保持；仍未具备异机、完整安全和人工冻结的验收结论。本轮核验发现的缺失声明已修复，剩余发布方式门禁明确列出，未扩展P1/P2。下一任务：对照现有A2安全验收表，只确认P0网络隔离及磁盘/fd剩余项的实际缺口，再修确有阻断的一项。

可报名/参赛仍需Owner确认资格/权属；可提交完整作品需剩余P0安全/资源人工及异机门禁、材料视频匿名与正式发布；竞争力需真实对照、误差分析和人工质量结果，不混入本轮开发范围。本次运行精确 token 数不可获得，开工6k–12k，本轮核验及发现缺口修复完成，实际是否在估算区间不可确认；范围内增加原Vite配置修改，没有新增仓库文件。

发布绑定：702931556f83e457c5c5cbe2de400699fc07cb6c已推送docs/a8-runtime-resource-audit，远端完整哈希一致；6个既有文件，无新增源码文件。当前核验和必要声明修复完成，完整P0未完成，未合并main或Release。

## 23. P0安全差距核对与文件描述符限制（2026-09-06）

基线079b14c，分支fix/a2-nofile-limit，开工干净、Root单写。仅修一个实际缺口：API及tools的nofile从默认1048576/1048576落实安全表256/256。沿用Compose和tool-smoke，无新源码文件/依赖/API/Schema/队列/图谱。网络共享及data卷任务配额缺口已定位到原代码/配置，保持未完成，详情见安全表9.4。

| 用户任务 | 状态 | 本轮结果与验证证据 | 待完成/阻塞 | 责任角色 | 发布状态 |
|---|---|---|---|---|---|
| A1 | 累计完成 | 契约不变 | 保持兼容 | 用户/Root | 既有成果已上传 |
| A2 | 进行中；本轮fd配置完成 | 最终内核256/256、EMFILE及释放恢复；runner失败回收、后续调用成功 | 网络deny-egress、任务磁盘配额及完整耗尽/隔离验收 | 用户/Root | 本轮待绑定 |
| A3 | 单机累计完成 | API重建后旧任务报告保持 | 无新调度工作 | 用户/Root | 既有成果已上传 |
| A4 | P0样例链累计完成 | 两工具原小样例在256限制下通过 | 无新公开样例性能结论 | 用户/Root | 既有成果已上传 |
| A5 | 本机ZIP累计完成 | 原Qwen四SHA保持，不推理 | 人工质量复核 | 用户/Root与Owner | 既有成果已上传 |
| A6 | 本机四格式下载累计完成 | 原报告SHA保持，不重复下载 | 异机确认 | 用户/Root | 既有成果已上传 |
| A7 | 本机配置完成；异机未开始 | Compose配置/重建成功，API健康/2CPU保持 | Windows环境及复现 | 用户/Root | 本轮待绑定 |
| A8 | 资源核验完成；最终冻结进行中 | 无新增第三方资源，原声明保持 | 人工、服务条款、最终冻结；镜像再分发义务依发布方式确认 | 用户/Root与Owner | 既有成果已上传 |

本机API与独立禁网tools分别通过nofile边界和ScanCode/Syft小样例。初始6+新增250=256，下一次打开EMFILE、释放恢复、hard提高失败；首次假定初始3的失败保留，查明Rosetta占用后按实际初始数断言。通过真实run_json_tool验证失败映射、子进程回收及下一次调用成功；不将其外推为API主进程整体fd耗尽恢复或完整NEG-A2-028。最终API重建后两组原receipt各verify四SHA保持。

当前仍可本机演示Git/ZIP→真实工具→资源/待复核风险证据→四格式报告及已有ZIP/Qwen建议；未具备异机、完整安全和人工冻结验收结论。下一任务限定：复用现有上传/工作目录，确认并落实P0任务临时磁盘硬上限及失败清理；网络隔离单列，不以全API断网破坏Git/Qwen接线。

可报名/参赛需Owner资格/权属确认；完整作品需剩余P0安全/异机/人工门禁及材料、视频、匿名和正式发布；竞争力需真实对照及误差分析。不编造完成率或获奖概率。本次运行精确 token 数不可获得，开工6k–12k，本轮范围完成、无扩大，实际是否在估算区间不可确认。

发布绑定：06e3e54318811c2c93b5c7c115c59e17585f8acc已推送fix/a2-nofile-limit，远端完整哈希一致；7个既有文件，无新增文件。fd配置及本轮边界验收完成，全P0未完成，未合并main或Release。

## 24. 工作目录临时磁盘硬上限（2026-09-06）

基线780536b，分支fix/a2-workspace-disk-limit；Root单写。现有workspaces由无任务硬配额的data子目录改为1GiB共享tmpfs，保留已有目录名称和API。原ZIP写目标失败从误报损坏修为scanner_failed/workspace_write_failed。复用tool-smoke，不建新清单/配置/接口/依赖。更新前确认queued/running=0且原工作目录空，持久上传/数据库/报告未删除。

| 用户任务 | 状态 | 本轮结果/验证 | 未完成/阻塞 | 责任角色 | 发布状态 |
|---|---|---|---|---|---|
| A1 | 累计完成 | 契约及既有错误码保持 | 保持兼容 | 用户/Root | 既有已上传 |
| A2 | 本轮工作目录上限完成；整体进行中 | 真实1GiB容量、接收/解压ENOSPC、失败清理/恢复；190回归通过 | 默认deny-egress、持久上传累计预算等剩余安全/压力验收 | 用户/Root | 本轮待绑定 |
| A3 | 单机累计完成 | 保留uploads/dispatch，相关持久派发测试通过 | 无新队列任务 | 用户/Root | 既有已上传 |
| A4 | P0样例链累计完成 | 最终挂载上小ZIP正例/清理通过 | 本轮无Git磁盘耗尽全链结论 | 用户/Root | 既有已上传 |
| A5 | 本机累计完成 | 原Qwen四SHA保持，不推理 | 人工质量复核 | 用户/Root及Owner | 既有已上传 |
| A6 | 本机四格式下载累计完成 | 原报告保持，不重复下载 | 异机确认 | 用户/Root | 既有已上传 |
| A7 | 本机完成；异机未开始 | API健康，实际mount/uid/mode/cpu/nofile通过 | Windows复现 | 用户/Root | 本轮待绑定 |
| A8 | 资源核验完成；最终冻结进行中 | 无新资源 | 人工/服务条款/正式冻结与发布方式审查 | 用户/Root及Owner | 既有已上传 |

1GiB为工作目录共享上限（不保证每任务预留），工具/tmp另有256MiB，持久上传/报告不在其中。写满只在无生产卷隔离容器执行；剩余1MiB和3MiB分别验证接收及解压失败后清理，底层errno=ENOSPC，恢复后同一摄取服务成功。首次回归107通过/2条回环监听PermissionError，原样受控复验2通过；追加81通过，合计190通过、1条既有弃用warning。最终生产挂载小正例与旧Git/Qwen各四SHA通过。

当前仍可Mac本机演示Git/ZIP→真实扫描→资源/风险证据→报告及已有Qwen建议；缺少生产扫描子进程网络隔离、剩余存储预算/安全压力、人工和异机验收。下一任务：落实扫描子进程默认deny-egress，只允许既有Git获取与Qwen调用按原边界工作，不把整个API断网或新增队列作为替代。

可报名/参赛仍需Owner资格/权属确认；完整作品需剩余P0门禁、材料视频匿名及正式发布；竞争力需真实对照/误差分析和人工质量结果。本次运行精确 token 数不可获得，估算6k–12k，范围完成无扩大，实际是否在区间不可确认。

发布绑定：7ec1a418d018e03552361ab48fb27371bd7c1709已推送fix/a2-workspace-disk-limit，远端完整哈希一致；8个既有文件，无新增文件。本轮工作目录硬上限/真实超限清理完成，全P0未完成，未合并main或Release。

## 25. 扫描子进程默认禁网（2026-09-06）

基线872b2f1，分支fix/a2-scanner-no-network。当前Compose默认通过原生seccomp启动器执行既有扫描runner，禁非AF_UNIX socket/socketpair及io_uring，后代继承；Git/AI继续原路径。直接在Rosetta安装过滤失败已保留，BUILDPLATFORM原生启动器实际通过。新增一个必要C源码，不重复生成模块/队列/接口；构建GCC与静态运行库声明已登记。实际异机构建/运行仍未完成。

| 用户任务 | 状态 | 本轮完成/验证证据 | 未完成/阻塞 | 责任角色 | 发布状态 |
|---|---|---|---|---|---|
| A1 | 累计完成 | 契约无变化 | 保持兼容 | 用户/Root | 既有已上传 |
| A2 | 本轮扫描禁网边界完成；整体进行中 | 4类socket EPERM、后代继承、失败关闭；真实工具及授权网络保持 | 跨任务文件/IPC隔离、持久累计预算、其他安全矩阵 | 用户/Root | 本轮待绑定 |
| A3 | 单机累计完成 | 无队列变更、原报告保持 | 无新调度任务 | 用户/Root | 既有已上传 |
| A4 | P0样例链累计完成 | 生产固定工具入口和目录fd通过；Git真实获取及清理 | 无总体准确率新结论 | 用户/Root | 本轮待绑定 |
| A5 | 本机累计完成 | 原模型短generate成功、身份匹配 | 人工建议质量复核 | 用户/Root与Owner | 既有已上传 |
| A6 | 本机四格式下载累计完成 | 原两组四SHA保持 | 异机确认 | 用户/Root | 既有已上传 |
| A7 | 本机部署完成；异机未开始 | 原API健康，Git/Qwen开关及data卷保持 | Windows从源码build及运行验收，不能跨架构直接搬镜像 | 用户/Root | 本轮待绑定 |
| A8 | 台账更新完成；最终冻结进行中 | 必要构建资源及静态库声明记录 | 构建依赖完整锁定/再分发义务、人工及最终冻结 | 用户/Root与Owner | 本轮待绑定 |

182相关回归通过、1 opt-in网络测试跳过、1既有弃用warning；本轮另有生产Git实际获取（固定revision621e4974ca25ce531773def586ba3ed8e736b3fc）和Qwen短调用通过，不将跳过算通过。原生启动器下MIT/is-number样例与最终API固定入口Apache-2.0/is-number正例均通过。原两组报告四SHA保持。

当前仍能Mac本机演示Git/ZIP真实扫描→资源/风险证据→四格式报告及已有Qwen建议；本轮解决扫描子进程网络创建边界，未宣称完整跨任务文件/IPC隔离、安全冻结或异机通过。下一任务优先对照剩余P0门禁核验跨任务工作目录读取边界，复用现有只读会话和受控fd，不扩展队列或图谱。

可报名/参赛需Owner资格/权属确认；完整作品需剩余P0安全/异机/人工、材料视频匿名及正式发布；竞争力需真实对照及误差分析。本次运行精确 token 数不可获得；开工6k–12k，本轮目标完成，因转译限制新增必要原生启动器/构建阶段，未扩展产品范围，实际是否在估算区间不可确认。

发布绑定：665bd3862c221d1648fde16a00f8f0e07119cb07已推送fix/a2-scanner-no-network，远端完整哈希一致；10个既有文件及1个必要C源码。当前扫描禁网/Git和Qwen保持验收完成，全P0未完成，未合并main或Release。


## 26. 扫描跨任务工作目录读取边界（2026-09-06）

基线d38f897，fix/a2-scanner-file-boundary；Root单写。原runner真实合成标记复现跨任务读取；原C启动器加入Landlock ABI>=3（本机原生8）、当前目录fd只读与独立temp白名单，失败关闭。复用全部原文件，ScanCode固定串行模式0，原Git/Qwen路径保持。无新接口/队列/图谱/依赖。

| 用户任务 | 状态 | 本轮完成/累计证据 | 未完成/阻塞 | 责任角色 | 发布状态 |
|---|---|---|---|---|---|
| A1 | 累计完成 | 原契约兼容 | 保持兼容 | 用户/Root | 既有已上传 |
| A2 | 本轮读取边界完成；整体进行中 | 六路径内核拒绝、输入只读/temp可写/fork继承；155相关回归 | 剩余安全表与持久累计预算核对、最终安全冻结 | 用户/Root | 本轮待绑定 |
| A3 | 单机累计完成 | 原生命周期和报告保留，无调度变更 | 无新队列任务 | 用户/Root | 既有已上传 |
| A4 | P0样例链累计完成 | 最终镜像真实ScanCode Apache-2.0、Syft is-number正例 | 不外推总体准确率或任意后代exec兼容 | 用户/Root | 本轮待绑定 |
| A5 | 本机累计完成 | 原Qwen四SHA保持，本轮不重复推理 | 人工建议质量复核 | 用户/Root与Owner | 既有已上传 |
| A6 | 本机四格式下载累计完成 | 旧Git/Qwen各四SHA保持，已有Chrome落盘验收保留 | 异机确认 | 用户/Root | 既有已上传 |
| A7 | 本机完成；异机未开始 | 最终API健康，实际workspaces探针清理通过 | Windows设备尚未执行复现 | 用户/Root | 本轮待绑定 |
| A8 | 资源核验完成；最终冻结进行中 | 无新依赖，复用Linux内核接口 | 人工/条款/构建资源与正式发布冻结 | 用户/Root与Owner | 既有已上传 |

最终窄白名单不开放整个/proc或/dev/shm；整个/proc实验方案被自动审批拒绝，已撤回且未生产部署。当前Rosetta任意后代re-exec可能失败关闭，现有两工具固定入口实际可用；后代安全探针为fork。安全表9.7保留兼容失败和范围。最终更新前确认任务空闲及工作目录空，保留data，原两组报告各四SHA均通过。

当前可在Mac演示Git/ZIP真实扫描→资源/许可证/风险证据→四格式报告及已有Qwen建议。尚无异机、完整安全矩阵与人工冻结结论。P0剩余工作包为：剩余安全/存储条目核清并仅修阻断、Windows复现、人工质量与资源发布冻结；不据局部测试编造完成率或新工期。下一任务：核对持久上传/报告累计占用与P0原要求，先确认是否存在需要修复的实际缺口。

可报名/参赛需Owner资格与权属确认；完整作品需上述P0门禁及材料、视频、匿名、正式发布；竞争力需真实对照、误差分析及人工质量证据。本次运行精确 token 数不可获得，开工估算6k–12k，任务范围完成；为兼容转译改用既有串行模式，未扩大产品范围，实际用量是否在估算区间不可确认。

发布绑定：103aa77a8ce1a2d9c76fd45b64a791fe9e02cf44已推送fix/a2-scanner-file-boundary，远端完整哈希一致；9个既有文件、无新增文件。本机已部署并验证，跨任务读取边界完成，完整P0未完成，未合并main或Release。

## 27. 分支归并（2026-09-06）

用户授权整理分支。47个远端分支中，41个历史头已完整包含于450b8eb；保留main、integration/p0、两位组员分支、异机验收分支及PR #2来源。通过保留历史的PR合并至integration/p0后，按未变化的远端头和祖先关系清理。恢复SHA见原协作说明，实际执行结果见PR与最终refs核对。不合并main，不将治理整理当P0已完成。

本轮1222项unit/security通过、3项跳过、2条既有warning；前端20项通过，当前本地TypeScript/Vite构建成功。仅更新3个原治理文件，无业务代码、接口、扫描、推理或部署变化。

| 用户任务 | 状态 | 证据 | 待完成/阻塞 | 责任/发布 |
|---|---|---|---|---|
| A1/A3/A4/A6 | 累计功能完成 | 契约、生命周期、真实扫描、本机四格式下载保留 | 最终异机验证 | 用户/Root；已有提交归并 |
| A2 | 进行中 | 原边界验收及本轮完整回归 | 剩余安全/存储核清 | 用户/Root；已有提交归并 |
| A5 | 本机完成 | 原Qwen证据保留 | 人工质量复核 | 用户/Root与Owner；已上传 |
| A7 | Mac完成；异机未开始 | 固定验收版本保持 | 组员异机回传 | 用户集成/组员执行；未Release |
| A8 | 治理审查完成；整体进行中 | 41分支清单、原SHA、完整回归 | PR及清理执行、最终人工冻结 | 用户/Root；本轮PR |

当前可演示Git/ZIP到真实资源/风险/证据、四格式报告及已有Qwen建议。下一产品任务仍为P0剩余条目核对，异机由组员执行。报名需Owner资格权属；完整作品需P0冻结及材料/视频/匿名/正式发布；竞争力需真实对照与误差分析。精确token不可获得，开工3k–6k；按既有协作规则将目标由main调整为integration/p0，未扩产品范围。

执行结果：PR #3已合并，integration/p0=4056069b7dce35eecf36652dfc98ad9b96d5e147，与源8d13765文件树完全一致。归并完成；自动审批拒绝删除41个远端分支，理由是需要明确批量删除授权，命令未执行、分支数量未减少。main/组员/异机版本保持；清理等待用户批准，非代码或测试失败。本条远端结果追加发布在原验收分支，集成分支业务内容已完成归并。

## 28. 本人历史分支清理完成（2026-09-06）

用户明确授权删除不用的本人分支并要求不触碰组员分支。刷新远端和PR状态后，PR #2/#3均已合并，PR #1仍使用前端组员分支。先把当前本人治理记录合入并推送integration/p0，再逐一确认43个本人历史远端头均未移动、为integration/p0祖先且零独有提交，随后删除这些远端引用及对应本地分支。恢复SHA继续保存在`docs/06-github-collaboration.md`；源码、部署、前端、规则、Bench、测试和第三方目录相对PR #3合并结果零变化。

| 用户任务 | 状态 | 本轮完成/验证证据 | 未完成/阻塞 | 责任角色 | 发布状态 |
|---|---|---|---|---|---|
| A1 | 累计完成 | 契约与Schema未变化 | 保持兼容 | 用户/Root | 已在integration/p0保留 |
| A2 | 进行中 | 已完成的输入及安全边界提交均可追溯，未删除代码 | 剩余安全/持久预算核清与最终冻结 | 用户/Root | 历史分支已清理，提交保留 |
| A3 | 单机累计完成 | API、注册表、持久派发与报告链源码树不变 | 无新增队列任务 | 用户/Root | 已在integration/p0保留 |
| A4 | P0样例链累计完成 | 真实工具、许可证/风险/证据接线源码树不变 | 不外推总体准确率 | 用户/Root | 已在integration/p0保留 |
| A5 | 本机累计完成 | PR #2已合并，Qwen与降级实现保留 | 人工建议质量复核 | 用户/Root与Owner | 来源分支已清理，提交保留 |
| A6 | 本机四格式下载累计完成 | 报告生成、下载与原证据保留 | 异机确认 | 用户/Root | 已在integration/p0保留 |
| A7 | Mac完成；异机未开始 | 固定复现提交450b8eb仍可追溯 | Windows复现 | 用户/Root | 已在integration/p0保留 |
| A8 | 本轮分支治理完成；整体进行中 | 43个本人远端分支删除；远端仅四条预期分支 | 人工/资源/安全最终冻结 | 用户/Root与Owner | 治理结果待本轮记录推送 |

GitHub保留分支为`main`、`integration/p0`、扫描组员`codex/p0-external-tools-sync`和前端组员`feat/xzb-frontend`。两条组员分支的SHA分别保持89c8ba2和83e8928，未删除、合并、改写或推送。未合并main、未改仓库权限、未force push，也未删除用户运行数据或未跟踪的说明书产物。本地`docs/project-flowchart`含独有未上传图表，因未证明可丢弃而保留。

当前仍可在Mac演示Git/ZIP真实扫描到资源、许可证/风险证据、四格式报告及已有Qwen建议。尚无Windows异机、完整安全矩阵和人工冻结结论。报名/参赛仍需Owner资格与权属确认；完整作品还需上述P0门禁以及材料、视频、匿名和正式发布；获奖竞争力仍需真实对照、误差分析及人工质量证据。下一任务仍按P0剩余门禁推进，不因分支清理新增功能。

## 29. 中国市场界面汉化（2026-09-06）

基线`e0845c0`，短分支`feat/zh-cn-ui`。复用现有前端API适配层和许可证规则台账完成用户可见中文化：历史英文风险、规则判断和8条Qwen整改建议在显示层转换；资源类型、风险结果、证据来源、页面辅助标题改为中文；`NOASSERTION`显示为“待核验（NOASSERTION）”。新扫描的15条许可证规则和Qwen语言要求改为简体中文。品牌、包名、SPDX标识、文件路径、ID、Schema/API枚举和原始证据保持原值。

| 用户任务 | 状态 | 本轮完成/验证证据 | 未完成/阻塞 | 责任角色 | 发布状态 |
|---|---|---|---|---|---|
| A1 | 累计完成 | 领域模型、Schema和稳定枚举未改变；完整回归通过 | 保持兼容 | 用户/Root | 既有成果已上传 |
| A2 | 进行中 | 本轮未改变安全边界；Compose重建后健康 | 持久上传/报告累计预算及剩余安全表核清、最终安全冻结 | 用户/Root | 既有成果已上传 |
| A3 | Mac单机累计完成 | 保留30个终态历史任务；无queued/running，未新增队列逻辑 | 无本轮新增调度工作 | 用户/Root | 既有成果已上传 |
| A4 | P0样例链累计完成 | 15条既有许可证规则用户文案中文化；规则ID、动作和版本保持 | 不外推总体准确率 | 用户/Root | 已并入`integration/p0` |
| A5 | 本机累计完成；本轮中文输出完成 | Qwen输入语言为`zh-CN`，系统提示要求简体中文；旧8条建议显示层完整汉化 | 人工建议质量复核 | 用户/Root与Owner | 已并入`integration/p0` |
| A6 | 本机四格式下载累计完成 | 当前Web报告的风险、资源和整改建议中文显示；原下载报告与证据未改写 | Windows异机确认 | 用户/Root | 已并入`integration/p0` |
| A7 | Mac部署累计完成 | API/Web新镜像均健康；Chrome实查首页、真实风险、资源和报告 | Windows复现由组员执行 | 用户/Root；组员执行异机 | 已并入`integration/p0` |
| A8 | 进行中 | 无新增依赖/接口/文件；用户界面语言边界和AI辅助记录已更新 | 人工/资源/安全最终冻结及正式发布 | 用户/Root与Owner | 已并入`integration/p0` |

验证结果：前端21项测试和TypeScript/Vite生产构建通过；规则/AI定向94项通过；完整后端在受限环境为1192通过、30项仅因回环绑定EPERM失败，原样在受控权限复验为1222通过、3跳过、2条既有warning。Compose保留命名数据卷重建，API/Web均healthy。Chrome插件核对截图原任务、8条风险完整报告、资源类型筛选和首页；除品牌、技术标识和原始证据外未见遗留英文用户文案。没有重新扫描、调用模型或改写历史数据。实现`6c836ed`已并入`integration/p0`；本人短分支已删除，GitHub恢复`main`、`integration/p0`及两条组员分支，组员SHA未变。

当前Mac可独立演示中文首页、Git/ZIP真实扫描、ScanCode/Syft、资源/许可证风险与证据、历史Qwen建议及四格式报告。仍不具备Windows异机、完整安全矩阵、AI建议人工质量和最终资源/发布冻结结论。可报名/参赛仍需Owner确认资格与权属；完整作品还需上述P0门禁以及材料、视频、匿名和正式成果链接；获奖竞争力仍需真实对照、误差分析和人工质量证据。下一任务回到P0主线：核对持久上传/报告累计占用与原安全要求，只修实际阻断项。

本次运行精确token数不可获得；开工估算10k-16k，本轮汉化、测试和Chrome部署验收完整完成。范围内增加历史8条AI建议兼容翻译，未扩展接口、队列、图谱或P1/P2功能，无法确认实际token是否落入估算区间。

## 30. 汉化后真实 Git 运行配置恢复（2026-09-06）

用户提交的公开仓库任务`scn_3bd54e48-59e6-4deb-8214-189b183c3198`停在`queued/0%`。数据库无错误且工作目录为空；容器实查确认汉化后重建API时公开Git、AI及Docker到宿主Ollama三个开关均回到默认`0`。问题来自部署时未保留真实模式环境变量，汉化显示代码没有阻塞扫描。

本轮按既有部署边界恢复三个开关，容器内核对Ollama 0.33.3、锁定Qwen3标签和完整模型摘要；通过现有`GitScanRuntime`执行原任务ID，没有为该仓库创建第二条记录。任务在42秒内完成：Git revision `e32b3e6cea77f65e2c10bd5b1a0fe3d745057bac`，8组件、10证据、8条待复核风险、8条Qwen3中文建议、零错误。Chrome原进度页显示7/7阶段、100%及已完成；四格式实际字节SHA与报告链接全部一致。部署说明已在原文件补充ZIP默认模式、Git/Qwen真实模式及每次重建保留开关的要求，不改变安全默认值、接口、队列或恢复架构。

| 用户任务 | 状态 | 本轮完成/验证证据 | 未完成/阻塞 | 责任角色 | 发布状态 |
|---|---|---|---|---|---|
| A1 | 累计完成 | 契约、Schema和稳定枚举未变 | 保持兼容 | 用户/Root | 既有成果已上传 |
| A2 | 进行中 | 原网络与文件边界保持；本轮未放宽容器安全配置 | 持久上传/报告累计预算及最终安全冻结 | 用户/Root | 既有成果已上传 |
| A3 | Mac单机累计完成；本轮配置回归已关闭 | 原排队任务复用同一ID到`completed/100%`；无active任务 | 不增加Git恢复架构；Windows异机仍待验 | 用户/Root | 本轮待绑定 |
| A4 | P0样例链累计完成 | 用户所选真实Git仓库完成8组件/10证据/8风险 | 不外推总体识别准确率 | 用户/Root | 本轮待绑定 |
| A5 | 本机累计完成 | 锁定Qwen3生成8条中文待复核建议，身份摘要匹配 | 人工建议质量复核 | 用户/Root与Owner | 本轮待绑定 |
| A6 | 本机四格式累计完成 | HTML/JSON/CSV/资源清单下载字节与链接SHA一致 | Windows异机确认 | 用户/Root | 本轮待绑定 |
| A7 | Mac真实模式恢复并验证；异机未开始 | API健康、三个开关为1、Chrome进度7/7 | Windows复现由组员执行 | 用户/Root；组员执行异机 | 本轮待绑定 |
| A8 | 进行中 | 原部署说明补足真实模式重建规则，无新资源 | 人工/资源/安全最终冻结及正式发布 | 用户/Root与Owner | 本轮待绑定 |

核验过程中有一次验收命令漏传`--public-git`，因而创建了一个自建`demo` ZIP任务`scn_379f4c01-dd3c-4eb5-a9b5-9dd1093c3579`；它已终态完成并诚实保留一条`ai_response_invalid`降级，没有触碰用户Git任务，也未删除运行数据。最终queued/running为0。该失误已记录，不把它算作本轮产品证据。

当前Mac可独立演示中文界面、公开Git/ZIP真实扫描、ScanCode/Syft、资源/许可证风险与证据、Qwen3中文建议和四格式报告。仍缺Windows异机、持久数据累计预算核清、AI建议人工质量以及资源/安全/发布最终冻结。可报名/参赛仍需Owner确认资格与权属；可提交完整作品还需上述P0门禁以及材料、视频、匿名和正式成果链接；具备获奖竞争力还需真实对照、误差分析和人工质量证据。下一任务回到P0主线：核对持久上传/报告累计占用与原安全要求，只修实际阻断项。

本次运行精确token数不可获得；开工估算4k–8k，本轮诊断、运行配置恢复、原任务执行、报告/Chrome验证和原说明修订均完成，没有扩展P1/P2。实际消耗是否在估算区间不可确认。

发布绑定：文档提交`65f532dd9c9751d8af284a19a148e6d7435302bf`已推送并通过普通非快进合并进入`integration/p0`，合并提交`6cb53eb45734c9f6571203e59345dd4315b7bb48`已推送。本人短分支已删除；`main`和两条组员分支未修改。

## 31. 真实进度动态视觉与 AI 耗时诊断（2026-09-06）

当前集成线的进度页沿用前端组员`46f1640`/`83e8928`相同页面结构。原条形图以`stageIndex/7`为值：后端进入摄取并返回5%时仍有0个阶段完成，因此截图表现为空条。现改用冻结API的`progress`作为唯一目标值，从0开始在浏览器内单调平滑到最新后端值；2.5秒轮询得到15/35/55/70/85/95/100时继续递增。动画绝不越过API值，减少动态效果时直接显示真实值，partial/failed不补到100。阶段列表保留，运行阶段增加脉冲/流光；AI阶段显示Qwen3逐条生成及持续轮询说明。

AI诊断确认不是无限卡死。现有`apply_ai_remediations`对每个eligible finding串行调用一次Provider；每次在同一10秒上限内先核验Ollama 0.33.3、锁定模型名/摘要，再生成最多1024 token的结构化建议。8条风险样例42秒并全部生成；用户随后运行的`openai-python`任务有133条风险，总耗时172.40秒后进入partial，最终`ai_response_invalid`且0条AI整改，确定性133资源/165证据及四报告保留。当前存储不记录逐条推理耗时或失败在第几条，不能编造更细结论。规模越大，串行设计越慢；本轮只改善真实状态表达，不擅自改批处理、上限或模型契约。

| 用户任务 | 状态 | 本轮完成/验证证据 | 未完成/阻塞 | 责任角色 | 发布状态 |
|---|---|---|---|---|---|
| A1 | 累计完成 | API进度字段及Schema未改 | 保持兼容 | 用户/Root | 既有已上传 |
| A2 | 进行中 | 不改变扫描/模型权限边界 | 持久累计预算与最终安全冻结 | 用户/Root | 既有已上传 |
| A3 | Mac单机累计完成 | 真实状态轮询仍为2.5秒；无新接口/SSE | Windows异机验收 | 用户/Root | 既有已上传 |
| A4 | P0样例链累计完成 | 8资源成功样例与133资源partial样例均诚实展示 | 总体准确率和大仓库边界仍待人工判断 | 用户/Root | 既有已上传 |
| A5 | 本机可用；质量复核进行中 | 8条样例成功；133条样例发现结构校验失败 | AI规模、耗时及建议质量需P0裁决 | 用户/Root与Owner | 诊断已记录，本轮待绑定 |
| A6 | 本机四格式累计完成 | completed显示100，partial按后端停95；原报告可读 | Windows异机确认 | 用户/Root | 本轮待绑定 |
| A7 | Mac部署累计完成 | Web单服务重建healthy；Chrome实查95/100真实值 | Windows复现 | 用户/Root；组员执行异机 | 本轮待绑定 |
| A8 | 进行中 | 无新依赖/接口/文件；说明及AI日志更新 | 人工/资源/安全/发布最终冻结 | 用户/Root与Owner | 本轮待绑定 |

当前Mac仍可独立演示中文Git/ZIP扫描、真实工具、资源/风险证据、Qwen3建议与四格式报告；本轮进度视觉已完成，AI大规模串行耗时和一次输出校验失败不能包装成完全解决。P0仍缺持久上传/报告累计预算核清、Windows异机、AI人工质量与规模裁决、资源/安全/发布冻结。下一任务保持P0主线：先核对持久累计占用；AI若被Owner认定为演示阻断，再以现有证据单独确定最小处理策略。

可报名/参赛仍需Owner确认资格与权属；可提交完整作品还需上述P0门禁及材料、视频、匿名和正式成果链接；具备获奖竞争力还需真实对照、误差分析和人工质量证据。本次运行精确token不可获得；开工估算6k–12k，本轮实现、诊断、构建及Chrome验收完成，未扩展P1/P2，实际是否在估算区间不可确认。

发布绑定：实现提交`f23be24a314c1e2495ce1d5e8016086304171487`已推送，并以普通非快进合并进入`integration/p0`；合并提交`84ceb9f15ea2d9a9910761f1d1a1e92151d50993`已推送。本人短分支核对包含关系后删除；`main`和两条组员分支未修改。

## 32. 恢复原扫描行为与大仓库页面阻断修复（2026-09-06）

本轮撤销尚未推送的“每任务最多8条AI建议”后端实现，API镜像重新由`d9f4cad`基线构建；`backend/app`、API Dockerfile和Compose运行配置相对该基线零差异。对汉化前`e0845c0`与汉化实现的精确比较也确认Pipeline、公开Git摄取、ScanCode、Syft和容器资源限制没有改动。同一8组件`chatbot-streamlit-demo`在汉化前分别为42.39、42.27、41.02秒，汉化后为41.80、40.53秒，没有可复现的汉化性能回退。

用户截图对应`crewAI`任务有627组件，258.54秒后以`partial/95%`终态保留627风险；该输入远大于8组件成功样例。汉化前227组件`smolagents`在Qwen成功生成231条建议时也用时963.30秒，因此不能把大输入耗时归因为汉化。本轮不新增加速策略、批处理、上限或超时调整。只在现有前端适配层修复终态报告再次逐条请求712条Evidence的问题：报告已有不可变证据快照时直接复用，只请求确实缺失的证据；同时把历史部分结果说明中文化并按错误码和消息去重。历史任务中的`ai_assist_limited`继续如实显示，后续任务不会再由当前后端生成该错误。

| 用户任务 | 状态 | 本轮完成/验证证据 | 未完成/阻塞 | 责任角色 | 发布状态 |
|---|---|---|---|---|---|
| A1 | 累计完成 | 稳定API、Schema和枚举未改 | 保持兼容 | 用户/Root | 既有已上传 |
| A2 | 进行中 | 扫描安全边界和容器资源配置未改 | 持久上传/报告累计预算与最终安全冻结 | 用户/Root | 既有已上传 |
| A3 | Mac单机累计完成 | 无active任务后保留数据卷重建；历史任务可恢复 | Windows异机验收 | 用户/Root | 本轮本地待发布 |
| A4 | P0样例链累计完成 | 8组件成功任务及627组件部分结果均由既有API读取 | 大仓库外部工具完整率仍需样例边界说明 | 用户/Root | 本轮本地待发布 |
| A5 | 本机可用；人工复核进行中 | 恢复汉化前逐条Qwen行为，撤销未发布的8条限额 | 大规模耗时及建议质量仍需Owner裁决 | 用户/Root与Owner | 本轮本地待发布 |
| A6 | 本机四格式累计完成 | 终态JSON证据直接复用；既有报告数据未改 | Windows异机确认 | 用户/Root | 本轮本地待发布 |
| A7 | Mac部署累计完成 | API/Web均healthy，三项真实模式开关为1；Chrome实查95%部分结果及100%成功任务 | Windows复现 | 用户/Root；组员执行异机 | 本轮本地待发布 |
| A8 | 进行中 | 无新依赖、接口或文件；前端22项及生产构建通过 | 人工/资源/安全/发布最终冻结 | 用户/Root与Owner | 本轮本地待发布 |

当前Mac可独立演示中文Git/ZIP扫描、真实ScanCode/Syft、资源/风险证据、Qwen3建议及四格式报告；小样例既有成功任务可在Chrome正常恢复，大仓库工具超时或解析不完整时诚实保留部分结果。尚未具备大仓库全部外部工具必然成功、Windows异机、AI建议人工质量、持久累计预算及最终资源/安全/发布冻结。

可报名/参赛仍需Owner确认资格与权属；可提交完整作品还需上述P0门禁及材料、视频、匿名和正式成果链接；具备获奖竞争力还需真实对照、误差分析和人工质量证据。下一任务回到P0主线：核对持久上传/报告累计占用与原安全要求，只修实际阻断项。本次运行精确token数不可获得；开工估算4k–8k，本轮在原范围内完成恢复、直接阻断修复、构建和Chrome验收，未扩展P1/P2。

## 33. 产品完整回退至汉化前基线（2026-09-06）

用户明确要求放弃汉化后改动并完整恢复汉化前版本。当前产品源码、规则、测试、根说明、前端说明及部署说明已逐文件恢复到汉化前最后提交`e0845c00aabfb46443e59e3bbc861f5887748234`，`git diff --exit-code e0845c0`对这些路径为零。Git历史未重写；仅三个治理记录继续按追加规则保留汉化、诊断和本次回退事实。用户`output/`、SQLite数据卷、既有报告和组员分支均未修改。

回退前最后一个crewAI任务`scn_c790c3da-158d-44b4-a822-391e914861b0`在重建前自然终态：308.82秒、627组件、712证据、627风险、0条AI整改，`partial/report/95%`，外部工具及AI服务降级错误原样保留。回退后API/Web均healthy，公开Git、AI及宿主Ollama开关仍为1，active任务为0。Chrome确认8组件既有任务可在4秒内恢复到7/7、100%；627组件历史结果页在汉化前实现中超过20秒仍读取中，因为原实现会逐批读取大量Evidence。本轮完全回退，因此没有保留后来增加的证据快照复用、中文错误去重或动态进度。

| 用户任务 | 状态 | 本轮完成/验证证据 | 未完成/阻塞 | 责任角色 | 发布状态 |
|---|---|---|---|---|---|
| A1 | 累计完成 | 汉化前稳定API与Schema原样恢复 | 保持兼容 | 用户/Root | 既有基线已上传；回退提交待发布 |
| A2 | 进行中 | 汉化前安全实现保持，运行数据未删 | 持久上传/报告累计预算与最终安全冻结 | 用户/Root | 回退提交待发布 |
| A3 | Mac单机累计完成 | 重建前等待Git任务自然终态；重建后active=0 | Windows异机验收 | 用户/Root；组员执行异机 | 回退提交待发布 |
| A4 | P0样例链累计完成 | 8组件成功任务和627组件部分结果均保留 | 大仓库外部工具完整率和读取耗时边界 | 用户/Root | 回退提交待发布 |
| A5 | 本机可用；质量复核进行中 | 恢复汉化前英文提示与逐条Qwen行为 | AI大规模耗时、服务可用性和建议质量裁决 | 用户/Root与Owner | 回退提交待发布 |
| A6 | 本机四格式累计完成 | 既有持久数据未改 | Windows下载确认；大报告原版读取较慢 | 用户/Root | 回退提交待发布 |
| A7 | Mac部署累计完成 | 双容器healthy，三项真实模式开关为1，Chrome成功样例通过 | Windows复现 | 用户/Root；组员执行异机 | 回退提交待发布 |
| A8 | 进行中 | 产品树与`e0845c0`一致；20前端及117相关后端测试通过 | 资源/安全/发布最终冻结 | 用户/Root与Owner | 回退提交待发布 |

当前Mac仍可独立运行汉化前版本的Git/ZIP扫描、ScanCode/Syft、资源/风险证据、Qwen3建议和报告。中文风险文案、动态0–100进度、部分结果中文去重以及大报告Evidence快照复用均已撤销。大仓库扫描与历史结果页仍可能较慢，这是所选汉化前版本的已验证行为。

P0仍缺持久累计预算、Windows异机、AI人工质量与规模裁决、资源/安全/发布冻结。可报名/参赛仍需Owner确认资格与权属；可提交完整作品还需关闭P0门禁并准备材料、视频、匿名和成果链接；具备获奖竞争力仍需真实对照、误差分析和人工质量证据。下一任务应先决定是否接受汉化前版本的大仓库耗时边界，再继续持久累计占用核查。本次运行精确token数不可获得；开工估算5k–9k，完整回退、测试、部署和Chrome验收均在原范围内完成。

## 34. 公开 Git 容量失败修复与汉化前产品链复验（2026-09-06）

用户截图任务`scn_2a8b4e19-b530-498a-b0cd-ec2ae2d36913`的来源为`https://github.com/run-llama/llama_index`。生产容器内复用原`GitIngestionService`得到内部原因`scanner_failed:git_materialized_limit_exceeded`：Git/TLS/公网获取已通过，仓库物化超过512MiB安全上限。该上限及原通用错误消息均已存在于汉化前`e0845c0`，不是汉化引入的扫描故障。本轮不提高或绕过上限，只让四类既有容量错误返回“Public Git repository exceeds the configured scan capacity limit.”，保留原错误码、Schema和接口。

Root在Chrome正常“新建扫描”页亲自提交`https://github.com/andreped/chatbot-streamlit-demo`，产生任务`scn_eac4fbff-99de-4c3e-9849-a81a8416c789`。页面依次显示5%、85%和100%，46.30秒完成7/7阶段；固定Git revision为`e32b3e6cea77f65e2c10bd5b1a0fe3d745057bac`，得到8组件、10证据、8条待复核风险和8条Qwen3整改建议，零错误。四报告实际下载均为200：HTML 6208字节/SHA `5c544669...c7ad0`，JSON 40466字节/SHA `370e36ba...c51b`，CSV与资源清单各1769字节/SHA `e056dff8...5a17`。

API/Web均healthy；公开Git、AI和Docker宿主Ollama开关为1；容器能读取锁定模型`qwen3:4b-instruct-2507-q4_K_M`及摘要`0edcdef3...ba0`。API保持只读根文件系统、drop ALL capabilities、no-new-privileges、2 CPU、4GiB内存、128 PID、nofile 256及1GiB工作目录tmpfs；成功与容量失败后工作目录为空。25项公开Git相关回归通过、2项需要受控网络的测试按声明跳过、1条既有AnyIO弃用warning。

本轮API重建时未先确认活动任务，导致更早的`smolagents`任务`scn_0bb32fbb-89d0-44ef-bcec-fe13576569ae`失去内存执行线程并停在85%。按现有worker中断语义一次性收敛为`partial/ai_assist/85%`，保留80组件、6个AI资源及全部既有事实，追加`worker_interrupted`并生成四报告；没有重放Git或Qwen，也没有删除记录。最终注册表`queued/running=0`。依既定范围不新增Git恢复、lease或队列；后续重建前必须先核对活动任务为0。

| 用户任务 | 状态 | 本轮完成/验证证据 | 未完成/阻塞 | 责任角色 | 发布状态 |
|---|---|---|---|---|---|
| A1 | 累计完成 | 错误码、API、Schema和稳定枚举不变，仅细化容量提示 | 保持兼容 | 用户/Root | 本轮待绑定 |
| A2 | 进行中 | 512MiB Git物化上限保持；容器安全配置和失败清理通过 | 持久上传/报告累计预算及最终安全冻结 | 用户/Root | 本轮待绑定 |
| A3 | Mac单机累计完成 | 新真实任务正常终态；被重建中断的旧任务诚实收敛且active=0 | Windows异机；不在P0扩展Git恢复 | 用户/Root；组员执行异机 | 本轮待绑定 |
| A4 | P0样例链累计完成 | 小型公开Git真实完成8组件/10证据/8风险；超限输入明确拒绝 | 大仓库支持边界需写入最终使用说明，不外推总体准确率 | 用户/Root | 本轮待绑定 |
| A5 | 本机可用；人工复核进行中 | 锁定Qwen3生成8条建议，模型身份摘要匹配 | AI建议质量与规模裁决 | 用户/Root与Owner | 本轮待绑定 |
| A6 | 本机四格式累计完成 | 新任务四报告200、实际字节和SHA已核验 | Windows下载确认 | 用户/Root | 本轮待绑定 |
| A7 | Mac部署累计完成 | Docker双服务healthy；Chrome真实提交、进度、结果和报告页面通过 | Windows复现 | 用户/Root；组员执行异机 | 本轮待绑定 |
| A8 | 进行中 | 无新依赖、接口或文件；根因、限制和操作失误均已留痕 | 人工/资源/安全/发布最终冻结 | 用户/Root与Owner | 本轮待绑定 |

当前Mac可独立运行和演示汉化前版本的公开Git/ZIP扫描、ScanCode/Syft、资源/许可证风险与证据、Qwen3建议及四格式报告；合规规模的公开Git仓库已重新实跑通过。当前不具备超过512MiB物化上限的仓库扫描、运行中安全重启自动恢复、Windows异机、AI人工质量、持久累计预算及最终资源/安全/发布冻结。

可报名/参赛仍需Owner确认资格与权属；可提交完整作品还需关闭上述P0门禁并完成材料、视频、匿名和正式成果链接；具备获奖竞争力仍需真实对照、误差分析和人工质量证据。下一任务回到P0主线：核对持久上传与报告累计占用，只修明确缺口。本次运行精确token数不可获得；开工估算8k–14k，本轮根因修复、Docker重建、Chrome真实扫描、Qwen和四报告验收完整完成；额外发现并安全收敛一条由本轮重建中断的旧任务，未扩展产品架构。
