# P2 后端 B 两例交接与 npm 原始记录核对

日期：2026-10-12；整体 **PARTIAL**。本轮只读复核并建立索引，不生成扫描、用途、材料、结果、Evidence 或人审记录。不是公共 API。完整字段、文件 Hash 和 JSON Pointer 见 [结构化索引](p2b-two-case-index.json)，本轮检查见 [验证回执](p2b-two-case-validation.json)。

## 1. is-number@7.0.0：最接近的文本支持样例（未达到真实用途正例）

已发现同版本材料与历史条款锚点；实际用途全null、来源与范围未核，尚无真实正向用途建议。

| 对象 | 原有完整身份／定位 |
|---|---|
| Scan | scn_761868e1-b9fa-4225-af23-d05c93d7b80f |
| 资源 | cmp_1fc87b46-9132-51b6-b39e-bf1af669ca8a；pkg:npm/is-number@7.0.0 |
| Assessment | asm_2071ba47-8de3-5046-88cc-4ec03b089c97 / 1；全部Binding摘要见索引 /cases/0/binding |
| Material | p2mat_2414eae690a988d553a19cd091fd6560c3add60bbf69c4d716aeddb15a0b77b1 / 1；1091 bytes；SHA256 35bdd8a44339719441900fb50fbefc5e2dca1ca662cbaed7a687de842c8b70f2 |
| Result revision 1 | p2res_4c83b21c51fc4ece2de8d5f48c91afb268da0b0adc972fcdb330957d98691f10；SHA256 a6cc23f999a32f19016cf6c332a5c744e2c98b9bdaee8f11c2d75fab6b77b668；前驱 null |
| Result revision 2 | p2res_3910c073174a8aefc76f3f1ffe4a76fd7d4260d78cc7f2ecddee6c061b0f184c；SHA256 57bcff5806b05fcfac01c39b4e4cce28b92ffb0bac80b59e8112e01868c84af0；前驱 p2res_4c83b21c51fc4ece2de8d5f48c91afb268da0b0adc972fcdb330957d98691f10 |
| 同版 Summary | p2sum_0996fa116b79ce999a9a2cb74359849b86f2fe65417710e380c3841f51c804ea；绑定 Result revision 2 |
| Evidence | evd_41bb871f-014f-5e63-9744-cbbc4036edcd；evd_64abc673-5b47-546b-b7b2-4578a931c8de |
| 逐字段定位 | p2b-evidence-closure.json /cases/0；three-scan-readback.json /cases/0/p2 |

精确读取路径全部保留在索引 /cases/0/precise_get、/result_chain 和 /evidence；P2 Result/Material/Summary 带 assessment_version=1。未配置接收机URL，未执行live GET。Formal Assessment既有路径本身不接受版本参数，以Binding固定v1；完整旧正文仍缺。

七项真实保存用途全部 null；source-index 中 commercial/distributed=true 等仅是候选设想，未保存，不能当 Owner 声明。交付资源范围和排除项未确认。

材料仍 pending/user_supplied_unverified；manifest Evidence 的 verified 只表示解析观察。实际 advice.rule_ids、basis_evidence_ids、conditions 均为空；V4-MIT 和官方条款来源只是后续审核的规则上下文，未作为本例正向规则触发依据。父 Formal rule_version 与 B 候选规则分开。必要条件参见 /cases/0/rules/possible_conditions_for_future_review，不声称已满足。

已有四锚点在 p2b-isnumber-clause-readback.json /audit/clause_mapping：许可语句 [68,112) 第5行；声明保留 [502,573) 第12行；免责 [630,662) 第15行；责任限制 [832,892) 第17—18行。零基字节左闭右开、行号从1开始。这是历史本机匹配字节定位，本轮未重读原件；锚点不是完整条款边界，不证明 npm 来源、范围或履行。

扫描保留 partial / rules_stage_not_connected；Result由unknown→pending仅表示材料观察保存。完整扫描覆盖、可信来源、适用范围、人审与履行均未关闭；旧Formal和旧版Summary原字节没有用新版companion替代。

## 2. lodash@4.17.21：缺口样例（未证明禁止）

已保存同版本LICENSE观察，但文件/子资源/交付范围未核；未知不能解释为禁止，根文本不能自动推广。

| 对象 | 原有完整身份／定位 |
|---|---|
| Scan | scn_3fd9e9cb-e2ca-48b1-88a6-110d56fbbc68 |
| 资源 | cmp_0275b03d-5f19-5eaf-8ccf-f6b4caf5ac3e；pkg:npm/lodash@4.17.21 |
| Assessment | asm_0108cb18-19bf-5377-a6f2-b12476c9447b / 1；全部Binding摘要见索引 /cases/1/binding |
| Material | p2mat_74d7a9574bce0d306febe9696f35f902cb0f6ef00cdbc9da4da3d6942a8b2a49 / 1；1952 bytes；SHA256 f71e8ed126b46346494aad5486874cd8f0aafe95092ed67d2e3cb6110f939abc |
| Result revision 1 | p2res_05e8911184399cafcf6f41bd3e6fc19acbd35623011a8b5c327c26602d65a8e7；SHA256 bef620480f22db38641a7aff1bb7b9e5e604762c68caa619807b9c9863bf60d0；前驱 null |
| Result revision 2 | p2res_d37dd33a54af15b40f4729e56ce103142f1612155f78b2b85c226d7e0f1f42f7；SHA256 3773653a366eb7e354e2b4b80a35685981312c577b4f537f68471f929af3099b；前驱 p2res_05e8911184399cafcf6f41bd3e6fc19acbd35623011a8b5c327c26602d65a8e7 |
| 同版 Summary | p2sum_aaae5e69d5691c2f9989a760ff40e88a5d4fd7494199923cdf18d66083fc4db3；绑定 Result revision 2 |
| Evidence | evd_2e0913c6-0f00-5d28-a128-419be20d7a1b；evd_9e89d86e-c485-5d57-bbd1-03a24ad15c41 |
| 逐字段定位 | p2b-evidence-closure.json /cases/1；three-scan-readback.json /cases/1/p2 |

