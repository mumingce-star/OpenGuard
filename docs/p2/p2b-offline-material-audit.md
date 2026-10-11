# P2 B 现有材料离线核对交付

2026-10-11；整体 PARTIAL，源码/测试/脱敏证据在工作树，等待 Owner 复核；未发布。

以 Owner 指定 A 提交 `afca4c26c2fa45fa285fc9cabf48f52c54a59229` 的 P2 v1 为
TEST_ONLY 基线，A 源码、Schema 与合同对当前 HEAD 无差异。本次只新增 B 只读 helper
和离线命令，不接入 A 运行时，不修改既有合同、规则、Formal、数据库或旧回执。

`backend/app/p2b/offline_material_audit.py` 联合校验实际 Material/Result DTO、Result
自摘要、原 Result pin、Material 父 Binding、精确资源版本、引用闭包、现有观察摘要/
大小与七用途原值。重复核对复用原 Material/Result；new_facts=0、新 Evidence ID=[]、
新正向许可建议=[]。七个 null 原样保留，材料继续 user_supplied_unverified/pending。

条款定位支持许可语句、版权与许可声明保留、免责声明、责任限制四个文本锚点。
仅返回原 UTF-8 字节区间和行号，不导出第三方正文；空缺或重复锚点各记 missing/ambiguous。
锚点只证明文字位置，不识别完整许可、不证明适用范围，也不产生许可授权。
可读原字节必须匹配已有 SHA-256/大小/Git blob SHA-1，不能复制模板替代真实原文。

本机未定位到旧 Material 对应原字节，默认本轮三例证据为 metadata_only_not_byte_reverification，
条款位置 bytes_not_re_read。`is-number@7.0.0` 原件已经取得的事实不变，不重复索取或联网；
原字节定位功能用第一方合成文本测试，不能冒称真实 LICENSE 条款已完成本机重读。
lodash 根文件不能推广到 vendor/依赖或 npm 发布归档；express 仅复核原元数据，未调参。

离线复现（现有 Python 3.12 环境，无安装）：

```powershell
$env:PYTHONPATH = 'backend'
$env:PYTHONUTF8 = '1'
& ./.venv/Scripts/python.exe benchmarks/p2b_offline_material_audit.py
& ./.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/unit/test_p2b_offline_material_audit.py tests/unit/test_p2b_candidates.py tests/unit/test_p2b_three_scan_readback.py tests/unit/test_p2b_receipt_closure.py --tb=short
```

命令可在已获准的本地原字节位置使用 `--is-number-license`，仅只读，不抓取、不写库、不上传。
无需用户重新提供原件才能运行默认对账。本次新增 30 项测试，与已有 90 项合计 120 passed、
两条已有 TestClient 弃用警告；测试包含真实回执一致性与合成篡改/文本反例，未发 live GET。
第一次开发自检误用闭包不存在的 after_result 字段导致 KeyError，已改为显式传入原真实 Result
正文并核对闭包 pin；最终组合验收通过，不计作上游合同缺陷。

新增测试验证 null 不可改写、错版本/父绑定拒绝、上传者不得自升 verified、来源记录摘要
不得替代字节 Hash、材料引用不可丢失、字节/Blob 摘要拒绝、UTF-8/CRLF 行号、关键词不足、
重复锚点及重放不增事实。合成样例不是新增真实来源，也不计为真人 Gold。

脱敏结果见 `p2b-offline-material-audit.json`，运行与文件摘要见
`p2b-offline-material-validation.json`。独立 A 接口与材料需求见
[精确交接清单](p2b-a-handoff-requirements.md)。A02/A03/A05 等正式闭环、Owner 范围、
旧 Formal 读回、Windows/NOTICE、baseline 漂移和前端签收未关闭；P2 整体保持 PARTIAL。

没有联网、模型生成、服务启停、数据库写入、stage/commit/push、PR、合并或部署。
未引入依赖或第三方材料，沿用既有资源台账；完整原文、数据库、私有路径不进入交付。
