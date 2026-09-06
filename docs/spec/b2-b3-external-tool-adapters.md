# B2/B3 外部扫描器适配边界

状态：`IMPLEMENTED_FOR_P0_ADAPTERS`
版本：`b2-b3-external-tools/v1`

本模块提供 ScanCode 与 Syft 的受限 JSON 适配，不改变冻结的 P0 公共模型。

- `run_json_tool` 仅使用参数数组调用已安装的工具：禁用 shell、标准输入为 `/dev/null` 等价物、标准错误不采集、默认 120 秒超时、输出上限 8 MiB，并把缺失、超时和失败转换为稳定错误码。
- 适配层不接收 `ReadOnlyScanSession` 的工作目录。该会话只授予可信、非执行式 parser 逐文件读取能力；若暴露目录给任意子进程会破坏 A2-2 的安全边界。
- A4 ZIP 编排器复用 A2 已物化并封印的树，通过可信 fd 回调执行固定 ScanCode/Syft 命令，不重复物化，不向 parser 暴露目录。工具失败保留已有事实并生成脱敏 ScanError，以 partial 收口。
- ScanCode 只生成带相对 locator 的 `Evidence(kind=license_text)` 和原始许可证候选字符串。B4 才能将候选标准化为 `LicenseExpression`。
- Syft 只在 artifact 含有相对位置证据时生成 `Component`；不猜测许可证、版本或来源 URL。
- `merge_components` 按 PURL、否则 `(ecosystem,name,version)` 合并，保留全部证据和检测方法。元数据冲突清空冲突字段并产生诊断，置信度取保守最小值。

工具版本由部署配置固定并写入运行 provenance；本仓库不打包 ScanCode 或 Syft 的二进制文件。

## 真实 ZIP 接线（2026-09-05）

runner 增量读取 stdout，最多 8 MiB 加一个判定字节；超时、超限和退出均清理进程组并回收直接子进程。ScanCode 以受控 fd 目录为 cwd 扫描 `.`，返回文件集合须覆盖 inventory。Syft 根相对路径只在 source 精确匹配受控目标时接受，最终均须对应 inventory。Evidence.content_hash 绑定封印文件 SHA。

A4 保留 manifest Component ID 和许可证声明绑定，给精确匹配组件追加 Syft 证据。ScanCode 文件候选单独标准化并保持 pending，不将根 LICENSE 分给依赖。无声明组件为 NOASSERTION。默认开关关闭，Compose 启用；工具不完整时保留可用事实并返回 partial/report/95。公开 Schema、API、worker 和 B5 规则语义不变。
