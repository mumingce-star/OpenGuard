# 后端 B 收口与跨线依赖清单

更新时间：2026-09-22（Asia/Shanghai）
适用基线：`codex/scan-reliability-integration@9d67b88`、P1 Contract V1。
定位：这是协作执行清单，不替代冻结的 [P1 契约](../spec/p1-workspace-contract.md)，不新增公共 Schema、HTTP API 或授权/许可证结论。

## 结论

后端 B 的可自主实现部分 B01--B05 已有可复现工件；B06、B07 的剩余门禁分别依赖真人 Gold 治理和受控运行环境，不能由 B 用合成数据、AI 标注或文档替代。以下输入到齐前，B 不应把开发输入升级为正式指标，也不应向 P0/P1 事实或报告写入未经 A 线固定的内容。

| 工作包 | B 已交付 | 仍未关闭 | 可由 B 立即做的事 | 阻塞方 |
| --- | --- | --- | --- | --- |
| B01 Resource Profile | HF 离线解析器、2 模型+2数据集 v2 snapshots、Hash/来源质量/反例门禁 | 真实 transport、5+5 覆盖、不可变消费 | 仅维护离线 parser 与 regression | A 提供 transport/sidecar；真人复核来源 |
| B02 Detector | License/NOTICE 候选 detector，保持 `pending`/`review_required` | 更大事实覆盖、真实结果回流 | 对固定 facts 追加正反例；不改变公共语义 | A 提供固定 scan/facts 输入 |
| B03 License 关系 | facts v2/v3 的来源、证据和 gap | 上游原文、人工适用性判断 | 扩充已获授权的离线事实 | 真人权利复核 |
| B04 NOTICE | NOTICE/copyright 事实与缺口候选 | 原文、资源关系、人工确认 | 输出事实和缺失原因，不生成正文 | A 固定 NoticeDraft；真人核验 |
| B05 Bench | development detector 输入、hash/来源索引校验 | 真正预测/结果、冻结 Gold、独立评审 | 准备可审计运行适配器与错误分类入口 | B06、A 的固定运行入口 |
| B06 FN/FP | taxonomy、标注 SOP、盲审/复核辅助脚本 | 真人 Gold、争议裁决、匹配策略批准 | 校验提交物完整性；不替真人标注 | 两名真人 + Sol/Root |
| B07 性能 | 隔离 Pipeline profiler | 多次实测 receipt、环境摘要、性能分布 | 汇总 receipt、计算分位数并检查漂移 | A/Terra 的受控 POSIX 运行环境 |

## 后端 A 必须提供的帮助

这些项目是 B 的前置输入；B 收到后只消费固定版本，不写回扫描主链或替换历史对象。

| 优先级 | A 交付物 | 最小内容 | B 的消费与验收 |
| --- | --- | --- | --- |
| A-1 | 不可变 scan/facts 读取入口 | 固定 `scan_id`、`facts_hash`、`registry_revision`、终态、脱敏 Evidence 定位；未知/partial 明确保留 | B02/B03/B04 生成或复核候选事实；输入哈希不匹配即拒绝 |
| A-2 | Metadata sidecar 与显式 refresh job | 受控 transport、provider/kind/identity/revision、body SHA、容量/超时/错误码、只读查询；GET 不隐式联网 | B01 只解析 bounded bytes，返回 observation/gap；不得保存 raw payload |
| A-3 | NoticeDraft 不可变快照接口 | 固定 ScanRef、AssessmentRef、facts hash、entry/证据集合、draft hash；创建与读取分离 | B04 事实可被引用；B 不直接写 Draft、不把 license expression 代替原文 |
| A-4 | Bench 受控执行入口 | 固定 detector/config/revision、输入 artifact hash、隔离工作目录、结构化 result/receipt；禁止目标代码执行 | B05 在 Gold freeze 后写入 prediction/result，并将异常/partial 分开统计 |
| A-5 | POSIX 性能运行位 | 锁定 scanner runtime、工具版本、CPU/内存限制、冷/热状态说明、无活动任务；可运行 `benchmarks/profile_scan.py` | B07 收集至少多次 receipt，报告中仅使用实测分位数与失败率 |
| A-6 | P1 报告绑定 | Report V2 创建时固定 profile/notice/task/graph 的内容 hash，拒绝 latest 引用 | B 交付事实、Gold 与结果引用；不生成权威报告快照 |

