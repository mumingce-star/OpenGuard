# 后端 B 实施与验收回执（2026-11-16）

整体 **PARTIAL**。基线为 `codex/delivery-20261030@2cc7f63a812561bf71de11d2041e4027a345efda`。CLI 与 B07 改动已进入本地工作树。跨线改动保存在隔离候选中，供 A、前端和 Root 对照采用。本轮无 GitHub 发布。已发布的团队整合仍沿 `42aa2b2` 历史回执。

| 工作包 | 本轮实测与累计状态 | 下一步和责任 |
|---|---|---|
| B-F01 CLI | 修复缺参、未知选项、ZIP 不可打开与运行期错误分类。四个反例在旧代码失败。POSIX 上六个 CLI 单元与独立测试文件 161/161，含旧 inventory、Python/JS 成功路径和安全拒绝。 | Sol/Root 审差额并发布。 |
| B-F02 Material、NOTICE、coverage | 原 Material 代码和测试补丁通过适配检查，原 14 项客户端测试通过。原 NOTICE 候选的两个工厂反例由 2 失败转为 2 通过。原 coverage 及 manifest 通过私有接收，生成隔离组合。 | 前端采用 Material 并签真实浏览器。A 核实 NOTICE 维护者曾报的 433 项原件，并选择采用范围。A/Root 复核并采用 coverage。 |
| B-F03 正常工厂 | 原 160 文件、89 节点包实跑。原 coverage＋Summary 组合 88 通过、1 失败，叠加规范化回执候选后 89 通过。 | A 复核选定组合及共享源码差额，Root 决定采用和发布。 |
| B-F04 正式来源与 npm | 已发布缺 `timed_out` 拒绝沿原回执。本轮 P2B 相关离线测试通过。正式来源及 GET 消费待验。 | A 提供 receipt、issuer、策略、撤销及获准读取入口，B 核拒绝反例和同版本消费。 |
| B-F05 内容、范围、新 Evidence | 已有固定材料与范围候选。无正式同扫描关联及新版 Evidence 实测。 | A 提供同 scan 的 ScanRun、inventory、仓库和发布归档关系、版本及 CAS 路径。Owner 核 lodash 范围。 |
| B-F06 P4 正式消费 | 原角色和 Apache 模块回归、同固定 Git 对象重放通过。已有私有映射和字段差额。 | A 从授权证据仓组装同快照输入，接正常工厂与 Store，前端签同版展示，Sol 审条款语义。 |
| B-F07 规则 | 现有 15 条规则和 SPDX 边界沿规则库，P4 仍限固定受审文本的 §4(a)/(b)。本轮 B5 回归通过。 | B/Sol 复核原文、适用前提、人工状态和覆盖缺口，逐项扩展。 |
| B-F08 Profile、r2/v3、NOTICE | Profile 有可选工厂接线。NOTICE 原工厂节选候选通过。r2/v3 的正式来源与消费未闭合。 | A 提供真实 Profile 双键及获准读取和新事实派生回执，B 核内容定位与历史保持。 |
| B-F09 锁与 workspace | 现有 Python requirements/pyproject、npm lock v2/v3。新格式本轮未实施。 | B 先限定 pnpm、uv 版本。npm v1/shrinkwrap、Yarn、Poetry、Pipfile、PDM 留在待办。 |
| B-F10 SBOM | 继续沿 Syft 原生 JSON。CycloneDX JSON 尚未实施。 | B 在首链接线缺口处理后，完成 CycloneDX JSON 的版本与身份闭包验证。CycloneDX XML、SPDX JSON/tag-value 留在待办。 |
| B-F11 导入与角色 | 原四角色用例通过，Python 使用经审核映射。 | B 增补 JS/TS 静态语法子集，A 提供同对象受信构建和交付证据。 |
| B-F12 模型、数据集和 API | 已有有限文本和结构化候选检测。 | B/Luna 需真实获准样本和反例，固定来源并度量四类覆盖。 |
| B-F13 D4 | 本地工厂覆盖合成子集复用和历史对象保持。express 与独立旧 v6 正式对账待原件。 | 各保管方分别交 express 同链前后及旧 Formal、独立旧 v6 原 JSON/HTML。M1 继续 STOP。 |
| B-F14 Git 与 ZIP 真链 | 现有历史扫描与报告可复用。本轮仅 CLI/工厂及 NOTICE 隔离测试。 | A/B/前端分别签 Git、ZIP 输入到同版报告两链。 |
| B-F15 恢复与报告 | 工厂测试实际暴露重放响应键序不同。最小候选使三个写路由通过现有模型验证后使用既有 canonical 编码，保持错误响应和 GET 路径，原回滚与同 key/body 字节断言通过。 | A 采用回执补丁，前端签十场景与真实恢复，Root 核对固定报告。 |
| B-F16 评测 | 固定 P4 开发重放 3/3，独立预测仍为 0。 | Luna/真人补权利、标签、裁决、新盲集，Sol 核原规划和指标分母，B 按裁决修复。 |
| B-F17 性能 | 修复 B07 重复 run/receipt 和混组准入。保留同组失败样本，按字段身份比较工具与环境。B06/B07 邻接 15 通过。 | A/环境提供固定配置的真实冷/热采集，Sol/Luna 复核原收据、失败率及分位数。 |
| B-F18 发布 | 本地源码、测试、候选和证据可复核。 | Root 按最小差额采用、独立验收和发布。现有预览与发布分支不代表本轮组合。 |

