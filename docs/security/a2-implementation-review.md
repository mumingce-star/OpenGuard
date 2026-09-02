# A2 安全输入工程可实现性审查

状态：`TERRA_IMPLEMENTATION_REVIEW`

审查日期：2026-09-02

范围：仅审查 `threat-model.md` 与 `a2-security-acceptance.md` 的 A2 落地路径；不代表任何 `SEC-A2-*` 已实现或已通过负面测试，也不改变 P0 v0.1.1 公共契约。

## 1. 结论口径

- `ACCEPT`：可在 A2 内以明确模块、运行时约束与测试接口实现。
- `ADJUST`：目标可保留，但规范需补充可执行边界，或必须拆出专门的实现/测量门禁。
- `BLOCK`：不能由普通应用进程或直接 Git 子进程单独证明；缺少指定的部署/传输前置条件时，A2 不得宣称满足该项。

本轮结论为 **12 ACCEPT、6 ADJUST、2 BLOCK**。两个 `BLOCK` 都是可解决的工程依赖，不是对安全目标本身的否定。

## 2. SEC-A2-001..020 逐项审查

| ID | 结论 | 可实现路径与依据 | A2 模块/测试边界 |
|---|---|---|---|
| `SEC-A2-001` | ACCEPT | `urllib.parse` 后对原始值和规范化值双检；仅允许 ASCII/IDNA 规范化后的 DNS 名、443 和无 userinfo/query/fragment。IP literal、控制字符和二次解码分隔符在任何网络/子进程前拒绝。 | `ingestion/url_policy.py: parse_public_git_url`；`NEG-A2-001..003`。 |
| `SEC-A2-002` | ACCEPT | 请求 DTO 只转交已验证的规范 URL；结构化审计事件只保留 host、URL SHA-256、scan/request ID。拒绝原因使用固定枚举，绝不把原 URL 交给日志格式化或 `ScanError.message`。 | `ingestion/source_audit.py`、`security/redaction.py`；`NEG-A2-002`,`031`。 |
| `SEC-A2-003` | ADJUST | 不得只用 `ipaddress.is_global`。`getaddrinfo` 的全部 A/AAAA 必须经显式 deny CIDR 集分类，含 IPv4-mapped IPv6、文档网段、CGNAT 和云元数据地址；任一非公网结果即失败。 | `security/address_policy.py: resolve_and_require_public`；resolver 注入接口和 `NEG-A2-004..005`。补充平台/语言版本的 CIDR 单测矩阵。 |
| `SEC-A2-004` | BLOCK | 直接执行 `git clone https://host/...` 无法证明 Git/libcurl 每次实际 socket 都连接到事先复核的 IP，同时保持原 host 的 TLS SNI/证书校验；预先 DNS 校验后仍让 Git 按 host 连接不能防 DNS 重绑定。 | A2 必须先提供受控 CONNECT egress proxy/sidecar：代理对每个 CONNECT host 解析全部地址、复核、立即拨号至允许 IP，并只做 TCP 隧道以保留端到端 TLS/SNI。无此部署件时关闭 Git 自动重定向并把 `git_redirects_max` 收紧为 0；没有真实代理集成测试不得通过 `NEG-A2-006..008`。 |
| `SEC-A2-005` | ACCEPT | 以白名单环境运行锁定绝对 Git 二进制：空隔离 HOME/XDG、禁用 system/global config、禁用 credential interaction、空 template/hooks、禁用协议与 LFS smudge，固定 `--depth=1 --single-branch --no-tags --no-recurse-submodules`。请求、仓库和父环境均不能追加 argv/config/proxy。 | `ingestion/git_runner.py: build_git_env/build_clone_argv`；建议以 `GIT_CONFIG_NOSYSTEM`、空 global config、`GIT_TERMINAL_PROMPT=0`、空 credential helper、`GIT_LFS_SKIP_SMUDGE=1` 和 `http.followRedirects=false` 组成最小集合。`NEG-A2-009..010` 必须用 hook/filter/helper/proxy 替身验证实际无调用。 |
| `SEC-A2-006` | ACCEPT | 不做普通 checkout 后再“检查链接”。浅获取后先用 `git ls-tree -r -z` 校验 object mode 和规范路径，只允许 regular blob/tree；再以 `git cat-file --batch` 把已验证 blob 写入安全 staging root。这样不触发 checkout filter，也不物化 symlink/gitlink。 | `ingestion/git_materializer.py: validate_tree/materialize_blobs`；`NEG-A2-011..012` 和包含 gitlink 的真实 object fixture。 |
| `SEC-A2-007` | ADJUST | Git 子进程无法可靠报告其 TLS/pack 网络字节，工作树大小也不能替代 transfer quota。应用层可限制 wall-clock、进程组、物化字节、文件数和 staging volume；精确且保守的网络配额须由受控 egress proxy 对每任务隧道字节硬截断。 | `security/limits.py`、`ingestion/process_group.py`、egress proxy quota；`NEG-A2-013`。规范应明确 `git_transfer_max_bytes` 的执行者是 egress 层，不能把 materialized 计数当作该项通过证据。 |
| `SEC-A2-008` | ADJUST | 标准库 `zipfile` 可用于受限流式读取，但不能单独作为 central/local header、offset overlap、多卷和 ZIP64 边界的安全证明。先写独立 preflight，显式解析 EOCD/central directory/local header 的必要字段，再把单条已核验内容交给流式 reader 并在 EOF/close 验 CRC。 | `ingestion/zip_preflight.py`、`zip_stream.py`；`NEG-A2-014..015`。选择的 ZIP 库版本、受支持压缩算法和 ZIP64 行为须锁版并加入畸形 corpus。 |
| `SEC-A2-009` | ACCEPT | 在写入前进行纯内存路径规范化：拒绝 NUL/控制字符、反斜杠、绝对/drive/UNC、空/`.`/`..` 分段；维护 NFC+casefold 键和父目录类型表，安全 join 仅作第二重断言。 | `security/archive_path.py: normalize_member_path`；`NEG-A2-016..018`。为 macOS/Linux 共享 fixture 增加 Windows 保留设备名和 Unicode 等价组合。 |
| `SEC-A2-010` | ADJUST | 只“相信 ZIP external attribute”不足以跨工具识别类型。已知 Unix symlink/special mode 必须拒绝；未知属性只可按新建普通文件字节流处理，绝不恢复 owner、ACL、xattr、权限或任何链接。 | `ingestion/zip_entry_policy.py`；`NEG-A2-019`。规范宜补充零/未知外部属性的明确处理规则，避免把常见 ZIP 误判为特殊文件。 |
| `SEC-A2-011` | ACCEPT | central-directory 声明值只用于预检；复制循环同时计实际压缩输入、实际输出、单文件、总量、条目、深度、时间和 staging disk。任何超限立即停止当前流、终止任务并清理，不生成部分 inventory。 | `security/quota.py`、`zip_stream.py`；`NEG-A2-020..021` 与等于/刚超过边界。最终磁盘配额仍由部署层兜底。 |
| `SEC-A2-012` | ACCEPT | macOS/Linux 的 Python `os.open(..., dir_fd=..., O_NOFOLLOW|O_CREAT|O_EXCL)`、`mkdir(..., dir_fd=...)` 可实现逐段 `openat` 风格写入。启动时探测 `dir_fd` 与 `O_NOFOLLOW` 支持；不满足即拒绝启动 A2，而非退回字符串路径 API。清理同样以已打开 root dirfd 递归 unlink/rmdir，不对不可信路径执行宽泛删除。 | `security/secure_dir.py: SecureRoot/open_child/write_new_file/remove_tree`；`NEG-A2-023`,`029`,`030`。安全支持矩阵只承诺 POSIX macOS/Linux，不承诺 Windows。 |
| `SEC-A2-013` | ACCEPT | inventory 从 root dirfd 递归、`lstat`/`openat(O_NOFOLLOW)`，稳定 UTF-8 path 排序并按冻结格式哈希；读取前后比较 inode/type/size，最终再验证 manifest。输入目录 0700，完成后去写权限；扫描器使用只读 mount/副本。 | `ingestion/inventory.py: build_inventory/verify_unchanged`；`POS-A2-001..005`,`NEG-A2-024`。 |
| `SEC-A2-014` | ACCEPT | 所有外部工具由固定 argv 列表、固定 cwd/umask/encoding 和最小环境启动；不可信文件名不进入 option 位置，支持时插入 `--`。目标树不提供给 shell、包管理器、构建器或解释器。 | `security/subprocess_policy.py`、`ingestion/process_group.py`；`NEG-A2-025..026`。 |
| `SEC-A2-015` | BLOCK | Python 计数和 `setrlimit` 可提供部分开发防护，但不能单独证明网络隔离、跨任务文件隔离、cgroup memory/CPU/disk 上限或可靠进程数限制。macOS 开发机尤其不能等价替代 Linux cgroup/网络 namespace。 | A2 完成前必须提供受支持的 Linux 容器/namespace 运行 profile：只读输入 mount、独立 writable temp、non-root UID、cgroup v2、fd/process limits 和默认 deny egress；macOS 仅运行标注为开发级的单元/有限集成测试。`NEG-A2-027..028` 的通过证据来自该 profile。 |
| `SEC-A2-016` | ACCEPT | 父调度器拥有每任务工作区和整个子进程组；所有 success/failure/timeout/cancel 进入同一 `finally`，先终止/等待进程组再 descriptor-safe 删除。重启清道夫只枚举受控 root 中带 versioned OpenGuard prefix 的过期目录；清理失败隔离并令 worker 不可复用。 | `ingestion/workspace.py: create/close/cleanup_orphans` 与 `TaskSupervisor`；`NEG-A2-029..030`。success 清理触发点应是同一 ScanRun 的最后一个只读消费者结束，而非 inventory 完成。 |
| `SEC-A2-017` | ACCEPT | 建立唯一 `security/redaction.py`：原始异常只能进入内部受控事件，API/`ScanError` 只从 code→固定通用文案映射；日志字段 allowlist、控制字符转义、长度限制和摘要化。Evidence 摘录在保存前过同一策略。 | `security/redaction.py`、`ingestion/error_mapper.py`；`NEG-A2-031..032`。不能把当前模型中的基本字符串校验误表述为已完成 A2 全量脱敏。 |
| `SEC-A2-018` | ADJUST | 版本锁定和来源登记可实现，但 ScanCode/Syft/镜像/规则尚未实际引入，不能在 A2 代码中伪造完整供应链证明。 | `third_party/` 台账、锁文件/镜像 digest、构建验证脚本；`NEG-A2-033`。规范应把“输入安全底座已锁定的 Git/ZIP 库”与“未来扫描器适配器已锁定”分开验收。 |
| `SEC-A2-019` | ACCEPT | 同步拒绝返回既有 HTTP envelope；异步 ingestion 失败写 `ScanRun(status=failed, stage=ingestion, errors=[ScanError(...)])`。输入安全失败绝不进入 `partial/completed`；`partial` 仅在 inventory 成功后的下游可恢复故障。 | `ingestion/error_mapper.py`、`TaskSupervisor`；`NEG-A2-034..035`。`details.reason` 只存在同步 envelope/内部审计，当前 `ScanError` 不新增字段。 |
| `SEC-A2-020` | ADJUST | Pydantic settings 可在启动校验最小/硬上限并生成规范化 config digest；每 worker semaphore 可控制本进程并发。但全局队列、跨重启幂等和临时磁盘总量需要部署配置与持久任务 registry。 | `settings.py`、`ingestion/task_registry.py`、`security/limits.py`；`NEG-A2-013`,`028`,`036`。在 SQLite/队列接口落地前，不得声称跨 worker 的幂等或全局并发已经保证。 |

