"""TASK-only real ASGI/SQLite checks; bottom fetch/model are closed fixtures.

The real LICENSE bytes do not turn the synthetic parents or transports into a
real acquisition. No external network or actual model is used by these checks.
"""
from copy import deepcopy
import hashlib
import socket

import pytest
from fastapi.testclient import TestClient

from app.assessment.engine import build_assessment
from app.domain.usage import UsageDeclaration
from app.p2.contract import CreateRequest, P2Error, canonical, digest
from app.p2.local_actions import build_local_actions, CONDITION
from app.p2.official_sources import OfficialSourceService
from test_official_sources import flow, ready, adopt_body, LICENSE


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('TEST_ONLY: no socket or DNS is allowed')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)


def adopted(flow):
    svc, run, assessment, old, fetcher, model, app, root = flow
    out = ready(flow)
    receipt = svc.adopt(run.id, assessment.id, adopt_body(old, out['candidate']['candidate_id']))
    assert svc.wait_idle()
    return receipt, out['candidate']


def test_actual_fixed_get_action_quote_usage_pending_and_no_write(flow):
    svc, run, assessment, old, fetcher, model, app, root = flow
    receipt, candidate = adopted(flow)
    new, material = receipt['result'], receipt['material']
    app.state.p2_service.official_sources = svc
    base = f'/api/v1/scans/{run.id}/assessments/{assessment.id}/p2'
    with TestClient(app) as client:
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*.db')}
        calls = fetcher.calls, model.calls
        old_raw = client.get(base + '/results/' + old['result_id'], params={'assessment_version': 1}).content
        summary_raw = client.get(base + '/results/' + new['result_id'] + '/summary', params={'assessment_version': 1}).content
        response = client.get(base + '/official-sources', params={'assessment_version': 1, 'result_id': new['result_id']})
        assert response.status_code == 200, response.text
        value = response.json()['local_actions']
        assert value['state'] == 'supported_verification_actions'
        assert value['result_id'] == new['result_id'] and value['result_revision'] == 2
        assert value['binding'] == new['binding'] and value['usage'] == new['usage']
        assert value['formal_effect'] == 'none' and value['model_calls'] == 0
        assert value['source_admission'] == value['applicability'] == 'NOT_SIGNED'
        assert value['obligations'] == 'NOT_ESTABLISHED'
        check = dict(value); sha = check.pop('content_sha256')
        assert digest(check) == sha
        source = value['source_refs'][0]
        assert source['material_id'] == material['material_id']
        assert source['subject'] == material['subject'] and source['verification_state'] == 'pending'
        text = LICENSE.read_text()
        for clause in value['clauses']:
            assert text[clause['start']:clause['end']] == clause['quote'] == CONDITION
            assert clause['line_start'] == text[:clause['start']].count('\n') + 1
            assert clause['line_end'] == text[:clause['end']].count('\n') + 1
        codes = {action['code'] for action in value['actions']}
        assert 'CHECK_MODIFIED_FILES' in codes and 'CHECK_SERVICE_DELIVERY_BOUNDARY' in codes
        assert 'CHECK_PLANNED_DELIVERY' not in codes  # current synthetic usage says false.
        for action in value['actions']:
            assert action['claim_level'] == 'verification_action_only'
            assert all(new['usage'][field] is True for field in action['usage_fields'])
            assert action['source_material_ids'] == [material['material_id']]
        for _ in range(2):
            assert client.get(base + '/official-sources', params={'assessment_version': 1, 'result_id': new['result_id']}).content == response.content
        assert client.get(base + '/results/' + old['result_id'], params={'assessment_version': 1}).content == old_raw
        assert client.get(base + '/results/' + new['result_id'] + '/summary', params={'assessment_version': 1}).content == summary_raw
        assert all(a['state'] != 'conditional_candidate' for a in new['resources'][0]['advice'])
        assert before == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*.db')}
        assert calls == (fetcher.calls, model.calls)


def test_old_no_material_and_new_usage_do_not_borrow_other_result_material(flow):
    svc, run, assessment, old, fetcher, model, app, root = flow
    receipt, candidate = adopted(flow)
    r2 = receipt['result']
    assert svc.status(run.id, assessment.id, 1, old['result_id'])['local_actions']['actions'] == []
    assert svc.status(run.id, assessment.id, 1, old['result_id'])['local_actions']['state'] == 'awaiting_material'
    updated_usage = UsageDeclaration(commercial=False, modified=True, distributed=True, network_service=True,
                                     training=None, redistributed_assets=False, source_disclosure=True)
    updated = svc.p2.assessments.create(build_assessment(run, updated_usage, version=2), idempotency_key='new-usage-test-only', run=run)
    binding = svc.p2.context(run.id, updated.id)[2]
    new = svc.p2.write(run.id, updated.id, CreateRequest(binding=binding, expected_revision=0,
        parent_result_id=None, idempotency_key='new-usage-initial'), 'create')['result']
    value = svc.status(run.id, updated.id, updated.version, new['result_id'])['local_actions']
    assert value['state'] == 'awaiting_material' and not value['source_refs'] and not value['actions']
    assert value['usage']['training'] is None and value['usage']['distributed'] is True
    assert value['binding'] != r2['binding']


