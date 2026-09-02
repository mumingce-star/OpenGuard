# B1-2 Python P0 Mapper 与 CLI 兼容契约

- 版本：`v0.1.0`
- 状态：`FROZEN_DESIGN_BASELINE / IMPLEMENTATION_UNVERIFIED`
- 日期：2026-09-02
- 设计负责人：Sol
- 后续实现负责人：Terra
- 后续独立验证负责人：Luna
- 依赖契约：P0 `v0.1.1`、B1-1 `b1-python-manifest/v1`、A2-2 `ReadOnlyScanSession`

## 1. 目标、结论与非结论

B1-2 把已冻结的 `PythonManifestParseResult` 映射为 P0 v0.1.1 的
`Component` 与 `Evidence`，并为现有离线本地 ZIP CLI 增加一个显式 Python 依赖扫描
模式。mapper 是纯内存、确定性的运行级适配层；CLI 仍只通过 A2-2 生命周期绑定的只读
consumer 读取 manifest。

本契约冻结可直接实现和独立测试的接口、ID、字段、排序、错误、时间与向后兼容语义，
但不是运行时证明。设计完成不表示 mapper、CLI 新模式、ScanRun、许可证、Web、Git 或
Linux 隔离已经实现或通过。

本任务明确不做：

- 不修改 P0 v0.1.1 模型、导出 Schema、sample、枚举或公共 API；
- 不实现 JavaScript/TypeScript、package/lockfile、Python lockfile 或依赖求解；
- 不推断 purl、许可证、版权方、resolved dependency、安装/下载/漏洞或合规状态；
- 不创建 `LicenseExpression`、`RiskFinding`、`ScanError`、`ScanRun` 或报告对象；
- 不实现 Web/FastAPI、Git intake、TrustedEgress、Linux profile、registry 或 A2 总编排；
- 不执行目标代码、不安装目标依赖、不联网、不访问 materialized workspace 路径。

## 2. 冻结 Python 接口

Terra 新增 `backend/app/scanners/python_p0_mapper.py`，并从
`backend.app.scanners` 导出以下入口与结果 DTO：

```python
from dataclasses import dataclass
from datetime import datetime

from app.domain.models import Component, Evidence
from app.scanners.python_manifest import ParseStatus, ParserDiagnostic, PythonManifestParseResult

MAPPER_SCHEMA_VERSION = "b1-python-p0/v1"

@dataclass(frozen=True)
class PythonP0MappingResult:
    schema_version: str
    status: ParseStatus
    components: tuple[Component, ...]
    evidence: tuple[Evidence, ...]
    diagnostics: tuple[ParserDiagnostic, ...]

def map_python_manifest_result(
    result: PythonManifestParseResult,
    *,
    root_digest: str,
    observed_at: datetime,
) -> PythonP0MappingResult: ...
```

`schema_version` 固定为 `b1-python-p0/v1`。mapper 不接收 ID factory、随机数、主机
路径、scan ID、locale、marker 环境或可变 producer；这些输入会破坏同一冻结输入的
确定性。任何 mapper 自有不变量或 P0 构造失败都脱敏为：

```text
scanner_failed:python_p0_mapper_failed
```

该错误使用现有 `IngestionSecurityError`，不得包含原异常、DTO 原文、URL、路径、堆栈或
Pydantic error text。B1-1/A2-2 的 `IngestionSecurityError` 不在 mapper 内改写。

## 3. 输入完整性与运行级上下文

mapper 在创建任何 P0 对象前一次性验证：

1. `result` 必须是精确 `PythonManifestParseResult`，`schema_version` 必须等于
   `b1-python-manifest/v1`；未知对象或子类自定义行为不被接受。
2. `root_digest` 必须是 64 位小写 SHA-256 十六进制；它是 inventory root digest，
   不是 ZIP 上传摘要或 manifest 摘要。
3. `observed_at` 必须是显式 UTC、offset 为零的 `datetime`；naive 或非 UTC offset
   不自动猜测/转换。
4. manifest 的 `relative_path` 唯一，`content_sha256` 为 64 位小写 SHA-256；每条
   EvidenceDraft 的 `manifest_path` 必须精确引用一个 manifest，且
   `content_sha256` 必须与该 manifest 相等。
5. 每个 dependency 至少有一条 EvidenceDraft；`normalized_name`、scope、source kind、
   direct reference、lines/field locator 组合必须符合 B1-1 冻结形态。