## 3. 建议的模块与函数边界

```text
backend/app/
  security/
    address_policy.py      # resolve_all, require_public_address_set
    archive_path.py        # normalize_member_path, collision_key
    secure_dir.py          # SecureRoot: open_child, mkdir_child, write_new_file, remove_tree
    quota.py               # QuotaLedger: reserve, count_stream, assert_within_limits
    redaction.py           # sanitize_text, safe_event, fixed_public_message
    subprocess_policy.py   # build_sanitized_env, fixed_argv, ProcessGroup
  ingestion/
    url_policy.py          # parse_public_git_url
    egress_client.py       # TrustedEgress contract; no direct internet fallback
    git_runner.py          # clone_no_checkout with fixed executable/environment
    git_materializer.py    # validate_tree, materialize_blobs without checkout
    zip_preflight.py       # parse/validate archive structure
    zip_stream.py          # stream_verified_members
    workspace.py           # per-run workspace and orphan cleanup
    inventory.py           # descriptor-safe inventory and root_digest v1
    error_mapper.py        # policy failure -> frozen API/ScanRun representation
    task_registry.py       # durable idempotency/concurrency ownership boundary
```

`TrustedEgress` 是 A2 的关键依赖：它接收 host、443、scan ID 和字节预算；自行解析/分类全部地址，立即连接一个允许 IP，并保持请求的 TLS server name。应用不能将普通 `requests`、Git 默认网络或用户代理作为替代路径。

