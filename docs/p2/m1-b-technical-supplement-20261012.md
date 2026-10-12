# P2 B：M1 技术补件与精确交接（2026-10-12）

本包是 **TEST_ONLY 离线技术草稿**；整体 PARTIAL，M1 的 Owner STOP 保持有效。
它补充旧观察的审查索引，不创建 Material、Result、Evidence、人工签认或许可结论。
机器对照见 `p2b-version-object-alignment-20261012.json`，实际检查见
`p2b-handoff-validation-20261012.json`。以下要求字段不是获批公共 DTO。

## 已有成果与本轮增量

直接复用三例真实 TEST_ONLY 回执、B 离线候选/材料/npm/对账及四条款定位。
B 源码和测试已随 `ca0dc317c95d6c08e606de469b56b3e7e0f9b0aa` 等提交发布；
前端实现提交 `7dd84b5e7c0b610bcaaf7ec074de0a6e03fdd244` 已发布到功能分支，
并已本地合入当前 `50d8704a362f6e6615c1ed95d7f06da2bc3e871f`。
发布依据是已有仓库回执及本地 Git 引用，本轮没有在线查询。
旧 JSON 的未发布/字节未找到字段保留为历史快照，以本日期记录补充当前状态。

本轮只新增五项补件草稿、五条对象链的对照、版本/摘要/接口差异和逐项依赖。
复算摘要、搬运既有定位及重复保存均不算新事实；正式新增事实、Evidence、正向许可结论均为 0。
本轮源码及测试未改，历史 B 120 passed、前端 133 passed/构建通过、Root 12 项
静态兼容通过直接复用，不称本轮或接收机真实验收。

## M1 五项补件

### 1. 来源、producer、版本与原文归属

| 资料 | 精确对象与摘要 | 等级及待确认项 |
|---|---|---|
| M1 历史 npm 发行包 | is-number@7.0.0，3730 bytes，SHA256 `7b75c1057198cf97696909a9bee176c9c5e9bcb5b03bf3ecef2f484defadd51e`，成员 `package/LICENSE` | 复用 M1 blocker 的历史包内字节相同记录，本轮未重读归档；A 补发行包获取回执、producer、UTC、policy、成员类型/清单和对应存储 |
| LICENSE 原字节 | 1091 bytes，SHA256 `35bdd8a44339719441900fb50fbefc5e2dca1ca662cbaed7a687de842c8b70f2`，Git blob SHA1 `9af4a67d206f24ecdbb5fdff2839041ca0bbd346` | B 已有直接安装副本字节核对；不证明官方来源、原 sidecar 位置或全部包内容适用 |
| B 历史 Git tag 文件 | `https://raw.githubusercontent.com/jonschlinkert/is-number/7.0.0/LICENSE`；上述原文 Hash；获取时间 `2026-10-10T08:18:54.766497+00:00` | 历史 HTTP 观察，不是本轮获取；tag 不是不可变 commit，不是 npm 发行包范围证明 |
| M1 人工确认链 | `human-review-pending.json /0`；旧材料指针 `TRANSFER/evidence/http-events.json /24/response/material` | 仅已公开 blocker 的引用，原文件本轮未读取；reviewer、reviewed_at、scope、签发/确认状态保持 null/pending，由 cz/授权审核者、A、Owner 分别确认 |

M1 scan 为 `scn_fb8856de-91c3-41b7-b758-fcf35c2ea77d`，resource 为
`cmp_1fc87b46-9132-51b6-b39e-bf1af669ca8a`，Assessment 为
`asm_6c664ed7-7c41-512c-bbcc-a178a8edea79` v1，旧 Result revision 3。
公开 blocker 未给出完整 Material/Result/Evidence ID、Binding Hash 或实际 GET；机器表明确留空。
同 resource ID 和相同 LICENSE Hash 不能借用 B 的另一 scan/Assessment 的回执。
不再次索取 LICENSE 或地址；仅请求 A 提供已有 RESULT/MANIFEST/确认链的必要脱敏字段。

### 2. 条款、条件、义务与反证索引

复用 `p2b-isnumber-clause-readback.json /audit/clause_mapping`；零基左闭右开字节区间，
行号从 1 开始。定位作用于上述 SHA 的完整原字节，迁移为 M1 审核索引仍待确认同一字节对象。

