# GitHub 三人协作方案

## 2026-09-06 分支归并

将450b8eb累计验收链通过保留历史的merge PR汇入integration/p0，main仍等待P0里程碑。保留main、integration/p0、fix/a2-scanner-file-boundary、codex/p0-external-tools-sync、feat/xzb-frontend和feat/a5-ollama-transport；开放PR #1/#2暂保留。其余41个历史分支仅在头未变化且已完整包含于合并结果后清理。merge保留原提交，避免squash使Evidence提交丢失祖先关系；不改仓库设置。

异机继续固定450b8ebe3381a6a27ca333ed78c9a7ad572ba65b。以后复用integration/p0作为开发入口，任务合入后清理历史分支，不为发布记录反复开新分支。清理不删除提交历史；本文件末尾登记恢复SHA。实际结果以PR与远端refs核对为准。

## 仓库目标

GitHub 仓库用于三名成员共享代码、通过 Pull Request 审查变更，并为竞赛形成可核验的提交、测试和开放成果记录。

三个 Codex 开发对话还必须通过 `docs/coordination/AGENT_WORKLOG.md` 共享状态：每次开工先完整阅读并登记 START，每次结束追加完成/部分完成/阻塞报告。该日志是跨对话交接的事实来源，不允许模型只依赖各自聊天历史。

竞赛规则允许参赛阶段因知识产权、隐私或第三方许可限制采用私有仓库；晋级总决赛的作品原则上应提供公开成果或明确开放计划。无论仓库公开或私有，都不得提交无权再分发内容、访问凭据、个人信息或商业秘密。

## 推荐权限

- 仓库负责人：`Admin`；
- 两位团队成员：`Write`；
- 不授予不必要的 `Admin` 权限；
- 评审或临时协作者按需使用 `Read`/`Triage`，结束后复核权限。

## 推荐仓库设置

### General

- 默认分支：`main`；
- `integration/p0` 作为当前团队开发集成入口；成员从它创建一个短生命周期任务分支，并通过 Pull Request 合回 `integration/p0`；
- `main` 只接收通过完整里程碑验收的 `integration/p0` Pull Request，不直接承接日常功能提交；
- 合并方式保留 `Squash merging`，关闭不需要的合并方式以保持历史清晰；
- 合并后自动删除 head branch；
- Issues 开启，用于缺陷和任务追踪；
- Discussions 可暂不开启，避免维护负担。

### Branch protection / Rulesets

对 `main` 建立规则：

- 必须通过 Pull Request；
- 至少 1 位成员批准；
- 新提交后旧批准失效；
- 所有讨论解决后才能合并；
- 启用必需状态检查后，要求测试通过；
- 禁止 force push；
- 禁止删除 `main`；
- 负责人也遵守规则，紧急修复需留下可核验记录。

对 `integration/p0` 建立较轻量规则：禁止 force push和删除，要求 Pull Request、解决讨论，并在状态检查稳定后要求后端测试与前端构建通过。组员现有分支在本人完成迁移前保留；Root 只清理已经被 `integration/p0` 完整包含且没有独有提交的项目负责人历史任务分支。

### Security

- 启用 Dependabot alerts；
- 启用 Dependabot security updates；
- 启用 secret scanning 和 push protection（GitHub 账户/仓库支持时）；
- 不在 Actions、Issue、PR、Wiki 或 Release 中粘贴真实密钥；
- Actions 权限采用最小权限，默认只读，按工作流单独提升。

## 三人工作分配建议

- 架构/规则负责人：维护 Schema、ADR、评测规范和最终审查；
- 主线工程负责人：维护后端、前端、部署和跨模块集成；
- 测试/材料负责人：维护 fixtures、Bench、第三方资源台账和材料检查。

文件所有权不替代相互审查。跨模块接口变更必须在 PR 中说明迁移影响、测试和回滚方法。

## 许可证与开放边界

仓库公开前，三名成员应共同确认：

1. 团队对自主代码拥有公开授权；
2. 指导教师、学校、实验室或其他单位不存在未披露权属争议；
3. 第三方代码、模型、数据和素材允许当前使用及公开方式；
4. 仓库根目录包含团队选择的 `LICENSE`；
5. `NOTICE` 和第三方资源清单满足实际依赖义务；
6. 需要专利或保密保护的内容已完成必要措施或从公开仓库排除。

选择许可证属于团队的权利决定。建议在理解署名、专利授权、衍生作品和再分发义务后，由三名成员共同确认；不要仅因为其他项目使用某许可证就机械复制。

## 首次推送前检查

- 删除或忽略 `.DS_Store`、缓存、构建产物、模型权重和本地数据库；
- 搜索密钥、令牌、邮箱、个人信息和本机绝对路径；
- 检查提交者姓名和邮箱是否是成员希望公开的身份；
- 检查共享工作日志是否记录本次任务的开始、结果、测试和未完成项；
- 确认 README、LICENSE、SECURITY、CONTRIBUTING 和第三方资源说明；
- 运行基础测试；
- 先查看 `git status` 和待提交文件，再创建首个提交。

