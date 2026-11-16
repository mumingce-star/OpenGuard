# P1 后端 B 固定联验预期 v1

本目录固定 B02 对 `notice-license-facts-v2/facts.json` 的保守输出边界：17 个 Finding 候选、0 个 Obligation 候选。源 facts 以 canonical JSON SHA-256 固定；调用方必须把该外部固定 Hash 传给 detector，不能对已修改输入现场重算后冒充原包。

17 个 Finding 中，14 个只是既有 gap 的 `review_required` 投影，3 个只是 provider 声明未验证提示。它们都不是违规、授权或正式许可证结论。因为输入不存在已验证且适用的许可证表达式，B02 不得生成 Obligation 候选。

复算：

```powershell
node --test tests/p1_license_notice_facts_detector_contract.test.mjs
```
