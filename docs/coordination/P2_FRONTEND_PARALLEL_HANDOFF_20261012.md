# P2 前端并行实施与末次联调清单（2026-10-12）

用户决定：距离完整作品交付约三天，已冻结合同能支持的前端工作先做；阶段 1 运行、原件和人工签收缺口留到最后统一联调。此决定不等于阶段 1 或 P2 整体验收通过，也不授权提交、推送、合并、部署、修改后端或把 TEST_ONLY 数据称为生产事实。

## 身份与证据等级

- 当前工作线：`codex/p2-readiness`；工作树基点 `68e1f2ca2319d3426291c0bd2b823b577f7f7f1b`。新增前端**未提交**，不存在本轮 frontend commit SHA。源文件逐项 Hash 见本机 `tmp/p2-d1-freeze-20261011/frontend-source-hashes.json`；2026-10-12 本轮最终检查时，78 个前端文件聚合 SHA256 为 `483d7021023921e0982183a6a9fe3315d2ea982b9bb57af507c2b5daf7c81a9e`。开发继续变更时必须重新计算，不能当永久锁定版本。
- 依据：Owner 交接的统一 TEST_ONLY 候选 `ec4c680bf7bb0d7d0af583e5376336421361fc8d`、包内冻结 Schema、记录 HTTP 响应及后端 B《OpenGuard-P2-前端交付需求-20261011》。B 文档引用的较新 `da142ea` 未作为本轮锁定运行后端或新增字段依据。
- 已交付 HTTP 回执的 Result 9 种变体、Summary 3 项、Answer 3 项、Material 3 项可被当前校验器**静态**接受；这不是目标机真实 API 签收。浏览器 TEST_ONLY 回放使用记录 GET 与明确构造的 P1 列表/旧 Summary 适配，仅能验证前端交互，不是新真实扫描或正式评估。
- 原 D1 前端逐文件证据曾被辅助脚本覆盖，已在 `tmp/p2-d1-freeze-20261011/D1_EVIDENCE_AMENDMENT.md` 说明；不能把旧 75 文件聚合 Hash 与新 78 文件清单混为同一个冻结快照。

## F01—F09 执行矩阵

| 项 | 本轮前端结果 | 尚需最后联调/外部输入 |
|---|---|---|
| F01 合同及身份 | 固定 Scan、Assessment、Assessment version、Result ID/revision 与同版 Summary；Result URL 参数可刷新恢复。已列出前端改动及工作树 Hash，不虚报 commit。 | Owner 复核候选兼容与最终冻结 SHA；真实接收机复验。 |
| F02 L1 状态 | 继续复用 P1 Assessment 页，展示后端 Result 资源状态、用途候选、Evidence/gap、`candidate_only`、`pending`/`unknown`/`partial`，与 Formal 分区；不从名字/来源猜许可证。 | 用获准目标数据逐项看页面、录请求和截图；人工适用性不是前端可代签。 |
| F03 L2 问题 | 只允许选择服务端返回的问题、选项及显式资源子集；未选择不默认全选，`FULFILLED` 文案明确是未核验用户声明。 | 独立可重置数据集完成实际成功 POST/读回；不能写入固定只读接收样本。 |
| F04 版本与并发 | 独立 Result 历史、固定旧版只读、同版 Summary、expected_revision/parent_result_id 与原 idempotency key；409 不自动合并。 | 两会话真 409、重读、重启及固定 URL 浏览器签收。 |
| F05 错误及不确定保存 | 403/404/409/413/422/503 有分级反馈；网络或 503 后保留请求体与键，仅允许显式 GET 核对后人工原样重放。无自动 POST，刷新前警告。 | 目标服务上复验实际错误响应。刷新/关闭标签会丢失内存中的未决请求，应提醒操作者保留原回执，不可声称跨重启恢复草稿。 |
| F06 小文本材料 | 显式资源/版本/Evidence 绑定；LICENSE/LICENCE/NOTICE 文本文件白名单、UTF-8、原始字节 SHA256、base64、来源、完整性声明及大小门槛；保存读回仍标为用户提供、待核验。 | 用获准材料在可重置环境测 201/错误/读回；后端/人工决定适用性与真实 NOTICE，不因材料上传而提升验证状态。 |
| F07 目标机固定接收 | 前端代码和静态回执可继续；此项**未签收**。 | 匹配镜像 `sha256:6510aeaf29bdcfb1b3bdb3655fef73d39f9bc6164ae876011a57c356c5cef23c` 的来源/独立 Hash 或获批新锁定组合；新私有根恢复同 ID，27 个精确 GET/Hash/重启/无副作用。不得用旧 P1 镜像冒充。 |
| F08 浏览器矩阵 | TEST_ONLY 回放下：390px 无横向溢出、reduced-motion、固定旧 Result URL 刷新、38 GET/0 写操作，未出现页面异常。**不是**真实接收机通过。 | 真 API 的 L1/L2、成功写入、错误、历史/键盘/窄屏/打印和截图，区分测试数据与正式历史。 |
| F09 Formal/companion/交接 | 页面将 P2 Summary 标为“非正式报告”，引用父 Assessment 的正式报告链接；未将 P2 建议写回 Formal。末次联调问题按本表登记。 | 旧 v6 Formal 原 JSON/HTML 及 Hash、获准来源；Owner/人工许可审阅；生产 NOTICE 能力独立签收。缺原件时不能用 Summary 或新报告代替。 |

