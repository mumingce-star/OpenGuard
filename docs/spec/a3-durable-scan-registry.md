# A3-0 持久 ScanRun 注册表契约

- 版本：`v0.1.0`
- 状态：`FROZEN_DESIGN_BASELINE / IMPLEMENTATION_UNVERIFIED`
- 日期：2026-09-02
- 设计负责人：Sol
- 后续实现负责人：Terra
- 后续独立验证负责人：Luna
- 依赖契约：P0 Domain/API `v0.1.1`

## 1. 结论、边界与人员责任

A3-0 冻结一个单机 POSIX 部署内的 SQLite `ScanRun` 注册表。它持久保存完整、已经通过
P0 v0.1.1 模型校验的 `ScanRun` 快照，以内部递增 `revision` 提供 compare-and-swap
（CAS），并以非敏感请求指纹实现跨进程、跨重启幂等。它是后续 A3 FastAPI 与 A4
Pipeline 的内部前置，不是新的 HTTP API。

本规格遵守技术执行书分工：注册表、API 单一事实源和集成由项目负责人掌握；不接管扫描分析组员
负责的 B2-B7 扫描/分析能力，也不接管前端组员负责的 React 页面。设计轮不修改 backend、测试、
P0 模型、导出 Schema、sample 或进度台账。

本轮明确不做：

- 不新增、删除或改变 `ScanRun`、六个 P0 endpoint、公共错误包络或枚举；
- 不启动 FastAPI，不实现 repository/service/HTTP handler，不产生 OpenAPI；
- 不实现后台 worker、队列、租约、心跳、重试、超时、孤儿回收或 A4 stage 编排；
- 不执行 B2-B7 scanner，不接收 Git/ZIP，不保存上传文件、凭据、报告正文或临时路径；
- 不做 PostgreSQL、Redis、网络文件系统、多主数据库、复制、备份或在线迁移；
- 不把本地 SQLite 测试外推为生产集群、高可用或灾难恢复证明。

## 2. 冻结内部接口

实现位置为 `backend/app/persistence/scan_registry.py`，由
`backend.app.persistence` 只导出以下公共内部对象：

```python
from dataclasses import dataclass
from pathlib import Path

from app.domain.models import ScanRun

REGISTRY_STORAGE_SCHEMA = "openguard.scan-run-registry"
REGISTRY_STORAGE_VERSION = 1

@dataclass(frozen=True)
class StoredScanRun:
    run: ScanRun
    revision: int

@dataclass(frozen=True)
class ScanRunPage:
    items: tuple[StoredScanRun, ...]
    next_after_scan_id: str | None

class ScanRegistryError(RuntimeError):
    code: str

class SQLiteScanRunRegistry:
    def __init__(
        self,
        database_path: Path,
        *,
        busy_timeout_ms: int = 5_000,
    ) -> None: ...

    def create(
        self,
        run: ScanRun,
        *,
        idempotency_fingerprint: str | None = None,
    ) -> StoredScanRun: ...

    def get(self, scan_id: str) -> StoredScanRun: ...

    def replace(
        self,
        run: ScanRun,
        *,
        expected_revision: int,
    ) -> StoredScanRun: ...

    def list_runs(
        self,
        *,
        limit: int = 100,
        after_scan_id: str | None = None,
    ) -> ScanRunPage: ...

    def close(self) -> None: ...

    def __enter__(self) -> "SQLiteScanRunRegistry": ...
    def __exit__(self, *args: object) -> None: ...
```

所有参数都要求精确类型；`bool` 不得冒充整数。`StoredScanRun`/`ScanRunPage` 必须冻结，
容器必须是 tuple。注册表不返回 SQLite connection/cursor、数据库绝对路径、原始 JSON
buffer 或可变内部对象。

## 3. 数据库路径、权限与 SQLite profile

### 3.1 路径门禁

