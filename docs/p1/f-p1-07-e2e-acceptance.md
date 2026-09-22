# F-P1-07 全链路验收记录

日期：2026-09-20（2026-09-22 完成最新生产接线隔离复验）
分支：`codex/p1-frontend-integration`
基线：`origin/integration/p1@2bd9ff2`
保留的原 Docker 环境：`http://127.0.0.1:8081/`（旧 `4179` Vite 进程在本轮收尾时未运行，本轮未重启或替换）
本轮隔离联调环境：`http://127.0.0.1:8082/`（从原数据卷复制，写操作不影响 8081）

## 1. 验收结论

F-P1-01 至 F-P1-06 的前端实现已按 History → Resource Cards → Graph → Remediation → Diff → Report V2 顺序集成到现有 P1 React 工作台。最新 `2bd9ff2` 已将 Remediation 与 Report V2 接入生产工厂；前端新增显式 Report V2 创建入口后，类型检查、96 项前端测试、生产构建及真实接口浏览器 smoke 均通过。

F-P1-07 当前结论为 **PARTIAL**。页面与真实接口的已有数据链路可演示；未通过项来自当前真实后端数据集或本机验收基础设施，不由前端伪造补齐：

1. 生产 History 当前只有 11 条，200+ 记录仅由冻结的合成验收数据/前端测试覆盖，尚未完成当前 8081 实例的 205 条浏览器实测。
2. Remediation 成功态已在隔离真实 API 上关闭：从 Formal Assessment 显式派生 88 项任务，todo → in_progress → done、备注、version 和刷新恢复通过；失败回滚与 409 CAS 仍由前端/后端自动测试覆盖，尚缺浏览器并发双会话复现证据。
3. Report V2 成功态已关闭：前端显式创建固定快照，绑定当前 88 个 Task 版本；完整 HTML/JSON GET、页面正文、URL 恢复与下载响应均通过。当前快照没有 NOTICE Draft，页面明确显示缺失且不补造。
4. Resource Profile 基础成功态已关闭：真实 Resource 投影返回 `profile_id`、provider、pending license/authorization 与 Evidence，同时保留 `metadata_observation_unavailable`。远端尚未包含真实生产 Metadata Parser，因此 verified 远程元数据仍不能冒充完成。
5. Windows 目录绑定到验收容器后显示 mode 0777，后端 `root_unsafe` 安全门禁拒绝启动 `/2` 合成验收包。未降低权限、未绕过校验。

## 2. 全链路结果

| 环节 | 结果 | 真实验收事实 |
|---|---|---|
| Landing | 通过 | 首页可见，工作台入口和产品语义正常 |
| New Scan | 通过（未提交新扫描） | 真实接口模式可见；ZIP/Git 输入与用途选择不推断授权 |
| Progress | 通过 | `scn_9a0...` 明确显示 partial、3 项覆盖限制，未解释为失败或删除 |
| History | 通过；规模项受限 | 真实 11 条记录，completed/partial/failed 可辨识；筛选 URL 可恢复 |
| Assessment | 通过 | `asm_0b4...` 为 Formal Assessment v1；“证据不足”未提升为许可通过；Obligation 为空时如实显示 |
| Resource Card | 基础成功态通过；真实远程元数据受限 | Profile GET 返回正式 `profile_id`、provider、pending/unknown、Evidence 与 `metadata_observation_unavailable`；不提升为 verified |
| Resource Graph | 通过 | 真实 123 节点/136 边；只渲染后端节点和边；搜索、筛选、缩放、侧栏语义可用 |
| Finding/Evidence | 通过 | Finding 使用“待核查线索”语义，资源/Assessment/Graph 链路可追溯 |
| Scan Diff | 通过 | 真实 base/target、revision、覆盖状态及 API 差异；无 Assessment 时不伪造变化；partial 不等于删除 |
| Remediation | 真实成功态通过 | 显式派生 88 项；状态、备注、version 与刷新恢复通过；done 文案不等于项目合规；回滚/CAS 自动测试通过 |
| Report V2 | 真实创建、读取与下载通过 | 显式 POST 创建固定快照，URL 恢复；313,209-byte JSON 与 605,940-byte HTML 下载均返回 200；NOTICE 缺失不伪造 |

## 3. 自动验证

