# A2-0/A2-1 本地 ZIP 实现终审

状态：`SOL_FINAL_AUDIT_COMPLETE_LOCAL_SLICE_CONDITIONAL`

审计日期：2026-09-02

审计对象：分支 `feat/a2-zip-ingestion` 的不可变实现提交 `53499ea`（基线 `0b7e4b7`）所包含的 A2-0/A2-1 本地 ZIP 纵切。

## 1. 范围与结论

本审计只判断当前本地 ZIP 接收、预检、安全物化、inventory 和清理纵切，不把设计审查、单元测试或 macOS 文件系统结果外推为 A2 系统完成证据。

终审结论为：**本地 ZIP 最小纵切条件通过；A2 总门禁未通过。** 当前实现已形成可运行、失败关闭且不改变 P0 的开发级纵切；冻结 `SEC-A2-008..013/016` 中仍有结构语料、并发完整性和生命周期控制缺口，因此不能把 101 项全量回归写成完整 ZIP corpus、TrustedEgress、Git 或 Linux 隔离已经验收。

| 审计面 | 结论 | 说明 |
|---|---|---|
| P0 v0.1.1 模型、API、Schema、sample | `PASS-UNCHANGED` | 本分支差异不含 `backend/app/domain/models.py`、`docs/spec/p0-domain-contract.md`、`schemas/p0/scan-result.schema.json` 或 `examples/sample-scan-result.json`；未新增公共字段、枚举、endpoint 或错误包络。 |
| 稳定 ZIP code/reason | `PASS-COVERED-SCOPE` | 已测的结构、路径、碰撞、类型和七类配额映射与冻结矩阵一致；`SEC-A2-009` 已消除路径形态与路径阈值的文字歧义。 |
| local/central header、CRC、data descriptor、小型 ZIP64 | `CONDITIONAL` | 已有定向实现和小型样本；未形成多卷、offset/区段重叠、完整 ZIP64/descriptor 变体的版本化畸形 corpus。 |
| descriptor-relative 写入与失败关闭 | `PASS-DEV-SLICE` | POSIX 能力启动探测、随机 0700 workspace、`dir_fd`、`O_NOFOLLOW`、独占新建和 descriptor-relative 清理已落地；macOS 开发证据不替代 Linux profile。 |
| inventory/root digest | `PASS-STABLE-OUTPUT` | 普通文件经 descriptor 重读，按 UTF-8 path 排序并生成冻结 `openguard-inventory-v1` 根摘要；同尺寸并发内容改写的检测仍未闭合。 |
| 生命周期、registry/API | `NOT-CLOSED` | 当前调用只返回内存 inventory 并立即清理，适合本子纵切；尚无最后只读消费者、quarantine、worker 禁用、orphan 清道夫、durable registry 或 `ScanRun` 映射。 |
| TrustedEgress、Git、Linux cgroup/deny-egress | `BLOCKED-OUTSIDE-SLICE` | 本轮没有实现或运行证据，仍按冻结设计保持阻塞。 |

## 2. 实现模块映射

| 模块 | 当前责任 | 终审判断 |
|---|---|---|
| `backend/app/security/errors.py` | 内部不可变 `IngestionSecurityError(code, reason)`，不携带原始输入 | 适合内部安全边界；尚未接公开 HTTP/异步 `ScanError` mapper。 |
| `backend/app/security/limits.py` | 管理员配置范围、上传/单文件/总量/ratio 的实际流式计数 | 请求不能提高限额；声明值只作预检，实际输出继续计数。 |
| `backend/app/security/archive_path.py` | 分段、NFC、case-fold、设备名、home shorthand、深度和 UTF-8 长度策略 | 主要策略与稳定 reason 对齐；首段 `~`/`~user` 已按窄规则拒绝，后续普通文件名中的 `~` 保持允许。 |
| `backend/app/security/secure_dir.py` | POSIX 能力探测、受控 root、随机 workspace、逐段 no-follow 写入和递归清理 | descriptor-safe 结构正确；尚无 quarantine/orphan/worker 不复用控制面。 |
| `backend/app/ingestion/workspace.py` | workspace 生命周期入口 | 当前只负责 create/cleanup/close，不是完整 `TaskSupervisor`。 |
| `backend/app/ingestion/zip_preflight.py` | central metadata、local header、路径、类型、声明配额和 descriptor 交叉验证 | 已覆盖当前小型支持集；未显式闭合多卷、offset/区段重叠与完整 ZIP64 corpus。 |
| `backend/app/ingestion/zip_stream.py` | 上传落盘、预检后流式解压、实际配额、inventory、`finally` 清理 | 不调用 `extract`/`extractall`；任一失败不返回部分 inventory。 |
| `backend/app/ingestion/inventory.py` | descriptor-relative 普通文件重读、单文件 SHA-256、稳定 root digest | 排序/摘要可复算；读取前后仅比较 type/dev/inode/size，未证明同尺寸并发内容改写必被拒绝。 |

