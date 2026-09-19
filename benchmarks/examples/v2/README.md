# Bench 2.0 manifest 正反例

本目录是 `openguard-bench-manifest/2.0` 的可执行示例集。所有 artifact 都是零字节固定文件，仅用于演示路径、大小、SHA-256、引用闭包和治理准入，不代表真实评测数据。

## 正例

- `valid/smoke.json`：未冻结、无 evaluation，推导为 `smoke`。
- `valid/development.json`：gold 与 matching policy 已冻结，请求 `development`。
- `valid/reportable-single-human.json`：单真人时间隔离盲化复标，请求 `reportable_single_human`。
- `valid/reportable-independent.json`：两名不同真人独立标注，请求 `reportable_independent`。

## 反例

- `unknown-field.json`：未知顶层字段。
- `unsafe-path.json`：artifact 路径含 `..`。
- `dangling-reference.json`：来源 artifact 悬空。
- `split-leakage.json`：同一 family 跨 split。
- `hash-mismatch.json`：artifact SHA-256 不匹配。
- `holdout-exposure.json`：holdout 用于规则开发，正式准入被拒绝（退出码 3）。
- `revision-parent.json`：revision=2 但 parent 为空。

从仓库根目录运行：

```powershell
mvn -f backend/java/pom.xml exec:java `
  -Dexec.mainClass=dev.openguard.bench.BenchManifestCli `
  -Dexec.args="validate benchmarks/examples/v2/valid/development.json"
```

CLI 只在 stdout 输出一份稳定 JSON。退出码：0 通过、1 契约无效、2 输入/用法错误、3 请求准入等级未达到。
