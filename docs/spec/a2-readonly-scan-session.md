# A2-2 安全只读扫描会话契约

状态：`FROZEN_DESIGN_BASELINE / IMPLEMENTATION_UNVERIFIED`

版本：`v0.1.0`

日期：2026-09-02

负责人：Sol（设计、安全边界与契约审查）

## 1. 目标、依据与非目标

本契约解决一个局部生命周期断点：当前 `ZipIngestionService.ingest()` 在返回 `Inventory` 前于 `finally` 清理任务树，因此后续可信 manifest/许可证解析器无法在同一任务内读取 inventory 中的小文件。A2-2 新增一个同步、受限、生命周期绑定的只读消费接口，并保留现有 `ingest()` 行为。

本设计继承 `SEC-A2-009/012/013/016/017/019/020`、`NEG-A2-023/024/029/031/034/036` 和既有 A2 ZIP 稳定错误语义。它是一个仓库内部 Python 契约，不是 P0 HTTP/Schema 契约。

非目标：

- 不新增或修改 P0 v0.1.1 字段、枚举、Schema、sample、endpoint 或对外错误包络。
- 不实现 B1 manifest/许可证 parser，不实现 Git、TrustedEgress、Web/FastAPI、durable registry 或 Linux sandbox profile。
- 不允许任意不可信 Python 代码作为 callback。Python 同进程代码可通过导入 `os`、反射或访问私有属性绕开 API；本契约不是安全沙箱，也不能代替 `SEC-A2-015` 的真实 Linux 隔离证据。

## 2. 冻结的对外类与方法

以下“对外”仅指 `backend.app.ingestion` 包内可供可信应用代码导入的接口；不对 HTTP 或第三方插件开放。

```python
T = TypeVar("T")

@dataclass(frozen=True)
class ScanReadLimits:
    single_file_max_bytes: int | None = None
    total_max_bytes: int | None = None

@dataclass(frozen=True)
class ScanSessionResult(Generic[T]):
    inventory: Inventory
    consumer_result: T

class ReadOnlyScanSession:
    @property
    def inventory(self) -> Inventory: ...

    def read_bytes(
        self,
        relative_path: str,
        *,
        max_bytes: int | None = None,
    ) -> bytes: ...

class ZipIngestionService:
    def ingest(self, archive_stream: BinaryIO) -> Inventory: ...

    def ingest_with_consumer(
        self,
        archive_stream: BinaryIO,
        consumer: Callable[[ReadOnlyScanSession], T],
        *,
        read_limits: ScanReadLimits | None = None,
    ) -> ScanSessionResult[T]: ...
```

冻结语义：

1. `ingest()` 的签名、返回类型、inventory/root digest 字节规范、稳定 ZIP `code/reason` 和返回前清理行为不变；CLI 继续只调用此方法，输出 Schema/version 不变。
2. `ingest_with_consumer()` 只在 ZIP 完整接收、预检、物化、inventory 与初始重验证成功后调用一次 `consumer`。调用前的失败保留既有 `IngestionSecurityError` 映射，且 consumer 不得被调用。
3. `ScanSessionResult` 只能在 consumer 正常返回、会话最终重验证通过、会话已失效且 workspace 清理成功后返回。任一失败不返回部分 `Inventory`、部分 `bytes` 或 `consumer_result`。
4. `ReadOnlyScanSession` 使用 `__slots__`，公开成员只有 `inventory` 和 `read_bytes`。不实现 `open`、`path`、`root`、`fd`、`fileno`、`write`、分块流、目录遍历或任意路径查询。
5. `read_bytes()` 只返回完整文件的不可变 `bytes`；不返回 `Path`、绝对路径、相对 root、目录/文件 descriptor、`BinaryIO`、`memoryview` 或可写对象。
6. `consumer_result` 可为任意应用 DTO。即使 consumer 直接或嵌套保存/返回 session 引用，方法返回前 session 也已失效，后续读取必须拒绝。

## 3. 服务端配额与调用者收紧

`ZipSafetyLimits` 新增两个经管理员配置的冻结字段：

