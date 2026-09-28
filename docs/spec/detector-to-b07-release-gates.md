# Detector 至 B07 的八项交付门禁

状态：`冻结执行顺序，未发布`（2026-09-27）。本文件把负责人指定的八项工作拆为不可互相替代的责任包。任何“通过”都必须同时具有提交版本、可复现命令、结果回执和责任方签收；没有这些证据时状态只能是进行中或阻塞。

| 编号 | 责任方 | 范围与冻结边界 | 前置条件 | 完成证据 |
| --- | --- | --- | --- | --- |
| G0 | Root/Sol | `Detector 0.3` 仅识别 AI资源候选；`License/NOTICE facts detector` 仅消费哈希固定 facts。二者不得共用编号、Gold、输出或授权语义。 | 无 | 本契约、独立输入/输出测试、版本号和变更记录 |
| G1 | 后端 B | Detector 0.3 离线开发集与 FN 优先修复；只允许 AST、受限字面量结构化配置和明确 URL。 | G0 | train/dev/holdout 无 family/content 泄漏；每一个 FN/FP taxonomy 类有 fixture；非 Gold 标记；定向回归 |
| G2 | 后端 B | NOTICE source 独立验收和 A 交接包。 | G0 | 篡改、绑定边界、容量、重启、partial 和只读 reader 均为独立回执；消费契约不含生产接线 |
| G3 | 后端 A | 可信 STAGED/BOUND 存储接入，NoticeDraft、Profile、Report 的固定 binding。 | G2 及 A 对契约确认 | 真实 ScanRun/Assessment revision、input/inventory/facts/package hash 全闭包；重启读回；API/Report 不回读上游；迁移与安全回归 |
| G4 | 前端 | Profile、NOTICE、Bench、性能页面与浏览器回执。 | G3、B05/B07 受控 artifact | 浏览器只显示已绑定状态和受控统计；不把 pending 显示为授权；页面截图/录屏、真实 API E2E 和下载 hash 回执 |
| G5 | 两位真人 + 裁决人 | 双盲 Gold 和第三位真人裁决。 | G1、B06 可授权候选及盲审包 | 两名不同 reviewer 的独立性/exposure 签收、提交 hash、分歧与第三人裁决；AI 非唯一批准者；gold freeze SHA |
| G6 | B05 执行责任方 | 正式评测。 | G5、冻结 detector/config/matching policy | 新 immutable revision；预测仅在 Gold freeze 后产生；holdout 一次性运行；Precision/Recall/F1、失败率和 FN/FP 逐项可追溯 |
| G7 | B07 执行责任方 | 真实性能测试。 | G3/G4 的目标版本固定 | 至少两条同环境 controlled receipt；输入/配置/结果 hash、阶段耗时、失败率、环境摘要；不得用开发或生产偶发运行代替 |
| G8 | 后端 A/Root | Windows `fcntl` 兼容与全量回归。 | 代码修复或平台边界实现 | Windows 上不会在 collection 时无条件导入 `fcntl`；若 POSIX 功能不可用须显式 fail-closed、可诊断且可被测试；全量 pytest、前端、Node、Java 结果均记录 |

## G0 编号与语义

- `Detector 0.3`：版本号 `openguard.static-ai-detector/0.3`，输入为已读取相对路径文本，输出为 `AIAsset` 候选和文件行证据。没有许可证/NOTICE/授权输出。
- `License/NOTICE facts detector`：版本号 `openguard.license-notice-facts-detector/0.2`；输入为 caller 固定 SHA-256 的 v2 facts。v3 由 `openguard.notice-license-facts-consumption/1` 只读 adapter 消费，未经独立批准不得转成 v2 或 B02 输入。
- 两条链均固定 `authorization_status=pending`、`license_expression_id=null`；`review_required` 不是违规。LICENSE text、provider label、gap 和 NOTICE observation 分别建模，互不推导。

## 依赖与禁止绕过

```text
G0 -> G1 -> G5 -> G6
G0 -> G2 -> G3 -> G4
G3/G4 -> G7
G8 是 G3/G4/G6/G7 发布前的跨平台回归门禁
```

禁止以开发 fixture 代替真人 Gold、以历史测试代替本次回执、以公开仓库可访问代替可授权引用、以单次运行代替性能数据、以浏览器页面文案代替 hash binding，或以 Windows 收集错误“跳过”完整回归。

## G8 的可接受修复口径

Windows 不能调用 POSIX-only `fcntl` 时，模块导入必须仍可完成。实现可将 POSIX file-lock/descriptor 功能隔离为运行时 capability：不支持的平台对依赖该能力的入口明确返回受控 `unsupported_platform`/fail-closed 状态，而与之无关的 domain、fixture、API contract 和前端测试必须可收集运行。不得用广泛 skip、xfail 或移除安全断言来制造绿灯。

G8 完成后必须以同一锁定依赖环境依次运行 Python 全量、Node 合同集、Java Maven 全量和前端 build/test；每项的 passed/failed/skipped、平台、解释器/包版本和未支持能力均写入不可变回执。任何既有失败需按节点和原因逐项比对，不能只报总数。
