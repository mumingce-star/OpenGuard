# P1 后端 B 离线事实交付（2026-10-11）

状态：**PARTIAL / preparation / automated_static_subset**。本轮无提交、推送、网络抓取、包安装或服务启停；无正式 Gold、正式质量指标、性能结论或真人代签。

## 版本与保护范围

| 引用 | 实际 SHA（本地只读核验，未 fetch） |
|---|---|
| 当前工作分支 `codex/scan-reliability-integration` | `bed87f58241acb4918c133c6854b99a528073b1d` |
| `origin/integration/p1` | `aabd7940f65ec8a78b33c863b4db81b400509b7d`；本机无 `integration/p1` 本地分支 |
| 本地 `main` | `074cccdbda14f9bcf9be5184c577541959e83209` |
| `origin/main` | `476d954998be6ed943532791530f5d6234f4893f` |

当前分支含 P2；本轮不消费 `tests/fixtures/p2b`、P2 Store/Result/Material 回执或 npm TEST_ONLY 扫描。核对本轮使用的既有 B detector、NOTICE collector、HF/ModelScope fixtures、v2/v3 facts、自动静态审计文件：当前 HEAD 与 P1 跟踪基线无 diff。共享日志原有追加、reports、其他 pytest 目录均保留。仅把本轮新建测试目录移入已被 `.gitignore` 排除的 `tmp/`，未清理其他成果。

开工 README、日志、进度、Sol handoff 已按序读取；巨大日志和进度首次工具输出截断，随后补读近期完整记录和相关历史。**不能声称日志逐字完整阅读门禁已满足**；Root 发布前还须补核此流程限制。本轮对产品/API/冻结 Schema/正式许可证规则无修改。

## B01–B07 状态与验收表

下表“已发布”是既有提交及本地远端跟踪记录，非本轮 GitHub 在线读回。机器对账详见 [JSON 回执](p1-b-offline-audit-20261011.json)。

| 项目 | 已发布版本 / 累计能力 | 本轮当前证据与立即完成项 | 依赖与验收条件 | 失败及风险 |
|---|---|---|---|---|
| B01 | `bc2b7afe1c7528d891a2945c31cc633069f76b47` 已含 metadata/parser 与 detector 批次；HF v1/v2、ModelScope 离线观察可复核 | 28 条 fixture（HF 20 条正例+7 条反例，ModelScope 1 条 dataset）；逐文件和 manifest SHA、HF identity/revision、ModelScope Namespace/Name 核验；身份/异常回归通过 | Luna 异机同 SHA、同字节、解释器/平台/命令/退出码签收；A 提供 Profile 消费对象与版本回执 | ModelScope fixture 为合成 `acme/demo-dataset`，不是两个真实 live 样本；HF 有重复字符合成 revision，不能当真实上游固定版本；独立回执全部“待签收” |
| B02-A / Detector 0.3 | `bc2b7af` 静态候选与明确 AST/配置/URL；规则版本保持 0.3 | 原固定 ZIP 的 314 项 train/dev 分歧逐文件 SHA 与行号核验，44 机器 FN/270 机器 FP；已确认错误 0、无法判断 0、待真人裁决 314 | 真人复核完整上下文/任务范围；确认有正反例后才修改规则；同输入同配置保留前后 artifact/Hash 消融；新 holdout 独立封存 | 字节可读不等于语义已判断；不删除重复 Evidence、不用旧 holdout 调参；本轮未改规则、无消融收益主张 |
| B02-B | `f3e51f5` 固定 v2 联验、后续 `0d21f0382b84737a115367ee182ab216967b1163` 已含接纳候选 | 8 facts / 10 Evidence → 17 Finding 候选 / 0 Obligation；逐 fact/package SHA、Pointer、原 Evidence ID、候选 ID 与关系对账；2 条零候选保持 | A 给真实终态 ScanRun/Assessment/facts hash 和资源/Evidence 映射；不得以合成准入测试代真实生产回执 | 全部 pending/review_required；不得把 gap 当违规或候选当正式 Assessment |
| B03 | v3 facts 与 adapter 已进入 P1；facts 最近提交 `0d21f03` | v2/v3 共 39 个 fact 行，Git source 5 项复算，4 项匹配、1 项不匹配；原事实不改写 | B/Root 新不可变 facts revision，Luna 独立校验；A input→inventory→facts→Formal 全链 | `frontend/package.json` 的 declared commit/hash 错绑，影响 8 条 npm Evidence；当前 v3 Git 身份链不能验收 |
| B04 | NOTICE collector/selector、独立关系与 partial 离线能力；P1 基线 `aabd794` | 零候选、截断、预算、无效 UTF-8、超大文件、重复与篡改离线正反例；机器表保留 A/Draft/Report 空格 | A STAGED→BOUND、真实终态、partial 原因、重启读回与 Draft/Report 引用；前端同版本签收 | A 两个边界 suite 本轮 122 setup errors（Windows `os.geteuid`），不算业务失败/通过；没有 A 正式签收 |
| B05 | `2d822af0ae67fc3bde7f1e45fea8e3ec781f52e5` 静态来源与审计工具 | 只读 audit verified：30 来源、25 fixed/completed、5 failed、18 重复键组；保存队列与内存重建逐字段一致 | Luna 独立复算；真人 Gold、新 holdout 与 Sol 等级批准；正式预测须绑定冻结版本 | 失败保留分母；9 个旧 holdout 已暴露，仅开发用途；本轮不输出 Precision/Recall/F1 |
| B06 | 既有 reference-only/taxonomy/盲审/amendment 工具；均 preparation | 314 分歧仍待签；14 组 train/dev 重复匹配键各保留不同 Evidence；准备源入口盲审清单、未填真人模板和操作要求 | 两名独立真人、第三位真人裁决；Luna 维护封存/独立回执；Sol 批准等级，Codex 不代签 | 来源可访问不证明再分发权；错误队列选择有偏，不能单独用于总体 Recall 或 Gold 冻结 |
| B07 | v2 controlled receipt validator/汇总器已在 P1 | 成功/失败保留、缺环境、缺阶段、重复 receipt 拒绝正反例通过；正式性能字段 null | A 提供同 SHA 受控 Linux 原始 receipt ≥2，冷/热、失败不删；采集计划与人工复核 | 测试手写值不是测量；Windows 与历史单次扫描耗时不能替代 Linux 原始数据 |

