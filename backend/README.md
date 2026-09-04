# Backend 模块

计划包结构：

```text
app/
├── api/             # scan、findings、reports、benchmarks
├── ingestion/       # repo、zip、workspace
├── scanners/        # scancode、syft、manifest、AI assets
├── domain/          # 统一数据模型
├── knowledge/       # SPDX、OSI、许可证义务
├── risk/            # 确定性规则和证据链
├── ai/              # 结构化抽取、解释和整改建议
├── reporting/       # HTML、JSON、CSV、资源清单
├── persistence/     # SQLite 与迁移接口
└── security/        # 限额、路径、防泄漏和清理
```

第一阶段不执行目标仓库代码，也不安装其依赖。

## A3-0 持久 ScanRun 注册表

`app.persistence.SQLiteScanRunRegistry` 是后续 A3 API/A4 编排的内部前置：在私有 POSIX
目录中的 SQLite WAL 数据库持久化完整 P0 `ScanRun` 快照，并提供 revision CAS、创建请求
fingerprint 幂等、稳定 keyset 分页和关闭语义。它不启动 HTTP、worker 或 scanner，也不保存
ZIP、路径、凭据或报告正文。每次 CRUD 使用独立连接并固定 `WAL`、`FULL`、`foreign_keys` 和
`trusted_schema=OFF`；快照以 strict UTF-8 canonical JSON BLOB 保存，损坏、未知 schema、锁竞争
和路径权限问题只暴露稳定、脱敏的 `ScanRegistryError.code`。

实现侧回归：

```bash
PYTHONPATH=backend python -m pytest -q tests/unit/test_a3_scan_registry.py
```

此结果仅证明单机 POSIX SQLite 上的持久 ScanRun 注册表纵切；FastAPI、后台 worker、Pipeline、
外部 scanner、集群/备份/灾难恢复和 exactly-once 外部副作用仍不在范围内。

## A2-0/A2-1 本地 ZIP 安全边界

`app.ingestion.ZipIngestionService` 是当前首条不联网的输入纵切。服务在构造时只
接受管理员提供的、已存在的绝对 POSIX workspace root 和 `ZipSafetyLimits`；配置在
启动时校验，调用方没有可以提高上传、解压、文件、路径或压缩比限额的请求参数。

它先将 ZIP 流受限写入 descriptor-relative workspace，随后在写入目标树前验证所有
成员名、NFC/case-fold 冲突、文件/目录冲突、加密与已知 Unix 特殊类型，以及首段为
`~` 或 `~user` 的 home shorthand；并交叉核对
central directory 与每个 local header 的标志、压缩方式、文件名、CRC 和尺寸。小型
ZIP64 尺寸字段及当前支持的数据描述符会与 central directory 一致性校验，任何 local/
central 不一致都以 `invalid_archive/archive_integrity_failed` 拒绝。普通文件经
`openat`/`dir_fd`、`O_NOFOLLOW` 和 `O_CREAT|O_EXCL` 流式新建；文件清单从该树重新
计算 SHA-256，并以 `openguard-inventory-v1` 生成稳定 root digest。所有成功和失败
路径都会尝试清理本任务 workspace；清理失败会失败关闭并阻止返回 inventory，因而不会
发布部分树。

零或未知 ZIP external attributes 被当作新的普通文件字节，不恢复权限、owner、ACL、
xattr 或链接。已知 symlink、device、FIFO、socket 等类型会被拒绝。

稳定 `details.reason` 契约与冻结安全验收一致：全部原名/NFC/case-fold/文件目录冲突
统一为 `invalid_archive/archive_duplicate_path`，已知特殊类型为
`invalid_archive/archive_entry_type_unsafe`。上传、总解压、单文件、条目数、压缩比、
路径深度和路径长度配额统一为 `archive_limit_exceeded`，其 reason 分别为
`archive_upload_size_limit`、`archive_total_size_limit`、`archive_single_file_limit`、
`archive_entry_count_limit`、`archive_ratio_limit`、`archive_path_depth_limit` 和
`archive_path_length_limit`。

