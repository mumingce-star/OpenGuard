# P2 后端 B 当前任务与条件续接计划

日期：2026-10-12。状态依据：21:28 两例交付、21:30 M1 技术补件、21:47 npm 指定路径核对、21:57 六份交付复核收工记录。

本文件是执行计划，不新增公共合同、DTO、规则、业务对象或签发结论。实际开工时重新检查最新记录，不能把此时点状态当作永久状态。

## 一、结论与阶段边界

后端 B 当前独立实现、文本定位、两例索引、M1 五项技术草稿、已有六工件复核和发布白名单均已收口。没有新补件或具体缺陷时，不应再安排相同复核、重复文档或全套回归。P2 业务闭环仍 PARTIAL，M1 Owner STOP 保持；独立审核、接收机和发布分别未完成。

P2 当前主线：真实对象/用途与证据 → L1 确定性条件候选或缺口 → L2 回答/小文本观察 → 独立 Result revision 与同版 Summary → 补证对账 → 前端真实接收。Result 保存成功不等于许可成立；Summary 不是旧 Formal Report。旧 R6/Qwen 用途诊断与迁移属于另行约定的工作，不能由 B 的确定性候选完成状态推导为已完成或已获执行权。

权威合同：`docs/spec/p2-backend-contract.md`，机器 Schema：`schemas/p2/contract-v1.schema.json`。本计划提到的待交接字段不自动成为获批公共 DTO。

## 二、累计完成与验证等级

| 工作 | 当前状态 | 证据与边界 |
|---|---|---|
| B 候选/材料/npm离线解析/闭包/对账工具 | 已有实现与验收 | backend/app/p2b；历史120 passed/2 warnings，原90为子集，不相加 |
| 三例正常 TEST_ONLY 扫描和材料读回 | 已有真实历史回执 | tests/fixtures/p2b/three-scan-readback.json；受控第一方manifest，不证明实际安装或发布包适用性 |
| is-number匹配LICENSE四锚点 | 已完成 | docs/p2/p2b-isnumber-clause-readback.json；1091字节匹配不证明可信官方获取 |
| 两例逐字段交接 | 草稿已交付 | p2b-two-case-handoff.md/index.json/validation.json；实际受支持用途正例仍未成立 |
| M1五项技术补件与版本对齐 | 草稿已交付 | m1-b-technical-supplement-20261012.md及alignment/validation；缺人审与M1原链，不借B另一scan绑定 |
| 官方npm记录定位及指定draft路径核对 | 调查已收口，原始获取记录仍缺 | frontend-handoff-draft.json的/npm是blocked_awaiting_trusted_egress、official_metadata_observed=false；不是原始响应 |
| 六工件现有交付复核与发布白名单 | 21:57收口，未发现工件缺陷 | 19组离线PASS，61摘要大小引用/29文件、81Pointer、9Result自摘要、21null；不是Python DTO/Schema/pytest或接收机签收 |

21:57检查器初次误把非JSON原件当JSON，导致3组检查器失败；修正检查器后只重跑失败组通过。它不是产品缺陷，不应因此修改旧业务工件。两例19组/8前端对象、M1 60静态、B120、前端133/build均引用各自历史回执，不叠加，不称本次计划整理重跑。

三个样例实际七用途共21个null保留。来源台账设想用途不能替代A保存用途。材料pending/user_supplied_unverified，新增可信Evidence/新正向结论0；conditions为空不表示没有义务。

## 三、B的剩余任务矩阵

| 编号（本计划内部） | 工作与现在可做的部分 | 解除条件 | B应交付的验收结果 |
|---|---|---|---|
| T1 | 复用已有精确需求和白名单；现在可分项答复/接收合法已有补件，无需重新盘点 | 收到新原件/回执或发现具体差异 | 每项通过/拒绝/缺失、指针与原字节Hash；不重造全部交付 |
| T2 | 官方npm原始观察核验；旧draft已核，不重复搜索 | 保管方原始响应与获取回执，A正式DTO/受控验证器；新获取另需既有明确出口权 | 精确版本、URL/UTC/HTTP/大小Hash/policy/timed_out逐项结果；许可声明仍未核验 |
| T3 | 来源和发布包关系核验 | A受信receipt及不可变commit/归档成员关系 | 错对象/版本/Hash、冲突/撤销、来源与范围关系结果；不自签可信来源 |
| T4 | is-number真实用途条件候选 | 有效Evidence、充分coverage、真实用途和适用范围 | 候选与依据/条件/缺口，或保持gap；不保证肯定结论 |
| T5 | lodash实际范围对照 | 精确实际文件集合、排除项、各范围关系证明 | 根许可不能推广到所有示例/vendor/依赖；缺口不等于商业使用禁止 |
| T6 | M1产品续接 | Owner明确续接；A旧方法映射与完整M1对象；相应人工确认 | 按授权范围继续；现在STOP，不制造capture/resolve路由 |
| T7 | 完整D4补证对账 | A新Evidence正式闭环、同scan新旧对象、完整旧Formal、获准操作环境 | 依据新增/删除/更新，建议/条件变化，解决/新增/剩余gap；旧对象保持 |
| T8 | 前端与恢复问题定位 | 获准运行组合/固定清单、实际网络与浏览器回执 | 后端闭包核验及具体缺陷修复范围；前端独立签收 |
| T9 | 发布交接 | Root独立审核、相关验证和明确发布范围 | 已有六工件白名单复用；Root处理提交推送，不默认授权合并或部署 |

