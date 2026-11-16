# F01—F07 交付验收矩阵

更新：2026-10-23。作者：GPT-6 Codex，单执行者，承担 Root/Terra 实现与自测职责。分支 `codex/delivery-20261030`，HEAD `4132a12d37cbfe871c6b75d49ca51922da190e43`，包含未提交改动。未暂存、提交、推送、建 PR 或合并；所有任务发布状态均为 **NOT_RUN**。本矩阵记录 10 月 22—23 日同一实施任务的实际结果，不将此前其他任务的测试算入验收。

## 验收矩阵

|任务|本轮实现与主要文件|实际验证|未完成、风险与下一步|整项状态|
|---|---|---|---|---|
|F01 Windows＋Docker|`deploy/compose.yaml`、两个 Dockerfile、`delivery.ps1`、`delivery.env.example`、`delivery_acceptance.py`、部署说明；明确评估/P2开关、新项目和卷、国内构建源；修复 PowerShell 空环境变量覆盖 env-file|Compose 常规安全默认检查通过；PowerShell 7 两种 Prepare 配置、隔离地址/卷、继承 Owner/AI 变量隔离与恢复通过；只生成自有 ZIP，零业务 HTTP|Docker Desktop 旧 socket 启动失败；目录备份被拒绝访问，正常 UAC 提升返回取消。镜像构建、容器启动、完整链路及干净机器复现均 NOT_RUN；Windows PowerShell 5.1 本次又遇执行策略禁止，未绕过策略|PARTIAL，目标环境阻塞|
|F02 连续流程与版本|`App.tsx`、Assessment/Remediation/ReportV2、`versionContext.ts`；URL 固定身份、精确读取旧评估、换版本清理下游身份；拒用错误扫描或版本的缓存|前端完整测试清单 152/152；TypeScript 与 Vite 构建通过；包含刷新解析、筛选链接、换版本、错误版本的合成回归|真实新建扫描到各页、前进后退、直接链接、刷新和只读网络检查 NOT_RUN；自测不是浏览器签收|PARTIAL|
|F03 异常与恢复|`p2Recovery.ts`、`p2Workflow.ts`、`P2Workbench.tsx`、P2 Service；POST 前最小 session 标记、原请求丢失只读核对、保留已保存 Result、仅重试 Summary；完整资源映射校验、切版本取消迟到摘要；任务保存失败改为结果待确认|前端测试覆盖同键/异 body、CAS、响应丢失、存储失败零 POST、刷新恢复与 Summary 失败；新增后端资源映射反例|Linux Store/API 回归未运行；真实 timeout/503/刷新故障与双浏览器仍 NOT_RUN。恢复标记不含原 body，丢失 body 时不自动重放；本轮不能宣称所有写操作跨刷新恢复均已验|PARTIAL|
|F04 真实整改复扫|`examples/delivery-remediation/` 自有前后样例，requests 范围声明手改为精确版本；现有 Diff 后端/前端增加显式 ZIP 配对，验收脚本关联两次扫描/任务/报告|前端 ZIP 配对门槛测试通过；自有 ZIP 及输入摘要已生成；新增后端配对边界用例尚待 Linux|**Web 真实整改复扫 NOT_RUN**。Java 两次 CLI 不代替此项；确认配对只是用户声明，不能证明项目来源或确认资源删除；许可 pending 保留|PARTIAL，亮点未验收|
|F05 证据问答|Assessment 页面及既有 `assessment/chat.py`、`service.py`；三类问题、真实运行 trace 持久化、无引用和模型失败说明；新增超时/越界引用反例|纯报告/导出/AI 校验与 transport 合成测试共 156 通过（与 F06 共用，不重复相加）；前端全量通过|新增 Chat Store/API 用例待 Linux；真实模型三问、逐条证据点击、耗时与开关前后事实核对 NOT_RUN。当前授权保持 AI 关闭，不下载或启动模型；确定性 P2 不包装成模型成果|PARTIAL，亮点未验收|
|F06 固定报告与下载|`p1/report_v2_html.py`、ReportV2 页面；固定 scan/input SHA/snapshot 摘要、缺失字段兼容和打印样式；保留 P0 四格式及 V2 HTML/JSON，复用已有任务/NOTICE 快照|与 F05 共用的 156 项测试通过；前端报告测试和构建通过；新增固定身份及未知字段断言|真实界面下载、七字段真实资源映射、中文打印/匿名检查、后续任务不改旧报告、获准停启后同 URL 同字节均 NOT_RUN；合成渲染不算持久化验收|PARTIAL|
|F07 独立 Java 核心|RepositoryScanner、RealRepositoryScan、StructuredReports、DeliveryCoreTest、`backend/java/README.md`；不跟随文件链接、范围版本 unknown、泛 GPL 不猜版本、保留全部 profile、输出拒覆盖|JDK 25.0.2/Maven 3.9.16，`mvn -f backend/java/pom.xml test` **35 通过**；两次受信目录 CLI 实际生成 JSON/CSV/HTML，requests unknown→2.32.3；许可 pending/review_required 保留|本地最低运行门禁通过，发布及另一台交付机复现待完成。不是任意不可信 ZIP 安全入口，不等价于 Python 全扫描器；Java CSV 为其原有字段，不冒充 Web 七字段清单|PARTIAL；本地运行 PASS|

## 实际命令与失败记录

