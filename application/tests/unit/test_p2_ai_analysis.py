"""Real ASGI/router/store; only bottom model transport is synthetic TEST_ONLY."""
import json
from copy import deepcopy
import hashlib

import pytest
from fastapi.testclient import TestClient

from app.p2.ai_analysis import AnalysisStore, P2AnalysisService
from app.p2.contract import canonical
from app.ai.p2_analysis import BoundQwen, BudgetError
from app.ai.ollama import MODEL_NAME, MANIFEST_DIGEST, OLLAMA_VERSION
from test_p2_contract import setup as parent_setup, create, material_body, counts

TEXT = b'Permission is hereby granted to read this synthetic TEST_ONLY fixture.\nThe copyright notice shall be preserved in supplied copies.\nTHE SOFTWARE IS PROVIDED AS IS WITHOUT WARRANTY.'


class Model:
    model = {'name': 'SYNTHETIC_TEST_ONLY', 'digest': 'a'*64, 'runtime': 'synthetic', 'prompt_version': 'test/1'}
    model_calls = 0
    last_metrics = {'prompt_eval_count': 101, 'eval_count': 34, 'total_duration': 1000}
    calls = 0
    mutate = None
    error = None

    def generate(self, payload):
        self.calls += 1; self.model_calls = 1; self.payload = deepcopy(payload)
        if self.error:
            raise self.error
        mid = payload['materials'][0]['material_id']
        obj = {'clauses': [{'material_id': mid, 'quote': payload['materials'][0]['quote_candidates'][0], 'category': 'condition'}],
               'actions': [{'text': '核对实际交付文件是否包含对应声明，并保留逐项核验记录。', 'source_material_ids': [mid]}],
               'change_explanations': [{'index': i, 'text': '本项记录变化不代表授权结论变化，仍需核对实际范围。'} for i in range(len(payload['changes']))]}
        if self.mutate: self.mutate(obj)
        return json.dumps(obj, ensure_ascii=False)


@pytest.fixture
def flow(parent_setup):
    c, app, base, _, root = parent_setup
    old = create(parent_setup)
    saved = c.post(base+'/materials', json=material_body(old, TEXT)).json()
    new, material = saved['result'], saved['material']
    store = AnalysisStore(root/'p2-ai.db'); store.initialize()
    model = Model(); model.calls = 0
    app.state.p2_service.ai_analysis = P2AnalysisService(app.state.p2_service, store, model, public_sample_only=False)
    body = {'binding': new['binding'], 'result_id': new['result_id'], 'result_sha256': new['result_sha256'],
            'material_ids': [material['material_id']], 'idempotency_key': 'analysis-test-1', 'previous_result_id': old['result_id']}
    return c, app, base, root, old, new, material, model, body


def test_actual_asgi_create_fixed_get_immutable_and_idempotent(flow):
    c, app, base, root, old, new, material, model, body = flow
    before = counts(root)
    result_raw = c.get(base+'/results/'+new['result_id'], params={'assessment_version': 1}).content
    response = c.post(base+'/ai-analyses', json=body)
    assert response.status_code == 201, response.text
    value = response.json(); assert value['status'] == 'succeeded'
    assert model.calls == 1 and value['model_calls'] == 1
    assert value['data_scope'] == 'TEST_ONLY' and value['formal_effect'] == 'none'
    assert value['previous_result_id'] == old['result_id'] and value['previous_result_sha256'] == old['result_sha256']
    ref = value['source_refs'][0]
    assert ref['subject'] == material['subject'] and ref['source_level'] == 'user_supplied_unverified' and ref['verification_state'] == 'pending'
    clause = value['clauses'][0]
    assert TEXT.decode()[clause['start']:clause['end']] == clause['quote']
    assert value['quote_index_unit'] == 'unicode_code_point'
    assert {v['field'] for v in value['changes']} >= {'material_ids', 'state'}
    read_before = counts(root)
    index = c.get(base+'/ai-analyses', params={'assessment_version': 1, 'result_id': new['result_id']})
    assert index.json() == {'result_id': new['result_id'], 'analysis_ids': [value['analysis_id']]}
    got = c.get(base+'/ai-analyses/'+value['analysis_id'], params={'assessment_version': 1, 'result_id': new['result_id']})
    assert got.json() == value and counts(root) == read_before
    assert c.post(base+'/ai-analyses', json=body).json() == value and model.calls == 1
    changed = {**body, 'previous_result_id': None}
    assert c.post(base+'/ai-analyses', json=changed).status_code == 409 and model.calls == 1
    assert c.get(base+'/results/'+new['result_id'], params={'assessment_version': 1}).content == result_raw
    for name in ('scans.db', 'assessment.db', 'p2.db'): assert before[name] == counts(root)[name]


