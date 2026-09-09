# OpenGuard-Bench P0 protocol

The first batch reuses the scanner teammate's five synthetic source cases in `cases/static-ai-assets-v1.json` (upstream implementation `1c7239e`, branch tip `89c8ba2`). The expected labels are preserved unchanged. Their author-provided labels are reviewed here against source snippets; no independent human double annotation is claimed.

`run_static_assets.write_result` invokes the current detector on source text. It records actual assets, Evidence, detector version and case SHA. `evaluate_scan_result` computes per-case and micro-aggregated TP/FP/FN, precision, recall and F1 using exact resource labels. Duplicate occurrences within one case count as one resource. When a metric denominator is zero, the evaluator returns zero; therefore the correct negative case has zero TP/FP/FN and is not itself scored as a positive detection.

`deploy/smoke.py --bench-cases` independently submits the same sources to the existing ZIP HTTP API and checks risk/Evidence/report integration. A generic-URL-only negative case honestly ends with `dependency_manifest_not_found`, zero resource summary and a 409 resource response; it has no report. This expected no-resource outcome is not an infrastructure failure or proof of a completed empty scan.

These five cases test basic model/dataset/API recognition and a negative control, not production accuracy, license correctness, AI suggestion quality or full P0 completion. Broader real-repository labels and human review remain future evidence work, not a prerequisite invented for this bounded first-batch integration.

## P0 closeout: first 12 real review candidates (2026-09-08)

Owner and cz independently review original source before comparing answers, then record disagreements and AI applicability. No machine-produced expected labels are supplied here. Four requested strata have three records each. These are selected from existing detections, not a random sample or a recall benchmark; do not infer missed-resource rates from this set. Unknown authorization remains unknown. Previously viewed system output must be disclosed by each reviewer. Source hashes were freshly verified against the fixed GitHub revisions; candidate membership is not a human approval.

Historical scan results identify candidates only; final acceptance must bind the agreed OpenGuard commit and rerun affected paths. Owner will provide both human reviews and Windows receipts for Root to evaluate. No acme/synthetic examples count toward these twelve.

