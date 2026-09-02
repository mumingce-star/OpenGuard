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

所有依赖、模型、数据、框架、组件、工具、素材和第三方服务在首次引入时登记，不在提交前集中补录。
