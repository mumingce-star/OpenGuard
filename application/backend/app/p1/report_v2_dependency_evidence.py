"""Report V2 dependency evidence contract from one frozen ScanRun."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.domain.models import ScanRun, ScanStatus

from .dependency_evidence import DependencyEvidenceItem, _project_dependency_evidence_v1
from .models import REPORT_DEPENDENCY_EVIDENCE_SCHEMA, P1Model, P1ScanRef


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



MAX_REPORT_ITEMS = 20_000
MAX_REPORT_DOCUMENT_BYTES = 16 * 1024 * 1024


class ReportItemCapacityError(ValueError):
    pass


def base_archive_items(
    scan: dict,
    assessment: dict,
    binding: dict,
    tasks: list[dict],
    notices: list[dict],
    graphs: list[dict],
) -> int:
    """Count the archived source records and explicit fixed references."""
    scan_rows = ('components', 'ai_assets', 'evidence', 'findings', 'licenses',
                 'obligations', 'remediations', 'errors', 'report_links')
    assessment_rows = ('dimensions', 'resource_evaluations', 'obligations', 'coverage_issues')
    source_refs = ('task_refs', 'notice_refs', 'algorithm_refs')
    return (
        sum(len(scan[name]) for name in scan_rows)
        + sum(len(assessment[name]) for name in assessment_rows)
        + sum(len(binding[name]) for name in source_refs)
        + len(tasks)
        + sum(len(draft['entries']) for draft in notices)
        + sum(len(graph['nodes']) + len(graph['edges']) for graph in graphs)
    )


def dependency_observation(run: ScanRun, scan_ref: P1ScanRef, *, remaining: int) -> dict:
    """Build all scoped rows, rejecting report overflow without truncating."""
    if remaining < 0:
        raise ReportItemCapacityError('report_generation_capacity_exceeded')

    def accept(item: DependencyEvidenceItem) -> None:
        nonlocal remaining
        count = 1 + len(item.gaps) + len(item.evidence)
        for conflict in item.conflicts:
            count += 1 + len(conflict.gaps)
            for side in (conflict.declaration, conflict.lock):
                if side is not None:
                    count += 1 + len(side.evidence)
        remaining -= count
        if remaining < 0:
            raise ReportItemCapacityError('report_generation_capacity_exceeded')

    items, total, more = _project_dependency_evidence_v1(
        run, source=None, after=None, limit=remaining, accept_item=accept,
    )
    if more:
        raise ReportItemCapacityError('report_generation_capacity_exceeded')
    return P1ReportDependencyEvidence(
        schema_version=REPORT_DEPENDENCY_EVIDENCE_SCHEMA,
        scan_ref=scan_ref,
        coverage='unknown',
        total=total,
        returned=len(items),
        incomplete=scan_ref.status == ScanStatus.PARTIAL or any(item.incomplete for item in items),
        items=items,
    ).model_dump(mode='json')
