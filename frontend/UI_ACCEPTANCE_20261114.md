# Gemini UI 修复复验 — 2026-11-14

结论：按用户确认的门槛通过，可更新 PR #4；不代表全部扩展测试通过或整个系统已经完成生产验收。

## 三项问题关闭

| 问题 | 修复与验证 |
| --- | --- |
| UI-01 未经验证的装饰性 VERIFIED | 未扫描侧栏改为中性版本记录说明；登录插画明确标注示例数据、示例摘要、流程示意，步骤编号不冒充核验结果。源码、浏览器文本与截图复核通过。 |
| UI-02 归档文案承诺签名 | 改为“保存固定版本与内容摘要”，与当前保存及完整性校验能力一致；浏览器 SVG 实际样式解码复核通过。 |
| UI-03 窄屏微小文字与残留占位 | 390px 下隐藏相关装饰伪元素，实际 computed style 为 display:none、height:0，归档辅助正文不少于 12px；关键按钮可用。 |

## 本轮验证

- 冻结候选的 269 个源码、测试及配置文件与交付目录 SHA-256 一致；发布的 7 个产品文件与已测候选逐一一致。
- 默认 package.json test 脚本：187/187 通过。
- `tsc --noEmit`：通过。
- `vite build` 默认及启用账户/P2/进度事件配置：通过；大 chunk 警告仍存在。
- `node --test tests/*.test.mjs`：1117 项，1102 通过、15 失败；与修复前 Gemini 候选的失败名称集合相同，没有新增失败。历史 UI v3 基线为 16 项失败；保留历史报告，不改写旧结果。
- 真实本地后端 + Chrome：10 组检查、23 个页面状态，1440×900 与 390×844；无页面脚本错误、无检查到的 API HTTP 错误、无页面横向溢出。
- 实际完成注册、固定 http-server 快照扫描、概览、资源分页与无结果筛选、P2 r1、绑定真实 LICENSE 原文生成 r2、归档创建/预览/JSON 下载、聊天欢迎页与窄屏历史抽屉。
- 数据位于独立 TEST_ONLY 目录；后端代码未修改。外部仓库抓取和真实模型推理未运行，固定扫描使用交付版样例快照。
- 浏览器检查脚本最初因 SVG innerText 用法失败，修正测试脚本为 textContent 后通过；视口切换后立即截图出现重复残影，等待绘制稳定后使用原生视口截图复核。两者均未修改产品代码。

## 发布范围

本次同步 Gemini 集成以来的 7 个产品文件：

- `src/styles/workspace-v3.css`
- `src/components/AssistantMarkdown.tsx`
- `src/components/Auth.css`
- `src/components/AuthIllustration.tsx`
- `src/components/ui.tsx`
- `src/pages/AuthPage.tsx`
- `src/pages/ReportV2.tsx`

相较上轮 Gemini 验收，最终修复仅改变 workspace-v3.css 和 AuthIllustration.tsx。32 个 services、API 契约、依赖和锁文件未变。保留此前公开副本的 8 个 runner 路径参数化处理；不将本机路径重新带回仓库。

## 已知限制

- 下列 15 项扩展失败按已确认范围披露，不能将本次结果表述为全套测试通过；修复这些测试/行为需后续单独处理。
- 本轮未复跑所有历史浏览器专项；上轮已完成的聊天/表格/引用检查属于先前证据，非本轮新增运行结果。
- 未验收真实 Qwen 推理、干净机器安装、跨平台运行或完整无障碍符合性；独立人工审查仍待 PR 审查者进行。
- 未登记再分发授权的首页视频 openguard-hero-bg.mp4 与封面 openguard-hero-poster.jpg 继续排除，公开副本不保证该首页媒体呈现。
- 仓库不含匹配的完整后端。此次本地联调通过不代表该 GitHub 仓库可直接全栈部署。
- 浏览器账号、运行数据、原始 API 记录、截图和本机日志不随公开源码上传。

### 扩展失败名称

- `continuous assessment explains scoped conditions and maintenance without turning them into vulnerabilities or Qwen output`
- `tests/official-model-preview-boundary.test.mjs`
- `primary sidebar order follows scan lifecycle and preserves all detail pages`
- `result-first view has collapsed optional supplements and no compulsory numbered steps`
- `old material-scoped result, counts and evidence stay inside a closed disclosure`
- `opening optional section reveals the retained answer form without writes`
- `optional material choice preserves the exact existing form and closes back to result without writing`
- `closing disclosure hides retained answer drafts and keeps results and immutable history readable`
- `successful explicit answer keeps CAS binding, saves once and returns to the primary result`
- `read-only still disables optional writes rather than hiding its boundary`
- `historical still disables optional writes rather than hiding its boundary`
- `409 remains visible outside disclosure and cannot auto-retry or overwrite pending request`
- `network uncertainty preserves the identical request until an explicit retry`
- `preliminary read error remains visible even when old evidence details are closed`
- `recording product configuration explicitly enables the real progress-events GET`