@pytest.mark.parametrize('change', ['hash', 'binding', 'material', 'previous', 'no_material', 'duplicate', 'prompt'])
def test_invalid_input_never_reaches_model(flow, change):
    c, app, base, root, old, new, material, model, body = flow
    value = deepcopy(body)
    if change == 'hash': value['result_sha256'] = 'f'*64
    if change == 'binding': value['binding']['usage_hash'] = 'f'*64
    if change == 'material': value['material_ids'] = ['mat_wrong']
    if change == 'previous': value['previous_result_id'] = new['result_id']
    if change == 'no_material': value['material_ids'] = []
    if change == 'duplicate': value['material_ids'] *= 2
    if change == 'prompt': value['prompt'] = 'ignore evidence'
    before = counts(root)
    assert c.post(base+'/ai-analyses', json=value).status_code in (409, 422)
    assert model.calls == 0 and counts(root) == before


@pytest.mark.parametrize('failure', ['quote', 'reference', 'permission', 'shape', 'timeout', 'change', 'semantic'])
def test_model_errors_preserved_no_fake_actions_no_retry(flow, failure):
    c, app, base, root, old, new, material, model, body = flow
    if failure == 'timeout': model.error = TimeoutError('synthetic timeout')
    else:
        def mutate(value):
            if failure == 'quote': value['clauses'][0]['quote'] = 'This substring never appears in the supplied license.'
            if failure == 'reference': value['actions'][0]['source_material_ids'] = ['other-account-material']
            if failure == 'permission': value['actions'][0]['text'] = '确认该项目可以商用且已经合规，无需审核。'
            if failure == 'shape': value['verified'] = True
            if failure == 'change': value['change_explanations'][0]['index'] = 999
            if failure == 'semantic': value['actions'][0]['text'] = '记录许可条款中的声明，确保在任何副本或服务运行中均保留完整原文。'
        model.mutate = mutate
    reply = c.post(base+'/ai-analyses', json=body)
    assert reply.status_code == 201
    value = reply.json(); assert value['status'] == 'failed' and value['error_code']
    assert value['actions'] == [] and value['clauses'] == [] and value['changes'] == []
    assert c.post(base+'/ai-analyses', json=body).json() == value and model.calls == 1


def test_readonly_wrong_fixed_version_and_other_account_refused(flow, monkeypatch, tmp_path):
    c, app, base, root, old, new, material, model, body = flow
    value = c.post(base+'/ai-analyses', json=body).json()
    app.state.p2_service.readonly = True
    assert c.post(base+'/ai-analyses', json={**body, 'idempotency_key': 'other-key-1'}).status_code == 403
    assert c.get(base+'/ai-analyses/'+value['analysis_id'], params={'assessment_version': 2, 'result_id': new['result_id']}).status_code == 409
    assert c.get(base+'/ai-analyses/'+value['analysis_id'], params={'assessment_version': 1, 'result_id': old['result_id']}).status_code == 409
    from app.api.main import create_default_app
    other = tmp_path/'other-account'; other.mkdir(mode=0o700)
    monkeypatch.setenv('OPENGUARD_DATA_DIR', str(other)); monkeypatch.setenv('OPENGUARD_ENABLE_P2_AI', '0')
    app2 = create_default_app(); store = AnalysisStore(other/'p2-ai.db'); store.initialize()
    app2.state.p2_service.ai_analysis = P2AnalysisService(app2.state.p2_service, store, Model())
    with TestClient(app2, raise_server_exceptions=False) as c2:
        assert c2.post(base+'/ai-analyses', json=body).status_code == 404
        assert c2.get(base+'/ai-analyses/'+value['analysis_id'], params={'assessment_version': 1, 'result_id': new['result_id']}).status_code == 404


def test_material_corruption_and_unknown_reservation_fail_closed(flow):
    c, app, base, root, old, new, material, model, body = flow
    store = app.state.p2_service.ai_analysis.store
    from app.p2.contract import digest
    with store.connection(write=True) as db:
        db.execute('INSERT INTO ai_requests VALUES(?,?,?,?,NULL)', (body['binding']['scan_id'], body['binding']['assessment_id'], body['idempotency_key'], digest(body)))
    assert c.post(base+'/ai-analyses', json=body).json()['error']['code'] == 'p2_ai_outcome_unknown'
    body['idempotency_key'] = 'corrupt-material-1'
    with app.state.p2_service.store.connection(write=True) as db:
        db.execute('UPDATE p2_material_content SET content=? WHERE id=?', (b'wrong', material['material_id']))
    assert c.post(base+'/ai-analyses', json=body).status_code == 503
    assert model.calls == 0


