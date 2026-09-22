# P1 后端 B 工作包总览

本文整理 P1 Frozen Contract 定义的 B01–B07。它是实施与验收索引，
不替代 [Frozen Contract](../spec/p1-workspace-contract.md)，也不新增公共 API、
Schema 或法律/授权结论。

## 责任边界

后端 B 的职责是从已经受限的输入、固定样本和人工治理材料中产生可追溯的**候选事实**：
解析、检测、许可证/NOTICE事实、Bench artifact、Gold/FN 治理和性能记录。

后端 B 不负责网络传输、默认应用工厂、sidecar 持久化、公共 API、Formal Assessment/Task、
不可变 NoticeDraft/Report Snapshot、前端页面、生产发布或独立验收。它们分别由 A/Root、
xzb、Luna 和 Sol 的既定职责处理。

| 工作包 | 当前本地状态 | 已有交付 | 关闭条件 |
|---|---|---|---|
| B01 Resource Profile parser | 已实现、待独立/生产验收 | Hugging Face model/dataset 离线 parser、5+5 固定快照、3反例 | A 显式接线；Luna 在授权环境复验真实观察；Sol 审核语义 |
| B02 Detector | 已实现并完成本地 Python 验收 | 从 B03/B04 v2 facts 导出 17 个 review 候选、0 obligation | Luna 独立篡改复验；新 P1 revision 消费候选；不能直接变 Formal Finding |
| B03 License relation facts | 已实现演示集 | v2 许可证观察强度、关系状态、来源/选中值 hash | 扩展为经批准的真实库存；人工核验适用性 |
| B04 NOTICE facts | 已实现演示集 | NOTICE/版权/gap 事实及 evidence 闭包 | A 将冻结 facts 转为 NoticeDraft；Luna 重启/异机验收 |
| B05 Bench | development 输入集已实现，尚无真实执行 | Bench 2.0 Java Schema、库、离线 CLI 与 detector 输入/prediction/result 固定 artifact | 生成带真实预测/结果 artifact 的评测 revision，并经 B06 Gold 治理后才可请求高等级 |
| B06 Gold / FN 治理 | 规范已具备，未执行 | 公开语料、双人复核、holdout、amendment 与 FN/FP taxonomy | 人工 Gold、争议关闭、冻结 hash、独立复核回执 |
| B07 性能 | 未开始实测 | 只有目标与测量边界 | 固定语料、运行配置、分位数/失败率原始回执 |

## 已验证链路

```text
固定 Hugging Face 快照 ──> B01 受限解析
                                 │
B03/B04 固定 facts ───────────> B02 review 候选 ──> A 的冻结绑定（后续）
                                 │
Bench artifact / Gold / 性能回执 ─> B05 / B06 / B07（独立后续）
```

- B01 只输出 `ParsedMetadataObservation`，许可证声明与授权保持 `pending`；详见
  [B01 parser](b01-huggingface-metadata-parser.md)。
- B02 只输出内部 `LicenseNoticeCandidateSet`。gap 和 provider 声明均为
  `review_required`，不构成违规或合规结论；详见
  [B02 detector](../spec/b-p1-02-license-notice-facts-detector.md)。
- B03/B04 v2 facts 的正式许可证表达式始终为空；详见
  [B03/B04 facts](../spec/b-p1-03-license-relations-and-b04-notice-facts.md)。
- B05 的 manifest 校验并不执行评测、不生成 Gold；详见
  [B05 Bench](../spec/b-p1-05-bench-2-manifest.md)。

## 本地验收口径

| 范围 | 命令或检查 | 当前结果 |
|---|---|---|
| B01 | parser unit/security | 32/32，语句覆盖率 87% |
| B02 | detector unit/security | 16/16，语句覆盖率 85% |
| B03/B04/B02 固定链 | Node 固定 facts 与候选预期 | 7/7 |
| B05 | Maven Bench/NOTICE 定向 | 19/19（既有回执） |

这些均是离线、本地、固定输入的结果；不能替代真实资源、真人复核、跨平台或生产验收。

## 后续顺序与责任人

1. Root/环境负责人修复隔离 Python 依赖环境，确保 `h11==0.16.0` 等锁定依赖可复现；
   再运行 B01/B02/metadata transport 联合回归。
2. Luna 独立复验 B01/B02 的篡改、离线、重启和跨平台边界；真实 Hugging Face 观察必须在
   获授权环境执行，且不能改写固定 fixture。
3. Sol 审核 B01/B02/B03/B04 的 `pending`、gap 和原始许可证声明语义，批准可纳入新
   P1 integration revision 的事实范围。
4. A/Root 完成 opt-in factory、metadata sidecar 与候选到 NoticeDraft/Profile/Report 的
   不可变绑定；失败时必须保持 feature disabled。
5. B 线建立带固定 artifact 的 B05 评测 revision，完成 B06 真人 Gold/FN 治理，再以
   固定配置执行 B07 性能测量。
6. xzb 在 A 的公共接口和快照语义冻结后实现 Profile/NOTICE 页面与浏览器验收。

## 不可跨越的门禁

- `gated=false`、公开可读、provider license、成功抓取或存在 SHA 都不是授权证明。
- 不得把 B02 candidate 直接写为 Formal Finding、Obligation 或 Report 结论。
- 固定 fixture 仅代表采集时刻；远端当前响应只能形成新的观察回执。
- B05–B07 未有原始 artifact、人工记录或测量回执时，不得报告准确率、召回率、F1、性能或
  真人审查完成度。

## 2026-09-23 状态更正（AMENDMENT）

本节优先于本文件中较早的状态快照：B01 `resource-profile-v2` 已是 5 model + 5 dataset，具有 4 类反例；B02 已有固定 candidate matrix；B03/B04 已扩展为 v3 离线库存及已许可 archive 观察（仍非 NOTICE 原文或许可证适用性结论）；B05 是 Gold 未冻结时的 smoke 运行准备；B06 有双人盲审/分歧/amendment 工具但没有实际双人 Gold；B07 已有受控 receipt 汇总器但没有真实性能结论。所有结论仍以当前 revision、Hash、独立验收和人工治理为准。
