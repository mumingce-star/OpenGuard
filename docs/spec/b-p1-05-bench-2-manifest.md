# B-P1-05 OpenGuard-Bench 2.0 Manifest 设计

状态：设计已确认，待实现
契约标识：`openguard-bench-manifest/2.0`
适用范围：离线 JSON manifest、Java 库与 CLI、Maven/CI 校验
不在范围：Web API、数据库、P0 `ScanRun` 变更、Formal Assessment 写入、自动生成真人裁决

## 1. 目标

Bench 2.0 manifest 是评测批次的不可变编排契约。它绑定样本、数据划分、gold、人工治理、修订和评测产物，回答以下问题：

1. 使用的是哪一版基准、哪些不可变文件和哪些固定来源；
2. train/dev/holdout 是否按项目族和内容隔离；
3. gold 由谁、以何种暴露条件复核，争议是否关闭；
4. manifest 修订是否保留父版本、变更理由和旧评测失效关系；
5. 某次评测最多可以声明到哪个指标等级；
6. 在另一台机器上能否只凭仓库文件复现校验结论。

manifest 不保存或覆盖业务事实。`ScanRun`、人工记录、gold、预测和结果均作为带 SHA-256 的 artifact 引用。

## 2. 已确认的设计决策

- 使用 JSON Schema Draft 2020-12 加 Java 语义校验双层模型。
- Java 只提供独立库和 CLI；不新增 Spring Web API，不启动服务。
- Schema 处理类型、格式、枚举、局部条件和封闭对象；Java 处理引用图、文件完整性、跨记录唯一性、隔离、时序、修订链和准入推导。
- 校验必须 fail-closed。缺失事实不会推导为通过，不允许手填 `eligible=true`。
- 单真人流程是合法状态，但不能冒充双人独立复核。
- holdout 可在 gold 冻结后用于最终评测；用于规则、提示词、阈值或模型开发的暴露会降低该 manifest 修订版的准入等级。
- amendment 只能追加新修订并引用父 manifest；不得原地覆盖历史。
- 同一项目族或相同内容摘要不得跨 split。

## 3. 契约边界

### 3.1 输入

- 一个 UTF-8 JSON manifest；
- manifest 所在目录下、由 `artifacts[*].path` 引用的普通文件；
- classpath 中固定的 Bench 2.0 JSON Schema。

### 3.2 输出

CLI 向 stdout 输出一个稳定 JSON `ValidationReport`。成功与业务校验失败不向 stdout 混入日志、Maven 文本或堆栈；无法读取/解析输入时仍输出脱敏诊断。

### 3.3 不信任边界

manifest、artifact 路径、文件内容、时间、角色声明和请求等级均不可信。校验器不得联网、执行样本代码、跟随越界符号链接或根据作者自报角色提升准入等级。

身份独立性不能仅由程序证明。程序验证结构、不同 reviewer ID、暴露声明和记录绑定；最终材料必须披露身份仍依赖真人/组织流程核验。

## 4. 顶层对象

顶层对象关闭额外字段，必须包含：

| 字段 | 作用 |
| --- | --- |
| `schema_version` | 常量 `openguard-bench-manifest/2.0` |
| `identity` | manifest ID、修订、创建时间、父 manifest 绑定 |
| `benchmark` | 任务、标签集版本、样本粒度、范围 |
| `artifacts` | 不可变文件引用 |
| `cases` | case 身份、项目族、内容摘要和 split |
| `governance` | review、exposure、争议和冻结事实 |
| `amendments` | 当前修订的追加式变更记录 |
| `evaluations` | 被测版本、运行配置、预测/结果和请求等级 |

ID 使用小写前缀加受限 ASCII，例如 `bmf_...`、`art_...`、`case_...`、`rev_...`、`amd_...`、`eval_...`。Schema 只验证格式；Java 验证全局或各命名空间唯一性。

## 5. 数据模型

### 5.1 `identity`

```json
{
  "manifest_id": "bmf_openguard_bench_2",
  "revision": 1,
  "created_at": "2026-09-17T11:00:00Z",
  "parent": null
}
```

