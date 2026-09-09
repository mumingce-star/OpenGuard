# A5-0 AI Provider 与确定性降级规格

状态：冻结 v1（Sol，2026-09-04）

2026-09-09 定向修订（P0 外部契约不变）：Ollama 优先采用内部 `resource_batch_mode`，按来源情境、版本是否已记录、许可状态及规则分批，每批最多16条，逐项提供真实资源、版本、规则、许可来源、覆盖限制及证据摘录，不复用旧报告答案。模型生成对应资源证据情境的许可核验重点；程序另外整理扫描事实、证据位置和查找步骤，在原 summary/steps 内明确标注来源。页面将模型解释与程序事实导航分开展示。此模式替代“共享三步等于逐资源解释”的生产路径；旧共享模式和普通 Provider 的单条协议仍保留兼容测试。

没有对应来源情境的通用句、串用情境、未知英文标识或版本、模型生成 URL、危险断言、结构错误均拒绝。有效成员可保留，失败成员不附加 AI Remediation，整次返回 degraded 并经原计划保留 partial。引用仍绑定原 Finding，不把另一资源的证据给当前风险。许可来源的额外摘录仅用于分析，不扩展当前风险可输出的引用集合。

每条最多读取3条风险证据和3条额外许可摘录，每段180字符；这不是完整文件阅读。原始全部 Evidence、Risk、报告都保留。批请求超过24000字节时明确降级，不增大8192上下文或1024输出token预算、不重试生成。批次身份包含原始上下文及模型与提示摘要；传输只提取共同字段并省略无语义的哈希字符串，不删证据片段。固定 Flask 的60秒为验收目标，并非所有仓库的时间保证或新增执行限额。上述内容校验是有限门禁，不能替代人对解释的语义和可执行性复核。

2026-09-07 性能修订：Ollama 的可选 `review_plan_mode=True` 对无义务的 `license-evidence-gate` 同类上下文生成共享核验流程，细节见 `a5-ollama-transport.md` 最新修订。外部模型不新增字段；每项风险仍有自己的 pending Remediation 和 Evidence 关联，明确标记共享建议、未逐项确认许可。失败只影响相应上下文，保留其他成功建议并返回 degraded；不具备该能力的 Provider 仍保留本文原整批撤回语义。禁止把固定模板标为模型生成结果；固定摘要只表达既有不确定性，三条实际行动必须来自通过校验的模型响应。

生产 Git/ZIP 共用的 dependency plan 在报告阶段检查持久错误；AI错误、有界覆盖或解析不完整均保留原错误并收敛为partial，不再仅因为后续步骤返回就标completed。通用worker仍尊重调用方提供的plan；此修复位于真实生产计划，不改其状态契约。
范围：项目负责人 A5/S4 的最小可执行纵切
依赖：P0 contract `0.1.1`、既有 `RiskFinding` / `Evidence` / `LicenseExpression` / `Remediation` / `ScanRun`

## 1. 目标与非目标

A5-0 为本地或远程模型实现提供同一注入接口，并把模型返回值收敛成严格、可审计的 P0
`Remediation`。AI 只解释既有风险和生成待人工复核的整改步骤；确定性扫描、许可证标准化和风险
规则始终是事实来源。

本纵切不实现 Ollama/HTTP 客户端、重试器、模型下载、提示模板调优、README/Model Card 候选
抽取、许可证规则、AI 资源检测、报告或前端。真实 Qwen3 + Ollama 运行时和 A4 接线属于 A5-1。

## 2. 角色与所有权

- Sol：冻结本文的输入、输出、错误和证据边界。
- Terra：只实现 `backend/app/ai/` 和实现侧单元测试，不改变 P0/Schema/API。
- Luna：只新增独立可靠性与安全测试，不修改实现或规则语义。
- Root：复核不可变事实、全量回归、证据绑定与 GitHub 发布。

B4/B5 许可证知识/规则和 B6 AI 资源检测属于扫描分析组员，本轮不得实现、修补或用占位结论替代。

## 3. Provider 接口

Provider 由调用方注入，必须暴露：

- `mode`：精确为 `local` 或 `remote`，仅描述传输部署类型；
- `producer`：合法的 P0 `ProducerRef(type=ai)`，完整记录 `provider`、锁定 `model_id` 和
  `prompt_schema_digest`；
- `generate(payload, timeout_seconds)`：接收 UTF-8 canonical JSON 字符串，返回 UTF-8 JSON
  字符串。

A5-0 不信任 Provider 实现。接口不得接收或记录 API key、绝对路径、原始仓库对象或可执行目标
代码；网络、认证、进程和真正的 timeout 强制由 A5-1 transport 负责。

## 4. 输入快照

每次请求只针对一条尚无整改建议的 `warning`、`review_required` 或 `unknown` finding。canonical
输入包含：

1. 固定 schema/version 与语言；
2. finding 的完整只读 P0 快照；
3. finding 已引用的 Evidence 快照；
4. 与 finding 资源已绑定的 LicenseExpression 快照及其 Evidence；
5. 明确禁止新增/改写 package、resource、path、license、obligation、rule、outcome 或 severity。

允许引用集合是请求中实际提供的 evidence ID 集合。输入缺失引用、P0 聚合本身无效或 Provider
身份非法时，调用在模型执行前失败关闭。

## 5. 严格输出

Provider 每次必须返回一个 JSON object，且只允许以下字段：

