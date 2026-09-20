# B-P1-06 OpenGuard-Bench 2.0 公开语料与治理补充规范

状态：提请负责人批准（2026-09-19）
适用范围：公开仓库元数据、离线基准语料、人工标注、误差分析与候选 `ResourceProfileDraft`。
不在范围：联网抓取、自动认定许可证/授权/合规、公开受限原件、修改既有 P0/P1 Schema 或替代真人裁决。

本规范补充而不替代以下已冻结或已实现的契约：

- Bench 2.0 manifest、准入等级、holdout 与 amendment 语义：`docs/spec/b-p1-05-bench-2-manifest.md`；
- provider-neutral Draft 和 Hugging Face 离线字段映射：`docs/spec/b-p1-01-resource-profile-draft.md`；
- 既有候选复核与人工标注边界：`docs/spec/scan-result-human-annotation-plan.md`。

## 1. Bench 2.0 manifest 的执行索引

manifest 固定使用 `openguard-bench-manifest/2.0` 与 JSON Schema Draft 2020-12；结构校验后必须再执行本地语义校验。它绑定不可变 artifact（路径、大小、SHA-256、再分发状态）、case、split、review/exposure/dispute/freeze、amendment 和 evaluation；不得用清单内的自报字段替代 artifact 或人工事实。

| 主题 | 强制规则 | 失败后的处理 |
| --- | --- | --- |
| 可复现性 | 所有本地 artifact 必须校验 SHA-256 与大小；远程只引用的对象必须标明 `reference_only` | 校验失败，不能形成有效评测 |
| split | 同一 `family_id` 或 `content_sha256` 不得跨 train/dev/holdout | 视为泄漏，拒绝准入 |
| gold | gold 先冻结，预测及结果随后产生 | 时间关系不成立，指标无效 |
| 人工治理 | AI 不计入真人数；同一 reviewer 不能伪作两名独立评审 | 降级或拒绝所请求的等级 |
| amendment | 只追加新 revision，绑定 parent、旧/新摘要、理由、批准人与 artifact | 不得就地改写历史，受影响 evaluation 失效 |
| 指标声明 | validator 根据事实导出 `derived_tier`，不信任 `eligible` 一类自报值 | 请求等级高于导出等级，返回策略拒绝 |

可报告等级从低到高为 `smoke`、`development`、`reportable_single_human`、`reportable_independent`。首批公开仓库仅允许先达到 development；只有满足既有 holdout、冻结、真人审查和争议关闭门禁时，才可升级到更高等级。

## 2. 首批公开仓库的选择原则与候选池

### 2.1 纳入原则

首批不是“受欢迎项目榜”，而是可复现、可标注、可安全引用的分层抽样框。每一个候选必须在离线 index 中记录仓库 URL、固定 commit SHA、采集日期、许可证文件定位、资源类别覆盖、可再分发状态和排除原因；不克隆或提交第三方源码、权重、数据文件或带个人信息的 issue 内容。

必须同时满足：

1. 公开可访问、固定到不可变 commit；fork 与同源镜像合并为同一 `family_id`；
2. 明确存在顶层或可定位的许可声明，且允许仓库元数据/必要的脱敏定位被引用；
3. 至少覆盖一个目标任务：软件依赖、模型引用、数据集引用、第三方 API、许可证候选或风险提示；
4. 能在不运行目标代码、不安装目标依赖、不读取密钥的条件下静态取样；
5. 样本不只来自单一语言、组织、模板或资源提供方；同一生态在首批最多占两个项目；
6. 不包含私有仓库、受控访问内容、疑似个人数据、受限模型权重或不能说明引用权利的原件。

下列情形直接排除或仅保留 `reference_only`：需要登录/令牌、仓库删除或默认分支漂移而无法固定、许可证冲突且不能保留原始证据、包含真实密钥/敏感样本、数据/模型条款禁止再分发、只剩二进制且无法做合法静态证据定位。

