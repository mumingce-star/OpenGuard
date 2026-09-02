# OpenGuard 开源合规助手

参赛方向：AI 开发工具与开源协作

目标：对公开代码仓库或本地项目进行代码依赖、开源模型、数据集和第三方服务的统一盘点，生成带证据的许可证风险提示、整改建议和《开源及第三方资源使用清单》。

> 产品定位是“合规信息整理与风险提示工具”，不提供法律意见，不替代许可证原文核验或专业法律审查。

## 当前可运行状态（2026-09-02）

现在已经可以独立跑通第一条真实纵切：**本地 ZIP → 安全校验与临时物化 → 文件级 SHA-256 inventory → 稳定 JSON**。这条演示不会联网、不会执行 ZIP 中的代码，也不会安装其中的依赖。

当前还不是完整参赛成品：Web 界面、公开 Git/本地目录输入、Python/JavaScript 依赖识别、许可证规则、AI 解释、报告导出和 Bench 仍需按进度台账继续实现。评委最终看到的产品形态仍是下文定义的本地 Web 应用。

使用 Python 3.12 环境，在项目根目录运行：

```bash
PYTHONPATH=backend python -m app.cli ./your-project.zip
PYTHONPATH=backend python -m pytest -q
```

第一条命令成功时输出 JSON；安全拒绝、输入错误和退出码说明见 [backend/README.md](backend/README.md)。第二条命令用于复现当前自动测试。系统 Python 不是 3.12 时，应先创建或选择 Python 3.12 虚拟环境；不要用修改项目版本约束的方式绕过环境要求。

## 竞赛交付定义

在 2026-10-15 20:00 前形成：

- 可本地部署的完整 Web 应用；
- Python 与 JavaScript/TypeScript 项目扫描能力；
- 代码依赖、模型、数据集、第三方 API 四类资源图谱；
- 15 种常见许可证的结构化义务与风险规则；
- 确定性扫描、规则判断和 AI 辅助解释的证据链；
- HTML、JSON 和参赛资源清单报告；
- OpenGuard-Bench 评测集及评测脚本；
- 公开代码、规则、测试、文档和部署说明；
- 技术报告、3-5 分钟演示视频和佐证材料。

## 总体数据流

```text
仓库 URL / ZIP / 本地目录
          |
          v
安全获取与文件清单
          |
          +--> ScanCode：文件许可证、版权、包信息
          +--> Syft：软件依赖与 SBOM
          +--> 自研解析器：模型、数据集、API、素材引用
          |
          v
统一资源模型 + 来源证据
          |
          +--> SPDX/OSI 标准化
          +--> 自研许可证义务规则引擎
          +--> AI 条款抽取与整改说明（必须引用证据）
          |
          v
风险图谱 / 修复建议 / 第三方资源清单 / 报告
          |
          v
OpenGuard-Bench 自动评测
```

## 项目目录

```text
OpenGuard/
├── README.md
├── backend/                 # API、扫描编排、规则引擎、AI、报告
├── frontend/                # 扫描任务、资源图谱、风险和报告界面
├── rules/                   # 许可证义务与风险规则
├── benchmarks/              # 合成样例、人工标注真值和评测脚本
├── docs/                    # 竞赛、架构、资源、模型与计划文档
├── tests/                   # 单元、集成、端到端及安全测试
├── deploy/                  # Docker Compose 与本地部署
└── third_party/             # 第三方资源台账，不存放无权再分发内容
```

## 协作开发

- 所有 Codex 模型开始和结束任务时必须遵守 [AGENTS.md](AGENTS.md)，并读写 [共享工作日志](docs/coordination/AGENT_WORKLOG.md)；
- 当前完成项、未完成项、责任模型和 GitHub 发布状态统一维护在 [项目进度台账](docs/coordination/PROJECT_PROGRESS.md)；
- 贡献流程与 Pull Request 要求见 [CONTRIBUTING.md](CONTRIBUTING.md)；
- 安全问题处理见 [SECURITY.md](SECURITY.md)；
- 三人 GitHub 权限、分支保护和开放边界见 [docs/06-github-collaboration.md](docs/06-github-collaboration.md)；
- 第三方资源在首次引入时登记，不在提交前集中补录；
- `main` 保持可运行，功能开发通过短分支和 Pull Request 合并。
- 每个验收通过的任务点由 Root Coordinator 统一整理、提交并推送到 GitHub，只上传最终竞赛作品所需内容。

## 评委验收门槛

作品进入材料制作阶段前必须满足：

1. 从输入仓库到报告导出可以一次跑通；
2. 每条风险都能回溯到文件、字段或官方许可证文本；
3. AI 失败时，确定性扫描和规则结果仍然可用；
4. 对基准集输出准确率、召回率、人工修正率和耗时；
5. 开放仓库具有 LICENSE、NOTICE、第三方资源清单、测试和部署说明；
6. 演示材料不出现学校名称、学校 LOGO 或指导教师信息；
7. 仓库和报告中不包含账号密码、API 密钥或无权再分发资源。

## 设计原则

- 先证据，后结论；
- 规则引擎负责确定性义务，AI 负责抽取、解释和建议；
- 不执行被扫描项目的代码，不安装其依赖；
- 对未知、自定义或冲突授权输出“不确定”，禁止猜测；
- 所有第三方组件在引入当天登记版本、来源和许可证；
- 每个功能必须有测试或可复现案例。

## License

OpenGuard 的团队自主代码和文档采用 [Apache License 2.0](LICENSE) 开放。第三方软件、模型、数据、素材和服务仍分别受其自身许可证、授权条款或服务条款约束；本仓库的许可证不会改变第三方内容原有权利归属。
