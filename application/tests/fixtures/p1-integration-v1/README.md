# P1 固定联验样本包 v1

本目录提供离线、确定性、可复算的 P1 验收输入，不启动服务、不执行真实扫描，也不生成最终 Report V2 快照或下载 API 响应。

覆盖内容：

- 同一 OpenGuard 项目的两个祖先关系 Git commit；较早 revision 为 `partial`，较新 revision 为 `completed`；
- 一份含真实 NOTICE gap Finding、`LIC-APACHE-2.0-NOTICE` 候选 Obligation 的 Assessment；
- 一份真实 derive 请求与来源严格指向 `/obligations/0` 的 Remediation Task 上游输入，并附机器可验的预期 Task；
- 精确 100、300、500 节点的 P1 ResourceGraphView；
- 205 条 P1 ScanHistoryItem；
- 直接引用真实 Hugging Face Resource Profile 与 NOTICE/license facts 的 Report V2 草稿输入；
- `manifest.json` 中固定 commit、每个源文件/产物 SHA-256 与机器可断言预期结果。

边界：provider license 只保留原始观察值，`license_expression_id` 保持 `null`，`authorization_status` 保持 `pending`；任何 gap、Finding 或 Obligation 都不构成许可证结论。

复算与校验：

```powershell
node tests/fixtures/p1-integration-v1/generate.mjs --check
node --test tests/p1_integration_fixture.test.mjs
py -m pytest -q tests/unit/test_p1_integration_fixture.py
```

如需有意更新样本，先确认两个固定 commit 与真实上游事实包仍符合用例，再运行不带 `--check` 的生成命令，并审阅全部 JSON diff。
