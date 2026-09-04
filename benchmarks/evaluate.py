"""Small transparent evaluator for versioned OpenGuard-Bench golden cases."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class Metrics:
    true_positive: int
    false_positive: int
    false_negative: int

    @property
    def precision(self) -> float:
        denominator = self.true_positive + self.false_positive
        return self.true_positive / denominator if denominator else 0.0

    @property
    def recall(self) -> float:
        denominator = self.true_positive + self.false_negative
        return self.true_positive / denominator if denominator else 0.0

    @property
    def f1(self) -> float:
        denominator = self.precision + self.recall
        return 2 * self.precision * self.recall / denominator if denominator else 0.0

    def as_dict(self) -> dict[str, float | int]:
        return {"true_positive": self.true_positive, "false_positive": self.false_positive,
                "false_negative": self.false_negative, "precision": self.precision,
                "recall": self.recall, "f1": self.f1}


def _items(case: Mapping[str, Any], field: str) -> set[str]:
    values = case.get(field)
    if not isinstance(values, list) or any(not isinstance(item, str) or not item for item in values):
        raise ValueError(f"case {field} must be a non-empty-string list")
    return set(values)


def evaluate_cases(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Evaluate exactly keyed expected/predicted labels without sampling.

    Each case requires a stable id plus `expected` and `predicted` string
    lists.  It intentionally reports raw counts so an empty prediction cannot
    be presented as a successful benchmark.
    """
    seen: set[str] = set()
    total = Metrics(0, 0, 0)
    per_case: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, Mapping) or not isinstance(case.get("id"), str) or not case["id"]:
            raise ValueError("case requires a non-empty id")
        case_id = case["id"]
        if case_id in seen:
            raise ValueError("duplicate case id")
        seen.add(case_id)
        expected, predicted = _items(case, "expected"), _items(case, "predicted")
        metrics = Metrics(len(expected & predicted), len(predicted - expected), len(expected - predicted))
        total = Metrics(total.true_positive + metrics.true_positive, total.false_positive + metrics.false_positive,
                        total.false_negative + metrics.false_negative)
        per_case.append({"id": case_id, **metrics.as_dict()})
    return {"case_count": len(per_case), "metrics": total.as_dict(), "cases": per_case}


def evaluate_file(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid benchmark JSON") from error
    if not isinstance(payload, Mapping) or set(payload) != {"version", "cases"} or not isinstance(payload["version"], str):
        raise ValueError("invalid benchmark document")
    if not isinstance(payload["cases"], list):
        raise ValueError("benchmark cases must be a list")
    result = evaluate_cases(payload["cases"])
    return {"version": payload["version"], **result}
