Status: DRAFT — READY FOR PROJECT LEAD REVIEW

NOT FROZEN

Baseline: integration/p0

36d1b794909bf2e655e5968e1a8b3eb03a27bc15

这是 P1 Contract 草案，不能作为已经批准的 Formal Contract。

## 本次 Review 材料发布说明

根据负责人后续发布执行书，本稿发布路径为 `docs/spec/p1-workspace-contract.md`，样例及历史验证回执位于 `docs/p1/`。下面原始草案全文原样保留，包含起草时的目录、分支待确认及未推送记录；这些属于起草时状态，不代表本次发布状态。DECISION-09 的原始方案和建议亦原样保留；本次路径授权不等于其他架构决策或契约已获批准。

样例为 DRAFT / NON-AUTHORITATIVE EXAMPLE，不是 runtime fixture 或 Formal Schema。验证回执仅证明起草时的 JSON 解析、example 结构、reference 与 Git diff 检查，不等于 P1 功能测试通过，也不等于 Contract 已批准。原 DOCX 提取文本仅留在本地，不随本次发布。

以下为原始草案：

---

# OpenGuard A-P1-01：P1 公共契约审阅草案

状态：READY FOR REVIEW；尚未批准冻结、未接入运行路径。日期：2026-09-13。

本稿依据《OpenGuard AI P1 技术规划与三人协作执行书 V2.0》及本轮启动执行书，以本地 `integration/p0@36d1b794909bf2e655e5968e1a8b3eb03a27bc15` 为代码事实源。P0/R1B-A CLOSED 是负责人给定的阶段结论；本轮没有重新验收生产或 Windows。所有“建议”均为待批准设计，不表示功能已实现。

当前只存于 Git 忽略的 output 审阅目录。负责人分支创建问题仍待答复；不修改 integration/p0。批准后的建议唯一正式路径为 `docs/p1/00-p1-contract.md`（本轮执行书路径），不再同时创建 docs/spec 下的同义文档。

## 1. 已读依据与当前代码核对

- 完整提取、阅读 V2.0 DOCX 正文与表格；没有进行版式/插图视觉验收。原始提取文本与本稿同目录保存。
- 已读 README、AGENTS、docs/00–04、p0-domain-contract、a3-fastapi-api、b5-license-rule-engine、进度台账，并核对 domain/api/assessment/persistence/pipeline 与前端 types/services。
- `backend/app/domain/models.py`：P0 contract=0.1.1，extra=forbid；现有资源、Evidence、Finding 和状态机保留。终态事实不可由 P1 改写；运行中 ScanRun 仍按既有状态机更新，不能笼统称所有 ScanRun 都静态不变。
- `backend/app/api/service.py:create_git_scan_record`：Project.id 每次新建；它不是跨扫描稳定项目 ID。Git input_digest 是规范化 URL 的 SHA256，不等于源码内容哈希。
- `backend/app/persistence/scan_registry.py:list_runs`：已有内部列表查询，limit 1–100，created_at DESC / scan_id ASC，after_scan_id 游标锚点。当前没有公开 GET /api/v1/scans。P1 复用内部能力，不重写 registry。
- `backend/app/assessment/models.py`：Assessment 1.0，formal=true；保留 id、version、scan_id、facts_hash、usage_hash、rule_version。正式维度状态仅 conditional/restricted/unknown/not_applicable。
- `backend/app/assessment/engine.py`：facts_hash 来自规范化 ScanRun；rule_version 为评估规则版本、许可证规则版本与 digest 的组合串，不能截断为 2026.09.2。usage_hash 不含 declared_at。
- `backend/app/api/assessment.py` 与 frontend/services/assessments.ts：Assessment 路由嵌套在 scan 下；时间线已有 offset 分页语义。本轮不以新 cursor 契约替换旧接口。
- frontend/src/types/domain.ts 是 UI 适配类型：handling/verification 等不等于后端事实枚举。禁止直接拿 UI 的 resolved/passed 当作 P1 工作流或授权事实。
- 现有扫描 registry 严格验证数据库结构；不往 scans.db 塞 P1 表。现有 Assessment 独立 store 保留。
- 旧架构、B5/API 文档含早期规划/未部署描述，进度台账最新段落停在较早发布点。当前实现和最新执行书优先；本轮不改历史文档。

## 2. P0 frozen boundary 与 P1 目标

