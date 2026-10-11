# P2 B 证据闭包与合同适配审计（2026-10-11）

状态：**PARTIAL；B 离线定向验收通过，待 A／Owner／前端，发布待 Root**。

本轮源码基线 `codex/scan-reliability-integration@0d9d581b259261b23cbf9190988429c96bdf2488`。
实际 `git merge-base --is-ancestor afca4c26c2fa45fa285fc9cabf48f52c54a59229 HEAD` 返回 0；
A 的 P2 源码、Schema、合同与阶段1 Review 对 HEAD 无差异。合并点 `647e4d8` 已在本地，
不是 Owner Review。Review 明确 pending；本轮未 fetch，远端仅按本地跟踪引用记录，不能声称本轮在线读回。
本机现有日志追加、reports 和受权限限制的 pytest 目录保留；未启停服务、联网取 npm 或安装包。

## 可机器复核的三例链

详见 [完整脱敏链](p2b-evidence-closure.json)，从已有三例公开回执导出，含受控 ZIP 摘要、ScanRun
终态与错误、npm name/version/purl、manifest Evidence ID/locator/来源 SHA-256、固定 tag URL/UTC/原字节
SHA-256/blob SHA-1、Assessment 绑定、Material 和 Result 1→2／同版 Summary 的精确 GET。

运行：`PYTHONPATH=backend python tests/fixtures/p2b/verify_receipt_closure.py`（PowerShell 以环境变量设置）。
校验器只打印 JSON，不读私有数据根、不联网、不运行扫描、不产生新 ID。
它在内存调用既有第一方 archive 构造函数，明确将 ZIP creator OS 固定为历史 POSIX 的 3；
三例 ZIP 和各 manifest 文件原字节摘要均与回执一致。Result 自摘要按 A canonical 算法重算，
Binding/Result/Material/Summary 通过实际 DTO 与 Draft2020-12 Schema 校验。

| 例 | scan_id | Assessment | 本轮链的含义 |
|---|---|---|---|
| is-number@7.0.0 | scn_761868e1-b9fa-4225-af23-d05c93d7b80f | asm_2071ba47-8de3-5046-88cc-4ec03b089c97 / 1 | unknown→pending；无新增候选 |
| lodash@4.17.21 | scn_3fd9e9cb-e2ca-48b1-88a6-110d56fbbc68 | ID/版本见机器链 | 根 MIT 不可泛化；文件范围仍待核 |
| express@4.18.2 | ID见机器链 | ID/版本见机器链 | 独立保留例；未改规则或调参 |

三例均 `CONTROLLED_FIRST_PARTY_MANIFEST_ONLY` + `TEST_ONLY`；partial/rules，
错误 `rules_stage_not_connected`。manifest_field 的 verified 仅证明解析观察，不能充当
license_text／上游来源或人工适用性证明。固定 tag LICENSE 与 Material.source_sha256 一致，
Material 仍 text_observed / adopted_as_unverified_observation / user_supplied_unverified / pending。
实际 npm 发布包的正文、范围与义务履行未获证明。

**完整 Formal Assessment 回执缺口**：既有 three-scan-readback 的 assessment 是仅六字段的脱敏投影，
不含完整 Assessment 正文；Binding.assessment_sha256 是 A 当时签发的完整对象摘要。
本轮只能比对 ID/version/facts_hash/usage_hash/rule_version 与两个 Result 的 Binding，
不能用投影摘要替代完整 Assessment 摘要。full_assessment_readback 和 old_formal_report_readback 均 null。
GET 纯读／数据库摘要来自既有真实运行；本轮是离线重核，没有新的 live GET 或数据库读回。

用途版本也不补造：A 候选将 Binding.usage_hash 作为 B expected_usage_version 的 pin；
source-index 历史 usage_version=null 不是新 Formal 用途版本。三例实际保存七维用途均 null，
与 source-index 的候选用途设想分离。旧 Report 缺口不得由 Summary 关闭。

