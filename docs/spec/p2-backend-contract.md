# P2 v1：独立结果、回答和小材料 HTTP 合同

本候选以 `integration/p1@aabd7940f65ec8a78b33c863b4db81b400509b7d` 的后继 cz 分支 `6dc340776bc63c3b925d7fa3645efbbd40c4ccf9` 为基础。未把其他未提交隔离候选拼入本分支。实现身份是本文件所在完整提交；基础 SHA 本身不包含 A 增量。

Owner 已确认：L2 创建独立 `result.revision`，不要求每次回答新建 Assessment。只有原用途/正式评估流程改变 Assessment；这里不调用该流程。L1 是确定性 P2B 候选及缺口，**不是 Qwen 用途建议、Formal dimensions 或正式授权结论**。旧 R6、Qwen L1 proof 和前端均未迁移/接线。

## 运行与存储

正常工厂 `app.api.main:create_default_app` 已注册路由，持久化为数据根内私有 `p2.db`，非离线 DiagnosticStore。默认关闭功能，默认只读；启动显式启用，不通过 URL 切换权限。POSIX 私有目录、Python 3.12、现有 backend 依赖；本轮已核验 Python 3.12.14/FastAPI 0.141.1/Pydantic 2.13.4/SQLite、amd64 离线镜像。Windows 权限适配未验收。

以下是接收方未来获准运行时的入口，目录必须为该机器专用的 0700 root，不指向 Owner 原库：

```sh
OPENGUARD_DATA_DIR=/ABSOLUTE/PRIVATE/TASK_ROOT \
OPENGUARD_ENABLE_ASSESSMENTS=1 OPENGUARD_ENABLE_P2=1 \
OPENGUARD_P2_READONLY=0 OPENGUARD_P2_DATA_SCOPE=TEST_ONLY \
OPENGUARD_ENABLE_AI=0 OPENGUARD_ENABLE_PUBLIC_GIT=0 \
OPENGUARD_ENABLE_DURABLE_ZIP=0 OPENGUARD_ENABLE_PROFILE_METADATA=0 \
OPENGUARD_ENABLE_EXTERNAL_SCANNERS=0 \
PYTHONPATH=backend python3 -m uvicorn app.api.main:create_default_app \
  --factory --host 127.0.0.1 --port 18080
```

不使用旧 Compose。没有自动导入业务数据的公共接口。工厂仅在启动时初始化已开启的 Store；GET 不初始化/修复，不扫描、不抓取、不采用材料、不建 Assessment/报告、不调用模型。工厂保留原 Observer 配置，但 P2 路由不调用这些 Observer。数据库/原始材料不得上传。关闭写入设 `OPENGUARD_P2_READONLY=1`，关闭 P2 设 `OPENGUARD_ENABLE_P2=0`；现有 Origin 检查继续生效。P2_READONLY只约束P2写入口，不是全站权限开关；既有只读预览服务器未修改。退出用正常 SIGTERM。

## 精确路由

前缀 `P=/api/v1/scans/{scan_id}/assessments/{assessment_id}/p2`。所有 DTO 均在 `schemas/p2/contract-v1.schema.json` 的 `$defs`；字段禁止额外项，布尔严格区分 true/false/null。生产 OpenAPI 同时发布 DTO 与错误 Schema。

| method/path | 参数/请求 | 响应 | 语义 |
|---|---|---|---|
| GET `P/binding` | path scan/assessment | Binding | 当前父身份，只读；不生成结果 |
| POST `P/results` | CreateRequest | 201 Receipt | 显式生成首个确定性结果；已有 head 时按 CAS 返回原结果 |
| GET `P/results` | `assessment_version>=1`, `offset=0..10000` | ResultIndex | 每页20，head 可变；不是固定结果 URL |
| GET `P/results/{result_id}` | `assessment_version>=1` 必填 | Result | 不可变结果，重复刷新同身份 |
| GET `P/results/{result_id}/summary` | 同上 | Summary | 该结果的不可变 companion，不是新 Formal Report |
| POST `P/answers` | AnswerRequest | 201 Receipt | 显式资源子集回答，同步事务 |
| GET `P/answers/{answer_id}` | `assessment_version>=1` | Answer | 原回答不可变读回 |
| POST `P/materials` | MaterialRequest | 201 Receipt | 小文本观察、绑定、采用为未核验观察、增量结果在一次事务内完成 |
| GET `P/materials/{material_id}` | `assessment_version>=1` | Material | 元数据与内容 Hash；服务端核验留存字节，不返回正文 |

`scan_id/assessment_id/result_id/answer_id/material_id` 是完整身份；不能省略 Assessment 版本后选择 latest。结果 URL 不生成内容。summary 不能通过另一个 result ID 复用。

## 身份与 L1 字段

`Binding` 固定 `scan_id, assessment_id, assessment_version, registry_revision, project_revision, facts_hash, usage_hash, rule_version, assessment_sha256`。project_revision 可以明确为 null；资源的 version 也可为 null，但不能上传不能精确定位版本的材料。服务端从现有 Registry/Assessment 读取、验证事实/用途 Hash、资源闭包，计算前后复核；不信任请求自报摘要。

