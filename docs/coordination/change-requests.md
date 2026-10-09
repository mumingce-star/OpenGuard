# Cross-owner change requests

## CR-20260923-P0B05-run-preparation-artifacts

- 提出者：用户，2026-09-23；状态：执行中。
- 目标：固化 B05 离线评测运行准备的 detector、config、input、prediction/result artifact 格式、manifest SHA-256 校验与错误分类入口；在真实人工 Gold 冻结前，禁止计算、写入或展示 Precision、Recall、F1。
- 所有权与影响：Bench fixture、测试与 B05 规范通常属于 Luna；用户明确授权 Root 直接修改这些离线材料。不得修改公共 API、Assessment、正式风险结论、现有 Gold 人工结论或 Bench 2.0 公共 Schema。
- 契约边界：Hash 仅绑定仓库内 artifact 字节；`gold.json` 继续是非人工的 development placeholder。运行前置条件和错误分类仅为离线准备协议，不执行 detector、不联网、不形成实际 prediction/result 或任何正式评测指标。
- 验收：Node 复算 manifest 中每个 artifact 的大小/SHA-256、provenance 和 artifact 闭包；显式断言 Gold 未冻结时 `metrics=null`，且所有 artifact 不含 Precision/Recall/F1；错误分类入口必须固定且不产生误导性指标。

## CR-20260922-P0B01-five-by-five-offline-fixture

- 提出者：用户，2026-09-22；状态：执行中。
- 目标：将 `tests/fixtures/huggingface/resource-profile-v2/` 的固定离线回归样本由 2 个模型 + 2 个数据集扩展为 5 + 5，并补齐来源观察 SHA-256、缺失/冲突/非法输入反例和离线副作用门禁。
- 所有权与影响：该目录和对应测试通常由 Luna 负责；用户已明确授权 Root 直接修改。保留 v1/v2 既有记录，不改公共 Schema、默认工厂、transport 或生产 API。
- 契约边界：fixture 仅为固定、脱敏的离线 JSON 观察。Hash 只证明仓库内文件字节与 manifest 的绑定；不联网抓取，不认定当前上游状态、授权、许可证表达式或许可证适用性。
- 验收：manifest 精确固定 5 model + 5 dataset 和每个 source observation hash；缺失/冲突保持 pending gap，非法输入失败关闭；单测禁止 socket/subprocess，运行 B01 定向 pytest、compileall 与 diff 检查。
- 2026-09-23 补充：用户明确授权以 Java 离线契约测试与 Maven 编译替代当前不可运行的 Python pytest/compileall 回执。替代范围只验证 fixture 结构、Hash、pending/无升级与非法 identity 失败关闭；不宣称已替代 Python parser 的行为回归，也不迁移或删除 Python 实现。

## CR-20260923-P0B02-candidate-matrix

- 提出者：用户，2026-09-23；状态：执行中。
- 目标：基于已冻结 `notice-license-facts-v2` 增加 B02 detector 的正例、反例、误报与漏报候选矩阵及回归测试。
- 所有权与影响：B02 Python detector/fixture/test 通常分别属于 Terra/Luna；用户明确授权 Root 仅增加离线 fixture、测试和规格。不得修改检测器公共导出、公共 API、Assessment、Task、NoticeDraft、Report 或正式风险结论。
- 契约边界：正例只是 `review_required` 候选；反例是零候选事实；误报保护禁止把 NOTICE gap 变为违规；漏报保护只断言既有 fact gap/provider declaration 必须产生候选。该矩阵不是 Gold、FP/FN 指标或法律结论。
- 验收：Python unit 直接调用内部 detector 并比对固定矩阵；Node 复算 facts/hash/matrix 一致性；无网络、无服务操作，`git diff --check` 通过。

## CR-20260923-P0B03B04-approved-offline-observations

- 提出者：用户，2026-09-23；状态：执行中。
- 目标：扩充 B03/B04 已获许可的离线 License、NOTICE、版权和来源关系观察；每条绑定路径、locator、Hash、来源版本。
- 所有权与影响：fixture/doc/test 通常属于 Luna；用户明确授权 Root 直接增加离线事实。不得生成或伪造 NOTICE 正文，不得以许可证表达式取代 NOTICE，不改 B02 输入、公共 API、Assessment 或正式风险结论。
- 验收：来源必须为已有仓库内固定 v1 观察，每条带 source path/locator/content/container Hash/source version；Node/Java 验证零正文、pending/null、关系闭包和固定 Hash。

