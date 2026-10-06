# 自动静态范围 Bench

`auto_static_bench.py` 是一个无人值守的、可复算的**限定静态范围**评测入口。它从
`auto-static-sources.json` 中 30 个候选公开 GitHub 仓库（12 个 holdout）解析一次 `HEAD`，
随后只使用解析出的 40 位 commit 下载原始 ZIP。`freeze.json` 保存来源 URL、commit、
原始 ZIP SHA-256、UTC 抓取时间、根 LICENSE 的明确 SPDX 标识或项目元数据字面声明
（否则为 `unknown`）、声明来源文件哈希和失败原因。`catalog.json` 保存原始 30 项
来源目录，计分前须通过目录哈希和逐项身份校验。原始第三方 ZIP 只保存在本机被 Git
忽略的 `benchmarks/results/local/`。

```powershell
$env:PYTHONPATH = 'backend'
py -3.12 -m benchmarks.auto_static_bench freeze benchmarks/auto-static-sources.json benchmarks/results/local/auto-static-YYYYMMDD
py -3.12 -m benchmarks.auto_static_bench freeze benchmarks/auto-static-sources.json benchmarks/results/local/auto-static-YYYYMMDD-r2 --reuse benchmarks/results/local/auto-static-YYYYMMDD
py -3.12 -m benchmarks.auto_static_bench freeze benchmarks/auto-static-sources.json benchmarks/results/local/auto-static-YYYYMMDD-r3 --reuse benchmarks/results/local/auto-static-YYYYMMDD-r2 --retry-failed
py -3.12 -m benchmarks.auto_static_bench evaluate benchmarks/results/local/auto-static-YYYYMMDD baseline
py -3.12 -m benchmarks.auto_static_bench audit benchmarks/results/local/auto-static-YYYYMMDD baseline
py -3.12 -m benchmarks.auto_static_review benchmarks/results/local/auto-static-YYYYMMDD baseline benchmarks/results/local/auto-static-YYYYMMDD/review-train-dev.json
py -3.12 -m benchmarks.auto_static_bench compare benchmarks/results/local/auto-static-YYYYMMDD/metrics/baseline.json benchmarks/results/local/auto-static-YYYYMMDD/metrics/candidate.json 0.3.0 benchmarks/results/local/auto-static-YYYYMMDD/rule-change.json
```

冻结目录不可覆盖；重采集必须使用新目录并保留旧目录。每次预测使用新 `run_id`，
避免覆盖预测或指标。运行前 oracle 会执行已知答案与变形自检；失败则不计分。
不执行、不安装目标仓库代码。ZIP 限额、路径、符号链接和 UTF-8 检查失败时，
样本保持 `failed`，并计入总数及失败率。

`audit` 完全只读且不联网、不调用 Detector 或 oracle：核验目录与冻结账本、
每个固定 ZIP SHA-256、Gold 与预测文件哈希、样本身份/版本、计分集合、误差 ID、
分组汇总和失败样本保留。缺件、篡改或聚合不一致会失败关闭；`compare` 在
计算规则变更前也先审计两次输入。它只证明已保存产物之间的完整性与一致性，
**不证明机器 Gold 的语义正确、第三方 ZIP 的再分发权或评测等级已获人工批准**。
收据未做独立数字签名；能同时改写整个本机目录的对手仍需外部固定哈希或可信发布记录约束。
一个 Detector 观察可有不同 evidence ID 但落到相同评测匹配键；审计将其单列为
`repeated_match_keys`，不擅自删除证据或把它们额外计作 TP/FP。

`auto_static_review` 在审计通过后生成只写一次的人工复核队列，包含来源 URL、固定
commit、输入/Gold/预测哈希、定位及机器分歧类别，但不复制第三方正文，也不填写
裁决。默认只列 train/dev 个案；`--include-holdout` 必须显式指定，且只能由负责
封存后复核的人使用。失败样本按 split 汇总；默认输出不含 holdout 的失败详情。
当前自动评测的原始 `metrics/` 仍含 holdout 错误明细，所以这九个样本不是未泄露的
正式盲 holdout；正式 G5/G6 需要重新封存并限制访问。机器分歧仅是待裁决候选，
不能直接当成已确认 FN/FP，也不能驱动无反例验证的规则修改。

独立 Gold 只覆盖 oracle 明确支持的字面量 Python AST、普通 JS/TS 导入与构造、
JSON/TOML/YAML 配置、`.env` 键和 Hugging Face/ModelScope 字面量 URL。
含动态/歧义构造的整个文件不进入计分，数量记为 `unscored_files`；预测若落在
oracle 不能判定的行，单列为 `unscored_predictions`，不充当 FP；不支持、
超大、非 UTF-8 和符号链接文件计入 `skipped_files`。同一原始快照的 Gold 写入
`gold/` 后不可改写；预测、指标、运行收据分别写入 `predictions/`、`metrics/`、
`runs/`。匹配键固定为样本、路径、行号、资源类型、provider、名称和文件 SHA-256。
冻结绑定 oracle 版本及源码哈希；预测和运行收据绑定 Detector/规则版本、Detector
源码哈希、配置哈希及输入哈希。配置与运行收据还绑定运行器源码 SHA-256，
避免计分或错误分类代码变化后仍把两次运行误认为同一评测配置。指标按
train/dev/holdout 分开，失败样本不会从分母中删除。

误差表只为可确定的 FN 标 Tier A/B；动态或不安全构造通过 `unscored_files`
报告，不能伪称 Tier C 已有可计分 FN。FP 原因若不能从结构证据直接判定，
保留 `unclassified`。`compare` 将两次相同冻结输入的误差 ID 与 holdout 指标
绑定到规则版本；不同输入哈希拒绝比较。

本工具的 `automated_scope_ready` 仅表示其受限静态子集满足至少 20 个已计分样本、
至少 5 个已计分 holdout、零已冻结输入的完整性/检测失败及非空 holdout 正例条件。
抓取失败仍留在原始 20–30 项分母和 `failure_rate` 中，并不凭借替补样本消失。
现有 Bench 2.0 的可报告等级要求真人盲审，
故本工具始终输出 `bench_2_reportable=false`。自动结果不能代替 G5 真人 Gold，
也不能解释为真实仓库所有 AI 资源的总体召回率或授权结论。

2026-10-06 本机首次冻结 30 项来源，实际固定 25 项、其中 holdout 9 项；
另 5 项采集失败留在 `freeze.json`，未从分母移除。源码绑定的本机运行
`baseline_v5_audit` 在此范围获得 TP=2654、FP=292、FN=48，Precision=0.9009、
Recall=0.9822、F1=0.9398；9 个可计分 holdout 的 F1=0.9698。文件计分覆盖率为
0.8547，预测计分覆盖率为 0.9341，30 项来源的失败率为 0.1667。这些指标仅代表
oracle 支持的静态结构，292 个 FP 仍不能凭机器比对直接认定为真实误报。
本机只读审计通过，并发现 18 个重复匹配键（不是 18 条已证实的错误候选）；
本机 train/dev 待复核队列包含 44 个机器 FN、270 个机器 FP、14 组重复匹配键；
5 个采集失败均保留在总账，默认队列只展开非 holdout 的失败详情。
原始 ZIP、Gold、预测、指标和
收据留在被忽略的本机目录，不随源码仓库分发。跨机器复现应重新采集并核对
固定 commit 和原始 ZIP SHA-256；只复用仓库 URL 不保证输入字节完全一致。
