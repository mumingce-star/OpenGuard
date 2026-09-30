# B04 NOTICE 来源事实包独立复核

本说明覆盖 `openguard.notice-source/1` 的离线来源事实包。它不产生许可证解释、授权判断、义务、合规结论或最终 NOTICE。

## 可复核边界

- `whole_bytes_sha256` 是采集到的完整原始字节哈希；`retained_bytes_sha256` 是包内保留 UTF-8 字节的哈希。
- `excerpt` 必须同时带 `excerpt_bytes_sha256`，且它必须等于 `retained_bytes_sha256`；两者都不等于全文哈希是允许的。
- `full` 的全文和保留内容相同，因此 `whole_bytes_sha256 == retained_bytes_sha256`，并且不带 excerpt hash。
- 空内容是可观察事实：`full`、`text=""`、`byte_range=[0,0]` 和空字节 SHA-256；它不表示缺失、许可状态或任何法律效果。
- 非 UTF-8、超单文件限制、预算耗尽、路径不在 inventory、读取失败均保留为 `not_scanned`/`read_failed` 与明确 gap；不得补写正文或静默删除。
- 内容重复不会合并或提升关系。每个 `observation_key` 与 locator 原样保留，关系只能是调用方提供依据的 `resolved`，或带原因但无 subject 的 `unresolved`。

## 公开复核 fixture

`tests/fixtures/notice-source-v1/public-collection.json` 是无第三方正文、可公开分发的合成来源事实集合，包含：完整内容、截断内容、空内容、重复内容、遗漏路径、已解析关系与未解析关系。测试将其绑定为终态包，再调用 `review_notice_source_package`；该投影只输出覆盖、遗漏/无法解析原因、关系状态和三种哈希，不输出法律语义。

复核命令：

```powershell
$env:PYTHONPATH='backend'; .\.venv\Scripts\python.exe -m pytest -q tests/unit/test_notice_source_collector.py tests/unit/test_notice_source_review.py tests/security/test_notice_source_contract_independent.py
```
