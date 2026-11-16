"""Actual15/16 remain failures; schema narrows program-owned change kinds.

JSON Schema validation is offline, not proof of Ollama grammar compatibility or
a new model pass. No captured output is changed or saved as a corrected result.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket

import pytest
from jsonschema import Draft202012Validator

from app.p2.action_plan import (PROMPT_VERSION, PlanSemanticError, plan_prompt,
    plan_schema, prepare_plan_payload, validate_plan)

AUDIT = Path(__file__).resolve().parents[3] / 'runtime/p2-ai-model-audit'
CAPTURES = {
    15: ('15-e54ab95b089a', 'a7341b15f3d8f1fced6c3444cede5b627ae09d189581f4f015067564fcb5ca01',
         '31a5019fe0231f197606fd6fbd91a9e20e2fbd488380cba68ff92b33cfb0a8e6', 4),
    16: ('16-62505ac7b033', '2c02d59502138fbbd8b2eafb08d09d7816fcd218a0892f00b3a68d6583961e9f',
         '0d136bc509d94f253027880a6de18e63ae840cbd482977fc0c18f0f17ca10c9a', 5),
}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('Frozen-output offline regression: no model/network')
    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(socket.socket, 'connect_ex', denied)
    monkeypatch.setattr(socket, 'getaddrinfo', denied)


def capture(number):
    stem, request_sha, response_sha, count = CAPTURES[number]
    request_path, response_path = AUDIT/(stem+'-request.json'), AUDIT/(stem+'-response.json')
    raw_request, raw_response = request_path.read_bytes(), response_path.read_bytes()
    assert hashlib.sha256(raw_request).hexdigest() == request_sha
    assert hashlib.sha256(raw_response).hexdigest() == response_sha
    request, response = json.loads(raw_request), json.loads(raw_response)
    return json.loads(request['prompt']), response, count, (raw_request, raw_response)


@pytest.mark.parametrize('number', [15, 16])
def test_actual_failed_responses_remain_rejected_and_all_kind_errors_are_reported(number):
    payload, response, mismatch_count, before = capture(number)
    assert response['done'] is True and response['done_reason'] == 'stop'
    original = response['response']
    with pytest.raises(PlanSemanticError) as error:
        validate_plan(original, prepare_plan_payload(payload))
    value = error.value
    assert value.code == 'plan_change_kind' and value.recoverable is True
    assert value.path == '/change_explanations/1/kind'
    assert len(value.details['issues']) == mismatch_count
    expected = value.details['expected_kind_by_index']
    assert len(expected) == 6
    assert [row['index'] for row in expected] == list(range(6))
    assert all(row['field'].startswith('usage.') and row['kind'] == 'usage_change' for row in expected)
    for issue in value.details['issues']:
        assert issue['actual'] == 'resource_change' and issue['expected'] == 'usage_change'
    assert response['response'] == original
    stem = CAPTURES[number][0]
    assert (AUDIT/(stem+'-request.json')).read_bytes() == before[0]
    assert (AUDIT/(stem+'-response.json')).read_bytes() == before[1]


@pytest.mark.parametrize('number', [15, 16])
def test_all_usage_schema_cannot_generate_the_observed_resource_change_kind(number):
    payload, response, _, _ = capture(number)
    schema = plan_schema(payload)
    Draft202012Validator.check_schema(schema)
    changes = schema['properties']['change_explanations']
    assert changes['minItems'] == changes['maxItems'] == 6
    assert changes['items']['properties']['kind']['enum'] == ['usage_change']
    assert 'oneOf' not in changes['items']
    actual_output = json.loads(response['response'])
    errors = list(Draft202012Validator(schema).iter_errors(actual_output))
    assert errors
    assert all(list(e.path)[0] == 'change_explanations' for e in errors)
    assert all(e.validator == 'enum' for e in errors)


def test_mixed_program_changes_bind_each_index_to_exact_kind_with_const_branches():
    payload, response, _, _ = capture(15)
    # SYNTHETIC_TEST_ONLY contrast: no file or model result is modified.
    payload = {k: v for k, v in payload.items() if k not in {'plan_context', 'plan_feedback'}}
    payload['changes'] = [payload['changes'][0],
        {'field': 'gaps', 'before': ['old'], 'after': ['old', 'new']}]
    schema = plan_schema(payload)
    Draft202012Validator.check_schema(schema)
    item = schema['properties']['change_explanations']['items']
    branches = item['oneOf']
    assert [(b['properties']['index']['const'], b['properties']['kind']['const']) for b in branches] == [
        (0, 'usage_change'), (1, 'resource_change')]
    validator = Draft202012Validator(item)
    for row in ({'index': 0, 'kind': 'usage_change'}, {'index': 1, 'kind': 'resource_change'}):
        assert validator.is_valid(row)
    for row in ({'index': 0, 'kind': 'resource_change'}, {'index': 1, 'kind': 'usage_change'}):
        assert not validator.is_valid(row)
    obj = json.loads(response['response'])
    obj['change_explanations'] = [{'index': 0, 'kind': 'usage_change'}, {'index': 1, 'kind': 'resource_change'}]
    _, _, rendered, _ = validate_plan(json.dumps(obj), prepare_plan_payload(payload))
    assert len(rendered) == 2 and rendered[1]['field'] == 'gaps'
    obj['change_explanations'][1] = {'index': 0, 'kind': 'usage_change'}
    with pytest.raises(PlanSemanticError, match='plan_change_index'):
        validate_plan(json.dumps(obj), prepare_plan_payload(payload))


def test_single_resource_change_and_no_change_have_legal_bounded_schemas():
    payload, _, _, _ = capture(15)
    payload = {k: v for k, v in payload.items() if k not in {'plan_context', 'plan_feedback'}}
    payload['changes'] = [{'field': 'state', 'before': 'unknown', 'after': 'pending'}]
    schema = plan_schema(payload)
    Draft202012Validator.check_schema(schema)
    assert schema['properties']['change_explanations']['items']['properties']['kind']['enum'] == ['resource_change']
    payload['changes'] = []
    schema = plan_schema(payload)
    Draft202012Validator.check_schema(schema)
    assert schema['properties']['change_explanations']['maxItems'] == 0


def test_prompt9_contains_full_readonly_program_mapping_without_changing_input():
    payload, _, _, _ = capture(15)
    before = deepcopy(payload)
    system = plan_prompt(payload)
    assert PROMPT_VERSION == 'p2-bound-action-plan/9'
    assert '不可自行重新分类' in system
    marker = 'change_kind_by_index（程序只读对应表）：'
    mapping = json.loads(system.split(marker, 1)[1].split('\n', 1)[0])
    assert len(mapping) == 6
    assert all(row['kind'] == 'usage_change' for row in mapping)
    assert payload == before
