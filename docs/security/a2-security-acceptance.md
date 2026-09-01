# A2 Git/ZIP 安全输入验收门禁

状态：`CONDITIONAL_FROZEN_DESIGN_BASELINE`

版本：`0.1`

冻结日期：2026-09-02

适用范围：Terra 的 A2 安全获取与 inventory 实现、Luna 的安全负面测试、Root 的任务验收。

> 本文全部参数是**条件性设计默认值，尚未实现、尚未经过真实仓库可用性和负面测试验证**。参数只能由服务端管理员配置，请求方不能放宽；超过硬上限时启动失败或任务失败关闭。Terra 的工程审查与 Luna 的可测性审计均已完成，但真实 `TrustedEgress`、Linux 安全运行 profile、依赖台账和全量测试证据仍未形成，因此本文不是 A2 已完成或安全控制已生效的证明。

## 1. 契约不变性

- 保持 `docs/spec/p0-domain-contract.md` v0.1.1 的对象、枚举、六个 API 路径、状态机和错误包络；
- 不新增 `Resource/Risk/ScanResult` 平行模型，不改变 `Project.source_type/source/revision/root_digest`；
- Git 创建请求仍为 JSON，ZIP 仍为 multipart；P0 不增加私有仓库 OAuth；
- 使用现有顶层错误码和 `details` 对象；本文定义的 `details.reason` 值不要求新增字段；
- A2 实现如发现必须新增公共字段，先提交文末变更请求，不得直接修改 Schema/API。

## 2. 设计默认值与硬上限

所有 byte 数使用二进制单位；实现必须同时检查声明值和实际消耗值。

| 配置键 | 设计默认值 | 可配置范围/硬上限 | 理由 |
|---|---:|---:|---|
| `git_redirects_max` | 0 | 0-5 | 直接 Git 模式禁止自动重定向；只有满足 `SEC-A2-004` 的 `TrustedEgress` 已实现并通过集成测试时，管理员才可调高。 |
| `git_connect_timeout_s` | 10 | 3-30 | 避免不可达地址长期占用 worker。 |
| `git_total_timeout_s` | 120 | 30-600 | 对学生项目较宽松，同时限制慢服务/巨型 pack。 |
| `ingestion_total_timeout_s` | 180 | 60-900 | 覆盖获取、物化、inventory 和清理；与后续扫描器超时分开。 |
| `git_transfer_max_bytes` | 256 MiB | 16 MiB-1 GiB | 由 `TrustedEgress` 按每任务保守隧道字节硬截断；浅克隆仍可能含大对象。 |
| `git_materialized_max_bytes` | 512 MiB | 64 MiB-2 GiB | 给常见前端/模型配置仓库留余量，不允许无界工作树。 |
| `git_file_count_max` | 50,000 | 1,000-100,000 | 兼顾中型仓库与 inode/遍历成本。 |
| `zip_upload_max_bytes` | 64 MiB | 8 MiB-256 MiB | 在 API 流式接收阶段先限制上传占用。 |
| `zip_uncompressed_max_bytes` | 256 MiB | 32 MiB-1 GiB | 控制解压磁盘和后续哈希成本。 |
| `zip_entry_count_max` | 20,000 | 100-100,000 | 覆盖常见源码包，限制 tiny-file 炸弹。 |
| `single_file_max_bytes` | 32 MiB | 1 MiB-128 MiB | P0 静态元数据扫描无需处理巨型媒体/权重；超限整项拒绝而非静默遗漏。 |
| `zip_expansion_ratio_max` | 100:1 | 10:1-200:1 | 对高压缩文本仍有余量，拦截典型压缩炸弹；同时检查总量。 |
| `path_depth_max` | 32 | 8-64 | 限制深层目录和平台路径处理开销。 |
| `path_utf8_bytes_max` | 1,024 | 256-4,096 | 在不依赖宿主 PATH_MAX 的情况下限制异常路径；每个分段还须满足文件系统约束。 |
| `worker_cpu_cores` | 2 | 0.5-4 | 比赛单机的安全/可用性折中。 |
| `worker_memory_max_mib` | 1,024 | 256-2,048 | 容纳扫描器但避免单任务耗尽宿主。 |
| `worker_temp_disk_max_mib` | 1,024 | 128-4,096 | 覆盖上传、解压、只读扫描副本和工具临时文件。 |
| `worker_processes_max` | 64 | 16-128 | 阻止 fork/process 炸弹，即使目标代码原则上不执行。 |
| `worker_fds_max` | 256 | 64-1,024 | 限制文件描述符耗尽。 |
| `concurrent_ingestions_per_worker` | 2 | 1-4 | 控制单机峰值；全局并发另由部署配置。 |
| `cleanup_retry_max` | 3 | 1-5 | 处理短暂占用，同时避免无限重试。 |
| `orphan_temp_ttl_hours` | 6 | 1-24 | 启动/周期清道夫的兜底，不替代每任务立即清理。 |