### 2.2 10 个候选（非已收录、非许可或合规结论）

| 候选仓库 | 主要覆盖 | 选择理由 | 初始处理 |
| --- | --- | --- | --- |
| `pydantic/pydantic` | Python 依赖、文档证据 | Python 包声明与多种元数据定位 | train/dev 候选 |
| `psf/requests` | Python 依赖、许可证候选 | 小型、稳定的依赖和许可证定位样本 | train/dev 候选 |
| `fastapi/fastapi` | Python、API/文档引用 | 框架依赖与文档中的服务引用边界 | dev 候选 |
| `pallets/flask` | Python、软件组件 | 与既有 Java 扫描纵切的可对照软件样本 | holdout 候选 |
| `huggingface/transformers` | Hugging Face 模型、数据集引用 | 覆盖 `from_pretrained` 与配置/文档定位 | dev 候选 |
| `huggingface/datasets` | 数据集引用、数据卡字段 | 覆盖数据集加载器和 card 元数据边界 | holdout 候选 |
| `langchain-ai/langchain` | 多 provider API、模型引用 | 测试 SDK/API 误报和间接引用 | holdout 候选 |
| `run-llama/llama_index` | 模型、数据、API 混合引用 | 用于同文件多类资源拆分 | dev 候选 |
| `vercel/ai` | TypeScript、AI provider API | 与 Python 生态隔离的 SDK/端点识别 | train/dev 候选 |
| `microsoft/semantic-kernel` | 多语言 API、模型连接器 | 用于跨语言和 provider-neutral 映射复核 | holdout 候选 |

上表只构成采购与复核队列。实际纳入前由资料负责人把每个项目固定到 commit、完成许可/再分发筛查、与既有 family/content 去重，然后才由 Bench 维护者生成 manifest。不得把仓库名称、公开状态、stars、HF 可见性或 `gated=false` 解释成授权、许可证兼容或合规通过。

## 3. human reviewer、holdout 与 amendment 流程

```text
固定候选范围与 commit
  -> 脱敏 source index + train/dev/holdout 分组
  -> 隐藏系统预测的真人标注
  -> 独立复核 / 必要时真人裁决
  -> gold freeze（SHA 绑定）
  -> 仅一次锁定版本的 holdout 评测
  -> 结果与错误分类
  -> 如发现来源/标签/范围错误：追加 amendment，并使受影响结果失效
```

### 3.1 人工审查

- `benchmark_gold` 模式中，评审人不得看到系统预测、AI 草稿、另一名真人结论或同批 amendment；须记录 reviewer ID、角色、时间、暴露声明与覆盖 case。
- 可先使用练习样本校准口径；练习样本不得进入正式指标分母。
- 两名不同真人完成独立标注后，分歧由真人裁决；证据不足时保留 `uncertain`/`disputed`，AI 不能担任裁决者。
- 单真人时间隔离复标可形成受限的 `reportable_single_human` 证据，但不得表述为双人独立标注。

### 3.2 holdout

- holdout 必须与 train/dev 按项目族和内容摘要隔离，在 gold freeze 前不得用于规则、提示词、阈值、模型训练或错误分析。
- 仅允许冻结后的目标版本、固定运行配置和 SHA 绑定的 gold/matching policy 在 holdout 上评测。
- 任一开发性暴露均必须在 `governance.exposures` 留痕，并将该 revision 降至 development；不能“换个名字”继续报告为未泄漏 holdout。

### 3.3 amendment

amendment 触发于 `source_correction`、`label_correction`、`scope_correction`、`evidence_recovery` 或 `policy_change`。它必须包含目标对象、旧/新摘要、理由、提出者、真人批准者、时间和不可变 artifact；AI 可提出但不能是唯一批准者。变更 case、gold、matching policy、split、review 或 freeze 时，父 revision 的相关 evaluation 自动失效，必须重新评测。禁止借 amendment 排除预测失败的 case；此类行为应记录为选择偏差并阻断正式等级。