当前范围不包含公开 Git、TrustedEgress、Linux cgroup/network namespace、持久任务
注册表、最终 API 状态映射或完整 ZIP64/多卷/header-overlap 语料证明；macOS 的单元
和文件系统测试不能作为这些部署级安全控制的证据。

## A2-2 生命周期绑定的只读扫描会话

后续可信解析器需要读取 manifest、许可证等小文件时，应使用
`ingest_with_consumer()`，不能取得临时目录路径或文件描述符：

```python
from app.ingestion import ZipIngestionService

with open("./demo.zip", "rb") as archive:
    service = ZipIngestionService("/absolute/server-owned-workspace-root")
    try:
        result = service.ingest_with_consumer(
            archive,
            lambda session: session.read_bytes("pyproject.toml"),
        )
    finally:
        service.close()
```

consumer 只能读取 inventory 中精确登记的普通文件，并受服务端单文件/累计读取上限、
descriptor-relative `O_NOFOLLOW`、目录与文件 identity seal、SHA-256 复验约束。回调
结束后保存的 session 引用永久失效；open/read/close、替换竞态、跨线程、重入、consumer
异常和 cleanup 均按稳定错误失败关闭。该接口仅供可信、非执行性的进程内解析器使用；
Python 私有属性和反射并不是安全沙箱，不得将任意第三方代码作为 consumer 执行。

## B1 Python manifest 解析器

`app.scanners.parse_python_manifests` 是可信、非执行性的 A2-2 consumer：仅从
`ReadOnlyScanSession.inventory` 发现 `pyproject.toml` 与精确小写的
`requirements*.txt`，再以 `read_bytes()` 在固定额度内读取。它解析 PEP 508 声明、
`project.dependencies`、optional dependency groups 和 `build-system.requires`，生成
稳定的不可变中间 DTO 与字段/行级 evidence draft；不会打开目标路径、执行代码、安装
目标依赖、联网或求值 marker。`packaging==26.3` 是精确锁定的解析依赖；缺失或版本不符
时以 `scanner_failed:python_manifest_parser_unavailable` 失败关闭。

实现侧回归与真实内存 ZIP 纵切可复现为：

```bash
PYTHONPATH=backend python -m pytest -q tests/unit/test_b1_python_manifest_parser.py
```

这只是 B1-1 的 parser DTO 层；B1-2 已在独立模块中把该 DTO 映射为 P0 `Component` 与
`Evidence`，但两者都尚未扫描许可证或输出最终资源清单。

独立安全回归可单独复现：

```bash
PYTHONPATH=backend python -m pytest -q tests/security/test_a2_readonly_scan_session_independent.py
```

## B1-2 Python P0 映射

`app.scanners.map_python_manifest_result` 将冻结的 B1-1 DTO 纯内存映射为 P0
`Component` 与 `Evidence`。映射器以 inventory root digest、manifest locator/hash/excerpt
和固定 UUIDv5 namespace 生成稳定 ID；调用方必须显式注入零偏移 UTC `observed_at`。
它不会重读 manifest、求值 marker、访问网络或推断已安装/已解析版本、purl、许可证和风险。
parser 的 `partial` 与七字段 diagnostic 原样保留，不能等同于未来 `ScanRun` 的状态。

离线本地 ZIP CLI 的显式 Python 依赖模式为：

```bash
PYTHONPATH=backend python -m app.cli --python-dependencies ./demo.zip
```

该模式只在 A2-2 生命周期绑定的 read-only consumer 中调用 B1 parser 和 mapper，使用
`262144` 字节单文件、`4194304` 字节累计读取上限。成功或可恢复的 parser partial 均在
stdout 输出单行、稳定排序的 `openguard.python-dependencies` JSON；P0 对象完整保留
`null` 字段，diagnostic 固定输出全部七个字段。固定 `clock`、同一 ZIP 和版本 profile
可以逐字复现输出；真实 wall-clock 只会改变 Evidence 的 `observed_at`，不会改变 ID。

