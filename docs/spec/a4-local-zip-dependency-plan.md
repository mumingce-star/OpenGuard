# A4-1 本地 ZIP 依赖流水线接线规格

状态：`FROZEN-FOR-IMPLEMENTATION`

责任：Sol/Root 冻结；Terra 实现；Luna 独立验证；Root 发布

依赖：A2-2 `ReadOnlyScanSession`、B1 Python/JavaScript parser 与 P0 mapper、A3-0 registry、A4-0 worker

## 1. 目标与真人责任边界

A4-1 只实现项目负责人拥有的 Pipeline 集成层：把一个本地 ZIP 文件交给既有 A2 安全摄取，并在同一个生命周期绑定的只读会话内调用既有 B1 Python 与 JavaScript 公共解析/映射接口，最后通过 A4-0 worker 把真实 `Component`、`Evidence` 和 provenance 写入 durable `ScanRun`。

本任务不修改或复制扫描分析组员拥有的 B1-B7 内部逻辑，不实现 ScanCode、Syft、SPDX、许可证规则、模型/数据/API 检测或 Bench，也不进入前端。解析器执行必须受 A2 会话约束，不得直接读取解压目录、执行目标代码、安装依赖或联网。

## 2. 内部工厂接口

实现位于 `backend/app/pipeline/local_zip.py`，并由 `app.pipeline` 导出：

```python
def build_local_zip_dependency_plan(
    archive_path: Path,
    workspace_root: Path,
    *,
    clock: Callable[[], datetime],
) -> PipelinePlan: ...
```

- 参数必须为精确 `Path`、`Path` 和 callable；不接受请求方自定义安全/读取限额。
- 工厂不打开文件、不创建 workspace、不启动线程或 worker；所有副作用只在显式 `ScanPipelineWorker.run()` 后发生。
- 每个 plan 只能用于一次执行；复用时 ingestion 阶段以 `local_zip_plan_reused` 失败，避免闭包中的上一任务结果串入新任务。
- 该工厂不新增 HTTP API；调用方负责先建立一个符合下节前置条件的 queued `ScanRun`。

## 3. queued 输入前置条件

ingestion handler 只接受：

1. `project.source_type=zip`；
2. `project.source` 精确等于 `archive_path.name`，只把逻辑文件名写入 P0，不写本机路径；
3. `project.root_digest` 与 `provenance.inventory_digest` 均为空；
4. components、AI assets、licenses、evidence、obligations、findings、remediations、errors 与 report links 均为空，summary 全为零；
5. `provenance.ai_enabled=false` 且 `ai_model=null`。

不兼容的 queued 任务以 `local_zip_plan_incompatible` 在 ingestion 阶段失败。`provenance.input_digest` 必须是将被摄取 ZIP 原始字节的 SHA-256；流水线用随流读取的 digest 与其比较，不在打开前预读再重开，从而避免把两个不同文件实例当作同一输入。摘要不符以 `input_digest_mismatch` 失败，且不得发布 inventory 或扫描聚合。

本地文件不能打开时使用 `local_zip_unavailable`；A2 拒绝、会话完整性或 cleanup 失败统一使用 `zip_ingestion_failed`。持久错误只包含固定 code/message，不包含绝对路径、文件内容、URL、凭据、底层 reason 或异常文本。

## 4. 生命周期与阶段映射

### 4.1 ingestion

1. 打开 ZIP 二进制流并用 SHA-256 观察每个实际读取字节；
2. 构造 `ZipIngestionService(workspace_root)`；
3. 以固定 `ScanReadLimits(single_file_max_bytes=2 MiB, total_max_bytes=12 MiB)` 调用一次 `ingest_with_consumer()`；该总额覆盖既有 Python 4 MiB 与 JavaScript 8 MiB parser 的组合上限，不允许请求方抬高；
4. consumer 在同一个 `ReadOnlyScanSession` 中依次调用 Python 与 JavaScript parser/mapper。两路分别捕获稳定失败，任一路失败不得阻止另一路获得可用结果；未知异常只转为内部失败标记，不向持久结果泄露；
5. A2 final integrity 与 cleanup 成功、流摘要等于 `provenance.input_digest` 后，更新 `project.root_digest` 和 `provenance.inventory_digest` 为 inventory root SHA-256，并把两路映射结果保存于该 plan 的一次性内存状态。

