# P2 L2 / CAS / 持久化本机验收回执（2026-10-15）

## 结论

在不改动原三例固定根的前提下，本机对从固定根复制出的独立、可重置 `TEST_ONLY` 私有副本完成了真实 HTTP 写入、同键幂等、旧 revision CAS 409、冲突后重读、Answer/Material 读回、服务重启和前端浏览器恢复验收。

本回执仅证明回环开发环境中的 P2 v1 契约与当前前端可联调；不把 `TEST_ONLY` 材料写成真实项目许可结论，不代签正式锁定镜像、人工许可适用性、生产 NOTICE 或 P2 整体 PASS。

## 身份与隔离边界

- 后端交付源：团队统一候选 `codex/team-integration-20261013@7dce111f18cac1fd15d0482ed759d0a6329cccae`，包含慕名策 P2 后端 `afca4c26c2fa45fa285fc9cabf48f52c54a59229`。
- 当前前端基点：`codex/p2-readiness@9ad9998d6f3df82618966c5865d13006a1efe6bc` 叠加未提交 P2 工作树；本轮未提交、未推送、未合并。
- 原只读固定根及 `15176 / 4183` 未被写入、初始化或替换。
- 写入数据根：WSL 内部 `/opt/openguard-p2-write-20261015/receiver`，权限保持 `0700`，容器 UID/GID `10001:10001`。
- API：`127.0.0.1:15177`；前端预览：`127.0.0.1:4184`。
- 仅允许显式回环 Origin `http://127.0.0.1:4184,http://localhost:4184`；没有关闭 Origin 检查。
- 开关：P2/Assessment 开启，`P2_READONLY=0`，数据等级 `TEST_ONLY`；AI、公开 Git、外部扫描器、Profile Metadata 保持关闭。
- 开发运行镜像：`sha256:6514fdf0abee6925b3c00671a20ddfdf65e09c3ac8acc666153d69556005d6f1`。交接说明中的正式锁定镜像 `sha256:6510aeaf...` 本机仍未取得，不将开发镜像冒充正式接收结果。

## 真实写入与 CAS 结果

| 检查 | 实际结果 |
|---|---|
| 固定父绑定 | Scan `scn_fb8856de-91c3-41b7-b758-fcf35c2ea77d`；Assessment `asm_6c664ed7-7c41-512c-bbcc-a178a8edea79` v1 |
| 脚本正式起点 | Result `p2res_cc4733c89d7f44fe9f0b08c160c24f56f0e5b5a3b36edea5a5a89f9c94347cc7` revision 4 |
| Answer 201 | `p2ans_4d3e89a079a8d1ae8e9e02ea789f7f899160ba2dbd89cad5a164e6bd553abaf7`；新 Result revision 5 |
| Answer 同键重放 | 201，Result/Answer ID 与首次完全一致 |
| 旧客户端冲突 | 仍使用 revision 4 及旧 parent 的另一请求得到真实 409；`error.code=p2_revision_conflict`，`details.reason=p2_revision_conflict`，后续 GET 重读为 revision 5 |
| Material 201 | `p2mat_5e43d4054e34764f9f148bb770925e0e6b03c4b83ec5114912ff00b7198b6cf1`；新 Result revision 6 |
| Material 同键重放 | 201，Result/Material ID 与首次完全一致 |
| Material 语义 | `verification_state=pending`，`adoption_status=adopted_as_unverified_observation`，`formal_effect=none`，`completeness=EXCERPT` |
| 最终 Result | `p2res_e518330f89aa8a906544867e0543fa30269c498ce40d258bbfa97d2c5fdb5472` revision 6；SHA256 `169b69afeb2ce8e08c220cee28eeb86bfbd618352516ac06557cd4ad82d21206` |
| 同版 Summary | Result ID/revision/SHA 一致；`report_kind=P2_COMPANION_NOT_FORMAL_REPORT`；`formal_effect=none` |