| 字段 | 默认值 | 安全范围 | 额外约束 |
|---|---:|---:|---|
| `scan_single_file_read_max_bytes` | 2 MiB | 64 KiB..32 MiB | 不得大于 `single_file_max_bytes` |
| `scan_total_read_max_bytes` | 16 MiB | 1 MiB..256 MiB | 必须大于等于 `scan_single_file_read_max_bytes`，且不得大于 `uncompressed_max_bytes` |

非 `int`、`bool`、低于下限、高于上限或破坏交叉约束的服务配置使服务启动失败，不在运行时静默修正。

`ScanReadLimits` 是单次调用的收紧值：`None` 表示使用服务值；非空值必须是非 `bool` 正整数，且小于等于对应服务值。任一字段试图放宽、非法或使总量小于单文件值，在 ZIP 流被消费前拒绝为 `scanner_failed/scan_read_limit_invalid`。

`read_bytes(..., max_bytes=N)` 可再收紧该次读取；`N` 必须是非 `bool` 正整数且不高于有效单文件限额，否则为 `scan_read_limit_invalid`。已登记 size 高于此次上限或累计剩余额度时，在打开文件前拒绝为 `scanner_failed/scan_read_limit_exceeded`。

计数规则：

- 每次读取按 snapshot 的完整文件 size 原子预留累计额度，重复读取重复计数。
- 预留在 open/read/完整性失败后不退回，防止通过重试绕过总额度。
- 仅在全文件完成读取、EOF、身份/size/type 前后一致且 SHA-256 与 snapshot 相符后返回 `bytes`；不暴露部分缓冲区。

## 4. 路径、descriptor 与 TOCTOU 重验证

### 4.1 仅允许 inventory 普通文件

`relative_path` 必须是精确 `str`，不接受 `PathLike`、`bytes` 或子类自定义解析。实现须复用同一组归一化规则验证绝对路径、反斜杠、drive/UNC/device、控制字符、空/`.`/`..` 分段、NFC、深度和 UTF-8 长度；然后要求输入与 snapshot 中的规范相对路径完全相等。

不存在、是目录、仅 case-fold/NFC 别名相等或任一形态非法时，在任何文件系统打开操作前统一失败为 `scanner_failed/scan_path_not_in_inventory`。错误不包含输入路径。

### 4.2 内部 snapshot

实现必须在同一 root descriptor 上产生不对消费者暴露的 `_InventorySnapshot`：

```text
_InventorySnapshot
├─ inventory: Inventory
├─ root_seal: _DirectorySeal(dev, ino, type)
├─ directories[parts]: _DirectorySeal(dev, ino, type)
└─ files[relative_path]: _FileSeal(parts, dev, ino, type, size, sha256)
```

`build_inventory()` 保留现有返回类型；新增内部 `build_inventory_snapshot()`，前者可调用后者并只返回 `.inventory`。文件 seal 取最终已哈希 descriptor 的 `fstat`，目录 seal 包括 tree root 与每个父目录。只允许普通目录/文件；不记录绝对路径。

### 4.3 每次读取与最终重验证

内部 `_ReadOnlyFileReader` 持有 workspace 私有能力，session 本身不暴露它。每次读取必须：

1. 从已封印 `parts` 出发，从 root dirfd 逐段以 `O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC` 打开父目录；禁止字符串 join 后打开。
2. 每层目录 `fstat` 必须与对应 seal 的 type/dev/inode 一致。
3. 末端以 `O_RDONLY|O_NOFOLLOW|O_CLOEXEC` 打开；打开前 `lstat`、打开后 `fstat` 与读取后 `fstat` 均必须是普通文件，且 type/dev/inode/size 与 seal 及彼此一致。
4. 读取精确 seal size，验证 EOF，对完整字节计算 SHA-256 并与 seal 相等。因此同 inode、同 size 的内容改写也必须失败，而不只依赖 stat 差异。
5. 任一 symlink、父目录替换、inode/type/size 变更、短读/多读或哈希不符使整个会话中毒；消费者即使 catch 住该异常，外层也不得返回成功。

在调用 consumer 前和 consumer 正常/异常结束后，必须 descriptor-relative 重验证完整 snapshot，包括目录/文件身份、type、size 和每文件 SHA-256。这可阻止 consumer 未主动读取的变更文件被当作有效 inventory。对同进程恶意代码的“改写后在两次观察之间完整恢复”不作沙箱承诺，因此 consumer 必须是可信、非执行性 parser。

