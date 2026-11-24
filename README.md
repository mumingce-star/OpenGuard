# OpenGuard v2.5.0

OpenGuard 是面向开发团队的本地优先开源合规与证据溯源工作台。它从项目输入中发现资源和依赖，关联许可证、声明用途和原文证据，并将研判及报告固定为可复核的版本。

本包提供本机 `TEST_ONLY` 运行环境。版本和产品树见 [VERSION.json](VERSION.json)，文件校验见 [FILE_HASHES.json](FILE_HASHES.json)，实测范围见 [VALIDATION.md](VALIDATION.md)。这是本地里程碑，远程发布状态以 `VERSION.json` 为准。

## 核心能力

- **无头离线扫描 CLI（`openguard.py scan`）。** 复用生产五生态 ZIP 流水线、B58 依赖证据和 SBOM 解析。根目录的 `LICENSE`、`LICENSE.txt`、`LICENSE.md`、`COPYING` 与 `COPYING.txt` 复用 `material-claims/4` 原文解析器和同族 Copyleft 冲突规则，保守报告 `UNKNOWN`，产生 0 条 `SUPPORT`。支持本地项目目录与 ZIP。目录遍历自动排除 `.git`、`node_modules`、`__pycache__`、`.venv`、`venv`、`target`、`dist`、`build` 和 `.pytest_cache`，遇到符号链接或其他非普通条目时跳过并标记 `partial`。ZIP 走生产归档安全检查。
- **报告与 CI 门禁。** 无头扫描支持 `--format text|json|markdown`，JSON 默认单独写到标准输出并使用 `openguard-cli-scan/1`，报告不含宿主机绝对路径。`--output <file>` 独占新建，拒绝覆盖现有文件。`--usage commercial,distributed,modified` 记录用途，`--fail-on conflict,copyleft,partial` 选择门禁。退出码 `0` 表示通过选定门禁，`1` 表示命中选定门禁，`2` 表示参数、输入或运行环境错误。

- **五生态离线扫描。** 支持 npm、Python、Go、Rust 和 Java。Go 读取 `go.mod` 与 `go.sum`，Rust 读取 `Cargo.toml` 与 `Cargo.lock` v3/v4，Java 读取 `pom.xml` 与 `gradle.lockfile`。CycloneDX 1.5（JSON/XML）及 SPDX 2.3（JSON/tag-value）按组件声明的身份与版本核对 PURL。动态版本、无法解析的依赖与不能唯一确定的冲突保留为待核查证据。
- **npm 与 Python 根包。** ZIP 扫描读取根目录的 `package.json` 或 `pyproject.toml`。Python 优先采用 PEP 621 的 `[project]`，仅在该表缺失时读取 Poetry 的 `[tool.poetry]`。根包版本缺失、声明为动态或无效时跳过 Python 根包，独立保留已有依赖观察。根包进入同一扫描、正式 Assessment 和 v4 研判。
- **Cargo 与 Maven 根包。** 根目录的 `Cargo.toml` 与 `pom.xml` 可绑定明确的根包坐标、版本和单项 SPDX 声明。两个生态的根包均进入 `material-claims/4` 原文定位，也可验证 Copyleft `SPDX_TEXT_CONFLICT`。缺少发行来源绑定时保持 `UNKNOWN`，对应验收产生 0 条 `SUPPORT`。Go 保留依赖证据，`go.mod` 缺少根包版本时不生成推测版本。
- **依赖与版本证据。** B58 离线观察受支持的清单、锁文件及 SBOM。`GET /api/v1/scans/{scan_id}/dependency-evidence` 和工作台展示依赖来源、文件路径、SHA-256、证据 ID 及版本冲突双方。声明、推断和待补证的版本分别呈现。
- **许可材料与条款定位。** `material-claims/4` 识别受支持的 MIT、Apache-2.0、ISC、BSD-2-Clause 和 BSD-3-Clause 完整文本，保留条款的原始字节区间、行号与摘要。条件 `SUPPORT` 需要明确用途、精确对象版本和完整的发行来源与材料绑定。Python 根包可以绑定并解析 MIT 原文，未建立受支持的发行来源绑定时保持 `UNKNOWN`。Apache-2.0 精确匹配 NOTICE 后仍保留 §4(d) 人工核对，结果为 `UNKNOWN`。
- **Copyleft 全文与冲突。** 支持 MPL-2.0、GPL-2.0、GPL-3.0、LGPL-2.1、LGPL-3.0 和 AGPL-3.0 的已收录标准全文。识别到的原文与单项 SPDX 声明不一致时，关联原文及声明证据并给出 `SPDX_TEXT_CONFLICT`。同一 Copyleft 族的 `-only` 与 `-or-later` 声明不会因识别到该族标准全文而触发冲突。Copyleft 保留源代码披露或文件范围人工复核，规则不产生 `SUPPORT`。
- **增量研判与固定归档。** 补材或回答后生成影响集与新版 Result，历史 Result 可按原 ID 只读复核。Report V2 1.0 和 1.1 绑定正式 Assessment 并提供不可变 HTML/JSON 快照，1.1 归档包含依赖证据。评估包保留相关版本与摘要。

