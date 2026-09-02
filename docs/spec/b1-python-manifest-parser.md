# B1-1 Python Manifest Parser 设计门禁

- 版本：`v0.1.0`
- 状态：`FROZEN_DESIGN_BASELINE / LOCAL_CANDIDATE (APPROVED-PENDING-ROOT-BINDING)`
- 日期：2026-09-02
- 设计负责人：Sol
- 后续实现负责人：Terra
- 后续独立验证负责人：Luna
- 依赖契约：P0 `v0.1.1`、A2-2 `ReadOnlyScanSession`

## 1. 结论与非结论

B1-1 冻结为一个可信、非执行性的仓库内 parser：它只消费 A2-2 会话暴露的 `inventory` 属性与 `read_bytes()` 方法，发现并解析 `requirements*.txt` 和 `pyproject.toml`，输出不可变、确定性、可追溯的中间 DTO。它不得获得 materialized workspace、真实路径、文件描述符或网络能力。

本文件是实现门禁，不是运行时证明。本轮不修改 backend、测试、P0 Schema/sample 或项目进度，不批准 B1 evidence，不声明 JavaScript/lockfile、许可证识别、Web、Git、TrustedEgress 或 Linux 隔离已经完成。

## 2. 安全能力边界

### 2.1 唯一允许的输入

parser 的公开入口等价于：

```python
def parse_python_manifests(session: ReadOnlyScanSession) -> PythonManifestParseResult: ...
```

实现只可：

1. 读取 `session.inventory.entries` 中的 `relative_path`、`size_bytes`、`sha256`；
2. 对已在 inventory 中且被本规格选中的路径调用 `session.read_bytes(relative_path, max_bytes=262_144)`；
3. 使用纯内存、确定性解析逻辑产生 DTO。

调用方创建会话时必须请求 `ScanReadLimits(single_file_max_bytes=262_144, total_max_bytes=4_194_304)`。若服务端上限更低，沿用 A2-2 的失败语义，不得抬高或绕过服务端上限。

### 2.2 明确禁止

- 不接收、返回或推导 materialized workspace/主机绝对路径；不使用 `open()`、`Path`、`os.walk`、`glob` 或文件描述符反射读取目标树。
- 不执行或导入目标代码、构建后端、插件、marker 环境、requirements 指令或配置脚本。
- 不运行 shell、包管理器、VCS 客户端或安装命令；不解析 wheel/sdist，也不创建虚拟环境。
- 不联网、解析 DNS、探测 URL、克隆仓库或验证远端对象是否存在。
- 不把进程内 parser 描述成不可信代码 sandbox；A2 的 TrustedEgress/Linux 隔离门禁不因此关闭。
- 不把 traceback、异常原文、绝对路径、URL 凭据、查询串、索引地址或整份 manifest 放入 DTO、日志或 P0 错误。

A2-2 抛出的 `IngestionSecurityError` 必须原样上抛；parser 不得把 `scan_session_expired`、完整性、线程、重入、路径白名单或读取配额失败改写成“部分成功”。

## 3. Manifest 发现与确定性顺序

只遍历 inventory 的 sealed regular-file 条目，不访问目录：

- `pyproject.toml`：basename 必须 ASCII 大小写精确相等；
- `requirements*.txt`：basename 必须以小写 ASCII `requirements` 开头、以 `.txt` 结尾，`*` 可为空；
- 不支持 `requirements.in`、`Pipfile`、`setup.py`、`setup.cfg`、lockfile 或大小写变体。

若 `relative_path` 的任一 POSIX segment 与下列名称大小写精确相等，则忽略：

```text
.git  .hg  .svn  .venv  venv  __pycache__  site-packages  node_modules
```

不忽略 `vendor`、`build`、`dist` 或任意未列出的业务目录，避免漏掉 monorepo 中有意提交的 manifest。

候选路径按 `relative_path.encode("utf-8")` 升序读取；同一路径只读一次。输出 manifest、依赖、证据和诊断分别使用第 7 节排序键，不能依赖 dict/set、ZIP central directory、TOML 表或输入系统的自然顺序。路径不做 Unicode NFC/NFD 合并、不做大小写折叠；A2 inventory 是路径身份的唯一事实源。

资源上限：

