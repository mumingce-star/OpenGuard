"""Deterministic TASK50 v4 context and model-selection boundary tests."""

from copy import deepcopy
from hashlib import sha256
import importlib
import json
from types import SimpleNamespace

import pytest

from app.domain.models import ComponentType
from app.p2.action_plan import PlanSemanticError
from app.p2.contract import digest


USAGES = ('commercial', 'distributed', 'modified')
BINDING = {'scan_id': 'scn_task50', 'assessment_id': 'asm_task50', 'assessment_version': 1}
DIGEST = 'a' * 64
SUPPLY = 'SUPPLY_MISSING_LICENSE_MATERIAL'
VERIFY = 'VERIFY_PERMISSIVE_OBLIGATIONS'
VERIFY_SOURCE = 'VERIFY_UNESTABLISHED_RELEASE_SOURCE'
CONFLICT = 'RESOLVE_SPDX_TEXT_CONFLICT'
NOTICE = 'REVIEW_APACHE_NOTICE_SECTION_4D'


@pytest.fixture
def domain(request):
    try:
        return importlib.import_module('app.p2.v4_action_plan')
    except ModuleNotFoundError as exc:
        if exc.name != 'app.p2.v4_action_plan':
            raise
        class MissingContract:
            def __getattr__(self, name):
                pytest.fail(f'TASK50 v4 plan contract is missing {name}: {request.node.name}')
        return MissingContract()


def fixture(*, license_id='MIT', version='1.0.0', version_state='INITIAL_RESULT',
            decisions=('UNKNOWN', 'NOT_COVERED', 'NOT_COVERED'), material=False,
            package_type=ComponentType.APPLICATION):
    subject = {'resource_id': 'cmp_target', 'version': version}
    resource = SimpleNamespace(
        id=subject['resource_id'], name='sample-component', version=version, ecosystem='npm',
        component_type=package_type,
    )
    run = SimpleNamespace(id=BINDING['scan_id'], components=[resource])
    view = {
        'schema_version': 'openguard-material-claims/4',
        'view_id': 'p4view_task50',
        'result_id': 'p2res_task50',
        'result_sha256': DIGEST,
        'revision': 1 if version_state == 'INITIAL_RESULT' else 2,
        'previous_result_id': None if version_state == 'INITIAL_RESULT' else 'p2res_before',
        'binding': BINDING,
        'data_scope': 'TEST_ONLY',
        'formal_effect': 'none',
        'declaration_observations': [{'subject': subject, 'expression': license_id, 'normalized_ids': [license_id]}],
        'claims': [{'subject': subject, 'usage': usage, 'claim_id': 'p4claim_' + usage, 'state': state,
                    'counter_evidence': [], 'evidence': [{'evidence_id': 'evd_' + usage, 'source_sha256': DIGEST}]}
                   for usage, state in zip(USAGES, decisions)],
        'advice': [{'subject': subject, 'usage': usage, 'saved_value': False if state == 'NOT_COVERED' else True,
                   'state': state, 'reasons': [], 'claim_ids': ['p4claim_' + usage]}
                   for usage, state in zip(USAGES, decisions)],
        'materials': [],
        'source_observations': [],
        'incremental_impact': {'mode': version_state, 'changed_claims': []},
    }
    if material:
        text = '连续原始许可文字（含汉字）' * 120
        raw = text.encode()
        view['materials'] = [{
            'subject': subject, 'material_id': 'p2mat_task50', 'source_sha256': DIGEST,
            'filename': 'LICENSE', 'byte_count': len(raw) + 10, 'parse_state': 'MATCHED_MIT', 'text_license': license_id,
            'source_binding': 'PINNED_RELEASE_MATCH',
            'clauses': [{'clause_id': 'clause_task50', 'material_id': 'p2mat_task50',
                         'kind': 'condition', 'quote': text, 'quote_sha256': sha256(raw).hexdigest(),
                         'byte_start': 10, 'byte_end': len(raw) + 10, 'material_sha256': DIGEST}],
        }]
    if license_id == 'GPL-3.0-only':
        view['advice'][0]['reasons'] = ['COPYLEFT_SOURCE_DISCLOSURE_REVIEW_REQUIRED']
    return run, view, resource


def build(domain, items, selected=()):
    usage = {'network_service': False, 'training': False, 'redistributed_assets': False, 'source_disclosure': False}
    usage.update((row['usage'],row['saved_value']) for row in items[1]['advice']
                 if row['subject']['resource_id'] == items[2].id)
    return domain.build_context(*items, list(selected), usage=usage)


def response(domain, context):
    quote = context['quote_catalog'][:1]
    actions = [item for item in context['action_catalog'] if item['required']]
    if not actions:
        actions = context['action_catalog'][:1]
    return {
        'analysis_protocol': domain.ANALYSIS_PROTOCOL,
        'prompt_version': domain.PROMPT_VERSION,
        'selected_quotes': [{'quote_id': row['quote_id'], 'category': row['kind']} for row in quote],
        'selected_actions': [{key: row[key] for key in ('action_kind', 'basis_ids')} for row in actions],
        'selected_change_indices': list(range(len(context['incremental_impact_summary']['changed_claims']))),
    }