| 主题 | byte / line | 对象、条件与未知项 | 反证或限制索引 |
|---|---|---|---|
| 许可语句 | `[68,112)` / 5 | 仅为许可语句锚点；实际文件集合、版本和授权适用范围待 Owner/审核者确认 | 不覆盖其他依赖/vendor；来源签发与范围关系未闭合 |
| 声明保留 | `[502,573)` / 12 | 保留版权与许可声明条件的待审索引；副本/实质部分范围与实际交付文件、保留位置未知 | M1 未见 NOTICE 的历史记录不能证明无义务；履行凭据待确认 |
| 免责声明 | `[630,662)` / 15 | 免责文字索引，不能据此推导许可适用或保留义务已履行 | 原文完整审核与最终交付副本仍需独立核验 |
| 责任限制 | `[832,892)` / 17–18 | 跨行责任限制索引，不代表完整条件集合或人审已完成 | 相同 Hash 不能证明签发者、实际范围或履行 |

四个区间是锚点而非完整条款边界；不得把未覆盖文字解释为不存在附加条件。
专利、商标、其他文件/依赖许可、附加通知的审查结果保留 unknown，由审核者说明依据与限制。
本轮不抄录第三方全文，不制造新的条款 Evidence。

### 3. 用途、范围与同对象/版本关联

三例七字段 `commercial / modified / distributed / network_service / training /
redistributed_assets / source_disclosure` 共 21 个 null 原值全部保留。
M1 的七字段原值未在当前公开 blocker 给出，不能由 B 三例或来源台账假设用途代填。

Owner 待确认：真实用途及 usage Hash、交付资源 ID/精确版本、实际文件集合与 manifest Hash、
范围选择器、示例/vendor/node_modules/依赖等排除项、范围确认所引用的 A receipt ID/version/Hash
及原文 Hash、适用性决定与限制、履行凭据/交付位置。
审核者身份、日期、决定、scope 与理由保持未填写；可以 unknown、拒绝或 pending，
不要求肯定结论。来源可信、范围适用、义务履行分别核验，不能互相代替。

### 4. 错版与自然缺口对照

| 对照 | 固定依据 | 预期保守处理 / 等级 |
|---|---|---|
| M1 自然缺口 | 上述 npm 发行包 Hash；blocker 记载未找到 NOTICE、cz 确认链缺失 | 保留通知/确认链缺口；未找到不等于不需要。历史材料记录，本轮不重读归档或执行 M1 |
| B 自然缺口 | 三例固定扫描 ZIP/Binding/Result；原 `rules_stage_not_connected`、scope/source gaps、21 null | coverage 和未知用途保留，无新正向候选；真实历史 TEST_ONLY 记录 |
| 真实固定来源错对象对照 | lodash@4.17.21 LICENSE，SHA256 `f71e8ed126b46346494aad5486874cd8f0aafe95092ed67d2e3cb6110f939abc`；URL/UTC/blob 见机器表 | 不能当作 is-number@7.0.0 依据；此为跨对象审查对照，不冒称同包真实错版或已运行 M1 拒绝测试 |
| 历史错版请求 | `real-http-receipts.json` 的 `wrong-version`，固定 v6 对象与原文摘要/请求摘要见机器表 | 历史 HTTP 409 `p2_resource_version_conflict`；请求版本人为变更，明确 SYNTHETIC_REQUEST_MUTATION，不是另一版本真实上游材料 |
| 既有 B 摘要/版本负例 | `test_p2b_offline_material_audit.py`、`test_p2b_candidates.py`；120 项历史集合内 | 合成对象/摘要变更单列，不修改第三方原文；不计新增自然案例或本轮测试 |

同包另一真实版本的固定来源对照未在当前可读资料找到，明确仍缺；不联网补抓、不用合成错版充数。
express 保持规则/Hash冻结，独立 D4 未获本轮执行；lodash 的示例/vendor/依赖/实际范围限制保留。

### 5. 相对旧 Material 的增量事实台账

