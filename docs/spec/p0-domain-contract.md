# OpenGuard P0 领域与 API 契约

状态：`FROZEN_FOR_A1`

版本：`0.1.1`

冻结日期：2026-09-01

适用范围：A1 核心数据模型、P0 前后端公共 DTO、扫描器/规则/AI/报告模块交换对象、Luna fixtures。

## 1. 约束优先级与目标

本契约按以下优先级解决冲突：

1. 正式竞赛通知、作品提交要求和技术报告参考大纲；
2. 仓库现有架构、安全、交接与协作契约；
3. 《OpenGuard AI 详细项目规划与 Codex 交接执行书 V1.0》的 P0 建议；
4. 实现便利性。

目标是让 Terra 只依赖本文即可实现 Pydantic 模型，让 Luna 只依赖本文即可构造有效与无效 fixtures。A1 不实现克隆、解压、扫描器、规则引擎、AI、数据库或 HTTP 路由。

产品定位保持为“合规信息整理与风险提示工具”。任何对象、状态或建议都不得表述为法律结论或再利用授权。

## 2. 唯一公共模型与兼容映射

仓库只保留一套公共领域对象。技术执行书中的简化名称仅作为产品展示或导入别名，不生成第二套类、表或 JSON 结构。

| 技术执行书名称 | 冻结公共对象 | 处理方式 |
|---|---|---|
| `Resource(type=package)` | `Component` | 软件包与代码依赖使用 `Component` |
| `Resource(type=model/dataset/api/asset)` | `AIAsset` | 非软件依赖资源使用 `AIAsset`，`asset_type` 区分类型 |
| `License` | `LicenseExpression` | 保存 SPDX 表达式、来源与核验状态；义务单独引用 |
| `Risk` | `RiskFinding` | 必须含规则版本、证据引用、结果语义和整改引用 |
| `ScanResult` | `ScanRun` | `ScanRun` 是一次扫描聚合根，包含资源、证据、风险和报告链接 |
| `Resource[]` | `components[]` + `ai_assets[]` | API 可在展示层合并，不在存储层抹平差异 |
| `bench/` | `benchmarks/` | 以现有仓库目录为准，不新建 `bench/` |

禁止在代码中新增名为 `Resource`、`Risk` 或 `ScanResult` 的平行领域模型。若前端需要统一列表，使用只读 `ResourceView` DTO，并由 `Component`/`AIAsset` 映射生成。

## 3. 通用序列化规则

- JSON 字段使用 `snake_case`；未知字段默认拒绝，版本迁移必须显式处理。
- 所有 ID 为小写、稳定、不透明字符串，格式为 `<prefix>_<ulid-or-uuid>`。前缀：`prj`、`cmp`、`ast`、`evd`、`lic`、`obl`、`rsk`、`rem`、`scn`。
- 时间使用 UTC RFC 3339，例如 `2026-09-01T12:00:00Z`；不接受无时区时间。
- 哈希使用对象 `{algorithm, value}`；P0 只允许 `sha256`，值为 64 位小写十六进制。
- URI 使用绝对 `https` URI；本地路径使用相对 POSIX 路径，不公开绝对路径。
- 行号从 1 开始，区间两端均包含；无法定位时不伪造行号。
- `confidence` 为 `0.0..1.0`；确定性解析器也必须记录来源，不能只靠高置信度代替证据。
- 枚举值使用小写 `snake_case`；数组默认稳定排序并去重。
- 可选字段缺失时省略，禁止用空字符串表示未知。未知事实使用明确状态或 `null`。
- 所有聚合结果包含 `contract_version: "0.1.1"`。

### 3.1 公共枚举

