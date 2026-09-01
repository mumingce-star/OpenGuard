import copy
import json
import re
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
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "p0" / "a1-boundary-fixtures.json"


def load_sample() -> dict:
    return json.loads(SAMPLE_PATH.read_text())


def load_boundary_fixtures() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def test_sample_validates_with_pydantic_and_exported_json_schema() -> None:
    sample = load_sample()
    scan = ScanRun.model_validate(sample)
    schema = json.loads(SCHEMA_PATH.read_text())

    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(instance=sample, schema=schema)
    assert schema == ScanRun.model_json_schema()

    assert scan.contract_version == "0.1.0"
    assert scan.summary.finding_counts["review_required"] == 1


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda value: value.update(id="scan_wrong"), "id must use the scn_ prefix"),
        (lambda value: value["components"][0].update(confidence=1.01), "less than or equal to 1"),
        (lambda value: value.update(created_at="2026-09-01T12:00:00"), "UTC"),
        (lambda value: value["evidence"][0].update(locator="C:\\fixture.txt"), "relative POSIX"),
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


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["findings"][0].update(
            resource_kind="component", resource_id=value["ai_assets"][0]["id"]
        ),
        lambda value: value["findings"][0].update(
            resource_kind="ai_asset", resource_id=value["components"][0]["id"]
        ),
        lambda value: value["remediations"][0].update(
            finding_id=value["components"][0]["id"]
        ),
        lambda value: value["obligations"][0].update(
            license_expression_id=value["components"][0]["id"]
        ),
    ],
)
def test_cross_object_references_are_type_checked(mutate) -> None:
    invalid = copy.deepcopy(load_sample())
    mutate(invalid)

    with pytest.raises(ValidationError):
        ScanRun.model_validate(invalid)


def test_partial_scan_with_recoverable_error_is_valid() -> None:
    value = copy.deepcopy(load_sample())
    value.update(load_boundary_fixtures()["partial_scan"])

    scan = ScanRun.model_validate(value)

    assert scan.status == "partial"
    assert scan.errors[0].recoverable is True


def test_partial_scan_without_recoverable_error_is_rejected() -> None:
    invalid = copy.deepcopy(load_sample())
    invalid.update(status="partial", stage="report", errors=[])

    with pytest.raises(ValidationError):
        ScanRun.model_validate(invalid)


@pytest.mark.parametrize(
    "locator",
    [
        "/private/tmp/input.txt",
        "../outside.txt",
        "nested/../../outside.txt",
        r"C:\\Users\\runner\\input.txt",
    ],
)
def test_file_and_manifest_locators_reject_absolute_or_traversal_paths(locator: str) -> None:
    for kind in ("file", "manifest_field"):
        invalid = copy.deepcopy(load_sample())
        invalid["evidence"][0].update(kind=kind, locator=locator)

        with pytest.raises(ValidationError):
            ScanRun.model_validate(invalid)


@pytest.mark.parametrize(
    "message",
    [
        "/private/tmp/secret.txt: scanner failed",
        "scanner failed at /private/tmp/secret.txt",
        "Authorization token=redacted",
        "api_key=redacted",
    ],
)
def test_scan_error_messages_reject_paths_and_credentials(message: str) -> None:
    invalid = copy.deepcopy(load_sample())
    invalid.update(
        status="partial",
        stage="report",
        errors=[
            {
                "code": "scanner_failed",
                "stage": "scan",
                "message": message,
                "recoverable": True,
            }
        ],
    )

    with pytest.raises(ValidationError):
        ScanRun.model_validate(invalid)


def test_ai_candidate_and_ai_remediation_remain_pending() -> None:
    value = copy.deepcopy(load_sample())
    value["evidence"][0].update(
        detected_by="ai_candidate", verification_status="pending"
    )
    value["remediations"][0].update(
        generated_by={"type": "ai", "name": "qwen3", "version": "0.1"},
        verification_status="pending",
    )

    scan = ScanRun.model_validate(value)

    assert scan.evidence[0].verification_status == "pending"
    assert scan.remediations[0].generated_by.type == "ai"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["evidence"][0].update(
            detected_by="ai_candidate", verification_status="verified"
        ),
        lambda value: value["remediations"][0].update(
            generated_by={"type": "ai", "name": "qwen3", "version": "0.1"},
            verification_status="verified",
        ),
    ],
)
def test_ai_candidate_and_ai_remediation_cannot_be_verified(mutate) -> None:
    invalid = copy.deepcopy(load_sample())
    mutate(invalid)

    with pytest.raises(ValidationError):
        ScanRun.model_validate(invalid)


def test_summary_requires_all_four_outcomes_and_non_negative_counts() -> None:
    value = copy.deepcopy(load_sample())
    value["summary"]["finding_counts"] = {
        "pass": 0,
        "warning": 0,
        "review_required": 1,
        "unknown": 0,
    }
    scan = ScanRun.model_validate(value)
    assert set(scan.summary.finding_counts) == {
        "pass",
        "warning",
        "review_required",
        "unknown",
    }

    for invalid_counts in (
        {"pass": 0, "warning": 0, "review_required": 1},
        {"pass": 0, "warning": 0, "review_required": 1, "unknown": -1},
    ):
        invalid = copy.deepcopy(value)
        invalid["summary"]["finding_counts"] = invalid_counts
        with pytest.raises(ValidationError):
            ScanRun.model_validate(invalid)


@pytest.mark.parametrize("status", ["partial", "cancelled"])
def test_terminal_statuses_require_finished_at(status: str) -> None:
    value = copy.deepcopy(load_sample())
    value.update(status=status, stage="report")
    value["errors"] = load_boundary_fixtures()["partial_scan"]["errors"]
    value["finished_at"] = "2026-09-01T12:02:00Z"

    scan = ScanRun.model_validate(value)
    assert scan.finished_at is not None

    invalid = copy.deepcopy(value)
    invalid["finished_at"] = None
    with pytest.raises(ValidationError):
        ScanRun.model_validate(invalid)


def test_unknown_fields_are_rejected_in_nested_objects() -> None:
    invalid = copy.deepcopy(load_sample())
    invalid["provenance"]["ai_model"] = {
        "type": "ai",
        "name": "qwen3",
        "version": "0.1",
        "model_provider": "ollama",
    }

    with pytest.raises(ValidationError):
        ScanRun.model_validate(invalid)


def test_public_boundary_fixture_contains_no_sensitive_or_identifying_strings() -> None:
    payload = json.dumps(load_boundary_fixtures(), ensure_ascii=False)
    forbidden = (
        r"(?i)(?:api[_-]?key|secret|token|password)\s*[=:]",
        r"(?i)(?:/Users/|/private/|[A-Za-z]:\\)",
        r"(?:学校|校名|指导教师|实验室|student_name|member_name)",
    )

    for pattern in forbidden:
        assert not re.search(pattern, payload)