`worker_*` 必须由容器/cgroup/进程限制和应用计数共同落实；仅在 Python 中比较计数不能通过安全验收。限额提高不得超过硬上限；若真实公开仓库评估显示默认值不合适，Terra 提交测量证据，由 Sol 调整设计、Luna 更新边界测试。

## 3. 冻结验收 ID

### `SEC-A2-001` - Git 仅允许公开 HTTPS

创建 Git 扫描时必须：

- 只接受 `https` scheme，URL 最长 2,048 UTF-8 bytes；
- host 必须是可规范化的 DNS 名称，拒绝空 host、`localhost`、IP literal、混淆/无效 IDNA；
- 只允许默认端口或显式 443；拒绝 userinfo、query、fragment、控制字符和二次解码后出现的凭据/分隔符；
- 拒绝 `http`、`ssh`、`git`、`file`、`ftp`、`data`、`ext` 及 Git scp-like 语法；
- 日志不得记录原始拒绝 URL。

失败：`invalid_source`。

### `SEC-A2-002` - URL 凭据与请求数据最小化

- `user:pass@host`、token query/fragment、换行和控制字符一律在网络请求前拒绝；
- 客户端不能设置代理、证书路径、Git 配置、额外 header、refspec、clone 参数或限额；
- `Project.source` 只保存通过验证的规范化公开 HTTPS URL；日志只保存 host、URL SHA-256、`scan_id` 和阶段。

失败：`invalid_source`；不得在错误消息回显敏感片段。

### `SEC-A2-003` - 公网地址判定

初始连接前解析全部 A/AAAA，并对 IPv4、IPv6、IPv4-mapped IPv6 统一分类。若任一结果为下列地址，整次解析失败关闭：

- unspecified、loopback、private、link-local、multicast、reserved、documentation/test、benchmark、carrier-grade NAT；
- IPv6 unique-local、site-local、zone-scoped 或其他非全局单播；
- 云元数据/平台专用地址，即使语言标准库误判为 global；
- 混合公网与非公网结果。

只检查字符串或只检查第一个 IP 不能通过。失败：`invalid_source`，`details.reason=source_address_not_public`。

### `SEC-A2-004` - 重定向、DNS 重绑定与 TLS

- 直接 Git 模式的 `git_redirects_max=0`，必须关闭 Git/libcurl 自动重定向；任何重定向均拒绝；
- 只有 `TrustedEgress` 能为每次连接记录原始 host、全部解析地址、实际拨号 IP 和 TLS server name，并通过真实代理集成测试证明逐跳复核、立即拨号与端到端 TLS 主机校验时，管理员才可将 `git_redirects_max` 配置为 1-5；
- 允许重定向时，每跳均重新执行 `SEC-A2-001` 至 `003`，并生成上述连接证据；
- 禁止 HTTPS 降级、相对跳转绕过、凭据传播到新 host 和超限/循环重定向；
- 每次实际连接前再次解析并复核；连接必须固定到已复核 IP，同时以规范化 host 做 TLS SNI/证书校验；
- egress 层必须拒绝所有非公网目的地址，作为 DNS 竞态的第二道控制；
- 若 Git 客户端无法证明每跳验证和连接固定，必须关闭自动重定向并由受控获取层处理。

失败：`invalid_source`；原因分别为 `source_redirect_not_allowed` 或 `source_dns_rebinding_detected`。

### `SEC-A2-005` - Git 进程与配置隔离

Git 获取必须使用锁定的绝对二进制和参数数组，默认分支浅克隆；结果上等价于：

- depth 1、single branch、no tags、no recursive submodules；
- 不执行 hook，不使用用户/系统 Git 配置、credential helper、template、filter、LFS smudge、fsmonitor 或外部 diff；
- 禁止 `file`/`ext` 及所有非 HTTPS 传输，禁用终端凭据提示；
- 使用每任务隔离 `HOME`/config/cwd 和受控环境；忽略请求或仓库提供的代理/配置；
- 不接受用户提供的 branch/ref/额外参数；仓库 `.gitmodules` 和 `.gitattributes` 只能作为不可信文件证据，不触发获取/过滤器。