## CR-20260905-B1-B7-closure

- Requested by: CZ, 2026-09-05.
- Scope: continue B1–B7 implementation using the frozen P0 domain contract.
- Target files: `backend/app/scanners/`, `backend/app/licenses/`, `backend/app/detectors/`, `benchmarks/`, and their unit fixtures/tests.
- Ownership impact: backend implementation is normally Terra-owned and test/bench content Luna-owned. The user explicitly authorized direct completion in this conversation.
- Contract impact: additive modules only. `Resource`/`Evidence`/`RiskFinding` P0 schema, source-evidence gate, and no-legal-advice semantics remain unchanged.
- Verification: deterministic fixture tests, schema-compatible model construction, `compileall`, and targeted pytest. Linux-only external-tool ZIP gates remain separately reported if the host cannot evidence them.

## CR-20260913-java-backend-migration

- Requested by: 用户，2026-09-13。
- Scope: 审计 `backend/app/**/*.py`，以 Java 作为新的后端运行时主线；优先迁移领域模型、受限仓库扫描、依赖/许可证/AI 资源发现、规则结果和结构化报告。
- Target files: 新增 `backend/java/` Maven/Spring Boot 模块及其测试、迁移规范、协调记录；既有 Python 文件在 Java 契约与安全回归通过前作为兼容基线保留，不删除、不覆盖。
- Ownership impact: `backend/` 通常由 Terra 负责；本次由用户明确授权 Root 直接实施。变更将触及不可信路径、Git 输入和外部工具边界，必须保留不执行目标代码、不安装目标依赖、证据优先与人工复核语义。
- Contract impact: 保持 P0 JSON Schema、`unknown`/`review_required` 语义和报告证据链；Java 输出新增而非替换已发布 Python API，生产切换需另行验收。
- Verification: Maven 单元测试、固定样例契约校验、真实受信任检出仓库扫描、JSON/CSV/HTML 结构化产物校验，以及 Python/Java 对照测试；外部 ScanCode/Syft 仅在其可执行文件已固定并可用时启用。
## CR-20260913-second-human-blind-review

- 提出者：GPT-5 / Root Coordinator；日期：2026-09-13；状态：执行中（用户明确授权）。
- 目标：在 `benchmarks/annotations/real-resource-20260911-ai-assisted/` 新增第二位独立真人盲审的隔离材料、空白五维裁决模板、提交校验器，以及盲审完成后使用的分歧/仲裁模板。
- 所有权与影响：目标目录为 Luna 的标注材料范围；不修改 `ai-draft.json`、`human-confirmation.json`、`human-amendment-r05.json` 或已有指标。新增契约要求第二评审在提交前不可接触 AI 草稿、首位裁决、R05 修订和 AI 复审，并逐条填写 resource/evidence/license/risk/suggestion 五维。
- 验收：包内不泄露被隐藏结论；R01-R12 恰好各一条；严格校验独立性声明、包哈希与全部五维；分歧/仲裁工作区在盲审锁定前不得写入最终裁决。后续由 Luna 复核材料可用性、由 Sol 复核仲裁语义。

## CR-20260917-single-human-rereview

- 提出者：用户；日期：2026-09-17；状态：实现完成，待真人执行。
- 目标：在只有一名真人的条件下，为既有R01-R12建立时间隔离盲化复标、两轮差异、冲突查证和最终冻结闭环，并提供详细操作手册。
- 所有权与影响：新增内容位于Luna负责的Bench标注材料目录；用户明确授权Root直接实现。不修改既有AI草稿、首轮真人回执、R05修订、gold指标或公共P0/P1 Schema。
- 契约边界：仅允许声明`single_human_time_separated_rereview`；不能声明双人独立复核、标注者间一致率或AI第二评审。当前工具仅适用于`output_review`，不得用于隐藏预测的`benchmark_gold`。
- 验收：至少72小时冷却；12条/60维完整填写；逐维理由和逐记录证据定位；包、回执、比较、冲突与最终快照哈希绑定；篡改中间比较文件失败关闭；合成闭环14项通过。

## CR-20260918-bench2-java-contract