精确读取路径全部保留在索引 /cases/1/precise_get、/result_chain 和 /evidence；P2 Result/Material/Summary 带 assessment_version=1。未配置接收机URL，未执行live GET。Formal Assessment既有路径本身不接受版本参数，以Binding固定v1；完整旧正文仍缺。

七项真实保存用途全部 null；source-index 中 commercial/distributed=true 等仅是候选设想，未保存，不能当 Owner 声明。交付资源范围和排除项未确认。

材料仍 pending/user_supplied_unverified；manifest Evidence 的 verified 只表示解析观察。实际 advice.rule_ids、basis_evidence_ids、conditions 均为空；V4-MIT 和官方条款来源只是后续审核的规则上下文，未作为本例正向规则触发依据。父 Formal rule_version 与 B 候选规则分开。必要条件参见 /cases/1/rules/possible_conditions_for_future_review，不声称已满足。

没有本轮可读的 lodash 原始LICENSE字节，条款定位明确为空。根LICENSE不能自动覆盖样例、外部文件、子资源、依赖或实际交付范围；这是范围证据缺口，不据此断言这些文件实际存在独立限制或商业用途被禁止。

扫描保留 partial / rules_stage_not_connected；Result由unknown→pending仅表示材料观察保存。完整扫描覆盖、可信来源、适用范围、人审与履行均未关闭；旧Formal和旧版Summary原字节没有用新版companion替代。

## npm 原始记录核对结果

P2 frontend-handoff-draft.json /npm 明确为 blocked_awaiting_trusted_egress。GET目标 https://registry.npmjs.org/is-number/7.0.0 已约定，但实际UTC、final URL、HTTP、响应Hash/大小、policy及原字节为null；重定向、超时、验证器身份、name/version/license/repository/dist字段均无实际原响应可核。离线parser和合成测试不是官方获取成功。

M1 blocker另记载3730字节发行包SHA256 7b75c1057198cf97696909a9bee176c9c5e9bcb5b03bf3ecef2f484defadd51e，package/LICENSE为1091字节且摘要与B旧观察一致。本轮未定位到归档原字节与获取回执，仅保留历史文档声明；其scan scn_fb8856de-91c3-41b7-b758-fcf35c2ea77d与本例不同，禁止借用其绑定。元数据响应Hash、发行包Hash、LICENSE内容Hash与Evidence记录Hash分别核对。

已检查公开交接目录、fixture、资源台账和本机reports文件清单及相关字符串；不能推断其他未授权私有位置不存在原件。本轮网络请求为0，未重新抓取、下载、安装或执行包代码。已请求现有原始记录的获准只读位置，无需再索取已经取得的LICENSE。

## 人工审核与外部依赖

| 责任方 | 所需内容／解除条件 |
|---|---|
| A/原件保管方 | 官方精确npm原始响应/归档与获取回执的已有只读位置；原字节与policy/UTC/HTTP/URL/timeout/digest齐备后核对；不得要求重新索取已持有LICENSE |
| A | 可信来源receipt、npm发布包关系、Evidence物化与规则来源/coverage映射；同scan/resource/version/Binding完整闭包可读回 |
| Owner | 真实用途、交付资源集合/范围/排除项；明确原值与范围；不要求肯定许可决定 |
| Owner指定人工审核人 | 条款适用性、条件与履行核验；具审核身份/日期/对象版本/原文Hash/范围/决定，可保持pending或拒绝 |
| A/原件保管方 | 完整旧Assessment及旧Formal报告、旧版Summary固定读回；不可变原件/Hash，不用重渲染或新版Summary代替 |
| A/前端/Owner | 获准运行组合和接收机固定GET验证；实际对象/版本与响应Hash相符；本轮路径不是live可访问声明 |

审核人需分别核对来源身份、包版本及文件范围、条款完整条件、真实用途、交付范围/排除项与义务履行，记录姓名或受控审核ID、日期、引用Hash及决定；公开工件不代填个人身份。可以保留pending/unknown或拒绝，不要求肯定许可结论。B不代Owner和审核人签收。

## 本轮验证与发布

本轮新增两例索引和审查交接，不重复生成业务样例；新增事实、Evidence、正向建议均为0。使用现有前端只读验证器检查两例历史Result/Material/Summary，另复算Result摘要、引用与版本链、源文件Hash和JSON Pointer；验证等级为历史真实回执离线核对，不是新HTTP或接收机签收。

Python命令启动失败，现有venv所引用运行时不可用；未安装或更改环境。本轮不声称重新运行Python DTO/Schema或120项回归；公共Schema仅记录Hash及固定契约关系，历史验收与本轮静态核验分列。无需为文档新增重复测试。

旧B成果已有功能分支发布记录；本轮三份交付文档/索引/验证回执未提交、推送、PR或部署。M1 STOP及其他在途补件保持，不修改产品代码/公共Schema/旧工件。整体PARTIAL主要因为真实正向用途样例与官方npm原始记录尚缺。