| 资源 | 冻结上限 | 处置 |
|---|---:|---|
| 候选 manifest | 64 | 读取前整体失败 `python_manifest_limit_exceeded` |
| 单 manifest | 262,144 bytes | 读取前整体失败 `python_manifest_limit_exceeded` |
| 候选总字节 | 4,194,304 bytes | 读取前整体失败 `python_manifest_limit_exceeded` |
| requirements 拼接后单逻辑行 | 8,192 UTF-8 bytes | 该 manifest 诊断并跳过，其他 manifest 继续 |
| 接受的依赖声明总数 | 4,096 | 整体失败 `python_manifest_limit_exceeded` |
| 单声明的脱敏原文/摘录 | 1,000 Unicode code points | 截断并加固定 `…`，不得截入 secret |

候选数量、单文件大小和候选总字节必须仅用 inventory 元数据在第一次 `read_bytes()` 前预检，避免“先读前 N 个”的顺序依赖。负数、不一致或非预期 inventory 元数据视为内部不变量失败。

## 4. `requirements*.txt` 冻结语义

### 4.1 词法处理

1. 字节必须严格解码为 UTF-8；不猜测 locale、BOM 以外编码或替换坏字符。UTF-8 BOM 只允许出现在文件开头并被移除。
2. CRLF/LF 统一成逻辑换行；裸 CR 也视为换行。记录每个逻辑声明覆盖的 1-based `start_line/end_line`。
3. 未被转义的行尾反斜杠连接下一物理行；连接后 UTF-8 长度不得超过 8,192 bytes。文件末尾悬空反斜杠为无效声明。
4. 空白行和首个非空白字符为 `#` 的整行注释忽略。行内 `#` 只有在不位于引号内、且前一字符为空白时才开始注释；URL fragment 不得被误删。
5. 先抽取尾随 hash 选项，再将剩余单个声明交给固定版本的 `packaging.requirements.Requirement`。parser 不实现另一套宽松 PEP 508 文法。

### 4.2 支持、拒绝与警告

| 语法 | 冻结处置 | 规范化结果 |
|---|---|---|
| `name`、PEP 440 specifier | 支持 | 名称 PEP 503 canonical；specifier 子项按文本升序 |
| extras | 支持 | 每项 canonical 后去重并按 UTF-8 bytes 排序 |
| environment marker | 支持但绝不求值 | 保存固定 `packaging` 版本产生的 canonical marker 文本 |
| `name @ https://...` | 条件支持 | 仅通过 4.3 安全门禁后保存为 `direct_url` |
| `name @ git+https://...` | 条件支持 | 仅通过 4.3 安全门禁后保存为 `vcs`，不克隆 |
| 一个或多个 `--hash=sha256:<64hex>` | 支持 | 小写、去重、排序；只证明声明携带 hash，不证明内容 |
| `-r`/`--requirement` include | 拒绝该行并诊断 | 不跟随、不读取被引用文件 |
| `-c`/`--constraint` constraint | 拒绝该行并诊断 | 不改变任何已解析声明 |
| `-e`/`--editable` | 拒绝该行并警告 | 不推断本地包、名称或版本 |
| `--index-url`、`--extra-index-url`、`--find-links`、其他 option | 拒绝该行并警告 | option 值不进入 DTO/日志 |
| 无显式包名的 URL/VCS/本地路径 | 拒绝该行并诊断 | 不从 URL、目录或仓库名猜包名 |
| PEP 508 解析失败或未知尾随 token | 拒绝该行并诊断 | 不做容错猜测 |

同一 manifest 中一行失败不阻止其他合法行进入结果，因此结果为 `partial`。被拒绝的行不得生成依赖 DTO 或 EvidenceDraft。

### 4.3 Direct URL/VCS 安全门禁

命名引用必须同时满足：

- URL 无 ASCII control、反斜杠、空 hostname、username/password 或 query；
- scheme 只能是 `https` 或 `git+https`，明确拒绝 `http`、`file`、`ssh`、`git`、`git+ssh` 及本地/相对路径；
- hostname 使用解析器的 ASCII lower-case 结果；不得做 DNS、私网或可达性判断，因为根本不发请求；
- fragment 只能包含一个可选 `subdirectory=<安全相对 POSIX 路径>` 和零或多个 `sha256=<64hex>`，其他 fragment key 拒绝；
- `subdirectory` 解码后不得为空、绝对、包含 `.`/`..` segment、反斜杠、NUL 或控制字符；
- 保存的引用必须是无凭据、无 query、fragment 已排序的 canonical 文本，最大 1,000 code points。

