# 技术报告证据映射

状态：`ACTIVE_CONTROL_PLANE`

版本：`0.1`

适用范围：附件2九章技术报告、演示视频、答辩材料和佐证材料的事实门禁。本文不是报告正文。

## 1. 字段与状态

每条主张必须包含：

- `claim_id`：稳定主张 ID；
- `评分项`：`SCORE-01` 至 `SCORE-06`，可多选；
- `evidence_id`：稳定证据 ID；`EVD-PLANNED-*` 只是预留号，不表示证据已存在；
- `位置`：仓库文件、测试产物或受控材料位置；
- `owner`：产出与复核责任线；
- `验证方法`：可重复的事实核验方法；
- `版本/run_id`：代码提交、规则/Bench 版本或扫描运行 ID；
- `披露边界`：`public`、`deidentified`、`restricted` 或 `do_not_publish`；
- `状态`：`verified`、`planned`、`blocked`。

`verified` 只表示当前证据支持表中限定的主张，不代表完整产品或最终报告已经完成。性能、截图、实验和用户反馈没有原始记录时必须保持 `planned`/`blocked`。

## 2. 九章控制矩阵

| claim_id | 章节/拟用主张 | 评分项 | evidence_id | 位置 | owner | 验证方法 | 版本/run_id | 披露边界 | 状态 |
|---|---|---|---|---|---|---|---|---|---|
| `CLM-01-001` | 一、OpenGuard 申报“AI 开发工具与开源协作”，产品定位为对软件、模型、数据集和 API/服务做统一证据化盘点。 | `SCORE-01`,`SCORE-03` | `EVD-OFFICIAL-RULES-20260812` | `docs/spec/competition-requirements.md`、`README.md` | Sol 编制，Luna 复核 | 对照正式附件1 p.1、通知 p.4 和项目 README；问题真实性另由 `CLM-01-002` 验证 | 规则基线 2026-08-12；snapshot `1d77a51` | `public` | `verified` |
| `CLM-01-002` | 一、目标用户痛点真实且优先级明确。 | `SCORE-01` | `EVD-PLANNED-NEEDS-001` | 计划：匿名访谈/案例/竞品原始记录 | 团队采集，Sol 设计，Luna 归档 | 样本范围、日期、问题、原始匿名记录和分析可追溯 | 待分配 | `deidentified` | `planned` |
| `CLM-01-003` | 一、成品的三项核心亮点为四类资源统一建模、第一类证据链、确定性规则与 AI 分层。 | `SCORE-02`,`SCORE-03` | `EVD-PLANNED-PRODUCT-001` | 设计契约在 `docs/spec/p0-domain-contract.md`；完整实现/端到端证据待形成 | Sol/Terra/Luna | 对象与证据链已有 A1 证据；规则/AI/报告主链完成后再联合核验 | 待最终实现版本/run_id | `public` | `planned` |
| `CLM-02-001` | 二、P0 领域模型和六个 `/api/v1/scans` 接口已冻结，可供后续模块消费。 | `SCORE-02`,`SCORE-04` | `EVD-A1-CONTRACT-002` | `docs/spec/p0-domain-contract.md` | Sol；Terra/Luna 已消费 | 核对版本、API 表、状态机和变更策略 | contract `0.1.1`; snapshot `1d77a51` | `public` | `verified` |
| `CLM-02-002` | 二、系统架构覆盖安全输入、扫描、标准化、规则、AI 和报告闭环。 | `SCORE-02` | `EVD-PLANNED-ARCH-001` | `docs/01-system-architecture.md`；最终架构图待形成 | Sol/Terra | 架构图与实际模块、数据流、信任边界逐项对照 | 待实现版本 | `public` | `planned` |
| `CLM-02-003` | 二、比赛版可在学生团队可承担的单机成本内部署。 | `SCORE-01`,`SCORE-04` | `EVD-PLANNED-DEPLOY-001` | 计划：部署清单、资源观测和陌生设备复现记录 | Terra，Luna 复现 | 锁定硬件/软件环境，记录安装耗时、峰值资源和失败 | 待分配 | `deidentified` | `planned` |
| `CLM-03-001` | 三、`Component` 与 `AIAsset` 覆盖软件、模型、数据集、API/服务，且所有资源至少引用一条 Evidence。 | `SCORE-02`,`SCORE-03` | `EVD-A1-MODEL-001` | `backend/app/domain/models.py`、`schemas/p0/scan-result.schema.json`、`examples/sample-scan-result.json` | Terra 实现，Luna 测试，Sol 审核 | Pydantic、Draft 2020-12 Schema、sample 与引用完整性测试 | contract `0.1.1`; snapshot `1d77a51` | `public` | `verified` |
| `CLM-03-002` | 三、AI 对非结构化内容做候选抽取、解释和整改，不能覆盖确定性事实，关闭后主链仍可用。 | `SCORE-03`,`SCORE-04` | `EVD-PLANNED-AI-001` | 契约在 `docs/spec/p0-domain-contract.md`；运行时和消融待实现 | Sol/Terra/Luna | AI 开/关同样例；Schema、证据引用、冲突、超时、幻觉负例 | 待分配 | `public` | `planned` |
| `CLM-03-003` | 三、所有开源及第三方资源均披露版本、来源、许可/授权、自研边界、义务和开放方式。 | `SCORE-03`,`SCORE-05` | `EVD-PLANNED-LEDGER-001` | `third_party/README.md`；最终资源台账/附件待形成 | Luna 台账，Sol 审核 | 对锁版清单、上游 LICENSE/NOTICE 和附件七字段做交叉审计 | 待分配 | `public`/`restricted` 逐项决定 | `planned` |
| `CLM-04-001` | 四、A1 已实现 Pydantic 领域模型、公开 JSON Schema、sample 和边界验证。 | `SCORE-02`,`SCORE-04` | `EVD-A1-TEST-001` | `backend/app/domain/models.py`、`schemas/p0/scan-result.schema.json`、`examples/sample-scan-result.json`、`tests/unit/test_p0_domain_models.py` | Terra 实现，Luna 独立回归 | 执行 `PYTHONPATH=backend python -m pytest -q tests/unit/test_p0_domain_models.py`，并检查 Schema 导出一致 | snapshot `1d77a51`; 当前 46 项 | `public` | `verified` |
| `CLM-04-002` | 四、截至当前基线，团队已持续记录 AI 辅助研发的用途、修改和验证。 | `SCORE-03`,`SCORE-06` | `EVD-AI-LOG-001` | `docs/05-ai-assistance-log.md` | 各模型记录，Sol/Luna 终审 | 与 Git 变更、日志和测试逐条抽查；最终提交仍需检查遗漏 | 滚动记录至提交版本 | `public` | `verified` |
| `CLM-04-003` | 四、Git/ZIP 输入满足 A2 安全门禁且不执行目标代码。 | `SCORE-02`,`SCORE-04` | `EVD-PLANNED-A2-001` | `docs/security/threat-model.md`、`docs/security/a2-security-acceptance.md`；实现/测试待形成 | Sol 设计，Terra 实现，Luna 审计 | 全部 `SEC-A2-*` 与负面测试通过，保留命令和脱敏结果 | 设计 `0.1`; 无 run_id | `public` | `planned` |
| `CLM-05-001` | 五、从 Git/ZIP 到 HTML/JSON/资源清单的主流程可运行、可演示。 | `SCORE-04` | `EVD-PLANNED-E2E-001` | 计划：固定 fixture、端到端结果、脱敏截图和演示 | Terra，Luna 复现 | 空环境按固定命令运行，保存提交、配置摘要、输入/输出哈希与 run_id | 待分配 | `deidentified` | `planned` |
| `CLM-05-002` | 五、OpenGuard 在 Bench 上的准确率、召回率、F1、人工修正率、耗时和失败率达到可报告结果。 | `SCORE-04` | `EVD-PLANNED-BENCH-001` | 计划：`benchmarks/` 原始 JSON/CSV、标注、脚本和错误样例 | Sol 指标，Luna 数据，Terra 执行 | 固定 Bench/代码/规则版本重算；检查样本去重、防泄漏和置信说明 | 待分配 Bench/run_id | `public`/`restricted` 逐样本决定 | `planned` |
| `CLM-05-003` | 五、用户试用证明工具易用或减少披露遗漏。 | `SCORE-01`,`SCORE-04` | `EVD-BLOCKED-USER-001` | 尚无用户反馈 | 团队采集，Luna 归档，Sol 审核 | 需真实匿名记录、样本范围、任务、问题与同意边界 | 无 | `deidentified`/`restricted` | `blocked` |
| `CLM-05-004` | 五、A1 当前测试基线为 46 项通过。 | `SCORE-04` | `EVD-A1-TEST-002` | `tests/unit/test_p0_domain_models.py`、共享工作日志 | Luna/Root | 在当前提交重跑单文件测试；报告只引用对应提交的结果 | snapshot `1d77a51` | `public` | `verified` |
| `CLM-06-001` | 六、团队自主代码和文档采用 Apache-2.0，第三方资源不因本仓库许可证改变原权利。 | `SCORE-05` | `EVD-LICENSE-001` | `LICENSE`、`README.md` | Root/Sol | 核对仓库许可证文本与 README 权利边界 | snapshot `1d77a51` | `public` | `verified` |
| `CLM-06-002` | 六、公开成果包括可复用代码、规则、Bench、测试、文档和维护计划。 | `SCORE-05` | `EVD-PLANNED-OPEN-001` | 最终公开仓库/Release/维护说明待冻结 | Root/Terra/Luna | 未登录访问、文件清单、安装/测试复现、权利扫描 | 待最终提交 | `public` | `planned` |
| `CLM-06-003` | 六、具有实际状态的上游 Issue/PR 或社区贡献。 | `SCORE-04`,`SCORE-05` | `EVD-PLANNED-UPSTREAM-001` | 当前无可报告贡献 | 团队 | 核对公开链接、提交者授权、状态和贡献内容 | 无 | `public` | `planned` |
| `CLM-07-001` | 七、Sol 已完成不可信 Git/ZIP 等风险设计，Terra 已完成工程可实现性审查，Luna 已完成独立可测性审计；当前仅构成条件性设计基线，不构成实现有效性证明。 | `SCORE-02`,`SCORE-06` | `EVD-S2-DESIGN-001` | `docs/security/threat-model.md`、`docs/security/a2-security-acceptance.md`、`docs/security/a2-implementation-review.md`、`docs/security/a2-test-audit.md` | Sol 设计；Terra/Luna 审查完成；Root 限定状态 | 核对威胁-控制-测试 ID、Terra `12 ACCEPT/6 ADJUST/2 BLOCK` 与 Luna `1/3/1` 正向、`9/20/7` 负面设计判定；实现效果另见 `CLM-07-002` | design `0.1`; reviews 2026-09-02；无实现 run_id | `public` | `verified` |
| `CLM-07-002` | 七、安全控制在真实 A2 实现中有效。 | `SCORE-04`,`SCORE-06` | `EVD-PLANNED-A2-TEST-001` | 计划：安全单元/集成测试与隔离运行记录 | Terra/Luna | 全部 `NEG-A2-*` 通过；资源、清理、网络和日志独立检查 | 待分配 | `deidentified` | `planned` |
| `CLM-07-003` | 七、许可证和授权核验已覆盖最终实际使用的全部第三方资源。 | `SCORE-03`,`SCORE-05`,`SCORE-06` | `EVD-PLANNED-LICENSE-001` | 最终资源台账、上游许可快照和审查记录待形成 | Luna 整理，Sol/Owner 核验 | 锁定版本逐项核对来源、授权、义务、开放边界 | 待分配 | `public`/`restricted` | `planned` |
| `CLM-08-001` | 八、项目已建立区分“已完成、未完成、实验观察和未来计划”的报告治理机制。 | `SCORE-06` | `EVD-PROGRESS-001` | `docs/coordination/PROJECT_PROGRESS.md`、本映射 | Root/Sol/Luna | 对当前状态逐项比对代码、测试和材料；最终报告仍需重新核验 | 滚动；最终提交前冻结 | `public` | `verified` |
| `CLM-08-002` | 八、后续功能、开放维护和社区协作计划可执行但不冒充现状。 | `SCORE-05`,`SCORE-06` | `EVD-PLANNED-ROADMAP-001` | 最终维护计划待形成 | Root/Terra | 每项列责任人、里程碑、依赖和公开边界 | 待分配 | `public` | `planned` |
| `CLM-09-001` | 九、附录资源清单完整映射附件2七组业务字段。 | `SCORE-03`,`SCORE-05`,`SCORE-06` | `EVD-PLANNED-INVENTORY-001` | 最终《开源及第三方资源使用清单》待形成 | Luna/Terra/Sol | 台账到附件无损映射；空值、状态和授权逐项复核 | 待分配 | `public`/`restricted` | `planned` |
| `CLM-09-002` | 九、代码、演示、安装包/网盘链接和运行说明在评审期有效。 | `SCORE-04`,`SCORE-05`,`SCORE-06` | `EVD-BLOCKED-LINKS-001` | 最终成果链接未冻结 | Root/Terra/Owner | 未登录、异机、完整下载/部署/播放和权限复核 | 无 | `public`/`restricted` | `blocked` |
| `CLM-09-003` | 九、测试、反馈、Bench、Issue/PR 和提交记录均可回到原始证据。 | `SCORE-04`,`SCORE-05` | `EVD-PLANNED-APPENDIX-001` | 最终 evidence index 待导出 | Luna | 校验 ID、哈希、版本、run_id、权限和匿名状态 | 待分配 | 逐项决定 | `planned` |

