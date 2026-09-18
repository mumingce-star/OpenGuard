# 第二位独立真人盲审工作包

本目录用于 R01-R12 的第二位真人复核。它不替代许可证原文审阅，也不构成法律意见。

## 隔离规则

协调人先运行 `node prepare-blind-packet.mjs <安全输出路径>`，只将生成的盲审包和本目录的模板交给第二评审。第二评审提交前不得查看下列文件、其终端输出、截图或口头转述：

- `../ai-draft.json`；
- `../human-confirmation.json`；
- `../human-amendment-r05.json`；
- `../second-ai-review.json`；
- 任何已生成的分歧或仲裁文件。

盲审包保留被评估的最小断言、原文入口和待评估建议；它**不含**既有五维标签、理由、问题代码或首位裁决。这里的“盲”指对先前答案盲，不是对待审系统断言盲。

## 操作顺序

1. 在与上述文件隔离的目录中生成并核对盲审包 SHA-256。
2. 复制 `second-human-blind-review.template.json` 为新的私有回执文件；不得覆盖模板。
3. 逐条阅读固定 revision 的原文及上下文，填写 R01-R12 的 `resource`、`evidence`、`license`、`risk`、`suggestion` 五维、理由和证据定位。不得以 `null` 提交。
4. 填写独立性声明；若已接触任何被隐藏内容，必须如实标记为 `false`，该回执不能作为独立盲审。
5. 使用 `node validate-blind-review.mjs --packet <盲审包> --review <回执>` 校验。校验通过后冻结回执内容，再交给协调人。
6. 仅在冻结回执校验通过后，协调人和未参与初标的第三位真人才能打开 `adjudication.template.json`，记录逐维分歧与仲裁。AI 不得替代真人仲裁。

标签字典沿用 `docs/spec/scan-result-human-annotation-plan.md`：资源/证据/许可使用 `correct`、`partially_correct`、`incorrect`、`uncertain`、`not_applicable`；风险使用 `accept`、`revise`、`reject`、`uncertain`、`not_applicable`；建议使用 `actionable`、`too_generic`、`incorrect`、`uncertain`、`not_applicable`。

当前工作包只提供材料和校验，不含任何第二位真人的实际判断，也不将批次标记为最终完成。