## 快速启动

### 原生 macOS / Linux

将 ZIP 解压到新的用户可写目录，进入 `OpenGuard/`。需要 CPython 3.12（含 venv/pip）、Git 和现代浏览器。启动器面向 macOS 和 Linux，Windows 使用 WSL2 的 Linux 用户目录。跨平台实测范围见 [VALIDATION.md](VALIDATION.md)。

```sh
python3.12 verify_package.py
python3.12 openguard.py setup
python3.12 openguard.py check
python3.12 openguard.py self-test
python3.12 openguard.py start
```

`verify_package.py` 核对清单中 905 份文件的字节数和 SHA-256。`setup` 默认从 PyPI 安装 [27 项固定依赖](deployment/requirements.lock)。已有匹配平台及 CPython 3.12 的完整 wheelhouse 时，可用 `python3.12 openguard.py setup --offline-wheelhouse /path/to/wheelhouse` 离线安装。wheelhouse 由开发者单独准备。已有满足同一锁文件的 venv 时，可用其解释器运行 `check`、`self-test` 与 `start`。

`self-test` 启动临时回环服务，使用隔离的 `TEST_ONLY` 账户与数据验证 `material-claims/4`、补材引起的 r1→r2 变化、历史 Result 的原字节和评估包下载。TASK54 产品基线的 37 项自检已实测通过。自检证据保存在该包的 `runtime/self-tests/`，服务在命令退出前停止。

也可使用 `sh ./start.sh`，或在 macOS 运行 `./启动OpenGuard.command`。打开终端显示的 `READY http://127.0.0.1:端口/`，在本包中注册本机账号。用 `--port` 指定空闲端口，按 Ctrl+C 停止服务。预构建页面位于 `web/`，普通运行无需 Node 或 Vite。账号、扫描和报告写入当前包私有的 `runtime/`。

### Docker Compose

在解压后的 `OpenGuard/` 目录运行 `docker compose up --build`，通过 `http://127.0.0.1:8000/` 访问。Compose 仅在宿主机回环地址发布端口。容器以专用非 root 用户运行，账号、扫描和报告保存在 `openguard_runtime` 命名卷，Python 依赖位于镜像内的 `/opt/openguard-venv`。`docker compose stop` 停止服务并保留数据卷。首次构建需要镜像仓库、系统软件源和 Python 包索引。

例如，运行 `OPENGUARD_HOST_PORT=18000 docker compose up --build` 后，通过 `http://127.0.0.1:18000/` 访问。Compose 会将同一端口传给容器内的 `OPENGUARD_PUBLIC_PORT`。网关同时接受内部端口和显式声明的映射端口上的 `127.0.0.1` 与 `localhost`。

需要在容器内使用宿主机 Ollama 时，启用 `OPENGUARD_CONTAINER_MODE=1` 与 `OPENGUARD_OLLAMA_DOCKER_HOST=1` 两个开关，再显式选择固定主机端点。Compose 在容器内设置第一个开关。宿主机的 Ollama 必须能够从 Docker 主机网关访问。

