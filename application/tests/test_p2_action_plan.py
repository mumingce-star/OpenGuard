"""Closed offline protocol tests; synthetic selections are not model inference."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket

import pytest

from app.p2.action_plan import (ANALYSIS_PROTOCOL, DISPLAY_ORIGIN, PROTOCOL,
    PlanSemanticError, plan_prompt, plan_schema, prepare_plan_payload,
    review_legacy_output, validate_plan)
from app.p2.contract import canonical, digest
from app.p2.local_actions import CONDITION

TASK = Path(__file__).resolve().parents[3]
AUDIT = TASK / 'runtime/p2-ai-model-audit'


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('Offline protocol test: network and model forbidden')
    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(socket.socket, 'connect_ex', denied)
    monkeypatch.setattr(socket, 'getaddrinfo', denied)


@pytest.fixture
def payload():
    return json.loads(json.loads((AUDIT/'13-615f525ed709-request.json').read_text())['prompt'])


def selection(value, kinds=None):
    """Explicit SYNTHETIC_TEST_ONLY model selection for validator negatives."""
    context = prepare_plan_payload(value)['plan_context']
    condition = next(q for q in context['quote_catalog'] if q['quote'] == CONDITION)
    kinds = kinds or ['CHECK_MODIFIED_COPY', 'CHECK_TRAINING_SCOPE', 'CHECK_ASSET_SCOPE']
    actions = []
    for kind in kinds:
        row = next(row for row in context['action_catalog'] if row['kind'] == kind)
        actions.append({k: row[k] for k in ('target_id', 'basis_kind')} |
                       {'kind': kind, 'basis_ids': row['eligible_basis_ids'][:1]})
    return {'clauses': [{'quote_id': condition['quote_id'], 'category': 'condition'}],
            'actions': actions,
            'change_explanations': [{'index': i, 'kind': 'usage_change' if row['field'].startswith('usage.') else 'resource_change'}
                                    for i, row in enumerate(value.get('changes', []))]}


def validate(value, obj):
    return validate_plan(json.dumps(obj, ensure_ascii=False), prepare_plan_payload(value))


def test_actual13_legacy_review_detects_unsupported_delivery_and_preserves_original(payload):
    path = AUDIT/'13-615f525ed709-response.json'
    before = path.read_bytes()
    old = json.loads(json.loads(before)['response'])
    saved = deepcopy(old)
    issues = review_legacy_output(old, payload)
    assert any(x['code'] == 'legacy_delivery_premise_not_observed' and x['path'] == '/actions/3/text' for x in issues)
    assert any(x['code'] == 'legacy_cross_scope_basis_unverified' and x['path'] == '/actions/1/text' for x in issues)
    assert any(x['code'] == 'legacy_cross_scope_basis_unverified' and x['path'] == '/actions/2/text' for x in issues)
    assert old == saved and path.read_bytes() == before


def test_context_idempotent_and_under_existing_provider_payload_cap(payload):
    before = deepcopy(payload)
    enriched = prepare_plan_payload(payload)
    assert prepare_plan_payload(enriched) == enriched
    assert payload == before
    assert enriched['analysis_protocol'] == ANALYSIS_PROTOCOL
    assert enriched['plan_protocol'] == PROTOCOL
    assert len(canonical(enriched)) <= 24000
    context = dict(enriched['plan_context']); sha = context.pop('context_sha256')
    assert digest(context) == sha
    assert context['subject'] == payload['subject'] and context['usage'] == payload['usage']


def test_validated_plan_keeps_condition_and_usage_gap_sources_separate(payload):
    obj = selection(payload)
    before = deepcopy(obj)
    clauses, actions, changes, details = validate(payload, obj)
    assert obj == before and clauses[0]['quote'] == CONDITION
    assert clauses[0]['start'] >= 0 and changes == []
    assert actions[0]['source_material_ids'] == [payload['materials'][0]['material_id']]
    assert actions[1]['source_material_ids'] == actions[2]['source_material_ids'] == []
    assert actions[1]['basis_kind'] == 'usage_gap'
    assert '训练数据、模型或其他资源' in actions[1]['text']
    assert all(a['display_origin'] == DISPLAY_ORIGIN for a in actions)
    assert all(a['claim_level'] == 'verification_action_only' for a in actions)
    assert details['status'] == 'validated' and details['formal_effect'] == 'none'
    assert details['raw_model_output_is_display_text'] is False
    assert details['selection_sha256'] == digest(obj)


@pytest.mark.parametrize('kind', ['CHECK_PLANNED_COMPONENT_DELIVERY', 'CHECK_SERVICE_SCOPE', 'CHECK_PUBLIC_SOURCE_SCOPE'])
def test_false_current_usage_excludes_inapplicable_action(payload, kind):
    value = selection(payload)
    value['actions'][0]['kind'] = kind
    with pytest.raises(PlanSemanticError) as error:
        validate(payload, value)
    assert error.value.code == 'plan_action_not_eligible' and error.value.recoverable
    assert kind not in error.value.details['allowed']


def test_true_distribution_supports_only_planned_never_completed_delivery(payload):
    payload['usage']['distributed'] = True
    _, actions, _, _ = validate(payload, selection(payload, ['CHECK_PLANNED_COMPONENT_DELIVERY']))
    assert '拟交付' in actions[0]['text'] and '不表示交付已经发生' in actions[0]['text']
    assert '已交付文件清单' not in actions[0]['text']
    assert actions[0]['usage_fields'] == ['distributed']


def test_false_versus_null_usage_are_not_collapsed(payload):
    payload['usage']['training'] = None
    context = prepare_plan_payload(payload)['plan_context']
    kinds = [r['kind'] for r in context['action_catalog']]
    assert 'CHECK_TRAINING_SCOPE' not in kinds and 'CONFIRM_TRAINING' in kinds
    _, actions, _, _ = validate(payload, selection(payload, ['CONFIRM_TRAINING']))
    assert '仍未知' in actions[0]['text'] and actions[0]['source_material_ids'] == []
    payload['usage']['training'] = False
    assert 'CONFIRM_TRAINING' not in [r['kind'] for r in prepare_plan_payload(payload)['plan_context']['action_catalog']]


@pytest.mark.parametrize('alter', [
    lambda p: p['usage'].__setitem__('distributed', 0),
    lambda p: p['binding'].__setitem__('project_revision', 'f'*40),
    lambda p: p['subject'].__setitem__('version', '15.0.0'),
    lambda p: p['materials'][0].__setitem__('source_sha256', 'f'*64),
    lambda p: p['materials'][0].__setitem__('text', p['materials'][0]['text']+' '),
    lambda p: p['materials'][0].__setitem__('verification_state', 'verified'),
    lambda p: p['materials'][0]['subject'].__setitem__('resource_id', 'cmp_FOREIGN'),
])
def test_wrong_actual_input_cannot_be_repaired_by_generation(payload, alter):
    value = deepcopy(payload); alter(value)
    with pytest.raises(PlanSemanticError) as error:
        prepare_plan_payload(value)
    assert error.value.recoverable is False


def test_prepared_context_cannot_be_tampered_or_become_stale(payload):
    enriched = prepare_plan_payload(payload)
    enriched['plan_context']['usage']['distributed'] = True
    with pytest.raises(PlanSemanticError, match='plan_context_conflict'):
        prepare_plan_payload(enriched)
    enriched = prepare_plan_payload(payload)
    enriched['usage']['training'] = False
    with pytest.raises(PlanSemanticError, match='plan_context_conflict'):
        prepare_plan_payload(enriched)


@pytest.mark.parametrize('mutation,code', [
    (lambda obj: obj['actions'][0].__setitem__('target_id', 'usage_training'), 'plan_action_target_id'),
    (lambda obj: obj['actions'][1].__setitem__('basis_kind', 'license_condition'), 'plan_action_basis_kind'),
    (lambda obj: obj['actions'][1].__setitem__('basis_ids', [obj['clauses'][0]['quote_id']]), 'plan_action_basis'),
    (lambda obj: obj['actions'][0].__setitem__('basis_ids', ['gap_training_scope_unobserved']), 'plan_action_basis'),
    (lambda obj: obj['clauses'][0].__setitem__('category', 'disclaimer'), 'plan_clause_role'),
    (lambda obj: obj['actions'].append(deepcopy(obj['actions'][0])), 'plan_action_not_eligible'),
    (lambda obj: obj['actions'][0].__setitem__('basis_ids', [obj['clauses'][0]['quote_id']]*2), 'plan_action_basis'),
])
def test_wrong_action_edges_fail_typed_checks(payload, mutation, code):
    obj = selection(payload); mutation(obj)
    with pytest.raises(PlanSemanticError) as error:
        validate(payload, obj)
    assert error.value.code == code
    assert error.value.path.startswith('/') and error.value.recoverable is True


def test_permission_or_disclaimer_cannot_stand_in_for_the_notice_condition(payload):
    context = prepare_plan_payload(payload)['plan_context']
    permission = next(q for q in context['quote_catalog'] if q['quote'].startswith('Permission'))
    obj = selection(payload)
    obj['clauses'] = [{'quote_id': permission['quote_id'], 'category': 'permission'}]
    obj['actions'][0]['basis_ids'] = [permission['quote_id']]
    with pytest.raises(PlanSemanticError, match='plan_action_basis'):
        validate(payload, obj)


def test_condition_must_be_selected_with_its_actual_role(payload):
    context = prepare_plan_payload(payload)['plan_context']
    disclaimer = next(q for q in context['quote_catalog'] if q['quote'].startswith('THE SOFTWARE'))
    obj = selection(payload)
    obj['clauses'] = [{'quote_id': disclaimer['quote_id'], 'category': 'disclaimer'}]
    with pytest.raises(PlanSemanticError, match='plan_action_uncited_condition'):
        validate(payload, obj)


@pytest.mark.parametrize('raw', ['{', 'null', '[]', '{"clauses":[],"clauses":[]}',
    '{"clauses":[],"actions":[],"change_explanations":[],"text":"已交付"}'])
def test_ambiguous_syntax_or_extra_free_text_does_not_trigger_silent_correction(payload, raw):
    with pytest.raises(PlanSemanticError) as error:
        validate_plan(raw, prepare_plan_payload(payload))
    assert error.value.recoverable is False


def test_model_cannot_supply_freeform_action_text(payload):
    obj = selection(payload)
    obj['actions'][0]['text'] = '对照已交付文件清单，已经允许商用'
    with pytest.raises(PlanSemanticError) as error:
        validate(payload, obj)
    assert error.value.code == 'plan_output_shape' and error.value.recoverable is False


def test_program_changes_cover_exact_saved_usage_and_reject_invented_or_missing_changes(payload):
    payload['changes'] = [{'field': 'usage.distributed', 'before': True, 'after': False}]
    _, _, changes, _ = validate(payload, selection(payload))
    assert '由是变为否' in changes[0]['explanation']
    assert changes[0]['before'] is True and changes[0]['after'] is False
    obj = selection(payload); obj['change_explanations'] = []
    with pytest.raises(PlanSemanticError, match='plan_change_coverage'):
        validate(payload, obj)
    obj = selection(payload); obj['change_explanations'][0]['index'] = True
    with pytest.raises(PlanSemanticError, match='plan_change_index'):
        validate(payload, obj)


def test_feedback_is_additive_and_does_not_mutate_usage_or_action_eligibility(payload):
    first = prepare_plan_payload(payload)
    second = deepcopy(first)
    second['plan_feedback'] = {'code': 'plan_action_not_eligible', 'path': '/actions/0/kind',
        'details': {'allowed': ['CHECK_MODIFIED_COPY']}, 'parent_output_sha256': 'a'*64}
    repaired_input = prepare_plan_payload(second)
    assert repaired_input['plan_context'] == first['plan_context']
    assert repaired_input['usage'] == first['usage']
    assert 'plan_feedback只描述错误位置' in plan_prompt(repaired_input)
    assert 'distributed=false没有交付行动' in plan_prompt(first)


def test_schema_contains_only_typed_choices_not_prefabricated_action_sentences(payload):
    schema = plan_schema(prepare_plan_payload(payload))
    fields = schema['properties']['actions']['items']['properties']
    assert set(fields) == {'kind', 'target_id', 'basis_kind', 'basis_ids'}
    assert 'text' not in fields
    assert 'CHECK_PLANNED_COMPONENT_DELIVERY' not in fields['kind']['enum']
    assert schema['properties']['change_explanations']['maxItems'] == 0
    assert '完整新JSON' not in plan_prompt(payload)  # Only a recorded semantic failure enables feedback wording.