`Result` 自身含 `result_id, revision, previous_result_id, result_sha256, schema_version, algorithm_version, created_at, data_scope, computation, publication_status, formal_effect`。`result_id` 内容身份包含绑定、算法、data_scope、前驱、revision、资源计算及材料/答案引用；结果正文自 Hash 与 Store 记录 Hash 均检查。读取还核对 SQL 行和 payload 的 scan/assessment/object ID，配置不得把 TEST_ONLY 改称 OWNER。

- `usage` 保存七维原值，不自动补 false。
- `resources[].subject.{resource_id,version}` 是适用对象；`advice[].scope=RESOURCE`，无项目级推广。
- `advice[].usage/saved_value/selection` 表示该用途及本次选择。NOT_SELECTED 不等于不适用。
- `advice[].state/conditions/gaps/basis_evidence_ids/rule_ids` 分别给候选建议、必要条件、证据缺口与来源。未形成建议时不能把 conditions 空列表读成无义务。
- `resources[].evidence_ids/evidence_source_hashes/material_ids/answer_ids` 给实际引用；source_hashes 只列真实 content_hash，缺失时保留命名缺口，绝不以 Evidence 记录自身的摘要代替原材料 Hash。`recomputed_resource_ids/reused_resource_ids` 由后端决定。
- `inherited_local_support` 仅承接父 Assessment；`inherited_support_source=PARENT_ASSESSMENT_NOT_NEW_VALUE`，不是本轮新增成果。

### 状态边界

| 字段/枚举 | 含义 |
|---|---|
| `publication_status=succeeded` | 本次独立结果已经保存，**不是许可判断成功** |
| `state=candidate` | 有确定性条件候选，仍 `verification_state=candidate_only` |
| `state=unknown` | 未形成候选；命名 gaps 说明来源/版本/范围等不足 |
| `state=pending` | 已有新材料观察，适用性未核验 |
| `state=partial` | 存在候选与缺口或不同资源状态；不等于扫描/正式结论改变 |
| `advice.state=not_selected` | 保存值 false，此次未选择，不能改写为 allowed/not_applicable |
| `error.details.state=rejected/conflict/unavailable` | 拒绝、409 冲突或503不可用；不保存成功结果 |
| `Material.verification_state=pending` | 用户上传未核验；`FULL_TEXT_CLAIMED` 也是用户声明 |
| `Answer.provenance=USER_ASSERTED` | FULFILLED 等只是用户断言，绝不自动完成 Formal 义务 |

**本适配器没有可从 P0 人审标记推导 P2B `upstream_verified` 的依据。** 保存的许可名、producer、URL、文本关键词均不能满足该来源门槛。当前适配器明确保留 `upstream_source_attestation_missing`，不产生新的正向 conditional_candidate。cz 内部的正向门槛原样保留；当前真实 v6 的新用途正向成果为零。这是待解决的可信来源接纳缺口，不能因为 HTTP 201 而关闭。

冲突检查包括 scope 中真实资源/版本/许可表达绑定、多个已核验 scope、不同已核验许可材料 Hash、MIT expression 与 normalized_ids 不一致。即使某份资源许可文本未进入当前 LicenseExpression 列表也不丢掉冲突。拒绝不是自动选择较宽松材料。Hash 不证明上游发布者或许可适用性。

## L2 回答、材料与版本

全部写请求共同字段：`binding`、`expected_revision`、`parent_result_id`、`idempotency_key`（8–100个 ASCII 字母/数字/下划线/连字符）。初次0/null；之后精确当前 head。

AnswerRequest 还包括 `question_id, question_code, answer_code, subjects[], evidence_ids[]`。问题 ID 来自该结果的 `questions`，不能由前端自造。问题来源标为 `DETERMINISTIC_P2_NOT_R6_AGGREGATE`，不是冒充旧 R6 两问。两类语义为交付范围和履行声明，分别允许：

- `DELIVERY_SCOPE_FOR_RESOURCES`: YES_INCLUDE / NO_EXCLUDE / NOT_DECIDED。
- `OBLIGATION_FULFILLMENT_IN_DELIVERY`: FULFILLED / NOT_FULFILLED / NOT_DELIVERED_YET / UNKNOWN。

subjects 1–1000、无重复；只覆盖明确列出的资源，其他资源继续未知。每个 subject version 必须精确相等。evidence_ids 至多100、无重复、只能取这些资源原有证据闭包。回答追加不可变 Answer，revision 对应创建时独立结果 revision；不改变原 Assessment，也不重标旧 R6 UserFact。

MaterialRequest 还包括 `subject, evidence_ids, filename, content_base64, source_sha256, source_description, completeness`。只允许 LICENSE/LICENCE/NOTICE，可加 `.txt/.md/.rst`；UTF-8，非空，拒绝NUL、非法编码、危险文件名、Hash不符、资源/版本/证据错绑。每份解码后最多65536 bytes，每个父 Assessment 最多20份；HTTP body上限98304 bytes，其他写请求16384 bytes。JSON重复键和NaN/Infinity拒绝。不是ZIP/二进制/通用上传平台，不执行文件，不依关键词认定许可。

