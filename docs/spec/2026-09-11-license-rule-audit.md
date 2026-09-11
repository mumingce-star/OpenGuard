# 许可证规则只读审计与修复建议

日期：2026-09-11。作者：GPT-6 / Root Coordinator。

## 范围与结论

检查当前工作分支 `codex/scan-reliability-integration@4c9e16b`，并对照已获取的集成版 `5611c00`。两版的 `backend/app/licenses/spdx.py`、`backend/app/rules/engine.py`、`rules/license-obligations.yaml` 无差异。未联网确认远端最新提交，结论仅对应这些版本。

规则引擎能生成有证据引用的复核提示，但表达式语义、覆盖完整性、输入一致性、共享对象聚合及规则治理仍有问题。此文只给方案，不修改业务代码、规则、Schema，不启动或停止服务，不自动提交或推送。

## 已验证问题与解决方案

### R1：OR 与 AND 被当成同一集合处理（优先修复）

- 位置：`backend/app/rules/engine.py:201`。引擎只读取 `normalized_ids` 集合，逐规则求交集，没有消费表达式结构。
- 复现：已验证证据下，`MIT OR GPL-3.0-only` 和 `MIT AND GPL-3.0-only` 都产生 MIT、GPL 两条相同规则提示。结果仍为 review_required，不是法律裁决，但会抹去可选分支，误导风险展示。
- 依据：SPDX Annex D.4.2 的 OR 表示选择，D.4.3 的 AND 表示同时要求；WITH 和括号也有独立语义。来源：https://spdx.github.io/spdx-spec/v2.3/SPDX-license-expressions/
- 方案：建立受限、版本化的表达式语法树；AND 聚合必需分支，OR 保留备选分支及尚未选择状态，不能自动替用户选择许可。无法处理的复合表达式先降级为有明确原因的复核结果，而不是展开为全部义务。
- 验收：同样的MIT/GPL输入，AND和OR须输出不同的分支结构；覆盖嵌套、优先级、WITH和未选择分支，保证风险摘要不把备选GPL提示当成必然义务。

### R2：标准化与规则覆盖不一致，部分覆盖会静默遗漏（优先修复）

- 位置：`backend/app/licenses/spdx.py:17`、`backend/app/rules/engine.py:216`。
- 复现：AGPL-3.0-only有规则，却得到空normalized_ids和pending；LGPL-3.0-only、CDDL-1.0可标准化却没有规则；`MIT AND CDDL-1.0`只返回MIT提示，没有缺少CDDL规则的诊断。
- 根因：别名字典、规则库独立维护；引擎只在一个规则都没匹配时才报告覆盖不足。
- 方案：维护已批准的支持矩阵和数据版本，分别标记“合法SPDX”“能标准化”“有评估规则”，不要混为一谈；补AGPL映射，对每个必须评估的叶节点计算未覆盖集合，输出coverage诊断，不以一个分支成功代表全表达式已评估。LGPL/CDDL是否纳入当前产品范围须明确，范围外也应有可见限制。
- 验收：三集合的一致性CI检查；纯未知、完全覆盖、部分覆盖分别测试；不删除已覆盖分支，也不隐藏未覆盖分支。

### R3：证据完整性和表达式一致性检查不足（优先修复）

- 位置：`backend/app/rules/engine.py:194`、`backend/app/domain/models.py:412`。
- 复现A：LicenseExpression引用两个Evidence，调用evaluate只提供其中一个已verified的Evidence，仍触发MIT规则。列表推导式先丢掉不存在的引用，再检查剩余证据，缺失信息被吞掉。
- 复现B：通过LicenseExpression.model_validate构造expression为GPL-3.0-only、normalized_ids为MIT的对象，evaluate仍触发MIT规则。领域校验只检查字符/ID格式，不校验两字段语义一致性。
- 边界：完整ScanRun有引用存在性校验，能拦住部分缺证据输入；A为独立evaluate接口的防御缺口，不能直接称为所有生产路径均可绕过。B即使通过LicenseExpression校验仍成立。
- 方案：evaluate显式检查全部必需引用可解析，缺失时失败关闭或返回明确unknown；从唯一可信解析结果导出normalized_ids，输入不一致时拒绝或降级。不得仅因文件哈希正确就把许可真实性或授权认定为已核验。
- 验收：缺一条/全部缺失/重复ID/混合pending和verified/表达式与ID矛盾均有反例测试；再验证完整ScanRun入口。

### R4：共享许可证对象导致聚合ID冲突（优先修复）

- 位置：`backend/app/rules/engine.py:230`与集成版`backend/app/pipeline/license_rules.py:66`。
- 复现：构造通过ScanRun.model_validate的两个Component，共享一个verified LicenseExpression，apply_license_rules抛出license_rule_state_conflict。
- 根因：Obligation ID只含license ID、rule ID/version和证据，不含资源；每个资源分别evaluate生成相同义务对象，聚合层却拒绝任何重复ID。
- 方案：按现有Obligation归属许可证的契约，优先将内容完全一致的义务按ID去重，保留资源各自的RiskFinding和Remediation；相同ID但不同内容仍必须报冲突。若改为资源级义务，须先完成契约审查，再调整ID，不直接改冻结Schema。
- 验收：两个资源共享一条许可得到一份共享义务、两份资源发现及各自整改；真实内容冲突仍失败，不能笼统关闭重复检查。

