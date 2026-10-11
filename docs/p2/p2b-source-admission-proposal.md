# P2 B 最小可信来源／人工范围接纳提案

版本：proposal/1；状态：**待 A／Owner 正式合同与实现，未签发，未改变当前结论**。
2026-10-11 用户仅确认责任划分：A签发来源与版本绑定，Owner签发人工范围和适用性。

## 接纳两份独立回执

A来源回执至少包括：不可变receipt_id/版本、受控签发者身份、policy_id/版本、UTC，精确请求与最终URL、
GET/HTTP状态/零重定向、文件原字节大小/SHA-256、固定repository commit/revision及blob身份；
绑定scan_id、resource_id、ecosystem=npm、包名、精确版本、父Assessment ID/version、facts_hash、usage_hash。
签发接口只允许A受信路径，不接受上传者自报verified或B注入验证器。完整原文/私有库留在获准数据根。

Owner适用性回执引用A来源receipt_id及SHA-256，说明具体文件集合或可核验的范围选择器与排除项、
实际扫描对象和npm发布包的关系依据、包版本、用途版本、license表达式及原文Hash、审核决策与责任。
人工范围不可只写runtime_dependency而省略包内容绑定。义务履行独立复核，不因适用性已签就自动fulfilled。
公开回执不记录个人身份信息；内部授权签发者由Owner治理。

两个回执分别有 pending/accepted/rejected/conflict/revoked/missing；接受仅表示来源或范围证明，
不等于许可授权整体通过。缺签发、版本/Hash不一致、过期policy或撤销不得被较宽松材料覆盖。

## 三例精确来源候选

[机器闭包](p2b-evidence-closure.json)保存全部六文件的精确request/final URL、tag、blob SHA-1、
原字节SHA-256/大小及历史UTC；[原来源台账](../../tests/fixtures/p2b/real-source-index.json)保存网页URL。

| 固定tag／文件 | LICENSE原字节SHA-256 | 来源URL |
|---|---|---|
| is-number 7.0.0 / LICENSE | 35bdd8a44339719441900fb50fbefc5e2dca1ca662cbaed7a687de842c8b70f2 | https://raw.githubusercontent.com/jonschlinkert/is-number/7.0.0/LICENSE |
| lodash 4.17.21 / LICENSE | f71e8ed126b46346494aad5486874cd8f0aafe95092ed67d2e3cb6110f939abc | https://raw.githubusercontent.com/lodash/lodash/4.17.21/LICENSE |
| express 4.18.2 / LICENSE | 95a5762890e5c1c9808921cef095661fc482c5e1f0bba31446ac85595df6237c | https://raw.githubusercontent.com/expressjs/express/4.18.2/LICENSE |

这里的固定revision目前是tag名+精确blob/原字节摘要，**tag指向的不可变commit尚未签发**。
A须提供解析并冻结的commit及发布包关系证明，不能仅凭tag或URL称来源已可信接纳。
当前实际扫描只含第一方package.json/package-lock.json精确声明，未下载/安装npm包；
因此“同名同版本仓库tag”不能证明“npm发布归档含同正文及适用范围”。禁止B绕过A出口补造证明。

材料来源等级分别保留：manifest_parser_observation、fixed_git_tag_byte_observation、
user_supplied_unverified、official_registry_metadata（仅A可信GET后）、accepted_source_receipt、
owner_scope_attestation；只有后两份有效且闭包完整才能由A构造B的upstream_verified/human_verified输入。
文件名、MIT字样、URL、P0人审verified、上传者verified=true、FULL_TEXT_CLAIMED都不是该提升依据。

## Evidence 与 Result 原子绑定

A实现签发和不可变存储后，明确单独的来源Evidence与scope Evidence角色；每个新Evidence绑定
同scan/resource/version、receipt ID/hash、原文Hash、范围/排除项及用途pin。不得改写或删除既有Evidence。
若现有ScanRun终态不可变，A应正式定义独立P2 Evidence表/命名空间和引用闭包，不能让B伪装写入原扫描。
新增Result使用原CAS/幂等事务；依据ID和来源Hash必须进入resource.evidence_ids/evidence_source_hashes及
advice.basis_evidence_ids，receipt关系可通过获准精确GET读回。公共Schema新增须Owner正式批准。

同版Summary绑定Result ID/revision/hash；父Formal Assessment版本仍独立。
冲突/撤销创建新的不可变状态或拒绝回执，旧Result/Material/Evidence与旧Formal Report仍可只读核验，
旧Result仅证明当时依据，展示时须同时提示后继撤销；不能重写历史为授权成立。
缺失只输出具体gap，不保存假正向。GET始终不抓取、不补证、不修复、不生成版本。

## 接纳前的明确缺口及交接要求

A还需修订当前提前返回路径的扫描coverage gap传播、npm observation→Result的明确DTO，
以及候选规则V4-MIT与父Formal rule_version的来源区别；不能向当前严格DTO偷偷增加字段。

收到正式交接后B的验收顺序：

1. 核对Owner合同版本、A签发权和回执不可变Hash，获得获准同一数据根或等价只读回执。
2. 对is-number至少一项显式true用途取得真实受支持情形；当前三例用途全null且scan partial，
   即使来源接受，B现有门禁仍不能产生候选。由A正常流程提供充分覆盖和用途绑定；不足则命名gap。
3. lodash逐项保留文档示例／vendor／node_modules范围限制，不把根MIT覆盖整个包或依赖。
4. express保持规则Hash不变独立D4，失败原样保存，不按holdout调参。
5. A出口唯一GET https://registry.npmjs.org/is-number/7.0.0，固定GET/final URL、UTC、HTTP、
   原字节大小/SHA-256、零重定向及policy ID；只证明官方元数据本次观察，license仍provider_declared_unverified。
6. 同scan比较新旧Result/Material/Evidence/用途和同版Summary的建议新增/删除/依据更新与剩余gap；
   向A另取完整旧Formal Assessment及Report的精确GET/原字节Hash，不以Summary替代。
7. 冲突、撤销、缺失、CAS失败后旧对象仍可读；前端在接收机独立验证，不由B代签。

当前可信来源回执、Owner适用性回执、不可变commit/npm适用关系、可信npm GET及旧Formal读回均missing。
本提案的URL/hash只是待接受候选，不签发任何新正向建议，不放行阶段1或正式前端交接。

## 2026-10-11 授权与条件任务澄清

Owner已允许A afca4c26c2fa45fa285fc9cabf48f52c54a59229的现有P2 v1合同/Schema用于限定TEST_ONLY离线兼容开发；本提案仍不是已批准新DTO或已签发来源回执。A01—A09全部完成不是离线核对/负例/缺口分析开工条件。上方is-number显式true条件仅描述真实证据齐备后可做的条件候选验收，不要求Owner制造肯定用途或授权；当前三例21项null原值保留。原件已取得，本机未找到已获准字节位置时仅请求读取方式，不重新索取/抓取。A来源、Owner范围/适用性和履行相互独立；精确请求、状态及解除条件见p2b-external-dependencies.json，当前口径见p2b-current-status.md。生产、联网、正式模型、服务启停、公共Schema/Formal修改和提交发布仍未获授权。
