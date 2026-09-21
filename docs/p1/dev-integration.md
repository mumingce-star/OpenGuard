# P1 隔离联调说明

基于 `integration/p1@62d78dadff3d01251bba648e9a17676b55870c05`。**合成测试数据，不代表生产启用或 P1 全部完成。** 本文是开发操作说明，不是第二份 Contract；字段和权威边界仍以 [Frozen Contract V1](../spec/p1-workspace-contract.md) 和 `schemas/p1/` 为准。

## 适用范围

本入口把现有正式 SQLite Registry、Assessment、History/Diff/Graph、Task、Report V2 实现接到独立开发数据库；不是固定 JSON Mock server。仅种子是团队合成样例。Task/Report 通过真实领域校验、事务与 HTTP 写入，不能把这些结果作为真实仓库扫描证据。

只允许显式 derive/PATCH Task 和 POST Report V2。Git/ZIP、新扫描、dispatcher、ScanCode/Syft、Qwen、Chat、重新评估和 Metadata 网络刷新不启用。固定 Formal Assessment 在显式 init 时由本地确定性逻辑生成；启动、刷新或 GET 不会新建评估或报告。

## 启动前提与检查

从仓库根目录执行。需要已有 Docker Desktop/引擎、Python 3 标准库，以及本机已经核验、具有 `/opt/api/bin/python` 和项目锁定依赖的 runtime image。前端需已有 Node、pnpm 和按仓库锁文件准备好的 `frontend/node_modules`。

```sh
pwd
git branch --show-current
git rev-parse HEAD
git status --short
python3 --version
docker version
```

有未解释的分支/源码变化、Docker 不可用或依赖缺失时停止，不执行生产 Compose，不重建生产镜像，不通过 pip/npm 临时升级环境。新机器依赖准备是独立环境步骤；本文不会自动下载镜像、模型或依赖。现有 `openguard-a06-dev` 是回归容器，不修改它的映射或配置。

## 初始化、启动、停止与恢复

以下命令从仓库根目录执行。`P1_ROOT` 必须是 `output/manual-fixes/` 下新的专属 `p1-dev-*` 目录；不用生产 `data/`，不用历史真实报告。选择时间戳只用于新空间命名；恢复时必须复用之前的值。

```sh
P1_ROOT="output/manual-fixes/p1-dev-$(date +%Y%m%d-%H%M%S)"
P1_IMAGE="$(docker inspect --format '{{.Image}}' openguard-a06-dev)"
python3 deploy/p1_dev.py init --root "$P1_ROOT" --image "$P1_IMAGE"
python3 deploy/p1_dev.py start --root "$P1_ROOT" --image "$P1_IMAGE" --api-port 18011 --web-port 15174
python3 deploy/p1_dev.py status --root "$P1_ROOT"
```

没有 `openguard-a06-dev` 时，不创建替代测试容器或自动拉取镜像。由操作者显式提供一个**已在本机核对过**、包含上述 Python/锁定依赖的完整 runtime image ID，再执行同一 init/start：

```sh
P1_IMAGE='sha256:<已核对的本地镜像完整64位摘要>'
docker image inspect --format '{{.Id}} {{.Os}}/{{.Architecture}}' "$P1_IMAGE"
# 确认身份及运行时前提后，沿用上面的 init/start 命令。
```

占位符不是可执行镜像值。镜像不存在、身份不符或运行时未经核对时停止；不用 `latest`、不自动下载、不执行生产 Compose。普通 `pnpm exec vite` 已是首选入口，Codex 缓存路径只是已有环境的可选用法，不要求重装 Node。

`init` 成功后应有 `.openguard-dev-integration.json`、`dev-manifest.json` 和合成数据库；`start` 应显示本轮实例标识及 `http://127.0.0.1:18011`。任何步骤报错就停止并保留日志。不要重复 init，不删除数据库，不用生产配置“补齐”环境。重复 init 不覆盖已有 Task/Report。端口冲突明确报错，不杀占用者、不悄悄换端口。

```sh
python3 deploy/p1_dev.py stop --root "$P1_ROOT"
python3 deploy/p1_dev.py status --root "$P1_ROOT"
# 恢复同一数据空间：保留原 P1_ROOT / P1_IMAGE，不运行 init。
python3 deploy/p1_dev.py start --root "$P1_ROOT" --image "$P1_IMAGE" --api-port 18011 --web-port 15174
```