| Historical branch | Preserved commit |
|---|---|
| docs/a3-a4-durable-zip-spec | `16cd7d4865a27a6a6401e8b629e0d13ae592be32` |
| docs/a7-browser-download-handoff | `15b12eca42522a0dd0e1180ed7fedfe0842836c3` |
| docs/a8-runtime-resource-audit | `079b14c7917ef791015ef9cbbf851e220021f29b` |
| docs/p0-first-product-gap-check | `d640ef4dafc77ccb2b5cd52468973e4c244e3c37` |
| feat/a2-public-git-egress | `280ad02e309483fecc428d23b44041f253ab7781` |
| feat/a2-readonly-scan-session | `9b70ba6de88812d9228ee85e3a28c54710bd22be` |
| feat/a2-zip-cli-demo | `33cd336eebbee3cdda714cddc5f2c36a0fbfce9e` |
| feat/a2-zip-ingestion | `693c7c4797a5e39c8e1d33e438e2d6819851db6a` |
| feat/a3-durable-scan-registry | `7ca289de4dfe644856f09afc099da4e73e0a55f7` |
| feat/a3-durable-zip-storage | `2368d91120a72e7bb474ddacfcb72743b9aa02b1` |
| feat/a3-fastapi-api | `37b25c140efcdad2e9bd47c6fe6e89713a6f41a5` |
| feat/a3-zip-background-scan | `dcebda71f2d63e0ff46b90d1721b86b4d2a817ac` |
| feat/a3-zip-dispatcher-recovery | `5679113088f980b5ec73f385679348a064df24af` |
| feat/a4-ai-asset-report | `6ac399817f2753547285b8a7cfa82d8ae5f9fa9d` |
| feat/a4-b5-rule-integration | `048c16787dbb213a9dd2c9af76bb5be2bd3e4e83` |
| feat/a4-local-zip-pipeline | `bce04fe0ca89665894b6221e0894efdd35f2b1be` |
| feat/a4-pipeline-worker | `ed91e34dcecf056656d0a4b3e40d5b1ddd8840bc` |
| feat/a4-real-zip-scanners | `6a832f3300ab0752d724b7dd4e1105ff818f40a8` |
| feat/a4-zip-license-report | `8318f883cc8cd3d1e6c44ba650c4c6eb04f3c91a` |
| feat/a5-ai-provider | `ee700d9b94e1d2cce86ade22ff0020a10849076a` |
| feat/a5-pipeline-integration | `1ba14aff6894aabdd25f4491688df5d7b852e95a` |
| feat/a6-download-csp-fix | `d9a6aca60a6924a394b2345c684f35b3047afe13` |
| feat/a6-pipeline-publish | `ec57e57273652b0a21feba3f4d53ab4064255f3c` |
| feat/a6-report-delivery | `6de6671fe211dad99c28606833a245a8a9a70674` |
| feat/a6-report-export-core | `682c9ed146cf4a5122e6adf9c4d6230fc11062b9` |
| feat/a7-minimal-compose | `2dc451d901f59ff055faa0826f82c015af3ee189` |
| feat/a7-public-git-deploy-acceptance | `341dc348670a558fae35d699b204e4d927f898fb` |
| feat/a7-public-zip-qwen-acceptance | `be1b4f43a7fcec3e5b2c424065b119270f64a458` |
| feat/a7-simple-web | `a1a710f8c05d7830b745f8f5b2f3b201ec95bd1c` |
| feat/a8-scanner-bench-acceptance | `0dcca3947bdd942fa5b308e3f856a305abe61983` |
| feat/b1-js-manifest-p0-cli | `3985385c7e2aef6ccd6e9b2f0570519cbdbf95f6` |
| feat/b1-p0-mapper-cli | `380b896cf2b3e0efa4f1f39a450d36f2f32bdfa7` |
| feat/b1-python-manifest-parser | `d57ea4033a41f2e45334a8011dc866445dd4496f` |
| feat/p0-domain-contract | `1d77a511c23391fc77ee651dd6387a45a0ddb1b1` |
| feat/s0-s2-design-gates | `0b7e4b72f734a39c126c1c6f387868837d9a5c24` |
| fix/a2-nofile-limit | `780536bdf47ed55d8e6c228b284344e46f36f16e` |
| fix/a2-scanner-no-network | `d38f897616ade0d933a4e8274a6173d5a67479ff` |
| fix/a2-workspace-disk-limit | `872b2f1b46fbca30529fd5c6142c88fc69ed2e6a` |
| fix/a7-api-cpu-limit | `1d11d0192c3ef421b098a324e47e6dae2923a5cc` |
| fix/a7-api-python-lock | `1b5bb6bb9f680d138f313fd80d8362955b1533f3` |
| fix/a7-debian-git-pin | `39d062ab20acb949a3d7f9b5eb7dbe52520d92c5` |
