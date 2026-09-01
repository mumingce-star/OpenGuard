# Sol、Terra、Luna 研发路由

该表描述 Codex/开发助手的分工。参赛产品默认运行 Qwen3 等开放权重模型；如果产品使用 OpenAI API，必须另行登记服务条款、费用、密钥管理和第三方服务依赖。

## 思考程度定义

- `none/low`：格式化、机械改写、简单脚手架和小修复；
- `medium`：常规编码、测试和文档；
- `high`：跨模块设计、复杂调试和评测；
- `xhigh`：高风险架构、规则逻辑、系统审查；
- `max`：关键决策、最终质量门禁和难以回滚的问题，少量使用。

## 模块级分工

| 工作模块 | 主模型与思考程度 | 复核模型 | 理由 |
|---|---|---|---|
| 竞赛需求、评分拆解 | Sol `xhigh` | Sol `max` 最终审查 | 直接影响整个参赛路线 |
| 总体架构和领域模型 | Sol `xhigh` | Terra `high` 做可实现性检查 | 需要跨模块一致性 |
| 安全边界和威胁模型 | Sol `xhigh` | Sol `max` 里程碑审计 | 涉及不可信仓库和敏感信息 |
| 许可证义务数据结构 | Sol `xhigh` | 人工核验许可证原文 | 高风险逻辑，不允许模型独立裁决 |
| 许可证规则实现 | Terra `high` | Sol `xhigh` | Terra 高效编码，Sol 审逻辑漏洞 |
| ScanCode/Syft 适配器 | Terra `high` | Sol `high` | 外部工具集成和异常处理 |
| Python/JS manifest 解析 | Terra `medium` | Luna `medium` 批量补测试 | 规则明确、样例多 |
| 模型/数据/API 检测器 | Terra `high` | Sol `high` | 需要跨格式抽取与误报控制 |
| 统一资源图谱 | Sol `high` 设计，Terra `high` 实现 | Sol `high` | 数据关系会影响全系统 |
| AI 提示词和 JSON Schema | Sol `high` | Terra `medium` 回归测试 | 需要可靠、可验证输出 |
| AI 整改解释 | Terra `high` | Sol `high` 抽检高风险样例 | 内容生成量较大但要守边界 |
| 后端 API 和任务编排 | Terra `high` | Sol `high` | 日常主力开发 |
| 数据库和迁移 | Terra `medium` | Luna `medium` 生成边界测试 | 常规工程工作 |
| 前端信息架构 | Sol `high` | Terra `high` | 评委需要快速理解证据链 |
| 前端页面实现 | Terra `high` | Luna `medium` 做细节修复 | 兼顾质量与速度 |
| 报告和资源清单导出 | Terra `medium` | Luna `medium` 批量格式验证 | 输出结构明确 |
| 基准集设计和指标 | Sol `xhigh` | Terra `high` | 决定可验证效果的 25 分 |
| 合成测试夹具 | Luna `medium` | Terra `medium` 抽检 | 批量、重复、低风险 |
| 单元测试 | Luna `medium` | Terra `medium` | 高吞吐生成后人工/主模型复核 |
| 集成与端到端测试 | Terra `high` | Sol `high` | 跨模块失败定位复杂 |
| 性能、错误和消融分析 | Sol `high` | Terra `high` | 需要严谨解释结果 |
| README、API 文档 | Luna `medium` 初稿 | Terra `medium` | 可批量生成但需事实核对 |
| 第三方资源台账 | Luna `low` 整理 | Terra `high` 核对版本/许可 | 机械整理与合规判断分离 |
| 技术报告初稿 | Terra `high` | Sol `xhigh` | Terra 组织材料，Sol 站在评委角度删改 |
| 演示视频脚本 | Terra `high` | Sol `high` | 兼顾叙事和技术证据 |
| 提交前全量审计 | Sol `max` | 人工逐项确认 | 最后质量门禁 |

## 调用原则

1. 默认 Terra `medium/high`，不要把所有任务都交给 Sol；
2. Luna 适合生成批量样例，但不能单独决定许可证义务或最终风险；
3. Sol 用在一次错误会导致返工、失分或一票否决的节点；
4. 每个模型生成的代码都必须运行测试和人工审查；
5. 在 `docs/05-ai-assistance-log.md` 记录 AI 用途、人工修改与验证方式；
6. `max` 仅用于架构冻结、规则冻结和提交前审计。