P1 在已有真实扫描与评估上提供可追溯的合规工作台。保留 Git/ZIP、扫描覆盖、partial、证据链、自动 Initial Assessment、正常 Qwen 解释、历史报告与当前下载行为。

本轮不修改 domain、API 实现、数据库、Pipeline、Scanner、Detector、Rules、AI prompt、前端、依赖或部署。生产基线由执行书指定：Detector 0.2.0、Rules 2026.09.2、STEP6.1 2/192/384、ScanCode 32.5.0、Syft 1.51.0；本轮未操作生产验证这些配置。

权威顺序：Scan Facts > Formal Assessment > P1 View / Workflow / Report 展示 / AI / UI。

必须分别显示：Unknown != Prohibited；Unknown != Allowed；Pending != Verified；Detected License != Authorization；Root License != Dependency License；File observation != blanket grant；Finding != confirmed violation；Obligation detected != violated；AI/Graph != Formal Assessment；Task done != compliance verified；History/Diff != rescan；GET != scanner/Qwen/metadata fetch。

P1 新 metadata 是附加观察，不能回写旧事实，也不能悄悄影响旧 Assessment。未来让新证据参与正式评估须独立批准有来源的新事实输入与评估版本流程，本轮不提供这个通道。

## 3. 七对象与责任

| 对象 | 层 / 独立 Schema 建议 | 持久化类别 | 权威与来源 | 主责 / 审阅 / 消费 |
|---|---|---|---|---|
| ScanHistoryItem | view / 是 | A：读取派生，无独立事实表 | registry + 已有评估引用 | A / cz、xzb / xzb、A |
| ScanDiffView | view / 是 | A：读取派生，暂不加缓存 | 双方事实与可比较评估分区 | A / cz、xzb / xzb、报告 |
| ResourceGraphView | view / 是 | A：读取派生，formal=false | 现有 ID 关系，不制造边 | A / cz / xzb、报告 |
| ResourceProfile | view + 观察 sidecar / 是 | 现有事实派生 + D 类不可变观察；可缓存投影 | 授权事实与 metadata 观察隔离 | cz 定义解析事实、A 存储/传输/API / 双方 / xzb、报告 |
| RemediationTask | workflow / 是 | C：独立持久化、CAS 版本 | 人工处置，不改变正式结论 | A / cz、xzb / xzb、报告 |
| NoticeDraft | report / 是 | D：不可变生成快照 | 逐条引用与缺口；不是义务履行证明 | cz 内容事实、A 快照/API / 双方 / xzb、报告 |
| ReportV2Snapshot | report / 是 | D：不可变快照 | 正式事实、工作流、AI分节标识 | A / cz、xzb / xzb、交付 |

A=Derived-on-read；B=Cached derived view（只作后续优化，不要求首版实施）；C=Persistent workflow；D=Immutable snapshot。

## 4. 公共字段、版本与来源

下列为类型草案，非已发布 JSON Schema。七个对象使用独立 schema_version：`openguard.p1.<history|diff|graph|profile|task|notice|report>/0.1-draft`；批准时独立提升到 1.0，不能拿草案响应冒充正式 1.0。对象顶层与所有具名嵌套值对象建议 additionalProperties=false；可扩展数据只允许事先命名并约束的 observation 字段。未知版本前端报不支持，不静默转成功。

建议未来 JSON Schema Draft 2020-12，$id 使用 `urn:openguard:p1:<object>:<version>`，隔离在 schemas/p1；不能覆盖 schemas/p0。本轮不生成尚待决策的正式 JSON Schema/Python/TS 类型，避免两套提前冻结的契约。随附 JSON 仅语义样例，明确不是 Schema 校验通过的生产响应。

共同来源值对象（不混为一个万能业务 ViewModel）：

| 名称 | 字段与约束 |
|---|---|
| ScanRef | scan_id:string；revision:string|null=project.revision；facts_hash:SHA256；input_hash:SHA256；inventory_hash:SHA256|null；status:原 ScanStatus；registry_revision:int>=1（并发读取版本，不是 Git revision） |
| AssessmentRef | assessment_id:string；version:int>=1；scan_id:string；facts_hash/usage_hash:SHA256；rule_version:string 完整保留；formal=true，仅在确实存在正式评估时引用 |
| EvidenceRef | namespace=scan；scan_id；evidence_id；引用必须在该 scan 中解析。metadata 新证据用 namespace=profile_observation + observation_id，不混入旧 evidence_ids |
| Provenance | producer:{name,version}；source_refs:ScanRef[]；assessment_refs:AssessmentRef[]；generated_at:UTC；algorithm_version:string；参数摘要 parameters_hash:SHA256；不含密钥、绝对路径、提示词正文 |

