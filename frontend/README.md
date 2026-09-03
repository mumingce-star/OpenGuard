# OpenGuard Frontend

AI 开源合规与溯源工作台。保留品牌粒子首页与发光光标；工作台围绕同一任务的资源、风险、证据和报告组织。

## 运行与构建

使用 Node.js 24 与 pnpm 11（本轮实际验证环境）。在 frontend 目录运行：

```bash
pnpm install --frozen-lockfile
pnpm dev
pnpm test
pnpm build
```

默认地址 http://127.0.0.1:5173；本轮独立预览使用 5174：`pnpm dev --port 5174 --strictPort`。
部署到静态服务器时，需将工作台路径回退至 index.html，才能刷新深层链接。

## 体验路径

1. 首页点击“加载演示项目”，或工作台点击“载入固定演示”。
2. 进度页可等待、跳过等待或重新开始演示。
3. 概览指标可跳到对应筛选；风险详情展示自身资源与证据。
4. 资源详情、图谱节点都使用同一证据阅读器。
5. 报告包含六个真实章节，可导出完整 JSON；资源 CSV 只导出当前筛选范围。

演示场景包含标准、无风险、无资源、证据缺失/AI 失败、部分失败和任务失败。它们是合成 fixture，不会读取用户仓库或 ZIP。演示快照存放在当前浏览器 localStorage；清除站点数据会丢失演示任务。

## 路由与结构

- `/`：首页。
- `/app/new-scan?mode=mock|api`：新建扫描。
- `/app/scans/:scanId/overview|progress|risks|resources|graph|report`：任务页面。
- `/app/scans/:scanId/risks/:riskId`：具体风险。
- mode、筛选条件写入 URL；任务编号不变，刷新只查询任务，不重复提交。
- 旧的无任务工作台地址进入新建页，不自动加载某个历史演示。

`src/pages` 为页面；`src/components` 为共享 UI/证据阅读器/动效；
`src/services` 负责契约校验、API、演示存储和纯数据变换；
`src/types` 是前端消费模型；`src/hooks` 管理路由和任务读取；
`src/mocks` 为独立合成快照。
图谱使用 React Flow，按页懒加载，不增加首页首屏的图谱 JS。

## 环境变量与真实接口

复制 .env.example 为 .env.local（不提交真实密钥）：

- VITE_DATA_MODE：mock 或 api，默认为 mock。页面显式切换通过 URL 覆盖默认值。
- VITE_API_BASE_URL：后端服务地址，默认 http://localhost:8000。
- VITE_MAX_ZIP_MB：与后端约定的正数上限；未配置时禁用真实 ZIP 提交，不自行假设 200 MB。
- 所有 VITE\_ 变量都会进入浏览器代码，不能放 Token、API Key 或服务端秘密。

真实模式已具备调用与错误处理入口，但本轮没有实现/验证真实扫描后端。
前端拟定的接口、数据类型和待确认事项见 [API_CONTRACT.md](API_CONTRACT.md)。
API 报错、数据结构不符、404 均明确显示，不自动回退 mock；用户可以主动选择演示。

## 验证

`pnpm test`：16 项 Node 测试，覆盖统计/过滤/导出、输入校验、数据契约、演示状态与 API 错误。
`pnpm build`：TypeScript 检查与生产打包。

浏览器回归脚本依赖 Playwright 与本机 Chrome，可在测试环境提供 Playwright：
`pnpm add -D playwright`（团队决定是否纳入统一测试工具链）。
启动 5174 后运行 `pnpm test:browser`。已有共享运行时时可通过 OPENGUARD_PLAYWRIGHT 指定模块绝对路径，无需修改 package.json。

可选测试环境变量：
OPENGUARD_TEST_URL（默认 http://127.0.0.1:5174）、OPENGUARD_BROWSER（默认 chrome）、
OPENGUARD_QA_OUTPUT（截图目录，默认系统临时目录）。

测试创建隔离浏览器上下文，不操作用户已登录浏览器。
12 组浏览器用例包括多尺寸布局、刷新、筛选返回、抽屉键盘、CSV/JSON下载、模拟 API 响应和失败场景。
模拟接口测试不等于后端联调通过；屏幕阅读器、真机触控、现场投影和大规模数据仍需团队验收。

## 边界

- 人工“已处理”与“复扫通过”是独立字段，前端不自动改变验证结论。
- 未知许可、缺失证据保持待确认；不展示虚构准备度、整改加分或 AI 置信度。
- 统计与报告来自同一完整快照；服务端分页必须先做 adapter/全量汇总，不能把一页当总量。
- 任务取消、真实复扫、覆盖率、历史扫描差异、认证授权由后端约定后再接入。
- 不包含法律判断引擎，不构成法律意见。

本轮变更清单见 [OPTIMIZATION_SUMMARY.md](OPTIMIZATION_SUMMARY.md)；
视觉来源与新增依赖见 [THIRD_PARTY_UI.md](THIRD_PARTY_UI.md)。
运行时第三方许可文本随 public/THIRD_PARTY_NOTICES.txt 一起发布。
