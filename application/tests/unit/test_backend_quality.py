"""Quality-01 regressions; TEST_ONLY fixtures, not real-project certification.

Authored for a separately approved Python/TestClient run. No model or server.
Internal projection counterexamples below are labelled separately from API cases.
"""
import hashlib
import json
import sqlite3
from copy import deepcopy

import pytest

from app.p2.contract import ErrorEnvelope
from app.p2.material_claims import project
from test_p2_contract import (
    setup as base_setup, create, material_body, variant,
)
from test_p2_preliminary import setup, admit, MIT
from test_task33_material_claims import get, inputs, declaration_facts


def subject(value):
    return value['resource_id'], value['version']


def logical_databases(root):
    """Capture all logical values, not just row counts; only fixture databases."""
    result = {}
    for path in sorted(root.glob('*.db')):
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
            result[path.name] = tuple(db.iterdump())
    return result


def assert_old_and_databases_unchanged(h, old, snapshot):
    c, _, base, _, root = h
    reply = c.get(base + '/results/' + old['result_id'],
                  params={'assessment_version': old['binding']['assessment_version']})
    assert reply.status_code == 200 and reply.json() == old
    assert logical_databases(root) == snapshot


def assert_reference_graph(h, result, view):
    """Check the public graph against saved rows and scan provenance edges."""
    svc = h[1].state.p2_service
    run, _, _, resources = svc.context(result['binding']['scan_id'], result['binding']['assessment_id'])
    scan_evidence = {e.id: e for e in run.evidence}
    licenses = {x.id: x for x in run.licenses}
    rows = {subject(r['subject']): r for r in result['resources']}
    declarations = {subject(x['subject']): x for x in view['declaration_observations']}
    materials = {m['material_id']: m for m in view['materials']}
    clauses = {c['clause_id']: c for m in view['materials'] for c in m['clauses']}
    claims = {c['claim_id']: c for c in view['claims']}
    sources = {s['source_observation_id']: s for s in view['source_observations']}
    assert len(rows) == len(result['resources'])
    assert set(declarations) == set(rows)
    assert len(declarations) == len(view['declaration_observations'])
    assert len(materials) == len(view['materials']) and set(materials) == set(result['material_ids'])
    assert len(clauses) == sum(len(m['clauses']) for m in view['materials'])
    assert len(claims) == len(view['claims']) and len(sources) == len(view['source_observations'])
    assert len({subject(s['subject']) for s in sources.values()}) == len(sources)
    assert view['result_id'] == result['result_id'] and view['result_sha256'] == result['result_sha256']
    assert view['revision'] == result['revision'] and view['binding'] == result['binding']
    assert view['formal_effect'] == 'none' and view['applicability_review'] == 'NOT_SIGNED'
    assert view['model_calls'] == 0

    def check_evidence(refs, row):
        assert len({r['evidence_id'] for r in refs}) == len(refs)
        for ref in refs:
            eid = ref['evidence_id']
            assert eid in row['evidence_ids'] and eid in scan_evidence
            assert ref['source_sha256'] == row['evidence_source_hashes'].get(eid)
            if ref['source_sha256'] is not None:
                assert scan_evidence[eid].content_hash.algorithm == 'sha256'
                assert scan_evidence[eid].content_hash.value == ref['source_sha256']

    for key, declaration in declarations.items():
        row = rows[key]; resource = resources[key[0]]
        lic = licenses.get(resource.license_expression_id)
        expected = set()
        if lic is not None:
            assert declaration['expression'] == lic.expression
            assert declaration['normalized_ids'] == lic.normalized_ids
            expected = {eid for eid in lic.evidence_ids
                        if eid in resource.evidence_ids and eid in row['evidence_ids']
                        and eid in scan_evidence and scan_evidence[eid].content_hash is not None
                        and scan_evidence[eid].content_hash.algorithm == 'sha256'
                        and row['evidence_source_hashes'].get(eid) == scan_evidence[eid].content_hash.value}
        assert set(declaration['declaration_evidence_ids']) == expected
        assert {r['evidence_id'] for r in declaration['evidence']} == expected
        check_evidence(declaration['evidence'], row)
        if declaration['evidence_status'] == 'COMPLETE':
            assert lic is not None and expected and expected == set(lic.evidence_ids)

    with svc.store.connection() as db:
        for mid, material in materials.items():
            row = rows[subject(material['subject'])]
            saved = svc.store.get(db, 'material', mid, result['binding']['scan_id'], result['binding']['assessment_id'])
            raw = svc.store.material_bytes(db, saved)
            assert saved['subject'] == material['subject'] and mid in row['material_ids']
            assert saved['source_sha256'] == material['source_sha256'] == hashlib.sha256(raw).hexdigest()
            assert material['byte_count'] == len(raw)
            assert {r['evidence_id'] for r in material['evidence']} == set(saved['evidence_ids'])
            check_evidence(material['evidence'], row)
            for clause in material['clauses']:
                assert clause['material_id'] == mid and clause['material_sha256'] == material['source_sha256']
                chunk = raw[clause['byte_start']:clause['byte_end']]
                assert chunk.decode('utf-8') == clause['quote']
                assert hashlib.sha256(chunk).hexdigest() == clause['quote_sha256']
                assert clause['line_start'] == raw[:clause['byte_start']].count(b'\n') + 1

    reachable = set()
    assert len({(subject(a['subject']), a['usage']) for a in view['advice']}) == len(view['advice'])
    for advice in view['advice']:
        key = subject(advice['subject']); row = rows[key]; declaration = declarations[key]
        assert advice['reasons'] and advice['limitations']
        assert advice['saved_value'] is result['usage'][advice['usage']]
        assert advice['claim_ids'] and len(set(advice['claim_ids'])) == len(advice['claim_ids'])
        for cid in advice['claim_ids']:
            reachable.add(cid); claim = claims[cid]
            assert claim['subject'] == advice['subject'] and claim['usage'] == advice['usage']
            assert claim['state'] == advice['state'] and claim['conditions'] == advice['conditions']
            assert claim['formal_effect'] == 'none'
            scoped = {mid for mid, m in materials.items() if subject(m['subject']) == key}
            assert set(claim['material_ids']) == scoped
            assert set(claim['clause_ids']) == {c['clause_id'] for mid in scoped for c in materials[mid]['clauses']}
            check_evidence(claim['evidence'], row)
            expected_eids = set(declaration['declaration_evidence_ids'])
            expected_eids.update(r['evidence_id'] for mid in scoped for r in materials[mid]['evidence'])
            for counter in claim['counter_evidence']:
                assert set(counter['material_ids']) <= scoped
                assert set(counter['declaration_evidence_ids']) <= set(declaration['declaration_evidence_ids'])
                expected = {r['evidence_id'] for mid in counter['material_ids'] for r in materials[mid]['evidence']}
                expected.update(counter['declaration_evidence_ids'])
                assert set(counter['evidence_ids']) == expected
                assert set(counter['source_observation_ids']).isdisjoint(scan_evidence)
                for sid in counter['source_observation_ids']:
                    assert sources[sid]['subject'] == claim['subject']
                if counter['code'] == 'SPDX_TEXT_CONFLICT':
                    assert declaration['expression'] != 'MIT'
                    assert counter['material_ids'] and all(materials[mid]['text_license'] == 'MIT' for mid in counter['material_ids'])
                    assert set(counter['declaration_evidence_ids']) == set(declaration['declaration_evidence_ids'])
                elif counter['code'] == 'SPDX_NORMALIZATION_CONFLICT':
                    assert declaration['expression'] == 'MIT' and declaration['normalized_ids'] != ['MIT']
                    assert counter['material_ids'] == []
                elif counter['code'] == 'BOUND_LICENSE_BYTES_CONFLICT':
                    assert counter['declaration_evidence_ids'] == []
                    assert len({materials[mid]['source_sha256'] for mid in counter['material_ids']}) > 1
                elif counter['code'] == 'NOTICE_REQUIRES_REVIEW':
                    assert counter['declaration_evidence_ids'] == []
                    assert bool(counter['material_ids']) != bool(counter['source_observation_ids'])
                expected_eids.update(counter['evidence_ids'])
            assert {r['evidence_id'] for r in claim['evidence']} == expected_eids
        if advice['state'] == 'SUPPORT':
            assert advice['saved_value'] is True and advice['conditions']
            assert declaration['evidence_status'] == 'COMPLETE'
            assert declaration['expression'] == 'MIT' and declaration['normalized_ids'] == ['MIT']
            assert any(s['subject'] == advice['subject'] and s['notice_status'] == 'ABSENT_COMPLETE'
                       for s in sources.values())
            assert any(materials[mid]['adoption_state'] == 'CONDITIONAL_TEXT_BASIS'
                       for cid in advice['claim_ids'] for mid in claims[cid]['material_ids'])
    assert reachable == set(claims)