## 4. `ResourceProfileDraft` 与 Hugging Face fixture 映射

Draft 是 provider-neutral 的内部候选对象：它保存“某 provider 响应中观察到的字段与证据”，不是许可证、授权或合规结论。身份、生命周期、声明元数据、字段级 `EvidenceRef`、诊断和稳定 ID 必须保持可追溯；无法安全确定身份时 fail closed，不生成可匹配资源。

| Draft 概念字段 | HF model fixture | HF dataset fixture | 处理边界 |
| --- | --- | --- | --- |
| `provider` / `resource_kind` | 固定 `huggingface` / `model` | 固定 `huggingface` / `dataset` | 不由 URL 猜测其他 provider |
| `canonical_id` | `/id` | `/id` | 缺失或空值时拒绝身份 |
| `revision` | `/sha`, `/lastModified` | `/sha`, `/lastModified` | 只作版本事实，不等于权利状态 |
| 可见性/可用性 | `/private`, `/gated`, `/disabled` | 同左 | 不推出可用、获授权或可再分发 |
| 许可证声明候选 | `/cardData/license`、tags | `/cardData/license`、tags | 保留原值和冲突诊断，不标准化为 SPDX 结论 |
| 描述/标签 | `/cardData/*`、`/tags` | `/cardData/*`、`/tags` | 仅作为可定位元数据 |
| 字段证据 | fixture SHA + JSON Pointer | fixture SHA + JSON Pointer | 只使用离线、脱敏 fixture |

投影至既有 P0 候选时，必须固定 `license_expression_id=null`、`authorization_status=pending`。`private=false`、`gated=false`、存在 `sha`、抓取成功或 `cardData.license` 非空，均不得提升这些字段。新增正式 `detected_by` 枚举、公共 Evidence materialization 或 P0/P1 字段，先走第 6 节批准。

## 5. FN/FP taxonomy 初稿

分类单位是“gold 中的资源声明或风险断言”与“预测对象”的匹配结果；一条资源可同时有身份、版本、类别、证据、许可证声明和风险多个维度。未建立完整 gold 时，只能登记候选复核缺陷，不能报告 FN、recall 或生产准确率。

| 类别 | 代码 | 定义 | 优先处置 |
| --- | --- | --- | --- |
| FN：完全漏检 | `FN-ABSENT` | gold 对象在预测中完全不存在 | 扩充检测模式/fixture |
| FN：类型漏检 | `FN-TYPE` | 识别到对象但模型/数据集/API/组件类型错误 | 修正分类器与匹配策略 |
| FN：身份或版本漏检 | `FN-IDENTITY` | 同类候选存在但 canonical ID、revision 或 locator 不可接受 | 补证据定位，不自动合并 |
| FN：证据漏检 | `FN-EVIDENCE` | 结论未能回链到 gold 要求的文件/字段/片段 | 增加 EvidenceRef 规则 |
| FN：风险漏检 | `FN-RISK` | 可证实的规则触发未产生 finding | 修正规则与前置事实 |
| FN：不确定性漏检 | `FN-UNCERTAINTY` | 证据不足却未标 `unknown`/`review_required` | 加强 fail-closed 降级 |
| FP：幻觉对象 | `FP-HALLUCINATED` | 预测对象不存在于定义的标注范围 | 收紧模式或 AST/证据要求 |
| FP：错误归属 | `FP-ATTRIBUTION` | 把文档示例、注释、依赖名或其他资源归为实际对象 | 标示引用强度，不声称运行使用 |
| FP：类别错误 | `FP-TYPE` | 将正确字符串归到错误资源类别 | 调整类型判别 |
| FP：过度精确 | `FP-OVERPRECISION` | 名称/版本/许可证/授权超出证据可支持程度 | 降为候选或 `pending` |
| FP：证据错配 | `FP-EVIDENCE` | evidence 指向不同对象、过期 revision 或不支持断言 | 修正 join 与 revision 绑定 |
| FP：风险过报 | `FP-RISK` | 规则前置条件不成立、许可来源冲突或范围不适用 | 修正规则条件，保留人工复核 |
| FP：泄漏污染 | `FP-LEAKAGE` | 预测或阈值受 holdout/答案暴露影响，表观命中不可计 | 作废该 revision 结果 |