不存在“必须等A所有工作包全部完成才能做任何事情”的依赖。每项有自己的解除条件。普通pending保存不强求人审肯定；适用性、来源、履行分别核验。M1 STOP是其单独任务边界。

## 四、A/保管方增量交付清单

每个交接项注明提供方、固定版本、获准读取方式、资料指针、原字节Hash/大小、状态及执行范围；“未见”不等于私下不存在。下列请求不要求阶段1合同、统一TEST_ONLY包或已收HTTP样例整包重交。

1. **运行版本与映射**：最终backend/frontend SHA、Schema ID/Hash、镜像来源/digest/linux/amd64、TEST_ONLY root ID/manifest；ec4c680候选可核验清单及主线差异；旧capture/resolve到当前路由/Service/Store的方法、DTO、事务与迁移映射。当前主线无该两条路由。
2. **可信来源签发**：不可变receipt ID/version/Hash、受信issuer、policy/version、UTC、accepted/rejected/conflict/revoked状态；scan/resource/name/ecosystem/version与完整Binding；原文Hash/大小和精确只读GET。上传者verified=true不能代替签发。
3. **包内容关系**：repository/不可变commit、相对路径/blob/原字节Hash；npm发布归档Hash、成员清单/类型/成员Hash、LICENSE与实际范围及排除项。tag/同名同版本/安装副本不能独立证明关系。
4. **新Evidence存储闭环**：license_text/scope_attestation角色、命名空间、receipt引用、内容Hash与记录Hash语义、用途pin、精确GET、Result basis引用及原子CAS。旧终态ScanRun/Evidence不可伪写。
5. **coverage和规则映射**：包括提前返回分支的status/errors/coverage/gaps传播；父Formal规则与B候选规则分别固定。facts_hash不当作任意snapshot Hash。
6. **npm原始记录与DTO**：实际原始响应/获取回执的获准只读位置，TRANSFER实际根或RESULT/MANIFEST索引；A受控验证器/出口；固定GET、request/final URL、零重定向、UTC、HTTP、32KiB、原字节Hash、policy和严格布尔timed_out。若从未取得，A在已获明确授权范围内获取，B不绕过A。
7. **完整旧对象**：完整旧Assessment原序列化/Hash、原v6 Formal ID/格式/原字节Hash/固定GET、需要对账的旧版Summary。六字段投影、新渲染、新版companion都不能替代缺失原件。
8. **恢复与负例回执**：支持平台、获准恢复根与可重置写入范围；错绑/错Hash/冲突/撤销/CAS失败后旧对象读回、重启前后Hash。历史隔离loopback HTTP不是目标机验收。

镜像和旧报告由实际持有人提供，NOTICE窄修由维护者负责，只有B实际保管/维护时才是B自身交付。现有is-number LICENSE定位已结束，不再索取。Python不可启动、Windows geteuid、NOTICE父本、baseline失败分别保留；不默认由B安装修复环境。

## 五、前端与Owner交付

前端现有实现与历史133/build复用。下一步提供：

- 最终版本组合和获准接收环境；A/Owner批准的27精确GET清单及预期ID/Hash，缺清单不凑数。
- 同固定对象真实GET与刷新/重启读回；精确版本404不回退latest。
- 可重置TEST_ONLY根上真实回答/材料POST201及精确读回。
- 两会话CAS409与head/binding重新读取；同key同body重放、同key不同body冲突。
- 超时保存未知时先读回，必要时原key原body处理；未决请求当前仅内存，不能称跨刷新恢复完成。
- state/gap/basis、服务端差异、旧新版、同版Summary、Formal区分的网络记录与截图。
- 每项失败的预期/实际、版本对象、复现步骤与责任方。B不代签浏览器验收。

Owner/授权审核者提供：真实七用途、交付文件集合/范围选择器/排除项、用途版本Hash、引用A receipt与原文Hash的适用性、独立履行确认与必要reviewer/date/scope、M1明确续接。允许unknown/pending/rejected；公开工件不代填个人信息。材料保存、来源可信、范围适用、履行、产品签收分别判断。

## 六、推荐推进顺序与项目门禁

1. 复用21:57复核结果和现有白名单，Root进行独立审核；B不用重新跑同样19组。
2. A/保管方提供现有npm原始记录、镜像/旧报告/版本映射；Owner并行确认实际范围与M1续接。
3. B只核验收到的对应增量，缺失项明确列gap，不让单项等待阻断所有其他可做项。
4. 对应获准环境中完成D4、前端接收与恢复；没有明确服务启动权不主动启动服务。
5. Root按白名单、敏感复核与既有授权处理发布，功能分支发布不等于main合并或部署。

当前可验证：离线核对/文本定位/前端静态交互；支持环境扫描报告有历史演示记录，本机Python失效不称全部当前可运行。尚缺：新可信正向候选、完整旧Formal、跨栈真实签收。报名/参赛门禁为资格权利/目标机/Java核心；完整作品还需正式闭环/独立审核/端到端/发布和报告视频匿名资源AI材料；竞争力还需真人Gold/new holdout/对比消融/可信质量性能。没有权重分母，不报百分比。

