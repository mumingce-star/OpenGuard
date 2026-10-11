# B03 v3 固定来源修正：source-binding-r2

状态：**修正实现与本机离线验收通过；待独立审核、Root 发布及 A 新版本接纳**。本轮仅 P1 B03，不改 A/API/Assessment/Report、前端业务、正式规则或冻结 Schema；不启动服务、不抓取来源、不安装、不提交推送。

旧包 `tests/fixtures/notice-license-facts-v3/facts.json` 原字节保留。生成器原先读取当前工作树、却把来源标为 `9d67b88f39fa4aaa8ab24048aea224204eabd490`；该 commit 的 `frontend/package.json` SHA 是 `a8e9bab912ffc5ef1afc2da36db5b0de932ce872e235e02b55dce9ceca65f09a`，旧包记录的是工作树文件 SHA `16e9db4fb169ef63a982912b983e8259332e580554a451e4053c3f43e73b05fc`。

现在全部来源均经本机 Git 的 `ls-tree`/`cat-file` 读取固定 commit 中的普通 blob，并复验 blob 身份；不读取当前工作树源文件。只接受完整 commit SHA、安全相对路径，拒绝 tree/非普通 blob/缺件，禁用对象替换与缺失对象自动获取。来源大小和执行时间受限。

## 不可变交付

修订目录：`tests/fixtures/notice-license-facts-v3/revisions/source-binding-r2/`。

| 工件 | 内容与摘要 |
|---|---|
| `facts.json` | 同一冻结 v3 Schema，31 facts/31 Evidence；文件 SHA `6157b50a2a47955574c404f2302ab7b35a3d2e8e3046aaadcfe26326ce442795`；canonical package SHA `466f8abd7f3b0f2fd7ff1a0f80a8cbd210db6ec80bbb6857046651f2fb67b096` |
| `amendment.json` | 旧/新文件及 canonical SHA、8 条受影响 Evidence、来源修正原因、旧下游失效要求；独立审核/真人批准/A读回均 null |
| `manifest.json` | 15 个 source 文件的固定 commit、size/SHA；facts/amendment 工件哈希；状态维持离线准备、未获独立签收 |
| 根目录旧 `facts.json` | 保留 SHA `4f2a8304ad457dffdc7e4ba276e3602bf93b4f83b1e7e177bbcb84f4a8d841f7`；source binding 缺陷保留作历史与负例，不当新闭包输入 |

8 项 npm source Hash 已修正；全部 31 项选定字段 Hash、fact 语义、关系/gap、report_v3_rows 不变。生成器 producer 为 `3.0.1`。HF manifest 的本地来源 revision 也明确为同一 Git commit；provider 的 upstream revision 仍是固定 fixture 声明，未提升为实际上游授权或异机签收。

旧包与上一轮 `p1-b-offline-audit-20261011.*` 均作为当时审计快照保留，不能改写成“当时已经无错”。新修订使用新包 Hash，不能借用旧 Scan/Assessment/BOUND/Report 身份伪造重算完成。

## 验证与复现

Windows / CPython 3.12.10 / Node 26.2.0。未新增第三方依赖；Python 使用已有项目环境，沙箱启动受限时获准本地执行。

```powershell
node tests/fixtures/notice-license-facts-v3/generate.mjs --check
node --test tests/notice_license_facts_v3.test.mjs tests/notice_license_facts_v3_revision.test.mjs
$env:PYTHONPATH='backend'; $env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/unit/test_b03_fixed_git_revision.py tests/unit/test_b03_b04_v3_consumption_adapter.py tests/unit/test_p1_license_notice_facts_detector.py tests/security/test_p1_license_notice_facts_detector_independent.py --basetemp tmp/pytest-b03-r2-20261011
```

Node 最终 **10 passed / 0 failed / 0 skipped**；Python **24 passed / 0 failed / 0 skipped**。Node 独立 `git show` 复算全部 15 来源；正反例覆盖工作树脏字节注入不影响生成、非法路径/ref、tree 冒充 commit、缺失 blob、哈希篡改、旧包和新 revision 不可覆盖。Python 核验原 Schema、v3 adapter pin、原 v2 候选兼容。31 source/selected Hash独立复算全部匹配、source mismatch 为0；编译、严格 JSON、diff-check及敏感/发布白名单检查见 `b03-source-binding-r2-validation.json`。

生成器不带参数只允许首次创建新修订，已存在则失败；`--check` 校验三份工件，`--stdout` 只读输出新事实包。禁止用删除旧修订再重生成来绕过不可变要求；后续变化另建 revision/amendment。

## 责任与发布范围

| 本轮／累计 | 状态与下一步 | 责任／GitHub |
|---|---|---|
| 固定 commit 原字节读取、8项来源修正、31事实保守语义、15source闭包及篡改反例 | 本机验证通过；可独立离线复算 | B已处理；当前 `codex/scan-reliability-integration@bed87f5`，仅工作树，无本轮提交/推送 |
| 旧v3包、旧离线对账、原v2候选保留 | 历史已发布包仍有来源缺陷；修正不能静默覆盖 | Root只选择本轮B03文件/日志记录，保护其他P1/P2未提交成果 |
| 独立校验与正式生产绑定 | Luna/Sol独立复核；A用新pin创建新绑定、使旧派生结果失效或显式标历史，再给终态/重启/Draft/Report回执 | 未签收，不能称P1整体完成；B不代签、不修改A持久化或前端 |

本次没有 A/前端新的运行回执；Windows A 的 POSIX setup 阻断、真人 Gold、新 holdout、正式质量/性能门禁均未由本修正关闭。可参赛仍须目标机/Java核心/材料验收；完整作品还需独立审核、新生产绑定、前端浏览器及发布；竞争力仍需真人 Gold、对比消融与受控性能。无统一分母和权重，不报告百分比。

开工日志完整阅读仍受巨大输出截断限制，已登记；另一个 Root 的预览启动任务在途，本轮未干预其服务和文件。精确 token 数不可获得；开工估算6,000～12,000，修正范围已实现并本机验证，无法核定实际用量是否在估算区间内。
