# P2 B 当前状态与条件任务复核（2026-10-11）

整体 **PARTIAL**；限定 TEST_ONLY 离线工作获准，发布、生产、联网、正式模型、服务启停、
公共 Schema/Formal 修改、提交推送、合并与部署未获授权。

## 已有成果与本轮结果

七文件交付已存在，未重复实现，也未新增测试。本轮复算原 validation 清单中六工件的
原字节 SHA-256/大小并全部匹配，单独记录第七份 validation 自身摘要；既有 CLI 本轮实际
运行，三例输出与已保存 `p2b-offline-material-audit.json` 一致。现有 Material/Result DTO、
Result 自摘要、原 Result pin、父 Binding、资源版本、引用闭包和用途原值校验继续复用。

120 passed、2 条已有警告是上一轮的历史组合验收，90 是其子集。本轮源码没有改变，
没有重复跑 pytest，也不称本轮 120 passed。新增事实、Evidence、正向许可建议仍为 0，
三例七用途共 21 个 null 保持原值，材料继续 pending/user_supplied_unverified。

本轮新增：本状态说明、机器外部依赖清单、状态验证证据和日期明确的文档更正。
源码、冻结输入、旧 Result/Material、七文件交付、P1 B03 与 P1 离线审计均保护。

## 已取得的原件与可读取位置

`is-number@7.0.0` LICENSE 原件已取得。既有记录说明完整字节保存于运行者指定的隔离
P2 数据根，但公开回执未给出该数据根或获准读取方式。不得把元数据 GET 误当正文 GET。
本轮查阅来源记录及已有本地忽略资料，以 1091 字节大小过滤后复算候选 SHA-256，未找到
摘要匹配的原字节；未读取系统账户、其他会话、容器或业务数据库，未联网。

已在当前用户对话提出精确请求：请原件保管方提供**已有原件的获准读取位置或只读方式**，
不用重新上传或抓取正文。请求待回复时，其他离线复核继续。三例本轮仍 metadata_only，
条款 bytes_not_re_read；条款定位功能的历史合成验证不代替真实原件重读。

收到获准原字节后，B 使用现有 CLI 的 `--is-number-license`，先校验：

- SHA-256：`35bdd8a44339719441900fb50fbefc5e2dca1ca662cbaed7a687de842c8b70f2`；
- byte_count：`1091`；Git blob SHA-1：`9af4a67d206f24ecdbb5fdff2839041ca0bbd346`；
- subject：三例清单中 is-number 的原 resource ID / `7.0.0` 和父 Binding。

仅匹配字节才定位四个文本锚点的 byte/line，missing/ambiguous 如实记录；摘要或身份不匹配
即停止该原件核验并保留错误。不导出正文，不补 Evidence，不提升来源等级，不形成授权。

## 历史口径更正

| 历史资料/描述 | 当前口径 | 保留边界 |
|---|---|---|
| `docs/spec/p2b-independent-preparation.md` 2026-10-08章节“三例身份为空” | 2026-10-10 已有三例真实 TEST_ONLY scan/resource/Evidence/Assessment/Material/Result/summary 身份和精确路径 | 只扫描受控第一方 manifest，未证明实际 npm 安装或发布包适用性 |
| `docs/p2/stage1-review.md` 历史“cz三例仍无真实Scan/Evidence绑定” | 以上三例回执已取得，原句是 A 阶段1历史时点 | A 原审查与 HTTP 回执不改写；来源签发等门禁仍缺 |
| 旧审查“90 passed” | 20:42 最新离线组合历史验收是 120，含原90；本轮未重跑 | 不将两次测试相加或称本轮实测 |
| 基线/合同尚未冻结，所有A交付都须先到位 | Owner已允许指定A P2 v1合同/Schema用于限定离线工作，A01—A09全部完成不是开工条件 | 不等于完整 Owner Review、生产批准、正式新DTO或可信签发 |
| 来源提案要求真实显式true情形 | 这是证据齐备后可验证条件候选的条件任务 | 不要求Owner人为肯定，不将任何null改为true/false |
| 三例來源索引中的设想用途 | 不是A实际保存用途；实际七字段以原 Result/usage_hash 为准 | 三例全null，本轮0新正向结论 |

更正只追加当前日期说明与共享日志 AMENDMENT，未重写旧结果或历史验证回执。

## 任务分层与外部依赖

下表的“缺失”表示当前仓库未见相应正式签发/批准/接收回执，不代表责任方私下没有资料。
完整字段请求、解除条件、可解锁任务见 `p2b-external-dependencies.json`；字段是交接需求，
不是新增公共 P2 DTO。已有详细 A 字段清单继续见 `p2b-a-handoff-requirements.md`。

