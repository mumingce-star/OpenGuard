# A3-2 ZIP HTTP 创建与进程内后台扫描规格

状态：`APPROVED-PENDING-ROOT-BINDING`

## 1. 目标与责任边界

A3-2 实现项目负责人拥有的 API、输入接线与 Pipeline 集成：保持 P0 的六条业务路径不变，在同一个 `POST /api/v1/scans` 上同时接受既有 Git JSON 与冻结的 ZIP `multipart/form-data`，把合法 ZIP 安全暂存、创建 durable queued `ScanRun`，再以 FastAPI 进程内 BackgroundTask 显式执行既有 A4-1。

截图中的 `partial/rules/70` 不是 ZIP/Pipeline 失败。它表示依赖资源和证据已经可用，但组员负责的许可证规则尚未接线。公开口径固定为“阶段性结果可用，许可证分析待接入”，不得改写为 `completed` 或完整合规结论。

本轮不修改 P0 Schema、A2、B1-B7、A3 registry、A4 worker/plan 或前端；不实现许可证规则、Git 网络输入、AI、报告、持久任务队列、重试、lease/heartbeat、崩溃恢复、Linux/TrustedEgress。

## 2. HTTP 契约

- 路径：`POST /api/v1/scans`，业务路径总数仍为六条。
- Git：保持 `application/json` 与 `GitScanCreateRequest` 行为不变。
- ZIP：`multipart/form-data`，只允许一个 `source_type=zip`、一个 `file`、零或一个 `idempotency_key`；未知或重复字段拒绝。
- ZIP 文件名必须是无路径、无控制字符、UTF-8 不超过 255 bytes 的 `.zip` 名称；文件 Content-Type 只接受 `application/zip`、`application/x-zip-compressed` 或 `application/octet-stream`。
- 上传压缩字节沿用服务端 A2 默认上限 64 MiB，请求不得抬高。
- 成功返回既有 `202 {scan_id,status,status_url}`。该响应只承诺任务已持久创建，不承诺背景执行已经结束。

## 3. 暂存、幂等与生命周期

1. 默认应用启动时创建并验证私有 `0700` 的 `data/uploads` 与 `data/workspaces`；SQLite 保持 `0600`。
2. 上传以随机服务端名称和 `0600` 文件暂存，不采用客户端路径；流式计算 SHA-256，空文件和超过 64 MiB 立即拒绝并清理。
3. queued P0 `ScanRun` 的 `project.source_type=zip`、`project.source=随机暂存逻辑名`，项目显示名仅来自已验证文件名；`provenance.input_digest` 绑定实际上传字节。
4. ZIP 幂等 fingerprint 只由 `source_type=zip` 与实际字节摘要组成。同 key/同字节返回原任务且删除重复暂存；同 key/不同字节返回 409。
5. 仅新任务登记 BackgroundTask。后台调用既有一次性 A4-1 plan；结束后无论 partial/failed/异常都删除暂存 ZIP。A2 自身继续负责解压 workspace 的成功/失败清理。

## 4. 状态与错误

- 合法依赖 ZIP 的当前预期终态为 `partial/rules/70`，带真实 Component/Evidence 和 `rules_stage_not_connected`。
- 坏 ZIP 在 202 后由 A4-1 形成脱敏 terminal failure；这区分“HTTP 字段无效”和“异步内容安全校验失败”。
- 同步公开错误只使用既有错误信封：无效 multipart/文件名/类型为 `invalid_archive`，超限为 `archive_limit_exceeded`，幂等冲突为 `invalid_source`，暂存或 runtime 故障为 `internal_error`。
- 响应、错误、ScanRun 和日志不得包含本机绝对暂存路径、客户端路径、底层异常或凭据。

## 5. 明确可靠性边界

FastAPI BackgroundTask 是单进程最小纵切，不是 durable worker queue。进程在响应后、任务结束前退出时，SQLite 可能保留 queued/running，当前版本没有 lease、重试或 orphan 回收；因此 evidence 只能证明“受控单进程存活期间，HTTP ZIP 请求可驱动 A4-1”。这些可靠性能力必须另立项目负责人任务，不得由单元测试外推。

## 6. 验收

- `POS-A3ZIP-001`：混合 Python/JavaScript ZIP 返回 202，最终为 `partial/rules/70`，资源和证据 GET 可用。
- `POS-A3ZIP-002`：同 key/同字节返回同 scan，不重复执行，重复暂存清理。
- `POS-A3ZIP-003`：Git JSON 六路由与既有错误/幂等行为完全回归。
- `POS-A3ZIP-004`：默认工厂创建私有运行目录，真实 Uvicorn 能完成 202→terminal 查询。
- `NEG-A3ZIP-001`：缺失/重复/未知字段、错误 source_type、空 key 拒绝且不创建任务。
- `NEG-A3ZIP-002`：非法文件名或 Content-Type 拒绝且无暂存残留。
- `NEG-A3ZIP-003`：空上传和 64 MiB 刚超过返回稳定错误并清理。
- `NEG-A3ZIP-004`：同 key/不同摘要冲突且重复暂存清理。
- `NEG-A3ZIP-005`：坏 ZIP 被异步持久化为脱敏 failed，暂存与 A2 workspace 清理。
- `NEG-A3ZIP-006`：未配置 ZIP runtime 的应用拒绝 multipart，但 Git JSON 仍可用。

候选 evidence：`EVD-A3-ZIP-BACKGROUND-SCAN-001`。只有实现测试、独立测试、完整回归、Schema、OpenAPI、真实回环、权限/敏感/清理和不可变提交绑定均通过后才可批准。

## 7. 2026-09-03 验证裁决

- 实现侧 20 项通过；Luna 独立非回环 21 项通过；实现与独立非回环合计 41 项通过。
- 两个真实 Uvicorn 回环项在获准受控环境合计 2 项通过；新 ZIP 探针验证 multipart 202、`partial/rules/70`、resources 查询与进程结束后 SQLite 重开。
- 完整集合在沙箱为 `684 passed, 2 failed`，两项失败均为沙箱禁止 bind `127.0.0.1`；同两项在获准环境为 `2 passed`，故当前完整集合等价 686 项通过。
- P0 Schema 导出等值、compileall、diff、受保护路径、目录权限、敏感信息、依赖台账与上传范围检查通过；无开放 P0/P1/P2 实现缺陷。
- `python-multipart==0.0.32` 已按官方 PyPI 核验版本、Apache-2.0、Python 3.12 支持、Trusted Publishing 与 wheel SHA-256，并登记资源台账。
- evidence `EVD-A3-ZIP-BACKGROUND-SCAN-001` 已绑定不可变实现提交 `530e93055528761d9c9b08a99d348ab41d2c9c37`，状态为 `APPROVED`；只批准 macOS/POSIX、CPython 3.12、SQLite、FastAPI 单进程存活期间的 ZIP HTTP→BackgroundTask→A4-1 纵切，不批准持久队列、崩溃恢复、许可证、AI、报告或完整作品。
