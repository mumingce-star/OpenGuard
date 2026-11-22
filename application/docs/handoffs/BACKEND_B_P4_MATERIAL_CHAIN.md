# 后端 B 首条真实材料支持链

状态 PARTIAL。基线 `codex/delivery-20261030@2cc7f63`。业务范围采用本轮用户所附详细任务。当前可见仓库、会话附件和按名称检查的项目资料中未定位《OpenGuard 国赛阶段项目技术规划书 P3—P7 V1.0》原件，仍需按原件补核阶段编号与门禁。

## 当前能力盘点

| 能力 | 文件或入口 | 输入 → 输出 | 测试与状态 | 缺口及下一步 |
|---|---|---|---|---|
| 资源发现与角色 | `backend/app/scanners/javascript_manifest.py`、`backend/java/…/scan/RepositoryScanner.java` | 清单、有限文本 → 依赖、声明位置、AI 资源引用 | 部分实现；JS CLI 回归存在独立参数失败 | B-P4-01 待将声明、导入、构建与交付线索映射到 observed/inferred/unknown 并保留冲突 |
| 依赖版本和锁文件 | `backend/app/scanners/javascript_manifest.py`、`javascript_p0_mapper.py`、`backend/app/pipeline/manifest_licenses.py` | package.json、npm lock v2/v3 → 直接依赖版本、P0 证据、显式许可声明 | 部分实现；现有 JS CLI 用例覆盖声明与锁版本 | 缺少当前用途/交付证明；pnpm、Yarn、Python 锁格式未纳入本轮 |
| LICENSE / NOTICE | `backend/app/p2b/materials.py`、`backend/app/detectors/license_notice_facts.py`、`backend/app/p1/notice_facts.py` | 受限 UTF-8 字节或固定事实包 → 文本观察、候选、缺口 | 已实现且有验证；本轮重跑 P1 detector、P2B 候选、材料回放和回执 | 继续复用候选接纳与人工范围核验。NOTICE 义务和附加条款未接此适配器 |
| SBOM | `backend/app/scanners/syft_pipeline.py`、`external_tools.py` | 受控 Syft JSON → 组件、版本及证据 | 部分实现；本轮映射测试有结果，真实可执行工具用例跳过 | SPDX JSON 与 CycloneDX 通用输入仍需另定版本和限制 |
| 规范化与规则 | `backend/app/licenses/spdx.py`、`backend/app/rules/engine.py` | SPDX 标识/别名及证据 → 规范表达式、待核义务/风险 | 已实现且有验证；B5 本轮 10 项通过 | 现有解析保留平面 AND/OR；WITH 不支持。私有映射对所有组合拒绝生成单条条件主张 |
| 版本与范围绑定 | `backend/app/p2b/offline_material_audit.py`、`_apache_redistribution.py` | 既有回执，或精确 Subject、受审核绑定、证据字节 → 审计或条件链接 | 部分实现；固定真实原件正例、错版/跨对象/越范围反例本轮通过 | 后端 A 接纳不可变来源，提供同快照和用途事实 |
| ClaimLink 等价关联 | `backend/app/p2b/_apache_redistribution.py` | 绑定与规则 → 同对象/版本/范围下的条件主张、原文及规则定位 | 部分实现；单条 Apache-2.0 §4(a) 私有链接 | Sol 复核语义，A 决定正式表示与引用闭包 |
| Requirement 等价缺口 | 同上及既有 P2B 候选 | 绑定、材料或用途不足 → 对象、原因与后续动作 | 部分实现；本轮覆盖缺材料、不支持、冲突、事实缺失、解析失败和有依据的不适用 | A 复核多对象聚合并保存所有受影响 Subject；其他用途和义务待接入 |
| Benchmark | `benchmarks/p2b_offline_material_audit.py`、`p1-fixed-repositories/`、`examples/v2/` | 既有回执、准备清单、合成治理示例 → 离线审计/门禁校验 | 独立条件建议 Bench 未实现；新增开发证据见 `benchmarks/p4-material-chain-development.md` | Luna 与真人复核者获取分离的样本和标签 |
| 后端 A 接口 | `backend/app/p2/contract.py` 与 `service.py` | P2 Material、Evidence、Result → 既有 candidate_only | P2 候选已接现有工厂；本轮适配器仅离线 | 采用下节输入映射后跑真实工厂、Store、HTTP 和浏览器签收 |

## 接收方使用说明

