# A2 独立安全测试说明

本目录由 Luna 维护，测试不依赖 Terra 的 `tests/unit/` 实现侧测试。ZIP 语料在测试运行时用 Python 标准库生成；ZIP64、data descriptor 和 header 变体使用本文件同目录测试中的小型、可审计字节构造，不提交来源不明二进制，也不访问真实内网或云元数据地址。

## 运行

在项目根目录执行：

```bash
PYTHONPATH=backend python -m pytest -q tests/security/test_a2_zip_security_independent.py
PYTHONPATH=backend python -m pytest -q
```

### 本地 ZIP CLI 演示独立回归

复现命令（项目根目录）：

```bash
PYTHONPATH=backend python -m pytest -q tests/security/test_a2_zip_cli_independent.py
PYTHONPATH=backend python -m pytest -q
```

当前真实结果：独立 CLI 测试 `5 passed`；全量测试 `111 passed`。独立测试仅动态生成小型、可审计的标准库 ZIP，不提交二进制 fixture、不联网、不执行不可信目标代码。

5 项覆盖范围：

1. 有效 ZIP 的确定性 JSON、条目排序与同输入重复运行一致性。
2. 路径穿越 ZIP 的稳定拒绝、空 stdout、固定 stderr 及无 workspace 残留。
3. 缺失文件、目录、非 ZIP 和错误参数的退出语义、脱敏输出与无异常堆栈/路径泄漏。
4. `python -m app.cli` 子进程成功/拒绝/调用错误的退出码 0/1/2 与输出隔离。
5. `run_local_zip` 成功和拒绝路径的显式 workspace 清理。

该 CLI 结果只证明离线本地 ZIP→inventory 演示候选，不等同 Web、Git/TrustedEgress、Linux profile、durable registry/API 映射或 A2 总门禁完成。

### A2-2 安全只读扫描会话独立回归

复现命令（项目根目录）：

```bash
PYTHONPATH=backend python -m pytest -q tests/security/test_a2_readonly_scan_session_independent.py
```

最终真实结果：共收集 46 个参数化场景，`46 passed`；与该文件一起运行的全量测试共 175 项，`175 passed`。原三项阻塞及 Sol 追加的两项 P1 均已由 Terra/Root 修复并经 Luna 原样复跑确认：

- `NEG-A2-RS-008`：目标 `open` 错误现稳定映射为 `scanner_failed/scan_file_read_failed`。
- `NEG-A2-RS-008`：目标 `close` 错误现不会静默成功，稳定产生 `scan_file_read_failed`。
- `NEG-A2-RS-022`：`ReadOnlyScanSession` 公开能力面已收窄为 `inventory`、`read_bytes`。
- `NEG-A2-RS-008`：消费前验证后的瞬态 `tree` 根 descriptor open 错误稳定映射为 `scan_file_read_failed`，敏感 marker 不泄漏。
- `NEG-A2-RS-008`：目标 file fd close 故障进入受控 recovery，外层返回 `scan_file_read_failed`，完成后目标 fd 为 `EBADF`。

已通过的场景覆盖绝对/父级/点段/空段/反斜杠/drive/UNC/NFC/case/Path/bytes/目录/未登记路径、外部 sentinel、父目录与文件的 symlink/FIFO/目录替换、同 size 新 inode、同 inode 内容改写、受控读错误、单文件与累计限额刚超 1 byte、重复读取计数、0/bool/非 int/放宽值、`None` 派生兼容、过期引用、真实跨线程中毒、同 session/同 service 重入、独立并发、异常脱敏、consumer catch 仍整体失败、未读取文件最终复验、cleanup 成功/失败与最高优先级、ZIP 前置拒绝零调用、bad ZIP 映射、BaseException 清理重抛、瞬态根 descriptor open 和目标 fd close recovery/EBADF。

本机 macOS/POSIX 结果仅证明当前实现的独立回归行为，不外推为 Linux 隔离、TrustedEgress 或 A2 总门禁；`NEG-A2-RS-024` 的不可信代码执行不属于本接口的可信 consumer 验证范围。

