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
├── reports/         # HTML、JSON、CSV、资源清单
├── persistence/     # SQLite 与迁移接口
└── security/        # 限额、路径、防泄漏和清理
```

第一阶段不执行目标仓库代码，也不安装其依赖。

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

## B2 ScanCode 许可证证据

Linux 部署环境可将已固定、已校验的 ScanCode 可执行文件配置为
`OPENGUARD_SCANCODE_BIN`，并运行：

```bash
OPENGUARD_SCANCODE_BIN=/opt/openguard/scancode PYTHONPATH=backend python -m app.cli --scancode-licenses ./demo.zip
```

该模式不执行或安装 ZIP 内代码/依赖。它只把 ScanCode 的许可证候选映射为 pending
`Evidence`，不产生 SPDX、许可证结论或风险；工具只能通过短生命周期目录描述符读取已封存
的 ZIP 树，扫描前后都会校验 inventory。Windows 会明确拒绝该模式，因为没有 POSIX
descriptor 安全能力。

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
