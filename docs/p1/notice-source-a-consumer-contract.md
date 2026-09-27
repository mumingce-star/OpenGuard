# NOTICE source：后端 A 消费交接包

状态：`候选交接，等待 A 接受`。本文件不启用 factory/API/Report，也不表示 CZ collector 已进入 A 的生产存储。

## A 必须接受的输入

A 只接收由 CZ validator 通过的 canonical package，再由 A 自己构造 `ValidatedNoticeSourceInput`。A 必须重新验证而不是信任包内自述：

1. `scan_id` 对应真实终态 `completed|partial` ScanRun；
2. registry revision、input digest、inventory digest 与实际 ScanRun 一致；
3. package bytes SHA-256 等于 `package_hash`，且小于等于 8 MiB；
4. coverage 为 `completed` 时两类缺口为空；为 `partial` 时 `omissions` 或 `gap_codes` 至少有一项；
5. Formal Assessment 的 id/version/scan/facts hash 与当前事实闭包一致。

只有 `NoticeSourceBindingService.bind()` 可以从 STAGED 形成 BOUND。任何 caller 构造的 BOUND、binding hash、verified flag、facts hash 或 assessment binding 均必须拒绝。Reader 仅可读取已 BOUND 对象；没有数据、facts hash 不同或 assessment version 不同必须返回空，不得重放 scanner、collector 或网络。

## 状态与语义

`pending`、`review_required`、`license_expression_id=null` 原样保留。LICENSE 的 `text_observed`、独立 NOTICE 观察、provider 声明和 gap 是不同事实；A 不得用其中任一项推导授权、适用许可证、义务或违规。

## 交接验收回执

执行 `tests/unit/test_p1_notice_source_binding.py` 时，A 必须单列回执如下测试组，而不能只给总数：

- tamper/replay/conflict 与 ScanRun/Assessment/revision/facts 边界；
- 8 MiB package、SQLite full、私有权限与 sidecar/symlink；
- 关闭重开后 BOUND-only reader 的字节和 binding 一致性；
- partial 的 omissions/gap_codes 无丢失；
- INSERT 异常事务 rollback、不产生伪 BOUND。

当前此组的 fixture 明确是 `TEST_ONLY_NOTICE_SOURCE_INPUT`，不是 CZ collector 的生产输出。因此 A 在接线前还必须增加一个“CZ validator 输出 -> A admission”的适配测试；该测试不可重用正式 Gold、不可写入公共 API。A 接受后，Root 才能将本任务纳入提交/发布门禁。