验收以行为测试和实际进程参数/环境的脱敏记录为准，不以注释或单一 Git flag 为准。

### `SEC-A2-006` - Git 工作树条目安全

- checkout 后用 `lstat`/安全目录遍历，不跟随任何链接；
- P0 对 symlink、gitlink/submodule、hardlink 语义、device、FIFO、socket 和其他非普通目录/文件失败关闭；
- 拒绝绝对/父级路径、NUL/控制字符、Unicode NFC 或 case-fold 后碰撞、文件/目录同名冲突；
- 普通文件的 executable bit 可作为元数据存在，但必须在扫描副本中清除且永不执行；
- `.git` 目录不交给扫描器，只保留规范化 commit hash 作为 `Project.revision`。

失败：`invalid_source`，`details.reason=git_entry_unsafe`。这是 P0 的安全/可用性取舍，Terra 不得自行改为跟随安全链接。

### `SEC-A2-007` - Git 资源与时间限制

- 在网络流、pack/object 存储、物化工作树和 inventory 阶段持续计数；
- 施加表中 transfer、materialized、file count、single file、Git timeout、ingestion timeout、worker limits；
- `git_transfer_max_bytes` 必须由 `TrustedEgress` 对每任务上下行隧道字节做保守累计并在超限时断开；应用层的 materialized bytes、staging disk 和 wall-clock 是相互独立的纵深防线，不能替代或证明 transfer quota；
- 超限或超时立即终止完整进程组，等待退出，关闭文件描述符并执行 `SEC-A2-016`；
- 不能通过压缩/稀疏文件/硬链接让“表面大小”小于实际占用；磁盘配额是最终兜底。

失败：超时使用 `scanner_timeout`；资源超限使用 `scanner_failed`，细分原因 `git_fetch_limit_exceeded` 或 `ingestion_resource_exhausted`。

### `SEC-A2-008` - ZIP 识别、结构和完整性

- 文件扩展名/MIME 不可信；按 ZIP signature、EOCD/central directory 和本地 header 交叉验证；
- 拒绝非 ZIP、截断、多卷、加密、未知/未支持压缩算法、矛盾 size/offset、重叠结构和损坏条目；
- ZIP64 可在全部 A2 限额内使用，不能绕过 32-bit/64-bit 计数；
- 每个文件在流式读取末尾验证 CRC 和实际未压缩字节数。

失败：`invalid_archive`；加密为 `archive_encrypted`，损坏为 `archive_integrity_failed`。

### `SEC-A2-009` - ZIP 路径规范化

每项写盘前必须在内存中完成：

1. 拒绝 NUL、ASCII 控制字符、反斜杠、空路径、绝对路径、`~`、Windows drive/UNC/device path；
2. 按 `/` 分段并 Unicode NFC；拒绝空、`.`、`..` 分段；
3. 检查 UTF-8 bytes、单分段平台约束和深度；
4. 计算规范路径、NFC+case-fold 键和父目录类型；任一重复/碰撞/文件目录冲突即拒绝；
5. 安全 join 后再次证明目标位于本任务 root 内；字符串前缀比较不足以通过。

失败：`invalid_archive`，原因 `archive_path_unsafe` 或 `archive_duplicate_path`。

### `SEC-A2-010` - ZIP 条目类型

- 仅接受普通目录和普通文件；已知 Unix mode、DOS/reparse 或其他 external attributes 表示符号链接、硬链接语义、device、FIFO、socket 等特殊类型时必须拒绝；
- 文件条目的 external attributes 为零、缺失或无法判定类型时，只能把经核验的解压字节流新建为普通文件；不得因此恢复或推导链接、owner、ACL、xattr、权限或 executable bit。明确的安全目录条目可创建普通目录；
- 实现不得复现归档中的 owner、group、setuid/setgid/sticky、ACL、xattr 或 executable bit；
- 即使元数据无法可靠识别硬链接，也只按新建普通文件流式写入，绝不调用链接创建 API。

失败：`invalid_archive`，`details.reason=archive_entry_type_unsafe`。

### `SEC-A2-011` - ZIP 配额与压缩炸弹

在 central directory 预检和实际流式解压两阶段均执行：