## 逐字段适配结论

| B 内部字段/语义 | A DTO／当前实现 | 判定及剩余事项 |
|---|---|---|
| candidate_only | resources[].verification_state 固定 candidate_only | 一致；无正式授权提升 |
| suggestions[].state/conditions/basis_evidence_ids | advice[].state/conditions/basis_evidence_ids/rule_ids | 候选形式可映射；三例当前 basis/conditions 为空，不能读成没有义务 |
| rule_version=V4-MIT、rule_source | advice.rule_ids；Binding.rule_version 是父 Formal 规则版本 | 当前三例无正例；单独的 B 规则版本/来源 URL 没有明确 wire 字段，A 正式接纳时需冻结可追溯方式 |
| basis_source_sha256 | resources[].evidence_source_hashes + advice.basis_evidence_ids | 可按依据ID选取来源Hash；全资源 map 不等于全都是建议依据 |
| snapshot_sha256 / expected_scan_id | Binding.facts_hash/registry_revision/assessment_sha256；A 构造并计算内部快照 | 不是同一摘要语义；请求不能自报认证成功 |
| usage_version / expected_usage_version | A 用 Binding.usage_hash，Assessment.version 独立 | L2 Result revision 不改变原 Formal Assessment 或用途 |
| coverage_gaps / scan_coverage_incomplete | B evaluate_bound_candidate 会传递；A candidate 提前缺口路径没有逐条映射 scan.errors | **具体缺口**：三例 Result 未带 rules_stage_not_connected/scan_coverage_incomplete；机器链保留 ScanRun 错误。提请A修订，B未改A代码 |
| text_observed/content_sha256/byte_count/source_level | Material.parse_status/source_sha256/byte_count/source_level | source_sha256 是上传原字节内容Hash；不是 URL、Evidence 记录Hash或官方真实性 |
| provider_declared_unverified | npm parser 离线返回；当前 A Material/Result DTO 没有 npm observation 字段或接入 | **未接入**；不能添加 DTO 禁止的额外项或声称已经进入 Result |
| uploaded material | Result.material_ids + resources.material_ids + uploaded_material_applicability_pending | 独立材料观察；不会成为旧 ScanRun 的新 Evidence，后续正式接纳须 A 明确 Evidence 物化政策 |
| publication_status=succeeded/formal_effect=none | Result 固定值 | 保存成功；许可判断成功仍未证明 |
| companion Summary | P2_COMPANION_NOT_FORMAL_REPORT，同 Result ID/revision/hash | 独立不可变摘要；不替代旧 Formal Report |

## 负向矩阵与证据等级

已有合成测试保持复用，不为同一情形复制测试。具体函数见 tests/unit/test_p2_contract.py、
test_p2b_candidates.py；本轮另补缺失的跨文件 DTO/Schema/自摘要/精确路径联合校验和 npm 回执字段拒绝。

| 拒绝项 | 已有覆盖 | 本轮证据 |
|---|---|---|
| 错scan/Assessment/资源/版本/Evidence | 三例真实errors + A parent/subject测试 | 既有真实错误回执离线核对；本轮未新发HTTP |
| 扫描/用途pin错绑、Evidence闭包/来源Hash错绑 | B bound_snapshot/pinned_scan_or_purpose | 本轮B实测通过；合成 |
| 已核验许可文本／scope／normalized_ids冲突 | B conflict和A stored_conflicting/conflicting_license_facts | B实测；A当前Windows初始化阻断 |
| 重复／不同材料、无效摘要/文本、CAS与同键重放 | B local_material + A duplicate/retry/two_writers | B实测；A阻断；三例历史原键重放不冒充新实测 |
| 旧Evidence删除／改写，非目标对象／Evidence变化 | B d4_accounting相关测试 | 本轮B实测；合成 |
| 旧Assessment/Report Hash变化或无效Hash | B old_artifact_changed/invalid_readback_hash | 本轮B实测；旧真实Formal Report仍缺 |
| Result摘要篡改、重算摘要后删除来源Hash、错GET／Summary版本 | 新test_p2b_receipt_closure.py | 本轮实测，真实回执+合成篡改，非新扫描 |
| npm固定GET/URL/零重定向/策略/大小Hash/UTC/验证器 | 原npm测试 + 新字段和verifier矩阵 | 离线合成；未取得官方网络回执 |