结果演进必须区分历史首次发现与修复后复测：

- 初轮（Terra 修复前）：独立安全测试 35 项，`21 passed`、`14 failed`；全量 97 项，`83 passed`、`14 failed`。这些失败按冻结安全验收 reason 保留，形成了独立缺陷证据。
- Terra 修复并经 Sol 裁决后：独立安全测试 35 项，`35 passed`；Terra ZIP 单元测试 18 项，`18 passed`；当前全量测试因 Terra 新增 2 项单元测试为 99 项，`99 passed`。为与历史口径可比，排除这 2 项新增单测后的原 97 项为 `97 passed`、`2 deselected`。
- 两项路径超限断言的 code 修正是测试侧按 Sol 裁决对齐冻结矩阵：`archive_limit_exceeded`，reason 仍为 `archive_path_depth_limit` / `archive_path_length_limit`；没有放宽安全边界，也没有修改 backend。
- 本轮 home shorthand 独立扩展后：独立安全测试 36 项，`36 passed`；Terra ZIP 单元测试 19 项，`19 passed`；当前全量 101 项，`101 passed`。相对上一轮 35/99，新增 1 个 Luna 独立测试和 1 个 Terra 实现侧测试。

## 已覆盖

- 路径逃逸、父级/点段、空段、反斜杠、控制字符、盘符、UNC、首段 `~`/`~user`、Windows 保留名、NFC/case-fold、原名重复和文件/目录冲突；深度与 UTF-8 路径长度含等于/刚超过边界。
- Unix FIFO/device/socket 属性拒绝；零和未知 producer external attributes 只生成普通字节；嵌套 ZIP 不递归展开。
- 非 ZIP、截断、加密 flag、CRC 损坏、ZIP64 小成员、data descriptor、local/central header 篡改、上传/条目/单文件/总量/ratio 边界。
- 正常 UTF-8 inventory 排序与 root digest；成功/失败清理；受控临时目录中的真实 no-follow 父链接阻断和外部哨兵保护。

## 历史首次失败与修复记录

以下是初轮 14 项失败，均遵循 `docs/security/a2-security-acceptance.md` 的稳定 reason；Terra 随后修复了实现侧 13 项 reason 漂移与 1 项 local/central header 完整性问题：

| 独立测试范围 | 实际结果/缺陷 |
|---|---|
| NFC/case-fold、原名重复、文件/目录冲突 | 分别返回 `archive_path_collision`、`archive_duplicate_name`、`archive_file_directory_conflict`，未统一到验收期望 `archive_duplicate_path`。 |
| 深度、路径长度 | 初轮返回 `archive_path_depth_exceeded`、`archive_path_utf8_bytes_exceeded`；Sol 裁决明确 code 应为 `archive_limit_exceeded`，Luna 已仅修正这两项测试侧 code 期望，reason 保持 `archive_path_depth_limit`、`archive_path_length_limit`。 |
| FIFO/device/socket | 返回 `archive_entry_type_rejected`，未使用 `archive_entry_type_unsafe`。 |
| local/central size 不一致 | 初轮服务未抛出 `archive_integrity_failed`，篡改输入仍形成结果；Terra 已补充完整性校验，修复后通过。 |
| 条目、单文件、总量、上传、ratio 超限 | 分别返回 `zip_entry_count_max_exceeded`、`single_file_max_bytes_exceeded`、`zip_uncompressed_max_bytes_exceeded`、`zip_upload_max_bytes_exceeded`、`zip_entry_expansion_ratio_exceeded`，未使用验收矩阵要求的稳定 `archive_*_limit` reason。 |

