"""Offline prompt/unchanged-validator checks; never evidence of model success."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket

import pytest

from app.ai.p2_analysis import (BoundQwen, PROMPT_VERSION, output_schema,
                                prompt_for)
from app.ai.ollama import MODEL_NAME, MANIFEST_DIGEST, OLLAMA_VERSION
from app.p2 import ai_analysis as validator_module
from app.p2.ai_analysis import validate_output


TASK = Path(__file__).resolve().parents[3]
AUDIT = TASK / 'runtime/p2-ai-model-audit'
REQUEST = AUDIT / '12-615f525ed709-request.json'
RESPONSE = AUDIT / '12-615f525ed709-response.json'
VALIDATOR_SHA = '838bf2c55cd4c5e6e05c1b95d2e60775d460a17db31b3c943faa6e0229e47d78'


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('TEST_ONLY: no socket, DNS or actual model allowed')
    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(socket.socket, 'connect_ex', denied)
    monkeypatch.setattr(socket, 'getaddrinfo', denied)


@pytest.fixture
def actual_payload():
    return json.loads(json.loads(REQUEST.read_text())['prompt'])


def test_captured_failed_output_and_validator_remain_exact(actual_payload):
    assert hashlib.sha256(REQUEST.read_bytes()).hexdigest() == '5c4168190846fd048ac71874aea78e1b6d7ea546d117c1596c04e61bae350f1a'
    assert hashlib.sha256(RESPONSE.read_bytes()).hexdigest() == '2270a191df648e39553593602dad809c4e351677ed23346a21bd5a0b5c771f10'
    assert hashlib.sha256(Path(validator_module.__file__).read_bytes()).hexdigest() == VALIDATOR_SHA
    generated = json.loads(RESPONSE.read_text())
    assert generated['done'] is True and generated['done_reason'] == 'stop'
    with pytest.raises(ValueError, match='known action semantic error'):
        validate_output(generated['response'], actual_payload)


def test_current_actual_usage_has_specific_positive_targets(actual_payload):
    system = prompt_for(actual_payload)
    guidance = system.split('当前用途适用的行动组织指引：\n', 1)[1]
    assert PROMPT_VERSION == 'p2-bound-material-actions/7'
    for selected in ('当前已选择修改代码', '当前已选择商业使用',
                     '当前已选择模型训练', '当前已选择资源再分发'):
        assert selected in guidance
    assert '本组件副本或实质部分' in guidance
    assert '版权和许可声明保留位置' in guidance
    assert '把代码材料与训练数据分开核对' in guidance
    assert '当前未声明向他人交付本组件，也未声明提供在线服务' in guidance
    assert '当前用途已声明向他人分发或交付' not in guidance
    assert '单独确认在线服务' not in guidance
    assert '针对计划公开的修改后源码' not in guidance


@pytest.mark.parametrize('field,label', [
    ('commercial', '当前已选择商业使用'),
    ('modified', '当前已选择修改代码'),
    ('training', '当前已选择模型训练'),
    ('redistributed_assets', '当前已选择资源再分发'),
])
def test_true_branch_cannot_leak_into_false_or_unknown(actual_payload, field, label):
    for value in (False, None):
        payload = deepcopy(actual_payload)
        payload['usage'][field] = value
        guidance = prompt_for(payload).split('当前用途适用的行动组织指引：\n', 1)[1]
        assert label not in guidance
        if value is None:
            assert '尚未确定的用途保持未知' in guidance


def test_existing_service_distribution_and_disclosure_branches_still_apply(actual_payload):
    payload = deepcopy(actual_payload)
    payload['usage'].update(network_service=True, distributed=True, source_disclosure=True)
    guidance = prompt_for(payload).split('当前用途适用的行动组织指引：\n', 1)[1]
    assert '针对计划公开的修改后源码' in guidance
    assert '单独确认在线服务' in guidance
    assert '当前用途已声明向他人分发或交付' in guidance
    assert '当前未声明向他人交付本组件' not in guidance


def test_no_applicable_selection_still_has_bounded_fact_target(actual_payload):
    payload = deepcopy(actual_payload)
    payload['usage'] = {field: False for field in payload['usage']}
    guidance = prompt_for(payload).split('当前用途适用的行动组织指引：\n', 1)[1]
    assert '待补记录' in guidance and '不要凭空安排在线服务交付检查' in guidance
    payload['usage'] = {}
    assert '本组件准确版本的对应关系' in prompt_for(payload)


def test_clause_roles_and_generation_schema_are_not_relaxed(actual_payload):
    system = prompt_for(actual_payload)
    assert '不能改写成必须保留免责段落这一新增义务' in system
    assert '不要把已给出的条款内容重新写成是否存在某条款的问题' in system
    assert '材料已经采用或保存' in system and '不能宣称可商用' in system
    previous_schema = json.loads(REQUEST.read_text())['format']
    assert output_schema(actual_payload['materials'], actual_payload['changes']) == previous_schema
    assert 'enum' not in previous_schema['properties']['actions']['items']['properties']['text']


def test_synthetic_concise_bound_actions_use_unchanged_validator(actual_payload):
    material = actual_payload['materials'][0]
    quote = next(q for q in material['quote_candidates'] if q.startswith('The above copyright'))
    synthetic_output = {
        'clauses': [{'material_id': material['material_id'], 'quote': quote, 'category': 'condition'}],
        'actions': [
            {'text': '核对修改后文件中本组件副本的范围，记录版权与许可声明保留位置。',
             'source_material_ids': [material['material_id']]},
            {'text': '记录训练输入与再分发资源各自的准确版本和许可材料，分别核对适用范围。',
             'source_material_ids': [material['material_id']]},
        ],
        'change_explanations': [],
    }
    clauses, actions, changes = validate_output(json.dumps(synthetic_output, ensure_ascii=False), actual_payload)
    assert len(clauses) == 1 and len(actions) == 2 and changes == []
    assert all(row['claim_level'] == 'verification_action_only' for row in actions)
    # This fixture validates structure/binding, not genuine generated semantics.
    wrong = deepcopy(synthetic_output)
    wrong['actions'][0]['text'] = '核对当前distributed=true的用途设定，记录文件清单。'
    with pytest.raises(ValueError, match='usage value conflict'):
        validate_output(json.dumps(wrong, ensure_ascii=False), actual_payload)


def test_closed_test_transport_receives_new_prompt_and_same_schema(actual_payload, tmp_path):
    tmp_path.chmod(0o700)
    provider = BoundQwen(tmp_path / 'SYNTHETIC_TEST_ONLY_budget.json')
    captured = []

    def closed_transport(path, **kwargs):
        captured.append((path, kwargs))
        if path == '/api/version':
            return {'version': OLLAMA_VERSION}
        if path == '/api/tags':
            return {'models': [{'name': MODEL_NAME, 'digest': MANIFEST_DIGEST}]}
        assert path == '/api/generate'
        return {'model': MODEL_NAME, 'done': True, 'done_reason': 'stop', 'response': '{}'}

    provider.transport._request_json = closed_transport
    assert provider.generate(actual_payload) == '{}'
    requests = [kwargs['body'] for path, kwargs in captured if path == '/api/generate']
    assert len(requests) == 1
    body = requests[0]
    assert body['system'] == prompt_for(actual_payload)
    assert body['format'] == json.loads(REQUEST.read_text())['format']
    assert body['options']['temperature'] == 0
    assert provider.model['prompt_version'] == 'p2-bound-material-actions/7'
    assert len(json.loads((tmp_path / 'SYNTHETIC_TEST_ONLY_budget.json').read_text())['intents']) == 1
