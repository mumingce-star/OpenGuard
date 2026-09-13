# OpenGuard P1 Workspace Contract

Status: FROZEN — P1 CONTRACT V1

Contract Version: 1.0

Baseline: integration/p0

36d1b794909bf2e655e5968e1a8b3eb03a27bc15

Approved by: Project Lead

Approval Date: 2026-09-13

唯一权威 Markdown：`docs/spec/p1-workspace-contract.md`。本文件冻结的是数据、API提案和功能边界，不代表 P1 功能已实现或部署。正式 Schema 位于 `schemas/p1/`，固定合成样例位于 `docs/p1/object-examples.json`。未来实现必须同时满足 Schema 与下文的跨对象语义约束；JSON Schema 不能独立证明证据真实性。

## 1. 来源、范围与 P0 保护

依据 V2.0 技术规划、A-P1-01 Review 草案和负责人 FINAL V1 Freeze 批准条款。Review 提交为 `646c678bb878cccb561aee56ec4abbaa9ea23fa5`。本轮只冻结 Contract/Schema/Examples，不改 backend、frontend、rules、pipeline、deploy、schemas/p0 或生产配置。

P0 ScanRun contract=0.1.1、Assessment schema=1.0 保留。现有状态机、Git/ZIP 安全限制、覆盖、partial、证据引用、自动 Initial Assessment、正常 Qwen 流程、历史报告与四种下载行为不变。运行中的 ScanRun 仍按既有状态机更新，P1 不回写其事实。

代码事实：Project.id 每次扫描新建；registry 已有 list_runs，排序 created_at DESC/scan_id ASC；无公开 GET /api/v1/scans。Assessment timeline 已使用 offset。Git input_digest 是已有规范化输入 URL 的摘要，不等于源代码内容 hash；inventory_digest 与 facts_hash 分开。Assessment.rule_version 是完整组合串，不截断为许可证规则版本。前端 UI verification/handling 不是后端授权枚举。

生产配置以既有冻结记录为准，本轮不重新验收生产：Detector 0.2.0、Rules 2026.09.2、STEP6.1 2/192/384、ScanCode 32.5.0、Syft 1.51.0。

## 2. 权威层级

Scan Facts > Formal Assessment > P1 Views / Workflow / Graph / AI / UI。

Unknown != Prohibited；Unknown != Allowed；Pending != Verified；Detected License != Authorization；Root License != Dependency License；file observation != blanket grant；Finding != confirmed violation；Obligation detected != violated；AI/Graph != Formal Assessment；Task done != compliance verified；History/Diff != rescan；GET != scanner/Qwen/metadata fetch。

P1 metadata 只是额外观察，不回写旧 ScanRun，不提升 authorization 或旧 Formal Assessment。未来正式评估接纳新证据需单独批准有来源的新事实和评估版本流程。用户备注不是 Evidence。

## 3. Architecture Decision Record

以下九项均为 APPROVED；约束是负责人批准后的最终方案，替代旧草案中的待定方案。

### DECISION-01 — APPROVED，A with change：项目身份

GitHub 使用 `canonical_github_repo_v1`；Project.id 仍是单次扫描对象 ID。不引入持久 Project 实体。

只从已知事实规范化身份：host=github.com；owner/repo 构成键 `github.com/<owner>/<repo>`，GitHub owner/repo 大小写归一为小写，去 repo 末尾 `.git` 和路径末尾 `/`；scheme、query、fragment、branch/revision 不参与身份。禁止联网追踪 redirect、rename 或 fork 同一性。

身份等价不放宽输入准入：现有 P0 URL policy 仍只接受安全公开 HTTPS Git URL，拒绝 query/fragment、凭据、不安全端口及 GitHub 非两段仓库路径。P1 不让原本被拒的 URL 绕过准入；对合法已有 source 复用原 policy 的解析/host/path校验语义，再提取身份键。不能为剥除 branch 而接受任意 tree/blob URL。非 GitHub 或无法可靠识别的历史输入保守 scan_only，不猜仓库关联。

ZIP 默认 scan_only，key=scan_id；不得按 filename、archive hash、目录名推断长期项目。跨 ZIP 人工关联不在 P1 V1。

### DECISION-02 — APPROVED，A with change：资源双键

`resource_identity_key` 表示跨扫描逻辑资源；`resource_instance_key` 表示该次扫描观察到的具体实例，不替代原 resource_id。