| 枚举 | P0 值 |
|---|---|
| `SourceType` | `git`, `zip`, `local` |
| `ComponentType` | `library`, `application`, `framework`, `runtime`, `unknown` |
| `AIAssetType` | `model`, `dataset`, `api`, `service`, `asset` |
| `EvidenceKind` | `file`, `manifest_field`, `url`, `tool_output`, `license_text`, `metadata` |
| `DetectionMethod` | `manifest_parser`, `scancode`, `syft`, `static_pattern`, `ast`, `manual`, `ai_candidate` |
| `VerificationStatus` | `verified`, `pending`, `not_applicable`, `rejected` |
| `FindingOutcome` | `pass`, `warning`, `review_required`, `unknown` |
| `Severity` | `info`, `low`, `medium`, `high` |
| `ScanStatus` | `queued`, `running`, `completed`, `partial`, `failed`, `cancelled` |
| `ScanStage` | `queued`, `ingestion`, `inventory`, `scan`, `normalize`, `rules`, `ai_assist`, `report`, `completed` |
| `ProducerType` | `parser`, `scanner`, `rule_engine`, `ai`, `human` |

`Severity` 表示处理优先级，不表示法律责任。`FindingOutcome` 是结论可信度/处置语义，两者不得合并。

## 4. 一等对象

下列“必填”是序列化层要求；允许值仍须满足字段约束。

### 4.1 `Project`

| 字段 | 类型 | 必填 | 约束 |
|---|---|---:|---|
| `id` | string | 是 | `prj_` 前缀 |
| `name` | string | 是 | 1..200 字符 |
| `source_type` | `SourceType` | 是 | P0 UI 必须支持 `git`、`zip`；`local` 仅本地部署/开发入口 |
| `source` | string | 是 | Git 为公开 HTTPS URL；ZIP/local 对外只保存脱敏逻辑名 |
| `revision` | string/null | 否 | Git 提交哈希；未解析时省略或 `null` |
| `root_digest` | `HashValue`/null | 否 | inventory 完成后填写 |
| `created_at` | datetime | 是 | UTC |

不得把临时绝对路径、令牌化 URL 或用户个人目录写入公共结果。

### 4.2 `Evidence`

`Evidence` 是第一类对象，所有风险和 AI 候选字段都通过 ID 引用它。

| 字段 | 类型 | 必填 | 约束 |
|---|---|---:|---|
| `id` | string | 是 | `evd_` 前缀 |
| `kind` | `EvidenceKind` | 是 | 证据类别 |
| `locator` | string | 是 | 相对路径、字段定位符或 HTTPS URL |
| `excerpt` | string/null | 否 | 最小必要片段；默认最多 1000 字符并脱敏 |
| `start_line` | integer/null | 否 | 与 `end_line` 同时出现，>=1 |
| `end_line` | integer/null | 否 | >= `start_line` |
| `content_hash` | `HashValue`/null | 否 | 可获得原始内容时填写 |
| `detected_by` | `DetectionMethod` | 是 | 生成证据的方法 |
| `producer` | `ProducerRef` | 是 | 工具/规则/模型/人工的名称与版本 |
| `observed_at` | datetime | 是 | UTC |
| `verification_status` | `VerificationStatus` | 是 | AI 候选默认 `pending` |

规则：

- `ai_candidate` 只能生成候选证据，不能把 `verification_status` 直接写为 `verified`。
- `file`/`manifest_field` 的 `locator` 必须是仓库相对路径，不能包含 `..`、绝对路径或凭据。
- 证据片段不得包含密钥、令牌、个人信息或无权再分发的大段内容。

### 4.3 `Component`

| 字段 | 类型 | 必填 | 约束 |
|---|---|---:|---|
| `id` | string | 是 | `cmp_` 前缀 |
| `name` | string | 是 | 规范化包名 |
| `version` | string/null | 否 | 未锁定版本不得猜测 |
| `ecosystem` | string | 是 | P0 为 `pypi`、`npm` 或 `unknown` |
| `component_type` | `ComponentType` | 是 | 默认 `library` |
| `purl` | string/null | 否 | 合法 Package URL |
| `source_url` | https URI/null | 否 | 不由包名臆造 |
| `license_expression_id` | string/null | 否 | 引用 `LicenseExpression.id` |
| `evidence_ids` | string[] | 是 | 至少 1 个有效 `evd_` 引用 |
| `detected_by` | `DetectionMethod[]` | 是 | 至少 1 项 |
| `confidence` | number | 是 | 0..1 |