`https` 引用后续可作为候选 P0 `source_url`；`git+https` 仅留在 manifest evidence 中，不能直接写入 P0 的 HTTPS-only `source_url`。两者均不能产生版本、许可证、purl 或“已验证来源”结论。

## 5. `pyproject.toml` 冻结语义

使用 Python 3.12 标准库 `tomllib` 严格解析 UTF-8；不得加载 build backend、tool plugin 或目标代码。

| TOML 字段 | 决策 | scope/group | field locator |
|---|---|---|---|
| `project.dependencies` | 支持 string array | `runtime`/`None` | `project.dependencies[i]` |
| `project.optional-dependencies.<group>` | 支持 string array | `optional`/canonical group | `project.optional-dependencies.<encoded-group>[i]` |
| `build-system.requires` | 支持 string array | `build`/`None` | `build-system.requires[i]` |

数组中每个字符串必须是单个 PEP 508 requirement，并复用 4.2/4.3 的规范化与 URL 门禁；pyproject 字符串内不支持 requirements option 或 `--hash`。`build-system.requires` 被纳入，是因为构建依赖也是应披露的第三方软件，但必须与 runtime 分 scope，且绝不执行。

以下情况必须稳定诊断：

- TOML 语法错误、重复 key、目标字段不是预期 table/array/string；
- `project.dynamic` 包含 `dependencies` 或 `optional-dependencies`；静态声明仍可解析，但结果为 `partial`；
- 存在 `dependency-groups`、`tool.poetry`、`tool.pdm` 或 `tool.hatch` 的依赖声明；v0.1.0 不解析，结果为 `partial`；
- optional group 名包含控制字符、为空或 canonical 后冲突；相关组跳过，不猜测合并。

`tomllib` 不提供 token 行号，因此 pyproject EvidenceDraft 的 `start_line/end_line` 为 `None`，但 `field_locator` 必须精确到数组索引；不能用脆弱的二次正则伪造行号。group 在 field locator 中按 UTF-8 percent-encoding 编码非 `[A-Za-z0-9._-]` 字节。

## 6. 冻结 DTO

实现使用 `@dataclass(frozen=True)`、tuple 与字符串 enum；不得直接返回可变 dict/list。

```python
class ManifestKind(str, Enum):
    REQUIREMENTS = "requirements"
    PYPROJECT = "pyproject"

class DependencyScope(str, Enum):
    RUNTIME = "runtime"
    OPTIONAL = "optional"
    BUILD = "build"

class DependencySourceKind(str, Enum):
    INDEX = "index"
    DIRECT_URL = "direct_url"
    VCS = "vcs"

class ParseStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"

@dataclass(frozen=True)
class ManifestEvidenceDraft:
    manifest_path: str
    field_locator: str | None
    start_line: int | None
    end_line: int | None
    content_sha256: str
    excerpt: str

@dataclass(frozen=True)
class ParsedManifest:
    relative_path: str
    kind: ManifestKind
    size_bytes: int
    content_sha256: str
    status: ParseStatus

@dataclass(frozen=True)
class PythonDependencyDeclaration:
    normalized_name: str
    declared_name: str
    version_specifier: str | None
    marker: str | None
    extras: tuple[str, ...]
    direct_reference: str | None
    source_kind: DependencySourceKind
    scope: DependencyScope
    group: str | None
    hashes: tuple[str, ...]
    raw_declaration: str
    source_manifest: str
    evidence: tuple[ManifestEvidenceDraft, ...]

@dataclass(frozen=True)
class ParserDiagnostic:
    code: str
    severity: str  # "warning" | "error"
    manifest_path: str | None
    field_locator: str | None
    start_line: int | None
    end_line: int | None
    message: str  # 固定模板，不拼接不可信原文或异常文本

@dataclass(frozen=True)
class PythonManifestParseResult:
    schema_version: str  # 固定 "b1-python-manifest/v1"
    status: ParseStatus
    manifests: tuple[ParsedManifest, ...]
    dependencies: tuple[PythonDependencyDeclaration, ...]
    diagnostics: tuple[ParserDiagnostic, ...]
```

`raw_declaration` 只对已经通过安全门禁的声明保留：折叠空白、移除注释、canonical hash/URL、最多 1,000 code points。它不是原文件转储。`declared_name` 只保留 parser 接受的包名 token；`normalized_name` 使用 `packaging.utils.canonicalize_name()`。重复合并后，`source_manifest`/`declared_name` 取所有对应证据中的 UTF-8 byte 最小值，`evidence` 仍保留全部来源；canonical `raw_declaration` 必须由字段重建，不能受原空白差异影响。