## 3. 章节门禁

| 章节 | 附件2参考页 | 报告进入定稿的最低门禁 |
|---|---|---|
| 一、作品概述 | p.2 | `CLM-01-002` 有真实需求证据；核心亮点不超过实际实现。 |
| 二、需求分析与总体方案 | p.2 | 架构图与代码一致；成本/资源数据有观测记录。 |
| 三、AI技术与开源及第三方资源选择 | p.2-p.3 | AI 必要性有消融；资源、自研与权利边界台账完整。 |
| 四、设计与实现过程 | p.3 | 功能、分工、迭代和 AI 记录与 Git/工作日志一致。 |
| 五、成果展示与效果验证 | p.3 | 只采用带版本/run_id 的实验、截图和反馈；未达目标如实披露。 |
| 六、创新性与开放价值 | p.3 | 竞品版本/日期明确；公开成果已完成权利和复现审查。 |
| 七、合规、安全与风险说明 | p.3-p.4 | 许可证、安全、AI、知识产权和适用边界均有剩余风险。 |
| 八、总结与展望 | p.4 | 现状与计划分栏；不把计划状态改写为完成。 |
| 九、附录 | p.4-p.5 | 资源表、链接、运行说明、原始记录、受限提交说明齐全。 |

## 4. 采用与撤回规则

1. 主张进入报告前，`status` 必须为 `verified`；`planned` 只能写入“计划/未完成”，`blocked` 只能写入限制与依赖。
2. 代码、规则、模型、Bench 或截图版本变化后，相关 `verified` 自动退回 `planned`，直至重新核验。
3. 证据位置不可访问、哈希不一致、授权过期或匿名失败时，立即撤回主张，不以截图片段替代。
4. `SCORE-04` 的数字必须能由原始 JSON/CSV 重算；四舍五入规则和样本量在图表附近披露。
5. 许可证和授权只采用风险提示/核验状态语言；“公开可访问”不得写成“开源”或“可再利用”。