- 上传 64 MiB、总解压 256 MiB、单文件 32 MiB、20,000 条目；
- 每项和整体实际扩展比不超过 100:1；压缩 size 为 0 且非空时按超限处理；
- 深度 32、路径 1,024 UTF-8 bytes；目录也计入条目数；
- 任一项超限拒绝整个 ZIP，不静默跳过、不产生部分 inventory。

失败：`archive_limit_exceeded`，`details.reason` 为 `archive_upload_size_limit`、`archive_total_size_limit`、`archive_single_file_limit`、`archive_entry_count_limit`、`archive_ratio_limit`、`archive_path_depth_limit` 或 `archive_path_length_limit`。

### `SEC-A2-012` - 安全流式解压

- 为每个任务创建不可预测、权限 0700、从不复用的新目录；
- 不使用通用 `extract`/`extractall`；从已验证 root directory descriptor 逐级安全创建目录/文件，禁止跟随链接，文件以独占新建打开；
- 以固定小块流式复制，并对总量、单文件、比率、磁盘和时间实时计数；失败删除整个任务树；
- 普通文件模式固定为 0600/0644，目录 0700；mtime 等仅作不可信元数据，不影响逻辑；
- 嵌套 ZIP/tar 作为普通文件，不递归解压；后续扫描器也必须关闭递归归档展开。

### `SEC-A2-013` - 不可变 inventory 与摘要

- 获取/解压结束后再次从 root descriptor 进行 `lstat` 遍历，确认只有普通目录/文件且未发生碰撞；
- 生成稳定排序的相对 POSIX 路径、实际 size、非执行模式和每文件 SHA-256；根摘要由规范化 inventory 计算；
- `root_digest` 的 v1 规范输入为 UTF-8 字节：先写固定头 `openguard-inventory-v1\n`，再按路径 UTF-8 bytes 升序为每个普通文件写入 `path\0size_decimal\0sha256_hex\n`，最后对完整字节串取 SHA-256；目录、mtime、临时绝对路径和 `.git` 不进入摘要；
- Git `revision` 从已物化的 `HEAD` 读取并规范化为小写完整对象 ID（SHA-1 仓库为 40 hex，SHA-256 仓库为 64 hex），不得使用用户输入或含糊分支名代替；
- inventory 完成后输入树改为只读，扫描器使用只读挂载/副本；若内容、size、inode 类型或摘要在扫描前变化，任务失败；
- `Project.revision` 保存 Git commit hash；`root_digest` 保存 SHA-256；API/证据不暴露临时绝对路径。

### `SEC-A2-014` - 禁止执行与命令注入

- 不运行、构建、测试、import、eval、安装或启动目标项目，不调用其 Makefile、package scripts、setup hook、容器、宏或插件；
- 外部进程必须使用参数数组，禁止 shell、字符串拼接、`eval`、命令替换和环境变量展开；
- 不可信值不能作为选项；工具支持时使用 `--`，否则扫描固定 staging root/文件描述符而不是将原文件名拼入命令；
- 固定可执行文件路径、允许参数、环境、cwd、umask 和编码；清除可能改变加载/执行行为的变量；
- 文件名含 `--help`、`;`、换行、反引号、`$()` 等时仍只能作为数据，且日志需转义控制字符。

### `SEC-A2-015` - 扫描器隔离与网络策略

- A2 安全完成证据必须来自项目声明支持的 Linux container profile：non-root、每任务进程/容器、只读输入、独立可写 temp、无宿主目录挂载、cgroup v2 资源限制和默认 deny-egress；macOS 只允许开发级单元/有限集成验证，不能替代该 profile 的安全证据；
- 后续 ScanCode、Syft 和自研解析器接入时必须复用同一 sandbox contract；它们未在 A2 实际引入前不得被表述为已隔离或已验证；
- 默认无任何网络；只有 Git 获取器能通过 `SEC-A2-003/004` 的受控 egress；
- 落实 CPU、memory、disk、process、fd 和 wall-clock 上限，超限终止进程组；
- 禁止递归归档、动态插件、目标仓库配置和自动下载数据库/规则；规则/数据库在构建时锁定；
- 不允许扫描器写入输入树或读取其他任务目录、服务配置和宿主凭据。

### `SEC-A2-016` - 临时目录生命周期