无 flag 的 `python -m app.cli LOCAL_ZIP` 仍是冻结的 inventory 演示，既不导入也不调用
parser、mapper 或 clock。两个 CLI 模式均不联网、不执行 ZIP 代码、不安装目标依赖；失败
只输出稳定的 `code:reason`，不会公开路径、URL、manifest 内容或 traceback，且 task
workspace 在成功、partial 或失败后均会清理。

实现侧 B1-2 回归可复现为：

```bash
PYTHONPATH=backend python -m pytest -q tests/unit/test_b1_python_p0_mapper_cli.py
```

这仍是本地 Python manifest 到 P0 的有界纵切，不是完整依赖清单、许可证/合规结论、报告、
Git intake、TrustedEgress 或 Linux 隔离的运行级证明。

## B1-3/B1-4 JavaScript manifest 与 P0 映射

本地 ZIP 的 JavaScript 依赖纵切可通过以下显式模式运行：

```bash
PYTHONPATH=backend python -m app.cli --javascript-dependencies ./demo.zip
```

它仅在 A2-2 的受限只读 consumer 中读取根项目 `package.json` 与同目录
`package-lock.json` v2/v3；支持四类根直接依赖，并以 lock 的直接 `packages` 条目补充
精确版本和 canonical HTTPS registry URL。严格 JSON、任意层重复 key、输入配额、不安全
selector、lock root 不一致与不受支持 lock 均返回稳定 partial 或脱敏失败。不会调用
Node/npm、执行项目代码、安装依赖或联网；npm v1/shrinkwrap/Yarn/pnpm/workspace/传递依赖、
许可证和合规结论均不在本纵切范围内。

实现侧回归：

```bash
PYTHONPATH=backend python -m pytest -q tests/unit/test_b1_javascript_manifest_p0_cli.py
```

## 本地 ZIP CLI 演示

在项目根目录、已安装项目测试依赖的环境中，可用以下命令只运行本地 ZIP 安全接收与
inventory 摘要演示：

```bash
PYTHONPATH=backend python -m app.cli ./demo.zip
```

命令不联网、不执行 ZIP 中的代码、不安装其依赖，也没有可以抬高默认安全限额的命令行
选项。成功时 stdout 仅输出稳定 JSON（`schema`、`version`、`root_digest` 与排序后的
`entries`）；安全拒绝时 stdout 为空，stderr 仅输出稳定的 `code:reason`，退出码为 1。
参数或输入文件不可用时同样不回显路径或原始异常，并以退出码 2 失败。临时 workspace
仅用于本次进程，服务关闭后不会保留任务目录。

## A3-1 FastAPI 最小 API

在项目根目录安装 `backend/pyproject.toml` 的运行与 dev 依赖后启动：

```bash
PYTHONPATH=backend python -m uvicorn app.api.main:create_default_app --factory --host 127.0.0.1 --port 8000
```

浏览器打开 `http://127.0.0.1:8000/docs` 可查看冻结六类 P0 路由。默认运行数据写入
Git 忽略的 `data/scans.db`；也可用 `OPENGUARD_DATA_DIR` 指定一个仅当前用户可访问的
数据目录。当前 `POST /api/v1/scans` 只接受公开 HTTPS Git JSON，并真实持久化为 queued；
尚无 worker，所以不会克隆仓库、执行扫描或伪造完成结果。ZIP multipart、Pipeline、扫描器、
报告生成和前端均不属于 A3-1。

最小创建示例：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/scans \
  -H 'Content-Type: application/json' \
  -d '{"source_type":"git","source":"https://github.com/example/OpenGuard","idempotency_key":"demo-001"}'
