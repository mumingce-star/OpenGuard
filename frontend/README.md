# OpenGuard Web

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

本轮unit20通过、TypeScript及生产构建通过；开发服务和生产preview各通过同一套10项真实浏览器检查。覆盖上传/进度/资源风险证据/四格式报告SHA/刷新不重复POST/手机导航/partial/无效ZIP异步failed/404无mock降级/无不支持接口和浏览器运行错误。运行产物留临时目录，不提交仓库。

排队、执行、失败和取消状态只读status；completed/partial才读取结果。明确report_not_ready/not_generated允许展示已有事实而无下载；存储500与任务404仍报错。视觉及来源登记见 `THIRD_PARTY_UI.md`；未引入 React Flow 或新增运行依赖。