`stop` 保留本轮容器和数据；同一 image/端口参数的 `start` 恢复该实例，不重新初始化。`stop` 只处理通过实例身份核对的本轮容器，不使用 `pkill`、`killall` 或 `docker compose down`。代码只读挂载，数据只挂本轮根目录；不挂生产卷、模型、用户主目录、Docker socket 或密钥。Docker 容器内部允许监听 `0.0.0.0`，宿主机仅 publish `127.0.0.1`。禁止外部功能调用不等于网络层完全断网，实际网络设置见本轮验收回执。

本机 Docker Desktop 的 bind mount 所有者映射经核对后，本专属容器使用容器内 UID 0；同时保持 `--cap-drop=ALL`、`no-new-privileges`、只读根文件系统、代码只读及唯一合成数据可写挂载。它不是 `--privileged`、host network 或宿主机 root 授权，不挂生产目录。不能把这个容器内 UID 选择套用到生产部署，也不宣称适用于尚未实测的 Windows/Linux；不得以 chmod 777 处理差异。

恢复时标签仅用于所有权判断。启动还检查实际完整容器 ID、Image、loopback 发布、五个只读源码挂载、唯一可写数据挂载、rootfs/capabilities/no-new-privileges、网络/命名空间、资源限制、工作目录及完整启动命令。新建后也核对同一实际 ID；不匹配停止流程，不自动改配置或删除重建。`stop` 只需要确认所有权和实际 ID，仍可停止安全配置异常的自有实例；归属不明拒绝。

健康与 smoke 的每个响应通过开发层 `X-OpenGuard-Dev-Identity` 绑定 `root_id`、`synthetic=true`、`seed_version`。它不是生产 API 或认证机制，不含本机路径、不改 Frozen JSON。首次写入前先 GET 核对；后续响应、`--verify` 与代理保持同一身份。请求携带相同身份前置条件，防止检查后错连其他开发根造成写入。所有 HTTP 重定向直接拒绝，不跨主机/端口访问，不改变真实 Origin 或 Sec-Fetch-Site。失败不会生成 PASS 回执；回执记录实际 base/origin、远端观察身份及 manifest 身份。旧回执可以只读 verify，但新的远端身份核验不能省略。

开发预检在任何可写 registry 连接前，以 SQLite `mode=ro` 检查 P0 原 schema verifier，以及 sidecar 的列/类型/非空/default/主键/唯一键/索引和 user_version。错误库拒绝，不迁移、不重seed。非空 WAL 纳入完整性验证；SHM 协调字节不作为持久事实恒定保证。

路径校验同时使用限定范围、规范化路径、私有权限和 marker，不仅凭 marker 接受任意目录；符号链接、路径穿越、未知已有数据库和不匹配的种子空间拒绝。初始化失败不留下成功 marker。未使用本开发入口时，生产默认工厂不会改变。

## 独立前端入口

原 `frontend/vite.config.ts` 保持默认 `/api → 127.0.0.1:8000`。只有显式选以下配置才进入本轮 API；不改原 `.env`，不改现有 5174、8011、8080。

在另一个终端进入仓库的 `frontend/`：

```sh
OPENGUARD_P1_API_PORT=18011 OPENGUARD_P1_WEB_PORT=15174   pnpm exec vite --config vite.p1-dev.config.ts
```

如果当前 Mac 的 `pnpm` 不在 PATH，而已经存在已核验的 Codex runtime，可使用以下**现有文件**，不安装、不下载。缺失时停止并准备独立环境，不使用 App 内受签名限制的 Node 替代：

```sh
P1_NODE_DIR="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin"
P1_PNPM_CLI="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/pnpm/bin/pnpm.cjs"
test -x "$P1_NODE_DIR/node" && test -f "$P1_PNPM_CLI"
export PATH="$P1_NODE_DIR:$PATH"
OPENGUARD_P1_API_PORT=18011 OPENGUARD_P1_WEB_PORT=15174 node "$P1_PNPM_CLI" exec vite --config vite.p1-dev.config.ts
```

正常输出 `http://127.0.0.1:15174/`。**每次从这个首页进入**，不是直接跳到新建扫描页。本环境不支持新扫描；当前已有页面不等于新 P1 History/Task/Report 页面已经完成。接口联调先用下方脚本/API。

配置复用原 Vite 插件与许可证输出，`VITE_API_BASE_URL` 固定为同源 `/api/v1`，不接受任意外部 proxy URL。只绑定 loopback、`strictPort=true`，保留真实 Origin，不启用 wildcard CORS。默认写入 Origin 为本轮 localhost/127.0.0.1 的 API/Web 端口；若显式改端口，API launcher 与 Vite 必须一起配置。不要用 CLI `--host 0.0.0.0` 覆盖隔离边界。

