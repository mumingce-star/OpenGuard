# cz：P1扫描、Detector与Bench接续交接

责任划分：cz负责扫描分析领域；负责人负责架构、公共Domain/API、Pipeline集成、Formal Assessment与正式交付；xzb负责前端。以下是负责人在cz已有扫描成果上为P0收口完成的集成与增强，不覆盖cz原贡献，也不授权从旧分支整包回灌。

## 共同冻结基线

OpenGuard P0：**CLOSED**；R1A、R1B-A：CLOSED。负责人已批准由P0收口进入P1交接，P0不再作为功能开发主线。

- 完整源码基线：`36d1b794909bf2e655e5968e1a8b3eb03a27bc15`（`origin/integration/p0`）。本分支包含完整Domain、API、Pipeline、Assessment、Rules、Frontend、Tests、Deploy，不是裁剪目录。
- 已验收生产基线：Detector **0.2.0**；Rules **2026.09.2**；STEP6.1 **2 / 192 / 384**（history / question bytes / answer bytes）；ScanCode **32.5.0**；Syft **1.51.0**。
- 已验证产品主链：Git / ZIP → inventory → ScanCode / Syft → AI Asset Detector → Rules → Formal Assessment → Qwen Explanation → Frontend / Report。本次交接不重新运行上述验收。
- 最终真实Git A/B：`huggingface/smolagents@30bb1161095dbae2271e6bc3cc4c219cc3897a57`，旧scan `scn_cd5920ca-d5ae-42c7-a168-1fe01daa9bb7`，新scan `scn_a5bd2a99-ac84-4743-8530-5e3dc4ef033f`。组件80→80，AI资产6→16，证据203→240，发现86→96；原6资产全部保留，新增10个模型有真实源码AST证据。两次均partial，原因是同样的依赖解析限制，不是无条件全覆盖成功。
- 正式数据在最终验收时为111 scans / 20 assessments；这是时间点快照，不保证以后数量不变，且Git checkout不包含本机生产数据库。
- 异机验证完成：**依据负责人本次交接确认**；本轮只做文档与分支发布，没有重新执行Windows验收。不要把这句话用作本轮Windows实测回执。
- 本机入口从OpenGuard首页开始：`http://127.0.0.1:5174/`，正式API为8011。127.0.0.1指使用者自己的电脑；组员需要按仓库部署说明启动本机服务，不能直接访问负责人的Mac服务。

## 负责人已完成的P1前置工作，以及尚未完成的契约

1. **P0正式冻结**：主链收口、生产0.2.0恢复、真实Git A/B已通过，有稳定基线；生产恢复采用fresh container，原异常容器、rollback与历史数据保留。不得自行重启或替换生产。
2. **Formal Assessment分层**：不可由展示层修改的Scan facts与版本化Formal Assessment分离；保留conditional、restricted、unknown、not_applicable等正式状态的原语义。
3. **项目评估产品路径**：Usage Declaration、Project Assessment、Review Groups、Evidence grounding、Qwen解释已具备。P1提高管理、可视化、历史、协作、整改和报告价值，不重新发明扫描后的基础结论页。
4. **真实历史数据基础**：111 scans / 20 assessments可为后续History、Diff验收提供真实案例，但公共列表和Diff契约仍须冻结，不能因数据库已有记录就宣称History/Diff已实现。
5. **Detector 0.2.0**：由URL/static pattern扩展到受限制的AST structured detection，并通过真实Git；后续增量必须Bench-driven。
6. **Bench基础**：已有真实标注、human review、AI-assisted draft、FN分类与source checks。历史artifact指标不等于当前Detector live performance，人工单人复核不等于Verified License；Bench数据不得进入Formal Assessment事实层。
7. **P1方向**：从扫描器与合规结果页升级为“AI开源项目合规工作台”。本轮没有P1功能编码。
8. **公共对象尚待负责人Contract Freeze**：ScanHistoryItem、ScanDiffView、ResourceGraphView、ResourceProfile、RemediationTask、NoticeDraft、ReportV2Snapshot。仅为规划名称，不是已发布Schema或API。

