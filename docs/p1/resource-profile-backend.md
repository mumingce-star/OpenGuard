# A07-2 ResourceProfile Backend

实现说明，不是第二份 Contract。权威接口为 Frozen P1 Contract 1.0 与
`schemas/p1/resource-profile.schema.json`；本轮未修改 Schema。

## 架构与信任边界

`TemporaryMetadata → MetadataParser → ParsedMetadataObservation → 严格校验 →
不可变 MetadataObservation → metadata.db → ResourceProfile`。

Parser port `metadata-parser-port/1` 位于 `backend/app/p1/profile_models.py`。
关键字输入为 provider、resource_kind、resource_identity、temporary_metadata、source_descriptor；
输出只能为严格 `ParsedMetadataObservation`，不接受任意 dict/extension。
字段包括 parser_version、bounded_excerpt、fields、verification_status、coverage_gaps。
excerpt 最多 1000 **字符**，fields 最多 64，value 是非空字符串或 null；空版本 clarification
不适用于 metadata field。拒绝额外字段、raw/authorization 等保留字段名及完整响应文本副本。
Parser 是进程内受信实现，不是能隔离恶意 Python 代码的沙箱。

Transport 独占 provider/repository/revision/source_url/fetched_at/body_sha256 的权威。
服务校验 descriptor 与请求、bytes/hash/长度、版本及 revision 状态的一致性。
`bounded_content_revision_unconfirmed` 保留 resolved_revision=null，加入
`metadata_revision_unconfirmed`，不升级 verified revision。
`content_hash` 是 transport 原响应 SHA256；规范化 DTO 的完整性 Hash 另存数据库。
真实 HF/B01 parser 未实现；`app.profile_synthetic` 只供测试和 Acceptance 显式注入，
不在生产 default factory 中导入或启用。

## 独立存储

`metadata.db`，`PRAGMA user_version=1`，显式 initialize；import/GET 不建库。
三张表：`metadata_observations`、`profile_refresh_jobs`、`profile_refresh_requests`。
逐项状态置于经过 DTO 校验且带 Hash 的 job_json 中，不另设 job_items 表。
observation_id 主键不可变；请求 `(scan_id,request_key)` 唯一并外键引用 job。
完整 sqlite_master/索引/约束/user_version 与实现自有 DDL 比较，未知库拒绝，不迁移。
私有 0700 目录/0600 文件，拒绝 symlink/hardlink/宽权限；busy_timeout 2 秒；
`BEGIN IMMEDIATE` 原子预留和逐项完成，observation 插入与 item 成功同事务。
默认最小剩余空间 512 MiB、库上限 128 MiB、单记录 128 KiB；synthetic root 显式 min_free=0。
新库使用 SQLite 默认 DELETE journal；安全测试另开启并保持真实非空 WAL/SHM 检查。

Observation ID 绑定 scan/resource identity+instance、provider、请求 revision mode/value、
resolved revision、原内容 Hash、parser 版本、规范化观察与算法 `resource-profile/1`。
去重语义排除 fetched_at/provenance.generated_at，重复相同事实保留第一次观察的完整对象；
同 ID 不同语义冲突，不能覆盖。读取校验完整 DTO Hash/语义 Hash/绑定。

## Profile GET

`GET /api/v1/scans/{scan_id}/resources/{resource_id}/profile`。
identity、双键、license observations、authorization_fact 仅来自固定 Scan facts；
metadata 只在 metadata_observations，不能提升授权、创建 Scan Evidence 或改 Assessment/Report。
Scan evidence 引用实际当前 Evidence；metadata 引用 namespace=profile_observation。
无观察仍返回 Profile，gap=`metadata_observation_unavailable`。
completed/partial 可读；partial 保留扫描缺口；queued/running 为 not_ready，failed/cancelled 为 not_comparable。
GET 不 fetch/parse/retry，不创建 Assessment/Report，不改变业务表。
profile_id 绑定事实 Hash、资源双键、观察集合和算法/参数；Profile provenance.generated_at
是本次实际投影的 UTC 生成时间（RFC3339 Z），语义 ID 仅排除顶层 provenance.generated_at。
重复 GET 比较除该时间外的完整语义，不能通过固定旧 Scan 时间伪造生成时间。
Observation.fetched_at 仍来自 transport；其 provenance.generated_at 是 parser/normalization
实际生成时刻，既有 observation 去重语义仍排除该时刻，重复 fetch 复用第一次不可变观察。

