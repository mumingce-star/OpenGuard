# P2 阶段1后端候选：待 Owner Review

本次完成正常后端 HTTP / Store 接线及固定 v6 隔离真实验收；**阶段1整包不标 PASS，xzb 整体阶段2仍 BLOCKED**。新可信正向来源接纳/材料、接收机运行兼容及 Owner 签收未完成；不能把持久化成功解释为许可支持成立。

## 固定源码与修改范围

- 功能分支 `codex/p2-stage1-backend-20261010`。本文件所在 Git 完整提交为 A 候选身份。
- fetch 后 `integration/p1=aabd7940f65ec8a78b33c863b4db81b400509b7d`；cz=`6dc340776bc63c3b925d7fa3645efbbd40c4ccf9`，旧 `b7cc94b8f87ad3fef3682ba5ac4e84b76b63e36c` 已不是 tip。cz tip 包含该 integration commit。
- 新 `backend/app/p2/{contract,store,service}.py`、`backend/app/api/p2.py`，`main.py` 薄接线；新 P2 契约测试，两个既有 OpenAPI 路由清单仅追加新路由；机器Schema、合同、脱敏回执与协调日志。
- 没有合并原未提交 R6/Qwen/离线 L1 候选，不冒充原 P2-01 前后端整包已统一。无前端改动、无原库迁移、无新 provider 或 Formal 政策。

## 验收结果

| 检查 | 实际结果 |
|---|---|
| 最终相关 pytest | 430 唯一节点：428 PASS / 2 FAIL / 0 SKIP。P2+P2B 117节点全部通过，属于430的子集，不能叠加 |
| 两条旧失败 | `test_p1_notice_draft_production_wiring.py::test_a3_06_11_content_and_no_authority_escalation[resolved-excerpt-notice_source_excerpt_truncated]` 及 `unresolved-excerpt-...`；未修改父提交均复现 `excerpt_content_invalid`。不是本轮新回归，也未关闭 |
| 真正Fail-first | 2节点：SQL行/payload错绑与P0人审来源过度提升；另1节点：缺失内容Hash被记录Hash替代。原失败单列保留 |
| 最终真实HTTP | 31请求：13个GET 200，6个POST 201（3次真实创建+3次原键重放），5个POST409、1个404、3个422、1个413、1个只读POST503、1个关闭GET503 |
| 独立版本 | result revision 1→2→3；同一Assessment v6；仅3个结果/3个summary/1个answer/1个material |
| 范围/旧对象 | 45资源中，仅指定1资源受影响，44整行复用；ScanRun/Assessment及非P2库逐表内容Hash不变；原旧结果刷新/重启后可读 |
| 材料与Formal | 原v6许可片段，明确EXCERPT、user_supplied_unverified/pending；新许可正向判断0，Formal改变0，业务输入模型调用0 |
| 实际HTTP性质 | 单个network-none容器内loopback TCP + uvicorn正常工厂 + SQLite。不是TestClient或静态JSON服务；新事实写入均TEST_ONLY |

原始JUnit/日志见 [test-receipt.json](test-receipt.json) 与 `evidence/`，真实HTTP及完整ID见 [real-http-receipts.json](real-http-receipts.json)，逐表计数/内容摘要见 [database-receipt.json](database-receipt.json)。此前中间失败、两次父本缺静态fixture收集错误及两个采证脚本错误保留在本任务私有证据目录，未冒充产品Fail-first，也未重写成最初全绿。最终HTTP响应重新序列化后与记录的完整wire大小/Hash逐项一致。原始Fail-first JUnit的断言标记有一行尾随空格；未改其字节。`.gitattributes`仅对该证据文件设置空白例外，其他源码/测试/文档仍执行完整diff检查，JUnit均禁文本换行转换。

## 固定真实对象与直接读取

- scan：`scn_6c0f972a-18c1-4566-a7fa-df623053bea5`
- Assessment：`asm_8412408d-1c91-51e1-99e0-c135239bf510` / version `6`
- resource：`cmp_0c32e291-83e7-5bc9-b474-1e5921b668b2` / `2.13.4`
- 项目 revision：null（原件如此，不能推断为某个commit）；Registry revision 13。
- Evidence：`evd_3572442a-235f-5048-98cb-246536791eb2`、`evd_82906a46-4439-50f3-bd0a-807784efa9c5`、`evd_99c84e41-a588-5c8e-ac02-104ad689f7c4`。
- 初始 result：`p2res_9f3d4ff6e4ded6e0ca653ef388bca2aff70ab94e11f0d8d4d38d6d6a7dff8c61`
- 回答后 result：`p2res_f957fbc9262c97e1e13591234c483b30e628885ca52ae82a1d864529a6c2284d`
- 材料后 result：`p2res_5627887dcb3805d594201ea0ce7f71f9c775d16ea31fc7b568876938dc77e250`
- answer：`p2ans_343c7bc43b8c30b4e09a20d311fc0668655f70f498c00a19165e1e99b941e13b`
- material：`p2mat_12349e2c493de1caa787b629d84a4d785f56c095e4c241d45d54c53ccb18ff00`
- companion：`p2sum_dba7a787e97d0266931a4bc8877b12e5ce75ff25bfd150a4e66f283873e36057`