`assess_redistribution` 是私有 Python 入口。继续使用 P2 `Subject` 和 B5 `RuleSet`。本轮支持绑定的第一方代码与文档、40 位 Git 提交、特定完整 LF 文本的 SHA-256、README 范围声明和单一 Apache-2.0 许可。解析器限定每份字节材料最多 64 KiB UTF-8。它接收已经读取的字节，不打开路径、处理归档或读取网络。

后端 A 从有权限的证据仓和审核记录组装 `ReviewedBinding`。资源 ID、不可变提交、范围、证据 ID、路径和 SHA-256 必须源于同一受审核对象；声明来自已有 SPDX 证据。组件的名称、用户输入的版本/Hash 或上传回执本身都不足以创建此绑定。调用方还负责用途事实及会影响关联结果的反证检查，尤其是不同来源间的冲突和单独补充条款。当前适配器校验已传入的引用与文本，真实性及外部反证范围依赖 A。

| 输入例 | 私有输出 |
|---|---|
| 样本对象 `openguard:first-party`、版本 `2cc7f63a812561bf71de11d2041e4027a345efda`、范围 `first_party_code_and_docs`、用途 `distributed`、场景 `planned`，引用解析到两份固定原件 | `conditional`，`provide_license_copy_to_recipients_if_redistributed`；规则 `LIC-APACHE-2.0-NOTICE@1.0.0`、规则集摘要、第 4(a) 条和范围声明原文定位。实际交付、义务履行、其余条款待核 |
| 请求同名另一提交、`npm:express` 或全依赖范围，仍复用该绑定 | `review_required / evidence_conflict`，拒绝链接 |
| 原件缺失或引用无法解析，或来源原件与固定 Hash 冲突 | `missing_material` 或 `evidence_conflict`，拒绝链接 |
| 使用方式未知，或用户声称排除资源而缺经核实记录 | `user_fact_missing`，拒绝链接 |
| 调用方提供经独立核实的未再分发事实，同时交付范围证据可解析且 Hash 一致 | `not_applicable`，保留适用性证据引用，此路径仅有合成回归 |

当前公共 API、DTO、Schema 和 Store 无变更。最小接入请先在 A 内部读取和校验来源，再把私有输出映射为既有候选状态及证据引用。若需要对前端暴露用途、字节区间、规则集摘要或结构化缺口，请由公共契约负责人先审核字段需求；旧客户端沿用现有字段。接入测试按来源真实性与权限 → 引用闭包 → 同版工厂候选 → 存储回读 → 前端验收执行。未授权、错对象、错版本、冲突、未知或缺件均需可观察且保持候选边界。后端 A 负责安全读入测试，覆盖恶意归档、路径穿越及软链接逃逸。

本轮复用仓库自有 LICENSE、README 和规则，未新增第三方资源或运行时依赖。Sol 复核条款与缺口语义，Luna 复核标签及独立样本管理，Root 验收并发布。

## 2026-11-14 后端 A 接入增量

此前段落记录 §4(a) 基线。本节描述当前私有模块。前端 F-P3-04 评审稿用于核对 B1/B2 接收项。正式 PurposeAdvice 字段、组合版本 manifest、同版接口与浏览器回执仍待对应负责人确认。

### B-P4-01 角色与格式

`assess_resource_roles(components, evidence, manifests=..., facts=..., import_sources=...)` 接收同一扫描快照的 P0 对象、两个清单映射结果及已授权事实。每条结果含组件 ID、版本及 4 个角色。每个角色有状态、源类型、定位、已有 Evidence ID、可用的 SHA-256 和行号。冲突保留代码及原诊断位置。声明字段 `observed` 指字段已观察，Python `build-system.requires` 对构建使用为 `inferred`。只有 lock/SBOM 的依赖归属为 `inferred`，其交付角色为 `unknown`。正负事实冲突为 `unknown`，保留两条证据和极性。

| 输入 | 当前支持范围 |
|---|---|
| `pyproject.toml`、`requirements*.txt` | 沿现有 Python parser/mapper 的可定位声明；构建要求来自 `build-system.requires`。精确 requirements pin 依然按 manifest 处理 |
| `package.json`、`package-lock.json` v2、v3 | 沿现有 JS parser/mapper 的直接依赖及可绑定的相邻 lock 条目；附根字段冲突、精确版本冲突及声明冲突 |
| npm lock v1、`npm-shrinkwrap.json`、`pnpm-lock.yaml`、`yarn.lock`、`poetry.lock`、`uv.lock`、`Pipfile.lock`、`pdm.lock` | 当前私有纵切无独立解码器。Syft 可能报告对应路径，角色入口按 SBOM 来源保留 |
| Syft 原生 JSON（`syft-json`，已有 mapper） | 复用 `artifacts`、PURL、版本和相对位置。覆盖本轮合成映射，已有真实工具测试的目标版本为 1.51.0 |
| SPDX JSON/tag-value、CycloneDX JSON/XML | 直接输入及独立版本验收待扩展 |
| Python 导入 | 多份受审核、有 SHA-256 的 UTF-8 `.py` 文件，每份最多 256 KiB，AST 静态绝对 import/from-import。A 显式绑定模块根到 P0 组件，保留具体行号。动态导入、JS/TS 语法识别及自动模块归属待扩展 |
| 构建／交付 | 可消费已审核 `BoundRoleEvidence`。交付要求精确版本；P0 Evidence 必须是已核验证据并带 SHA-256。产物解析和执行事实由来源维护者提供 |