@pytest.mark.parametrize('case', ['complete', 'excerpt', 'spdx_conflict', 'notice'])
def test_saved_api_graph_has_exact_references_and_explicit_limits(setup, case):
    h = setup
    if case == 'spdx_conflict':
        def change(p):
            p['licenses'][0].update(expression='GPL-3.0-only', normalized_ids=['GPL-3.0-only'], verification_status='pending')
        h = variant(h, change)
    old, result, _, _, _ = admit(h, completeness='EXCERPT' if case == 'excerpt' else 'FULL_TEXT_CLAIMED')
    if case == 'notice':
        body = material_body(result, b'SYNTHETIC_TEST_ONLY notice', key='quality-notice')
        body.update(filename='NOTICE', completeness='FULL_TEXT_CLAIMED')
        response = h[0].post(h[2] + '/materials', json=body)
        assert response.status_code == 201
        result = response.json()['result']
    before = logical_databases(h[4]); view = get(h, result)
    assert_reference_graph(h, result, view)
    expected = {'complete': 'SUPPORT', 'excerpt': 'UNKNOWN', 'spdx_conflict': 'COUNTER_EVIDENCE', 'notice': 'UNKNOWN'}[case]
    assert next(a for a in view['advice'] if a['usage'] == 'commercial')['state'] == expected
    assert next(a for a in view['advice'] if a['usage'] == 'modified')['state'] == 'NOT_COVERED'
    if case == 'excerpt':
        assert all(m['adoption_state'] == 'OBSERVATION_ONLY' for m in view['materials'])
    assert_old_and_databases_unchanged(h, old, before)


