# Hugging Face Resource Profile 固定快照包（v1）

本包保存 2026-09-20 通过 Hugging Face 公开 REST API 采集的最小、脱敏元数据观察值：5 个 model 与 5 个 dataset。每个 `snapshots/**/*.json` 都是独立的不可变源文件；`manifest.json` 将每个观察字段绑定到该文件的 SHA-256 与 RFC 6901 JSON Pointer。

快照没有保存模型权重、数据样本、README 全文、cookie、鉴权头、账户信息或完整 API 响应。`source_url` 中的 `expand[]` 参数限定了当时请求的字段；复现时请将远端响应视为可能变化的当前状态，不能用它替换本包的固定字节。

`declared_license_raw` 是 provider 声明的原始值，只用于展示和后续人工核查。它不是 SPDX 标准化结果，`license_expression_id` 在所有真实快照和负例中均为 `null`。同理，`private=false`、`gated=false`、存在 revision、响应可读取或声明许可证，都不是授权证明；所有记录固定为 `authorization_status: "pending"`。

`counterexamples/` 下的文件均为**合成负例**，不是对远端资源现状的陈述：分别覆盖缺失 revision/许可证、顶层与卡片许可证声明冲突，以及 `NOASSERTION` 与不支持的 `gated="auto"`。测试必须确保这些例子不会被自动补全、标准化为正式许可证表达式或提升授权状态。

后端 B 的 `HuggingFaceMetadataParser`（`openguard-huggingface-metadata/1`）直接消费本包，
对应测试为 `tests/unit/test_p1_huggingface_metadata_parser.py` 与
`tests/security/test_p1_huggingface_metadata_parser_independent.py`。本包是离线回归基线；
后续真实资源验收必须另存观察回执，不得用远端当前响应改写这些固定字节。