## 3. 冻结错误映射

下表是本子纵切可对外引用的冻结映射。实现中的 `archive_stream_invalid`、`archive_unsupported_compression`、`posix_security_capability_unavailable`、`workspace_*` 等内部 reason 尚未接 API mapper，不应在 Root 冻结前扩写成新的公共 P0 契约。

| 条件 | `code` | 冻结 `details.reason` |
|---|---|---|
| 非 ZIP、截断或结构/CRC 不一致 | `invalid_archive` | `archive_not_zip` 或 `archive_integrity_failed` |
| 加密 ZIP | `invalid_archive` | `archive_encrypted` |
| 非法路径形态 | `invalid_archive` | `archive_path_unsafe` |
| 原名重复、NFC/case-fold 碰撞、文件/目录冲突 | `invalid_archive` | `archive_duplicate_path` |
| 已知不安全条目类型 | `invalid_archive` | `archive_entry_type_unsafe` |
| 上传、总解压、单文件、条目数或 ratio 超限 | `archive_limit_exceeded` | `archive_upload_size_limit`、`archive_total_size_limit`、`archive_single_file_limit`、`archive_entry_count_limit`、`archive_ratio_limit` |
| 路径深度或 UTF-8 长度超限 | `archive_limit_exceeded` | `archive_path_depth_limit` 或 `archive_path_length_limit` |

任何上述输入安全失败都必须整体失败，不生成 `partial`/`completed`。当前服务尚未建立 HTTP envelope 或异步 `ScanRun`，因此测试中的内部异常不能冒充最终 API 证据。

## 4. ZIP 支持与不支持边界

### 当前已实现并有定向测试

- 单文件流中的普通 ZIP 目录/文件，压缩方式限 `stored` 和 `deflate`；嵌套 ZIP 只作为普通文件字节，不递归展开。
- central/local 的 flag、compression、编码后 filename、CRC、compressed size、uncompressed size 交叉检查。
- 带签名的小型 32-bit data descriptor 样本；读取末尾由 `ZipExtFile` 校验 CRC。
- 单普通文件、小数据量、ZIP64 size extra + ZIP64 EOCD/locator 的 `stored` 样本。
- 已知 Unix symlink/FIFO/device/socket 类型拒绝；零或无法判定的 producer 属性只按新普通文件字节写入，不恢复 owner、ACL、xattr 或权限。

### 不得由当前测试外推

- 多卷 ZIP 的显式拒绝、伪 EOCD/central directory、异常 offset、local/central/data range 重叠。
- ZIP64 offset、多个成员、ZIP64 data descriptor、extra field 排列/重复以及不同创建工具的完整变体。
- 未支持压缩算法、DOS/reparse/其他已知非 Unix 特殊属性的完整跨工具 corpus。
- 解压与 inventory 期间的真实并发父目录替换、同 inode 同尺寸内容改写。

因此，小型 ZIP64 和 data descriptor 的准确表述是“**当前限额内的两个定向构造样本通过**”，不是“完整 ZIP64/data descriptor 支持已验收”。

## 5. 路径、文件系统、inventory 与清理审计

已确认的正向性质：

- 路径在任何目标文件创建前规范化；重复、NFC/case-fold 碰撞和文件/目录冲突整包拒绝。
- 首段等于 `~` 或以 `~` 开头的 home shorthand 在物化前以 `invalid_archive/archive_path_unsafe` 拒绝；`ordinary/file~.txt` 仍作为普通路径数据，并已有 Terra unit 与 Luna 独立正反例。
- 安全 root 必须是绝对 POSIX 目录且不能 group/other writable；缺少 `dir_fd`、`O_DIRECTORY` 或 `O_NOFOLLOW` 能力时启动失败关闭。
- 目标文件通过父目录 descriptor 逐段打开并以 `O_CREAT|O_EXCL|O_NOFOLLOW` 新建，archive 权限和链接语义不被恢复。
- inventory 只接受普通文件，经独立 descriptor 重读生成每文件 SHA-256，再按冻结字节格式生成根摘要。
- success 和所有异常都进入 `finally` 清理；清理失败会替代先前结果并阻止成功返回。

仍需 Root 排期的差异：

1. inventory 的 before/opened/after 检查覆盖 type/dev/inode/size，但同 inode、同 size 的并发内容改写可能不被识别；`NEG-A2-024` 仍需实现和真实并发测试。
2. 当前服务在 inventory 形成后立即清理，适合“只返回内存 inventory”的纵切；接入扫描器后必须由 supervisor 延长至最后只读消费者结束。
3. `workspace_cleanup_failed` 已失败关闭，但尚未隔离残留目录、禁用 worker 或由受限清道夫回收；`SEC-A2-016` 不能据此标记完成。