## 5. 生命周期、线程、并发与重入

单个会话状态机为：

```text
CREATED -> ACTIVE -> INVALIDATING -> EXPIRED -> CLEANED
                 \-> FAILED ------^       \-> CLEANUP_FAILED
```

- session 在 consumer 被调用的线程上创建并绑定 owner thread。`inventory` 可在 ACTIVE 期访问；`read_bytes()` 还需满足 owner thread 和非重入读取。
- 任何其他线程访问 `read_bytes()` 都立即中毒会话并返回 `scanner_failed/scan_session_thread_violation`；不会转移 owner，也不会排队读取。
- 同一 session 上一次 `read_bytes()` 尚未完成时再进入读取，中毒为 `scanner_failed/scan_session_reentrant`。
- consumer 中在同一线程上再调用同一 `ZipIngestionService.ingest_with_consumer()` 也拒绝为 `scan_session_reentrant`。不同线程、不同调用的 session/workspace 相互隔离，可并发执行；不允许跨 session 共享 budget、reader 或文件能力。
- consumer 返回或抛出后，在任何最终重验证/清理之前先将 session 转为 EXPIRED。任何保存引用的后续 `inventory`/`read_bytes()` 访问统一拒绝为 `scanner_failed/scan_session_expired`，不得因 workspace 尚未删除而短暂恢复。
- `ZipIngestionService.close()` 只能由调用者在所有并发调用结束后执行；与活动调用并发 close 不在本内部接口的支持契约内。

## 6. 稳定错误、脱敏与优先级

新增会话错误均使用 `IngestionSecurityError`，且 `code=scanner_failed`。`reason` 只允许下表字面量：

| 条件 | 稳定 `reason` |
|---|---|
| 调用或单次限额非法/试图放宽 | `scan_read_limit_invalid` |
| 单文件或累计额度不足 | `scan_read_limit_exceeded` |
| 路径不是 inventory 中精确普通文件 | `scan_path_not_in_inventory` |
| `open/read/close` 系统失败，且未观察到明确身份/完整性差异 | `scan_file_read_failed` |
| 目录/文件替换、链接、type/inode/size/hash/EOF 不一致 | `scan_file_integrity_failed` |
| 回调结束后使用保存引用 | `scan_session_expired` |
| 非 owner thread 读取 | `scan_session_thread_violation` |
| session 读取或同线程 service consumer 重入 | `scan_session_reentrant` |
| consumer 抛出普通异常 | `scan_consumer_failed` |
| workspace 按既有重试上限仍清理失败 | `workspace_cleanup_failed` |

映射与优先级：

1. 工作区清理必须在所有路径执行；`workspace_cleanup_failed` 优先级最高，覆盖成功、consumer 错误或先前会话错误，与既有 ZIP 服务失败关闭语义一致。
2. 清理成功时，最终 snapshot 重验证的 `scan_file_integrity_failed` 优先于 consumer 普通异常。若无最终完整性失败，保留会话首个已锁存的策略/读取错误。
3. consumer catch 住 session 产生的异常也不能解除中毒；外层必须抛出已锁存错误。只有异常对象身份与该 session 锁存对象一致时才保留细分 reason；consumer 自行构造的 `IngestionSecurityError` 不可伪造安全错误，统一映射为 `scan_consumer_failed`。
4. consumer 的 `Exception` 不记录/返回 `str(error)`、类名、路径、堆栈、文件名或文件内容；统一 `scan_consumer_failed`。`KeyboardInterrupt`/`SystemExit` 等 `BaseException` 仍必须使 session 失效并执行清理，清理成功后原样重抛，不属于稳定业务错误契约。
5. 所有新 reason 仅进入受控内部审计。本任务不把它们擅自加入 P0 `ScanError`、HTTP `details.reason` 或 CLI 成功 JSON。

## 7. 执行次序与不可部分成功

`ingest_with_consumer()` 的唯一允许次序为：

1. 先验证服务端/调用收紧配额；
2. 沿用现有 ZIP 接收、预检、安全物化和实际解压配额；
3. 构建 inventory + 内部 snapshot，完成 consumer 前全树重验证；
4. 创建 ACTIVE session，同步调用一次可信 consumer；
5. 在 `finally` 的最前面使 session 失效，再进行 consumer 后全树重验证；
6. 关闭会话内部 reader/descriptor，执行既有有界 cleanup retry；
7. 按第 6 节优先级抛错，或返回完整 `ScanSessionResult`。

