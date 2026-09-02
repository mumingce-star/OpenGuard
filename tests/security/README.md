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
