"""Actual ASGI package reads on fresh SYNTHETIC_TEST_ONLY stores; no model/network."""
import hashlib
import io
import json
from copy import deepcopy
from types import SimpleNamespace
import zipfile

import pytest

from app.api.evaluation_export import router
from app.p2.contract import P2Error, canonical, digest
from app.p2.evaluation_export import MAX_FILE_BYTES
from test_p2_contract import setup as parent_setup, create, material_body, answer_body, counts


@pytest.fixture
def flow(parent_setup, monkeypatch):
    c, app, base, _, root = parent_setup
    if not any(getattr(route, 'path', '').endswith('/evaluation-package') for route in app.routes):
        app.include_router(router())
    def forbidden(*args, **kwargs):
        raise AssertionError('export may not connect or generate')
    monkeypatch.setattr('socket.create_connection', forbidden)
    monkeypatch.setattr('app.ai.p2_analysis.BoundQwen.generate', forbidden)
    return parent_setup


def package(c, base, result, **selection):
    return c.get(base + '/results/' + result['result_id'] + '/evaluation-package',
                 params={'assessment_version': result['binding']['assessment_version'], **selection})


def unpack(response):
    assert response.status_code == 200, response.text
    assert response.headers['content-type'] == 'application/zip'
    assert hashlib.sha256(response.content).hexdigest() == response.headers['x-content-sha256']
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert names == sorted(names) and len(names) == len(set(names))
        assert all(not x.startswith('/') and '..' not in x.split('/') for x in names)
        files = {name: archive.read(name) for name in names}
    for name, info in json.loads(files['FILE_HASHES.json']).items():
        assert info == {'byte_count': len(files[name]), 'sha256': hashlib.sha256(files[name]).hexdigest()}
    return files


def test_exact_get_is_reproducible_no_writes_and_original_reports_unchanged(flow):
    c, app, base, _, root = flow
    result = create(flow)
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.db')}
    row_counts = counts(root)
    first = package(c, base, result); files = unpack(first)
    assert package(c, base, result).content == first.content
    binding = result['binding']
    assert files['01_REPORT/Assessment.html'] == app.state.assessment_service.store.report(binding['scan_id'], binding['assessment_id'], 'html')
    assert files['01_REPORT/Assessment.json'] == app.state.assessment_service.store.report(binding['scan_id'], binding['assessment_id'], 'json')
    assert json.loads(files['02_P2/Result.json']) == result
    summary = json.loads(files['02_P2/Summary.json'])
    assert summary['result_sha256'] == result['result_sha256'] and summary['result_revision'] == 1
    manifest = json.loads(files['VERSION_BINDING.json'])
    assert manifest['binding'] == binding and manifest['business_writes'] == manifest['generation_model_calls'] == manifest['outbound_http_requests'] == 0
    assert '03_MATERIALS' not in files
    assert counts(root) == row_counts
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.db')} == before


def test_pending_material_answer_and_old_new_results_stay_separate(flow):
    c, _, base, _, root = flow
    r1 = create(flow)
    r2 = c.post(base + '/materials', json=material_body(r1)).json()['result']
    r3 = c.post(base + '/answers', json=answer_body(r2)).json()['result']
    before = counts(root)
    old = unpack(package(c, base, r1)); current = unpack(package(c, base, r3))
    assert not any(x.startswith(('03_MATERIALS/', '04_ANSWERS/')) for x in old)
    mid, aid = r3['material_ids'][0], r3['answer_ids'][0]
    material = json.loads(current[f'03_MATERIALS/{mid}/Material.json'])
    assert material['verification_state'] == 'pending' and material['source_level'] == 'user_supplied_unverified'
    raw = current[f'03_MATERIALS/{mid}/LICENSE']
    assert hashlib.sha256(raw).hexdigest() == material['source_sha256']
    assert json.loads(current[f'04_ANSWERS/{aid}.json'])['answer_id'] == aid
    assert json.loads(current['02_P2/Result.json']) == r3
    assert json.loads(old['02_P2/Result.json']) == r1 and counts(root) == before


@pytest.mark.parametrize('params,status', [({'assessment_version': 2}, 409),
    ({'analysis_id': '../private'}, 422), ({'analysis_id': 'id_a', 'preview_id': 'id_b'}, 422),
    ({'latest': '1'}, 422), ({'report_snapshot_id': 'rptv2_missing'}, 404)])
def test_wrong_or_unknown_selections_rejected(flow, params, status):
    c, _, base, _, root = flow; result = create(flow); before = counts(root)
    response = c.get(base + '/results/' + result['result_id'] + '/evaluation-package',
                     params={'assessment_version': 1, **params})
    assert response.status_code == status, response.text
    assert counts(root) == before


def test_duplicate_query_and_unknown_result_do_not_fall_back_to_head(flow):
    c, _, base, _, root = flow; result = create(flow); before = counts(root)
    path = base + '/results/' + result['result_id'] + '/evaluation-package'
    assert c.get(path + '?assessment_version=1&assessment_version=1').status_code == 422
    assert c.get(base + '/results/p2res_missing/evaluation-package?assessment_version=1').status_code == 404
    assert c.post(path, json={}).status_code == 405
    assert counts(root) == before


