# A03 — Scan Diff Backend 实施说明

Supporting implementation note only.
Authoritative semantics remain:
`docs/spec/p1-workspace-contract.md`
and `schemas/p1/*.schema.json`.

本文件是实施与评审说明，不是新 Contract，不改变已冻结的语义或 ERRATUM-01。

## 1. 实现身份与发布状态

| 项目 | 值 |
|---|---|
| Task | A03 — Scan Diff Backend |
| Implementation commit | `66dfdd18bb07726eb8a18a6b8fd7d147a277668b` |
| Baseline | `9822c8668683f0be475086b81642f2d8b41aa453` |
| Branch | `feat/p1-history-diff` |
| Algorithm | `scan-diff/1.0` |
| Response / Contract version | `1.0` |

功能提交已普通 push 到 `origin/feat/p1-history-diff`；A03-DOC-01 开始前已核实本地 HEAD 与远端均为上述 implementation commit。第一轮独立 Review 为 FUNCTIONAL PASS、DOCUMENTATION FIX REQUIRED。本次补齐说明并修正旧发布状态，A03 仍等待负责人最终 Review / Integration，不标为 CLOSED。

## 2. API 与比较准入

`GET /api/v1/scans/{target_scan_id}/diff`

- `base_scan_id`：必填。
- `base_assessment_id`、`target_assessment_id`：成对可选；只传一个或空 ID 返回 `400 invalid_argument`。
- 返回 `ScanDiffView 1.0`，包括 ScanRef、资源变化、三类事实变化、独立 Assessment Diff、coverage 和 provenance。
- GET 不生成 scan、assessment、Qwen 内容、metadata、report 或 task。

| 输入状态 | 结果 |
|---|---|
| base 与 target 为同一扫描 | `400 invalid_argument` |
| 任一侧 queued / running | `409 not_ready` |
| 任一侧 failed / cancelled | `409 not_comparable` |
| 两侧均 completed / partial | 进入项目身份和事实比较检查 |
| project identity 不同 | `409 not_comparable` |
| 任一扫描不存在 | `404 not_found` |

completed / partial 只是比较准入条件，不表示资源已获授权。ZIP/local 使用 scan_only 身份，不同 scan 默认不可比较。

## 3. 项目身份与 ScanRef

项目身份完全复用 A02 的 `public_source` / `identity`：对合法的公开 GitHub source 使用 `canonical_github_repo_v1`，规范 owner/repo 大小写、末尾 `.git` 与 `/`，revision 不参与项目身份。先遵守原安全输入策略，不新增 redirect、fork、rename equivalence，也不联网猜测仓库关联。

ScanRef 保留 `scan_id`、`revision`、`facts_hash`、`input_hash`、`inventory_hash`、`status`、`registry_revision`。`facts_hash` 复用现有 `assessment.engine.facts_digest`；`input_hash` 是既有输入摘要，不能称为源码内容 hash。缺失的 inventory hash 保留 null。

## 4. 资源双键与匹配

`resource_identity_key` 表示逻辑资源，`resource_instance_key` 表示有事实支撑的具体实例，二者均不替代原 resource_id。

- Component：优先规范化 PURL，逻辑键去版本并保留身份所需信息；没有可靠 PURL 时仅使用已知 ecosystem 与该生态规范化包名。未知生态或不可靠名称不猜身份。
- AIAsset：使用 asset kind、resource provider 与事实中的 canonical name；不猜 URL、版本或 provider。runtime inference provider 不进入 resource provider identity。
- 无事实支撑的身份或实例键为 null，不能用空字符串假装已识别。

匹配分三步：

1. 两侧唯一、非 null 的 exact resource_instance_key，且 logical identity 一致。
2. 对未消费资源，按两侧唯一 resource_identity_key 配对。
3. 多候选保持 ambiguous，无可靠身份保持 unmatched；逐个保留单侧 ResourceRef，不强造一对一关系。

已匹配资源不得再次消费。算法使用索引桶，不使用 fuzzy、Levenshtein、LLM、path guess 或 URL guess。

## 5. 资源变化、删除与覆盖

| kind | 含义 |
|---|---|
| changed | 可靠配对后实例或比较字段发生变化；完全相同的资源不列入变化列表 |
| added | target 观察到，而 base 未观察到可靠匹配资源；不保证是新引入 |
| not_observed_in_target | base 观察到，target 未观察到匹配资源；不直接等于 confirmed removed |
| ambiguous | 剩余两侧有相同逻辑身份但候选不能唯一配对；输出单侧记录，不指定猜测配对 |
| unmatched | 无可靠身份，不能确定跨扫描关联 |

只有双方 completed、没有 coverage diagnostics/errors、资源 identity 可靠，且记录为 not_observed_in_target 时，当前实现才允许 `removal_confirmed=true`。其他情况保留 null；target partial、base partial、ambiguous、unknown identity 均不能证明删除。

coverage 的 base_complete / target_complete 按状态生成：completed 为 true，partial 为 false。gaps 使用安全摘要 `base scan partial`、`target scan partial`；completed 仍携带 diagnostics 时，输出 `base scan reports coverage diagnostics` 或 target 对应文本。不原样暴露内部错误对象。partial 既不是 failed，也不是 completed；base partial 下的 added 只能表示观察差异。

## 6. 事实分区与证据

- resources：资源字段变化，保留 before/after ResourceRef。
- license_observation_changes：许可证表达式及已有资源绑定的观察变化；独立、未绑定的许可证观察不传播给依赖或 AIAsset。
- verification_changes：来自事实的 verification / authorization 状态变化，与许可证观察分开。
- finding_changes：按资源关联及规则等确定性身份比较，不按描述语言模糊匹配；多候选不能强配。

