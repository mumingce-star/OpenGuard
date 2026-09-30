# Detector 0.3、B03/B04 与 B05–B07 离线准备冻结

状态：`draft / offline only`（2026-09-27）。本文件冻结本轮两个检测任务及其交付边界；不新增公共 API、P0/P1 Schema、生产扫描接线、正式 Gold、Assessment、NoticeDraft 或报告结论。

## 1. 两个独立检测任务

| 任务 | 输入 | 允许输出 | 明确禁止 |
| --- | --- | --- | --- |
| AI资源 Detector 0.3 | 已读取的相对路径文本；离线 fixtures | pending AIAsset 候选及文件/行证据 | 网络、执行输入、授权/许可证推断、正式 Gold 指标 |
| License/NOTICE facts detector | 由 caller 哈希固定的 facts package | `review_required` facts 候选 | 从 LICENSE 文本推断 NOTICE、产生 obligation、授权或正式 expression |

Detector 0.3 的离线 fixture 是 `tests/fixtures/detector-0.3/cases.json`：包含 AST、字面量结构化配置、URL revision 正例，以及 `FN-ABSENT`、`FN-EVIDENCE`、`FP-ATTRIBUTION`、`FP-HALLUCINATED`、`FP-OVERPRECISION`、`FP-LEAKAGE` 各一例。每个 `family_id` 只允许出现于 train、dev、holdout 中的一个 split；该文件自声明 `offline_non_gold`，不能转换为正式 Gold 或指标分母。

当前静态识别覆盖 Hugging Face/ModelScope 模型与数据集 URL、Python 调用、Python 与 JavaScript/TypeScript 中具明确导入和构造调用的 OpenAI/Anthropic/Google SDK，以及 YAML/JSON/TOML 与 `.env` 的受限字面量配置入口。输出统一为 pending/review-required 资源候选，带资源类型、来源、文件/行定位、规则版本和证据 SHA-256；环境变量值不进入证据。仅导入 SDK、普通 URL、动态字符串、别名/动态 import、注释/文档与无关配置均不形成候选。

TOML、JSON 和受限的单行 YAML 仅接受明确的模型/数据集字段（如 `model_name_or_path`、`pretrained_model_name_or_path`、`dataset_name`）；它们以 `manifest_parser` 和 `manifest_field` 作为配置候选证据，不表述实际运行。JSON 重复键、无效 TOML、YAML 动态/复杂结构均失败关闭。URL 仅接受明确的 Hugging Face 资源根或 `resolve/blob` 文件路径；docs、blog、papers、tree、space、登录等路由一律是负例。

`tests/fixtures/detector-0.3/manifest.json` 是 `openguard.detector-artifact-manifest/1`：固定 `cases.json`、`detector.json`、`input.json`、`prediction.json`、`result.json` 的路径、长度、SHA-256 与依赖边；每个下游工件还回写直接上游的路径/摘要。`test_detector_03_offline_tdd.py` 必须同时复算这两层约束并用内存篡改样本验证拒绝。预测/结果均为 `not_executed`、指标为 `null`，不能报告正式指标。FN/FP taxonomy 的每个类别均由该测试逐项消费并断言其 fixture 回归，仍不构成 Gold。

## 2. B03/B04 v3 consumption adapter

`app.detectors.license_notice_facts_v3_adapter` 是仅内存、只读的消费适配器。它必须接收 caller 在不可变 artifact 中固定的 canonical SHA-256，并只输出已观察的 subject、三种 relationship state、gap 与 provenance evidence ID。它不把 v3 降级或伪装成 B02 v2 输入。

每一个导出的对象保持以下不变量：

- `authorization_status="pending"`；
- `license_expression_id=null`；
- `gap` 仍是信息/证据缺口，非违规；
- `text_observed` 的 LICENSE 与独立 NOTICE 观察相互独立；
- provider label 是 `provider_declared_unverified`，不构成授权、适用性或 SPDX 标准化。