@pytest.mark.parametrize('sensitive', [b'/Users/someone/private/project', b'https://user:password@example.com/license',
    b'-----BEGIN RSA PRIVATE KEY-----', b'api_key=secretvalue12345'])
def test_sensitive_report_is_rejected_not_silently_omitted(flow, monkeypatch, sensitive):
    c, app, base, _, root = flow; result = create(flow); before = counts(root)
    original = app.state.assessment_service.store.report
    monkeypatch.setattr(app.state.assessment_service.store, 'report', lambda sid, aid, fmt: sensitive if fmt == 'html' else original(sid, aid, fmt))
    response = package(c, base, result)
    assert response.status_code == 409 and response.json()['error']['code'] == 'evaluation_package_sensitive_content_blocked'
    assert sensitive.decode() not in response.text and counts(root) == before


def test_wrong_material_row_or_hash_is_not_exported(flow, monkeypatch):
    c, app, base, _, _ = flow; r1 = create(flow)
    r2 = c.post(base + '/materials', json=material_body(r1)).json()['result']
    original = app.state.p2_service.record
    def wrong(*args):
        value = deepcopy(original(*args)); value['subject']['resource_id'] = 'cmp_other'; return value
    monkeypatch.setattr(app.state.p2_service, 'record', wrong)
    assert package(c, base, r2).status_code == 409


def test_size_bound_and_cross_assessment_report_refused(flow, monkeypatch):
    c, app, base, _, _ = flow; result = create(flow); original = app.state.assessment_service.store.report
    monkeypatch.setattr(app.state.assessment_service.store, 'report', lambda sid, aid, fmt: b'A' * (MAX_FILE_BYTES + 1) if fmt == 'html' else original(sid, aid, fmt))
    assert package(c, base, result).status_code == 413
    def cross(sid, aid, fmt):
        if fmt != 'json': return original(sid, aid, fmt)
        value = json.loads(original(sid, aid, fmt)); value['assessment']['id'] = 'asm_other'; return canonical(value)
    monkeypatch.setattr(app.state.assessment_service.store, 'report', cross)
    assert package(c, base, result).status_code == 409


def test_exact_ai_saved_body_selection_and_rejected_output_status(flow):
    c, app, base, _, _ = flow; result = create(flow); p2 = app.state.p2_service
    body = {'result_id': result['result_id'], 'result_revision': result['revision'],
            'result_sha256': result['result_sha256'], 'binding': result['binding'],
            'status': 'failed', 'error_code': 'SYNTHETIC_TEST_ONLY_TIMEOUT', 'source_refs': [], 'actions': [], 'clauses': []}
    sha = digest(body); identity = 'p2ai_' + sha
    value = {**body, 'analysis_id': identity, 'analysis_sha256': sha}
    def read(sid, aid, chosen, rid, version):
        assert (sid, aid, rid, version) == (result['binding']['scan_id'], result['binding']['assessment_id'], result['result_id'], 1)
        if chosen != identity: raise P2Error('p2_ai_not_found', 404)
        return value
    p2.ai_analysis = SimpleNamespace(read=read)
    files = unpack(package(c, base, result, analysis_id=identity))
    assert json.loads(files['05_AI_AND_SOURCES/Analysis.json']) == value
    assert package(c, base, result, analysis_id='p2ai_other').status_code == 404
    p2.ai_analysis = SimpleNamespace(read=lambda *args: (_ for _ in ()).throw(P2Error('p2_ai_saved_output_rejected', 409)))
    files = unpack(package(c, base, result, analysis_id=identity))
    assert '05_AI_AND_SOURCES/Analysis.json' not in files
    status = json.loads(files['05_AI_AND_SOURCES/Status.json'])['analysis']
    assert status['state'] == 'REJECTED_SAVED_OUTPUT' and status['analysis_id'] == identity


def test_source_actions_hash_and_fixed_preview_never_auto_selected(flow):
    c, app, base, _, _ = flow; result = create(flow); p2 = app.state.p2_service
    candidate = {'candidate_id': 'p2src_synthetic', 'subject': result['resources'][0]['subject'],
                 'license_text': 'SYNTHETIC_TEST_ONLY license'}
    preview = {'binding': result['binding'], 'result_id': result['result_id'], 'result_revision': 1,
               'result_sha256': result['result_sha256'], 'candidate_id': candidate['candidate_id'],
               'status': 'failed', 'actions': [], 'clauses': [],
               'source_refs': [{'candidate_id': candidate['candidate_id'], 'subject': candidate['subject'],
                    'source_sha256': hashlib.sha256(candidate['license_text'].encode()).hexdigest(),
                    'source_level': 'retrieved_unadopted_candidate', 'verification_state': 'pending'}]}
    sha = digest(preview); pid = 'p2preview_' + sha
    preview.update(preview_id=pid, preview_sha256=sha)
    actions = {'binding': result['binding'], 'result_id': result['result_id'],
               'result_sha256': result['result_sha256'], 'actions': [{'text': '核对SYNTHETIC_TEST_ONLY原文范围。'}]}
    actions['content_sha256'] = digest(actions)
    status = {'binding': result['binding'], 'result_id': result['result_id'], 'result_sha256': result['result_sha256'],
              'candidate': candidate, 'fetch': {'state': 'failed', 'error_code': 'upstream_404'},
              'analysis': {'state': 'failed', 'analysis_id': None, 'preview_id': pid, 'preview': preview},
              'local_actions': actions}
    p2.official_sources = SimpleNamespace(status=lambda *args: deepcopy(status), close=lambda: None)
    assert package(c, base, result).status_code == 409
    files = unpack(package(c, base, result, preview_id=pid))
    assert json.loads(files['06_ACTIONS/SourceBoundActions.json']) == actions
    assert 'SYNTHETIC_TEST_ONLY原文范围' in files['START_HERE.html'].decode()
    assert package(c, base, result, preview_id='p2preview_other').status_code == 409
    status['local_actions']['binding']['assessment_version'] = 2
    assert package(c, base, result, preview_id=pid).status_code == 409