SHA256 为64位小写十六进制；这里字段是 string，不改 P0 HashValue。未知 hash 用明确 nullable 字段，不造全零真实哈希。UTC 时间采用 RFC3339 Z。派生对象 generated_at 是读取投影时间，不参与语义内容 hash；快照 created_at 是持久时间，内容 hash 算法显式版本化。

- History 不新增 ID，用 scan_id。Diff/Graph/Profile 投影 ID 为带 namespace 前缀的规范化输入摘要，包含算法版本；不使用随机新 ID 破坏刷新稳定性。
- task_id=`tsk_<uuid>`；draft_id=`ntc_<uuid>`；snapshot_id=`rptv2_<uuid>`。快照显式 POST 的 idempotency_key 与输入 fingerprint 配合，同键异输入409，同键同输入返回原对象。
- resource_id/evidence_id/license_expression_id/finding_id/obligation_id 继续使用 scan 内原 ID；跨 scan 比对用另一个 resource_identity_key，不覆盖旧 ID。
- 公共规范化 hash：UTF-8 JSON、键排序、紧凑分隔；集合先按契约键排序，语义有序数组保序；拒绝 NaN/Infinity。未来实现需跨语言固定向量。P0 facts_hash 使用现有 engine 函数，禁止另造不一致算法。
- 快照固定 assessment ID/version/usage_hash，不采用访问时的 latest。历史视图的 latest 是读取时明确标注的引用，读不到则 null + unavailable，不创建评估。

## 5. ScanHistoryItem

字段：schema_version、scan_id、project_identity、source_type、source、revision、input_hash、inventory_hash、status、stage、created_at、finished_at、component_count、ai_asset_count、finding_count、summary、latest_assessment、provenance。

计数非负整数；finding_count=sum(summary.finding_counts)，summary 原有分项不得丢弃。时间沿用 finished_at，**不另起 completed_at**：partial/failed/cancelled 也是终态。运行中计数是当前进度快照，不能当最终事实。

project_identity 草案：{key,method,source_project_id}。Git method=canonical_git_url_v1，key 对规范化已有 source 求摘要，不随 branch/revision 改变；不联网解析重定向或别名。ZIP method=scan_only 默认不按文件名聚合；需要跨 ZIP 版本比较时必须明确人工确认关系（DECISION-01）。source 只返回已有允许公开的输入标识，local 路径脱敏。

History 默认包含历史终态与运行态，不能只显示 completed；assessment 不存在或 sidecar 不可用，不应让整条扫描消失。

## 6. ScanDiffView

字段：schema_version、view_id、base:ScanRef、target:ScanRef、project_match、facts_diff、assessment_diff、coverage、provenance。只比较已终止扫描；活跃扫描409。failed/cancelled 缺少事实时返回不可比较原因，不展示“全部删除”。

facts_diff 包含 resources.{added,not_observed_in_target,changed,unmatched}、license_observation_changes、verification_changes、finding_changes。每条 change 保留 before/after 的 scan_id、resource_id、evidence_refs、字段路径和前后值；不只给自然语言摘要。字段缺失与null/未知区分。partial 下“目标未观察到”不等于 removed；只有两边相应范围覆盖可证明且身份匹配唯一，才允许标记 removal_confirmed=true，否则null。

identity规则草案：package 优先规范化 PURL 去版本作为对应键，同时保留版本/生态/位置上下文；无 PURL 用 ecosystem+name。AI 用 kind+resource provider+canonical source identity，版本是变化字段；runtime provider 不替换 resource provider。多实例或同名冲突进入 unmatched/ambiguous，不强行合并、不凭资源名判同一对象。只有可可靠解析的事实进入键；不能猜 URL。

assessment_diff 为独立对象：status=compared|not_comparable|unavailable，base/target AssessmentRef，dimensions/obligation changes，reason。usage_hash 不同时不推断改善/恶化。相同用途但规则版本不同，明确原因混杂，不把变化归因源码。无评估时仅做 facts_diff，不隐式生成。

## 7. ResourceGraphView

