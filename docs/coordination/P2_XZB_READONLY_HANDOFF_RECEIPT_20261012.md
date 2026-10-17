# P2 xzb 只读交接材料接收核对（2026-10-12）

结论：**只读资料已收；运行交付与目标机验收未完成**。本回执只记录接收机本地读取得到的事实，不追认发送方历史运行结果为 xzb 本机结果，也不构成新的前后端兼容签收。

## 实际收件与完整性

| 对象 | 本机核对结果 |
|---|---|
| `OpenGuard_P2_XZB_只读交接材料_20261012.zip` | 64,232 bytes；本机 SHA256 `79cdb6025688e50cfd093fd2264837fc34340dd9471066339e9ef98b646c0b87`。用户消息未给独立预期 Hash，故仅证明本机所收文件身份，不证明与发送方原件同字节。 |
| 包内结构 | 4 个文件：只读审查报告、manifest、D1—D4 证据矩阵、Owner 给 xzb 的消息；无镜像、源码、数据根或接口响应原件。路径无逃逸项。 |
| 包内 manifest | `P2_XZB_HANDOFF_MANIFEST.json` SHA256 `73ac5b976810c11c4969b22942b17b6f2040fbb3fb19ed4ce0d6b75887c7b108`。manifest 登记的另 3 个文件的字节数及 SHA256 在本包中均匹配。 |
| 已另行收到的统一候选包 | `OpenGuard_P2_STAGE1_UNIFIED_TEST_ONLY_20261011.zip` 本机 SHA256 `743600b7748d07df7dcb587617cfc3825547d58e53cad33eb95c348905275854`，与此次只读说明所引用值一致；此前 44/44 包内条目核对已记录。这不是此次只读 ZIP 新增的运行数据。 |

## 对本机前端身份的更正

发送方交接说明的 `D1_RECEIPT_NOT_AVAILABLE_FOR_REVIEW` 仅描述其限定搜索范围，**不能推论 xzb 尚未实现 D1**。本机已有 `P2_D1_REFRESH_RECEIPT_20261012.md` 和对应 78 文件 Hash 清单，先前提交基点为 `codex/p2-readiness@9ad9998d6f3df82618966c5865d13006a1efe6bc`。但是该清单固定的聚合 Hash `847888b1b9b7081cfb371a42dcaa1fb4eb43ce42e45ca1dbd09bdfaabfcaaeac` 属于 13:08 的旧工作树；随后 P2 引用读回竞态窄修使以下两文件改变：

| 文件 | 当前原始字节 SHA256 |
|---|---|
| `frontend/src/components/P2Workbench.tsx` | `4b96769fddf5e091ee50c9e51ab04537403f99418f01a96f3c3153262fcdbfb4` |
| `frontend/tests/p2-workflow.test.mjs` | `761f5e71996a3ff1b9bba3d3566bddf7a244287682335727d11352d36dcc59dc` |

按旧清单相同 78 文件、相同排序与聚合算法重新只读计算，**当前**聚合 SHA256 为 `a6a9659df76e7abd67ba1f208eb86f49743a4e57899fbdb4f93d301d4498746e`；其余 76 文件与旧清单 Hash 相同。当前源码仍是已提交基点加未提交叠加，不能用基点 SHA 冒称当前完整兼容 SHA。发送方可凭本回执和已存在的 D1 回执做只读复核；正式同组合兼容仍需目标机验证。

## 尚未由此次交付解除的门禁

- **B1/B2 运行与接收机**：交接包没有 `sha256:6510aeaf29bdcfb1b3bdb3655fef73d39f9bc6164ae876011a57c356c5cef23c` 的镜像导出文件或独立 Hash。此次本机只读 `docker image inspect` 报 Docker daemon pipe 不存在，故未证实镜像在接收机可用；未恢复私有数据根、启动服务、运行 27 GET、重启或真实浏览器。
- **D1**：当前前端的本地静态回执存在，Owner／后端仍未取得并审核；旧 Hash 不可代替当前工作树。未形成前后端同组合运行签收。
- **B3/B4/B5**：旧 v6 Formal 原件、指定审核人的许可适用性签认、两条 NOTICE fixture 问题的候选复核与最终 Owner 审查，仍按原固定清单分别跟踪。三例 TEST_ONLY `partial/pending` 及同版 P2 companion 不能替代这些证据。
- **额外技术项**：此次说明列出的 B03 新 pin 待 A 接纳和终态读回、A04 coverage 传播阻塞、M1 新来源事实与真实用途/适用性未签认，均未因收到这份只读索引而关闭；独立录制的 chalk 初评不在统一候选中。

本次未运行新产品测试、未写业务数据，也未修改后端/Schema/正式 Assessment；前端最近一次 137/137 测试和构建属于上一轮回执，不计作本轮。未提交、推送、合并或部署。下一步由镜像持有人/Owner 提供固定镜像导出与独立 Hash，并接收本机 D1 当前 Hash；运行条件具备后由 xzb/Codex 在全新私有根进行实际 API、重启和浏览器验收，不重复索取已收的统一 TEST_ONLY 包。
