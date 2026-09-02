"""Regression coverage for the non-executing ScanCode/Syft adapter boundary."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.domain.models import Component, ComponentType, DetectionMethod
from app.scanners.external_tools import (
    ToolExecution,
    map_scancode_output,
    map_syft_output,
    merge_components,
    parse_json_output,
    run_json_tool,
)


_DIGEST = "0" * 64
_NOW = datetime(2026, 9, 2, tzinfo=timezone.utc)


def test_scancode_maps_only_locatable_license_evidence_and_candidates() -> None:
    result = map_scancode_output(
        {"files": [
            {"path": "LICENSE", "sha256": "a" * 64, "detected_license_expression": "MIT"},
            {"path": "src/main.py", "license_detections": [{"license_expression": "Apache-2.0"}]},
            {"path": "../outside", "detected_license_expression": "GPL-3.0-only"},
        ]},
        root_digest=_DIGEST,
        observed_at=_NOW,
        tool_version="32.3.0",
    )
    assert result.license_candidates == ("Apache-2.0", "MIT")
    assert [item.locator for item in result.evidence] == ["LICENSE", "src/main.py"]
    assert all(item.detected_by is DetectionMethod.SCANCODE for item in result.evidence)
    assert all(item.verification_status.value == "pending" for item in result.evidence)


def test_syft_maps_artifact_locations_without_guessing_license_or_version() -> None:
    result = map_syft_output(
        {"artifacts": [
            {"name": "requests", "version": "2.32.0", "purl": "pkg:pypi/requests@2.32.0", "locations": [{"path": "requirements.txt"}]},
            {"name": "bad", "locations": [{"path": "../outside"}]},
        ]},
        root_digest=_DIGEST,
        observed_at=_NOW,
        tool_version="1.20.0",
    )
    assert len(result.components) == len(result.evidence) == 1
    component = result.components[0]
    assert component.ecosystem == "pypi" and component.license_expression_id is None
    assert component.detected_by == [DetectionMethod.SYFT]
    assert result.evidence[0].locator == "requirements.txt"


def test_component_merge_keeps_evidence_and_marks_metadata_conflict() -> None:
    first = Component(
        id="cmp_123e4567-e89b-12d3-a456-426614174000", name="requests", version="2.32.0", ecosystem="pypi",
        component_type=ComponentType.LIBRARY, purl="pkg:pypi/requests@2.32.0", source_url=None,
        license_expression_id=None, evidence_ids=["evd_123e4567-e89b-12d3-a456-426614174000"],
        detected_by=[DetectionMethod.MANIFEST_PARSER], confidence=1.0,
    )
    second = first.model_copy(update={
        "id": "cmp_123e4567-e89b-12d3-a456-426614174001",
        "source_url": "https://example.com/requests",
        "evidence_ids": ["evd_123e4567-e89b-12d3-a456-426614174001"],
        "detected_by": [DetectionMethod.SYFT],
        "confidence": 0.8,
    })
    merged = merge_components([first], [second])
    assert len(merged.components) == 1 and merged.components[0].source_url is None
    assert len(merged.components[0].evidence_ids) == 2
    assert merged.components[0].confidence == 0.8
    assert merged.diagnostics[0].code == "component_metadata_conflict"


def test_tool_output_is_bounded_and_invalid_json_is_not_promoted() -> None:
    assert parse_json_output(ToolExecution("syft", "complete", json.dumps({"artifacts": []}).encode())) == {"artifacts": []}
    assert parse_json_output(ToolExecution("syft", "complete", b"not-json")) is None
    unavailable = run_json_tool("openguard-tool-that-does-not-exist", ["--version"])
    assert unavailable.status == "unavailable" and unavailable.error_code == "tool_unavailable"