## 7. 规范化、重复、冲突与排序

声明 identity 为：

```text
(normalized_name, scope, group, extras, version_specifier,
 marker, source_kind, direct_reference, hashes)
```

完全相同 identity 的声明合并成一个 DTO，所有 EvidenceDraft 去重后保留；添加 `dependency_duplicate` warning。不得因重复丢弃来源位置。

相同 `(normalized_name, scope, group)` 的不同 identity 均保留：

- 不同 exact `==` pin，或不同 direct reference：`dependency_declaration_conflict` error；
- 其他不同 specifier/marker/extras/hash：`dependency_multiple_constraints` warning；
- 不同 scope 或 optional group 不判冲突。

v0.1.0 不求解 PEP 440 可满足性，不把多个范围自动求交，也不让后出现项覆盖前项。

稳定排序键：

- manifest：`relative_path` UTF-8 bytes；
- EvidenceDraft：`(manifest_path bytes, field_locator or "", start_line or 0, end_line or 0, content_sha256)`；
- dependency：identity 中 enum 使用 `.value`、`None` 使用空 bytes、其余字符串/tuple 使用 UTF-8 bytes 序；
- diagnostic：`(manifest_path or "", start_line or 0, field_locator or "", code, severity)`。

所有 optional group、extra、hash 和 specifier 子项先 canonicalize、去重、排序。相同输入 inventory/root digest 与相同 parser/`packaging` 版本必须产生逐字段相等结果。

## 8. 部分成功与稳定错误

### 8.1 可恢复的 per-manifest/声明诊断

固定 diagnostic code：

```text
manifest_encoding_invalid
manifest_toml_invalid
manifest_field_invalid
manifest_logical_line_too_long
requirement_invalid
requirement_include_unsupported
requirement_constraint_unsupported
requirement_editable_unsupported
requirement_option_unsupported
requirement_unnamed_reference_unsupported
requirement_reference_unsafe
requirement_hash_invalid
pyproject_dynamic_dependencies_unsupported
pyproject_tool_table_unsupported
dependency_duplicate
dependency_declaration_conflict
dependency_multiple_constraints
```

出现任一 warning/error 时结果 `status="partial"`；无诊断时为 `complete`。坏 manifest 不阻止其他 manifest，但坏 manifest 自身不产生猜测结果。即使全部 manifest 都坏，也返回 `partial` 空依赖和稳定诊断。

### 8.2 整体失败

parser 自有整体失败只允许：

| P0 code | reason | 场景 |
|---|---|---|
| `scanner_failed` | `python_manifest_limit_exceeded` | 第 3 节任一整体配额超限 |
| `scanner_failed` | `python_manifest_parser_unavailable` | 锁定 `packaging` 缺失或版本不等于 26.3 |
| `scanner_failed` | `python_manifest_parser_failed` | 内部不变量或未分类实现错误 |

错误 message 使用固定、可本地化模板；不得包含 Python exception、manifest 内容、URL、路径以外的主机信息或堆栈。A2-2 已定义错误优先级与 service poison；其错误原样传播并优先于 parser 部分结果。

## 9. Evidence 与 P0 v0.1.1 映射

### 9.1 本纵切不直接实例化 P0

B1-1 parser 不直接创建 `Component`/`Evidence`。原因是 parser 不拥有 `scan_id`、ID factory、UTC `observed_at`、producer/version 注入、跨 parser merge 或 ScanRun 错误仲裁。直接创建 P0 会把仓库语法解析与运行级身份/时间耦合。

后续 mapper 必须消费冻结 DTO，并遵守：

| DTO | P0 映射 |
|---|---|
| 每个 EvidenceDraft | `Evidence(kind="manifest_field")` |
| `manifest_path` + `field_locator` | `locator`；requirements 可用 path + lines，pyproject 使用 `path:field_locator` |
| `start_line/end_line` | requirements 精确映射；pyproject 保持 `None` |
| `content_sha256` | `content_sha256`，必须等于 inventory seal |
| `excerpt` | 已脱敏且不超过 P0 1,000 字符 |
| producer | 由 mapper 注入固定 `manifest_parser` 与实现版本 |
| declaration | `Component(component_type="library", ecosystem="pypi", detected_by="manifest_parser")` |

Component `name` 使用 `normalized_name`。只有唯一、无 wildcard 的 `==<PEP440-version>` 才可把 canonical `Version` 写入 P0 `version`；范围、`===`、marker、direct/VCS 或冲突声明的 version 都为 `None`。`evidence_ids` 包含全部合并证据。