6. `diagnostics` 非空时 `result.status` 必须为 `partial`；为空时必须为 `complete`。
   任一 manifest 为 `partial` 却没有诊断也视为 mapper 不变量失败。
7. result 及其 manifest/dependency/evidence/diagnostic 元素都必须是冻结 DTO 的精确类型，
   容器必须是 tuple；manifest、dependency、dependency evidence 与 diagnostic 必须已满足
   B1-1 的 canonical 排序和去重规则。mapper 只验证，不通过重新排序来接受手工拼装的
   非 canonical DTO。

mapper 不重新读取 inventory/manifest，不重新运行 PEP 508，也不修改 parser diagnostics。

## 4. 确定性 UUID、namespace 与 identity material

### 4.1 冻结 namespace

唯一 namespace 为：

```text
derivation: uuid5(NAMESPACE_URL, "https://openguard.dev/namespaces/b1-python-p0/v1")
uuid:       7d857170-1410-582b-a296-bb0fc9a9f057
```

实现必须使用上面的字面 UUID；不得在运行时从 DNS、环境变量、机器 ID、时间或随机数派生。

### 4.2 Canonical name bytes

UUIDv5 的 name 是下列 JSON array 的 canonical JSON string；UUIDv5 内部使用该 string
的 UTF-8 bytes：

```python
canonical_name = json.dumps(
    material,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
)
canonical_name_bytes = canonical_name.encode("utf-8")
object_uuid = uuid.uuid5(PYTHON_P0_NAMESPACE, canonical_name)
```

JSON 中缺失语义使用 `null`，整数保持十进制 JSON number；不得使用 `repr()`、默认
JSON 空白、平台换行或 locale 排序。最终 P0 ID 是小写 hyphenated UUID：

```text
evd_<uuid5>
cmp_<uuid5>
```

### 4.3 Evidence identity

每条去重后的 Evidence identity material 为：

```json
["evidence","v1","<root_digest>","<locator>",<start_line-or-null>,<end_line-or-null>,"<content_sha256>","<excerpt>"]
```

`observed_at` 与 producer 不进入 ID，因此同一 root/locator/content 在不同运行时间或仅
producer metadata 重发时仍是同一证据身份；它们仍作为 Evidence 字段输出。

### 4.4 Component identity

本纵切禁止生成 purl，因此严格使用 P0 fallback 去重键：

```json
["component","v1","<root_digest>","pypi","<normalized_name>",<version-or-null>]
```

`source_url`、evidence IDs、confidence 与 observed time 不进入 Component ID。同一 root
中相同 `(pypi, name, version)` 必须合并，不能因 scope、group、marker、extras 或 manifest
位置制造多个 P0 组件。root digest 改变时所有 B1-2 Evidence/Component ID 必须改变。

UUID 碰撞、重复 ID 指向不同 identity 或相同 identity 产生不同 ID 均整体失败，不得后缀
加序号或随机重试。

### 4.5 独立已知答案向量

以下向量是契约字面量，Terra 与 Luna 必须直接断言结果，不得调用被测 mapper helper 生成
期望值。令 `root_digest = "0" * 64`：

| 对象 | canonical material | UUIDv5 / P0 ID |
|---|---|---|
| Evidence | `["evidence","v1","0000000000000000000000000000000000000000000000000000000000000000","requirements.txt",1,1,"1111111111111111111111111111111111111111111111111111111111111111","requests==2.32.5"]` | `evd_62a3eee2-9135-53d4-95cb-bd48e7fcbdfe` |
| pinned Component | `["component","v1","0000000000000000000000000000000000000000000000000000000000000000","pypi","requests","2.32.5"]` | `cmp_d2c4370f-4dee-58e4-a924-5c0ca9589acf` |
| unversioned Component | `["component","v1","0000000000000000000000000000000000000000000000000000000000000000","pypi","requests",null]` | `cmp_55dc00bc-8e38-53ee-96c3-b1f3459ddf9a` |

## 5. Locator 的合法编码

P0 允许 `path:field`，但仓库相对路径本身可含 `:` 或 `%`。B1-2 对所有 manifest path
先使用 RFC 3986 percent-encoding：

```python
encoded_path = quote(manifest_path, safe="/-._~")
```

要求：UTF-8 编码、`/` 保留、percent hex 使用大写；literal `%`、`:`、空格、`#`、`?`
及非 ASCII 字节都编码。解码后必须与 A2/B1 原 `manifest_path` 逐 code point 相等，重新
编码必须得到同一 canonical 文本。