字段：schema_version、view_id、formal=false、scan_ref、nodes、edges、coverage、provenance。节点包括 project/component/ai_asset/license_observation/evidence/finding/obligation；Assessment Dimension 首版不纳入，避免双权威混图。

节点 id 使用 `scan_id:kind:source_id`，保留 source_ref。edge 含 id/type/source/target/source_refs；任意边端点必须存在。允许的边与唯一推导条件：

| 边 | 确定性来源 |
|---|---|
| PROJECT_HAS_RESOURCE | ScanRun.components / ai_assets 成员 |
| RESOURCE_HAS_LICENSE_OBSERVATION | resource.license_expression_id，显示“观察到”，不显示“已授权” |
| RESOURCE_SUPPORTED_BY_EVIDENCE | resource.evidence_ids |
| RESOURCE_HAS_FINDING | finding.resource_kind + resource_id |
| FINDING_SUPPORTED_BY_EVIDENCE | finding.evidence_ids |
| FINDING_REFERENCES_OBLIGATION | finding.obligation_ids |
| LICENSE_HAS_RULE_OBLIGATION | obligation.license_expression_id；是规则输出引用，不承诺法律履行 |

不存在于当前模型的依赖传递边不得凭共现生成。根许可证不会自动连向所有依赖。图筛选/分页必须返回完整计数、当前范围、omitted counts 与 continuation；不得把 UI 截取误称完整覆盖。≤500节点是未来性能样例条件，不是删除其他资源的许可。布局与折叠属于 UI，不写回。

## 8. ResourceProfile 与 cz 接口

字段：schema_version、profile_id、scan_ref、resource_ref、identity、license_observations、authorization_fact、metadata_observations、coverage_gaps、evidence_refs、provenance。

resource_ref.kind 复用 component/ai_asset，display_type 可派生 package/model/dataset/api/service/asset，不丢已有类别。identity={name,version,ecosystem,provider,source_url} 为当前事实的投影；缺失=null。

license_observations 每条保留 license_expression_id、expression、relation_scope、evidence_refs、verification_status（现有 verified/pending/not_applicable/rejected）。不能用 SPDX parseable 表示授权 verified。authorization_fact={status,source_ref} 只复制已有 AIAsset 状态；component 无对应字段则null，不能从 LicenseExpression 合成授权。

metadata_observations：observation_id、provider、resource_identity_key、requested_revision、resolved_revision、source_url、fetched_at、content_hash、parser_version、fields、field_sources、verification_status、coverage_gaps。verified metadata 仅指指定字段核验及其证据，不是授权。公开网页可读!=分发许可；原文保存/摘录策略及限额待批准。

cz 纯函数接口草案：parse_profile(provider, bounded_document_bytes, source_descriptor) -> ProfileObservationDraft。输入由 A 提供已限量内容及真实 URL/哈希/时间；cz 不负责网络、密钥、自动重试或写数据库。输出字段要有 JSON pointer/行号/原字段定位、解析器版本、缺失/冲突。HF fixtures 优先，ModelScope 后续；至少5模型+5数据集 fixture，成功/缺失/冲突/无效元数据都测试。

A 管理 HTTPS allowlist、公共 DNS/IP 验证、重定向逐跳验证、端口、超时、大小、Content-Type、容量/缓存/并发上限；禁止 localhost、私网、任意代理继承和 GET 隐式 fetch。外部失败只产生 enrichment 状态，不改 scan.status。当前任何 transport 都未实现。

## 9. RemediationTask

字段：schema_version、task_id、scan_id、assessment_ref、origin、resource_ids、evidence_refs、title、status、note、version、created_at、updated_at、provenance。

origin={kind:condition|restriction|gap|next_step|obligation, source_pointer, source_hash}；pointer 固定于该 assessment version，不能指向 latest 数组。建议所有任务绑定正式 AssessmentRef；无评估不 derive。现有 P0 Remediation 是建议对象，不能当作新工作流存储。

status=todo|in_progress|done|dismissed；version>=1 单调递增；PATCH 仅允许 status/note+expected_version，不接受正式结论或证据改写。旧版本409。done/dismissed 可明确恢复todo，保留变更审计；不删除。note 建议最多2000字符、理由缺失是否允许见DECISION-04；用户备注不是证据 verified。任务源内容在新 Assessment 下失效时显示 superseded，不自动变更任务status，也不修改旧assessment。

derive 输入固定 assessment+算法版本+幂等键，重复请求不能复制任务。任务变更只改 sidecar；旧报告快照不跟随任务状态变化。