只有通过 4.3 的普通 `https` direct URL 可成为候选 `source_url`；`git+https` 只保留在 evidence。不得从包名或 URL 猜测 purl、许可证、版权方、下载状态、resolved version、安装状态或漏洞状态。语法验证只能支持“声明被观察到”，不能支持“依赖已安装/可获取/安全/合规”。

## 10. 恶意输入与泄漏防护

- 先以 inventory size 做 O(1) 配额预检，再解码；逻辑行、声明数、摘录长度均有硬上限。
- marker 只解析/规范化，不使用当前主机环境求值；不同运行主机输出相同。
- TOML 不支持动态 provider；requirements include/constraint/editable/option 不触发任何能力扩张。
- URL userinfo/query/未知 fragment 失败关闭；option 行的值不进入诊断。日志只记录 code、计数和 root digest 等非敏感元数据。
- diagnostic message 使用常量，不拼接 `repr(error)`、原始行或 TOML exception；debug 日志也遵守同一边界。
- manifest path 只能来自 A2 inventory 的相对路径；P0 mapper 复用 P0 locator 校验，不允许本机绝对路径。
- 对 hash、URL、name、marker、group 的规范化不得使用灾难性回溯正则；优先有限状态扫描、`urllib.parse` 和固定 `packaging`/`tomllib`。
- 测试不得访问网络、安装目标依赖或执行 fixture 代码；恶意 fixture 使用动态临时字节或可合法再分发的小文本。

## 11. 第三方依赖门禁

`tomllib`、`urllib.parse`、hashing、排序与 percent-encoding 使用 Python 3.12 标准库。完整 PEP 508/PEP 440/marker 语法采用直接依赖 `packaging==26.3`：

- 必要性：手写同等文法容易对 URL、marker、extras 和 specifier 产生接受差异或安全绕过；`packaging` 是 PyPA 的专用解析实现。
- 锁定：必须精确 `==26.3`，运行时检查版本；升级需重新跑本规格全部 POS/NEG 并记录规范化 diff。
- 来源/兼容：只从官方 PyPI 获取；Python 要求 `>=3.9`，兼容本仓库 Python 3.12。
- 许可证：上游声明 `Apache-2.0 OR BSD-2-Clause`；引入前由 Luna 在 `third_party/README.md` 登记版本、官方来源、许可证、使用方式、自研边界与开放方式，Root/Sol 复核上游 LICENSE/NOTICE 义务。
- 变更面：Terra 只在实现提交中改 `backend/pyproject.toml`；本设计轮不下载、不安装、不改 lock/台账。

无第三方安全替代仅允许“reduced profile”：标准库解析 TOML，requirements/pyproject 只接受 canonical bare name，任何 extras/specifier/marker/direct URL/VCS 都诊断拒绝。该 profile 不能满足本 B1-1 完整验收，不能标记 COMPLETE；生产路径应以 `python_manifest_parser_unavailable` 失败关闭，不能静默降级。

## 12. 精确验收矩阵

### 12.1 Positive（12）

| ID | 必须证明 |
|---|---|
| `POS-B1-PY-001` | 只从 inventory 发现精确范围，忽略冻结目录，UTF-8 byte 顺序稳定 |
| `POS-B1-PY-002` | requirements name/specifier/extras/marker canonical，marker 未求值 |
| `POS-B1-PY-003` | 注释、continuation 与 1-based 起止行证据正确 |
| `POS-B1-PY-004` | 命名安全 HTTPS direct reference 被接受但不访问 |
| `POS-B1-PY-005` | 命名 `git+https` VCS 被接受为 evidence-only 且不克隆 |
| `POS-B1-PY-006` | 多个 sha256 hash 小写、去重、排序且不声称已验证 artifact |
| `POS-B1-PY-007` | `project.dependencies` 产生 runtime 声明与精确 field locator |
| `POS-B1-PY-008` | optional dependency group canonical、scope 隔离、顺序稳定 |
| `POS-B1-PY-009` | `build-system.requires` 产生 build scope 且不加载 backend |
| `POS-B1-PY-010` | exact duplicate 合并声明并保留全部排序证据 |
| `POS-B1-PY-011` | 一个坏 manifest 与一个好 manifest 返回确定性 partial 结果 |
| `POS-B1-PY-012` | 内存 ZIP → A2 session → parser 纵切无真实路径/网络/执行，重复运行逐字段相等 |

