"""Exact saved-output replay and synthetic counterexamples; no model calls."""
from copy import deepcopy
import json
from pathlib import Path
import socket

import pytest

from app.p2.ai_analysis import validate_output

FIXTURE = Path(__file__).parents[1] / 'fixtures/ai-action-subject-20261116'


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('Offline validator regression must not use network')
    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(socket, 'getaddrinfo', denied)


def saved_pair():
    request = json.loads((FIXTURE / 'request.json').read_text())
    response = json.loads((FIXTURE / 'response.json').read_text())
    return json.loads(response['response']), json.loads(request['prompt'])


def test_exact_rejected_response_accepts_without_rewriting_any_text_or_binding():
    obj, payload = saved_pair()
    original = deepcopy(obj)
    clauses, actions, changes = validate_output(json.dumps(obj), payload)
    assert obj == original
    assert [a['text'] for a in actions] == [a['text'] for a in original['actions']]
    assert [a['source_material_ids'] for a in actions] == [a['source_material_ids'] for a in original['actions']]
    assert [c['quote'] for c in clauses] == [c['quote'] for c in original['clauses']]
    assert [c['after'] for c in changes] == [c['after'] for c in payload['changes']]
    assert payload['materials'][0]['verification_state'] == 'pending'


@pytest.mark.parametrize('text', [
    '对照许可条款确认交付文件中是否包含完整版权声明',
    '对照已引用的许可条款检查实际交付文件是否包含对应版权声明，并记录保留位置。',
    '对照许可条款核对修改后源码文件中是否包含版权声明，记录待补文件。',
])
def test_license_basis_and_file_subject(text):
    obj, payload = saved_pair()
    obj['actions'] = [{**obj['actions'][0], 'text': text}]
    assert validate_output(json.dumps(obj), payload)[1][0]['text'] == text


@pytest.mark.parametrize('text', [
    '对照许可条款确认是否包含完整版权声明',
    '检查许可条款中是否包含对修改和分发的限制。',
    '对照许可条款确认交付文件中是否包含版权声明，并检查许可条款是否存在免责说明。',
    '对照许可条款确认交付文件中是否包含版权声明，检查是否允许保留许可声明。',
    '对照许可条款确认交付文件中是否包含版权声明，服务运行中必须保留完整原文。',
    '核对许可条款中关于版权归属的表述，确认是否明确列出所有权利人。',
])
def test_actual_license_questions_and_other_known_errors_still_rejected(text):
    obj, payload = saved_pair()
    obj['actions'] = [{**obj['actions'][0], 'text': text}]
    with pytest.raises(ValueError, match='known action semantic error'):
        validate_output(json.dumps(obj), payload)


@pytest.mark.parametrize('mutation', ['permission', 'foreign_material', 'quote', 'usage'])
def test_other_guards_remain_active(mutation):
    obj, payload = saved_pair()
    if mutation == 'permission':
        obj['actions'][-1]['text'] += '，已经合规。'
    elif mutation == 'foreign_material':
        obj['actions'][-1]['source_material_ids'] = ['foreign-resource-material']
    elif mutation == 'quote':
        obj['clauses'][0]['quote'] = 'A fabricated quote not present in the actual material.'
    else:
        obj['actions'][-1]['text'] += '，usage.distributed=false。'
    with pytest.raises(ValueError):
        validate_output(json.dumps(obj), payload)
