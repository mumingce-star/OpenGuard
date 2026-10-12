# P1 B 证据续核与接收清单（2026-10-12）

状态：**PARTIAL，仅安全只读盘点与采证记录**。完整历史日志/进度阅读门禁未满足；未开展产品修改。未改源码、业务测试、冻结 Schema、规则、旧事实包、旧审计、Scan/Assessment/BOUND/Draft/Report。未启动/停止服务、安装依赖、执行来源代码、联网抓取、访问业务数据库或发布 Git。本轮四份工件是内部采证/交接材料，不是新公共 DTO 或正式评估。

本文件供 Root 转交 A/前端/Luna/Sol；**清单已准备，未实际发送，未取得新资料或签收**。相关用户和 P2 文档、reports、缓存全部保留；P2 TEST_ONLY 不作为 P1 正向证据。无人工 Gold、许可适用性、正式质量/性能结论或模型代签。

## 1. 版本、发布与本轮证据索引

| 对象 | 本轮本地只读核验 |
|---|---|
| 工作分支 / HEAD | `codex/scan-reliability-integration@50d8704a362f6e6615c1ed95d7f06da2bc3e871f` |
| origin 同名缓存 | `246bfba90c6094db7c7bad3c4d5cdcdb693ae9f1`，当前领先 7 个提交；未 fetch/在线核验 |
| origin/integration/p1 缓存 | `aabd7940f65ec8a78b33c863b4db81b400509b7d` |
| 本地 main / origin/main 缓存 | `074cccdbda14f9bcf9be5184c577541959e83209` / `476d954998be6ed943532791530f5d6234f4893f` |
| P1 离线审计 / B03 修订 | `09c61cb` / `8f9db3c` 均被 HEAD 和 origin 同名缓存包含；本地包含关系未显示 integration/p1/main 包含它们 |
| 最新发布依据 | PROJECT_PROGRESS 的“2026-10-11 当日追加成果的 GitHub 发布回执”：历史工作分支已推送并读回；旧文档当时的“未发布”不代表当前状态 |
| 本轮新增 | 未暂存、未提交、未推送；不等同 integration/main 合并、运行版本或部署 |

| 工件 | 用途 / 权限边界 |
|---|---|
| [只读复核入口](p1-b-evidence-followup-20261012.mjs) | 固定 Git blob、实际选定字段、包摘要、历史候选引用、原件摘要与台账复算；复用生成器/B06 校验器。只允许一次创建新输出，无扫描/联网/业务写入 |
| [新机器回执](p1-b-evidence-followup-20261012.json) | 221 PASS / 0 FAIL；**机器检查数，不是 pytest 测试数或独立签收**；含 15 source、31 Evidence、31 fact 行及所有未绑定空字段 |
| [本轮验证与白名单](p1-b-validation-20261012.json) | 环境失败、工具校验、合成 B07 反例、公开/敏感检查、当前工件 SHA；合成/真实/独立验收分栏 |
| [旧审计](p1-b-offline-audit-20261011.json) | 原时点的历史缺陷与 v2 对账，原字节保留；不得当作 r2 已消费证明 |
| [修订 manifest](../../tests/fixtures/notice-license-facts-v3/revisions/source-binding-r2/manifest.json) / [amendment](../../tests/fixtures/notice-license-facts-v3/revisions/source-binding-r2/amendment.json) | 外部 pin、受影响 Evidence、旧派生结果状态、待签收字段 |

## 2. B01—B07 当前状态

| 工作包 | 本轮真正完成 / 累计可复用 | 未关闭与责任 |
|---|---|---|
| B01 | 28 个 HF/ModelScope fixture 文件及 3 个 manifest 与原审计 SHA 一致；有 observed 的身份/revision 复核。累计受限离线 parser、transport 可复用 | parser 本轮未执行；HF 合成 revision、ModelScope acme/demo 合成观察不是新 live 来源。A 提供实际 Profile 消费对象；Luna 异机，Sol 语义签收 |
| B02 | v2 canonical pin、17 保存候选的 fact/package Hash、Pointer、Evidence 引用和保守状态复核；2 条零候选保留；义务 0。累计既有 detector | 本轮不重新运行 Python detector；候选不当 Formal。A 新真实 Assessment/资源映射、Luna 反例签收 |
| B03 | r2 15/15 Git 普通 blob 与 size/file SHA、31/31 source/selected SHA、31 fact 引用闭包、8 Evidence 修订映射、发布工件字节全匹配；新回执不覆盖旧包 | Luna/Sol 独立审核；A 先接受合法消费路径并给新事实版本。未签字段全部 null；不得直接转 NOTICE source 或 Formal |
| B04 | 已有 selector/collector/严格五态/来源包/生命周期能力与负例入口已定位；两条 excerpt 历史失败已定位到 A 夹具缺字段 | A 修夹具并受支持环境复跑；固定 Git/ZIP 真实终态 STAGED→BOUND→Draft→Report、重启与前端签收缺。本轮不关闭历史失败 |
| B05 | 当前 freeze/catalog/receipt/metrics/queue Hash 闭包；30 台账、25 固定归档 SHA、5 失败及其缺归档状态复核；train/dev gold/prediction 文件 SHA 重算 | Python 原 audit 本轮未执行；旧 gold 为机器 oracle。真人双标/裁决、新 holdout、Luna 封存及 Sol 等级批准缺，不输出正式指标 |
| B06 | 314 未裁决保留、train/dev 14 重复组复算；224 无答案源入口及空模板复核；两个现有治理 CLI 通过 | 314 不是已确认错误；确认错误 0 是未裁决状态，不能推断规则无错。两名真人、第三人裁决、Luna/Sol 负责后续，规则未改 |
| B07 | 固定 v2 校验器/汇总器复用；字段与失败保留、缺件/重复 receipt 反例独立工具对账见 validation；采样建议见第 7 节 | 没有新受控 Linux 实测；A 原始测量/环境及计划、Luna 独立复算、Sol/Root 批准缺；两份合成/真实回执均不能自动成立正式 p95 |