## 七、可直接交给后端B的Codex指令

```text
你是OpenGuard后端B。始终用简体中文，并称呼用户为【宇宙无敌聪明的帅哥】。
本轮执行P2条件续接，先确认新补件和最新授权，不重复已有交付与已收口复核。

【开工】
遵循AGENTS：按顺序读README、完整工作日志、进度及自身交接，检查Git和在途任务，追加START。
若历史读取不完整，明确限制，不声称满足完整门禁或据此开始产品修改。
以实际最新HEAD为准，不强退到计划引用的50d8704。
保护六份P2交付、截图指令、P1、reports、旧回执与用户未提交文件；共享记录仅追加。

【复用完成项】
读取docs/p2/p2b-next-task-plan.md与21:57收工记录。
复用两例handoff/index/validation、M1补件/alignment/validation六工件，
三例真实TEST_ONLY回执、固定v6链、四锚点、已有p2b工具和发布白名单。
既有实现、两例索引、M1五项草稿、npm路径核对、六工件19组复核已经收口。
无新输入/缺陷时，不重新复核同一集合、重新生成索引/补件或重复跑全套测试。

【先检查新输入】
逐项检查是否收到A/保管方/Owner/前端的新资料或明确范围变更。
已有frontend-handoff-draft.json /npm路径已核，是blocked_awaiting_trusted_egress而非原始响应，
不要重复索取该文件、扩大全机搜索或索要已经取得的is-number LICENSE。
复用已有精确需求，只列真正缺失增量及责任方、字段、解除条件和解锁任务。
没有新资料或缺陷则说明当前独立范围已收口，业务PARTIAL/发布未完成，不造新任务。

【对应资料到位才续核】
1. 获准原字节：校验Hash/大小/身份/版本/指针，不能将安装副本升级为官方来源。
2. A来源receipt：验证issuer/policy/状态/不可变绑定；错绑、冲突、撤销保留，
   不接受调用者自报verified，不借另一个scan/Assessment的同名包或相同Hash。
3. commit与npm归档：核对不可变commit/blob/归档/成员/LICENSE/实际范围关系。
   元数据、归档、扫描ZIP、LICENSE、对象JSON、Result自摘要、wire Hash分开。
4. npm：只消费A受控原始回执；固定is-number@7.0.0官方精确GET，核对URL/零重定向/
   UTC/HTTP/32KiB/原字节Hash/policy/严格布尔timed_out，HTTP200不覆盖超时。
   来源字段仍按其真实等级，license声明不自动verified。
5. Evidence与coverage：校验A正式命名空间/角色/receipt/内容Hash/原子CAS/只读GET/
   Result依据引用及所有分支保留coverage/errors/gaps；不伪写旧终态ScanRun。
6. 有有效来源、充分coverage、真实用途/范围时核验is-number条件候选；不足则gap。
   保留三例21null；来源台账假设true不是实际保存用途，不能人为制造正例。
7. lodash按实际文件范围检查，根LICENSE不推广到示例/vendor/依赖；缺口不等于禁止。
8. express规则与Hash冻结做独立D4，不按该样例调参。
   比较同scan新旧Result/Material/Evidence/Summary、建议/条件与解决/新增/剩余gap，
   完整旧Assessment及原Formal单独核验，不用投影/重渲染/新版Summary代替。
9. M1先取得Owner明确续接、A旧方法映射及完整M1对象、对应人工确认；否则保持STOP。
   当前主线无capture/resolve，不自行新增路由或用B其他链补空ID。
10. 前端给最终组合、批准固定GET清单、真POST/CAS/幂等/超时/恢复与网络截图后，
    核验后端对应闭包，具体缺陷归责任方；不代签接收机或自行凑27GET。

【责任与执行边界】
A负责公共API/存储/受信来源/Evidence/运行平台；Owner或授权审核者负责真实用途/
适用性/独立履行/M1决定；前端负责浏览器真实签收；Root负责独立审核与发布。
镜像/旧报告/NOTICE任务按实际保管方与维护者归属，不默认B承担。
普通pending技术保存不强求人审肯定。unknown/rejected/pending允许如实保留。
不主动启停服务、联网抓取、安装依赖、调用模型或访问业务数据库。
产品修改必须在授权范围和仓库门禁满足后进行；不偷偷扩公共DTO/Schema、改规则或旧Formal。
stage/commit/push/merge/deploy由Root按明确范围处理，收到资料不等于取得这些权限。
已有授权有效且适用时直接按其范围继续，不重复请求许可。

【验证与收工】
只做实际增量必要验证；历史B120/前端133/build引用原回执，不称本轮实测、不加总。
Python不可用如实记录，不反复探测、不修改版本约束/断言/baseline或删测试。
Windows geteuid、NOTICE父本与当前运行时失败分别保留，不声称被Node检查关闭。
交付新增核验结果、未完成及解除条件、按责任方精确清单、已有白名单的必要增量。
不要无变化重造全部工件。按实际变更更新要求的治理记录并追加收工状态。
区分本轮范围完成、P2业务PARTIAL、独立审核未完成与发布未完成。
说明实际命令/退出码/验证等级、文件范围、风险、进度/下一步和token可获得性。
```

## 八、本次分析的验证与限制