| 分类 | 本轮条目 | 接纳边界 |
|---|---|---|
| 旧观察已有 | LICENSE 原文、版本、1091 bytes/Hash，M1 旧材料 revision 3 保存，B 三例未核验材料及四锚点 | 不算本轮新增事实；旧材料仍未核验 |
| 此次技术补件新增 | 跨 scan/Assessment 的身份差异、四种 Hash 分型、不可解析候选 SHA、capture/resolve 映射缺口、逐责任方字段索引 | 文档审查增量，不是许可事实或 Evidence；不改变保存对象 |
| 待人工确认 | 来源归属/producer、reviewer/日期、真实用途/范围/适用性、履行 | cz/授权审核者、A、Owner 各自确认，不代签 |
| 仍缺 | M1 完整对象和 GET/Hash、A 来源/Evidence/运行包/npm DTO、旧完整 Formal、前端真接收 | A 正式流程决定新 Evidence 是否接纳；重复保存/复算/定位不能增加事实数 |

普通 pending 材料的技术保存与正式许可接纳分开，不把肯定人审设为技术保存的普遍前提；
M1 此刻另有任务书 STOP，本包不执行其 capture/resolve、保存或派生结果动作。

## 版本、接口和运行差异

| 基线 | 当前核对结果 | 待解除项 |
|---|---|---|
| A `afca4c26c2fa45fa285fc9cabf48f52c54a59229` | 当前祖先；合同、公共 Schema、`backend/app/p2` 及路由与当前 Git 对象对照 | 仅作限定离线基线，不等于最终获批运行组合 |
| 统一候选 `ec4c680bf7bb0d7d0af583e5376336421361fc8d` | M1/前端文档引用；本机 Git 对象不可解析，无法比较候选代码和包内 Schema | A 提供该候选源码/冻结清单、Schema、接口映射及与主线差异；禁止口头替换 |
| 当前集成 `50d8704a362f6e6615c1ed95d7f06da2bc3e871f` | B/前端/M1 文档已本地合入；当前合入尚未发布，缓存 origin 为 `246bfba…` | 最终组合与运行批准由 A/Owner 确认；本轮不发布 |
| 前端 `7dd84b5e7c0b610bcaaf7ec074de0a6e03fdd244` | 已发布功能分支；两服务文件本地与该提交对齐 | 最终 frontend/backend/Schema/image/root 一起冻结；静态接受不是目标机签收 |
| 历史镜像 `sha256:6510aeaf29bdcfb1b3bdb3655fef73d39f9bc6164ae876011a57c356c5cef23c` | 历史固定 v6 TEST_ONLY 运行记录 | 镜像持有人/Owner/A 提供来源、独立 digest、linux/amd64及可恢复根；不视为当前集成镜像 |

主线 `P=/api/v1/scans/{scan_id}/assessments/{assessment_id}/p2` 的 Binding、Result、Answer、Material、
Summary 及精确版本查询直接复用。当前该路由模块未提供 capture/resolve；本轮不创造路由。
A 应逐项给出旧方法/DTO/事务边界到现有路由/服务/Store 的映射、不可映射项及迁移策略。
M1 GET 在映射/ID未交付前保持 null；机器表其余路径只登记现有合同/回执，不表示运行可访问。

## 后端 A 的八项精确需求

