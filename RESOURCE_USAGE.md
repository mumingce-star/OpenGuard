# OpenGuard v2.6.1 资源与第三方归属

本里程碑的产品与测试树继承自 `b304f4338422a5472b281f6a09c1e5b8895ff642`。完整版本链、树摘要及锁文件身份见 [VERSION.json](VERSION.json)，配套文件摘要见 [FILE_HASHES.json](FILE_HASHES.json)。

## 自有代码及第三方组件

- OpenGuard 自有代码采用 [Apache-2.0](LICENSE)。历史 UI 贡献和许可说明见 [THIRD_PARTY_UI.md](application/frontend/THIRD_PARTY_UI.md)。现用首页由代码绘制。旧界面视频、海报和独立字体文件不在本包。
- 后端使用 [27 项精确依赖](deployment/requirements.lock)，含 FastAPI、Starlette、Pydantic、Uvicorn、httpx2 与测试工具。包内提供锁文件，Python 解释器、虚拟环境、wheelhouse 及操作系统工具由使用者准备。本次离线复验复用固定 CPython 3.12 venv。v2.5 的无头离线 CLI、v2.6 的许可证兼容矩阵引擎与 v2.6.1 审计加固仅使用标准库与既有锁定依赖，新增第三方依赖为 0。
- 预构建页面包含 React `19.2.8`、ReactDOM `19.2.8`、scheduler `0.27.0`（MIT）及 Tailwind CSS `4.3.3`（MIT）。圆形玻璃按钮改编自 cssbuttons-io / massive-mayfly-74（MIT）。署名及许可证见 [web/third-party-licenses.txt](web/third-party-licenses.txt)、[THIRD_PARTY_LICENSES/](THIRD_PARTY_LICENSES/) 和 [按钮许可](application/frontend/UIVERSE_CSSBUTTONS_IO_LICENSE.txt)。
- 前端完整版本见 [pnpm-lock.yaml](application/frontend/pnpm-lock.yaml)。Vite `8.2.2`（MIT）、TypeScript `5.9.2`（Apache-2.0）用于构建或类型检查，所附上游许可证位于 `THIRD_PARTY_LICENSES/`。运行包包含预构建页面。Node `v24.22.3`、同锁依赖缓存和用于 pnpm 锁测试的 `yaml@2.9.0` 只作为包外离线复验输入。
- 外部 ScanCode 与 Syft 适配代码保留，交付启动配置关闭外部扫描器，这些工具未随包分发。P6 基准样本来源及许可声明见 [冻结清单](application/benchmarks/p6_benchmark_manifest.json)。

## 容器构建依赖

[Dockerfile](Dockerfile) 使用官方 `python:3.12-slim` 基础镜像，从 Debian 软件源安装 `git`，并将锁定的 Python 依赖安装到 `/opt/openguard-venv`。[docker-compose.yml](docker-compose.yml) 声明回环端口映射和独立运行数据卷，[.dockerignore](.dockerignore) 限定镜像构建输入。发布 ZIP 提供构建配置和应用文件，容器镜像由用户或 CI 构建，wheelhouse 由使用者单独准备。

## Web 产物清单

以下 8 份预构建文件来自冻结产品树，共 1,261,612 字节。TASK60A 的同锁离线 Vite 构建已逐字节核对，超过 500 kB 的 chunk 告警为 0。

| 包内路径 | 字节 | SHA-256 |
| --- | ---: | --- |
| `web/index.html` | 898 | `5d49fe169da46c4d3a4523a001ad7d23de8730f6b115af3af622add175b657ca` |
| `web/about.html` | 898 | `5d49fe169da46c4d3a4523a001ad7d23de8730f6b115af3af622add175b657ca` |
| `web/third-party-licenses.txt` | 5,794 | `6bace3f1e7ccee1144b6a3ff4a8ac947c5a9afb00f1419b2f406843a21139d53` |
| `web/assets/main-DTjwc3MZ.js` | 340,236 | `76b9fa576bb6868c1969e0a32d900334e7cc2cebc60a6f52089ab4b651ade80a` |
| `web/assets/main-D1Dke-iz.css` | 436,821 | `b6f8b808ea339d08ece33de900565e6249cce9779d22ca0f7b838eae1e81eb53` |
| `web/assets/p2-workbench-BpK-WfaC.css` | 50,269 | `52f626427defd032001820ea6a4b656cd2d263f713e75a45b9e02ffb8154edb2` |
| `web/assets/p2-workbench-CXBmWfYD.js` | 237,076 | `1ee5d5951d63e6c3c93eee8d127e723ed6f6715f95784b835d40bc421e94d606` |
| `web/assets/react-runtime-YahHAMAi.js` | 189,620 | `c5f08825cdca736a015fe6303f97a64ec1e4511a38b5f2f6f589ecb35e815c65` |

## 冻结锁文件、许可规则及基准

| 包内路径 | SHA-256 |
| --- | --- |
| `application/frontend/pnpm-lock.yaml` | `357bf1d00f49ffcddcfb13fadf232f79bd864341d210fd8ea324106ee679185f` |
| `deployment/requirements.lock` | `15aa7739d2d387e9763975a87e6e20e7b224a242be0a0aeff257c081f8e23ab0` |
| `application/rules/license-obligations.yaml` | `103461f4d3a1d09482b6deeb0cf76b8f689243a0935ce8b3d604c908edb782c3` |
| `application/benchmarks/p6_benchmark_manifest.json` | `622389e049a110e3235b7080582f9a770cdbcaf0ca5d339899003336af2a489e` |

