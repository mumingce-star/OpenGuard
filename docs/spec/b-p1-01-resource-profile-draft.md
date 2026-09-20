# B-P1-01：`ResourceProfileDraft` 与 Hugging Face fixture 映射契约

状态：设计冻结候选（尚未改变 P0/P1 Domain、API 或数据库）
版本：`resource-profile-draft/0.1`
所有者：Sol / Root（契约）；Luna（fixture 与回归）；Terra（后续 materializer）

## 1. 目标与非目标

`ResourceProfileDraft`（以下简称 Draft）是扫描分析阶段的**带证据候选事实**：它把离线、固定的 provider 响应或文档 fixture 归一化为模型、数据集、Space 或 API 的资源档案草稿。它不是 P0 `AIAsset` 的替代品，也不是许可、访问权或合规结论。

本工作包只定义：

- provider-neutral 字段、空值和冲突语义；
- Hugging Face（HF）model/dataset fixture 的离线 JSON Pointer 映射；
- Draft 到既有 P0 `AIAsset` 的受限投影条件；
- fixture 实施所需的正反例验收口径。

本工作包不定义联网抓取、令牌、页面爬取、下载文件、许可证 SPDX 标准化、授权确认、风险判定、公共 API、持久化或对当前 `schemas/p0/scan-result.schema.json` 的变更。`private`、`gated`、`disabled` 和 card 中的 license 文本均不能单独推导“可用”“获授权”“合规”或“不可用”。

## 2. 输入与信任边界

输入必须是受控目录内的单个 UTF-8 JSON fixture，且在解析前已由调用者给出相对路径、SHA-256 和采集时间。解析器不得访问网络、跟随外部 URL、读取 fixture 以外的文件或执行 fixture 内容。

每个被写入 Draft 的非空业务值必须由至少一条 `EvidenceRef` 支撑。`EvidenceRef` 在本设计中是轻量内部引用；后续 materializer 才把它转换为 P0 第一类 `Evidence` 对象并生成正式 `evidence_ids`。

```json
{
  "fixture_path": "huggingface/models/acme--demo-model.json",
  "fixture_sha256": "<64 lowercase hex>",
  "json_pointer": "/id",
  "observed_at": "2026-09-19T00:00:00Z"
}
```

`json_pointer` 遵循 RFC 6901；其中 `~` 写作 `~0`，`/` 写作 `~1`。指针只定位输入事实，不能表示对远端 URL 的再次验证。

## 3. Provider-neutral Draft

```json
{
  "schema_version": "resource-profile-draft/0.1",
  "draft_id": "rpd_<stable-id>",
  "resource_kind": "model",
  "provider": {"id": "huggingface", "display_name": "Hugging Face"},
  "identity": {
    "provider_resource_id": "acme/demo-model",
    "canonical_url": "https://huggingface.co/acme/demo-model",
    "revision": "<optional immutable revision>"
  },
  "display": {"name": "acme/demo-model", "summary": null},
  "lifecycle": {
    "last_modified_at": null,
    "disabled": null,
    "visibility": "unknown",
    "access_gate": "unknown"
  },
  "declared_metadata": {
    "license_text": null,
    "library_name": null,
    "task": null,
    "tags": []
  },
  "field_evidence": {"identity.provider_resource_id": ["evref_1"]},
  "diagnostics": []
}
```

| 字段 | 类型与约束 | 语义 |
| --- | --- | --- |
| `schema_version` | 固定字符串 | 当前固定为 `resource-profile-draft/0.1`；未知版本拒绝解析。 |
| `draft_id` | 稳定 ID | 基于 `schema_version`、`resource_kind`、`provider.id`、`identity.provider_resource_id`、`fixture_sha256` 计算；不包含显示文案、时间、tags 或授权状态。 |
| `resource_kind` | `model` / `dataset` / `space` / `api` / `unknown` | 由入口 fixture 的类别或确定性 discriminator 给出；不能从标签猜测。HF 本轮只接受 model、dataset。 |
| `provider.id` | 小写受控标识 | 如 `huggingface`；`display_name` 是展示字段，不能参与匹配或安全决策。 |
| `identity.provider_resource_id` | 非空、最多 200 字符的 provider 内标识 | 是同 provider、同 kind 下的主键；保留 provider 原始大小写，不从 URL 反推。 |
| `identity.canonical_url` | HTTPS、无凭据、无 query/fragment | 仅按本映射模板构造；不可构造或不匹配 ID 时为 `null` 并写诊断。 |
| `identity.revision` | 可空不可变修订 | 仅接受 provider 明确给出的 commit/SHA；`lastModified`、发布日期、下载数都不是 revision。 |
| `display.name` / `summary` | 可空展示文案，需长度上限 | 不作为身份、版本或许可事实。无明确字段时 name 回退到 `provider_resource_id`；summary 本轮不从 HTML/README 推断。 |
| `lifecycle.last_modified_at` | 可空 RFC 3339 UTC 时间 | 仅表示 fixture 中声明的最后修改时刻，不代表当前远端状态。 |
| `lifecycle.disabled` | `true` / `false` / `null` | 仅为 provider 声明的禁用标志；不等于访问权或合规状态。 |
| `lifecycle.visibility` | `public` / `private` / `unknown` | `private=true` 映射 `private`；`false` 映射 `public`；缺失/错误为 `unknown`。它是观察值而非用户有权访问的证明。 |
| `lifecycle.access_gate` | `gated` / `ungated` / `unknown` | `gated=true/false` 才可映射；不能由 HTTP 成功、标签或 `private` 代替。 |
| `declared_metadata.license_text` | 可空原始声明 | 只保存 fixture 明确字段中的文本/字符串；不是 SPDX、不是许可证已核验，更不改变 P0 `license_expression_id`。 |
| `declared_metadata.library_name` / `task` | 可空原始声明 | 分别记录运行库与任务/管线标签；不以它们反推资源类型。 |
| `declared_metadata.tags` | 已去重、稳定排序的字符串数组 | 仅展示/检索候选，不能独立提升任何安全、许可或访问结论。 |
| `field_evidence` | `字段路径 -> 非空 EvidenceRef[]` | 只允许为实际写入的非空字段登记；空值必须无证据，冲突值必须全量保留证据并写 diagnostic。 |
| `diagnostics` | 稳定排序的受控码数组 | 例如 `missing_required_id`、`invalid_timestamp`、`unsupported_fixture_kind`、`conflicting_card_license`；有身份级错误时不产出 Draft。 |