### 12.2 Negative（24）

| ID | 必须证明 |
|---|---|
| `NEG-B1-PY-001` | 非 UTF-8 内容只产生固定脱敏诊断 |
| `NEG-B1-PY-002` | 坏 TOML/重复 key 不泄漏 parser exception |
| `NEG-B1-PY-003` | pyproject 目标字段类型错误不被字符串化猜测 |
| `NEG-B1-PY-004` | 畸形 PEP 508 声明不产生 DTO |
| `NEG-B1-PY-005` | include 指令不跟随或读取引用路径 |
| `NEG-B1-PY-006` | constraint 指令不改变其他声明 |
| `NEG-B1-PY-007` | editable/本地路径不执行、不猜包名 |
| `NEG-B1-PY-008` | index/find-links/未知 option 的值不进入结果或日志 |
| `NEG-B1-PY-009` | 无显式名称的 URL/VCS 被拒绝 |
| `NEG-B1-PY-010` | `http/file/ssh/git+ssh` 与相对/绝对本地引用被拒绝 |
| `NEG-B1-PY-011` | URL 凭据、query、控制字符、未知 fragment 被拒绝且不回显 |
| `NEG-B1-PY-012` | 非 sha256、错误长度或畸形 hash 被拒绝 |
| `NEG-B1-PY-013` | marker 在不同主机环境下不求值且输出一致 |
| `NEG-B1-PY-014` | manifest 数量超过 64 时读取前整体失败 |
| `NEG-B1-PY-015` | 单 manifest 超过 262,144 bytes 时读取前整体失败 |
| `NEG-B1-PY-016` | 候选总字节超过 4,194,304 时读取前整体失败 |
| `NEG-B1-PY-017` | 逻辑行超过 8,192 bytes 时该 manifest partial、无截断解析 |
| `NEG-B1-PY-018` | 接受声明超过 4,096 时整体失败且无截断结果 |
| `NEG-B1-PY-019` | exact pin/direct reference 冲突均保留并产生固定 conflict |
| `NEG-B1-PY-020` | dynamic/tool-specific dependency table 不执行 provider 且被诊断 |
| `NEG-B1-PY-021` | parser 无法获得真实路径、fd、workspace 或会话私有属性 |
| `NEG-B1-PY-022` | traceback、绝对路径、secret-like option/URL 内容不泄漏到 DTO/日志/错误 |
| `NEG-B1-PY-023` | monkeypatch subprocess/socket/open/import target 后确认零执行、零网络、零旁路读取 |
| `NEG-B1-PY-024` | `packaging` 缺失/错版及 A2 session 过期分别稳定失败，不返回部分结果 |

独立验证不得只复用 Terra helper 生成期望值；必须对冻结 DTO 字面值、稳定 error reason、调用次数和副作用 sentinel 作外部断言。

## 13. 后续所有权与可复现命令

### 13.1 Terra 实现面

允许修改：

```text
backend/app/scanners/__init__.py
backend/app/scanners/python_manifest.py
backend/pyproject.toml
backend/README.md
tests/unit/test_b1_python_manifest_parser.py
docs/05-ai-assistance-log.md
docs/coordination/AGENT_WORKLOG.md
```

Terra 不得修改本规格、Luna 独立测试、P0 Schema/sample 或 `PROJECT_PROGRESS.md`。实现前必须让 Luna/Root 完成 `packaging==26.3` 台账登记与许可复核；若依赖门禁未完成，停在 `python_manifest_parser_unavailable`，不得换用未审依赖。

### 13.2 Luna 独立验证面

允许修改：

```text
tests/security/test_b1_python_manifest_parser_independent.py
tests/fixtures/b1-python-manifest/
tests/security/README.md
third_party/README.md
docs/05-ai-assistance-log.md
docs/coordination/AGENT_WORKLOG.md
```

Luna 不得修改 backend、Terra unit、本规格、P0 或项目进度；不得为了过测试放宽冻结断言。fixture 必须小型、文本化、注明来源/自建状态，无密钥、无真实成员路径、无网络获取步骤。

### 13.3 Root 集成验收

在仓库根目录使用项目既有 Python 环境执行：

```bash
PYTHONPATH=backend python -m pytest -q tests/unit/test_b1_python_manifest_parser.py
PYTHONPATH=backend python -m pytest -q tests/security/test_b1_python_manifest_parser_independent.py
PYTHONPATH=backend python -m pytest -q
PYTHONPATH=backend python -m pytest -q tests/unit/test_p0_contract.py
PYTHONPATH=backend python -m compileall -q backend/app tests
git diff --check
git diff --name-only
```

