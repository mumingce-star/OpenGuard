# B07 受控 Linux 性能收据 v2

`openguard.controlled-pipeline-receipt/2` 是性能采集的固定输入契约，不是性能结果，也不会启动扫描。

每份收据必须绑定固定 source commit/source hash、输入/配置/结果 SHA-256，并且只接受 `execution_mode=controlled_linux`、`production_scan_started=false`。正式数据只能由 A 在受控 Linux 环境采集；Windows、本地开发、手写 JSON 和本文件中的测试对象不能作为正式性能结论。

环境记录必须包含 Linux kernel 与镜像 digest、CPU 型号/逻辑核数、内存限制/观测峰值，以及 ScanCode、Syft、静态 Detector、规则版本。每次运行明确标记 `cold` 或 `warm`，且五个阶段按固定顺序存在：`unpack`、`scancode`、`syft`、`static_detector`、`rule_consolidation`。失败保留收据、失败分类和发生阶段；不允许删除失败样本改善失败率。

汇总器至少接收两份同环境收据，并输出总耗时、冷/热耗时与每阶段的 p50/p95、阶段计时覆盖率、成功数、失败率和失败分类。输出固定标记 `formal_performance_claimed=false`，因而即使未来的受控 Linux 收据通过校验，也仍需 A 的正式采集方案、原始收据和人工复核才能提出正式性能结论。

```powershell
node benchmarks/b07-summarize-receipts.mjs --input controlled-linux-receipts.json --output b07-summary.json
node --test tests/b06_b07_p2b_contract.test.mjs
```
