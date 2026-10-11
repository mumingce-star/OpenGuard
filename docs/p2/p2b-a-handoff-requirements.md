# P2 B 限定离线开发：后端 A 精确交接缺口

日期：2026-10-11；状态：PARTIAL，待 Owner 复核，未授予发布授权。

Owner 已允许 B 提前开展限定离线开发，使用
`codex/p2-stage1-backend-20261010@afca4c26c2fa45fa285fc9cabf48f52c54a59229`
的 P2 v1 合同及 Schema 作 TEST_ONLY 兼容基线。此确认不批准生产、破坏性 Schema
变更或 Formal 新政策。A01—A09 不再是 B 离线工作的串行开工前提，A02/A03/A05
涉及的正式证据、来源和存储闭环仍是独立门禁。本文按具体能力列缺口，不代 A 重定义工作包。

`is-number@7.0.0` LICENSE 已取得；不再索要或抓取原件。其现有摘要
`35bdd8a44339719441900fb50fbefc5e2dca1ca662cbaed7a687de842c8b70f2`
及 Material ID 保留，旧观察不计新增事实。B 本次本机可读资料是公开回执元数据，
没有定位到对应原字节；不据此声称原件未取得，也不伪造条款定位成功。

## A 已有接口，继续复用

前缀 `P=/api/v1/scans/{scan_id}/assessments/{assessment_id}/p2`。

| 接口/对象 | B 精确需求 | 当前限制 |
|---|---|---|
| GET `P/binding` / Binding | 完整 scan_id、assessment_id/version、registry_revision、project_revision、facts_hash、usage_hash、rule_version、assessment_sha256 | 全字段精确 pin；null 不推断；B 本次离线核对已有回执 |
| GET `P/results/{result_id}?assessment_version=N` / Result | 固定身份、revision/前驱、result_sha256、七用途原值、资源证据与材料闭包 | 禁止 latest 替代；revision 不改 Formal version |
| GET `P/materials/{material_id}?assessment_version=N` / Material | 原 subject/version、来源内容 Hash、byte_count、pending/source_level | 元数据 GET 不返回正文；保存成功不是来源核验 |
| GET `P/results/{result_id}/summary?assessment_version=N` / Summary | 同 result ID/revision/hash 与 Binding | companion 不代 Formal Report |
| POST `P/results`、`P/materials`、`P/answers` | 原 CAS、父 result、幂等键/原 body；失败时保留旧对象 | 本次 B 不调用、不新增版本、不补真实用途 |

已有三例完整 ID、精确路径与父绑定见 `p2b-evidence-closure.json`；没有要求 A 重造扫描或重发旧材料。

## 仍需 A 提供的接口合同及材料

以下是**待 A 确认的交接要求**，不是已存在的新路由；不向严格 P2 v1 DTO 偷添字段。

| 独立门禁 | A 需交付的精确字段/材料 | B 收到后的离线验收 |
|---|---|---|
| 可信来源签发 | 受信签发入口/只读精确 GET 合同，receipt_id/version/hash、issuer/policy ID 与版本、UTC、accepted/rejected/conflict/revoked 状态；绑定 scan/resource/name/ecosystem/精确版本、父 Binding 与原文 SHA/大小 | 检查签发路径、身份和版本/摘要；上传者自报 verified 一律不能代替 |
| 不可变来源与发布包关系 | repository 与不可变 commit、文件相对路径/blob SHA、原字节 SHA/大小；npm 精确版本发布归档 digest、清单/文件 digest、LICENSE 与范围关系依据，保留排除项 | tag/URL/同名同版本不当作发布包适用性；错版本、摘要冲突、撤销缺口保留 |
| 独立 Evidence 物化/存储 | A 明确新 Evidence 命名空间/表或正式策略、receipt 引用、license_text/scope_attestation 角色、source/content hash 区别、只读 GET、Result basis 引用闭包及原子 CAS | 旧 Evidence 不覆盖；新增依据 ID/Hash 可逐项读回；不由 B 写入 ScanRun 或伪装签发 |
| coverage 与候选规则溯源 | scan_status/原 errors/coverage gaps 到 Result 的完整映射，父 Formal rule_version 与 B V4-MIT 的版本/来源关系 | 提前返回也保留 rules_stage_not_connected；不能把 facts_hash 当 B snapshot_sha256 |
| npm 元数据观察接入 | A 冻结 observation DTO 与 Result/Evidence 绑定策略；未来获授权时，唯一 GET `https://registry.npmjs.org/is-number/7.0.0` 的 request/final URL、GET、零重定向、UTC、HTTP、timeout、原字节大小/Hash、policy ID | 本次不联网；未来官方声明仍 provider_declared_unverified，不是已核验许可 |
| 旧 Formal 读回 | 完整原 Assessment 正文/身份版本/确切序列化与 Hash；旧 Formal Report ID/格式/原字节 digest/只读固定 GET 及授权范围 | 不能用六字段投影复算完整 Assessment；不能用 Summary 或重渲染报告替代旧字节 |
| 错误/恢复与支持环境 | 固定兼容提交、获准 TEST_ONLY 数据根或等价只读包；冲突/撤销/缺失/失败保存后的旧对象读回；Windows 与 NOTICE 父本失败独立结果 | B 仅在授权环境验证；不以当前 120 项 B 测试覆盖 A Windows setup 阻断 |

## Owner 单独确认，A/B 不代填

真实用途七字段保留当前保存的原值；本次三例全 null。真实交付资源集合、范围选择器及
排除项、适用性决策和义务履行需独立真实核对，可以是未知、拒绝或不适用，
不要求肯定许可结论。Owner 范围确认应引用 A 有效来源回执和原文 Hash；A 签发来源
不自动确认交付范围，范围确认也不自动证明声明/NOTICE 已随副本交付。

在以上独立门禁关闭前：B 可继续离线条款定位、差异核对、负例和缺口分析；
新增已验证正向许可结论为零。express 保持独立未用于调参；前端接收机兼容与浏览器
签收、正式模型生成、生产写入、Formal 修改、合并和部署均未获本次授权。
