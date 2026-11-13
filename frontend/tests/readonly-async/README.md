# STATIC_CANDIDATE_NOT_EXECUTED

本目录是实际测试源码，全部 **NOT_RUN**。本轮没有执行 Node、TypeScript、测试、构建、Vite、浏览器或产品入口，没有红绿结果，也没有前端接收签收。当前任务禁止浏览器及 serve；以下步骤需要未来另获明确包含本地测试入口与浏览器的执行许可。

兼容边界：当前候选的权限状态在 commit 期 `useLayoutEffect` 更新，scope effect 完成 pending 初始化后才授予 mounted；旧 4 个 VM 测试的 React stub 不含 `useLayoutEffect`，原字节仅保留为输入参考，未来须使用真实 React runtime 验证，不能把旧 VM 的兼容性报错认定为产品回归失败。

`index.html` / `browser.tsx` 使用真实 React 19 `createRoot`、`flushSync` 和 Profiler。每个场景只创建一个 root；切换只读时保持相同组件、相同 Assessment 与相同 DOM subtree。没有 VM fake hooks，也不直接替换 `continueUsageUpdate`、`ensureP2`、`submitWrite`。运行链是实际 `ProjectUsageEditor → projectUsage → assessments/p2 → scans.request → window.fetch`。

`transport.ts` 只替换底层 fetch：逐条记录 dispatch、原始请求体和 SHA-256；严格限定合成路由，未知请求抛错，永不调用原生 fetch。测试结束或失败也不恢复原生 fetch，防止有缺陷的候选出现延迟续写。Index 的 JSON 响应由 deferred gate 控制，在只读 props 的 flushSync commit 后才释放；5 秒只作为失败 watchdog，不用等待时长制造竞态。后续新页面执行应重新加载，不能把失败后的页面当作干净环境。

revision-02 为未知请求建立独立 `unexpectedDispatches` 台账；origin（含凭据/fragment）、method、path 和完整 query 必须精确匹配，每个许可路由最多 dispatch 一次。错 endpoint、额外 query、重复调用、异常输入/请求体在抛错前已经记账；即使产品 catch 吞掉拒绝，各案例最终也必须独立断言台账为空。只读 commit 后对**全部 endpoint 的所有非 GET** 计数并断言为零，同时单列 POST 数，不只过滤预期 parent/results。已发送请求的未知回执拒绝仍保留 dispatch，且不伪造状态码。案例结果包含 `unexpected_dispatches` 与 `readonly_write_checks`；这里依旧没有运行结果。修订前全部 6 文件及 Hash 保存在 TASK/evidence/test-source-revision-02/before，修改 diff 与新 Hash 同目录留档。

所有响应都是显式合成 fixture，标识为 **SYNTHETIC_TRANSPORT_NOT_ASGI**。种子 Assessment POST 只返回合成 202 pending，用于经真实 service 建立待确认操作。Result POST 只记录真实调用链产生的 dispatch，然后让传输回执不可得；没有伪造 201、成功 Result/summary、409/405 或服务端拒绝。测试不证明 ASGI、后端持久化、全机零网络或已发送请求被撤回。页面加载和 Vite 资产流量不属于这个产品 fetch ledger。

覆盖的源码场景：

1. `readonly_pending`：真实 service 生成的原 pending 在只读入口中不得恢复或新建写入；原 key 保留。
2. `readonly_changed_draft`：先在真实 DOM 修改草稿，再同实例切只读，直接派发表单 submit 事件验证入口 guard，避免“用途未改变”造成假阳性。
3. `ordinary_disabled`：普通 disabled 不阻断用户明确点击待确认恢复；真实链在 Index 释放后产生一个 Result POST，Assessment POST 不重发，原 request/idempotency key 保留；回执仍不确定。
4. `parent-forwarding.test.mjs`：用现成 TypeScript AST 检查 P2Workbench 独立传递 readOnly；这是源级对照，不能当作 DOM 或运行证据。原 4 个 VM 脚本保持原字节参考，未运行。
5. `test5_dynamic`：可写点击恢复，真实链暂停于 Index；同 createRoot 同实例提交 readOnly=true；随后释放空 Index；断言新 Result POST=0，Assessment 不重发，原 op/key 与未 attempt 的 P2 状态保留。
6. `revoked_not_revived`：同一挂起任务在只读后又恢复可写，旧 permit 仍不得复活。
7. `post_already_sent`：先证明 Result POST 已 dispatch，再切只读；只要求后续新 POST=0，保留 p2Attempted 和完成未知，不要求取消/回滚已发送请求。
8. `prepared_not_attempted`：真实 service 的 single microtask 前撤权，Assessment POST=0，原 op/key 与 assessmentAttempted=false 保留；普通恢复仍不 POST，必须点击 UI 的“保存原请求”后才以原 key 发送一次。随后只读阻止后续自动续写。

未来经授权的运行准备：在 `TASK/runtime/frontend` 建立获准的完整前端副本，再覆盖候选产品文件与本目录；`candidate/after` 是增量，不能直接当完整前端启动。沿用已存在且获准使用的 React / ReactDOM / TypeScript / Vite 依赖，不安装依赖。用副本自己的现有 Vite CLI 显式指定 `tests/readonly-async/vite.test.config.ts`；不使用原 Vite 配置，不加载原 `.env` 或 proxy。测试配置限定副本布局，`envDir:false`、API base `/api/v1`、loopback、strictPort、hmr:false，cache/outDir 均落 TASK，emptyOutDir:false。计划端口 19873；未来须先经获准方式确认空闲，冲突则失败，不借用现有服务。浏览器地址为 `http://127.0.0.1:19873/tests/readonly-async/index.html`，获准后手动点击一次；初始结果为 NOT_RUN，只有未来真实执行才会生成案例结果。不要通过任意 npm script 隐式启动原配置。

同测试字节的入口 guard 父本对照：另建独立完整副本，使用 `input/reference/candidate/after` 的两个组件及本轮 before 的 `projectUsage.ts`，覆盖**完全相同字节**的本测试目录。其余依赖和 source 与候选一致，使用同样隔离配置、合成传输和浏览器步骤。父本预期差异仅是待验证假设：TEST5 的 Index 释放后可能出现 Result POST，记录在先于拒绝的 dispatch ledger 中；不预填失败，不视为已证实。父本不支持本轮新增可恢复未尝试 API，扩展场景结果须按接口版本解释，不能拿其缺失冒充 TEST5 竞态证据。核心对照只比较 TEST5 的相同源码、同一 deferred 时序和原 key，运行前后记录三个产品源文件与测试文件 hash。

未来输出在 DOM `#results` 和 `window.__OPENGUARD_READONLY_ASYNC_RESULTS__`，包含 ledger、请求体 hash、原 key、storage 快照和 Profiler phase。这里没有生成运行结果文件，`actual_backend_requests` / `asgi_outcome` 保持 null；合成测试结论不能替代真正接收证据。
