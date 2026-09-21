# A06 Report V2 原始 writer 兼容 fixture

仅用于永久兼容性测试，不作为运行时实现或部署代码。
来源：负责人 A06 未提交源码 Review 快照（导出时间 2026-09-15T10:46:35Z），基线 commit `2f67aa1809572c73c8c67893753792c4fcd74684`。
两份文件是该基线之上的未提交 Report V2 1.1 成果，不声称它们存在于该 commit 内。
原 Review archive SHA256：`9f4769514289b200adbe499ffaae4aeb5b01900a2ffad851785c2402a4f9efee`。

- report_v2.py：`3aa1a3ab82f51e096bc3586f2969fb56f16f734921f93b656b229d6488a92272`
- report_v2_store.py：`007b5c0509b99409d02132d73bf9eba2a365c29d5ee254439befa1e787b5862c`

测试加载前逐文件断言 Hash，使用临时数据库和合成来源，由原 writer 创建报告，再由当前服务验证离线重放及原始附件字节不变。禁止将 fixture 当作生产修复来源；不包含真实数据库、真实报告或完整备份。