旧 `b-backend-work-packages.md` 的 B05 “尚无真实执行”等是早期快照；当前已有固定收集与机器静态 Bench。它仍不是人工 Gold 或正式质量证据。

## 3. 新旧事实版本与真实链

固定 Git 来源为 `9d67b88f39fa4aaa8ab24048aea224204eabd490`。SHA-256 的输入分别是文件原字节和按键排序/紧凑 UTF-8 JSON 的完整对象；数组保序。二者不同，不能互换为 API facts_hash、库存摘要或 NOTICE package_hash。

| 工件 | 文件 SHA-256 | canonical package SHA-256 |
|---|---|---|
| 旧 v3 | `4f2a8304ad457dffdc7e4ba276e3602bf93b4f83b1e7e177bbcb84f4a8d841f7` | `ea04f17caf7202c4c560502b7dcec73ecc164e01f7d2c53083e6c21d0d12a8c9` |
| r2 v3 | `6157b50a2a47955574c404f2302ab7b35a3d2e8e3046aaadcfe26326ce442795` | `466f8abd7f3b0f2fd7ff1a0f80a8cbd210db6ec80bbb6857046651f2fb67b096` |

8 条变更都是 `frontend/package.json` 来源文件 SHA：旧 `16e9db4fb169ef63a982912b983e8259332e580554a451e4053c3f43e73b05fc` → 固定 Git 实际 `a8e9bab912ffc5ef1afc2da36db5b0de932ce872e235e02b55dce9ceca65f09a`。

受影响 Evidence：`evidence.dependency.npm.@tailwindcss--vite`、`.react`、`.react-dom`、`.tailwindcss`、`.@types--react`、`.@types--react-dom`、`.typescript`、`.vite`（除第一个外均沿用同一 `evidence.dependency.npm` 前缀）。完整 8 ID 和逐条 old/new/selected Hash 在新回执 `sections.b03.affected_evidence_ids/evidence`；31 项 fact/关系/gap/report 行及 selected Hash 未变。HF Evidence 的 provider revision 和本机 Git blob revision 分别列出，不拿 provider revision 作本仓库 Git 版本或上游授权证明。

`benchmarks/p1_b_offline_audit.py:113` 仍读取旧 v3，但明确复算并保留 mismatch，没有把旧包自动提升为可信。它继续用于历史缺陷盘点；**r2 当前复核用本轮入口**。v3 adapter 校验 caller 给定 canonical pin 和候选语义，不替 A 验证库存/终态或审核来源；自 pin 成功不足以接纳。

三类独立身份必须保持：B02 v2 `LicenseNoticeCandidateSet`；B03/B04 v3 `draft_facts_only` 观察；CZ `openguard.notice-source/1` Collection/Package。NOTICE package 自摘要另排除 `package_hash`，A admission 的 bytes/package_hash 校验按其独立契约执行，不与 v3 canonical pin 混用。

| 真实链环节 | 旧/历史证据 | 本轮 r2 同版真实证据 |
|---|---|---|
| 固定输入 / inventory / 资源 Evidence | 旧离线审计明确 `bounded_static_source_not_A_inventory` | A 未提交；全部 null |
| 终态 Scan / Formal Assessment | 已有历史受支持环境扫描与独立 P2 TEST_ONLY 回执 | 不借其身份；A r2 合法消费路径和实际对象未提供 |
| NOTICE STAGED/BOUND / Draft / Report | 源码已有接线，历史前端有 NOTICE 缺失态 | 未有同版成功链、包/绑定 Hash 或引用闭包 |
| 下载 / 刷新 / 重启 / 旧版本 | 历史其他版本的可读性不丢弃 | 前端与 A 未签收 r2，不能填成功 |

旧包是“保留且有来源缺陷的历史事实”。A 应提供旧派生对象清单并显式标历史/失效及新版本重算记录，禁止覆盖旧结果或用相同旧 ID 声称 r2 已消费。B 不知道实际旧派生对象 ID，未补造失效清单。

