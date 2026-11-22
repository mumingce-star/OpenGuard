# 资源、模型与第三方归属

本文件适用于 OpenGuard 国赛本地候选 `aic-national-p3-p7-20261122-candidate`。受测产品与测试冻结于 `1f4dc46aab5c494be71c518fe869787a24f679ba`。版本链、产品树和依赖锁摘要以 `VERSION.json` 为准，包内文件摘要以 `FILE_HASHES.json` 为准。远程发布等待 Owner 接纳和单独授权。

## 自有代码及第三方闭包

OpenGuard 自有代码采用根 `LICENSE` 的 Apache-2.0。第三方组件按其各自许可归属。历史 UI 贡献和许可参考见 `application/frontend/THIRD_PARTY_UI.md`，前序录制改动见 `FRONTEND_UPDATE_20261116.md`。该文件仅记录历史状态。现用首页由代码绘制，旧版视频、海报及独立字体文件未随包分发。

- 后端依赖锁在 `deployment/requirements.lock`，共 27 个精确版本，包含 FastAPI、Starlette、Pydantic、Uvicorn、httpx2 及其依赖和测试工具。P7 使用既有 Python 3.12 venv 只读核对安装元数据与许可证记录。此 ZIP 提供依赖声明，Python 包、轮子、虚拟环境和操作系统工具由接收者另行取得。
- 预构建页面内含 React 19.2.8、ReactDOM 19.2.8、scheduler 0.27.0 的 MIT 运行时代码，以及 Tailwind CSS 4.3.3 的样式。随附 `web/third-party-licenses.txt` 和 `THIRD_PARTY_LICENSES/`。圆形玻璃按钮改编自 cssbuttons-io / massive-mayfly-74（MIT），署名位于 `application/frontend/UIVERSE_CSSBUTTONS_IO_LICENSE.txt` 和同一 Web 许可证清单。
- 前端完整依赖版本见 `application/frontend/pnpm-lock.yaml`。Vite 8.2.2（MIT）与 TypeScript 5.9.2（Apache-2.0）用于构建或检查，随附上游许可记录，ZIP 未附开发工具目录或 Native 二进制。固定 Node v24.22.3 及 `yaml@2.9.0` 为本轮离线检查环境，YAML 仅用于 pnpm 锁测试，两者都在 ZIP 外。
- 外部 ScanCode 和 Syft 适配代码保留。冻结启动配置关闭外部扫描器，ZIP 未附相应工具。P6 Benchmark 的本地只读素材来源和许可声明固定在 `application/benchmarks/p6_benchmark_manifest.json`，评测过程的复建第三方包和隔离数据位于包外证据目录。

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

固定可选模型为 Ollama `0.33.3` 与 `qwen3:4b-instruct-2507-q4_K_M`。模型 manifest digest 为 `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`，模型权重不入包，运行时另行取得。模型身份与冻结启动器常量对照。P7 的 `MODEL_CALLS=0`，未进行模型身份查询或推理。普通扫描与评估使用本机作业链，默认关闭自动 Qwen。

公开包只包含冻结的普通文件。Git 管理目录、依赖目录、个人运行数据、账号数据库、私有日志、模型权重及旧界面媒体排除。少量测试源码中的密钥格式和合成路径用于验证拒收，归属由各测试文档说明。P5 浏览器截图、P6 原始 ASGI 交换及本轮测试数据留在独立证据目录。
