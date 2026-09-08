# 最小本机部署

当前提供两个常驻容器：`web`（生产静态文件与同源代理）、`api`（现有单进程 FastAPI、ZIP dispatcher、SQLite、报告）。API 复用 Dockerfile.scanner 的工具阶段，在现有 ZIP 生命周期内执行 ScanCode/Syft；scanner 保留为按需独立工具检查。Compose 默认启用 ZIP；AI、公开 Git 默认关闭，可按下文显式启用。

## 启动

准备 Docker Engine + Compose，或按[官方 Mac 安装说明](https://docs.docker.com/desktop/setup/install/mac-install/)安装 Docker Desktop。首次构建需要联网下载官方基础镜像和依赖；后续运行不安装目标项目依赖。工具镜像约需数 GB 磁盘空间，建议 Docker 可用内存至少 6 GB；这是配置建议，尚未测定最低资源需求。

在仓库根目录运行：

```bash
docker compose -f deploy/compose.yaml up -d --build --wait
```

在 **Chrome** 打开 <http://127.0.0.1:8080/app/new-scan>，选择 ZIP 并提交。含 npm 依赖的输入可完成资源、待核验风险和报告；缺少许可证声明保留 NOASSERTION，工具失败或漏扫则显示部分完成。Web 仅监听本机回环，API 不映射宿主端口。无需账号、API 密钥或新增接口。

端口占用时可在命令前加 `OPENGUARD_WEB_PORT=8081`。Docker CLI 未加入 PATH 时，使用 Docker Desktop 中配置的 CLI 路径；不要修改应用安全策略或跳过签名检查。

## 实际验收与重建

以下只使用 Python 标准库。输出目录应在仓库外，包含生成的 ZIP、任务 ID 和报告摘要：

```bash
python3 deploy/smoke.py --external-scanners --output /tmp/openguard-compose-check
# 可把上一步生成的 compose-demo.zip 用 Chrome 页面再次上传。
docker compose -f deploy/compose.yaml up -d --force-recreate --no-deps --wait api
python3 deploy/smoke.py --output /tmp/openguard-compose-check --verify
```

首条验收真实 SPA 深链接、ZIP 完成、三个资源（含 Syft 识别的项目自身）、pending 许可证、两工具版本和来源 SHA、风险/Evidence、四报告 SHA-256、缺声明输入、路径穿越 ZIP 失败、未知任务 404；第二次只读验证重建后原任务和四报告字节相同。只重启 API 时 nginx 通过 Docker DNS 重新解析服务地址。

```bash
docker compose -f deploy/compose.yaml ps
docker compose -f deploy/compose.yaml logs --tail 50 api web
docker compose -f deploy/compose.yaml stop
# 移除容器但保留 data 卷：
docker compose -f deploy/compose.yaml down
```

不要使用 `down -v`，除非确实要永久删除扫描和报告。数据存于 `data` named volume，首次从镜像初始化 UID/GID 10001、0700；运行时不以 root 修复权限。已有卷权限错误应先备份并核对，不应放宽后端权限检查。API 和 Web 根文件系统只读，临时区可写但不可执行，不挂 Docker socket 或用户目录。

## 扫描工具环境

```bash
docker compose -f deploy/compose.yaml --profile tools build scanner
docker compose -f deploy/compose.yaml --profile tools run --rm scanner
```

默认执行 `tool-smoke.py`：临时生成 MIT 文本和 npm lock，真实执行 ScanCode 许可证扫描与 Syft SBOM，核对 MIT、相对 LICENSE 定位、`pkg:npm/is-number@7.0.0` 与 lock 来源，并输出原始 JSON 的 SHA-256。不运行样例代码、不安装样例依赖、不联网扫描；容器 `network_mode: none`、非 root、只读、无额外 capability、4 GB 内存/2 CPU 上限，输出不保存进仓库。

ScanCode 官方 Linux 包包含 x86_64 wheels，因此 **API 和 scanner 固定 linux/amd64**；Apple silicon 通过 Docker 的 Linux amd64 支持运行。Web 使用本机架构，API 的 /opt/api venv 与 ScanCode venv 分离。

| 工具 | 锁定版本 | 官方 Linux 包 SHA-256 |
|---|---|---|
| [ScanCode Toolkit](https://github.com/aboutcode-org/scancode-toolkit/releases/tag/v32.5.0) | 32.5.0 / Python 3.12 / amd64 | `638adcd0af576d1f4d5b64dde228724b3ca4fdee2c4de20d88e4356be353f027` |
| [Syft](https://github.com/anchore/syft/releases/tag/v1.51.0) | 1.51.0 / linux_amd64 | `2a2e837a2c8d59ec9af5472ee22d3b04ee463c4e44476ecf993fd1e5ab6ebc7f` |

下载后先校验再解包；工具与随包许可证保留在镜像，仓库不存安装包。ScanCode 使用官方发行包的离线 wheels，构建期预热许可证索引，运行缓存仅写 `/tmp`。Syft 更新检查关闭。基础 Python、Node、nginx 镜像按 Dockerfile 中的 manifest digest 固定；前端使用既有 pnpm 锁文件，后端沿用 pyproject 的精确直接依赖。系统包和后端传递依赖尚非完整离线锁，不能宣称两次镜像构建必然逐字节一致。

## 本轮实测边界（2026-09-05）

- Apple silicon Docker Desktop 4.89.0、Engine 29.7.2、Compose 5.5.0；Docker 官方包摘要、签名与公证核验通过。
- API/Web 镜像构建与健康检查通过；Python 3.12.14、nginx 1.30.4；真实 HTTP 9 项和容器重建后四报告摘要通过。
- Chrome **extension 插件**完成 ZIP 选择、提交、完成报告与页面恢复；JSON 下载点击后插件未返回 download 事件，下载管理页被插件策略禁止，浏览器保存结果未确认。下载接口/文件内容另由 HTTP 四格式摘要验证，不能混记成 Chrome 保存已验。
- 断网 amd64 scanner 真实 MIT 与 npm SBOM 检查通过。本轮 API 工具事实接线及真实 Chrome 报告已通过；AI 资产、Compose 内 Ollama/Git、陌生机复现仍未完成。

工具版本在调用前核验，ScanCode 文件覆盖及两工具 locator 必须匹配 A2 inventory，Evidence SHA 来自封印文件。根 LICENSE 只作文件候选，不自动赋给依赖。宿主机开关 OPENGUARD_ENABLE_EXTERNAL_SCANNERS 默认 0，Compose 明确启用；接受时固定开关，旧排队任务仍关闭。API 使用现有 Compose 网络，只有独立 scanner probe 设置 network_mode:none，不能声称 API 子进程拥有单独网络隔离。

## 模型引用样例

```bash
python3 deploy/smoke.py --external-scanners --ai-assets --output /tmp/openguard-model-check
# 在 Chrome 上传输出目录中的 compose-demo.zip。
```

该样例复用同一验收脚本，增加 README 中的 Qwen/Qwen3-4B-Instruct-2507 官方引用和已有 Ollama 标签，不包含权重或推理代码。预期为三个软件资源与一个模型，四格式报告都有模型条目、文件行号和来源 SHA。模型保持 NOASSERTION/pending，不把本机安装或旁边 LICENSE 当成授权证据。

只识别被扫描 ZIP 中的明确引用，不读取操作者模型目录、不运行模型、不抓取远程许可证。完整 HTTPS 仓库链接可识别；带查询、fragment、子路径或尾斜杠链接保守忽略。文本文件受 4 MiB/文件、16 MiB/总读取、4096 文件与 A2 剩余额度共同限制（2026-09-07 更新），跳过或无法解析时显示不完整诊断；不承诺任意项目覆盖率。

下一步按执行书验收一个真实公开项目的完整 P0 链，再收口首批样例与陌生机复现。

## 固定公开项目与本机 Qwen3

公开验收样例为 [smolagents 固定提交](https://github.com/huggingface/smolagents/tree/a3df1a21db6045aa9be15b4bdf2067041100e96a)，
下载 [该提交 ZIP](https://github.com/huggingface/smolagents/archive/a3df1a21db6045aa9be15b4bdf2067041100e96a.zip) 到仓库外。
原始 ZIP SHA256 为 `c486d41688b937e208393b95e70fc7293c555b046f4284a8fca7a925fe6ef4a9`。
标签v1.0.0与pyproject自述1.1.0.dev0不同，复现以完整commit及ZIP摘要为准。
不安装其依赖或执行其源码，根Apache-2.0不继承给模型、数据集或依赖。

在已准备锁定模型的 Mac 上启动原有 Ollama（版本与模型见A5规格），只监听回环。若已有服务则复用；将日志写入本机文件，避免长扫描被终端输出阻塞：

```bash
umask 077
OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 OLLAMA_NOHISTORY=1 nohup ollama serve > /tmp/openguard-ollama.log 2>&1 < /dev/null &
# 另一个终端；先完成AI关闭基线：
docker compose -f deploy/compose.yaml up -d --build --wait
python3 deploy/smoke.py --public-zip /tmp/smolagents.zip --output /tmp/openguard-public-noai
# 显式启用 Docker Desktop 到宿主机已有模型的连接：
OPENGUARD_ENABLE_AI=1 OPENGUARD_OLLAMA_DOCKER_HOST=1 docker compose -f deploy/compose.yaml up -d --no-deps --wait api
python3 deploy/smoke.py --public-zip /tmp/smolagents.zip --expect-ai --compare-to /tmp/openguard-public-noai/report.json --output /tmp/openguard-public-ai
```

也可在 Chrome 上传同一ZIP，然后将任务ID传入上述脚本的 `--scan-id`，避免重复扫描。
脚本校验四个明确模型/数据集引用、来源SHA/行号、软件依赖、未知授权、AI身份/证据引用与四格式报告；
临时输出包含任务ID、原始报告和SHA receipt，失败记录不覆盖为成功。`--verify`可复核重建后的四格式字节。
此验收不是完整识别准确率评测。2026-09-07 起 A5 按等价上下文共享生成，原逐条耗时属于下方历史记录；模型失败仍明确降级并保留确定性扫描和报告。当前 Windows 验收等待上限见后文，不改变后端单次推理限额或增加自动重试。

2026-09-06 实测：AI 关闭 29.33 秒；锁定 Qwen3 开启 963.30 秒，227 组件、4 引用资产、283 证据、231 待核验提示和 231 待复核建议。确定性事实对照、Chrome 正文及容器重建后的四格式 SHA 均通过。整批模型输出曾因非法 JSON Pointer 降级；只改提示词引导，原校验与原子降级保留。实际建议质量尚未经 golden 标注评测，不能将结构校验通过解释为语义全部准确。

## 扫描组员首批 P0 样例

复用现有验收脚本的 `--bench-cases benchmarks/cases/static-ai-assets-v1.json`，从真实 ZIP HTTP 接口验证4个正例与1个无资源负例；`--verify`复核原任务，不重复扫描。先关闭AI，输出放仓库外。完整命令及限制见[Bench实测记录](../benchmarks/static-ai-assets-evidence.md)。负例按当前契约failed且无报告，不把它包装成空扫描成功。

## 公开 Git 的最小部署验收

API 镜像使用 Debian bookworm 官方 `git` 包；本次实测 `1:2.39.5-0+deb12u3`，运行版本 `2.39.5`。发行版来源见[Debian Git 包](https://packages.debian.org/bookworm/git)，许可证及来源说明随包保留在 `/usr/share/doc/git/copyright`；系统包尚不是完整离线锁。Python API/扫描工具版本沿用既有配置。

```bash
# 首次构建包含 Git 的 API；默认仍不开放 Git 输入执行。
OPENGUARD_ENABLE_PUBLIC_GIT=1 docker compose -f deploy/compose.yaml up -d --build --wait
# Chrome -> 新建扫描 -> GitHub仓库 -> 提交真实扫描：
# https://github.com/pypa/sampleproject.git
python3 deploy/smoke.py --public-git https://github.com/pypa/sampleproject.git --scan-id <Chrome任务ID> --output /tmp/openguard-public-git
# 省略 --scan-id 会新建一次扫描；不要重复提交同一验收任务。
OPENGUARD_ENABLE_PUBLIC_GIT=1 docker compose -f deploy/compose.yaml up -d --force-recreate --no-deps --wait api
python3 deploy/smoke.py --output /tmp/openguard-public-git --verify
```

若要保留此前本机Qwen3连接，在每次Compose up前同时设置 `OPENGUARD_ENABLE_AI=1 OPENGUARD_OLLAMA_DOCKER_HOST=1`；否则沿用默认AI关闭。公开Git与ZIP均复用原manifest许可证、明确AI引用、真实ScanCode/Syft和报告阶段。没有增加Git队列恢复或新接口；不要在Git运行中重建API，进程中断后的Git自动恢复不在本任务范围。

2026-09-06 Chrome实测PyPA sampleproject的实际revision为 `621e4974ca25ce531773def586ba3ed8e736b3fc`：13.84秒，9组件/11证据/9待核验提示，四格式报告通过。本批AI关闭，没有生成新的Qwen建议。`--expected-revision`可验证预先记录的HEAD；API仍读取公开默认分支，未来分支变更应检查新revision，不能称URL已永久锁定。

11条Evidence与同revision独立归档原文件SHA一致；HTTP、回环/元数据IP、query URL在接收前拒绝，保留域名 `.invalid` 摄取失败且无报告，成功/失败后工作目录为空。容器实际UID10001、cap=0、NoNewPrivs=1、Seccomp=2、只读根、4GiB内存/128进程、私有named volume与noexec临时区通过。初次检查把Docker HostConfig.Binds中的named volume误当宿主目录，随后依据Mounts.Type核实未挂载宿主目录；未修改容器权限。

这些证据只证明当前Mac上的Linux Compose最小部署。工具子进程仍使用API容器网络，不宣称逐子进程网络隔离、所有攻击语料或陌生机验收完成；pending提示不等于违规确认或授权通过。

## 两台 Windows 的共同验收（2026-09-08，等待实测回执）

两台机器分别独立执行；都验证 AI 关闭的真实 Git、ZIP、证据和报告，至少一台再验证真实 Qwen。Mac 实测不代替 Windows 通过。以下使用 **Windows PowerShell**，准备 Git、Python 3 和处于 Linux containers 模式的 Docker Desktop；先确认 `docker version` 同时有 Client/Server，`docker compose version`、`py -3 --version` 可用。安装中涉及管理员认证、WSL 或重启，由设备操作者完成，不关闭系统防护。已有目录不要覆盖，首次使用新目录：

```powershell
git clone --branch integration/p0 https://github.com/mumingce-star/OpenGuard.git OpenGuard
cd OpenGuard
git checkout --detach b86658e37286f132bf098f0e7642bf25e557ffa9
git rev-parse HEAD
$env:OPENGUARD_ENABLE_PUBLIC_GIT = "1"
$env:OPENGUARD_ENABLE_AI = "0"
$env:OPENGUARD_OLLAMA_DOCKER_HOST = "0"
docker compose -f deploy/compose.yaml up -d --build --wait
docker compose -f deploy/compose.yaml ps
$Evidence = Join-Path $env:TEMP ("openguard-acceptance-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
New-Item -ItemType Directory -Path $Evidence
```

固定提交包含容量准入及等待检查；后续说明更新不代表必须改用分支最新代码。不要从仍为早期基线的 main 开始，不复制 Mac 镜像或 data 卷。每条命令成功后才继续；失败保留输出，不通过重复提交覆盖失败。构建与下载耗时不计入扫描时间；环境准备失败单独记为部署阻断。

### 固定输入及最长等待

| 用例 | 配置 | 从创建任务被接受起的最长观察等待 |
|---|---|---|
| 已有小 ZIP 安全冒烟（含缺声明、恶意 ZIP 子任务） | AI 关闭 | 每个子任务 900 秒 |
| PyPA sampleproject 默认分支，记录实际 revision | AI 关闭 | 900 秒 |
| 上文固定 smolagents ZIP，完整 SHA 必须相同 | AI 关闭 | 900 秒 |
| 同一 smolagents ZIP 与本机 AI 关闭报告对照 | 真实 Qwen | 1200 秒 |

预算依据：现有 ScanCode 总预算 360 秒、Syft 120 秒，Git 获取另有预算；900 秒为这些阶段及文件处理、报告收尾保留余量，AI 用例额外留 300 秒。AI 仍按等价上下文共享生成，每次调用 30 秒，不因风险数量逐条扩展。**这些是本批样例的验收观察上限，不是后端全链路硬超时，也不是每次都应耗时这么久的性能目标。** 单次状态 HTTP 读取最多 15 秒，遇到网络错误可更早失败；超时检查可能在正在进行的读取返回后才打印，但超时后收到 completed 仍判失败。

不得自行延长上限、排队多个验收任务或用 `--scan-id` 重新起算失败任务的等待时间。超过上限仍 running、失败后执行进程残留、持续阻塞后续正常任务，均不通过。脚本只记录失败，不取消、重放或清除后台任务。

### 两台都执行：AI 关闭

从上文固定提交链接下载 ZIP 至 `$Evidence\smolagents.zip`；不要下载默认分支 ZIP。以下下载与 SHA 不一致应停止，不改验收摘要：

```powershell
Invoke-WebRequest -Uri "https://github.com/huggingface/smolagents/archive/a3df1a21db6045aa9be15b4bdf2067041100e96a.zip" -OutFile "$Evidence\smolagents.zip"
if ((Get-FileHash "$Evidence\smolagents.zip" -Algorithm SHA256).Hash.ToLower() -ne "c486d41688b937e208393b95e70fc7293c555b046f4284a8fca7a925fe6ef4a9") { throw "ZIP SHA mismatch" }
py -3 deploy/smoke.py --external-scanners --ai-assets --wait-seconds 900 --output "$Evidence\small-zip"
$Revision = ((git ls-remote https://github.com/pypa/sampleproject.git HEAD) -split "\s+")[0]
if ($Revision -notmatch '^[0-9a-f]{40}$') { throw "Cannot capture Git revision" }
py -3 deploy/smoke.py --public-git https://github.com/pypa/sampleproject.git --expected-revision $Revision --wait-seconds 900 --output "$Evidence\git"
py -3 deploy/smoke.py --public-zip "$Evidence\smolagents.zip" --wait-seconds 900 --output "$Evidence\zip-noai"
```

Git 是默认分支实扫，记录 `$Revision` 和 receipt 的实际 revision；两台不同时运行导致上游变更时交回差异审核，不假称同一输入。固定 ZIP 则必须完全相同。小 ZIP 脚本会创建多个安全子任务；receipt 绑定正常主任务，accepted/status/wait 可能对应最后一个子任务，回执时保持整个目录。

没有 queued/running 任务后，保持上述三个开关，重建 API 并确认旧报告保留：

```powershell
docker compose -f deploy/compose.yaml up -d --force-recreate --no-deps --wait api
py -3 deploy/smoke.py --output "$Evidence\git" --verify
py -3 deploy/smoke.py --output "$Evidence\zip-noai" --verify
```

`--verify` 不新建扫描。若任务超时，先保留 `accepted.json`、`status.json`、`wait.json`（已有者）及终端错误，再收集 `docker compose -f deploy/compose.yaml logs --tail 100 api` 和 `docker compose -f deploy/compose.yaml top api`。不要重建来掩盖超时或先杀进程再声称无残留；负责人依据这些证据安排恢复及后续正常任务检查。进程列表本身不足以证明任务归属，有疑义记待核验。

### 至少一台追加：真实 Qwen

按 [A5 模型运行规格](../docs/spec/a5-ollama-transport.md) 准备官方 Ollama **0.33.3**、`qwen3:4b-instruct-2507-q4_K_M`，完整模型摘要必须为 `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`。版本/模型不符应记录阻断，不解除身份校验。模型准备与首次下载不计扫描等待；不使用模拟建议替代真实 Qwen。Windows 上模型安装与 Docker 到宿主的连接尚待该机器验证，无法连接时回传脱敏错误，不开放公网端口或关闭防火墙。

无活动任务时，在同一 PowerShell 中执行：

```powershell
$env:OPENGUARD_ENABLE_AI = "1"
$env:OPENGUARD_OLLAMA_DOCKER_HOST = "1"
docker compose -f deploy/compose.yaml up -d --no-deps --wait api
py -3 deploy/smoke.py --public-zip "$Evidence\smolagents.zip" --expect-ai --compare-to "$Evidence\zip-noai\report.json" --wait-seconds 1200 --output "$Evidence\zip-ai"
```

必须检查真实 AI 身份、建议关联本风险 Evidence、AI 前后确定性事实相同和四报告摘要。脚本结构检查不代替 12 条人工质量复核。模型失败的 partial 报告可以保留，但不算本项 AI 成功。

### Chrome 实际保存与回传

在 Chrome 打开 `http://127.0.0.1:8080/app/scans/实际scan_id/report?mode=api`，scan_id 来自 git 或 zip-noai 的 receipt。确认真实接口模式，检查资源、风险与原文件 Evidence；分别保存 HTML、JSON、CSV、资源清单到明确目录。以 `Get-FileHash -Algorithm SHA256 -LiteralPath "实际文件路径"` 核对**同一任务** receipt 的 `reports` 对应摘要，并记录字节数。浏览器被拦截记阻断，不关闭保护；HTTP 下载不算 Chrome 保存成功。不要重新扫描只为下载报告。

每台回传：系统版本/CPU架构、Docker/Compose/Python版本、固定代码 SHA、三次 AI 关闭命令的输出及整个输出目录、重建后两条 PASS、Chrome 四文件 SHA/字节数及页面截图；AI 那台追加模型版本/摘要、AI 命令输出和 zip-ai 目录。失败也原样回传，不只发成功截图。排除账号、令牌、完整环境变量及个人目录内容；负责人汇总后由 Root 判定通过/失败/待核验。两台结果、人工复核和最终冻结未齐前，不宣布 P0 通过。

## Chrome 下载排障记录（2026-09-06）

现有报告下载响应的CSP现为`sandbox allow-downloads; default-src 'none'; base-uri 'none'; form-action 'none'`，仅允许预期附件下载，保留其他限制；不改变报告字节、摘要、接口或Chrome设置。依据[MDN sandbox文档](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/sandbox)，未包含allow-downloads的sandbox会限制下载。

本机用户在修复前后均确认Chrome显示“贵组织屏蔽了该文件，因为它不符合安全政策”。修复后手动点击也受阻，指定Downloads目录未出现报告；因此不能断言CSP是此次唯一根因，浏览器落盘门禁仍被组织策略阻塞。需由有权限的管理员按实际策略处理，或之后在符合策略的另一台设备正常验收；不关闭保护、不绕过组织限制，也不以命令行保存冒充Chrome下载。

61项相关API/报告测试通过；本次API重建后原Git及ZIP/Qwen四格式摘要均保持。资源/安全清单核对见docs/02-resource-inventory.md及docs/security/a2-security-acceptance.md第9节：检查完成不等于最终冻结。

## 2026-09-06 API CPU 配额验收

API服务现沿用独立scanner的`cpus: 2`，只改变原Compose一项配置。保持Git/AI/Docker-host原开关重建API，私有数据卷未变，健康检查通过。Docker NanoCpus=2000000000；容器cgroup v2 `cpu.max=200000 100000`。4个自建Python忙循环各运行约4秒后正常退出，cpu.stat增量nr_periods=41、nr_throttled=41、usage_usec=8272191，证明实际发生节流；无目标代码执行或新扫描。内存4GiB、128PID、UID10001、只读根、cap_drop ALL及no-new-privileges保持。

原Git和ZIP/Qwen两份receipt各执行一次`deploy/smoke.py --verify`，四格式摘要均保持。该检查证明配额与原报告留存，不声称已复跑真实扫描性能或完成所有资源隔离。Chrome下载详情本轮直接显示“贵组织屏蔽了此文件，因为它不符合安全政策”，无正常保存入口，真实四格式浏览器落盘仍待合规策略环境验收；没有改策略、改传输路径或借演示文件替代。

## 2026-09-06 API Python 运行依赖锁定

复用backend/pyproject.toml的`tool.openguard.api-lock.requirements`保存已验收API环境的15个直接/间接运行包精确版本，适用CPython3.12/Linux amd64；project.dependencies保持原5个直接依赖，不把间接包改为业务直接依赖。API镜像从空venv按该列表以`--no-deps`安装，构建先要求全部直接精确声明被包含，再运行`pip check`，缺失/不兼容闭包使构建失败，不静默解析新间接版本。后续升级必须同步更新原列表并重建验证，不新增平行requirements文件。

本次安装层重新执行成功；重建容器实际15包集合与锁定列表严格相等，运行pip check通过（非root缓存目录不可写仅导致pip禁用缓存，未sudo或放宽权限）。Git和旧ZIP/Qwen两组receipt各verify四格式SHA保持，cpu.max仍200000 100000，API健康。不重新扫描或推理。pip自身沿用固定Python基础镜像的venv引导版本；此项是API运行依赖版本锁定，不宣称新增发行包hash校验、Dev/ScanCode环境锁定或Debian系统包快照锁定。

### 真实 Chrome 四格式落盘通过（2026-09-06，AMENDMENT）

用户手动查看后报告没有下载相关政策；此前仅据“组织屏蔽”文案归因过早。普通Chrome原生页面操作可以弹出保存对话框，用户完成原文件保存；没有更改安全设置、传输路径、Blob或文件名。原Git任务scn_fed61b87-fc58-4e70-a7af-0d0e5ead9330的HTML6722字节、JSON28846字节、CSV和资源清单各2024字节均实际落盘，SHA与本文件既有Git验收记录全部一致。JSON可解析且任务ID一致，两CSV均7列/9资源行。具体历史拦截触发机制未被证明，不宣称所有浏览器环境已修复；当前Mac四格式正常下载已通过，旧阻塞状态由此结果更正。文件留在用户下载目录，不上传Git，不重复生成扫描。

## 2026-09-06 Debian Git 精确构建版本

API镜像在原Dockerfile中明确安装`git=1:2.39.5-0+deb12u3`与配套`git-man=1:2.39.5-0+deb12u3`，安装后分别通过dpkg-query核对精确发行包版本，继续使用Debian仓库默认签名校验。版本来自原已验收镜像，不升级Git，不添加替代下载源或忽略签名参数。上游移除该版本时构建应失败，由后续明确升级任务处理，不自动退回无版本安装。

该固定只约束Git与git-man，不代表所有Debian系统依赖、仓库快照或整个镜像字节永久可复现。版本固定也不替代后续安全更新审查；本轮不引入额外仓库快照架构。

## API／工具文件描述符上限（2026-09-06）

现有Compose api与scanner明确设置 `ulimits.nofile.soft: 256`、`hard: 256`，沿用P0安全表默认值；每个进程继承此限额，非容器fd总数。配置需要重建容器才能生效；保持原有AI/Git环境开关和data卷，不使用down -v。不要通过放宽capabilities或自行提高限制让测试通过。

复用现有命令验证（自建小输入，不下载/执行目标依赖）：

```bash
docker compose -f deploy/compose.yaml config --quiet
docker compose -f deploy/compose.yaml --profile tools run --build --rm scanner
docker compose -f deploy/compose.yaml exec -T api python /opt/openguard/tool-smoke.py
```

tool-smoke先检查真实继承的256/256、拒绝提高硬限制、到上限返回EMFILE及释放后恢复，再运行原两工具样例。运行环境若有Rosetta额外fd，按/proc实际占用计入256，不固定可新增数为253。最终API及独立tools均为initial6/opened250；两工具样例通过。原Git/ZIP-Qwen receipt的smoke --verify各通过，API健康/2CPU保持。网络deny-egress和data卷任务磁盘配额仍未通过；详见原安全表9.4，不将本项外推为完整安全冻结或异机验收。

## 工作目录临时磁盘硬上限（2026-09-06）

API现将现有 `/var/lib/openguard/workspaces` 挂为1GiB tmpfs，uid/gid10001、0700、noexec/nosuid/nodev。Git物化和ZIP工作副本复用该路径，无新API或目录配置。该容量为所有在途工作目录共享总额，也约束单个任务最大占用；不是每任务独享1GiB，不保证并发任务各自预留空间。tmpfs占用受API已有4GiB内存限制约束，磁盘和内存资源不是相互独立。

数据库、reports、dispatch以及待处理ZIP的uploads继续保留在原data卷；容器重建只清空临时工作树，queued恢复仍使用持久上传。部署前须确认没有queued/running任务且原workspaces为空，防止遮蔽旧树；有残留时先核查生命周期，不删除用户数据，不执行down -v。保持原AI/Git环境开关后用既有Compose up更新api。

此项只约束工作目录；工具 `/tmp` 另有256MiB上限，持久uploads/report累计占用不计入1GiB，不能声称所有存储都有任务配额或完整worker临时存储预算已冻结。

真实写满验收复用tool-smoke中的check_workspace_quota，只允许在空的独立 `/quota` tmpfs执行。以下一次性容器不挂载data卷，临时占用约1GiB，退出自动回收：

```bash
docker run --rm --platform linux/amd64 --network none --read-only --cap-drop ALL --security-opt no-new-privileges --memory 4g --cpus 2 --pids-limit 128 --ulimit nofile=256:256 --tmpfs /tmp:size=256m,mode=1777,noexec,nosuid,nodev --tmpfs /quota:size=1g,uid=10001,gid=10001,mode=0700,noexec,nosuid,nodev --entrypoint python openguard-api -c 'import json,runpy; print(json.dumps(runpy.run_path("/opt/openguard/tool-smoke.py")["check_workspace_quota"]()))'
```

原ZIP生产摄取在剩余1MiB（接收失败）和3MiB（接收成功、解压失败）均触发实际ENOSPC，返回scanner_failed/workspace_write_failed，任务树清空；释放填充文件后同一服务成功摄取并清理。最终API挂载容量1073741824字节、权限正确；小ZIP在实际挂载路径成功/清理，原Git/Qwen各四格式报告verify通过，无新公开扫描/推理。运行时无用户数据卷参与写满测试。

## 扫描子进程禁网（2026-09-06）

现有API/tools镜像默认设置 `OPENGUARD_SCANNER_SANDBOX=/opt/openguard/scanner-no-network`。生产run_json_tool在原固定命令前加原生启动器，目录fd、cwd、进程组和超时机制保持。启动器安装不可撤回且后代继承的seccomp过滤器后才exec扫描器：只允许AF_UNIX socket/socketpair用于扫描器本地IPC，拒绝IPv4/IPv6及其他网络family，并拒绝io_uring_setup防止异步网络调用绕过；未知架构及x32 ABI失败关闭。无Python preexec线程风险、无新服务/接口，不添加capability或关闭Docker安全配置。

首次尝试在amd64/Rosetta进程直接装libseccomp失败（load=-125/errno22），因此启动器必须按Docker BUILDPLATFORM编译为构建主机原生架构，并静态链接后复制进现有amd64扫描镜像。新增源码只在deploy/scanner-no-network.c，GCC只在构建阶段；随包运行库版权保留。**不同架构设备应从源码重新build；不要把本机生成的混合架构镜像导出给另一种架构使用。** 原生Linux amd64实现分支已包含，实际异机验收仍待Windows设备执行。

镜像中的默认环境变量不可移除以规避过滤器。若路径不符、启动器缺失、过滤器加载或exec失败，runner返回失败/不可用，不直接运行扫描器。未配置该环境变量的宿主开发调用不具备本节保障，仅当前Compose镜像profile为已验收入口。

复用原验收脚本（API正常运行，不访问外部网络）：

```bash
docker compose -f deploy/compose.yaml exec -T api python -c 'import runpy; print(runpy.run_path("/opt/openguard/tool-smoke.py")["check_network_sandbox"]())'
```

实测IPv4/IPv6的TCP/UDP四类libc.socket均EPERM，后代exec进程也被拒绝，AF_UNIX socketpair可用，父进程仍可创建网络套接字。最终API固定ScanCode/Syft入口和传递目录fd的正例通过；分别检测Apache-2.0和is-number7.0.0。原Git TrustedEgress成功获取PyPA sampleproject revision621e4974ca25ce531773def586ba3ed8e736b3fc并清理；原模型qwen3:4b-instruct-2507-q4_K_M短推理done=true。旧Git/Qwen两组四SHA保持，APIhealthy。

此项是扫描子进程及后代的网络创建边界；不等于网络namespace、跨任务文件/Unix IPC隔离、持久存储预算或完整P0安全验收完成。生产仅传递受控目录fd，不能扩展为传递已有网络socket。Git获取器和Qwen调用不使用扫描启动器，仍遵循各自原有网络门禁。


## 扫描子进程跨任务读取边界（2026-09-06）

原启动器同时施加Landlock文件限制和原seccomp网络限制。要求运行内核Landlock ABI至少3（含truncate保护），本机Docker原生ARM实测ABI8；不支持或规则失败时拒绝执行，不降级为无限制扫描。运行时通过原单个任务目录fd给予当前输入只读权限，每次调用独立临时目录承载HOME/TMP/ScanCode缓存，结束后回收。只开放必要运行库、特定系统信息文件及原生转译父进程的可执行文件inode；不开放整个/proc、其他任务、持久data或共享/tmp树。依据：[Linux Landlock文档](https://docs.kernel.org/userspace-api/landlock.html)。

ScanCode固定入口使用既有串行模式 `--processes 0`，避免进程池对共享信号量的依赖；不开放/dev/shm。当前Rosetta任意后代再次exec可能因新的/proc/self/maps不可读而失败关闭，不能宣称任意子程序兼容；本轮验证fork继承以及当前固定ScanCode/Syft入口真实输出。此前禁网节的后代exec结果属于上一版本，本版本继承探针明确为fork。

复用原脚本验证合成任务边界（不读取真实任务内容）：

```bash
docker compose -f deploy/compose.yaml exec -T api python -c 'import runpy; print(runpy.run_path("/opt/openguard/tool-smoke.py")["check_file_sandbox"]())'
```

本轮实际workspaces挂载中六种读取绕行均被内核拒绝，当前输入可读不可写、私有temp可写、fork后代受限，退出工作目录为空。最终镜像ScanCode识别apache-2.0，Syft识别pkg:npm/is-number@7.0.0；155相关回归通过。旧Git/Qwen两组四报告SHA保持，API健康；本轮不重复公开扫描或推理。该边界不等于所有文件元数据操作、Unix IPC或完整P0安全矩阵均已隔离。宿主未配置沙箱的开发运行仍不具备本节保障。

## 真实 Git 扫描的运行与等待（2026-09-07）

Docker Desktop 必须处于运行状态。使用 Git 和本机 Qwen 时，重建、启动都应保留原有三个开关：

```bash
OPENGUARD_ENABLE_PUBLIC_GIT=1 OPENGUARD_ENABLE_AI=1 OPENGUARD_OLLAMA_DOCKER_HOST=1 docker compose -f deploy/compose.yaml up -d --build --wait
```

执行上面的重建命令前，应确认没有 queued/running 任务；现有公开 Git 任务不支持重启后续跑。该命令不删除数据卷。API/Web 健康不代表宿主 Ollama 和锁定模型必然可用，仍须完成一次真实扫描确认。

Git 获取和外部工具执行共用现有 ingestion 阶段，因此 5% 可能持续数分钟。AI 对同类待核验风险共享一次中文核验流程，每条风险保留自己的证据关联；特殊规则继续逐条生成。页面和报告将共享内容标为“同类风险AI核验建议，未逐项确认许可”。生产入口每次调用最多30秒、Qwen上下文8192，不设置只处理前几条的上限，不重放已发送的生成请求。模型运行内存本机实测约3.9GB；减少调用次数不会消除扫描工具本身耗时。

终态 partial 表示扫描已经结束并保留部分结果，不能等同于卡住，也不能当作完整扫描成功；报告已生成时可直接查看四种报告，具体未完成内容见提示。前端复用当前任务报告内的 Evidence 快照，缺少的证据才通过原接口补取。


2026-09-07 扫描覆盖修复：ScanCode主扫描和补扫共用360秒总预算，Git获取及Syft仍各120秒。Python现解析静态字符串dependency-groups，开发依赖与运行依赖分开记录；复杂include-group等仍提示不完整。AI资源扫描按实际剩余字节读取，避免全仓库体积误占额度。大仓库等待时间包含扫描工具及逐条AI建议，旧报告不会自动重新扫描或改写；需要新建扫描验证新代码。

同轮进一步减少重复工作：AI资源文件在批次前后校验整树、逐文件验证Hash后才一次返回；模型输入共享相同Evidence对象，建议引用最多3条相关证据，原报告保留全部证据。该优化不取消Hash检查，也不把未成功生成的AI建议伪装为成功。

当前公开 Git 采用有界扫描：仓库根地址可带 `.git` 或尾斜杠；请每次输入一个地址，不输入分支/文件页面或粘连的多个URL。文件不超过4096时尽量全部选择，更大仓库最多512个候选，优先浅层许可证、依赖清单、锁文件、README；还受16MiB总读取、4MiB单文件及原解析器预算约束。符号链接和子模块不跟随。存在未覆盖内容时结果为“部分结果”，JSON及HTML完整列出未扫描路径、原因和Git对象，不能理解为整个仓库已扫描完毕。网络不可达、私有仓库及超出硬安全上限仍会失败；不会绕过安全检查。

AI请求失败时，扫描事实和其他成功建议保留，失败项明确标记；Ollama不可用不会被伪装为AI成功。共享流程供人工逐项对照证据，不构成授权或合规结论。

### P0 persistent capacity admission (2026-09-08)

The default API factory now checks persistent storage before accepting either Git JSON or ZIP multipart, before consuming the upload body. Default admission watermark: 2 GiB; each queued/running scan plus the proposed scan reserves 256 MiB; available filesystem space must also retain a 512 MiB floor after reservations. Count actual/allocated file size conservatively, deduplicate hardlinks, include reports/uploads/dispatch/SQLite/WAL/SHM and unknown regular files. Exclude workspaces only when it is a separate mounted directory (Compose tmpfs); same-filesystem local workspaces count. Unexpected/unreadable entries fail closed. No existing report is automatically deleted.

POST can now return HTTP 503, existing ErrorEnvelope shape with code `scan_capacity_unavailable` and reason `persistent_capacity_exceeded`, `persistent_capacity_busy` or `persistent_capacity_unavailable`. GET status/evidence/resources/reports remains available. Even an idempotent POST is rejected while admission is unavailable; use GET for an existing task. A simultaneous upload/record-creation window can receive busy and should be retried manually. Queued/running reservations persist across API restart via the registry. A transient filesystem race can conservatively reject a submission.

This is a single-API-process admission watermark and safety headroom, NOT an OS volume quota or a guaranteed per-scan write maximum. Already admitted work, external processes or unbounded registry snapshots can exceed the watermark. Do not deploy multiple API workers claiming the same concurrency protection. Reports and SQLite are not auto-pruned; Owner checks usage and handles retention manually, backing up before any separately authorized removal. Do not delete the data volume to free space. Full physical cumulative quota remains unverified, not silently marked passed.

Before Docker update/deployment verify there are zero queued/running scans and no pending upload. Maintenance interrupts in-process Git work; it is not automatically replayed. Keep the task record and diagnose before any controlled state recovery. After maintenance start the original services, verify health and existing report hashes. Noninteractive `docker desktop update` can take default confirmation and restart immediately: never invoke it during active work. No automatic Git retries are introduced.