统一顺序：P1-0 Contract / Schema / Feature Boundary Freeze → P1-1 History + Diff → P1-2 Bench 2.0 + ResourceProfile facts → P1-3 Resource Graph → P1-4 Remediation Tasks → P1-5 NOTICE / License Draft → P1-6 Report V2 → P1-7 CI / performance / competition evidence。不要抢先实施后面的功能。

## 权威层级与共同边界

**Scan facts > Formal Assessment > P1 Review / Graph / Task / AI / UI**。

- Unknown != Prohibited；Unknown != Allowed；Pending != Verified。
- Detected License != Authorization；Root License != Dependency License；File observation != blanket grant。
- Finding != confirmed violation；Obligation detected != obligation violated。
- AI explanation != Formal Assessment；Graph != Formal Assessment；Task completed != Compliance verified。
- History/Diff !=重新扫描；GET != Scanner/Qwen invocation。
- 产品正常终态会自动产生Initial Assessment，并可能触发一次标准Qwen整体解释。后续验收先看Scan facts，再独立验收自动评估；不额外生成重复评估/Chat。Qwen属于解释层，不能提升事实或授权等级。
- Assessment的rule_version实际为评估引擎版本、许可证规则版本与摘要组合；不要误以为一定是裸字符串2026.09.2。

## Git协作规则

旧`feat/xzb-frontend`及`codex/license-rule-p0-fixes`、`codex/p0-external-tools-sync`、`codex/scan-reliability-integration`仅作历史参考，不是P1起点。禁止整分支merge回新线。若有未采用的独立有效成果，先逐commit审计，由负责人另行决定是否cherry-pick；本次未执行。

不要向`integration/p0` push。不要创建`integration/p1`，等A-P1-01冻结后由负责人决定集成方式。本分支小步提交；PR说明：做了什么、原因、测试、公共接口影响、新增依赖、第三方许可证影响、Bench影响、P0 regression。不得覆盖别人未提交成果，不force push，不擅自修改模型、API、数据库、生产Volume或部署配置。

本交接提交仅新增当前角色handoff文档；产品代码与P0基线一致。第一批交付为只读复核报告，后续功能需要按公共契约边界推进。

## P0后期负责人在扫描侧的集成与增强

1. ScanCode/Syft进入正式Git/ZIP Pipeline；保留有界扫描、安全隔离、覆盖状态和Evidence。
2. Rules Engine与Formal Assessment分层集成；SPDX AND/OR组合表达、license evidence完整性与fail-closed保护（参见`b933847`）。
3. Root License不能传递给Dependency或AIAsset，detected不能提升为authorization。
4. R1A Hugging Face canonical URL识别（`dfbde05`）；保留datasets等正确资源身份，不把站点普通路径误认模型。
5. Detector0.2.0受限structured AST检测（`36d1b79`）。代表性支持：smolagents.InferenceClientModel、smolagents.TransformersModel、明确绑定的LiteLLM Anthropic messages与Google GenAI调用。**以structured_models.py的精确白名单和测试为准，不是支持整个SDK所有动态调用。**
6. 支持Python Markdown fenced code并保留原Markdown locator/行号；不执行目标代码。
7. provider表达资源identity ecosystem，而非运行服务：`InferenceClientModel(model_id="deepseek-ai/DeepSeek-R1", provider="together")`归属huggingface，不能归属together。
8. AST＋URL合并为一个资产并合并Evidence；只有真实URL证据才保留canonical source_url，AST-only可为None，禁止拼造URL当证据。
9. 最终smolagents同revision A/B：6→16资产，原6全部保留；FN-07 README87行，Distill-Qwen-32B英文inspect_runs.md185行，均pending。行号仅该固定revision的验收记录，不得硬编码Detector。
10. 真实资源Bench、人工/AI辅助标注安全迁移（`b39e2c4`）、固定源码回放和FN分类已提供基础。Detector0.2.0固定回放曾得到TP16/FP0/FN34；这是指定50条固定集口径，不是任意仓库的准确率保证。

