"""Offline DTO and JSON Schema contracts for dual-version Report V2."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from referencing import Registry, Resource

from app.api.report_v2 import ReportV2CreateRequest
from app.p1.models import (
    REPORT_DEPENDENCY_EVIDENCE_SCHEMA,
    REPORT_DEPENDENCY_EVIDENCE_TITLE,
    P1ReportV2Snapshot,
    P1ReportV2SnapshotV11,
    report_v2_snapshot_adapter,
)
from app.p1.report_v2_dependency_evidence import P1ReportDependencyEvidence


SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas" / "p1"
HASH = "a" * 64


def _validator(filename: str) -> Draft202012Validator:
    selected = json.loads((SCHEMA_ROOT / filename).read_bytes())
    common = json.loads((SCHEMA_ROOT / "common.schema.json").read_bytes())
    schema_registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    Draft202012Validator.check_schema(selected)
    return Draft202012Validator(selected, registry=schema_registry)


def _scan_ref(status: str = "completed") -> dict:
    return {
        "scan_id": "scn_contract",
        "revision": None,
        "facts_hash": HASH,
        "input_hash": HASH,
        "inventory_hash": None,
        "status": status,
        "registry_revision": 1,
    }


def _snapshot(version: str) -> dict:
    scan_ref = _scan_ref()
    assessment_ref = {
        "assessment_id": "asm_contract",
        "version": 1,
        "scan_id": scan_ref["scan_id"],
        "facts_hash": HASH,
        "usage_hash": HASH,
        "rule_version": "rules/1",
        "formal": True,
    }
    base = "/api/v1/scans/scn_contract/assessments/asm_contract/report-v2/rptv2_contract"
    sections = [{
        "authority": "formal_assessment",
        "schema_version": "1.0",
        "source_ids": [assessment_ref["assessment_id"]],
        "content_hash": HASH,
        "snapshot_ref": base + "?format=json#/sections/0/content",
    }]
    if version == "1.1":
        sections.append({
            "authority": "observation",
            "schema_version": REPORT_DEPENDENCY_EVIDENCE_SCHEMA,
            "title": REPORT_DEPENDENCY_EVIDENCE_TITLE,
            "source_ids": [scan_ref["scan_id"]],
            "content_hash": HASH,
            "snapshot_ref": base + "?format=json#/sections/1/content",
        })
    return {
        "schema_version": version,
        "snapshot_id": "rptv2_contract",
        "binding": {
            "scan_ref": scan_ref, "assessment_ref": assessment_ref,
            "task_refs": [], "notice_refs": [], "algorithm_refs": [],
        },
        "created_at": "2026-11-22T00:00:00Z",
        "generator_version": "report-v2/1.2",
        "sections": sections,
        "content_hash": HASH,
        "artifacts": [
            {"format": fmt, "content_hash": HASH, "size_bytes": 1, "href": base + "?format=" + fmt}
            for fmt in ("html", "json")
        ],
        "provenance": {
            "producer": {"name": "openguard-report-v2", "version": "1.2"},
            "source_refs": [scan_ref],
            "assessment_refs": [assessment_ref],
            "generated_at": "2026-11-22T00:00:00Z",
            "algorithm_version": "report-v2/1.2",
            "parameters_hash": HASH,
        },
    }


@pytest.mark.parametrize(("version", "model", "filename"), [
    ("1.0", P1ReportV2Snapshot, "report-v2-snapshot.schema.json"),
    ("1.1", P1ReportV2SnapshotV11, "report-v2-snapshot-v1.1.schema.json"),
])
def test_snapshot_version_dispatch_and_frozen_descriptors(version, model, filename):
    value = _snapshot(version)
    _validator(filename).validate(value)
    parsed = report_v2_snapshot_adapter.validate_python(value)
    assert type(parsed) is model
    assert parsed.model_dump(mode="json") == value


@pytest.mark.parametrize("defect", ["missing", "duplicated", "wrong_title", "wrong_authority", "missing_title", "on_legacy"])
def test_snapshot_dependency_descriptor_contract(defect):
    value = _snapshot("1.1")
    filename = "report-v2-snapshot-v1.1.schema.json"
    sections = value["sections"]
    dependency = sections[-1]
    if defect == "missing":
        sections.pop()
    elif defect == "duplicated":
        sections.append(dependency.copy())
    elif defect == "wrong_title":
        dependency["title"] = "Report"
    elif defect == "wrong_authority":
        dependency["authority"] = "workflow"
    elif defect == "missing_title":
        del dependency["title"]
    else:
        value["schema_version"] = "1.0"
        filename = "report-v2-snapshot.schema.json"
    assert not _validator(filename).is_valid(value)
    with pytest.raises(ValidationError):
        report_v2_snapshot_adapter.validate_python(value)


def test_report_descriptor_requires_same_scan_binding():
    value = _snapshot("1.1")
    value["sections"][-1]["source_ids"] = ["scn_other"]
    with pytest.raises(ValidationError, match="report_dependency_evidence_source"):
        report_v2_snapshot_adapter.validate_python(value)


@pytest.mark.parametrize("status", ["completed", "partial"])
def test_empty_dependency_observation_preserves_coverage_and_terminal_status(status):
    value = {
        "schema_version": REPORT_DEPENDENCY_EVIDENCE_SCHEMA,
        "scan_ref": _scan_ref(status),
        "coverage": "unknown",
        "total": 0,
        "returned": 0,
        "incomplete": status == "partial",
        "items": [],
    }
    _validator("report-v2-dependency-evidence.schema.json").validate(value)
    assert P1ReportDependencyEvidence.model_validate(value).model_dump(mode="json") == value
    with pytest.raises(ValidationError, match="report_dependency_evidence_completeness"):
        P1ReportDependencyEvidence.model_validate({**value, "incomplete": not value["incomplete"]})
    with pytest.raises(ValidationError, match="report_dependency_evidence_count"):
        P1ReportDependencyEvidence.model_validate({**value, "total": 1})
    with pytest.raises(ValidationError):
        P1ReportDependencyEvidence.model_validate({**value, "next_cursor": None})


def test_creation_selector_defaults_to_legacy_and_rejects_non_versions():
    assert ReportV2CreateRequest(idempotency_key="scope").schema_version == "1.0"
    assert ReportV2CreateRequest(idempotency_key="scope", schema_version="1.0").schema_version == "1.0"
    assert ReportV2CreateRequest(idempotency_key="scope", schema_version="1.1").schema_version == "1.1"
    for invalid in (None, "2.0", " 1.1", 1.1, True):
        with pytest.raises(ValidationError):
            ReportV2CreateRequest.model_validate({"idempotency_key": "scope", "schema_version": invalid})