## 6. 测试演进与当前证据

| 阶段 | Luna 独立安全 | Terra ZIP unit | 全量 | 结论 |
|---|---:|---:|---:|---|
| 独立首轮 | `21 passed / 14 failed` | 当时口径未重跑 | `83 passed / 14 failed`（97 项） | 发现 13 项 reason 漂移和 1 项 local/central 完整性缺陷。 |
| Terra 修复后、Sol 裁决前 | `33 passed / 2 failed` | `18 passed` | `97 passed / 2 failed`（99 项） | 两项失败是路径阈值 code 期望与冻结矩阵冲突。 |
| Luna 按裁决复测 | `35 passed / 0 failed` | `18 passed / 0 failed` | `99 passed / 0 failed` | 被覆盖的本地 ZIP 子纵切回归通过；首次失败链保留。 |
| 终审后 home shorthand 闭环 | `36 passed / 0 failed` | `19 passed / 0 failed` | `101 passed / 0 failed` | Terra 采用仅首段窄规则，Luna 独立覆盖拒绝与普通波浪号文件名非回归。 |

当前 36 项独立测试和 19 项实现侧测试使用标准库动态构造的小型、可审计 ZIP 字节与受控临时目录。它们是 macOS/POSIX 开发级实现证据，不是完整系统、供应链或部署证据。历史 21/14 到 35/0 的缺陷发现与修复链继续保留，终审后的 home shorthand 增量单独形成 36/101 口径。

## 7. 评委/Root 复现命令

在仓库根目录、已安装项目测试依赖的环境中执行：

```bash
PYTHONPATH=backend python -m pytest -q tests/security/test_a2_zip_security_independent.py
PYTHONPATH=backend python -m pytest -q tests/unit/test_a2_zip_ingestion.py
PYTHONPATH=backend python -m pytest -q tests/unit/test_p0_domain_models.py
PYTHONPATH=backend python -m pytest -q
git diff --check
```

复现记录已绑定实现提交 `53499ea`、Python 3.12.13 标准库 `zipfile`、macOS 本地开发 profile、默认服务端配置、命令、结果、复核角色与脱敏状态。该绑定只支持本地开发纵切证据；后续 Linux/容器 profile 仍须生成独立运行记录。

## 8. 证据等级与编号建议

- `EVD-S2-DESIGN-001` 只证明 S2/A2 设计、实现审查和独立可测性追溯，**不得**作为本次 ZIP 实现通过证据。
- Root 已分配 `EVD-A2-ZIP-IMPL-001`，绑定提交 `53499ea`、2026-09-02 本地复现、Python 3.12.13、独立安全测试 36 项与全量 101 项、Root/Sol/Terra/Luna 复核链和推送前脱敏检查。它只能支持 `verified-local-dev-slice` 主张，不得被引用为 A2 总门禁、Linux 隔离、TrustedEgress 或完整 ZIP corpus 已通过。
- 当前可给出的等级是 `verified-local-dev-slice`：实现已读审、36 项独立安全测试和 101 项全量回归可复现，但系统级控制与完整 corpus 未闭合。

## 9. 未关闭门禁与 Root 交接

以下条件保持开放，任何一项都不能用本地 ZIP 绿灯替代：

1. TrustedEgress 的逐连接 DNS/实际 destination IP/TLS SNI、重定向和隧道字节硬限额；
2. Git no-checkout/tree/blob materialization、hook/filter/LFS/credential/proxy 隔离；
3. 受支持 Linux non-root、只读输入、独立 temp、cgroup v2、process/fd/disk 和 deny-egress profile；
4. 完整版本化 ZIP 畸形 corpus，以及上节 inventory/清理缺口；
5. durable registry、跨 worker/重启幂等、最终 HTTP/`ScanRun` 错误映射与完整生命周期；
6. 实际依赖/基础镜像版本、来源、digest/checksum/signature、SBOM/NOTICE 和第三方台账。

Root 下一步应先决定本审计列出的剩余实现差异是否进入 A2-1 修复批次，再由 Terra 修实现、Luna补独立用例；随后冻结提交、分配实现 evidence ID、更新 `PROJECT_PROGRESS.md` 并决定提交/推送。本审计本身不授权这些后续动作。

## 10. 本地 ZIP CLI 演示终审

终审状态：`PASS-IMPLEMENTATION / BLOCK-EVIDENCE-FREEZE-DOC-TRACEABILITY`。

本节只扩展“如何让评委离线复现既有 ZIP→inventory 纵切”，不扩大第 1 至 9 节的实现和证据边界。`python -m app.cli LOCAL_ZIP` 接受恰好一个参赛者本地准备的 ZIP 路径；`--help` 只显示单行用法。CLI 没有网络、Git、目标代码执行、依赖安装、HTTP API、P0 字段或安全限额覆盖参数，构造 `ZipIngestionService` 时使用既有 `ZipSafetyLimits` 默认值。

