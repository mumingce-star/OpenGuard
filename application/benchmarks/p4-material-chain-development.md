# P4 材料支持链开发验证 v1

本轮固定标签版本 `p4-material-chain-development/v1`，代码化清单位于 `tests/unit/test_p4_apache_redistribution.py`。待第二人复核。样本在实现和定向测试中已暴露，分歧记录尚待独立复核，已知未知包括真实交付范围、其他条款及履行状态。

| 材料 | 来源及版本 | SHA-256 | 定位（从零计字节，右开） |
|---|---|---|---|
| LICENSE | 本仓库提交 `2cc7f63a812561bf71de11d2041e4027a345efda`，Git blob `261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64` | `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4` | 第 94–95 行，[5206, 5310) |
| README.md | 同提交，Git blob `d2a217dc9e546e16d15b8a1e0cf6f943519c9a75`，由文件自身声明自有代码与文档使用 Apache-2.0 | `2941166b3c8574882c34d4af2a6d8af7a5b827b7701e4978813305808b71f4ea` | 第 201 行，[18662, 18937) |

正例复用原件，不复制新素材。1 个真实开发项目、1 条真实材料与假定用途组合、24 个派生行为测试、0 个独立项目。负例围绕相同项目改变输入或绑定，计入开发回归。当前没有 A/AI/前端端到端运行。既有 P2 回执测试属于回放；P1 固定仓库的 25 个槽位仍为准备台账；Bench v2 正反例用于治理准入。这些均不计入本轮项目数或独立指标。

| 指标 | 结果与含义 |
|---|---|
| 本地条件主张精确率 | 1/1。分母是新适配器在这组开发用例中产生的条件主张数，分子是与本轮开发标签一致的主张数；重复确定性断言不另计。样本已暴露、标签待复核 |
| 严重安全错误 | 0 个在定向用例中观察到的越对象、越版本、缺证肯定或虚假义务履行；范围仅限本组测试 |
| 独立条件建议精确率 | 未测，符合准入的独立预测 0 条，分母 0，值未定义。系统端到端需 A/AI/前端和独立标签 |

错误与限制：错版本、错对象、Hash/范围不一致需对账来源；空材料、损坏编码和超限各有独立拒绝原因；组合表达式保留原语义供后续处理，适配器拒绝按单许可推导。JavaScript CLI 既有缺参数反例返回 1，断言期待 2。CLI 维护者应在参数解析阶段处理缺失的 ZIP 参数。真实 Syft 用例未配置受控二进制，隔离 ZIP 用例依赖 POSIX，留给扫描维护者及测试环境复验。

相对规划目标，尚需 5 个开发项目、2 个独立项目及至少 39 条真值用途—对象主张候选，并实际完成独立标签双人复核、分歧裁决和评测。由 Luna 与复核者冻结样本及标签，A 和前端提供同版端到端结果，Sol 审核指标口径。

## 2026-11-14 增量 v2

[机器结果](p4-material-chain-development.json) 记录同一已暴露开发项目的版本、Git blob、材料 SHA-256、用途情景、对象及范围、定位、预期和实际结果。第二人复核仍待。§4(b) 复用上表原件，位置为 LICENSE 第 97–98 行，[5322, 5432)。修改用途来自重放程序中 `MODIFIED_PLAN` 合成材料第 1 行，SHA-256 和定位见机器结果。此前 §4(a) 仍按本组开发结果报告 1/1；§4(b) 新增一组同项目合成用途回归，缺事实回归返回 `modified_delivery_scope_unknown`。重放 3/3 匹配。独立项目 0、预测 0，精确率未定义。既有剩余 5 个开发项目、2 个独立项目和至少 39 条候选由 Luna 及复核者跟踪。独立划分、双人复核、分歧裁决均待。未取得规划书原件，任务编号、门槛和候选口径待逐条核对。

### 实际复现

从仓库根目录运行。实测 Windows 11、Python 3.12.10、pytest 8.4.2、Pydantic 2.13.4。

```powershell
$env:PYTHONPATH='backend'
.venv/Scripts/python.exe -m benchmarks.p4_material_chain_development
$suite = @(
    'tests/unit/test_p4_resource_roles.py'
    'tests/unit/test_p4_apache_redistribution.py'
    'tests/unit/test_p2b_offline_material_audit.py'
    'tests/unit/test_p2b_candidates.py'
    'tests/unit/test_p2b_receipt_closure.py'
    'tests/unit/test_p1_license_notice_facts_detector.py'
    'tests/unit/test_b5_license_rule_engine.py'
    'tests/unit/test_b1_python_manifest_parser.py'
    'tests/unit/test_b1_python_p0_mapper_cli.py'
    'tests/unit/test_b1_javascript_manifest_p0_cli.py'
    'tests/unit/test_b3_syft_real_output.py'
)
$target = $suite[0..1]
.venv/Scripts/python.exe -m pytest -q -rs --tb=short @target
.venv/Scripts/python.exe -m pytest -q -rs --tb=short @suite
git diff --check
```

实跑 pytest 额外指定会话目录的 `--basetemp` 及 `--junitxml`。定向 38 通过、0 失败、0 跳过。邻接 309 通过、2 失败、5 跳过，2 条 TestClient 依赖弃用警告。4 个 sealed ZIP 用例因 Windows 缺 POSIX 描述符能力跳过，1 个真实 Syft 用例因未提供受控可执行文件跳过。两条 CLI 失败均为预期 2、实际 1，分别是 Python 入口传入不存在的 ZIP 和 JS 模式缺少 ZIP 参数。用 `git archive` 导出 HEAD 的 `backend/app`、`rules` 和对应两个测试文件，在隔离目录重跑 `test_new_cli_controlled_failure_has_no_traceback_or_path` 与 `test_js_cli_flag_misuse_is_stable[arguments1]`，两条均复现。后续由 CLI 维护者处理，环境/扫描维护者提供 POSIX 和固定 Syft。

错版本、跨对象、越范围、Hash 不符、表达式不支持和证据不全都保持待核。§4(b) 新反例含用途事实自身的对象、版本和范围错误。范围排除仅在同对象、同版本、同范围、有审核引用且原字节匹配的合成回归成立。角色定位回归使用受控清单、合成 Syft JSON、固定 Python 源码与模拟审核证据；以 npm scope 转义、锁版本冲突、Python 依赖行冲突和相反交付证据定位错误。正式来源授权、Store、HTTP、浏览器、目标机、产物语义核验及独立评测均未运行。
