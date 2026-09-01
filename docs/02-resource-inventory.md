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
| Qwen3 小参数模型 | 本地条款抽取与解释 | Apache-2.0，按具体权重仓库复核 | 必需 |
| Ollama | 本地模型服务 | MIT | 推荐 |
| React | 前端框架 | MIT | 必需 |
| TypeScript | 前端语言 | Apache-2.0 | 必需 |
| Vite | 构建工具 | MIT | 必需 |
| ECharts | 仪表盘与图表 | Apache-2.0 | 推荐 |
| React Flow | 资源关系图 | 按锁定版本核验 | 推荐 |
| pytest | 单元与集成测试 | MIT | 必需 |
| Playwright | 端到端测试 | Apache-2.0 | 推荐 |
| Docker Compose | 一键部署 | 按发行版本核验 | 必需 |

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
