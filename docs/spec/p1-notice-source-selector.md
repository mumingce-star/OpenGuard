# P1 NOTICE Source — CZ-S1 Production Candidate Selector

状态：`CZ_SELECTOR_READY_FOR_OWNER_REVIEW`（仅选择器；不是 A4 lifecycle 状态）。

开发基线：`integration/p1@92e22beb8bf5b83494d1e0f7a1ca741dfdc43742`。CZ-S1 后续工作必须从
`codex/cz-s1-selector-92e22be`（该精确基线的直接分支）开始；历史 `064a3d03...` 不再作为开发起点。
本次仅更新基线，不改变下文任何选择、关系、容量或授权语义。

## 输入与输出

公开 API 是 `select_notice_source_candidates(inventory: Inventory) -> SelectorResult`。输入必须是可信
`Inventory` 的元数据；任何其他输入或重复路径均拒绝为 `ValueError("notice_source_inventory_invalid")`。
选择器不读取文件正文，不接收 session，不访问工作区、网络、Git、scanner、AI、Registry、Assessment 或 A 侧存储。

结果的 `candidates` 是可直接交给现有 `collect_notice_source_package(..., candidates=result.candidates)` 的
`tuple[NoticeSourceCandidate, ...]`。`SelectorResult.truncated` 和 `omitted_count` 只表达候选覆盖损失，绝不表示
被忽略的文件不存在 NOTICE、许可义务或任何法律结论。

## 冻结选择规则

1. 仅检查每个 `InventoryEntry.relative_path` 的 basename；root 与任意嵌套目录等价。
2. basename 以 Unicode `casefold()` 做大小写无关比较，候选 stem 精确为 `NOTICE`、`LICENSE`、`LICENCE` 或 `COPYING`。
3. 仅允许无扩展名、`.txt` 或 `.md` 扩展名（扩展名同样大小写无关）；`README`、源码及其他后缀不选择。
4. 绝不从目录名推断 relation。每个候选固定为 `relation_state="unresolved"`、`subject=None`、
   `basis="inventory_path_candidate_only"`。
5. 输出按 exact `relative_path` 的 UTF-8 bytes 升序。`locator` 原样等于该 Inventory 条目的路径；不规范化、不猜测、不构造路径。
6. `observation_key` 为固定 UUIDv5 namespace `a669e60d-3d93-58f5-9e41-427b4b5899cb` 对 exact `relative_path` 的派生值，格式
   `notice-source-candidate:<uuid>`。它稳定、可重算、路径间唯一（受 UUIDv5 碰撞概率约束）且小于 256 字符。
7. 先完成全量排序，再保留前 `MAX_ITEMS=1024` 项；剩余数量精确写入 `omitted_count`，并将 `truncated=True`。零候选合法，返回
   `candidates=()`、`truncated=False`、`omitted_count=0`。

## 非目标与消费约束

selector 不基于 `size_bytes` 过滤。超大文件、读取配额和 UTF-8 可读性由既有 collector 用显式 coverage/gap 状态表达。
候选 basename 仅表示“可能值得尝试观察的 NOTICE/许可来源”，不产生 LicenseExpression、Obligation、Finding、Authorization、
Formal Resource ID 或 Evidence ID。A4 后续必须消费 `truncated/omitted_count`，不得静默丢弃第 1025 个及之后的候选。