去重键优先为 `purl`，否则使用规范化的 `(ecosystem, name, version)`；来源冲突时保留全部证据并进入复核，不静默覆盖。

### 4.4 `AIAsset`

| 字段 | 类型 | 必填 | 约束 |
|---|---|---:|---|
| `id` | string | 是 | `ast_` 前缀 |
| `asset_type` | `AIAssetType` | 是 | 模型、数据集、API、服务或素材 |
| `name` | string | 是 | 无法确定时使用可核验 locator 名称，不编造品牌 |
| `provider` | string/null | 否 | 例如 `hugging_face`；需证据 |
| `version` | string/null | 否 | 模型 revision、数据版本或 API 版本 |
| `source_url` | https URI/null | 否 | 具体资源 URL 优先于主页 |
| `license_expression_id` | string/null | 否 | 服务/API 无开源许可证时允许为空，另登记授权状态 |
| `authorization_status` | `VerificationStatus` | 是 | 默认 `pending` |
| `evidence_ids` | string[] | 是 | 至少 1 个有效引用 |
| `detected_by` | `DetectionMethod[]` | 是 | 至少 1 项 |
| `confidence` | number | 是 | 0..1 |

`AIAsset` 不得把“可访问”解释为“允许再利用”。模型、数据集许可证与 API 服务条款必须分别核验。

### 4.5 `LicenseExpression`

| 字段 | 类型 | 必填 | 约束 |
|---|---|---:|---|
| `id` | string | 是 | `lic_` 前缀 |
| `expression` | string | 是 | 有效 SPDX 表达式或 `LicenseRef-*` |
| `normalized_ids` | string[] | 是 | 表达式中的标准 ID；未知时为空数组 |
| `source_url` | https URI/null | 否 | SPDX/上游许可证原文 |
| `evidence_ids` | string[] | 是 | 至少 1 个证据；纯 `LicenseRef` 也必须可定位 |
| `confidence` | number | 是 | 0..1 |
| `verification_status` | `VerificationStatus` | 是 | 自动识别默认 `pending`，人工/可信工具复核后可 `verified` |

禁止由 AI 直接确定 SPDX ID；AI 只能提出候选，经确定性标准化和 Schema 校验后保留。

### 4.6 `Obligation`

| 字段 | 类型 | 必填 | 约束 |
|---|---|---:|---|
| `id` | string | 是 | `obl_` 前缀 |
| `license_expression_id` | string | 是 | 有效许可证引用 |
| `action` | string | 是 | 版本化规则中的动作标识 |
| `trigger` | string | 是 | 可核验的适用条件，不写成无条件法律结论 |
| `description` | string | 是 | 风险提示语言 |
| `source_evidence_ids` | string[] | 是 | 许可证原文/官方来源证据 |
| `rule_id` | string | 是 | 稳定规则 ID |
| `rule_version` | string | 是 | 语义化版本 |
| `verification_status` | `VerificationStatus` | 是 | 未人工核验的高风险规则不得标 `verified` |

### 4.7 `Remediation`

| 字段 | 类型 | 必填 | 约束 |
|---|---|---:|---|
| `id` | string | 是 | `rem_` 前缀 |
| `finding_id` | string | 是 | 引用 `RiskFinding.id` |
| `summary` | string | 是 | 可执行但非法律结论 |
| `steps` | string[] | 是 | 至少 1 项 |
| `evidence_ids` | string[] | 是 | 建议所依据的证据 |
| `generated_by` | `ProducerRef` | 是 | 区分模板、规则或 AI |
| `verification_status` | `VerificationStatus` | 是 | AI 建议默认 `pending` |

AI 不可新增扫描结果中不存在的包、路径、许可证或义务。Schema 校验失败或证据引用不存在时丢弃 AI 输出，并保留规则模板建议。

### 4.8 `RiskFinding`

