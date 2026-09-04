# A6-0 确定性报告导出核心

状态：P0 冻结实现纵切
范围：项目负责人 A6；不包含扫描分析组员 B5 或前端组员 F0

## 1. 目标

给定已经通过 P0 `ScanRun` 校验、且状态为 `completed` 或 `partial` 的快照，生成可复现的内存报告：

- JSON：报告元数据和完整 P0 `ScanRun` 快照；
- CSV：附件 2 要求的七字段《开源及第三方资源使用清单》；
- HTML：可直接打开的静态扫描报告；
- `resource_inventory`：与七字段 CSV 相同的专用清单出口。

本纵切不创建或推断许可证、义务、风险和 AI 建议。`partial/rules/70` 可以导出阶段性报告，但必须保留原始错误，并明确“没有风险结果不等于通过合规核验”。

## 2. 稳定性与安全边界

- 只接受 P0 `ScanRun` 精确类型和冻结 `ReportFormat`；`queued`、`running`、`failed`、`cancelled` 不导出。
- 输出不注入新的当前时间，等价快照即使顶层集合顺序不同，也产生相同 JSON 字节和 SHA-256。
- HTML 对所有输入值做实体转义，静态页面声明禁止脚本、外部资源、表单和基地址。
- CSV 为 UTF-8 BOM，换行和制表符规范为空格，并对 `= + - @` 起始单元格增加文本前缀，避免表格软件公式执行。
- 未知许可证、义务、使用/开放方式和团队自主修改内容统一保留“待核验/待人工补充”，不得猜测。
- 输出只保存在内存；文件落盘、`ReportLink`、FastAPI 下载和 Pipeline REPORT 接线属于 A6 后续纵切。

## 3. 内部接口

```python
render_report(run: ScanRun, report_format: ReportFormat) -> ReportArtifact
```

`ReportArtifact` 提供 `format`、`media_type`、安全稳定文件名、`content` 和内容 SHA-256。错误只暴露：

- `report_invalid_argument`；
- `report_not_ready`。

本接口不改变 P0 Domain、JSON Schema、HTTP API 或 SQLite Schema。

## 4. 验收范围

- JSON 往返校验、稳定排序、内容摘要与输入不变；
- CSV 七字段、组件和 AI 资源映射、未知项诚实状态、公式注入防护；
- HTML 转义、CSP、完整/阶段性口径、结构化错误显示；
- 非终态和错误参数失败关闭；
- 不新增第三方依赖，不修改 `rules/`、`frontend/` 或组员模块。

## 5. 非目标

- 不实现 B4/B5 许可证标准化或规则；
- 不调用 Qwen3，也不补写 A5 建议；
- 不提供法律结论或“合规通过”推断；
- 不修改前端页面；
- 不接入 HTTP 下载、持久文件或 Pipeline REPORT 阶段；
- 不把本纵切标记为 A6 父任务或完整参赛作品已完成。