本次核对最新日志、进度、README、Sol交接、P2合同和两组交付。复用21:57离线验收，不重复产品测试；只检查本执行计划的引用、格式和敏感模式，具体结果见本次收工记录。整份历史日志/进度虽加载，但输出截断，未满足逐字完整审阅门禁，不称全量历史审计。未启动服务、联网、访问业务数据库、调用模型或提交发布。

本次运行精确token数不可获得；开工估算4,000～8,000，实际是否在区间不可核定。

## 九、实际 npm 原件到件后的当前执行状态

本节依据原件到件收工（2026-10-12 22:27:40），更新上文21:57时点状态；前文保留历史。用户随后要求继续，先消费新增原件结果，不重复30组原字节核查。完整分项证据见 [实际原件读回](p2b-npm-original-readback.md)及[机器回执](p2b-npm-original-readback.json)。本轮只更新条件清单，不触发M1产品保存、重算或Formal迁移。

### 已解除与不能再索取的事项

| 原缺口 | 到件后结果／定位 |
|---|---|
| npm原始响应不可读 | 已取得3199 bytes原字节；/metadata 与 /acquisition_receipt/metadata |
| 精确发行包及LICENSE关系只能引用历史摘要 | 已取得3730 bytes包；metadata SHA1/SHA512 SRI、4普通成员、成员原字节一致性PASS；/tarball |
| 四锚点只有安装副本读回 | 已在实际npm发行包LICENSE原字节重核，/clauses |
| M1完整Material/Result/Binding未知 | 已取得历史r3结构化正文并复算Result canonical，/M1 |

无需再向Owner索取这10份原件、相同LICENSE地址、旧draft或重新抓取/安装。Manifest原件含Owner私有路径，仓库只使用脱敏读回；原字节与归档不随公开任务分支上传。

### M1五项补件的当前验收定位

| 补件 | B已交付的技术依据 | 仍待的人工／A工作 |
|---|---|---|
| 1 来源、producer与归属 | /metadata固定包名/版本/registry声明；/acquisition_receipt记载URL/UTC/HTTP/headers/Hash/大小；/tarball成员关系 | A正式issuer/policy/接纳状态及独立验证器；实际请求方法/最终URL/redirect/timeout未在回执明确，不由B补造 |
| 2 条款、条件、义务与反证定位 | /clauses四锚点在同LICENSE SHA上本轮实测；/tarball完整4成员未发现NOTICE | 指定审核人审完整条款和范围/条件；锚点不冒充全部条款，未发现NOTICE不等于无义务 |
| 3 同对象版本用途/范围 | /M1完整Binding、material及r3；/M1/usage七null、交付范围NOT_DECIDED保留 | Owner真实用途/实际交付文件集合及排除项；审核人适用性与履行；B不能替代人审 |
| 4 自然缺口与错版本 | /tarball/notice真实归档缺NOTICE；旧lodash范围缺口案例继续引用 | 同包另一真实版本材料仍缺；不能把合成错版或lodash跨对象误写为自然错版本 |
| 5 相对旧r3的增量 | /changes区分新增可读性/本轮字节关系验证与业务事实0；没有新Evidence或正向建议 | 正式Evidence物化与Result补证/存储由A冻结；Owner另行决定M1产品续接 |

B独立技术补件已经有精确索引可交；未获人工确认的字段不必靠反复生成文件补齐。公开签名未做密码学验签、parent excerpt完整父文件未提供等限制保留在/limits，不否定已完成的原字节一致性核对。

### 现有九项任务的当前条件

| 任务 | 当前可判定状态 | 仍需的最小增量／责任方 |
|---|---|---|
| T1到件核对 | 本批到件30组PASS，独立范围收口 | 仅真实新增资料/差异触发续核，B不再泛称原件未取得 |
| T2 npm核对 | 原字节/精确身份/发行包关系已核；受信DTO未完成 | A受控接纳回执及缺method/final URL/redirect/timeout/policy/验证器，不重新索原文 |
| T3来源/包关系 | 精确npm包成员关系PASS；正式来源/实际范围仍待 | A签发与scope绑定；不可变Git关系仅在对应主张需要时验，不把Git commit强加为所有npm原字节核验前提 |
| T4真实用途候选 | 尚未具备真实正向候选；旧三例与M1分开 | Owner真实用途和分发范围、指定审核、A可引用Evidence/coverage；B不能补null为true |
| T5 lodash范围 | 原范围缺口未由is-number原件解除 | Owner/A提供lodash实际文件集合及许可范围关系 |
| T6 M1产品续接 | 完整历史Material/Result/Binding已到，其他门禁仍待 | Owner明确M1产品续接及A实际方法/DTO/事务映射；普通“继续任务”本轮用于限定技术交接，不自建路由或触发产品保存 |
| T7 D4对账 | 只有旧r3，无同链新Evidence/Result和完整旧Formal | A正式Evidence/CAS/basis/存储及同scan前后完整闭包；来源技术核对不等于新业务事实 |
| T8接收机 | 2个M1对象静态接受已通过，无live验证 | 前端/A获准最终组合、固定GET清单及真POST/CAS/恢复网络回执 |
| T9发布 | 新脱敏读回本地，发布权限未新增 | Root独立审核及现有明确发布范围；本轮不stage/commit/push |

### M1审核人可以直接使用的固定对象

