# 评分证据追踪矩阵

状态：`BASELINED`

版本：`0.1`

## 1. 状态与分值边界

证据状态只使用：

- `verified`：本仓库已有可定位产物，且本轮或既有可复现门禁已核验；
- `planned`：能力或证据尚未形成，但责任线和验收方法已确定；
- `blocked`：依赖外部授权、真实用户、最终上传或其他当前不可替代输入。

官方满分来自附件1 p.4-p.5。内部目标是团队规划，不代表评委承诺：

| 评分 ID | 官方评分项 | 官方满分 | 内部目标 |
|---|---|---:|---:|
| `SCORE-01` | 问题与场景价值 | 15 | 13 |
| `SCORE-02` | 创新性与方案设计 | 20 | 17 |
| `SCORE-03` | AI 与开源融合 | 20 | 18 |
| `SCORE-04` | 实现完成度与可验证效果 | 25 | 22 |
| `SCORE-05` | 开放成果与复用价值 | 15 | 13 |
| `SCORE-06` | 材料规范与表达 | 5 | 5 |
|  | **合计** | **100** | **88（内部）** |

不得把内部目标写入“官方分值”列，也不得用代码行数、材料数量或模型规模替代评分证据。

## 2. 评分项到交付证据

| 追踪 ID | 评分 ID | OpenGuard 能力/主张 | 代码证据 | 测试证据 | 材料证据 | 责任模型 | 状态 |
|---|---|---|---|---|---|---|---|
| `TRACE-01-A` | `SCORE-01` | 面向学生/开源团队解决四类第三方资源分散、来源难追踪和披露困难的问题。 | 不适用 | 需求案例验证尚未执行 | `README.md`、`docs/00-evaluator-charter.md`；真实访谈/案例记录待形成 | Sol 主责，Luna 核验材料 | `planned` |
| `TRACE-01-B` | `SCORE-01` | 竞品差异以可核验功能而非口号表达。 | 后续统一资源图谱与证据链实现 | 后续同一 fixture 的 ScanCode/Syft 基线对比 | 竞品能力/版本/日期/来源表待形成 | Sol/Terra | `planned` |
| `TRACE-02-A` | `SCORE-02` | 软件、模型、数据集、API/服务统一追踪，但保留 `Component` 与 `AIAsset` 的类型差异。 | `backend/app/domain/models.py` | `tests/unit/test_p0_domain_models.py` | `docs/spec/p0-domain-contract.md` | Sol 契约，Terra 实现，Luna 测试 | `verified` |
| `TRACE-02-B` | `SCORE-02` | `Evidence` 为第一类对象，风险、义务和整改通过稳定 ID 关联。 | `backend/app/domain/models.py` | A1 引用完整性与负面边界测试 | `docs/spec/p0-domain-contract.md`、`examples/sample-scan-result.json` | Sol/Terra/Luna | `verified` |
| `TRACE-02-C` | `SCORE-02` | 安全获取不可信 Git/ZIP 且不执行目标代码。 | A2 尚未实现 | `SEC-A2-*` 负面矩阵待实现 | `../security/threat-model.md`、`../security/a2-security-acceptance.md` | Sol 设计，Terra 实现，Luna 审计 | `planned` |
| `TRACE-03-A` | `SCORE-03` | AI 只做非结构化候选抽取、解释和整改；确定性事实优先，AI 失败可降级。 | 当前只有 `ProducerRef` 契约实现 | AI Schema、冲突、超时、关闭消融待实现 | `docs/spec/p0-domain-contract.md`、`docs/05-ai-assistance-log.md` | Sol/Terra/Luna | `planned` |
| `TRACE-03-B` | `SCORE-03` | 每项第三方资源披露来源、版本、许可/授权、自研边界、义务和开放方式。 | 资源清单生成器尚未实现 | 七字段映射与完整性测试待实现 | `docs/02-resource-inventory.md`、`third_party/README.md`；最终台账待补 | Luna 台账，Terra 导出，Sol 审核 | `planned` |
| `TRACE-03-C` | `SCORE-03` | 产品运行 AI 使用开放权重模型并记录 provider/model/schema 摘要。 | `ProducerRef` 三字段已实现；运行时未接入 | A1.1 条件字段测试已存在；真实 AI 回归待执行 | `docs/spec/p0-domain-contract.md`、`docs/05-ai-assistance-log.md` | Sol/Terra/Luna | `planned` |
| `TRACE-04-A` | `SCORE-04` | 从 Git/ZIP 输入到 HTML/JSON/资源清单报告一次跑通。 | A1 数据模型已实现；A2-A6 未实现 | 当前仅 46 项 A1 测试；端到端测试待形成 | 运行说明、演示视频、截图均待形成 | Terra 主责，Luna 验证，Sol 审计 | `planned` |
| `TRACE-04-B` | `SCORE-04` | OpenGuard-Bench 输出 Precision、Recall、F1、人工修正率、耗时和失败率，并含基线/消融/错误分析。 | Bench 脚本未实现 | 数据划分、标注复核和重算门禁待实现 | 原始 JSON/CSV、版本/run_id、图表待形成 | Sol 设计，Luna 数据，Terra 执行 | `planned` |
| `TRACE-04-C` | `SCORE-04` | 扫描超时、部分成功、未知与取消状态可解释且可复现。 | A1 状态机与运行时校验已实现 | `partial/error`、路径脱敏等 A1 测试已通过；A2/A4 集成待实现 | 错误案例表待形成 | Sol 契约，Terra 实现，Luna 回归 | `planned` |
| `TRACE-04-D` | `SCORE-04` | 真实用户试用或反馈支持效果主张。 | 不适用 | 试用方案和匿名同意记录待建立 | 尚无用户反馈，不得声称已验证 | 团队负责采集，Luna 归档，Sol 审核 | `blocked` |
| `TRACE-05-A` | `SCORE-05` | 自主代码与文档采用 Apache-2.0，第三方权利边界单独保留。 | `LICENSE` | 发布清单/许可证门禁待最终重跑 | `README.md`、`third_party/README.md` | Root/Terra/Luna | `verified` |
| `TRACE-05-B` | `SCORE-05` | 公开代码、规则、测试、Bench 和部署文档可由陌生人复现。 | 当前仅 A1 代码/Schema/sample | A1 可复现；完整陌生设备部署未执行 | 公开链接、维护计划和安装说明待完成 | Terra/Root，Luna 复现 | `planned` |
| `TRACE-05-C` | `SCORE-05` | 公开范围只含有权公开内容，受限内容给出明确开放计划。 | 不适用 | 发布前敏感/权利扫描待执行 | 最终授权与开放边界需权利人确认 | Root/团队权利人，Sol 审核 | `blocked` |
| `TRACE-06-A` | `SCORE-06` | 技术报告覆盖附件2九章且每项主张绑定证据。 | 不适用 | 报告链接、页数、大小、证据 ID 检查待实现 | `report-evidence-map.md` 已建立；报告正文未形成 | Sol 主编，Luna 事实审计 | `planned` |
| `TRACE-06-B` | `SCORE-06` | 名称、简介、PDF、视频、清单、链接、匿名和 AI 披露满足提交规范。 | 可选自动检查脚本尚未实现 | 最终上传前清单待签核 | `submission-checklist.md` | Luna 初检，Sol/Root 终检，队长签署 | `planned` |

## 3. 证据升级规则

1. `planned -> verified` 必须同时补齐：稳定位置、验证命令/方法、版本或 `run_id`、责任人复核和披露边界。
2. 截图只能证明对应版本的可见状态，不能代替原始测试或运行记录。
3. 用户反馈必须保留采集日期、样本范围、问题、原始匿名记录和同意/公开边界；没有记录时保持 `planned`/`blocked`。
4. 性能、准确率、召回率、错误率、耗时和用户数量不得从计划值推导。
5. `verified` 仅表示证据当前可核验，不表示评委必然给出内部目标分。
6. 报告中的采用状态以 `report-evidence-map.md` 为准；最终上传以 `submission-checklist.md` 为准。
