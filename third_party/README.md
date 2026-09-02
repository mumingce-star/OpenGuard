# 第三方资源台账

正式台账字段：

| 名称 | 类型 | 版本/提交 | 官方来源 | 许可证/授权 | 使用方式 | 关键义务 | 自研边界 | 合规状态 | 开放方式 |
|---|---|---|---|---|---|---|---|---|---|
| PyPA packaging | Python 运行时库 | 26.3 | https://pypi.org/project/packaging/26.3/ | Apache-2.0 OR BSD-2-Clause | 仅用于离线解析与规范化 PEP 508/PEP 440 requirement、名称、specifier 和 marker；不联网、不安装被扫描项目依赖 | 分发时保留上游版权与许可证文本；项目 Apache-2.0 不改变该依赖的双许可证 | OpenGuard 自研 manifest 发现、读取限额、URL 安全门禁、DTO、证据定位、去重/冲突和错误语义；不复制其解析实现 | 已核验（2026-09-02，官方 PyPI 版本/来源与上游许可证） | 作为精确锁版运行时依赖声明，不在仓库存放 wheel/sdist |
| pytest | Python 开发/测试框架 | 8.4.2 | https://pypi.org/project/pytest/8.4.2/ | MIT | 仅用于运行 OpenGuard 自身测试；不扫描、执行或安装被扫描项目的依赖 | 分发时保留上游版权与许可证文本；测试环境依赖不构成被扫描项目依赖 | OpenGuard 自研测试、fixture 与验收逻辑；不复制 pytest 实现 | 已在当前用户 Python 3.12 环境安装并以 `python -m pytest --version` 核验（2026-09-03） | 通过项目 `backend` 开发依赖精确锁版，不在仓库存放 wheel/sdist |
| ScanCode Toolkit | 外部扫描器（可选部署工具） | 32.5.0；Windows py3.12 包 SHA-256 `d659258d8067d36403f8a4df21ca0446b1a56f615754c92139d8a264d57abe49` | https://github.com/aboutcode-org/scancode-toolkit/releases/tag/v32.5.0 | Apache-2.0 | 仅通过无 shell、超时和输出上限的适配器读取 JSON；不执行被扫描项目代码 | 部署时保留上游许可证、版本与校验；工具输出只作待规范化证据 | OpenGuard 自研安全调用边界、相对定位校验、P0 Evidence 映射和规则/风险语义；不复制 ScanCode 引擎 | 已在当前用户工具环境校验并运行 `scancode --version`（2026-09-02）；不随仓库分发 | 不在仓库存放或自动下载二进制 |
| Anchore Syft | 外部 SBOM 扫描器（可选部署工具） | 1.51.0；Windows amd64 包 SHA-256 `fc5ffaeffb993576ece9c791da5a688fb2c8969a1479bbfe58583672c64da336` | https://github.com/anchore/syft/releases/tag/v1.51.0 | Apache-2.0 | 仅通过无 shell、超时和输出上限的适配器读取 JSON；不执行被扫描项目代码 | 部署时保留上游许可证、版本与校验；工具输出不猜测许可证 | OpenGuard 自研安全调用边界、相对定位校验、P0 Component/Evidence 映射与跨来源合并 | 已以官方 checksums 清单校验并运行 `syft version`（2026-09-02）；不随仓库分发 | 不在仓库存放或自动下载二进制 |

所有依赖、模型、数据、框架、组件、工具、素材和第三方服务在首次引入时登记，不在提交前集中补录。
