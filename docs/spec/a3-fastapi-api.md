# A3-1 FastAPI 最小 HTTP API 实现规格

状态：`INDEPENDENT-VERIFIED-LOCAL`

本文件实现 `p0-domain-contract.md` 第 7 节的第一条可运行 HTTP 纵切，不建立第二套公共
契约。公共领域契约仍为 `0.1.1`，持久状态唯一来源仍是 A3-0
`SQLiteScanRunRegistry`。

## 1. 本纵切边界

本轮实现：

1. FastAPI 应用工厂、Swagger/OpenAPI；
2. `POST /api/v1/scans` 的公开 Git JSON 请求；
3. 扫描状态、资源、风险、证据和报告五类读取；
4. 统一的 `{error:{code,message,request_id,details}}` 非 2xx 信封；
5. 单机私有 SQLite 数据目录和 Uvicorn 启动入口。

本轮不实现：ZIP multipart、Git clone 或任何联网、worker、A4 Pipeline、扫描器、许可证
规则、AI、报告生成、前端、认证/CORS、取消/扫描列表、健康或版本端点。尤其是 `202`
只表示请求已持久化为 `queued`，不能写成扫描已经执行。A3 总包仍为进行中。

## 2. 路由与返回

| 方法 | 路径 | 本轮行为 |
|---|---|---|
| POST | `/api/v1/scans` | 接受 `{source_type:"git",source,idempotency_key?}`，返回 `202` 与 `scan_id/status/status_url` |
| GET | `/api/v1/scans/{scan_id}` | 返回状态、阶段、进度、摘要和结构化错误 |
| GET | `/api/v1/scans/{scan_id}/resources` | 返回只读 `ResourceView`；`Component`/`AIAsset` 是唯一领域对象 |
| GET | `/api/v1/scans/{scan_id}/risks` | 返回稳定按 finding ID 排序的 `RiskFinding` |
| GET | `/api/v1/scans/{scan_id}/evidence/{evidence_id}` | 返回单条 `Evidence` |
| GET | `/api/v1/scans/{scan_id}/report?format=...` | 只返回 ScanRun 已登记的 `ReportLink`，不现场生成报告 |

`ResourceView` 是 `{kind,resource}` 标签包装，不复制或改写领域事实。资源支持
`kind/ecosystem/provider/verification_status`，风险支持
`outcome/severity/resource_kind`。`ecosystem` 只适用于组件，`provider` 和
`verification_status` 只适用于 AI 资产；组合不匹配时返回空集合，不猜测映射关系。

## 3. 创建与幂等语义

- 仅接受无凭据、无 query/fragment、非 localhost/IP literal 且含仓库路径的 HTTPS URL；
- 该检查只冻结 HTTP 输入边界，不进行 DNS 或网络访问，也不替代未来 TrustedEgress；
- 相同 `idempotency_key` 与同一规范化 source 返回原扫描；同 key 不同 source 返回
  `invalid_source/idempotency_conflict`；
- 新扫描真实写入 SQLite，初态必须是 `queued/queued/0`，所有结果数组为空；
- 尚无 worker，因此读取资源/风险/证据返回 `scan_not_ready`，报告返回
  `report_not_ready`；测试中的终态 ScanRun 由注册表显式注入，不是产品伪造结果。

## 4. 错误与线程边界

所有公开错误只使用冻结 code、固定 message、服务端生成 `request_id` 和稳定
`details.reason`；不返回 Pydantic 明细、异常文本、绝对路径、URL 或凭据。同步路由由
FastAPI 在线程池执行，SQLite 操作不直接阻塞事件循环。未识别异常统一为
`internal_error/unexpected_failure`。

## 5. 本轮验收

- OpenAPI 恰好列出六条冻结业务路径，`/docs` 可访问；
- Git 创建、规范化、持久化、幂等与冲突可复现；
- queued 不伪造结果，终态读取与四类过滤可复现；
- 缺失扫描/证据、未就绪报告、请求校验与内部异常均使用统一脱敏信封；
- 默认工厂创建 `0700` 数据目录与 `0600` SQLite 文件；
- A3-1、A3-0、P0、全量、Schema 等值与真实 Uvicorn smoke 全部通过后才能绑定证据。