```

## A4-0 显式单进程 Pipeline Worker

`app.pipeline.ScanPipelineWorker` 仅由后端调用方显式传入完整七阶段 `PipelinePlan` 后执行；它不会
启动线程、轮询数据库或自动消费 API 创建的 queued 任务。worker 以 A3 revision/CAS 认领 queued
快照，按固定阶段持久化进度，并把已校验 Adapter 的完整 `ScanRun` 聚合写回 SQLite。Adapter 只是
调用方注入的边界；其测试 stub 不代表真实 Git/ZIP 摄取、扫描、许可证、AI 或报告结果。

实现侧回归：

```bash
PYTHONPATH=backend python -m pytest -q tests/unit/test_a4_pipeline_worker.py
```

该能力只证明本机 SQLite、单进程、单次显式调用的 durable 编排。它不提供后台任务、重试、租约、
心跳、超时、崩溃恢复、exactly-once 外部副作用或完整 Web 扫描流程。

## A5-1b 真实运行复现

`python -m app.ai.runtime_probe SCAN_RUN.json --runs 2 --timeout-seconds 60` 只连接已运行的
本机 Ollama loopback。输入必须是至少含一个尚未绑定 remediation 的合法 P0 `ScanRun`；不要修改
冻结样例，可复制到仓库外的临时目录再清空样例 remediation。命令不会安装、下载或启动模型，
不会打印 prompt、模型原文、异常或输入绝对路径；成功时只输出版本、锁定 model ID、成功率、
聚合延迟和事实/来源/`pending`/稳定 ID 校验结果，失败只输出固定错误 JSON。正式实测应以
`OLLAMA_NO_CLOUD=1 OLLAMA_NOHISTORY=1` 启动仅绑定 `127.0.0.1` 的 Ollama 服务。

## A4-1 本地 ZIP 依赖计划

`app.pipeline.build_local_zip_dependency_plan()` 是项目负责人集成层的显式一次性计划：调用方先建立
一个本地 ZIP 对应的 queued `ScanRun`，再把该计划交给 `ScanPipelineWorker`。计划在同一个 A2-2
只读会话内调用既有 Python 与 JavaScript parser/mapper，核对 ZIP 原始字节摘要，随后把 inventory
root digest、真实 P0 `Component`/`Evidence`、producer 版本和 summary 持久化到 A3 SQLite。

当前许可证规则尚未接线，所以有真实依赖证据的预期终态是 `partial/rules/70`，错误码为
`rules_stage_not_connected`；这不是运行失败，也不能描述为完整许可证或合规扫描。AI 与 report 阶段
不会执行。workspace root 必须是后端预先创建、仅当前用户可写的绝对 POSIX 目录；计划不接受调用方
抬高 A2 安全限额，不联网、不执行 ZIP 中的代码、不安装依赖，也不暴露本机 ZIP 路径。

实现侧回归：

```bash
PYTHONPATH=backend python -m pytest -q tests/unit/test_a4_local_zip_pipeline.py
```

该内部工厂本身不启动 HTTP 或后台队列；A3-2 现已在受控单进程内替调用方创建 queued 记录并通过
BackgroundTask 显式执行它。公开 Git、安全网络摄取、许可证规则、AI、报告和持久队列仍不属于 A4-1。

## A3-2 ZIP HTTP 与进程内后台扫描

安装 `backend/pyproject.toml` 的精确锁版依赖后，默认应用在既有六条业务路径中同时支持 Git JSON
与 ZIP multipart。启动：

```bash
PYTHONPATH=backend OPENGUARD_DATA_DIR=./data uvicorn app.api.main:create_default_app --factory --host 127.0.0.1 --port 8000
```

另一个终端提交 ZIP：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/scans \
  -F source_type=zip \
  -F idempotency_key=demo-zip-001 \
  -F file=@./your-project.zip\;type=application/zip
```

