"""Read-only HTTP DTOs for the frozen P0 API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from app.domain.models import (
    AIAsset,
    Component,
    Evidence,
    FindingOutcome,
    P0Model,
    RiskFinding,
    ScanError,
    ScanStage,
    ScanStatus,
    ScanSummary,
    Severity,
    VerificationStatus,
)


class GitScanCreateRequest(P0Model):
    source_type: Literal["git"]
    source: str = Field(min_length=1, max_length=2048)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("source", "idempotency_key")
    @classmethod
    def reject_surrounding_whitespace(cls, value: str | None) -> str | None:
        if value is not None and value != value.strip():
            raise ValueError("value cannot contain surrounding whitespace")
        return value


class ScanCreateAccepted(P0Model):
    scan_id: str
    status: ScanStatus
    status_url: str


class ScanRunStatusView(P0Model):
    scan_id: str
    status: ScanStatus
    stage: ScanStage
    progress: int = Field(ge=0, le=100)
    summary: ScanSummary
    errors: list[ScanError]


class ResourceView(P0Model):
    """Tagged, read-only wrapper; it is not a second domain resource model."""

    kind: Literal["component", "ai_asset"]
    resource: Component | AIAsset

    @field_validator("resource")
    @classmethod
    def kind_must_match_payload(cls, value: Component | AIAsset, info: object) -> Component | AIAsset:
        data = getattr(info, "data", {})
        expected = "component" if isinstance(value, Component) else "ai_asset"
        if data.get("kind") != expected:
            raise ValueError("resource kind does not match payload")
        return value


class ResourceFilters(P0Model):
    kind: Literal["component", "ai_asset"] | None = None
    ecosystem: Literal["pypi", "npm", "unknown"] | None = None
    provider: str | None = Field(default=None, min_length=1, max_length=200)
    verification_status: VerificationStatus | None = None


class ResourcesResponse(P0Model):
    items: list[ResourceView]
    total: int = Field(ge=0)
    filters: ResourceFilters


class RisksResponse(P0Model):
    items: list[RiskFinding]
    total: int = Field(ge=0)


class ErrorBody(P0Model):
    code: str
    message: str
    request_id: str
    details: dict[str, str]


class ErrorEnvelope(P0Model):
    error: ErrorBody


class RiskFilters(P0Model):
    outcome: FindingOutcome | None = None
    severity: Severity | None = None
    resource_kind: Literal["component", "ai_asset"] | None = None


__all__ = [
    "ErrorBody",
    "ErrorEnvelope",
    "Evidence",
    "GitScanCreateRequest",
    "ResourceFilters",
    "ResourcesResponse",
    "RiskFilters",
    "RisksResponse",
    "ScanCreateAccepted",
    "ScanRunStatusView",
]