`database_path` 必须是非空 `Path`，指向普通本地文件；禁止 `:memory:`、SQLite URI、NUL、
目录、FIFO/device/socket 和符号链接。直接父目录必须已存在、由当前有效用户拥有、是普通
目录，owner 具备 `rwx` 且 group/other 没有任何权限；注册表不递归创建目录。

新数据库先以 no-follow/exclusive 语义创建为 `0600`，已有数据库必须是当前用户拥有的
普通文件且 group/other 无权限。SQLite WAL/SHM 文件只能位于同一个私有父目录。实现不得
把配置路径或 SQLite 原错误写入异常、日志或公共结果。

这是可信部署配置边界，不宣称抵御拥有同一 OS 账号或 root 权限的攻击者。数据库路径
不得直接来自 HTTP 参数；容器部署应把它放在专用持久卷的私有目录。

### 3.2 固定连接设置

每个进程可创建自己的 registry instance，每个操作使用独立连接；连接固定：

```text
uri = false
isolation_level = None
PRAGMA journal_mode = WAL
PRAGMA synchronous = FULL
PRAGMA foreign_keys = ON
PRAGMA trusted_schema = OFF
PRAGMA busy_timeout = <busy_timeout_ms>
```

`busy_timeout_ms` 必须为非 `bool` 整数 `1..30_000`，默认 5,000。超时后不无限重试；锁
竞争稳定失败为 `registry_busy`。任何写操作都使用 `BEGIN IMMEDIATE`，完成校验后一次提交；
异常必须 rollback。不得拼接用户 SQL、加载 SQLite extension、使用 trigger 执行业务逻辑，
或把 JSON 当作 SQL。

## 4. 存储 Schema 与 canonical JSON

数据库 schema v1 只包含 metadata 与快照表，等价约束为：

```text
registry_metadata
  schema_name        = "openguard.scan-run-registry"
  schema_version     = 1

scan_runs
  scan_id                    TEXT PRIMARY KEY
  revision                   INTEGER NOT NULL CHECK revision >= 1
  idempotency_key            TEXT UNIQUE NULL
  idempotency_fingerprint    TEXT NULL
  created_at                 TEXT NOT NULL
  status                     TEXT NOT NULL
  contract_version           TEXT NOT NULL
  run_json                   BLOB NOT NULL
```

`PRAGMA user_version` 同时固定为 `1`，必须与 metadata 相等。只有零字节新文件可以初始化；
已有非空数据库若缺表、缺 metadata、版本不一致或版本未知，失败关闭，不自动建旁路表、不
drop/recreate、不猜迁移。未来迁移必须另立规格与备份/回滚门禁。

写入前必须要求 `type(run) is ScanRun`，再以当前 P0 模型完整重验证。唯一存储 bytes 为：

```python
payload = run.model_dump(mode="json")
canonical = json.dumps(
    payload,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
    allow_nan=False,
).encode("utf-8")
```

不追加 LF，不省略 `None`，不使用 pickle、`repr()`、平台 locale 或默认空白。读取时必须
严格 UTF-8 解码、拒绝重复 JSON key、`NaN`/`Infinity` 和非 object 顶层，再以
`ScanRun.model_validate()` 重载并重新 canonicalize；重编码 bytes 必须逐字节相等。
`scan_id`、`created_at`、`status`、`contract_version` 列必须与 JSON 对应字段逐字相等。

一行 JSON、P0 引用、summary 或镜像列任一损坏时，该操作整体 `registry_corrupt`，不得返回
部分对象。未知行级/数据库级版本为 `registry_schema_unsupported`。不得自动删除、修复、
跳过或把损坏 `ScanRun` 降级成空结果。

## 5. create 与幂等

### 5.1 初始快照

`create()` 只接受满足 P0 v0.1.1 且 `status=queued`、`stage=queued`、`progress=0`、
`started_at=None`、`finished_at=None` 的 `ScanRun`。首个实际插入的 revision 固定为 `1`。

