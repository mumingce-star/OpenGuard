# P2 后端 B 独立准备（2026-10-08）

状态：**候选，未接入正式 Assessment**。Root 明确回复 P2-01 基线和 DTO 尚未冻结。本文件及 `backend/app/p2b/` 只覆盖 B 可独立验证的离线事实；任何 A API、存储、报告、前端状态或公网抓取均未修改。

## 三个真实来源与字段样例

机器可读台账在 `tests/fixtures/p2b/real-source-index.json`。`scan_id`、`scan_object_id`、`evidence_ids` 当前为空：尚无这三个固定输入的真实扫描回执，不能伪造 P0 身份。`source_object_key` 只是来源台账键，不是 P0 对象 ID。每个上游固定 tag 文件均记录 **Git blob SHA-1 和原文字节 SHA-256**；重新计算的 Git blob SHA-1 与上游文件接口返回值一致，因而 SHA-256 对应这些文件的确切字节。它们不能代替后续用户上传材料及真实扫描 Evidence 的独立 SHA-256。没有把上游许可证原文复制进仓库。

| 角色 | 固定对象 | 来源与 Git blob SHA-1 | 许可关系、条件与未知项 |
|---|---|---|---|
| 有限正例候选 | `is-number@7.0.0` | [package.json](https://github.com/jonschlinkert/is-number/blob/7.0.0/package.json) `3715072609d61a010bff7116331b71f04206af96`；[LICENSE](https://github.com/jonschlinkert/is-number/blob/7.0.0/LICENSE) `9af4a67d206f24ecdbb5fdff2839041ca0bbd346` | 同一上游 tag 声明 MIT 并有 LICENSE；仅在精确扫描对象、适用范围、原文和人工核验都绑定时，依 [OSI MIT](https://opensource.org/license/mit) 提供保留版权与许可声明的条件候选。npm 发布包的内容及义务履行未知。 |
| 缺口/限制反例 | `lodash@4.17.21` | [package.json](https://github.com/lodash/lodash/blob/4.17.21/package.json) `83080d4381ebe92e1a6ac5d254dd3fb5bc6fd452`；[LICENSE](https://github.com/lodash/lodash/blob/4.17.21/LICENSE) `77c42f1408a38a0609cac12c887616cb21bfb736` | 上游原文明确将文档示例代码列为 CC0，并提示 `node_modules`/`vendor` 文件另有许可；根 MIT 不自动覆盖这些对象。具体使用文件、范围和用途仍未知。 |
| D4 保留样例 | `express@4.18.2` | [package.json](https://github.com/expressjs/express/blob/4.18.2/package.json) `0996637deaa0c79b2a7503f1ce06f22608eba8cc`；[LICENSE](https://github.com/expressjs/express/blob/4.18.2/LICENSE) `aa927e44e31d486f807634887662efa39256bf84` | 固定 tag 有 MIT 声明与原文；此样例未用于 L1 规则调整。实际扫描对象、包内容、用途细节、人工适用性均待 D4。 |

下表的 SHA-256 是**上游 Git tag 文件原始字节**的历史内存复算值，URL 与 Git blob SHA-1 对应上表及机器台账；不是 npm 发布包、用户上传文件或 ScanRun Evidence 的哈希。每文件 UTC 获取时间和原字节编码未记录，不能补造。

| 固定 tag | `package.json` 原字节 SHA-256 | `LICENSE` 原字节 SHA-256 |
|---|---|---|
| `is-number@7.0.0` | `51c133f4e41df982aef69027249ff9d7262645029f437d079adc7c83328fb620` | `35bdd8a44339719441900fb50fbefc5e2dca1ca662cbaed7a687de842c8b70f2` |
| `lodash@4.17.21` | `0d486d8dd5d67f09a44aa72a6acecba39a5a66c07ec4f988e9c2ee3075563a5e` | `f71e8ed126b46346494aad5486874cd8f0aafe95092ed67d2e3cb6110f939abc` |
| `express@4.18.2` | `2cd424f19ed994070c827b5448a3bc5fbee955bbbe81aff28204d8c5a5a89ebb` | `95a5762890e5c1c9808921cef095661fc482c5e1f0bba31446ac85595df6237c` |

### 逐字段事实链复核

| 用途声明 → 精确对象 | 材料 → 扫描 Evidence | `V4-MIT` → 当前建议/缺口 | 未知项 |
|---|---|---|---|
| `is-number`：`commercial=true`、`distributed=true`；目标版本 `7.0.0`，真实扫描对象 ID 与用途版本均为 `null`。 | 固定 tag 的 `package.json` 和 `LICENSE` URL、blob SHA-1 与原字节 SHA-256 如上；材料尚未作为真实本地补证接纳，`material_ids=[]`，`evidence_ids=[]`。 | 只有 A 的同 scan 精确对象、已核验 MIT 原文、人工适用性与对象范围 Evidence 闭包成立后，才可给保留版权/许可声明的 `conditional_candidate`；当前为 `real_scan_binding_missing`，**无正式建议**。 | npm 发布包是否包含相同正文、NOTICE 字节、人工适用性、义务履行、真实扫描覆盖与获取 UTC 时间。 |
| `lodash`：`commercial=true`、`distributed=true`，其余部分用途未知；目标版本 `4.17.21`，真实扫描对象 ID/用途版本为 `null`。 | 固定 tag 两文件有历史哈希；根 LICENSE 对文档示例及 `node_modules`/`vendor` 范围有限制，实际使用对象未确定；`material_ids=[]`、`evidence_ids=[]`。 | `V4-MIT` 不可泛化到例子/vendor/其他对象；当前 `real_scan_binding_missing`、`file_scope_unverified`、`separate_terms_for_examples_and_vendor_files`，**无正式建议**。 | 用了哪些文件、各文件独立条款、未知用途维度、人工范围/适用性、获取 UTC 时间。 |
| `express`：`network_service=true`，其余部分用途未知；目标版本 `4.18.2`，真实扫描对象 ID/用途版本为 `null`。 | 固定 tag 两文件有历史哈希；未获得 NOTICE 字节，也无本地材料接纳和 P0 Evidence，`material_ids=[]`、`evidence_ids=[]`。 | 仅保留为规则冻结后的独立 D4 样例；当前 `real_scan_binding_missing`、`independent_reconciliation_pending`，**无正式建议**，不据此调整 L1。 | npm 发布包正文、人工适用性、扫描覆盖、义务履行及同 scan 补证前后 Assessment/报告。 |

三例的 `training` 与 `source_disclosure` 现均明确记为 `null`，表示来源台账没有用途声明；它们不是用户确认的 `false`。`source_object_key` 只连接上述上游台账行，不能代替 A 签发的对象 ID。正式链必须逐 Evidence 记录 ID、scan/object/version、来源摘要、原文内容摘要和核验者/范围，再由 A 认证快照及用途版本；任何一环缺失时只给缺口。

## L1 最小支持矩阵

输入仅为调用方给出的扫描对象、完整 Evidence ID 集合、对象/版本绑定观察和三态用途。B 输出 `candidate_only`、条件、`basis_evidence_ids`、规则来源和逐项缺口。它不写正式 Assessment，也不调用模型。现有 `assessment-1.0-facts2` 只对 **精确版本、已核验许可原文、人工核验范围** 的 MIT 软件提供有限提升；根 LICENSE 不继承依赖，AI 资产独立判断。B 的候选门禁进一步要求 Evidence 的 scan/object/version 一致，悬空 ID 直接拒绝。

| 情况 | B 回执 |
|---|---|
| 精确 MIT 软件对象、已核验原文/适用性/范围、显式 `true` 用途 | `conditional_candidate`，引用全部依据 ID；保留版权与许可声明、核查履行 |
| 缺许可或人工范围证据 | `license_text_and_applicability_unverified` 或 `object_scope_unverified`，无建议 |
| 错版本、错对象、根 LICENSE 给依赖 | `evidence_wrong_version` / `evidence_wrong_object`，无建议 |
| 用途 `null` | `usage_*_unknown`，该用途无建议 |
| AI 资产 | `ai_asset_independent_license_required`，无 MIT 软件建议 |
| 模型失败 | `model_explanation_unavailable`，确定性候选与 Evidence 不被覆写 |
| 悬空 Evidence | 抛 `dangling_or_duplicate_evidence`，拒绝候选 |

该正例是**支持范围的条件样例**，当前真实来源台账仍缺扫描和人工绑定，因此并未实际输出“已授权”。

## L2 本地材料与 npm 边界

`parse_local_material` 只接受 64 KiB 以内 UTF-8 `LICENSE`/`LICENCE`/`NOTICE` 小文件及指定对象、精确版本、来源声明和内容 SHA-256。成功仅为 `text_observed`，`official_statement=false`、`applicability_human_verified=false`、`authorization_status=pending`。来源字段是上传者声明，孤立文件或口头声明绝不升级为官方授权。

仓库内不存在 `npm_acquisition.py`；此前 P2 分析日志也记载 PDF 所提本地模块未提供。B 仅实现离线 `parse_official_response`：固定 `is-number@7.0.0`、固定官方 URL `https://registry.npmjs.org/is-number/7.0.0`、32 KiB 响应上限、UTC 时间、响应 SHA-256、错误回执及许可证声明的待核验状态。**尚未发起 GET**；A 未冻结出口、超时和 DTO 之前不能把离线 parser 当作官方获取成功回执。无包下载、安装或其它 provider。

## D4 独立对账准备

目前只能确认三个固定上游 tag 的来源观察，不能给出真实“补证前后 Assessment 改变”的结论。待 A 提供同一 `scan_id` 的补证前后只读快照和 Evidence 闭包，逐样例核对：新增对象/版本/许可文本/范围事实的 ID 与 SHA-256；L1 条件候选增减；仍未知的包发布内容、适用性、用途、扫描覆盖和义务履行。`express@4.18.2` 在规则冻结后才用于独立对账，不参与调参。三例不是正式 Bench，也不是真人 Gold。来源不可重现或 Windows/POSIX 受限时，保留失败回执，不以另一来源补成成功。

## 当前离线回执与运行

`PYTHONPATH=backend .venv/Scripts/python.exe -m pytest -q tests/unit/test_p2b_candidates.py` 在本机为 `18 passed`。成功样例输出 `conditional_candidate`、`basis_evidence_ids=[ev-license, ev-scope]`、`rule_source=https://opensource.org/license/mit`；错误包、版本、对象、SHA-256、悬空 Evidence、超限、超时及不可信来源均有拒绝或失败回执测试。这里的 `ev-license`/`ev-scope` 仅为合成单元测试 ID，不是三个真实来源的 P0 Evidence。

未解决限制：P2-01 DTO/出口未冻结；未取得三个真实 ScanRun；未人工核验上游与发布包适用关系；未执行官方 npm GET；未形成 D4 补证前后正式对账或 A 接纳回执。

## 2026-10-08 续轮完整性复核

- L1 改为从调用方的 Evidence ID 列表和权威快照映射取证，拒绝悬空、重复及映射内 ID 被重标。快照本身的权威性仍由 A 的冻结接纳契约负责。
- L2 本地材料要求 `(scan_id, object_id)` 双键及精确版本在调用方快照中匹配；成功仍只证明文本观察。npm 离线 parser 即使收到固定 URL 字符串，也返回 `parsed_untrusted_transport`、`official_metadata_observed=false`，避免伪造官方 GET 来源。
- 再次通过 GitHub 固定 tag 文件接口逐一核对三个样例六个文件的 Git blob SHA-1，均与台账一致；package.json 分别声明 `is-number/7.0.0/MIT`、`lodash/4.17.21/MIT`、`express/4.18.2/MIT`。这是来源文件复核，不是 D4 正式 Assessment 前后对账。
- npm parser 可核对调用方给出的响应 SHA-256；不一致时拒绝。模型解释失败时，L1 保留已满足条件的确定性候选并显式给出模型缺口。
- 六个固定上游文件的内容 SHA-256 已补入机器台账；原文仅经 GitHub 文件接口读取并在内存中求哈希，未写入仓库。`npm_acquisition.py` 在仓库及 `F:\aic` 邻近目录均未检出，来源仍不可核验。

## 本轮 B 内部接线与拒绝矩阵（待 A 冻结）

`evaluate_bound_candidate(snapshot=..., object_id=...)` 增加了 B 内部只读快照入口。它要求同一次扫描、精确对象 ID/类型/版本、用途版本和七个三态用途字段、对象 Evidence 完整闭包、各 Evidence 的扫描/对象/版本与来源 SHA-256。成功只返回 `candidate_only`，并携带快照摘要、用途版本、规则版本、依据 ID 和逐依据来源摘要。调用方 A 必须认证快照及摘要；B 目前只能检查格式与内部闭包，不能验证自报摘要是否来自 A。旧 `evaluate_candidate` 保留离线 fixture 兼容，不作为生产接纳入口。

| 输入 | B 内部回执 | A 接纳要求 |
|---|---|---|
| 精确 MIT 软件对象、已核验原文与人工适用性/对象范围、显式用途 `true`、完整闭包 | `conditional_candidate`，含条件、依据 ID/来源 Hash、`rule_version=V4-MIT`；义务履行仍待核验 | A 重新校验快照、规则/用途版本及 Evidence，不转换为授权 |
| 某项用途 `null` | 该项无建议，`usage_<field>_unknown`；其他已明确且满足证据的用途可独立保留条件候选 | A 保持该项未知 |
| partial、AI 资产、根 LICENSE 用于依赖或范围证据不匹配 | 无相应用途候选，返回覆盖/独立许可/范围缺口 | A 不接纳超范围建议 |
| 悬空、重复、遗漏、重标 Evidence；错扫描/对象/版本；缺来源 Hash/用途版本 | `ValueError` 拒绝，无部分成功候选 | A 记录拒绝并保留原 Assessment |
| 模型解释失败 | 确定性条件候选仍在，另列 `model_explanation_unavailable` | A 不以模型失败修改确定性事实 |
| 本地同对象/版本 `LICENSE`/`LICENCE`/`NOTICE` 有界 UTF-8 文本 | `text_observed`、内容 SHA-256、`source_level=user_supplied_unverified`、`official_statement=false`、`authorization_status=pending` | A 负责安全上传、权威对象绑定、原子去重与人工适用性 |
| 本地材料同身份同内容或不同内容 | 分别拒绝为 `duplicate_material`、`material_identity_conflict` | A 用持久化历史原子判断并保留原版本 |
| npm 有界离线 200 JSON、精确 `is-number@7.0.0` | `parsed_untrusted_transport`、`source_level=untrusted_transport`，解析器版本 `p2b-npm-metadata/1`，license 仅 `provider_declared_unverified`，`official_metadata_observed=false` | 只有 A 可信出口回执通过后才可标记本次官方元数据已观察 |
| npm 超时、非 200、错包/版本、重复键、超限或 Hash 不符 | `failed` 或严格解析拒绝；`parse_official_response_receipt` 提供不含原文的失败回执 | A 记录实际 HTTP/失败原因，不提升来源或授权 |

`parse_attested_response` 是仅供 A 可信出口接线的内部适配器：要求 A 控制的 `verify_attestation` 验证回执，且固定 GET/URL/零重定向、策略 ID、响应大小/Hash 与 UTC 时间都通过，才标记该次 `official_metadata_observed=true`。合成单测中的验证器只测试状态隔离，不是实际可信网络证明；真实 GET 仍未执行。

本轮重新经 GitHub 固定 tag 文件接口取得六个原始文件字节，并用 SHA-1(`blob <长度>\0<原字节>`) 与 SHA-256 重算；六对摘要均与机器台账逐项一致。该核对证明的是上游 Git 文件身份，不证明 npm 发布包内容、扫描对象、许可适用性或义务履行。`source_object_key` 仍非 P0 对象 ID，三个 `scan_id`、`scan_object_id` 和 `evidence_ids` 保持空值。`express@4.18.2` 未用于本轮 L1 规则调整。

前端只需展示 A 返回的 `conditional_candidate`、`text_observed`、`provider_declared_unverified`、`pending` 与具体缺口文案；不得从文件名、MIT 字样或元数据成功推断授权。本轮尚无 A 冻结的 P2-01 DTO、可信 npm 出口、三个真实 ScanRun 与同 scan 补证前后快照，故 D4 仍待真实接线。字段和 A 拒绝条件详见 `CR-20261008-P2B-A-frozen-contract` 的接线补充。

`reconcile_object` 已提供只读的同扫描对象对账入口：拒绝跨扫描、对象身份变化、既有 Evidence 改写/删除、非目标对象变化和旧 Assessment/报告读回 Hash 变化；只列出新增 Evidence 的来源/内容 Hash、候选用途增减及解决/新增/剩余缺口。它尚未收到三个真实样例的 A 快照，单元测试中的 ID/Hash 均是合成值，不可作为 D4 正式通过回执。

下面是可直接传给 `evaluate_bound_candidate(snapshot=..., object_id="cmp-example")` 的**合成结构样例**。所有 ID 和 Hash 仅用于接口测试，绝非真实扫描或人工核验回执；实际接线时这些字段只能由 A 的权威只读快照提供。

```json
{
  "scan_id": "scan-example", "status": "completed", "coverage_gaps": [],
  "snapshot_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "objects": [{
    "id": "cmp-example", "scan_id": "scan-example", "kind": "component",
    "name": "is-number", "version": "7.0.0", "scope": "runtime_dependency",
    "evidence_ids": ["ev-license", "ev-scope"],
    "usage": {"version": "purpose-example-1", "values": {
      "commercial": true, "modified": false, "distributed": true,
      "network_service": false, "training": false,
      "redistributed_assets": false, "source_disclosure": false
    }}
  }],
  "evidence": {
    "ev-license": {
      "id": "ev-license", "scan_id": "scan-example", "object_id": "cmp-example",
      "version": "7.0.0", "role": "license_text", "source_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "content_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "source_status": "upstream_verified", "verification_status": "verified",
      "license_expression": "MIT", "applicability": "human_verified"
    },
    "ev-scope": {
      "id": "ev-scope", "scan_id": "scan-example", "object_id": "cmp-example",
      "version": "7.0.0", "role": "scope_attestation", "source_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "producer": "human", "verification_status": "verified", "scope": "runtime_dependency"
    }
  }
}
```

## 2026-10-09 真实样本交付审计与前端开工包

本节的机器可读交接草案为 `tests/fixtures/p2b/frontend-handoff-draft.json`。它的 `scan_id`、对象 ID、Evidence/Material ID、用途版本、补证后回执均为空；`source_object_key` 只索引固定上游 tag。**不得将此草案交给前端作为可验收的正式 API 输入**。A/Root 的 `CR-20261008-P2B-A-frozen-contract` 仍待冻结，当前工作区没有这三例的真实 ScanRun、P0 对象/Evidence 闭包或 A 的正式材料接纳记录。故“真实正例”目前只是**真实上游来源的条件正例**，尚不是正式扫描中的已验证正例。

### 三例身份、材料与引用链

三例精确名称、版本、用途声明、固定 tag URL、`package.json`/`LICENSE` 的原始字节 SHA-256 见 `real-source-index.json`；SHA-256 是 2026-10-08 历史回执，本轮未重新取得上游字节。六个材料的文件名分别为 `package.json` 和 `LICENSE`，固定版本分别是 `7.0.0`、`4.17.21`、`4.18.2`。历史获取方式是 GitHub 固定 tag 文件接口及内存中原字节哈希复算；**每文件 UTC 获取时间与原字节编码没有记录**，因而台账显式标空。尚未取得 NOTICE 原文字节；不能据此判定 NOTICE 不存在或无需保留。数据等级为 `fixed_upstream_tag_observation_not_scanned_evidence`，人工核验 `pending`。所列 MIT 是 package 声明和上游文件观察，不是 npm 发布包适用性结论。

| 用途 → 对象/版本 → 材料 → Evidence → Rule → 建议/缺口 |
|---|
| `distributed=true` → `is-number@7.0.0` → 固定 tag 的 `package.json` 与 `LICENSE`（哈希见台账）→ **真实 Evidence ID 缺失** → `V4-MIT` 仅待核 → `real_scan_binding_missing`、原文适用性/范围/履行待核；不得展示正式条件建议。 |
| `distributed=true`、部分用途未知 → `lodash@4.17.21` → 固定 tag 两文件 → **真实 Evidence ID 缺失** → `V4-MIT` 不可泛化 → 文档示例代码与 `node_modules`/`vendor` 需分别识别条款，保留 `file_scope_unverified`。 |
| `network_service=true`、其他用途未知 → `express@4.18.2` → 固定 tag 两文件 → **真实 Evidence ID 缺失** → 规则冻结后的独立 D4 对账，不参与 L1 调整 → `independent_reconciliation_pending`。 |

### L1 字段来源和条件

| 字段 | 来源/阶段 | 空值、冲突和版本语义 |
|---|---|---|
| `scan_id`、`status`、`coverage_gaps`、对象 ID/`kind`/`name`/精确 `version`/`scope`、完整 `evidence_ids`、Evidence 绑定及 `source_sha256` | A 权威只读 ScanRun/扫描自动发现，B 只读核对 | 身份缺失、错扫描/对象/版本、悬空/重复/遗漏 Evidence 或来源 Hash 无效：B 拒绝；`partial`/覆盖缺口：无候选。A 尚需冻结快照认证与内容摘要算法。 |
| `usage.version`、七项三态用途 `commercial`、`modified`、`distributed`、`network_service`、`training`、`redistributed_assets`、`source_disclosure` | A 版本化用户用途输入；不是扫描自动发现 | 版本或字段缺失：拒绝；单项 `null`：该项 `unknown` 且无该项建议；`training=true` 或 `source_disclosure=true`：超出 L1 矩阵。 |
| 许可证表达式、原文 `content_sha256`、`source_status`、`verification_status`、人工 `applicability`；人工 `scope_attestation` | 扫描/材料观察 + 解析器标准化 + 人工补充；A 负责正式采用 | 只有同对象/版本的 `MIT`、上游已核来源、原文 Hash、`verified`、`human_verified` 与人工同范围证明同时成立，B 才产生条件候选；已核验文本或范围互相冲突则 `license_evidence_conflict`/`object_scope_conflict`，无候选。`pending` 只保留观察，`unknown` 保留缺口。 |
| `basis_evidence_ids`、`basis_source_sha256`、`rule_version=V4-MIT`、条件/剩余缺口 | B 确定性候选解析器；规则来源为 OSI MIT URL | 内部 `candidate_only`，不是 A 接纳、授权或义务已履行；模型建议只能作为解释层，模型失败保留确定性结果并增加 `model_explanation_unavailable`。 |

`parse_local_material` 版本为 B 内部 `openguard.p2b.local-material/0`：只处理同一真实扫描对象和精确版本绑定的 64 KiB 内 UTF-8 `LICENSE`/`LICENCE`/`NOTICE`（可带受支持文本扩展名）。`license_mention` 仅是文本观察。当前仓库**没有可绑定真实 ID 的本地 LICENSE/NOTICE 样本**，故不得用合成测试 ID 伪称已提供。生命周期必须分别记录：字节已提供、B 已解析、A 正式接纳、人工核实义务已履行；前一步不会自动推出后一步。同名同 Hash 和同名不同 Hash 的拒绝只是 B 预检，A 需原子去重并持久化。

### 负向实际回执与 A 依赖

B 单测逐项验证：错 resource ID/版本、悬空/重复 Evidence、已核验许可文本冲突、范围冲突、材料重复/同身份冲突、超时、提示词注入文字、metadata 自称 `verified`、训练范围 Evidence 用于分发用途、孤立材料拒绝或仅保持 `pending`。错绑在 B 内部拒绝；**A 服务端拒绝、旧 Assessment/报告原样读回以及人工/TEST_ONLY 样本不进入正式发现，仍需 A 的真实回执**。`reconcile_object` 只能用 A 签发的补证前后快照及旧工件读回 Hash 验证同一扫描、受影响对象与历史不可变性；当前仅有合成单测。

可信 npm 仍为 `blocked_awaiting_trusted_egress`：固定目标 `GET https://registry.npmjs.org/is-number/7.0.0`，本轮没有实际请求、最终 URL、UTC 时间、HTTP 状态、响应 SHA-256/大小或出口策略 ID。A/Root 先冻结 DNS/代理/重定向/超时/字节上限和可信回执验证器，再由 A 执行唯一在线 GET；B 只解析 A 可信回执。离线 parser 版本 `p2b-npm-metadata/1`；metadata 的 license 永远是 `provider_declared_unverified`，不提供 LICENSE 原文、授权或义务履行证明。

前端只消费 A 正式 ID、版本、状态、引用和允许展示的条件建议。联调草案里的 `before` 是**预期缺口形状**，`after=null` 表示无正式补证回执，`display_advice=null` 表示当前没有可展示的正式建议。A 需给 B/前端逐例正式 `scan_id`、对象/Evidence/Material/Rule ID、用途版本、核验状态、接纳或拒绝、Assessment/报告前后 ID 与 Hash 和旧版本读回结果，才可替换草案并签收。

## 2026-10-09 B 侧闭包与 A 输入核对

| 输入或回执 | 状态 | 当前证据位置与含义 |
|---|---|---|
| 三例固定上游 tag 的 package/LICENSE URL、Git blob SHA-1、原字节 SHA-256 | 已取得 | `real-source-index.json`；2026-10-08 历史原字节复算，采集 UTC 时间未记录。仅为上游来源观察。 |
| B 离线 L1/L2/npm/D4 解析与拒绝 | 已取得 | `backend/app/p2b/` 和 `tests/unit/test_p2b_candidates.py`；测试 ID、哈希是合成 fixture。 |
| P2-01 冻结快照 DTO、快照认证、用途版本、A 候选接纳 DTO | 未取得 | `CR-20261008-P2B-A-frozen-contract` 仍标待 A/Root 冻结；草案字段不得替代。 |
| A 材料原子接纳、服务端拒绝与旧工件读回 | 未取得 | 无三例真实 Material ID、服务端接纳/拒绝和 Assessment/报告读回回执。 |
| 可信 npm 出口策略、验证器和唯一 GET 回执 | 未取得 | `frontend-handoff-draft.json` 的请求时间、HTTP、响应 Hash、策略 ID 仍为空；`official_metadata_observed=false`。 |
| 三例真实 ScanRun、P0 对象/Evidence 闭包及同 scan 补证前后回执 | 未取得 | `real-source-index.json` 与交接草案的真实 ID 为空；不能做正式 D4 对账。 |

本轮只读对账器除用途候选新增/删除外，还列出同一用途的依据变化 `suggestions_updated`，以及前后 `basis_evidence_ids`/`basis_source_sha256`。新增 Evidence 的 `content_sha256` 若给出，必须是规范小写 SHA-256；既有 Evidence 删除或改写、非目标对象/证据变化、旧工件读回哈希变化均失败关闭。它仍不签发正式 Assessment，也不证明自报快照或旧报告摘要的真实性；A 必须提供可信只读回执。机器交接草案新增字段来源和待 A 回执占位，所有正式 ID 继续为空。

新增 Evidence 内容摘要格式错误使用 `invalid_added_content_hash`；旧 Assessment/报告读回摘要格式错误使用 `invalid_readback_hash`。两者都不给部分成功的对账结果。

`evaluate_bound_candidate` 另接受可选的 `expected_scan_id`、`expected_usage_version` pin；与内部快照不符时分别拒绝 `snapshot_scan_mismatch`、`usage_version_mismatch`。生产调用时只有 A 能从已认证 ScanRun 与已版本化用户用途签发这两个值，B 的比较不验证签发者。现有合成测试仅检验错绑拒绝，不构成真实 P2-01 DTO 或接纳回执。
