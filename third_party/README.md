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
| Git | 外部源码传输/对象读取工具 | `2.50.1 (Apple Git-155)`（当前 macOS profile） | https://git-scm.com/downloads；https://git-scm.com/docs/git-clone | GPL-2.0-only；以实际发行包 LICENSE 为准 | A2-3a 只用固定绝对可执行文件执行无 checkout 的公开 HTTPS 浅克隆、`ls-tree` 与 `cat-file --batch` | 若随部署镜像分发 Git，必须保留许可证和对应源码提供义务；不得把当前 Apple 版本外推为最终 Linux 镜像版本 | OpenGuard 自研 URL/DNS/TrustedEgress、进程 allowlist、对象路径/type/配额校验、物化、inventory 与 provenance；不复制 Git 实现 | 当前本机版本与行为已核验；最终 Linux 镜像的包版本、摘要和许可证文件待 A7 锁定 | 仓库不保存 Git 二进制；部署时使用锁定系统包/镜像并登记摘要 |
| Cloudflare 1.1.1.1 DNS over HTTPS | 公共 DNS 服务 | 公共服务，无软件版本；固定 endpoint `cloudflare-dns.com/dns-query` 与 bootstrap `1.1.1.1`/`1.0.0.1` | https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/make-api-requests/dns-wireformat/；https://developers.cloudflare.com/1.1.1.1/privacy/public-dns-resolver/ | 服务条款与隐私政策适用；不分发服务端软件 | A2-3a 查询公开仓库主机的 A/AAAA，避免本机代理 Fake-IP 污染；只发送 DNS 名称，不发送仓库路径、凭据或扫描内容 | 部署/报告需披露外部 DNS 处理及隐私边界；离线部署应提供管理员审计后的替代解析 profile，而不能静默直连系统 DNS | OpenGuard 自研 TLS/HTTP/DNS wireformat 有界客户端、全部地址公网判定与立即拨号；不复制 Cloudflare 代码 | 已核验官方 DoH 请求方式、bootstrap 和公开解析器隐私页；最终部署前仍需团队复核适用条款 | 不在仓库存放第三方内容；仅公开配置、来源与用途 |
| ScanCode Toolkit | 外部扫描器（可选部署工具） | 32.5.0 | https://github.com/aboutcode-org/scancode-toolkit/releases/tag/v32.5.0 | 软件 Apache-2.0；数据 CC-BY-4.0；内嵌组件各自许可 | 通过受限 JSON Adapter 获取许可证/版权候选，不执行被扫描项目代码 | 部署时保留上游许可证、版本与校验；输出必须继续经过规范化和人工核验 | OpenGuard 自研安全调用边界、相对定位校验与 P0 Evidence 映射，不复制 ScanCode 引擎 | 组员环境已作候选验证；当前 macOS 集成和真实工具输出仍待复核 | 不在仓库存放或自动下载二进制 |
| Anchore Syft | 外部 SBOM 扫描器（可选部署工具） | 1.51.0 | https://github.com/anchore/syft/releases/tag/v1.51.0 | Apache-2.0 | 通过受限 JSON Adapter获取组件候选，不执行被扫描项目代码 | 部署时保留上游许可证、版本与校验；不把候选许可证当作已确认事实 | OpenGuard 自研安全调用边界、相对定位校验、P0映射与跨来源合并 | 组员环境已作候选验证；当前 macOS 集成和真实工具输出仍待复核 | 不在仓库存放或自动下载二进制 |
| Ollama | 本地模型运行时 | 0.33.3 | https://github.com/ollama/ollama/releases/tag/v0.33.3；https://docs.ollama.com/macos | MIT；上游 `LICENSE` | A5 本地 loopback transport；以 `OLLAMA_NO_CLOUD=1`、`OLLAMA_NOHISTORY=1` 运行，只监听 `127.0.0.1` | 分发时保留上游许可证和来源；安装包不进入仓库，不静默升级锁定版本 | OpenGuard 自研 loopback/禁代理/超时/响应封装与 A5-0 接线；不复制 Ollama 实现 | 已核验（2026-09-04；官方 DMG 196424896 bytes、SHA-256 `cc21bd6a1486ddff3cdcbf00549f61d0a3e6e6893d6456a12d37c486161bcc43`；Developer ID Team `3MU9H2V9Y9`、Gatekeeper、公证、arm64 与运行版本通过） | 只公开版本、来源、摘要和复现说明；不再分发运行时 |
| Qwen3 | 开放权重模型 | `qwen3:4b-instruct-2507-q4_K_M` | https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M；https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507 | Apache-2.0；模型页及 Qwen 模型仓库 | 本机 A5 整改建议结构化推理；仅把模型输出作为待人工核验 remediation，不提升为许可证事实 | 保留模型来源和许可证；不得把模型输出写成法律结论，不在公开仓库再分发权重 | OpenGuard 自研 canonical prompt、证据引用和 pending remediation；不复制或再分发权重 | 已核验（2026-09-04；锁定权重本机下载并完成 3/3 结构化推理） | 仅公开官方链接、摘要和聚合实测，不存放或再分发权重 |
| Qwen3 Ollama manifest | 模型 manifest/blob 身份 | `sha256:0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`；blob `sha256:85e4a5b7b8ef0e48af0e8658f5aaab9c2324c76c1641493f4d1e25fce54b18b9` | 官方 registry manifest；模型页 https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M | 随对应 Qwen3 模型 | 完整 digest pinning 与每次 Provider 调用前的 tags 比对；模型 blob 只保留在本机缓存 | 保留摘要来源与校验记录；不得据摘要推断许可证规则正确或模型质量普适 | OpenGuard 自研 digest 比对和 ProducerRef/config_digest 绑定；不生成或托管模型 blob | 已核验（2026-09-04；磁盘 manifest 原始字节 SHA-256 与 API tags 均等于锁定值；2497280480-byte blob 重算 SHA-256 一致） | 仅记录摘要和官方链接，不公开 blob |

