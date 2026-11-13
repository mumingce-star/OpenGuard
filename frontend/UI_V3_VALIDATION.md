# Frontend UI v3 publication and validation

## 来源与提交划分

- 第一提交导入现有 portable-v2 前端：原始清单 272 个文件，逐一校验 SHA256；发布 270 个文本源码/配置/测试文件。8 个历史浏览器 runner 的个人 Playwright 路径改为 `OPENGUARD_PLAYWRIGHT` 或包名 `playwright-core`，README 增加快照边界。其余导入源码保持原字节。
- 第二提交仅包含本轮 11 个修改的产品源码文件、1 个新增 CSS 文件，以及本说明和协作记录更新。
- 交付来源是组合快照，并非可等同于任何单个历史 Git 提交。没有导入后端、数据库、运行扫描、报告产物、浏览器 profile、node_modules 或 dist。测试目录中的固定 JSON 是既有测试夹具，不代表此次真实扫描输出或正式结论。

## UI 范围

以 1440×900 桌面为主，保留 390px 窄屏可用性；统一工作台布局、侧栏、表单、扫描进度、概览、资源、评估、报告和 Assistant。保留用途三态、真实日志/警告、原报告六章语义、精确材料绑定和现有聊天恢复/停止行为。长内容允许局部滚动或折叠。没有新增知识库、归档、重新生成或解绑上下文能力。32 个 services 文件以及 Landing/AuthPage 产品源码保持不变。

## 本地验证记录（2026-11-13）

- 默认测试入口 `pnpm test` 对应 Node test 命令：187/187 通过。
- `tsc --noEmit` 与默认 Vite 生产构建通过；开启 P2/account/progress 功能的构建通过。大于 500KB 的既有 chunk 警告仍存在。
- 扩展 `node --test tests/*.test.mjs tests/assistant/service.test.mjs tests/project-chat/service.test.mjs`：1117 项，1101 通过、16 失败；原始基线复跑同样 16 项失败，本轮未新增失败。
- P2 工作台与叙事专项：53/53 通过。
- Assistant 真实 React/service + 合成封闭传输测试：10/10 通过。历史 ProjectChat 浏览器测试有 6 项失败，其期望的可编辑聊天控件与原始只读归档组件不符；该组件本轮未改。
- 26 个实际页面检查覆盖 1440px/390px，未见页面异常或横向溢出；保留登录/首页深色外观。
- 经用户授权的本地真实后端 TEST_ONLY 联调：21 个资源、52 条证据；上传 LICENSE 原始字节后 r2 重算 1 个、复用 20 个；验证固定上下文会话与报告归档/下载。后端未改。
- 多轮聊天截图使用真实固定上下文上的合成消息；没有验证真实 Qwen 多轮推理。以上本地结果不等于 GitHub CI、跨平台或陌生机安装通过。

## 已知复现限制

历史 8 个浏览器 runner 依赖未随原交付包提供的 `helpers/frontend-config.mjs`，并仍有 macOS Chrome 运行约定；`progress-recording-entry.test.mjs` 也读取此 helper。仅参数化 Playwright 私人路径并不能使这些专项直接跨平台运行。默认 187 项测试不需要该 helper。完整扩展测试当前不是全绿，不应设置为未经修复的合并通过依据。

首页引用 `public/landing/openguard-hero-bg.mp4` 与 `openguard-hero-poster.jpg`，现有资源登记未提供这两项素材的再分发授权，本次不发布。工作台构建不依赖这两个文件；公开快照首页的视频/封面不能完整显示，需维护者提供可发布素材后补齐。不会将本次源码上传描述为完整视觉资产或全栈部署包。

## 第三方与 AI

保留 package.json、pnpm-lock.yaml、THIRD_PARTY_UI.md 和构建时许可证输出。UI v3 未新增依赖；没有复制付费组件源码或上传参考设计截图。GPT-6 Codex 完成实现、差异检查与自动化验证，用户确认范围与上传方式；独立人工代码审查尚未完成，待 PR 审查。

## 上传副本复核

公开副本再次执行 package.json 默认测试命令：187/187 通过；TypeScript 检查与生产构建通过；8 个路径参数化 runner 通过语法检查。上述 runner 未作为跨平台浏览器回归重新执行。12 个 UI 产品文件与本地验收版本 SHA256 一致。
