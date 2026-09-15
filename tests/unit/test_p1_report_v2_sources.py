"""Independent fixed-source faults and exact Task history regression for A06."""
from datetime import datetime, timezone
import hashlib

import pytest

from app.p1.models import P1TaskRef
from app.p1.report_v2_sources import validate_fixed_sources, validate_task
from app.p1.remediation_store import RemediationTaskStore, RemediationStoreError
from test_p1_report_v2_service import report_env


def sources(env):
    return env.registry.get(env.run.id), env.assessment


def test_fixed_sources_and_original_task_are_valid_and_readonly(report_env):
    env = report_env
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in env.path.rglob('*.db')}
    stored, assessment = sources(env)
    validate_fixed_sources(stored, assessment, env.run.id, assessment.id)
    validate_task(env.task.model_dump(mode='json'), P1TaskRef(task_id=env.task.task_id, version=1), stored, assessment)
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before}


@pytest.mark.parametrize('field,value,reason', [
    ('id', 'other', 'source_identity_mismatch'),
    ('input_hash', '0'*64, 'assessment_scan_record_mismatch'),
    ('revision', 'other', 'assessment_scan_record_mismatch'),
    ('scan_status', 'running', 'assessment_scan_record_mismatch'),
    ('version', True, 'source_structure_invalid'),
    ('resource_ids', ['missing'], 'resource_reference_invalid'),
    ('finding_ids', ['missing'], 'finding_reference_invalid'),
    ('evidence_ids', ['missing'], 'evidence_reference_invalid'),
    ('ai_evidence_ids', ['missing'], 'ai_evidence_reference_invalid'),
    ('license_ids', ['missing'], 'license_reference_invalid'),
    ('remediation_ids', ['missing'], 'remediation_reference_invalid'),
])
def test_assessment_source_faults(report_env, field, value, reason):
    stored, assessment = sources(report_env)
    changed = assessment.model_copy(deep=True)
    setattr(changed, field, value)
    with pytest.raises(ValueError, match=reason):
        validate_fixed_sources(stored, changed, report_env.run.id, assessment.id)


def test_usage_changed_without_updating_hash_rejected(report_env):
    stored, assessment = sources(report_env)
    changed = assessment.model_copy(deep=True)
    # A real permitted purpose field changes; declared_at alone is excluded.
    changed.usage = changed.usage.model_copy(update={'commercial': not bool(changed.usage.commercial)})
    with pytest.raises(ValueError, match='usage_hash_mismatch'):
        validate_fixed_sources(stored, changed, report_env.run.id, assessment.id)


def test_declared_at_and_old_rule_version_not_reinterpreted(report_env):
    stored, assessment = sources(report_env)
    changed = assessment.model_copy(deep=True)
    changed.usage = changed.usage.model_copy(update={'declared_at': datetime(2020, 1, 1, tzinfo=timezone.utc)})
    changed.rule_version = 'historical-rule/0.1'
    validate_fixed_sources(stored, changed, report_env.run.id, assessment.id)


@pytest.mark.parametrize('field,value,reason', [
    ('resource_kind', 'ai_asset', 'resource_identity_invalid'),
    ('scope_evidence_ids', ['missing'], 'evidence_reference_invalid'),
    ('license_expression', 'invented', 'license_reference_invalid'),
])
def test_resource_nested_refs(report_env, field, value, reason):
    stored, assessment = sources(report_env)
    changed = assessment.model_copy(deep=True)
    if field == 'resource_kind':
        value = 'component' if changed.resource_evaluations[0].resource_kind == 'ai_asset' else 'ai_asset'
    setattr(changed.resource_evaluations[0], field, value)
    with pytest.raises(ValueError, match=reason):
        validate_fixed_sources(stored, changed, report_env.run.id, assessment.id)


def test_assessment_obligation_is_not_scan_obligation(report_env):
    from app.assessment.models import AssessmentObligation
    stored, assessment = sources(report_env)
    changed = assessment.model_copy(deep=True)
    changed.obligations.append(AssessmentObligation(id='assessment-only-obligation', action='Review',
        requirement='Retain statement', trigger='distribution', rule_id='historical', rule_version='old',
        resource_ids=[stored.run.components[0].id], evidence_ids=[stored.run.evidence[0].id]))
    assert 'assessment-only-obligation' not in {item.id for item in stored.run.obligations}
    validate_fixed_sources(stored, changed, report_env.run.id, assessment.id)


@pytest.mark.parametrize('location,value,reason', [
    (('task_id',), 'tsk_wrong', 'task_identity_mismatch'),
    (('version',), 2, 'task_identity_mismatch'),
    (('origin','source_pointer'), '/missing', 'task_origin_invalid'),
    (('origin','source_hash'), '0'*64, 'task_source_hash_mismatch'),
    (('resource_ids',), ['missing'], 'task_resource_reference_invalid'),
    (('evidence_refs',), [dict(namespace='profile_observation', observation_id='unknown')], 'task_evidence_reference_invalid'),
    (('created_at',), 'Z', 'task_structure_invalid'),
    (('assessment_ref','version'), True, 'task_binding_mismatch'),
    (('provenance','parameters_hash'), '0'*64, 'task_provenance_invalid'),
    (('provenance','generated_at'), '2026-02-31T00:00:00Z', 'task_provenance_invalid'),
])
def test_task_faults(report_env, location, value, reason):
    stored, assessment = sources(report_env)
    task = report_env.task.model_dump(mode='json')
    cursor = task
    for key in location[:-1]:
        cursor = cursor[key]
    cursor[location[-1]] = value
    with pytest.raises(ValueError, match=reason):
        validate_task(task, P1TaskRef(task_id=report_env.task.task_id, version=1), stored, assessment)