## 4. 分阶段实现顺序

1. **A2-0 运行前置条件**：管理员配置 schema、受控 temp root、Linux container/egress profile、固定 Git/ZIP 库版本、测试用受控 DNS/HTTPS/proxy。未满足时不开始 Git 网络入口。
2. **A2-1 ZIP 安全纵切**：workspace、路径/条目 preflight、dirfd 流式写入、QuotaLedger、inventory、同步错误映射和生命周期。ZIP 可先形成首条真实主链，且不依赖网络 pinning。
3. **A2-2 Git 本地 materialization**：锁定 Git、no-checkout、tree mode/path 校验、blob materialization、revision/root digest；先使用本地受控 bare fixture，验证无 hooks/filter/LFS/submodule。
4. **A2-3 受控公网 Git**：接入 TrustedEgress，默认零自动重定向、代理字节硬上限、真实 TLS/SNI/DNS-rebinding 集成测试。达标后才开放公网 URL。
5. **A2-4 隔离与清理**：Linux profile 下运行 scanner probe、资源/网络/跨任务负面测试、timeout/cancel/restart 清道夫；之后才把同一 profile 交给 B2/B3 扫描器。
6. **A2-5 冻结证据**：Luna 运行所有 POS/NEG、Terra 提交真实仓库可用性测量、Sol/Root 关闭下列修订项，再允许 A2 标记完成。