## 10. NoticeDraft

字段：schema_version、draft_id、scan_id、assessment_ref、created_at、generator_version、entries、coverage_gaps、content_hash、provenance。

entry={entry_id,resource_ids,license_expression_ids,obligation_refs,evidence_refs,text,missing}。obligation_refs 区分 scan obligation 与 assessment obligation namespace，不能因都叫 id 混用。缺文本 text=null、missing记录缺口；禁止模型补造许可证原文。text须来自可定位的许可证/版权证据或明确标注的模板说明，文件级观察不能升级成包授权。每项保留原来源、范围、哈希；关系不充分时只能提示待核对。

POST 显式生成不可变快照；GET 读取既有快照；下载无状态副作用。不能用生成/下载成功将 obligation.fulfillment 改成 satisfied。

## 11. ReportV2Snapshot

字段：schema_version、snapshot_id、scan_ref、assessment_ref、created_at、generator_version、sections、content_hash、artifacts、provenance。

sections 分 authority=scan_facts|formal_assessment|workflow|observation|ai_explanation，每节含 schema_version、source_refs、content_hash、payload或不可变快照引用。Formal Assessment 原对象和结论原样保留，不能把 action plan 的 done 汇入正式许可摘要。AI解释保留ai_status与来源，无额外生成调用。

固定记录 Detector/tool版本来源于该scan.provenance，rule_version来自所引用assessment；无法取得版本明确unknown，不使用当前服务版本冒充历史版本。Graph算法/Task.version/NoticeDraft.id及hash必须固定；引用可变任务时必须复制当时快照而非访问时读取最新。

artifacts 至少HTML/JSON，含format、content_hash、size_bytes、相对下载href；不返回宿主绝对路径。顶层content_hash计算不含自身及artifacts外部字节哈希的规范化snapshot payload，避免循环；每个artifact再独立算文件SHA。旧四种 P0 报告继续原路径，PDF属后续可选项。

## 12. API Contract Proposal（全部新接口均未实现）

现有 GET /scans/{sid}/assessments 复用，不创建第二套 timeline。下列路径均以 /api/v1 开头；`A=/scans/{scan_id}/assessments/{assessment_id}` 是文档缩写，实际URL必须展开。

| 方法 / 路径 | 输入 / 输出 | 副作用 |
|---|---|---|
| GET /scans | cursor?,limit=20,max100,status?,source_type?,q?,project_key? -> schema_version,items,next_cursor | 只读History |
| GET /scans/{target}/diff | base_scan_id 必填，base_assessment_id?/target_assessment_id? 成对 -> ScanDiffView | 只读，不猜用途 |
| GET /scans/{sid}/graph | cursor?,limit?,filter? -> ResourceGraphView | 只读投影；页边引用闭包须保持 |
| GET /scans/{sid}/resources/{rid}/profile | -> ResourceProfile | 无缓存仍只读事实和缺口 |
| POST /scans/{sid}/resource-profiles/refresh | resource_ids,expected_facts_hash,idempotency_key -> job reference | 后续明确启用后才可外部读取；未启用503 |
| GET /scans/{sid}/resource-profiles/jobs/{job_id} | -> pending/succeeded/failed + item结果 | 只读，不重试；不是ScanStatus |
| GET A/remediation-tasks | cursor?,limit -> items,next_cursor | 只读 |
| POST A/remediation-tasks/derive | idempotency_key,expected_facts_hash -> tasks | sidecar幂等写 |
| PATCH A/remediation-tasks/{task_id} | status?,note?,expected_version -> task | CAS；不改assessment |
| POST A/notice-drafts | idempotency_key -> NoticeDraft | 显式快照 |
| GET A/notice-drafts/{draft_id} | -> NoticeDraft / artifact | 只读 |
| POST A/report-v2 | idempotency_key,task版本集,notice_draft_id? -> ReportV2Snapshot | 显式快照，不调用Qwen/扫描 |
| GET A/report-v2/{snapshot_id} | format=json|html -> 快照或文件 | 只读，不现场生成 |

所有列表排序必须固定。History复用 created_at DESC,scan_id ASC；cursor绑定过滤条件和锚点，非法/过期cursor返回400，不静默回首页。新插入记录在刷新第一页出现；不承诺跨请求完整数据库快照，状态可能更新。新Task列表建议created_at ASC,task_id ASC；现有Assessment offset接口保持原样（DECISION-06）。