## 复现与精确身份

- POSIX 验证复用本地镜像 `sha256:29d3e7a7e3ea9e5872470325f34eb2bb06ecc779439c4baa71ea3ad42ba11a18` 的 Python 3.12.14，使用已有 pytest 8.4.2、FastAPI 0.141.1、Starlette 1.6.0、httpx2 2.12.0 和 Pydantic 2.13.4。不拉取、不联网、不监听。测试进程以 UID 10001、2 CPU、2 GiB 内存运行，输入只读，业务断言落在临时 `TEST_ONLY` 数据根。
- CLI 用 `PYTHONPATH=backend python -m pytest -q` 执行 `test_a2_zip_cli*`、`test_b1_python_p0_mapper_cli*` 和 `test_b1_javascript_manifest_p0_cli*` 的六个 unit/security 文件。混合命令中的 CLI 分组按 JUnit 单列为 **161 通过**，另有 11 项角色通过。27 个 Apache 节点初次因隔离容器未挂 Git 对象而在 setup 报错，随后在宿主的 P4/P2B/B5 相关集合获得 **140 通过**，固定 Git 对象重放与原 JSON 一致。两套结果各自保留。
- Material 原源码补丁 SHA-256 `20d036f97718943924f757daf835898176d6120df6741e8981443c460cfa0b03`，测试补丁 `cfe1d3dce8e32ac3c7dc731c593c80d895b2f94483b0783347bd31542569654b`。用原候选的 `node --test .../receipt-normalization.test.mjs` 复现 14 项，证据等级为 VM/mock fetch。
- NOTICE 原补丁 SHA-256 `39441ec8bed122156751217c36085d2ba8e4662adb6f18f49b8772c50aa`，实际候选夹具 `dfea99aab9e60e1e502ffcf342b9effa21bce5fe983c4db304a5e56a763cee6a`。以 `pytest -q tests/unit/test_p1_notice_draft_production_wiring.py -k "test_a3_06_11 and excerpt"` 在隔离树验证。首次缺只读文档及原 facts 夹具的收集错误单列。原夹具在 Content 校验处因缺 excerpt 摘要拒绝，候选保留 whole 摘要、严格校验及 UTF-8 字节范围。
- coverage 两件原件 SHA-256 分别为 `76481697641c53c6f9a1256de02ae81e1b4ab74f9aeed1cadeb5773ecf753995`、`e8ab0e9310c1c64a94bb667ea91870683617281d822c072c0fd074729d49c290`。原 `adopt_coverage.py` 验证并生成 Service `7d17b1b512976170c2ff849fcc47e14f5385ce178648b084e242e51aad716038`。原补丁在缺版本、缺范围或缺摘要分支的汇合处独立追加覆盖缺口。原工厂测试覆盖 partial、completed 带错误、未知错误和干净 completed，以及这些条件与前置缺件的组合。
- 工厂使用原 `python3.12 -B run_factory.py`，执行 63 个原节点与 26 个增量节点。512 MiB 初次触发 Assessment 的磁盘门禁，故以 1536 MiB 临时盘复测。第二次唯一失败是同 key/body 响应字节。规范化补丁 SHA-256 `1127e07cd75f00d70f65bd1e8de53a7ce2dc102a897bb9fcc0d8d44ead42e94d`，最终 160 文件 manifest `1c8281330e414bfeaac530391f28b52c678600e5c41538d9e6aeeeb249fe131a`，89 通过 JUnit `3837a3309429c796a7b5de843b1d64dbc001935cd6ff59a183d8c86e3443fc60`。Store 事务回滚、零写入 GET、旧 Result/合成 Formal 保持和子集复用的原断言通过。该组合用合成夹具验证。
- B07 复现命令为 `node --test tests/b06_b07_p2b_contract.test.mjs tests/b07_performance_receipt_v2.test.mjs`。新增反例涵盖重复 run、非字符串 ID 及混用来源、输入、配置或工具。汇总未采集真实耗时。本轮未新增第三方资源或依赖，公共 API 路由、DTO/Schema、规则集版本通用定义均无变更。

公开候选的最小差额为 CLI 和 B07 源码、对应测试及说明。跨线候选只能按原 Material 两补丁、NOTICE 单 hunk、coverage 原补丁及新增 P2 规范化补丁分别审核。原包、测试库、日志及收据留在本机。Root 发布时需重新核对精确暂存清单与敏感信息。

已有可独立演示能力包括受支持环境的 ZIP CLI、P4 开发重放、Java 受信目录核心和历史预览。正式来源与当前 Git/ZIP 同版端到端、正式历史原件、报告和浏览器恢复仍待签收。报名依赖 Owner 核资格、平台和权利。完整作品还需两条真链、目标机、同版报告及匿名演示。竞争力还需独立 Gold、新盲集、消融及真实质量与性能数据。
