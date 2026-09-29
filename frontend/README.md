# OpenGuard Web

2026-09-07：终态 JSON 报告已有不可变 Evidence 时直接复用，先校验任务身份和证据编号，仅对缺失 ID 调用单证据接口。700 条证据回归用例只需8次API请求。进度条绑定后端百分比；partial 明确为已结束且可查看已有报告，不补成100%。公开 Git 的 ingestion 阶段目前还包含受控工具扫描，AI 阶段仍逐条生成，阶段内百分比可能保持不变。

复用组员 `83e8928` 的核心页面，接入现有 P0 六 API。默认真实接口，演示模式必须主动选择；请求失败不会返回模拟结果。

## 本地启动

先按 `../backend/README.md` 启动真实后端，监听 `127.0.0.1:8000`。前端使用现有锁文件安装依赖：

```bash
pnpm install --frozen-lockfile
pnpm dev
```

打开 Vite 显示的本机地址，进入工作台，选择 ZIP 并提交。扫描完成后依次查看概览、风险详情与证据、资源清单、报告。四种下载均读取后端已发布产物；浏览器刷新按任务编号恢复，不重新上传。

Vite 开发及 preview 均将同源 `/api` 代理到后端。`pnpm build && pnpm preview` 可核验生产构建；preview 仅用于本地预览，尚不等于 Compose／生产部署。

可选环境变量：

- `VITE_DATA_MODE=mock`：默认进入固定合成演示；不扫描上传内容。
- `VITE_MAX_ZIP_MB`：额外的浏览器大小预检；未设置时由后端限制。

公开 Git 需后端管理员显式启用；默认关闭时显示后端错误。前端不调用额外仓库预验证、修改风险或图谱接口。

## 范围与数据

页面：新建扫描、进度、概览、风险详情、资源清单、报告。许可证声明 `pending` 显示待核验；信息级 `review_required` 不提升为高风险。真实结果只读，没有人工处理或复扫确认能力。没有报告时不伪造许可证、时间或下载。

状态、资源、风险与证据来自冻结 API；终态 JSON 报告补充其已保存的许可证、项目、时间及整改字段。页面不是新的公共 DTO 或报告标准。完整 ScanCode／Syft、AI 资产接线及陌生机部署仍待验收。

```bash
pnpm test
pnpm build
```

测试覆盖 mock 兼容、真实 DTO 适配、202 请求形状、错误与取消、pending/info 语义及固定下载端点。真实浏览器测试使用已启动的真实后端和Vite，动态生成ZIP，不拦截伪造API响应：

```bash
# 环境需可用的 Playwright 与 Chrome；OPENGUARD_PLAYWRIGHT 可指定已有包路径。
# OPENGUARD_PYTHON 可指定用于生成临时ZIP的Python，默认python3。
OPENGUARD_TEST_URL=http://127.0.0.1:5173 pnpm test:browser
```

P1 工作台另提供只读全链路 smoke。它动态选择真实 History、Assessment、Resource、Graph 与 Diff 数据，不创建扫描、评估、任务或报告；同时检查 URL 恢复、GET-only、键盘、reduced-motion、390px 窄屏和打印媒体，并生成截图与 JSON 回执：

```bash
# OPENGUARD_PLAYWRIGHT 指向现有 Playwright 包；不会安装新依赖。
OPENGUARD_TEST_URL=http://127.0.0.1:4179 \
OPENGUARD_QA_OUTPUT=../output/manual-fixes/p1-frontend-browser \
pnpm test:browser:p1
```

后端未提供的 Profile、Remediation 非空状态或 Report V2 快照会按真实缺失态验收，不会由 Mock 补成成功结果。

Profile Metadata 只在用户点击“刷新真实元数据”后发起 `POST /resource-profiles/refresh`；普通页面读取不会抓取远程元数据。页面逐字段展示后端 observation 的 `pending` / `verified` 状态，声明中的 license 不会被前端提升为已核验许可。

Report V2 中的 NOTICE 同样是显式写操作：前端先请求后端不可变 NoticeDraft，再将返回的 `draft_id` 和 `content_hash` 原样固定到报告请求。浏览器不自行生成 NOTICE 或 Obligation。

## A3 消费兼容（待 Owner Review）

本地同步后端 `064a3d03c4f087bdbfc96e7564ac4a77fae4a11c`。默认工厂在 `OPENGUARD_ENABLE_ASSESSMENTS=1` 时已配置 BOUND 消费与 Report Notice reader；这不表示每个扫描都存在 BOUND，也不表示 source lifecycle 已完成。

前端按 HTTP 状态及后端 reason 区分：409 `notice_source_not_bound`（无精确 BOUND）、409 `notice_source_binding_mismatch`（固定绑定不一致）、503 `notice_source_unavailable`（暂不可读）、503 `notice_source_invalid`（完整性失败）、503 `notice_not_configured`（服务未配置）。其他错误保留实际诊断，不统称“尚未接线”。Report 引用不存在的草稿显示 404 `notice_draft_not_found`；旧 409 reader-unavailable 仅保留兼容，不作为当前默认预期。

`notice-bound/1.0` 与历史 `notice/1.0` 使用相同公开 1.0 草稿结构。正文、摘录及缺口均来自后端；空许可证/义务引用保持未知，不是“无义务”。创建和重试只由明确按钮触发；刷新、分享、下载只 GET 已保存快照。Profile 仍按原 ScanRun/facts/resource 读取，不承担 NOTICE 或正式评估职责。

已存在依赖时，在仓库根使用以下命令；本任务不安装依赖：

```bash
cd frontend
pnpm test
VITE_API_BASE_URL=/api/v1 pnpm run build
OPENGUARD_API_PROXY_TARGET=http://127.0.0.1:18011 pnpm exec vite preview --host 127.0.0.1 --port 15174 --strictPort
```

P1 smoke 还需显式选择 P0 场景。按本机实际 manifest 设置 `OPENGUARD_P0_REPORT_SCENARIO=available` 或 `not_generated`、完整 `OPENGUARD_P0_SCAN_ID`；后一种需通过 `OPENGUARD_P0_NOT_GENERATED_SCAN_IDS` 列出本次页面实际读取的无报告扫描，不能泛化允许所有 409。然后用已有 Playwright 跑 `pnpm run test:browser:p1`。只在独立数据副本验收写操作；无 exact BOUND 时记录 `A3_BACKEND_AVAILABLE_BUT_SAMPLE_BOUND_MISSING`，不伪造成功态。

本轮unit20通过、TypeScript及生产构建通过；开发服务和生产preview各通过同一套10项真实浏览器检查。覆盖上传/进度/资源风险证据/四格式报告SHA/刷新不重复POST/手机导航/partial/无效ZIP异步failed/404无mock降级/无不支持接口和浏览器运行错误。运行产物留临时目录，不提交仓库。

排队、执行、失败和取消状态只读status；completed/partial才读取结果。明确report_not_ready/not_generated允许展示已有事实而无下载；存储500与任务404仍报错。视觉及来源登记见 `THIRD_PARTY_UI.md`；未引入 React Flow 或新增运行依赖。
