# P2 cz 后端 B 代码说明接收核对

日期：2026-10-13。结论：**代码说明已收，属于静态交接；未证明该版本的源码已在团队仓库发布或与前端联调通过。**

## 本机收到的原件

- `OpenGuard后端B代码说明.docx`：53,927 bytes，本机 SHA256 `e13cd2004a761a09064e3e4bc02486f556017070a3e64720688e9f2132de9eb5`。Word 文档没有嵌入源码归档或测试证据附件。
- 文档自述来自 `codex/scan-reliability-integration` 的当前工作树，Git 基线 `50d8704a362f6e6615c1ed95d7f06da2bc3e871f`；收录 `backend/app/p2b` 六个 Python 文件的全文及原字节 SHA256，分别为 `__init__.py`、`candidates.py`、`materials.py`、`npm_metadata.py`、`offline_material_audit.py`、`reconcile.py`。
- 文档明确称此次仅整理现有实现，不新增业务代码、Evidence 或人工审核结论，不运行产品测试、扫描或网络操作；总体状态 `PARTIAL`。Word 的排版文字不能代替对应原始源码字节。

## 与当前本机仓库的对照

- 当前 xzb 工作分支为 `codex/p2-readiness@9ad9998d6f3df82618966c5865d13006a1efe6bc`，工作区原有未提交前端/文档改动均保留；本分支没有 `backend/app/p2b` 或 `docs/p2`，不能在本工作树核对文档列出的六个原始文件 Hash。
- 本机缓存的 `origin/codex/scan-reliability-integration` 为 `713a0845b74e81b810dacf852c3ddd9f1f7f4e11`（2026-10-10），其中只有五个 `p2b` 文件，没有文档列出的 `offline_material_audit.py`；文档的 `50d8704a...` Git 对象本机不存在。尝试 `git ls-remote` 访问团队 GitHub 时连接失败，故**不能断言当前远端仍旧或已经更新**。
- 内置 LibreOffice 不在可用 PATH，文档渲染器无法出图；已直接读取 DOCX 正文结构和全部关键章节，不把未完成的视觉版面检查标为通过。

## 对阶段门禁的实际影响

该模块提供的是保守的 **B 侧离线候选与核验工具**：对象/版本/Evidence 绑定、最多 64 KiB 的本地 LICENSE/NOTICE 文本观察、`is-number@7.0.0` npm 原始响应核对、既有 TEST_ONLY Material 审计和补证前后只读对账。其源码说明将本地材料标为 `user_supplied_unverified/pending`，把候选输出与 Formal Assessment 分开；可信传输见证依赖 A 的验证器，不由 B 自行联网签发。Word 中关于用户用途确认的叙述不是本次用户直接签认，也不能替代 Owner 确认真实交付范围或人工许可适用性审核。

因此可关闭“**已收到 B 侧代码说明及静态字段边界**”这一收件项；不能据此关闭 B03 生产接纳/终态读回、A04 coverage 传播、M1 新可信事实、阶段1锁定接收机、阶段2真实正例或生产 NOTICE。此前统一候选 TEST_ONLY 包及现有 D1 前端回执不需要重复索取。

## 最小下一输入

如需对接此文档的新代码，cz 或 Owner 应提供**可取得的精确源码提交/分支或原字节源码归档及独立 Hash**，与文档六文件 Hash 逐项匹配；同时给出该源码版本的实际测试/运行回执及是否已经由 A 接纳到统一候选。收到之前不从 Word 复制代码入产品、不改公共 DTO、不把离线 `conditional_candidate` 当作正式 L1 结果。前端继续使用 A 已冻结的 P2 API 和保守状态语义。

本轮仅读取附件及本机 Git 对象，不修改前后端产品、依赖、Schema、Formal 或数据；无提交、推送、合并或部署。