def test_projection_undeclared_use_and_restriction_keep_graph_boundaries(setup):
    """Internal defensive projections, not claims of publicly reachable writes."""
    _, result, _, _, _ = admit(setup)
    resources, materials, root, pin = inputs(setup, result)
    before = logical_databases(setup[4])
    for usage_value, assertion, expected in [(None, None, 'UNKNOWN'), (True, 'NOT_FULFILLED', 'RESTRICTION')]:
        candidate = deepcopy(result)
        candidate['usage']['commercial'] = usage_value
        if assertion:
            candidate['resources'][0]['user_assertions']['OBLIGATION_FULFILLMENT_IN_DELIVERY'] = assertion
        view = project(candidate, resources, materials, root, pin,
                       {rid: 'MIT' for rid in resources}, declaration_facts=declaration_facts(setup, result))
        assert_reference_graph(setup, candidate, view)
        item = next(a for a in view['advice'] if a['usage'] == 'commercial')
        assert item['state'] == expected
        assert item['reasons'] == (['USAGE_UNDECLARED'] if usage_value is None else ['USER_REPORTS_DELIVERY_OBLIGATION_UNFULFILLED'])
    assert_old_and_databases_unchanged(setup, result, before)


def test_pending_scan_declaration_is_not_relabelled_as_authenticated(setup):
    def pending(p):
        p['licenses'][0]['verification_status'] = 'pending'
        for e in p['evidence']:
            if e['id'] in p['licenses'][0]['evidence_ids']:
                e['verification_status'] = 'pending'
    h = variant(setup, pending)
    _, result, _, _, _ = admit(h)
    view = get(h, result); assert_reference_graph(h, result, view)
    svc = h[1].state.p2_service
    run, _, _, _ = svc.context(result['binding']['scan_id'], result['binding']['assessment_id'])
    declaration = view['declaration_observations'][0]
    assert declaration['evidence_status'] == 'COMPLETE'
    assert all(e.verification_status.value == 'pending' for e in run.evidence
               if e.id in declaration['declaration_evidence_ids'])
    assert view['formal_effect'] == 'none' and view['applicability_review'] == 'NOT_SIGNED'


