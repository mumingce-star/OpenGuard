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