- 提出者：用户；日期：2026-09-18；状态：本地实现完成，待发布。
- 目标：按已批准的 B-P1-05 设计实现 Bench 2.0 Draft 2020-12 JSON Schema、独立 Java 校验库与 CLI、正反例和自动化校验测试，供 CI/Maven 离线使用，不新增 Web API。
- 所有权与影响：`backend/java/` 通常由 Terra 负责，`benchmarks/` 测试材料通常由 Luna 负责；用户已明确授权 Root 在本任务中直接实现。保留现有 P0/P1 Schema 与运行时接口，不改写人工标注或 gold 结论。
- 契约影响：新增 `openguard-bench-manifest/2.0` 和稳定诊断报告 `openguard-bench-validation-report/1.0`；Schema 负责结构约束，Java 负责 ID/引用闭包、split 隔离、holdout 暴露、amendment 链、文件哈希和正式指标准入；CLI 退出码固定为 0/1/2/3。
- 验收：Maven 单元/集成测试、正反例期望诊断、CLI JSON 与退出码、离线路径/符号链接/哈希安全测试、`git diff --check`、第三方依赖台账和设计/进度/AI 辅助记录同步。

## CR-20260920-bp1-public-field-approval

- 提出者：GPT-5 / Root Coordinator；日期：2026-09-20；状态：**待项目负责人批准**。
- 目标：为 B-P1-01 `ResourceProfileDraft`、B-P1-05 Bench 2.0 与 FN taxonomy 提交公共字段的显式批准请求；本请求本身不修改 Domain、Assessment、P0/P1 Schema、公共 API、报告 DTO 或现有 gold。
- 请求批准的范围：
  1. `ResourceProfileDraft` 是否作为版本化公共对象，以及 `provider`、`canonical_id`、`resource_kind`、`revision` 的定义、默认值、空值和迁移语义；
  2. `visibility`、`gated`、`disabled` 的展示/脱敏边界；它们不得表示授权或可再分发权；
  3. `declared_license_raw` 的公共暴露和后续 SPDX 映射责任；批准前 `license_expression_id` 固定为空；
  4. `authorization_status` 的枚举、责任人和证据门槛；批准前固定为 `pending`；
  5. `detected_by` 新枚举、公共 Evidence materialization、reviewer/holdout/amendment 治理字段；
  6. FN/FP taxonomy 与 matching policy 的版本、历史指标回填与 holdout 脱敏策略。
- 已有设计依据：`docs/spec/b-p1-01-resource-profile-draft.md` 第 6～8 节、`docs/spec/b-p1-05-bench-2-manifest.md`、`docs/spec/b-p1-06-bench-public-corpus-governance.md` 第 5～6 节。
- 批准前约束：只允许离线、脱敏 fixture 和 Java 内部 Draft；不得联网、不得实现 metadata transport、不得修改 Domain/Assessment/公共 API，且不得从 provider 元数据推导许可证、授权或合规结论。
- 请负责人逐项给出 `批准`、`驳回` 或 `需修订`，并记录 Schema/API 版本、迁移/回滚、脱敏与再分发策略、责任人和生效 revision。批准后才可进入 parser 接入、Gold、Detector 0.3、License Provenance/NOTICE Facts 与 holdout 阶段。
## CR-20260923-B06-B07-P2B-offline-gates

- 提出者：用户，2026-09-23；状态：执行中。
- 范围：B06 双人独立真人盲审/分歧/FN-FP taxonomy/amendment 校验，B07 仅消费受控 Pipeline receipt 的性能汇总，以及 P2B B 工件交付质量门禁。
- 边界：不生成或伪造真人 Gold，不允许 AI 或单人复核替代双人独立真人 Gold；不启动生产扫描，不把单次耗时作为性能结论；不修改 A 的 snapshot、Report、Task 或前端。

## CR-20261006-NOTICE-selector-partial-and-G8

- 提出者：用户；日期：2026-10-06；状态：本地实现，待 A/Sol 独立复核与生产签收。
- 目标：NOTICE 候选数超过 1024 时保留受控扫描的有界前缀，按 `partial` + `notice_selector_truncated` 显式标记覆盖缺口；终态准入重算可信 Inventory 并核对前缀、顺序和 gap。Windows 可导入 durable dispatcher，但实际 POSIX 锁不可用时失败关闭。
- 所有权与影响：触及 A4 生产 lifecycle、A1 终态准入和 durable ZIP 派发器，由用户当前明确授权 Root 推进；A 需复核终态安全边界，B 需复核 NOTICE 来源语义。旧独立 `admit_terminal` 保持截断拒绝，不改公共 API、Schema、Assessment、Report 或法律判断。
- 验收：selector/coverage/平台能力定向单测通过；受控 POSIX 上补跑 ZIP/Git→STAGED/BOUND→Draft→Report 六文件、完整回归与重启读回；A 提供终态哈希回执，前端提供同版本真实 API 浏览器回执。未取得这些回执前不宣称 NOTICE 全面完成。