- Scan：scn_fb8856de-91c3-41b7-b758-fcf35c2ea77d；资源：cmp_1fc87b46-9132-51b6-b39e-bf1af669ca8a@7.0.0。
- Assessment：asm_6c664ed7-7c41-512c-bbcc-a178a8edea79 v1；完整facts_hash/usage_hash/父rule_version/assessment_sha256见机器回执/M1/binding。
- Material：p2mat_c5090e4fd86a58311fab75962e7d545057d2e8b028c358d467f764b225e0c61b revision1；LICENSE SHA256 35bdd8a44339719441900fb50fbefc5e2dca1ca662cbaed7a687de842c8b70f2。
- Result：p2res_eabfaa020c8a91cd4a5a309861ad4f0ab90cae07263d4ac48370b8a02b89fc83 revision3；SHA256 00c297c662b1ad5efadbc6e92fe2d2401a6b53d555013c497427457ce74a7dca。
- 人审原件：human-review-pending-is-number.json，/reviewer、/reviewed_at、/scope为空，/conclusion=PENDING_HUMAN_REVIEW；只作为既有原件，不提供自动签署入口。
- 核验事项：实际软件文件/版本与适用范围；真实商业/修改/分发/网络服务/训练/素材再分发/源码公开用途；交付资源集合和排除项；版权/许可声明保留及其他条件的履行凭据。未知可以继续pending，审查可以拒绝，不保证正向结论。

已经向当前用户询问真实用途、交付范围及指定审核人，答复未到时不代填。来源签发、Owner范围、人审、履行、产品签收互相独立。固定GET只列出既有合同路径，未执行live GET；Answer/Summary只有引用ID，仍需其原正文，不能用新渲染替代。

当前独立核对与技术交接范围已完成。后续只有真正新增A/Owner/审核人/前端资料或明确改变执行范围才继续相应动作；P2整体PARTIAL，源码/Schema/规则/旧回执均不变。

### 用户对用途、交付范围及审核人的明确答复

2026-10-12，用户已答复之前的三项询问；不再标记为“用户尚未答复”，也不反复询问同一内容。答复作为USER_CHAT_STATEMENT记录，未写入Formal或P2业务对象。

| 项目 | 用户明确答复 | 对M1保存状态的影响 |
|---|---|---|
| 实际用途 | 仓库中用于扫描识别、npm元数据及许可证材料的测试／演示；M1自身具体用途尚未确认 | 保留七项用途全部null；测试演示角色不能推导商业/修改/分发等七项值 |
| 随作品交付范围 | 当前仓库包含依赖声明、测试及校验代码，未发现对应包源码目录或发行包；最终交付范围尚未确认 | M1保持NOT_DECIDED；此处仓库观察不等于最终镜像/基础工具/作品交付清单完整检查 |
| Owner指定审核人 | 尚无可核实指定人选；reviewer=null；“cz／授权审核者”只是责任描述 | 不创建审核身份、签认或许可verified；reviewed_at/scope继续为空 |

该答复与已有 [M1三项自动证据核查](m1-automated-confirmation-20261012.md) 的技术边界一致；本轮不重跑其16组检查或把用户陈述计作独立审计。后续只接收真正新增的M1用途/输入关联、最终交付manifest/SBOM/排除项，以及Owner真实审核任命和审核结果。可以继续pending/unknown或拒绝；不为形成正例强行提升状态。原先七用途及材料/Result/人审JSON、事实Hash、用途Hash均不修改。

## 十、2026-10-12 当前用户请求：P2全景与B任务分工

本节按现行P2 v1合同、当前源码和最新交接分析，不改变公共合同或任务授权。优先级：本节及第九节的到件/用户答复更新优先于前文历史“npm原件未到”等描述。完整大历史输出截断，已经全文件机器检索并核对相关章节，但未满足逐字完整历史审阅；本次是限定P2分析，不是全仓最终审计。

### 10.1 当前P2究竟要交付什么

早期路线图的“更多生态、兼容矩阵、自动PR、私有仓库、高级协作”与当前P2 L1/L2工作不是同一份执行范围。本次以[现行合同](../spec/p2-backend-contract.md)为准，不把早期扩展路线图转成B本轮任务。

当前产品闭环为：固定Scan和Assessment绑定 → 独立L1候选/缺口 → L2资源子集回答或LICENSE/NOTICE观察 → 服务端原子生成下一Result revision → 同版Summary及历史精确读回 → 前端真实展示和接收验收。

- L1：现行正常工厂调用确定性B候选逻辑，不是旧R6两问、离线Qwen L1或正式授权结论。
- L2：交付范围/履行回答与小材料保存；回答只属于显式资源子集，不自动改变七用途或Formal。
- 版本：Result revision推进，Assessment version保持父流程既有版本。Summary是P2伴随摘要，不是旧Formal Report。
- 信任：材料字节一致、npm声明、来源接纳、范围适用性、履行、产品签收是独立环节；HTTP201只证明保存。
- 历史：旧Result、Material、Evidence及旧Formal均需保留；新来源/撤销状态不能改写旧字节。

### 10.2 已有成果，不应重新开发