@pytest.mark.parametrize('field', ['result_hash', 'binding', 'subject', 'version', 'usage'])
def test_wrong_result_identity_rejected(flow, field):
    svc, run, assessment, old, *_ = flow
    receipt, candidate = adopted(flow)
    value = deepcopy(receipt['result']); row = value['resources'][0]
    if field == 'result_hash': value['result_sha256'] = 'f' * 64
    elif field == 'binding': value['binding']['usage_hash'] = 'f' * 64
    elif field == 'subject': row['subject']['resource_id'] = 'cmp_other'
    elif field == 'version': row['subject']['version'] = '14.1.1'
    else: value['usage']['distributed'] = not value['usage']['distributed']
    with pytest.raises(P2Error, match='p2_local_action_binding_conflict'):
        build_local_actions(svc.p2, value, row, candidate)


@pytest.mark.parametrize('field', ['hash', 'scan', 'subject', 'version', 'commit', 'source_hash', 'source_role', 'raw_text'])
def test_wrong_source_even_with_rehashed_candidate_rejected(flow, field):
    svc, run, assessment, old, *_ = flow
    receipt, candidate = adopted(flow)
    new = receipt['result']; value = deepcopy(candidate)
    if field == 'hash': value['candidate_sha256'] = 'f' * 64
    elif field == 'scan': value['scan_id'] = 'scn_other'
    elif field == 'subject': value['subject']['resource_id'] = 'cmp_other'
    elif field == 'version': value['subject']['version'] = '14.1.1'
    elif field == 'commit': value['commit'] = 'f' * 40
    elif field == 'source_hash': value['sources'][0]['sha256'] = 'f' * 64
    elif field == 'source_role': value['sources'][0]['source_level'] = 'accepted'
    else: value['license_text'] += 'extra terms'
    if field != 'hash':
        check = {k: v for k, v in value.items() if k not in {'candidate_id', 'candidate_sha256'}}
        value['candidate_sha256'] = digest(check); value['candidate_id'] = 'p2src_' + digest(check)
    with pytest.raises(P2Error, match='p2_local_action_source_conflict'):
        build_local_actions(svc.p2, new, new['resources'][0], value)


def test_wrong_material_bytes_and_evidence_fail_closed(flow):
    svc, run, assessment, old, *_ = flow
    receipt, candidate = adopted(flow)
    new, material = receipt['result'], receipt['material']
    with svc.p2.store.connection(write=True) as db:
        db.execute('UPDATE p2_material_content SET content=? WHERE id=?', (b'altered', material['material_id']))
    with pytest.raises(P2Error, match='p2_integrity_error'):
        build_local_actions(svc.p2, new, new['resources'][0], candidate)


def test_source_absent_is_empty_projection_not_fake_material_or_permission(flow):
    svc, run, assessment, old, fetcher, model, app, root = flow
    value = build_local_actions(svc.p2, old, old['resources'][0], None)
    assert value['state'] == 'source_unavailable' and value['actions'] == value['clauses'] == value['source_refs'] == []
    assert value['usage'] == old['usage'] and value['model_calls'] == 0
    assert fetcher.calls == model.calls == 0


def test_jobs_disabled_keeps_saved_get_and_material_adoption_but_no_dispatch(flow):
    svc, run, assessment, old, fetcher, model, app, root = flow
    out = ready(flow)
    svc.jobs_enabled = False
    calls = fetcher.calls, model.calls
    def forbidden(*args, **kwargs):
        raise AssertionError('No new external or model operation authorized')
    fetcher.fetch = model.generate = forbidden
    before = svc.store.path.read_bytes()
    svc.on_terminal(run); svc.on_result(run.id, assessment.id, old); svc.safe_on_result(run.id, assessment.id, old)
    svc._fetch(run.id); svc._analyze(old['result_id'])
    assert svc.store.path.read_bytes() == before
    with pytest.raises(P2Error, match='official_source_jobs_disabled'):
        svc._submit(forbidden)
    app.state.p2_service.official_sources = svc
    base = f'/api/v1/scans/{run.id}/assessments/{assessment.id}/p2'
    with TestClient(app) as client:
        response = client.post(base + '/official-sources/adopt', json=adopt_body(old, out['candidate']['candidate_id']).model_dump())
        assert response.status_code == 201, response.text
        new = response.json()['result']
        assert new['revision'] == 2
        assert response.json()['material']['verification_state'] == 'pending'
        value = client.get(base + '/official-sources', params={'assessment_version': 1, 'result_id': new['result_id']}).json()
        assert value['runtime_jobs_enabled'] is False
        assert value['analysis']['state'] == 'not_scheduled' and value['analysis']['analysis_id'] is None
        assert value['local_actions']['state'] == 'supported_verification_actions'
        assert client.get(base + '/results/' + old['result_id'], params={'assessment_version': 1}).json() == old
        assert calls == (fetcher.calls, model.calls)


@pytest.mark.parametrize('invalid', [0, 1, None, '0', 'false'])
def test_jobs_configuration_must_be_bool(flow, invalid, tmp_path):
    svc, *_ = flow
    with pytest.raises(ValueError, match='explicit bool'):
        OfficialSourceService(svc.p2, tmp_path / 'new-store', svc.fetcher, svc.ai, jobs_enabled=invalid)
