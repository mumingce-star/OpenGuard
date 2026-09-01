"""Frozen P0 domain contract implemented with Pydantic v2."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import ClassVar, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CONTRACT_VERSION = "0.1.0"
_ID_SUFFIX = r"(?:[0-9a-hjkmnp-tv-z]{26}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
_ABSOLUTE_PATH = re.compile(r"^(?:/|\\\\|[A-Za-z]:[\\/])")
_SENSITIVE_FRAGMENT = re.compile(r"(?i)(?:api[_-]?key|secret|token|password)\s*[=:]")


class SourceType(StrEnum):
    GIT = "git"
    ZIP = "zip"
    LOCAL = "local"


class ComponentType(StrEnum):
    LIBRARY = "library"
    APPLICATION = "application"
    FRAMEWORK = "framework"
    RUNTIME = "runtime"
    UNKNOWN = "unknown"


class AIAssetType(StrEnum):
    MODEL = "model"
    DATASET = "dataset"
    API = "api"
    SERVICE = "service"
    ASSET = "asset"


class EvidenceKind(StrEnum):
    FILE = "file"
    MANIFEST_FIELD = "manifest_field"
    URL = "url"
    TOOL_OUTPUT = "tool_output"
    LICENSE_TEXT = "license_text"
    METADATA = "metadata"


class DetectionMethod(StrEnum):
    MANIFEST_PARSER = "manifest_parser"
    SCANCODE = "scancode"
    SYFT = "syft"
    STATIC_PATTERN = "static_pattern"
    AST = "ast"
    MANUAL = "manual"
    AI_CANDIDATE = "ai_candidate"


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    PENDING = "pending"
    NOT_APPLICABLE = "not_applicable"
    REJECTED = "rejected"


class FindingOutcome(StrEnum):
    PASS = "pass"
    WARNING = "warning"
    REVIEW_REQUIRED = "review_required"
    UNKNOWN = "unknown"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ScanStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScanStage(StrEnum):
    QUEUED = "queued"
    INGESTION = "ingestion"
    INVENTORY = "inventory"
    SCAN = "scan"
    NORMALIZE = "normalize"
    RULES = "rules"
    AI_ASSIST = "ai_assist"
    REPORT = "report"
    COMPLETED = "completed"


class ProducerType(StrEnum):
    PARSER = "parser"
    SCANNER = "scanner"
    RULE_ENGINE = "rule_engine"
    AI = "ai"
    HUMAN = "human"


class ReportFormat(StrEnum):
    HTML = "html"
    JSON = "json"
    CSV = "csv"
    RESOURCE_INVENTORY = "resource_inventory"


def _validate_id(value: str, prefix: str) -> str:
    if not re.fullmatch(rf"{re.escape(prefix)}_{_ID_SUFFIX}", value):
        raise ValueError(f"id must use the {prefix}_ prefix followed by a lowercase ULID or UUID")
    return value


def _validate_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("datetime must use UTC with an explicit timezone")
    return value.astimezone(timezone.utc)


def _validate_https(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("URL must be an absolute public https URL without credentials")
    return value


def _validate_relative_locator(value: str) -> str:
    path_part = value.split(":", 1)[0]
    if not value or _ABSOLUTE_PATH.match(value) or any(part == ".." for part in path_part.split("/")):
        raise ValueError("locator must be a relative POSIX path or field locator")
    return value


def _contains_absolute_path_fragment(value: str) -> bool:
    """Detect a Unix or Windows absolute path embedded in user-visible text."""
    for index, character in enumerate(value):
        previous = value[index - 1] if index else ""
        following = value[index + 1] if index + 1 < len(value) else ""
        boundary = not previous or (not previous.isalnum() and previous not in "_./")

        if character == "/" and boundary and following != "/":
            return True
        if (
            character.isalpha()
            and following == ":"
            and index + 2 < len(value)
            and value[index + 2] in {"/", "\\"}
            and boundary
        ):
            return True
        if character == "\\" and boundary and following == "\\":
            return True
    return False


def _stable_unique(values: list[str | StrEnum]) -> list[str | StrEnum]:
    return sorted(set(values), key=lambda item: str(item))


class P0Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HashValue(P0Model):
    algorithm: Literal["sha256"]
    value: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProducerRef(P0Model):
    type: ProducerType
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=100)
    config_digest: HashValue | None = None


class RunEnvironment(P0Model):
    python_version: str = Field(min_length=1, max_length=100)
    platform: str = Field(min_length=1, max_length=200)
    openguard_version: str = Field(min_length=1, max_length=100)


class RunProvenance(P0Model):
    input_digest: HashValue
    inventory_digest: HashValue | None = None
    tool_versions: list[ProducerRef] = Field(default_factory=list)
    ruleset_version: str = Field(min_length=1, max_length=100)
    contract_version: Literal[CONTRACT_VERSION]
    ai_enabled: bool
    ai_model: ProducerRef | None = None
    run_environment: RunEnvironment

    @model_validator(mode="after")
    def validate_ai_provenance(self) -> "RunProvenance":
        if self.ai_enabled and self.ai_model is None:
            raise ValueError("ai_model is required when ai_enabled is true")
        if self.ai_model is not None and self.ai_model.type is not ProducerType.AI:
            raise ValueError("ai_model must have producer type ai")
        return self


class Project(P0Model):
    ID_PREFIX: ClassVar[str] = "prj"

    id: str
    name: str = Field(min_length=1, max_length=200)
    source_type: SourceType
    source: str = Field(min_length=1, max_length=2048)
    revision: str | None = None
    root_digest: HashValue | None = None
    created_at: datetime

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return _validate_id(value, cls.ID_PREFIX)

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _validate_utc(value)

    @model_validator(mode="after")
    def validate_source(self) -> "Project":
        if self.source_type is SourceType.GIT:
            _validate_https(self.source)
        elif _ABSOLUTE_PATH.match(self.source) or ".." in self.source.split("/"):
            raise ValueError("zip/local source must be a sanitized logical name")
        return self


class Evidence(P0Model):
    ID_PREFIX: ClassVar[str] = "evd"

    id: str
    kind: EvidenceKind
    locator: str = Field(min_length=1, max_length=2048)
    excerpt: str | None = Field(default=None, max_length=1000)
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    content_hash: HashValue | None = None
    detected_by: DetectionMethod
    producer: ProducerRef
    observed_at: datetime
    verification_status: VerificationStatus

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return _validate_id(value, cls.ID_PREFIX)

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        return _validate_utc(value)

    @model_validator(mode="after")
    def validate_evidence(self) -> "Evidence":
        if (self.start_line is None) != (self.end_line is None):
            raise ValueError("start_line and end_line must appear together")
        if self.start_line is not None and self.end_line is not None and self.end_line < self.start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        if self.kind in {EvidenceKind.FILE, EvidenceKind.MANIFEST_FIELD}:
            _validate_relative_locator(self.locator)
        elif self.kind is EvidenceKind.URL:
            _validate_https(self.locator)
        if self.detected_by is DetectionMethod.AI_CANDIDATE and self.verification_status is not VerificationStatus.PENDING:
            raise ValueError("ai_candidate evidence must remain pending")
        if self.excerpt and _SENSITIVE_FRAGMENT.search(self.excerpt):
            raise ValueError("excerpt must not contain sensitive credential fragments")
        return self


class Component(P0Model):
    ID_PREFIX: ClassVar[str] = "cmp"

    id: str
    name: str = Field(min_length=1, max_length=200)
    version: str | None = Field(default=None, max_length=200)
    ecosystem: Literal["pypi", "npm", "unknown"]
    component_type: ComponentType = ComponentType.LIBRARY
    purl: str | None = None
    source_url: str | None = None
    license_expression_id: str | None = None
    evidence_ids: list[str] = Field(min_length=1)
    detected_by: list[DetectionMethod] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return _validate_id(value, cls.ID_PREFIX)

    @field_validator("evidence_ids")
    @classmethod
    def normalize_evidence_ids(cls, value: list[str]) -> list[str]:
        return [str(item) for item in _stable_unique(value)]

    @field_validator("detected_by")
    @classmethod
    def normalize_detected_by(cls, value: list[DetectionMethod]) -> list[DetectionMethod]:
        return [item for item in _stable_unique(value)]

    @model_validator(mode="after")
    def validate_component(self) -> "Component":
        if self.purl is not None and not self.purl.startswith("pkg:"):
            raise ValueError("purl must be a Package URL")
        if self.source_url is not None:
            _validate_https(self.source_url)
        if self.license_expression_id is not None:
            _validate_id(self.license_expression_id, "lic")
        for evidence_id in self.evidence_ids:
            _validate_id(evidence_id, "evd")
        return self


class AIAsset(P0Model):
    ID_PREFIX: ClassVar[str] = "ast"

    id: str
    asset_type: AIAssetType
    name: str = Field(min_length=1, max_length=200)
    provider: str | None = Field(default=None, max_length=200)
    version: str | None = Field(default=None, max_length=200)
    source_url: str | None = None
    license_expression_id: str | None = None
    authorization_status: VerificationStatus = VerificationStatus.PENDING
    evidence_ids: list[str] = Field(min_length=1)
    detected_by: list[DetectionMethod] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return _validate_id(value, cls.ID_PREFIX)

    @field_validator("evidence_ids")
    @classmethod
    def normalize_evidence_ids(cls, value: list[str]) -> list[str]:
        return [str(item) for item in _stable_unique(value)]

    @field_validator("detected_by")
    @classmethod
    def normalize_detected_by(cls, value: list[DetectionMethod]) -> list[DetectionMethod]:
        return [item for item in _stable_unique(value)]

    @model_validator(mode="after")
    def validate_asset(self) -> "AIAsset":
        if self.source_url is not None:
            _validate_https(self.source_url)
        if self.license_expression_id is not None:
            _validate_id(self.license_expression_id, "lic")
        for evidence_id in self.evidence_ids:
            _validate_id(evidence_id, "evd")
        return self


class LicenseExpression(P0Model):
    ID_PREFIX: ClassVar[str] = "lic"

    id: str
    expression: str = Field(min_length=1, max_length=500)
    normalized_ids: list[str] = Field(default_factory=list)
    source_url: str | None = None
    evidence_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    verification_status: VerificationStatus = VerificationStatus.PENDING

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return _validate_id(value, cls.ID_PREFIX)

    @field_validator("normalized_ids", "evidence_ids")
    @classmethod
    def normalize_ids(cls, value: list[str]) -> list[str]:
        return [str(item) for item in _stable_unique(value)]

    @model_validator(mode="after")
    def validate_license(self) -> "LicenseExpression":
        if not re.fullmatch(r"[A-Za-z0-9.+()\-\s]+", self.expression):
            raise ValueError("expression must be an SPDX expression or LicenseRef")
        if self.source_url is not None:
            _validate_https(self.source_url)
        for evidence_id in self.evidence_ids:
            _validate_id(evidence_id, "evd")
        return self


class Obligation(P0Model):
    ID_PREFIX: ClassVar[str] = "obl"

    id: str
    license_expression_id: str
    action: str = Field(min_length=1, max_length=200)
    trigger: str = Field(min_length=1, max_length=1000)
    description: str = Field(min_length=1, max_length=2000)
    source_evidence_ids: list[str] = Field(min_length=1)
    rule_id: str = Field(min_length=1, max_length=200)
    rule_version: str = Field(min_length=1, max_length=100)
    verification_status: VerificationStatus

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return _validate_id(value, cls.ID_PREFIX)

    @field_validator("source_evidence_ids")
    @classmethod
    def normalize_evidence_ids(cls, value: list[str]) -> list[str]:
        return [str(item) for item in _stable_unique(value)]

    @model_validator(mode="after")
    def validate_obligation(self) -> "Obligation":
        _validate_id(self.license_expression_id, "lic")
        for evidence_id in self.source_evidence_ids:
            _validate_id(evidence_id, "evd")
        return self


class Remediation(P0Model):
    ID_PREFIX: ClassVar[str] = "rem"

    id: str
    finding_id: str
    summary: str = Field(min_length=1, max_length=1000)
    steps: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    generated_by: ProducerRef
    verification_status: VerificationStatus

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return _validate_id(value, cls.ID_PREFIX)

    @field_validator("steps")
    @classmethod
    def normalize_steps(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("steps cannot contain blank values")
        return [str(item) for item in _stable_unique(value)]

    @field_validator("evidence_ids")
    @classmethod
    def normalize_evidence_ids(cls, value: list[str]) -> list[str]:
        return [str(item) for item in _stable_unique(value)]

    @model_validator(mode="after")
    def validate_remediation(self) -> "Remediation":
        _validate_id(self.finding_id, "rsk")
        for evidence_id in self.evidence_ids:
            _validate_id(evidence_id, "evd")
        if self.generated_by.type is ProducerType.AI and self.verification_status is not VerificationStatus.PENDING:
            raise ValueError("AI remediation must remain pending")
        return self


class RiskFinding(P0Model):
    ID_PREFIX: ClassVar[str] = "rsk"

    id: str
    resource_kind: Literal["component", "ai_asset"]
    resource_id: str
    outcome: FindingOutcome
    severity: Severity
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=2000)
    rule_id: str = Field(min_length=1, max_length=200)
    rule_version: str = Field(min_length=1, max_length=100)
    trigger: str = Field(min_length=1, max_length=1000)
    evidence_ids: list[str] = Field(default_factory=list)
    obligation_ids: list[str] = Field(default_factory=list)
    remediation_id: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return _validate_id(value, cls.ID_PREFIX)

    @field_validator("evidence_ids", "obligation_ids")
    @classmethod
    def normalize_ids(cls, value: list[str]) -> list[str]:
        return [str(item) for item in _stable_unique(value)]

    @model_validator(mode="after")
    def validate_finding(self) -> "RiskFinding":
        _validate_id(self.resource_id, "cmp" if self.resource_kind == "component" else "ast")
        for evidence_id in self.evidence_ids:
            _validate_id(evidence_id, "evd")
        for obligation_id in self.obligation_ids:
            _validate_id(obligation_id, "obl")
        if self.remediation_id is not None:
            _validate_id(self.remediation_id, "rem")
        if self.outcome in {FindingOutcome.WARNING, FindingOutcome.REVIEW_REQUIRED} and not self.evidence_ids:
            raise ValueError("warning and review_required findings require evidence")
        return self


class ScanError(P0Model):
    code: str = Field(min_length=1, max_length=100)
    stage: ScanStage
    message: str = Field(min_length=1, max_length=1000)
    recoverable: bool
    tool: str | None = Field(default=None, max_length=200)
    evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("evidence_ids")
    @classmethod
    def normalize_evidence_ids(cls, value: list[str]) -> list[str]:
        return [str(item) for item in _stable_unique(value)]

    @model_validator(mode="after")
    def validate_error(self) -> "ScanError":
        if _contains_absolute_path_fragment(self.message) or _SENSITIVE_FRAGMENT.search(self.message):
            raise ValueError("error message must be sanitized")
        for evidence_id in self.evidence_ids:
            _validate_id(evidence_id, "evd")
        return self


class ScanSummary(P0Model):
    component_count: int = Field(ge=0)
    ai_asset_count: int = Field(ge=0)
    evidence_count: int = Field(ge=0)
    finding_counts: dict[FindingOutcome, int]

    @model_validator(mode="after")
    def validate_outcomes(self) -> "ScanSummary":
        expected = set(FindingOutcome)
        if set(self.finding_counts) != expected or any(value < 0 for value in self.finding_counts.values()):
            raise ValueError("finding_counts must contain each FindingOutcome with a non-negative count")
        return self


class ReportLink(P0Model):
    format: ReportFormat
    href: str = Field(min_length=1, max_length=2048)
    content_hash: HashValue
    generated_at: datetime

    @field_validator("generated_at")
    @classmethod
    def validate_generated_at(cls, value: datetime) -> datetime:
        return _validate_utc(value)

    @field_validator("href")
    @classmethod
    def validate_href(cls, value: str) -> str:
        return _validate_relative_locator(value)


class ScanRun(P0Model):
    ID_PREFIX: ClassVar[str] = "scn"

    contract_version: Literal[CONTRACT_VERSION]
    id: str
    idempotency_key: str | None = Field(default=None, max_length=200)
    status: ScanStatus
    stage: ScanStage
    progress: int = Field(ge=0, le=100)
    project: Project
    components: list[Component] = Field(default_factory=list)
    ai_assets: list[AIAsset] = Field(default_factory=list)
    licenses: list[LicenseExpression] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    obligations: list[Obligation] = Field(default_factory=list)
    findings: list[RiskFinding] = Field(default_factory=list)
    remediations: list[Remediation] = Field(default_factory=list)
    summary: ScanSummary
    provenance: RunProvenance
    errors: list[ScanError] = Field(default_factory=list)
    report_links: list[ReportLink] = Field(default_factory=list)
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return _validate_id(value, cls.ID_PREFIX)

    @field_validator("created_at", "started_at", "finished_at")
    @classmethod
    def validate_times(cls, value: datetime | None) -> datetime | None:
        return _validate_utc(value) if value is not None else value

    @model_validator(mode="after")
    def validate_scan_run(self) -> "ScanRun":
        terminal = {ScanStatus.COMPLETED, ScanStatus.PARTIAL, ScanStatus.FAILED, ScanStatus.CANCELLED}
        if self.status in terminal and self.finished_at is None:
            raise ValueError("terminal scan status requires finished_at")
        if self.status not in terminal and self.finished_at is not None:
            raise ValueError("non-terminal scan status cannot have finished_at")
        if self.status is ScanStatus.FAILED and not self.errors:
            raise ValueError("failed scan requires at least one structured error")
        if self.status is ScanStatus.PARTIAL and not any(error.recoverable for error in self.errors):
            raise ValueError("partial scan requires at least one recoverable structured error")
        if self.status is ScanStatus.COMPLETED and self.stage is not ScanStage.COMPLETED:
            raise ValueError("completed scan must have completed stage")
        if self.status is ScanStatus.QUEUED and (self.stage is not ScanStage.QUEUED or self.progress != 0):
            raise ValueError("queued scan must be queued at zero progress")
        self._validate_unique_and_references()
        self._validate_summary()
        return self

    def _validate_unique_and_references(self) -> None:
        collections = (
            self.components,
            self.ai_assets,
            self.licenses,
            self.evidence,
            self.obligations,
            self.findings,
            self.remediations,
        )
        all_ids = [item.id for collection in collections for item in collection]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("all aggregate object IDs must be unique")
        evidence_ids = {item.id for item in self.evidence}
        license_ids = {item.id for item in self.licenses}
        component_ids = {item.id for item in self.components}
        asset_ids = {item.id for item in self.ai_assets}
        obligation_ids = {item.id for item in self.obligations}
        finding_ids = {item.id for item in self.findings}
        remediation_ids = {item.id for item in self.remediations}

        def require(values: list[str], available: set[str], label: str) -> None:
            unknown = sorted(set(values) - available)
            if unknown:
                raise ValueError(f"unknown {label} reference(s): {', '.join(unknown)}")

        for component in self.components:
            require(component.evidence_ids, evidence_ids, "evidence")
            if component.license_expression_id is not None:
                require([component.license_expression_id], license_ids, "license")
        for asset in self.ai_assets:
            require(asset.evidence_ids, evidence_ids, "evidence")
            if asset.license_expression_id is not None:
                require([asset.license_expression_id], license_ids, "license")
        for license_expression in self.licenses:
            require(license_expression.evidence_ids, evidence_ids, "evidence")
        for obligation in self.obligations:
            require([obligation.license_expression_id], license_ids, "license")
            require(obligation.source_evidence_ids, evidence_ids, "evidence")
        for finding in self.findings:
            require(finding.evidence_ids, evidence_ids, "evidence")
            require(finding.obligation_ids, obligation_ids, "obligation")
            if finding.resource_kind == "component":
                require([finding.resource_id], component_ids, "component")
            else:
                require([finding.resource_id], asset_ids, "AI asset")
            if finding.remediation_id is not None:
                require([finding.remediation_id], remediation_ids, "remediation")
        for remediation in self.remediations:
            require([remediation.finding_id], finding_ids, "finding")
            require(remediation.evidence_ids, evidence_ids, "evidence")
        for error in self.errors:
            require(error.evidence_ids, evidence_ids, "evidence")

    def _validate_summary(self) -> None:
        expected = {
            FindingOutcome.PASS: 0,
            FindingOutcome.WARNING: 0,
            FindingOutcome.REVIEW_REQUIRED: 0,
            FindingOutcome.UNKNOWN: 0,
        }
        for finding in self.findings:
            expected[finding.outcome] += 1
        actual = self.summary
        if (
            actual.component_count != len(self.components)
            or actual.ai_asset_count != len(self.ai_assets)
            or actual.evidence_count != len(self.evidence)
            or actual.finding_counts != expected
        ):
            raise ValueError("summary must be calculated from aggregate arrays")
