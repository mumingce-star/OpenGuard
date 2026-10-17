# P2 三例 TEST_ONLY 前端验收回执（2026-10-15）

## 结论

本回执限定的三项前端工作已完成。三例均来自隔离的真实后端 API，数据属性保持为 `TEST_ONLY` / 受控验收数据；本结论不把样本解释为真实项目许可结论，也不关闭人工许可适用性、生产 NOTICE 或正式锁定镜像门禁。

## 固定验收对象

| 场景 | ScanRun | Assessment | Result | Revision | Material |
| --- | --- | --- | --- | ---: | --- |
| is-number | `scn_fb8856de-91c3-41b7-b758-fcf35c2ea77d` | `asm_6c664ed7-7c41-512c-bbcc-a178a8edea79` v1 | `p2res_eabfaa020c8a91cd4a5a309861ad4f0ab90cae07263d4ac48370b8a02b89fc83` | 3 | `p2mat_c5090e4fd86a58311fab75962e7d545057d2e8b028c358d467f764b225e0c61b` |
| lodash | `scn_bf5f710b-c70e-4255-8060-2a3d55cddcf3` | `asm_71b40610-e7c5-510a-92b2-31d164a633e0` v1 | `p2res_9cd0d08c1ac97283557bdc5154b924c2ba21b517f81f4e8891672e2b41e949fe` | 3 | `p2mat_6a8fdbb975d6d9a10fe19dd6c327a46d971b4a5504cf0a9467162d17ce7e27ce` |
| express | `scn_7b2704b8-9313-46e5-a6ce-4cb716315094` | `asm_a77d8b86-3fcf-5d6a-947e-bc9627a39e85` v1 | `p2res_8286c522bc3e9085c7d1207a445220c2f8ab22fc69495b854df27190366f0146` | 3 | `p2mat_63620942049ad82bc486747c12e442d99a805f3b22468dad853b121a833af970` |

## 浏览器验收矩阵

三例均逐项通过：

- 显示“受控验收数据，仅用于功能验证；不是生产历史或许可证明”；
- 显示固定资源身份、材料引用、原扫描 Evidence、独立 Result 第 3 版及同版摘要；
- `pending`、`unknown`、覆盖限制/证据缺口均按原状态展示；
- 显示“材料引用本身不证明材料来源或适用性”及“未知/待核验不等于已获授权”；
- source Hash 有明确展开入口；实际展开后可见 SHA-256；
- Evidence 控件实际触发并进入对应证据上下文；
- 同版摘要明确标注“非正式报告”，且不能替代或改写 Formal Assessment；
- 固定 URL 恢复到同一 Assessment、Result 与 revision，未使用前端补造字段或第二套结论。

## 自动验证

- P2 相关前端测试：`22/22 PASS`；覆盖精确绑定、错误绑定拒绝、TEST_ONLY/pending/缺口语义、Evidence/source Hash 闭包、材料/回答引用、固定 Result/同版 Summary、只读写入保护等。
- 本轮此前完整前端测试：`144/144 PASS`；TypeScript 与 Vite build：PASS。
- `git diff --check`：PASS。
- 本机 P2 API `http://127.0.0.1:15176/openapi.json`：HTTP 200。
- 前端预览 `http://127.0.0.1:4183/`：HTTP 200。
- 本轮浏览器操作只有 GET/页面交互，没有 POST、init、apply 或正式数据写入。

## 边界

以上三项前端范围可以标记为完成。仍未因此完成的项目级门禁：交接说明锁定镜像的正式接收、人工作用域/许可适用性签认、旧 v6 Formal 原件和生产 NOTICE 链。它们不得反向改写本回执中的前端完成结论，也不得由前端伪造。