所有依赖、模型、数据、框架、组件、工具、素材和第三方服务在首次引入时登记，不在提交前集中补录。

### 真实工具接线状态补充（2026-09-05）

ScanCode32.5.0/Syft1.51.0 沿用已登记官方包和 SHA，现已复用组员 f8bedfd 的 pipeline 代码接入 API ZIP 主链；新增的受控目录、文件清单/SHA 校验与聚合由 OpenGuard 编写。API 与独立 scanner 共享 Dockerfile 的工具阶段，API 使用单独 venv；未引入新依赖、未复制引擎、未上传安装包或生成报告。真实 Chrome 报告及 HTTP 来源哈希/版本验证通过。根 LICENSE 候选保持 pending，不代表依赖授权；完整镜像再分发审计仍留最终交付。

## 2026-09-05 最小部署实际引入

- ScanCode 32.5.0、Syft 1.51.0沿用上述已有资源，状态补充为：官方Linux发行包摘要校验及断网容器真实MIT/npm样例通过，Web Pipeline事实接线仍未完成。来源、完整摘要与命令见[部署说明](../deploy/README.md)，镜像保留随包LICENSE/NOTICE，不上传安装包或生成结果。
- Python官方`3.12-slim-bookworm`镜像（运行3.12.14）、Node官方`24-bookworm-slim`构建镜像和nginx官方`stable-alpine`（运行1.30.4）首次用于部署；各manifest完整digest固定在Dockerfile。来源为[Docker Official Images](https://github.com/docker-library/official-images)、[Python镜像](https://hub.docker.com/_/python)、[Node镜像](https://hub.docker.com/_/node)、[nginx镜像](https://hub.docker.com/_/nginx)。Python受PSF条款、Node主体MIT及随包组件条款、Debian/Alpine系统包各自条款约束，不将整个镜像统称Apache-2.0；只发布构建说明，不发布镜像。完整镜像再分发资源审计仍归最终交付。
- nginx 1.30.4：[上游BSD-2-Clause许可证](https://github.com/nginx/nginx/blob/release-1.30.4/LICENSE)；只用于静态Web与API反向代理，OpenGuard自行编写配置，未改nginx源码；保留版权、条款和免责声明，镜像保留上游随包文件。
- pnpm 10.30.0只用于构建，沿用前端锁文件；[官方来源](https://github.com/pnpm/pnpm/tree/v10.30.0)，MIT及随包第三方条款。未加入运行时或修改前端依赖/锁文件，构建阶段不进入最终Web镜像。
- Docker Desktop 4.89.0仅为经用户明确授权安装的本机部署工具；[官方Mac来源](https://docs.docker.com/desktop/setup/install/mac-install/)，适用Docker Subscription Service Agreement，不作为OpenGuard代码或镜像再分发。官方arm64构建238018，DMG SHA-256 `d333f7c8d42f746429ab1f32ad3284efec887e2a08c03b2ed373a7091373e392`与官方checksums一致，Developer ID Team `9BNSXJN65R`、arm64、codesign和Gatekeeper公证通过；Engine29.7.2/Compose5.5.0实跑。

## 2026-09-05 模型引用样例

沿用已登记 Qwen3 与 Ollama，不新增依赖、下载、推理或权重分发。本机现有 qwen3:4b-instruct-2507-q4_K_M manifest 再读 SHA 为 0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0，与既有锁定值相等；本轮没有重算权重 blob，也不把安装记录当成被扫描项目的使用证据。

样例只引用 [Qwen 官方模型页](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)，当日核对页面标注 Apache-2.0；运行中的静态扫描器不抓取该网页，不将人工浏览结果注入扫描事实，因此模型 LicenseExpression 仍为 NOASSERTION、授权 pending。扫描证明的是输入 README 中的明确引用。检测器复用团队 f8bedfd 候选，0.1.1 修正来源哈希、重复和误识别；不复制模型卡正文、不上传个人配置。

## 2026-09-06 真实公开项目验收样例

huggingface/smolagents 固定commit `a3df1a21db6045aa9be15b4bdf2067041100e96a`：
https://github.com/huggingface/smolagents/tree/a3df1a21db6045aa9be15b4bdf2067041100e96a 。
根LICENSE为Apache-2.0，源码只作为外部静态扫描输入，未修改、安装、执行或复制入作品仓库；
保留原ZIP内版权及许可证。归档SHA和获取/复现命令见deploy/README.md。
Qwen2.5-Coder、FLUX.1-dev及两个HF数据集仅为该输入中的明确引用，不是OpenGuard新增运行依赖，
未下载权重或数据集，授权未知保留NOASSERTION/pending；不能套用仓库根许可证。
实际建议生成复用此前登记的本机Qwen3 4B/Ollama，不新增模型或工具依赖。

## 2026-09-06 公开 Git 最小部署

API镜像新增[Debian bookworm Git](https://packages.debian.org/bookworm/git)发行包，实测1:2.39.5-0+deb12u3/运行Git2.39.5；包内copyright及发行版来源保留，最终分发义务逐项复核归资源冻结。仅作为既有安全无checkout摄取工具，不修改Git，不新增Python依赖或下载目标项目依赖。

[PyPA sampleproject](https://github.com/pypa/sampleproject)作为公开静态扫描输入，实测commit621e4974ca25ce531773def586ba3ed8e736b3fc，根LICENSE.txt为MIT。源码/归档不复制进作品仓库、不安装/执行；根许可不自动继承给peppercorn等依赖。独立归档SHA b3eccda9bfb92813e361eed4f074b97165233eb94ebc60166608ce5412d08a07，仅存本机临时验收目录。运行命令见deploy/README.md。

## 2026-09-06 AMENDMENT：实际依赖核对，冻结待完成

较早的ScanCode/Syft“仍待集成”描述仅代表当时状态；当前两工具已在真实Git/ZIP链验收，证据见PROJECT_PROGRESS第15/16节。此前“Git部署锁定”不等于Dockerfile已经固定Debian包版本：目前apt安装git无精确版本，最终可复现构建仍需处理。

当前API环境通过importlib.metadata只读取得以下版本（安装快照，不冒充正式锁文件或许可证已核验）：

```text
annotated-doc==0.0.5
annotated-types==0.8.0
anyio==4.15.1
click==8.5.0
fastapi==0.141.1
h11==0.16.0
idna==3.19
packaging==26.3
pip==25.0.1
pydantic==2.13.4
pydantic_core==2.46.4
python-multipart==0.0.32
starlette==1.6.0
typing-inspection==0.4.4
typing_extensions==4.16.0
uvicorn==0.52.4
```

上述直接/间接包以及前端pnpm-lock.yaml中实际构建资源需要按固定版本核对来源、许可证和必要声明，补入本台账原位置；现有选型表不算正式核验。本轮不新增或升级这些依赖，也不根据包名推定许可证。前端直接锁版为React/ReactDOM19.2.8、Tailwind及其Vite插件4.3.3；开发构建另有TypeScript5.9.2、Vite8.2.2及React类型包19.2.18/19.2.5。版本来自锁文件，不声称已对部署bundle逐包重算。

### 2026-09-06 API 间接版本冻结补充

前文API15个运行包（不含pip）现已在既有backend/pyproject.toml中逐项精确锁定，构建使用该闭包并禁止自动解析间接依赖，pip check必须通过。重建后15包集合与旧已安装版本完全一致；无新增/升级第三方资源。pip由固定基础镜像创建venv引导，开发依赖和ScanCode专用venv不属于此次闭包。该技术冻结不代替每个包的许可证/来源/必要声明复核，也不声称所有发行文件hash或Debian包版本均已冻结。

### 2026-09-06 Debian Git 版本固定补充

原已验收Git及git-man发行包版本1:2.39.5-0+deb12u3现写入Dockerfile精确安装参数并通过dpkg-query检查；来源仍为原Debian bookworm仓库，不升级工具或新增资源。git为amd64、git-man为all。此项关闭Git构建时自动选择版本的缺口，不外推为全部Debian依赖/发行物hash/完整再分发义务已冻结；若旧版本不再可获取，构建失败而非自动换版。

## 2026-09-06 运行资源来源与必要声明核验

本节更新前文历史状态。对照 API 实际发行元数据、随包原文、pyproject 的15包锁定闭包，以及前端锁文件/安装包，向官方 PyPI/npm 固定版本接口核对24个版本及许可证，全部一致。来源登记不等于所有发行物哈希或完整镜像再分发审计。

### API 运行依赖（完整15包范围）

以下均通过官方固定版本元数据与当前容器随包许可证核对；没有复制其实现，使用方式为 API 依赖，公开方式为锁版声明/构建说明，wheel 不入仓库。许可证原文保留在 `/opt/api/lib/python3.12/site-packages/<distribution>.dist-info/licenses/`。MIT需保留版权/许可全文；BSD需保留版权/条件/免责声明；Apache需保留许可、相关原有声明及修改说明（若修改），不能机械要求不存在的 NOTICE；PSF保留原有许可/版权；packaging 保留随包双许可文本。现有第三方包未作源码修改。

| 包/固定版本 | 官方版本来源 | 许可证 | 随包原文文件 |
|---|---|---|---|
| typing_extensions 4.16.0 | https://pypi.org/project/typing_extensions/4.16.0/ | PSF-2.0 | `LICENSE` |
| annotated-doc 0.0.5 | https://pypi.org/project/annotated-doc/0.0.5/ | MIT | `LICENSE` |
| python-multipart 0.0.32 | https://pypi.org/project/python-multipart/0.0.32/ | Apache-2.0 | `LICENSE.txt` |
| idna 3.19 | https://pypi.org/project/idna/3.19/ | BSD-3-Clause | `LICENSE.md` |
| starlette 1.6.0 | https://pypi.org/project/starlette/1.6.0/ | BSD-3-Clause | `LICENSE.md` |
| h11 0.16.0 | https://pypi.org/project/h11/0.16.0/ | MIT | `LICENSE.txt` |
| uvicorn 0.52.4 | https://pypi.org/project/uvicorn/0.52.4/ | BSD-3-Clause | `LICENSE.md` |
| pydantic_core 2.46.4 | https://pypi.org/project/pydantic_core/2.46.4/ | MIT | `LICENSE` |
| click 8.5.0 | https://pypi.org/project/click/8.5.0/ | BSD-3-Clause | `LICENSE.txt` |
| annotated-types 0.8.0 | https://pypi.org/project/annotated-types/0.8.0/ | MIT | `LICENSE` |
| packaging 26.3 | https://pypi.org/project/packaging/26.3/ | Apache-2.0 OR BSD-2-Clause | `LICENSE`, `LICENSE.APACHE`, `LICENSE.BSD` |
| anyio 4.15.1 | https://pypi.org/project/anyio/4.15.1/ | MIT | `LICENSE` |
| pydantic 2.13.4 | https://pypi.org/project/pydantic/2.13.4/ | MIT | `LICENSE` |
| fastapi 0.141.1 | https://pypi.org/project/fastapi/0.141.1/ | MIT | `LICENSE` |
| typing-inspection 0.4.4 | https://pypi.org/project/typing-inspection/0.4.4/ | MIT | `LICENSE` |

许可义务原文参考：[MIT](https://opensource.org/license/mit)、[BSD-3-Clause](https://opensource.org/license/bsd-3-clause)、[Apache-2.0 第4节](https://www.apache.org/licenses/LICENSE-2.0)。typing_extensions 的 LICENSE 含 PSF 历史声明，保留整个原文件，不用一行 SPDX 替换。

### 前端运行与构建资源

| 资源/固定版本 | 官方来源 | 许可证/用途 | 声明与分发边界 |
|---|---|---|---|
| react 19.2.8 | https://www.npmjs.com/package/react/v/19.2.8 | MIT；浏览器UI | 已核对随包LICENSE；浏览器产物附完整原文 |
| react-dom 19.2.8 | https://www.npmjs.com/package/react-dom/v/19.2.8 | MIT；浏览器DOM渲染 | 已核对随包LICENSE；浏览器产物附完整原文 |
| scheduler 0.27.0 | https://www.npmjs.com/package/scheduler/v/0.27.0 | MIT；ReactDOM运行依赖 | 已核对随包LICENSE；浏览器产物附完整原文 |
| tailwindcss 4.3.3 | https://www.npmjs.com/package/tailwindcss/v/4.3.3 | MIT；构建生成CSS | 已核对随包LICENSE；浏览器产物附完整原文 |
| @tailwindcss/vite 4.3.3 | https://www.npmjs.com/package/@tailwindcss/vite/v/4.3.3 | MIT；构建插件 | 已核对随包LICENSE；构建期保留原文件，最终nginx不含node_modules |
| typescript 5.9.2 | https://www.npmjs.com/package/typescript/v/5.9.2 | Apache-2.0；编译检查 | 已核对随包LICENSE.txt及ThirdPartyNoticeText.txt；构建期保留原文件，最终nginx不含node_modules |
| vite 8.2.2 | https://www.npmjs.com/package/vite/v/8.2.2 | MIT；构建工具 | 已核对随包LICENSE.md含内嵌组件许可；构建期保留原文件，最终nginx不含node_modules |
| @types/react 19.2.18 | https://www.npmjs.com/package/@types/react/v/19.2.18 | MIT；编译类型 | 已核对随包LICENSE；构建期保留原文件，最终nginx不含node_modules |
| @types/react-dom 19.2.5 | https://www.npmjs.com/package/@types/react-dom/v/19.2.5 | MIT；编译类型 | 已核对随包LICENSE；构建期保留原文件，最终nginx不含node_modules |

实际发现旧浏览器 JS 缺少完整版权/许可，CSS只有简短MIT标识。现有 `frontend/vite.config.ts` 现从锁定安装包读取 React、ReactDOM、scheduler、Tailwind 的 LICENSE，生成 `dist/third-party-licenses.txt` 并在 HTML 加 rel=license 链接；任一原文缺失会导致构建失败。不是手抄清单，不新增仓库许可副本或依赖。后续新增浏览器依赖须更新覆盖范围，不宣称自动发现全部传递包。

本机 `pnpm build` 与现有 Web Docker 构建均成功，JS/CSS文件名与修改前一致；只重建/更新web，API和数据不动。部署附件 HTTP200、4618字节，SHA256 `fb50515ff9316032a876ad16ef1e8dc36a2e7cd46a5dc62c3250a6b82bdf6d25`；四份原始许可逐字包含、首页引用通过。Chrome插件打开该附件返回ERR_BLOCKED_BY_CLIENT，未改变保护，也未将插件浏览验收记为通过。此前真实报告四格式下载结论不因此撤回。

### 工具、模型与发行边界更正

- ScanCode32.5.0 原容器 `/opt/scancode/NOTICE` 与[官方固定版本NOTICE](https://github.com/aboutcode-org/scancode-toolkit/blob/v32.5.0/NOTICE)均明确：软件 Apache-2.0、检测数据 CC-BY-4.0。保留 `/opt/scancode/apache-2.0.LICENSE`、`cc-by-4.0.LICENSE`、NOTICE及thirdparty的ABOUT/NOTICE；数据署名为 nexB Inc. and others，来源为上述固定版本，未修改其数据。内嵌工具有各自许可，不能由顶层Apache覆盖，最终镜像若再分发需逐包审查并落实适用源码提供义务。
- Syft1.51.0 保留 `/opt/syft/LICENSE`；Python保留 `/usr/local/lib/python3.12/LICENSE.txt`；Debian Git保留 `/usr/share/doc/git/copyright`（摘要见前节）。本轮核对文件存在和ScanCode声明，不把它计为所有OS/Go/扫描器传递组件逐包审计完成。
- Qwen3/Ollama、基础镜像digest、pnpm及Docker Desktop继续沿用原登记；本轮未重新下载权重或改变服务条款。公开样例是扫描输入，不能把其依赖/许可继承为本项目依赖。
- 当前发布源码/构建说明，未发布镜像或模型权重；完整镜像再分发、外部服务适用条款、人工许可/风险标签与AI建议复核仍须最终确认。历史选型中的未使用资源不新增为P0任务。
