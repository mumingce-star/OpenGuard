# Hugging Face Resource Profile 固定快照包 v2

v2 固定包含 5 个 model、5 个 dataset 离线快照，以及字段缺失、许可证冲突、不支持字段和非法 identity 反例。每个正例同时以 `source_file_sha256` 与 `source_observation_sha256` 绑定同一脱敏离线观察文件；这两个 Hash 只证明仓库内固定字节，不能证明上游当前状态。

这些 JSON 是受控的离线测试输入，不是远端资源当前状态的声明。每个文件由 `manifest.json` 固定 SHA-256；测试只在内存中构造 `TemporaryMetadata`。不保存权重、数据样本、cookie、鉴权头、完整响应或账户信息。

解析器必须验证 provider/kind/identity、精确 API source URL、UTC `fetched_at`、body SHA-256、revision 与 revision mode。来源质量不足或非法输入时统一 `metadata_invalid` 失败关闭；可解析但字段缺失/冲突时只输出 pending observation 与 coverage gap。测试禁止 socket/subprocess；所有授权和许可证适用性均在该包范围外。