所有字符串最多 2,048 Unicode code points（`summary` 最多 4,000、tags 单项最多 200 且总数最多 100）。超限、控制字符、含凭据 URL、非对象根 JSON 或重复冲突身份均失败关闭；不得截断后继续生成看似完整的 Draft。

## 4. Hugging Face fixture 的规范形态

Luna 后续应为每一类资源保存**最小脱敏响应快照**，而非保存模型权重、数据文件、cookie、鉴权头或完整卡片正文。fixture 文件名使用稳定的 URL 安全编码，例如 `huggingface/models/acme--demo-model.json`；fixture manifest 另行保存采集时间和 SHA-256。

model fixture 的最小正例：

```json
{
  "id": "acme/demo-model",
  "sha": "0123456789abcdef0123456789abcdef01234567",
  "lastModified": "2026-09-18T12:00:00.000Z",
  "private": false,
  "gated": false,
  "disabled": false,
  "pipeline_tag": "text-generation",
  "library_name": "transformers",
  "tags": ["transformers", "text-generation"],
  "cardData": {"license": "apache-2.0"}
}
```

dataset fixture 的最小正例：

```json
{
  "id": "acme/demo-dataset",
  "sha": "abcdef0123456789abcdef0123456789abcdef01",
  "lastModified": "2026-09-18T12:00:00.000Z",
  "private": false,
  "gated": "auto",
  "disabled": false,
  "tags": ["text", "classification"],
  "cardData": {"license": "cc-by-4.0"}
}
```

`gated: "auto"` 是 provider 特有状态，无法无损映射到本版三值 Draft，因此结果必须为 `access_gate=unknown` 且带 `unsupported_gate_value`；不能擅自归类为 gated 或 ungated。

## 5. HF 字段映射

| Draft 字段 | HF model JSON Pointer | HF dataset JSON Pointer | 转换与拒绝条件 |
| --- | --- | --- | --- |
| `resource_kind` | fixture 通道 `models/` | fixture 通道 `datasets/` | 由文件清单/调用参数指定；根 JSON、tags、URL 均不能决定类型。 |
| `provider.id` | 常量 | 常量 | 均为 `huggingface`。 |
| `identity.provider_resource_id` | `/id` | `/id` | 必须为恰好一个非空 `namespace/name`；空、第三段路径、控制字符或与 fixture 通道不符时拒绝。 |
| `identity.canonical_url` | `/id` | `/id` | model：`https://huggingface.co/{id}`；dataset：`https://huggingface.co/datasets/{id}`。ID 仅允许 URL 路径安全字符；否则不构造 URL。 |
| `identity.revision` | `/sha` | `/sha` | 仅接受 40 或 64 位小写十六进制 commit 值；其他值为空并写 `invalid_revision`。 |
| `display.name` | `/id` | `/id` | 直接复制；本版不把 card 的 title 当作身份。 |
| `lifecycle.last_modified_at` | `/lastModified` | `/lastModified` | 严格 RFC 3339 解析并归一为 UTC；异常值为 `null + invalid_timestamp`。 |
| `lifecycle.disabled` | `/disabled` | `/disabled` | 仅布尔值有效；缺失为 `null`，其他类型记 `invalid_boolean`。 |
| `lifecycle.visibility` | `/private` | `/private` | 布尔真/假映射 private/public；缺失或非布尔未知并诊断。 |
| `lifecycle.access_gate` | `/gated` | `/gated` | 严格 `true -> gated`、`false -> ungated`；缺失为 unknown；其他值 unknown+诊断。 |
| `declared_metadata.license_text` | `/cardData/license` | `/cardData/license` | 仅非空字符串，按原值保存；缺失/对象/数组不转字符串且诊断。 |
| `declared_metadata.library_name` | `/library_name` | 不映射 | 字符串才接受；dataset 固定 `null`，不得用 tags 猜测。 |
| `declared_metadata.task` | `/pipeline_tag` | 不映射 | 字符串才接受；dataset 固定 `null`。 |
| `declared_metadata.tags` | `/tags/*` | `/tags/*` | 仅字符串元素；去重后 Unicode 码点稳定排序；遇到非字符串元素不产生该元素并写诊断。 |

