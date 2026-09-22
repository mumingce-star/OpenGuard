# P0 B03/B04 真实事实库存 v3

`tests/fixtures/notice-license-facts-v3/` 是独立、离线、可复现的事实库存；它不替换 B02 已冻结的 v2 输入，也不产生 NoticeDraft、授权、许可证适用性、兼容性、义务或违规结论。

## 覆盖范围

- 根项目 `LICENSE`；根 `NOTICE` 和项目专属 copyright 未观察到时明确记录为 gap；
- `backend/pyproject.toml` 中的 Python 运行时和开发直接依赖；
- `backend/java/pom.xml` 中的 Java 直接依赖；
- `frontend/package.json` 中的 npm 运行时和开发直接依赖；
- B01 固定的 Hugging Face 模型和数据集快照。

## 证据与失败关闭

每个事实必须有 `fact_provenance_evidence_ids`。每条 Evidence 都保存来源路径、语义 locator、完整来源文件 SHA-256、选中内容 SHA-256、采集时间、producer/version 和 source revision。只有 JSON 值填写 `selected_json_pointer`；TOML 和 XML 使用可复核的语义 locator，避免伪造 JSON Pointer。

根 LICENSE 仅为 `text_observed`；AI 卡片 license 字段仅为 `provider_declared_unverified`；项目清单只证明依赖声明存在。许可证、NOTICE、copyright 未观察到时一律是 `gap`，且 gap 不等于违规。

所有事实的 `authorization_status` 固定为 `pending`，`license_expression_id` 固定为 `null`。扫描到可见性、版本、provider 标签或根 LICENSE 均不得提升为授权或许可证结论。

## 验收

`generate.mjs --check` 验证生成物未漂移；Node 和 Java 测试分别验证 Hash 粒度、locator、证据引用闭包、Draft 2020-12 schema 及 pending/null 失败关闭条件。所有过程不访问网络也不启动服务。