### R5：语法支持有限，模糊GPL别名却过度确定

- 位置：`backend/app/licenses/spdx.py:26`、`:40`。
- 复现：括号、WITH、GPL-3.0-or-later都变为pending；`GPL 3.0`反而直接变为GPL-3.0-only，在提供verified证据时状态也为verified。
- 影响：合法表达式失去可评估性；模糊文本没有说明only还是or-later时，现有映射选择了更具体的含义。人工确认文本存在并不必然确认版本选择。
- 方案：区分严格SPDX解析与宽松候选提取；保留原文和歧义原因。没有充分版本证据时不自动决定only/or-later；语法合法但规则不支持时输出“不支持”，不能混称“证据待核验”。复用经评估的成熟解析库，锁定库及SPDX数据版本后登记依赖；本轮不安装。
- 验收：only/or-later/加号、WITH、括号、LicenseRef、非法表达式、模糊别名分别测试；保持unknown而不猜测是允许的保守行为，但应标出具体原因。

### R6：规则缺少官方依据与人工审核元数据

- 位置：`rules/README.md`与`backend/app/rules/engine.py:109`、`rules/license-obligations.yaml`。
- 事实：README要求官方来源、版本、人工复核状态；执行数据只有id/version/license_ids/severity/title/obligation/remediation，加载器还严格拒绝额外字段。结果中的待复核状态不能替代规则自身的审核来源。
- 方案：经契约审查增加source_url、section、原文快照digest、来源版本、审核状态/日期和维护责任等字段；建立“规则→原文条款→测试→审核记录”映射。未复核规则保留提醒或禁用确定性义务；不能由模型代签。每次内容改变同步规则版本和回归。
- 验收：15条规则都有可解析来源与明确审核状态；缺来源的新增规则不能通过发布检查。法律语义仍需有资格的人工核验，本轮不作法律结论。

### R7：触发前提仅是文案，尚无场景判定

- 位置：`backend/app/rules/engine.py:202`、`:233`。规则trigger被复制到输出，不参与条件计算；evaluate没有分发、修改、网络提供服务等场景输入。
- 影响：同一许可在不同使用场景产生相同的提示等级。目前全部输出review_required是安全边界，不应改成自动pass，但也不能宣传为已经判断适用义务。CC0/Unlicense中的来源留档属于项目策略提醒，应与许可强制义务分开标识。
- 方案：将规则区分为许可义务、内部策略和待核实事实；按需增加三态场景上下文（已知是/否/未知）。没有事实时仅提出条件性提醒；有明确不适用证据时标注不适用，而非删掉证据。固定confidence=0.8不能宣传为经过校准的准确率。
- 验收：同一许可证的场景是/否/未知，分别产生适用/不适用/待核验提示；不得从代码依赖存在直接推断实际分发。

### R8：逐规则测试覆盖被高估

- 位置：`tests/fixtures/license-rules/cases.json`、`tests/unit/test_b5_license_rule_engine.py`。
- 实测：15条规则，verified_cases只有6条，缺9条逐规则正例。当前分支与已获取集成版该fixture文件无差异。另有“规则数等于15”测试，但它不等价于15条规则都完成行为验收。
- 方案：补齐逐规则正例及未核验/缺失/不适用反例，再补R1至R5的跨模块输入；CI强制规则ID集合等于fixture覆盖集合。人工规则审核与自动fixture通过分别记录，不能互相替代。
- 验收：15条规则100%具备约定fixture，表达式与数据门槛探针纳入固定回归，Linux容器中的完整链路另验。

## 本轮执行与限制

- 当前分支：`test_b5_license_rule_engine.py`为10 passed；`test_b4_b6_b7_extensions.py`为5 passed，其中包含B6/B7，不能称为15条许可测试。
- 集成副本：B5与A4纯逻辑回归17 passed、1 deselected；显式排除persists用例，本轮未复验Windows持久化/容器端到端。
- 内存探针复现R1至R5；模型不一致及缺引用使用model_validate复验；共享许可通过完整ScanRun校验后再调用集成器。现有测试全绿不覆盖这些额外探针。
- Python显式虚拟环境路径本轮可运行3.12.10；普通python命令不可用，不能把之前环境失败继续当成本轮运行结果。未安装、重装或修复运行时。
- 官网核对SPDX表达式语义；不评判每条法律文本完整正确性。用户已提供的一名真人AI辅助标签确认不是15条许可规则原文审核。

## 建议实施顺序

1. Terra修R3输入一致性、R4聚合；Luna建立失败回归，Sol审查共享义务语义。
2. Terra与Sol确定R1/R2/R5表达式及支持矩阵，先保守降级再补完整解析。
3. Sol与真人维护R6/R7来源和场景语义；Luna补R8固定回归。
4. Root验收固定版本的CLI/规则/容器/报告链路后，按用户授权与暂存区规则发布。当前没有实施修复，不能标记问题已关闭。
