"""Strict Pydantic v2 DTOs for project-level license compatibility matrix responses."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from app.domain.models import Ecosystem
from app.licenses.compatibility import CompatibilityStatus, RULE_VERSION, SCHEMA_VERSION
from app.p1.models import P1Model, P1ScanRef

Text = Annotated[str, Field(min_length=1, max_length=2000)]


class TargetLicenseResolution(P1Model):
    license: str | None = Field(default=None, min_length=1, max_length=100)
    source: Literal["explicit", "root_package", "root_conflict", "ambiguous_roots", "undeclared"]
    status: Literal["RESOLVED", "UNKNOWN"]
    root_component_id: str | None = None
    gaps: list[str]


class CompatibilityUsageSummary(P1Model):
    commercial: bool
    distributed: bool
    modified: bool
    network_service: bool


class CompatibilityCounts(P1Model):
    COMPATIBLE: int = Field(ge=0)
    CONDITIONAL: int = Field(ge=0)
    REVIEW_REQUIRED: int = Field(ge=0)
    INCOMPATIBLE: int = Field(ge=0)
    UNKNOWN: int = Field(ge=0)


class CompatibilitySummary(P1Model):
    overall_status: CompatibilityStatus
    dependency_count: int = Field(ge=0)
    unique_license_count: int = Field(ge=0)
    target_counts: CompatibilityCounts
    pairwise_counts: CompatibilityCounts
    compatible_count: int = Field(ge=0)
    conditional_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    incompatible_count: int = Field(ge=0)
    unknown_count: int = Field(ge=0)


class CompatibilityComponentRef(P1Model):
    resource_id: Text
    name: Text
    version: str | None = Field(default=None, max_length=200)
    ecosystem: Ecosystem
    evidence_ids: list[str]


class TargetAssessment(CompatibilityComponentRef):
    declared_license: str | None = Field(default=None, max_length=200)
    status: CompatibilityStatus
    rule_id: Text
    rationale: Text
    obligations: list[str]
    chosen_branch: str | None = Field(default=None, max_length=100)


class PairwiseConflict(P1Model):
    license_a: Text
    license_b: Text
    status: Literal["CONDITIONAL", "REVIEW_REQUIRED", "INCOMPATIBLE"]
    rule_id: Text
    rationale: Text
    components_a: list[CompatibilityComponentRef]
    components_b: list[CompatibilityComponentRef]


class CompatibilityMatrixCell(P1Model):
    row: int = Field(ge=0)
    col: int = Field(ge=0)
    status: CompatibilityStatus
    rule_id: Text


class CompatibilityMatrix(P1Model):
    licenses: list[str]
    truncated: bool
    cells: list[CompatibilityMatrixCell]


class LicenseCompatibilityResponse(P1Model):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    rule_version: Literal[RULE_VERSION] = RULE_VERSION
    scan_ref: P1ScanRef
    supported_targets: list[str]
    target: TargetLicenseResolution
    usage: CompatibilityUsageSummary
    summary: CompatibilitySummary
    target_assessments: list[TargetAssessment]
    pairwise_conflicts: list[PairwiseConflict]
    matrix: CompatibilityMatrix
    formal_effect: Literal["none"] = "none"
    model_calls: Literal[0] = 0
    limitations: list[str]