另外必须运行一个真实内存 ZIP → A2 `run_scan_session` → parser 的无磁盘路径暴露纵切，并检查：两次结果逐字段相等、`read_bytes` 仅命中已发现候选且每路径一次、无 socket/subprocess/open 旁路、P0 Schema/sample/export 等值、没有本机绝对路径或凭据进入改动。

## 14. 放行条件

只有以下全部成立，Sol 才可把状态从 `IMPLEMENTATION_UNVERIFIED` 改为实现候选：

1. Terra 12 POS + 24 NEG 的实现侧对应项全绿；
2. Luna 以独立断言覆盖全部 36 个 ID，且没有修改上游实现；
3. `packaging==26.3` 版本、官方来源、许可证与使用边界已登记并复核；
4. A2/P0/Schema 回归、真实内存 ZIP 纵切、compileall、diff 与敏感信息检查通过；
5. evidence 绑定不可变提交、运行 profile 与复现命令；不得把设计、mock 或单元测试计数冒充产品运行证据。

任何一项未满足时，B1-1 保持 `IMPLEMENTATION_UNVERIFIED`，Root 不得更新为“已完成”。

## 15. 2026-09-02 最终审计 AMENDMENT（BLOCKED）

本节保留 v0.1.0 冻结契约，不改写前文。Sol 在 Python 3.12.13、`packaging==26.3` 的本地 profile 原样复跑 Luna `56 passed`、Terra `38 passed`、全量 `269 passed`、P0 `46 passed`，并确认 Schema export 等值、compileall、diff、尾随空白、敏感信息/本机绝对路径及 P0 受保护路径检查通过。官方 PyPI 与已安装 METADATA 均确认 `packaging 26.3`、Python `>=3.9`、`Apache-2.0 OR BSD-2-Clause`；仓库锁版和第三方台账一致。

绿灯之外的只读内存探针复现以下 P1，因此不得提升为实现候选，也不批准候选 evidence ID：

| Finding | 冻结要求 | 可复现输入与实际输出 | 影响 |
|---|---|---|---|
| `P1-B1-FINAL-001` | 4.1 只把 CRLF/LF/裸 CR 作为行结束 | `a==1<U+2028>b==2` 实际产生依赖 `a,b` | Unicode line separator 被 `str.splitlines()` 当成两条声明，改变声明边界与行证据，而非作为单条无效 PEP 508 输入拒绝 |
| `P1-B1-FINAL-002` | 第 3/6 节限制 canonical raw/摘录最多 1,000 code points | 1,001 字符合法 name 实际得到 `len(raw_declaration)==1001` | DTO 硬上限未执行；长输入可越过冻结输出/披露边界 |
| `P1-B1-FINAL-003` | 4.2 extras canonical 后去重排序 | `a[x_y,x-y]` 实际得到 `('x-y', 'x-y')` | canonical collision 未去重，污染 raw、identity 与后续 Component evidence 合并 |
| `P1-B1-FINAL-004` | 7.2 对 identity 逐字段排序，`None` 映射空 bytes | `a` 与 `a>=1` 实际顺序为 `>=1,None` | `_merge()` 使用 `repr(identity)`，与冻结稳定序列化顺序相反 |
| `P1-B1-FINAL-005` | 4.3 保存有效、确定性的 HTTPS canonical reference | `a @ https://[::1]/pkg` 被 complete 接受并保存为 `https://::1/pkg` | IPv6 brackets 丢失，生成畸形 direct reference，后置 P0/source 映射不可依赖 |

另有一项 P2 复现说明债：13.3 的 `tests/unit/test_p0_contract.py` 当前不存在；本次真实 46 项命令为 `tests/unit/test_p0_domain_models.py`。历史命令保留，上述真实路径是后续复测的权威 AMENDMENT。

关闭条件：Terra 只修上述五项并补实现侧回归；Luna 在不改上游实现的前提下增加独立断言，分别映射既有 `NEG-B1-PY-004/022`、`POS-B1-PY-002/012` 与 `NEG-B1-PY-011`，不增加或重写冻结 12/24 ID；Root 重跑本节完整 profile 后交 Sol 复审。未关闭前，既有通过结果只能证明当前已覆盖样本，不得绑定 B1 候选 evidence。

