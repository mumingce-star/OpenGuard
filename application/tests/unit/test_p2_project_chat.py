"""Actual ASGI, private stores and budget; only Ollama HTTP is fake."""
from copy import deepcopy
import fcntl
import hashlib
import json
import os

import pytest

from app.ai.ollama import MODEL_NAME, MANIFEST_DIGEST, OLLAMA_VERSION
from app.ai.project_chat import BoundProjectQwen, ChatBudget
from app.p2.contract import P2Error, canonical
from app.p2.project_chat import ChatRequest, select_scan_evidence, validate_answer, usage_fact
from test_p2_contract import setup as parent_setup, create, material_body, counts

TEXT = b'MIT License\n\nPermission is hereby granted to use this synthetic test fixture.\n\nThe copyright notice shall be preserved in copies of this fixture.'


def valid_reply(payload):
    return {'result_id': payload['scope']['result_id'], 'result_sha256': payload['scope']['result_sha256'],
            'usage_echo': payload['usage'],
            'answer': '当前材料与具体交付文件的适用范围仍需核验，请先记录本组件的文件清单，再核对版权和许可声明保留位置；其他依赖需要分别补齐对应依据。',
            'citations': [{'basis_id': payload['evidence'][0]['basis_id'], 'quote': payload['evidence'][0]['quote']}]}


class FakeTransport:
    def __init__(self):
        self.calls = []; self.payloads = []; self.change = None; self.error = None

    def _now(self): return 100.0

    def _request_json(self, path, *, deadline, limit, body=None):
        assert deadline == 220.0
        self.calls.append(path)
        if self.error: raise self.error
        if path == '/api/version': return {'version': OLLAMA_VERSION}
        if path == '/api/tags': return {'models': [{'name': MODEL_NAME, 'digest': MANIFEST_DIGEST}]}
        assert path == '/api/generate' and body['stream'] is False
        payload = json.loads(body['prompt']); self.payloads.append(payload)
        value = valid_reply(payload)
        if self.change: self.change(value)
        return {'model': MODEL_NAME, 'done': True, 'done_reason': 'stop', 'response': json.dumps(value, ensure_ascii=False)}


@pytest.fixture
def flow(parent_setup):
    client, app, base, _, root = parent_setup
    first = create(parent_setup)
    response = client.post(base+'/materials', json=material_body(first, TEXT))
    assert response.status_code == 201, response.text
    result = response.json()['result']
    budget = ChatBudget(root/'chat-budget.json')
    provider = BoundProjectQwen(budget); fake = FakeTransport(); provider.transport = fake
    service = app.state.p2_service.project_chat
    service.provider, service.budget = provider, budget
    body = {'binding': result['binding'], 'result_id': result['result_id'], 'result_sha256': result['result_sha256'],
            'question': '现在需要核对哪些文件和声明？', 'request_id': 'chat-question-001'}
    query = {'result_id': result['result_id'], 'assessment_version': result['binding']['assessment_version']}
    return client, app, base+'/project-chat', root, result, first, body, query, fake, budget


def test_get_is_read_only_and_returns_exact_scope(flow):
    c, app, url, root, result, _, body, query, fake, budget = flow
    before = counts(root)
    response = c.get(url, params=query)
    assert response.status_code == 200, response.text
    value = response.json()
    assert value['items'] == [] and value['context']['usage'] == result['usage']
    assert value['scope']['result_sha256'] == result['result_sha256']
    assert value['scope']['binding'] == result['binding']
    assert value['limits']['used_model_calls'] == 0
    assert not budget.path.exists() and not fake.calls and counts(root) == before


def test_real_route_persists_multiturn_quotes_and_never_changes_business(flow):
    c, app, url, root, result, _, body, query, fake, budget = flow
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.db') if p.name != 'p2-project-chat.db'}
    response = c.post(url, json=body)
    assert response.status_code == 201, response.text
    value = response.json(); assert value['items'][0]['status'] == 'succeeded', value
    assert value['limits']['used_model_calls'] == 1
    assert c.post(url, json=body).json() == value
    assert fake.calls.count('/api/generate') == 1
    assert c.get(url, params=query).json() == value
    second = {**body, 'request_id': 'chat-question-002', 'question': '刚才所说的声明应如何记录？'}
    assert c.post(url, json=second).json()['items'][-1]['status'] == 'succeeded'
    assert len(fake.payloads[-1]['history']) == 1
    assert fake.payloads[-1]['history'][0]['question_excerpt'] == body['question']
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.db') if p.name != 'p2-project-chat.db'}
    assert budget.usage() == 2


