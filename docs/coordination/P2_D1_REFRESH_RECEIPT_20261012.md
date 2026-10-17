# P2 D1 当前前端源码身份补充回执

日期：2026-10-12（Asia/Shanghai）。状态：**静态源码身份已重新固定；Owner 复核与交接包整包签收未完成**。

本文件是此前 `tmp/p2-d1-freeze-20261011/D1_FREEZE_RECEIPT.md` 及 `D1_EVIDENCE_AMENDMENT.md` 的补充，不改写旧回执。旧 75 文件快照的逐文件清单曾被辅助脚本覆盖，不能从新清单倒推旧状态。这里固定的是 **当前** 前端源码，而非追认旧快照或声明已在锁定接收机运行。

## 1. 来源与核对

| 项目 | 本次结果 |
|---|---|
| 统一 TEST_ONLY 外层 ZIP SHA256 | `743600b7748d07df7dcb587617cfc3825547d58e53cad33eb95c348905275854`，本机重新计算匹配 |
| 候选身份 | 包内 `CANDIDATE_IDENTITY.json` 与 `TRANSFER_MANIFEST.json` 均为 `ec4c680bf7bb0d7d0af583e5376336421361fc8d`；不是远端集成提交身份 |
| 包内完整性 | 44/44 条目实际字节数及 SHA256 匹配；`SOURCE.zip` SHA256 为 `46e0ba649df89a1a7b444bfa8dee4e37c52a580dd2785f2f54281c603e3557f4` |
| 当前前端 Git 基点 | `codex/p2-readiness@9ad9998d6f3df82618966c5865d13006a1efe6bc`，此前已仅推送功能分支；本次未提交、推送或合并 |
| 当前前端工作树 | 78 个 Git 可见文件，完整相对路径、原始字节长度与 SHA256 见 `P2_D1_CURRENT_FRONTEND_HASHES_20261012.json`；聚合 SHA256 `847888b1b9b7081cfb371a42dcaa1fb4eb43ce42e45ca1dbd09bdfaabfcaaeac` |
| 本轮未提交前端叠加 | `P2AdvicePanel.tsx`、`P2Workbench.tsx`、`workspace.css`、`p2-advice.test.mjs` 四文件；上述 78 文件聚合 Hash 包含这些工作树字节，不能以 HEAD SHA 代替完整当前源码身份 |

聚合算法在 JSON 中给出：按相对路径的 Ordinal 顺序，对每个文件原始字节算小写 SHA256，连接 `sha256 + 两个空格 + path + LF` 后以 UTF-8 计算 SHA256。JSON 文件本身 SHA256 为 `9bd79be3dfbcd5e376b6d16b5ed600ceea3e4f2c005656a5685c794d55022abe`。尚无代表这四个未提交文件的正式兼容 commit SHA。

## 2. D1 合同与当前静态兼容边界

原 D1 回执已逐项记录 9 条 L1/L2 路由、请求/响应 DTO、状态/错误、Scan/Assessment/version/Result/同版 Summary 绑定及 Formal 分界；本轮没有修改该候选合同。当前前端的 Result 校验与旧 D1 中三个已记录最终 Result 的静态匹配是**既有证据**，本轮未重新执行那三个验证。此次重新运行 `audit-current-frontend.mjs`，记录 HTTP 的 Summary/Answer/Material 各 3/3 静态校验通过；等级明确为 `STATIC_RECORDED_HTTP_NOT_RECEIVER`。阶段 2 的资源级 L1 页面另有 136/136 前端测试及 TEST_ONLY 浏览器回放，均不代替真实 API。

前端拟修改文件与接口依赖已在原 D1 回执登记；其中 L1 读取、Result 历史、同版 Summary 与 L2 前端接线现已在功能分支或本地增量实现。仍须在锁定后端环境验证实际请求/响应、刷新、错误边界和写入；不能因静态相容而声明运行兼容。Formal Assessment 不受 P2 建议覆盖。

## 3. 接收机与其他独立门禁

本次尝试启动现有 Docker Desktop 后，`docker info` 仍报 `npipe:////./pipe/dockerDesktopLinuxEngine` 不存在，进程退出；本次无法 inspect 指定镜像。此前一次 Docker Engine 可用时，`sha256:6510aeaf29bdcfb1b3bdb3655fef73d39f9bc6164ae876011a57c356c5cef23c` 的 inspect 返回 `No such image`。本机已知的交接目录未发现同 ID tar；外层统一 ZIP 不含镜像。本次**未**恢复数据根、启动后端、执行 27 GET、做重启或浏览器 live API 验收。运行条件恢复后由 xzb/Codex 执行 B2，不应再要求后端重复发送已有合同和 TEST_ONLY 回执。

旧 v6 Formal 原件由有权转交者提供，人工适用性由 Owner 指定审核人签认；NOTICE 测试夹具修补和最终候选/门禁复核由维护者及 Owner 审阅。生产 NOTICE 不属于此 D1 回执。此处不新增阶段 1 条件，仅按既有 B1—B5 清单保留独立责任。

## 4. 安全与结论

本次只新增当前版本的 Hash 清单及此补充回执，追加共享日志和进度；未覆盖旧 D1 回执、原 ZIP、SOURCE、已有数据库、前端产品或后端业务。`git diff --check` 通过。没有 commit、push、merge、PR、部署、重新 init/apply 或模型调用。

**结论**：当前源码身份可复核，A1 静态证据的覆盖问题已补救到新工作树；原旧快照不追认。D1 最终冻结仍待 Owner 复核；更严格的阶段 1 整包仍为 PARTIAL，B1/B2/B3/B4/B5 状态不能被当前静态核对自动关闭。
