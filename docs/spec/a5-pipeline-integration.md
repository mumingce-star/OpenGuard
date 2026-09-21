# A5-1c Pipeline AI_ASSIST 接线规格

状态：已验证并发布 v1（Root/Astra→Luna→Root，2026-09-05；实现证据 `3237ab0`）

范围：项目负责人 A5/A4 集成；只消费扫描分析组员 B5 公共输出，不修改规则语义

## 1. 目标与边界

共享 dependency plan 的 `AI_ASSIST/85` 阶段调用既有
`apply_ai_remediations()`。AI 只处理 B5 已生成、结果为 `warning`、
`review_required` 或 `unknown` 且尚未绑定整改的 finding；B5 已生成的确定性整改保持原样，
不得由 AI 覆盖或重复生成。

本任务不实现许可证发现、SPDX 标准化、B5 规则、模型/数据/API 检测、前端、持久任务队列或
部署。当前 ZIP/Git 路径没有 B2/B3/B4 许可证事实时仍在 `rules/70` 诚实终止，不能仅因 A5
已接线而声称真实仓库的许可证 AI 分析已跑通。

## 2. 配置与执行

- 默认 `OPENGUARD_ENABLE_AI=0`，不需要 Provider、不调用模型，并记录 `ai_enabled=false`；
- 只有精确设置 `OPENGUARD_ENABLE_AI=1` 才由默认应用注入已锁定的本机
  `OllamaProvider`，其他值启动失败；
- ZIP 与公开 Git runtime 把同一显式 Provider、开关和有界 timeout 传入各自的一次性计划；
- 默认总 timeout 继续使用 A5-0 的 10 秒，不在本纵切新增重试或静默切换模型；
- Provider 缺失、开关或 timeout 非法属于调用方配置错误，在计划建立前失败。

## 3. 成功、跳过与降级

- `generated`：只追加 `verification_status=pending` 的 P0 `Remediation`，并把其 ID 绑定到
  原 finding；事实、证据、规则结果和统计逐值保持；
- `skipped`：B5 finding 已有确定性整改或没有符合条件的 finding，不执行生成；
- `disabled`：保持确定性结果并明确 AI 关闭；
- `degraded`：Provider 不可用或响应无效时不发布任何候选建议，保留 B5 结果，只追加一条脱敏、
  可恢复的 `ai_assist` 错误，并继续 REPORT 与 A6 四格式发布。

`degraded` 不等于许可证规则失败。报告必须显示真实错误和缺失的 AI 建议，不得把未知或待复核
结论改写成通过。

## 4. 验收

实现侧必须覆盖：

1. 默认关闭且 Provider 零生成调用；
2. B5 pending evidence-gate finding 生成待人工复核整改，并保持事实/引用；
3. B5 已有确定性整改时 AI 不重复生成；
4. Provider 失败后 SQLite 仍提交规则结果，A6 四格式报告仍可下载且无原始异常泄漏；
5. ZIP/Git 两种 source-specific plan 均传递相同 A5 配置；
6. 默认应用只接受 `OPENGUARD_ENABLE_AI=0/1`；
7. A4/A5/A6/API/P0 回归、Schema 等值、compileall、diff、敏感信息与上传范围门禁通过。

本纵切的独立证据只能证明已有 B5 finding 的 A5 Pipeline 行为。上游真实许可证事实、更多项目的
模型效果、Bench、Linux 隔离、持久 worker、前端接线与完整竞赛作品仍需单独验收。