消费方 A 只能将 adapter 的 `source_package_sha256` 与 its facts binding 一起存储；hash 不匹配、引用不闭包、状态升级或 unknown relationship 一律拒绝。任何将 v3 变为 B02 输入的迁移，都必须新建版本化 adapter、独立 manifest、人工评审和新 revision，不得修改 v2 或 P1 固定结果。

## 3. NOTICE source 交付给 A 的契约

交付候选是内部 `NoticeSourceStore` 的 `STAGED -> BOUND -> read-only` 路径。A 的前置条件是：实际 ScanRun revision、input/inventory digest、formal Assessment facts hash 与 stage package hash 全部匹配。A 不得信任 caller 自述 binding，不得回填 source 内容，不得用 Git URL hash 代替归档字节 hash。

交付测试必须分别覆盖：包/行篡改拒绝、hash/scan/assessment 边界不匹配、单包与数据库容量拒绝、进程重启后只读读取相同绑定、symlink/sidecar 拒绝及 `partial` omission 保留。只有这些定向测试均通过且 A 确认消费语义后，才允许提交或发布；本轮没有作出该确认。

## 4. B05/B06/B07 受控准备

### B05

当前唯一可运行的开发输入是 `benchmarks/examples/v2/development-detector-v1`：`source_commit=a34c29f`，每个 artifact 已固定 size/SHA-256，facts 输入固定为其 `expected_package_sha256`。它的 Gold 是明示 `human_gold_frozen=false` 的占位输入，故只允许 `smoke`，预测/结果保持 `not_executed`，不得出现 Precision、Recall 或 F1。

### B06

候选仓库仅作为 `reference_only` 队列，名单与选择约束见 `b-p1-06-bench-public-corpus-governance.md`。每一条纳入记录在人工复核前必须一次性冻结：`repository_url`、40 位 `commit`、source bytes `sha256`、source timestamp、redistribution status、family_id、split 和审核人。任何缺字段条目均不得进入 train/dev/holdout 或盲审包；不得以仓库可公开访问、license label 或 stars 替代授权许可。

首批已固定的 `reference_only` 候选见 `benchmarks/candidates/b06-reference-only-v1.json`：它只引用既有 `source-reverification.json` 的三组公开仓库、固定 commit 与 Git 对象 SHA-256，不保存第三方源文件、不赋予 Gold/split，也不宣称取得再分发授权。真人权利复核、family 去重和 split 赋值仍是准入前置条件。

盲审包只可包含 case ID、去标识 source locator、任务说明和事实证据；必须排除 split、系统预测、AI 草稿、其它 reviewer 结论、正式 Gold 和可还原的第三方正文。review receipt 必须记录 reviewer 的去标识 ID、角色、独立性与 exposure 声明、case 覆盖、时间、输入 artifact hash 和 reviewer 提交 hash。AI 不得作为唯一批准者。

### B07

受控 receipt 统一使用 `openguard.controlled-pipeline-receipt/2`，必须含：`execution_mode="controlled_linux"`、`production_scan_started=false`、`startup_mode=cold|warm`、固定 Linux kernel/image digest、CPU、内存限制/峰值、ScanCode/Syft/Detector/规则版本、输入/配置/结果 artifact hashes。阶段以固定顺序记录 `unpack`、`scancode`、`syft`、`static_detector`、`rule_consolidation` 的耗时和 completed/failed/not_run 状态；失败必须保留受控错误码与原因。任何 receipt 缺字段、环境不一致、重复 `receipt_id`、来源 hash 未固定或有生产扫描迹象，均不能进入汇总。`b07-summarize-receipts.mjs` 输出 p50/p95、冷/热、阶段覆盖率、失败率和错误分类的描述统计，并固定 `formal_performance_claimed=false`，不是生产性能基准。

amendment 只能追加，必须含 parent revision、受影响 artifact、旧/新 SHA-256、原因、提出者、人工批准者和时间；影响 source、label、split、review 或 freeze 时，相关 evaluation 自动失效且必须重跑。