- requirements EvidenceDraft：`field_locator is None`，locator 仅为 `encoded_path`，且
  `start_line/end_line` 必须同时为 1-based integer。
- pyproject EvidenceDraft：lines 必须同时为 `None`，locator 为
  `encoded_path + ":" + field_locator`。

pyproject field locator 只接受 B1-1 生成的三种 ASCII grammar：

```text
project.dependencies[<non-negative-index>]
build-system.requires[<non-negative-index>]
project.optional-dependencies.<encoded-group>[<non-negative-index>]
```

`encoded-group` 非空，仅含 `[A-Za-z0-9._-]` 或 canonical `%HH`；percent decode 后再按
B1-1 规则编码必须 round-trip 相等。field locator 不进行第二次 percent-encoding。
最终 locator 必须满足 P0 1..2048 code points；越界整体失败，不截断。

示例：

```text
input path: dir/a:b% c/pyproject.toml
field:      project.dependencies[0]
locator:    dir/a%3Ab%25%20c/pyproject.toml:project.dependencies[0]
```

## 6. Evidence 字段映射

一个唯一 EvidenceDraft 映射一个 P0 `Evidence`：

| P0 字段 | 冻结值/来源 |
|---|---|
| `id` | 第 4.3 节确定性 `evd_` UUID |
| `kind` | `manifest_field` |
| `locator` | 第 5 节 canonical locator |
| `excerpt` | EvidenceDraft.excerpt；原样、1..1000 code points |
| `start_line/end_line` | requirements 精确映射；pyproject 都为 `None` |
| `content_hash` | `{algorithm:"sha256", value: content_sha256}` |
| `detected_by` | `manifest_parser` |
| `producer.type` | `parser` |
| `producer.name` | `openguard-python-manifest-parser` |
| `producer.version` | `0.1.0`，与当前 `backend/pyproject.toml` 项目版本一致 |
| producer 其他字段 | 全部 `None` |
| `observed_at` | mapper 的单次 UTC 注入值 |
| `verification_status` | `verified` |

`verified` 只证明冻结 parser 在 sealed manifest 中观察到该声明及定位/哈希，不证明包、
URL、artifact、版本可获取，也不表示许可证或合规已核验。

相同 Evidence identity 合并为一条；相同 locator/lines 但 hash 或 excerpt 不同是不同证据。
若同一 root 中出现这种矛盾，输入不变量失败而不是同时发布互相冲突的内容。

## 7. Component 映射、exact pin 与合并

### 7.1 固定字段

| P0 字段 | 冻结值/来源 |
|---|---|
| `id` | 第 4.4 节确定性 `cmp_` UUID |
| `name` | `normalized_name` |
| `ecosystem` | `pypi` |
| `component_type` | `library` |
| `version` | 仅第 7.2 节允许，否则 `None` |
| `purl` | 始终 `None` |
| `source_url` | 仅第 7.3 节允许，否则 `None` |
| `license_expression_id` | 始终 `None` |
| `evidence_ids` | 所有贡献声明的 Evidence ID 并集，去重、字典序 |
| `detected_by` | 仅 `["manifest_parser"]` |
| `confidence` | `1.0` |

`confidence=1.0` 仅描述“显式命名声明被确定性解析并映射”的置信度，不是 resolved、installed、
reachable、safe、licensed 或 compliant 的置信度。

### 7.2 唯一 exact pin

只有同时满足以下条件才写 P0 version：

1. `source_kind == index` 且 `direct_reference is None`；
2. `marker is None`；
3. specifier 恰好一个 `==<version>`，不是 `===`、不含逗号或 `*`；
4. `<version>` 可由锁定 `packaging.version.Version` 解析，写入 `str(Version(value))`；
5. 同一 `(normalized_name, scope, group)` 没有 B1-1 定义的 exact pin/direct reference
   冲突。

mapper 按 B1-1 第 6.2 节的冻结 grouping/identity 规则从 dependency DTO 重新判定第 5 项，
不靠缺少 dependency identity 的 diagnostic 文本反向猜测归属，也不重新解析原 manifest。

范围、bare name、compatible release、wildcard、arbitrary equality、marker、direct URL、
VCS 或冲突簇全部映射 `version=None`，不得从 URL fragment/hash 猜版本。