```sh
OPENGUARD_OLLAMA_DOCKER_HOST=1 \
OPENGUARD_MODEL_ORIGIN=http://host.docker.internal:11434 \
docker compose up --build
```

使用容器模式与上述明示端点时，Assistant 和 P2 AI 仍由用户发起。直接在宿主机运行 `start.sh` 时，服务监听和模型连接分别限定为 `127.0.0.1` 和 `http://127.0.0.1:11434`。

### 无头扫描 CLI（本机与 Docker）

使用满足锁文件的 CPython 3.12 环境运行。当前解释器缺少锁定依赖时，CLI 可只读复用已安装且通过校验的包内 `runtime/venv`，在同一 PID 内至多调用一次 `execve`，并使用 `-B` 禁止写入字节码。扫描阶段禁止网络和子进程，模型调用为 0，且不创建或写入包内 `runtime/`。

```sh
python3.12 -B openguard.py scan samples/is-number-7.0.0-derived.zip --format json
python3.12 -B openguard.py scan ./my-project --format markdown \
  --usage commercial,distributed,modified --fail-on conflict,copyleft,partial
```

镜像已构建时，可在无网络容器中扫描内置 ZIP。将 `openguard:local` 替换为本地镜像名。

```sh
docker run --rm --network none --security-opt no-new-privileges openguard:local \
  /opt/openguard-venv/bin/python -B openguard.py scan samples/is-number-7.0.0-derived.zip --format json
```

### 从扫描到报告

1. 上传待审查项目的 ZIP。可用 `samples/is-number-7.0.0-derived.zip` 熟悉流程，并声明商业使用、分发或修改等实际用途。
2. 核对资源、依赖证据和 v4 概览。为样例补充 `samples/is-number-LICENSE.txt`，关联准确对象、版本和来源，再查看 r1 至 r2 的影响集。
3. 保存正式 Assessment 和报告快照，再下载 HTML 或 JSON。交接材料和版本依据时，可导出当前 Result 的完整评估包。

`samples/http-server.bundle` 是固定本地 Git 样例。启动器核对其摘要，并使用该固定离线来源。样例和第三方归属见 [RESOURCE_USAGE.md](RESOURCE_USAGE.md)。

## 可选本地模型

扫描、材料提交、版本复核和报告导出均可独立运行。已自行配置 Ollama `0.33.3` 与 `qwen3:4b-instruct-2507-q4_K_M` 时，可用 `python3.12 openguard.py model-check` 核对本机模型身份。包内未附模型权重或模型服务。

用户可以明确选择同一扫描的一项 npm 或 PyPI 资源，发起 `openguard-action-plan/3` 研判。程序从该资源的 `material-claims/4`、已选绑定材料和 B58 版本证据生成候选目录。模型只能选择目录中的引文及行动码，中文核验行动由程序按固定模板渲染。结果单独保存，模型失败、超时或越权时，正式规则结论保持原样。未选择资源的旧请求沿用 `action-plan/2` 路径。

应用默认关闭 `OPENGUARD_P2_AI_V4_PLAN`，包内本地 `TEST_ONLY` 启动器显式提供该能力。关闭时新协议请求会被拒绝。发布门禁使用确定性替身验证该协议，本轮本机 Ollama 实时推理未运行。

## 使用边界与路线图

依赖发现、材料完整性、文本支持、条款适用和实际履约分别呈现。`UNKNOWN` 表示当前证据或规则不足，带条件的 `SUPPORT` 仍需按实际分发范围核对。历史归档用于复核当时证据，更新用途或材料后应审查新版结果。

- **v2.6 及后续版本**计划扩展项目级许可证兼容矩阵引擎与团队协作能力。

OpenGuard 自有代码采用 [Apache-2.0](LICENSE)。第三方组件按各自许可归属，见 [RESOURCE_USAGE.md](RESOURCE_USAGE.md)。