Root license 不传播；Detected license != authorization；Pending != verified；Finding != violation。Diff 不补造许可或升级事实确定性。

每条证据引用必须为 `namespace=scan`、`scan_id`、`evidence_id`，且 evidence_id 在对应 scan 中真实存在。changed 可包含两侧证据，但 before/after 不得串 scan；引用稳定排序、去重，无支持证据时可为空，不伪造引用。

## 7. 独立 Assessment Diff

Assessment Diff 与 Scan Facts Diff 分离：

- 未指定两个 Assessment ID：只读取得各 scan 已有 latest，不创建 Assessment。
- 显式指定：两个 ID 必须成对，严格读取指定对象，不用 latest 替代。指定 ID 属于错误 scan 时拒绝；缺失时 status 为 unavailable。
- 已取得对象的 scan_id、facts_hash、formal 绑定错误：返回 integrity error（`503 upstream_unavailable`），不继续比较。
- usage_hash 不同：status 为 not_comparable，reason 为 `usage context differs`，不输出改善或恶化判断。
- rule_version 不同：可展示原始 Formal 字段变化，但 reason 必须为 `rule version differs`，不把规则升级归因于项目变化。
- 只比较确定性的 dimension status、conditions、restrictions、gaps、obligations、resource evaluations 等 Formal 字段。AI summary、Qwen 文本不参与 Formal Diff。

## 8. 确定性与 ERRATUM-01

view_id 由 algorithm、base ScanRef、target ScanRef、Assessment selection 确定性产生；selection 包含请求选择和实际选中的引用。generated_at 不进入 semantic view identity。相同输入与选择下，除读取时 generated_at 外，输出语义稳定；资源、各类变化和证据数组稳定排序。latest 后来发生变化时，选中引用及 view identity 可随之变化。

ERRATUM-01 — Diff Empty String Preservation 是已批准的 Contract V1 语义勘误，不是新功能或 Schema 1.1。Component.version 等 P0 合法 scalar 可能为 `""`：

- `""`：原字段存在但值为空。
- `null`：字段缺失 / 无值。
- 两者不得互相转换；不能 trim 或 normalize-away 来规避事实。

仅以下五类 Diff change-value 的 before/after（共 10 个 string branch）允许空字符串：

1. resources[].field_changes[]
2. license_observation_changes[]
3. verification_changes[]
4. finding_changes[]
5. assessment_diff.changes[]

path、view_id、project_identity_key、scan/resource/evidence/assessment ID、非 null identity/instance key、source IDs、rule_version、非 null reason 等仍保持原严格约束。Contract 仍为 1.0；P0 模型、common Schema 和其他 Schema 未因此放宽。本次文档收尾不再次修改 Contract。

## 9. 错误与只读边界

沿用 `error:{code,message,request_id,details}`，包括 `400 invalid_argument`、`404 not_found`、`409 not_ready`、`409 not_comparable`、`503 upstream_unavailable`。错误信息脱敏，不返回绝对路径、数据库路径、内部异常或凭据。无法安全满足引用契约时拒绝，不通过修改原事实来拼出有效响应。

GET 不调用 scanner、Git clone、ZIP ingestion、ScanCode、Syft、Detector、Rules rerun、Assessment creation、Qwen、Chat、metadata fetch、Report generation 或 Task write，不写数据库。现有初始化 registry 的读取路径和 Assessment 只读存储被复用；已有隔离测试用写方法阻断、调用前后数据库 hash 和 registry revision 不变验证该边界。不为 Diff 新建存储或迁移数据库。

## 10. 已完成验收记录与 OpenAPI

以下是 implementation commit `66dfdd18bb07726eb8a18a6b8fd7d147a277668b` 的既有验收结果，来自本次执行书及进度台账；本次 documentation-only 收尾没有重新运行产品测试。

| 验收集合 | 已记录结果 |
|---|---|
| A03 + Contract | 109 passed |
| A02 History | 24 passed |
| all unit | 1068 passed, 1 skipped |
| related security | 81 passed |
| Contract Schema | 42 passed |
| Python | 3.12.14 |

集合有重叠，不相加成新的独立总数。1 skipped 为既有条件测试，不是 A03 失败；已有 Starlette deprecation warning 不隐瞒。这些记录不代表 GitHub CI green，也不代表 Production 验收。

OpenAPI 基线为 11 paths，A03 为 12 paths；唯一新增路径是 `GET /api/v1/scans/{target_scan_id}/diff` 及其参数/响应类型，既有 route 没有删除或替换。A02 History、原扫描创建/查询、Assessment 路由及已有响应结构保持兼容。

本轮仅执行文档内容、引用路径、允许文件范围和 `git diff --check` 检查，不重复完整 1068 unit。

## 11. 限制与下一步

- V1 Diff 为即时 derived view，不持久化；generated_at 每次 GET 变化。
- 没有跨 ZIP 人工项目关联，不做 fuzzy resource matching。
- partial 无法证明删除；completed 带 diagnostics 时也不能确认删除。
- rule version 变化存在归因混杂；不同用途不作改善/恶化判断。
- 无 Assessment 时不自动生成，Diff 不触发重新扫描或 AI。
- 本功能当前未部署 Production；普通 push 不等于部署或 integration/p1 已集成。
- A04 及后续工作未由本轮开始。

下一步仅等待负责人最终 Review / Integration；A03-DOC-01 不实现 Graph、Task、Report 或前端功能。
