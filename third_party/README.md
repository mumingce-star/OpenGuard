# 第三方资源台账

正式台账字段：

| 名称 | 类型 | 版本/提交 | 官方来源 | 许可证/授权 | 使用方式 | 关键义务 | 自研边界 | 合规状态 | 开放方式 |
|---|---|---|---|---|---|---|---|---|---|
| PyPA packaging | Python 运行时库 | 26.3 | https://pypi.org/project/packaging/26.3/ | Apache-2.0 OR BSD-2-Clause | 仅用于离线解析与规范化 PEP 508/PEP 440 requirement、名称、specifier 和 marker；不联网、不安装被扫描项目依赖 | 分发时保留上游版权与许可证文本；项目 Apache-2.0 不改变该依赖的双许可证 | OpenGuard 自研 manifest 发现、读取限额、URL 安全门禁、DTO、证据定位、去重/冲突和错误语义；不复制其解析实现 | 已核验（2026-09-02，官方 PyPI 版本/来源与上游许可证） | 作为精确锁版运行时依赖声明，不在仓库存放 wheel/sdist |
| FastAPI | Python Web 框架 | 0.141.1 | https://pypi.org/project/fastapi/0.141.1/ | MIT | A3-1 路由、Pydantic 请求/响应校验与 OpenAPI | 分发时保留上游版权和 MIT 许可证文本 | OpenGuard 自研 API DTO、持久注册表映射、业务状态与错误语义；不复制框架实现 | 已核验（2026-09-03，官方 PyPI 版本、来源、许可证；未使用 standard extra） | 精确锁版运行时依赖，不在仓库存放 wheel/sdist |
| python-multipart | Python multipart 流式解析库 | 0.0.32 | https://pypi.org/project/python-multipart/0.0.32/ | Apache-2.0 | FastAPI/Starlette 解析冻结的 ZIP `multipart/form-data` 创建请求；OpenGuard 随后自行执行上传字节上限、安全暂存、摘要与 A2 校验 | 分发时保留上游版权、许可证与声明 | OpenGuard 自研字段约束、文件名规则、上传限额、私有暂存、幂等、后台生命周期、错误语义与 A4-1 接线；不复制解析器实现 | 已核验（2026-09-03，官方 PyPI 最新版本、来源、许可证、Python 3.12 支持与发布哈希） | 精确锁版运行时依赖，不在仓库存放 wheel/sdist |
| Uvicorn | Python ASGI 服务器 | 0.52.4 | https://pypi.org/project/uvicorn/0.52.4/ | BSD-3-Clause | 本地启动 FastAPI 应用；只使用基础安装，不启用 standard extra | 分发时保留上游版权、许可证与免责声明 | OpenGuard 自研应用工厂、数据目录和路由；不复制服务器实现 | 已核验（2026-09-03，官方 PyPI 版本、来源、许可证） | 精确锁版运行时依赖，不在仓库存放 wheel/sdist |
| HTTPX2 | Python HTTP 测试客户端 | 2.12.0 | https://pypi.org/project/httpx2/2.12.0/ | BSD-3-Clause | 仅由 Starlette TestClient 在 A3-1 测试中调用，不用于产品联网 | 分发时保留上游版权、许可证与免责声明 | OpenGuard 自研测试输入、期望值和验收断言；不复制客户端实现 | 已核验（2026-09-03，官方 PyPI 版本、来源、许可证） | 精确锁版 dev 依赖，不在仓库存放 wheel/sdist |
| pytest | Python 开发/测试框架 | 8.4.2 | https://pypi.org/project/pytest/8.4.2/ | MIT | 仅用于运行 OpenGuard 自身测试；不扫描、执行或安装被扫描项目的依赖 | 分发时保留上游版权与许可证文本 | OpenGuard 自研测试与验收逻辑；不复制 pytest 实现 | 组员环境已验证版本；集成分支继续使用项目隔离测试环境复核 | 通过 backend 开发依赖精确锁版，不在仓库存放 wheel/sdist |
| ScanCode Toolkit | 外部扫描器（可选部署工具） | 32.5.0 | https://github.com/aboutcode-org/scancode-toolkit/releases/tag/v32.5.0 | Apache-2.0 | 通过受限 JSON Adapter 获取许可证/版权候选，不执行被扫描项目代码 | 部署时保留上游许可证、版本与校验；输出必须继续经过规范化和人工核验 | OpenGuard 自研安全调用边界、相对定位校验与 P0 Evidence 映射，不复制 ScanCode 引擎 | 组员环境已作候选验证；当前 macOS 集成和真实工具输出仍待复核 | 不在仓库存放或自动下载二进制 |
| Anchore Syft | 外部 SBOM 扫描器（可选部署工具） | 1.51.0 | https://github.com/anchore/syft/releases/tag/v1.51.0 | Apache-2.0 | 通过受限 JSON Adapter获取组件候选，不执行被扫描项目代码 | 部署时保留上游许可证、版本与校验；不把候选许可证当作已确认事实 | OpenGuard 自研安全调用边界、相对定位校验、P0映射与跨来源合并 | 组员环境已作候选验证；当前 macOS 集成和真实工具输出仍待复核 | 不在仓库存放或自动下载二进制 |
| Ollama | 本地模型运行时候选 | 0.33.3 | https://github.com/ollama/ollama/releases/tag/v0.33.3 | MIT；上游 `LICENSE` | 仅作为 A5-1a 本地 loopback transport 候选；本轮未安装、未启动、未请求 | 分发时保留上游许可证和来源；不得把未运行候选写成实际模型证据 | OpenGuard 自研 loopback/禁代理/超时/响应封装与 A5-0 接线；不复制 Ollama 实现 | 待核验（锁定候选；本机未安装/未运行） | 仅公开官方链接，不下载或再分发运行时 |
| Qwen3 | 开放权重模型候选 | `qwen3:4b-instruct-2507-q4_K_M` | https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M；https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507 | Apache-2.0；模型页及 Qwen 模型仓库 | 仅作为 A5-1a 传输身份候选；本轮未下载权重、未运行推理 | 以锁定模型页/模型卡和实际授权为准；不得把候选摘要、性能或许可证义务写成已实测结论 | OpenGuard 自研 canonical prompt、证据引用和 pending remediation；不复制或再分发权重 | 待核验（锁定候选；权重未下载/未运行） | 仅公开官方链接，不存放或再分发权重 |
| Qwen3 Ollama manifest | 模型 manifest/blob 身份 | `sha256:0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`；blob `sha256:85e4a5b7b8ef0e48af0e8658f5aaab9c2324c76c1641493f4d1e25fce54b18b9` | 官方 registry manifest；模型页 https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M | 随对应 Qwen3 模型 | 仅用于完整 digest pinning 与运行前比对；本轮未访问本机 Ollama、未下载或比对 | 保留摘要来源与校验记录；不得据摘要推断模型性能、许可证合规或真实推理 | OpenGuard 自研 digest 比对和 ProducerRef/config_digest 绑定；不生成或托管模型 blob | 待核验（规格锁定候选；本机未比对） | 仅记录摘要和官方链接，不公开 blob |

所有依赖、模型、数据、框架、组件、工具、素材和第三方服务在首次引入时登记，不在提交前集中补录。
