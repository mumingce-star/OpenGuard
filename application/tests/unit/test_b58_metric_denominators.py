import pytest

from benchmarks.evaluate import Metrics, evaluate_cases


@pytest.mark.parametrize("counts,expected", [
    ((0, 0, 0), (None, None, None)),
    ((0, 0, 2), (None, 0.0, None)),
    ((0, 2, 0), (0.0, None, None)),
    ((0, 2, 3), (0.0, 0.0, 0.0)),
    ((2, 1, 1), (2 / 3, 2 / 3, 2 / 3)),
])
def test_zero_denominators_are_undefined_not_measured_zero(counts, expected):
    metrics = Metrics(*counts)
    assert (metrics.precision, metrics.recall, metrics.f1) == expected


def test_empty_case_not_removed_and_misses_preserved():
    result = evaluate_cases([
        {"id": "empty", "expected": [], "predicted": []},
        {"id": "failed-prediction", "expected": ["resource"], "predicted": []},
    ])
    assert result["case_count"] == 2
    assert result["cases"][0]["precision"] is None
    assert result["metrics"]["false_negative"] == 1
    assert result["metrics"]["precision"] is None
    assert result["metrics"]["recall"] == 0
