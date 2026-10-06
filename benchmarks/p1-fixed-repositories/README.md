# P1 固定仓库 Bench 准备台账

`preparation.json` 固定保留 25 个候选槽位，其中 7 个为 holdout。它现在是准备台账，**不是**正式质量评测：所有记录均为 `planned/not_collected`，因此没有 URL、commit SHA、输入哈希、抓取日期或许可证声明，也没有 Gold、预测、指标或质量结论。

收集一个样本时，必须把状态改为 `fixed`，并记录公开 URL、40 位 commit SHA、SHA-256 输入摘要、UTC 抓取日期和原样许可证声明。获取/哈希/许可证/扫描失败时状态必须为 `failed`，同时保留原因；不得删除失败样本以改善指标。

只有至少 20 个 `fixed` 样本、至少 5 个 `fixed` holdout 且无记录错误时，准备门禁才允许创建后续运行。Gold、预测、指标和运行绑定必须分别存于 `gold/`、`predictions/`、`metrics/`、`runs/`；运行记录还必须绑定 detector 版本、规则版本、配置 SHA-256 和输入 SHA-256。正式产物继续由 Bench 2.0 manifest 校验。

旧 9 个样例、0.1.0 检测器结果和 AI 单独标注资料均仅为探索资料，禁止复制、迁移或表述为本 P1 台账的 Gold、holdout、预测、指标或正式质量结论。