- `schema_version`：固定 `openguard.ai-remediation/v1`；
- `finding_id`：必须与请求完全一致；
- `summary`：1..1000 字符；
- `steps`：1..8 项，每项非空且不超过 1000 字符；
- `evidence_ids`：1..32 项，去重后仍非空，且全部属于允许引用集合。

拒绝额外字段、重复 JSON key、非 UTF-8/非对象、空/截断 JSON、NaN/Infinity、超过 64 KiB 的
响应、未知 evidence、错误 finding 身份、敏感凭据片段或绝对路径片段。输出 Schema 刻意不包含
事实字段，因此模型没有可被提升为许可证、规则、资源或风险事实的通道。

## 6. 提升为 P0 Remediation

全部响应先完成解析、结构化校验和跨引用校验，之后才能原子写入：

- `Remediation.generated_by` 使用 Provider 的 AI `ProducerRef`；
- `verification_status` 固定 `pending`，AI 无权提升为 `verified`；
- `finding_id` 与 evidence 引用保持校验后的原值；
- ID 使用固定 namespace 对 finding ID、Provider 身份、prompt Schema 摘要和 canonical 输出做
  UUIDv5，确保相同输入关键字段稳定；
- 同时只更新原 finding 的 `remediation_id`、追加 remediation，并在 provenance 记录 AI producer；
- components、AI assets、licenses、evidence、obligations、finding 的 outcome/severity/rule/trigger/
  description、summary 统计和报告链接必须逐值保持不变。

对一批 finding 的处理是原子的：任一 Provider 调用或响应校验失败，不发布部分 AI 建议。

## 7. 降级语义

稳定状态为：

- `generated`：至少一条有效建议已提升；
- `skipped`：没有符合条件且未绑定 remediation 的 finding，完全不调用 Provider；
- `disabled`：AI 显式关闭，保留确定性结果并在 provenance 标记 `ai_enabled=false`；
- `degraded`：Provider 不可用、超时、抛错或输出无效，丢弃整批候选并保留确定性结果。

`disabled` 不添加错误。`degraded` 只允许追加一条稳定、脱敏、可恢复的 `ScanError`，stage 固定
`ai_assist`，错误码不得包含 Provider 原始异常；同时在 provenance 记录本次尝试的 AI producer。
除该 provenance/error 诊断外，输入 ScanRun 的确定性对象和统计必须不变。失败不得把
`unknown` 改成 `pass`，也不得阻止后续基础报告生成或使一个已完成的确定性主链变为 failed。

## 8. 稳定错误码

- `ai_invalid_argument`：调用方输入、Provider 元数据或配置非法；抛出内部边界异常；
- `ai_provider_unavailable`：Provider 调用失败或超时；结果为 `degraded`；
- `ai_response_invalid`：响应解析、Schema、引用或内容门禁失败；结果为 `degraded`。

用户可见消息必须固定且不含响应正文、异常文本、路径、URL 参数或凭据。

## 9. A5-0 验收矩阵

实现侧至少覆盖：

- 有效响应生成 pending Remediation、稳定 ID 和完整 AI ProducerRef；
- 只选择 eligible/unbound findings，零候选不调用 Provider；
- local/remote 使用同一接口；
- AI disabled 时确定性结果逐值保留；
- Provider 抛错与无效 JSON 稳定降级且不发布部分建议；
- 额外字段、重复 key、错 finding、未知 evidence、空/超长字段、响应超限被拒；
- 输入事实与 summary 不被 AI 输出修改；
- 相同输入与输出关键字段生成相同 remediation ID。

Luna 独立测试至少补充路径/凭据泄漏、截断/非有限 JSON、批处理第二项失败的原子性、AI 关闭
消融和 P0 聚合重新校验。A5-0 只有在定向测试、全量后端回归、P0 Schema 等值、compileall、
diff 与敏感信息门禁都通过后，才能标为完成；这些结果仍不证明真实 Ollama/Qwen3、网络隔离、
许可证正确性、报告或完整参赛产品。


## 2026-09-09 V2：默认组级共同指导

本节替代上一轮默认逐资源补写。`domain/grouping.py` 在生成前形成等价情境：规则/版本/触发、判断与原等级、资源类型、规范化许可和验证状态、证据充分性、声明位置、版本记录是否存在、实际用途未知、义务与扫描范围限制。具体成员名称/版本值/ID/摘录不送入共同指导提示；它们完整保留于原事实和每条自身 Evidence 绑定中。相同背景允许共享，不声称模型逐一审阅。

每个有证据组最多尝试一次，不将失败扩成逐成员调用；失败保留原降级。内部短输出为 summary、三步 locate/source/record、limitations，经结构、文本安全、无授权推断检查再绑定。规则判断/许可/等级/证据不允许 AI 改写。保持原本地模型/token/单次时间预算。

进程内 LRU 最多128份共同指导，键覆盖 provider mode、ProducerRef模型配置与提示摘要、完整情境、提示/输出Schema和投影版本。输出禁止成员名、数量、URL与个体证据，因此成员变化可以复用共同指导，始终重新绑定各成员自己的引用。缓存非持久、重启不保留；无缓存不是故障。真实日志 `group_ai_metrics` 分开记录原发现数/情境组/需AI组/缓存/请求/重试/成功组/成员关联/实际耗时。成员关联数量绝非独立审查次数。
