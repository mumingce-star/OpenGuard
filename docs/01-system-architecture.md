# 系统架构与模块边界

## 1. 技术栈建议

- 前端：React、TypeScript、Vite、ECharts 或 React Flow；
- 后端：Python 3.12、FastAPI、Pydantic；
- 数据：SQLite（比赛版），保留 PostgreSQL 迁移接口；
- 扫描：ScanCode Toolkit、Syft；
- 规则：版本化 YAML/JSON 规则库；
- AI：本地 Qwen3 小参数模型，通过 Ollama 调用；
- 报告：Jinja2 HTML、JSON、CSV，最终按需生成 PDF；
- 测试：pytest、Playwright、固定扫描样例；
- 部署：Docker Compose，本地单机运行。

Sol、Terra、Luna 用于辅助研发，不作为参赛产品默认运行时模型。产品默认采用开放权重模型，以强化“AI+开源”的主题一致性。

## 2. 后端模块

### ingestion

- 接受公开仓库 URL、ZIP 或本地目录；
- 限制文件大小、文件数量和扫描时长；
- 使用浅克隆，不执行目标仓库代码；
- 生成不可变文件清单和内容摘要。

### scanners

- `scancode_adapter`：许可证文本、文件头、版权和包元数据；
- `syft_adapter`：依赖和 SBOM；
- `manifest_parser`：解析 pyproject、requirements、package.json、lockfile；
- `ai_asset_parser`：识别 Hugging Face 模型、数据集、API 和外部服务；
- `evidence_collector`：保存路径、行号、字段、URL 和原始片段。

### normalization

统一为以下核心对象：

- Project
- Component
- AIAsset
- Evidence
- LicenseExpression
- Obligation
- RiskFinding
- Remediation
- ScanRun

### license_knowledge

- 同步 SPDX License List；
- 记录 OSI 认证状态；
- 保存许可证原文 URL 和版本；
- 维护 15 种常见许可证义务规则；
- 支持未知许可证与自定义 LicenseRef。

### risk_engine

第一版规则：

- 缺少许可证；
- 许可证声明互相冲突；
- 需要署名但未发现署名；
- Apache-2.0 NOTICE 义务待核查；
- Copyleft 组件再分发义务待核查；
- AGPL 网络服务源代码提供义务待核查；
- 模型或数据集许可证缺失；
- 自定义许可证未被识别；
- 资源可访问但没有明确再利用授权；
- 外部 API 服务条款未登记。

输出必须区分：`pass`、`warning`、`review_required`、`unknown`，不输出法律裁决。

### ai_assistant

AI 仅用于：

- 从非结构化 README、Model Card、Dataset Card 抽取候选字段；
- 对规则结果生成通俗解释；
- 根据证据生成整改步骤；
- 草拟第三方资源清单和 NOTICE；
- 对未知条款提出“需要人工核查”的问题清单。

所有结构化输出必须通过 JSON Schema 校验；许可证 ID、文件路径和义务必须能关联证据。AI 不得覆盖确定性扫描结果。

### reporting

- 项目概览；
- 组件和 AI 资源图谱；
- 许可证分布；
- 风险清单和证据；
- 整改建议；
- 自动生成的第三方资源使用清单；
- JSON、CSV、HTML 导出；
- 扫描环境、工具版本和时间戳。

## 3. 前端页面

1. 新建扫描：仓库 URL、ZIP、本地目录；
2. 扫描进度：阶段、耗时、错误和工具版本；
3. 总览仪表盘：资源数量、许可证、风险等级；
4. 资源图谱：代码包、模型、数据集、API 及关系；
5. 风险详情：证据、许可证原文链接、规则和整改建议；
6. 资源清单编辑：人工确认和导出；
7. 基准评测：版本间指标和错误案例；
8. 项目设置：模型、超时、隐私和免责声明。

## 4. 安全边界

- 不执行、编译或安装目标仓库代码；
- 扫描进程设置 CPU、内存、时间和磁盘限制；
- 拒绝路径穿越、压缩炸弹和超大文件；
- 不持久保存用户上传项目，默认扫描后清理；
- 日志自动脱敏令牌、密钥和个人信息；
- 网络访问使用域名白名单并设置超时；
- 报告不包含完整许可证受限材料或访问凭据。

## 5. MVP 与延后项

MVP 支持 Python 和 JavaScript/TypeScript；常见 15 种许可证；公开仓库、ZIP 和本地目录；HTML/JSON/资源清单导出。

延后：企业账户、私有仓库 OAuth、漏洞扫描、恶意代码检测、全部许可证兼容矩阵、自动法律结论、分布式任务队列。
