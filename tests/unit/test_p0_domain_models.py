import copy
import json
import sys
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.domain.models import ScanRun  # noqa: E402


SAMPLE_PATH = ROOT / "examples" / "sample-scan-result.json"
SCHEMA_PATH = ROOT / "schemas" / "p0" / "scan-result.schema.json"


def load_sample() -> dict:
    return json.loads(SAMPLE_PATH.read_text())


def test_sample_validates_with_pydantic_and_exported_json_schema() -> None:
    sample = load_sample()
    scan = ScanRun.model_validate(sample)
    schema = json.loads(SCHEMA_PATH.read_text())

    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(instance=sample, schema=schema)

    assert scan.contract_version == "0.1.0"
    assert scan.summary.finding_counts["review_required"] == 1


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda value: value.update(id="scan_wrong"), "id must use the scn_ prefix"),
        (lambda value: value["components"][0].update(confidence=1.01), "less than or equal to 1"),
        (lambda value: value.update(created_at="2026-09-01T12:00:00"), "UTC"),
        (lambda value: value["evidence"][0].update(locator="/private/secret.txt"), "relative POSIX"),
        (lambda value: value["evidence"][0].update(end_line=9), "end_line"),
        (lambda value: value.update(unexpected="forbidden"), "Extra inputs are not permitted"),
        (
            lambda value: value["components"][0].update(
                evidence_ids=["evd_423e4567-e89b-12d3-a456-426614174000"]
            ),
            "unknown evidence reference",
        ),
        (lambda value: value["summary"].update(component_count=99), "summary must be calculated"),
        (lambda value: value.update(finished_at=None), "terminal scan status requires finished_at"),
        (lambda value: value.update(status="failed"), "failed scan requires at least one structured error"),
    ],
)
def test_contract_rejects_key_invalid_inputs(mutate, expected: str) -> None:
    invalid = copy.deepcopy(load_sample())
    mutate(invalid)

    with pytest.raises(ValidationError, match=expected):
        ScanRun.model_validate(invalid)