### 7.3 `source_url`

仅当一个合并后的 P0 component 的全部贡献声明都是 `direct_url`，全部
`direct_reference` 逐字相同且该簇无冲突时，写该 canonical HTTPS URL。任一 index、VCS、
不同 direct URL 或冲突声明混入时为 `None`；不得选择“第一条”或“最后一条”。

`git+https` 不是 P0 HTTPS-only `source_url`，始终只通过 Evidence.excerpt 保留。

### 7.4 多证据与冲突

先按 B1 dependency identity 消费声明，再按 P0 fallback key
`(pypi, normalized_name, mapped_version)` 合并 Component。不同 scope/group/marker/extras/hash
不进入 P0 字段，但其全部 Evidence 必须保留在 `evidence_ids`。parser 的
`dependency_duplicate`、`dependency_multiple_constraints`、
`dependency_declaration_conflict` 继续作为 diagnostics 输出；mapper 不静默消除。

## 8. Status、diagnostics 与稳定排序

`PythonP0MappingResult.status` 精确继承经第 3 节验证的 parser status。diagnostics 保留
原冻结 DTO 字段与顺序，不转为 P0 Evidence、RiskFinding 或 ScanError：

```json
{
  "code": "requirement_invalid",
  "severity": "error",
  "manifest_path": "requirements.txt",
  "field_locator": null,
  "start_line": 1,
  "end_line": 1,
  "message": "Requirement declaration is invalid."
}
```

本 wrapper 的 `partial` 只是 B1 parser 的可恢复结果，不是 P0 `ScanRun.status=partial`；
未来 A4 才负责把 diagnostics 映射为带 recoverable error 的合法 ScanRun。

最终排序：

- Evidence：`(locator UTF-8 bytes, start_line or 0, end_line or 0, content_hash.value,
  excerpt UTF-8 bytes, id)`；
- Component：`(ecosystem, name, version or "", purl or "", source_url or "", id)` 各字符串
  使用 UTF-8 bytes；
- `evidence_ids` 与 `detected_by` 使用 P0 模型的稳定去重结果；
- diagnostics 必须已经符合 B1-1 冻结排序，mapper 验证而不重排掩盖异常。

## 9. CLI 语法与旧模式字节兼容

### 9.1 用户调用与兼容分派

```text
python -m app.cli LOCAL_ZIP
python -m app.cli --python-dependencies LOCAL_ZIP
python -m app.cli --help
```

`--python-dependencies` 只在参数恰好为两个且它是第一项时进入新模式，第二项作为不透明
路径交给既有文件打开边界。其余参数必须按旧分派顺序处理：精确单参数 `--help` 输出帮助，
任意其他单参数仍作为 legacy `LOCAL_ZIP`，零个或多于一个参数才是 usage error。因此单独的
`--python-dependencies`、单独的未知 dash-leading token 仍保留旧“把它当路径打开”的字节
语义；`LOCAL_ZIP --python-dependencies`、重复 flag 或额外参数保持旧 usage error。调用者若
文件名以 dash 开头，应传 `./<name>`。`--help` 的 stdout 继续逐字等于：

```text
usage: python -m app.cli LOCAL_ZIP
```

### 9.2 旧 inventory 模式冻结

无 flag 的路径必须继续调用现有 `run_local_zip()`/`ingest()`，`inventory_payload()`、
JSON dump 参数、stdout/stderr 和退出码逐字不变。相同有效 ZIP 在本任务前后的 stdout
必须 byte-for-byte 相等；旧模式不得导入/调用 parser、mapper 或 clock。

旧模式成功仍是单行 compact、`sort_keys=True`、UTF-8 JSON 加一个 LF；现有
`schema="openguard.zip-inventory"`、`version="1"`、entries/root digest 不变。

### 9.3 Python dependency 模式编排

Terra 增加以下兼容 helper；不得再造第二个 CLI module 或并行 payload class：

```python
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

def python_dependency_payload(
    inventory: Inventory,
    mapping: PythonP0MappingResult,
) -> dict[str, object]: ...

def run_local_zip_python_dependencies(
    archive_path: Path,
    workspace_root: Path,
    *,
    clock: Callable[[], datetime],
) -> tuple[Inventory, PythonP0MappingResult]: ...

def main(
    arguments: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    clock: Callable[[], datetime] | None = None,
) -> int: ...
```