停止前端用**启动它的终端 Ctrl-C**；不要停止原有 5174 服务。停止 API 使用上面的专属 stop 命令。

## API 能力矩阵

下表路径均在 `/api/v1` 下，`S`/`A`/`T`/`R` 是 manifest 或真实响应的 ID。错误 body 保留 `ErrorEnvelope` 和 `X-Request-ID`，不能只按 HTTP 200 判断业务完整性。

| 能力 | 实际路径 | 本环境行为 | 常见错误 |
|---|---|---|---|
| History | `GET /scans` | 只读；cursor/limit/status/source_type/q/project_key；q 只匹配安全公开字段 | 400 参数/cursor；503 来源不可用 |
| Diff | `GET /scans/{target}/diff?base_scan_id={base}` | 同项目固定快照；可显式绑定双方 Assessment ID；不扫描 | 400 参数；404 缺失；409 不可比较；503 完整性 |
| Graph | `GET /scans/{S}/graph` | completed/partial；重复参数过滤；完整 closure；不分页 | 400 参数/资源不存在；404；409 状态；413 容量；503 |
| 固定 Assessment | `GET /scans/{S}/assessments/{A}` | 仅读取存储的确定性评估与既有展示字段 | 404；503 存储 |
| Task 列表 | `GET /scans/{S}/assessments/{A}/remediation-tasks` | 只读分页；superseded 为只读计算 | 400；404；409；503 |
| Task 派生 | `POST .../remediation-tasks/derive` | 显式固定 facts_hash、幂等派生，写独立任务库 | 400；403；409；413 body；503 |
| Task 更新 | `PATCH .../remediation-tasks/{T}` | CAS expected_version、append-only audit；不修改 Formal/Scan | 400；403；404；409 CAS；413 body；503 |
| Report 创建 | `POST /scans/{S}/assessments/{A}/report-v2` | 显式不可变快照；固定 refs；幂等 | 400；403；404；409；413；503 |
| Report 下载 | `GET .../report-v2/{R}?format=json或html` | 已保存字节；GET 不渲染、不创建 | 400；404；503 完整性 |
| Notice/Profile | 没有本轮可用 reader / parser 接线 | 不虚构成功；带未支持 refs 的报告按既有错误拒绝 | 未注册路径404；reader/来源未就绪按实际409/503 |
| 新扫描/Chat/重新评估 | 不在本轮允许写入口 | 开发层拒绝，不能调用真实扫描/模型 | 503 feature_disabled |

本轮重点验收带固定 assessment_id 的 Assessment GET；其他既有只读路由按实际服务响应处理，不由这份能力表扩大承诺。评估列表可读取已存储记录，但不代表重新评估、Chat写入或模型能力已经启用。示例直接使用manifest固定ID，保持固定绑定。

Graph 数组只用 `resource_ids=A&resource_ids=B`；`A,B` 不会拆分。Graph 的 `coverage.view_complete=true` 只表示当前选择的已有事实投影完整，partial 仍保留 `scan_gaps`。无效查询可先400；queued/running409 not_ready；failed/cancelled409 not_comparable。

Task PATCH 省略字段保留旧值，显式 null 无效。note 原样保存，长度不超过2000；done/dismissed最终 note 必须含非空白字符。Task done ≠ compliance verified；Report success ≠ compliance verified。

## Manifest 与固定引用

`dev-manifest.json` 明确 `synthetic=true`、seed/version、代码版本与数据根身份：

- `scans.completed_base` / `scans.completed_target`：可比较的 completed 扫描。
- `scans.partial`：带真实合成 coverage gap 的 partial 场景。
- `assessments[scan_id]`：固定 assessment_id、version、facts_hash、usage_hash。
- `comparisons.base_scan_id` / `target_scan_id`：Diff 对。
- `graph_refs[scan_id]`：由真实 `ReportGraphReader.capture` 得到的 graph algorithm_ref。

不要手写看似真实的 ID/Hash，不读取或复制生产数据库来生成样例。

当前种子为 `p1-dev-integration/2`。它补齐开发用确定性评估持久记录；不迁移或覆盖旧种子空间。旧root与产物保留；遇到旧seed/marker不匹配时停止，另建全新 `p1-dev-*` 空间显式init，不在原库改表或重seed。

## 可执行接口样例：一次显式写入，之后只读恢复

从仓库根目录执行，沿用刚才的 `P1_ROOT`，API 已启动。脚本只读取这个 manifest 的 ID/Hash，使用 Python 标准库向明确的 loopback API 发有界请求，不访问外部仓库。