def payload(domain, context):
    return {'analysis_protocol': domain.ANALYSIS_PROTOCOL, 'context': context, 'context_sha256': digest(context)}


def actions(context):
    return {item['action_kind']: item for item in context['action_catalog']}


def test_task50_empty_r1_requires_real_license_material_action(domain):
    context = build(domain, fixture())
    assert context['protocol'] == 'openguard-action-plan/3'
    assert context['result_revision'] == 1 and context['previous_result_id'] is None
    assert context['material_ids'] == context['quote_catalog'] == []
    assert context['dependency_conflicts'] is None
    assert actions(context)[SUPPLY]['required'] is True
    assert VERIFY not in actions(context)
    assert domain.plan_schema(payload(domain, context))['additionalProperties'] is False
    assert domain.ANALYSIS_PROTOCOL in domain.plan_prompt(payload(domain, context))
    clauses, rendered, changes = domain.validate_plan(json.dumps(response(domain, context)), payload(domain, context))
    assert clauses == changes == []
    assert rendered[0]['text'] == '补充 sample-component@1.0.0 对应版本的许可证原文及来源记录。'


@pytest.mark.parametrize(('expression', 'states', 'allowed'), [
    ('MIT', ('SUPPORT', 'NOT_COVERED', 'NOT_COVERED'), True),
    ('MIT', ('SUPPORT', 'UNKNOWN', 'NOT_COVERED'), False),
    ('MIT', ('SUPPORT', 'COUNTER_EVIDENCE', 'NOT_COVERED'), False),
    ('MIT', ('UNKNOWN', 'NOT_COVERED', 'NOT_COVERED'), False),
    ('MPL-2.0', ('SUPPORT', 'NOT_COVERED', 'NOT_COVERED'), False),
])
def test_task50_permissive_action_requires_subject_support_without_conflict(domain, expression, states, allowed):
    items = fixture(license_id=expression, decisions=states, material=True)
    context = build(domain, items, ('p2mat_task50',))
    assert (VERIFY in actions(context)) is allowed


def test_task50_scope_does_not_cross_resource_for_claims_changes_or_quotes(domain):
    run, view, resource = fixture(version_state='INCREMENTAL_DERIVED', material=True,
                                  decisions=('SUPPORT', 'NOT_COVERED', 'NOT_COVERED'))
    delta = {
        'usage': 'commercial', 'subject': {'resource_id': resource.id, 'version': resource.version},
        'previous_claim_id': 'p4claim_before', 'current_claim_id': 'p4claim_commercial',
        'previous_state': 'UNKNOWN', 'current_state': 'SUPPORT', 'previous_reasons': ['MISSING_LICENSE_MATERIAL'],
        'current_reasons': ['PINNED_RELEASE_AND_COMPLETE_MIT_CONDITIONAL_TEXT'],
        'trigger_material_ids': ['p2mat_task50'], 'trigger_answer_ids': [],
    }
    view['incremental_impact']['changed_claims'] = [dict(delta, subject={'resource_id': 'cmp_wrong', 'version': '1'}), delta]
    view['materials'].append(dict(view['materials'][0], subject={'resource_id': 'cmp_wrong', 'version': '1'},
                                  material_id='p2mat_wrong'))
    context = build(domain, (run, view, resource), ('p2mat_task50',))
    assert context['incremental_impact_summary'] == {'mode': 'INCREMENTAL_DERIVED', 'changed_claims': [delta]}
    assert all(row['material_id'] == 'p2mat_task50' for row in context['quote_catalog'])
    rendered, _, changes = domain.validate_plan(json.dumps(response(domain, context)), payload(domain, context))
    assert rendered == context['quote_catalog'][:1]
    assert changes == [{
        'index': 0,
        'explanation': 'sample-component@1.0.0 的商业使用研判由 UNKNOWN 变为 SUPPORT。核对本次变动的材料与证据。',
    }]
    with pytest.raises(ValueError):
        build(domain, (run, view, resource), ('p2mat_wrong',))


def test_task50_quote_catalog_uses_contiguous_utf8_original_ranges(domain):
    items = fixture(material=True)
    original = items[1]['materials'][0]['clauses'][0]['quote'].encode()
    context = build(domain, items, ('p2mat_task50',))
    assert context['quote_catalog']
    for quote in context['quote_catalog']:
        raw = quote['quote'].encode()
        assert raw == original[quote['byte_start'] - 10:quote['byte_end'] - 10]
        assert 0 < len(raw) <= 300 and quote['quote_sha256'] == sha256(raw).hexdigest()
    items[1]['materials'][0]['clauses'][0]['quote_sha256'] = 'b' * 64
    with pytest.raises(ValueError):
        build(domain, items, ('p2mat_task50',))