`revision=1` 时 `parent` 必须为 `null`。更高修订必须包含父 manifest 的相对路径、SHA-256、manifest ID 和前一修订号。Java 校验修订号连续、父文件位于根目录内、父摘要匹配、父 ID 相同，且 amendment 不形成环。

### 5.2 `benchmark`

至少包含：

- `benchmark_id` 和 `title`；
- 非空 `task_types`，值来自 `component_detection`、`ai_resource_detection`、`license_normalization`、`risk_detection`、`inventory_completeness`、`suggestion_grounding`；
- `label_set_version`；
- `case_granularity`；
- `scope.included`、`scope.excluded`；
- `matching_policy_artifact_id`。

匹配规则必须作为 artifact 冻结，不能只写自然语言版本名。

### 5.3 `artifacts`

每项包含：

```json
{
  "artifact_id": "art_gold_index",
  "role": "gold",
  "path": "artifacts/gold.jsonl",
  "media_type": "application/x-ndjson",
  "size_bytes": 1234,
  "sha256": "<64 lowercase hex>",
  "redistribution": "repository_allowed"
}
```

`role` 至少覆盖 `source_index`、`gold`、`review`、`resolution`、`matching_policy`、`prediction`、`result`、`run_config`、`amendment`、`manifest_parent`。`redistribution` 为 `repository_allowed`、`reference_only` 或 `restricted_local`。

`path` 必须为 `/` 分隔的规范仓库相对路径。禁止空段、`.`、`..`、绝对路径、驱动器、反斜杠、NUL、URI、查询串和 fragment。Java 在读取前后均验证真实路径仍位于 manifest 根目录，且对象为普通文件；默认拒绝符号链接。

所有 artifact 均检查字节数和流式 SHA-256。`reference_only` 可没有本地文件，但必须提供固定来源对象和其摘要；引用该对象的准入规则必须明确允许远程仅引用，否则失败。校验过程绝不联网补取。

### 5.4 `cases`

每项包含：

- `case_id`：稳定 case 身份；
- `family_id`：项目、fork 或同源样本族；
- `content_sha256`：用于跨 split 去重；
- `split`：`train`、`dev` 或 `holdout`；
- `source_artifact_ids`：至少一个来源索引或允许公开的 fixture；
- `gold_artifact_id`；
- `authorization_status`：`verified`、`pending`、`reference_only`、`rejected`；
- `included` 和可选 `exclusion_reason`。

`included=false` 的 case 不进入指标分母，且必须给出理由；禁止在看到预测后通过 amendment 静默排除失败 case。Java 对 amendment 原因和 evaluation 时间执行反选择检查。

同一 `family_id` 只能属于一个 split；相同 `content_sha256` 只能属于一个 split。case ID、family ID 和摘要按 UTF-8 字节序形成确定性索引。

### 5.5 `governance`

包含：

- `reviews[]`：review ID、artifact、reviewer ID、actor type、模式、系统/AI 暴露、提交时间和覆盖 case；
- `exposures[]`：split、actor、用途、发生时间和依据 artifact；
- `disputes[]`：阻断范围、状态、相关 review/resolution；
- `freeze`：gold 冻结时间、冻结 artifact 集、冻结人类型和状态。

`actor_type` 为 `human` 或 `ai`。复核模式为：

- `ai_assisted_confirmation`；
- `single_human_blinded_relabel`；
- `independent_human_annotation`；
- `human_adjudication`；
- `ai_review`。

AI 记录永不计入真人数量。相同 reviewer ID 不计作两位独立真人。`single_human_blinded_relabel` 必须记录先前暴露、冷却期开始/结束和盲化包 artifact。

exposure 用途为 `annotation`、`error_analysis`、`rule_development`、`prompt_development`、`model_training`、`threshold_tuning` 或 `final_evaluation`。holdout 在冻结前出现后五类中的开发用途时，不得达到正式可报告等级。

未解决且 `blocking=true` 的 dispute 阻止正式等级。没有第三人或证据不足时保留 `disputed`/`uncertain`，AI 不得作为仲裁者。

### 5.6 `amendments`