## 已确认的 B03 来源错绑

v3 声明 `frontend/package.json` 来自 `9d67b88f39fa4aaa8ab24048aea224204eabd490`：

- 包内 source SHA：`16e9db4fb169ef63a982912b983e8259332e580554a451e4053c3f43e73b05fc`。
- `git show <固定commit>:frontend/package.json` 原字节实算：`a8e9bab912ffc5ef1afc2da36db5b0de932ce872e235e02b55dce9ceca65f09a`。
- 当前工作树文件恰与包内 SHA 一致，不能据此替代固定 Git 原字节；将 LF 简单转 CRLF 也不匹配。生成器读当前工作树却硬编码旧 sourceRevision，是可直接验证的绑定缺陷。
- 8 条受影响 Evidence 在 JSON `fact_chain.source_binding_affected_evidence` 列出，相关 8 行标 `source_binding_state=mismatch`。既有 Node `generate --check` 通过只能证明工作树重生成一致，不能证明 declared commit 一致。

修正请求：B/Root 另建不可变事实 revision/amendment，生成器读取真实固定 commit blob；若输入来自工作树，应明确工作树快照身份及外部固定摘要，不谎称历史 commit。必须保留旧包、old/new package SHA、来源证明及依赖该包的失效/重算记录，Luna/Sol 复核后再交 A。**本轮保留冻结 v3，不现场刷新哈希或改旧 Schema。**

## 离线逐项对账范围

JSON `sources.cases` 每项固定 sample/commit/ZIP SHA→相对文件/字节数/文件 SHA→机器候选类型及原 prediction Evidence ID→Gold/prediction/run SHA；不保存原文。FN 没有匹配预测时 Evidence ID 列表为空。这里 inventory 是 `bounded_static_source_not_A_inventory`，不能冒充 A inventory。