本层没有 `partial`。输入安全失败、会话策略失败、读取/完整性失败、consumer 失败或清理失败均不得产生可供上层发布的部分结果。未来上层映射必须继续遵守 `SEC-A2-019`：这些失败不得成为 `completed` 或 `partial`。

## 8. 冻结验收矩阵

### 8.1 Terra 实现侧正向用例

| ID | 输入/操作 | 必须断言 |
|---|---|---|
| `POS-A2-RS-001` | 现有 `ingest()` 处理有效 ZIP | 返回的 inventory/root digest 与冻结 v1 一致；返回前仍清理；CLI JSON/exit 不变。 |
| `POS-A2-RS-002` | consumer 读取 inventory 内一个限额内 UTF-8 路径小文件 | 返回完整 `bytes`，其 size/SHA-256 与 inventory 一致；result 同时含 inventory 和 consumer DTO。 |
| `POS-A2-RS-003` | 多文件顺序读取且累计值等于有效上限 | 边界值成功；每次读取计数可重算。 |
| `POS-A2-RS-004` | 调用者将单文件/总量限额进一步调低 | 收紧值生效，服务默认值不被改写。 |
| `POS-A2-RS-005` | consumer 不读文件、只返回基于 immutable inventory 的 DTO | 会话后重验证和清理均成功；不暴露临时路径。 |
| `POS-A2-RS-006` | 同一 service 串行复用两次 | budget/session/workspace 不串扰，两次都清理。 |
| `POS-A2-RS-007` | 两线程在同一 service 上执行独立调用 | 每次只读自己的 session/workspace，结果和额度相互隔离。 |
| `POS-A2-RS-008` | consumer 保存 session 引用但在回调内正常使用 | 主调用可成功；返回后保存引用已过期。 |

### 8.2 Luna 独立负向与真实文件系统用例

| ID | 攻击/失败条件 | 冻结结果 |
|---|---|---|
| `NEG-A2-RS-001` | 绝对路径、`..`、点/空段、反斜杠、drive/UNC、NFC/case 别名 | 打开前 `scan_path_not_in_inventory`，无 root 外读取。 |
| `NEG-A2-RS-002` | 读目录、未登记文件、`Path`/`bytes` 参数 | `scan_path_not_in_inventory`，不接受 PathLike 式隐式解析。 |
| `NEG-A2-RS-003` | 在读取前将父目录替换为 symlink | `scan_file_integrity_failed`；外部 sentinel 未读/未改。 |
| `NEG-A2-RS-004` | 将普通文件替换为 symlink/FIFO/目录 | `scan_file_integrity_failed`；不跟随、不阻塞。 |
| `NEG-A2-RS-005` | 以同 size 新 inode 替换文件，即使内容相同 | identity seal 不符，`scan_file_integrity_failed`。 |
| `NEG-A2-RS-006` | 同 inode、同 size 改写内容 | SHA-256 不符，`scan_file_integrity_failed`；不返回变更字节。 |
| `NEG-A2-RS-007` | 读取期间截断、增长、身份或 type 竞态更换 | before/open/after/EOF/hash 任一不符均 `scan_file_integrity_failed`。 |
| `NEG-A2-RS-008` | 底层 open/read/close 发生受控 `OSError`且无明确 seal 差异 | `scan_file_read_failed`；不泄漏 errno/path。 |
| `NEG-A2-RS-009` | 单文件限额刚超 1 byte | `scan_read_limit_exceeded`；打开前失败。 |
| `NEG-A2-RS-010` | 累计限额刚超 1 byte，包括重读同文件 | `scan_read_limit_exceeded`；无部分结果。 |
| `NEG-A2-RS-011` | 调用或 `max_bytes` 为 0/`bool`/非整数/超服务值 | `scan_read_limit_invalid`；调用者不能放宽。 |
| `NEG-A2-RS-012` | consumer 返回后使用保存 session，包括清理前故障注入窗口 | 永久 `scan_session_expired`，无再激活。 |
| `NEG-A2-RS-013` | 将 session 交给其他线程读取 | `scan_session_thread_violation`，主线程结束时仍整体失败。 |
| `NEG-A2-RS-014` | 同 session 读取重入或 callback 同线程递归调用同 service | `scan_session_reentrant`，内外 workspace 均清理。 |
| `NEG-A2-RS-015` | consumer catch 住 session 限额/路径/完整性异常后返回成功 DTO | 锁存错误仍从外层抛出，无 result。 |
| `NEG-A2-RS-016` | consumer 抛出含路径、token 形式或文件正文的异常 | 只见 `scanner_failed/scan_consumer_failed`，无原文/类名/堆栈。 |
| `NEG-A2-RS-017` | consumer 伪造 `IngestionSecurityError` | 不信任伪造 code/reason，统一 `scan_consumer_failed`。 |
| `NEG-A2-RS-018` | consumer 期间改动未读取的 inventory 文件 | consumer 后全树重验证失败为 `scan_file_integrity_failed`。 |
| `NEG-A2-RS-019` | cleanup 失败，consumer 原本成功 | 最终 `workspace_cleanup_failed`，不返回 result。 |
| `NEG-A2-RS-020` | cleanup 失败且 consumer/完整性也失败 | cleanup reason 按最高优先级返回；较早错误不泄漏。 |
| `NEG-A2-RS-021` | ZIP 输入安全拒绝或 inventory 失败 | consumer 零调用；保留现有稳定 ZIP code/reason；工作区清理。 |
| `NEG-A2-RS-022` | 公开 session 表面结构审计 | 无绝对路径、`Path`、fd/`fileno`、stream/open/write/目录遍历公开能力。 |
| `NEG-A2-RS-023` | 并发独立 session 尝试串用对方 path/ref/budget | 只能命中自己 snapshot；无跨任务读取，两树都清理。 |
| `NEG-A2-RS-024` | consumer 通过目标项目脚本、import、子进程、网络或安装依赖执行扫描 | 该 consumer 不符合本接口信任前提；不得以此 API 测试结果声称已安全沙箱化。 |

