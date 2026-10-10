"""Controlled product-contract regressions, not real-project value evidence."""
import base64
import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_default_app
from app.assessment.engine import build_assessment
from app.domain.models import ScanRun, HashValue
from app.domain.usage import UsageDeclaration
from app.p2.contract import P2Error, Result, canonical, digest
from test_v4_assessment_core import controlled


def counts(root):
    result = {}
    for path in root.glob('*.db'):
        with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as db:
            result[path.name] = {t: db.execute('SELECT count(*) FROM "' + t + '"').fetchone()[0]
                                 for t, in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return result


def seed(app, run, usage):
    svc = app.state.assessment_service
    payload = run.model_dump(mode='json')
    queued = {**payload, 'status': 'queued', 'stage': 'queued', 'progress': 0, 'started_at': None, 'finished_at': None, 'idempotency_key': None}
    svc.registry.create(ScanRun.model_validate(queued))
    running = {**queued, 'status': 'running', 'stage': 'ingestion', 'progress': 5, 'started_at': payload['started_at']}
    svc.registry.replace(ScanRun.model_validate(running), expected_revision=1)
    payload['idempotency_key'] = None
    run = ScanRun.model_validate(payload)
    svc.registry.replace(run, expected_revision=2)
    return svc.store.create(build_assessment(run, usage), idempotency_key='controlled-parent', run=run)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    for key, value in {'OPENGUARD_DATA_DIR': str(tmp_path), 'OPENGUARD_ENABLE_ASSESSMENTS': '1',
                       'OPENGUARD_ENABLE_P2': '1', 'OPENGUARD_P2_READONLY': '0', 'OPENGUARD_P2_DATA_SCOPE': 'TEST_ONLY',
                       'OPENGUARD_ENABLE_AI': '0', 'OPENGUARD_ENABLE_PUBLIC_GIT': '0', 'OPENGUARD_ENABLE_DURABLE_ZIP': '0',
                       'OPENGUARD_ENABLE_PROFILE_METADATA': '0', 'OPENGUARD_ENABLE_EXTERNAL_SCANNERS': '0'}.items():
        monkeypatch.setenv(key, value)
    app = create_default_app()
    run = controlled()
    # Existing P0 human-reviewed fixture, with explicit resource/version scope.
    run.evidence[0].producer = run.evidence[-1].producer
    run.evidence[0].detected_by = run.evidence[-1].detected_by
    run.evidence[0].content_hash = HashValue(algorithm='sha256', value=hashlib.sha256((run.evidence[0].excerpt or 'controlled source').encode()).hexdigest())
    usage = UsageDeclaration(commercial=True, distributed=True, modified=False, network_service=None,
                             training=False, redistributed_assets=False, source_disclosure=False)
    a = seed(app, run, usage)
    with TestClient(app, raise_server_exceptions=False) as client:
        base = f'/api/v1/scans/{a.scan_id}/assessments/{a.id}/p2'
        binding = client.get(base + '/binding').json()
        body = {'binding': binding, 'expected_revision': 0, 'parent_result_id': None, 'idempotency_key': 'create-key-1'}
        yield client, app, base, body, tmp_path


def create(h):
    c, _, base, body, _ = h
    response = c.post(base + '/results', json=body)
    assert response.status_code == 201, response.text
    return response.json()['result']


def answer_body(result, key='answer-key-1'):
    q = result['questions'][0]
    return {'binding': result['binding'], 'expected_revision': result['revision'], 'parent_result_id': result['result_id'],
            'idempotency_key': key, 'question_id': q['question_id'], 'question_code': q['question_code'],
            'answer_code': 'YES_INCLUDE', 'subjects': q['subjects'][:1], 'evidence_ids': []}


def material_body(result, raw=b'MIT License\nUnreviewed controlled test text.', key='material-key-1'):
    r = next(r for r in result['resources'] if r['subject']['version'])
    return {'binding': result['binding'], 'expected_revision': result['revision'], 'parent_result_id': result['result_id'],
            'idempotency_key': key, 'subject': r['subject'], 'evidence_ids': r['evidence_ids'][:1], 'filename': 'LICENSE',
            'content_base64': base64.b64encode(raw).decode(), 'source_sha256': hashlib.sha256(raw).hexdigest(),
            'source_description': 'Controlled test input, not official provenance', 'completeness': 'EXCERPT'}


def test_default_factory_candidates_and_exact_immutable_get(setup):
    c, app, base, body, root = setup
    original = counts(root)
    r = create(setup)
    assert r['publication_status'] == 'succeeded' and r['formal_effect'] == 'none' and r['model_calls'] == 0
    assert r['computation'] == 'DETERMINISTIC_P2B'
    advice = {a['usage']: a for a in r['resources'][0]['advice']}
    assert advice['commercial']['state'] == 'unknown'
    assert advice['network_service']['saved_value'] is None
    assert advice['modified']['selection'] == 'NOT_SELECTED'
    assert not advice['commercial']['conditions'] and not advice['commercial']['basis_evidence_ids']
    assert 'upstream_source_attestation_missing' in advice['commercial']['gaps']
    before = counts(root)
    blob = c.get(base + '/results/' + r['result_id'], params={'assessment_version': 1}).content
    assert json.loads(blob) == r
    for _ in range(3):
        assert c.get(base + '/results/' + r['result_id'], params={'assessment_version': 1}).content == blob
    assert before == counts(root)
    assert original['assessment.db'] == before['assessment.db']
    assert original['scans.db'] == before['scans.db']
    assert c.post(base + '/results', json=body).json()['result'] == r


def test_answer_new_revision_same_assessment_and_summary(setup):
    c, app, base, _, root = setup
    old = create(setup)
    old_report = app.state.assessment_service.store.report(old['binding']['scan_id'], old['binding']['assessment_id'])
    reply = c.post(base + '/answers', json=answer_body(old))
    assert reply.status_code == 201, reply.text
    new, answer = reply.json()['result'], reply.json()['answer']
    assert new['revision'] == 2 and new['binding'] == old['binding']
    assert new['previous_result_id'] == old['result_id'] and answer['provenance'] == 'USER_ASSERTED'
    assert new['resources'][0]['user_assertions']['DELIVERY_SCOPE_FOR_RESOURCES'] == 'YES_INCLUDE'
    summary = c.get(base + '/results/' + new['result_id'] + '/summary', params={'assessment_version': 1}).json()
    assert summary['result_revision'] == 2 and summary['result_sha256'] == new['result_sha256']
    assert summary['binding'] == old['binding'] and summary['formal_effect'] == 'none'
    assert c.get(base + '/results/' + old['result_id'], params={'assessment_version': 1}).json() == old
    assert app.state.assessment_service.store.report(old['binding']['scan_id'], old['binding']['assessment_id']) == old_report
    assert c.get(base + '/answers/' + answer['answer_id'], params={'assessment_version': 1}).json() == answer


def test_material_is_pending_observation_not_new_license(setup):
    c, _, base, _, _ = setup
    old = create(setup)
    response = c.post(base + '/materials', json=material_body(old))
    assert response.status_code == 201, response.text
    new, material = response.json()['result'], response.json()['material']
    assert new['revision'] == 2 and new['binding'] == old['binding']
    assert material['adoption_status'] == 'adopted_as_unverified_observation'
    assert material['verification_state'] == 'pending' and material['formal_effect'] == 'none'
    assert 'uploaded_material_incomplete' in new['resources'][0]['gaps']
    assert c.get(base + '/materials/' + material['material_id'], params={'assessment_version': 1}).json() == material
    summary = c.get(base + '/results/' + new['result_id'] + '/summary', params={'assessment_version': 1}).json()
    assert summary['material_ids'] == [material['material_id']]


@pytest.mark.parametrize('field,value', [('assessment_version', 2), ('facts_hash', 'f' * 64), ('usage_hash', 'e' * 64),
                                      ('rule_version', 'other'), ('registry_revision', 99), ('project_revision', 'other'),
                                      ('assessment_sha256', 'c' * 64), ('scan_id', 'scn_other'), ('assessment_id', 'asm_other')])
def test_parent_mismatch_refuses_without_publication(setup, field, value):
    c, _, base, body, root = setup
    bad = deepcopy(body); bad['binding'][field] = value
    before = counts(root)
    response = c.post(base + '/results', json=bad)
    assert response.status_code == 409 and response.json()['error']['code'] == 'p2_parent_binding_conflict'
    assert counts(root) == before


@pytest.mark.parametrize('change,code,status', [
    ({'filename': '../LICENSE'}, 'p2_unsupported_material_name', 422),
    ({'filename': 'package.json'}, 'p2_unsupported_material_name', 422),
    ({'source_sha256': 'f' * 64}, 'p2_material_hash_mismatch', 422),
    ({'content_base64': '!bad'}, 'p2_material_base64_invalid', 422),
    ({'evidence_ids': ['evd_unrelated']}, 'p2_evidence_wrong_resource', 409),
    ({'subject': {'resource_id': 'cmp_other', 'version': '1.0.0'}}, 'p2_resource_not_found', 404),
    ({'source_description': ''}, 'p2_request_invalid', 422),
    ({'official_statement': True}, 'p2_request_invalid', 422),
    ({'evidence_ids': []}, 'p2_request_invalid', 422),
])
def test_material_errors_no_new_rows(setup, change, code, status):
    c, _, base, _, root = setup
    result = create(setup); body = material_body(result); body.update(change)
    before = counts(root)
    reply = c.post(base + '/materials', json=body)
    assert reply.status_code == status, reply.text
    assert reply.json()['error']['code'] == code
    assert counts(root) == before


@pytest.mark.parametrize('raw,code,status', [(b'x' * 65537, 'p2_material_size_limit', 413), (b'\xff', 'p2_material_utf8_required', 422),
                                           (b'a\x00b', 'p2_material_binary_content', 422), (b' \n', 'p2_material_empty_text', 422)],
                         ids=['over-64KiB', 'invalid-utf8', 'nul', 'blank'])
def test_material_byte_rules(setup, raw, code, status):
    c, _, base, _, root = setup
    result = create(setup); before = counts(root)
    reply = c.post(base + '/materials', json=material_body(result, raw))
    assert reply.status_code == status and reply.json()['error']['code'] == code, reply.text
    assert before == counts(root)


def test_material_wrong_version_and_atomic_duplicate_policy(setup):
    c, _, base, _, root = setup
    r = create(setup); body = material_body(r)
    bad = deepcopy(body); bad['subject']['version'] = '99.0.0'
    assert c.post(base + '/materials', json=bad).json()['error']['code'] == 'p2_resource_version_conflict'
    saved = c.post(base + '/materials', json=body).json()
    assert c.post(base + '/materials', json=body).json() == saved
    new = material_body(saved['result'], key='new-action-key')
    assert c.post(base + '/materials', json=new).json()['error']['code'] == 'p2_duplicate_material'
    conflict = material_body(saved['result'], b'Other bytes', key='conflicting-key')
    assert c.post(base + '/materials', json=conflict).json()['error']['code'] == 'p2_material_identity_conflict'


def test_network_retry_reuses_exact_response_and_stale_cas_returns_head(setup):
    c, _, base, _, root = setup
    r = create(setup); body = answer_body(r)
    lost_response = c.post(base + '/answers', json=body).json()
    after = counts(root)
    assert c.post(base + '/answers', json=body).json() == lost_response and counts(root) == after
    different = {**body, 'answer_code': 'NO_EXCLUDE'}
    assert c.post(base + '/answers', json=different).json()['error']['code'] == 'p2_idempotency_conflict'
    stale = {**body, 'idempotency_key': 'stale-key-1'}
    reply = c.post(base + '/answers', json=stale)
    assert reply.status_code == 409
    assert reply.json()['error']['details']['current_result_id'] == lost_response['result']['result_id']


def test_repeated_same_answer_with_new_key_is_noop(setup):
    c, _, base, _, root = setup
    first = c.post(base + '/answers', json=answer_body(create(setup))).json()
    r = first['result']; count = counts(root)['p2.db']['p2_objects']
    second = c.post(base + '/answers', json=answer_body(r, 'same-action-new-key')).json()
    assert second == first and counts(root)['p2.db']['p2_objects'] == count


@pytest.mark.parametrize('field,value', [('question_id', 'p2q_wrong'), ('answer_code', 'FULFILLED'),
                                      ('evidence_ids', ['evd_wrong']), ('subjects', [{'resource_id': 'cmp_other', 'version': None}])])
def test_answer_binding_rejections(setup, field, value):
    c, _, base, _, root = setup
    result = create(setup); body = answer_body(result); body[field] = value; before = counts(root)
    assert c.post(base + '/answers', json=body).status_code in {404, 409, 422}
    assert counts(root) == before


def test_cas_two_writers_publish_only_one_revision(setup):
    c, _, base, _, root = setup
    r = create(setup)
    with ThreadPoolExecutor(2) as pool:
        replies = list(pool.map(lambda key: c.post(base + '/answers', json=answer_body(r, key)), ['parallel-key-1', 'parallel-key-2']))
    assert sorted(x.status_code for x in replies) == [201, 409]
    assert c.get(base + '/results', params={'assessment_version': 1}).json()['head_revision'] == 2


def test_get_is_pure_and_reads_missing_without_generation(setup, monkeypatch):
    c, app, base, _, root = setup
    r = create(setup); before = counts(root)
    def prohibited(*a, **k):
        raise AssertionError('read initiated work')
    monkeypatch.setattr(app.state.p2_service, 'context', prohibited)
    monkeypatch.setattr(app.state.p2_service, 'candidate', prohibited)
    monkeypatch.setattr(app.state.p2_service.store, 'initialize', prohibited)
    for path in ['/results/' + r['result_id'], '/results/' + r['result_id'] + '/summary', '/results']:
        assert c.get(base + path, params={'assessment_version': 1}).status_code == 200
    assert c.get(base + '/results/missing', params={'assessment_version': 1}).status_code == 404
    assert c.get(base + '/results/' + r['result_id'], params={'assessment_version': 2}).status_code == 409
    assert counts(root) == before


def test_restart_reads_identical_result_and_summary(setup):
    c, _, base, _, _ = setup
    r = create(setup)
    second = create_default_app()
    with TestClient(second) as reopened:
        assert reopened.get(base + '/results/' + r['result_id'], params={'assessment_version': 1}).json() == r
        assert reopened.get(base + '/results/' + r['result_id'] + '/summary', params={'assessment_version': 1}).status_code == 200


def test_disabled_and_readonly_keep_reads_and_no_writes(setup):
    c, app, base, body, root = setup
    r = create(setup); before = counts(root)
    app.state.p2_service.readonly = True
    assert c.post(base + '/answers', json=answer_body(r)).json()['error']['code'] == 'p2_read_only'
    assert c.get(base + '/results/' + r['result_id'], params={'assessment_version': 1}).status_code == 200
    app.state.p2_service = None
    assert c.post(base + '/results', json=body).json()['error']['code'] == 'p2_service_disabled'
    assert counts(root) == before


def test_origin_duplicate_json_and_request_budget(setup):
    c, _, base, body, root = setup
    assert c.post(base + '/results', json=body, headers={'Origin': 'https://bad.example'}).status_code == 403
    assert c.post(base + '/results', content='{"x":1,"x":2}', headers={'content-type': 'application/json'}).json()['error']['code'] == 'p2_json_invalid'
    assert c.post(base + '/results', content='{"x":NaN}', headers={'content-type': 'application/json'}).status_code == 422
    assert c.post(base + '/materials', content='x' * 98305, headers={'content-type': 'application/json'}).status_code == 413


def test_fault_rolls_back_material_result_summary_and_request(setup, monkeypatch):
    c, app, base, _, root = setup
    r = create(setup); before = counts(root)
    original = app.state.p2_service.store.put
    def fail_summary(db, kind, *args):
        if kind == 'summary':
            raise OSError('controlled storage interruption')
        return original(db, kind, *args)
    monkeypatch.setattr(app.state.p2_service.store, 'put', fail_summary)
    reply = c.post(base + '/materials', json=material_body(r))
    assert reply.status_code == 503 and counts(root) == before


def test_corrupt_snapshot_is_not_repaired(setup):
    c, app, base, _, root = setup
    r = create(setup)
    with sqlite3.connect(root / 'p2.db') as db:
        db.execute("UPDATE p2_objects SET payload=? WHERE id=?", (b'{}', r['result_id']))
    before = (root / 'p2.db').read_bytes()
    reply = c.get(base + '/results/' + r['result_id'], params={'assessment_version': 1})
    assert reply.status_code == 503 and reply.json()['error']['code'] == 'p2_integrity_error'
    assert (root / 'p2.db').read_bytes() == before


def variant(h, mutate):
    c, app, base, body, root = h
    p = app.state.assessment_service.run(body['binding']['scan_id']).model_dump(mode='json')
    p['id'] = 'scn_' + str(uuid4())
    mutate(p)
    p['summary']['component_count'] = len(p['components'])
    p['summary']['evidence_count'] = len(p['evidence'])
    a = seed(app, ScanRun.model_validate(p), app.state.assessment_service.store.get_by_id(body['binding']['assessment_id']).usage)
    base = f'/api/v1/scans/{a.scan_id}/assessments/{a.id}/p2'
    b = c.get(base + '/binding').json()
    return c, app, base, {'binding': b, 'expected_revision': 0, 'parent_result_id': None, 'idempotency_key': 'variant-create'}, root


def test_unknown_and_pending_are_not_license_success(setup):
    def mutate(p):
        p['licenses'][0]['verification_status'] = 'pending'
        p['evidence'][0]['verification_status'] = 'pending'
    h = variant(setup, mutate); c, _, base, _, _ = h
    r = create(h)
    assert r['state'] == 'unknown'
    assert all(a['state'] != 'conditional_candidate' for a in r['resources'][0]['advice'])
    response = c.post(base + '/materials', json=material_body(r))
    assert response.status_code == 201
    assert response.json()['result']['state'] == 'pending'
    assert all(a['state'] != 'conditional_candidate' for a in response.json()['result']['resources'][0]['advice'])


def test_incremental_subset_reuses_unaffected_row_exactly(setup):
    def mutate(p):
        other = deepcopy(p['components'][0]); other['id'] = 'cmp_' + str(uuid4())
        other['license_expression_id'] = None
        other['evidence_ids'] = [p['evidence'][0]['id']]
        p['components'].append(other)
    h = variant(setup, mutate); c, _, base, _, _ = h
    old = create(h); body = answer_body(old)
    reply = c.post(base + '/answers', json=body)
    assert reply.status_code == 201, reply.text
    new = reply.json()['result']; affected = body['subjects'][0]['resource_id']
    assert new['recomputed_resource_ids'] == [affected] and len(new['reused_resource_ids']) == 1
    before = {r['subject']['resource_id']: r for r in old['resources']}
    assert all(r == before[r['subject']['resource_id']] for r in new['resources'] if r['subject']['resource_id'] != affected)


@pytest.mark.parametrize('change', ['wrong-resource', 'wrong-version', 'two-scopes', 'two-license-hashes'])
def test_stored_conflicting_evidence_refused_before_write(setup, change):
    def mutate(p):
        scope = p['evidence'][-1]
        if change in {'wrong-resource', 'wrong-version'}:
            obj = json.loads(scope['excerpt']); obj['resource_id' if change == 'wrong-resource' else 'version'] = 'different'
            scope['excerpt'] = json.dumps(obj)
        else:
            extra = deepcopy(scope if change == 'two-scopes' else p['evidence'][0]); extra['id'] = 'evd_' + str(uuid4())
            if change == 'two-scopes':
                obj = json.loads(extra['excerpt']); obj['scope'] = 'runtime_dependency'; extra['excerpt'] = json.dumps(obj)
            else:
                extra['content_hash']['value'] = 'f' * 64
                p['licenses'][0]['evidence_ids'].append(extra['id'])
            p['components'][0]['evidence_ids'].append(extra['id']); p['evidence'].append(extra)
    h = variant(setup, mutate); c, _, base, body, root = h
    before = counts(root)
    response = c.post(base + '/results', json=body)
    assert response.status_code == 409 and response.json()['error']['code'] in {'p2_evidence_binding_conflict', 'p2_evidence_conflict'}
    assert counts(root) == before


def test_root_license_or_scanner_verified_flag_is_not_human_binding(setup):
    def mutate(p):
        p['evidence'][0]['producer']['type'] = 'scanner'
    r = create(variant(setup, mutate))
    assert not any(a['state'] == 'conditional_candidate' for a in r['resources'][0]['advice'])


def test_configuration_change_cannot_relabel_test_results_owner(setup):
    c, app, base, _, root = setup
    r = create(setup); before = counts(root)
    app.state.p2_service.data_scope = 'OWNER'
    assert c.get(base + '/results/' + r['result_id'], params={'assessment_version': 1}).status_code == 503
    assert c.post(base + '/answers', json=answer_body(r)).status_code == 503
    assert counts(root) == before


def test_parent_rechecked_before_publication(setup, monkeypatch):
    c, app, base, body, root = setup
    original = app.state.p2_service.context; calls = []
    def changing(*args):
        result = original(*args); calls.append(1)
        if len(calls) > 1:
            result[2]['registry_revision'] += 1
        return result
    monkeypatch.setattr(app.state.p2_service, 'context', changing)
    before = counts(root)
    reply = c.post(base + '/results', json=body)
    assert reply.status_code == 409 and counts(root) == before


def test_factory_disabled_route_is_stable_503_without_new_store(setup, monkeypatch):
    _, _, base, _, root = setup
    monkeypatch.setenv('OPENGUARD_ENABLE_P2', '0')
    before = counts(root)
    with TestClient(create_default_app()) as client:
        response = client.get(base + '/results/missing', params={'assessment_version': 1})
        assert response.status_code == 503 and response.json()['error']['code'] == 'p2_service_disabled'
    assert counts(root) == before


def test_material_exact_size_allowed_and_no_execution(setup):
    c, _, base, _, _ = setup
    r = create(setup)
    reply = c.post(base + '/materials', json=material_body(r, b'x' * 65536))
    assert reply.status_code == 201 and reply.json()['material']['byte_count'] == 65536


def test_published_summary_failure_does_not_erase_saved_result(setup, monkeypatch):
    c, app, base, _, root = setup
    old = create(setup)
    saved = c.post(base + '/answers', json=answer_body(old)).json()['result']
    monkeypatch.setattr(app.state.p2_service, 'summary', lambda *args: (_ for _ in ()).throw(P2Error('p2_storage_unavailable', 503)))
    assert c.get(base + '/results/' + saved['result_id'] + '/summary', params={'assessment_version': 1}).status_code == 503
    assert c.get(base + '/results/' + saved['result_id'], params={'assessment_version': 1}).json() == saved


def test_human_scope_is_not_upstream_license_provenance(setup):
    # P0's reviewed flag and scope are not P2B's upstream/applicability receipt.
    result = create(setup)
    assert all(a['state'] != 'conditional_candidate' for r in result['resources'] for a in r['advice'])
    assert result['resources'][0]['inherited_local_support'] is True
    assert 'upstream_source_attestation_missing' in result['resources'][0]['gaps']


def test_get_rejects_valid_payload_relocated_under_other_row_id(setup):
    c, _, base, _, root = setup
    old = create(setup)
    new = c.post(base + '/answers', json=answer_body(old)).json()['result']
    with sqlite3.connect(root / 'p2.db') as db:
        blob, sha = db.execute('SELECT payload,sha256 FROM p2_objects WHERE id=?', (new['result_id'],)).fetchone()
        db.execute('UPDATE p2_objects SET payload=?,sha256=? WHERE id=?', (blob, sha, old['result_id']))
    response = c.get(base + '/results/' + old['result_id'], params={'assessment_version': 1})
    assert response.status_code == 503


@pytest.mark.parametrize('source', ['registry', 'assessment'])
def test_parent_storage_unavailable_is_not_not_found(setup, monkeypatch, source):
    from app.persistence.scan_registry import ScanRegistryError
    from app.assessment.store import AssessmentStoreError
    c, app, base, _, _ = setup
    target, name, error = ((app.state.p2_service.registry, 'get', ScanRegistryError('registry_integrity_error'))
                           if source == 'registry' else (app.state.p2_service.assessments, 'get_by_id', AssessmentStoreError('read_failed')))
    monkeypatch.setattr(target, name, lambda *a: (_ for _ in ()).throw(error))
    response = c.get(base + '/binding')
    assert response.status_code == 503 and response.json()['error']['code'] == 'p2_parent_storage_unavailable'


@pytest.mark.parametrize('change', ['normalization', 'other-text'])
def test_conflicting_license_facts_cannot_be_dropped_by_adapter(setup, change):
    def mutate(p):
        if change == 'normalization':
            p['licenses'][0]['normalized_ids'] = ['Apache-2.0']
        else:
            extra = deepcopy(p['evidence'][0]); extra['id'] = 'evd_' + str(uuid4())
            extra['content_hash']['value'] = 'e' * 64
            p['components'][0]['evidence_ids'].append(extra['id']); p['evidence'].append(extra)
    h = variant(setup, mutate); c, _, base, body, root = h
    before = counts(root); response = c.post(base + '/results', json=body)
    assert response.status_code == 409 and response.json()['error']['code'] == 'p2_evidence_conflict'
    assert counts(root) == before


def test_idempotency_receipt_must_match_stored_result(setup):
    c, _, base, body, root = setup
    old = create(setup)
    with sqlite3.connect(root / 'p2.db') as db:
        raw, = db.execute('SELECT payload FROM p2_requests').fetchone()
        receipt = json.loads(raw); receipt['result']['resources'][0]['gaps'].append('forged')
        raw = canonical(receipt)
        db.execute('UPDATE p2_requests SET payload=?,sha256=?', (raw, hashlib.sha256(raw).hexdigest()))
    response = c.post(base + '/results', json=body)
    assert response.status_code == 503
    assert c.get(base + '/results/' + old['result_id'], params={'assessment_version': 1}).json() == old


def test_published_schema_matches_product_dtos_and_exact_routes(setup):
    from pathlib import Path
    from app.p2 import contract as c
    from jsonschema import Draft202012Validator
    bundle = json.loads(Path('schemas/p2/contract-v1.schema.json').read_text())
    Draft202012Validator.check_schema(bundle)
    for cls in (c.Binding, c.CreateRequest, c.AnswerRequest, c.MaterialRequest, c.Result, c.ResultIndex,
                c.Answer, c.Material, c.Summary, c.Receipt, c.ErrorEnvelope):
        expected = cls.model_json_schema(); expected.pop('$defs', None)
        assert bundle['$defs'][cls.__name__] == expected
    client, _, base, _, _ = setup
    result = create(setup)
    Draft202012Validator({'$defs': bundle['$defs'], '$ref': '#/$defs/Result'}).validate(result)
    openapi = client.get('/openapi.json').json()
    paths = openapi['paths']
    prefix = '/api/v1/scans/{scan_id}/assessments/{assessment_id}/p2'
    assert set(p for p in paths if '/p2/' in p) == {prefix + s for s in (
        '/binding', '/results', '/results/{result_id}', '/results/{result_id}/summary',
        '/answers', '/answers/{answer_id}', '/materials', '/materials/{material_id}')}
    for path, methods in paths.items():
        if path.startswith(prefix):
            for method in methods.values():
                ref = method['responses']['409']['content']['application/json']['schema']['$ref']
                assert openapi['components']['schemas'][ref.rsplit('/', 1)[-1]]['title'] == 'ErrorEnvelope'
                assert 'p2' in ref  # FastAPI qualifies collision with the original P0 ErrorEnvelope


def test_missing_source_hash_is_not_replaced_by_evidence_record_hash(setup):
    def mutate(p):
        p['evidence'][0]['content_hash'] = None
    result = create(variant(setup, mutate))
    resource = result['resources'][0]
    assert set(resource['evidence_source_hashes']) < set(resource['evidence_ids'])
    assert 'evidence_source_hash_missing' in resource['gaps']
    assert all(a['state'] != 'conditional_candidate' for a in resource['advice'])
