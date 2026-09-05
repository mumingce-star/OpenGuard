# OpenGuard 开源合规助手

参赛方向：AI 开发工具与开源协作

目标：对公开代码仓库或本地项目进行代码依赖、开源模型、数据集和第三方服务的统一盘点，生成带证据的许可证风险提示、整改建议和《开源及第三方资源使用清单》。

> 产品定位是“合规信息整理与风险提示工具”，不提供法律意见，不替代许可证原文核验或专业法律审查。

## 当前可运行状态（2026-09-05）

现在已经可以独立跑通六层真实扫描底座纵切：**本地 ZIP → 安全校验与临时物化 → 文件级 SHA-256 inventory → 稳定 JSON**，**生命周期绑定只读会话 → Python/JavaScript manifest**，**声明与 npm lock v2/v3 → P0 `Component`/`Evidence`**，**Python/JavaScript 两种稳定依赖 JSON CLI**，**显式本地 ZIP Pipeline → durable P0 依赖聚合**，以及 **ZIP multipart HTTP 创建 → 进程内后台 A4-1 → 状态/资源/证据查询**。解析器只按 inventory 白名单读取小文件，读取结束后能力立即失效；这些流程不会联网、不会执行 ZIP 中的代码，也不会安装其中的依赖。

任务主线还已具备 SQLite durable `ScanRun` 注册表、六路由 FastAPI API，以及显式七阶段 A4-0 Pipeline Worker。A4-1 已把 A2 与既有 Python/JavaScript 依赖解析公共接口接到该 worker；A3-2 接入 ZIP multipart，A2-3a 又接入需管理员显式启用的公开 HTTPS Git。两种输入都能通过 BackgroundTask 执行依赖纵切并持久化组件、证据、摘要及四种报告链接。A4-2 已原样消费组员 B5 的 15 条证据门控许可证规则；当 `ScanRun` 已含有效许可证事实时，规则阶段可生成并持久化义务、风险与确定性整改。当前 ZIP/Git 依赖路径尚未产生 B2/B3/B4 许可证事实，因此真实输入仍诚实终止为 `partial/rules/70`、错误码 `rules_stage_not_connected`。这里的 `partial` 表示“依赖结果可用，许可证事实尚未进入规则阶段”，不是输入或依赖扫描失败；AI 主链接线和持久 worker 仍未完成。

A2-3a 不执行 checkout，而是让固定 Git 通过任务级 TrustedEgress CONNECT 代理获取浅克隆对象；代理逐连接用固定 TLS DoH 解析、拒绝任一非公网地址并立即拨号已验证 IP，Git 自己继续完成端到端 TLS/SNI。随后只用 `ls-tree`/`cat-file` 把普通 blob 流式写入受控目录并生成 revision/inventory。公开 Git 默认关闭，设置 `OPENGUARD_ENABLE_PUBLIC_GIT=1` 后才启用；团队仓库默认分支当前没有受支持 manifest，会在 A2 成功后诚实停为 `failed/scan/35`，真实纵切演示使用官方 PyPA sampleproject。

A5-0 还提供了可独立调用的 local/remote AI Provider 边界：给定已有 `RiskFinding`、`Evidence`
和绑定的许可证事实，它能把严格 JSON 提升为待人工复核的 P0 `Remediation`；关闭、异常、超限、
身份/证据不匹配时保留确定性结果并稳定降级。A5-1a 已增加只访问字面量回环地址、禁用环境代理、
核验固定运行时/模型/完整摘要并共享总超时的 Ollama HTTP transport。A5-1b 已在本机验证官方
Ollama `0.33.3` 与锁定 Qwen3 模型：manifest/blob 摘要一致，真实结构化推理 3/3 成功，冷轮约
4.34 秒、热轮约 2.73 秒，候选整改保持 `pending` 且不改变确定性事实。transport 尚未接入 ZIP
Pipeline，因此当前 Web 扫描仍不会自动产生 AI 建议。

A6-0 已提供确定性报告导出核心：对一个已验证的 `completed` 或 `partial` `ScanRun`，可生成稳定
JSON、竞赛七字段 UTF-8 CSV/资源清单和安全静态 HTML。A6-1 可把这些产物以私有权限、内容
SHA-256 和原子 metadata 提交持久化，生成 P0 `ReportLink`，并通过冻结的报告 GET 路径只读下载。
A6-2 已把 publisher 接到 Pipeline 首次终态提交边界：ZIP HTTP 主链现在会把四种报告链接与
`partial/rules/70` 在同一次 SQLite CAS 中公开，报告可在后端重启后继续下载。阶段性报告不会补写
缺失的许可证、风险或 AI 建议；GET 不现场生成报告，也不修改 SQLite。前端仍未接真实下载。