| 字段 | 类型 | 必填 | 约束 |
|---|---|---:|---|
| `id` | string | 是 | `rsk_` 前缀 |
| `resource_kind` | string | 是 | `component` 或 `ai_asset` |
| `resource_id` | string | 是 | 与 `resource_kind` 对应 |
| `outcome` | `FindingOutcome` | 是 | 见 4.8.1 |
| `severity` | `Severity` | 是 | 优先级，不是法律责任 |
| `title` | string | 是 | 简短、事实化 |
| `description` | string | 是 | 说明触发条件与不确定性 |
| `rule_id` | string | 是 | 稳定 ID |
| `rule_version` | string | 是 | 规则版本 |
| `trigger` | string | 是 | 实际命中的条件摘要 |
| `evidence_ids` | string[] | 是 | `warning`/`review_required` 至少 1 条；`unknown` 记录已检查证据或缺口证据 |
| `obligation_ids` | string[] | 是 | 可为空 |
| `remediation_id` | string/null | 否 | 有建议时引用 |
| `confidence` | number | 是 | 0..1 |

#### 4.8.1 结果语义

- `pass`：仅表示当前规则、输入和证据范围内未触发该检查；不得显示为“法律合规”。
- `warning`：存在可复现的规则触发和证据，需要处置或人工确认。
- `review_required`：证据存在，但条款适用、授权范围或上下文需要人工复核。
- `unknown`：事实缺失、冲突、无法解析或工具失败；不得自动降级为 `pass`。

### 4.9 `ScanRun`

| 字段 | 类型 | 必填 | 约束 |
|---|---|---:|---|
| `contract_version` | string | 是 | 当前固定 `0.1.1` |
| `id` | string | 是 | `scn_` 前缀 |
| `idempotency_key` | string/null | 否 | 创建请求可提供；同键同输入返回同一任务 |
| `status` | `ScanStatus` | 是 | 状态机约束 |
| `stage` | `ScanStage` | 是 | 当前或最后完成阶段 |
| `progress` | integer | 是 | 0..100，单调不减；失败时保留最后值 |
| `project` | `Project` | 是 | 聚合上下文 |
| `components` | `Component[]` | 是 | 默认空数组 |
| `ai_assets` | `AIAsset[]` | 是 | 默认空数组 |
| `licenses` | `LicenseExpression[]` | 是 | 默认空数组 |
| `evidence` | `Evidence[]` | 是 | 默认空数组 |
| `obligations` | `Obligation[]` | 是 | 默认空数组 |
| `findings` | `RiskFinding[]` | 是 | 默认空数组 |
| `remediations` | `Remediation[]` | 是 | 默认空数组 |
| `summary` | `ScanSummary` | 是 | 资源/结果计数必须由数组计算 |
| `provenance` | `RunProvenance` | 是 | 输入摘要、工具/规则/模型版本 |
| `errors` | `ScanError[]` | 是 | 默认空数组；结构化且脱敏 |
| `report_links` | `ReportLink[]` | 是 | 生成前为空 |
| `created_at` | datetime | 是 | UTC |
| `started_at` | datetime/null | 否 | UTC |
| `finished_at` | datetime/null | 否 | 终态必须填写 |

引用完整性要求：聚合内每个 ID 唯一；所有 `*_id`/`*_ids` 必须指向同一 `ScanRun` 中存在且类型匹配的对象。不得为了通过校验删除未知、失败或冲突记录。

## 5. 辅助值对象

### 5.1 `ProducerRef`

| 字段 | 类型 | 通用必填 | AI producer | 约束 |
|---|---|---:|---:|---|
| `type` | `ProducerType` | 是 | 是 | `ai` 表示大模型生产者 |
| `name` | string | 是 | 是 | 工具、规则引擎或模型服务的稳定名称 |
| `version` | string | 是 | 是 | 生产者/适配器版本 |
| `config_digest` | `HashValue`/null | 否 | 否 | 非敏感配置的规范化摘要，不记录配置正文 |
| `provider` | string/null | 否 | 是 | 例如 `ollama`；不得包含主机地址、账号或密钥 |
| `model_id` | string/null | 否 | 是 | 锁定的模型/权重标识与版本，不得使用含糊别名 |
| `prompt_schema_digest` | `HashValue`/null | 否 | 是 | 规范化提示词模板与输出 Schema 版本组合后的 SHA-256 摘要 |