初轮实现缺陷已由 Root/Terra 处理；Luna 未修改 backend、P0 契约、Schema/sample 或现有 unit 测试。完整 ZIP64 多卷、central-directory overlap、inventory 并发变更、清理失败/quarantine、Linux cgroup/deny-egress、TrustedEgress、Git 和最终 API `ScanRun` 映射仍不是本机测试证据，须后续真实集成层关闭。首次失败记录不可被修复后结果覆盖，最终证据应同时保留两次运行的命令、版本与复核状态。

### B1-1 Python manifest parser 独立回归

复现命令（项目根目录）：

```bash
PYTHONPATH=backend python -m pytest -q tests/security/test_b1_python_manifest_parser_independent.py
PYTHONPATH=backend python -m pytest -q tests/unit/test_b1_python_manifest_parser.py
PYTHONPATH=backend python -m pytest -q
```

当前真实结果：Luna 独立矩阵 `36 passed`（12 POS + 24 NEG）；Terra B1 unit `36 passed`；全量 `247 passed`；P0 领域/Schema/sample 回归 `46 passed`。独立测试以小型标准库内存 ZIP 调用真实 A2 `ZipIngestionService.ingest_with_consumer`，仅通过 `inventory/read_bytes` 代理记录读取，不复用 Terra helper 或期望。

独立重点覆盖：候选 manifest 只读一次、64 候选/262144 单文件/4194304 总字节读取前拒绝、4096 声明与 8192 逻辑行上限、requirements/pyproject locator 与 EvidenceDraft、重复/冲突语义、marker 跨环境不求值、option/URL 内容不泄漏、packaging 错版与真实 session 过期分离、能力面不含 path/fd/workspace、subprocess/socket/open/target import 零副作用，以及两次真实 ZIP→A2→parser 结果逐字段相等。

fixture 仅为 `tests/fixtures/b1-python-manifest/` 下两份团队自有小型文字输入，README 说明来源、Apache-2.0 项目许可和开放边界；不提交二进制、不联网、不安装依赖、不执行目标代码。macOS/POSIX 本地结果不外推为 Linux 隔离、TrustedEgress 或 A2 总门禁完成。

#### B1-1 AMENDMENT 复测

Root 集成审查后新增 15 项不增加冻结 ID 的精确加固断言。Terra 修订后，Luna 加固选择集 `15 passed`、独立全文件 `51 passed`（原 36 项 + 15 项加固），Terra B1 unit `38 passed`，全量 `264 passed`，P0/Schema/sample `46 passed`。原 `15 failed` 首轮证据保留在共享工作日志中；本次未修改独立断言或冻结契约，也未运行/宣称 Linux 隔离、TrustedEgress 或 A2 总门禁证据。

Sol 随后裁决 POS-003 的 marker canonical 双引号期望，Luna 仅修订该一处测试断言并保留测试名、行号断言与冻结 ID；复跑后独立全文件 `56 passed`，Terra B1 unit `38 passed`，全量 `269 passed`，P0/Schema/sample `46 passed`。未修改 backend、Terra unit、B1 规格、P0/Schema/sample 或项目进度。

#### FINAL-001..005 P1 独立复核

按 Terra/Sol 终审要求新增 5 组逐字面独立断言，不改变冻结 `12 POS + 24 NEG` ID 数量：U+2028 物理行、1001 字符 canonical raw、extras canonical collision、`None` 空 bytes 排序和 IPv6 bracket URL。新增选择 `5 passed`；独立全文件 `61 passed`，Terra B1 unit `40 passed`，全量 `276 passed`，P0/Schema/sample `46 passed`。本地结果不外推为 Linux 隔离、TrustedEgress 或 A2 总门禁。

Root 后续补充 FINAL-001 leading/trailing U+2028 探针；选择结果为 `1 passed, 2 failed`，两项失败均显示 `.strip()` 后错误接受 `a==1`，已保留 BLOCKED 证据并等待 Terra，不运行后续回归。

Terra 修复后，FINAL-001 三参数复测为 `3 passed`；Luna 独立全文件 `63 passed`，Terra B1 unit `40 passed`，全量 `278 passed`，P0/Schema/sample `46 passed`。leading/trailing U+2028 均保持为无效单行内容并产生 `requirement_invalid`，未修改冻结 ID。

