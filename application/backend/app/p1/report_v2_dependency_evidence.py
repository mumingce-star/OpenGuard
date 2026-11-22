"""Report V2 dependency evidence contract from one frozen ScanRun."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.domain.models import ScanStatus

from .dependency_evidence import DependencyEvidenceItem
from .models import P1Model, P1ScanRef


class P1ReportDependencyEvidence(P1Model):
    schema_version: Literal['openguard-report-v2-dependency-evidence/1']
    scan_ref: P1ScanRef
    coverage: Literal['unknown']
    total: Annotated[int, Field(strict=True, ge=0)]
    returned: Annotated[int, Field(strict=True, ge=0)]
    incomplete: Annotated[bool, Field(strict=True)]
    items: list[DependencyEvidenceItem]

    @model_validator(mode='after')
    def validate_observation(self):
        if self.scan_ref.status not in (ScanStatus.COMPLETED, ScanStatus.PARTIAL):
            raise ValueError('report_dependency_evidence_scan_status')
        if self.total != self.returned or self.returned != len(self.items):
            raise ValueError('report_dependency_evidence_count')
        resource_ids = [item.resource_id for item in self.items]
        if any(left >= right for left, right in zip(resource_ids, resource_ids[1:])):
            raise ValueError('report_dependency_evidence_item_order')
        incomplete = self.scan_ref.status == ScanStatus.PARTIAL or any(item.incomplete for item in self.items)
        if self.incomplete != incomplete:
            raise ValueError('report_dependency_evidence_completeness')
        return self