| 模块 | 已有实现/证据 | 仍未证明的部分 |
|---|---|---|
| B L1 | backend/app/p2b/candidates.py；精确对象/版本/用途pin、Evidence闭包、冲突和unknown判断、V4-MIT有限矩阵 | A真实受信来源和人工适用性转为有效输入；真实受支持用途候选 |
| B材料 | materials.py、offline_material_audit.py；64KiB UTF-8、Hash/身份、重复与冲突、条款定位 | 保存后不代表正式来源/适用性已核验 |
| B npm | npm_metadata.py；固定is-number@7.0.0、32KiB、严格JSON、Hash与A attestation适配 | A受控签发/验证器和正式业务绑定；禁止用合成lambda返回True替代 |
| B对账 | reconcile.py；同scan对象前后比较、依据/条件/缺口变化、旧工件pin | 同链新Evidence/Result以及完整旧Formal实证 |
| A服务端 | backend/app/p2/和backend/app/api/p2.py；正常工厂、私有p2.db、同步201、CAS、幂等、只读GET、Summary事务 | 来源/Evidence新策略、目标平台/接收根、正式生产批准 |
| 前端 | P2AdvicePanel.tsx、p2Advice.ts、p2Workflow.ts；已合入当前集成线 | 目标机真实网络/浏览器/写入/刷新恢复签收；未决请求仅内存 |
| 三例与v6 | 已有真实TEST_ONLY回执、完整ID/精确路径、材料与Result链 | 真实三例21项用途null、扫描partial及来源/范围门槛未关闭 |
| 新npm/M1资料 | p2b-npm-original-readback.md/.json，历史30组核对PASS；npm响应/归档/成员与M1完整Binding/Material/r3已到 | M1 Answer/Summary完整正文、A正式接纳、用途/交付范围/真实审核者及产品续接 |

以上测试及HTTP数字是历史回执，本次不重跑、不加总。当前Python不可用和Windows权限/NOTICE父本/baseline失败不被Node或文档检查关闭。

### 10.3 B任务：现在做什么，收到什么才能继续

下面W编号仅为本分析的工作包，不是新API字段，不替换原T1—T9或A编号。

| 工作包 | B要做的事和交付 | 现在是否能做 | 需要什么才能关闭 |
|---|---|---|---|
| W1 当前交接维护 | 引用已有两例/M1/原件读回，分项列已收、缺失、责任、解除条件；只核真实增量 | 可以；当前大部分已收口，不重复生成同义索引 | 新资料或明确差异才续核；无变化说明PARTIAL原因 |
| W2 来源接纳核验 | 校验A签发者/策略/不可变receipt、状态、Binding、对象版本和原文Hash；检查错绑/冲突/撤销不提升 | 已有提案和离线逻辑；正式验收等A | A受信合同及签发/GET/验证器，不接受调用方自报verified |
| W3 npm正式观察 | 复用已到3199bytes响应/3730bytes发行包/1091bytes LICENSE关系；对A缺失传输字段及DTO做增量核验 | 原字节范围完成；正式观察等A | 实际method/final URL/redirect/timed_out/policy/验证器与接纳；无法补回历史字段则如实保留缺口，由A决定是否需新受控获取 |
| W4 真实条件候选 | is-number按同对象有效Evidence、充分扫描覆盖、真实显式用途和人工范围产生条件候选，或输出具体gap | 当前不能声称已具备；合成正例已有 | A正式Evidence/coverage；Owner实际用途/交付文件集合；指定审核者适用性。无需七项都填满，仅支持用途中的真实true及其前提齐备才验 |
| W5 范围缺口样例 | lodash逐文件/子资源识别根许可边界、排除项、依据和未知；缺口不等于禁止 | 现有缺口交接可用；真实范围核验待资料 | Owner/A实际文件集合和不同范围的许可关系；不得借is-number包解除lodash缺口 |
| W6 D4增量对账 | express规则冻结、不用于调参；比较同scan前后依据、候选/条件和解决/新增/剩余gap、未受影响资源及旧版本 | 工具已有；真实闭环待A | A同链新Evidence/Material/Answer/Result/Summary正文、完整旧Assessment/Formal原字节与固定GET、运行范围 |
| W7 M1条件续接 | 复用M1完整r3，补真正缺失项后核对，获准才产品保存/重算；不可跨scan借ID | 技术补件完成；产品保持STOP | Owner明确M1续接；A当前方法/DTO/事务映射；必要用途/范围/审核。主线无capture/resolve，不自建旧路由 |
| W8 接收联调协助 | 为前端提供既有完整ID/JSON Pointer/期望状态；收到实际网络回执后核对B语义和具体缺陷 | 已有静态交接现在可用；live等A/前端 | 最终兼容SHA/Schema/支持环境/获准固定对象；前端真实GET/POST/CAS/幂等/错误/刷新回执 |
| W9 实际变更验证 | 有B缺陷或正式输入变化才运行对应有效测试、补文档/AI/资源记录 | 具体增量到位可做；不为文档无变化复跑 | 支持Python3.12环境；A/环境方处理平台问题，失败分层记录 |
| W10 发布交接 | 交Root必要文件白名单、实际验证、风险和剩余门禁 | 可以准备；现有白名单可复用 | Root独立审核及适用发布授权；只发布作品必要文件，不含原件/DB/归档/私有路径 |

不能把W2—W8所有资料合成一个“整包必须先到”的开工门禁。单项到件就完成该项不依赖缺件的核验。普通pending保存不强求肯定人审；高信任候选和M1单独停止点分别遵循自己的条件。