Package identity 优先规范化 PURL 去版本，保留身份所需 type/namespace/name/qualifiers；无可靠 PURL 时仅使用已知 ecosystem+该生态规范化包名，不能猜 ecosystem。AI identity 使用 resource kind + resource provider + canonical resource identity/name；runtime provider 不属于资源 provider。instance 可以加事实中的 version、revision、resolved identity、必要 scope/location；没有依据的键为null，不用空字符串冒充已识别。

Diff 先 exact instance key（须唯一且逻辑identity一致），再唯一 identity key 候选；多候选 ambiguous/unmatched，绝不强配。已匹配候选不得被重复使用。版本2.31→2.32可以表示version changed。禁止 fuzzy、名字相似度、Levenshtein、LLM、位置猜测、URL猜测。不同 project_identity 默认409 not_comparable。只有可靠事实位置才可作为实例区分，不可猜测位置。

### DECISION-03 — APPROVED，A：事实图

Graph formal=false。只允许七种现有事实边，见第7节。禁止推测依赖、共现、自动传递许可证、root→所有依赖/AI资源。Assessment Dimension 不进入V1；未来仅能作为独立 assessment overlay 另行设计。

### DECISION-04 — APPROVED，A with change：任务固定版本

Task 固定 scan_id、assessment_id/version，绝不绑定latest。CAS expected_version 控制写入。status仅todo/in_progress/done/dismissed；done/dismissed必须非空白note，长度≤2000字符。note只是workflow note，不能改变verification、authorization或Formal Assessment。新Assessment不改变旧Task绑定；view可显示superseded=true，但它不是人工status，不能自动完成/驳回任务。

### DECISION-05 — APPROVED，B with change：metadata最小化

V1 sidecar只存规范化字段、bounded excerpt、source_url、requested/resolved revision、fetched_at、content hash、parser version、field source/locator、verification status、coverage gaps、producer/provenance。bounded_excerpt最多1000字符，传输字节限制由后续安全实现独立控制。

禁止持久化完整远程raw payload；Schema不允许raw_payload或任意扩展包。明确full_response_replay_available=false，不能保证原响应完整重放。离线fixtures是测试材料，不是Production raw cache。以后保存raw必须新schema version、provider-specific storage policy、size limit、license/terms review及retention policy，不得偷加V1。

### DECISION-06 — APPROVED，A：分页兼容

新增P1 list API使用opaque cursor，绑定sort/filter/anchor；非法或失效明确400 cursor_invalid，不能默默回第一页。History排序created_at DESC,scan_id ASC，与registry一致。旧Assessment timeline offset完全不改。Graph完整图不是分页list API，不接受cursor/limit。

### DECISION-07 — APPROVED，A with change：不可变快照

NoticeDraft、ReportV2Snapshot显式POST创建；GET只读。固定scan reference、assessment ID/version、facts_hash、usage_hash、完整rule_version；包含Task则固定ID/version集合，包含Notice则固定ID/hash，包含Graph/Profile则固定算法version及内容hash。

相同幂等键同输入返回旧对象；同键异输入409；显式重新生成需新幂等请求及新的draft_id/snapshot_id，不能覆盖。Notice成功!=obligation fulfilled；Report成功!=compliance verified。

### DECISION-08 — APPROVED，B with change：完整图容量

V1返回所选filter范围的完整图，允许filter或必要只读selector，无cursor/limit及半实现续页字段。必须有容量常量/配置，数值不硬编码于Schema。超限返回413 graph_capacity_exceeded，details含安全的count_basis=estimated|actual、node_count、edge_count、configured_capacity:{max_nodes,max_edges}，不返回伪完整前N节点。允许用户缩小filter。

完整范围必须覆盖该selector对应节点和已列事实边所需端点；过滤后不能悬空引用。`coverage.view_complete=true`只表示已有事实在选定范围内图完整，scan_gaps仍保留partial。未来分页/引用闭包须新的兼容Contract变更。

### DECISION-09 — APPROVED，A with change：路径和编号

唯一Contract为`docs/spec/p1-workspace-contract.md`。docs/p1仅examples、receipts、supporting notes、handoff；不得另建同义权威Contract。任务编号统一V2.0：A01–A09、B01–B07、F01–F07。旧handoff编号只作历史，正式开发/PR按V2.0内容和编号。

