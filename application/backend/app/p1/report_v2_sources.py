"""A06 fixed-source consistency checks; no reads, writes or reassessment."""
from __future__ import annotations

from datetime import datetime, timezone
import re
from uuid import NAMESPACE_URL, uuid5

from app.assessment.engine import digest, facts_digest
from .models import P1RemediationTask
from .remediation import RemediationService


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _integer(value):
    return type(value) is int and value >= 1


def _date(value):
    if isinstance(value, datetime):
        return value.tzinfo is not None and value.utcoffset() == timezone.utc.utcoffset(value)
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z', value):
        return False
    try:
        datetime.fromisoformat(value.replace('Z', '+00:00'))
        return True
    except ValueError:
        return False


def validate_fixed_sources(stored, assessment, scan_id, assessment_id):
    """Validate references against this captured scan, not current rules or AI."""
    run = stored.run
    _require(run.id == scan_id and assessment.id == assessment_id, 'source_identity_mismatch')
    _require(assessment.scan_id == scan_id and assessment.formal is True, 'assessment_binding_invalid')
    _require(_integer(assessment.version) and _integer(stored.revision) and _date(assessment.generated_at), 'source_structure_invalid')
    _require(assessment.facts_hash == facts_digest(run), 'facts_hash_mismatch')
    _require(assessment.usage_hash == digest(assessment.usage.model_dump(mode='json', exclude={'declared_at'})), 'usage_hash_mismatch')
    _require(assessment.input_hash == run.provenance.input_digest.value
             and assessment.revision == run.project.revision
             and assessment.scan_status == run.status
             and assessment.project_name == run.project.name, 'assessment_scan_record_mismatch')
    resources = {item.id: ('component', item) for item in run.components}
    resources.update({item.id: ('ai_asset', item) for item in run.ai_assets})
    finding_ids = {item.id for item in run.findings}
    evidence_ids = {item.id for item in run.evidence}
    licenses = {item.id: item for item in run.licenses}
    def refs(row):
        _require(set(getattr(row, 'resource_ids', [])) <= resources.keys(), 'resource_reference_invalid')
        _require(set(getattr(row, 'finding_ids', [])) <= finding_ids, 'finding_reference_invalid')
        _require(set(getattr(row, 'evidence_ids', [])) <= evidence_ids, 'evidence_reference_invalid')
    refs(assessment)
    _require(set(assessment.ai_evidence_ids) <= evidence_ids, 'ai_evidence_reference_invalid')
    _require(set(assessment.license_ids) <= licenses.keys(), 'license_reference_invalid')
    _require(set(assessment.remediation_ids) <= {item.id for item in run.remediations}, 'remediation_reference_invalid')
    for row in assessment.resource_evaluations:
        _require(row.resource_id in resources, 'resource_reference_invalid')
        kind, resource = resources[row.resource_id]
        _require(row.resource_kind == kind and row.name == resource.name and row.version == resource.version, 'resource_identity_invalid')
        refs(row)
        _require(set(row.scope_evidence_ids) <= evidence_ids, 'evidence_reference_invalid')
        license_ = licenses.get(resource.license_expression_id)
        _require(row.license_expression == (license_.expression if license_ else None), 'license_reference_invalid')
        _require(all(next(f for f in run.findings if f.id == fid).resource_id == row.resource_id for fid in row.finding_ids), 'finding_reference_invalid')
    for row in [*assessment.dimensions, *assessment.obligations]:
        refs(row)
    # Assessment obligations are their own namespace: no membership comparison
    # with ScanRun.obligations, and no inference from fulfillment/status.
    _require(len({item.id for item in assessment.obligations}) == len(assessment.obligations), 'assessment_obligation_identity_invalid')


def validate_task(task, ref, stored, assessment):
    """Check one exact historical task without recomputing formal conclusions."""
    P1RemediationTask.model_validate(task)
    _require(task['task_id'] == ref.task_id and type(task['version']) is int
             and task['version'] == ref.version, 'task_identity_mismatch')
    expected_assessment = RemediationService._assessment_ref(assessment)
    _require(task['scan_id'] == stored.run.id and task['assessment_ref'] == expected_assessment
             and _integer(task['assessment_ref']['version']), 'task_binding_mismatch')
    _require(_date(task['created_at']) and _date(task['updated_at']), 'task_structure_invalid')
    origin = task['origin']
    source = next((source for source in RemediationService._sources(assessment)
                   if source[0] == origin['kind'] and source[1] == origin['source_pointer']), None)
    _require(source is not None, 'task_origin_invalid')
    kind, pointer, value, text, resources, evidence = source
    _require(origin['source_hash'] == digest(value), 'task_source_hash_mismatch')
    identity = dict(scan_id=stored.run.id, assessment_id=assessment.id, version=assessment.version, origin=origin)
    _require(task['task_id'] == 'tsk_' + str(uuid5(NAMESPACE_URL, 'openguard:task:' + digest(identity))), 'task_identity_mismatch')
    _require(task['resource_ids'] == sorted(set(resources)), 'task_resource_reference_invalid')
    _require(task['evidence_refs'] == [dict(namespace='scan', scan_id=stored.run.id, evidence_id=e) for e in sorted(set(evidence))], 'task_evidence_reference_invalid')
    _require(set(resources) <= {r.id for r in [*stored.run.components, *stored.run.ai_assets]}
             and set(evidence) <= {e.id for e in stored.run.evidence}, 'task_source_reference_invalid')
    provenance = task['provenance']
    _require(_date(provenance['generated_at']) and provenance['assessment_refs'] == [expected_assessment]
             and len(provenance['source_refs']) == 1
             and all(_integer(item['version']) for item in provenance['assessment_refs']), 'task_provenance_invalid')
    scan_ref = provenance['source_refs'][0]
    inventory = stored.run.provenance.inventory_digest
    expected_scan = dict(scan_id=stored.run.id, revision=stored.run.project.revision,
                         facts_hash=assessment.facts_hash, input_hash=assessment.input_hash,
                         inventory_hash=inventory.value if inventory else None, status=stored.run.status)
    _require(_integer(scan_ref['registry_revision']) and scan_ref['registry_revision'] <= stored.revision
             and {k: v for k, v in scan_ref.items() if k != 'registry_revision'} == expected_scan, 'task_provenance_invalid')
    _require(provenance['parameters_hash'] == digest(dict(algorithm=provenance['algorithm_version'],
             scan_ref=scan_ref, assessment_ref=expected_assessment, origin=origin)), 'task_provenance_invalid')