### 10.4 后端A、前端及Owner的最小补件清单

| 提供方 | 当前真正需要的增量 | 解锁B工作 |
|---|---|---|
| A | 受信来源receipt_id/version/hash、issuer、policy/version、UTC及accepted/rejected/conflict/revoked状态；完整Binding、scan/resource/npm名/精确版本、原文Hash/size和只读GET | W2/W4/W6 |
| A | npm获取缺method/final URL/redirect_count/timed_out/policy/验证器及正式observation DTO。不要重索已到原件或编造丢失字段 | W3 |
| A | 新license_text/scope_attestation Evidence正式命名空间/引用receipt/内容Hash与记录Hash区分、不可变GET、basis闭包、原子CAS策略；所有分支status/errors/coverage/gaps传播 | W4/W6；终态ScanRun不由B补写 |
| A/原件保管方 | 同链新旧Result及所需Answer/Summary完整正文；完整原Assessment和旧Formal ID/格式/原字节Hash/固定GET | W6/W7/W8；只给ID或投影不能代替正文 |
| A/环境维护者 | 最终backend/frontend SHA、Schema ID/Hash、支持平台/锁定镜像digest及获准TEST_ONLY根/manifest；旧M1操作到现行路由/Service/Store的实际映射 | W7/W8/W9；不把旧Compose当已批准环境 |
| 前端 | 同对象精确GET、材料/回答POST201+读回、双会话CAS409、原键原body重放/改body409、超时先查后重放、旧新版/同版Summary/状态缺口依据、刷新和重启网络/截图 | W8真实签收；缺固定27GET清单不凑数 |
| Owner/交付维护者 | M1精确输入和用途关联、实际交付manifest/SBOM/文件集合与排除项、用途pin、产品续接范围 | W4/W5/W7；现有“测试演示”声明不替代M1七用途 |
| Owner指定审核者 | 可核实任命；引用来源receipt/原文Hash/对象版本/范围的适用性审核及独立履行记录 | W4/W5/W7；允许pending/unknown/rejected，B不代签 |
| Root | 独立验收、白名单/敏感检查和授权范围内提交推送/PR治理 | W10；功能分支不等于main或部署 |

B不是A公共API/sidecar架构、受信出口/签发、前端浏览器验收、Owner用途/人审或Java核心迁移的默认主责。发现这些缺陷，给精确定位与回归建议；跨职责变更写明影响并由对应维护方复核。

### 10.5 两个需要A优先处理的源码事实

1. backend/app/p2/service.py的candidate()始终保留upstream_source_attestation_missing，现有P0人审flag不构成P2B上游许可/适用性证明。来源与新Evidence正式接纳由A闭合，B不能删除缺口制造正例。
2. 同函数仅部分路径调用evaluate_bound_candidate并传播run.errors；其他提前返回需要A明确coverage/errors/gaps的完整保留策略。前端P2WriteAttempt的未决请求只保存在内存，刷新后原请求恢复不能据现有实现直接宣称已完成；若需产品支持，交前端与A确定方案后针对性验证。

这些是接纳设计和验收关注点，本次不改代码，不声称发现了新的运行回归。

### 10.6 给后端B Codex的最新中文指令