- 成功、拒绝、失败、超时、取消和正常异常均在父调度器 `finally` 中关闭句柄并清理 Git/ZIP、扫描副本和工具 temp；
- inventory 完成后的输入可仅在同一 `ScanRun` 最后一个只读消费者结束前保留；不得跨运行长期保存或被其他任务复用；“成功清理”指完整 ScanRun 结束后的清理，不得在下游扫描器使用前提前删除；
- 先终止并回收完整进程组，再清理；重试不超过 `cleanup_retry_max`；
- 清理失败时隔离目录、记录不含路径/内容的安全告警、把 worker 标为不可复用，并由清道夫重试；
- worker 启动时及周期性删除超过 `orphan_temp_ttl_hours` 的本命名空间孤儿目录；不得扫描或删除不属于 OpenGuard 的目录；
- 测试覆盖 success/failure/timeout/cancel/forced-worker-restart；不声称取证级安全擦除。

### `SEC-A2-017` - 日志、错误和证据脱敏

- 默认不记录 ZIP body、文件内容、完整 URL、Git 输出、命令行、环境、堆栈或绝对路径；
- 允许记录：`request_id`/`scan_id`、阶段、稳定错误码、host、URL/输入摘要、计数、时长和工具版本；
- 对路径/文本先去控制字符、限制长度并按凭据/私钥/token/连接串/个人信息模式脱敏；检测命中时不保存原值；
- `Evidence.excerpt` 仍遵守 1,000 字符最小必要、脱敏和权利边界；不因调试绕过；
- HTTP/`ScanError.message` 为固定通用文案，不包含堆栈、绝对路径、IP 解析结果、凭据或完整第三方内容。

### `SEC-A2-018` - 扫描器供应链

- A2 只验收本任务实际引入的 Git 二进制、ZIP/preflight 库、基础运行镜像和安全依赖：锁定精确版本/镜像 digest/官方来源，有官方 checksum/signature 时核验并记录；
- ScanCode、Syft 和规则数据属于 B2/B3/后续规则任务；实际引入时再按本条锁版、登记、核验和回归，未引入时状态必须为 `planned`，不得借 A2 供应链门禁标为已验证；
- 镜像按 digest 固定；依赖/镜像/数据不在扫描时自动更新；
- 首次引入和每次升级更新 `third_party/` 台账、SBOM、许可证/NOTICE 和变更审查；
- 升级先跑 A1 全回归、全部 `NEG-A2-*`、畸形输入和固定结果差异，再进入发布；
- 不把“来自公开 GitHub/包仓库”当作完整性证明。

### `SEC-A2-019` - 错误、状态与失败关闭

- 在返回 `202` 前发现的 URL/ZIP 拒绝使用非 2xx 错误包络；异步 Git/ZIP 后续失败进入 `ScanRun.status=failed` 并至少含一条脱敏 `ScanError`；
- 输入安全策略失败、配额超限、路径/链接、SSRF 和完整性失败**不得**返回 `completed` 或 `partial`；
- `partial` 只允许 inventory 已成功、至少一个可用结果已形成，而后续必需扫描器/报告阶段发生可恢复失败；必须有 `recoverable=true` 的 `ScanError`；
- 基础设施/用户中止使用现有 `cancelled` 状态并执行清理；本文不新增取消 API；
- 未知或未分类的异常使用 `internal_error`，外部通用文案，内部安全日志保留 request/scan ID 而非原始内容。

### `SEC-A2-020` - 配置与并发治理

- 全部安全配置仅从管理员受控配置读取，启动时校验范围；请求不能覆盖；
- 实际生效配置的规范化 SHA-256 写入 ingestion `ProducerRef.config_digest`，不把配置正文写入结果；
- 每 worker 并发可由本进程 semaphore 管理；全局并发、跨 worker/重启的相同幂等键归一和任务所有权必须依赖 durable task registry，不能由内存状态宣称；
- 若 A2 不引入 durable task registry，则跨 worker/重启幂等明确转为 A3 前置条件：A2 只声明单 worker/单进程范围内的资源控制，不把 `POS-A2-003` 用作跨 worker/重启完成证据；
- 配置低于最小安全值或高于硬上限时服务启动失败；不能静默截断为另一个值；
- 限额变化必须更新本文版本、AI 辅助记录、负面边界和真实仓库可用性报告。

## 4. 错误码与细分原因

HTTP 仍使用 v0.1.1 的 `{error:{code,message,request_id,details}}`。`details.reason` 是可测试的稳定机器值，不含用户输入。