若 `run.idempotency_key is None`，`idempotency_fingerprint` 也必须为 `None`；重复 `scan_id`
失败为 `registry_already_exists`，即使 JSON 相同也不解释为幂等。

若 `run.idempotency_key` 非空，fingerprint 必须是 64 位小写 SHA-256 hex。它由未来 A3 API
基于规范化创建请求/上传摘要产生；注册表只验证和比较摘要，不接收原请求、URL 凭据或
ZIP bytes。事务内先按 idempotency key 查询：

1. key 不存在：插入所给 queued run 与 fingerprint，返回 revision 1；
2. key 已存在且 fingerprint 相同：返回现存 `StoredScanRun`，不比较调用者新生成的 scan ID，
   不更新 JSON、不增加 revision；
3. key 已存在但 fingerprint 不同：`registry_idempotency_conflict`，不泄漏旧/新摘要。

key 与 fingerprint 的唯一约束和比较必须在同一个 `BEGIN IMMEDIATE` 事务完成；不得依赖
进程内 dict/lock。这样同一数据库上的不同进程/worker 竞争创建时最多插入一个任务。

## 6. replace、CAS 与状态单向性

`expected_revision` 必须是非 `bool` 正整数。事务内先读并完整验证现存行，再检查 revision；
不相等时 `registry_revision_conflict`。实际更新以
`WHERE scan_id=? AND revision=?` 执行且 rowcount 必须为 1，新 revision 精确 `old+1`。

若新旧 canonical JSON 逐字节相等，在 revision 匹配后作为幂等 no-op 返回旧对象和旧
revision，不写 WAL。不同 JSON 必须满足：

| 当前状态 | 允许下一状态 |
|---|---|
| `queued` | `running`, `cancelled` |
| `running` | `running`, `completed`, `partial`, `failed`, `cancelled` |
| `completed`, `partial`, `failed`, `cancelled` | 无 |

另有以下跨快照不变量：

- `contract_version`、`id`、`idempotency_key`、`created_at` 不变；
- `project.id/name/source_type/source/created_at` 不变；`project.revision` 与
  `project.root_digest` 只允许从 `None` 变为一个合法值，之后不可改变或清空；
- `progress` 不下降；stage 顺序固定为 P0 枚举声明顺序，不后退；
- `queued -> running` 必须设置一次 `started_at`，之后不变，且不早于 `created_at`；
- `status=running` 时 stage 只能是 `ingestion..report`，不得仍为 `queued` 或提前为
  `completed`；终态 partial/failed/cancelled 保留实际最后 stage；
- terminal 必须设置 `finished_at`，不早于 `started_at or created_at`；
- `completed` 必须 `stage=completed` 且 `progress=100`；
- 从 queued 直接 cancelled 保持 `stage=queued`、`progress=0`；
- 所有新快照仍必须独立通过 P0 引用、summary、errors、终态时间和枚举校验。

非法转换统一 `registry_transition_invalid`；不能通过把 status 留为 `running` 来倒退 stage、
progress、时间或已固定 project 身份。冲突/失败不增加 revision，不返回候选新快照。

## 7. get、list 与稳定顺序

`get()` 只接受合法 P0 `scn_` ID。不存在返回 `registry_not_found`；存在则完整执行第 4 节
读取验证，返回独立重载的 `ScanRun` 与 revision。

`list_runs()` 的 `limit` 必须为非 `bool` 整数 `1..100`，默认 100。结果顺序固定为
`created_at DESC, scan_id ASC`。`after_scan_id` 为上一页最后一个 ID；注册表先读取其不可变
`created_at`，再做 keyset 查询，不使用 offset。anchor 不存在为 `registry_not_found`。

查询 `limit+1` 行：有更多结果时只返回前 limit 条，`next_after_scan_id` 为返回末项 ID；
否则为 `None`。任何返回页中的损坏行使整页失败，不跳过。A3-0 没有 delete，因此已发出的
anchor 不会由本接口删除。分页不建立跨调用长事务快照：并发新建可能按其 `created_at`
出现在后页，也可能排在已消费 anchor 之前而不进入本次遍历；既有行不得重复。