## 4. 对象、层与Ownership

| 对象 / Schema文件 | 层 | 存储 | 主责 / 审阅 / 消费 |
|---|---|---|---|
| ScanHistoryItem / scan-history-item | view | 只读派生 | A / cz,xzb / xzb |
| ScanDiffView / scan-diff-view | view | 只读派生 | A / cz,xzb / xzb,report |
| ResourceGraphView / resource-graph-view | view | 只读派生 | A / cz / xzb,report |
| ResourceProfile / resource-profile | view+观察 | 事实派生+不可变metadata sidecar | cz解析,A存储/传输/API / 双方 / xzb |
| RemediationTask / remediation-task | workflow | 独立持久化、CAS审计 | A / cz,xzb / xzb,report |
| NoticeDraft / notice-draft | report | 不可变snapshot | cz内容事实,A快照/API / 双方 / xzb,report |
| ReportV2Snapshot / report-v2-snapshot | report | 不可变snapshot | A / cz,xzb / xzb,交付 |

不另建扫描架构。不往严格scans.db添加P1表；旧assessment.db与报告保留。未来sidecar建库、容量及部署需后续任务验证和授权。派生缓存不是V1首版要求；若添加，key需包含facts hash/算法/参数，评估相关再含assessment ID/version/usage_hash/rule_version。

## 5. 公共Schema与来源

七对象独立JSON Schema Draft2020-12，schema_version固定"1.0"，$id=`urn:openguard:p1:<object-file-stem>:1.0`。common.schema.json仅复用严格值对象，非万能业务模型；所有对象additionalProperties=false。字段与类型以七Schema及common为准，下文定义语义。

ScanRef：scan_id/revision/facts_hash/input_hash/inventory_hash/status/registry_revision。revision是Git/资源来源版本，registry_revision是并发存储版本，不混用。input hash不当源码hash；inventory缺失为null；facts hash使用已有assessment.engine.facts_digest，不重新定义P0哈希算法。

AssessmentRef固定scan_id/assessment_id/version/facts_hash/usage_hash/rule_version/formal=true。Provenance记录producer、source_refs、assessment_refs、UTC生成时间、算法及参数hash。EvidenceRef namespace=scan时必须在该scan找到evidence_id；profile_observation引用不可伪装成旧scan Evidence。

Hash均64位小写SHA256，UTC用RFC3339 Z。新P1内容hash规范化UTF-8 JSON、键排序、紧凑分隔、拒绝NaN/Infinity；集合按稳定标识排序、语义有序数组保序。快照hash排除自身content_hash；Report另排除artifacts避免循环，每个artifact独立hash。视图语义hash排除读取时generated_at。

History用原scan_id；Diff/Graph/Profile投影ID由输入+算法版本确定性产生；tsk_/ntc_/rptv2_用唯一UUID。旧资源和Evidence ID不变。Schema只检查结构；跨引用存在性、相等绑定、哈希、计数、唯一配对和版本CAS须由后续实现验证，不能以Schema通过冒充真实事实验收。

## 6. History与Diff

History字段复用source/status/stage/created_at/finished_at，不另建completed_at。summary保留四种finding outcome计数，finding_count为其和，component/asset计数与原ScanRun一致。运行态计数标当前值。latest_assessment只是已有引用，缺失为null；GET不创建Assessment。

Diff仅比较终止且事实可用的扫描；不同项目409；失败或取消后不足以比较的结果明确not_comparable，不展示全部删除。resources保留before/after ResourceRef、两种身份键、字段路径/前后值、evidence_refs与removal_confirmed；许可证/verification/finding变化分别记录。nullable string变化值用于原标量的规范表示（如bool用true/false），null表示缺失，不能把未知变通过。

partial中的未观察到不是removed。只有两侧对应覆盖与身份证明确实支持，removal_confirmed才可true，否则null。assessment_diff独立为compared/not_comparable/unavailable；用途hash不同不能做改善/恶化判断；规则版本变化要披露归因混杂。没有Assessment只做事实diff，不生成。相互关联的scan/assessment/hash必须一致。

## 7. Graph

V1节点只含project/component/ai_asset/license_observation/evidence/finding/obligation。节点id=`scan_id:kind:source_id`，每条边保留source_refs（scan_id+原对象JSON pointer）。