`main()` 在新模式且 `clock is None` 时使用 `datetime.now(timezone.utc)`；测试可传固定
callable。旧模式不得调用该 clock。新模式：

1. 使用现有脱敏文件打开和临时 0700 workspace root；
2. 调用 `ZipIngestionService.ingest_with_consumer()`，并显式传
   `ScanReadLimits(single_file_max_bytes=262_144, total_max_bytes=4_194_304)`；这是 B1-1
   parser 的单 manifest/总读取上限，且仍受更小的服务端上限约束，不能抬高 A2 配置；
3. consumer 内调用 B1-1 parser，再用 session inventory root digest、clock 的唯一一次
   UTC 结果调用 mapper；
4. consumer 捕获 parser/mapper 的 `IngestionSecurityError`，只返回保存 code/reason 两个
   字符串的私有 frozen failure sentinel；clock 自身抛出的普通 `Exception` 则转为保存
   `scanner_failed/cli_runtime_failed` 的同类 sentinel。A2-2 完成终态复验、task cleanup
   且 service close 成功后，runner 在会话外按 sentinel 新建无 cause 的
   `IngestionSecurityError`。A2 的终态复验、descriptor recovery 或 cleanup 错误优先于
   sentinel；这既避免 consumer 错误被改写为 `scan_consumer_failed`，也不绕过 cleanup；
5. 只有完整成功/合法 parser partial 才序列化 stdout。

### 9.4 新模式 JSON v1

stdout 是 `ensure_ascii=False, sort_keys=True, separators=(",", ":")` 的单行 JSON 加 LF：

```json
{
  "components": [],
  "diagnostics": [],
  "evidence": [],
  "mapper_schema_version": "b1-python-p0/v1",
  "parser_schema_version": "b1-python-manifest/v1",
  "root_digest": "<64 lowercase hex>",
  "schema": "openguard.python-dependencies",
  "status": "complete",
  "version": "1"
}
```

Component/Evidence 使用 `model_dump(mode="json")` 的完整 P0 字段，`None` 序列化为
JSON `null`；不得用私有平行 DTO 改字段名。diagnostic 固定包含第 8 节全部七个键，`None`
也输出为 `null`。不输出 manifest 原文、绝对路径、workspace、scan ID 或 traceback。

### 9.5 时间与可复现性

clock 每次新模式成功解析只调用一次；全部 Evidence 使用同一 UTC instant。ID identity 明确
排除时间。同一 ZIP、parser/mapper 版本、固定 clock 和运行 profile 必须产生 byte-for-byte
相同 stdout；不同合法 clock 只允许改变 Evidence `observed_at`，ID、排序及其他字段不变。
真实 wall-clock 两次运行不承诺整行 JSON 相同，不得把这种预期时间差误报为不确定性。

### 9.6 退出、错误与 cleanup

| 结果 | exit | stdout | stderr |
|---|---:|---|---|
| inventory/new complete | 0 | 对应 JSON + LF | 空 |
| new parser `partial` | 0 | status=partial 的完整 JSON + LF | 空 |
| 输入安全、parser、mapper、cleanup 失败 | 1 | 空 | `code:reason\n` |
| 参数错误、输入文件不可用 | 2 | 空 | 既有 `invalid_request:<reason>\n` |
| clock 抛普通 Exception，或 CLI 未分类 OSError/RuntimeError | 1 | 空 | `scanner_failed:cli_runtime_failed\n` |

成功、partial、受控失败和未分类失败后均不得残留 task workspace。错误不得回显输入路径、
URL、manifest 内容、异常类/正文或 traceback；整体失败不得输出部分 JSON。

## 10. 精确验收矩阵

### 10.1 Positive（12）

