# OpenGuard v2.0.0

OpenGuard 是面向开发团队的本地优先开源合规与证据溯源工作台。它从项目输入中发现资源和依赖，关联许可证、声明用途和原文证据，并将研判及报告固定为可复核的版本。

本包提供本机 `TEST_ONLY` 运行环境。版本和产品树见 [VERSION.json](VERSION.json)，文件校验见 [FILE_HASHES.json](FILE_HASHES.json)，实测范围见 [VALIDATION.md](VALIDATION.md)。这是本地里程碑，远程发布状态以 `VERSION.json` 为准。

## 核心能力

- **许可材料与条款定位。** `material-claims/4` 识别受支持的 MIT、Apache-2.0、ISC、BSD-2-Clause 和 BSD-3-Clause 完整文本，定位条款的原始字节区间、行号与摘要。条件 `SUPPORT` 需有明确用途、精确资源版本、完整来源与材料绑定等依据。Apache-2.0 存在 NOTICE 时，保留 §4(d) 人工核对，精确匹配 NOTICE 后仍为 `UNKNOWN`。
- **Copyleft 与冲突。** 强、弱 Copyleft 声明给出范围复核提示。已识别的原文与单项 SPDX 声明不一致时，呈现 `SPDX_TEXT_CONFLICT` 及对应证据。MPL-2.0、GPL 系列当前可作为声明进入风险提示，其原文全文识别列入路线图。
- **依赖与版本证据。** B58 离线观察受支持的清单、锁文件及 SBOM，保留定位、摘要和来源。`GET /api/v1/scans/{scan_id}/dependency-evidence` 与工作台展示精确版本缺口和双侧版本冲突证据。范围声明、推断和已绑定版本分别显示。
- **增量研判与固定归档。** 补材或回答后生成影响集与新版 Result，历史 Result 可按原 ID 只读复核。Report V2 1.0 和 1.1 绑定正式 Assessment 并提供不可变 HTML/JSON 快照，1.1 归档包含依赖证据。评估包保留相关版本与摘要。

## 快速启动

将 ZIP 解压到新的用户可写目录，进入 `OpenGuard/`。需要 CPython 3.12（含 venv/pip）、Git 和现代浏览器。启动器面向 macOS 和 Linux，Windows 使用 WSL2 的 Linux 用户目录。跨平台实测范围见 [VALIDATION.md](VALIDATION.md)。

```sh
python3.12 verify_package.py
python3.12 openguard.py setup
python3.12 openguard.py check
python3.12 openguard.py start
```

`verify_package.py` 核对清单中 879 份文件的字节数和 SHA-256。`setup` 默认从 PyPI 安装 [27 项固定依赖](deployment/requirements.lock)。已有匹配平台及 CPython 3.12 的完整 wheelhouse 时，可用 `python3.12 openguard.py setup --offline-wheelhouse /path/to/wheelhouse` 离线安装。包内未附 wheelhouse。若已具备满足同一锁文件的 venv，可跳过 `setup`，用其解释器直接运行 `check` 与 `start`。

也可使用 `sh ./start.sh`，或在 macOS 运行 `./启动OpenGuard.command`。打开终端显示的 `READY http://127.0.0.1:端口/`，在本包中注册本机账号。用 `--port` 指定空闲端口，按 Ctrl+C 停止服务。预构建页面位于 `web/`，普通运行无需 Node 或 Vite。账号、扫描和报告写入当前包私有的 `runtime/`。

### 从扫描到报告

1. 上传待审查项目的 ZIP。可用 `samples/is-number-7.0.0-derived.zip` 熟悉流程，并声明商业使用、分发或修改等实际用途。
2. 核对资源、依赖证据和 v4 概览。为样例补充 `samples/is-number-LICENSE.txt`，关联准确对象、版本和来源，再查看 r1 至 r2 的影响集。
3. 保存正式 Assessment 和报告快照，再下载 HTML 或 JSON。交接材料和版本依据时，可导出当前 Result 的完整评估包。

`samples/http-server.bundle` 是固定本地 Git 样例。启动器核对其摘要，并使用该固定离线来源。样例和第三方归属见 [RESOURCE_USAGE.md](RESOURCE_USAGE.md)。

## 可选本地模型

扫描、材料提交、版本复核和报告导出均可独立运行。包内未附模型权重或模型服务。已自行配置 Ollama `0.33.3` 与 `qwen3:4b-instruct-2507-q4_K_M` 时，可用 `python3.12 openguard.py model-check` 核对本机身份。评估 AI 或助手由用户明确发起，生成结果与正式 Result 分开保存。交付启动配置关闭自动外部来源获取、外部扫描器和自动模型调用。

## 使用边界与路线图

依赖发现、材料完整性、文本支持、条款适用和实际履约分别呈现。`UNKNOWN` 表示当前证据或规则不足，带条件的 `SUPPORT` 仍需按实际分发范围核对。历史归档用于复核当时证据，更新用途或材料后应审查新版结果。

- **v2.1** 将支持 Python `pyproject.toml` 根包直扫。新增 MPL-2.0 / GPL 系列全文识别与精确 `SPDX_TEXT_CONFLICT` 反证，Copyleft 仍保持非 `SUPPORT`。
- **后续版本**将本地 Qwen3 的受控结构化输出接入 v4 增量研判与解释，改进 Docker 及 Linux/macOS 安装启动流程，并扩大 Go、Rust、Java 等生态覆盖。

OpenGuard 自有代码采用 [Apache-2.0](LICENSE)。第三方组件按各自许可归属，见 [RESOURCE_USAGE.md](RESOURCE_USAGE.md)。