例：`package.json:/dependencies/@scope~1lib` 配合 `package-lock.json:/packages/node_modules~1@scope~1lib/version` 得到该组件的声明 observed，构建、导入、交付为 unknown。若清单精确版本与 lock 条目冲突，声明为 unknown 且保留冲突字段。例：`PIL → Pillow` 必须由 A 显式绑定，`src/main.py:1` 的 `import PIL.Image` 给 Pillow 一个 observed 导入位置。实际运行和交付分别由运行记录与审阅过的交付事实确认。

### B-P4-02～05 材料、主张和缺口

继续从授权的同一固定快照装配 `Subject`、`ReviewedBinding`、`EvidenceRef`、字节和 `RuleSet`。A 核查读权限、路径安全、证据来源及引用闭包，并检查同一用途下的反证、单独条款和不同来源冲突。对 `planned_distribution_evidence`、`modified_files_evidence`、`no_distribution_evidence`，用审核记录的资源 ID、Git revision、scope 与证据引用创建 `ReviewedUseFact`。每个引用的 ID、相对路径和 SHA-256 均以来源登记为准，并保留完整的原件或审核记录。适配器校验同对象、版本、范围、引用解析和字节，事实含义与证据所属场景由 A 的审核记录确认。A 接入正式候选时为计划事实提供可回读的用途引用。历史 §4(a) 自报计划示例可省略该引用，此时方案是情景输入。

| 私有调用示例 | 私有结果与接收动作 |
|---|---|
| 固定对象与范围、`distribution="planned"`、`clause="4(a)"`，引用两份原件 | `conditional`，向接收者提供许可证文本的条件提醒。规则 ID/版本/摘要、原文区间和适用范围区间随链接返回 |
| 同对象、版本与范围，`clause="4(b)"`，增加 `modified_files_evidence` 和原字节 | `conditional`，随计划交付对修改文件保留显著修改说明；精确 LICENSE 原文为第 97–98 行，[5322, 5432) |
| 同上，§4(b) 缺修改事实 | `review_required / user_fact_missing / modified_delivery_scope_unknown`，确认计划交付的修改文件与范围 |
| `distribution="verified_absent"` 且存在同对象、版本和范围的经审核排除证据 | `not_applicable`，返回排除依据。当前仅有合成例；A 验证范围和证据 |

| 缺口类别 | 接收方动作 |
|---|---|
| `missing_material` | 补同快照绑定、原件或 Evidence 字节；保持待核 |
| `evidence_conflict` | 核对对象、版本、范围、证据路径/Hash 或声明冲突；阻断采用 |
| `user_fact_missing` | Owner 确认计划用途、修改范围或可核验排除证据 |
| `parse_failure` / `unsupported` | 补可解析 UTF-8 或交 Sol 审核完整文本、组合表达式、条款映射及规则版本 |

选用现有 candidate_only 流程。待核结果消费已有候选状态和可用证据引用。需完整对外表达时，请契约负责人评估以下字段需求后再纳入协议：用途情景和事实 Evidence ID、条款原文起止字节与行、规则集摘要、缺口类别／原因／动作、排除依据 Evidence ID。多对象结果以资源 ID 和不可变版本保留各自条件或缺口。Sol 复核语义及 §4(b) 映射。Owner 或指定责任人核实授权、实际交付和履行。

接收顺序为 A 验授权读取与来源绑定，A 用同版正常工厂执行和 Store 回读，A 签实际 HTTP 正反例，前端对同版本和用途核对状态、证据定位和恢复。Root 验收组合版本和发布。命令、机器结果及可直接组装的 `EvidenceRef` / `ReviewedUseFact` 示例见 [开发评测](../../benchmarks/p4-material-chain-development.md) 与 [重放入口](../../benchmarks/p4_material_chain_development.py)。
