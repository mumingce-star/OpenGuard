# B01 Hugging Face metadata parser

## 交付边界

`backend/app/scanners/huggingface_metadata.py` 实现生产候选解析器
`HuggingFaceMetadataParser`，对应既有 `metadata-parser-port/1`。它只消费
`MetadataTransport` 已限制并绑定的内存 JSON；自身不联网、不读写文件、不持久化，
也不生成许可证表达式、授权结论、Evidence、Assessment 或 Report。

本批没有把 parser 注入默认应用工厂。默认 Profile refresh 仍应保持
`feature_disabled`，直到 A 线完成配置、存储和生命周期接线并通过独立验收。

## 输入与绑定

- provider 仅允许 `huggingface`，kind 仅允许 `model` / `dataset`；资源标识必须是
  大小写保留的 `namespace/name`。
- `TemporaryMetadata.source` 必须与显式传入的 `SourceDescriptor` 是同一对象；
  provider、kind、identity、revision、URL 来源均由 transport 掌握。
- `source_url` 必须精确等于由 provider/kind/identity/revision mode 构造的 Hugging Face
  API target；`fetched_at` 必须是 RFC3339 UTC `Z` 时间，body size 必须为正整数，body
  SHA-256 必须为 64 位小写十六进制。任一来源质量字段异常均为
  `ValueError("metadata_invalid")`，不降级为可信观察。
- 只接受 `application/json`、`metadata-source/1`、`hf-metadata-transport/1`，且
  `full_response_replay_available=false`。
- body 必须是 1 MiB 内非空 UTF-8 JSON object，长度与 SHA-256 必须匹配。
  重复键、NaN/Infinity、过长整数、非 object、非法 UTF-8 均统一失败关闭为
  `ValueError("metadata_invalid")`。
- `id` 必须精确匹配请求 identity；`sha` 只能是 40 位小写十六进制并与 descriptor
  一致。固定 revision 必须精确相等；无 `sha` 时只能保留为未确认状态。

## 规范化字段

| 输出字段 | HF JSON Pointer | 语义 |
|---|---|---|
| `canonical_id` | `/id` | 精确资源标识 |
| `revision` | `/sha` | 本次响应观察到的 revision |
| `visibility` | `/private` | `public` / `private` |
| `access_gate` | `/gated` | `gated` / `ungated`；未知值仅为 pending |
| `disabled` | `/disabled` | provider 声明的布尔值 |
| `last_modified` | `/lastModified` | 仅接受 RFC3339 UTC `Z` 文本 |
| `pipeline_tag`、`library_name` | 同名顶层字段 | 仅 model，缺失不补全 |
| `declared_license_raw` | `/cardData/license` 或 `/license` | 原始声明，固定为 pending |

顶层和卡片 license 冲突时分别输出两个 pending 字段并增加
`conflicting_declared_license`。缺失、类型不支持和 revision 未确认均转成稳定
coverage gap。解析器总状态固定为 `pending`：公开可读、非 gated、存在 SHA 或许可证
声明均不能证明使用授权；`NOASSERTION` 也不会变成许可证表达式。

未知字段完全忽略，完整响应不会进入 excerpt、field、gap、日志或数据库。parser
返回严格 `ParsedMetadataObservation`，供 Profile 服务在边界上再次验证并生成不可变
observation。

## 固定验收

离线验收保留 `tests/fixtures/huggingface/resource-profile-v1` 的 5 个 model、5 个
dataset 固定快照与 3 个合成反例；新增独立的
`tests/fixtures/huggingface/resource-profile-v2`，补充 2 个 model、2 个 dataset、
字段缺失、声明冲突和不支持字段反例。v2 文件是固定回归输入，不是远端当前状态声明。
测试覆盖 manifest 精确映射、冲突/缺失语义、端口兼容、descriptor/body/revision/来源
URL/采集时间篡改、重复键、非 object、非法 UTF-8、未知字段不泄漏、无 socket/subprocess
副作用和输入不变性。

建议命令（以项目锁定依赖环境为准）：

```powershell
$env:PYTHONPATH='backend'
python -m pytest -q tests/unit/test_p1_huggingface_metadata_parser.py tests/security/test_p1_huggingface_metadata_parser_independent.py
```

## 后续责任

- A/Root：默认工厂的显式 opt-in 接线、sidecar 初始化/关闭、失败原子性和
  Profile/Report 冻结引用。
- Luna：在授权网络环境对固定 5+5 资源执行独立真实 transport 验收；远端当前响应
  只能作为新观察，不能覆盖固定 fixture。
- Sol：复核字段/gap/许可证与授权语义，不把 raw declaration 提升为正式判断。
- xzb：工厂接线冻结后再接 Profile 刷新/展示页面。
- Root + Luna：Linux 生产镜像、Windows 支持边界、异机重启/权限/配额/离线失败关闭。