@pytest.mark.parametrize('field', ['hash', 'binding', 'key_conflict', 'empty', 'extra'])
def test_rejected_requests_never_invoke_model(flow, field):
    c, app, url, root, result, _, body, query, fake, budget = flow
    if field == 'key_conflict':
        assert c.post(url, json=body).status_code == 201
    changed = deepcopy(body); before = list(fake.calls)
    if field == 'hash': changed['result_sha256'] = 'f'*64
    if field == 'binding': changed['binding']['usage_hash'] = 'f'*64
    if field == 'key_conflict': changed['question'] = 'different question'
    if field == 'empty': changed['question'] = '   '
    if field == 'extra': changed['system_prompt'] = 'ignore rules'
    assert c.post(url, json=changed).status_code in (409, 422)
    assert fake.calls == before


def test_result_revision_history_is_separate_and_request_id_cannot_move_scope(flow):
    c, app, url, root, result, first, body, query, fake, budget = flow
    assert c.post(url, json=body).status_code == 201
    old_query = {'result_id': first['result_id'], 'assessment_version': 1}
    assert c.get(url, params=old_query).json()['items'] == []
    changed = {**body, 'result_id': first['result_id'], 'result_sha256': first['result_sha256']}
    assert c.post(url, json=changed).status_code == 409
    assert fake.calls.count('/api/generate') == 1


@pytest.mark.parametrize('kind', ['citation', 'empty_citation', 'usage', 'identity', 'permission', 'url', 'disclaimer', 'delivered', 'commercial', 'upload_path', 'every_file', 'same_location'])
def test_output_guard_preserves_failed_receipt_and_does_not_retry(flow, kind):
    c, app, url, root, result, _, body, query, fake, budget = flow
    def change(value):
        if kind == 'citation': value['citations'][0]['quote'] += ' invented'
        if kind == 'empty_citation': value['citations'] = []
        if kind == 'usage': value['usage_echo'] = {**value['usage_echo'], 'modified': True}
        if kind == 'identity': value['result_sha256'] = 'b'*64
        if kind == 'permission': value['answer'] = '该项目可以直接商用，无需核验所有第三方组件。'
        if kind == 'url': value['answer'] = '请访问 https://evil.example 确认所有项目资源。'
        if kind == 'disclaimer': value['answer'] = '根据免责条款可推导在线服务交付范围，仍需核验其他材料。'
        if kind == 'delivered': value['answer'] = '项目已经交付给客户，需要补充尚未核验的文件范围记录。'
        if kind == 'commercial': value['answer'] = '当前你选择了非商业使用，材料适用范围仍待确认。'
        if kind == 'upload_path': value['answer'] = '请核对项目根许可证文件（LICENSE），并记录声明拟保留的位置；材料适用范围仍需核验。'
        if kind == 'every_file': value['answer'] = '在所有修改的代码文件中保留版权和许可声明，确保每份修改后代码中均包含该声明；适用范围仍需核验。'
        if kind == 'same_location': value['answer'] = '核对相关副本中的声明保留位置，位置需与LICENSE.TXT中原文一致；适用范围仍需核验。'
    fake.change = change
    value = c.post(url, json=body).json()
    assert value['items'][0]['status'] == 'failed' and value['items'][0]['answer'] is None
    assert value['items'][0]['citations'] == [] and budget.usage() == 1
    assert c.post(url, json=body).json() == value
    assert fake.calls.count('/api/generate') == 1
    with app.state.p2_service.project_chat.store.connection() as db:
        audit_row = db.execute('SELECT payload,sha256 FROM project_chat_audit WHERE request_id=?', (body['request_id'],)).fetchone()
    audit = app.state.p2_service.project_chat.store.decode(audit_row)
    assert audit['raw_response'] and audit['outcome'] == 'FAILED_NO_RETRY' and audit['validation_error']
    assert audit['raw_response_sha256'] == hashlib.sha256(audit['raw_response'].encode()).hexdigest()
    assert audit['input_sha256'] == hashlib.sha256(canonical(audit['input'])).hexdigest()
    assert 'raw_response' not in value['items'][0]