证据 ID：`EVD-A3-FASTAPI-GIT-API-001`，当前绑定经独立复核与 P1 闭环后的实现提交
`aedf65cef55f4683c3d82cb8e79b4d20d2fb1f71`。只批准为本机 macOS/POSIX 的最小
FastAPI/SQLite Git queued API 纵切证据；不得外推 ZIP、Git 物化、worker、Pipeline、
Linux isolation、TrustedEgress 或完整产品。

## 6. 2026-09-03 独立复核闭环

Luna 的原始独立测试发现并保留三项 P1：默认 Starlette 404/405 未使用统一错误信封、
`urlsplit()` 会静默接受原始控制字符、以及 2048 上限误按 Unicode code points 而非 UTF-8
bytes 执行。Root 仅在本纵切内完成最小修复，未新增路由、错误码或业务功能；Luna 未修改
或放宽独立断言并原样复测，三项 P1 全部关闭。

绑定门禁为：A3-1 实现与独立测试 `48 passed`，A3-0 实现与独立测试 `77 passed`，P0
`46 passed`，全量 `549 passed`，Schema 等值、compileall、diff、受保护路径及权限检查
通过。全量仍有 1 条 Starlette TestClient/AnyIO 第三方弃用 warning；该 warning 未被过滤，
但不影响本纵切断言。真实 Uvicorn 仅绑定 `127.0.0.1` 临时端口，验证 POST 202、GET queued、
停止后 SQLite 重开和 0700/0600 权限，不代表公网部署或扫描已执行。

### 2026-09-08 P0 capacity admission amendment

POST /api/v1/scans adds a documented 503 response using the existing ErrorEnvelope, code scan_capacity_unavailable, and reasons persistent_capacity_exceeded/busy/unavailable (full names use the persistent_capacity_ prefix). Git and ZIP are checked before input consumption. Existing route and domain shapes remain unchanged; this explicitly extends error semantics, not an unchanged-contract claim. Factory enables a 2GiB admission watermark, 256MiB per active/proposed scan and 512MiB filesystem reserve. Read routes are unaffected. Idempotent POST may also be refused; existing task GET remains usable. See deploy/README.md for single-process and non-hard-quota boundaries.


## 2026-09-09 V2 分组与进度兼容扩展

本轮没有新增路由、写接口或持久模型迁移。状态响应在原字段之外可选返回 `created_at`、`started_at`、`finished_at`（UTC ISO 时间，未知为 null）和 `ai_progress`。后者仅在当前进程执行 AI 阶段时提供组工作量 `groups_total/groups_done`、实际 `requests/cache_hits/successful_groups`、AI阶段 `elapsed_seconds` 和 `eta_seconds` 区间，`eta_scope=ai_stage`。没有两个实际请求耗时样本、重启后无观测或估计超时则没有 ETA；可有 `estimate_insufficient=true`。这不是整链剩余时间，也不是资源覆盖率，不能用它重写终态或原 progress。历史任务依靠持久时间和原进度读取。

风险列表在原 `items/total` 之外返回可选 `grouping`；筛选先作用于原发现再生成投影。`openguard.grouping/v1` 的每条 finding_id 有唯一主组，resource_count 是 ID 并集。组包含真实规则/版本、许可/证据/范围等 context、成员 ID、严重度数量及 advice。advice.kind 区分 group_ai、rule、historical、unavailable。旧客户端可忽略新增字段，新前端对缺失字段兼容；旧原始对象/CSV 不变。前端只投影和筛选已载入数据，分段展示不宣称后端分页。

### 真实步骤进度补充（2026-09-09）

现有状态响应可选 `work_progress: {percent, operation}`，仅运行中且当前进程有观测时非null。`percent` 为已执行流程步骤的权重（0≤值<100），不是文件覆盖率、耗时比例或许可证通过率；`operation` 为当前实际操作。Git/ZIP输入读取、文件清单、依赖解析、ScanCode/Syft结束事件驱动5/15/25/30/40/55/65/70等流程节点，后续按原阶段推进；AI按真实已完成组数在85至94之间推进。没有新事件时百分比不自行增长，界面活动光带仅说明仍在执行。原始 `progress`、`stage`、终态与持久报告不变；completed仍100，partial/failed按原值展示，终态清除临时观测。单进程128项有界观测，不新增队列、路由、定时任务或数据迁移；历史/旧接口缺字段时正常回退原进度。
