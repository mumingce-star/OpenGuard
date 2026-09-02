# B2/B3 外部扫描器适配边界

状态：`IMPLEMENTED_FOR_P0_ADAPTERS`
版本：`b2-b3-external-tools/v1`

本模块提供 ScanCode 与 Syft 的受限 JSON 适配，不改变冻结的 P0 公共模型。

- `run_json_tool` 仅使用参数数组调用已安装的工具：禁用 shell、标准输入为 `/dev/null` 等价物、标准错误不采集、默认 120 秒超时、输出上限 8 MiB，并把缺失、超时和失败转换为稳定错误码。
- 适配层不接收 `ReadOnlyScanSession` 的工作目录。该会话只授予可信、非执行式 parser 逐文件读取能力；若暴露目录给任意子进程会破坏 A2-2 的安全边界。
- 后续 A4 编排器必须在独立受控运行环境中物化树、调用固定的 ScanCode/Syft 命令，并把 `ToolExecution.error_code` 映射到 P0 `ScanError`。工具失败只能产生 partial/error，不得伪造 pass。
- ScanCode 只生成带相对 locator 的 `Evidence(kind=license_text)` 和原始许可证候选字符串。B4 才能将候选标准化为 `LicenseExpression`。
- Syft 只在 artifact 含有相对位置证据时生成 `Component`；不猜测许可证、版本或来源 URL。
- `merge_components` 按 PURL、否则 `(ecosystem,name,version)` 合并，保留全部证据和检测方法。元数据冲突清空冲突字段并产生诊断，置信度取保守最小值。

工具版本由部署配置固定并写入运行 provenance；本仓库不打包 ScanCode 或 Syft 的二进制文件。
