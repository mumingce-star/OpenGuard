"""Versioned assessment views, separate from immutable scan facts."""
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.domain.usage import UsageDeclaration

Conclusion = Literal["conditional", "restricted", "unknown", "not_applicable"]
DimensionId = Literal["commercial", "modification", "closed_distribution", "redistribution", "network_service", "ai_assets"]
LABELS = {"conditional": "可按条件使用", "restricted": "当前用途存在限制", "unknown": "证据不足，暂无法判断", "not_applicable": "不适用"}
DIMENSIONS = {"commercial": "商业使用", "modification": "修改与二次开发", "closed_distribution": "闭源发布／交付", "redistribution": "公开发布与再分发", "network_service": "对外在线服务部署", "ai_assets": "模型、数据、素材及 API 的独立条件"}


class AssessmentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResourceEvaluation(AssessmentModel):
    resource_id: str
    resource_kind: Literal["component", "ai_asset"]
    name: str
    version: str | None
    scope: str = "unknown"
    scope_evidence_ids: list[str] = Field(default_factory=list)
    license_expression: str | None = None
    license_verified: bool = False
    supported_permission: bool = False
    finding_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    locators: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    restrictions: dict[str, list[str]] = Field(default_factory=dict)
    gaps: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class DimensionAssessment(AssessmentModel):
    id: DimensionId
    title: str
    status: Conclusion
    conclusion: str
    conditions: list[str] = Field(default_factory=list)
    restrictions: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    resource_ids: list[str] = Field(default_factory=list)
    finding_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    strength: Literal["verified", "limited", "insufficient"] = "insufficient"


class AssessmentObligation(AssessmentModel):
    id: str
    action: str
    requirement: str
    trigger: str
    fulfillment: Literal["pending", "satisfied", "not_applicable"] = "pending"
    resource_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    rule_id: str
    rule_version: str


class Assessment(AssessmentModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str
    version: int = Field(ge=1)
    scan_id: str
    project_name: str
    revision: str | None
    input_hash: str
    facts_hash: str
    usage_hash: str
    cache_key: str
    generated_at: datetime
    usage: UsageDeclaration
    rule_version: str
    model_version: str
    prompt_version: str
    formal: bool = True
    scan_status: str
    ai_status: Literal["not_requested", "succeeded", "fallback", "failed"] = "not_requested"
    ai_summary: str | None = None
    ai_evidence_ids: list[str] = Field(default_factory=list)
    summary: str
    dimensions: list[DimensionAssessment]
    resource_evaluations: list[ResourceEvaluation]
    obligations: list[AssessmentObligation]
    coverage_issues: list[str]
    resource_ids: list[str]
    finding_ids: list[str]
    evidence_ids: list[str]
    license_ids: list[str]
    remediation_ids: list[str]
    rule_sources: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def utc_only(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError("generated_at must be explicit UTC")
        return value