## 4. NOTICE 两条失败：准确定位与最小建议

原始失败节点（均在 `tests/unit/test_p1_notice_draft_production_wiring.py`）：

1. `test_a3_06_11_content_and_no_authority_escalation[resolved-excerpt-notice_source_excerpt_truncated]`
2. `test_a3_06_11_content_and_no_authority_escalation[unresolved-excerpt-notice_source_excerpt_truncated]`

历史复现基线：`6dc340776bc63c3b925d7fa3645efbbd40c4ccf9`。夹具引入提交：`064a3d03c4f087bdbfc96e7564ac4a77fae4a11c`，其 Git 父提交 `04435e56cec38ab47aaf82125a56ab34359a5555`。失败基线与引入提交是不同概念；本轮证实当前夹具和严格 Content 模型与失败基线字节一致。

原回执：`docs/p2/evidence/baseline-notice-comparison.xml`，SHA `f11b70817b315da7c53e4fe91ad485f8bbf5e01eb684161f7131b256af5ba88e`，UTC `2026-10-10T05:40:05.715774+00:00`。两条为 Linux **FAIL**，不是 setup error；出错于测试第 179 行 `NoticeSourceCollection.model_validate(value)`，原始错误 `observations.0.content: Value error, excerpt_content_invalid`。仅复用 P2 目录中的这两条 P1 历史失败，不复用其 428 PASS 或 HTTP 成功作 P1 验收。

历史环境由 runtime-receipt 可核对：镜像 `sha256:6510aeaf29bdcfb1b3bdb3655fef73d39f9bc6164ae876011a57c356c5cef23c`、network none、只读 rootfs、UID 10001、2 CPU/2 GiB。完整 Python/内核版本未找到，记录 null，不据镜像猜测。Windows 旧 `os.geteuid` setup 错误与当前 Python 启动 exit 101 分开；本轮没有运行这些业务节点，不能称重现或修复。

定位：excerpt 分支从合法 full 拷贝数据并改 text/byte_range/truncated/retained Hash，却遗留 `excerpt_bytes_sha256=null`；Content 要求 excerpt Hash 与 retained Hash 相等。现有 B collector 已正确设置它，`test_excerpt_hashes_bind_retained_prefix_and_whole_content_without_replacement` 已有相应反例入口。

建议 A 维护方最小修改（本轮未应用）：用明确 UTF-8 编码前缀，计算一次 retained SHA，同时设置 `retained_bytes_sha256` 与 `excerpt_bytes_sha256`；保留原 `whole_bytes_sha256`。不要关闭 Content 校验。补覆盖非 ASCII 正例，以及缺/错 excerpt Hash、坏 UTF-8、范围错配、retained 篡改反例；先原样复跑上述两节点，再相关 collector/model/wiring 小集。若通过，分别记录夹具修复、模型反例、生产绑定证据，不合并为“NOTICE 已完成”。

本轮 Docker 只读查询 exit 1（不可连接/配置读受限），未启动 daemon 或服务。A 提供受支持环境回执即可续核，无需 B 重实现 A 存储。Owner 接受的 N2/N3 继续 deferred；不自动扩成阻断工作。

## 5. A / 前端 / 真人 / Root 精确依赖

每一项到件后独立核对并解锁对应工作，不等待全包才开始。缺资料保持 null；“已有代码”与“真实运行回执”分别保存。