#### B1-2 Python P0 mapper 与 CLI 独立回归

复现命令（项目根目录）：

```bash
PYTHONPATH=backend python -m pytest -q tests/security/test_b1_python_p0_mapper_cli_independent.py
PYTHONPATH=backend python -m pytest -q tests/unit/test_b1_python_p0_mapper_cli.py
```

本轮真实结果：Luna 独立测试 `30 passed`（冻结 12 POS + 18 NEG，逐 ID 断言）；Terra B1-2 unit `43 passed`；B1-1 parser unit `40 passed`；A2 CLI 聚焦 `10 passed`；P0 领域/Schema/sample `46 passed`；全量 `351 passed`。`compileall`、`git diff --check`、敏感信息/绝对路径检查通过。

独立测试使用标准库动态 ZIP，覆盖三个冻结 known-answer ID、P0 Component/Evidence 全字段、exact/range/marker/direct/VCS/conflict/多证据、percent locator round-trip、partial diagnostics、固定 clock 与旧 CLI 字节兼容；同时覆盖 0/1/2、parser/mapper/clock/A2 错误优先级、错误脱敏、workspace 清理，以及 socket/subprocess/目标代码/旁路 open 禁止。未新增二进制 fixture，不联网、不安装目标依赖、不执行 ZIP 中目标代码，也未调用 Terra helper 生成期望 UUID/locator/JSON/error。

该结果只证明本地 macOS/POSIX、可信 A2 consumer 下的 Python manifest→P0 mapper→离线 CLI 纵切；不等同许可证识别、依赖求解、JS/TS、lockfile、Web/API、Git、Linux isolation、TrustedEgress、OpenGuard-Bench、报告材料或 A2 总门禁完成。

#### B1-2 终审 P1 独立复核

按 Sol 终审发现、Terra 修复后的 `FINAL-B1P0-001/002` 增补两组独立测试，不增加原冻结 30 个 ID。`FINAL-B1P0-001` 手工构造 `project.optional-dependencies.dev%2Efoo[0]`，验证完整 encoded group 的非 canonical round-trip 被拒绝，并复核真实 parser 合法 optional group。`FINAL-B1P0-002` 手工验证重复 EvidenceDraft、不一致 declared_name、noncanonical raw、带 query direct URL、任意及敏感 diagnostic 均统一失败为 `scanner_failed:python_p0_mapper_failed`，并复核合法 diagnostics、direct URL、VCS 不回归。

本轮真实结果：新增选择 `2 passed`；Luna 全文件 `32 passed`；Terra B1-2 `45 passed`；B1-1 unit+independent `103 passed`；P0 `46 passed`；全量 `355 passed`；`schema_export_equal=true`；compileall、`git diff --check`、敏感信息/本机路径/尾随空白检查通过。仍仅支持本地 macOS/POSIX 可信 consumer 的 Python P0 CLI 纵切，不批准完整 evidence 发布，不外推许可证、JS/lockfile、Web/Git、Linux isolation、TrustedEgress、Bench 或完整竞赛材料。

### B1-3/B1-4 JavaScript manifest、P0 mapper 与 CLI 独立回归

复现命令（项目根目录）：

```bash
PYTHONPATH=backend /private/tmp/openguard-a1-venv/bin/pytest -q tests/security/test_b1_javascript_manifest_p0_cli_independent.py
PYTHONPATH=backend /private/tmp/openguard-a1-venv/bin/pytest -q tests/unit/test_b1_javascript_manifest_p0_cli.py
```

本轮独立文件共收集 27 项：冻结 `10 POS + 16 NEG` 逐 ID 测试，加 1 项 ID 目录校验；结果为 `22 passed`、`5 failed`。Terra 实现侧回归为 `35 passed`。独立测试只新增 `tests/security/test_b1_javascript_manifest_p0_cli_independent.py`，使用标准库动态 JSON/ZIP、手写 locator/UUIDv5 known-answer、JSON/error 字面量；不复用 Terra helper 生成期望值，不修改 backend、Terra unit、规格、P0/Schema/sample、PROJECT_PROGRESS 或 third_party。