def test_task50_dependency_projection_is_same_subject_even_with_nullable_version(domain, monkeypatch):
    run, view, resource = fixture(version=None, package_type=ComponentType.LIBRARY)
    run.components.insert(0, SimpleNamespace(id='cmp_predecessor', component_type=ComponentType.LIBRARY))
    called = []
    projected = SimpleNamespace(
        resource_id=resource.id, version=None, gaps=['version_unavailable'],
        conflicts=[SimpleNamespace(code='lock_version_conflict', status='confirmed',
                                   declaration=SimpleNamespace(evidence=[SimpleNamespace(evidence_id='evd_a')]),
                                   lock=SimpleNamespace(evidence=[SimpleNamespace(evidence_id='evd_b')]))])
    def project(owner, *, source, after, limit):
        called.append((owner.id, source, after, limit))
        return [projected], 2, False
    monkeypatch.setattr(domain, 'project_dependency_evidence', project)
    context = build(domain, (run, view, resource))
    assert called == [(run.id, None, 'cmp_predecessor', 1)]
    dep = context['dependency_conflicts']
    assert dep == {'resource_id': resource.id, 'version': None, 'gaps': ['version_unavailable'],
                   'conflicts': [{'code': 'lock_version_conflict', 'status': 'confirmed', 'evidence_ids': ['evd_a', 'evd_b']}]}
    assert {'RESOLVE_DEPENDENCY_VERSION_CONFLICT', 'PIN_EXACT_DEPENDENCY_VERSION'} <= actions(context).keys()


def test_task50_conflict_and_notice_are_mandatory(domain):
    _, view, _ = items = fixture(license_id='Apache-2.0')
    subject = view['claims'][0]['subject']
    view['claims'][0]['counter_evidence'] = [{
        'code': 'SPDX_TEXT_CONFLICT', 'evidence_ids': ['evd_conflict'], 'source_observation_ids': [],
        'material_ids': [], 'declaration_evidence_ids': [],
    }, {
        'code': 'NOTICE_REQUIRES_REVIEW', 'evidence_ids': [], 'source_observation_ids': ['p4source_task50'],
        'material_ids': [], 'declaration_evidence_ids': [],
    }]
    view['source_observations'] = [{'subject': subject, 'notice_status': 'PRESENT_UNREVIEWED',
                                   'source_observation_id': 'p4source_task50'}]
    catalog = actions(build(domain, items))
    assert all(catalog[k]['required'] is True for k in (CONFLICT, NOTICE, SUPPLY))


def test_task50_missing_required_action_only_allows_semantic_correction(domain):
    context = build(domain, fixture())
    selection = response(domain, context)
    alternate = actions(context)[VERIFY_SOURCE]
    selection['selected_actions'] = [{'action_kind': VERIFY_SOURCE, 'basis_ids': alternate['basis_ids']}]
    with pytest.raises(PlanSemanticError) as error:
        domain.validate_plan(json.dumps(selection), payload(domain, context))
    assert error.value.code == 'v4_required_action_missing' and error.value.recoverable is True


@pytest.mark.parametrize('mutation', [
    'illegal_action', 'injected_prose', 'duplicate_action', 'wrong_basis',
    'unknown_quote', 'wrong_category', 'change_outside_catalog', 'boolean_change', 'wrong_protocol',
])
def test_task50_forged_model_selection_is_not_recoverable(domain, mutation):
    context = build(domain, fixture(material=True, license_id='GPL-3.0-only'), ('p2mat_task50',))
    selection = deepcopy(response(domain, context))
    if mutation == 'illegal_action':
        selection['selected_actions'][0]['action_kind'] = VERIFY
    elif mutation == 'injected_prose':
        selection['selected_actions'][0]['text'] = '可直接分发'
    elif mutation == 'duplicate_action':
        selection['selected_actions'] *= 2
    elif mutation == 'wrong_basis':
        selection['selected_actions'][0]['basis_ids'] = ['evd_forged']
    elif mutation == 'unknown_quote':
        selection['selected_quotes'][0]['quote_id'] = 'quote_forged'
    elif mutation == 'wrong_category':
        selection['selected_quotes'][0]['category'] = 'permission'
    elif mutation == 'change_outside_catalog':
        selection['selected_change_indices'] = [5]
    elif mutation == 'boolean_change':
        selection['selected_change_indices'] = [True]
    else:
        selection['analysis_protocol'] = 'legacy'
    with pytest.raises(PlanSemanticError) as error:
        domain.validate_plan(json.dumps(selection), payload(domain, context))
    assert error.value.recoverable is False


@pytest.mark.parametrize('raw', ['{', '{"x":1,"x":2}', '{"x": NaN}', '[]'])
def test_task50_json_or_top_level_errors_are_not_recoverable(domain, raw):
    context = build(domain, fixture())
    with pytest.raises(PlanSemanticError) as error:
        domain.validate_plan(raw, payload(domain, context))
    assert error.value.recoverable is False
