# B1-3/B1-4 JavaScript manifest、P0 映射与 CLI 冻结规格

状态：`FROZEN_DESIGN_BASELINE`

日期：2026-09-02

证据候选：`EVD-B1-JAVASCRIPT-P0-CLI-001`

允许的最终证据范围：`verified-local-javascript-dependency-p0-cli-slice`

## 1. 本轮目标与非目标

本轮只形成一个可独立运行的纵切：

```text
本地 ZIP
  -> A2-2 ReadOnlyScanSession
  -> package.json + package-lock.json(v2/v3)
  -> JavaScriptDependency DTO
  -> P0 Component/Evidence
  -> python -m app.cli --javascript-dependencies LOCAL_ZIP
```

支持根项目的 `dependencies`、`devDependencies`、`optionalDependencies`、
`peerDependencies`，并用同目录 `package-lock.json` 的 root package 与直接
`node_modules/<name>` 项补充精确版本和 registry tarball URL。只输出根 manifest 直接声明；
不枚举传递依赖。

明确非目标：npm lock v1、`npm-shrinkwrap.json`、Yarn、pnpm、monorepo/workspace 跨包解析、
peer 元数据求值、依赖求解、安装状态、生命周期脚本、许可证、漏洞和合规结论。遇到这些内容
不得猜测或提升为已支持事实。

## 2. 输入发现与限额

- 候选文件名严格为小写 `package.json`、`package-lock.json`；忽略 `.git`、`.hg`、`.svn`、
  `.venv`、`venv`、`__pycache__`、`site-packages`、`node_modules` 内候选。
- 最多 64 个候选；单文件最大 2 MiB；候选累计最大 8 MiB；最大 4096 个声明；JSON 嵌套
  深度最大 64；字符串最大 8192 个 Unicode code point。
- 只能通过 `ReadOnlyScanSession.inventory` 发现，并通过 `read_bytes(relative_path)` 读取；
  禁止 `open`、`Path.read_*`、目录遍历、Node/npm 子进程、网络、import/require 目标代码。
- 文件必须是无 BOM 的严格 UTF-8 JSON；根必须是 object。使用 `object_pairs_hook` 检测任意
  层重复 key，重复 key 不能采用 first-wins 或 last-wins。
- inventory DTO 类型、唯一路径、size/hash 与读取结果不一致时失败关闭。

稳定运行失败：

| reason | 条件 |
|---|---|
| `javascript_manifest_parser_failed` | DTO/内部不变量、重复 inventory、未知异常 |
| `javascript_manifest_limit_exceeded` | 候选/字节/深度/字符串/声明数量超限 |
| `javascript_manifest_parser_unavailable` | 标准库 JSON 能力不可用（防御性门禁） |

上述均使用 `scanner_failed:<reason>`，不输出路径、原 JSON、URL 或 traceback。

## 3. JSON 与 npm 声明语义

### 3.1 包名

- unscoped：`[a-z0-9][a-z0-9._-]{0,213}`；scoped：`@scope/name`，scope/name 各使用同一
  小写 ASCII token 规则，总长不超过 214。
- 不做大小写修正、Unicode 归一化或静默裁剪；非法 key 生成 error diagnostic。
- npm 名称就是 `normalized_name` 和 `declared_name`，不应用 PyPI canonicalize。

### 3.2 字段优先级

每个字段必须是 object，value 必须是非空字符串且长度不超过 200。scope 映射为：

| 字段 | scope |
|---|---|
| `dependencies` | `runtime` |
| `devDependencies` | `development` |
| `optionalDependencies` | `optional` |
| `peerDependencies` | `peer` |

同名声明合并时，优先级为 optional > runtime > development > peer；完全相同的 selector 生成
`dependency_duplicate` warning 并保留全部 Evidence；selector 不同生成
`dependency_declaration_conflict` error、结果 `partial`，Component 不采用 lock 精确版本。

### 3.3 selector

本轮只接受 registry selector：

- 不含 ASCII/Unicode 控制符、空白、反斜杠；长度 1..200；
- 拒绝 `file:`、`link:`、`workspace:`、`npm:` alias、`git`、`git+`、`http:`、`https:`、
  `ssh:`、绝对/相对路径及含 `://` 的值；