| Edge | 事实依据 |
|---|---|
| PROJECT_HAS_RESOURCE | ScanRun.components/ai_assets成员 |
| RESOURCE_HAS_LICENSE_OBSERVATION | resource.license_expression_id；显示观察而非授权 |
| RESOURCE_SUPPORTED_BY_EVIDENCE | resource.evidence_ids |
| RESOURCE_HAS_FINDING | finding.resource_kind/resource_id |
| FINDING_SUPPORTED_BY_EVIDENCE | finding.evidence_ids |
| FINDING_REFERENCES_OBLIGATION | finding.obligation_ids |
| LICENSE_HAS_RULE_OBLIGATION | obligation.license_expression_id；规则引用，不代表履行 |

filter只选择resource_ids/resource_kinds；空数组表示全范围；选择资源时附带相关证据、finding、license、obligation及project的引用闭包。节点/边ID唯一，端点存在，计数与数组一致。配置capacity实际返回但不是扫描限额。超限响应规则见DECISION-08，无任何隐式截断。

## 8. Profile与cz接口

resource_ref保留resource identity/instance双键。identity为事实投影，未知null。license_observations保留expression ID、relation scope、verification、Evidence；可解析SPDX不等于授权。authorization_fact只复制已有事实及source pointer；component无授权字段则null，不由根许可证合成。

metadata_observations按DECISION-05严格字段保存，fields为具名字段、nullable文本值、locator、verification，不是任意JSON原响应。verified metadata只指该字段核验，不等于授权。缺失/冲突保留coverage_gaps。

cz纯离线parser接收provider、bounded bytes、source descriptor，输出规范化观察、字段locator、版本、缺口；不联网、不写DB。A承担HTTPS allowlist、DNS/IP公共性、逐跳redirect、端口、timeout、字节/类型/容量限制及显式refresh。GET无隐式fetch；外部失败不改scan终态。HF优先，ModelScope后续，至少5模型+5数据集fixture覆盖成功/缺失/冲突/无效输入。

## 9. Workflow与快照

Task origin包含kind、固定assessment JSON pointer及source_hash；resource/evidence_refs追溯原事实。superseded是view属性，写API不接受客户端赋值。PATCH只接受status/note/expected_version；持久version从1递增，冲突409；done/dismissed允许显式恢复todo并保留审计。不能自动变更Formal Assessment或P0 Obligation.fulfillment。

Notice entry固定resource/license/obligation/evidence引用，obligation namespace区分scan和assessment。无许可证原文text=null并记录missing，不由模型补造；源文本仅在合法来源与可定位证据支持时收录。生成/下载不自动满足义务。

Notice/Report使用Binding固定ScanRef、AssessmentRef、Task版本集、Notice ID/hash集及Graph/Profile算法与内容hash。未包含的集合为空，不引用latest。Report sections明确authority=scan_facts/formal_assessment/workflow/observation/ai_explanation，source_ids、schema_version、content_hash及不可变snapshot_ref；snapshot_ref必须解析到完整当时内容，禁止指向会变化的latest对象。报告不得只保存摘要而丢失Formal Assessment与明细。Task即使后来改动，原快照不变。

Report V2至少HTML/JSON；artifacts保存相对下载href、hash、size，不能泄露本机路径。样例中的example引用和零字节artifact占位只说明结构，不是可下载产品。AI解释保留原ai_status，不额外生成。历史tool/rule版本来自原scan/assessment，不用当前版本填补未知。

## 10. API Contract（提案已冻结，运行路由尚未实现）

全部前缀/api/v1；A代表`/scans/{scan_id}/assessments/{assessment_id}`，文档缩写不是实际路径。保留既有Assessment timeline与offset，不新增第二套。