每个错误记录至少包含 `error_id`、case/gold/prediction 引用、任务维度、taxonomy code、严重性、证据、发现阶段、处置状态和 amendment 链接（如有）。`uncertain` 不能默认为 TP 或 FP：报告时单列，或由预先冻结的 matching policy 定义处理方式。

## 6. 需要负责人批准的公共字段清单

以下字段在获批准前仅可位于内部 Draft、离线 fixture 或文档示例，禁止写入 P0/P1 公共 Schema、Web API、公开报告或正式 Bench gold。

| 字段/变更 | 原因 | 批准前的安全行为 | 建议批准人 |
| --- | --- | --- | --- |
| `ResourceProfileDraft` 作为公共对象 | 会形成新对外契约与版本责任 | 仅 Java 内部记录 | Sol + Root |
| `provider`、`canonical_id`、`resource_kind`、`revision` | 影响跨 provider 去重和匹配 | 不生成公共 stable ID | Sol + Terra |
| `visibility`、`gated`、`disabled` | 容易被误读为访问权或授权 | 只保留原始元数据证据 | Sol + 人工权利负责人 |
| `declared_license_raw` / SPDX 映射 | 涉及许可证标准化与风险规则 | `license_expression_id=null` | Sol + 规则负责人 |
| `authorization_status` | 涉及使用/再分发权利陈述 | 固定 `pending` | 人工权利负责人 + Root |
| 新 `detected_by` 枚举 | 影响 P0 schema、报告和历史兼容性 | 临时复用已批准值或不公开 | Sol + Terra |
| 公共 `Evidence` materialization | 影响证据 ID、脱敏与再分发责任 | 保留 fixture SHA + JSON Pointer | Sol + Luna |
| `reviewer_id`、独立性/暴露字段 | 含身份与审查治理风险 | 使用最小化、去标识化 ID | Root + 人工标注负责人 |
| `holdout` 公开索引/来源定位 | 可能泄漏评测样本 | 只公开聚合统计或冻结后摘要 | Root + Bench 维护者 |
| amendment 批准人及裁决字段 | 会决定 gold 与指标是否有效 | 禁止 AI 唯一批准 | Root + 人工裁决负责人 |
| FN/FP taxonomy 及 matching policy | 直接改变指标口径 | 先版本化为 `draft`，不回填历史结果 | Sol + Luna + Root |

批准记录应明确：字段定义、JSON Schema/API 版本、默认值、空值语义、迁移策略、脱敏与再分发策略、测试 fixture、回滚方案和生效 revision。未经批准，不得以“实现已经存在”作为公开字段或效果结论的依据。

## 7. 验收与后续责任

1. Luna：为每个最终入选仓库建立脱敏 source index、固定 commit 和正/反 fixture，并独立复核 split/family 去重；
2. Sol：冻结 taxonomy、matching policy 和公共 Schema 变更提案；
3. Terra：在批准后的字段契约下接入 scanner/materializer/report，不联网抓取、不开启服务；
4. 人工 reviewer：执行未见系统结果的标注、独立性/暴露签收及裁决；
5. Root：在 artifacts、审查回执、holdout 记录和测试均齐全后，验证 manifest 及发布范围。

在上述门禁关闭前，本规范中的候选库和 taxonomy 都是可审查的设计输入，不能用来宣称正式 gold、双人独立质量、许可证通过或可比较的公开指标。
