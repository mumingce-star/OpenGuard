# 代码、数据与资料清单

引入任何资源前都要核对固定版本仓库中的 LICENSE/NOTICE；下表许可证仅作为选型预期，最终以实际锁定版本为准。

## 核心扫描与标准

| 资源 | 用途 | 预期许可证/状态 | 官方来源 | 动作 |
|---|---|---|---|---|
| ScanCode Toolkit | 文件许可证、版权、包信息 | 引入前核验 | https://github.com/aboutcode-org/scancode-toolkit | 必需 |
| Syft | 依赖与 SBOM | Apache-2.0 | https://github.com/anchore/syft | 必需 |
| SPDX License List Data | 许可证 ID、文本、例外 | 引入前核验 | https://github.com/spdx/license-list-data | 必需 |
| SPDX Specification | 许可证表达式与 SBOM 标准 | 标准资料 | https://spdx.github.io/spdx-spec/ | 必需 |
| OSI License API | OSI 认证状态 | 官方接口 | https://opensource.org/licenses/ | 推荐 |
| CycloneDX ML-BOM | 模型物料清单参考 | 标准资料 | https://cyclonedx.org/ | 推荐 |
| Hugging Face Hub API | 模型/数据卡元数据 | 服务条款需登记 | https://huggingface.co/docs/huggingface_hub/ | 必需 |

## 运行时与应用框架

| 资源 | 用途 | 预期许可证 | 动作 |
|---|---|---|---|
| Python 3.12 | 后端运行时 | PSF | 必需 |
| FastAPI | HTTP API | MIT | 必需 |
| Pydantic | 数据校验 | MIT | 必需 |
| SQLAlchemy | 数据访问 | MIT | 推荐 |
| Jinja2 | HTML 报告模板 | BSD-3-Clause | 必需 |
| RapidFuzz | 名称和文本匹配 | MIT | 可选 |
| Qwen3-4B-Instruct-2507 Q4_K_M | 本地整改解释；锁定 Ollama tag `qwen3:4b-instruct-2507-q4_K_M`、manifest `sha256:0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0` | Apache-2.0；[Qwen 模型卡](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)、[Ollama 模型页](https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M)；2026-09-04 已下载到本机私有缓存，manifest 与 2497280480-byte blob 完整摘要均重算一致；不进入仓库 | 必需 |
| Ollama v0.33.3 | 本机回环模型服务；[固定 release](https://github.com/ollama/ollama/releases/tag/v0.33.3)、[macOS 安装说明](https://docs.ollama.com/macos) | MIT；上游 LICENSE 已核验；2026-09-04 官方 DMG 的大小/完整 SHA-256、Developer ID、Gatekeeper、公证、arm64 和安装后版本均通过 | 推荐 |
| React | 前端框架 | MIT | 必需 |
| TypeScript | 前端语言 | Apache-2.0 | 必需 |
| Vite | 构建工具 | MIT | 必需 |
| ECharts | 仪表盘与图表 | Apache-2.0 | 推荐 |
| React Flow | 资源关系图 | 按锁定版本核验 | 推荐 |
| pytest | 单元与集成测试 | MIT | 必需 |
| Playwright | 端到端测试 | Apache-2.0 | 推荐 |
| Docker Compose | 一键部署 | 按发行版本核验 | 必需 |
| Git `2.50.1 (Apple Git-155)` | A2-3a 公开 HTTPS 浅克隆与对象读取；当前仅本机 profile，最终 Linux 包版本/摘要待 A7 锁定 | GPL-2.0-only；[官方来源](https://git-scm.com/downloads)，随镜像分发时履行许可证与源码义务 | 必需 |
| Cloudflare 1.1.1.1 DoH | A2-3a 固定 TLS DNS 解析；只查询仓库主机名，不发送路径/代码/凭据 | 外部服务条款/隐私适用；[官方 wireformat 文档](https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/make-api-requests/dns-wireformat/)；最终部署前复核 | 当前 profile 必需 |

A5-1a 把上述身份固化进 transport、文档和测试；A5-1b 在用户授权后完成本机安装、约 2.5GB
权重下载和真实推理。3 次同一合法输入为 `3/3`，冷轮 4344.062 ms，热轮 2736.214/2723.574 ms；
运行时报告模型加载约 3.175 GB、100% GPU、context 4096。该结果只代表当前机器和当前样例，
不等于 Bench 质量评测。Ollama 二进制、模型权重、prompt 和完整 response 均不提交到仓库。

A2-3a 当前使用系统 Git 和 Cloudflare 公共 DoH，不把二进制或第三方仓库内容复制进本仓库。
受控测试仅保存公开仓库 URL 和聚合断言；目标对象、运行数据库与临时 workspace 在测试结束后
删除。最终 Docker/Linux 发行前必须锁定 Git 包版本/摘要并再次审查公共 DNS 服务条款与替代
profile，不能把当前 macOS 实测直接当作部署证据。

## 自主建设资源

### license-obligations

15 种常见许可证的结构化义务库，包括：署名、许可证保留、NOTICE、源代码提供、网络使用、专利条款、再分发和修改义务。每条规则需记录官方原文链接、人工复核状态和版本。

### ai-resource-detectors

识别以下证据：

- Hugging Face、ModelScope 模型和数据集 URL；
- `from_pretrained`、模型下载和缓存调用；
- OpenAI、Anthropic、Google 等外部 API SDK 或端点；
- README、配置文件和环境变量示例中的第三方服务；
- 模型卡、数据卡、自定义许可证链接。

### OpenGuard-Bench

- 20-30 个仅保存 URL、提交哈希和人工标注的公开项目样本；
- 50-100 个团队自建合成测试夹具；
- `expected_components.json`；
- `expected_licenses.json`；
- `expected_ai_assets.json`；
- `expected_risks.json`；
- 自动评测脚本和错误分析模板。

不要复制、再发布无权再分发的第三方仓库、模型或数据内容。

## 需要形成的代码清单

- 仓库安全获取器；
- 文件清单与哈希生成器；
- ScanCode 适配器；
- Syft 适配器；
- Python manifest 解析器；
- JavaScript manifest/lockfile 解析器；
- 模型、数据集和 API 引用解析器；
- SPDX 标准化器；
- 统一资源图谱模型；
- 许可证义务规则引擎；
- 风险证据关联器；
- AI 结构化抽取器；
- AI 整改说明生成器；
- 第三方资源清单生成器；
- HTML/JSON/CSV 报告器；
- 扫描任务 API；
- 仪表盘、图谱和风险详情页面；
- 基准评测脚本；
- 单元、集成、端到端和安全测试；
- Docker Compose 和本地部署脚本。

## 需要形成的非代码资料

- 需求调研和竞品比较；
- 系统架构图、模块图和数据流图；
- 许可证义务规则说明；
- 数据与评测标注规范；
- 用户试用记录和反馈；
- AI 辅助开发使用说明；
- 开源及第三方资源使用清单；
- README、安装、部署、使用和维护文档；
- 技术报告；
- 演示脚本和 3-5 分钟视频；
- 最终答辩 PPT（晋级后）。
