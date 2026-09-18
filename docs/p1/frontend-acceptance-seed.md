# P1 Frontend Acceptance Seed Pack v1

开发验收基础设施，基于 `944a00e3d98cba0f815f40dbc8bc96437afb44f3`。
**synthetic=true；没有真实仓库扫描、联网 Metadata 或模型调用。**
不是新的 Contract，不是 Gold，不是合规授权结论，不代表生产启用、P1 页面完成或性能门禁通过。

## 用途与数据

独立种子 `p1-frontend-acceptance/1` 使用正式 Registry、Assessment、History/Diff/Graph、
Remediation、Report V2 和 FastAPI。不是 Mock API；manifest 只提供固定 ID、场景和导航。
不得把 manifest 直接 import 到页面代替 API 返回。

| 场景 | 数据与实际实现 |
|---|---|
| History | 205 个确定性 ScanRun；completed/partial/failed/cancelled/running/queued；Git-like identity 和合成 ZIP；正式 cursor/filter |
| D1 | 同项目 completed/completed，revision/version/finding/license observation 变化、added、not_observed_in_target 且 removal_confirmed=true |
| D2 | completed/partial，未观察到不确认删除；Graph 保留 scan_gaps |
| D3 | target 没有 Assessment；不补隐藏评估，assessment_diff=unavailable |
| D4 | 显式固定双方 Assessment IDs，usage/facts/rule 绑定，assessment_diff=compared |
| Graph | 三个独立 scan，正式投影实际 100/300/500 节点；保留引用闭包，默认容量不改 |
| Task | 正式 derive 的 todo、固定 origin/source_hash/resource/evidence；另有真实空列表，不表示项目合规 |
| Report | basic/task/graph/long 四个正式持久化快照；task 固定 version，graph 使用全图内部 capture 引用 |

资源、证据、Finding、Obligation 和评估是合成内部事实。Task 追溯只证明这些对象的引用/摘要一致，
不证明真实项目存在对应义务。Task done 不等于 compliance verified。Long Report 来自较丰富合法事实，
实际字节数/Hash 取正式服务结果，不人为填大小。Graph 不包含推断边或评估维度。

## 启动

从仓库根执行。必须已有已核验的 Docker runtime image（Python 3.12.14 与锁定依赖）。
缺镜像/引擎/依赖时停止，不下载、不重建生产 image、不调用生产 Compose。
`openguard-a06-dev` 存在时可只读取得其实际 image；没有该容器时显式填已核验完整 image ID。

```sh
P1_IMAGE="$(docker inspect --format '{{.Image}}' openguard-a06-dev)"
P1_ROOT="output/manual-fixes/p1-frontend-acceptance-$(date +%Y%m%d-%H%M%S)"
python3 -B deploy/p1_frontend_acceptance.py init --root "$P1_ROOT" --image "$P1_IMAGE"
python3 -B deploy/p1_frontend_acceptance.py start --root "$P1_ROOT" --image "$P1_IMAGE"
python3 -B deploy/p1_frontend_acceptance.py print-manifest --root "$P1_ROOT"
```

`init` 显式创建数据，并通过正式服务 prepare Task/Report。失败保留现场，不删除/重跑覆盖。
默认 API `http://127.0.0.1:18011`、推荐 Web Origin `http://127.0.0.1:15174`。
实际 manifest 位于 `$P1_ROOT/frontend-acceptance-manifest.json`，只在 ignored output，不提交运行时产物。
含 root/seed 身份、固定 Scan/Assessment/Task IDs、snapshot IDs、API href、Hash/size、unsupported 状态。

原 `p1-dev-integration/2` 不迁移、不重 seed、不改旧 manifest。新容器使用独立
`openguard-p1-acceptance-*` 名称，复用原 launcher 的实际 ID/Image/端口/挂载/安全事实检查。
源码只读、唯一新合成目录可写、read-only rootfs/cap-drop ALL/no-new-privileges，宿主机仅 loopback。
UID 0 是已验证 Docker Desktop 的策略，不宣称 Windows/原生 Linux 通用；不得 chmod 777。
bridge 不是网络层禁止外联。身份响应头用于防错连，不是认证机制；不改变 Frozen P1 JSON。

## 显式 prepare、smoke 与只读 verify

```sh
# 可重复的 HTTP 幂等重放，原快照/Task ID 不增生；必须选择新回执名。
python3 -B deploy/p1_frontend_acceptance.py prepare --root "$P1_ROOT" --receipt prepare-1.json
# 会修改一个 Task：todo → in_progress → 旧version 409 → done+非空note。
python3 -B deploy/p1_frontend_acceptance.py smoke --root "$P1_ROOT" --receipt smoke-1.json
# 仅 GET；不再次 derive/POST/创建 Assessment/报告。
python3 -B deploy/p1_frontend_acceptance.py verify --root "$P1_ROOT" --receipt verify-1.json
```

每次首次写前校验远端 root_id/synthetic/seed_version，后续响应与身份前置条件保持绑定；
拒绝全部 redirect。所有 HTTP 操作只接受独立 loopback base/origin，不伪造 Sec-Fetch-Site 或放宽 Origin。
支持 `--base`/`--origin` 指向已配置的同源开发代理；代理必须仍回传同一身份。本轮不声明新浏览器页面验收完成。