## CR-20261008-P2B-A-frozen-contract

- 提出者：GPT-6.1 Sol（本对话后端 B）；日期：2026-10-08；状态：待 A/Root 冻结。用户确认 P2-01 基线和 DTO 尚未冻结。
- 目标：A 给 B 一个只读、稳定的扫描事实快照契约，至少有 `scan_id`、终态/覆盖状态、对象 ID/类型/精确版本、Evidence ID 闭包与不可变摘要、三态用途及其版本；并定义 B 候选事实 DTO 的接纳/拒绝状态、来源与哈希字段。B 仅返回候选事实和验证状态，A 独占正式 Assessment、持久化、报告及 API。
- 本地材料：A 定义上传/文件读取的安全边界、对象版本核对、SHA-256 与 source receipt 的权威性等级、人工适用性核验和重算入口；B 的离线解析只输出 `text_observed`，不能以用户声明升级为官方声明或授权。
- npm：A 冻结唯一官方 `GET https://registry.npmjs.org/is-number/7.0.0` 的可信出口、DNS/重定向/代理策略、超时/字节上限、响应来源与 UTC 时间回执，以及失败在正式评估中的传播方式。当前 B 只提供离线固定身份/有界响应 parser；未发起网络请求。不可下载/安装包或扩 provider。
- D4：A 提供同一 `scan_id` 的补证前后只读快照、事实哈希、候选接纳及正式重算回执，供 B 对三个固定真实来源逐项对账；`express@4.18.2` 保留为未调参样例。验收需展示新增事实、变化建议、剩余缺口及不可重现失败，不把它称为 Bench/Gold。
- 影响文件：A 的 API/存储/Assessment 所有权文件由 A 自行实现；B 不修改这些文件。本请求不预设最终 DTO 字段名或公开 Schema 版本。

### 2026-10-08 后端 B 接线补充（待 A/Root 冻结）

以下是 B 内部 `evaluate_bound_candidate` 的输入样例，不是公共 DTO 的批准版本。A 必须从同一次只读 ScanRun 生成并认证整个快照，固定 canonical 序列化和 `snapshot_sha256`；B 目前只能检查摘要形状，不能凭调用方自报摘要证明快照可信。

```json
{"scan_id":"scan-real-id","status":"completed","coverage_gaps":[],"snapshot_sha256":"<A核验的64位小写SHA-256>","objects":[{"id":"component-real-id","scan_id":"scan-real-id","kind":"component","name":"is-number","version":"7.0.0","scope":"runtime_dependency","evidence_ids":["evidence-license-id","evidence-scope-id"],"usage":{"version":"purpose-revision-id","values":{"commercial":true,"modified":false,"distributed":true,"network_service":false,"training":false,"redistributed_assets":false,"source_disclosure":false}}}],"evidence":{"evidence-license-id":{"id":"evidence-license-id","scan_id":"scan-real-id","object_id":"component-real-id","version":"7.0.0","role":"license_text","source_sha256":"<64位SHA-256>","content_sha256":"<64位SHA-256>","source_status":"upstream_verified","verification_status":"verified","license_expression":"MIT","applicability":"human_verified"},"evidence-scope-id":{"id":"evidence-scope-id","scan_id":"scan-real-id","object_id":"component-real-id","version":"7.0.0","role":"scope_attestation","source_sha256":"<64位SHA-256>","producer":"human","verification_status":"verified","scope":"runtime_dependency"}}}
```

样例中的 ID 和摘要占位符不得用作真实回执。A 还须定义 `scan_id`/对象 ID/版本/用途版本的空值与历史版本语义、Evidence 对象闭包的权威来源、`partial` 的缺失范围、同一 Evidence 多对象关系的表达和人工核验回执的签发责任。B 对缺对象、重复对象、用途版本缺失、用途字段不全、悬空/重复/遗漏 Evidence、证据重标、错扫描/对象/版本及来源 Hash 缺失直接拒绝；扫描 partial、AI 资产或范围未核验只给缺口。成功回执含 `candidate_only`、`usage_version`、`snapshot_sha256`、`basis_evidence_ids`、逐依据 `basis_source_sha256`、`rule_version=V4-MIT`、条件文本及剩余缺口。即使 B 返回候选，A 仍须重新核对快照、来源、规则版本和用途版本后才能接纳，不得转为授权或义务已履行。