响应中的 `status_url` 可用于轮询。当前合法依赖 ZIP 的预期终态是 `partial/rules/70`：这表示 Python/
JavaScript 依赖组件与证据已经可以查询，但许可证规则尚未接入；不是 ZIP/Pipeline 失败。资源可通过
`GET /api/v1/scans/{scan_id}/resources` 查看，证据可通过返回的 evidence ID 查询。

上传和 multipart 请求均有服务端边界，暂存目录与 workspace 为私有目录；任务结束后清理。该后台执行
仅为 FastAPI 单进程 BackgroundTask，不是持久任务队列：进程中途退出时还没有 lease、重试、恢复或
孤儿清道夫，不能外推生产可靠性。实现侧复现：

```bash
PYTHONPATH=backend python -m pytest -q tests/unit/test_a3_zip_background_scan.py
```

## A5-0 可注入 AI Provider 与确定性降级

`app.ai.apply_ai_remediations()` 接受一个已验证的 P0 `ScanRun` 和调用方注入的 local/remote
Provider。它只为尚未绑定整改的 `warning`、`review_required` 或 `unknown` finding 生成
`pending` Remediation；请求只含该 finding、已引用 Evidence 以及资源已绑定的许可证事实。
Provider 返回值必须是 64 KiB 以内的严格 JSON，并且只能引用请求中已有的 evidence ID。

AI 关闭时不需要 Provider；模型不可用、抛错、响应截断、重复键、额外字段、身份或引用不匹配、
敏感片段及绝对路径均稳定降级。降级只记录脱敏的 `ai_assist` 诊断和 AI provenance，不发布部分
建议，也不改变组件、AI 资源、许可证、义务、规则结果或统计。

实现侧回归：

```bash
PYTHONPATH=backend python -m pytest -q tests/unit/test_a5_ai_provider.py
```

## A5-1a 本地 Qwen3/Ollama transport

`app.ai.OllamaProvider` 已实现 A5-0 的标准库 HTTP Provider。它只接受字面量回环 IP，显式禁用
环境代理，并在每次生成前通过 `GET /api/version` 和 `GET /api/tags` 核验固定的 Ollama
`0.33.3`、模型 `qwen3:4b-instruct-2507-q4_K_M` 及完整 manifest SHA-256；之后才以
`stream=false`、`think=false`、固定 options 和 JSON Schema 调用 `POST /api/generate`。三次请求
共享一个总 deadline，任何连接、超时、HTTP、版本、模型、摘要或包装错误都只返回脱敏 transport
错误，并由 A5-0 保留确定性结果、记录 `degraded`。

本模块不会启动 Ollama、自动下载模型或读取凭据。当前开发机器尚未发现 Ollama，因此只能复现
协议 adapter 与本地测试 server，不能声称真实 Qwen3 已运行。安装、权重拉取、实际 manifest
比对、结构化输出质量/延迟实测属于 A5-1b；消费组员 B5 真实 finding 并接入 Pipeline 属于
A5-1c。

实现侧回归：

```bash
PYTHONPATH=backend python -m pytest -q \
  tests/unit/test_a5_ai_provider.py \
  tests/unit/test_a5_ollama_transport.py
```

## A6-0 确定性报告导出核心

`app.reporting.render_report()` 接受已验证、状态为 `completed` 或 `partial` 的 P0 `ScanRun`，
在内存中生成 JSON、HTML、CSV 或 `resource_inventory` 报告。CSV/资源清单严格使用竞赛要求的
七字段；HTML 对不可信值做实体转义并禁止脚本和外部资源；每个 `ReportArtifact` 都包含稳定
文件名、媒体类型、原始字节和 SHA-256。

```python
from app.domain.models import ReportFormat, ScanRun
from app.reporting import render_report

run = ScanRun.model_validate_json(scan_run_bytes)
artifact = render_report(run, ReportFormat.HTML)
```

