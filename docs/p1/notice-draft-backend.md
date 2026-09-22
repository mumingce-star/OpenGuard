# NoticeDraft Backend Core

Frozen NoticeDraft 1.0 的不可变草稿实现；不是授权验证、正式 Assessment、违规结论或义务履行证明。

## 接口与初始化

- `POST /api/v1/scans/{scan_id}/assessments/{assessment_id}/notice-drafts`：JSON 仅接受 `idempotency_key`（非空白、最长 200 字符）。使用既有 localhost Origin / Sec-Fetch-Site、JSON、16 KiB 写边界。
- `GET /api/v1/scans/{scan_id}/assessments/{assessment_id}/notice-drafts/{draft_id}`：只读取已保存快照；不接受 latest、路径、URL 或其他查询参数。
- `NoticeDraftStore(private_root / "notice_draft.db").initialize()` 显式初始化。目录 0700、文件 0600；只接受自身 exact schema / version，未知库不迁移。DELETE journal 模式；外部切换 WAL 的库拒绝打开，避免 GET 建立 shared-memory sidecar。
- `NoticeDraftService(registry, assessment_store, store, facts_reader=reader)` 通过 `create_app(..., notice_draft_service=service)` 注入。没有正式 per-scan reader，default factory 不初始化此 DB、不加载 fixture；路由公开，POST 返回 `503 feature_disabled`，无配置存储的 GET 返回 `404 not_found`。后者保留旧 Acceptance /1、/2 的 unavailable GET 行为，不隐藏 OpenAPI route。

错误：参数 400；来源拒绝 403；不存在 404；固定绑定/幂等冲突、not_ready、not_comparable 409；body 超限 413；配置或来源/存储不可用 503。错误不回显文件路径、SQL 或原始异常。

## A-owned facts port

`NoticeFactsReader.read(scan_id, facts_hash)` 返回 `NoticeFactsInput`：固定 scan ID、facts hash、结构化 v2 package、独立可信的 expected canonical package SHA256。reader 是服务器可信依赖，不是客户端上传入口；生产 reader 必须负责 per-scan 来源选择、原始字节校验与外部 hash 锚定。不能仅对任意不可信输入现算 hash 并当成来源验证。

只消费 `openguard.notice-license-facts/2`。严格结构、false/pending policies、唯一 ID、引用闭包、report rows 机器字段、时间、来源分层 hash 和 provider selected JSON value hash 均校验；不打开包内 path/URL，不调用 detector/generator。原始仓库/归档字节未包含在包中，不宣称消费层再次独立扫描或下载验证。

## 绑定、草稿与 hash

创建仅允许 completed/partial ScanRun 和对应固定 Formal Assessment，facts_hash 必须相同。queued/running 为 not_ready，failed/cancelled 为 not_comparable。

只在稳定、唯一、精确 purl/version/source 或 HF canonical identity/version/source 匹配时绑定资源；歧义不猜测。只允许能证明相同仓库 revision、完整 source URL/locator、内容 SHA、excerpt 的唯一 file Evidence 映射到 scan namespace。归档容器和 provider pointer 在当前 P0 无完整对应维度，保守为空并记录 `source_evidence_not_mapped_to_scan_namespace`。`ev.*` 永远不直接充当 ScanRun evidence ID。

只有观察关系及固定证据支持的 NOTICE excerpt 进入 text，其他为 null+missing。根项目/依赖/AI 均保留独立 entry。license_expression_ids、obligation_refs 保持空，不推断许可证或义务。gap 不等于违规，authorization 仍 pending。

canonical JSON 使用 UTF-8、sort_keys、无多余空格、禁止 NaN。content_hash 只排除自身，包含 draft_id、created_at、完整 binding、entries 和 provenance。entry 按 fact ID 排序，集合引用/gaps 稳定排序。provenance.parameters_hash 保存外部固定 package hash；内部 fingerprint 另绑定 package hash、完整 binding 和 generator version。

同 scoped key+固定输入返回原快照；相同 key+不同固定输入 409。相同固定输入的新 key 作为别名复用同一快照，避免逻辑重复；输入实际变化才产生新 draft。SQLite BEGIN IMMEDIATE 原子提交；请求记录 hash 绑定精确 scan/assessment/key/fingerprint/draft，快照行元数据绑定 payload 与 content_hash。普通 SHA256 检测数据不一致，不是防拥有本机 DB 写权限者整体重签的加密认证机制。

## 验收与未完成边界

测试消费未修改的 v2 fixture，经真实 Service、SQLite、FastAPI TestClient 与重新打开 Store 验收，称 `FIXTURE_BACKED_REAL_SERVICE_ACCEPTANCE`，不是 production live NOTICE scan。GET 不访问 registry、Assessment、reader、scanner、AI 或网络；重复响应固定。

Report V2 产品代码不改；非空 notice_refs 继续 `not_ready / notice_snapshot_reader_not_available`。Report 消费、正式生产 facts reader、生产接线、前端页面及真实扫描属于后续工作包。v3 不消费。未部署。
