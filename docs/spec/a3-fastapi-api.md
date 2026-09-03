# A3-1 FastAPI 最小 HTTP API 实现规格

状态：`IMPLEMENTED-PENDING-ROOT-VERIFICATION`

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

候选证据 ID：`EVD-A3-FASTAPI-GIT-API-001`。在 Root 完成不可变提交绑定前，其状态必须
保持 `PENDING`。