verify 用正式 API 遍历 205 条、核对筛选、Diff、全图/过滤图/partial、固定 Assessment、Task、双格式报告。
GET 前后按四个 SQLite 的每张业务表行数及全行规范化摘要审计（BLOB 纳入内容 Hash），
不是只比较 DB 文件 Hash；WAL/SHM 协调字节不当业务事实。
smoke 修改 Task 后再核对原 HTML/JSON Hash，并比较 Scan/Assessment/Report 业务状态不变。
重复 prepare 使用固定幂等键与初始 Task version；不自动跟随当前 Task version 生成新报告。

POST Report 返回 Snapshot 描述 DTO；GET `format=json` 返回带完整 section content 的报告文件，两者不是同一个 DTO。
Graph ref 来自正式内部 `ReportGraphReader.capture`，仅解决这些固定合成扫描，不虚构公共获取引用 API。

## 给 xzb 的顺序

由 xzb 在自己的授权范围安全恢复并集成前端 stash，本任务不操作其分支或页面。
使用现有 `frontend` 环境正常执行：

```sh
OPENGUARD_P1_API_PORT=18011 OPENGUARD_P1_WEB_PORT=15174 pnpm exec vite --config vite.p1-dev.config.ts
```

依次验收 History → Diff → Task → Graph → Report（F01/F05/F04/F03/F06）。
按 manifest 选择实体，页面访问真实 API；首页可打开不代表这些新页面完成。
F02 Profile 明确 `not_available_on_current_baseline`（A07-2/B01 pending）；F06 NOTICE 同样未就绪。
未注册路径 404 是未实现，不是“功能完成但暂无数据”，禁止伪造 Profile/NoticeDraft 200。

## 停止、恢复、全新空间

```sh
python3 -B deploy/p1_frontend_acceptance.py stop --root "$P1_ROOT"
python3 -B deploy/p1_frontend_acceptance.py status --root "$P1_ROOT"
# 恢复原空间，不 init，不删除数据：
python3 -B deploy/p1_frontend_acceptance.py start --root "$P1_ROOT" --image "$P1_IMAGE"
python3 -B deploy/p1_frontend_acceptance.py verify --root "$P1_ROOT" --receipt restart-verify.json
```

smoke 已改变 Task 的 root 不再用于初始 todo 验收；创建另一个全新时间戳 root，旧空间/失败日志保留。
stop 只操作通过所有权验证的确切容器 ID，不删除容器或空间；归属不明拒绝。
端口冲突停止，不杀其他进程；符号链接、路径越界、未知非空目录/SQLite、版本不匹配拒绝。

后端测试固定 `openguard-a06-dev` `/opt/api/bin/python`，不安装依赖。
本地测试、真实 HTTP 和重启的具体计数/Hashes 以本轮 ignored receipt 为准。
API 请求耗时只是小样本 observation，不是 p95 门禁；本轮未测 DOM/render、Windows/原生 Linux、生产 build 或真实仓库。
未改前端，前端测试不重复运行。Review 后是否提交/推送以及后续 A07-2，由负责人另行决定。

## Owner Review R1/R2：只读完整性与审计实例边界

`read_manifest` 不再只检查 identity/schema：固定 v1 集合必须完整，并与现有 Registry、
Assessment、Task 历史 version 1、ReportV2 快照及 artifact 描述一致。History 必须 205 条，
D1–D4、100/300/500 Graph、五个固定 Assessment、populated/empty Task、四类 Report 均不可删项。
Graph 计数从正式 reader 取得；不信任 manifest 自报数字。D3 仍不创建 Assessment。
后续合法 Task workflow 修改不会改写或使初始版本引用失效；Profile/NOTICE 仍不支持。

完整 init 的显式写入及内部校验全部成功后，才发布 manifest/成功 marker。
中途失败保留 DB 现场，普通 start/print-manifest 拒绝为 `acceptance_not_prepared`；
不自动修复、补数据或重 seed。完整但不一致的 manifest 拒绝为 `acceptance_manifest_invalid`。
这不是新增公共 API、Frozen Schema 或产品 ready 状态。

start、应用工厂、print-manifest 及 HTTP 验收入口复用后端只读验证。
无自有容器时 print-manifest 也需显式传入已核验的本地 `--image "$P1_IMAGE"`；
不安装宿主依赖、不下载镜像。停止状态使用 network-none 辅助容器和只读数据挂载；
运行状态先核对实际完整配置，再在确切容器 ID 内执行只读 SQL 校验，以正确读取实时 WAL。
不用 SQLite immutable 模式忽略 WAL，不 checkpoint、不复制运行中 DB，不调用 create/derive。
SQLite WAL/SHM 协调文件不等于业务写入；主 DB、非空 WAL 与业务行的验证另有测试和审计。

任何审计/验证 docker exec 前复用 `check_start_configuration`：完整 ID/Image、用户/目录/
启动命令、loopback 发布、rootfs/cap/security、network/namespace、设备、资源限额、tmpfs、
全部源码只读挂载及唯一数据挂载必须符合预期。只选取必要 inspect 字段，不输出环境变量。
标签只用于所有权，不能代替运行配置检查；stop 仍仅凭已核验所有权停止确切 ID，
不会因自有异常配置而失去停止能力。Docker Desktop UID 0 策略不宣称跨平台通用。

这轮真实 HTTP 仅证明专属合成空间可用；bridge 不是网络层禁外联，Python guard 不是防火墙。
具体失败轨迹、最终测试、HTTP/重启及篡改拒绝证据见新的 R1/R2 ignored 验证目录。