| 终审面 | 结论 | 可核验行为 |
|---|---|---|
| 成功输出 | `PASS` | 退出 0；stderr 为空；stdout 为单行 UTF-8 JSON，含 `schema=openguard.zip-inventory`、`version=1`、`root_digest` 和按 UTF-8 相对路径稳定排序的 `entries`；不含 workspace 或输入 ZIP 的本机路径。 |
| 安全拒绝 | `PASS` | 路径穿越等 `IngestionSecurityError` 退出 1；stdout 为空；stderr 仅为代码拥有的 `code:reason`，不输出解析器异常、堆栈或本机路径。 |
| 调用/文件错误 | `PASS` | 参数数量错误或输入文件不可用退出 2，分别输出 `invalid_request:invalid_arguments` 或 `invalid_request:input_file_unavailable`；不回显用户路径。 |
| 默认限额 | `PASS-NO-OVERRIDE` | CLI 没有上传、解压、文件、路径、压缩比或 cleanup 限额参数；请求侧不能抬高既有服务默认值。 |
| 临时目录 | `PASS-COVERED-SCOPE` | 外层 `TemporaryDirectory` 与服务内 task workspace 均有 `finally`/上下文清理；成功和受控拒绝测试均证明无 task 残留，cleanup 失败仍失败关闭。quarantine、worker 禁用和 orphan 清道夫仍不在该结论内。 |
| 评委解释口径 | `PASS-BOUNDED` | 运行说明明确要求用户自备本地 ZIP，并把结果限定为安全接收、校验、临时物化和 inventory/root digest；不得介绍成 Web 产品、依赖/许可证扫描结果或 A2 完成证据。 |

本轮终审实跑：Luna CLI 独立 `5 passed`；Terra CLI+ZIP `24 passed`；全量 `111 passed`；P0 `46 passed`，其中 P0 测试同时验证 sample、Draft 2020-12 存储 Schema 和 `ScanRun.model_json_schema()` 等值；`--help` 与真实有效/穿越/缺失输入的模块入口均按 0/1/2 退出且无路径泄漏。

证据冻结前有一项文档追踪差异必须由 Root/Luna 关闭：Luna 的 `20260902-1334` 收工记录称更新了 `tests/security/README.md`，但本轮终审的 Git 差异显示该文件相对基线未修改，文件中也没有 `tests/security/test_a2_zip_cli_independent.py` 的独立复现命令或 5 项结果。该差异不推翻 CLI 运行、独立测试或 111 项全量结果，但会造成“声明修改文件”与实际上传范围不一致；Root 应在固定证据前由 Luna 补充该说明，或以 append-only `AMENDMENT` 更正原记录。Sol 不越权修改 Luna 所有文件。

证据治理结论：CLI 实现可作为等级为 `verified-local-demo` 的**候选证据**；在上述文档追踪差异关闭，且 Root 固定包含本入口的不可变提交、Python/运行 profile、命令与输出摘要前，不得批准或分配 evidence ID。既有 `EVD-A2-ZIP-IMPL-001` 继续只证明提交 `53499ea` 的 `verified-local-dev-slice`，不能自动覆盖本次未提交 CLI 增量。

上传边界：仓库根存在一份未跟踪的用户本地技术 DOCX。本审计未读取、未解释其内容，也未对其作公开性、授权或脱敏判断；Root 必须将其从本分支暂存、提交和上传清单中排除。该文件的存在是发布边界风险，不是 CLI 演示证据。

本节不关闭完整 ZIP corpus、inventory 同尺寸并发改写、cleanup quarantine/worker/orphan、Git/TrustedEgress、Linux profile、durable registry、最终 HTTP/`ScanRun` 映射、依赖/许可证扫描或 A2 总门禁。

### 10.1 Root 证据追踪处置

`BLOCK-EVIDENCE-FREEZE-DOC-TRACEABILITY` 已于 2026-09-02 13:46 关闭：Luna 实际补充了 `tests/security/README.md` 的独立 CLI 复现命令、5 项覆盖范围及 `5 passed`/全量 `111 passed` 口径，并在共享日志以 AMENDMENT 更正先前声明。Root 随后独立复跑真实 ZIP CLI、全量 111 项、P0 46 项与 Schema 导出等值检查，结果通过。

证据编号 `EVD-A2-ZIP-CLI-001` 已绑定不可变实现提交 `910f745`，等级严格限定为 `verified-local-demo`。运行 profile 为 2026-09-02 macOS 本地开发环境、Python 3.12.13；复现入口、111 项全量测试、46 项 P0 回归、Schema 等值及 Root 真实成功/失败演示均记录于共享日志。本证据不改变第 10 节列出的任何开放系统门禁。