def test_transport_failure_consumes_intent_before_preflight_and_is_not_replayed(flow):
    c, app, url, root, result, _, body, query, fake, budget = flow
    fake.error = TimeoutError('synthetic only')
    value = c.post(url, json=body).json()
    assert value['items'][0]['status'] == 'failed' and budget.usage() == 1
    assert fake.calls == ['/api/version']
    c.post(url, json=body); c.get(url, params=query)
    assert fake.calls == ['/api/version']


def test_shared_independent_ledger_exhausts_at_eight(flow):
    c, app, url, root, result, _, body, query, fake, budget = flow
    legacy = root/'legacy-qwen-budget.json'; legacy.write_bytes(b'unchanged legacy ledger')
    other_account_budget = ChatBudget(budget.path)
    for index in range(8):
        value = c.post(url, json={**body, 'request_id': 'chat-budget-' + str(index)}).json()
        assert value['items'][-1]['status'] == 'succeeded', value
        assert other_account_budget.usage() == index + 1
    value = c.post(url, json={**body, 'request_id': 'chat-budget-nine'}).json()
    assert value['items'][-1]['error_code'] == 'p2_chat_budget_exhausted'
    assert value['limits']['remaining_model_calls'] == 0 and fake.calls.count('/api/generate') == 8
    assert legacy.read_bytes() == b'unchanged legacy ledger'