JSON `fact_chain.rows` 每项固定 v2/v3 fact→关系/gap→原 Evidence ID、locator、文件/字段/container SHA→候选 ID；`inventory`、`a_terminal`、`draft_report` 为 null。v3 的 31 项选定字段 Hash 已从实际源值复算通过（POM 属性仅取同文件显式值，不运行 Maven）；23 项 source 文件 Hash匹配，8 项 npm source Hash错绑。对缺件只写“需要 A 提供”，不制造 Scan ID、Formal、Report 或完成状态。

| 必须覆盖的负例 | 现有离线验收入口 | 本轮结果 / 仍缺证据 |
|---|---|---|
| 零候选 / selector 超限截断 | `test_notice_source_selector.py` | 定向组合通过；真实扫描/Draft 空状态需要 A/前端 |
| 读取预算 / 无效 UTF-8 / 超大文件 / prior read failure | `test_notice_source_collector.py` | 离线组合通过；partial omissions 不补造内容 |
| 相同内容多 Evidence / 包字段篡改 | collector / `test_notice_source_contract_independent.py` / v3 adapter | 离线组合通过，不自动删除 Evidence |
| 错扫描、revision、Assessment、绑定 Hash；重放/重启/只读 | `test_p1_notice_source_binding.py`、`test_p1_notice_source_adapter.py` | 本轮 122 setup errors，Windows POSIX 能力阻断，业务断言未执行；需要 A 受控环境完整回执 |
| 原文件 SHA/行号错绑、holdout 个案拒绝、JSON 重复键与非有限数 | 新 `test_p1_b_offline_audit.py` | 最终 14 passed；不改真人状态，盲审源入口不泄露机器答案 |
| 5 个采集失败 | 保存 freeze/catalog/run | 4 超归档字节上限、1 ref 非单一 commit；dev 2 / holdout 3，均留分母；没有重新抓取 |

## 向 A 的精确交接请求

此清单已登记共享协调文档；当前会话没有可用的 A/前端跨聊天发送工具，**尚未实际送达或取得协作者回填**，由 Root 转交。

1. 每包给完整仓库 SHA、API/Schema/registry/tool/rule revision、干净或带改动状态、受控平台及可复现命令；当前 P1 `aabd794` 与工作分支 `bed87f5` 分开，禁用 P2 回执替代。
2. 固定 Git：来源 URL、不可变 commit、获取策略、实际物化 inventory；固定 ZIP：原字节 SHA/大小及安全获取证明。不上传 ZIP/数据库/第三方正文。Git URL digest、archive bytes SHA、inventory digest 三者分别提供。
3. 同一 `scan_id` 的 queued/终态对象、registry revision、input/inventory/facts/package canonical Hash、status/stage/error/partial omissions/gaps；逐源文件与资源/Evidence 映射，Evidence 粒度、locator/Pointer、source/container/selected SHA。
4. Formal Assessment ID/version/facts Hash、规则版本和不可变对象 Hash；LICENSE/NOTICE/provider 声明独立。不得对本次 v3 8 条错绑 Evidence 自动接纳。
5. NOTICE STAGED package ID/hash 与接纳回执、BOUND binding/hash/CAS 版本、只读 reader；零候选/截断/读取预算/坏 UTF-8/超大/重复/错绑/篡改/partial 的成功或拒绝原因及零写入证明。
6. NoticeDraft ID/version/引用 Evidence 与 binding/package Hash；Report V2 同版 ID、链接、实际下载字节 Hash与引用。pending 保持 pending。
7. 受控重启前后精确 GET 对象/字节 Hash、数据库只读证明、旧版本仍可读；失败/重放/错绑定不覆盖旧对象。单元 TEST_ONLY 测试不代正式输入。
8. B01 Profile 同资源/来源 revision、transport/parser 版本、响应 SHA/size/UTC/最终 URL、异常/缺口及终态消费映射；Luna 异机签收独立于本机历史 live 观察。
9. B07 采集方案和原始 `controlled_linux` receipt ≥2：receipt/run ID、source commit/source SHA、input/config/result SHA、cold/warm、Linux kernel/image digest、CPU/逻辑核、内存 limit/peak、ScanCode/Syft/Detector/规则版本、五阶段有序耗时/status/failure_reason、total 与失败分类；保留失败、说明时钟与采样方法。不得交手写汇总代原始测量。

## 向前端的精确交接请求