当 `type == "ai"` 时，`provider`、`model_id`、`prompt_schema_digest` 三项必须同时存在；当 `type != "ai"` 时三项必须省略或为 `null`。摘要只用于版本追踪，不得反推出提示词正文，也不得包含密钥。

### 5.2 `RunProvenance`

字段：

- `input_digest: HashValue`；
- `inventory_digest: HashValue|null`；
- `tool_versions: {name, version}[]`；
- `ruleset_version: string`；
- `contract_version: string`；
- `ai_enabled: boolean`；
- `ai_model: ProducerRef|null`；
- `run_environment: {python_version, platform, openguard_version}`。

P0 的可复现报告至少披露 OpenGuard 版本、输入摘要、ScanCode/Syft 版本、规则版本、模型/Schema 版本和扫描时间。

### 5.3 `ScanError`

字段：`code`、`stage`、`message`、`recoverable`、可选 `tool`、可选 `evidence_ids`。`message` 必须脱敏，禁止包含绝对路径、命令行密钥或完整第三方内容。

### 5.4 `ScanSummary`

字段：`component_count`、`ai_asset_count`、`evidence_count`、`finding_counts`。计数均为非负整数；`finding_counts` 固定包含四个 `FindingOutcome` 键。

### 5.5 `ReportLink`

字段：`format`（P0：`html`、`json`、`csv`、`resource_inventory`）、`href`、`content_hash`、`generated_at`。API 不返回主机绝对路径。

## 6. 扫描状态机

允许转换：

```text
queued -> running -> completed
                 -> partial
                 -> failed
queued/running   -> cancelled
```

- `running` 时 `stage` 按主链单向推进；重试同一阶段可以保持不变。
- `completed`：确定性 P0 主链完成；AI 可降级，不要求所有结果都为 `pass`。
- `partial`：至少一个可用结果已生成，但必需扫描器/报告阶段有可恢复失败。
- `failed`：无法产生符合契约的最小结果；必须有至少一个 `ScanError`。
- `unknown` finding 不会把任务变成 `failed`；它是可见的业务结果。

## 7. P0 API 冻结

公共前缀固定为 `/api/v1`。技术执行书前端章节中的 `/scans` 是省略前缀的简写。

| 方法与路径 | 用途 | 最小成功返回 |
|---|---|---|
| `POST /api/v1/scans` | 创建 Git/ZIP 扫描 | `202` + `{scan_id,status,status_url}` |
| `GET /api/v1/scans/{scan_id}` | 状态、阶段、进度、摘要、错误 | `ScanRunStatusView` |
| `GET /api/v1/scans/{scan_id}/resources` | 查询组件和 AI 资源 | `{items: ResourceView[], total, filters}` |
| `GET /api/v1/scans/{scan_id}/risks` | 查询风险 | `{items: RiskFinding[], total}` |
| `GET /api/v1/scans/{scan_id}/evidence/{evidence_id}` | 查看单条证据 | `Evidence` |
| `GET /api/v1/scans/{scan_id}/report?format=...` | 获取/下载报告 | `ReportLink` 或相应内容 |

### 7.1 创建请求

- Git：JSON `{source_type:"git", source:"https://...", idempotency_key?}`。
- ZIP：`multipart/form-data`，字段 `source_type=zip`、`file`、可选 `idempotency_key`。
- P0 不实现私有仓库 OAuth。URL 含凭据时拒绝。

### 7.2 查询与分页

- 资源可按 `kind`、`ecosystem/provider`、`verification_status` 过滤。
- 风险可按 `outcome`、`severity`、`resource_kind` 过滤。
- P0 返回稳定排序；后续分页加入时不得改变对象 Schema。

### 7.3 错误响应

所有非 2xx 返回：

```json
{
  "error": {
    "code": "invalid_source",
    "message": "公开仓库地址无效或不被允许",
    "request_id": "req_example",
    "details": {}
  }
}
```

P0 最小错误码：`invalid_source`、`invalid_archive`、`archive_limit_exceeded`、`scan_not_found`、`scan_not_ready`、`evidence_not_found`、`report_not_ready`、`scanner_timeout`、`scanner_failed`、`internal_error`。响应不得泄漏堆栈、绝对路径或凭据。

