> GitHub脱敏发布副本：本地原件保持不变。本文中的历史文件路径仅是来源定位，并非本次附带的GitHub文件；本次仅上传同目录五份交接文档，不含源码包、运行镜像、数据或历史证据附件。原件与发布副本身份见本目录Manifest及Git提交。

# P2 A1—A5 总交付核对（2026-10-15）

结论：**PARTIAL_HANDOFF_READY**。统一候选、固定对象和来源材料可以继续复用；本轮补齐索引与配置边界。当前前端81文件、NOTICE新窄修原件、旧v6 Formal尚缺；完整接收机运行组合也尚未签收。没有重新开发、重包或重测。

核对依据：Owner任务书与本次补交的xzb最新原件。后者5443 bytes，SHA256 `d35cf2463a1fd3199562d53e2068eef7928e0f875ba82d3ac4188ffa021343bc`。负责人分别为后端A/Owner、后端B（cz）、前端（xzb）。下述历史结果均保留执行环境边界。

## A1 当前前端：BLOCKED_MISSING_SOURCE

`FRONTEND_CURRENT_SOURCE_NOT_RECEIVED`。定向查找本地工程、相关交接档案、Downloads及微信temp/drag，未获得最新清单、回执和完整81文件。未查看无关微信数据，也未联网或fetch。

xzb声明基准HEAD `9ad9998d6f3df82618966c5865d13006a1efe6bc`，含未提交增量；聚合SHA `c92a2143f1cdc46f903089f22237a62b95f183f75dd0111b78bfa991d5a732bd`。D1已形成及142单测、TypeScript/build、11项TEST_ONLY浏览器通过按xzb原件声明登记，不否定已做；本轮未取得对应原始回执，未独立计算聚合Hash。不能用旧HEAD或其他录制前端代替。

| 静态检查项 | 合同预期 | 当前结论／责任 |
|---|---|---|
| scan_id / assessment_id / assessment_version 与 result_id / revision 分开 | Scan/Assessment ID及version与Result ID/revision分开，previous_result_id可追溯 | BLOCKED_MISSING_SOURCE；xzb提供原件，A核查 |
| 精确 Result GET 和固定 URL | 按精确ID和assessment_version读取，不用latest替代固定结果 | BLOCKED_MISSING_SOURCE；xzb提供原件，A核查 |
| Summary 对应同一 result_id / revision / hash | 同一Result及其revision/Hash的伴随摘要 | BLOCKED_MISSING_SOURCE；xzb提供原件，A核查 |
| L1 候选与缺口展示 | 保留候选、缺口、三态用途，不自行生成许可肯定结论 | BLOCKED_MISSING_SOURCE；xzb提供原件，A核查 |
| L2 Answer / Material 绑定 | Answer/Material绑定父对象、精确资源与版本及Evidence | BLOCKED_MISSING_SOURCE；xzb提供原件，A核查 |
| parent_result_id / expected_revision CAS 冲突 | parent_result_id、expected_revision冲突后先读取精确结果 | BLOCKED_MISSING_SOURCE；xzb提供原件，A核查 |
| idempotency_key 重放 | 恢复时使用原idempotency_key和原请求正文 | BLOCKED_MISSING_SOURCE；xzb提供原件，A核查 |
| 手动恢复 / 刷新 / 新旧原值 | 刷新可恢复固定URL，新旧结果按原字节核对 | BLOCKED_MISSING_SOURCE；xzb提供原件，A核查 |
| facts_hash / usage_hash / rule_version 绑定 | facts_hash/usage_hash/rule_version来自父绑定，不替换为候选规则名 | BLOCKED_MISSING_SOURCE；xzb提供原件，A核查 |
| Formal 保持、companion 非 Formal、前端不产生许可肯定事实 | Formal不变；P2 companion Summary不是Formal Report | BLOCKED_MISSING_SOURCE；xzb提供原件，A核查 |

没有当前源码，不能编造文件行号或认定具体前端缺陷。唯一补件：既有81文件清单及计算算法、对应原字节/未提交增量、D1与最新回执；不要求重新提交/推送。后端参照已固定：`docs/spec/p2-backend-contract.md`、`backend/app/p2/contract.py`及Schema，完整大小/Hash见索引。取得前端后先静态对照，目标机验证单列。

## A2 镜像：原件在，完整交付门禁未齐

本轮只读查询现有Docker daemon，未启动Docker Desktop或容器。指定摘要存在，Docker暴露为Id/RepoDigest；OCI归档中其确切角色为image index摘要：

- index：`sha256:6510aeaf29bdcfb1b3bdb3655fef73d39f9bc6164ae876011a57c356c5cef23c`
- linux/amd64平台manifest：`sha256:fc613499c8028f352492b5e7a3c4811f957882a9de65b5ef892f838b029b137d`
- config：`sha256:edef3c06fd20d947c2c08f17a93bcd972d361cb6d0c59fe8bcb51ec854885cd4`
- 既有tar：`正式提交材料/20261013_送审更新版/05_可复现成果包/openguard-runtime-amd64.tar.gz`，525268051 bytes。
- tar SHA256：`327e3e5e4c711911b87cb3a29a5ee54470b93ab8a2b170588672b27a27e821e2`。

