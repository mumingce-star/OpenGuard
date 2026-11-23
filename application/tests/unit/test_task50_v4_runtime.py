"""TASK50 protocol transport coverage. The Ollama transport is a deterministic substitute."""

import json

import pytest

from app.ai.ollama import MANIFEST_DIGEST, MODEL_NAME, OLLAMA_VERSION
from app.ai.p2_analysis import BoundQwen, BudgetError
from app.p2.contract import digest


def request_data():
    context = {
        'protocol': 'openguard-action-plan/3',
        'quote_catalog': [],
        'action_catalog': [{'action_kind': 'SUPPLY_MISSING_LICENSE_MATERIAL',
                            'basis_ids': ['MISSING_LICENSE_MATERIAL'], 'required': True}],
        'incremental_impact_summary': {'mode': 'INITIAL_RESULT', 'changed_claims': []},
    }
    return {'analysis_protocol': 'openguard-qwen-v4-plan/3', 'context': context, 'context_sha256': digest(context)}


def substituted_model(tmp_path):
    tmp_path.chmod(0o700)
    model = BoundQwen(tmp_path / 'budget.json', max_generations=2)
    calls = []
    def request(path, **options):
        calls.append((path, options))
        if path == '/api/version':
            return {'version': OLLAMA_VERSION}
        if path == '/api/tags':
            return {'models': [{'name': MODEL_NAME, 'digest': MANIFEST_DIGEST}]}
        return {'model': MODEL_NAME, 'done': True, 'done_reason': 'stop', 'response': '{}'}
    model.transport._request_json = request
    return model, calls


def test_task50_transport_opt_out_precedes_budget_and_metadata(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENGUARD_P2_AI_V4_PLAN', raising=False)
    model, calls = substituted_model(tmp_path)
    with pytest.raises(BudgetError, match='p2_ai_protocol_disabled'):
        model.generate(request_data())
    assert calls == [] and model.model_calls == 0
    assert not model.path.exists()


def test_task50_transport_uses_v3_schema_and_durable_two_intent_budget(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENGUARD_P2_AI_V4_PLAN', '1')
    monkeypatch.setenv('OPENGUARD_P2_ACTION_PLAN', '0')
    model, calls = substituted_model(tmp_path)
    for _ in range(2):
        assert model.generate(request_data()) == '{}'
        assert model.model_calls == 1
    sent = [request['body'] for path, request in calls if path == '/api/generate']
    assert len(sent) == 2
    for body in sent:
        assert set(body['format']['required']) == {
            'analysis_protocol','prompt_version','selected_quotes','selected_actions','selected_change_indices',
        }
        assert body['format']['additionalProperties'] is False
        assert json.loads(body['prompt']) == request_data()
    before = list(calls)
    with pytest.raises(BudgetError, match='p2_ai_budget_exhausted'):
        model.generate(request_data())
    assert model.model_calls == 0 and calls == before
    assert len(json.loads(model.path.read_bytes())['intents']) == 2


def test_task50_invalid_opt_in_fails_closed_even_with_p2_disabled(tmp_path, monkeypatch):
    from app.api.main import create_default_app
    tmp_path.chmod(0o700)
    monkeypatch.setenv('OPENGUARD_P2_AI_V4_PLAN', 'invalid')
    monkeypatch.setenv('OPENGUARD_ENABLE_P2', '0')
    with pytest.raises(RuntimeError, match='invalid OPENGUARD_P2_AI_V4_PLAN'):
        create_default_app(data_dir=tmp_path)


@pytest.mark.parametrize('count,error', [(0, 'p2_ai_v4_no_actions'), (5, 'p2_ai_v4_required_action_overflow')])
def test_task50_unusable_action_catalog_fails_without_model(tmp_path, count, error):
    from app.p2.action_plan_runner import run_v4_plan
    payload = request_data()
    payload['context']['material_claims_view_id'] = 'p4view_fixture'
    payload['context']['action_catalog'] = [
        {'action_kind': kind, 'basis_ids': ['fixture_basis'], 'required': True}
        for kind in ('RESOLVE_SPDX_TEXT_CONFLICT', 'REVIEW_STRONG_COPYLEFT_DISCLOSURE',
                     'REVIEW_WEAK_COPYLEFT_FILE_SCOPE', 'REVIEW_APACHE_NOTICE_SECTION_4D',
                     'SUPPLY_MISSING_LICENSE_MATERIAL')[:count]
    ]
    payload['context_sha256'] = digest(payload['context'])
    model, calls = substituted_model(tmp_path)
    value = run_v4_plan(model, payload, audit_root=tmp_path/'audit')
    assert value['status'] == 'failed' and value['error_code'] == error
    assert value['plan'] is None and not value['attempts'] and not value['actions']
    assert not value['model_calls'] and not calls and not model.path.exists()