### 8.3 责任边界

- Terra 仅修改 `backend/app/ingestion/`、`backend/app/security/`、必要的包导出/模块说明和 `tests/unit/`；按上述签名、状态机、reason 和优先级实现，不修改 Luna 文件或 P0。
- Luna 仅新增/修改独立 `tests/security/` 与安全测试说明；不修改 Terra 实现、unit 期望、本契约或 P0。TOCTOU、symlink/type 替换、过期引用、真实线程、异常脱敏和清理优先级须使用真实临时文件系统/受控故障注入，不以纯 `SecureRoot` mock 冒充整合证据。
- Sol 在 Terra/Luna 结果后只审计契约一致性、错误优先级、脱敏、完成/未证明边界；Root 才负责全量复跑、证据绑定、进度、提交与发布。

## 9. 完成与尚未证明

### 本次 Sol 完成

- 冻结仓库内部类、方法、参数、返回值和 `ingest()`/CLI 向后兼容性。
- 冻结只读 capability、inventory 白名单、descriptor-relative/no-follow 读取、身份快照、SHA-256 复核和会话前后全树重验证。
- 冻结服务端配额、调用者仅收紧、线程/并发/重入/过期语义、稳定脱敏错误与无部分结果优先级。
- 冻结 `8 POS + 24 NEG` 和 Terra/Luna 可执行责任边界。

### 尚未证明，不得外推

- Terra 尚未实现本契约，Luna 尚未运行独立 A2-2 安全测试；现有 111 项绿灯不是 A2-2 运行证据。
- 本设计不关闭 cleanup quarantine/worker 不复用/orphan 清道夫、强退/取消、durable registry、最终 HTTP/`ScanRun` 映射或完整 ZIP corpus。
- 没有引入或验证 B1 parser、ScanCode、Syft、Git、TrustedEgress、公网获取、Web 服务、目标代码执行或依赖/许可证结果。
- macOS/POSIX 开发测试不能证明受支持 Linux non-root、只读 mount、cgroup v2、deny-egress、process/fd/disk 和跨任务隔离 profile。`SEC-A2-004` 的 TrustedEgress 与 `SEC-A2-015` 的 Linux 完成门禁继续阻塞。
- 只有 Terra 实现、Luna 独立回归、Sol 终审和 Root 绑定不可变提交/运行 profile 后，才能为本局部纵切申请有界 evidence ID；仍不等于 A2 总门禁完成。

