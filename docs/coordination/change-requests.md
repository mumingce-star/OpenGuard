# Cross-owner change requests

## CR-20260905-B1-B7-closure

- Requested by: CZ, 2026-09-05.
- Scope: continue B1–B7 implementation using the frozen P0 domain contract.
- Target files: `backend/app/scanners/`, `backend/app/licenses/`, `backend/app/detectors/`, `benchmarks/`, and their unit fixtures/tests.
- Ownership impact: backend implementation is normally Terra-owned and test/bench content Luna-owned. The user explicitly authorized direct completion in this conversation.
- Contract impact: additive modules only. `Resource`/`Evidence`/`RiskFinding` P0 schema, source-evidence gate, and no-legal-advice semantics remain unchanged.
- Verification: deterministic fixture tests, schema-compatible model construction, `compileall`, and targeted pytest. Linux-only external-tool ZIP gates remain separately reported if the host cannot evidence them.

## CR-20260913-java-backend-migration

- Requested by: 用户，2026-09-13。
- Scope: 审计 `backend/app/**/*.py`，以 Java 作为新的后端运行时主线；优先迁移领域模型、受限仓库扫描、依赖/许可证/AI 资源发现、规则结果和结构化报告。
- Target files: 新增 `backend/java/` Maven/Spring Boot 模块及其测试、迁移规范、协调记录；既有 Python 文件在 Java 契约与安全回归通过前作为兼容基线保留，不删除、不覆盖。
- Ownership impact: `backend/` 通常由 Terra 负责；本次由用户明确授权 Root 直接实施。变更将触及不可信路径、Git 输入和外部工具边界，必须保留不执行目标代码、不安装目标依赖、证据优先与人工复核语义。
- Contract impact: 保持 P0 JSON Schema、`unknown`/`review_required` 语义和报告证据链；Java 输出新增而非替换已发布 Python API，生产切换需另行验收。
- Verification: Maven 单元测试、固定样例契约校验、真实受信任检出仓库扫描、JSON/CSV/HTML 结构化产物校验，以及 Python/Java 对照测试；外部 ScanCode/Syft 仅在其可执行文件已固定并可用时启用。
## CR-20260913-second-human-blind-review

- 提出者：GPT-5 / Root Coordinator；日期：2026-09-13；状态：执行中（用户明确授权）。
- 目标：在 `benchmarks/annotations/real-resource-20260911-ai-assisted/` 新增第二位独立真人盲审的隔离材料、空白五维裁决模板、提交校验器，以及盲审完成后使用的分歧/仲裁模板。
- 所有权与影响：目标目录为 Luna 的标注材料范围；不修改 `ai-draft.json`、`human-confirmation.json`、`human-amendment-r05.json` 或已有指标。新增契约要求第二评审在提交前不可接触 AI 草稿、首位裁决、R05 修订和 AI 复审，并逐条填写 resource/evidence/license/risk/suggestion 五维。
- 验收：包内不泄露被隐藏结论；R01-R12 恰好各一条；严格校验独立性声明、包哈希与全部五维；分歧/仲裁工作区在盲审锁定前不得写入最终裁决。后续由 Luna 复核材料可用性、由 Sol 复核仲裁语义。

## CR-20260917-single-human-rereview

- 提出者：用户；日期：2026-09-17；状态：实现完成，待真人执行。
- 目标：在只有一名真人的条件下，为既有R01-R12建立时间隔离盲化复标、两轮差异、冲突查证和最终冻结闭环，并提供详细操作手册。
- 所有权与影响：新增内容位于Luna负责的Bench标注材料目录；用户明确授权Root直接实现。不修改既有AI草稿、首轮真人回执、R05修订、gold指标或公共P0/P1 Schema。
- 契约边界：仅允许声明`single_human_time_separated_rereview`；不能声明双人独立复核、标注者间一致率或AI第二评审。当前工具仅适用于`output_review`，不得用于隐藏预测的`benchmark_gold`。
- 验收：至少72小时冷却；12条/60维完整填写；逐维理由和逐记录证据定位；包、回执、比较、冲突与最终快照哈希绑定；篡改中间比较文件失败关闭；合成闭环14项通过。

## CR-20260918-bench2-java-contract

- 提出者：用户；日期：2026-09-18；状态：本地实现完成，待发布。
- 目标：按已批准的 B-P1-05 设计实现 Bench 2.0 Draft 2020-12 JSON Schema、独立 Java 校验库与 CLI、正反例和自动化校验测试，供 CI/Maven 离线使用，不新增 Web API。
- 所有权与影响：`backend/java/` 通常由 Terra 负责，`benchmarks/` 测试材料通常由 Luna 负责；用户已明确授权 Root 在本任务中直接实现。保留现有 P0/P1 Schema 与运行时接口，不改写人工标注或 gold 结论。
- 契约影响：新增 `openguard-bench-manifest/2.0` 和稳定诊断报告 `openguard-bench-validation-report/1.0`；Schema 负责结构约束，Java 负责 ID/引用闭包、split 隔离、holdout 暴露、amendment 链、文件哈希和正式指标准入；CLI 退出码固定为 0/1/2/3。
- 验收：Maven 单元/集成测试、正反例期望诊断、CLI JSON 与退出码、离线路径/符号链接/哈希安全测试、`git diff --check`、第三方依赖台账和设计/进度/AI 辅助记录同步。

## CR-20260920-bp1-public-field-approval

- 提出者：GPT-5 / Root Coordinator；日期：2026-09-20；状态：**待项目负责人批准**。
- 目标：为 B-P1-01 `ResourceProfileDraft`、B-P1-05 Bench 2.0 与 FN taxonomy 提交公共字段的显式批准请求；本请求本身不修改 Domain、Assessment、P0/P1 Schema、公共 API、报告 DTO 或现有 gold。
- 请求批准的范围：
  1. `ResourceProfileDraft` 是否作为版本化公共对象，以及 `provider`、`canonical_id`、`resource_kind`、`revision` 的定义、默认值、空值和迁移语义；
  2. `visibility`、`gated`、`disabled` 的展示/脱敏边界；它们不得表示授权或可再分发权；
  3. `declared_license_raw` 的公共暴露和后续 SPDX 映射责任；批准前 `license_expression_id` 固定为空；
  4. `authorization_status` 的枚举、责任人和证据门槛；批准前固定为 `pending`；
  5. `detected_by` 新枚举、公共 Evidence materialization、reviewer/holdout/amendment 治理字段；
  6. FN/FP taxonomy 与 matching policy 的版本、历史指标回填与 holdout 脱敏策略。
- 已有设计依据：`docs/spec/b-p1-01-resource-profile-draft.md` 第 6～8 节、`docs/spec/b-p1-05-bench-2-manifest.md`、`docs/spec/b-p1-06-bench-public-corpus-governance.md` 第 5～6 节。
- 批准前约束：只允许离线、脱敏 fixture 和 Java 内部 Draft；不得联网、不得实现 metadata transport、不得修改 Domain/Assessment/公共 API，且不得从 provider 元数据推导许可证、授权或合规结论。
- 请负责人逐项给出 `批准`、`驳回` 或 `需修订`，并记录 Schema/API 版本、迁移/回滚、脱敏与再分发策略、责任人和生效 revision。批准后才可进入 parser 接入、Gold、Detector 0.3、License Provenance/NOTICE Facts 与 holdout 阶段。
