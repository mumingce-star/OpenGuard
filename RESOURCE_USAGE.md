# OpenGuard v2.0.0 资源与第三方归属

本里程碑的产品与测试树继承自 `a9081dfbf900b7a901120e611603fed5f441fbd9`。完整版本链、树摘要及锁文件身份见 [VERSION.json](VERSION.json)，配套文件摘要见 [FILE_HASHES.json](FILE_HASHES.json)。

## 自有代码及第三方组件

- OpenGuard 自有代码采用 [Apache-2.0](LICENSE)。历史 UI 贡献和许可说明见 [THIRD_PARTY_UI.md](application/frontend/THIRD_PARTY_UI.md)。现用首页由代码绘制。旧界面视频、海报和独立字体文件不在本包。
- 后端使用 [27 项精确依赖](deployment/requirements.lock)，含 FastAPI、Starlette、Pydantic、Uvicorn、httpx2 与测试工具。包内提供锁文件，Python 解释器、虚拟环境、wheelhouse 及操作系统工具由使用者准备。本次离线复验复用固定 CPython 3.12 venv。
- 预构建页面包含 React `19.2.8`、ReactDOM `19.2.8`、scheduler `0.27.0`（MIT）及 Tailwind CSS `4.3.3`（MIT）。圆形玻璃按钮改编自 cssbuttons-io / massive-mayfly-74（MIT）。署名及许可证见 [web/third-party-licenses.txt](web/third-party-licenses.txt)、[THIRD_PARTY_LICENSES/](THIRD_PARTY_LICENSES/) 和 [按钮许可](application/frontend/UIVERSE_CSSBUTTONS_IO_LICENSE.txt)。
- 前端完整版本见 [pnpm-lock.yaml](application/frontend/pnpm-lock.yaml)。Vite `8.2.2`（MIT）、TypeScript `5.9.2`（Apache-2.0）用于构建或类型检查，所附上游许可证位于 `THIRD_PARTY_LICENSES/`。运行包包含预构建页面。Node `v24.22.3`、同锁依赖缓存和用于 pnpm 锁测试的 `yaml@2.9.0` 只作为包外离线复验输入。
- 外部 ScanCode 与 Syft 适配代码保留，交付启动配置关闭外部扫描器，这些工具未随包分发。P6 基准样本来源及许可声明见 [冻结清单](application/benchmarks/p6_benchmark_manifest.json)。

## Web 产物清单

以下 8 份 `web/` 产物来自冻结产品树。逐文件 SHA-256 见 [FILE_HASHES.json](FILE_HASHES.json)。

| 包内路径 | 字节 |
| --- | ---: |
| `web/index.html` | 898 |
| `web/about.html` | 898 |
| `web/third-party-licenses.txt` | 5,794 |
| `web/assets/main-BTTBgYYx.js` | 290,212 |
| `web/assets/main-DfOMEasE.css` | 433,430 |
| `web/assets/p2-workbench-BpK-WfaC.css` | 50,269 |
| `web/assets/p2-workbench-CoR0fGwX.js` | 267,877 |
| `web/assets/react-runtime-YahHAMAi.js` | 189,620 |

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

固定可选模型为 Ollama `0.33.3` 与 `qwen3:4b-instruct-2507-q4_K_M`。manifest digest 为 `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`，权重不入包。用户可在本机自备该身份的模型，相关生成请求须明确发起。普通扫描与评估使用本机作业链，交付启动配置关闭自动模型调用。本轮复验零模型调用。

ZIP 仅包含清单绑定的跟踪文件与清单本身。Git 管理目录、依赖缓存、个人运行数据、账号数据库、私有日志、模型权重及旧界面媒体均排除。测试源码里的合成路径和密钥格式只用于验证拒收。Chrome 截图、评测原始交换、测试记录和临时数据均位于包外。