## 8. AI 与确定性事实边界

1. 文件存在性、哈希、路径、版本、依赖树、SPDX ID 和规则触发由确定性组件产生。
2. AI 只做非结构化候选抽取、通俗解释和整改建议。
3. AI 输出必须通过结构化 Schema 校验且只能引用已有 `evidence_id`。
4. AI 与确定性事实冲突时，确定性事实保留；冲突另记 `review_required` 或 `unknown`。
5. AI 不可用、超时或输出无效时，`ScanRun` 仍可 `completed`，并在 `errors`/provenance 中记录降级。

## 9. 目录与里程碑冲突决议

- 使用现有 `benchmarks/`，不采用技术执行书的 `bench/`。
- A1 代码放在 `backend/app/domain/`，跨语言契约源文件后续放在 `schemas/p0/`；示例结果放在 `examples/sample-scan-result.json`。
- 现有日期计划（9月3日冻结、9月11日扫描底座等）是仓库主计划；技术执行书的 Day 1-45 作为相对工作量参考，不另起第二套日历。
- 2026-09-03 前只完成契约/Schema/指标冻结与 A1 最小实现；“Day 7 真实全链”解释为扫描底座阶段的阶段目标，不允许压缩正式安全、证据和测试门禁。
- P0 UI 公开入口优先 Git/ZIP；`local` 仅本地部署和测试能力，不阻塞第一条演示链。
- P0 报告最低为 HTML+JSON；CSV/资源清单仍属于 P0，但可在主链稳定后补齐。PDF 自动生成是可砍项。

## 10. Terra A1 实现接口

Terra 下一任务只应：

1. 在 `backend/app/domain/` 实现本文对象与枚举的 Pydantic v2 模型；
2. 设置 `extra="forbid"`、UTC 时间、ID 前缀、哈希、行号、置信度和交叉引用校验；
3. 导出 JSON Schema 到 `schemas/p0/scan-result.schema.json`；
4. 创建 `examples/sample-scan-result.json`，包含：1 个 Python 组件、1 个模型/API 资产、至少 3 条证据、1 条 `review_required` 或 `warning`、1 个整改建议、完整 provenance；
5. 补充模型单测，不实现 A2/API/扫描器。

如 Pydantic 实现需要新增、删除或改变公共字段，必须先由项目负责人确认；不得以实现方便为由更改本文语义。

## 11. Luna A1 验证接口

Luna 在 Terra 完成后独立验证：

- 有效 sample 与导出的 JSON Schema/Pydantic 双向通过；
- 缺失证据引用、错误 ID 前缀、越界 confidence、无时区时间、绝对路径、反向行号、未知字段均被拒绝；
- `warning`/`review_required` 至少有一条证据；`failed` 至少有一个错误；终态有 `finished_at`；
- summary 计数与实际数组一致；
- AI producer 不含密钥，AI 候选/建议默认不是 `verified`；
- fixture 与公开材料通过匿名和敏感信息检查。

Luna 不得为使测试通过而修改公共契约；发现歧义应记录失败样例并交回 Sol/Terra。

## 12. 冻结门禁与变更流程

本文版本 `0.1.1` 冻结 A1.1。以下变更属于破坏性变更：对象重命名、删除必填字段、改变枚举语义、改变 ID/引用关系、改变 API 路径或把未知转为通过。必须：

1. 在共享日志记录变更请求；
2. 由 Sol 说明竞赛、证据和下游影响；
3. Terra 提供迁移/实现影响；
4. Luna 提供 fixture/测试影响；
5. 项目负责人批准后提升契约版本。

非破坏性可选字段也必须记录来源、用途、验证和披露边界。未经审批，不得用“兼容别名”长期维持两套模型。

### 12.1 版本记录

- `0.1.0`：冻结 A1 核心对象、证据链、状态机和 API。
- `0.1.1`：经项目负责人确认，为 AI `ProducerRef` 冻结 `provider`、`model_id`、`prompt_schema_digest` 三个条件必填字段；未改变非 AI producer、风险语义或 API 路径。
