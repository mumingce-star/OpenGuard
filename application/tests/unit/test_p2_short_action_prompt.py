"""Prompt-only correction after actual rejected output09; no real inference."""
import json
from pathlib import Path
import socket

import pytest

from app.ai.p2_analysis import BoundQwen, PROMPT_VERSION, output_schema, prompt_for
from app.ai.ollama import OLLAMA_VERSION, MODEL_NAME, MANIFEST_DIGEST
from app.p2.ai_analysis import validate_output

FIXTURE = Path(__file__).parents[1] / 'fixtures/qwen-short-action-regression'


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('No actual model, socket or DNS is permitted')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)


def payload():
    return json.loads((FIXTURE / 'actual-input-09.json').read_text())


def test_original_actual_output_still_rejected_not_rewritten():
    raw = (FIXTURE / 'actual-output-09.json').read_text()
    actual = json.loads(raw)
    assert len(actual['actions'][0]['text']) == 300
    with pytest.raises(ValueError, match='incomplete embedded quote'):
        validate_output(raw, payload())


def test_prompt_and_internal_action_schema_are_short_without_policy_change():
    value = payload(); schema = output_schema(value['materials'], value['changes'])
    action = schema['properties']['actions']['items']['properties']['text']
    assert action == {'type': 'string', 'minLength': 8, 'maxLength': 90}
    system = prompt_for(value)
    assert '8至90个字符' in system and '不使用任何引号' in system
    assert '逐字原文只能放在clauses.quote' in system
    assert '不得从Git根LICENSE推导需要排除完整项目结构或第三方依赖的分发限制' in system
    assert '实际文件或分发范围未知时只要求记录和核对' in system
    assert PROMPT_VERSION == 'p2-bound-material-actions/6'
    assert schema['properties']['clauses']['items']['properties']['quote']['enum'] == list(dict.fromkeys(q for m in value['materials'] for q in m['quote_candidates']))


def test_concise_bound_verification_action_still_passes_existing_validator():
    value = payload(); material = value['materials'][0]
    quote = next(q for q in material['quote_candidates'] if q.startswith('The above copyright'))
    response = {'clauses': [{'material_id': material['material_id'], 'quote': quote, 'category': 'condition'}],
                'actions': [{'text': '核对计划交付文件与版权声明的保留位置，并记录待补项。',
                             'source_material_ids': [material['material_id']]}], 'change_explanations': []}
    clauses, actions, changes = validate_output(json.dumps(response, ensure_ascii=False), value)
    assert clauses[0]['quote'] == quote and actions[0]['claim_level'] == 'verification_action_only'
    assert len(actions[0]['text']) <= 90 and changes == []


def test_actual_provider_request_uses_frozen_new_system_and_schema(tmp_path):
    tmp_path.chmod(0o700)
    provider = BoundQwen(tmp_path / 'SYNTHETIC_ONLY_BUDGET.json')
    seen = []
    def closed_transport(path, **kwargs):
        seen.append((path, kwargs))
        if path == '/api/version':
            return {'version': OLLAMA_VERSION}
        if path == '/api/tags':
            return {'models': [{'name': MODEL_NAME, 'digest': MANIFEST_DIGEST}]}
        assert path == '/api/generate'
        return {'model': MODEL_NAME, 'done': True, 'done_reason': 'stop', 'response': '{}'}
    provider.transport._request_json = closed_transport
    provider.generate(payload())
    body = next(kwargs['body'] for path, kwargs in seen if path == '/api/generate')
    assert body['system'] == prompt_for(payload())
    assert body['format']['properties']['actions']['items']['properties']['text']['maxLength'] == 90
    assert provider.model['prompt_version'] == PROMPT_VERSION
    assert len([1 for path, _ in seen if path == '/api/generate']) == 1