## 5. 错误、阶段和生命周期映射

| 场景 | 入口 | `ScanRun` 表示 | 对外细节 |
|---|---|---|---|
| URL 语法、凭据、端口、地址在创建前被拒绝 | 同步 | 不创建任务 | HTTP `invalid_source` + 稳定 `details.reason`。 |
| ZIP 结构、路径、类型、限额在上传处理前被拒绝 | 同步 | 不创建任务 | `invalid_archive` 或 `archive_limit_exceeded` + 稳定 reason。 |
| 已接受任务的 Git/DNS/tree/ZIP/inventory 安全失败 | 异步 | `status=failed`，`stage=ingestion`，至少一条脱敏 `ScanError(code=invalid_source/invalid_archive/archive_limit_exceeded/scanner_failed)` | GET 状态只显示固定 message；细分 reason 留在受控内部审计，不擅加到 `ScanError`。 |
| ingestion 超时或配额/隔离失败 | 异步 | `failed`，`stage=ingestion`，`scanner_timeout` 或 `scanner_failed` | 固定通用 message；清理必须继续执行。 |
| inventory 已成功，后续扫描/报告可恢复失败 | 异步 | 仅此时可 `partial`；保留可用 inventory，并有 `recoverable=true` 的 `ScanError` | 属于 A4/B2+，不是输入安全拒绝的逃生路径。 |
| 基础设施取消/调度终止 | 异步 | `cancelled`，保留最后 stage/progress；无原始异常泄漏 | 父调度器终止进程组后执行 cleanup。 |