| ID | 必须证明 |
|---|---|
| `POS-B1-MAP-001` | 唯一无 marker `==` pin 映射 canonical version；Component/Evidence 全字段通过 P0 模型 |
| `POS-B1-MAP-002` | bare/range/marker/extras/hash 映射 version/purl/license/source 为空，confidence/detected_by 固定且证据不丢 |
| `POS-B1-MAP-003` | 唯一普通 HTTPS direct URL 只映射 source_url，不产生 version/purl/许可证或网络访问 |
| `POS-B1-MAP-004` | `git+https` VCS 仅保留在 Evidence，Component source_url/version 为空 |
| `POS-B1-MAP-005` | exact duplicate 与跨 scope/group 的同 P0 key 合并为一个 Component，全部 Evidence ID 去重保留 |
| `POS-B1-MAP-006` | conflicting pins/direct refs 均保留 diagnostics/证据，version/source_url 不被 first/last 覆盖 |
| `POS-B1-MAP-007` | requirements lines 与 pyproject field locator 正确；含 colon/percent/space/Unicode 的 path canonical round-trip |
| `POS-B1-MAP-008` | 第 4.5 节三个 known-answer ID、同 root 固定时间 JSON、不同时间 ID 不变、不同 root ID 改变且排序稳定 |
| `POS-B1-MAP-009` | complete/partial 与 diagnostic 七字段、顺序逐字保持；空依赖 partial 仍是合法 mapper 结果 |
| `POS-B1-MAP-010` | 旧 CLI 有效/拒绝/usage/help 的 stdout、stderr、exit 与任务前 golden bytes 完全相同，且不调用 parser/mapper/clock |
| `POS-B1-MAP-011` | 固定 clock 的磁盘 ZIP 新模式 complete E2E 输出 JSON v1/P0 对象，重复运行 byte-for-byte 相等并清理 |
| `POS-B1-MAP-012` | 一个好声明加一个坏声明的新模式以 exit 0 输出 deterministic partial；无网络/子进程/目标 import/open 旁路 |

### 10.2 Negative（18）

| ID | 必须证明 |
|---|---|
| `NEG-B1-MAP-001` | 错 parser schema、status/diagnostic 或 manifest partial 不变量整体失败为 mapper reason |
| `NEG-B1-MAP-002` | root digest 非小写 64hex 整体失败，不生成 ID/部分对象 |
| `NEG-B1-MAP-003` | naive、非 UTC offset、clock 非 datetime 或 clock 抛异常稳定失败；旧模式不调用并不受故障 clock 影响 |
| `NEG-B1-MAP-004` | EvidenceDraft 引用缺失 manifest、hash 不一致或 dependency 零 evidence 在构造前失败 |
| `NEG-B1-MAP-005` | requirements/pyproject line-field 组合非法、field grammar/percent round-trip 非 canonical 被拒绝 |
| `NEG-B1-MAP-006` | locator 编码后空或超过 2048、excerpt 空/超过 1000、敏感 fragment 被拒绝且不截断泄漏 |
| `NEG-B1-MAP-007` | 重复 manifest path、矛盾 Evidence identity 或 UUID identity 碰撞整体失败，不加随机后缀 |
| `NEG-B1-MAP-008` | 畸形 normalized name、scope/source/direct-reference 组合或非冻结 DTO 类型失败关闭 |
| `NEG-B1-MAP-009` | wildcard `==`、`===`、多个 specifier、marker 与冲突 pin 不得产生 P0 version/purl |
| `NEG-B1-MAP-010` | VCS、混合 index/direct 或不同 direct URL 不得选择 source_url；全部证据仍保留 |
| `NEG-B1-MAP-011` | 任一 P0 Component/Evidence 构造校验异常只见 `python_p0_mapper_failed`，无 Pydantic 文本 |
| `NEG-B1-MAP-012` | 新模式路径穿越/坏 ZIP 原样稳定拒绝，stdout 空、workspace 清理、无路径/traceback |
| `NEG-B1-MAP-013` | parser unavailable/limit/failed 经私有 sentinel 在 cleanup 后恢复原 reason，不被改写为 consumer failure |
| `NEG-B1-MAP-014` | mapper 失败经 cleanup 后输出 `scanner_failed:python_p0_mapper_failed`，无部分 JSON/DTO 原文 |
| `NEG-B1-MAP-015` | 新模式未分类运行错误只输出 `scanner_failed:cli_runtime_failed`，无异常类/路径/traceback |
| `NEG-B1-MAP-016` | flag 位置错误、重复/额外参数保持旧 usage bytes；单独新/未知 flag 保持 legacy 路径打开语义；不可用文件为 2/空 stdout/脱敏 stderr |
| `NEG-B1-MAP-017` | monkeypatch socket/subprocess/目标 import/内建 open 后只允许 CLI 输入文件打开，无网络、执行或目标树旁路读取 |
| `NEG-B1-MAP-018` | success、partial、parser/mapper/ingestion/runtime failure 全路径无 task workspace 残留；overall failure 不发布 partial |