## Copyleft 全文测试夹具

TASK49 离线识别测试夹具仅收录下列六份逐字许可证原文及其元数据。MPL 原件取自固定的 `lightningcss@1.32.0` 发行物，GNU 原文取自本机第三方许可副本。运行时识别使用原文指纹和条款定位规则。夹具 SHA-256 为 `4d7030e0fb19c5d580acf821f8e9ee85e207987cd4871f4c04747d01bf08ba80`。 [task49-copyleft-licenses.json](application/tests/fixtures/task49-copyleft-licenses.json)

| 许可证族 | 原文副本 | 字节 | 原文 SHA-256 |
| --- | --- | ---: | --- |
| MPL-2.0 | `lightningcss@1.32.0/LICENSE` | 15,648 | `5eba353fe5076ac3432177f8ab1cf75e3afcd0584251e37c3bfead5f447d040e` |
| GPL-2.0 | `frei0r/COPYING.GPL-2.0` | 18,002 | `231f7edcc7352d7734a96eef0b8030f77982678c516876fcb81e25b32d68564c` |
| GPL-3.0 | `frei0r/COPYING.GPL-3.0` | 35,147 | `8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903` |
| LGPL-2.1 | `frei0r/COPYING.LGPL-2.1` | 26,521 | `592987e8510228d546540b84a22444bde98e48d03078d3b2eefcd889bec5ce8c` |
| LGPL-3.0 | `frei0r/COPYING.LGPL-3.0` | 7,651 | `da7eabb7bafdf7d3ae5e9f223aa5bdc1eece45ac569dc21b3b037520b4464768` |
| AGPL-3.0 | `synthsod/LICENSE` | 34,523 | `8486a10c4393cee1c25392769ddd3b2d6c242d6ec7928e1414efff7dfb2f07ef` |

## 内置离线样例

- `is-number@7.0.0`（MIT）为固定 ZIP 演示主线。输入 `samples/is-number-7.0.0-derived.zip` 从 npm 发行物派生。材料原文见 `samples/is-number-LICENSE.txt`，测试用归档、profile 和 metadata 位于 `application/tests/fixtures/task33/is-number-7.0.0/`。两份派生 ZIP 和一份 TGZ 各含四个普通源文件。样例支持条件来自精确材料、对象和版本绑定，适用性仍须核对。
- `http-server@14.1.2`（MIT）为固定 Git 离线兼容样例。上游为 `http-party/http-server`，固定提交 `0d3b7bb5b6e8a59fd450ae2dca65870009cfcd8b`。随包 `samples/http-server.bundle` 为 462,976 字节，SHA-256 `b4d28764503ce135702d948878d8604495fd0addf38c7a070892e93d038c714b`。伴随 `samples/http-server-LICENSE.txt` SHA-256 `accfc4d5a588384b29c4817392854afb8f319b4568359ca8d063df8a9bc396b6`。启动检查核对此两份原件。

### 固定 Git 样例的六项嵌套例外

Owner 仅批准下表六项继续作为上述固定上游 bundle 的嵌套内容。相对路径与 SHA-256 均须匹配。PEM 是上游测试使用的公开配对材料，只用于识别样例原件，在本项目运行及演示中不得用作身份材料。PNG 属上游样例与文档，离线依据为上游仓库的 MIT 声明、原始 README 与样例代码。个别图片无单独创作者授权记录，进一步公开传播仍需 Owner 审视该边界。

| bundle 内原始路径 | 归属与类别 | 字节数 | SHA-256 |
|---|---|---:|---|
| `test/fixtures/https/agent2-cert.pem` | 公开上游 TLS 测试证书 | 1493 | `86cb2e5062f9c132ba293ba1900b6499b92970126651ce78132a2f7dec5667de` |
| `test/fixtures/https/agent2-key.pem` | 公开上游 TLS 测试私钥 | 1679 | `1e67ba403f19109a90f974c5a2f2e7513dfe07bca6d899374afd651952a010f8` |
| `public/img/turtle.png` | 上游样例 PNG | 55202 | `acadc81bf0ca74b9731eee589496134e19f55460aa984a0ed50e990a944c5466` |
| `screenshots/directory.png` | 上游文档截图 PNG | 7171 | `4a7b4358768f90d30eca5273cd4c21def025518535eb743164a85d178b63e0a3` |
| `screenshots/public.png` | 上游文档截图 PNG | 62498 | `4c3aa1b068e8ada2975250cb752182032513f9d7bbbd3c6b1f852cc7cb8f196a` |
| `screenshots/start.png` | 上游文档截图 PNG | 98522 | `f2408298ef05e3eb8d60589234576ceabf92ed6d0fab71b5badc90c804ef3ad0` |

## 固定可选模型与数据边界

固定可选模型为 Ollama `0.33.3` 与 `qwen3:4b-instruct-2507-q4_K_M`。manifest digest 为 `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`，权重不入包。用户可在本机自备该身份的模型，相关生成请求须明确发起。普通扫描与评估使用本机作业链。TASK50 的结构化输出门禁使用确定性替身，本机 Ollama 真机推理为 `NOT_RUN (LOCAL_OLLAMA_STOPPED)`。

ZIP 仅包含清单绑定的跟踪文件与清单本身。Git 管理目录、依赖缓存、个人运行数据、账号数据库、私有日志、模型权重及旧界面媒体均排除。测试源码里的合成路径和密钥格式只用于验证拒收。Chrome 截图、评测原始交换、测试记录和临时数据均位于包外。