- `npm test`：96 passed，0 failed。
- `npm run build`：TypeScript 检查通过；Vite 构建通过；54 modules transformed。
- 产物：JS 383.52 kB（gzip 119.01 kB），CSS 55.84 kB（gzip 13.21 kB）。
- `git diff --check`：通过。
- `npm run test:browser:p1`：14 passed，0 failed；使用 4179 → 8081 真实只读接口，无请求拦截或 Mock 回退。
- 浏览器回执：`output/manual-fixes/p1-frontend-browser-20260921-0225/receipt.json`；同目录保留 14 张全链路、窄屏与打印截图。
- History 测试：含 205 条游标分页、筛选、URL 恢复、empty/error/retry。
- Graph 测试：100/300/500 节点通过，无新增图谱依赖。
- Remediation 测试：状态更新、失败回滚、409 CAS 重读、Evidence 链路、空结果通过。
- Diff 测试：相同扫描不请求、不同版本、partial、无 Assessment、500 行规模通过。
- Report V2 测试：固定快照契约、长报告、缺失/下载失败/P0 回退路径通过。

2026-09-22 隔离真实 API 复核：History 11 条；Profile 基础 GET 200；从 `asm_0b42...` 显式派生 88 项任务并完成一次 todo → in_progress → done；创建 `rptv2_94d3...` 固定报告并读取 HTML/JSON。写操作只发生在复制数据卷；原 8081 未改。随后连续读取 History、Assessment、Profile、Graph、Diff、Task 与 Report V2，四个 SQLite 文件 SHA-256 前后一致，且隔离环境禁用 AI 与公网 Git，证明这些 GET 未隐式创建扫描、评估、任务、报告或调用 Qwen。

## 4. 状态与可访问性检查

- loading、empty、partial、error、retry：组件测试覆盖；partial、Profile 404、Task empty、Report 404 已由真实浏览器看到。
- URL 恢复：History 的 `status=partial&q=axios&limit=20`、Diff 的 base/target、Report 的 assessment/snapshot 均可从 URL 恢复。
- 键盘：History 行通过聚焦 + Enter 打开并由浏览器 Back 恢复；Graph 节点通过键盘打开详情，主要内容 skip link 与原生控件保留。
- `prefers-reduced-motion`：浏览器在 reduce 模式下完成 Graph 交互与截图，工作台降动效规则生效。
- 窄屏与打印：390px History/Graph 未出现页面级横向溢出；打印媒体隐藏应用导航并保留报告正文。物理打印机输出不属于本轮自动化证明。
- Mock 隔离：真实模式明确显示“失败不会回退演示”；真实页面未载入 DEMO 数据。

## 5. 页面与状态截图

`output/manual-fixes/p1-frontend-browser-20260921-0225/` 已自动截取：Landing、New Scan 真实模式、partial Progress、History 全部/筛选恢复、Formal Assessment、Resource Cards、Graph 键盘详情、Diff、Remediation 当前状态、Report V2 缺失/P0 回退、History/Graph 窄屏、P0 报告打印，共 14 张。

后端成功态到位后仍需补截：

1. 真实 205 条 History 的中间页与末页。
2. 100/300/500 真实 Graph 三档（当前仅自动测试/合成验收覆盖规模算法）。
3. 非空 Remediation 状态更新、失败回滚和 CAS 冲突。
4. Profile 成功态的 pending/verified/unknown 与 Evidence。
5. 完整 Report V2 长报告、P1 HTML/JSON 下载及 NOTICE Draft。

## 6. 5—7 分钟团队演示脚本

1. **0:00–0:35**：Landing 说明 OpenGuard 将扫描事实、正式评估和 AI 解释分层。
2. **0:35–1:05**：New Scan 展示真实模式与用途未知，不实际提交扫描。
3. **1:05–1:35**：打开 partial Progress，强调“部分完成不等于失败，也不代表资源被删除”。
4. **1:35–2:10**：History 按状态筛选并复制 URL，刷新后展示恢复。
5. **2:10–3:00**：Assessment 展示 Formal Conclusion、Evidence 缺口和未确定 Obligation。
6. **3:00–3:45**：Resource Cards 展示 provider、revision、verification、Evidence 与 Profile 缺失态。
7. **3:45–4:30**：Graph 搜索一个资源、缩放、打开详情并说明虚线/不确定语义来自后端。
8. **4:30–5:10**：Diff 比较两次真实扫描，指出无 Assessment 与 partial 的保护文案。
9. **5:10–5:40**：Remediation 展示空结果和任务状态语义；说明真实 Task 到位后才能演示 CAS。
10. **5:40–6:30**：Report V2 展示快照缺失不会伪造报告，并演示 P0 独立回退入口。
11. **6:30–7:00**：总结 95 项测试、构建通过和仍需后端提供的数据门禁。

## 7. 第三方 UI 资源、许可证与 NOTICE

本轮没有新增依赖。沿用锁文件和 `third_party/README.md` 已登记资源：