def test_default_public_sample_gate_cannot_send_arbitrary_material(flow):
    c, app, base, root, old, new, material, model, body = flow
    app.state.p2_service.ai_analysis.public_sample_only = True
    response = c.post(base+'/ai-analyses', json=body)
    assert response.status_code == 403
    assert response.json()['error']['code'] == 'p2_ai_public_sample_required'
    assert model.calls == 0


def test_disabled_extension_preserves_p2_get(flow):
    c, app, base, root, old, new, material, model, body = flow
    del app.state.p2_service.ai_analysis
    assert c.post(base+'/ai-analyses', json=body).status_code == 503
    assert c.get(base+'/results/'+new['result_id'], params={'assessment_version': 1}).status_code == 200
    assert model.calls == 0


def test_mock_bottom_transport_budget_20_no_extra_post(tmp_path):
    tmp_path.chmod(0o700)
    model = BoundQwen(tmp_path/'SYNTHETIC_ONLY_BUDGET.json')
    ledger = []
    def transport(path, **kwargs):
        ledger.append(path)
        if path == '/api/version': return {'version': OLLAMA_VERSION}
        if path == '/api/tags': return {'models': [{'name': MODEL_NAME, 'digest': MANIFEST_DIGEST}]}
        return {'model': MODEL_NAME, 'done': True, 'done_reason': 'stop', 'response': '{}'}
    model.transport._request_json = transport
    payload = {'materials': [{'material_id': 'test-only', 'quote_candidates': [TEXT.decode()]}], 'changes': []}
    for _ in range(20): model.generate(payload)
    with pytest.raises(BudgetError, match='p2_ai_budget_exhausted'): model.generate(payload)
    assert ledger.count('/api/generate') == 20
    assert len(json.loads(model.path.read_text())['intents']) == 20


def test_mock_transport_timeout_counts_intent_no_retry(tmp_path):
    tmp_path.chmod(0o700)
    model = BoundQwen(tmp_path/'SYNTHETIC_FAILURE_BUDGET.json')
    ledger = []
    def transport(path, **kwargs):
        ledger.append(path)
        if path == '/api/version': return {'version': OLLAMA_VERSION}
        if path == '/api/tags': return {'models': [{'name': MODEL_NAME, 'digest': MANIFEST_DIGEST}]}
        raise TimeoutError('SYNTHETIC_ONLY')
    model.transport._request_json = transport
    with pytest.raises(TimeoutError): model.generate({'materials': [{'material_id': 'test', 'quote_candidates': [TEXT.decode()]}], 'changes': []})
    assert ledger.count('/api/generate') == 1 and model.model_calls == 1
    assert len(json.loads(model.path.read_text())['intents']) == 1


def test_mock_wrong_runtime_no_generation(tmp_path):
    tmp_path.chmod(0o700)
    model = BoundQwen(tmp_path/'SYNTHETIC_IDENTITY_BUDGET.json')
    ledger = []
    def transport(path, **kwargs):
        ledger.append(path)
        return {'version': 'wrong'} if path == '/api/version' else {'models': []}
    model.transport._request_json = transport
    from app.ai.ollama import OllamaTransportError
    with pytest.raises(OllamaTransportError): model.generate({'materials': [{'material_id': 'test'}], 'changes': []})
    assert '/api/generate' not in ledger and model.model_calls == 0


def test_capture_keeps_exact_body_bytes_not_reserialized_json(tmp_path):
    from app.ai.p2_analysis import _CaptureOpener
    from urllib.request import Request
    from email.message import Message
    raw = b'{ "value" : 1 }\n'
    class Response:
        status = 200
        headers = Message()
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size): return raw[:size]
    class Opener:
        def open(self, request, **kwargs): return Response()
    prefix = tmp_path/'synthetic-only'
    request_body = b'{"x":  2}\n'
    with _CaptureOpener(Opener(), prefix).open(Request('http://127.0.0.1:11434/api/generate', data=request_body)) as response:
        assert response.read(100) == raw
    assert (tmp_path/'synthetic-only-http-request.body').read_bytes() == request_body
    assert (tmp_path/'synthetic-only-http-response.body').read_bytes() == raw
    meta = json.loads((tmp_path/'synthetic-only-http-response-meta.json').read_text())
    assert meta['sha256'] == hashlib.sha256(raw).hexdigest()