本接口不会写文件、更新 SQLite、创建 `ReportLink` 或启动下载路由。`partial/rules/70` 只能生成
明确标注“阶段性”的报告；缺失的许可证、规则风险和 AI 建议保持缺失，不会被推断成合规通过。
实现侧回归：

```bash
PYTHONPATH=backend python -m pytest -q tests/unit/test_a6_report_exports.py
```

A6-0 本身不写文件或提供 HTTP；已由下述 A6-1 接入持久化和只读下载，并由 A6-2 接入 Pipeline
终态发布。前端接线和最终匿名化验收仍属于 A6 后续纵切。

## A6-1 报告安全持久化与只读下载

`app.reporting.ReportArtifactStore` 把 A6-0 内存产物发布到后端私有报告目录，并返回 P0
`ReportLink`。默认应用创建 `data/reports` 为 `0700`；扫描子目录同为 `0700`，内容和 metadata
文件为 `0600`。内容以 SHA-256 寻址并先于 metadata 原子落盘，读取时重新验证类型、owner、权限、
inode、长度和摘要；损坏或替换不会返回部分字节。

publisher 是显式内部接口，不由 GET 触发：

```python
from app.domain.models import ReportFormat
from app.reporting import ReportArtifactStore

store = ReportArtifactStore(private_report_root)
link = store.publish(terminal_scan_run, ReportFormat.HTML)
```

`GET /api/v1/scans/{scan_id}/report?format=html` 返回 `ReportLink`；请求该 link 的相对 `href`
会在同一路径用 `download=true` 只读下载经过摘要校验的附件。下载包含 attachment、digest/ETag、
`nosniff`、`no-store` 和限制性 CSP。GET 不生成报告、不更新 SQLite；A6-2 已将 publisher 接到
Pipeline 首次终态提交边界，前端接线仍属后续纵切。`partial/rules/70` 下载继续明确显示许可证
规则尚未连接，不代表合规通过。

实现侧复现：

```bash
PYTHONPATH=backend python -m pytest -q \
  tests/unit/test_a6_report_exports.py \
  tests/unit/test_a6_report_delivery.py \
  tests/unit/test_a3_fastapi_api.py
```

## A6-2 Pipeline 终态报告发布

`app.reporting.PipelineReportPublisher` 会在 worker 首次写入 `completed` 或 `partial` 终态之前，
显式发布 JSON、HTML、CSV 和资源清单四种格式，再把全部 `ReportLink` 放入同一份终态 `ScanRun`。
默认 `ZipScanRuntime` 已使用同一个私有 `ReportArtifactStore` 完成接线。因此当前 ZIP HTTP 主链即使
因 B5 未到位停在 `partial/rules/70`，也会自动产生可下载、可重启读取的诚实阶段性报告。

SQLite 终态不可变，所以实现不会先落无链接终态再补写。报告文件先于一次终态 CAS 写入，但 API
只承认 SQLite `ScanRun.report_links` 已登记且与 store metadata 精确一致的产物；发布中断或 CAS
冲突留下的未登记文件不可见。报告正文投影掉 `report_links`，避免链接摘要引用自身形成递归哈希；
最终 API `ScanRun` 是链接的权威来源。发布失败会保留已取得的确定性结果，以脱敏
`report_publish_failed` 结束，不让任务永久卡在 running。

实现侧复现：

```bash
PYTHONPATH=backend python -m pytest -q \
  tests/unit/test_a6_pipeline_publish.py \
  tests/unit/test_a6_report_exports.py \
  tests/unit/test_a6_report_delivery.py \
  tests/unit/test_a4_pipeline_worker.py \
  tests/unit/test_a4_local_zip_pipeline.py \
  tests/unit/test_a3_zip_background_scan.py
```

本纵切不实现 B5 许可证规则、不调用 Qwen3、不接前端，也没有把进程内 BackgroundTask 扩展为
持久队列。完整许可证内容仍须消费组员提供的真实 `LicenseExpression`、`Obligation` 与
`RiskFinding`。
