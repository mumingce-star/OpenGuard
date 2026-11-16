"""Executable, fixed-corpus B02-A metrics; not a claim about all repositories."""

from benchmarks.run_static_assets import run_case_file


def test_b02a_v2_fixed_corpus_has_reproducible_micro_metrics():
    result = run_case_file("benchmarks/cases/static-ai-assets-v2.json")
    pairs = [(set(case["expected"]), set(case["predicted"])) for case in result["cases"]]
    tp = sum(len(expected & predicted) for expected, predicted in pairs)
    fp = sum(len(predicted - expected) for expected, predicted in pairs)
    fn = sum(len(expected - predicted) for expected, predicted in pairs)
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    f1 = 2 * precision * recall / (precision + recall)
    assert (tp, fp, fn) == (17, 0, 0)
    assert (precision, recall, f1) == (1.0, 1.0, 1.0)
    assert result["scanner"] == "openguard-static-ai-detector/0.3.0"