| 项/责任方 | 所需字段与当前证据 | 解除条件 → 解锁任务 |
|---|---|---|
| A：A + Owner/镜像持有人 | 唯一获批源码 SHA、Schema ID/原字节 Hash、frontend SHA；镜像来源/digest/平台；可恢复 TEST_ONLY root 的不含私有路径的 root ID/manifest Hash；各固定对象/GET/Hash；现有三基线/历史镜像未统一 | 提供版本清单与批准范围，无矛盾 pin → 以后获执行权的接收/恢复检查 |
| B：后端 A | 不可变 receipt ID/version/Hash、issuer 身份、policy ID/version、UTC、状态 accepted/rejected/conflict/revoked；scan/resource/name/ecosystem/version、完整 Binding、原文 Hash/大小、精确只读 GET；当前只有历史观察 | A 受信入口签发与闭包可验证 → 来源错版/冲突/撤销检查 |
| C：后端 A | repository/不可变 commit、文件相对路径/blob/原字节 Hash/大小；npm 发行包 Hash/成员清单/成员 Hash、关系与范围/排除项；当前 tag/安装副本、M1 历史归档记录 | 独立重算关系并确认精确对象 → 来源/版本和 lodash 范围核对 |
| D：后端 A | Evidence 角色 license_text/scope_attestation、命名空间/存储、receipt 引用、内容 Hash与记录 Hash语义、对象版本/用途 pin、精确 GET、Result basis 和原子 CAS闭包；当前只有旧 manifest Evidence | 正式策略/物化/存储可读回且不覆盖旧 Evidence → 新增/删除/更新依据及解决/新增/剩余 gaps 对账 |
| E：后端 A | 每一分支、含提前返回的 coverage/errors/gaps 传播映射；父 Formal rule_version 与 B 候选规则独立版本/来源；当前仅满足特定分支才进入 B snapshot | 全分支保留原错误且规则可追溯 → 覆盖不足/旧新版保守检查；facts_hash 不当 snapshot Hash |
| F：后端 A | 正式 npm DTO、A 控制的验证器/出口/policy 与 Result/Evidence 接线；显式布尔 timed_out、GET唯一指定URL、request/final URL/零重定向/UTC/HTTP/32KiB/原字节 Hash；当前只有 B 内部验证器，缺字段默认 false是历史兼容行为 | 冻结 DTO并拒绝缺失/非法 timed_out；获取另获网络权且由 A 执行 → 元数据观察验证；HTTP200不覆盖超时，许可声明仍 provider_declared_unverified |
| G：后端 A/原件持有人 | 完整旧 Assessment原序列化/Hash、旧 Formal Report ID/格式/原字节 Hash/固定 GET/授权范围；当前 B六字段投影、v6原报告缺失 | 完整原件可复算 → 历史 Formal 不变检查；Summary/重渲染不能替代 |
| H：后端 A + Owner/平台维护者 | 缺失/错版/错Hash/冲突/撤销/CAS失败后的旧对象固定读回、重启前后 Hash、支持平台及环境；现有隔离历史 HTTP，不是接收机证据 | 获准环境、恢复清单、负例及重启回执到位 → 正式接收/恢复；Windows/NOTICE失败另验 |

八项具体字段、source pointer、状态、execution gate均在机器表。A02/A03/A05继续独立，
有材料不等于有执行授权；不可向现有严格 DTO 添加上述提案字段。

## 任务矩阵、独立签收与停止点

| 工作 | 状态/责任 | 下一步与发布 |
|---|---|---|
| 既有 B 源码/120项回归/三例/条款定位 | 已有验收/后端 B | 已发布记录复用；本轮无重复生成 |
| 本轮 M1补件、版本/对象/接口/增量台账 | 草稿可复核/后端 B | 当前可执行范围收口；本轮新文档未提交或发布 |
| A–H 正式接口、Evidence、运行组合、旧 Formal | 依后端 A | 精确补件到位再核对；运行/网络动作另需授权 |
| 七用途、实际交付/范围、M1续接 | 依 Owner | 保留真实 null/unknown，引用 A receipt/原文Hash；Owner明确续接才执行M1产品动作 |
| 来源归属、条款/适用性与履行人工审查 | 依 cz/授权审核者 | reviewer/date/确认不代填；不用肯定结论换取通过 |
| 接收机 27 GET、真 POST、CAS409、重启 | 依前端 + A/Owner | A/Owner给出最终获批27个精确URL/预期对象Hash清单；缺少完整清单不自行凑27项 |
| 发布、合并、部署 | 依 Owner + Root | 本轮不授权；已有功能分支发布不代表生产或Formal启用 |

前端还需最终前后端 SHA/Schema/字段映射、获准接收环境与可重置根、固定 GET/Hash/重启，
真实回答/材料 POST+读回、两会话 CAS409、原键原body幂等、超时保存未知恢复、
旧新版/同版Summary/Formal分区/state/gap/basis截图与网络记录，以及失败的预期/实际/责任方。
未决请求目前只在内存，刷新会丢失；不能声称跨重启恢复草稿。

现有离线核对/文本定位及前端静态工作台可独立验证，历史受支持环境扫描/候选/报告可按历史演示；
尚无新的可信正向许可、完整旧Formal读回或跨栈真实签收。
可报名/参赛仍需资格权利/目标机/Java核心门禁；完整作品仍需正式闭环/独立审核/端到端/
发布及报告视频/匿名资源AI材料；获奖竞争力仍需真人Gold、新holdout、对比消融、质量性能复现。
不编造完成百分比。M1 STOP 与 P2 PARTIAL 保持，交付等待 Owner 复核。

本次运行精确 token 数不可获得；开工估算 8,000～16,000，离线草稿范围未扩张为产品动作，
无精确遥测判断实际是否在估算内。完整历史日志逐字阅读限制和本机 Python 环境启动失败
单独记录于验证回执；它们不被文档检查或历史测试覆盖。