## 前端交接边界

frontend-handoff-draft.json 中已有三例真实ID与精确GET；本轮链可帮助对照，仍为草案。
Owner批准合同、A提供获准同根或等价不可变回执、兼容提交及旧Formal读回前不发布正式handoff。
接收机须自己验证固定对象、旧新版切换、同版Summary与浏览器展示；B静态JSON及本机截图不代签。

- 404：显示固定对象未找到；不自动选择 latest，不自造 ID。
- 409：保留当前版本，读精确 binding/head；修正父绑定或CAS。相同键相异body不可自动重试。
- 422：显示具体输入原因，修正版本/摘要/编码/材料名，原输入不无限重发。
- 503：显示不可用/保存结果未知，先精确GET，再原键原body重放；不能断言未保存。
- pending/candidate/unknown/partial、basis Evidence、材料来源等级、条件和缺口按 A 响应展示；
  succeeded、MIT字样、FULL_TEXT_CLAIMED 或 FULFILLED 均不能标作授权成立。

## 本轮验证与失败分列

B 命令：设置 `PYTHONPATH=backend`、`PYTHONUTF8=1`，
`python -m pytest -q -p no:cacheprovider tests/unit/test_p2b_candidates.py tests/unit/test_p2b_three_scan_readback.py tests/unit/test_p2b_receipt_closure.py --tb=short`：
**90 passed，2个既有TestClient弃用警告**。其中真实回执一致性检查与合成拒绝/条件例不能互换等级。
中间 archive 默认Windows头复算曾导致11失败；明确历史POSIX creator OS后原摘要一致并复跑通过，
未改历史输入身份。新增测试先前空regex警告已修正。

`python -m pytest -q -p no:cacheprovider tests/unit/test_p2_contract.py --tb=line --basetemp=.tools/p2b-closure-pytest`：
**60 errors**，全部setup处 `AttributeError: os.geteuid`。本轮不是收集失败，实际在工厂初始化前阻断；
历史Windows合并回执的2 failed/2 passed/113 errors单列，历史Linux428/2不代替本轮通过。

两条NOTICE父本 excerpt fixture 历史 `excerpt_content_invalid` 未修复；本轮指定节点首次受GBK收集错误阻断，
设置UTF8后两条均在setup处os.geteuid阻断（46 deselected / 2 errors），不冒称在Windows重现同一父本业务失败。

固定baseline命令 `node benchmarks/p2b-verify-b-artifacts.mjs --baseline benchmarks/p2b-b-artifacts-baseline.json`：
**FIXTURE_DRIFT**，本轮首次511项（新增后数量会上升），baseline未更新；本机生成物与可发布工件待Root独立审阅。
受控输入闭包、JSON/Schema及编译为独立检查，不使baseline变绿。

本轮不新增依赖、provider或第三方正文；第三方来源继续使用原索引，AI与协调记录追加。
GitHub：本轮未stage/commit/push/PR，交Root逐文件复核发布。整个阶段1仍PARTIAL。

补充本轮Fail-first修复：可信npm回执包含timed_out=true且HTTP200时，旧B适配器忽略超时并误输出official_metadata_observed；新测试先实测1 failed，修复后超时返回failed/timeout/pending，异常类型拒绝npm_transport_timeout_invalid。缺该可选字段仍按false兼容旧内部调用；A正式回执必须显式冻结字段并由A控制验证器。最终B定向90 passed，规则candidates.py、A源码、公共DTO/Schema未修改。