通过范围包括四类根直接声明与稳定排序、scoped name/RFC6901、exact/range/tag、lock v2/v3 direct enrichment、duplicate/conflict/partial、固定 clock/known-answer、真实磁盘 ZIP→A2→parser→mapper→CLI、P0 Component/Evidence reload、旧 inventory/Python CLI 字节兼容、JS 0/1/2、错误脱敏、A2 integrity/consumer/正常 cleanup，以及 Node/npm/网络/目标代码/旁路文件 API 不调用。由于独立门禁仍为红色，本轮按放行规则未宣称全量、Schema、compileall 或竞赛 evidence 通过。

稳定复现的 5 项 P1 缺陷如下，失败原样保留在独立测试中，未代 Terra 修改：

| ID | 观察 | 影响 |
|---|---|---|
| `POS-B1-JS-001` | 合法 `~2.0.0` semver range 被报为 `dependency_selector_unsafe`，导致该声明丢失 | 四字段解析与可复现依赖清单不完整 |
| `NEG-B1-JS-009` | `https://registry.npmjs.org/a/../a.tgz` 被接受为 canonical resolved URL | 非 canonical URL 可能进入 source/evidence |
| `NEG-B1-JS-010` | forged inventory 的 `size_bytes` 与实际读取数据不一致仍可完成 | inventory/read seal 不完整 |
| `NEG-B1-JS-011` | forged `ParsedJavascriptManifest.size_bytes` 为非 int 仍可通过 mapper | frozen DTO 完整性校验不完整 |
| `NEG-B1-JS-012` | `package.json:/dependencies//a` 空 JSON-pointer token 仍可通过 mapper | Evidence locator 结构未完全 canonical 化 |

当前仅能批准“本地 macOS/POSIX、可信 A2-2 consumer、根 package.json + lock v2/v3 的直接 npm 声明”这一候选范围；Linux isolation、TrustedEgress、Git/Web/API、传递依赖、许可证/合规、OpenGuard-Bench 和完整竞赛材料仍未被本轮证明。

#### B1-3/B1-4 修复后加固复测

按 Terra `2146 AMENDMENT` 要求，先原样复跑上节 27 项，结果为 `27 passed`；原有 10 POS + 16 NEG ID、断言与失败历史均未放宽或改写。随后在同一独立测试文件追加 5 组不增加冻结 ID 数量的加固断言：严格 JSON 拒绝 `NaN`/`Infinity`/`-Infinity`，手工 DTO 拒绝非法/大写 npm name、file/path/协议 selector，拒绝非 UTF-8 字节序 manifest 以及 filename-kind、跨目录 source/lock、non-canonical resolved URL 篡改。

本轮真实结果：加固选择 `5 passed, 27 deselected`；Luna 独立全文件 `32 passed`；Terra JS unit `37 passed`；JS 实现+独立合计 `69 passed`；Python/A2/P0 聚焦 `355 passed`；全量 `424 passed`；显式 `schema_export_equal=True`；`compileall -q backend/app tests`、`git diff --check` 和敏感模式扫描通过。当前结果只批准本地 macOS/POSIX、可信 A2-2 consumer 的有界 JavaScript 直接依赖候选 evidence；不可变提交绑定、Root/Sol 终审、Linux/TrustedEgress、Git/Web/API、完整 Bench、许可证/合规与报告材料仍未由本轮批准。

### A3-0 durable ScanRun registry 独立安全回归

复现命令（项目根目录）：

```bash
PYTHONPATH=backend /private/tmp/openguard-a1-venv/bin/pytest -q tests/security/test_a3_scan_registry_independent.py
```