当前还不是完整参赛成品：ZIP 与公开 Git 已能把声明的 Python 依赖，以及根 `package.json` 与 `package-lock.json` v2/v3 的直接 npm 依赖映射为 P0 对象，但尚不代表依赖已安装/完整解析；B5 规则虽然已接入 A4，却仍需 B2/B3/B4 把真实许可证事实送入主链后才能对真实输入给出风险提示。本地目录输入、其他 lockfile、AI 主链接线、前端真实 API/下载接线、Linux 隔离、持久队列和 Bench 仍需按进度台账继续实现。评委最终看到的产品形态仍是下文定义的本地 Web 应用。

团队集成分支 `integration/p0` 还汇合了前端组员的 React/Vite 应用壳，以及扫描组员的 ScanCode/Syft 受限 JSON Adapter 候选。前端已通过锁文件安装和生产构建，但仍使用 mock；外部工具 Adapter 已通过本机 JSON 单测，但尚未接入当前 ZIP 主链或完成本机真实工具回归。两者均不得外推为完整 Web 或外部扫描器能力。

使用 Python 3.12 环境，在项目根目录运行：

```bash
PYTHONPATH=backend python -m app.cli ./your-project.zip
PYTHONPATH=backend python -m app.cli --python-dependencies ./your-project.zip
PYTHONPATH=backend python -m app.cli --javascript-dependencies ./your-project.zip
PYTHONPATH=backend python -m pytest -q tests/unit/test_b1_javascript_manifest_p0_cli.py tests/security/test_b1_javascript_manifest_p0_cli_independent.py
PYTHONPATH=backend python -m pytest -q tests/unit/test_b1_python_p0_mapper_cli.py tests/security/test_b1_python_p0_mapper_cli_independent.py
PYTHONPATH=backend python -m pytest -q tests/unit/test_b1_python_manifest_parser.py tests/security/test_b1_python_manifest_parser_independent.py
PYTHONPATH=backend python -m pytest -q tests/unit/test_a4_local_zip_pipeline.py tests/security/test_a4_local_zip_pipeline_independent.py
PYTHONPATH=backend python -m pytest -q tests/unit/test_a4_b5_rule_integration.py tests/unit/test_b5_license_rule_engine.py
PYTHONPATH=backend python -m pytest -q tests/unit/test_a3_zip_background_scan.py tests/security/test_a3_zip_background_scan_independent.py -k 'not real_uvicorn'
PYTHONPATH=backend python -m pytest -q tests/unit/test_a5_ai_provider.py tests/security/test_a5_ai_provider_independent.py
PYTHONPATH=backend python -m pytest -q tests/unit/test_a5_ollama_transport.py tests/security/test_a5_ollama_transport_independent.py
PYTHONPATH=backend python -m pytest -q tests/unit/test_a6_report_exports.py tests/unit/test_a6_report_delivery.py tests/unit/test_a6_pipeline_publish.py tests/unit/test_a3_fastapi_api.py
PYTHONPATH=backend python -m pytest -q tests/unit/test_a2_public_git_ingestion.py
OPENGUARD_RUN_LOOPBACK_TESTS=1 OPENGUARD_PUBLIC_GIT_TEST_URL=https://github.com/pypa/sampleproject.git PYTHONPATH=backend python -m pytest -q tests/security/test_a2_public_git_trusted_egress_integration.py
PYTHONPATH=backend python -m app.ai.runtime_probe ./your-scan-run-without-remediation.json --runs 3 --timeout-seconds 60
PYTHONPATH=backend python -m pytest -q
```

前三条命令分别输出 inventory、Python 依赖和 JavaScript 直接依赖的 P0 JSON；安全拒绝、输入错误、只读会话/parser/mapper/Pipeline/ZIP HTTP/A5/A6/公开 Git 用法和退出码说明见 [backend/README.md](backend/README.md)。随后命令分别复现 JavaScript、Python mapper、Python parser、本地 ZIP Pipeline、ZIP HTTP 后台纵切、A5 Provider、Ollama transport、A6 报告、A2-3a 离线安全门禁、显式授权的公开 Git 纵切与真实模型聚合探针。A2-3a 受控完整集合为 `872 passed, 1 warning`。系统 Python 不是 3.12 时，应先创建或选择 Python 3.12 虚拟环境；不要用修改项目版本约束的方式绕过环境要求。公开 Git 测试会访问操作者明确指定的仓库；真实模型探针要求本机已按锁定版本启动 Ollama。

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
- P0 开发期统一以 `integration/p0` 为团队基线，每位成员同时只维护一个短任务分支；历史任务分支的证据由提交哈希和进度台账追踪，不再作为日常入口；
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