| Method / Path | 输入 / 输出 | 副作用 |
|---|---|---|
| GET /scans | opaque cursor?,limit=20/max100,status?,source_type?,q?,project_key? → items,next_cursor | 只读History |
| GET /scans/{target}/diff | base_scan_id；assessment IDs成对可选 → ScanDiffView | 只读 |
| GET /scans/{sid}/graph | filter（resource_ids/resource_kinds）→完整ResourceGraphView | 只读，无cursor/limit |
| GET /scans/{sid}/resources/{rid}/profile | ResourceProfile | 只读已有观察，无fetch |
| POST /scans/{sid}/resource-profiles/refresh | resource_ids,expected_facts_hash,idempotency_key → job reference | 明确启用后受控外部读取 |
| GET /scans/{sid}/resource-profiles/jobs/{job_id} | pending/succeeded/failed及逐项状态 | 只读，不重试 |
| GET A/remediation-tasks | opaque cursor?,limit → items,next_cursor | 只读 |
| POST A/remediation-tasks/derive | idempotency_key,expected_facts_hash → tasks | 幂等sidecar写 |
| PATCH A/remediation-tasks/{task_id} | status?,note?,expected_version → task | CAS，done/dismissed最终note非空 |
| POST A/notice-drafts | idempotency_key及固定包含项 → NoticeDraft | 新不可变快照 |
| GET A/notice-drafts/{draft_id} | NoticeDraft/artifact | 只读 |
| POST A/report-v2 | idempotency_key,task版本集,notice引用及所含算法版本 → ReportV2Snapshot | 新不可变快照 |
| GET A/report-v2/{snapshot_id} | format=json/html | 只读 |

列表响应schema_version="1.0"；Task排序created_at ASC,task_id ASC。cursor绑定filter/sort/anchor，不能下载全部DB后浏览器过滤；不承诺跨请求事务快照，新插入需刷新首屏。已有接口response不增删字段。

沿用error:{code,message,request_id,details}。400 cursor_invalid/invalid_argument，404 not_found，409 conflict/not_comparable/not_ready，413 graph_capacity_exceeded，422 metadata_invalid，503 feature_disabled/upstream_unavailable。异步metadata错误记job/item，不改scan.status。错误脱敏。

显式写入继承本机Origin/请求大小限制，不新增用户系统。容量不足拒绝新写、保留历史；幂等对象与记录原子持久化。所有新增API的实现与请求Schema另属后续工作包，七响应Schema不是自动接入FastAPI的授权。

### History q Search Semantics（负责人批准的A02 clarification）

q先strip首尾空白，空值等价未提供；使用Unicode casefold后的literal substring匹配，禁止regex/fuzzy/编辑距离/相似度/拼写猜测/LLM。仅搜索project.name及History最终允许公开返回的安全source。必须先安全投影source再匹配，不能先搜索原始路径再脱敏；ZIP/local无安全公开source标识时source不参与搜索。不得搜索scan_id、Project.id、revision、Evidence/Finding、Assessment/Qwen、Report/Metadata正文或本地/workspace/container/ZIP内部路径。规范化q参与cursor filter绑定，大小写及首尾空白等价；不同q或有q与无q不得复用cursor。q不改变稳定排序，不产生扫描、模型、评估、外部读取或数据库写入。本澄清不改变Contract V1版本、Schema或其它决策。

## 11. 版本、回退与团队交付

未知schema版本前端明确报不支持，不静默升级事实。额外字段当前拒绝；后续扩展须经过兼容变更审查、版本与样例更新，不修改P0 schema。新增sidecar先隔离验证和可恢复备份，再单独部署批准；回退不得删历史。

A01契约/A02History/A03Diff/A04Graph/A05Task/A06Report/A07metadata安全/A08CI/A09交付；B01Profile/B02Detector/B03License关系/B04NOTICE/B05Bench/B06FN/B07性能；F01History/F02Cards/F03Graph/F04Tasks/F05Diff/F06Report/F07E2E。A负责公共接口，cz负责事实解析，xzb负责UI与浏览器验收，不按模型名称推断真人Ownership。

Bench2后续20–30固定repo/SHA/hash、至少5隔离holdout、20–30%双人复核；Gold不进入Formal，历史16/0/34仅固定50例，不冒充live指标。CI后续PR快测与重工具隔离。性能目标History200–500条p95<300ms、图≤500节点渲染<1s、Report<2s（不含扫描/Qwen/外部fetch），不是本次测得结果。

P1功能DoD还需真实历史/差异/图/卡片/任务/NOTICE/报告、Schema与语义回归、数据恢复、浏览器、人工Bench、性能分布、异机和负责人签收。本轮只完成Contract V1冻结。不创建integration/p1、不部署或实现功能。

P2非目标：私库OAuth、RBAC、多租户、CVE/SAST、完整法律判断、自动PR、Kubernetes/微服务及全语言重写。官方提交材料规格与内部演示时长不同，不改历史P0官方文档。