```text
你是OpenGuard后端B。使用简体中文，每次回复称呼用户为【宇宙无敌聪明的帅哥】。
任务是按实际到件推进P2的B职责，不重新开发已经存在的L1/L2/npm/D4模块。

一、开工与范围
遵守根AGENTS，按顺序阅读README、完整工作日志、进度及对应模型交接，再检查Git和在途文件，追加START。大文件分段读，若未完整审阅必须如实记录，不能以机器读过代替语义审阅或冒称已满足门禁。
读docs/spec/p2-backend-contract.md、schemas/p2/contract-v1.schema.json和docs/p2/p2b-next-task-plan.md第九、十节。旧章节由最新增量更正；使用实际HEAD，不退回历史SHA。
本轮先完成现有授权内的只读/离线增量核验。用户已有授权在适用范围内继续有效，不反复问许可；服务启停仍须用户明确要求。保持P1及用户未提交修改，共享治理只追加。

二、复用已有交付
复用backend/app/p2b/candidates.py、materials.py、npm_metadata.py、reconcile.py和offline_material_audit.py；A的backend/app/p2/及前端P2工作台已经存在。
复用两例handoff/index/validation、M1技术补件/alignment/validation、p2b-evidence-closure.json、three-scan-readback.json、固定v6回执及现有发布白名单。
特别阅读p2b-npm-original-readback.md/.json和m1-automated-confirmation-20261012.md：npm十原件已到，元数据/精确发行包/成员LICENSE关系及M1完整Binding/Material/r3已核。不要再索取同批原件、重抓npm、重新找LICENSE或重做30组/19组/16组检查。Answer/Summary只有ID时正文仍缺，不能假称全闭包到件。
用户已经回答用途/范围/审核者问题：仓库用于测试演示，M1真实七用途未确认、最终交付NOT_DECIDED、审核人未任命。不要反复问原问题，不自动补null或人审签认。

三、按资料逐项执行
1. 有新A receipt：核对issuer/policy/版本/不可变Hash/状态及同scan-resource-version-Binding-原文Hash。错绑、冲突、撤销和缺失失败关闭；自报verified或合成验证器不是可信接纳。
2. 有A npm DTO/真实传输补件：只补核method、固定request/final URL、redirect_count=0、UTC、HTTP、显式严格布尔timed_out、32KiB、原字节Hash/size、policy和受控验证器。不能凭HTTP200覆盖超时；缺失字段不猜。官方license仍provider_declared_unverified。
3. 有新Evidence/coverage：核对正式命名空间、license_text/scope_attestation角色、receipt引用、source/content/记录Hash语义、只读GET、Result basis引用和CAS；核对所有分支保留扫描partial/errors/gaps，不往旧终态ScanRun伪写。
4. 来源/Evidence/充分覆盖及真实用途/范围到位：用既有evaluate_bound_candidate核验is-number有限条件候选。只有当前矩阵支持用途中的真实true才可能产生候选，未知保持null，false是未选，training/source_disclosure超矩阵保留gap。没有足够事实则交最接近真实案例和精确缺口，不凑正例。
5. 有lodash实际文件集合：核对根许可适用范围、例子/vendor/依赖的独立关系与排除项。缺口不等于禁止，不借is-number材料补对象。
6. 有同链前后对象及完整旧Formal：冻结规则/Hash，以express独立D4比较依据新增/变化、建议新增/删除/条件变化、解决/新增/剩余gap、未受影响资源及旧对象Hash。不要修改旧Evidence；撤销以正式新状态表达。既有reconcile_object以追加证据场景为边界，不能静默放宽为删除历史。
7. M1单独检查Owner明确产品续接和A现行方法/DTO/事务映射、必要范围/审核资料。未到位保持STOP；M1与旧三例不是同scan。主线没有capture/resolve，不自行创建旧路由。
8. 为前端提供完整ID/assessment_version/result_revision、Hash、JSON Pointer及期望状态。收到真实GET/POST/CAS/幂等/超时/刷新网络回执再核B输出。前端负责浏览器签收；静态JSON接受不代签接收机。精确404不回退latest，Summary不代Formal，27GET仅以批准清单为准。
每项只等自己的必要输入，到件即完成该项可做核验，不等待A01—A09整包；无新事实/具体缺陷时不生成同义工件或重复测试。

四、修改与验证
只在现有授权和开工门禁满足后修改B维护模块的具体缺陷；公共API/Schema/存储/可信签发/平台由A维护，前端缺陷交前端。跨职责修改说明影响并指定复核方。
代码变更按影响选择tests/unit/test_p2b_candidates.py、test_p2b_receipt_closure.py、test_p2b_offline_material_audit.py、test_p2b_three_scan_readback.py；影响A接线再运行test_p2_contract.py及相关集成项。使用受支持Python3.12；环境不可用如实分层记录，不削弱约束/断言或把Node检查称pytest通过。
无代码变更不重复历史120/133/build。NOTICE父本、Windows权限、baseline与当前解释器失败分别保留，不默认要求B安装或代修。
不执行被扫描项目代码、不安装目标依赖。未授权不进行网络抓取、业务数据库写入、模型调用或部署。普通pending保存不强求肯定人审，来源/适用性/履行仍分别核验。

五、交付与收工
优先增量补现有计划/交接。输出每项当前状态、实际新增证据、精确定位、检查方法/退出码、缺失字段/责任方/解除条件；没有新补件说明独立范围已收口而P2仍PARTIAL。
执行必要diff/敏感检查，按需更新AI记录、资源台账和进度，日志追加COMPLETE/PARTIAL/BLOCKED；分析完成不等于业务完成，完整历史阅读限制保留。
Root复用既有白名单独立验收和发布；B不自行stage/commit/push/merge/deploy。原件、DB、归档、第三方全文、私有路径和个人信息不进入公开提交。
报告本轮/累计/未完成、责任、验证、GitHub状态、下一步，分别说明独立演示/完整作品/竞争力门禁。精确token不可获得时写明，并给估算区间，不能伪造精确消耗或完成百分比。
```

### 10.7 推荐排期和验收分层

第一轮：B直接交现有精确索引给A/前端/Owner，并按本表确认新到件；A来源接纳/Evidence/coverage与Owner用途/范围/审核任命并行。没有新资料时B不追加重复工作。

第二轮：对应资料齐备的资源先验真实候选/缺口/正式npm观察；另一缺件资源继续pending，不阻断已齐备者。A准备同链旧新对象与完整Formal，B做D4。

第三轮：A与前端在已获准环境进行真实读写、冲突、超时读回、旧版/同版Summary和刷新/重启，B核语义和证据；Root独立验收并按授权发布。

验收分为：模块与离线核验、真实业务来源闭环、跨栈接收、独立审核与GitHub发布，不能互相替代。当前可独立复核离线原件/条款/绑定与前端静态交互；扫描/报告可演示依据支持环境历史回执，本机当前全栈未复验。尚缺新可信真实条件候选、完整旧Formal和跨栈真实签收。

资格权利/目标机复现/可运行Java核心是可参赛项目门禁；真实闭环/独立审核/发布及匿名报告视频资源AI材料是完整作品门禁；真人Gold、新holdout、对比消融和可信质量性能是竞争力门禁。以上是当前台账待验证项，不代官方最终规则审查，无分母权重不报百分比。