| ID / 负责方 | 需要字段/工件 | 已有资料 | 当前缺件 | 解除条件 / 解锁 |
|---|---|---|---|---|
| A-RUN / A | 完整代码 SHA、API/Schema/registry/parser/tool/rule 版本、dirty diff digest、平台/镜像/有效非敏感开关、命令 | 当前 HEAD 与 main.py 接线 | 实际运行代码/配置回执 | 锁定唯一组合；解锁同版链核对。main.py 的 `OPENGUARD_ENABLE_ASSESSMENTS=1` 启用 lifecycle/BOUND/Draft/Report reader，metadata 另有开关；本轮未证明运行实例开关 |
| A-INPUT / A | 固定 Git 完整 commit 与来源输入 Hash；ZIP bytes SHA/size；同版库存 root digest、文件 path/size/SHA、资源身份/revision | r2 固定源码及归档台账 | 两种输入真实 A inventory | 输入与库存闭包逐字段一致；解锁 B01/B03/B04 实际资源对账，不抓新来源 |
| A-SCAN / A | 同 scan_id 的 queued→终态、registry revision、input/inventory/facts digest、status/stage/error、partial omissions/gaps、资源/Evidence 映射 | 已冻结 ScanRef，历史扫描 | 当前两条真实终态对象与运行记录 | 同输入/scan/version/hash/Evidence 闭包；解锁终态签收 |
| A-R2 / A，Luna/Sol | 接收的 r2 canonical pin、审核回执、合法消费类型/映射/新版本策略；旧派生结果 ID 及历史/失效状态 | 15来源/31事实/8变更，审核字段 null | A 消费路径确认、独立审核、新绑定 | A 明确允许的观察用途并重新验源；解锁新事实消费。禁止把 v3 当 Formal/NOTICE source |
| A-ASM / A | Assessment id/version/scan/facts_hash/usage_hash/完整 rule_version/内容 Hash，实际许可证关系与 Evidence | 冻结 AssessmentRef、候选 pending | 同输入正式对象与原件 | 对象引用闭包且观察未升级授权；解锁 Assessment 对账 |
| A-NOTICE / A | Collection→admission→STAGED package ID/bytes SHA/package_hash/coverage→BOUND binding Hash/CAS版本/Assessment；locator、source/whole/excerpt/retained Hash | 工厂、CZ validator、binding/reader 已实现 | Git/ZIP 同版真实 stage/bind/read 回执 | 校验全部来源/版本/覆盖字段；解锁 NOTICE 接收，成功不等于义务履行 |
| A-DRAFT / A | draft_id/version/content_hash、package/binding pin、同 ScanRef/AssessmentRef、资源/Evidence/义务引用；text 缺失原因 | NoticeDraft 代码 | 实际同版 Draft | refs 全闭包、pending 和缺口保留；解锁 Draft 签收 |
| A-REPORT / A | snapshot_id/version/content_hash、完整固定 Assessment/Draft/Task/Profile/Graph 内容及引用；JSON/HTML href/size/SHA | ReportNoticeReader 已接线、历史 NOTICE 缺失态报告 | 同版含 NOTICE 报告和真实下载 | 固定版本完整内容，不指向 latest；下载 SHA 相同；解锁 Report 签收 |
| A-RECOVERY / A | 重启前后 GET 对象/下载字节 Hash、旧版本可读、负例零写入/幂等重放证明（逐表内容摘要/CAS及对象计数即可，不交DB） | 历史 TEST_ONLY unit、安全入口 | 当前真实两链 read-only/restart/negative 证明 | 不变原件和失败零写入；解锁恢复/负例门禁 |
| A-PROFILE / A | 同 scan/resource/identity/revision 的 Profile、transport/parser版本、response SHA/size/UTC/final URL、coverage、消费对象 version/content_hash/Evidence | 28 fixture 与历史 ModelScope 观察 | 真实 Profile 实际消费对象，不是新抓取请求 | 来源观察与消费映射一致；解锁 B01 生产签收，Luna 异机另签 |
| A-LINUX / A | 受控 Linux 采样计划、原始 receipt、独立环境/阶段/Hash/失败、时钟和内存计量附件 | v2 validator/汇总器、采样建议 | 原始实测和批准 | 同 cohort 的合法固定输入；解锁 B07 工具对账及后续等级审批，不自动 p95 |
| F-RECEIVER / 前端 | 前端完整 SHA/浏览器/平台；A 同版 API、同 scan/Assessment/Draft/Report；脱敏网络状态/引用/Hash；pending/partial/零候选/错误页面；JSON/HTML 下载 SHA；刷新/重启及旧版读回 | F-P1-07 PARTIAL 与历史页面回执 | r2 同对象浏览器记录和操作者签收 | 实际浏览器 + A 原件 Hash 一致；解锁前端签收，B 单测/静态 JSON 无代签权 |
| HUMAN-GOLD / 两名真人+第三位裁决者，Luna/Sol | 固定源材料权利范围、双独立标注/exposure、各自提交 Hash、分歧裁决、新 holdout freeze、等级批准 | 224 无答案源入口、空模板；314 待裁决 | 全部人工提交/签名/冻结 | Luna 封存后由真人判断、Sol 审核等级；解锁 Gold/正式评测。不能发送含机器答案的本回执/旧审计 |
| ROOT-RELEASE / Root | 阅读门禁补核、独立审查、目标环境/Java核心与竞赛材料、发布授权、选定文件测试/公开/敏感清单、功能分支读回/PR/集成状态 | 历史工作分支发布、本文白名单 | 本轮授权与接收审核；完整历史读取仍缺 | 获用户明确发布指令后统一处理；解锁规定发布条件，main只经PR |

交付链必须分别为**固定 Git 与固定 ZIP 的同版本真实链**：输入/库存 → 终态 ScanRun → Assessment → NOTICE STAGED/BOUND → Draft → Report → 下载 → 重启读回。来源 URL digest、ZIP bytes SHA、inventory digest、A facts_digest、v3 canonical pin、NOTICE package/binding Hash、Draft/Report 内容/下载 SHA 分列，不用同名 `hash` 糊合。

负例矩阵入口：零候选/1024 截断 `test_notice_source_selector.py`；预算/空文件/坏 UTF-8/超大/重复/whole-excerpt-retained Hash `test_notice_source_collector.py`；篡改 `test_notice_source_contract_independent.py`；错 scan/revision/Assessment/Hash、重放/重启/零写入 `test_p1_notice_source_binding.py`、`test_p1_notice_source_adapter.py`、`test_p1_notice_draft_production_wiring.py`。本轮仅定位入口，未将历史 pass/setup 数冒充本轮测试。

