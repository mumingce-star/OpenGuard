# B2/B3 外部扫描器适配边界

状态：`IMPLEMENTED_FOR_P0_ADAPTERS`
版本：`b2-b3-external-tools/v1`

本模块提供 ScanCode 与 Syft 的受限 JSON 适配，不改变冻结的 P0 公共模型。

- `run_json_tool` 仅使用参数数组调用已安装的工具：禁用 shell、标准输入为 `/dev/null` 等价物、标准错误不采集、默认 120 秒超时、输出上限 8 MiB，并把缺失、超时和失败转换为稳定错误码。
- 适配层不接收 `ReadOnlyScanSession` 的工作目录。该会话只授予可信、非执行式 parser 逐文件读取能力；若暴露目录给任意子进程会破坏 A2-2 的安全边界。
- ScanCode 与 Syft 均通过 `ZipIngestionService.ingest_with_tree_consumer` 接入受控 ZIP 物化阶段：仅在 POSIX 环境把只读目录描述符继承给固定子进程，并以子进程自己的 `/proc/self/fd/<n>` 作为输入；扫描前后均校验 inventory seal。工具失败只能产生 partial/error，不得伪造 pass。通用 A4 编排、ScanRun partial/error 映射与 Linux ZIP 端到端回归仍未接入。
- ScanCode 只生成带相对 locator 的 `Evidence(kind=license_text)` 和原始许可证候选字符串。B4 才能将候选标准化为 `LicenseExpression`。
- Syft 只在 artifact 含有相对位置证据时生成 `Component`；不猜测许可证、版本或来源 URL。真实 Syft 1.51.0 回归使用公开 npm lockfile fixture；Windows 直接目录输出的根相对反斜杠会在测试专用直接目录模式规范化，生产 ZIP 描述符模式仍只接受 `/proc/self/fd/<n>/...` 前缀。
- `merge_components` 按 PURL、否则 `(ecosystem,name,version)` 合并，保留全部证据和检测方法。元数据冲突清空冲突字段并产生诊断，置信度取保守最小值。

ScanCode 调用固定为 `--license --strip-root --json -`，因此输出 locator 与 ZIP inventory 使用同一相对路径空间。工具版本由部署配置固定并写入运行 provenance；本仓库不打包 ScanCode 或 Syft 的二进制文件。
