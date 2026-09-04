# OpenGuard-Bench P0 protocol

Golden cases are versioned JSON. Each case has a stable ID and exact `expected` and `predicted` label lists. `benchmarks.evaluate.evaluate_file` reports TP/FP/FN, precision, recall and F1, including raw counts to prevent empty outputs from appearing successful.

`cases/p0-smoke.json` is a public synthetic smoke set, not a performance claim or a substitute for the planned independently reviewed corpus.