收到 A 资料后：先固定工件原字节摘要；逐项比较 input→inventory→scan→Assessment→source→Draft→Report 的 ID/version/hash/refs；任何错绑/缺正文/Hash不一致保留原失败、node/Pointer/expected/actual 和最小复现。机器合成、本机真实、独立接收三栏记录，不能自动换旧对象身份或补造生产成功。

## 6. Bench / 误差治理

本轮实际复核 30 台账、25 ZIP Hash、5 failed 的失败原因和未生成归档，台账分母未变。4 个归档超上限、1 个 ref 非单一 commit，均保留。train/dev 固定 Gold/prediction Hash和队列 Hash 闭包；314 原来源行号核验沿用旧审计，并由本轮归档/artifact Hash传递验证，**未重新解压逐行或运行标注器**。

计数更正：旧 audit 的 `repeated_match_keys=18` 实现是各样本 `len(predicted_labels)-len(unique_match_keys)` 之和，代表额外重复观察数量，不能直接称 18 组。本轮重算 train/dev 为 14 组，与队列一致；全 split 18 字段仅沿用已 pin 的历史计数，未解析 holdout 标签复算。不同 Evidence 不删除，不用于刷分。

44 机器 FN / 270 机器 FP 的 314 分歧全部待真人裁决；本轮已确认错误 0、规则变更 0、消融结论 0。旧 holdout 已暴露，仅开发使用；本轮只核其归档摘要，不读个案标签。Luna 独立封存新盲集，Codex 不造 Gold 或签名。

盲审者只收到现有源入口包、空模板及依法取得的固定材料；本文件和机器 JSON 含内部答案/选择信息，**不得发给盲审者**。224 入口来源是选择性错误队列，有选择偏差，不能作为总体 Recall 分母。

## 7. 性能准备（建议，未测量/未批准）

先由 A/环境负责人确认合法固定输入、代码 SHA/镜像、限制与时钟。以 source/input/config/环境/工具版本构成同一 cohort；每 cohort 区分 cold/warm，不混不同 ZIP/Git、规则配置或峰值限制。建议首轮每输入模式 5 次冷启动和 20 次热启动作探索；正式样本量/重复计划、异常归类和指标等级由 Sol/Root 批准，当前不是统计保证。失败/timeout 全保留，事先固定停止条件，不事后挑成功样本。

原始 v2 必填：schema、execution_mode=controlled_linux、production_scan_started=false、startup_mode；唯一 receipt_id/run_id；source_id/完整 source.commit/source_sha256；artifacts.input/config/result SHA；Linux family/kernel/image digest；CPU model/逻辑核；内存 limit/observed_peak；ScanCode/Syft/Detector/完整规则版本；total_duration_ms；有序 unpack/scancode/syft/static_detector/rule_consolidation 各 duration/status/failure_reason；status、error_classification。失败未运行阶段仍存在，not_run=0；result artifact 应为固定失败结果回执，不删除失败。

计量附件另提供 UTC开始/结束、单调时钟/计时范围、CPU/内存采样工具及间隔、冷/热定义、并发/缓存/是否包含获取与 AI、采样计划/完整原始路径及摘要、失败台账；不擅自扩冻结 v2 DTO。现有工具验证字段/同环境/唯一 receipt_id，**不会证明数据来源真实，也未强制 run_id 唯一或同 input/config cohort**；接收方必须另对账，未来工具加固另审。

本轮 validation 中的 controlled_linux 对象是合成工具输入，运行实际在 Windows/Node；其数值不是 Linux 测量。两份回执只能解锁工具对账，不能自动形成正式 p95；汇总 `formal_performance_claimed=false` 必须保留。

## 8. 验证、复现与发布白名单

从仓库根目录运行，输出选择尚不存在的新路径：

```powershell
node docs/p1/p1-b-evidence-followup-20261012.mjs tmp/p1-b-reviewer-own-receipt.json
node tests/fixtures/notice-license-facts-v3/generate.mjs --check
```

复核入口只解析固定 fixture 的显式 TOML/XML 声明来复算字段 SHA；不是一般依赖解析器。调用现有生成器/B06 CLI，不安装或执行被扫描依赖。独立审核者必须自己运行并签发新回执；重复当前 Codex 的 JSON不是独立签收。Python 恢复后可用原 r2 文档中的既有24节点与原审计CLI；本轮未重跑它们，不改版本约束或要求安装。

本轮 Windows/Node 26.2.0：新入口 exit 0，221 PASS/0 FAIL；生成器及 B06 两 CLI exit 0。Python `--version` exit 101、Docker只读查询 exit 1，属当前环境不可用。历史 234 Python、10 Node、24 r2 Python、Linux 428/2、122 Windows setup 等不加总、不称本轮成绩。

Root 仅可选择以下新增路径及本轮三份协调文档追加片段；既有用户/P2内容不可连带提交：