@pytest.fixture
def two_resources(base_setup):
    """Two existing independent provenance edges, not nonexistent foreign IDs."""
    def add(p):
        original = p['components'][0]
        other = deepcopy(original)
        other.update(id='cmp_123e4567-e89b-12d3-a456-426614174777', name='quality-other',
                     version='99.0.0', purl=None, source_url=None)
        lic = deepcopy(next(x for x in p['licenses'] if x['id'] == original['license_expression_id']))
        lic['id'] = 'lic_123e4567-e89b-12d3-a456-426614174777'
        ev = deepcopy(next(x for x in p['evidence'] if x['id'] == lic['evidence_ids'][0]))
        ev.update(id='evd_123e4567-e89b-12d3-a456-426614174777', excerpt='SYNTHETIC_TEST_ONLY second resource license')
        ev['content_hash'] = {'algorithm': 'sha256', 'value': hashlib.sha256(ev['excerpt'].encode()).hexdigest()}
        lic['evidence_ids'] = [ev['id']]
        other.update(license_expression_id=lic['id'], evidence_ids=[ev['id']])
        p['licenses'].append(lic); p['evidence'].append(ev); p['components'].append(other)
    return variant(base_setup, add)


@pytest.mark.parametrize('mutation,code', [('resource', 'p2_evidence_wrong_resource'), ('version', 'p2_resource_version_conflict')])
def test_existing_foreign_evidence_or_wrong_version_cannot_change_any_row(two_resources, mutation, code):
    h = two_resources; old = create(h); body = material_body(old, MIT)
    a = next(r for r in old['resources'] if r['subject'] == body['subject'])
    b = next(r for r in old['resources'] if r['subject'] != body['subject'])
    eid = next(e for e in a['evidence_ids'] if e not in b['evidence_ids'])
    body['evidence_ids'] = [eid]
    svc = h[1].state.p2_service
    run, _, _, _ = svc.context(old['binding']['scan_id'], old['binding']['assessment_id'])
    assert eid in {e.id for e in run.evidence} and b['evidence_ids']
    if mutation == 'resource':
        body['subject'] = b['subject']
    else:
        body['subject'] = {**a['subject'], 'version': b['subject']['version']}
    before = logical_databases(h[4])
    reply = h[0].post(h[2] + '/materials', json=body)
    assert reply.status_code == 409 and reply.json()['error']['code'] == code
    assert_old_and_databases_unchanged(h, old, before)