## 8. 并发、重启恢复与关闭

- 同一 instance 的操作取得短生命周期 activity lease；不同 instance/进程的正确性完全
  依赖 SQLite transaction/unique/CAS，而非共享 Python lock。
- 多个写者可竞争；SQLite 在 `busy_timeout_ms` 内串行化，超时为 `registry_busy`。不得把
  busy 当作成功、吞掉更新或无限退避。
- 正常进程或解释器重启后，用同一路径重新构造 registry，已提交快照、revision、幂等
  key/fingerprint 必须保持；未提交事务由 SQLite rollback/WAL recovery 处理。
- 重启时 `queued`/`running` 保持原状态，不擅自变成 failed/cancelled。worker 认领、lease、
  stale-running 恢复和 exactly-once 执行是 A4 前置后续任务；本注册表只提供 durable CAS。
- `close()` 无活动操作时原子标为 CLOSED，释放自身连接/资源；可重复调用且第二次 no-op。
  context manager 必须在 `__exit__` 调用它。
- 调用者必须先停止新请求并等待活动操作结束。若 close 与活动操作并发，立即
  `registry_busy` 且实例保持 OPEN；不得中断/回滚另一个线程。成功 close 后任何 CRUD/list
  都返回 `registry_closed`，不得隐式 reopen。

SQLite commit 返回只证明本地数据库确认提交；不证明磁盘硬件、备份、复制或业务 side
effect exactly-once。调用外部 scanner 前后仍需 A4 的任务协议。

## 9. 稳定错误与脱敏

`ScanRegistryError.code` 只允许以下字面量；为避免实现间文案漂移，冻结
`error.args == (error.code,)`、`str(error) == error.code` 且无可遍历底层 cause：

| code | 条件 |
|---|---|
| `registry_invalid_argument` | 类型、ID、fingerprint、limit/revision 或 P0 初始对象非法 |
| `registry_not_found` | scan/分页 anchor 不存在 |
| `registry_already_exists` | 非幂等 scan ID 重复 |
| `registry_idempotency_conflict` | 同 key 不同 fingerprint |
| `registry_revision_conflict` | CAS revision 过期或 rowcount 不为 1 |
| `registry_transition_invalid` | 状态、stage、progress、时间或不可变字段逆行 |
| `registry_schema_unsupported` | 数据库/行 schema 版本未知或不一致 |
| `registry_corrupt` | SQLite integrity、JSON、镜像列或 P0 快照损坏 |
| `registry_path_invalid` | 路径种类、父目录、symlink 或非本地文件非法 |
| `registry_permission_denied` | owner/mode/open 权限不满足 |
| `registry_busy` | SQLite 锁超时或并发 close 时仍有活动操作 |
| `registry_closed` | 成功 close 后调用操作 |
| `registry_io_failed` | 其他受控 SQLite/OS 存储失败 |

Pydantic、JSON、SQLite 和 OS 异常都不得作为可遍历 cause 或文本输出到日志/CLI/未来
HTTP；稳定异常应从 `None` 抛出。日志最多
记录 code、操作名、scan ID 的单向摘要和计数；禁止数据库路径、SQL、JSON、source、
idempotency key/fingerprint、凭据、绝对路径、堆栈或记录正文。未来 A3 HTTP 层必须另行
冻结到 P0 公共错误的映射，不能直接透传这些内部 code。

错误优先级固定为：已关闭实例优先；其后是无须 I/O 即可发现的参数/P0 错误；进入事务后
依次为 busy、被触及行的 schema/corrupt、not-found、idempotency/revision conflict、状态
转换；未分类存储失败最后映射 `registry_io_failed`。rollback/close 若不能确认连接已回到
可复用状态，则该 instance 必须关闭并返回 `registry_io_failed`，不得继续提供可能脏读的
成功结果。