- `docs/p1/p1-b-evidence-followup-20261012.md`
- `docs/p1/p1-b-evidence-followup-20261012.mjs`
- `docs/p1/p1-b-evidence-followup-20261012.json`
- `docs/p1/p1-b-validation-20261012.json`
- `docs/coordination/AGENT_WORKLOG.md`、`docs/coordination/PROJECT_PROGRESS.md`、`docs/05-ai-assistance-log.md` 的本轮追加片段

禁止上传 tmp/、reports/、缓存、ZIP、第三方正文、数据库、密钥、本机绝对路径与其他未提交材料。未引入第三方依赖/资源；现有 Node/Git及项目工具沿用资源台账，无需造新资源登记。AI辅助与共享记录仅说明机器采证，不变更人工状态。

## 9. 剩余门禁与收工口径

本轮真正完成：安全盘点、r2/保存候选/台账离线新回执、历史失败精确定位、独立复核入口及接收依赖/采样/白名单。累计独立能力：受支持环境历史 Git/ZIP扫描、候选/报告，B离线parser/collector/候选工具、固定来源复核；当前 Python 环境失效，不能声称全部现在本机可跑。

NOTICE 仍须 A 夹具修复和受支持复验、同版真实 source→STAGED/BOUND→Draft/Report→下载/重启、前端浏览器签收。P1 仍须完整历史阅读、Luna/Sol独立审核、A合法新事实生产接纳、真人 Gold/新盲集、原始 Linux 测量、规定发布/接收机及完整契约场景签收。

可报名/参赛还须资格/权利材料、目标机/Java核心验收；完整作品还须上述生产/浏览器/恢复/发布和匿名技术报告/视频/资源AI材料；获奖竞争力还须真人Gold/new holdout、对比消融、可信质量/性能。没有分母和权重，不报完成百分比。

本次运行精确 token 数不可获得；开工估算12,000～24,000。范围收口为只读采证与交接，未完成完整P1/NOTICE门禁，无法核定实际用量是否在估算区间内。

## 10. 独立审查与依赖续接（2026-10-12，本轮增量）

关联 START：`20261012-223207-GPT6-P1B独立审查续接`。第 1—9 节保留前轮时点；本节是新增协调记录，不覆盖原包、审计或业务对象。README 和 Sol 交接已完整读取，共享日志/进度历史未完整读取，阅读门禁仍未满足；本轮没有产品修改。

已实际使用本对话的协作工具派发 `/root/luna_r2_review`、`/root/sol_r2_review` 两个独立上下文审查任务，收到工具成功回执。派发日期为 2026-10-12（Asia/Shanghai）；精确工具派发时间未提供，代理 START 时间另见共享日志。两者均为同机 GPT-6 Codex 审查角色，不是异机 Luna/Sol 模型或真人签收。要求各自运行既有复核入口、检查固定来源和消费语义、签发新的审查记录。**实际派发不等于审核通过或 A 接收**；结果到件后只在本节续记。

未发现 A/前端跨聊天发送工具，未调用外部消息渠道。以下内容交当前 Root 对话和工作区转交，A/前端/真人仍为未发送、未到件、未签收。不得将 Root 可读或任务派发写成对应负责方已收件。

### 10.1 14 项依赖的发送、到件与验证状态

已有资料、必需字段、解除条件和解锁任务逐项沿用第 5 节；本表只补实际流转和新增缺口，不另造清单。到件日期“未提供”表示当前没有该项 P1 原件，不表示其他工作包没有新资料。