def test_exact_historical_task_read_does_not_load_history(report_env, monkeypatch):
    env = report_env
    original = env.task_store.get_version(env.run.id, env.assessment.id, env.task.task_id, 1)
    env.task_store.patch(env.run.id, env.assessment.id, env.task.task_id, 1, {'note': 'historical state changed'})
    def forbidden(*args, **kwargs):
        pytest.fail('must not traverse history or read current payload')
    monkeypatch.setattr(env.task_store, 'history', forbidden)
    monkeypatch.setattr(env.task_store, 'get', forbidden)
    before = env.task_store.path.read_bytes()
    assert env.task_store.get_version(env.run.id, env.assessment.id, env.task.task_id, 1) == original
    assert env.task_store.get_version('other', env.assessment.id, env.task.task_id, 1) is None
    assert env.task_store.get_version(env.run.id, 'other', env.task.task_id, 1) is None
    assert env.task_store.get_version(env.run.id, env.assessment.id, env.task.task_id, 99) is None
    assert env.task_store.path.read_bytes() == before
    validate_task(original, P1TaskRef(task_id=env.task.task_id, version=1), *sources(env))


def test_exact_read_absent_store_does_not_initialize(tmp_path):
    store = RemediationTaskStore(tmp_path / 'absent' / 'remediation.db', min_free_bytes=0)
    assert store.get_version('scan', 'assessment', 'task', 1) is None
    assert not store.path.parent.exists()
    with pytest.raises(RemediationStoreError, match='invalid_argument'):
        store.get_version('scan', 'assessment', 'task', True)


@pytest.mark.parametrize('fault', ['usage', 'input_hash', 'assessment_id', 'resource', 'finding', 'evidence', 'ai_evidence', 'license', 'dimension_evidence'])
def test_new_report_rejects_corrupt_assessment_without_any_writes(report_env, monkeypatch, fault):
    from app.p1.report_v2 import ReportV2ServiceError
    env = report_env
    changed = env.assessment.model_copy(deep=True)
    if fault == 'usage':
        changed.usage = changed.usage.model_copy(update={'commercial': not bool(changed.usage.commercial)})
    elif fault == 'input_hash':
        changed.input_hash = '0' * 64
    elif fault == 'assessment_id':
        changed.id = 'different-assessment'
    elif fault == 'dimension_evidence':
        changed.dimensions[0].evidence_ids = ['unknown']
    else:
        setattr(changed, {'resource': 'resource_ids', 'finding': 'finding_ids', 'evidence': 'evidence_ids',
                         'ai_evidence': 'ai_evidence_ids', 'license': 'license_ids'}[fault], ['unknown'])
    monkeypatch.setattr(env.assessment_store, 'get', lambda *args: changed)
    before = {p: p.read_bytes() for p in env.path.rglob('*.db')}
    with pytest.raises(ReportV2ServiceError) as error:
        env.service.create(env.run.id, env.assessment.id, idempotency_key='bad-source')
    assert error.value.code == 'upstream_unavailable'
    assert before == {p: p.read_bytes() for p in before}


@pytest.mark.parametrize('fault', ['identity', 'version', 'origin', 'source_hash', 'resource', 'evidence', 'provenance'])
def test_new_report_rejects_corrupt_task_without_any_writes(report_env, monkeypatch, fault):
    from app.p1.report_v2 import ReportV2ServiceError
    env = report_env
    changed = env.task.model_dump(mode='json')
    if fault == 'identity':
        changed['task_id'] = 'tsk_other'
    elif fault == 'version':
        changed['version'] = 2
    elif fault == 'origin':
        changed['origin']['source_pointer'] = '/nonexistent'
    elif fault == 'source_hash':
        changed['origin']['source_hash'] = '0'*64
    elif fault == 'resource':
        changed['resource_ids'] = ['missing']
    elif fault == 'evidence':
        changed['evidence_refs'] = [dict(namespace='scan', scan_id=env.run.id, evidence_id='missing')]
    else:
        changed['provenance']['source_refs'][0]['scan_id'] = 'different'
    monkeypatch.setattr(env.task_store, 'get_version', lambda *args: changed)
    before = {p: p.read_bytes() for p in env.path.rglob('*.db')}
    with pytest.raises(ReportV2ServiceError) as error:
        env.service.create(env.run.id, env.assessment.id, idempotency_key='bad-task',
                           task_refs=[P1TaskRef(task_id=env.task.task_id, version=1)])
    assert error.value.code == 'upstream_unavailable'
    assert before == {p: p.read_bytes() for p in before}


def test_task_provenance_bool_version_not_equal_to_integer(report_env):
    task = report_env.task.model_dump(mode='json')
    task['provenance']['assessment_refs'][0]['version'] = True
    with pytest.raises(ValueError, match='task_provenance_invalid'):
        validate_task(task, P1TaskRef(task_id=report_env.task.task_id, version=1), *sources(report_env))