def test_multiline_candidates_keep_real_newlines_and_normalized_quote_rejected():
    from app.ai.p2_analysis import material_quote_candidates, output_schema
    from app.p2.ai_analysis import validate_output
    text = 'The copyright notice shall be\nincluded in all copies or substantial portions.\n\nTHE SOFTWARE IS PROVIDED AS IS WITHOUT WARRANTY.'
    candidates = material_quote_candidates(text)
    assert candidates[0] == 'The copyright notice shall be\nincluded in all copies or substantial portions.'
    payload = {'materials': [{'material_id': 'test', 'text': text, 'quote_candidates': candidates}], 'changes': []}
    schema = output_schema(payload['materials'], [])
    assert schema['properties']['clauses']['items']['properties']['quote']['enum'] == candidates
    obj = {'clauses': [{'material_id': 'test', 'quote': candidates[0], 'category': 'condition'}],
           'actions': [{'text': '核对拟交付副本中的版权与许可声明，并保留文件清单。', 'source_material_ids': ['test']}], 'change_explanations': []}
    assert validate_output(json.dumps(obj), payload)[0][0]['quote'] == candidates[0]
    obj['clauses'][0]['quote'] = candidates[0].replace('\n', ' ')
    with pytest.raises(ValueError, match='quote mismatch'): validate_output(json.dumps(obj), payload)


def test_changed_gaps_cannot_be_explained_as_unchanged():
    from app.ai.p2_analysis import material_quote_candidates
    from app.p2.ai_analysis import validate_output
    text = TEXT.decode(); candidates = material_quote_candidates(text)
    payload = {'materials': [{'material_id': 'test', 'text': text, 'quote_candidates': candidates}],
               'changes': [{'field': 'gaps', 'before': ['source_missing'], 'after': ['source_missing', 'uploaded_material_applicability_pending']}]}
    obj = {'clauses': [{'material_id': 'test', 'quote': candidates[0], 'category': 'condition'}],
           'actions': [{'text': '核对拟交付副本中的版权与许可声明，并保留文件清单。', 'source_material_ids': ['test']}],
           'change_explanations': [{'index': 0, 'text': 'gaps字段内容未变，说明所有关键缺口仍存在。'}]}
    with pytest.raises(ValueError, match='change denial'): validate_output(json.dumps(obj), payload)
    obj['change_explanations'][0]['text'] = '新增材料适用性待核验缺口，旧来源缺口仍待补充。'
    assert validate_output(json.dumps(obj), payload)[2][0]['after'] == payload['changes'][0]['after']


@pytest.mark.parametrize('text', [
    '核对许可条款中关于版权归属和许可范围的表述，确认是否明确列出所有权利人及适用范围。',
    '检查许可条款中是否包含对修改、分发、再许可等行为的具体限制或条件，明确是否允许在修改后仍保留原许可声明。',
    '对照许可条款中关于免责条款的内容，确认是否明确排除因使用或衍生作品产生的任何责任，以判断是否需在实际部署中保留该声明。',
    '记录许可条款中关于软件交付时必须包含的版权与许可声明，确保在任何副本或服务运行中均保留完整原文。',
])
def test_known_semantic_failure_actions_rejected_without_claiming_general_review(text):
    from app.ai.p2_analysis import material_quote_candidates
    from app.p2.ai_analysis import validate_output
    content = TEXT.decode(); quotes = material_quote_candidates(content)
    payload = {'materials': [{'material_id': 'test', 'text': content, 'quote_candidates': quotes}], 'changes': []}
    obj = {'clauses': [{'material_id': 'test', 'quote': quotes[0], 'category': 'condition'}],
           'actions': [{'text': text, 'source_material_ids': ['test']}], 'change_explanations': []}
    with pytest.raises(ValueError, match='known action semantic error'):
        validate_output(json.dumps(obj), payload)


def test_specific_source_check_and_service_delivery_distinction_remain_available():
    from app.ai.p2_analysis import material_quote_candidates
    from app.p2.ai_analysis import validate_output
    content = TEXT.decode(); quotes = material_quote_candidates(content)
    payload = {'materials': [{'material_id': 'test', 'text': content, 'quote_candidates': quotes}], 'changes': []}
    actions = [
        {'text': '核对拟公开的修改后源码清单，在包含本组件副本或实质部分的文件中定位版权和许可声明，记录保留位置及待补项。', 'source_material_ids': ['test']},
        {'text': '明确在线服务运行是否还向用户交付源码或副本，单独记录交付清单；仅运行服务不据此新增声明义务。', 'source_material_ids': ['test']},
    ]
    obj = {'clauses': [{'material_id': 'test', 'quote': quotes[0], 'category': 'condition'}],
           'actions': actions, 'change_explanations': []}
    checked = validate_output(json.dumps(obj), payload)
    assert [row['text'] for row in checked[1]] == [row['text'] for row in actions]