本轮独立文件共收集 31 项：冻结 `8 POS + 16 NEG` 逐 ID 覆盖，另加 7 项跨场景/加固断言；最终结果为 `30 passed`、`1 failed`。测试不生成或提交持久化 fixture，使用临时 SQLite、第二个 SQLite connection、两个独立 registry instance、真实 POSIX 权限/FIFO/符号链接、手工 SQL/字节损坏注入、线程并发 CAS、重启、close/activity 及错误脱敏探针；canonical JSON、状态转换和 error envelope 均由本文件按冻结契约手工构造，不复用 Terra 私有 helper。

唯一失败为 `test_hardening_schema_declared_types_and_constraints_are_verified`：同名但错误声明类型、缺失 `scan_id` 主键/CHECK/幂等唯一约束的 schema 当前未被拒绝，未返回期望的 `registry_schema_unsupported`。该 P1 实现缺陷已原样保留，未修改 backend 或放宽独立断言；因此本轮未运行 Terra/P0/全量回归，也未批准 A3 evidence 发布。待 Terra 让 schema 类型、主键、检查约束、幂等唯一约束及 metadata 定义均 fail closed 后，由 Luna 原样复测。

本轮仅新增本独立测试并更新本说明、AI 辅助记录和共享工作日志；未修改冻结规格、P0/Schema/sample、PROJECT_PROGRESS、Terra unit、第三方资源台账、HTTP/worker/A4 或扫描分析组员 B2-B7/前端组员任务。当前证据边界仍是本机 macOS/POSIX 单机持久注册表，不外推 Linux isolation、TrustedEgress、多机并发、FastAPI/API、OpenGuard-Bench 或完整竞赛材料。

#### A3-0 schema hardening 复测

按 Terra `2325 COMPLETE` 原样复跑：既有独立 31 项 `31 passed`；新增最小 schema probe 14 项 `14 passed`；独立文件合计 `44 passed`。新增 probe 未改变冻结 ID，逐项验证 metadata 列定义、scan_runs 类型/notnull/PK、revision `CHECK (>= 1)`、幂等 UNIQUE、额外 index/列均 fail closed 为 `registry_schema_unsupported`，并验证合法库 close 后可重开读取。

后续门禁结果：Terra A3 `31 passed`；A3 独立+Terra 合计 `75 passed`；P0 `46 passed`；全量 `499 passed`；`schema_export_equal=True`；compileall、`git diff --check`、尾随空白、敏感模式和 world-writable 文件检查通过。A3-0 独立 P1 已关闭，但仍需 Root/Sol 做不可变提交绑定与有界 evidence 裁决；本地单机 POSIX 结果不外推 FastAPI、worker、Pipeline、Linux isolation、TrustedEgress、集群容灾、Bench 或完整竞赛材料。

#### FINAL-A3-001 sqlite_master 对象 allowlist 独立复测

按 Terra `2345 COMPLETE` 原始探针要求，在既有独立测试中加入 1 组 table/view/`AFTER INSERT` revision trigger 探针：探针选择 `1 passed`，Luna 全文件最终 `45 passed`。合法库分别注入额外用户表、view 及会把新行 revision 改为 999 的 trigger；每次重开均稳定返回 `registry_schema_unsupported`，移除对象后合法库可重开，原快照仍为 revision 1。未修改冻结 `8 POS + 16 NEG` ID 或放宽断言。

联合复测：Terra A3 `32 passed`；A3 独立+Terra 合计 `77 passed`；P0 `46 passed`；全量 `501 passed`；`schema_export_equal=True`；compileall、`git diff --check` 和敏感检查通过。FINAL-A3-001 已由独立测试关闭，但 A3 candidate evidence 仍需 Sol/Root 做不可变提交绑定、范围声明和最终裁决；结果仅覆盖本机 macOS/POSIX 单机 registry，不外推 HTTP、worker、Pipeline、Linux isolation、TrustedEgress、集群容灾、Bench 或完整竞赛作品。