一轮实现的冻结规模就是 12 POS + 18 NEG。Terra 可在一个 unit 文件中用参数化用例覆盖，
但每个 ID 必须有可检索的 test 名或 marker；Luna 必须逐 ID 独立断言，不复用 Terra helper
生成期望 UUID、locator、JSON 或错误。

## 11. 文件所有权与精确交接

### 11.1 Terra 实现面

Terra 只修改：

```text
backend/app/scanners/python_p0_mapper.py
backend/app/scanners/__init__.py
backend/app/cli.py
backend/README.md
tests/unit/test_b1_python_p0_mapper_cli.py
docs/05-ai-assistance-log.md
docs/coordination/AGENT_WORKLOG.md
```

Terra 不修改本规格、Luna 文件、P0 模型/Schema/sample、B1-1/A2-2 规格、
`PROJECT_PROGRESS.md` 或第三方台账。不得为了通过测试给旧 CLI 输出加字段、改变 help、
放宽 P0 validator 或引入第二套领域模型。

### 11.2 Luna 独立验证面

Luna 只修改：

```text
tests/security/test_b1_python_p0_mapper_cli_independent.py
tests/security/README.md
docs/05-ai-assistance-log.md
docs/coordination/AGENT_WORKLOG.md
```

fixture 使用运行时动态、小型标准库 ZIP；本任务无需新增二进制或批量 fixture。Luna 不修改
backend、Terra unit、本规格、P0 或项目进度；发现缺陷保留原样失败并交 Terra/Sol。

### 11.3 Root 集成与 Sol 终审

```bash
PYTHONPATH=backend python -m pytest -q tests/unit/test_b1_python_p0_mapper_cli.py
PYTHONPATH=backend python -m pytest -q tests/security/test_b1_python_p0_mapper_cli_independent.py
PYTHONPATH=backend python -m pytest -q tests/unit/test_b1_python_manifest_parser.py
PYTHONPATH=backend python -m pytest -q tests/security/test_b1_python_manifest_parser_independent.py
PYTHONPATH=backend python -m pytest -q tests/unit/test_p0_domain_models.py
PYTHONPATH=backend python -m pytest -q
PYTHONPATH=backend python -m compileall -q backend/app tests
git diff --check
git diff --name-only
```

Root 另运行真实磁盘 ZIP 的旧/new CLI、固定 clock 的两次新模式和普通 wall-clock 一次，
核对 golden bytes、P0 模型重载、ID/time 差异、0/1/2、stdout/stderr、workspace、Schema
export/sample 等值及敏感信息。Sol 最终只读检查本契约逐项实现、独立性和证据边界。

## 12. 放行条件与当前产品边界

只有以下全部成立，B1-2 才可从 `IMPLEMENTATION_UNVERIFIED` 提升为本地候选：

1. Terra 12 POS + 18 NEG 实现侧全部通过；
2. Luna 逐 ID 独立验证且未修改上游实现；
3. 旧 CLI golden bytes 与 P0 v0.1.1 模型/Schema/sample 零回归；
4. 新模式真实 ZIP、partial、错误、cleanup、副作用与固定 clock 重现门禁通过；
5. Root 绑定不可变提交、CPython/packaging/OpenGuard profile、命令与输出摘要；
6. Sol 无开放 P0/P1，并批准有界 evidence scope。

放行范围最多是 `verified-local-python-dependency-p0-cli-slice`：证明本地 ZIP 中的 Python
manifest 声明可经可信只读 consumer 映射为 P0 Component/Evidence 并由 CLI 输出。它不证明
依赖已解析/安装、许可证已识别、完整作品可提交、Linux/TrustedEgress 生效、A2 总门禁
关闭或产品具备获奖竞争力。

## AMENDMENT 2026-09-02 — FINAL_AUDIT_BLOCKED（开放 P1）

Sol 最终只读审计不批准 `EVD-B1-PYTHON-P0-CLI-001`，其状态保持未批准；
`verified-local-python-dependency-p0-cli-slice` 也不得进入发布或报告事实。当前开放问题：

1. `FINAL-B1P0-001`（P1）：optional group locator 的 canonical round-trip 校验只检查了
   重复正则捕获组的最后一个 token。精确冻结 DTO 中
   `project.optional-dependencies.dev%2Efoo[0]` 被接受并发布，但 `%2E` 解码为 safe `.`，
   按第 5 节重编码必须是 `dev.foo`；这违反 `NEG-B1-MAP-005`。