tar和6项小型OCI元数据摘要已核验；没有解包镜像层或导入镜像。镜像创建于2026-09-12，旧构建溯源commit为`c55065184d4753d8df9e39f4eac548fd3701df6a`。它能提供历史运行/测试环境；统一候选历史API通过只读挂载`/source`和`PYTHONPATH=/source/backend`运行，不能声称镜像自身已经包含ec4c源码及xzb最新前端。

本机宿主arm64；镜像声明linux/amd64；既有交付回执记录扫描启动器ELF machine=183（aarch64）。历史验证限Apple Silicon Docker，不能推及x86/Windows接收机。侧车明确第三方再分发审查待Owner确认；本轮不作许可签发。tar已经存在，不重复导出。

`LOCKED_RUNTIME_IMAGE_UNAVAILABLE`在此仅指“获准分发、匹配统一源码、满足目标架构的完整锁定运行组合尚未成立”，不是说镜像或tar不存在。镜像身份可静态审阅；交付权限与完整组合待决。

最小重锁定提案：先确认xzb宿主/engine架构；固定ec4c的SOURCE.zip及依赖锁、Dockerfile/base digest，另固定xzb81文件；明确源码只读挂载式组合或自包含镜像；解决扫描工具目标架构一致性；登记两私有根与端口配置、组件来源和再分发许可。若确需build/pull/export/运行验证，Owner单独批准后执行，不静默换P1或latest。

## A3 隔离配置与两条输入路径

历史176次HTTP及27次恢复GET已从原件核对，仅为发送机记录。TRANSFER的44项全部大小/Hash匹配；SOURCE.zip的731项同时匹配清单与当前统一目录。没有重跑这些请求或产品测试。

已有历史数据目录：统一候选`output/p2-stage1-acceptance/`下`data`、`run2/data`、`run2/restored/data`、`run3/data`、`run3/restored/data`、`receiver-tool-check/restored/data`；目录元数据权限0700。本轮不读取数据库，也不授权把这些历史根当可重置工作空间。

接收机两个新根尚未创建，实际路径与API地址均为null。已有restore工具只接受新的目标目录，并限制归档成员、大小及链接；来源为固定P2_TEST_ONLY_DATA.tar.gz。正常工厂启动会初始化Store；不得对历史固定根启动工厂或init/apply。配置提案见索引与`evidence/a2-a3-static-configuration.json`，尚未执行。

只读根仅做固定ID/Hash/版本/Summary GET及重启读回；可写根单独做L2回答、Material、CAS、原key/body重放、新Result和旧结果不变。`P2_READONLY=1`只保护P2写入口，不能当全站只读；`DURABLE_ZIP=0`也不等于彻底禁用ZIP。固定根不得接收扫描或其他POST。原Compose带build、共享data卷和不同默认开关，不可直接作为本轮接收配置。

固定Git输入：`https://github.com/http-party/http-server`，revision `0d3b7bb5b6e8a59fd450ae2dca65870009cfcd8b`。现有bundle 462976 bytes，SHA `b4d28764503ce135702d948878d8604495fd0addf38c7a070892e93d038c714b`，位置见索引。属于独立录制候选的历史公开输入（137文件安全读取，无安装/仓库执行/Qwen），不能据此声称统一候选已接通离线bundle或新获公网权限。

ZIP三例为自有TEST_ONLY合成manifest/lock输入，各含一个精确npm依赖：is-number@7.0.0、lodash@4.17.21、express@4.18.2。每例543/540/540 bytes，原件Hash见索引。它们不是官方软件发行包；后续npm材料另有原件。历史扫描partial、rules_stage_not_connected；用途预设不会把七项null自动变为true/false。固定例只读验收；新扫描需获准私有写根和启用配置，不能重新生成固定ID冒充恢复。

目标机后续顺序：核对源码/镜像/架构 → 两个独立新根 → 只读根27精确GET及重启 → 可写根L2/CAS/幂等/旧结果 → 已批准Git/ZIP流程及用途透传 → 浏览器/同版摘要或导出 → xzb实际回执交A/Owner复核。此清单是接收方分工，不是本轮已执行；不让A重跑176HTTP替代接收机证据。

## A4 cz六文件与材料接纳

六份原件已在本机Git commit `7caddf4e870b5a0da561359cf85b4e8e66662cda`取得，大小/Hash匹配B既有六件交付回执。均不在ec4c统一提交内，也未发现展开副本；索引使用Git对象定位，不伪造磁盘文件。不能继续写“B未交六文件”。

对六个p2b模块静态比较，四个相同；`npm_metadata.py`7017→7180 bytes（增加timed_out严格布尔校验，缺省兼容false）；新增`offline_material_audit.py`7298 bytes。新Hash分别为`eb7790f46b5053b490706c3caff5a61373c4a89c44140c9335331e935f5650a6`、`6dc09c020664be0065dee77e21156688ebf911ec0dec66243642406bc32d86c2`。未修改公共API/DTO；审计工具不接入A正式签发或Result存储。录制候选同字节不等于统一候选已接纳；只需A限定审查，不重组全项目。各模块完整前后Hash见Manifest。