## 本轮本地改动与验证

产品：`frontend/src/{App.tsx,pages/Assessment.tsx,services/assessments.ts,services/p2Advice.ts,services/p2Workflow.ts,types/p2Advice.ts,components/P2AdvicePanel.tsx,components/P2Workbench.tsx,styles/workspace.css}`。测试：`frontend/tests/{p2-advice.test.mjs,p2-workflow.test.mjs,runtime.mjs}`、`frontend/package.json`。前述部分文件是开工前已有未提交成果，本轮保留并增量接线；其他已有 NOTICE 测试修补和协调文档没有被覆盖。

- 前端完整测试 **133/133 PASS**；TypeScript 检查 PASS；Vite 生产构建 PASS；`git diff --check` PASS。未新增依赖或修改公共 Schema/后端。
- 静态兼容：交接包记录响应 Result 9、Summary 3、Answer 3、Material 3 项分别由当前校验器接受。它们的证据等级是 `STATIC_RECORDED_HTTP_NOT_RECEIVER`。
- TEST_ONLY 浏览器回放：390px 页面/文档宽度均 390px，独立 Result revision 3 与旧 revision 1 固定 URL 可选、刷新仍为 revision 1；38 GET、0 POST、0 pageerror、reduced-motion。结果是 UI 测试而非正式验收。
- 本机前端预览 `http://127.0.0.1:4182/` 返回 HTTP 200；当前 P2 后端并未接入该预览，不能用此地址签收真实 L2 保存。
- 本机 `127.0.0.1:8082` 当前连接被拒，未得到本轮真实 P2 服务回执；不得将上述静态/回放测试写成目标机真实 API PASS。既有 `8081/15174/15175` 演示环境不改。

## 末次联调必须带回的原件/签收

1. Owner/后端 A：锁定源码、精确镜像与来源 Hash；可恢复 TEST_ONLY 私有根、完整 ID/manifest；获准旧 v6 Formal 原件/Hash；如合同更新，给出新候选与差异，不口头替换。
2. cz/材料维护者：准确来源、完整文件 Hash 和原材料；未取得 NOTICE 保持缺口。授权审核人分别审阅三例许可适用性，允许审为 pending，但不得写成 verified。
3. xzb/前端与 Owner：在目标机运行 F07/F08 真 API 和浏览器矩阵，记录全 URL、响应、截图、重启结果及失败项；Owner 决定阶段 1/P2 整体状态。生产 NOTICE、真实扫描规模、正式项目合规需另行验收。

截至本回执：可继续前端开发/演示 TEST_ONLY 交互；**阶段 1 整包 PARTIAL，P2 正式跨栈验收未完成，完整作品不得宣称已交付**。未提交、未推送、未合并、未部署。

## 2026-10-12 09:45 发布状态补记

上段记录的是 09:10 前的工作树状态。用户随后明确授权上传；P2 前端实现、测试和本交接文档已提交为 `7dd84b5e7c0b610bcaaf7ec074de0a6e03fdd244`，并只推送到团队仓库的 `codex/p2-readiness` 功能分支。远端逐项核对 SHA 相同；`origin/integration/p1=aabd7940f65ec8a78b33c863b4db81b400509b7d` 仍为祖先，未改动集成分支、main、后端或部署。阶段 1 整包与 P2 正式验收状态不因代码推送而改变。旧工作树 Hash 是提交前源身份，不代替上述 Git 提交身份。