| 资源 | 锁定版本 | 许可证 | 用途/NOTICE |
|---|---:|---|---|
| react | 19.2.8 | MIT | 浏览器 UI；构建产物附原文 |
| react-dom | 19.2.8 | MIT | DOM 渲染；构建产物附原文 |
| scheduler | 0.27.0 | MIT | ReactDOM 运行依赖；构建产物附原文 |
| tailwindcss | 4.3.3 | MIT | CSS 构建；构建产物附原文 |
| @tailwindcss/vite | 4.3.3 | MIT | 构建插件，不进入最终运行依赖 |
| typescript | 5.9.2 | Apache-2.0 | 类型检查；保留 ThirdPartyNoticeText |
| vite | 8.2.2 | MIT + 内嵌组件许可 | 构建工具；保留随包 LICENSE |
| @types/react | 19.2.18 | MIT | 构建期类型 |
| @types/react-dom | 19.2.5 | MIT | 构建期类型 |

`vite.config.ts` 从安装包读取 React、ReactDOM、scheduler、Tailwind 许可并生成 `dist/third-party-licenses.txt`；缺少原文时构建失败。图谱使用现有 React/CSS/SVG 能力，没有引入图谱库。

## 8. 建议 PR（仅建议，未创建）

标题：`feat(frontend): integrate P1 history, resources, graph, remediation, diff and report views`

描述：

> 在现有 P1 React 工作台中按 F-P1-01 至 F-P1-06 顺序集成真实 History、Resource Cards/Profile、Resource Graph、Remediation Workbench、Scan Diff 和 Assessment Report V2 页面。所有正式结论继续由后端 Assessment/Report 快照提供，前端不推断许可证、授权、关系或差异。补充 URL 恢复、loading/empty/partial/error/retry、CAS 回滚、Evidence 跳转、reduced-motion、响应式与打印样式。前端 95 项测试及生产构建通过；真实 8081 浏览器 smoke 覆盖现有 10 条历史、123 节点图、partial 扫描、无任务及 Report V2 404/P0 回退。剩余真实 205 History、非空 Task/CAS、Profile 成功态与完整 Report V2 快照由后端验收数据到位后补验。

## 9. 进入最终签收前的门禁

- 后端提供当前环境可访问的 205 条 History 验收数据，或解决 Windows bind mode 0777 与安全根目录要求的冲突。
- 后端提供至少一组非空正式 Remediation Task，并保留可复现 409 CAS 场景。
- 后端提供成功的 Resource Profile 样本，含 pending/verified/unknown 与 Evidence。
- 后端提供至少一份完整 Report V2 快照及 HTML/JSON 下载，包含长报告和 NOTICE 草稿场景。
- 在非主开发机完成一次同构建、同脚本复现；P1 下载成功态到位后核对下载文件内容。

在上述门禁关闭前，不把 F-P1-07 标记为 COMPLETE，也不把当前 unknown/pending/partial 状态包装为已合规。

## 10. 2026-09-22 后端生产接线复验增量

### 本次关闭的前端缺口

- Report V2 增加“创建固定版本报告”显式写入口；仅绑定用户选定的 Formal Assessment 与服务器当前 Task 版本。
- 请求中的 `notice_refs` 与 `algorithm_refs` 保持空数组；前端不猜测 NOTICE、Graph 或授权引用。
- 创建成功后将 `assessment_id` 与 `snapshot_id` 写回 URL，并继续使用既有 GET reader 读取后端保存的 JSON/HTML。
- Resource Profile 基础成功态、Remediation 派生/状态/备注/version/刷新恢复、Report V2 长正文及 P1 JSON/HTML 下载完成真实浏览器联调。
- 390px Report V2 无页面级横向溢出；正式评估、AI 建议、NOTICE 草稿和 Provenance 继续保持视觉与文案边界。
- Docker 构建上下文排除本机 `frontend/node_modules/`，避免 Windows junction 进入 Linux build context；没有改变依赖或运行时行为。

### 仍未关闭的门禁

1. 远端 `origin/integration/p1` 经再次获取仍为 `2bd9ff2`；截图中 B01 Metadata Parser、NOTICE facts v2 标为“未提交、未推送”的内容没有进入正式远端，不能作为前端已可消费能力。
2. 当前真实 History 仍为 11 条。205 条仅有冻结验收包/单元测试证据，尚缺当前正式历史库的浏览器分页签收。
3. 100/300/500 Graph 已有冻结后端验收包与前端布局测试证据，尚缺当前正式数据环境三档浏览器截图与性能回执。
4. 当前 Assessment 的 `obligations` 为空，88 项 Task 均来自 gap/next_step；页面正确显示“未提供直接关联”，但尚缺非空 Obligation 的真实浏览器链路。
5. 当前报告快照没有 NOTICE Draft/图谱观察引用；Report V2 正确显示缺失，但 NOTICE 成功态仍等待后端正式发布。
6. CAS 409、PATCH 失败回滚、下载失败已由自动测试覆盖；最终团队验收仍建议补浏览器双会话冲突和受控失败截图。