本地材料由 A 负责安全上传/读取，并提供权威 `(scan_id, object_id) -> exact_version` 与已接纳 `(scan_id, object_id, version, canonical_filename) -> content_sha256` 历史映射。B 的成功样例为 `text_observed`、`content_sha256`、`byte_count`、`source_claim`、`official_statement=false`、`applicability_human_verified=false`、`authorization_status=pending`。相同身份同内容返回 `duplicate_material`，同身份不同内容返回 `material_identity_conflict`；错扫描/对象/版本、空文本、非 UTF-8、超限和摘要不符拒绝。A 应原子化检查并写入去重历史，防止并发上传绕过 B 的只读预检；A 决定用户来源声明如何保存和脱敏。

npm 仅请求 `GET https://registry.npmjs.org/is-number/7.0.0`。A 的可信出口回执需含固定请求/最终 URL、HTTP 状态、UTC 时间、响应原文字节 SHA-256/字节数、是否超时、DNS/代理/重定向策略验证结果、出口版本及失败原因；响应不得超出 32 KiB。B `parse_official_response` 的离线成功样例是 `state=parsed_untrusted_transport`、`parser_version=p2b-npm-metadata/1`、`official_metadata_observed=false`、`license_declaration_state=provider_declared_unverified`、`authorization_status=pending`，即使传入正确 URL 也不升级。超时或非 200 返回 `state=failed` 和原因/状态/可得响应 Hash；错包、错版本、重复 JSON 键、超限、摘要错误拒绝。B 已提供 `parse_attested_response(body, receipt, verify_attestation)` 窄接线点：先核固定 GET/最终 URL、零重定向、字节数、摘要及策略 ID，再要求由 A 实现的可信回执验证器明确返回 `True`；只有 200 且离线解析成功时输出 `official_metadata_observed=true`。A 必须冻结回执 DTO、验证器来源及 DNS/代理/超时/重定向策略，防止调用方注入自造验证器；该标志只证明本次官方元数据，不证明许可正文或适用性。

D4 所需 A 回执：三个真实 ScanRun 的同一 `scan_id` 补证前后只读快照、各快照/新增事实/Evidence SHA-256、用途版本、B 候选接纳及正式 Assessment 重算 ID、旧 Assessment 与旧报告的只读校验回执。B 逐例比较新增/保持不变/剩余未知；`express@4.18.2` 仅作未调参保留样例。A/Root 负责实现和冻结这些公共边界，B 不改 A 文件。

### 2026-10-09 B 对账与前端接线增量（仍待 A/Root）

- A 必须逐例签发 `scan_id`、对象 ID/类型/精确版本、`usage.version`、完整 Evidence ID 集合及来源/内容 SHA-256，补证前后各一份同次扫描快照；并分别给出新旧 Assessment/报告 ID、摘要和旧版只读读回摘要。空 ID、`source_object_key` 和 B 合成测试 Hash 均拒绝作为正式输入。
- B 的只读入口可接收 A 同请求固定的 `expected_scan_id`、`expected_usage_version`，与快照不同时分别拒绝为 `snapshot_scan_mismatch`、`usage_version_mismatch`。两项 pin 必须来自 A 已认证的扫描/用途版本，不得由上传者自报；A 尚未冻结其正式 DTO 字段名和验签方式。
- B `reconcile_object` 的候选对账结果新增 `suggestions_updated`、前后 `basis_evidence_ids` 与 `basis_source_sha256`；同一用途的依据变化需可见，不可仅看建议数量。新增 Evidence 的非空 `content_sha256` 格式无效、既有 Evidence 删除/改写、非目标对象或证据变化、旧工件摘要不一致均拒绝，A 应保留失败原因和原 Assessment/报告。B 的摘要格式检查不能代替 A 的来源认证与读回证明。
- B 区分 `invalid_added_content_hash`（新增 Evidence 内容摘要格式错误）与 `invalid_readback_hash`（旧 Assessment/报告读回摘要格式错误）；A 接纳回执应原样保留具体原因码，不能合并成成功状态或笼统的许可结论。
- A 正式接纳/拒绝矩阵需返回材料预检与服务端最终状态的区别、Material ID、对象/版本、是否有人工适用性签收、拒绝后旧 Assessment/报告仍可读的回执。A 出口失败需记录固定 GET 目标、最终 URL、UTC 时间、HTTP 状态或超时、响应大小/Hash、策略 ID 和失败码。未给这些回执时，机器草案 `frontend-handoff-draft.json` 的相关字段保持 `null`/`false`，前端不得将其当真实验收数据。
