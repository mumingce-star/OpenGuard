# P1 P2 前端交付给后端 B 的接收回执

记录时间：2026-10-13 12:53（Asia/Shanghai）。操作者：xzb 前端工作线 / Codex。本回执对应收到的《P1 P2 前端协作资料清单》（原件 SHA256 `9506146a47a76630a3be19d4b6860a2a464ce40e830995ab61c967f9b6b515bf`）。状态：**源码与构建证据已交；本轮同版真实 API 接收未运行**。这里的 PASS 仅覆盖表中明确写出的范围。

## 1 版本及环境身份

| 对象 | 本机实测身份 | 证据级别 |
| --- | --- | --- |
| 前端分支和 Git 基点 | `codex/p2-readiness`，`9ad9998d6f3df82618966c5865d13006a1efe6bc` | 本机 Git；不能代表未提交的完整前端 |
| 当前前端源码 | 81 个 Git 可见文件；聚合 SHA256 `c92a2143f1cdc46f903089f22237a62b95f183f75dd0111b78bfa991d5a732bd` | `P1_P2_FRONTEND_SOURCE_20261013.json` 包含逐文件路径、字节数、Hash 和聚合算法；全部为当前工作树原始字节 |
| 本轮前端构建 | TypeScript `tsc --noEmit` PASS，Vite v8.2.2 PASS，60 modules；`dist` 4 文件聚合 SHA256 `d4164a7c28ea89dbb762ab81de9ef2eb72a08f0ab939168e208d32d9440ad527` | 本机新构建；算法：相对 `dist/` 的路径按序排列，逐项 `lowercase_sha256 + 两空格 + 相对路径 + LF`，整体 UTF-8 SHA256 |
| 构建细项 | `index.html` 644 B / `d22d4ed9482da09b76750f0214379fdff2892d1ed7ee984e87c92169a250096c`；JS 434320 B / `4e96f8e0afeb58f3a165125045190f6aca4be3808732219d362b0d9dae69e2b8`；CSS 61657 B / `99c05b41404057b39d58201d34807de0aa6cd247956999dd0c9349d2f1e21579`；第三方许可文件 4618 B / `fb50515ff9316032a876ad16ef1e8dc36a2e7cd46a5dc62c3250a6b82bdf6d25` | 文件名分别为 `index.html`、`assets/index-Fafhyjyf.js`、`assets/index-iF46E1qF.css`、`third-party-licenses.txt` |
| 本机预览 | `http://127.0.0.1:4182/`，首页及 JS/CSS GET 均 200，返回字节 Hash 与上述新构建一致 | 静态前端可访问；不证明 API 正常 |
| 平台和浏览器 | Windows NT 10.0.26200.0；本轮未打开连接真实 API 的浏览器会话，因此无当前真实浏览器版本/截图 | 实测平台；浏览器现场项 NOT_RUN |
| 后端/Schema 组合 | 协作清单引用本地整合 `7dce111`；本工作树无该 Git 对象。GitHub 443 连接失败，不能核对同版 A 服务或冻结 Schema | **版本组合未签收**，不能用旧候选代替 |

构建聚合 Hash 只识别这四个编译产物；源码聚合 Hash 识别当前未提交工作树。两种 Hash 不与 Git commit SHA 混用。前端预览页的静态响应也不作为真实接口结果。

## 2 本轮验证和已有证据等级

- `frontend/npm test`：**142 PASS，0 FAIL，0 SKIP**；含 History 205 条分页、P1 Profile/Graph/Remediation/Diff/Report 与 P2 读取、保存边界、CAS/幂等逻辑。测试中的模拟响应只证明前端行为。
- `frontend/npm run build`：TypeScript 检查与 Vite 构建 PASS。`git diff --check` PASS。未新增依赖、后端代码或公共 Schema 改动。
- 已交统一 TEST_ONLY 候选与记录 HTTP 的静态 DTO 核对见 `P2_D1_REFRESH_RECEIPT_20261012.md`、`P2_STAGE2_TO_5_RECEIPT_20261013.md`；不能升格为本机真实 API。
- 最近 TEST_ONLY 浏览器回放见 `tmp/p2-stage2to5-20261013/browser-7/receipt.json`：11 个声明检查通过，78 次被拦截请求（4 次模拟 POST），对真实后端发出 0 次请求。390px、键盘、reduced-motion、打印、固定 URL、错误恢复仅为该测试等级。截图仍在同目录，须保留 TEST_ONLY 标识。
- P1 旧版真接口 E2E 见 `docs/p1/f-p1-07-e2e-acceptance.md`：它属于 2026-09 的 `2bd9ff2` 隔离环境，不能签收协作清单所说的当前 r2 同对象链。

## 3 P1 逐场景接收状态