def test_material_revision_reuses_only_unaffected_resource_and_preserves_old_graph(two_resources):
    h = two_resources; old = create(h); old_view = get(h, old)
    body = material_body(old, MIT); affected = body['subject']['resource_id']
    response = h[0].post(h[2] + '/materials', json=body)
    assert response.status_code == 201
    new = response.json()['result']; new_view = get(h, new)
    before_rows = {r['subject']['resource_id']: r for r in old['resources']}
    assert new['revision'] == old['revision'] + 1 and new['previous_result_id'] == old['result_id']
    assert new['recomputed_resource_ids'] == [affected]
    assert set(new['reused_resource_ids']) == set(before_rows) - {affected}
    for row in new['resources']:
        if row['subject']['resource_id'] != affected:
            assert row == before_rows[row['subject']['resource_id']]
    assert_reference_graph(h, new, new_view)
    assert get(h, old) == old_view
    for claim in new_view['claims']:
        if claim['subject']['resource_id'] != affected:
            assert claim['material_ids'] == [] and claim['clause_ids'] == []
    snapshot = logical_databases(h[4])
    assert_old_and_databases_unchanged(h, old, snapshot)


@pytest.mark.parametrize('status,code', [(404, 'p2_not_found'), (409, 'p2_resource_version_conflict'), (422, 'p2_request_invalid')])
def test_expected_api_failure_envelopes_keep_values_and_old_result(base_setup, status, code):
    h = base_setup; old = create(h); before = logical_databases(h[4])
    if status == 404:
        response = h[0].get(h[2] + '/results/p2res_missing/material-claims?assessment_version=1')
    else:
        body = material_body(old, MIT)
        if status == 409:
            body['subject'] = {**body['subject'], 'version': '99.0.0'}
        else:
            body['unexpected_quality_field'] = 'TEST_ONLY_MUST_NOT_ECHO'
        response = h[0].post(h[2] + '/materials', json=body)
    assert response.status_code == status
    envelope = ErrorEnvelope.model_validate(response.json())
    assert envelope.error.code == code and envelope.error.request_id
    assert 'TEST_ONLY_MUST_NOT_ECHO' not in response.text
    assert_old_and_databases_unchanged(h, old, before)


@pytest.mark.parametrize('error_type,status,code', [(OSError, 503, 'p2_storage_unavailable'), (RuntimeError, 500, 'internal_error')])
def test_mid_transaction_failure_has_no_partial_material_or_result(base_setup, monkeypatch, error_type, status, code):
    h = base_setup; old = create(h); before = logical_databases(h[4])
    store = h[1].state.p2_service.store; put = store.put
    sentinel = 'TEST_ONLY_PRIVATE_PATH_AND_SQL_SENTINEL'
    def fail(db, kind, *args):
        if kind == 'summary':
            raise error_type(sentinel)
        return put(db, kind, *args)
    monkeypatch.setattr(store, 'put', fail)
    response = h[0].post(h[2] + '/materials', json=material_body(old, MIT))
    assert response.status_code == status and response.json()['error']['code'] == code
    assert sentinel not in response.text
    # Generic 500 intentionally uses the existing P0 DTO, not a new P2 policy.
    error = response.json()['error']
    assert set(error) == {'code', 'message', 'request_id', 'details'} and error['request_id']
    if status == 503:
        ErrorEnvelope.model_validate(response.json())
    assert_old_and_databases_unchanged(h, old, before)


def test_evaluation_package_409_schema_and_actual_body_agree(base_setup):
    h = base_setup; old = create(h); before = logical_databases(h[4])
    template = '/api/v1/scans/{scan_id}/assessments/{assessment_id}/p2/results/{result_id}/evaluation-package'
    schema = h[1].openapi()
    ref = schema['paths'][template]['get']['responses']['409']['content']['application/json']['schema']['$ref']
    assert 'p2' in ref and 'ErrorEnvelope' in ref
    assert ref.rsplit('/', 1)[-1] in schema['components']['schemas']
    response = h[0].get(h[2] + '/results/' + old['result_id'] + '/evaluation-package', params={'assessment_version': 2})
    assert response.status_code == 409
    envelope = ErrorEnvelope.model_validate(response.json())
    assert envelope.error.code == 'p2_assessment_version_conflict'
    assert_old_and_databases_unchanged(h, old, before)
