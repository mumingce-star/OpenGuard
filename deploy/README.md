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

只识别被扫描 ZIP 中的明确引用，不读取操作者模型目录、不运行模型、不抓取远程许可证。完整 HTTPS 仓库链接可识别；带查询、fragment、子路径或尾斜杠链接保守忽略。文本文件受 512 KiB/文件、2 MiB/资产读取、128 文件与原 A2 总预算限制，跳过或无法解析时显示不完整诊断。大型 ZIP 的保守预算可能跳过小引用，不承诺任意项目覆盖率。

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
此验收不是完整识别准确率评测。现有A5逐条生成且一条失败会整体降级，较多依赖会增加耗时；
脚本最多等待30分钟，不改变单次推理限额或增加自动重试。模型不可用时仍保留确定性扫描和报告。

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

## 另一台设备的最小复现（待实际设备验收）

2026-09-06 用户确认目前没有另一台设备，因此本门禁尚未执行。同一Mac的新容器、重建镜像或测试通过不能代替异机结果。以下复用已有脚本；不需要新框架、账号、API密钥或复制开发机数据卷。先准备Docker的Linux容器环境、Git及Python 3，使用macOS/Linux或已配置Docker的WSL终端。

在另一台设备的新目录获取已验收版本，避免从仍为早期基线的main开始：

```bash
git clone --branch feat/a7-public-git-deploy-acceptance https://github.com/mumingce-star/OpenGuard.git OpenGuard
git -C OpenGuard checkout --detach 341dc348670a558fae35d699b204e4d927f898fb
cd OpenGuard
OPENGUARD_ENABLE_PUBLIC_GIT=1 OPENGUARD_ENABLE_AI=0 OPENGUARD_OLLAMA_DOCKER_HOST=0 docker compose -f deploy/compose.yaml up -d --build --wait
python3 deploy/smoke.py --external-scanners --ai-assets --output /tmp/openguard-other-zip
python3 deploy/smoke.py --public-git https://github.com/pypa/sampleproject.git --output /tmp/openguard-other-git
OPENGUARD_ENABLE_PUBLIC_GIT=1 OPENGUARD_ENABLE_AI=0 OPENGUARD_OLLAMA_DOCKER_HOST=0 docker compose -f deploy/compose.yaml up -d --force-recreate --no-deps --wait api
python3 deploy/smoke.py --output /tmp/openguard-other-zip --verify
python3 deploy/smoke.py --output /tmp/openguard-other-git --verify
```

两个初始命令各创建一个任务；`--verify`只复核原任务。PyPA默认分支可能变化，以输出receipt的实际revision为准；如果验收失败，保留原输出，不反复创建任务。此首轮关闭AI，不要求另一台设备额外安装模型，也不据此声称异机AI已通过。

Chrome打开 `http://127.0.0.1:8080/app/new-scan`。可用receipt中的scan_id打开现有任务 `/app/scans/实际scan_id/report?mode=api`，确认真实接口、资源/风险/Evidence；通过四个下载链接各保存一次。文件名为 `openguard-实际scan_id.html`、`.json`、`.csv`和`.resources.csv`（以浏览器实际名称为准）。核对文件SHA与同一任务receipt中的对应reports摘要；不要与开发机不同任务的摘要比较，也不要把HTTP下载代替浏览器落盘。

回传最小证据即可：设备系统与CPU架构、Docker/Compose版本、代码commit、两个命令的原始成功或失败输出、两个receipt.json、重建后两条PASS，以及Chrome实际文件的格式/字节数/SHA。不要回传用户名、主机名、完整环境变量、凭据、Docker账户或个人目录内容。只在上述结果实际取得后更新异机状态；准备好文档本身不算验收完成。

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
