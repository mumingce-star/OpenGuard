# 第三方资源台账

正式台账字段：

| 名称 | 类型 | 版本/提交 | 官方来源 | 许可证/授权 | 使用方式 | 关键义务 | 自研边界 | 合规状态 | 开放方式 |
|---|---|---|---|---|---|---|---|---|---|
| PyPA packaging | Python 运行时库 | 26.3 | https://pypi.org/project/packaging/26.3/ | Apache-2.0 OR BSD-2-Clause | 仅用于离线解析与规范化 PEP 508/PEP 440 requirement、名称、specifier 和 marker；不联网、不安装被扫描项目依赖 | 分发时保留上游版权与许可证文本；项目 Apache-2.0 不改变该依赖的双许可证 | OpenGuard 自研 manifest 发现、读取限额、URL 安全门禁、DTO、证据定位、去重/冲突和错误语义；不复制其解析实现 | 已核验（2026-09-02，官方 PyPI 版本/来源与上游许可证） | 作为精确锁版运行时依赖声明，不在仓库存放 wheel/sdist |
| pytest | Python 开发/测试框架 | 8.4.2 | https://pypi.org/project/pytest/8.4.2/ | MIT | 仅用于运行 OpenGuard 自身测试；不扫描、执行或安装被扫描项目的依赖 | 分发时保留上游版权与许可证文本；测试环境依赖不构成被扫描项目依赖 | OpenGuard 自研测试、fixture 与验收逻辑；不复制 pytest 实现 | 已在当前用户 Python 3.12 环境安装并以 `python -m pytest --version` 核验（2026-09-03） | 通过项目 `backend` 开发依赖精确锁版，不在仓库存放 wheel/sdist |
| ScanCode Toolkit | 外部扫描器（可选部署工具） | 32.5.0；Windows py3.12 包 SHA-256 `d659258d8067d36403f8a4df21ca0446b1a56f615754c92139d8a264d57abe49` | https://github.com/aboutcode-org/scancode-toolkit/releases/tag/v32.5.0 | Apache-2.0 | 仅通过无 shell、超时和输出上限的适配器读取 JSON；不执行被扫描项目代码 | 部署时保留上游许可证、版本与校验；工具输出只作待规范化证据 | OpenGuard 自研安全调用边界、相对定位校验、P0 Evidence 映射和规则/风险语义；不复制 ScanCode 引擎 | 已在当前用户工具环境校验并运行 `scancode --version`（2026-09-02）；不随仓库分发 | 不在仓库存放或自动下载二进制 |
| Anchore Syft | 外部 SBOM 扫描器（可选部署工具） | 1.51.0；Windows amd64 包 SHA-256 `fc5ffaeffb993576ece9c791da5a688fb2c8969a1479bbfe58583672c64da336` | https://github.com/anchore/syft/releases/tag/v1.51.0 | Apache-2.0 | 仅通过无 shell、超时和输出上限的适配器读取 JSON；不执行被扫描项目代码 | 部署时保留上游许可证、版本与校验；工具输出不猜测许可证 | OpenGuard 自研安全调用边界、相对定位校验、P0 Component/Evidence 映射与跨来源合并 | 已以官方 checksums 清单校验并运行 `syft version`（2026-09-02）；不随仓库分发 | 不在仓库存放或自动下载二进制 |

所有依赖、模型、数据、框架、组件、工具、素材和第三方服务在首次引入时登记，不在提交前集中补录。

## 2026-09-09 本机部署辅助工具（不随作品分发）

2026-09-10续配新增本机工具：微软WSL2.7.13.0官方MSI（Microsoft Corporation签名Valid，SHA见环境回执），作为Docker的WSL2运行环境，安装退出0；发行包及Linux内核等组件按各自随包授权使用，不作为自研代码或随仓库分发。微软Sysinternals Handle5.0来自官方download.sysinternals.com，Microsoft签名Valid，接受随包Sysinternals许可后仅用于只读目录占用诊断，不关闭句柄；工具和诊断日志留在忽略目录，不纳入作品依赖。Docker Engine仍未就绪，不能将工具安装算作部署成功。

| 名称 | 版本 | 来源与授权信息 | 使用与验证 | 分发范围 |
|---|---|---|---|---|
| Docker Desktop | 4.90.0.238679；CLI29.7.2；Compose5.5.1 | Docker官方Windows安装器；Docker Desktop Subscription Service Agreement，发行包各组件另依随包许可证 | 仅为本机容器环境；Docker Inc数字签名Valid，安装退出0，版本命令与Compose静态校验通过；引擎待Windows重启验收 | 不提交安装器/镜像/运行数据；团队自行确认适用订阅条件 |
| pypdf | 6.18.0 | PyPI pypdf6.18.0，上游py-pdf/pypdf；发行包附带BSD条款LICENSE | 临时读取用户部署PDF的七页文字；不加入后端依赖，不上传原PDF或抽取全文 | 仅临时本机工具，不提交第三方实现 |