| ID | Stratum | Review object | Fixed source / field | Source SHA-256 |
|---|---|---|---|---|
| R01 | 软件 | pydantic | [openai-python / pyproject.toml:dependency-groups.pydantic-v1[0] / line field/lock record](https://github.com/openai/openai-python/blob/be928151372e4b62adb4a1571cda52ad759b38be/pyproject.toml) | `a3190a42805422ecebc40fd522d2638a8c17c7149e79051451e8e24bb4a03258` |
| R02 | 软件 | pycparser | [openai-python / uv.lock / line field/lock record](https://github.com/openai/openai-python/blob/be928151372e4b62adb4a1571cda52ad759b38be/uv.lock) | `e70d75cd22a5411a38517060cce262d3ed7e07c353865d0c363c2235dec80a15` |
| R03 | 软件 | anyio | [openai-python / uv.lock / line field/lock record](https://github.com/openai/openai-python/blob/be928151372e4b62adb4a1571cda52ad759b38be/uv.lock) | `e70d75cd22a5411a38517060cce262d3ed7e07c353865d0c363c2235dec80a15` |
| R04 | 模型 | Qwen/Qwen3-Next-80B-A3B-Thinking | [smolagents / docs/source/en/examples/multiagents.md / line 39](https://github.com/huggingface/smolagents/blob/30bb1161095dbae2271e6bc3cc4c219cc3897a57/docs/source/en/examples/multiagents.md) | `fe70642c6a64e55e32344edb12955abc09c5fab55857fb4986b3369a040ef8f7` |
| R05 | 模型 | black-forest-labs/FLUX.1-dev | [smolagents / docs/source/en/tutorials/tools.md / line 258](https://github.com/huggingface/smolagents/blob/30bb1161095dbae2271e6bc3cc4c219cc3897a57/docs/source/en/tutorials/tools.md) | `57b9f1deeb7448f456f74cbbd6401241313729f7741cbe24c6dc298cfb47de02` |
| R06 | 模型 | intfloat/multilingual-e5-large-instruct | [litellm / scripts/sync_together_ai_models.py / line 138](https://github.com/BerriAI/litellm/blob/168a0055a244acdcf97c330c52e085ab40b1424c/scripts/sync_together_ai_models.py) | `1ac3017acb5819e088d3645f711d9b87752dd40ef6f5e0753cc3bc11dc738c7f` |
| R07 | 数据集 | smolagents/GAIA-annotated | [smolagents / examples/open_deep_research/README.md / line 64](https://github.com/huggingface/smolagents/blob/30bb1161095dbae2271e6bc3cc4c219cc3897a57/examples/open_deep_research/README.md) | `f66031c51430af60d61e42177b3e48d84c6ae23d483cfee2eb406b084e992732` |
| R08 | 数据集 | smolagents-benchmark/benchmark-v1 | [smolagents / examples/smolagents_benchmark/run.py / line 46](https://github.com/huggingface/smolagents/blob/30bb1161095dbae2271e6bc3cc4c219cc3897a57/examples/smolagents_benchmark/run.py) | `a1db747335affe27b9c28f99c6fda13c614ba047f2ff8a47486ae4339d420da2` |
| R09 | 数据集 | m-ric/agents_medium_benchmark_2 | [smolagents / README.md / line 258](https://github.com/huggingface/smolagents/blob/30bb1161095dbae2271e6bc3cc4c219cc3897a57/README.md) | `131628d2669b4ee983c715002b57ea4b375b62c8502f6354b8d9fdf3fbc39f8d` |
| R10 | API | anthropic | [litellm / litellm/anthropic_interface/readme.md / line 49](https://github.com/BerriAI/litellm/blob/168a0055a244acdcf97c330c52e085ab40b1424c/litellm/anthropic_interface/readme.md#L49) | `649aa8e07ccf2154fa5f6a41884f37cfd7bb1f1c569962b7d6dc056db8440cf7` |
| R11 | API | google | [litellm / litellm/google_genai/Readme.md / line 27](https://github.com/BerriAI/litellm/blob/168a0055a244acdcf97c330c52e085ab40b1424c/litellm/google_genai/Readme.md) | `05eb67a90e2c711d42d1d6e17a380e41f6bd67fcf51f6e08900166c72123333a` |
| R12 | API | openai | [litellm / litellm/router.py / line 974](https://github.com/BerriAI/litellm/blob/168a0055a244acdcf97c330c52e085ab40b1424c/litellm/router.py#L974) | `3ad43f8503791ea9bee2db8d2953c0f13edaab65ab0aab6f8372ffc6aa9fea57` |

Per review: reviewer/date/prior exposure; cited source field or line; reference vs license declaration vs authorization; uncertainty; final disagreement resolution. Only after independent notes compare system risk/evidence and AI steps. Findings of evidence mix-up, fabrication, unsupported authorization claims or unusable reports block signoff until fixed and retested. No human review is yet recorded by this candidate list.


### 2026-09-09 核对与纠正

复核入口：[12条真实记录复核表](real-resource-review.md)。R10/R12旧候选整理按名字优先匹配了同名软件组件，误把pyproject依赖字段列为API证据；本表已按实际api资产ID纠正。历史扫描报告未修改。R01–R03存在同名多版本，复核表固定资源ID及版本/约束，不可只按名称匹配。

以现存可下载报告为输入，12条Resource→Risk→AI关联、34次Evidence引用及25个固定源文件Hash核验通过。属于机器预核对，不是双人标注通过或准确率评分。smolagents与litellm报告本身为partial；候选可供原文复核，不将整次扫描宣称completed。两名真人每人12条判断尚待提交，最新代码的最终签收仍须结合约定回执。