说明：私有副本最初从 revision 3 启动。第一次契约探针在本地断言字段校准前已合法创建 revision 4；该过程未写固定根，也未改 Formal。最终可复跑脚本以 revision 4 为起点完成了上表 revision 5–6 全链。另一实际观察为：当新 idempotency key 携带与已有值相同的内容时，后端可返回 201 并复用当前 Result；前端已有校验允许这一合法形态，本轮补了回归测试。

## 重启和无副作用读取

- 容器正常 restart 后，固定 Result revision 6、Result SHA、Answer、Material 和同版 Summary 依然以同 ID 读取。
- 重启前后、以及重启后 5 个精确 GET 前后，7 个数据库文件 SHA256 完全一致：
  - `assessment.db` `45d7bb82a60d8efe31d0e1ee31122f031b2916c19d1191780d64d63133c33196`
  - `notice_draft.db` `2c8c8e3d4410a5ae6169c85689612f47ed95099577452f8274a6761d9e80e550`
  - `notice_source.db` `3a1f0c57fb1c1c1e3edba94f7bfe2c043cdb7854303d973ad635ad40e752ae1f`
  - `p2.db` `2399f45d9797ddcbcd5f344bc6d51c2a392dc7a566fccbff58a5a1fa59c0a290`
  - `remediation.db` `d133113f9a2736899adce131c37f70cf4434be05da1f97539cf60ddc0b40a588`
  - `report_v2.db` `a9acc6f7a6c9186f8fff4189b2c67fb3e5aaa3e0107ee0cdf9c4b5fc26d5992e`
  - `scans.db` `dd5b7085ce8e1b967cd6b686ec1d32935b71d20b57a15436e3d0513053b5e205`

## 浏览器验收

- 固定 URL 恢复 Assessment v1 + Result revision 6，刷新后仍为同一完整 Result ID。
- 页面显示 `TEST_ONLY`、待核验、未知、`uploaded_material_incomplete`、两个 Material ref、原 Evidence 和同版非正式 Summary。
- 页面继续明示“材料引用不证明来源或适用性”、“不改变正式评估或项目合规状态”。
- 默认不会写入；用户显式勾选授权确认后，服务端问题、资源、文件和来源控件才解锁。
- 用户可验收地址：`http://127.0.0.1:4184/app/scans/scn_fb8856de-91c3-41b7-b758-fcf35c2ea77d/assessment?mode=api&assessment_id=asm_6c664ed7-7c41-512c-bbcc-a178a8edea79&assessment_version=1&p2_result_id=p2res_e518330f89aa8a906544867e0543fa30269c498ce40d258bbfa97d2c5fdb5472&p2_revision=6`

## 代码和验证

- 新增 `frontend/tests/p2-live-write-acceptance.mjs`：限定回环地址和既有 `TEST_ONLY` Result，不自动 init/apply；提供 `write` 与重启后 `verify` 两模式。
- 更新 `frontend/tests/p2-workflow.test.mjs`：增加 201 内容去重可复用当前 Result 的合法回执用例。
- 真实写入回执：`output/receiver-runtime/p2-live-write-20261015/receipt.json`（本机 ignored 验收产物）。
- 前端全套：`145/145 PASS`。
- TypeScript `tsc --noEmit`：PASS。
- Vite 生产构建：PASS，60 modules。
- 写入验收：9 次主链请求，重启后 5 次精确 GET，全部通过。
- 本轮未新增依赖，未修改后端、公共 Schema 或 Formal Assessment。

## 仍不由本回执关闭的门禁

1. 正式锁定镜像 `sha256:6510aeaf...` 的提供/重锁定与正式接收签收。
2. 真实项目材料与获授权审核人的许可适用性结论；当前材料必须继续为 pending。
3. 生产 NOTICE 采集、不可变草稿和正式 Report 链。
4. 旧 v6 Formal 原报告与完整发布候选的 Owner 最终审查。
5. 真人 Gold/盲集、对比消融、端到端性能和演示材料的最终竞赛门禁。
