# OpenGuard Frontend

面向 AI 开源项目的可解释合规扫描工作台前端框架。

## 当前页面

- `/`：品牌首页，原创 Canvas 粒子文字 `OpenGuard`
- `/app/new-scan`：GitHub / ZIP 扫描入口
- `/app/progress`：七阶段扫描进度与实时发现流
- `/app/overview`：扫描概览、指标、风险分布与优先风险
- `/app/risk`：规则判断、扫描事实、AI 解释、证据链与整改建议
- `/app/resources`：资源类型筛选与许可证状态
- `/app/graph`：风险路径优先的轻量关系图
- `/app/report`：合规报告预览与 JSON 导出

当前数据均来自 `src/mocks/data.ts`，不依赖后端即可完成比赛演示。后续接 FastAPI 时，建议新增 `src/services` 与 adapter 层，页面只消费 domain model。

## 本地运行

```bash
pnpm install
pnpm run dev
```

默认访问 `http://127.0.0.1:5173/`。

## 构建

```bash
pnpm run build
```

## 环境变量

复制 `.env.example` 为 `.env.local`，不要把真实 Token 或 API Key 放进前端或提交记录。

- `VITE_API_BASE_URL`：FastAPI 地址
- `VITE_DATA_MODE`：`mock` 或 `api`

## 设计原则

- 近黑蓝工作台、靛蓝到青色高亮、克制辉光。
- 首页只保留粒子文字一个主视觉动效。
- 工作台优先信息可读性，区分“扫描事实 / 规则判断 / AI 推断”。
- 支持 `prefers-reduced-motion`；页面隐藏时粒子动画暂停。
- 1280×720 投屏、桌面与 390px 移动端均设置响应式布局。

第三方与视觉参考见 `THIRD_PARTY_UI.md`。
