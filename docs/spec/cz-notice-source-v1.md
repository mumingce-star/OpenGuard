# CZ NOTICE 生产来源契约（v1）

`openguard.notice-source/1` 是 CZ 的独立、纯采集输出包。它不是现有 v3 NOTICE/license facts 库存，也不是 A 侧 reader、数据库记录、公共 API、Report 或扫描主链的一部分。

## 已确认 R1 决策

- 不放宽现有受控读取限制：单文件 4 MiB、会话总读取 16 MiB；采集器只调用 `ReadOnlyScanSession.read_bytes`。
- 保留限额：全文最多 64 KiB/项；摘录最多 4 KiB/项；单 observation canonical JSON 最多 128 KiB；最多 1024 项；整个 canonical JSON（含 `package_hash`）最多 8 MiB。
- UTF-8 必须严格解码：不替换非法字符、不规范化 Unicode 或换行。摘录只在完整字符边界截取，`byte_range` 是原始字节范围。
- 可以消费 `completed` 或具有显式 coverage gap 的 `partial` 包；任何 binding/hash 不匹配必须拒绝。
- P1 不自动过期删除；本 DTO 只表达快照，可信保存、终态绑定、隔离恢复和发布权限仍由 A 侧负责。

## 包结构及不可混用语义

采集发生在 `ReadOnlyScanSession` 仍然有效时。此时 collector 只返回 `NoticeSourceCollection`：`schema_version`、`observed_at`、`coverage` 和 `observations`（含 caller 已知的 `collector` 与保守 `relation`）。它**不接收、不返回也不猜测** `scan_id`、`registry_revision`、`input_digest`、`inventory_digest` 或 `facts_hash`。

终态后 A 以真实 `ScanRun`、inventory 与 facts 闭包构造 `Binding`，调用 `bind_notice_source_collection(collection, binding=...)` 封装 `NoticeSourcePackage`。只有该终态包有 `binding.scan_id`、`registry_revision`、`input_digest`、`inventory_digest`、`facts_hash` 和 `package_hash`。ZIP 的 `input_digest` 是原 ZIP SHA-256；Git 的 `input_digest` 仍是来源 URL SHA-256，绝不是仓库内容或 archive bytes hash。包不提供或伪造 `archive_bytes`/`source.archive_bytes_sha256`。

`package_hash` 由 A 的终态封装步骤计算，不由 collector 或包内自报字段提供。canonical 材料是 UTF-8、键排序、紧凑 JSON 的完整终态 payload：`schema_version`、`observed_at`、`coverage`、`observations`、`binding`；明确排除 `package_hash` 自身。包内 `package_hash` 只能证明该 JSON 自洽，不能独立证明扫描归属；A 仍须以实际终态 ScanRun/registry/facts 逐项复核 binding。

每个 observation 的 `content` 必须使用以下五态之一：`full`、`excerpt`、`not_observed`、`not_scanned`、`read_failed`。只有 `full`/`excerpt` 才能含 `text`、`encoding=utf-8`、`byte_range`、`truncated`、`retained_bytes_sha256` 和已完成实际读取的 `whole_bytes_sha256`。现有 Evidence 的 `excerpt` 与 `content_hash` 不是本 DTO 的保留正文和 `retained_bytes_sha256`，不得互换。

资源关系以 `relation.state=resolved|unresolved` 表达；仅当调用方提供唯一、稳定且来源一致的依据时，`resolved` 才可带 `subject`。否则必须是 `unresolved`、`subject=null`，并保留 `basis`；采集器不生成或猜测正式 Resource/Evidence ID。

`coverage` 汇总 `omissions` 和 `gap_codes`。包括预算、路径不在 inventory、UTF-8 失败、会话 I/O/完整性失败在内的缺口必须显式呈现；没有缺口才可标记 `completed`。

## 接线边界

调用方在已完成 ZIP/Git ingestion 后、`ReadOnlyScanSession` 尚存时提供真实 inventory 中的候选路径及保守关系基础；此时不要求终态 revision/facts。CZ collector 不读取 archive 路径、不联网、不改写 `ScanRun`，也不消费 v3 离线 facts。A 只在终态后取得实际 binding，再封装、调用 validator、可信保存、只读 reader 与工厂接线。