| 条件 | HTTP/ScanError `code` | `details.reason` 示例 | 任务状态 |
|---|---|---|---|
| Git scheme/host/端口/凭据/URL 形态拒绝 | `invalid_source` | `source_scheme_not_allowed`、`source_credentials_forbidden`、`source_host_invalid` | 同步拒绝或 `failed` |
| 非公网地址、重定向或 DNS 重绑定 | `invalid_source` | `source_address_not_public`、`source_redirect_not_allowed`、`source_dns_rebinding_detected` | 同步拒绝或 `failed` |
| Git 不安全树条目 | `invalid_source` | `git_entry_unsafe` | `failed` |
| 非 ZIP、畸形、加密、路径/类型/碰撞/CRC | `invalid_archive` | `archive_not_zip`、`archive_encrypted`、`archive_path_unsafe`、`archive_entry_type_unsafe`、`archive_duplicate_path`、`archive_integrity_failed` | 同步拒绝或 `failed` |
| ZIP 数量/大小/比率/深度/路径超限 | `archive_limit_exceeded` | `archive_*_limit` | 同步拒绝或 `failed` |
| Git/ingestion 超时 | `scanner_timeout` | `ingestion_timeout` | `failed`；仅下游可恢复超时可 `partial` |
| Git/扫描器资源或隔离失败 | `scanner_failed` | `git_fetch_limit_exceeded`、`ingestion_resource_exhausted`、`scanner_sandbox_violation` | `failed`；仅下游可恢复失败可 `partial` |
| 未分类实现故障 | `internal_error` | 不对外披露内部原因 | `failed` |

异步 `ScanError` 当前没有 `reason` 字段：A2 先使用冻结的 `code` 和固定脱敏 `message`。若 UI 必须显示细分原因，按 `CR-A2-001` 走 v0.1.2 变更评审，不能把 `details.reason` 擅自加入 `ScanError`。

## 5. 正向验收

| 测试 ID | 输入 | 期望 |
|---|---|---|
| `POS-A2-001` | 公网 HTTPS、小型、无链接/子模块、限额内 Git 仓库 | 成功固定 commit；inventory 稳定；`root_digest` 可重算；未执行 hook/filter/脚本。 |
| `POS-A2-002` | 限额内、仅普通文件/目录、UTF-8 安全路径的 ZIP；含 external attributes 为零/未知的普通文件 | 成功；零/未知属性项只生成普通文件字节流，不恢复元数据；每文件/根 SHA-256 可重算；无绝对路径；原 ZIP 和 temp 按生命周期清理。 |
| `POS-A2-003` | 同一安全输入和幂等键重复提交 | 若 A2 引入 durable task registry，须跨 worker/重启返回或关联同一任务；若未引入，本测试转为 A3 前置且 A2 不宣称跨 worker/重启幂等。 |
| `POS-A2-004` | 文件名含空格、非 ASCII 和普通标点 | 作为数据处理，规范路径稳定，不进入命令/日志注入。 |
| `POS-A2-005` | Git/ZIP 完成后重算 inventory | 路径、size、文件哈希、根摘要稳定排序且一致。 |

## 6. 负面测试矩阵

Luna 必须以合成输入或本地受控 DNS/HTTPS 服务测试，不访问真实内网/元数据端点。