def test_selected_actual_archive_keeps_original_artifact_identity(flow):
    c, app, base, _, _ = flow; result = create(flow)
    response = c.post(base[:-3] + '/report-v2', json={'idempotency_key': 'export-fixed-archive',
                      'task_refs': [], 'notice_refs': [], 'algorithm_refs': []})
    assert response.status_code == 200, response.text
    snapshot = response.json(); identity = snapshot['snapshot_id']
    files = unpack(package(c, base, result, report_snapshot_id=identity))
    assert json.loads(files['VERSION_BINDING.json'])['report_snapshot_id'] == identity
    for fmt in ('json', 'html'):
        assert files['01_REPORT/Archive.' + fmt] == app.state.report_v2_service.artifact(
            result['binding']['scan_id'], result['binding']['assessment_id'], identity, fmt)


@pytest.mark.parametrize('mutation', ['quote', 'unlisted_source', 'promoted_ref', 'wrong_bytes', 'duplicate_ref'])
def test_real_saved_ai_get_and_quote_reference_guard(flow, monkeypatch, mutation):
    from app.p2.ai_analysis import AnalysisStore, P2AnalysisService
    from test_p2_ai_analysis import Model, TEXT
    c, app, base, _, root = flow; old = create(flow)
    receipt = c.post(base + '/materials', json=material_body(old, TEXT)).json()
    result, material = receipt['result'], receipt['material']
    store = AnalysisStore(root / 'p2-ai.db'); store.initialize()
    model = Model(); model.calls = 0
    service = P2AnalysisService(app.state.p2_service, store, model, public_sample_only=False)
    app.state.p2_service.ai_analysis = service
    response = c.post(base + '/ai-analyses', json={'binding': result['binding'], 'result_id': result['result_id'],
        'result_sha256': result['result_sha256'], 'material_ids': [material['material_id']],
        'idempotency_key': 'export-saved-ai', 'previous_result_id': old['result_id']})
    assert response.status_code == 201 and response.json()['status'] == 'succeeded', response.text
    saved = response.json(); calls = model.calls; before = counts(root)
    files = unpack(package(c, base, result, analysis_id=saved['analysis_id']))
    assert json.loads(files['05_AI_AND_SOURCES/Analysis.json']) == saved
    assert model.calls == calls and counts(root) == before
    bad = deepcopy(saved)
    if mutation == 'quote': bad['clauses'][0]['quote'] = 'wrong text'
    if mutation == 'unlisted_source': bad['source_refs'] = []
    if mutation == 'promoted_ref': bad['source_refs'][0]['verification_state'] = 'verified'
    if mutation == 'wrong_bytes': bad['source_refs'][0]['byte_count'] += 1
    if mutation == 'duplicate_ref': bad['source_refs'] *= 2
    body = dict(bad); body.pop('analysis_id'); body.pop('analysis_sha256')
    bad['analysis_sha256'] = digest(body); bad['analysis_id'] = 'p2ai_' + bad['analysis_sha256']
    monkeypatch.setattr(service, 'read', lambda *args: deepcopy(bad))
    assert package(c, base, result, analysis_id=bad['analysis_id']).status_code == 409


def test_summary_row_closure_rechecked(flow, monkeypatch):
    c, app, base, _, _ = flow; result = create(flow); p2 = app.state.p2_service
    original = p2.summary
    def wrong(*args):
        value = original(*args); value['resource_states'] = {}; return value
    monkeypatch.setattr(p2, 'summary', wrong)
    assert package(c, base, result).status_code == 409


def test_action_cannot_cite_a_material_which_no_clause_cites():
    from app.p2.evaluation_export import _quote_closure
    value = {'status': 'succeeded', 'quote_index_unit': 'unicode_code_point',
             'clauses': [{'material_id': 'mat_a', 'quote': 'alpha', 'start': 0, 'end': 5}],
             'actions': [{'source_material_ids': ['mat_b'], 'claim_level': 'verification_action_only'}]}
    with pytest.raises(P2Error) as failure:
        _quote_closure(value, {'mat_a': 'alpha', 'mat_b': 'beta'})
    assert failure.value.code == 'evaluation_package_analysis_reference_conflict'