```sh
python3 deploy/p1_dev.py graph-ref --root "$P1_ROOT"
python3 deploy/p1_dev_smoke.py --manifest "$P1_ROOT/dev-manifest.json" --base http://127.0.0.1:18011 --origin http://127.0.0.1:15174 --receipt "$P1_ROOT/http-smoke.json" --key dev-smoke-v1
```

预期最终输出 `result: PASS` 并保存逐请求 method/path/status/耗时、Task ID/version、snapshot_id、四份已下载附件及其Hash/大小。失败即停止，保留数据/日志，不删除重跑掩盖失败；已有 receipt 会拒绝覆盖。

脚本源码 `deploy/p1_dev_smoke.py` 就是可以交给前端逐步翻译为调用的等价请求示例，按顺序执行：

1. 先 `GET /scans?limit=1` 核对远端开发实例身份，再 `GET /scans` 读取三个合成快照。
2. 以 `comparisons` 固定base/target读取Diff。
3. GET全图、合法 `resource_kinds=component` 过滤图、partial图及scan gaps。
4. GET固定Assessment，核对ID/facts_hash。
5. POST derive，body为 `{idempotency_key, expected_facts_hash}`；同键重放不重复生成。
6. PATCH为in_progress（使用返回version），再用旧version确认409 conflict；然后带非空note PATCH为done。
7. 显式POST基础Report，另POST使用合法graph_ref且绑定确切Task版本的Graph报告；分别同键重放。
8. GET两份报告的HTML/JSON，逐一核对POST描述中的SHA256/字节数，确认GET正文和POST描述不是同一DTO。
9. 修改Task备注，再下载旧报告，确认所有旧Hash仍不变。
10. 验证新扫描被开发入口拒绝；不启动任何真实Git请求。

重启后只能使用 `--verify`，它不会再次POST/PATCH：

```sh
python3 deploy/p1_dev.py stop --root "$P1_ROOT"
python3 deploy/p1_dev.py start --root "$P1_ROOT" --image "$P1_IMAGE" --api-port 18011 --web-port 15174
python3 deploy/p1_dev_smoke.py --manifest "$P1_ROOT/dev-manifest.json" --base http://127.0.0.1:18011 --origin http://127.0.0.1:15174 --receipt "$P1_ROOT/http-smoke.json" --verify
```

预期 `restart_verification: PASS`：Task最终version/status和保存附件Hash/大小一致。上述写脚本用于明确验收，不应由网页加载/刷新自动调用。要验证代理，可在Vite运行时把只读 `--verify` 的 `--base` 改成 `http://127.0.0.1:15174`，请求经同源 `/api` 到隔离API；不改Origin绕过保护。

检查结束，在Vite终端Ctrl-C，并执行专属API stop。下载文件仅为合成开发产物，不提交数据库或其完整附件到Git。

## Report 两类 JSON

POST 返回 **ReportV2Snapshot 描述 DTO**（snapshot_id、固定 binding、附件 Hash/大小等）。GET `format=json` 返回 **完整报告内容文件**，其结构不同。不能把两者交给同一个假定完全相同的 DTO 解析器。

没有 Report list/metadata endpoint。保存 POST 返回的 snapshot_id；同键重试取得原快照。下载拿的是服务器保存的原字节，不由前端重拼，不用 latest 替换固定 Task/Assessment，不在刷新时再次 POST。

基础报告使用 `task_refs=[]`、`notice_refs=[]`、`algorithm_refs=[]`；先完成这个流程。需要包含任务时选择明确 task_id/version。需要图时使用本开发 manifest/CLI 的真实 graph_ref，报告必须包含全范围 observation；过滤图不是本批支持的报告图来源。

`ReportGraphReader.capture(stored)` 是后端内部 helper，**不是公开“获取报告图引用” API**。开发 CLI/manifest 只解决固定合成 fixture 的合法引用；浏览器任意扫描的动态选择与引用获取流程尚未完成，需要负责人另行审阅窄范围提案。前端不能猜 Hash、改 Hash 口径或拿过滤图替换全图。错误 Hash/版本应拒绝；reader 未配置应失败；Graph 容量与 ReportGraphReader 使用相同配置。

## xzb 的接入顺序

1. History/Diff：真实分页与筛选、固定扫描和评估对；loading/empty/error分别显示。
2. Task/基础Report：显式点击派生/更新/生成；保存版本、幂等键、snapshot_id，刷新只 GET。
3. Graph展示及可选报告包含：先Frozen Graph View；固定开发图引用按manifest验证；动态浏览器产品接口等待单独审批。