2. `FINAL-B1P0-002`（P1）：mapper 没有完整验证 B1-1 frozen/canonical DTO。只读探针证实
   它会接受并静默去重重复 EvidenceDraft、接受 B1-1 明确拒绝的带 query HTTPS direct
   reference、接受与 parser token 不一致的 `declared_name`，并原样发布任意 diagnostic
   code/severity/message（包括敏感 fragment）。这违反第 3.5/3.7、第 8 节以及
   `NEG-B1-MAP-006/008` 的失败关闭边界。

现有回归仍全绿：Luna B1-2 `30 passed`、Terra B1-2 `43 passed`、B1-1 unit+independent
`103 passed`、A2 CLI `10 passed`、P0/Schema/sample `46 passed`、全量 `351 passed`，
`schema_export_equal=true`；compileall、`git diff --check`、受保护路径零差异和敏感信息扫描
通过。绿灯说明既有路径未回归，但没有覆盖上述手工 tampered DTO，因此不能关闭 P1。

解除阻塞要求：Terra 在不改 P0 v0.1.1 的前提下补齐完整 optional group round-trip、
EvidenceDraft 去重和 B1-1 canonical dependency/diagnostic 验证；Luna 增加不复用 mapper helper
的逐字面独立负面回归；随后重跑本节全部门禁并由 Sol 复审。Root 不得在修复前绑定或发布
该 evidence。

## AMENDMENT 2026-09-02 — FINAL_AUDIT_CLOSED（P1 已关闭）

本条只关闭上一节 `FINAL-B1P0-001/002`，不改写历史 BLOCKED：

- optional group 正则现捕获完整 encoded group，`dev%2Efoo` 按完整 decode/re-encode 被拒绝；
- mapper 在 P0 构造前拒绝重复 EvidenceDraft、非 canonical name/raw/specifier/marker、
  query/非 canonical direct reference，以及非固定或含敏感 fragment 的 diagnostics；
- Sol 原七项 tampered DTO 探针全部稳定返回
  `scanner_failed:python_p0_mapper_failed`；合法 optional/direct/VCS/partial 与旧 CLI 路径未回归；
- Luna 独立 `32 passed`、Terra `45 passed`、P0 `46 passed`、全量 `355 passed`，
  `schema_export_equal=true`；compileall、diff、受保护路径和敏感/尾随空白检查通过。

Sol 未发现新的开放 P0/P1，批准 `EVD-B1-PYTHON-P0-CLI-001` 状态为
`APPROVED-PENDING-ROOT-BINDING`，其唯一允许范围为
`verified-local-python-dependency-p0-cli-slice`。在 Root 绑定不可变提交、CPython/packaging/
OpenGuard profile、命令与输出摘要前，该 evidence 仍不得进入发布或报告事实；本批准不外推
许可证、依赖求解/安装、JS/TS/lockfile、Web/Git、Linux isolation、TrustedEgress、Bench、
A2 总门禁、完整作品提交或获奖竞争力。

## ROOT EVIDENCE BINDING 2026-09-02

`EVD-B1-PYTHON-P0-CLI-001` 现绑定到不可变实现提交
`daee8a8b54b2c46adfe98eba31ffcb7c206d4133`，状态为 `APPROVED`，证据范围严格限定为
`verified-local-python-dependency-p0-cli-slice`。

绑定运行 profile：CPython `3.12.13`、`packaging==26.3`、OpenGuard P0 contract `0.1.1`；
Terra B1-2 `45 passed`、Luna 独立 `32 passed`、B1-1/A2 CLI/P0 聚焦 `159 passed`、全量
`355 passed`，存储 Schema 与 `ScanRun.model_json_schema()` 等值，compileall 与 diff 检查通过。
真实磁盘 ZIP 的旧 CLI 返回 `openguard.zip-inventory`，新 CLI 返回
`openguard.python-dependencies`，3 个 Component/3 个 Evidence 可被 P0 模型重新载入，固定
clock 两次输出逐字节相同，两个模式均 exit 0、stderr 为空且任务 workspace 清理完成。

该绑定只证明本地 ZIP 中的 `requirements*.txt`/`pyproject.toml` 声明可通过 A2 只读会话、
B1 parser 和 mapper 输出 P0 对象；不证明许可证识别、依赖求解或安装、JS/TS/lockfile、
Git/TrustedEgress、Linux 隔离、Web/API、报告、Bench、完整参赛提交或获奖竞争力。