- 接受普通 semver range、exact semver 和 tag，原样保存为 `requested_spec`，但 parser 不求值；
- 只有完整匹配 `v?MAJOR.MINOR.PATCH`（可含合法 prerelease/build）才是声明 exact version；
  输出版本去掉前导 `v`。实现可使用自有的有界正则，不得执行 npm。

## 4. package-lock v2/v3

- `lockfileVersion` 必须是 JSON integer 2 或 3（bool 不算 integer）；否则本文件生成 error
  diagnostic，不使用其中版本。
- `packages` 必须是 object；root 项 `""` 如存在也必须为 object。
- 同目录 `package.json` 是声明事实源；lockfile 不能凭空新增直接 Component。
- 对名称 `name` 仅查找精确 key `node_modules/<name>`；scoped 包为
  `node_modules/@scope/name`。nested `node_modules/a/node_modules/b` 不作为直接项。
- lock package 项必须是 object；`version` 若存在须为有效 exact semver；`resolved` 若存在只
  接受无 credentials/query/fragment 的 canonical public HTTPS URL，hostname 小写、默认端口
  省略。其他字段不影响本轮结果。
- root `packages[""]` 的四个依赖字段如出现，必须与同目录 package.json 对应字段逐 key/值
  相等；不一致生成 `lock_root_mismatch` error 并禁止该项目所有 lock enrichment。
- 缺少某个直接 package 项只产生 `lock_entry_missing` warning；声明仍输出，版本按 selector
  exact 规则决定。
- lock version 与 selector exact version 不一致时生成 `lock_version_conflict` error，版本置空；
  range/tag 可由合法 lock version 补充精确版本。

## 5. 冻结 DTO

实现必须提供不可变 dataclass/enum，并拒绝伪造或非 canonical DTO：

```text
JavascriptManifestKind = package_json | package_lock
JavascriptDependencyScope = runtime | development | optional | peer
JavascriptParseStatus = complete | partial

JavascriptEvidenceDraft(
  manifest_path, field_locator, content_sha256, excerpt
)

ParsedJavascriptManifest(
  relative_path, kind, size_bytes, content_sha256, status
)

JavascriptDependencyDeclaration(
  normalized_name, declared_name, requested_spec, resolved_version,
  scope, source_manifest, lock_manifest, resolved_url, evidence
)

JavascriptParserDiagnostic(
  code, severity, manifest_path, field_locator,
  start_line=None, end_line=None, message
)

JavascriptManifestParseResult(
  schema_version="b1-javascript-manifest/v1",
  status, manifests, dependencies, diagnostics
)
```

所有 tuple 使用 UTF-8 byte 排序；Evidence 以 locator/hash/excerpt 排序；diagnostic 以
path/locator/code/severity 排序。无 diagnostic 时必须 `complete`；存在 diagnostic 时必须
`partial`。JSON 文件不计算行号，两个 line 字段固定 `None`。

稳定 diagnostic：

| code | severity | message |
|---|---|---|
| `manifest_encoding_invalid` | error | `Manifest text is not valid UTF-8.` |
| `manifest_json_invalid` | error | `Manifest JSON is invalid.` |
| `manifest_duplicate_key` | error | `Manifest JSON contains a duplicate key.` |
| `manifest_field_invalid` | error | `Manifest dependency field has an unsupported type.` |
| `package_name_invalid` | error | `Package name is invalid or unsupported.` |
| `dependency_selector_unsafe` | error | `Dependency selector is unsafe or unsupported.` |
| `lockfile_version_unsupported` | error | `Package lock version is unsupported.` |
| `lock_root_mismatch` | error | `Package lock root dependencies do not match package.json.` |
| `lock_entry_invalid` | error | `Package lock entry is invalid.` |
| `lock_entry_missing` | warning | `Package lock entry is missing.` |
| `lock_version_conflict` | error | `Declared and locked dependency versions conflict.` |
| `dependency_duplicate` | warning | `Duplicate dependency declaration was merged.` |
| `dependency_declaration_conflict` | error | `Dependency declarations conflict.` |

