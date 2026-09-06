# A6-2 Pipeline 终态报告发布

状态：P0 实现纵切
范围：项目负责人 A4/A6 接线；不包含扫描分析组员 B5、前端或持久任务队列

## 1. 目标

A6-2 把已验收的 A6-1 publisher 接到 Pipeline 的首次终态提交边界。当前 ZIP HTTP 主链在规则阶段
产生可恢复的 `rules_stage_not_connected` 时，必须一次性持久化：

- 真实 Python/JavaScript 依赖组件、证据与摘要；
- `partial/rules/70` 及原始结构化错误；
- JSON、HTML、CSV、资源清单四种已发布报告的 P0 `ReportLink`。

这是一份诚实的阶段性报告，不是 B5 许可证分析的替代实现。

## 2. 提交顺序与可见性

SQLite registry 禁止修改任何终态，因此不能先提交无链接 `partial`，再补写 `ReportLink`。worker
在构造 `completed` 或 `partial` 候选后执行如下顺序：

```text
running ScanRun
  -> 构造未提交的 terminal candidate
  -> 私有 store 发布四种报告
  -> 校验 publisher 只增加完整且不重复的四种 ReportLink
  -> 一次 revision CAS 提交带链接 terminal ScanRun
  -> 只读 API 对外可见
```

store 是文件事务边界，registry 是 API 可见性提交点。内容已经写入但 publisher 中断或终态 CAS
冲突时，SQLite 没有对应 link，API 必须返回 `409 report_not_ready`，不得通过扫描 store 猜测或暴露
orphan。若 SQLite 已登记 link，而 store 内容或 metadata 缺失/不一致，则视为服务端完整性故障并返回
脱敏 `500 report_storage_failure`。

## 3. 报告快照与自引用

`ReportLink.content_hash` 是报告内容的 SHA-256。若报告正文再嵌入该 link，就会出现摘要依赖自身的
递归定义。因此四种报告都渲染未含 delivery links 的分析终态快照；最终 SQLite/API `ScanRun` 保存
并公开权威 `report_links`。这不改变组件、许可证、证据、风险、整改、摘要、provenance、错误或终态
控制字段。

## 4. 失败语义

- `partial` 报告发布失败：保留原阶段、进度、聚合结果和原错误，追加脱敏
  `report_publish_failed`，终态仍为 `partial`；
- 原本可 `completed` 的任务发布失败：若已有聚合结果则在 `report/95` 结束为 `partial`，否则结束为
  `failed`；
- publisher 返回的对象若修改 link 之外任何事实，worker 拒绝该对象并按发布失败处理；
- registry CAS 冲突继续使用 A4 的稳定并发冲突语义，不覆盖其他 writer，也不暴露已写 orphan；
- 无 publisher 的既有 worker 调用保持原行为，确保内部测试和其他显式调用方向后兼容。

## 5. 当前产品能力与边界

默认 app factory 复用同一个私有 report store 分别供 ZIP runtime 发布、FastAPI 读取。用户提交合法
ZIP 后，可轮询得到 `partial/rules/70`，读取四个 link，并下载经过摘要复核的阶段性报告；后端重启后
仍可读取。

本纵切不连接 A5/Qwen3，不生成许可证表达式、义务或风险，不实现公开 Git、安全网络获取、持久
worker、lease/retry/recovery，也不修改前端。B5 到位后，A4 只需让规则阶段返回其真实 P0 事实，
现有终态 publisher 即可把这些事实原样写入报告。

## 6. 复现

```bash
PYTHONPATH=backend python -m pytest -q \
  tests/unit/test_a6_pipeline_publish.py \
  tests/unit/test_a6_report_exports.py \
  tests/unit/test_a6_report_delivery.py \
  tests/unit/test_a4_pipeline_worker.py \
  tests/unit/test_a4_local_zip_pipeline.py \
  tests/unit/test_a3_zip_background_scan.py \
  tests/unit/test_a3_fastapi_api.py \
  tests/unit/test_p0_domain_models.py
```

专项覆盖 10 项；上述联合验收覆盖 177 项。A6-2 分支受控完整集合为 `856 passed, 1 warning`。