Material返回 `material_id, revision=1, subject, evidence_ids, source_sha256, byte_count, completeness, parse_status=text_observed, adoption_status=adopted_as_unverified_observation, verification_state=pending, source_level=user_supplied_unverified`。正文仅入私有 sidecar，GET元数据会核验其Hash。新同名同版本材料不同内容是409；没有替换旧材料或任意多版本材料编辑入口。已有 Material ID 可从结果引用选择查看；本轮没有跨 Assessment 的任意复用接口。

同请求键+原始语义 body 重放返回原 Receipt，哪怕 head 已前进；同键不同 body409。并发由 SQLite BEGIN IMMEDIATE + head CAS处理；失败回滚整个材料/答案/结果/摘要/请求凭据事务。丢失响应不能换新键盲重发：先读精确结果/列表，随后复用**原键原body**；503/网络超时不能断言未保存。新键和过期 CAS409，先重新读 head，明确新动作才用新键。重复相同回答不新建版本；相同材料新键409，原键可重放。

本合同为同步201，无Job、不返回伪202。网络超时只是不确定，客户端仍按上面精确读取/重放。文件/容量/并发错误503保留原结果；GET不修复。每库128MiB、记录8MiB、请求凭据10000条上限，无自动清理历史。

## 错误与重新读取

统一 `error.{code,message,request_id,details}`；不返回原异常、私有路径或上传正文。P2层 details包含reason、state、retry；CAS附 `current_result_id/current_revision`。全局Origin/body中间件沿用既有同形 ErrorEnvelope，细节不伪造为P2逻辑错误。

| HTTP | 稳定 code 示例 |
|---|---|
|403|origin_rejected|
|404|p2_not_found、p2_scan_not_found、p2_assessment_not_found、p2_resource_not_found|
|409|p2_revision_conflict、p2_idempotency_conflict、p2_parent_binding_conflict、p2_resource_version_conflict、p2_evidence_wrong_resource、p2_evidence_binding_conflict、p2_evidence_conflict、p2_question_binding_conflict、p2_duplicate_material、p2_material_identity_conflict|
|413|request_too_large、p2_material_size_limit、p2_material_count_limit、p2_resource_capacity、p2_result_too_large|
|422|p2_request_invalid、p2_json_invalid、p2_material_base64_invalid、p2_unsupported_material_name、p2_material_hash_mismatch、p2_material_utf8_required、p2_material_binary_content、p2_material_empty_text、p2_material_version_not_exact|
|503|p2_service_disabled、p2_read_only、p2_storage_unavailable、p2_parent_storage_unavailable、p2_integrity_error、p2_storage_invalid、p2_schema_unsupported、p2_capacity_exceeded|

409后 `GET P/results?assessment_version=N` 获取当前head，然后按ID精确GET；父绑定冲突时先GET binding；不自动合并或覆盖。404不能选择latest代替。422/413/403需纠正输入/环境，不能原样无限重试；503也先读取，不能把所有503称为“未保存”。已保存身份之后辅助summary读取失败不抹掉保存；再次GET原result可取得。失效/损坏记录只拒绝，不重新计算。

## 增量及 companion

回答或材料只重新计算其显式subjects。未受影响资源整行复用，保存两个ID集合；前端不计算另一套正式差异。每次有效变化创建 Result revision，原Result仍不可变。Summary与Result一次事务提交，绑定同Assessment ID/version/facts_hash/usage_hash/rule_version、result ID/revision/hash、全部材料及回答ID。summary GET只读。未改变现有 Report V2、NOTICE 或 Formal；不能把 companion 作为原历史报告已恢复的证据。

## 实际验收与未关闭门禁

`docs/p2/real-http-receipts.json` 是本轮真实 loopback HTTP 留存的脱敏响应，**不是端点运行时读取的静态fixture**。测试容器 network none，正常工厂与真实SQLite，固定v6原件恢复到一次性TEST_ONLY root；未克隆原整库，未重跑扫描/模型。原扫描请求fingerprint未留存，隔离导入用明确本地导入摘要；旧Report正文未取得，空非报告槽未参与报告成功宣称。完整原件和DB不提交。

固定对象、直接GET路径、新旧结果/材料/摘要完整ID见机器回执。本机服务已收尾；路径不等于xzb机器上已可访问。需接收方获得兼容提交及自己获准的数据根后另行实际启动，不能使用Owner路径或本文件回执代签。

当前未关闭：可信上游/适用性原件到P2B的正式接纳来源（不能由P0人审flag补出）；新真实正向用途样本；xzb目标机兼容/固定数据授权与运行签收；两条NOTICE既有fixture失败由父提交对照保留。Qwen业务诊断、Python Stage A和Formal新政策未执行。阶段1整包不标PASS，xzb整体阶段2不自动放行；具体模块先行接线需Owner/xzb接受本合同和这些边界。