不得把用户内容拼进 message。单文件出错不阻止其他文件，除非触发运行级失败；可恢复问题产生
`partial`。

## 6. Evidence locator 与 P0 映射

JSON locator 使用 `relative/path.json:/<RFC6901 tokens>`；token 只进行 `~`→`~0`、`/`→`~1`。
示例：

```text
package.json:/dependencies/react
package.json:/dependencies/@scope~1pkg
package-lock.json:/packages/node_modules~1react/version
package-lock.json:/packages/node_modules~1@scope~1pkg/resolved
```

Evidence：`kind=manifest_field`、`detected_by=manifest_parser`、producer name
`openguard.javascript-manifest`、version `b1-javascript-manifest/v1`、config digest 为 inventory
root SHA-256、`verification_status=verified`、时间由调用方注入的 UTC clock 提供。excerpt 为
canonical compact JSON 字符串值，最多 512 code point，不含凭据片段。

P0 Component：

- `ecosystem="npm"`、`component_type="library"`、`detected_by=[manifest_parser]`、
  `confidence=1.0`；license 为空；
- version：无冲突时优先合法 lock version，其次 selector exact version，否则 `null`；
- purl：有 version 时为 `pkg:npm/<name>@<version>`，其中 leading `@` percent encode 为 `%40`，
  scope/name 的 `/` 保留；没有 version 时为 `pkg:npm/<name>`；
- source_url：仅采用通过 canonical HTTPS 校验的 lock `resolved`；
- evidence_ids 包含声明及被采用的 lock version/resolved 证据。

UUIDv5 namespace 固定为 `2cda82be-8c98-5d1e-8078-0e18c6ec3bd5`。name material 均使用
UTF-8、`ensure_ascii=false`、`sort_keys=true`、compact separators 的 JSON 数组：

```text
Evidence:  ["javascript-evidence", root_digest, locator, content_sha256, excerpt]
Component: ["javascript-component", root_digest, normalized_name, scope,
            requested_spec, resolved_version, resolved_url]
```

ID 前缀分别为 `evd_`、`cmp_`。mapper schema 为 `b1-javascript-p0/v1`，必须在创建 P0
对象前验证完整 frozen DTO、diagnostic 字面量/顺序、locator round-trip、重复 Evidence、UTC
clock 和 root digest；失败统一为 `scanner_failed:javascript_p0_mapper_failed`。

## 7. CLI

新增且只新增精确模式：

```bash
PYTHONPATH=backend python -m app.cli --javascript-dependencies LOCAL_ZIP
```

stdout 单行 compact/sort_keys JSON：

```json
{"components":[],"diagnostics":[],"evidence":[],"mapper_schema_version":"b1-javascript-p0/v1","parser_schema_version":"b1-javascript-manifest/v1","root_digest":"<sha256>","schema":"openguard.javascript-dependencies","status":"complete","version":"1"}
```

旧 `LOCAL_ZIP` 与 `--python-dependencies LOCAL_ZIP` 的 help、参数、stdout、stderr、exit 和导入
边界必须保持。JS 模式显式使用 2 MiB 单文件/8 MiB 累计 A2 read limits。exit 0 为 complete/
partial 成功，输入/参数错误为 2，其余安全/扫描错误为 1。任何路径都必须完成 A2 最终完整性
校验和 workspace 清理；cleanup/完整性错误优先，不泄漏路径、URL、内容或 traceback。

## 8. 验收矩阵

正向：

| ID | 要求 |
|---|---|
| POS-B1-JS-001 | package.json 四个字段、scope 与稳定排序 |
| POS-B1-JS-002 | scoped 名称与 RFC6901 locator |
| POS-B1-JS-003 | exact/range/tag 的版本语义 |
| POS-B1-JS-004 | lock v2 直接版本 enrichment |
| POS-B1-JS-005 | lock v3 resolved HTTPS 与 purl |
| POS-B1-JS-006 | duplicate 合并、多 Evidence 与 partial warning |
| POS-B1-JS-007 | 声明/lock 冲突的 partial 语义 |
| POS-B1-JS-008 | 固定 clock、UUID known-answer 和重复运行一致 |
| POS-B1-JS-009 | 真实 ZIP→A2→parser→mapper→CLI 与 P0 重载 |
| POS-B1-JS-010 | 旧 inventory/Python CLI 字节兼容、0/1/2 与 cleanup |