- 前端此前 `pnpm test` 151 通过、`pnpm build` 通过。23 日终端的 pnpm 包装器触发依赖安装检查后因无 TTY 中止；未允许删除或重装 node_modules。改为按 `frontend/package.json` 的同一 13 文件清单运行 `node --test`，最新 **152 通过**；在 frontend 执行 `node node_modules/typescript/bin/tsc --noEmit` 与 `node node_modules/vite/bin/vite.js build` 均通过。没有依赖升级。
- Python 使用已有 3.12 环境与 `-X utf8`，设置 `PYTHONPATH=backend`。`pytest tests/unit/test_p1_report_v2_html.py tests/unit/test_a6_report_exports.py tests/unit/test_a5_ai_provider.py tests/unit/test_a5_ollama_transport.py -q`：**156 通过**。初次混合回归为 62 failed、17 passed、4 errors，包含本轮 HTML 缺失 scan_ref 缺陷（已修并通过上述回归）以及 Windows POSIX/符号链接限制；不能将整组失败都归为环境问题，也不能据后续纯测试宣称 Store 通过。未伪造 geteuid 或删断言。
- Java 首次离线 CLI 因 exec 插件未缓存失败，随后用 pom 已锁定 `org.codehaus.mojo:exec-maven-plugin:3.6.2:java` 经既有镜像运行成功。命令与边界见 Java README。真实 scan ID：before `scn_a96a3d89-b0d7-4aac-a236-e9fc1b3a6409`；after `scn_fc824a76-6ea4-4fd3-b832-7d29cdee7c28`。
- Compose 检查不需要引擎。PowerShell 7 显式调用 `deploy/delivery.ps1 -Action Prepare` 和 `-EnableP2Write` 两模式通过，并检查隔离和环境恢复。PowerShell 5.1 的同命令 23 日返回执行策略禁止，保留原错误；不修改系统策略凑通过。
- 本轮运行日志和输出保留在会话 work 及仓库忽略目录 `.tools/delivery-20261030/work/`，不纳入 GitHub。当前镜像 ID/平台运行回执和真实 Web scan ID 尚无，不能用源码 HEAD 或历史容器替代。

## Docker 修复与权限状态

用户已授权 Docker Desktop、新项目 `openguard-delivery-20261030`、回环 `127.0.0.1:8086`、专属 `openguard-delivery-20261030_data`、P2 TEST_ONLY、AI 关闭、自有样例及浏览器验收，空闲后仅该项目停启一次。23 日又明确授权自动修复，但禁止恢复出厂、删除数据或权限重置。

旧 Ingest socket 的 run 目录此前已原位保留备份；随后错误转为 Secrets Engine 的 engine.sock。只读核对该目录仅有两个零字节 socket。Move-Item 失败并留下空目标目录；Rename-Item 和原位 Directory.Move 都返回拒绝访问，原目录仍保留。最小管理员助手仅尝试备份这两个 socket；Windows UAC 启动返回“操作已被用户取消”，助手没有回执，不能声称修复执行成功。所有备份/失败目标保留，未删除任何数据、重置 ACL 或系统策略。原 Owner/M1/其它项目未操作。

此处是宿主机执行门禁，不缺少重复的项目运行授权。需本机允许正常管理员确认或提供已运行引擎后，再续跑已有命令；不能绕过 UAC。真实模型调用和 Git 发布尚未授权。

## 固定演示顺序与待关门禁

1. Docker 可用后，检查现有容器、端口与专属卷归属；Prepare、Build、Start 均用同一 P2 模式，记录源码改动清单、镜像 ID、实际配置与平台。未获同名卷归属确认时不复用。
2. 在真实页面上传自有 before ZIP，记录输入 SHA、扫描 ID、状态、资源/风险/Evidence；选择固定评估，生成任务并记录修改内容。
3. 在样例副本手动把范围声明改为精确版本；上传 after ZIP，产生新扫描；显式确认 ZIP 配对，读取已有 Diff，保留未知许可与剩余缺口。保存操作记录，不能用 fixture 或数据库改值替代。
4. 关联任务、评估和新报告；跨页、刷新、前进后退与固定链接核对版本；P2 在 TEST_ONLY 下验证恢复/冲突，普通 GET 不创建对象。
5. AI 另获明确范围后，执行依据/缺口/优先事项三问，逐条打开证据并记录实际 trace、失败与耗时；AI 关闭路径也须完整通过。
6. 从页面下载 P0/V2 报告，核对资源、任务、NOTICE、中文、七字段与匿名边界；保存 SHA。活动任务归零后仅对新项目 Stop/Start 一次，`delivery_acceptance.py verify` 只读回原 URL，核对字节不变。
7. 独立 Java CLI 展示三格式与其能力限制。28 日按实际回执冻结，29 日打包/材料/演练，30 日上传复核；日期不替代门禁。

当前能以本轮证据独立运行的是 Java 受信目录核心；前端可构建，纯报告/AI 校验可离线测试。统一 Windows Docker Web 真链、两个真实亮点、浏览器异常恢复、重启持久报告及干净机器复现尚不能宣称可交付。

报名/参赛：由用户核资格、赛道、缴费与提交平台；完整作品：关闭上述运行门禁并核资源权利、匿名材料、视频/PDF/交付包和演示签收；获奖竞争力：另需独立真人 Gold、新盲集、基线/消融及质量性能证据。责任为当前 GPT-6 Codex 继续实现与自测，Root 筛选发布，Sol/Luna/真人独立复核待执行；不虚构已有人签收或完成百分比。

接口影响：Diff 新增可选 `confirm_zip_pair`（默认关闭）；Chat trace 为附加持久字段；HTML renderer 更新，旧保存报告不重绘；现有正式 Schema/许可判断与 M1 STOP 不提升。新增依赖和样例来源见现有资源台账，不另造同义台账。

本次运行精确 token 数不可获得。开工后续实施估算 40,000～80,000 token，前置完整日志阅读未另行估算；新增环境修复与回归属于本轮必要工作，七项尚未完整验收，实际是否落在估算区间不可核定。