| 分类 / ID | 当前状态 | 责任方与精确请求 | 解除条件 / 可解锁任务 |
|---|---|---|---|
| 已收尾 / A | 指定合同、Schema和实现已有；仅离线范围获准 | A/Owner：继续复用afca4c2/P2 v1，不重复要求全合同重交 | 当前离线兼容核对可做；新增DTO/生产另行审批 |
| 现在可做 / BYTES | 原件已取得，获准位置未知；已请求 | 原件保管方：本地读取位置或获准只读方式、访问范围、原对象版本/Hash | 仅原字节核验与条款定位；不解锁来源等级/正向结论 |
| 依赖A / B | 可信来源回执未见 | A：不可变receipt ID/version/hash、受信issuer/policy、UTC/状态、父Binding/对象绑定、精确GET | 受信路径与Hash/身份通过后做来源接纳负例；B不代签 |
| 依赖A / C | commit与npm发布内容关系未签 | A：固定commit、文件/blob/字节Hash、发布归档digest/清单及LICENSE与范围关系、排除项 | 验证来源与包的精确关系，仍需Owner范围与履行 |
| 依赖A / D | 新Evidence正式闭环未见 | A：命名空间/角色、来源与内容Hash、receipt引用、只读GET、Result basis闭包与原子存储策略 | 新依据对账、错绑/撤销/冲突/CAS验证；旧ScanRun不伪写 |
| 依赖A / E | coverage/规则溯源缺口仍在 | A：status/errors/coverage到Result的映射、父Formal规则与B候选规则独立pin | 检查提前返回仍保留扫描缺口、规则版本追溯 |
| 依赖A / F | npm DTO/正式接线与真实获取未交 | A：DTO及受控验证器，显式timed_out、固定GET/final URL/零重定向/UTC/HTTP/大小Hash/policy | 有相应执行授权后A唯一获取；B校验HTTP200不能覆盖超时 |
| 依赖A / G | 旧完整Formal读回未交 | A：完整Assessment序列化/Hash及Report原字节/格式/Hash、固定版本GET | 才能关闭完整历史Formal读回门禁；Summary不可代替 |
| 依赖A / H | 获准接收环境与固定对象未签 | A/Owner：兼容SHA、TEST_ONLY只读包或数据根、固定ID/Hash及支持平台 | 有执行授权后读回/失败恢复/跨平台；本轮不启服务 |
| 依赖Owner / OWNER | 真实用途/交付/范围/适用性/履行未签 | Owner：真实七字段与用途pin、资源/文件集合和排除项、引用A有效来源及原文Hash的独立决策 | 可保持未知/拒绝；不必产生肯定结论，不代填 |
| 依赖前端 / FRONTEND | 正式接收机签收未交 | 前端：前后端SHA/Schema映射、获准同对象精确GET、状态/依据/旧新版/Summary展示及错误网络截图 | 真实接收机验收后正式产品签收；B静态JSON不代签 |
| 依赖Root / RELEASE | 新七文件与本轮文档均本地未发布 | Owner批准发布，Root按白名单独立审核、必要门禁和范围复核 | 之后才可stage/commit/push；本次不执行 |

A02/A03/A05 的正式证据、来源和存储工作包保持独立，本表不代 A 重划编号。
精确 is-number、lodash、express 身份和 GET 路径保存在机器清单的 `fixed_cases` 中。

## 建议顺序与验收边界

1. 原件保管方回填读取方式，B仅核对已有字节及文本定位；Owner复核本轮交付。
2. A并行交付B/C/D/E/G/H的正式闭环；Owner独立确认真实用途与范围，保持未知原值。
3. F仅在联网授权与A受控实现到位后执行唯一npm GET；本轮不执行。
4. 对应证据、充分覆盖、真实用途和执行授权齐备时，B按三例分别做条件候选/范围负例/D4；
   express冻结规则及Hash、不调参。不足继续输出gap，不保证或要求出现肯定结论。
5. 前端在获准环境做对象/版本/Hash和错误实测；Root在单独获授权后审核发布。

本轮只做离线复核；旧Windows `os.geteuid`、NOTICE父本失败与baseline FIXTURE_DRIFT
仍独立保留，未重跑或关闭。既有已发布成果以历史e891d26/da142ea/bed87f5记录为准，
未在线核验远端；最新七文件和本轮成果本地未提交。当前完整日志的逐字阅读门禁仍因
巨大输出未满足，读取范围与限制记入验证回执，未冒称流程完全满足。

## 2026-10-11 本地查找后续：is-number匹配字节已可读

用户要求查询本地代码后，在本地已安装工具的依赖目录找到is-number@7.0.0。LICENSE大小/SHA-256/Git blob SHA-1全部匹配上述历史值，已用现有CLI只读定位四个唯一文本锚点，脱敏结果见p2b-isnumber-clause-readback.json。本机地址只向用户提供，不进入公开文档。上文及旧验证文件的metadata_only/未找到描述是此前范围/时点，本次只解除is-number字节读取和文本定位停止点，不重写旧回执，不证明原私有存储位置或受信签发、发布包关系、适用性/履行。七null和新增事实/Evidence/正向建议0保留，其他两例未重读，整体PARTIAL。

## 2026-10-11 接续任务最新交接入口

本轮独立复核实际LICENSE四条byte/line及唯一性，现有CLI和旧真实readback相等，7原工件未变。BYTES读取定位已收尾，无需继续索取is-number原件/地址。最新当前口径以p2b-readback-review.md及p2b-external-dependencies-readback.json（revision2，旧清单Hash关联）为准，证据p2b-readback-validation.json。12条目中A仅离线可用、BYTES仅本机匹配字节定位完成，其余10项正式门禁保留，三例21null和pending/新增事实Evidence正向建议0不变。旧JSON仍是历史快照，不改写。下一步A与Owner并行补正式来源/范围/存储/旧Formal，npm/前端/发布需各自执行授权，整体PARTIAL；本轮无源码变更和pytest重跑。