### A 的回执格式

每次交付必须提供：`producer/version`、`scan_id` 或 job ID、输入/输出 SHA-256、实际 UTC 时间、配置摘要、已知 coverage gap、失败码、可复现命令和不包含敏感内容的结果路径。缺少其中任一项，B 只能标为 `development` 或 `review_required`。

## 前端必须提供的帮助

前端不承担 B 的事实判断，但须保证用户所见状态与后端不确定性语义一致。

| 优先级 | 前端交付物 | 最小交互/字段 | B 的验收关注点 |
| --- | --- | --- | --- |
| F-1 | Profile 展示与刷新状态 | canonical ID、revision、字段 locator、`pending`、coverage gaps、refresh job 状态；不展示为“已授权” | B01 观察可追溯，缺失/冲突不被隐藏 |
| F-2 | NOTICE 事实与草稿区分 | 原文证据/缺失原因、资源关系、NoticeDraft snapshot ID/hash；许可证候选与正文分栏 | B04 不会被 UI 降格为许可证字符串 |
| F-3 | Detector/Bench 结果页 | 输入/配置/预测/Gold/结果 artifact hash、tier、失败与不确定数 | development 必须显著标识；没有 Gold 时不显示 Precision/Recall/F1 |
| F-4 | 人工 Gold 复核页 | 阶段隔离、本人草稿/提交、分歧、裁决、冻结版本；服务端保证而非 CSS 隐藏 | B06 的盲审记录和 exposure 可核验，禁止 AI 充当第二真人 |
| F-5 | 性能与报告页 | receipt 运行环境、样本数、p50/p95/失败率、范围说明；报告引用固定快照 | B07 不将单次耗时或前端加载时间冒充 Pipeline 性能 |
| F-6 | 浏览器验收回执 | 成功、失败、刷新、网络中断、权限/阶段隔离的截图或脱敏 HAR；对应 build/revision | B 可将 UI 反馈映射回事实/API/展示缺陷，不直接改 UI |

## 联调顺序与 DoD

```text
A-1/A-2 固定事实与 metadata 生命周期
  -> B01--B04 产生或复核受限事实
  -> A-3 固定 NoticeDraft / A-6 固定 Report 绑定
  -> F-1/F-2 真实展示与浏览器回执
  -> 两名真人完成 B06 Gold freeze
  -> A-4 运行固定 detector
  -> B05 生成结果 + B06 分类 FN/FP
  -> A-5 受控 POSIX 多次性能运行 + B07 汇总
  -> F-3/F-4/F-5 展示并形成端到端回执
```

达到“B 可交接”至少需要：

1. B01--B04 每条事实都有来源、Hash、locator、producer 与不确定性状态；
2. B05 的 prediction/result 都绑定冻结输入、检测器版本与配置，且 Gold 先于运行冻结；
3. B06 至少两名真人独立标注、暴露声明、分歧处理与裁决签收齐全；
4. B07 有多次实际 receipt、环境描述、失败样本与分位数计算，不能由计划值或单次运行替代；
5. A 的快照/报告与 F 的界面均引用固定 hash，而非 latest；
6. 浏览器和异机/受控环境回执证明状态、错误与 partial 语义未被改变。

## 明确禁止

- 用 B01 fixture、`gated=false`、存在 license 字段或公开 URL 推导授权、再分发权或许可证适用性；
- 用开发集、合成 case、AI 草稿或单人自报代替正式 Gold/FN/FP；
- 通过删除失败样本、模糊 partial、替换历史 hash 或重写 gold 来提高指标；
- B 直接接入生产 API、写 NoticeDraft/Report/Assessment，或前端通过文案掩盖 `pending`/`review_required`；
- 在 Windows 上绕过 Git/ZIP 的 POSIX 安全门禁来制造“全链通过”结果。