运行地址前缀由自己的隔离API提供，以下精确URL path不表示服务仍运行：

```text
/api/v1/scans/scn_6c0f972a-18c1-4566-a7fa-df623053bea5/assessments/asm_8412408d-1c91-51e1-99e0-c135239bf510/p2/results/p2res_9f3d4ff6e4ded6e0ca653ef388bca2aff70ab94e11f0d8d4d38d6d6a7dff8c61?assessment_version=6
/api/v1/scans/scn_6c0f972a-18c1-4566-a7fa-df623053bea5/assessments/asm_8412408d-1c91-51e1-99e0-c135239bf510/p2/results/p2res_5627887dcb3805d594201ea0ce7f71f9c775d16ea31fc7b568876938dc77e250?assessment_version=6
/api/v1/scans/scn_6c0f972a-18c1-4566-a7fa-df623053bea5/assessments/asm_8412408d-1c91-51e1-99e0-c135239bf510/p2/results/p2res_5627887dcb3805d594201ea0ce7f71f9c775d16ea31fc7b568876938dc77e250/summary?assessment_version=6
```

授权恢复源 SHA256 `2f301c90dc1219a17b5801fcd7f96912f2b30c208a3f9da7546806fced6f22d2`。只复制必要固定 Scan/Assessment 原件，**未克隆原整库**。原扫描幂等请求fingerprint缺失，隔离恢复另记导入摘要；旧Report正文未获原件，未用新渲染替代。空非报告列不作为旧Report验收。新companion绑定经真实HTTP验证，旧Report不可冒称已重新验证。完整原件和DB保持本地，不进入Git。

## 四项阶段1门禁

| 门禁 | 状态与证据 | 下一责任 |
|---|---|---|
| 同一候选 SHA、入口、固定对象 | A后端候选/对象/启动入口已具备；xzb当前前端与本分支兼容及其机器固定数据未确认，整包待确认 | Owner/xzb确认候选及合法数据取得 |
| L1/L2契约、状态/错误真实可用 | HTTP持久化/读回/回答/观察/冲突已验证；可信上游→P2B正向来源接纳仍缺，当前真实L1仅缺口与旧支持标记 | A/cz补精确来源/适用性证明；不能让前端补猜 |
| 成功/缺口/失败/冲突真实响应 | 31次真实HTTP已留存；201表示保存成功，新正向许可建议未证明 | Owner审查合同语义及期望的价值门槛 |
| 新旧结果及同版报告 | 独立result 1–3和同版companion已验证；原旧Report未复制，接收机未签收 | Owner/xzb复核独立版本合同 |

不因为四行都有资料就全打勾。只读精确GET、错误展示、明确范围回答和材料pending状态可供准备；正式前端接线本轮未执行。阶段2整体授权不由本候选代签。

## 剩余缺口和停止点

1. P0人审许可/scope并不包含P2B要求的独立上游与适用性证明。当前适配保守留缺口；需要真实可核验来源和最小可信接纳合同，不能仅让调用方填 `verified=true`。cz三例仍无真实Scan/Evidence绑定，未下载或造样本。
2. 本候选没有把完整R6/离线Qwen L1移植进团队基线；Qwen真实proof/诊断、旧两问UserFact迁移和前端兼容需独立约定，不能以新P2问题ID冒充旧R6。
3. 两条NOTICE父本fixture失败未改。Owner Review、xzb目标机运行/数据授权均待完成。

`BACKEND_HTTP_PERSISTENCE=VALIDATED_FIXED_V6_ISOLATED_TEST_ONLY`；`STAGE1_BACKEND_CONTRACT=PARTIAL_NOT_ALL_GATES_CLOSED`；`OWNER_REVIEW=PENDING`；`XZB_STAGE2_PRODUCT_WIRING=BLOCKED`；`OVERALL=PARTIAL`；无merge/PR/deploy授权。Python阶段A和Trio历史停止状态不变。