def test_shared_flock_prevents_other_process_intent(flow):
    c, app, url, root, result, _, body, query, fake, budget = flow
    fd = os.open(str(budget.path)+'.lock', os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        value = c.post(url, json=body).json()
        assert value['items'][0]['error_code'] == 'p2_chat_busy'
        assert budget.usage() == 0 and fake.calls == []
    finally: os.close(fd)


def test_missing_provider_only_blocks_new_send_not_history(flow):
    c, app, url, root, result, _, body, query, fake, budget = flow
    saved = c.post(url, json=body).json()
    app.state.p2_service.project_chat.provider = None
    assert c.post(url, json=body).json() == saved
    assert c.get(url, params=query).json() == saved
    assert c.post(url, json={**body, 'request_id': 'chat-disabled-new'}).status_code == 503


def test_invalid_or_symlink_ledger_never_calls_transport(flow):
    c, app, url, root, result, _, body, query, fake, budget = flow
    target = root/'private-other.txt'; target.write_text('do not overwrite'); target.chmod(0o600)
    budget.path.symlink_to(target)
    assert c.post(url, json=body).status_code == 503
    assert target.read_text() == 'do not overwrite' and fake.calls == []


def test_material_tampering_is_rejected_before_model(flow):
    c, app, url, root, result, _, body, query, fake, budget = flow
    with app.state.p2_service.store.connection(write=True) as db:
        db.execute('UPDATE p2_material_content SET content=?', (b'tampered',))
    assert c.post(url, json=body).status_code in (409, 503)
    assert fake.calls == [] and budget.usage() == 0


def test_saved_advice_and_source_bindings_are_exact_in_prompt(flow):
    c, app, url, root, result, _, body, query, fake, budget = flow
    assert c.post(url, json=body).json()['items'][0]['status'] == 'succeeded'
    payload = fake.payloads[0]
    for row, saved in zip(payload['resources'], result['resources']):
        assert [payload['saved_advice_catalog'][key] for key in row['saved_advice_refs']] == saved['advice']
    material = next(row for row in payload['evidence'] if row['kind'] == 'material')
    assert material['source_level'] == 'user_supplied_unverified' and material['verification_state'] == 'pending'
    assert material['subject']['resource_id'] in material['resource_ids'] and len(material['source_sha256']) == 64
    assert material['uploaded_filename'] == 'LICENSE' and material['upstream_path'] is None
    assert '上传名' in material['label']


def test_p2_business_readonly_still_allows_isolated_chat(flow):
    c, app, url, root, result, _, body, query, fake, budget = flow
    app.state.p2_service.readonly = True
    before = counts(root)
    assert c.post(url, json=body).json()['items'][0]['status'] == 'succeeded'
    after = counts(root)
    assert all(after[name] == before[name] for name in before if name != 'p2-project-chat.db')


def test_full_2000_character_question_is_not_truncated_in_model_payload(flow):
    c, app, url, root, result, _, body, query, fake, budget = flow
    question = '问' * 2000
    value = c.post(url, json={**body, 'question': question}).json()
    assert value['items'][0]['status'] == 'succeeded'
    assert fake.payloads[0]['question'] == question


def test_copy_scope_action_does_not_impose_each_file_or_identical_location(flow):
    c, app, url, root, result, _, body, query, fake, budget = flow
    answer = '材料未指定具体文件或位置。核对修改文件中哪些实际包含本组件的副本或实质部分，在相关范围保留完整版权和许可声明，并记录拟保留位置；适用范围仍需核验。'
    fake.change = lambda value: value.update(answer=answer)
    value = c.post(url, json=body).json()
    assert value['items'][-1]['status'] == 'succeeded' and value['items'][-1]['answer'] == answer


def test_usage_fact_is_exact_deterministic_saved_result_projection(flow):
    c, app, url, root, result, _, body, query, fake, budget = flow
    before = counts(root)
    view = c.get(url, params=query).json()
    fact = next(row for row in view['context']['evidence'] if row['kind'] == 'result_fact')
    assert fact == usage_fact(result)
    assert fact['basis_id'] == 'result:' + result['result_sha256'] + ':usage'
    assert fact['resource_ids'] == [] and fact['verification_state'] == 'saved_declaration'
    assert fact['quote'] == ('涉及商业使用：是\n修改项目代码：否\n向他人分发／交付：是\n对外提供在线服务：未知\n'
                             '用于模型训练：否\n再分发模型／数据等资源：否\n计划公开源代码：否\n'
                             '以上为本版保存的演示用途声明，不证明实际行为已经发生或完成。')
    assert counts(root) == before and not fake.calls


@pytest.mark.parametrize('unsupported_clause', [True, False])
def test_no_license_body_cannot_imply_terms_but_usage_is_not_completed_behavior(flow, unsupported_clause):
    c, app, url, root, result, _, body, query, fake, budget = flow
    fact = usage_fact(result)
    payload = {'scope': {'result_id': result['result_id'], 'result_sha256': result['result_sha256']},
               'usage': result['usage'], 'evidence': [fact, {'basis_id': 'manifest-license', 'kind': 'scan_evidence',
                   'label': 'license_expression', 'resource_ids': [result['resources'][0]['subject']['resource_id']],
                   'quote': '"MIT"', 'verification_state': 'pending'}]}
    guard = {'assessment_id': body['binding']['assessment_id'], 'state_digest': 'a'*64,
             'formal_state': {'dimensions': [{'id': 'commercial', 'status': 'unknown'}]}, 'selected_resources': []}
    answer = ('选择分发不等于已交付代码，因为许可未明确要求交付源码，仍需核验实际行为。' if unsupported_clause else
              '本版声明商业使用和向他人分发，这些是演示用途选择。选择分发不等于已交付代码；实际交付的内容和时间仍需核验。')
    response = {'result_id': result['result_id'], 'result_sha256': result['result_sha256'], 'usage_echo': result['usage'],
                'answer': answer, 'citations': [{'basis_id': fact['basis_id'], 'quote': fact['quote']}]}
    if unsupported_clause:
        with pytest.raises(ValueError, match='p2_chat_license_body_required'):
            validate_answer(json.dumps(response, ensure_ascii=False), payload, guard)
    else:
        assert validate_answer(json.dumps(response, ensure_ascii=False), payload, guard)['answer'] == answer


def test_basis_selection_prioritizes_material_then_project_without_mutating_sources():
    from types import SimpleNamespace as N
    def evidence(identity, text, kind='metadata'):
        return N(id=identity, excerpt=text, kind=N(value=kind))
    items = [evidence('evd_000', '"4.21.1"'), evidence('evd_aaa', 'This related dependency has a descriptive source observation that remains unverified.'),
             evidence('evd_zzz', 'Project root copyright and license observation.', 'license_text'),
             evidence('evd_yyy', 'Material-bound component source observation.'),
             evidence('evd_orphan', 'This source has no relationship to any saved Result resource.'),
             evidence('evd_url', '"https://registry.example/other-package/-/other-package-1.2.3.tgz"')]
    resources = {'material': N(name='bound-component'), 'root': N(name='Project-Name'), 'other': N(name='other')}
    rows = [{'subject': {'resource_id': 'material'}, 'evidence_ids': ['evd_yyy']},
            {'subject': {'resource_id': 'root'}, 'evidence_ids': ['evd_zzz']},
            {'subject': {'resource_id': 'other'}, 'evidence_ids': ['evd_000', 'evd_aaa', 'evd_url']}]
    before = deepcopy((items, resources, rows))
    selected = select_scan_evidence(items, rows, resources, 'project-name', {'material'})
    assert [item.id for item, _ in selected] == ['evd_yyy', 'evd_zzz', 'evd_aaa']
    assert (items, resources, rows) == before
    assert selected[0][0] is items[3] and selected[0][0].excerpt == items[3].excerpt


def test_historical_basis_survives_new_selection_but_is_not_fed_back_to_model(flow, monkeypatch):
    import app.p2.project_chat as module
    c, app, url, root, result, _, body, query, fake, budget = flow
    service = app.state.p2_service.project_chat
    scope, context, run, *_ = service._context(body['binding']['scan_id'], body['binding']['assessment_id'], body['result_id'], 1)
    existing = next(item for item in context['evidence'] if item['kind'] == 'scan_evidence')
    assert service.store.reserve(scope, ChatRequest.model_validate(body))
    service.store.finish(scope, body['request_id'], result={'answer': '已有历史答复保持原文，具体用途仍需核验。',
        'citations': [{'basis_id': existing['basis_id'], 'quote': existing['quote']}]})
    saved = deepcopy(service.store.history(scope))
    monkeypatch.setattr(module, 'select_scan_evidence', lambda *args: [])
    view = c.get(url, params=query).json()
    assert view['items'] == saved
    assert next(item for item in view['context']['evidence'] if item['basis_id'] == existing['basis_id'])['quote'] == existing['quote']
    assert c.post(url, json={**body, 'request_id': 'after-selection-repair'}).json()['items'][-1]['status'] == 'succeeded'
    assert existing['basis_id'] not in {item['basis_id'] for item in fake.payloads[-1]['evidence']}
    assert fake.payloads[-1]['history'][0]['answer_excerpt'] == saved[0]['answer'][:300]
    assert service.store.history(scope)[0] == saved[0]


def test_history_revalidation_keeps_question_omits_unsafe_answer_and_preserves_raw(flow):
    c, app, url, root, result, _, body, query, fake, budget = flow
    service = app.state.p2_service.project_chat
    scope, context, *_ = service._context(body['binding']['scan_id'], body['binding']['assessment_id'], body['result_id'], 1)
    source = next(row for row in context['evidence'] if row['kind'] == 'material')
    old_answer = '请核对项目根许可证文件（LICENSE），并记录声明拟保留的位置；材料适用范围仍需核验。'
    old_output = {'answer': old_answer, 'citations': [{'basis_id': source['basis_id'], 'quote': source['quote']}]}
    assert service.store.reserve(scope, ChatRequest.model_validate(body))
    service.store.finish(scope, body['request_id'], result=old_output)
    old_raw = json.dumps(old_output, ensure_ascii=False)
    service.store.audit(scope, body['request_id'], {'raw_response': old_raw, 'origin': 'SYNTHETIC_OLDER_PROTOCOL'})
    old_saved = deepcopy(service.store.history(scope)[0])
    next_body = {**body, 'request_id': 'history-safe-followup', 'question': '刚才提到的材料应怎样核对？'}
    response = c.post(url, json=next_body)
    assert response.status_code == 201, response.text
    assert response.json()['items'][-1]['status'] == 'succeeded'
    history = fake.payloads[-1]['history']
    assert len(history) == 1 and history[0]['question_excerpt'] == body['question'][:160]
    assert history[0]['answer_omitted'] is True and '不能作为事实' in history[0]['history_note']
    assert 'answer_excerpt' not in history[0] and old_answer not in canonical(fake.payloads[-1]).decode()
    assert c.get(url, params=query).json()['items'][0] == old_saved
    with service.store.connection() as db:
        old_audit = service.store.decode(db.execute('SELECT payload,sha256 FROM project_chat_audit WHERE request_id=?', (body['request_id'],)).fetchone())
        new_audit = service.store.decode(db.execute('SELECT payload,sha256 FROM project_chat_audit WHERE request_id=?', (next_body['request_id'],)).fetchone())
    assert old_audit['raw_response'] == old_raw
    assert json.loads(new_audit['raw_response'])['answer'] == response.json()['items'][-1]['answer']
    assert new_audit['input']['history'] == history


def test_restart_recovers_only_unlocked_pending_without_model_replay(flow):
    c, app, url, root, result, _, body, query, fake, budget = flow
    store = app.state.p2_service.project_chat.store
    scope = c.get(url, params=query).json()['scope']
    with store.operation(body['request_id']):
        assert store.reserve(scope, ChatRequest.model_validate(body))
        store.initialize()
        assert store.history(scope)[0]['status'] == 'pending'
    store.initialize()
    value = c.get(url, params=query).json()
    assert value['items'][0]['status'] == 'failed'
    assert value['items'][0]['error_code'] == 'p2_chat_interrupted_outcome_unknown'
    assert c.post(url, json=body).json() == value and not fake.calls
    next_body = {**body, 'request_id': 'after-interruption'}
    assert c.post(url, json=next_body).json()['items'][-1]['status'] == 'succeeded'


def test_account_gateway_exact_chat_write_csrf_and_cross_account_read_isolation(flow, monkeypatch):
    from app.api.main import create_default_app
    from app.local_accounts import LocalAccountGateway
    from app.p2.contract import CreateRequest
    from starlette.responses import JSONResponse
    from starlette.testclient import TestClient
    from test_p2_contract import seed
    c, parent, url, root, result, _, body, query, fake, budget = flow
    origin = 'http://127.0.0.1:48124'
    monkeypatch.setenv('OPENGUARD_WEB_ORIGINS', origin)
    run, assessment, *_ = parent.state.p2_service.context(body['binding']['scan_id'], body['binding']['assessment_id'])
    saved = []
    def factory(data_root):
        app = create_default_app(data_dir=data_root)
        if not saved:
            a = seed(app, run, assessment.usage)
            binding = app.state.p2_service.context(a.scan_id, a.id)[2]
            r = app.state.p2_service.write(a.scan_id, a.id, CreateRequest(binding=binding, expected_revision=0,
                parent_result_id=None, idempotency_key='account-chat-seed'), 'create')['result']
            saved.append(r)
        service = app.state.p2_service.project_chat
        provider = BoundProjectQwen(budget); provider.transport = fake
        service.provider, service.budget = provider, budget
        return app
    async def frontend(scope, receive, send):
        await JSONResponse({'synthetic': True})(scope, receive, send)
    gateway = LocalAccountGateway(root=root/'accounts', origins=(origin,), cookie_name='og_session_0123456789ab',
                                  app_factory=factory, frontend=frontend)
    def register(client, name):
        token = client.get('/api/v1/auth/session').json()['csrf_token']
        reply = client.post('/api/v1/auth/register', headers={'Origin': origin, 'X-CSRF-Token': token},
                            json={'username': name, 'password': 'SyntheticChat2026!'})
        if reply.status_code != 201: raise AssertionError('synthetic registration failed')
        return reply.json()['csrf_token']
    with TestClient(gateway, base_url=origin) as client:
        token = register(client, 'chat_owner_a')
        assert client.get('/api/v1/scans').status_code == 200
        r = saved[0]
        path = f"/api/v1/scans/{r['binding']['scan_id']}/assessments/{r['binding']['assessment_id']}/p2/project-chat"
        request = {'binding': r['binding'], 'result_id': r['result_id'], 'result_sha256': r['result_sha256'],
                   'question': '当前哪些事项仍需核验？', 'request_id': 'gateway-chat-test'}
        assert client.post(path, json=request, headers={'Origin': origin}).status_code == 403
        assert client.post(path, json=request, headers={'Origin': 'https://invalid.example', 'X-CSRF-Token': token}).status_code == 403
        response = client.post(path, json=request, headers={'Origin': origin, 'X-CSRF-Token': token})
        assert response.status_code == 201, response.text
        assert response.json()['items'][0]['status'] == 'succeeded'
        assert client.post(path+'/anything', json=request, headers={'Origin': origin, 'X-CSRF-Token': token}).status_code == 403
        client.cookies.clear()
        register(client, 'chat_owner_b')
        query = {'assessment_version': r['binding']['assessment_version'], 'result_id': r['result_id']}
        assert client.get(path, params=query).status_code == 404
        assert budget.usage() == 1