A2 会在 consumer 返回后立即使 session 失效并清理物化树。因此 parser 的物理执行发生在 ingestion handler 内，而解析结果直到 `scan` 阶段才进入 P0 聚合；这是安全生命周期要求，不表示扫描分析逻辑被复制到 Pipeline。

### 4.2 inventory

只验证 ingestion 已形成同一非空 root/inventory digest 和一次性状态，不重新读 ZIP，不产生虚构 Evidence。

### 4.3 scan

- 合并成功映射得到的 Python/npm components 和 evidence，按 UTF-8 稳定键及 ID 排序；任何重复 ID 仅在对象逐字段相等时去重，否则失败关闭。
- 从 Evidence 的既有 `producer` 生成去重、稳定排序的 `provenance.tool_versions`；不得把 Pipeline 或未执行工具伪造成 producer。
- 重新计算 `ScanSummary`；licenses、obligations、findings、remediations、AI assets 与 report links 保持空。
- parser/mapper 返回 `partial` 时追加固定 recoverable `python_dependency_scan_partial` 或 `javascript_dependency_scan_partial`；单路失败但另一路有可用聚合时追加固定 recoverable `python_dependency_scan_failed` 或 `javascript_dependency_scan_failed`。
- 两路均失败时抛出不可恢复 `dependency_scan_failed`；两路成功但没有任何 component/evidence 时抛出不可恢复 `dependency_manifest_not_found`。不得把“无可用依赖证据”伪装成已完成扫描。

### 4.4 normalize

仅验证当前 components/evidence 可由 P0 `ScanRun` 重载并保持稳定。既有 B1 mapper 已输出 P0 对象，所以本阶段不另建第二套 normalizer，也不改变 B1 结果。

### 4.5 rules、AI 与 report

当前尚无获准的许可证规则 Adapter。`rules` handler 必须显式抛出 recoverable `rules_stage_not_connected`，固定消息为 `License rules are not connected for this scan.`。已有真实 component/evidence 时，A4-0 将终态写为 `partial/rules/70`；`ai_assist` 与 `report` 不得执行。

因此 A4-1 的成功验收终态是“带真实依赖证据的 partial”，不是 completed。只有后续真实规则、AI 降级和报告 Adapter 接入后，才能另立任务解除此门禁。

## 5. 固定公开错误语义

| code | stage | recoverable | 固定含义 |
|---|---|---:|---|
| `local_zip_plan_incompatible` | ingestion | false | queued ScanRun 不满足本计划前置条件 |
| `local_zip_plan_reused` | ingestion | false | 一次性 plan 被再次执行 |
| `local_zip_unavailable` | ingestion | false | 本地 ZIP 不能安全打开 |
| `zip_ingestion_failed` | ingestion | false | A2 摄取、完整性或 cleanup 失败 |
| `input_digest_mismatch` | ingestion | false | 实际流 SHA-256 与 provenance 不符 |
| `python_dependency_scan_partial` | scan | true | Python parser 返回部分结果 |
| `javascript_dependency_scan_partial` | scan | true | JavaScript parser 返回部分结果 |
| `python_dependency_scan_failed` | scan | true | Python 路失败但另一语言有可用聚合 |
| `javascript_dependency_scan_failed` | scan | true | JavaScript 路失败但另一语言有可用聚合 |
| `dependency_scan_failed` | scan | false | 两路均失败 |
| `dependency_manifest_not_found` | scan | false | 两路均无可发布的 component/evidence |
| `rules_stage_not_connected` | rules | true | 真实许可证规则尚未接线 |

scan handler 追加的 recoverable error 必须定位 `stage=scan`；rules 失败由 A4-0 定位 `stage=rules`。不得复制 B1 diagnostic 原文到 `ScanError.message`。

## 6. 冻结验收用例

### 正向

