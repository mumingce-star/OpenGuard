# P2 B 匹配原字节接续验收（2026-10-11）

整体 **PARTIAL**，Owner待复核，未授发布权。最新指令继续限定 TEST_ONLY 离线。
基线为A `afca4c26c2fa45fa285fc9cabf48f52c54a59229` 的P2 v1合同/Schema，
不要求A01—A09全部完成才开工；正式签发、范围、Evidence、npm、旧Formal和前端各自独立。

## 已有成果直接复用

原七文件、三例完整TEST_ONLY身份与精确GET、闭包核对器、30项材料负例及旧90项回归
均已交付。120 passed/2 warnings为20:42历史实测，本轮没有源码变更，不重复执行pytest。
23:12已完成本地is-number@7.0.0匹配LICENSE字节定位，该回执也复用，不重造Material、
Result、Evidence或扫描。私有本机路径仅在用户对话给出，公开资料不保存路径/正文/数据库。

## 本轮实际复核与条款映射

本轮重新只读核验package name/version与LICENSE：1091字节、SHA-256
`35bdd8a44339719441900fb50fbefc5e2dca1ca662cbaed7a687de842c8b70f2`、
Git blob SHA-1 `9af4a67d206f24ecdbb5fdff2839041ca0bbd346`均匹配旧记录。
用已保存locator直接切片原字节，独立复算行号和锚点唯一性，不调用helper来生成预期。
现有CLI带匹配字节的结果与`p2b-isnumber-clause-readback.json`中的audit相同；
原closure CLI输出与保存JSON相同，原七工件摘要/大小匹配，DTO/Schema/Result自Hash/
父Binding/版本/材料与Evidence引用/用途pin保持一致。

字节区间是**零基、左闭右开**；行号从1开始，按原字节LF计数。

| 文本主题 | 原字节区间 | 原文行号 | 定位结果 | 可作的映射与边界 |
|---|---|---|---|---|
| 许可语句锚点 | `[68,112)` | 5 | 唯一anchor_observed | 仅定位许可语句文字，不证明整个安装包或实际交付对象适用 |
| 版权与许可声明保留锚点 | `[502,573)` | 12 | 唯一anchor_observed | 作为保留声明条件的待复核定位；Owner仍需确认副本范围和实际履行 |
| 免责声明锚点 | `[630,662)` | 15 | 唯一anchor_observed | 仅定位免责文字，不产生授权通过或履行完成状态 |
| 责任限制锚点 | `[832,892)` | 17–18 | 唯一anchor_observed | 跨行字节及行号直接复核通过；不替代完整许可与范围审查 |

四锚点没有missing/ambiguous；合成负例既有测试仍覆盖这两种情况。本轮没用模板或
合成内容替代真实字节，也不输出第三方全文。匹配的是本地已安装副本的LICENSE，
字节相同不证明旧P2私有sidecar位置、受信签发者、不可变commit、npm发布归档或文件范围。
根文件的文字不能自动推广到其他依赖/vendor，也不能推断NOTICE不存在或不需要。

Material继续`pending/user_supplied_unverified`，Result与Formal不改，新增事实/
Evidence/正向建议都是0；三例21个null保持原值。lodash和express本轮仍metadata_only，
没有对express改规则或调参。完整旧Formal正文未取得，不宣称该门禁通过。

## 最新依赖快照与已关闭项

[最新机器清单](p2b-external-dependencies-readback.json)从旧清单派生为revision 2，
保存旧清单Hash与readback证据Hash，不覆盖历史JSON。12个条目中：A仅限定离线可用；
BYTES仅is-number匹配字节读取/条款定位已收尾；其余10项正式门禁继续保留。
因此无需再次向Owner/保管方索要is-number原件或读取地址。

| 任务层 | 当前状态 | 责任方 / 解除条件 / 可解锁任务 |
|---|---|---|
| 当前离线：7工件、真实条款、闭包与状态对账 | 已收尾 | B实际复核；Owner复核交付即可，不因此启生产或签发来源 |
| A-B/C | 受信来源/不可变commit/npm内容关系未签 | A提供receipt ID/version/hash、issuer/policy/UTC/状态、精确GET与对象Binding；提供commit/blob/归档和文件Hash关系后，B做来源/范围负例 |
| A-D/E | 新Evidence闭环/coverage与规则溯源未交 | A冻结Evidence命名空间、角色、摘要、receipt引用/GET/Result basis原子闭包；传播errors/gaps及独立规则pin后，B做错绑/冲突/撤销/CAS对账 |
| A-F | 正式npm DTO/接线与真实获取未交 | A提供显式timed_out及受控验证；另获联网权后A唯一GET指定is-number/7.0.0，B检查HTTP/URL/零重定向/UTC/大小Hash，license仍声明未核验 |
| A-G/H | 完整旧Formal读回/获准固定环境未交 | A提供旧Assessment确切正文序列化Hash、Report原字节/Hash/固定GET及兼容SHA/平台/固定对象；获执行授权后验收读回与恢复 |
| Owner | 真实用途、交付集合、范围/排除项、适用性和履行未签 | Owner独立确认并引用A有效来源/原文Hash；可以未知或拒绝，不要求人为true/肯定结论 |
| 前端 | 正式接收机签收未交 | 前端以同SHA/合同/对象/版本/Hash验证展示、旧新版/Summary/Formal区分、404/409/422/503、超时/CAS/幂等及脱敏截图网络记录 |
| 发布 | 未授权 | Owner另授发布权；Root独立审核源码/测试/材料白名单及相关门禁后处理，不自动合并/部署 |

A02/A03/A05正式证据、来源、存储闭环不因本地字节匹配关闭。精确字段、负责方、
解除条件、可解锁任务、执行权限与三例全部固定路径继续保存在最新机器清单，
没有向严格P2 v1 DTO偷偷加字段或由B代签A/Owner。

## 当前可交付范围与下一步

本轮新增本说明、revision 2依赖清单和`p2b-readback-validation.json`；旧七文件及
`p2b-isnumber-clause-readback.json`保留。Root可将这些源码/测试/脱敏文档列入后续
审核白名单；本轮不stage/commit/push/PR/merge/deploy，完整正文/私有路径/缓存/数据库
均排除。P1 B03/P1离线审计与用户文件保持独立。

下一步由A并行补B/C/D/E/G/H，Owner独立确认真实范围与用途；F须另获联网授权，
前端须获准运行环境；B只在对应证据与执行授权齐备后继续条件候选和D4。不足则输出gap。
根MIT不泛化，express独立冻结，不为得到正向结果改用途或规则。

Windows os.geteuid、NOTICE父本失败与baseline历史FIXTURE_DRIFT没有重跑/关闭/重写。
没有新模型、服务、数据库、Formal或Schema动作，发布授权仍未授予。
本轮读取范围和完整日志逐字阅读未满足的限制如实见validation；不声称完整流程通过。

已有离线核对和文本定位能独立运行，历史受支持扫描/候选/报告可按历史证据演示。
尚无新可信正向结论、完整旧Formal读回或前端正式签收；报名/参赛仍需资格权利/
目标机/Java核心，完整作品需正式闭环/独立审核/端到端/发布及材料，竞争力需真人Gold/
新holdout/对比消融与质量性能复现。不用百分比表示这些独立未闭门禁。