每项记录 amendment ID、目标对象、旧值摘要、新值摘要、原因码、说明、提出者类型、批准者类型、artifact 和时间。

原因码至少包括 `source_correction`、`label_correction`、`scope_correction`、`evidence_recovery`、`policy_change`。正式 gold 变更必须由真人批准；AI 可以提出 amendment，但不能成为唯一批准者。

修改 case、gold、matching policy、split、review 或 freeze 的 amendment 会使父修订上的 evaluation 失效。新 evaluation 必须绑定当前修订，并显式引用当前 gold 与 matching-policy artifact。不能在 manifest 内放置其自身文件摘要，否则会形成不可解的自引用；CLI 改为在 `ValidationReport` 中报告本次实际读取文件的 SHA-256，供外部发布回执绑定。

### 5.7 `evaluations`

每项包含：

- `evaluation_id`；
- `benchmark_revision`，必须等于当前 `identity.revision`；
- `target_split`；
- `system_revision`；
- `gold_artifact_id`、`matching_policy_artifact_id`、`run_config_artifact_id`、`prediction_artifact_id`、`result_artifact_id`；
- `started_at`、`finished_at`；
- `requested_tier`；
- 可选 `declared_metrics`，只用于与结果 artifact 复核，不能作为事实源。

预测生成时间不得早于对应 gold 冻结要求定义的时间边界。对 holdout 的正式评测必须绑定不可变代码版本和配置摘要。

## 6. 准入等级

Java 从事实字段推导 `derived_tier`：

| 等级 | 最低门禁 |
| --- | --- |
| `smoke` | Schema、引用闭包、本地必需 artifact 和摘要有效 |
| `development` | smoke + split 隔离 + matching policy 冻结；允许开发用途暴露 |
| `reportable_single_human` | development + 一名真人完成隔离复标 + 暴露/冷却期/一致性披露 + gold 冻结 + 无阻断争议 + holdout 无开发泄漏 |
| `reportable_independent` | development + 至少两名不同真人独立标注 + 分歧由真人裁决或保留 uncertain + gold 冻结 + holdout 无开发泄漏 |

等级顺序固定。manifest 有效但 `requested_tier` 高于 `derived_tier` 时返回策略拒绝，而不是篡改请求或把整个 JSON 判为结构无效。

当前历史批次的一次 AI 辅助真人确认不足以达到 `reportable_single_human`；只有按隔离复标方案形成新记录后才能重新推导。

## 7. Java 设计

包：`dev.openguard.bench`

| 类 | 单一职责 |
| --- | --- |
| `BenchManifestCli` | `validate <path>`、stdout JSON、stderr 最小提示、退出码 |
| `BenchManifestService` | 固定顺序编排各校验阶段 |
| `JsonSchemaManifestValidator` | classpath Schema、Draft 2020-12、严格 format、稳定诊断映射 |
| `ArtifactIntegrityValidator` | 路径边界、普通文件、大小和 SHA-256 |
| `BenchSemanticValidator` | ID/引用、split、治理、时序、修订和准入推导 |
| `ValidationReport` | 稳定输出 DTO |
| `Diagnostic` | `code`、`severity`、JSON Pointer、固定 message |
| `MetricTier` | 有序等级和比较 |

解析使用现有 Jackson 2 依赖。JSON Schema 校验采用 `com.networknt:json-schema-validator:2.0.4`；该发布线面向 Jackson 2，并支持 Draft 2020-12。Schema 加载限定为 classpath，不启用网络 Schema 获取。依赖版本和许可证须同步登记第三方台账。

校验顺序固定：

1. 参数、文件大小和 UTF-8/JSON 解析；
2. JSON Schema；
3. 建立不可变 ID 索引；
4. 引用闭包；
5. artifact 文件完整性；
6. split 与泄漏；
7. review、dispute 和 freeze；
8. parent/amendment/evaluation 时序；
9. 推导等级并比较请求等级；
10. 按 `(severity, code, json_pointer, message)` 排序诊断。

如果前一阶段无法安全建立后一阶段所需事实，跳过依赖阶段，避免产生级联噪声或空指针异常。输入错误不得泄漏绝对路径、文件正文、异常类或堆栈。