| 测试 ID | 覆盖 ID | 攻击输入 | 期望结果 |
|---|---|---|---|
| `NEG-A2-001` | `SEC-A2-001` | `http`/`ssh`/`git`/`file`/`ext`/scp-like URL | `invalid_source`; 网络与进程均未启动。 |
| `NEG-A2-002` | `SEC-A2-001`,`002` | userinfo、token query/fragment、CRLF、双编码分隔符 | 拒绝；响应/日志不含原始秘密。 |
| `NEG-A2-003` | `SEC-A2-001` | IP literal、非 443 端口、无效/混淆 IDNA | `invalid_source`。 |
| `NEG-A2-004` | `SEC-A2-003` | 127.0.0.1、0.0.0.0、私网、链路本地、保留 IPv4 | `source_address_not_public`；无连接。 |
| `NEG-A2-005` | `SEC-A2-003` | `::1`、ULA、link-local、IPv4-mapped private、混合 public/private DNS | 整组拒绝；不只选择公网地址继续。 |
| `NEG-A2-006` | `SEC-A2-004` | 公网首跳重定向到私网/HTTP/带凭据 URL | 每跳拒绝；凭据不转发。 |
| `NEG-A2-007` | `SEC-A2-004` | DNS 首次公网、连接前改为私网 | `source_dns_rebinding_detected` 或 egress 阻断；无私网连接。 |
| `NEG-A2-008` | `SEC-A2-004` | 直接 Git 模式发生任一重定向；或 TrustedEgress 模式发生循环/超过有效配置 | `source_redirect_not_allowed`，进程/临时目录清理。 |
| `NEG-A2-009` | `SEC-A2-005` | 仓库声明 submodule、LFS filter、恶意 `.gitattributes`/`.gitmodules` | 不递归、不执行/下载；按树策略拒绝 gitlink。 |
| `NEG-A2-010` | `SEC-A2-005`,`014` | 系统/global Git config 中 credential helper、hook/template、filter、proxy | 隔离后均不调用；测试替身无调用记录。 |
| `NEG-A2-011` | `SEC-A2-006` | Git symlink 指向 root 外、绝对路径、循环链接 | `git_entry_unsafe`；未读取 target。 |
| `NEG-A2-012` | `SEC-A2-006` | Git case-fold/Unicode 路径碰撞、特殊文件 | 拒绝且不覆盖任何文件。 |
| `NEG-A2-013` | `SEC-A2-007`,`020` | 超大/慢 Git、超文件数、超单文件、磁盘配额 | 对应 timeout/resource 错误，进程组终止并清理。 |
| `NEG-A2-014` | `SEC-A2-008` | 非 ZIP、截断、伪 central directory、多卷、加密 ZIP | `invalid_archive`；无落盘或残留。 |
| `NEG-A2-015` | `SEC-A2-008` | local header/central directory size 不一致、CRC 错 | `archive_integrity_failed`；整个输入失败。 |
| `NEG-A2-016` | `SEC-A2-009` | `../x`、`a/../../x`、`/abs`、`C:/x`、UNC/device path | `archive_path_unsafe`；root 外无创建。 |
| `NEG-A2-017` | `SEC-A2-009` | 反斜杠、NUL、控制字符、`.`/空分段、超深/超长路径 | 对应 invalid/limit error；不落盘。 |
| `NEG-A2-018` | `SEC-A2-009`,`010` | NFC/case-fold 重名、重复条目、文件/目录冲突 | `archive_duplicate_path`；不采用“最后覆盖”。 |
| `NEG-A2-019` | `SEC-A2-010` | ZIP symlink、hardlink 元数据、device/FIFO/socket、setuid | `archive_entry_type_unsafe`；不创建链接/设备。 |
| `NEG-A2-020` | `SEC-A2-011` | 上传体积、总解压、单文件、条目数分别刚超默认值 | `archive_limit_exceeded` 和精确 `archive_*_limit`。 |
| `NEG-A2-021` | `SEC-A2-011` | 单项/整体 100:1 边界内与边界外、声明 0 压缩大小非空 | 边界内可继续，边界外 `archive_ratio_limit`；实际计数一致。 |
| `NEG-A2-022` | `SEC-A2-012` | ZIP 内嵌 ZIP/tar 炸弹 | 只作为普通文件；不递归展开。 |
| `NEG-A2-023` | `SEC-A2-012`,`013` | 解压期间尝试用竞态替换父目录为 symlink | 安全 fd/open flags 阻止；root 外无写入。 |
| `NEG-A2-024` | `SEC-A2-013` | inventory 后修改/替换文件 | 摘要/类型变化导致失败；不扫描变更内容。 |
| `NEG-A2-025` | `SEC-A2-014` | 文件名 `--help;$(touch x)`、换行、反引号、shell 元字符 | 无 shell/命令副作用；仅作为数据；日志转义。 |
| `NEG-A2-026` | `SEC-A2-014`,`015` | manifest 含 install/build/test scripts 和外部 URL | 不执行、不安装、不联网；仅静态读取最小字段。 |
| `NEG-A2-027` | `SEC-A2-015` | 扫描器尝试写输入、访问网络、读其他任务/环境文件 | sandbox 阻断并记录 `scanner_sandbox_violation`。 |
| `NEG-A2-028` | `SEC-A2-015`,`020` | CPU、内存、进程、fd、wall-clock 分别超限 | 进程组终止；状态/错误正确；worker 可控。 |
| `NEG-A2-029` | `SEC-A2-016` | success、validation fail、timeout、cancel、异常各路径 | 任务目录均立即消失；清理失败则隔离且 worker 不复用。 |
| `NEG-A2-030` | `SEC-A2-016` | 模拟 worker 强退并重启 | 清道夫只删除本命名空间过期孤儿目录，不触碰其他目录。 |
| `NEG-A2-031` | `SEC-A2-017` | URL/文件/manifest 含 token、私钥、密码、连接串、绝对路径 | API、日志、错误、证据无原值/路径/堆栈；只见稳定 ID/摘要。 |
| `NEG-A2-032` | `SEC-A2-017` | 文件名含 ANSI/CRLF/HTML/CSV 公式前缀 | 日志不可伪造；A2 输出保留安全数据边界；A6/F0 门禁项被触发。 |
| `NEG-A2-033` | `SEC-A2-018` | 改动 A2 实际 Git/ZIP/安全依赖或基础镜像摘要，或运行时请求自动更新 | 构建/启动失败；不得静默拉取新版本；未来扫描器/规则只在实际引入后纳入。 |
| `NEG-A2-034` | `SEC-A2-019` | 任一输入安全拒绝 | 不得为 `partial/completed`；同步非2xx或异步 `failed`+ScanError。 |
| `NEG-A2-035` | `SEC-A2-019` | inventory 成功、后续必需扫描器可恢复超时 | 可为 `partial`，但至少一条 `recoverable=true` 的脱敏 `ScanError`。 |
| `NEG-A2-036` | `SEC-A2-020` | 请求尝试提高限额；配置越过硬上限/低于安全下限 | 请求字段被拒绝；非法服务配置导致启动失败。 |