分页不能下载全部数据库后在浏览器过滤；后续实现若需新索引/兼容查询必须独立测试，不改变扫描写入语义。graph预算与边端点续页协议待DECISION-08，不可先实现截断并声称完整。

错误沿用 {error:{code,message,request_id,details}}：400 invalid_argument/cursor_invalid；404 not_found；409 conflict/not_comparable/not_ready；503 feature_disabled/upstream_unavailable；422 metadata_invalid（异步任务则记录为job/item错误）。安全消息不得回显凭据/绝对路径。旧API错误码完全保留。

POST/PATCH 继承现有本机Origin检查和请求大小控制；这不是账户鉴权。无用户系统/RBAC/OAuth新增。快照生成与sidecar写入失败不得污染旧报告；容量不足拒绝新写，保留历史。幂等记录与持久对象事务提交，不留假成功。

## 13. Persistence / 兼容与回退

- History/Diff/Graph首版只读，不要求新增DB。live扫描读取标明版本，不能缓存成终态；终态缓存键必须含facts hash+算法+参数，Assessment视图再含id/version/usage_hash/rule_version。
- ResourceProfile观察持久化建议独立metadata sidecar；Task/幂等/变更记录建议独立workflow sidecar；Notice/ReportV2不可变artifact和清单。具体文件名/建库尚待DECISION-05，不在本轮迁移。
- 不改严格 scans.db；不要求把任何P1表写进assessment.db；旧数据库只读可用，未生成P1对象显示“尚未生成”而非历史失效。
- 未来sidecar显式schema版本和可恢复备份，先隔离测试再单独部署批准。新增服务版本回退时仍可读旧scan/report，未知P1版本可拒绝对应新功能，不能自动删表降级。
- 首版默认不删历史报告、任务、观察；容量阈值由后续实现测定，存储不足停止新增而非自动清理证据。

## 14. 前端、三人并行与任务编号

xzb只消费批准后的P1 DTO，runtime validation 与UI适配分离；Graph高亮/过滤是UI状态；Task标done不得更新正式许可颜色。History/Diff/Graph GET不得引入扫描或AI调用。未知、partial、无Assessment、无metadata、过期task、无snapshot均有可见状态。刷新不得重发POST。样例必须标mock，不用于真实验收证据。

A 主责契约/API/持久化/网络安全/投影/集成发布；cz 主责解析观察/许可证关系/NOTICE事实/Bench；xzb主责页面和浏览器验收。边语义与数据模型共同审阅后再并行，不让模型角色替代三位真人负责人。

V2.0任务编号为本轮参照：A01契约、A02历史、A03Diff、A04Graph、A05Task、A06Report、A07metadata安全、A08CI、A09交付；B01Profile、B02Detector、B03License关系、B04NOTICE、B05Bench、B06FN、B07性能；F01History、F02Cards、F03Graph、F04Tasks、F05Diff、F06Report、F07E2E。

先前P1交接分支里的任务编号与V2.0部分不同（例如早期B01指Bench、F02指Diff）。不得用编号相同判断成果相同；需要按任务内容映射。保留两位组员分支与旧交接，不覆盖改名，本次新草案作为待批准更正依据。

## 15. 待负责人决定（草案不擅自替代批准）

