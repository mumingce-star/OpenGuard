"""A06 Report V2 frozen-schema DTO tests."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.p1.models import P1ReportV2Snapshot
from test_p1_contract_schema import validator


HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
HASH_E = "e" * 64
HASH_F = "f" * 64


def report_example() -> dict:
    scan_ref = {
        "scan_id": "scn_report_test",
        "revision": "abc123",
        "facts_hash": HASH_A,
        "input_hash": HASH_B,
        "inventory_hash": HASH_C,
        "status": "completed",
        "registry_revision": 1,
    }

    assessment_ref = {
        "assessment_id": "asm_report_test",
        "version": 2,
        "scan_id": "scn_report_test",
        "facts_hash": HASH_A,
        "usage_hash": HASH_D,
        "rule_version": "assessment-test/1.0",
        "formal": True,
    }

    return {
        "schema_version": "1.0",
        "snapshot_id": "rptv2_report_test",
        "binding": {
            "scan_ref": scan_ref,
            "assessment_ref": assessment_ref,
            "task_refs": [
                {
                    "task_id": "tsk_report_test",
                    "version": 3,
                }
            ],
            "notice_refs": [],
            "algorithm_refs": [
                {
                    "kind": "graph",
                    "version": "resource-graph/1.0",
                    "content_hash": HASH_E,
                }
            ],
        },
        "created_at": "2026-09-14T12:00:00Z",
        "generator_version": "report-v2/1.0",
        "sections": [
            {
                "authority": "formal_assessment",
                "schema_version": "1.0",
                "source_ids": ["asm_report_test"],
                "content_hash": HASH_F,
                "snapshot_ref": "assessment:asm_report_test@2",
            }
        ],
        "content_hash": HASH_A,
        "artifacts": [
            {
                "format": "json",
                "content_hash": HASH_B,
                "size_bytes": 123,
                "href": (
                    "/api/v1/scans/scn_report_test/"
                    "assessments/asm_report_test/"
                    "report-v2/rptv2_report_test?format=json"
                ),
            }
        ],
        "provenance": {
            "producer": {
                "name": "openguard-report-v2",
                "version": "1.0",
            },
            "source_refs": [scan_ref],
            "assessment_refs": [assessment_ref],
            "generated_at": "2026-09-14T12:00:00Z",
            "algorithm_version": "report-v2/1.0",
            "parameters_hash": HASH_C,
        },
    }


def test_report_v2_dto_matches_frozen_schema() -> None:
    value = report_example()

    validator("ReportV2Snapshot").validate(value)

    model = P1ReportV2Snapshot.model_validate(value)

    assert model.model_dump(mode="json") == value


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("binding", "task_refs", 0, "version"), 0),
        (("artifacts", 0, "href"), "/tmp/report.json"),
        (("sections", 0, "authority"), "latest"),
    ],
)
def test_report_v2_rejects_invalid_frozen_values(path, value) -> None:
    payload = deepcopy(report_example())

    target = payload
    for key in path[:-1]:
        target = target[key]

    target[path[-1]] = value

    assert list(validator("ReportV2Snapshot").iter_errors(payload))

    with pytest.raises(ValidationError):
        P1ReportV2Snapshot.model_validate(payload)


def test_report_v2_rejects_unknown_field() -> None:
    payload = report_example()
    payload["latest"] = True

    assert list(validator("ReportV2Snapshot").iter_errors(payload))

    with pytest.raises(ValidationError):
        P1ReportV2Snapshot.model_validate(payload)