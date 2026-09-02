# Backend 模块

计划包结构：

```text
app/
├── api/             # scan、findings、reports、benchmarks
├── ingestion/       # repo、zip、workspace
├── scanners/        # scancode、syft、manifest、AI assets
├── domain/          # 统一数据模型
├── knowledge/       # SPDX、OSI、许可证义务
├── risk/            # 确定性规则和证据链
├── ai/              # 结构化抽取、解释和整改建议
├── reports/         # HTML、JSON、CSV、资源清单
├── persistence/     # SQLite 与迁移接口
└── security/        # 限额、路径、防泄漏和清理
```

第一阶段不执行目标仓库代码，也不安装其依赖。

## A2-0/A2-1 本地 ZIP 安全边界

`app.ingestion.ZipIngestionService` 是当前首条不联网的输入纵切。服务在构造时只
接受管理员提供的、已存在的绝对 POSIX workspace root 和 `ZipSafetyLimits`；配置在
启动时校验，调用方没有可以提高上传、解压、文件、路径或压缩比限额的请求参数。

它先将 ZIP 流受限写入 descriptor-relative workspace，随后在写入目标树前验证所有
成员名、NFC/case-fold 冲突、文件/目录冲突、加密与已知 Unix 特殊类型，以及首段为
`~` 或 `~user` 的 home shorthand；并交叉核对
central directory 与每个 local header 的标志、压缩方式、文件名、CRC 和尺寸。小型
ZIP64 尺寸字段及当前支持的数据描述符会与 central directory 一致性校验，任何 local/
central 不一致都以 `invalid_archive/archive_integrity_failed` 拒绝。普通文件经
`openat`/`dir_fd`、`O_NOFOLLOW` 和 `O_CREAT|O_EXCL` 流式新建；文件清单从该树重新
计算 SHA-256，并以 `openguard-inventory-v1` 生成稳定 root digest。所有成功和失败
路径都会尝试清理本任务 workspace；清理失败会失败关闭并阻止返回 inventory，因而不会
发布部分树。

零或未知 ZIP external attributes 被当作新的普通文件字节，不恢复权限、owner、ACL、
xattr 或链接。已知 symlink、device、FIFO、socket 等类型会被拒绝。

稳定 `details.reason` 契约与冻结安全验收一致：全部原名/NFC/case-fold/文件目录冲突
统一为 `invalid_archive/archive_duplicate_path`，已知特殊类型为
`invalid_archive/archive_entry_type_unsafe`。上传、总解压、单文件、条目数、压缩比、
路径深度和路径长度配额统一为 `archive_limit_exceeded`，其 reason 分别为
`archive_upload_size_limit`、`archive_total_size_limit`、`archive_single_file_limit`、
`archive_entry_count_limit`、`archive_ratio_limit`、`archive_path_depth_limit` 和
`archive_path_length_limit`。

当前范围不包含公开 Git、TrustedEgress、Linux cgroup/network namespace、持久任务
注册表、最终 API 状态映射或完整 ZIP64/多卷/header-overlap 语料证明；macOS 的单元
和文件系统测试不能作为这些部署级安全控制的证据。
