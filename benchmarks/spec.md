# OpenGuard-Bench P0 protocol

The first batch reuses the scanner teammate's five synthetic source cases in `cases/static-ai-assets-v1.json` (upstream implementation `1c7239e`, branch tip `89c8ba2`). The expected labels are preserved unchanged. Their author-provided labels are reviewed here against source snippets; no independent human double annotation is claimed.

`run_static_assets.write_result` invokes the current detector on source text. It records actual assets, Evidence, detector version and case SHA. `evaluate_scan_result` computes per-case and micro-aggregated TP/FP/FN, precision, recall and F1 using exact resource labels. Duplicate occurrences within one case count as one resource. When a metric denominator is zero, the evaluator returns zero; therefore the correct negative case has zero TP/FP/FN and is not itself scored as a positive detection.

`deploy/smoke.py --bench-cases` independently submits the same sources to the existing ZIP HTTP API and checks risk/Evidence/report integration. A generic-URL-only negative case honestly ends with `dependency_manifest_not_found`, zero resource summary and a 409 resource response; it has no report. This expected no-resource outcome is not an infrastructure failure or proof of a completed empty scan.

These five cases test basic model/dataset/API recognition and a negative control, not production accuracy, license correctness, AI suggestion quality or full P0 completion. Broader real-repository labels and human review remain future evidence work, not a prerequisite invented for this bounded first-batch integration.