因此，本轮关闭了此前由生产接线阻塞的 Profile 基础、Remediation 成功态和 Report V2 成功态，但 F-P1-07 总体仍为 **PARTIAL**，直到上述真实规模、Obligation、Metadata/NOTICE 与跨机复现门禁关闭。

## 11. 2026-09-23 新基线前端补齐与真实接口复验

当前分支已安全快进到 `origin/integration/p1@b76e532`，保留所有未提交前端成果。验收使用独立 Compose 项目、隔离数据卷与 `http://127.0.0.1:8082/`；没有替换原 8081 数据。

### 本轮已完善

- Resource Card 增加显式“刷新真实元数据”操作；普通 GET 不会远程抓取。刷新返回 job/item/status/observation 后才展示观测。
- 元数据 observation 展示 provider、requested/resolved revision、source URL、观测时间、字段定位与逐字段 verification status；长 ID 可换行。
- Report V2 增加显式 NoticeDraft 创建入口；只把后端返回的 `draft_id` + `content_hash` 固定进报告，不在浏览器组装 NOTICE、license、authorization 或 Obligation。
- NoticeDraft 未配置时展示明确的生产接线缺失原因；历史 Report V2 仍可从 URL 刷新恢复。

### 真实环境证据

- 对 `scn_df75e81b-d5cd-43d9-b91c-3f71ddb6cf59` 的 Hugging Face 模型显式刷新成功：job `prj_92561eb02616451fa469b5dcd65b2850`，observation `obs_d80f343e65013ddb432bd7ecdd65b3d4ebf742bdc8cc1c8c1d028568a35f2f3f`。
- 后端返回 resolved revision `e502dd4100cc68c0de57643fd4317ec93a128670`、visibility/public、gate/ungated、disabled/false 及声明 `apache-2.0`。页面仍将 license 声明显示为“待核验”，没有提升为正式许可结论。
- NoticeDraft POST 真实返回 `503 feature_disabled / notice_not_configured`；前端显示“需后端注入 NoticeDraftService 与真实 NoticeFactsReader”，不回退 Mock。
- History、Assessment、Profile、Graph、Diff、Remediation、Report V2 JSON/HTML 的真实 GET 均成功；读取前后 `scans.db`、`assessment.db`、`remediation.db`、`report_v2.db`、`metadata.db` SHA-256 全部不变。
- `npm run test:browser:p1`：14/14 通过，真实 `8082` API、无 Mock/请求拦截；回执与 14 张截图位于 `output/p1-browser-20260923/`。
- `npm test`：102/102；`npm run build`：TypeScript + Vite 通过（55 modules，JS 391.15 kB / gzip 120.54 kB，CSS 57.27 kB / gzip 13.44 kB）；`git diff --check` 通过。

### 仍无法由前端完善的项目

| 缺口 | 不能由前端完成的原因 | 后端需提供 |
|---|---|---|
| NOTICE 真实成功态 | 默认工厂未注入 `notice_draft_service`，真实 POST 为 503 | 在默认生产工厂注入已初始化的 NoticeDraft store/service 和真实 Notice facts reader；提供可创建/查询的样本 |
| Report V2 固定 NOTICE | 生产 Report V2 没有 NoticeDraft reader，非空 `notice_refs` 会 409 | 把同一不可变 NoticeDraft store reader 注入 ReportV2Service，并提供含 NOTICE 的 JSON/HTML 快照 |
| 非空 Obligation 链路 | 当前 Assessment/NoticeDraft 的 `obligation_refs` 为空；前端不能把 Finding/Task 推断为法定义务 | 提供经正式规则生成、与 Evidence/Resource/Assessment 绑定的 Obligation 事实与真实样本 |
| 205 条真实 History | 当前隔离库仅 11 条；205 只是 fixture/单测，不能冒充生产历史 | 提供实际 205+ Registry 记录或可安全导入的真实验收数据卷 |
| 100/300/500 真实 Graph | 新提交是冻结 fixture，不是真实扫描 API 环境 | 提供三个真实 scan_id，Graph API 分别返回对应规模的节点/边及 coverage/capacity 信息 |
| CAS 双会话浏览器证据 | 自动测试已覆盖 409 和回滚，但当前没有专用于重现的受控任务 | 提供一个可重置的非空 Task 验收集，允许两个会话使用同一旧 version 稳定触发 409 |
| 跨机发布复现 | 本轮只证明当前 Windows + Docker Desktop 机器 | 提供锁定镜像/配置、安全的验收数据包及 Linux/第二台机器运行回执 |

结论：前端目前能完成的 Profile/NOTICE/Report 接线和错误表达已完成；F-P1-07 仍为 **PARTIAL**，剩余项均需后端生产接线、真实事实或最终发布环境，不应由前端推断或伪造。