必须处理400参数、403来源拒绝、404缺失、409冲突/未就绪/不可比较、413超限、503未配置/来源不可用。partial不得显示completed；失败不能回退Mock成功。Unknown既不是禁止也不是允许；Pending不是Verified；Detected License不是Authorization；根许可证不等于依赖/模型许可证。Task done不能改变评估授权结论。

可先开发上述页面，不必等Notice/Profile。本轮不修改xzb业务页面或其分支，不把Vite启动等同全部P1界面验收。

## cz 的接入边界

- B01：离线 Profile parser/adapter；输入是负责人提供的明确资源/观察材料，输出与Frozen Schema及既有来源模型一致的结构化观察，不把声明直接提升为 verified license。
- B04：NOTICE facts；输出可追溯的事实、来源与必要内容，不代替公共API、报告快照或授权裁定。
- cz不写公共API、生产DB或网络抓取入口。远程Metadata获取/A07不在本任务中。
- 可用合成fixtures核对字段与引用，但这不等于真实Metadata验收。完整Notice/Profile reader和报告包含能力尚未实现，不能在文档或UI标成成功。

## 验证与尚未完成

新增前端配置检查从 `frontend/` 执行：

```sh
pnpm exec tsc --noEmit
pnpm test
node --test tests/p1-dev-config.test.mjs
```

后端统一回归继续复用 `openguard-a06-dev` 的已锁定Python环境；不重建、不安装依赖。本轮专用HTTP冒烟是合成数据的实际Host HTTP，不代替真实Git/ZIP，也不授权运行原来排除的 `test_real_uvicorn_disabled_git_rejects_without_queued_scan`。

本轮已实际验证：合成数据真实HTTP Task/基础与Graph报告、停止恢复后的只读Hash验证、Vite代理只读验证和Chrome首页。Chrome直接导航原始API JSON曾被客户端阻止，未绕过；这不等同全部P1页面或浏览器业务操作通过。

精确测试命令、每次日志、源码Hash、网络/端口及实际浏览器证据见本轮 ignored validation receipt。未实际做的跨机、浏览器或新P1页面检查须标“未验证”，不能使用旧548通过代替本轮结果。

仍未交付：完整Notice/Profile；全部P1新业务页面；任意扫描的正式浏览器Graph引用流程；生产启用/部署；真实仓库全链路；异机验收和P1竞赛最终交付。

### 2026-09-16 源码 Review 限定修补（DEV-R1/R2/T1）

原验收证据仍在 `output/manual-fixes/p1-dev-integration-20260916/`，不覆盖。
本次修补和失败轨迹在 `output/manual-fixes/p1-dev-review-20260916-195148/`：

- 首轮 fail-first：25 项中 17 失败、8 通过；模拟 Docker 配置错配、redirect 和真实 TestClient 错实例复现工具缺口。坏列完整工厂启动已经拒绝，但 DELETE 模式 scans.db 在拒绝前发生 Hash 变化；这不是生产异常或坏库服务成功启动的证据。
- 只读预检加强后，四类坏列数据库及 metadata/version/约束错误在 DELETE/WAL 模式均拒绝，主 DB、非空 WAL 和 schema 保持不变。只修改开发入口，不迁移或放宽既有 registry/store。
- 最终 Python 3.12.14 回归：668 通过（原 619 个唯一节点全部保留，新增 49 个）、0 失败、仅精确排除原 real_uvicorn 那一项。Starlette 既有弃用警告保留。新增错实例/redirect 用例未排除。
- 真实新 Docker 实例：实际配置/身份确认、26 次合成 HTTP、合法停止恢复后的 6 次 GET、真实 Vite 代理 6 次 GET 均通过。旧同 seed manifest 错连新端口在首次 GET 拒绝，无写请求、无 PASS 回执、主 DB Hash 不变；该真实探针当时没有 WAL 文件，非空 WAL 不变由 SQLite 用例覆盖。
- Docker 配置错配和 redirect 是替身/定向单测，没有故意制造危险 Docker 配置或访问外部 URL。容器身份头是防错连信息，不是鉴权凭证；bridge 不是网络层禁外联。
- 前端文件未变，复用现有 Node/Vite 做代理验证，没有安装依赖；本次没有重跑前端 59 项/TypeScript、Chrome 或生产 build。前述 Chrome 首页属于原验收，不是本次新证据。Windows/原生 Linux 策略和真实仓库仍未验收。

本次保持未暂存、未提交、未推送、未合并、未部署生产；旧开发空间和失败证据保留，完成后停止本次启动的实例，等待负责人 Review。