每个测试必须记录：测试 ID、fixture 来源/授权、代码提交、Git/ZIP/扫描器版本、有效配置摘要、命令、期望、实际结果、运行时、复核人和脱敏状态。不能仅用 mock 证明文件系统、网络或进程隔离；关键边界至少有一层真实集成测试。

## 7. 验收完成定义

A2 只有同时满足以下条件才能 `COMPLETE`：

1. `SEC-A2-001` 至 `020` 全部在代码中有可定位实现；
2. `POS-A2-001`、`002`、`004`、`005` 和 `NEG-A2-001` 至 `036` 全部通过，边界值包含等于/刚超过；`POS-A2-003` 若 A2 引入 durable task registry 则必须通过，否则须在验收记录中转为 A3 前置且不得计作 A2 完成证据；
3. A1 全量回归仍通过，存储 Schema 等于模型导出，sample v0.1.1 仍有效；
4. Git/ZIP 到 inventory 的固定样例可重复得到相同 revision/root digest；
5. success/failure/timeout/cancel/restart 清理，以及只读输入、cgroup v2、non-root、跨任务隔离和默认 deny-egress，均在受支持 Linux container profile 中由独立集成检查证明；macOS 结果只作开发证据；
6. A2 实际引入的 Git/ZIP/基础镜像与安全依赖已锁版并登记来源/许可/摘要；未来 ScanCode/Syft/规则保持 `planned`，在各自任务引入后独立验收；
7. `git diff --check`、敏感信息、本机绝对路径、缓存/临时文件和待提交文件清单检查通过；
8. Terra 提交可实现性说明，Luna 提交独立负面测试审计，Sol/Root 关闭冲突后才冻结最终默认值；若未引入 durable task registry，验收记录必须把跨 worker/重启幂等列为 A3 前置且不得宣称 A2 已满足。

## 8. 变更请求（不属于当前 Schema/API）

| 变更请求 | 触发条件 | 建议 | 当前处理 |
|---|---|---|---|
| `CR-A2-001` | UI 必须展示异步输入拒绝的精细机器原因 | 在未来 v0.1.2 为 `ScanError` 增加可选 `reason` 或结构化 details，并做 Schema/API/fixture 迁移 | **未批准，不得在 A2 擅自新增字段**；当前只用冻结 `code`+通用 message。 |
| `CR-A2-002` | 产品需要用户主动取消扫描 | 另行设计 `POST /api/v1/scans/{id}/cancel`、幂等和状态竞争 | **未批准，不属于 A2 API**；当前仅保证基础设施/任务取消时清理和 `cancelled` 状态。 |
| `CR-A2-003` | 需要兼容含安全 symlink/submodule 的真实仓库 | 设计“不跟随链接的安全复制/元数据表示”和独立风险状态 | **未批准**；P0 当前失败关闭，不能由实现自行放宽。 |