| ID | 背景与方案A / B | 建议 | 影响 / 阻塞并行 |
|---|---|---|---|
| DECISION-01 | Project.id不稳定。A：Git按规范source聚合，ZIP独立；B：现在引入持久Project实体和关联管理 | A；跨ZIP比较后续显式关联 | A02/A03历史分组需确认；不阻塞cz纯解析 |
| DECISION-02 | 同名多实例无法可靠跨scan配对。A：精确identity+歧义保留；B：启发式模糊匹配 | A；不同source默认409，不跨fork强比 | A03，需cz审阅identity规则 |
| DECISION-03 | Graph会混入推断。A：仅列明的事实边；B：增加Assessment维度层/传递依赖边 | A；无事实的传递边无论方案都禁止 | A04/F03边语义冻结前阻塞 |
| DECISION-04 | Task与结论需要隔离。A：固定assessment版本，CAS，done/dismissed要求理由；B：绑定latest且仅人工状态 | A；理由作为备注非verified evidence | A05/F04；原assessment永不回写 |
| DECISION-05 | enrichment回溯与容量。A：限量原始metadata+hash持久sidecar；B：仅保存字段/摘录和hash | A在来源允许保存且预算批准时；否则B并披露不可完整重放 | A07/B01存储前阻塞；离线fixture解析可准备 |
| DECISION-06 | V2建议cursor统一，旧timeline已offset。A：新列表cursor、旧接口不改；B：新增独立P1 timeline包装 | A，减少重复接口 | xzb需明确适配；不阻塞纯schema审阅 |
| DECISION-07 | 报告应固定版本。A：显式POST生成Notice/Report快照，GET只读；B：列表仅返回当前拼装视图 | A；Report V2快照是本轮目标 | A06/F06；不把B当不可变快照 |
| DECISION-08 | 大图不可静默截断。A：确定性分页+引用闭包，标明全局总数；B：先完整返回、UI局部展开，有明确容量拒绝 | 待A04容量实测后定；草案倾向A | 仅阻塞graph分页细节，不阻塞边语义 |
| DECISION-09 | 路径与交接编号存在多个版本。A：本执行书docs/p1路径+V2.0编号；B：旧docs/spec路径/旧编号 | A，单一正式文档并保留历史 | 影响三人引用，正式下发前确认 |

## 16. V2.0覆盖、非目标与后续DoD

| V2.0项目 | 本契约覆盖 | 后续实现/验收（本轮未完成） |
|---|---|---|
| History | 派生字段、项目身份、分页、旧数据 | A02/F01真实列表与刷新/空/错误态 |
| Diff | facts/assessment分离、身份、partial | A03/F05固定双scan差异、不同用途拒比 |
| Graph | 显式事实边、formal=false、范围披露 | A04/F03边追溯、预算和真实页面 |
| Profile/Card | facts/观察/授权分层、离线parser | B01/A07/F02 fixtures与显式安全fetch |
| Task | 固定assessment、CAS、幂等、无权威提升 | A05/F04持久恢复/冲突/状态回归 |
| NOTICE | entry引用/缺口/快照 | B04/A06已验证文本来源与下载 |
| Report V2 | 不可变分节、来源、hash、旧报告保留 | A06/F06 HTML+JSON和截图实测 |
| Bench2 | 只作评测；不进入Formal | B05：20–30公开repo、固定SHA/hash、至少5holdout、20–30%双审；Gold与Detector分开变更 |
| CI | 不改发布边界 | A08：PR快测/安全/schema/frontend/build/benchquick；重工具夜间或手动；真实Git里程碑 |
| Performance | 不混扫描、Qwen和view耗时 | B07/A：200–500历史p95<300ms、≤500节点渲染<1s、Report<2s（排除扫描/模型/外部fetch）；均是待实测目标 |

Bench开发/回归集可记录重叠，但holdout必须与开发调参来源隔离，至少5仓库，身份以固定repo/commit/hash为准；争议负责人裁决。历史50条样本16/0/34即precision100%、recall32%不等于一般实时性能；P1目标precision≥95%、recall≥60%、许可关系≥90%、关键语义违规0、批扫描成功≥90%，必须报告分母/覆盖和失败，不能视为承诺。

P1 DoD：批准独立schema与固定样例；旧ScanRun/Assessment1.0回归无破坏；GET无外部副作用；所有资源/风险/证据引用保留；Task完成不提升结论；快照可复现和历史恢复；真实页面而非mock验收；Bench holdout与人工复核；明确性能分布和缓存；生产候选/回退/异机证据；负责人最终签收。本轮只交付契约草案，不声称上述功能DoD已满足。

P2非目标：私库OAuth/GitHub App、用户/RBAC、多租户、CVE/SAST、完整法律判断、自动PR、Kubernetes/微服务、全语言重写、AI决定授权。新Graph依赖（例如@xyflow/react）须独立版本/体积/许可证评估，不在本轮安装。V2内部演示5–7分钟与旧竞赛章程提交视频3–5分钟不同，不自动改官方提交规格。20–24工作日仅规划参考，不在本轮重新承诺期限。

## 17. 审阅与状态

本轮产物：本Markdown、七对象合成JSON样例、验证回执。无运行实现、无正式Schema发布、无提交/push、无生产操作。因保护integration/p0，未在P0共享台账追加记录；本节为隔离任务记录，待负责人批准分支后再按项目流程落库。

下一步只等待负责人审阅分支与DECISION项，再由A协调cz/xzb确认共同契约。不得自动进入History/Diff/Graph编码。
