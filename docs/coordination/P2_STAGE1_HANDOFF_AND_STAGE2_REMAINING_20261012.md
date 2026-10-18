# P2 阶段1交接与阶段2剩余项（2026-10-12）

本备忘固定**当前已核验的状态**，不新增阶段1门禁，不以记录本身代替验收。详情分别见 `P2_STAGE1_CLOSEOUT_CHECKLIST_20261011.md`、`P2_D1_REFRESH_RECEIPT_20261012.md` 及 `P2_FRONTEND_PARALLEL_HANDOFF_20261012.md`。后续若收到新物件，应核对其完整身份并追加结果，不能无痕改写本记录。

## 阶段1：不再重复索取的材料

统一 TEST_ONLY ZIP、候选接口合同、Schema、固定 ID、记录 HTTP 样例及恢复工具已收到；本机重新核对外层 SHA256、候选双清单与包内 44/44 文件。前端当前 78 文件的版本化 Hash 清单已补充；旧 D1 逐文件证据被覆盖的问题明确保留。**这些不是仍需后端重交的项目。**

## 阶段1：仍需关闭的固定责任

| 门禁 | 精确下一输入或动作 | 责任 |
|---|---|---|
| D1 最终复核 | 审阅新补充回执及当前前端源码身份；旧 75 文件快照不可追认 | Owner |
| B1 锁定运行环境 | 提供交接指定 `linux/amd64` 镜像 `sha256:6510aeaf29bdcfb1b3bdb3655fef73d39f9bc6164ae876011a57c356c5cef23c` 的可信离线交付及独立 Hash，或书面批准新锁定组合；本机 Docker Engine 也需恢复可连接 | 镜像持有人/Owner；本机环境由 xzb/Codex 排查 |
| B2 接收机与浏览器 | B1 后在全新私有根恢复相同 ID，实跑 27 个精确 GET/正文 Hash、同根重启、GET 无副作用及真实浏览器；不改原样本、不 init/apply | xzb/Codex |
| B3 旧 v6 Formal 原件 | 获准转交的原对象、原 JSON/HTML 字节及 Hash、Scan/Assessment/version 绑定；新三例报告不能代替 | 原件持有人/Owner |
| B4 人工适用性 | 指定审核人对精确发行包、用途/分发范围和证据作签认；证据不足可保持 pending，不可技术代签 verified | Owner 指定的审核人 |
| B5 最终候选 | 审阅本地 NOTICE 测试夹具窄修，在锁定候选复测并复核前端兼容、残余风险及整包状态 | NOTICE 维护者、Owner、xzb |

生产 NOTICE 不是上述 D1 技术冻结或 TEST_ONLY 接收包的通过证明，继续独立跟踪。

## 阶段2：L1 用途建议剩余项

原计划阶段2步骤12—16的**本地前端实现**已覆盖：冻结 DTO 的固定 Assessment/version 读取；loading/empty/error/retry；资源级首屏判断、对象/范围/条件/边界；Evidence/缺口与 partial 保守语义。最新本地证据为前端 136/136 测试、TypeScript/Vite build、`git diff --check` 通过；TEST_ONLY 回放 54 GET/0 POST/0 pageerror，含 390px 与旧 Result URL 恢复。记录 HTTP 的 Summary/Answer/Material 各3例是静态兼容，**不是活 API**。本地新增四个前端文件改动尚未提交/推送；已推送的功能分支 HEAD 是 `9ad9998d6f3df82618966c5865d13006a1efe6bc`，不能代表最新工作树。

阶段2要从 **PARTIAL** 变为可验收，还差以下实测与复核；不需要后端再设计一套新 L1 API：

1. 在 B1/B2 建立的锁定后端实例上，使用交接包固定的完整 Scan/Assessment/Result ID 和版本，从实际 API 打开 L1 页面；核对正向候选与证据不足/partial 边界，不让未知提升为允许或 verified。
2. 在同一实例验证 loading、empty、404/409/503、手动 retry、错绑拒显、URL 刷新/分享恢复；记录请求、响应、页面截图和控制台/网络错误。GET 不得产生 POST、扫描、Assessment 或模型调用。
3. 对真实固定数据复核主卡的资源身份、用途、条件、缺口、Evidence 跳转、窄屏和键盘；保留 Formal 与 L1 候选的视觉及文案边界。TEST_ONLY 正向/边界截图可用于功能验收，但不得称为真实生产许可结论。
4. Owner 复核上述证据与本地四文件增量；若批准发布，再单独授权提交/推送功能分支。发布行为本身不能替代运行验收。

旧 v6 Formal 原件和人工适用性审核属于阶段1整包/最终跨栈签收责任，不应每次以“后端又缺少 L1 接口”形式重新阻塞阶段2**前端开发**。但在真实后端实例不可用时，阶段2**验收**仍为 PARTIAL。阶段3 L2 写入、生产 NOTICE、最终完整作品均不是本阶段2的已通过项。