负责人批准的兼容映射仅在 `identity.version`：源 Component/AIAsset version 为 `""` 时，
投影 null 并加入 `identity_version_empty_normalized_to_unknown`。
不回写 ScanRun/facts_hash，不改 Diff、metadata value、Assessment、Evidence、Report 或 Frozen Schema。
ERRATUM-01 仍仅适用于 Diff。Owner R2另批准只在 identity.provider 将 AIAsset.provider
精确空字符串映射 null，并加入 identity_provider_empty_normalized_to_unknown；不 trim、不猜测
provider、不从URL补齐，不修改上游事实/hash或 metadata field。其余字段不擅自清洗。

## Refresh / Job

- `POST /api/v1/scans/{scan_id}/resource-profiles/refresh`
- `GET /api/v1/scans/{scan_id}/resource-profiles/jobs/{job_id}`

请求仅 resource_ids、expected_facts_hash、idempotency_key；资源集合排序但重复 ID 拒绝。
最多 32 个资源、16 KiB JSON 请求；继承 local Origin/Sec-Fetch-Site 写边界。
验证稳定 Scan、facts_hash、归属和安全 MetadataRequest 后预留 job。
只支持可安全构造的 Hugging Face model/dataset 标识；不接受客户端 URL/headers/token/timeout。
POST 显式同步执行 `refresh_once`，不启动 worker/定时器/无限重试。单资源受 A07-1 transport 预算限制。
同 key 同规范化请求返回原 job；异输入 409；真实 SQLite 两连接并发只产生一个 job。
claim 原子取得一次执行权；中断后 pending 不自动重试，GET 不恢复执行；必要时由负责人明确使用新 key。

公开 job 状态仅 pending/succeeded/failed。部分失败总状态 failed，items 保留逐项成功/失败；
成功 observation 不删除，scan.status 不变。外部失败只保留 allowlist reason code，
不保存异常正文、Location、headers、cookie/token 或原响应。
默认生产 `create_default_app` 不构造 MetadataTransport、不注入 parser/store；
Profile 可读 Scan facts，Refresh 和未配置的 Job 返回 503 feature_disabled。

## Synthetic 验收与限制

Acceptance `/1` 原样可 read/start/status/stop/verify，不补 metadata.db、不增加 Profile。
新 `init-v2` 显式初始化 `/2`，调用正式服务生成观察；五个 F02 场景见 Acceptance 文档。
manifest 只保存固定引用/场景/预期状态，不包含业务 Profile Mock。
HTTP smoke 重放 refresh/job/幂等/冲突，相同已播种观察去重；scan 9 的额外
`synthetic/unfetched` 资源不预先 refresh，用真实 HTTP 验证空观察到新观察，固定资源 ID 尾段 9c45。
所有 metadata bytes 由内存 synthetic transport 提供，无 DNS/DoH/socket/TLS；
测试/HTTP harness 的 loopback guard 是进程级防误操作，不是 OS firewall。
raw sentinel 检查主 DB、非空 WAL、SHM、API、job、error、repr/log，不通过删库掩盖泄露。

未验收/未实现：真实 B01 parser、真实 HF 内容、NOTICE、人工核验接纳、Report/Profile integration、
前端业务页面、Windows/原生 Linux/生产部署。Docker Desktop UID 0 策略不代表跨平台许可。
负责人源码 Review 前不提交、推送、合并或部署。