1. 同 A commit/API 版本、同一 `scan_id`、Assessment/Draft/Report immutable version；给前端 SHA、浏览器/平台、固定输入 Hash、操作和脱敏网络回执。
2. pending、unknown、review_required、partial+omissions/gaps 和失败分别显示；provider 声明不显示“已授权”，零候选不显示“已合规”。
3. Profile 与 NoticeDraft 展示准确引用 Evidence、source/binding/package Hash与版本；本次 v3 source mismatch 提供明确错误/待核验状态。
4. Report V2 下载：同版请求/状态/headers、下载字节 SHA、格式/引用闭包；刷新后不换版本、不重复上传。
5. 刷新/受控后端重启前后对象 Hash一致、旧版可读；404/409/422、超时、partial 与不可用状态保留，不虚构成功。
6. 提供截图或录屏及脱敏浏览器回执，由接收机操作者签收；B 的单元测试、JSON 或合成 UI 不能代替浏览器签收。前端启停服务须另获用户明确指令。

## 真人盲审与等级批准

新模板 `p1-b-human-review-template-20261011.json` 所有签名/裁决为 null，不能直接进入正式校验器。[源入口 packet](p1-b-blind-source-packet-20261011.json) 共 224 个独立文件入口，只提供 source commit/ZIP SHA/相对文件/文件 SHA，不含机器 FP/FN、预测名称、AI 答案、其他 reviewer 判断或 split；不复制正文。内部完整对账 JSON 是有答案的协调资料，**不能交盲审员**。Luna 应仅将源入口 packet、空模板及合法取得的固定源入口交给评审，隔离本仓库其他有答案文件。可通过审计 CLI 的 `--blind-output <新路径>` 复算。

这是 train/dev 分歧处置准备，存在候选选择偏差，不是整体 Gold。正式 Gold 应由 Luna 在权利审核后提供完整任务源材料及独立新封存 holdout，两位真人独立标注，第三位真人裁决；真人填写独立性/exposure、scope、证据与提交 Hash。Sol 只能按真人证据复核等级，Codex 不签真人声明、许可证适用性或批准。

## 命令、平台与结果

本机 Windows / CPython 3.12.10 / Node 26.2.0，使用既有 `.venv`；沙箱内不能启动该解释器，获准本地执行后通过。未安装任何依赖。

```powershell
$env:PYTHONPATH='backend'; $env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m benchmarks.auto_static_bench audit benchmarks/results/local/auto-static-20261006-r7 baseline_v5_audit
.\.venv\Scripts\python.exe -m benchmarks.p1_b_offline_audit --frozen benchmarks/results/local/auto-static-20261006-r7 --run-id baseline_v5_audit --output <新的只写一次JSON路径>
```

具体 pytest 节点、退出码与计数登记于相邻 `p1-b-validation-20261011.json`：主 P1 组合 232 passed/0 failed/0 skipped；最后增加盲审答案隔离后新单测 14 passed/0 failed/0 skipped；Node 两组 11 和 4 passed/0 failed/0 skipped，后一组以 `^B06|^B07` 排除 P2B。232 与后续14重叠，不重复相加。初次 B01 186 passed/1 setup error 是本轮新 tmp 父目录不存在，改用现有忽略 tmp 后由组合复验关闭；A 两 suite 122 setup errors 为 `os.geteuid`，仍开。编译/严格 JSON/diff/敏感检查在收工回执登记。

## 可交付与剩余门禁

既有受支持平台的 Git/ZIP 扫描、静态候选、pending 事实与报告可按历史回执演示；本轮离线 hash 审计和对账可独立复算。尚无 P1 B 全链终态签收、正式 Gold/质量/性能结论或当前 Windows A 生命周期绿灯。

可报名/参赛仍须目标机/Java 核心及竞赛材料验收；完整作品须关闭 B03 来源错绑、新事实 revision、A 终态/重启/Draft/Report、前端浏览器签收与正式发布；竞争力须真人 Gold、新 holdout、独立误差/对比/消融与受控性能。无统一分母或权重，不报百分比。

本次运行精确 token 数不可获得；开工估算 12,000～24,000。离线审计范围已交付，新增确认 B03 固定 commit 错绑；整体任务仍 PARTIAL，无法凭缺失遥测判断是否落在估算范围内。
