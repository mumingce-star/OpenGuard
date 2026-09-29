# NOTICE source G2 独立验收与 A 侧交接包

状态：`离线验收通过；生产接入未开始`。本包只交接 `openguard.notice-source/1` 的受控采集、终态绑定与只读消费边界；不是 A factory、NoticeDraft、Profile、Report、公共 API 或正式授权/NOTICE 结论。

## 交接对象与唯一边界

1. CZ 在有效 `ReadOnlyScanSession` 内调用 `collect_notice_source_package(...)`，只能返回未绑定 `NoticeSourceCollection`。
2. A 在终态 `ScanRun` 与正式 Assessment 存在后，调用 `NoticeSourceAdapter.admit(...)`；adapter 必须自行读取真实 ScanRun/Assessment，构造 `Binding`，验证并保存 canonical package bytes。
3. A 仅能经 `NoticeSourceBindingService.bind(...)` 将 STAGED 包绑定到真实 `scan_id`、registry revision、input/inventory/facts SHA-256、Assessment ID/version 和 package hash。
4. 消费端只能经 `BoundNoticeSourceReader.read(...)` 读 BOUND 包；reader 不回读上游，不写入数据库，也不能以 caller 字段替代 binding。

## 不变量

- 采集阶段不得猜测或携带 `scan_id`、revision、input/inventory/facts hash；终态 binding 才可添加它们。
- ZIP `input_digest` 是原 ZIP 摘要；Git `input_digest` 是来源 URL 摘要，二者都不是 archive bytes hash。
- 保持 `partial` 的 omissions/gap；不得把 provider label、LICENSE 文本、gap 或 observation 升格为授权、SPDX、obligation 或最终 NOTICE 结论。
- `package_hash`、binding hash、私有 SQLite 文件/sidecar 权限、容量和 CAS 均失败关闭。
- G2 不启用生产能力；A 的 factory/NoticeDraft/Profile/Report 接线属于 G3，必须另行验收。

## 独立验收矩阵

| 验收主题 | 证据入口 | 当前结果 |
| --- | --- | --- |
| collector 内容、限额、partial、读取失败 | `test_notice_source_collector.py` | 通过 |
| package/binding 篡改拒绝 | `test_notice_source_contract_independent.py` | 通过 |
| A1 STAGED→BOUND、hash/scan/assessment 边界、容量、重启、reader 只读、DB/sidecar 篡改 | `test_p1_notice_source_binding.py` | Windows 上被 `fcntl` 收集阻断，需在受控 POSIX 环境复跑 |
| A2 adapter 真实 CZ collection、封口、容量、重启与 decode | `test_p1_notice_source_adapter.py` | Windows 上被同一 `fcntl` 收集阻断，需在受控 POSIX 环境复跑 |

Windows 上的 `ModuleNotFoundError: fcntl` 是 G8 平台兼容问题；它不能被记作 G2 通过、跳过或生产接入。必须保存受控 POSIX 完整输出，并在 G8 修复后重跑 Windows 集合。

## A 侧准入前检查

```text
collection -> adapter.admit -> STAGED
terminal ScanRun + matching Assessment -> service.bind -> BOUND
matching scan/facts/assessment tuple -> reader.read -> immutable package
```

任一 hash、revision、scan、Assessment、容量、权限或数据库完整性错误：拒绝且零绑定写入；不得重试覆盖 BOUND、DELETE 修复或回填 source。

## 禁止的状态表述

- “DTO/collector 已实现”不等于“生产已接入”；
- “集成分支历史发布”不等于“当前工作区已提交”或“main 已合并”；
- “离线 fixture 通过”不等于“真实 NoticeDraft/Report 已消费”；
- 任何 `pending` observation 不等于已验证授权或法律结论。

## 后续责任

- 后端 A：完成 G8 后复跑 A1/A2 组合测试；然后才可提议 G3 factory/NoticeDraft/Profile/Report 的独立设计与验收。
- Root：核对 POSIX 和 Windows 回执、敏感信息、暂存范围、提交和发布门禁。
- 真人负责人：确认目标环境与生产启用范围；本交接包不授予生产部署权限。