## 10. AMENDMENT v0.1.1 - 旧 ZIP 限额配置与扫描默认值兼容裁决

日期：2026-09-02

状态：`FROZEN_DESIGN_BASELINE`

触发证据：既有 Luna 回归使用 `ZipSafetyLimits(single_file_max_bytes=1 * MiB)`。v0.1.0 同时要求扫描单文件默认为 2 MiB、不得高于 ZIP 单文件上限、违反时启动失败；普通 dataclass 的 `int=2 * MiB` 无法区分“调用者没有配置”与“显式配置 2 MiB”，会破坏旧配置的向后兼容性。不允许修改 Luna 旧测试来隐藏该冲突。

本 AMENDMENT 只覆盖第 3 节中 `scan_single_file_read_max_bytes` 的声明默认与派生规则；其余 API、配额、生命周期、错误、POS/NEG 和未证明边界不变。

### 10.1 冻结配置形式

```python
@dataclass(frozen=True)
class ZipSafetyLimits:
    # 既有字段省略
    scan_single_file_read_max_bytes: int | None = None
    scan_total_read_max_bytes: int = 16 * MIB
```

`None` 是唯一的“使用安全派生默认值”标记，调用者省略该字段或显式传 `None` 语义相同。它不表示无限制，不得传递到会话 budget。服务在消费任何 ZIP 字节前解析：

```python
effective_scan_single_file_read_max_bytes = min(
    2 * MIB,
    limits.single_file_max_bytes,
)
```

若 `scan_single_file_read_max_bytes` 是显式 `int`，有效值就是该整数，并继续严格要求：

- 非 `bool` 的 `int`；
- 在 64 KiB..32 MiB 内；
- 不得高于 `single_file_max_bytes`；
- 不得高于 `scan_total_read_max_bytes`。

任一显式值违反上述约束仍在服务配置验证时抛出 `ValueError`，不静默 clamp。只有 `None` 派生分支使用 `min(2 MiB, single_file_max_bytes)`，因为这是对旧未配置扫描限额调用的兼容解析，不是对显式管理员值的宽松修正。

### 10.2 精确兼容结果

| 构造 | 有效扫描单文件上限 | 结果 |
|---|---:|---|
| `ZipSafetyLimits()` | 2 MiB | 标准默认不变。 |
| `ZipSafetyLimits(single_file_max_bytes=1 * MIB)` | 1 MiB | 旧配置继续有效；扫描不得超过更严的 ZIP 上限。 |
| 上述旧配置 + `scan_single_file_read_max_bytes=None` | 1 MiB | 与省略字段完全相同。 |
| `single_file_max_bytes=1 * MIB, scan_single_file_read_max_bytes=2 * MIB` | 无 | 显式放宽仍 `ValueError`，不 clamp 为 1 MiB。 |
| `single_file_max_bytes=32 * MIB, scan_single_file_read_max_bytes=1 * MIB` | 1 MiB | 显式收紧有效。 |

`ScanReadLimits` 的单次调用语义不变：它只能相对上述 **effective** 服务值再收紧；试图超过 effective 值仍是 `scanner_failed/scan_read_limit_invalid`。

### 10.3 验收矩阵增补（不新增 ID）

- `POS-A2-RS-001` 增补：既有 `ZipSafetyLimits(single_file_max_bytes=1 * MIB)` 必须能构造服务，旧 `ingest()`/CLI 回归不变，有效扫描单文件上限为 1 MiB。
- `POS-A2-RS-004` 增补：标准 32 MiB ZIP 配置下，省略/传 `None` 均派生 2 MiB；显式 1 MiB 仍是合法收紧。
- `NEG-A2-RS-011` 增补：当 ZIP 单文件上限为 1 MiB 时，显式扫描上限 2 MiB 必须 `ValueError`，不得 clamp；该断言与省略/`None` 派生 1 MiB 的正向断言成对。

本裁决同时保留三项不变性：旧 ZIP 配置可用；标准配置扫描默认仍为 2 MiB；任何显式扫描限额都严格验证且不得高于 ZIP/累计上限。
