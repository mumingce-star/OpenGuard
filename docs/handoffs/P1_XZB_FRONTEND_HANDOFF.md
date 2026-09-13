# xzb：P1前端接续交接

责任划分：项目负责人负责架构、Domain/API、Pipeline、集成、Docker与最终发布；xzb负责前端产品实现；cz负责扫描/Detector/Rules/Bench。以下描述的是负责人在xzb原前端成果上的P0收口集成，不抹去组员贡献，也不表示所有变更由一人独立编写。

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

## P0后期负责人在前端基础上完成或推进的成果

1. 真实API接线：正式模式只消费后端返回，Mock仅用于明确的演示/原型场景，失败不能回退成演示成功。
2. Git / ZIP扫描与页面联动，Progress / Overview / Resources / Risks / Report消费真实结果。
3. Formal Project Assessment基础页、前端适配、Usage declaration与项目评估路径。
4. EvidenceReader以及风险到证据的查看体验；事实、规则判断和AI解释分开呈现。
5. 分组风险/资源、分类报告与实际进度展示；不得用假进度或隐藏partial替代后端状态。
6. 本地Qwen解释、项目答疑与历史恢复接线；STEP6.1的上下文限制为后端权威，前端配合展示，不自行放宽。
7. 真实浏览器验收、frontend测试、TypeScript/build以及Production API proxy联动已在P0推进并留有历史记录；本次文档提交不声称重新运行这些检查。
8. 前端产品化诊断修正：editable、multiple constraints与未知原因分开映射，保留技术诊断。相关集成提交可查`78127c8`、`5611c00`、`b7329cf`、`0475e66`、`35ac0b8`；这是导航，不是全部历史。

### 先读当前代码

- `frontend/src/App.tsx`，`frontend/src/pages/`：重点Assessment.tsx、NewScan.tsx、Overview.tsx、Progress.tsx、Report.tsx、Resources.tsx、Risks.tsx；首页Landing.tsx。
- `frontend/src/components/EvidenceReader.tsx`、`frontend/src/components/UsageForm.tsx`。
- `frontend/src/services/`：scans.ts、assessments.ts、assessmentPresentation.ts、model.ts。
- `frontend/src/types/domain.ts`、`frontend/tests/`、`frontend/package.json`及现有API契约/部署说明。运行前从现有配置确认命令；前端既有检查为TypeScript、pnpm test和build。

不要把旧feat/xzb-frontend当作当前正式前端。不要重新设计P0扫描主链、重做Assessment基础页、把真实API换回Mock、自行改变Domain字段或条件状态。Unknown不显示为禁止，Pending不显示为Verified，Finding不写成确认违规，AI explanation不冒充正式评估。

## P1前端任务次序

|任务|目标与交付边界|
|---|---|
|F-P1-01 History|展示历史扫描、revision、时间、status、summary，查看旧扫描并选择两条比较；等待正式历史接口。|
|F-P1-02 Scan Diff|新增/移除资源、状态、license、risk、assessment变化；完全由后端Diff contract驱动，前端不猜匹配或变化语义。|
|F-P1-03 Resource Graph|Project→Component→AIAsset→License→Evidence→Finding→Obligation；节点/类型/风险筛选、详情与证据跳转。Graph只是View，边不能制造新事实。|
|F-P1-04 Resource Profile / Model & Dataset Card|面向model/dataset/api展示identity、provider、version/revision、detected evidence、metadata、license/authorization status和coverage gap；区分Detected、Metadata observed、License verified、Authorization verified。|
|F-P1-05 Remediation Task UI|组织conditions、restrictions、gaps、next_steps、obligations；完成状态仅workflow，不回写正式合规结论。|
|F-P1-06 Report V2 UI|Executive summary、Resource map、Key risks、Evidence、Assessment、Action plan、NOTICE/Draft入口与历史变化；依赖冻结ReportV2Snapshot。|
|F-P1-07 演示体验|GitHub输入→扫描→Assessment→Graph→Evidence→Diff→Remediation→Report；改善密度与交互，不删明细、不伪装覆盖。|

### 第一批实际任务

先阅读上述真实代码，对照旧分支认知差异，提交`P0_FRONTEND_HANDOFF_REVIEW.md`：当前页面、真实API、数据结构、与旧版本差异、P1所需后端字段、**不修改代码的P1页面计划**。建议放入`docs/handoffs/`，先检查是否已存在，避免重复。

等负责人A-P1-01冻结公共对象后，先History＋Diff基础页，再Graph。冻结前可做页面结构、交互草图、组件拆分方案、明确标注mock的contract prototype；不得把自行设计字段当正式API提交。

## xzb开工命令

先确保自己工作区干净；有未提交成果先自行保留处理，不强制覆盖。

```sh
git fetch origin
git switch -c p1/xzb-frontend --track origin/p1/xzb-frontend
```

若本地分支已经存在：

```sh
git switch p1/xzb-frontend
git pull --ff-only
```

首先阅读`docs/handoffs/P1_XZB_FRONTEND_HANDOFF.md`。不要从旧feat/xzb-frontend继续P1。