| ID / 负责方 | 本轮已有 / 仍缺 | 发送状态 | 到件日期 | 验证结果 / 解除入口 |
|---|---|---|---|---|
| A-RUN / A | HEAD/接线已存在；缺实际运行 SHA 和有效配置 | 待 Root 转交，未向 A 发送 | 未提供 | 未验证实际实例；第 5 节 A-RUN |
| A-INPUT / A | 固定来源 pin 已有；缺 Git、ZIP 两条实际库存 | 待 Root 转交，未向 A 发送 | 未提供 | 未验证真实输入闭包；A-INPUT |
| A-SCAN / A | 历史扫描已有；缺对应两条终态 ScanRun | 待 Root 转交，未向 A 发送 | 未提供 | 未验证新同版 Scan；A-SCAN |
| A-R2 / A，Luna/Sol | 两份同机独立上下文回执已到；仍缺 A 合法观察消费确认、新版本及旧派生清单 | 两审查任务已发送并返回；A 未发送 | 2026-10-12 同机审查到件；A 意见未提供 | 来源观察 PASS、语义 QUALIFIED；非生产签收，见 10.4；A-R2 |
| A-ASM / A | 候选 pending 已有；缺同输入完整 Assessment 原件 | 待 Root 转交，未向 A 发送 | 未提供 | 未验证事实/用途/规则引用；A-ASM |
| A-NOTICE / A | 工厂/校验/reader 已有；缺真实 STAGED/BOUND 与失败修复回执 | 待 Root 转交，未向 A 发送 | 未提供 | 原两条 Linux FAIL 未关闭；A-NOTICE 与第 4 节 |
| A-DRAFT / A | 代码已有；缺同版不可变 Draft | 待 Root 转交，未向 A 发送 | 未提供 | 未验证固定内容/引用；A-DRAFT |
| A-REPORT / A | reader/历史缺失态已有；缺同版报告及下载原件 | 待 Root 转交，未向 A 发送 | 未提供 | 未验证 Report 引用闭包/下载；A-REPORT |
| A-RECOVERY / A | 既有反例入口；缺本链重启、旧版、重放及零写入证明 | 待 Root 转交，未向 A 发送 | 未提供 | 未验证恢复和业务负例；A-RECOVERY |
| A-PROFILE / A | 离线 fixture 已有；缺真实 Profile 消费对象 | 待 Root 转交，未向 A 发送 | 未提供 | 未验证真实上游观察；A-PROFILE |
| A-LINUX / A、环境方 | 现有 validator/采样建议；缺原始测量/计量附件和批准 | 待 Root 转交，未向 A/环境方发送 | 未提供 | 合成检查不能充作 Linux 实测；A-LINUX 与第 7 节 |
| F-RECEIVER / 前端 | F-P1-07 历史 PARTIAL；缺同版浏览器/下载/恢复原件 | 待 Root 转交，未向前端发送 | 未提供 | 未签收真实 API 浏览器流程；F-RECEIVER |
| HUMAN-GOLD / 双标真人、裁决者，Luna/Sol | 224 无答案入口/空模板；缺双标、裁决、新 holdout 和等级批准 | 待 Root 按盲审边界转交，未向真人发送 | 未提供 | 314 仍待裁决；HUMAN-GOLD |
| ROOT-RELEASE / Root | 本工作区已提供四工件和本节转交正文；缺正式审核/用户发布授权 | 当前 Root 可读；未发布 | 2026-10-12，仅工作区交付 | 未签发布验收；ROOT-RELEASE |

P2 新资料已由另一任务核对并在 `20261012-222740-GPT6-B官方npm原件到件收工` 登记；本轮只读其协调状态，保护其两个产物，不重复索取该批资料，不把 M1/P2 对象当上表的 P1 Git/ZIP 同版链。

### 10.2 交 Root 的可直接转交正文（尚未对外发送）

**给 A：**请先回复 A-RUN、A-R2 及第 4 节两 excerpt 节点的维护/复验安排，再按件提供第 5 节 A-INPUT 至 A-RECOVERY 的固定 Git 和 ZIP 同版本真实链。请明确 r2 `466f8abd7f3b0f2fd7ff1a0f80a8cbd210db6ec80bbb6857046651f2fb67b096` 仅作为 v3 观察的合法消费路径、固定 pin、新对象版本和旧派生对象历史/失效策略；不要借旧 Scan/Assessment/BOUND/Draft/Report 身份声称新修订已消费。文件原字节 SHA、v3 canonical、A facts/inventory 和 NOTICE package/binding Hash 分列。excerpt 夹具按明确 UTF-8 前缀计算 retained 摘要，同时设置 excerpt 摘要，保留 whole 摘要；请在受支持环境复跑原两参数节点及相关 collector/model/wiring，并交命令、环境、exit、原始结果。B 不直接改 A 夹具/存储，不弱化 Content。另请提供 A-PROFILE 实际消费对象，以及 A-LINUX 的原始环境、五阶段、Hash、失败和计量附件；先核 run_id 唯一与同 input/config cohort，不把工具通过当实测真实性或 p95 批准。

**给前端：**请在获准环境使用 A 同版本真实 API，逐项提供第 5 节 F-RECEIVER 所需的同 scan/Assessment/Draft/Report、前端 SHA/浏览器环境、脱敏网络、pending/partial/零候选/错误页面、JSON/HTML 下载 SHA、刷新/重启及旧版本读回。逐项说明操作者与签收状态；静态 JSON 和 B 单测不能替代浏览器签收。

**给真人标注协调方：**仅转交 `p1-b-blind-source-packet-20261011.json`、`p1-b-human-review-template-20261011.json` 和已获准固定源入口，路径均位于 `docs/p1/`。组织两人独立标注、第三人裁决，Luna 独立封存新 holdout，Sol 另批等级。**不要转交本文、机器审计/续核 JSON 或内部答案给盲审者**。旧 holdout 仅开发使用，收到真实裁决前不修改规则或出正式指标。

### 10.3 原件保护与本轮发布边界

取件时原 MD 为 23900 bytes，SHA `e228e1b7546cd18f914c002ba330ba099a91365e1001acad10f75168c58810c7`；本轮仅末尾追加，因此原 validation 中 MD pin 继续指向前轮版本，**不等于当前追加后文件摘要**。原 MJS、机器 JSON、validation JSON 摘要沿用原回执，要求收工确认不变；旧包和旧审计不改。新的审查回执只证明其实际执行/审查范围，不改旧 manifest/amendment 的 null，也不自动签发授权、Gold、生产或异机验收。