## 8. CLI 契约

```text
BenchManifestCli validate <manifest.json>
```

stdout 示例：

```json
{
  "contract_version": "openguard-bench-validation-report/1.0",
  "valid": false,
  "derived_tier": "development",
  "requested_tiers": ["reportable_independent"],
  "diagnostics": [
    {
      "code": "BENCH_HOLDOUT_EXPOSED",
      "severity": "error",
      "json_pointer": "/governance/exposures/0",
      "message": "Holdout was exposed to development activity."
    }
  ]
}
```

退出码：

- `0`：契约有效且所有 evaluation 满足其请求等级；
- `1`：Schema、artifact 或语义无效；
- `2`：CLI 用法、文件读取、UTF-8 或 JSON 解析失败；
- `3`：manifest 有效，但至少一个 evaluation 请求等级高于实际等级。

无 evaluation 时只校验 manifest，可返回 `0`，并报告当前 `derived_tier`。

## 9. 文件布局

```text
docs/spec/b-p1-05-bench-2-manifest.md
schemas/bench/v2/manifest.schema.json
benchmarks/examples/v2/valid/
benchmarks/examples/v2/invalid/
backend/java/src/main/java/dev/openguard/bench/
backend/java/src/test/java/dev/openguard/bench/
```

Maven 将 `schemas/bench/v2/manifest.schema.json` 复制到 `schema/bench/v2/manifest.schema.json`。CLI 不依赖当前工作目录寻找 Schema。

## 10. 测试矩阵

### 10.1 正例

- 最小 smoke manifest；
- train/dev 合法隔离；
- 单真人隔离复标达到受限可报告等级；
- 双真人独立复核和真人裁决达到独立等级；
- 正确父摘要和 amendment 的第二修订；
- 无 evaluation 的纯 manifest 校验。

### 10.2 Schema 反例

- 未知顶层/嵌套字段；
- 错误常量、枚举、时间、ID、SHA-256、负字节数；
- revision 与 parent 局部条件冲突；
- excluded case 缺 exclusion reason；
- review 模式缺对应暴露/冷却期字段。

### 10.3 语义反例

- 重复 ID、悬空或错误角色引用；
- 相同 family/content 跨 split；
- AI 计作真人、同一真人计两次；
- holdout 开发期暴露；
- 未解决阻断争议；
- gold 未冻结、预测时序非法；
- parent 摘要/修订不匹配、amendment 环、修改后复用旧 evaluation；
- 请求等级高于推导等级。

### 10.4 文件安全反例

- `..`、绝对路径、驱动器、反斜杠和 URI；
- 符号链接或真实路径逃逸；
- 缺失、非普通文件、大小不符和 SHA-256 不符；
- 超限 manifest/artifact；
- 路径或异常中含敏感内容时诊断仍脱敏。

### 10.5 CLI 回归

- 退出码 `0/1/2/3`；
- stdout 为单一 JSON，诊断顺序稳定；
- 相同输入重复运行字节一致；
- 错误不输出堆栈或本机绝对路径；
- 从不同当前目录运行仍能加载 classpath Schema。

## 11. 验收命令

```powershell
mvn -f backend/java/pom.xml test
mvn -f backend/java/pom.xml exec:java `
  -Dexec.mainClass=dev.openguard.bench.BenchManifestCli `
  -Dexec.args="validate benchmarks/examples/v2/valid/smoke.json"
```

还必须运行 JSON 解析、`git diff --check`、敏感信息检查和待提交文件清单复核。测试不得联网或启动 Spring Boot。

## 12. 实施边界与后续

本工作包只交付契约和离线校验能力。运行器自动生成 manifest、评测指标重算、Web 展示、数据库、权限和 Formal Assessment 接入属于后续工作包。

Sol/Root 冻结 Schema 和准入语义；Terra 实现 Java 库与 CLI；Luna 独立补充反例、跨平台路径和 holdout 泄漏测试；Root 复核第三方依赖、文档、测试与发布范围。

现有 P0 历史 manifest 可以作为迁移输入，但不得原地改名冒充 2.0。迁移必须生成新 manifest、记录来源 artifact 和限制说明。