## 10. 精确验收矩阵

### 10.1 Positive（8）

| ID | 必须证明 |
|---|---|
| `POS-A3-REG-001` | queued `ScanRun` create/get 为 revision 1；BLOB 是冻结 canonical JSON，P0 重载逐字段相等。 |
| `POS-A3-REG-002` | 同 idempotency key + fingerprint 的跨 instance 重试返回同一原任务/revision，不写入第二行。 |
| `POS-A3-REG-003` | queued→running→running→completed 的 stage/progress/time 单向更新按 CAS 每次精确 +1，completed 为 100。 |
| `POS-A3-REG-004` | 相同 JSON + 正确 revision 是 no-op；revision 与 WAL-visible 内容均不变。 |
| `POS-A3-REG-005` | `created_at DESC, scan_id ASC` 的 1/100 边界和多页 keyset 无重复/遗漏，next anchor 正确。 |
| `POS-A3-REG-006` | close/reopen 或新进程模拟后，快照、revision、幂等映射逐字保持；queued/running 不被擅自改终态。 |
| `POS-A3-REG-007` | 两个独立 registry 并发使用同 expected revision 时恰一项更新成功，另一项 revision conflict；数据库有效。 |
| `POS-A3-REG-008` | queued 直接 cancelled、running 到 partial/failed/cancelled 的合法 P0 样例可保存；context close 幂等且重开可读。 |

### 10.2 Negative（16）

| ID | 必须证明 |
|---|---|
| `NEG-A3-REG-001` | 非精确 ScanRun、P0 校验失败、非法 scan ID/limit/bool/revision 均为脱敏 invalid argument，无写入。 |
| `NEG-A3-REG-002` | create 初态不是 queued/queued/0 或携带 started/finished 时间被拒绝。 |
| `NEG-A3-REG-003` | 无 idempotency key 却给 fingerprint、或有 key 缺/错 fingerprint 被拒绝；原文不泄漏。 |
| `NEG-A3-REG-004` | 非幂等重复 scan ID 为 already exists；同 key 不同 fingerprint 为 idempotency conflict。 |
| `NEG-A3-REG-005` | get/replace/list anchor 不存在稳定 not found，空结果仅用于真实空页。 |
| `NEG-A3-REG-006` | stale expected revision 及两个 writer 竞态 loser 均 revision conflict，不覆盖 winner。 |
| `NEG-A3-REG-007` | queued→completed/partial/failed、terminal→任意变化和 queued 内容变更均 transition invalid。 |
| `NEG-A3-REG-008` | running stage/progress 回退、completed 非 100/非 completed stage 被拒绝。 |
| `NEG-A3-REG-009` | scan/idempotency/created_at/project 固定字段变化，或 project revision/root digest 改写/清空被拒绝。 |
| `NEG-A3-REG-010` | started/finished 缺失、改变、早于前序时间，或新快照 P0 引用/summary/error 不合法被拒绝。 |
| `NEG-A3-REG-011` | 手工注入非 UTF-8、重复 key、NaN、非 object、非 canonical bytes 或 P0 无效 JSON，get/list/replace 均 corrupt 且无部分返回。 |
| `NEG-A3-REG-012` | metadata/user_version/行 contract 版本未知、缺失或不一致均 schema unsupported；数据库不被重建。 |
| `NEG-A3-REG-013` | memory/URI、目录/FIFO、DB/父目录 symlink、非私有 mode 或错误 owner 在 SQL 前按 path/permission code 拒绝。 |
| `NEG-A3-REG-014` | 持有外部写锁超过 busy timeout 时返回 registry busy、事务回滚；释放后实例仍可用。 |
| `NEG-A3-REG-015` | 活动操作期间 close 为 busy 且保持 OPEN；成功 close 后所有操作 closed，重复 close no-op。 |
| `NEG-A3-REG-016` | SQLite/OS/Pydantic 故障只暴露固定 code/message；stderr、日志与异常不含路径、SQL、JSON、key、摘要、source 或 traceback。 |

