# B-P1-02 License/NOTICE facts detector

本说明是 [P1 Frozen Contract](p1-workspace-contract.md) 的后端 B 实施补充，不新增公共 API、公共 Schema 或第二份权威 Contract。

## 1. 输入与输出

`app.detectors.license_notice_facts.detect_license_notice_candidates` 只接收已经加载的 `openguard.notice-license-facts/2` 对象，以及调用方从不可变 manifest/fixture 固定的 `expected_package_sha256`。Hash 使用稳定 UTF-8 canonical JSON 复算；调用方不得对已修改的输入现场重算 Hash 后把它当作原包。detector 不读路径、文件、数据库或网络，也不执行外部程序。

输出是确定性 `LicenseNoticeCandidateSet`：分别包含 Finding 与 Obligation 候选。每个 Finding 固定包含候选 ID、来源 fact ID、资源 canonical ID、候选类别/代码、facts JSON Pointer、fact canonical SHA-256、整个 facts package canonical SHA-256，以及上下文 Evidence 的对象 Pointer、source/container/selected-content SHA-256 与原始 selected JSON Pointer。状态恒为 `review_required`、`authorization_status=pending`，正式许可证表达式为空，`confirmed_violation=false`。

候选只能表达以下两类需复核事实：

- facts 中已经存在的 gap；
- `relationships.license.state=declared_unverified` 的 provider 许可证声明。

当前 v2 输入没有“已验证且确定适用的许可证表达式”，所以 Obligation 候选必须为空。detector 不产生 Formal Finding、正式 Obligation、Assessment、Task、NoticeDraft 或 Report V2 Snapshot；A/Root 仍负责在冻结 Scan/Assessment Binding 下消费候选。

## 2. 保守规则

- `gap` 始终映射为 `review_required`，不是违规、违约或不合规结论；
- provider 声明仅映射为 `LICENSE_DECLARATION_UNVERIFIED`，不做 SPDX 标准化，不提升授权；
- 输入中不是 `pending` 的 authorization、任何非空正式 expression、悬空 Evidence、重复 fact/gap、未知对象字段、Evidence Hash/Pointer 结构异常、Report row 与 fact 不闭包、策略被提升或 package Hash 不匹配均 fail-closed；
- 候选顺序与 ID 仅由输入事实决定，重复运行不依赖时钟、网络或进程状态。

## 3. P1 固定联验关系

P1 v1 仍固定引用 B03/B04 v1 facts，保证旧 commit/hash 可复现；本 detector 面向已版本化的 v2 facts，不能静默回写或替换 P1 v1。迁移应建立新的 P1 integration revision，重算其 manifest、source hash 和预期结果。

当前 v2 样本应导出 17 个 Finding 候选、0 个 Obligation 候选：14 个既有 gap 加 3 个 provider 声明未验证候选。固定预期见 `tests/fixtures/p1-integration-b-v1/expected.json`。这个数字只是固定样本断言，不是生产检测率、Bench 分数或法律结论。

## 4. 验收

- unit：v2 事实的固定候选数、稳定性、Evidence Pointer/Hash闭包、保守状态、未知结构与输入篡改拒绝；
- security：无网络/子进程能力、NOTICE缺失不升级为违规；
- Node：固定预期的 source package canonical Hash、Finding代码分布、0 Obligation和保守语义；
- B05 Bench、B06 真人 Gold/FN 与 B07 性能仍需各自独立的 artifact、治理和实测，不由本模块伪造。