| 层级 | 本轮判断 | 依据与边界 |
|---|---|---|
| SOURCE_MATERIAL_ACQUIRED | 已取得 | 九项npm材料包原件及父文件字节区间一致；发行包SHA-1/SHA-512、LICENSE成员字节一致 |
| MATERIAL_OBSERVATION_ADOPTED | 历史正常工厂接纳观察已证实 | runtime-sessions正常create_default_app；HTTP原件索引24（第25条）POST materials=201；正常服务分支保存解析观察 |
| NEW_FACT_CONFIRMED | 未成立 | 技术字节归属已核对，但旧r3观察不能重复计为新业务事实；正式来源接纳/存储尚缺 |
| HUMAN_APPLICABILITY_APPROVED | 未成立 | 七用途全部null；范围NOT_DECIDED；reviewer/time/scope仍null，pending |

M1原对象与固定r3、Material、Answer、Summary完整身份见Manifest `A4_M1`；来源是is-number@7.0.0，LICENSE SHA `35bdd8a44339719441900fb50fbefc5e2dca1ca662cbaed7a687de842c8b70f2`。现有缺口包括upstream_source_attestation_missing、object_scope_unverified及uploaded_material_applicability_pending。不是“官方材料未到”；A负责正式接纳策略与受信回执，Owner提供真实用途/范围及指定审核者，审核者记录理由、原件Hash与适用性。Codex不代签。

资源级条件候选已存在于**独立录制候选**：chalk@4.1.2，scan `scn_c93dba2a-e272-4a8a-90d3-e3244aa99901`，Result r3 `p2res_fd12a726d5ccb7b548f866c601584e97b2f79ceb2318029b1ad3e1e6913139d1`。保存结果`automatic-real-r3.json#/resources/19`为CONDITIONAL，商业/交付目标对应完整MIT材料；要求保留版权与完整许可声明，并核对实际交付清单。LICENSE成员SHA `48da2f39e100d4085767e94966b43f4fa95ff6a0698fba57ed460914e35f94a0`；来源、四个Evidence ID及完整父绑定在Manifest `recording_conditional_candidate`。人工适用性NOT_SIGNED。该范围只到此精确资源，不扩大到全项目，不替代M1固定对象或父Formal规则版本。

历史B计数分别承接120测试（90为子集）、两例19组、M1 60静态、npm30组；本轮0测试，不累加为总PASS。

## A5 历史项与独立生产门禁

旧v6：`OLD_V6_FORMAL_ORIGINAL_MISSING`。scan `scn_6c0f972a-18c1-4566-a7fa-df623053bea5`，Assessment `asm_8412408d-1c91-51e1-99e0-c135239bf510` v6。找到同Scan的openguard.report v1扫描报告，缺Assessment绑定，不能替代v6 Formal。需原件持有人提供原JSON/HTML、字节Hash及共享许可；或Owner接受保留该缺件，不阻挡其他前端工作。

NOTICE：最新xzb说明记载仅测试夹具补Hash、隔离433/433；本轮未取得新diff、精确候选、JUnit/日志及维护者纳入证明，故`INTEGRATION_NOT_VERIFIED`。旧固定JUnit确有433唯一节点、431PASS/2FAIL，属于历史原件，不否定后来修复；也不称新窄修集成PASS。请提供既有证据，不要求重测。

A04原交付明确`BLOCKED_OFFLINE_TEST_ENVIRONMENT`，Fail-first/最终NOT_RUN，无永久测试或代码修改；本轮不因现有Docker镜像可见就自行解除其授权/环境门禁。B03新pin接纳、生产NOTICE、M1正式来源/人审、独立真实用途建议、完整live runtime、最终Owner验收与发布权限逐项独立，见门禁矩阵，不混进D1冻结条件。

## 保护与行动回执

本轮844个台账文件原字节Hash复核一致；731源码已包含其中。17工作树HEAD/分支/dirty前后相同；107容器ID/镜像/状态/端口等稳定字段相同。cz另有12固定Git blob二次核验。目录与Hash核查不等于读取数据库或测试通过；没有全盘快照，未监控既有服务内部写入。历史日志采用已获准的定向P2审阅。

新增仅本任务目录的交接文档、证据及文档生成脚本。产品测试、JUnit生成、HTTP、外网、扫描、模型、业务库操作、容器启动/exec、build/pull/save/load、Git修改、重包统一ZIP、发消息均为0。读取现有Docker元数据不改变容器。没有改共享工作日志。

`OVERALL=PARTIAL`；`OWNER_FINAL_ACCEPTANCE=PENDING_OWNER_DECISION`；`PUBLISH_AUTHORIZATION=NOT_GRANTED`。其余M1、模型和根因阻断保留。交付后停止。