本审计不外推 JavaScript/TypeScript、lockfile、P0 mapper、许可证识别/结论、Web/API、Git、Linux isolation、TrustedEgress、完整 ZIP corpus、OpenGuard-Bench、报告导出或 A2 总门禁。

## 16. 2026-09-02 CLOSED AMENDMENT（LOCAL CANDIDATE）

本节追加关闭第 15 节五项 P1，不改写其首轮失败证据。Sol 只读复核当前 parser、Terra unit 与 Luna 独立断言，并在 Python 3.12.13、`packaging==26.3` 的本地 macOS/POSIX profile 原样复跑；未发现新的 P0/P1。

| Finding | 当前关闭证据 |
|---|---|
| `P1-B1-FINAL-001` | `re.split(r"\r\n|\n|\r", text)` 仅承认冻结物理行结束；`a==1<U+2028>b==2` 稳定为 `requirement_invalid`、零依赖 |
| `P1-B1-FINAL-002` | canonical raw 超过 1,000 code points 时稳定拒绝且不生成 DTO；1,001 字符探针为 `requirement_invalid`、零依赖 |
| `P1-B1-FINAL-003` | extras canonical 后以 set 去重并按 UTF-8 bytes 排序；`a[x_y,x-y]` 输出唯一 `('x-y',)` |
| `P1-B1-FINAL-004` | `_identity_sort_key()` 逐字段编码，`None` 为 `b""`；`a` 稳定排在 `a>=1` 前 |
| `P1-B1-FINAL-005` | IPv6 hostname canonical 时恢复 brackets；公开入口保存 `https://[::1]/pkg` |

本轮真实结果：五项独立 P1 选择集 `5 passed, 56 deselected`；Luna 独立全文件 `61 passed`；Terra B1 unit `40 passed`；全量 `276 passed`；P0 `46 passed`；`schema_export_equal=true`；compileall、`git diff --check`、未跟踪文件 no-index whitespace、尾随空白、敏感信息/本机绝对路径、P0 受保护路径和规格/Luna `12 POS + 24 NEG` 唯一 ID 检查通过。13.3 的 P0 权威复测路径仍以第 15 节 AMENDMENT 为准：`tests/unit/test_p0_domain_models.py`。

Sol 批准候选 evidence：

```text
EVD-B1-PYTHON-MANIFEST-001
status: APPROVED-PENDING-ROOT-BINDING
scope: verified-local-trusted-consumer-parser-candidate
```

该批准仅表示当前本地可信 A2 `ReadOnlyScanSession` consumer parser 的实现与冻结 B1-1 契约在上述 profile 下通过。Root 仍须把 evidence 绑定不可变提交、Python/`packaging` 版本、完整命令与运行输出后，才能进入项目进度或报告证据映射；绑定前不得表述为已发布、跨平台或产品级完成。

范围继续排除 JavaScript/TypeScript、lockfile、P0 `Component`/`Evidence` mapper、依赖解析/安装、许可证识别或法律结论、Web/API、Git、Linux isolation、TrustedEgress、完整 ZIP corpus、Bench、报告导出与 A2 总门禁。

### 16.1 CLOSED AMENDMENT - FINAL-001 首尾 U+2028

Root 在第 16 节批准后补充 leading/trailing U+2028 探针；Luna 首轮保留 `1 passed, 2 failed, 60 deselected`，证明通用 Unicode `strip()/split()` 会把首尾 U+2028 吞掉并错误接受声明。Terra 随后只把 continuation、注释尾部、声明外层和 token 分割收窄为 ASCII space/tab；CRLF/LF/裸 CR 仍是唯一物理行结束。

Sol 本轮只读复跑 `-k p1_b1_final_001`，结果为 `3 passed, 60 deselected in 0.02s`；独立内存探针对 middle、leading、trailing 三种输入均得到 `requirement_invalid:0`。Luna 已记录独立全文件 `63 passed`、Terra `40 passed`、全量 `278 passed`、P0 `46 passed`；本单点复审未重复冒充这些上游全量运行。

`EVD-B1-PYTHON-MANIFEST-001` 的 `APPROVED-PENDING-ROOT-BINDING` 候选批准继续有效，不重新分配 ID，也不扩大 scope。Root 仍须完成不可变提交/运行 profile 绑定；范围仍仅为本地可信 A2 consumer parser，不外推既有 JavaScript/lockfile、P0 mapper、许可证、Web、Linux/TrustedEgress 或 A2 总门禁非目标。