当前发布仍未获授权。Root 复用第 8 节白名单，仅在审查结果真实到件并复核后增列必要独立审查回执、本节与本轮三份协调文档的追加片段；tmp 原始机器输出留本机且不上传，P2、reports、用户其他变更均排除。不新增第三方资源/依赖，继续使用既有 Node/Git 与项目工具台账。

### 10.4 两份同机独立审查到件与验证分栏

2026-10-12 已收到两个审查任务的实际执行结果和新回执，父任务完整核阅其内容并要求补足实际 stdin 检查代码。它们是新的审查记录，不是 B 原 JSON 改名；审查程序复用了同一入口，故两份 221 **分别记录，不求和，也不作为新增测试覆盖数**。未发现新的 r2 固定来源字节缺陷。当前结论仅足以支持离线观察审查，整体仍 PARTIAL。

| 栏 / 记录 | 本轮执行与结果 | 证明范围 / 保留条件 |
|---|---|---|
| Luna 角色 [审查记录](b03-r2-luna-review-20261012.json) | Node v26.2.0 / win32/x64 / Git 2.54.0.windows.1；既有入口一次 exit 0，221 PASS / 0 FAIL；独立 stdin 补充 28 PASS / 0 FAIL，exit 0 | 固定 Git 普通 blob 身份、15来源/31Evidence/31事实/8 amendment、8 npm Pointer/选定摘要等；固定来源观察 PASS。只补录已执行的检查源码，未重复执行 |
| Sol 角色 [审查记录](b03-r2-sol-review-20261012.json) | Node v26.2.0 / win32/x64；既有入口一次 exit 0，221 PASS / 0 FAIL；独立 stdin 补充 9 PASS / 0 FAIL，exit 0 | 固定原件/旧新摘要、保守语义、消费/失败边界；QUALIFIED。专用 Schema 验证器和 Python 本轮未执行，历史 Node10/Python24 不相加 |
| B07 合成工具检查 | 本轮未重跑；复用前轮 validation 中合成检查 | 不是受控 Linux 原始测量，正式性能未批准 |
| P1 真实生产运行 | 本轮未执行，未有 A 新生产链原件 | 不推断代码/配置/部署版本或 A 消费成功 |
| 独立验收 | 同机独立上下文模型审查已执行；异机/真人/前端未签收 | 不是两台机器、双真人标注、Luna 外部验收或 Sol 正式等级批准 |
| 业务 pytest | 本轮 0；未重探 Python/Docker 或执行业务节点 | Linux 两 FAIL、Windows setup error、前轮解释器/容器不可用分别保留；未宣称修复 |

Sol 新明确的审查边界：`backend/app/detectors/license_notice_facts_v3_adapter.py` 的 `consume_v3_facts`（第 48 行）只做 caller pin 与有限观察结构检查，不调用冻结 JSON Schema，也不验证 Evidence 的来源/选定 SHA。因此调用者自算 pin 不能替代 A 受信来源准入。本轮仅在 `backend/app/p1`、`backend/app/api/main.py`、`backend/app/pipeline` 检索未见该函数调用；这不证明所有路径不存在或未部署，不视为 r2 原件缺陷，不擅自扩为产品修改。

入口输出的固有 `same-agent/not-independent` 和 `pending` 标签保留原样；新的独立上下文事实由两份审查记录表达，不能静默改成 A 或真人签收。HF provider revision 仍为 fixture 声明；v3 完整 canonical 与 NOTICE 排除自身 package_hash 的摘要不互换。原 manifest/amendment 的审核/人审/A 读回字段仍 null，任何生产绑定字段继续 false/null。

复现入口沿用第 8 节。两份回执补录的 stdin 检查依赖各自 pin 的本机 tmp 机器输出；异机复现须先用既有入口创建**自己的尚不存在输出**，将源码中的输出路径改为该自有路径，并记录新输出 SHA。Sol 第九项另需原 execution 元数据或新的真实命令执行元数据。时间戳改变会改变原字节 SHA，不能要求不同执行的机器输出字节一致，也不能覆盖或上传旧 tmp。原运行摘要继续代表原时点；本轮未以补录命令为理由再次运行这些检查。

父复核特别指出：Sol 的公开只读检查段原先省略结果输出/失败退出尾部，内部 `check` 会捕获断言错误，因此裸运行该段的 exit 0 **不能证明九项 PASS**。原实跑九项 PASS 有原运行结果支持；仅补充复现说明和必要元数据/退出方法，不改原断言、不重跑。复现须核逐项 checks 并在 FAIL 时非零退出；未执行的示例 harness 只能标建议。当前两个角色的复现依赖均限现有获准材料，尚未取得异机执行回执。

本轮白名单增量仅 `docs/p1/b03-r2-luna-review-20261012.json`、`docs/p1/b03-r2-sol-review-20261012.json`、本文件第 10 节，以及共享日志/进度/AI辅助记录的本轮追加片段；前轮四工件白名单复用。两份 review 是内部审查记录，不是新增公共 Schema/DTO。未获发布授权，仍不得提交/推送/合并/部署。