负向：

| ID | 要求 |
|---|---|
| NEG-B1-JS-001 | BOM/非UTF-8/无效JSON |
| NEG-B1-JS-002 | 任意层重复 JSON key |
| NEG-B1-JS-003 | 非object根/字段/value |
| NEG-B1-JS-004 | 候选、字节、深度、字符串、声明超限 |
| NEG-B1-JS-005 | 非法/Unicode/大写/超长 npm 名称 |
| NEG-B1-JS-006 | file/link/workspace/npm alias/git/http/path selector |
| NEG-B1-JS-007 | lock v1/非2或3/非法 packages/root/entry |
| NEG-B1-JS-008 | root mismatch/缺项/version conflict 稳定诊断 |
| NEG-B1-JS-009 | credentials/query/fragment/非canonical resolved URL |
| NEG-B1-JS-010 | duplicate inventory/伪造 size/hash/read mismatch |
| NEG-B1-JS-011 | 伪造 DTO、排序、status、diagnostic、Evidence 重复 |
| NEG-B1-JS-012 | 非UTC clock、坏 digest、locator 非canonical |
| NEG-B1-JS-013 | parser/mapper/clock 未知异常统一脱敏 |
| NEG-B1-JS-014 | 不调用 Node/npm/网络/目标代码/旁路文件 API |
| NEG-B1-JS-015 | A2 integrity/consumer/cleanup 错误优先并无残留 |
| NEG-B1-JS-016 | 未支持 lock/workspace 不得外推为完整依赖或合规证据 |

Terra 只能修改 backend 实现、`tests/unit/test_b1_javascript_manifest_p0_cli.py`、后端说明、AI
日志和共享日志；Luna 只能新增独立 security 测试、更新 security README、AI 日志和共享日志，
不得复用 Terra helper 生成 expected UUID/locator/JSON。两者不得修改 P0/Schema/sample、本规格、
PROJECT_PROGRESS 或 third_party，不得提交/推送。

放行必须同时满足：Terra 10 POS/16 NEG、Luna 逐 ID 独立验证、旧两模式 CLI 与 P0 零回归、
真实磁盘 ZIP/固定 clock/错误/cleanup、Root 不可变提交绑定及 Sol/Root 无开放 P0/P1。绿灯只
批准本文件开头的有界 evidence scope。

## ROOT EVIDENCE BINDING 2026-09-02

`EVD-B1-JAVASCRIPT-P0-CLI-001` 已绑定不可变实现提交
`80ee2a98fbd5e598359a5ae097dd21f94839b290`，状态为 `APPROVED`，证据范围严格限定为
`verified-local-javascript-dependency-p0-cli-slice`。

绑定 profile：CPython `3.12.13`、OpenGuard P0 contract `0.1.1`；Terra JS `37 passed`、
Luna 独立 `32 passed`、JS 合计 `69 passed`、Python/A2/P0 保护集 `236 passed`、全量
`424 passed`；存储 Schema 与 `ScanRun.model_json_schema()` 等值，compileall、diff、空白、
敏感信息和受保护路径检查通过。

真实混合 ZIP 的 inventory、Python、JavaScript 三种 CLI 均 exit 0、stderr 为空；JS 模式输出
3 个 Component 与 7 个 Evidence，全部可由 P0 模型重新载入，固定 UTC clock 两次输出逐字节
相同，内部任务 workspace 清理完成。首次独立验证的 5 项 P1 与 Root 4 类加固探针均已关闭，
且 Luna 原断言未放宽。

该绑定不证明 npm lock v1、shrinkwrap、Yarn、pnpm、workspace、传递依赖、许可证、漏洞、
依赖安装/求解、Git/Linux/TrustedEgress、Web/API、报告、Bench、完整参赛提交或获奖竞争力。
