"""TASK39 isolated API, source-binding and revision regression cases."""
import base64
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tarfile
from uuid import uuid4
import zipfile

import pytest

from app.domain.usage import UsageDeclaration
from app.p2b.material_claims import parse_claim_material
from test_a4_local_zip_pipeline import _queued, _run
from test_p2_contract import answer_body, create, material_body, seed, setup as base_setup, variant
from test_p2_preliminary import MIT, setup
from test_task33_material_claims import get
from test_task37_real_material_chain import database_state

APACHE = (Path(__file__).resolve().parents[3] / 'LICENSE').read_bytes()
NOTICE = 'TEST_ONLY attribution\nCopyright 2026 示例\n'.encode()
NAME = 'task39-apache-test'
VERSION = '1.2.3'
USES = {'commercial', 'distributed', 'modified'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pinned_source(directory, license_id, license_raw, notice):
    directory.mkdir()
    package = {'name': NAME, 'version': VERSION, 'license': license_id}
    files = {'package/package.json': json.dumps(package).encode(), 'package/LICENSE': license_raw}
    if notice is not None:
        files['package/NOTICE'] = notice
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as archive:
        for name, content in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    raw = stream.getvalue()
    tar_url = f'https://registry.npmjs.org/{NAME}/-/{NAME}-{VERSION}.tgz'
    metadata = json.dumps({**package, 'dist': {'tarball': tar_url, 'shasum': hashlib.sha1(raw).hexdigest(),
        'integrity': 'sha512-' + base64.b64encode(hashlib.sha512(raw).digest()).decode()}}).encode()
    profile = json.dumps({'schema_version': 'openguard-public-npm-source-profile/1', 'data_scope': 'TEST_ONLY',
        'packages': [{'package': NAME, 'version': VERSION, 'metadata_file': 'metadata.json',
            'metadata_sha256': sha(metadata), 'tarball_file': 'source.tgz', 'tarball_sha256': sha(raw),
            'license_file': 'LICENSE', 'license_sha256': sha(license_raw), 'member': 'package/LICENSE',
            'metadata_url': f'https://registry.npmjs.org/{NAME}/{VERSION}', 'tarball_url': tar_url,
            'fetched_at': '2026-11-22T00:00:00Z', 'applicability_review': 'NOT_SIGNED'}]}).encode()
    for name, content in [('metadata.json', metadata), ('source.tgz', raw), ('LICENSE', license_raw), ('profile.json', profile)]:
        (directory / name).write_bytes(content)
    return sha(profile)


def upload(h, parent, subject, raw, filename='LICENSE'):
    row = next(row for row in parent['resources'] if row['subject'] == subject)
    body = material_body(parent, raw, key=f'task39-{filename}-{parent["revision"]}')
    body.update(subject=subject, evidence_ids=sorted(row['evidence_source_hashes']), filename=filename,
                completeness='FULL_TEXT_CLAIMED', source_description='TEST_ONLY exact archive material')
    reply = h[0].post(h[2] + '/materials', json=body)
    assert reply.status_code == 201, reply.text
    return reply.json()['result']


def assert_impact(before_result, before_view, result, view):
    impact = view['incremental_impact']
    assert impact['mode'] == 'INCREMENTAL_DERIVED'
    assert impact['previous_result_id'] == before_result['result_id']
    assert impact['previous_revision'] == before_result['revision']
    assert impact['previous_view_id'] == before_view['view_id']
    assert impact['affected_resource_ids'] == result['recomputed_resource_ids']
    assert impact['unchanged_resource_ids'] == result['reused_resource_ids']
    assert impact['added_material_ids'] == sorted(set(result['material_ids']) - set(before_result['material_ids']))
    assert impact['added_answer_ids'] == sorted(set(result['answer_ids']) - set(before_result['answer_ids']))
    assert impact['unchanged_claims_verified'] is True
    for claim in view['claims']:
        rid = claim['subject']['resource_id']
        if rid in impact['unchanged_resource_ids']:
            previous = next(c for c in before_view['claims'] if (c['subject'], c['usage']) == (claim['subject'], claim['usage']))
            assert {k: v for k, v in claim.items() if k != 'claim_id'} == {k: v for k, v in previous.items() if k != 'claim_id'}
            assert claim['claim_id'] in impact['reused_claim_ids']
        else:
            assert claim['claim_id'] in impact['recomputed_claim_ids']


@pytest.mark.parametrize('raw', [APACHE, APACHE.replace(b'\n', b'\r\n')], ids=['lf', 'crlf'])
def test_complete_apache_exact_byte_spans(raw):
    parsed = parse_claim_material(raw, 'LICENSE')
    assert parsed['parse_state'] == 'MATCHED_APACHE_2_0'
    assert parsed['text_license'] == 'Apache-2.0'
    assert parsed['license_version'] == '2.0'
    assert parsed['version_scope'] == 'LICENSE_VERSION_AND_RESOURCE_VERSION'
    assert [s['kind'] for s in parsed['spans']].count('condition') == 4
    assert [s['kind'] for s in parsed['spans']].count('permission') == 2
    assert {s['kind'] for s in parsed['spans']} >= {'license_identifier', 'warranty'}
    for span in parsed['spans']:
        start, end = span['byte_start'], span['byte_end']
        assert raw[start:end].decode() == span['quote']
        assert sha(raw[start:end]) == span['quote_sha256']
        assert span['line_start'] == raw[:start].count(b'\n') + 1
        assert span['line_end'] == raw[:end - 1].count(b'\n') + 1


@pytest.mark.parametrize('raw', [b'Apache License, Version 2.0', APACHE[:-220], APACHE + b'\x00', APACHE + b'\xff'],
                         ids=['title-only', 'truncated', 'nul', 'invalid-utf8'])
def test_incomplete_apache_never_produces_text_spans(raw):
    parsed = parse_claim_material(raw, 'LICENSE')
    assert parsed['parse_state'] not in {'MATCHED_MIT', 'MATCHED_APACHE_2_0'}
    assert parsed['spans'] == []


@pytest.mark.parametrize('declared,upload_license,archive_notice,upload_notice,pinned,expected,reason', [
    ('Apache-2.0', APACHE, None, None, True, 'SUPPORT', 'PINNED_RELEASE_AND_COMPLETE_APACHE_2_0_CONDITIONAL_TEXT'),
    ('Apache-2.0', APACHE, NOTICE, None, True, 'UNKNOWN', 'NOTICE_REQUIRES_REVIEW'),
    ('Apache-2.0', APACHE, NOTICE, b'TEST_ONLY different notice', True, 'COUNTER_EVIDENCE', 'BOUND_NOTICE_BYTES_CONFLICT'),
    ('Apache-2.0', APACHE, NOTICE, NOTICE, True, 'UNKNOWN', 'NOTICE_MATCHED_REQUIRES_HUMAN_OBLIGATION_REVIEW'),
    ('Apache-2.0', APACHE, None, NOTICE, True, 'UNKNOWN', 'NOTICE_REQUIRES_REVIEW'),
    ('MIT', APACHE, None, None, True, 'COUNTER_EVIDENCE', 'SPDX_TEXT_CONFLICT'),
    ('Apache-2.0', MIT, None, None, True, 'COUNTER_EVIDENCE', 'SPDX_TEXT_CONFLICT'),
    ('Apache-2.0', APACHE.replace(b'\n', b'\r\n'), None, None, True, 'UNKNOWN', 'SOURCE_OR_EVIDENCE_BINDING_NOT_ESTABLISHED'),
    ('Apache-2.0', APACHE, None, None, False, 'UNKNOWN', 'SOURCE_OR_EVIDENCE_BINDING_NOT_ESTABLISHED'),
    ('Apache-2.0 AND MIT', APACHE, None, None, True, 'UNKNOWN', 'SOURCE_OR_EVIDENCE_BINDING_NOT_ESTABLISHED'),
], ids=['absent', 'not-uploaded', 'mismatch', 'matched-review', 'extra-notice', 'mit-apache-conflict',
        'apache-mit-conflict', 'different-bytes', 'unconfigured-source', 'multi-license'])
def test_pinned_archive_asgi_notice_and_license_conflicts(base_setup, declared, upload_license,
                                                          archive_notice, upload_notice, pinned, expected, reason):
    c, app, _, _, root = base_setup
    source_license = 'MIT' if declared == 'MIT' else 'Apache-2.0'
    raw = MIT if source_license == 'MIT' else APACHE
    zip_path = root / 'task39-test-only.zip'
    with zipfile.ZipFile(zip_path, 'w') as scanned:
        scanned.writestr('package.json', json.dumps({'name': NAME, 'version': VERSION,
                                                   'license': declared, 'dependencies': {'role-check': '1.0.0'}}))
        scanned.writestr('LICENSE', raw)
        if archive_notice is not None:
            scanned.writestr('NOTICE', archive_notice)
    registry, scanned = _run(root, zip_path, _queued(zip_path, index=3901))
    try:
        component = next(item for item in scanned.run.components if item.name == NAME)
        usage = UsageDeclaration(commercial=True, distributed=True, modified=True, network_service=False,
                                 training=False, redistributed_assets=False, source_disclosure=False)
        assessment = seed(app, scanned.run, usage)
        base = f'/api/v1/scans/{assessment.scan_id}/assessments/{assessment.id}/p2'
        binding_reply = c.get(base + '/binding')
        assert binding_reply.status_code == 200, binding_reply.text
        h = c, app, base, {'binding': binding_reply.json(), 'expected_revision': 0,
                          'parent_result_id': None, 'idempotency_key': 'task39-create'}, root
        if pinned:
            source = root / 'task39-pinned-source'
            service = app.state.p2_service
            service.public_source_root = str(source)
            service.public_source_profile_sha256 = pinned_source(source, source_license, raw, archive_notice)
        first = create(h)
        subject = next(row['subject'] for row in first['resources'] if row['subject']['resource_id'] == component.id)
        first_view = get(h, first)
        second = upload(h, first, subject, upload_license)
        second_view = get(h, second)
        result = upload(h, second, subject, upload_notice, 'NOTICE') if upload_notice is not None else second
        before_get = database_state(root)
        view = get(h, result)
        assert view['schema_version'] == 'openguard-material-claims/4'
        assert view['rule_version'] == 'mit-apache2-bound-claim/4'
        relevant = [entry for entry in view['advice'] if entry['subject'] == subject]
        assert {entry['usage'] for entry in relevant} == USES
        assert all(entry['state'] == expected and reason in entry['reasons'] for entry in relevant), relevant
        if declared == 'Apache-2.0 AND MIT':
            # The frozen root-package scanner admits one canonical identifier only.
            declaration = next(entry for entry in view['declaration_observations'] if entry['subject'] == subject)
            assert declaration['evidence_status'] == 'UNKNOWN'
        if expected == 'SUPPORT':
            assert all(all(clause in ' '.join(entry['conditions']) for clause in ('4(a)', '4(b)', '4(c)')) for entry in relevant)
        if expected == 'COUNTER_EVIDENCE':
            assert all(any(item['code'] == reason for item in claim['counter_evidence'])
                       for claim in view['claims'] if claim['subject'] == subject)
        if reason == 'NOTICE_MATCHED_REQUIRES_HUMAN_OBLIGATION_REVIEW':
            notice = next(entry for entry in view['materials'] if entry['filename'] == 'NOTICE')
            assert notice['source_sha256'] == sha(NOTICE) and notice['clauses'][0]['quote'].encode() == NOTICE
            assert all(any('4(d)' in line for line in entry['conditions'] + entry['limitations']) for entry in relevant)
        assert_impact(first, first_view, second, second_view)
        assert first_view['incremental_impact']['mode'] == 'INITIAL_RESULT'
        assert first_view['incremental_impact']['previous_result_id'] is None
        if upload_notice is not None:
            assert_impact(second, second_view, result, view)
        assert get(h, first) == first_view and get(h, second) == second_view
        assert get(h, result) == view
        assert database_state(root) == before_get
        if expected == 'SUPPORT':
            obligation = next(q for q in result['questions'] if q['question_code'] == 'OBLIGATION_FULFILLMENT_IN_DELIVERY')
            reply = c.post(base + '/answers', json={
                'binding': result['binding'], 'expected_revision': result['revision'],
                'parent_result_id': result['result_id'], 'idempotency_key': 'task39-obligation-unfulfilled',
                'question_id': obligation['question_id'], 'question_code': obligation['question_code'],
                'answer_code': 'NOT_FULFILLED', 'subjects': [subject], 'evidence_ids': [],
            })
            assert reply.status_code == 201, reply.text
            receipt = reply.json()
            restricted = receipt['result']
            stable = database_state(root)
            restricted_view = get(h, restricted)
            assert_impact(result, view, restricted, restricted_view)
            assert all(entry['state'] == 'RESTRICTION' for entry in restricted_view['advice'] if entry['subject'] == subject)
            changes = restricted_view['incremental_impact']['changed_claims']
            assert {change['usage'] for change in changes} == USES
            assert all(change['previous_state'] == 'SUPPORT' and change['current_state'] == 'RESTRICTION'
                       and change['trigger_answer_ids'] == [receipt['answer']['answer_id']] for change in changes)
            assert get(h, result) == view and database_state(root) == stable
    finally:
        registry.close()


@pytest.mark.parametrize('role_case,state,conflicts', [
    ('manifest', 'observed', []), ('lock', 'inferred', []),
    ('conflict', 'unknown', ['lock_version_conflict']), ('license-field', 'unknown', []),
])
def test_bound_b58_role_and_conflicts_in_asgi(setup, role_case, state, conflicts):
    evidence_id = 'evd_' + str(uuid4())
    def attach(payload):
        role_evidence = deepcopy(payload['evidence'][0])
        path = {
            'manifest': 'package.json:/dependencies/example-package',
            'license-field': 'package.json:/license',
        }.get(role_case, 'package-lock.json:/packages/node_modules~1example-package/version')
        role_evidence.update(id=evidence_id, kind='manifest_field', locator=path,
                             excerpt=json.dumps(payload['components'][0]['version']),
                             detected_by='manifest_parser', verification_status='pending',
                             producer={'type': 'parser', 'name': 'openguard.javascript-manifest', 'version': '1'},
                             content_hash={'algorithm': 'sha256', 'value': sha(path.encode())})
        payload['evidence'].append(role_evidence)
        payload['components'][0]['evidence_ids'].append(evidence_id)
        if conflicts:
            payload['errors'].append({'code': conflicts[0], 'stage': 'normalize', 'message': 'TEST_ONLY scope conflict',
                                      'recoverable': True, 'evidence_ids': [evidence_id]})
    h = variant(setup, attach)
    first = create(h)
    result = upload(h, first, first['resources'][0]['subject'], MIT)
    view = get(h, result)
    material, = view['materials']
    assert material['role'] == ('unknown' if state == 'unknown' else 'dependency')
    assert material['role_state'] == state
    assert material['role_conflicts'] == conflicts
    if state != 'unknown':
        assert material['role_basis_evidence_ids'] == [evidence_id]
    else:
        assert material['role_basis_evidence_ids'] == []
    assert not any(entry['state'] == 'SUPPORT' for entry in view['advice'])


def test_answer_impact_keeps_unaffected_resource_and_old_view(base_setup, monkeypatch):
    def mutate(payload):
        other = deepcopy(payload['components'][0])
        other.update(id='cmp_' + str(uuid4()), license_expression_id=None,
                     evidence_ids=[payload['evidence'][0]['id']])
        payload['components'].append(other)
    h = variant(base_setup, mutate)
    first = create(h)
    first_view = get(h, first)
    body = answer_body(first, key='task39-answer-impact')
    response = h[0].post(h[2] + '/answers', json=body)
    assert response.status_code == 201, response.text
    other = response.json()['result']
    assert len(other['reused_resource_ids']) == 1
    before_get = database_state(h[4])
    view = get(h, other)
    assert_impact(first, first_view, other, view)
    assert view['incremental_impact']['added_answer_ids'] == other['answer_ids']
    assert get(h, first) == first_view
    assert database_state(h[4]) == before_get

    from app.p2 import material_claims as projection
    original = projection.project_core
    reused = set(other['reused_resource_ids'])

    def corrupt_unaffected_projection(result, *args, **kwargs):
        payload = original(result, *args, **kwargs)
        if result['result_id'] == other['result_id']:
            claim = next(c for c in payload['claims'] if c['subject']['resource_id'] in reused)
            claim['conditions'] = ['TEST_ONLY inconsistent unaffected clause condition']
        return payload

    monkeypatch.setattr(projection, 'project_core', corrupt_unaffected_projection)
    reply = h[0].get(h[2] + '/results/' + other['result_id'] + '/material-claims', params={'assessment_version': 1})
    assert reply.status_code == 503 and reply.json()['error']['code'] == 'p2_claim_integrity_error'
    assert get(h, first) == first_view and database_state(h[4]) == before_get
