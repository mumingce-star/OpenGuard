# Contributing to OpenGuard

感谢参与 OpenGuard。当前仓库由三人竞赛团队共同维护，所有成员遵循同一套可追溯开发流程。

## 分支约定

- `main`：始终保持可运行，只通过 Pull Request 合并；
- `integration/p0`：当前 P0 团队集成入口；短分支从这里创建并通过 Pull Request 回到这里，里程碑验收后再由 `integration/p0` 向 `main` 提交 PR；
- `feat/<short-name>`：新功能；
- `fix/<short-name>`：缺陷修复；
- `docs/<short-name>`：文档和材料；
- `test/<short-name>`：测试、夹具和基准数据。

分支名使用小写英文、数字和连字符，不在分支名中写学校、成员姓名或敏感信息。

## 日常流程

1. P0 开发期从最新 `integration/p0` 创建短生命周期分支；里程碑发布才以 `main` 为目标；
2. 开工前阅读 `AGENTS.md` 和完整共享工作日志，追加 `START` 记录；
3. 每次提交只处理一个逻辑主题；
4. 收工前追加 `COMPLETE`、`PARTIAL` 或 `BLOCKED` 报告；
5. 推送分支并创建 Pull Request；
6. 在 PR 中填写变更、验证、第三方资源和 AI 辅助情况；
7. 至少由另一位成员审查；
8. 所有必需检查通过后合并；
9. 合并后删除远程功能分支。

不要继续从历史 `feat/*` 任务分支串行派生新功能。旧任务分支的提交哈希和 evidence 继续保留在 Git 历史与进度台账中，团队日常只需要关注 `main`、`integration/p0` 和自己当前的一个短分支。

## 提交信息

推荐使用 Conventional Commits：

```text
feat(scanner): add Python manifest parser
fix(security): reject zip path traversal
test(rules): add Apache-2.0 NOTICE fixtures
docs(report): record benchmark methodology
```

允许的常见类型：`feat`、`fix`、`test`、`docs`、`refactor`、`build`、`chore`。

## Pull Request 门禁

提交 PR 前必须确认：

- 代码能够运行，相关测试已经执行；
- 新功能或规则包含测试或可复现样例；
- 每个风险结论可以关联证据；
- 没有执行或安装被扫描项目的代码；
- 没有提交密钥、令牌、个人信息、学校信息或本机绝对路径；
- 新增第三方组件已登记版本、来源、许可证/授权和使用方式；
- AI 生成代码或文本已经人工审核并记录验证方法；
- 已更新 `docs/coordination/AGENT_WORKLOG.md`；
- 报告数据、截图和指标没有被手工编造。

## 第三方资源

首次引入依赖、模型、数据、素材、工具或服务时，同步更新 `third_party/` 台账。公开可访问不代表允许复制、训练、改编或再分发；无法确认授权时标记为“待核验”，不要把资源内容提交到仓库。

## 安全问题

不要在公开 Issue 中披露可被利用的安全缺陷、密钥或个人数据。请先按照 [SECURITY.md](SECURITY.md) 中的团队内流程处理。