临时目录状态机为 `created -> receiving/materializing -> inventoried -> read_only_consumed -> cleaned`；任一异常转为 `terminating -> cleaned` 或 `quarantined`。重启清道夫只能处理过期、命名和权限均符合 OpenGuard workspace 策略的目录，不能扫描宽泛系统临时目录。

## 6. 未来测试接口与尚待测量项

### 可注入测试接口

- `Resolver`: 固定返回全部 A/AAAA，用于 mixed-address 和 rebinding；不访问真实内网。
- `TrustedEgress`: 记录 host、拨号 IP、SNI、重定向/连接次数和保守字节数，用受控 TLS 服务断言无私网连接。
- `GitExecutable`: hook/filter/LFS/credential/proxy 替身，仅记录是否被调用；真实 Git object fixture 单独覆盖 tree modes。
- `SecureRoot`: 在父目录替换和并发竞争下验证 dirfd/no-follow 写入，不以 mock 替代真实文件系统集成。
- `SandboxProbe`: 在 Linux profile 尝试网络、输入写入、其他任务读取、CPU/memory/process/fd 超限；这不是执行目标项目。
- `Clock/TaskRegistry`: 驱动 timeout、cancel、cleanup retry 和 restart orphan 情形。

### 必须在实现后测量或决定

1. 以公开、小型、无链接仓库测量默认 Git timeout、materialized size、文件数和真实可用性；不要在没有数据时调整默认值。
2. 验证 egress proxy 的 TLS SNI、实际 destination IP、每任务总字节和断连行为；没有这组证据，`SEC-A2-004/007` 保持阻塞。
3. 确认 A2 最终支持的 Linux runtime、cgroup v2、network namespace、磁盘 quota 与容器镜像版本；macOS 只作为开发/兼容测试平台。
4. 选定 ZIP preflight 库/自实现范围，并对 ZIP64、data descriptor、Unicode、外部属性和损坏 corpus 做版本化回归。
5. 决定 SQLite task registry 的最小接口是否随 A2 引入；若不引入，应把跨 worker/重启幂等承诺从 A2 完成定义中移至后续任务。

## 7. 只建议、不直接修改的 Sol 规范修订

1. **`SEC-A2-004`**：明确 A2 直接 Git 模式默认 `git_redirects_max=0`；仅当 `TrustedEgress` 可记录每个连接的 host、解析地址、实际拨号 IP 和 TLS server name 时才允许大于 0 的重定向。这样避免“预检 DNS 后 Git 自己连接”被误认为 pinning。
2. **`SEC-A2-007`**：在 `git_transfer_max_bytes` 旁明确它由 egress proxy 以保守隧道字节数执行；应用进程的 materialized/disk 计数是独立防线，不能替代 transfer quota。
3. **`SEC-A2-015`**：将 A2 的安全完成证据绑定受支持 Linux container/cgroup/egress profile；macOS/Linux 的应用单元测试不能替代该 profile。B2/B3 接入实际扫描器后应复用同一 sandbox contract。
4. **`SEC-A2-018`**：区分“本 A2 实际引入的 Git/ZIP 依赖已锁定”与“未来 ScanCode/Syft/规则数据已锁定”，防止未引入资源被写成已验证供应链。
5. **`SEC-A2-020`**：明确跨 worker/重启幂等依赖 durable task registry；若注册表不在 A2 范围，改为 A3 前置条件而非已满足事实。

这些都是实现性澄清，不请求新增 P0 字段、API 路径或枚举。`CR-A2-001..003` 仍保持未批准。
