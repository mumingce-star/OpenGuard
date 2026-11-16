# NOTICE / license facts v2（后端 B03/B04）

本包是 v1 的确定性、向后隔离升级；v1 保持字节不变，以免破坏既有固定 commit/hash 验收。v2 仍只提供事实和 Report V2 草稿行，不创建正式 NoticeDraft、快照、数据库或下载 API。

v2 新增：

- `authorization_status=pending` 机器字段；
- `text_observed` 与 `provider_declared_unverified` 观察强度；
- `source_file_sha256`、`container_sha256`、`selected_content_sha256` 三层哈希语义；
- JSON Pointer 选值哈希、逐 Evidence `captured_at` 与 producer；
- 根项目固定 commit，以及所有关系的 `applicability=pending_review`；
- `GAP_NOTICE_FILE_NOT_OBSERVED`，避免把“没有独立 NOTICE 文件”表述成自动违规；
- Report rows 从 facts 确定性生成，机器字段逐项闭包，不允许手工漂移。

边界：任何 provider label、文件标题、NOTICE存在或gap都不等于许可证适用性、授权、违规或义务履行结论；`license_expression_id` 始终为空。

复算：

```powershell
node tests/fixtures/notice-license-facts-v2/generate.mjs --check
node --test tests/notice_license_facts_v2.test.mjs
```