| 场景 | 本轮结论 | 当前可复用的前端能力及尚未完成的现场证据 |
| --- | --- | --- |
| F01 History 与 F05 Diff | **NOT_RUN 同版真实实例** | 页面已有游标、筛选、URL 恢复、partial/coverage 和后端 Diff 展示；本轮无同版 scan 对、实际分页 HTTP、before/after 响应或截图。旧版真接口回执只作历史证据。 |
| F02 Resource Card / Profile | **NOT_RUN 同版真实实例** | 已有身份、revision、字段来源、pending/unknown/verified、缺口及 refresh 状态；本轮无当前 Profile GET、刷新 Job 或失败态现场响应。不得把许可证观察写为授权。 |
| F03 Graph | **NOT_RUN 同版真实实例** | 页面仅用后端边/节点且覆盖 partial/容量、搜索筛选；本轮无当前图谱响应、实际节点边数、截图。 |
| F04 Remediation | **NOT_RUN 同版真实实例** | 任务 version、expected_version、备注与状态、乐观回滚/CAS 的前端测试通过；本轮没有获准同对象 PATCH、双会话 409 或刷新读回。done/dismissed 不代表 Formal 改变。 |
| F06 NOTICE / Report V2 | **NOT_RUN 同版真实实例** | 界面区分事实、草稿和 Formal 快照，缺失原文明确显示；本轮没有当前 Draft/Snapshot ID、下载原字节 Hash、恢复或报告正文截图。不得用许可字符串代替 NOTICE 原文。 |
| F07 全链路 E2E | **NOT_RUN 当前接收机** | 旧 P1 历史回执可复用为回归参考；同 scan/Assessment/Draft/Report 的当前版本网络、截图、重启与旧版读取没有现场结果。 |
| Bench / 性能可选项 | **NOT_RUN** | 本轮没有经确认的 artifact、Gold、配置、样本数或运行耗时；不报告正式 Precision/Recall/F1 或 Pipeline p50/p95。 |

## 4 P2 逐场景接收状态

统一路径合同已由本地前端静态校验：`/api/v1/scans/{scan_id}/assessments/{assessment_id}/p2`，固定结果、回答、材料及同版 Summary 读取携带 `assessment_version`。前端 Result revision 与父 Assessment version 分开，Summary 显示为非 Formal。以下现场项均没有本轮真实请求响应，不能填写 HTTP 201/409/503 为实际结果。

| 场景 | 本轮结论 | 已有逻辑证据 / 实际缺口 |
| --- | --- | --- |
| 固定 Binding、Result、Answer、Material、Summary 精确 GET | **NOT_RUN LIVE** | DTO/错绑/固定版本单元测试及已收 HTTP 静态回放通过；没有当前同版完整 URL、响应、Hash 和截图；404 不自动改选 latest。 |
| Answer 与小材料 POST 201、Receipt、GET 读回 | **NOT_RUN LIVE** | 显式提交、≤65536 字节、最多 20 份、原字节 Hash、待核验语义已有测试；没有获准可重置数据根上的原请求、201 和读回。 |
| 双会话 CAS 409、重读和明确后续动作 | **NOT_RUN LIVE** | UI 不自动合并或覆盖；没有两个独立浏览器上下文的实际 409 回执。 |
| 同 key 同 body 幂等、同 key 异 body 409 | **NOT_RUN LIVE** | 原请求体和键在当前标签页内存保留并可显式恢复；没有服务端幂等读回或异体冲突网络回执。 |
| timeout/503 后先读后重放；Summary 单独失败 | **NOT_RUN LIVE** | 测试回放覆盖未知态、手动重放、Result 已保存但 Summary 缺口；没有真实网络故障回执。跨刷新未决请求恢复**未实现**，须保持为明确产品限制。 |
| 旧新版、recomputed/reused、同版 Summary | **NOT_RUN LIVE** | 前端可并排显示指定前版/本版的后端原值且不自算差异；未在同一真实父对象上核对不可变旧版及新 revision。 |
| 状态、gap、basis、权限与刷新/重启 | **NOT_RUN LIVE** | candidate_only、USER_ASSERTED、pending、partial、unknown 等静态/回放可辨；没有当前服务的权限拒绝、重启读回或真实截图。 |

## 5 本机接收阻塞与下一次执行入口

本轮只读探测：`127.0.0.1:8081`、`8082`、`15174`、`15175` 的 `/` 均为**连接拒绝，未产生 HTTP 状态码**；`docker info` 报 `npipe:////./pipe/docker_engine` 不存在。本地 Git 中也没有协作清单引用的 `7dce111`；`git ls-remote origin` 因 github.com:443 连接失败。这些是本机运行和版本核验未就绪，**不是后端 B 未交付的证明**。既有统一 TEST_ONLY ZIP、源码/DTO和 HTTP 记录已收到，不再重索。

运行条件恢复后，xzb/Codex按同一获准版本先核源码/Schema/镜像/数据根及只读范围，再以完整 scan_id、Assessment ID/version 执行 P1 同对象链。P2 固定 GET 和快照下载先读；写入/CAS/故障重放只在可重置 TEST_ONLY 副本执行。每项记录实际操作者、UTC 时间、原请求/响应或脱敏 HAR、状态码、对象完整 ID/Hash、截图、刷新及重启结果。真实材料、生产 NOTICE、真人许可审核分别签收，不能由回放代替。

**交给 B 的处置结论**：当前没有本轮真实 HTTP 缺陷可归因于 B。B 可先核本回执与逐文件源码 Hash；待同版环境可达后再凭明确 URL、JSON Pointer、预期/实际和最小复现判断缺陷。无需重复提交已收 TEST_ONLY 包，也不依据本机网络失败认定远端分支未上传。
