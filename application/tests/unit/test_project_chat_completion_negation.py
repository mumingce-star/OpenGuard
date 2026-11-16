"""Synthetic language cases: unknown is not a claim of completed delivery."""
import pytest
from app.p2.project_chat import validate_usage_prose
USAGE = dict(commercial=True, modified=True, distributed=True, network_service=False,
             training=False, redistributed_assets=False, source_disclosure=False)

@pytest.mark.parametrize('text', [
    '项目未被证实已向他人交付，实际分发行为尚待独立核验。',
    '本项目未被证实已经交付。',
    '用途选择不代表已向他人交付。',
    '不能确认已经分发。',
])
def test_explicit_unproven_completion_is_not_affirmative(text):
    validate_usage_prose(text, USAGE)

@pytest.mark.parametrize('text', [
    '项目已向他人交付。', '项目已经交付。', '已经分发。',
    '项目未被证实已交付但已经分发。',
    '项目未被证实已交付；已经分发。',
    '项目并非未被证实已交付。', '项目不是未被证实已交付。',
    '不能说未被证实已经交付。',
    '项目未被证实，但已经交付。',
])
def test_assertions_and_double_negation_still_fail_closed(text):
    with pytest.raises(ValueError, match='p2_chat_unverified_completion'):
        validate_usage_prose(text, USAGE)


def test_output_contract_requires_unique_citations_without_widening_values():
    from app.ai.project_chat import output_schema
    payload = {'evidence': [{'basis_id': 'TEST_ONLY', 'quote': 'Original test-only quote.'}],
               'scope': {'result_id': 'test_result', 'result_sha256': 'a' * 64}, 'usage': USAGE}
    schema = output_schema(payload)['properties']['citations']
    assert schema['uniqueItems'] is True
    assert schema['maxItems'] == 4
    assert schema['items']['properties']['basis_id']['enum'] == ['TEST_ONLY']
    assert schema['items']['properties']['quote']['enum'] == ['Original test-only quote.']


@pytest.mark.parametrize('text,accepted', [
    ('本版用途包含商业使用和分发。计划声明不等同于实际完成。', True),
    ('本版用途包含商业使用和分发。计划声明不等于实际完成。', True),
    ('本版用途包含商业使用和分发。全部流程都已完成。', False),
    ('本版用途包含商业使用和分发。可以直接商用，不等同于实际完成。', False),
])
def test_equivalent_uncertainty_phrase_keeps_formal_guards(text, accepted):
    import json
    from app.ai.project import validate
    context = {'assessment_id': 'TEST_ONLY', 'state_digest': 'a' * 64,
               'evidence': [], 'formal_state': {'dimensions': [{'id': 'commercial', 'status': 'unknown'}]}}
    result = {'assessment_id': 'TEST_ONLY', 'state_digest': 'a' * 64, 'answer': text, 'evidence_ids': []}
    if accepted:
        validate(json.dumps(result), json.dumps(context))
    else:
        with pytest.raises(ValueError):
            validate(json.dumps(result), json.dumps(context))


def test_not_equivalent_to_completed_is_not_completion_assertion():
    validate_usage_prose('计划声明不等同于已经交付。', USAGE)
