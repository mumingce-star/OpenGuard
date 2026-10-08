# B05 自动静态来源完整性复核（2026-10-06）

本记录只复核本机 `auto-static-20261006-r7` 冻结账本和
`baseline_v5_audit` 已保存工件的一致性；不裁决 Gold、FN/FP 语义，
不把自动静态子集提升为正式 Bench 2.0。第三方 ZIP 和具体机器错误明细
留在 Git 忽略的本地目录，不随本记录分发。

## 复核方法与结果

- 运行 `py -3.12 -m benchmarks.auto_static_bench audit benchmarks/results/local/auto-static-20261006-r7 baseline_v5_audit`：`verified`；30 项来源、25 项固定且完成、5 项失败、9 项已计分 holdout、18 组重复匹配键。
- 在内存中重新执行 `prepare_review_queue(..., include_holdout=False)` 并逐字段与已保存的 `review-train-dev-v1.json` 对照：一致。队列有 314 项机器分歧（FN 44、FP 270）、2 项非 holdout 采集失败、14 组非 holdout 重复匹配键；`formal_gold=false`、`reviewer_required=true`。
- 14 组队列内重复键均各有两次观察、两个不同 `evidence_id`。这是同一评测匹配键的多证据观察，不证明候选重复或误报；不得删除证据来改善指标。全体 18 组中的另外 4 组位于 holdout，未在默认队列展开。

## 失败账本（不可从分母删除）

| 样本 | split | 账本原因 | 本轮可确认范围 |
|---|---|---|---|
| `litellm` | dev | `archive exceeds byte limit` | 已记录单一 commit；原始 ZIP 未作为成功快照固定 |
| `llama_index` | dev | `source ref did not resolve to one commit` | 未取得可冻结的单一 commit |
| `crewai` | holdout | `archive exceeds byte limit` | 已记录单一 commit；默认队列不展开 holdout 个案 |
| `openai_cookbook` | holdout | `archive exceeds byte limit` | 已记录单一 commit；默认队列不展开 holdout 个案 |
| `gemini_cookbook` | holdout | `archive exceeds byte limit` | 已记录单一 commit；默认队列不展开 holdout 个案 |

这些是采集器保存的失败原因，不是对远端仓库当前状态或 ZIP 实际授权的独立鉴定。
重新抓取须另建冻结目录、保留旧失败，并核对 commit 与原始 ZIP 哈希；不得覆盖本轮输入。

## 待人工／跨环境关闭

- B/Luna 对机器 FN/FP 逐项查看原始证据、完成独立 Gold 和分歧裁决；当前 39 个 Tier A、5 个 Tier B 仅为机器分类，269 个 FP 仍为 `unclassified`，不能据此直接改规则或宣布消融收益。
- 现有 holdout 错误明细已经存在本机指标工件中，不能称为未泄露的正式盲 holdout。G5/G6 需新封存、限制访问并绑定真人复核和正式收据。
- B/Terra 仅在裁决后补 Detector 反例/规则，保留修改前后 FN/FP 与新 holdout 对比；B07 受控 Linux 数据和 B01/B03/B04 生产证据链不由此复核证明。