- `POS-A4ZIP-001`：包含 Python 与 npm 声明的真实 ZIP 经一次 A2 会话产生两种 ecosystem 的 P0 components/evidence，最终为 `partial/rules/70`。
- `POS-A4ZIP-002`：仅 Python 或仅 JavaScript 声明仍发布该路结果，并诚实停在 rules partial。
- `POS-A4ZIP-003`：一条语言 partial 或失败、另一条有可用聚合时，结果和固定 recoverable scan error 同时持久化。
- `POS-A4ZIP-004`：root/input/inventory digest、producer/tool_versions、summary、排序与 SQLite 重开后一致。
- `POS-A4ZIP-005`：成功与拒绝路径均不留下 task workspace；解析期间不联网、不执行或安装目标项目代码。

### 负向

- `NEG-A4ZIP-001`：非 ZIP source、逻辑文件名不匹配、已有 root/inventory/聚合、AI enabled 的 queued 任务失败关闭。
- `NEG-A4ZIP-002`：不存在、不可读或非 ZIP 文件形成固定 ingestion 错误，持久结果不含本机路径或底层异常。
- `NEG-A4ZIP-003`：实际 ZIP 流摘要不符时失败，且不持久化 root、inventory、component 或 evidence。
- `NEG-A4ZIP-004`：A2 的路径、链接、压缩、配额、完整性或 cleanup 拒绝仍失败关闭并清理。
- `NEG-A4ZIP-005`：两路 parser/mapper 都失败时为 `failed/scan/35`，不进入 normalize/rules。
- `NEG-A4ZIP-006`：一条语言抛出含路径、URL 或 secret 的未知异常时，另一条可用结果可保留，但 durable error 不泄露原文。
- `NEG-A4ZIP-007`：无 manifest/无依赖的 ZIP 不生成虚构 Evidence 或 completed，使用固定失败语义。
- `NEG-A4ZIP-008`：重复但不相等的 component/evidence ID、非法 mapper 对象或无效 P0 引用失败关闭。
- `NEG-A4ZIP-009`：同一 plan 第二次使用时不读取 ZIP、不调用 parser，稳定失败为 `local_zip_plan_reused`。
- `NEG-A4ZIP-010`：rules 阶段前不得出现 license/finding/AI/report；rules 失败后 AI/report handler 不执行，终态不得为 completed。

## 7. 发布声明

A4-1 evidence 只能表述为：“本机受控测试环境下，本地 ZIP 经既有 A2 安全只读会话调用既有 B1 Python/JavaScript 声明解析，真实 P0 依赖证据由 A4/A3 持久化，并因许可证规则未接线而诚实返回 partial。”

不得据此宣称完整依赖求解、许可证识别、合规结论、公开 Git 输入、Web 自动扫描、AI 解释、报告导出、Linux/TrustedEgress、Bench 或完整参赛作品已经完成。

## 8. 实现验证与候选证据（2026-09-03）

- 候选 evidence：`EVD-A4-LOCAL-ZIP-DEPENDENCY-PIPELINE-001`。
- 当前裁决：`APPROVED-PENDING-ROOT-BINDING`；等待不可变实现提交哈希与远端分支核对后升级为 `APPROVED`。
- 实现侧：`tests/unit/test_a4_local_zip_pipeline.py` 共 29 项通过。
- 独立侧：`tests/security/test_a4_local_zip_pipeline_independent.py` 共 20 项通过；与实现侧合计 49 项通过。
- 完整集合：沙箱内 643 项通过，唯一真实回环端口项因 bind 权限受限；在获准的本机回环环境补跑该项 1 项通过，因此当前完整集合等价 644 项通过。
- 静态门禁：P0 Schema 导出等值、compileall、diff、受保护路径、目录权限、敏感信息与上传范围检查通过；没有开放 P0/P1/P2 实现缺陷。
- 运行 profile：macOS/POSIX、CPython 3.12.13、SQLite 3.53.1、单进程显式调用、预创建私有 workspace root、真实 A2 只读会话与既有 B1 Python/JavaScript 公共 parser/mapper。
- 证据边界：只证明本地 ZIP 声明依赖接线、P0 持久化和 rules 缺失时的诚实 partial；不证明许可证合规、HTTP 自动消费、Git 网络输入、AI、报告、Linux 隔离或完整作品。