Terra 可参数化用例，但每个 ID 必须可检索。Luna 必须用第二个 SQLite connection、真实
临时 POSIX 权限/链接和手工 SQL 损坏注入独立断言；不得复用 Terra helper 生成 expected
canonical bytes、状态转换或错误 code。

## 11. 实现、独立验证与证据门禁

Terra 实现只应新增/修改：

```text
backend/app/persistence/__init__.py
backend/app/persistence/scan_registry.py
tests/unit/test_a3_scan_registry.py
backend/README.md
docs/05-ai-assistance-log.md
docs/coordination/AGENT_WORKLOG.md
```

Luna 独立验证只应新增/修改：

```text
tests/security/test_a3_scan_registry_independent.py
tests/security/README.md
docs/05-ai-assistance-log.md
docs/coordination/AGENT_WORKLOG.md
```

双方不得修改 P0/Schema/sample、本规格、PROJECT_PROGRESS 或对方测试；不得为了过测试
自动修复损坏 DB、放宽状态或回显底层错误。本实现只用 Python 3.12 标准库 `sqlite3/json`，
不新增第三方依赖或 third_party 台账项。

Root 验收至少运行 Terra 8 POS/16 NEG、Luna 逐 ID 独立测试、P0 46 项、全量 pytest、Schema
等值、compileall、`git diff --check`、权限/路径/敏感信息检查，并用关闭后新 instance 证明
重启恢复。只有 Terra 实现、Luna 独立验证、Sol 无开放 P0/P1、Root 绑定不可变提交与运行
profile 后，才可申请一个有界 evidence ID。

本设计当前没有运行 evidence，状态必须保持 `IMPLEMENTATION_UNVERIFIED`。未来最多可证明
“单机 POSIX SQLite 上完整 P0 ScanRun 快照的持久、幂等与 CAS 注册表纵切”；不得据此声称
FastAPI、worker、Pipeline、exactly-once side effect、多机容灾、B2-B7、前端或完整参赛作品
已经完成。

## 12. CLOSED AMENDMENT（2026-09-02）

`FINAL-A3-001` 已关闭：实现现对全部非 SQLite 内部 `sqlite_master` 对象执行严格 allowlist，
只接受 `registry_metadata` 与 `scan_runs` 两张冻结用户表，拒绝额外 table、view、trigger 和
显式/额外 index。Terra 已补实现回归；Luna 用原始额外 table/view/`AFTER INSERT` revision
trigger 探针独立确认均为 `registry_schema_unsupported`，移除对象后合法库保持 revision 1。
冻结 `8 POS + 16 NEG`、P0 v0.1.1、公共接口与错误码均未改变，当前无开放 P0/P1。

候选 evidence `EVD-A3-DURABLE-SCAN-REGISTRY-001` 裁决为
`APPROVED-PENDING-ROOT-BINDING`。Sol 复跑 A3 实现与独立测试 `77 passed`；Root 报告全量
`501 passed`、P0 `46 passed`、Schema 等值、compileall 与 diff 门禁通过。Root 仍须绑定不可变
提交、CPython/SQLite/OpenGuard 版本、运行 profile、完整命令与输出摘要后，才能把该 ID 写成
正式运行 evidence。

批准范围严格限于本机 macOS/POSIX、单机本地 SQLite、完整 P0 `ScanRun` 快照的 canonical
持久化、幂等、revision/CAS、状态单向性、分页、重启读取、私有路径和损坏失败关闭纵切。
不包含 FastAPI/HTTP、Git/ZIP 创建请求、worker/A4 Pipeline、Linux isolation、TrustedEgress、
多机/高可用/灾备、exactly-once 外部副作用、B2-B7、前端、Bench 或完整竞赛作品。
