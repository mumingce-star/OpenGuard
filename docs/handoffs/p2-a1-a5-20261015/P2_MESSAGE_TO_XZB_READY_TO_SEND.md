> GitHub脱敏发布副本：本地原件保持不变。本文中的历史文件路径仅是来源定位，并非本次附带的GitHub文件；本次仅上传同目录五份交接文档，不含源码包、运行镜像、数据或历史证据附件。原件与发布副本身份见本目录Manifest及Git提交。

# 给xzb的交接消息草稿

本轮A1—A5已做只读核对，结论是PARTIAL_HANDOFF_READY。

你已收到的ec4c统一TEST_ONLY包无需再索取或重包：ZIP Hash保持743600b7748d07df7dcb587617cfc3825547d58e53cad33eb95c348905275854；44项清单和731源码本轮核对一致。三例固定ID、合同/DTO、176次HTTP和27次恢复GET继续引用原件；后两项属于发送机证据，不代替你的接收机验收。

本轮新增了三项索引：

- 已有镜像tar位置与独立SHA。指定6510aeaf…是OCI index摘要，tar SHA是327e3e5e…；完整值见索引。镜像声明amd64，但扫描启动器有aarch64限制，且第三方分发仍待Owner确认。先确认你的目标机架构，不能把这个历史运行环境当作已内置ec4c和最新前端的完整镜像。
- 只读验收与可重置L2写入的两套私有根配置提案。没有创建新根或启动服务；固定样本不能CAS改写、init/apply。P2_READONLY也不是全站只读开关。
- cz六件已在本地固定commit 7caddf4e870b5a0da561359cf85b4e8e66662cda核验，统一ec4c未包含。npm材料及历史正常工厂接纳可追溯；M1仍缺正式来源接纳/新增事实和真实范围、人审，不能把旧r3观察当新事实。

请直接转交两组既有原件，不必重新推送或重测：

1. P2_FRONTEND_SOURCE_20261013.json、其81份原字节及聚合算法、P2_STAGE2_TO_5_RECEIPT_20261013.md/D1原回执。当前A可见材料只有你的最新说明，不会拿旧commit否定已实现的L1/L2功能。
2. NOTICE仅fixture补Hash窄修的diff、精确被测候选、433/433原JUnit与日志，以及维护者审查/进入候选的证明。历史431/433不能用来否定后续修复，但当前也还不能签集成PASS。

旧v6 Formal仍需原件持有人给准确Assessment v6的JSON/HTML与Hash，或由Owner保留缺件限制；这不挡住其他前端工作。

待固定组合、兼容性及相应授权到位后，由你/Codex在目标机完成镜像身份、新私有根恢复、27精确GET及重启、独立L2/CAS/幂等/旧结果核对和浏览器验收，再交A/Owner复核。公开Git/ZIP新扫描、镜像重建和真实人审不能由本次只读交接自动授权。

附件为本轮总报告、接收索引、Manifest和门禁矩阵。保留OVERALL=PARTIAL、OWNER_FINAL_ACCEPTANCE=PENDING_OWNER_DECISION、PUBLISH_AUTHORIZATION=NOT_GRANTED。

（本文件为待发送草稿；Codex未发送给xzb。）