### 先读当前代码与证据结构

- `backend/app/scanners/`、`backend/app/detectors/`，重点static_assets.py和structured_models.py。
- `backend/app/licenses/`、`backend/app/rules/`、根`rules/`。
- `backend/app/pipeline/`：external_scans.py、ai_assets.py、license_rules.py及Git/ZIP集成。
- `benchmarks/`，重点`annotations/real-resource-20260911-ai-assisted/`内README、manifest、迁移回执、human review、AI draft和source checks，以及当前`benchmarks/evaluate.py`。
- `tests/unit/test_b6_static_assets.py`、`tests/unit/test_b6_structured_ai_assets.py`、`tests/unit/test_benchmark_actual_static_assets.py`。

禁止从旧scanner分支重新开始；不要重设计P0 Domain、自改FastAPI公共契约或Formal Assessment定义。不得用LLM做确定性发现或猜license/hash/version/provider/文件存在性。扫描性能不能靠少扫描、放宽安全、隐藏partial或删Evidence制造提升。

## P1扫描侧任务次序

|任务|目标、证据和边界|
|---|---|
|B-P1-01 Bench 2.0（首优先级）|逐步扩展20–30个真实AI开源仓库；区分development/training与holdout。按package/model/dataset/api分别报告TP/FP/FN、Precision/Recall/F1，不只汇总总分。Gold记录来源、revision、标注者、review状态、修改历史；先复用现有结构。|
|B-P1-02 FN Taxonomy|按high-value、low-risk、deterministically detectable排序。新规则必须先真实FN→规则设计→fail-first测试→实现→固定Bench replay，禁止仓库allowlist或项目特例刷分。|
|B-P1-03 ResourceProfile facts|提出model/dataset identity、provider、revision/version、card locator、license metadata observation、source metadata、evidence IDs、confidence/verification status。先交负责人字段提案，批准后才改公共模型。|
|B-P1-04 Remote Metadata Enrichment|可研究HF Model/Dataset Card，但先设计Trusted Egress、缓存、版本绑定、Evidence producer、timeout、fallback、metadata provenance；远程失败不能让扫描失败。不得在事实扫描层偷偷联网，负责人批准前不编码。|
|B-P1-05 Rules质量|用真实Evidence与Bench推动常见组合、义务映射和coverage gaps；Rules Engine不是Assessment Engine，证据不足保持unknown。|
|B-P1-06 NOTICE / License Draft facts|确定哪些Resource具有NOTICE/attribution obligation及支持证据，提供NoticeDraft输入；不自行决定Draft workflow或把草稿变成正式授权。|
|B-P1-07 性能与质量报告|记录仓库规模、文件数、ScanCode/Syft/Detector各耗时、总Pipeline耗时，关联准确率、召回率、失败及partial原因；固定输入、区分冷/热运行，不混入AI缓存提速。|

### 第一批实际任务

先阅读0.2.0实现、R1A/R1B-A测试和真实Bench，提交`P0_SCANNING_HANDOFF_REVIEW.md`：ScanCode/Syft能力、Detector能力、Rules能力、Bench状态、已知FN类别、P1优先级、ResourceProfile事实字段提案。建议放入`docs/handoffs/`，先查是否已有，避免重复。

然后准备Bench2.0样本设计；等待负责人冻结ResourceProfile、Graph、Diff公共contract。第一批不要立即加Detector规则，只有Benchmark证据支持且范围确认后再做增量。

## cz开工命令

先检查自己工作区，未提交成果不覆盖。

```sh
git fetch origin
git switch -c p1/cz-scanning --track origin/p1/cz-scanning
```

若本地分支已经存在：

```sh
git switch p1/cz-scanning
git pull --ff-only
```

先读`docs/handoffs/P1_CZ_SCANNING_HANDOFF.md`；不要继续使用旧scanner/codex分支作为P1基线。