若 provider 同时给出顶层 `license` 与 `/cardData/license`，本版不选择其一：仅当二者规范化后完全相同才写入 `license_text`，否则保持 `null`、保留两条证据并写 `conflicting_declared_license`。这是声明冲突，不是许可证判定。

## 6. Draft 到当前 P0 `AIAsset` 的受限投影

在公共 Schema 未获负责人批准前，Draft 只能由内部 materializer 生成临时 P0 候选。仅在身份字段有效、每个投影字段都已有转化后的 P0 `Evidence`、且无 `missing_required_id`/`unsupported_fixture_kind`/身份冲突诊断时允许投影：

| P0 `AIAsset` 字段 | Draft 来源 | 规则 |
| --- | --- | --- |
| `asset_type` | `resource_kind` | model -> `model`；dataset -> `dataset`；其余种类不投影。 |
| `name` | `identity.provider_resource_id` | 不使用 card title。 |
| `provider` | `provider.id` | `huggingface`。 |
| `version` | `identity.revision` | 可为 `null`；仅 commit/SHA，不以日期替代。 |
| `source_url` | `identity.canonical_url` | 仅 canonical HTTPS URL。 |
| `evidence_ids` | materialized `field_evidence` | 至少含 `/id` 与产生 `source_url` 的证据（同一条可复用）。 |
| `detected_by` | materializer 固定值 | 新增实现前不可假定现有 enum 值；需要负责人批准是否为 `manual`、`static_pattern` 或新方法。 |
| `confidence` | 固定性解析 | 仅说明 fixture 字段映射置信，不代表远端可访问、许可证或授权事实。 |
| `license_expression_id` | 不映射 | 始终 `null`。 |
| `authorization_status` | 不映射 | 始终保持 P0 默认 `pending`。 |

`visibility=public`、`access_gate=ungated`、`disabled=false`、`license_text` 或有 `sha` 都不得把 `authorization_status` 改为 `verified`，也不得写入 `license_expression_id`。同样，Fixture 的采集成功不能证明其在扫描时仍存在。

## 7. Fixture 与回归验收

Luna 实现 fixture 时应至少覆盖下列 ID；预期是 Draft 语义，不是远端事实：

| Case ID | 输入要点 | 必须断言 |
| --- | --- | --- |
| `hf-model-minimal` | model、合法 id、sha、布尔 gated/private | 完整 model Draft；P0 候选的 license 为 null、authorization 为 pending。 |
| `hf-dataset-minimal` | dataset、合法 id、sha、`gated="auto"` | dataset Draft，access gate unknown，产生 `unsupported_gate_value`。 |
| `hf-missing-id` | 缺 `/id` | 不产生 Draft/P0 候选，`missing_required_id`。 |
| `hf-invalid-id` | 三段路径、空段或含控制字符 | 失败关闭，不构造 canonical URL。 |
| `hf-invalid-date` | 非 RFC 3339 `/lastModified` | 仍可生成身份有效 Draft，但日期为 null 且有诊断。 |
| `hf-license-conflict` | 顶层与 cardData license 不同 | `license_text=null`，两处 EvidenceRef 均保留，产生冲突诊断。 |
| `hf-secret-url` | 任一候选 URL 含 userinfo/query token | 拒绝 fixture，输出中不得回显凭据。 |
| `hf-tags-mixed` | tags 含重复、非字符串 | 只保留合法去重 tags，产生类型诊断且排序稳定。 |

所有 case 还必须验证：同一 fixture 字节重复解析的 `draft_id` 与字段排序稳定；任一被采用字段都能回溯到 fixture digest 和 JSON Pointer；变更 fixture digest 必须改变 `draft_id`；日期、下载数、likes、summary 的变化不得单独改变身份；解析全程无网络调用。

## 8. 后续接入门禁

1. Sol/Root 审核并批准是否把本候选变成版本化 Schema，特别是 Draft ID 的 UUID/哈希算法和 `detected_by` 扩展。
2. Luna 按第 7 节创建最小、脱敏、可再分发的 fixture 与失败夹具；不得提交真实受限模型或数据内容。
3. Terra 实现纯离线 parser/materializer，先通过 fixture 回归，再申请修改 P0/P1 schema 或 API。
4. B4/B5 或人工复核在独立证据链上处理 `license_text`，不得把本 Draft 映射作为许可/授权结论来源。

本设计的完成只表示字段和映射边界已明确；不表示 HF 集成、网络获取、许可证核验、用户授权或合规结论已完成。
