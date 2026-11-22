"""TASK39 isolated API, source-binding and revision regression cases."""
import base64
from contextlib import closing
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
from uuid import uuid4
import zipfile

import pytest

from app.domain.usage import UsageDeclaration
from app.p2b.material_claims import parse_claim_material
from test_a4_local_zip_pipeline import _queued, _run
from test_p1_notice_lifecycle_ingestion import env as notice_env
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


def pinned_source(directory, license_id, license_raw, notice, *, name=NAME, version=VERSION):
    directory.mkdir()
    package = {'name': name, 'version': version, 'license': license_id}
    files = {'package/package.json': json.dumps(package).encode(), 'package/LICENSE': license_raw}
    if notice is not None:
        files['package/NOTICE'] = notice
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as archive:
        for member_path, content in files.items():
            member = tarfile.TarInfo(member_path)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    raw = stream.getvalue()
    tar_url = f'https://registry.npmjs.org/{name}/-/{name.rsplit("/", 1)[-1]}-{version}.tgz'
    metadata = json.dumps({**package, 'dist': {'tarball': tar_url, 'shasum': hashlib.sha1(raw).hexdigest(),
        'integrity': 'sha512-' + base64.b64encode(hashlib.sha512(raw).digest()).decode()}}).encode()
    profile = json.dumps({'schema_version': 'openguard-public-npm-source-profile/1', 'data_scope': 'TEST_ONLY',
        'packages': [{'package': name, 'version': version, 'metadata_file': 'metadata.json',
            'metadata_sha256': sha(metadata), 'tarball_file': 'source.tgz', 'tarball_sha256': sha(raw),
            'license_file': 'LICENSE', 'license_sha256': sha(license_raw), 'member': 'package/LICENSE',
            'metadata_url': f'https://registry.npmjs.org/{name}/{version}', 'tarball_url': tar_url,
            'fetched_at': '2026-11-22T00:00:00Z', 'applicability_review': 'NOT_SIGNED'}]}).encode()
    for filename, content in [('metadata.json', metadata), ('source.tgz', raw), ('LICENSE', license_raw), ('profile.json', profile)]:
        (directory / filename).write_bytes(content)
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


# The inline texts keep ordinary offline runs self-contained. TASK43's acceptance
# run supplies the archived package corpus and verifies its original material
# digests before using it.
_TASK43_ISC = b'''Copyright 2026 TEST_ONLY

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR
IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
'''
_TASK43_BSD_INTRO = (
    b"Redistribution and use in source and binary forms, with or without "
    b"modification, are permitted provided that the following conditions are met:"
)
_TASK43_BSD_SOURCE = (
    b"Redistributions of source code must retain the above copyright notice, "
    b"this list of conditions and the following disclaimer."
)
_TASK43_BSD_BINARY = (
    b"Redistributions in binary form must reproduce the above copyright notice, "
    b"this list of conditions and the following disclaimer in the documentation "
    b"and/or other materials provided with the distribution."
)
_TASK43_BSD_ENDORSE = (
    b"Neither the names of the Mozilla Foundation nor the names of project "
    b"contributors may be used to endorse or promote products derived from this "
    b"software without specific prior written permission."
)
_TASK43_BSD_WARRANTY = (
    b'THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND '
    b'ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED '
    b'WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE '
    b'DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE '
    b'FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL '
    b'DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR '
    b'SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER '
    b'CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, '
    b'OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE '
    b'OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.'
)
_TASK43_BSD2 = b'\n\n'.join((
    b'Copyright (c) 2026 TEST_ONLY', _TASK43_BSD_INTRO,
    b'1. ' + _TASK43_BSD_SOURCE, b'2. ' + _TASK43_BSD_BINARY, _TASK43_BSD_WARRANTY,
))
_TASK43_BSD3 = b'\n\n'.join((
    b'Copyright (c) 2009-2011, Mozilla Foundation and contributors\nAll rights reserved.',
    _TASK43_BSD_INTRO, b'* ' + _TASK43_BSD_SOURCE, b'* ' + _TASK43_BSD_BINARY,
    b'* ' + _TASK43_BSD_ENDORSE, _TASK43_BSD_WARRANTY,
))
_TASK43_MIT_UNTITLED = MIT.split(b'\n\n', 1)[1]
_TASK43_APACHE_BRACES = APACHE.replace(b'brackets "[]"', b'brackets "{}"').replace(
    b'[yyyy] [name of copyright owner]', b'{yyyy} {name of copyright owner}',
)
_TASK43_MATERIALS = {
    'http-server': ('bundle-tree', 'MIT', _TASK43_MIT_UNTITLED,
                    'accfc4d5a588384b29c4817392854afb8f319b4568359ca8d063df8a9bc396b6'),
    'gen-mapping': ('authentic', 'MIT', _TASK43_MIT_UNTITLED,
                    'e58e4f6d4f57ab1e4a503a523d1c4e34ed03eee292a0237a898ac158c1b7bc69'),
    'nanoid': ('authentic', 'MIT', MIT.replace(b'Copyright (c)', b'Copyright'),
               'da4db1480d9beea3483a2eda5c53b22238d0827d57da162b48f122e04d2d9987'),
    'detect-libc': ('authentic', 'Apache-2.0', _TASK43_APACHE_BRACES,
                    'b40930bbcf80744c86c46a12bc9da056641d722716c378f5659b9e555ef833e1'),
    'graceful-fs': ('authentic', 'ISC', b'The ISC License\n\n' + _TASK43_ISC,
                    'f65c5d9f22a317b2a10803bd1868461ce6499c2ed7217bc80c0cc772a748789c'),
    'picocolors': ('authentic', 'ISC', _TASK43_ISC,
                   '6582629e2979466878f6014313dcc2f3756c9616148682227ce3063dde310750'),
    'source-map-js': ('authentic', 'BSD-3-Clause', _TASK43_BSD3,
                      '6cb0631f71c7749763fd3dd1d5bee52dd1070ec17f2edc1710079ad070bd2fbd'),
    'bsd2': (None, 'BSD-2-Clause', _TASK43_BSD2, None),
}
_TASK43_PROFILES = {
    'MIT': ('MATCHED_MIT', 'PINNED_RELEASE_AND_COMPLETE_MIT_CONDITIONAL_TEXT', MIT, ('完整 MIT 许可声明',)),
    'Apache-2.0': ('MATCHED_APACHE_2_0', 'PINNED_RELEASE_AND_COMPLETE_APACHE_2_0_CONDITIONAL_TEXT', APACHE, ('§4(a)', '§4(b)', '§4(c)')),
    'ISC': ('MATCHED_ISC', 'PINNED_RELEASE_AND_COMPLETE_ISC_CONDITIONAL_TEXT', _TASK43_ISC, ('完整 ISC 许可声明',)),
    'BSD-2-Clause': ('MATCHED_BSD_2_CLAUSE', 'PINNED_RELEASE_AND_COMPLETE_BSD_2_CLAUSE_CONDITIONAL_TEXT',
                     _TASK43_BSD2, ('源码再分发', '二进制再分发')),
    'BSD-3-Clause': ('MATCHED_BSD_3_CLAUSE', 'PINNED_RELEASE_AND_COMPLETE_BSD_3_CLAUSE_CONDITIONAL_TEXT',
                     _TASK43_BSD3, ('源码再分发', '二进制再分发', '背书或推广')),
}


def _task43_material(name):
    variant, license_id, raw, digest = _TASK43_MATERIALS[name]
    archive = None
    fixtures = os.environ.get('OPENGUARD_TASK43_FIXTURES')
    if fixtures and variant:
        archive = Path(fixtures) / name / variant / 'scan.zip'
        with zipfile.ZipFile(archive) as sample:
            raw = sample.read('LICENSE')
        assert sha(raw) == digest
    return license_id, raw, archive


def _task43_assert_quotes(raw, spans):
    assert spans
    for span in spans:
        start, end = span['byte_start'], span['byte_end']
        assert 0 <= start < end <= len(raw)
        assert raw[start:end].decode('utf-8') == span['quote']
        assert sha(raw[start:end]) == span['quote_sha256']
        assert span['line_start'] == raw[:start].count(b'\n') + 1
        assert span['line_end'] == raw[:end - 1].count(b'\n') + 1


@pytest.mark.parametrize('sample', _TASK43_MATERIALS)
def test_task43_original_material_has_exact_spans(sample):
    license_id, raw, _ = _task43_material(sample)
    parsed = parse_claim_material(raw, 'LICENSE')
    assert (parsed['text_license'], parsed['parse_state']) == (license_id, _TASK43_PROFILES[license_id][0])
    _task43_assert_quotes(raw, parsed['spans'])
    kinds = [span['kind'] for span in parsed['spans']]
    assert {'permission', 'condition', 'warranty'} <= set(kinds)
    if sample in {'http-server', 'gen-mapping'}:
        assert kinds == ['copyright', 'permission', 'condition', 'warranty']


def test_task43_mit_flexible_heading_preserves_legacy_matcher():
    from app.p2.preliminary import complete_mit as legacy_match
    text = b'The MIT License (MIT):\r\n\r\n' + _TASK43_MIT_UNTITLED.replace(
        b'Copyright (c) 2026 Synthetic Contract Fixture',
        'Copyright © 2026 例子\nCopyright 2021–2026 Example Authors'.encode(),
    ).replace(b'\n', b'\r\n')
    parsed = parse_claim_material(text, 'LICENSE')
    assert parsed['parse_state'] == 'MATCHED_MIT'
    assert len(parsed['spans']) == 5
    _task43_assert_quotes(text, parsed['spans'])
    assert legacy_match(MIT)
    assert not legacy_match(text)
    assert not legacy_match(_TASK43_MIT_UNTITLED)


@pytest.mark.parametrize('sample', tuple(_TASK43_MATERIALS))
def test_task43_tampered_warranty_never_matches(sample):
    _, raw, _ = _task43_material(sample)
    needle = b'WITHOUT WARRANTIES' if sample == 'detect-libc' else b'"AS IS"'
    changed = raw.replace(needle, b'DIFFERENT WARRANTY', 1)
    assert changed != raw
    parsed = parse_claim_material(changed, 'LICENSE')
    assert parsed['parse_state'] in {'UNSUPPORTED', 'FAILED'} and not parsed['spans']


def test_task43_apache_tail_rejects_hybrid_or_freeform_addendum():
    mixed = _TASK43_APACHE_BRACES.replace(b'{yyyy}', b'[yyyy]')
    for raw in (mixed, _TASK43_APACHE_BRACES + b'\nAdditional grant.\n'):
        assert parse_claim_material(raw, 'LICENSE')['parse_state'] == 'UNSUPPORTED'
    tail = _TASK43_APACHE_BRACES + 'Copyright © 2026 测试人\n'.encode()
    parsed = parse_claim_material(tail, 'LICENSE')
    assert parsed['parse_state'] == 'MATCHED_APACHE_2_0'
    _task43_assert_quotes(tail, parsed['spans'])


def _scan_zip_into_assessment(base_setup, zip_path, *, index):
    root = base_setup[-1]
    registry, scanned = _run(root, zip_path, _queued(zip_path, index=index))
    with closing(registry):
        return _bind_scanned_run(base_setup, scanned.run), scanned.run


def _bind_scanned_run(base_setup, run):
    c, app, _, _, root = base_setup
    usage = UsageDeclaration(commercial=True, distributed=True, modified=True, network_service=False,
                             training=False, redistributed_assets=False, source_disclosure=False)
    assessment = seed(app, run, usage)
    endpoint = f'/api/v1/scans/{assessment.scan_id}/assessments/{assessment.id}/p2'
    binding = c.get(endpoint + '/binding')
    assert binding.status_code == 200, binding.text
    return c, app, endpoint, {'binding': binding.json(), 'expected_revision': 0,
                             'parent_result_id': None, 'idempotency_key': 'scan-create'}, root


def _task43_endpoint(base_setup, declared, material, *, archive=None, notice=None, pinned=True):
    _, app, _, _, root = base_setup
    if archive is None:
        name, version = NAME, VERSION
        zip_path = root / 'task43-test-only.zip'
        with zipfile.ZipFile(zip_path, 'w') as z:
            z.writestr('package.json', json.dumps({'name': name, 'version': version, 'license': declared}))
            z.writestr('LICENSE', material)
    else:
        with zipfile.ZipFile(archive) as z:
            package = json.loads(z.read('package.json'))
        name, version = package['name'], package['version']
        zip_path = archive
    harness, run = _scan_zip_into_assessment(base_setup, zip_path, index=4301)
    component = next(entry for entry in run.components if (entry.name, entry.version) == (name, version))
    if pinned:
        source = root / 'task43-pinned-source'
        service = app.state.p2_service
        service.public_source_root = str(source)
        service.public_source_profile_sha256 = pinned_source(
            source, declared, material, notice, name=name, version=version,
        )
    first = create(harness)
    subject = next(row['subject'] for row in first['resources'] if row['subject']['resource_id'] == component.id)
    return harness, first, subject


@pytest.mark.parametrize('sample', ('graceful-fs', 'picocolors', 'bsd2', 'source-map-js'))
def test_task43_pinned_permissive_license_asgi(base_setup, sample):
    license_id, raw, archive = _task43_material(sample)
    harness, old, subject = _task43_endpoint(base_setup, license_id, raw, archive=archive)
    before = get(harness, old)
    result = upload(harness, old, subject, raw)
    view = get(harness, result)
    expected_state, reason, _, conditions = _TASK43_PROFILES[license_id]
    items = [item for item in view['advice'] if item['subject'] == subject]
    assert {item['usage'] for item in items} == USES
    assert all(item['state'] == 'SUPPORT' and reason in item['reasons']
               and all(text in ' '.join(item['conditions']) for text in conditions) for item in items), items
    observation = next(item for item in view['materials'] if item['subject'] == subject)
    assert observation['parse_state'] == expected_state
    assert observation['source_binding'] == 'PINNED_RELEASE_MATCH'
    _task43_assert_quotes(raw, observation['clauses'])
    assert_impact(old, before, result, view)
    assert get(harness, old) == before


@pytest.mark.parametrize('declared,observed', [(a, b) for a in _TASK43_PROFILES for b in _TASK43_PROFILES if a != b])
def test_task43_cross_license_conflict_fails_closed(base_setup, declared, observed):
    raw = _TASK43_PROFILES[observed][2]
    harness, old, subject = _task43_endpoint(base_setup, declared, raw, pinned=False)
    result = upload(harness, old, subject, raw)
    advice = [item for item in get(harness, result)['advice'] if item['subject'] == subject]
    assert len(advice) == 3 and all(item['state'] == 'COUNTER_EVIDENCE'
                                    and 'SPDX_TEXT_CONFLICT' in item['reasons'] for item in advice)


@pytest.mark.parametrize('declared,expected_reason', [
    *((license_id, 'COPYLEFT_SOURCE_DISCLOSURE_REVIEW_REQUIRED') for license_id in
      ('GPL-2.0-only', 'GPL-2.0-or-later', 'GPL-3.0-only', 'GPL-3.0-or-later', 'AGPL-3.0-only', 'AGPL-3.0-or-later')),
    *((license_id, 'WEAK_COPYLEFT_FILE_SCOPE_REVIEW_REQUIRED') for license_id in
      ('LGPL-2.1-only', 'LGPL-2.1-or-later', 'LGPL-3.0-only', 'MPL-2.0', 'LGPL-3.0-or-later')),
])
def test_task43_copyleft_reason_and_conflict_precedence(base_setup, declared, expected_reason):
    manifest = _task44_manifest(declared)
    archive = _task44_zip(base_setup, {'package.json': manifest, 'LICENSE': MIT})
    harness, run = _scan_zip_into_assessment(base_setup, archive, index=4401)
    component = next(entry for entry in run.components if (entry.name, entry.version) == (NAME, VERSION))
    assert not any(error.code == 'rules_stage_not_connected' for error in run.errors)
    evidence = _assert_scanned_license(run, component, declared, 'package.json:/license', manifest)
    old = create(harness)
    subject = next(row['subject'] for row in old['resources'] if row['subject']['resource_id'] == component.id)
    view = get(harness, old)
    _assert_v4_declaration(view, subject, declared, evidence.id, manifest)
    selected = {use for use in USES if old['usage'][use] is True}
    advice = {item['usage']: item for item in view['advice'] if item['subject'] == subject}
    assert set(advice) == USES and selected
    assert all(advice[use]['state'] == 'UNKNOWN' and advice[use]['reasons'][0] == expected_reason
               for use in selected)
    assert all(advice[use]['state'] == 'NOT_COVERED' for use in USES - selected)
    result = upload(harness, old, subject, MIT)
    conflict = {item['usage']: item for item in get(harness, result)['advice'] if item['subject'] == subject}
    assert set(conflict) == USES
    assert all(conflict[use]['state'] == 'COUNTER_EVIDENCE' and 'SPDX_TEXT_CONFLICT' in conflict[use]['reasons']
               for use in selected)
    assert all(conflict[use]['state'] == 'NOT_COVERED' for use in USES - selected)


def _task44_manifest(declared='MIT', **fields):
    return json.dumps({'name': NAME, 'version': VERSION, 'license': declared, **fields}).encode()


def _task44_zip(base_setup, files):
    archive = base_setup[-1] / 'task44-test-only.zip'
    with zipfile.ZipFile(archive, 'w') as scanned:
        for path, raw in files.items():
            scanned.writestr(path, raw)
    return archive


def _assert_scanned_license(run, component, declared, locator, raw):
    license_ = next((item for item in run.licenses if item.id == component.license_expression_id), None)
    assert license_ is not None
    assert license_.expression == declared and license_.normalized_ids == [declared]
    evidence, = (item for item in run.evidence if item.id in license_.evidence_ids)
    assert evidence.id in component.evidence_ids
    assert evidence.locator == locator
    assert evidence.content_hash.algorithm == 'sha256' and evidence.content_hash.value == sha(raw)
    assert license_.verification_status.value == evidence.verification_status.value == 'pending'
    return evidence


def _assert_v4_declaration(view, subject, declared, evidence_id, raw):
    declaration = next(item for item in view['declaration_observations'] if item['subject'] == subject)
    assert declaration['expression'] == declared and declaration['normalized_ids'] == [declared]
    assert declaration['evidence_status'] == 'COMPLETE'
    assert declaration['declaration_evidence_ids'] == [evidence_id]
    assert declaration['evidence'] == [{'evidence_id': evidence_id, 'source_sha256': sha(raw)}]


def _task44_uv(name, version):
    return (f'version = 1\nrevision = 3\n[[package]]\nname = "{name}"\nversion = "{version}"\n'
            'source = { registry = "https://pypi.org/simple" }\n').encode()


def test_task44_zip_b58_documents_supply_hash_bound_dependency_roles(base_setup):
    files = {
        'package.json': _task44_manifest(),
        'uv.lock': _task44_uv('task44-uv', VERSION),
        'poetry.lock': b'[metadata]\nlock-version = "2.1"\n[[package]]\nname = "task44-poetry"\nversion = "1.2.3"\n',
        'bom.json': json.dumps({'bomFormat': 'CycloneDX', 'specVersion': '1.5', 'components': [
            {'bom-ref': 'cdx', 'name': 'task44-cdx', 'version': VERSION, 'purl': f'pkg:npm/task44-cdx@{VERSION}'},
        ]}).encode(),
        'sbom.spdx.json': json.dumps({'spdxVersion': 'SPDX-2.3', 'packages': [
            {'name': 'task44-spdx', 'SPDXID': 'SPDXRef-Test', 'versionInfo': VERSION, 'externalRefs': [
                {'referenceCategory': 'PACKAGE-MANAGER', 'referenceType': 'purl',
                 'referenceLocator': f'pkg:pypi/task44-spdx@{VERSION}'},
            ]},
        ]}).encode(),
        'unsupported.cdx.json': b'{',
    }
    harness, run = _scan_zip_into_assessment(base_setup, _task44_zip(base_setup, files), index=4402)
    assert run.status.value == 'completed'
    evidence_by_id = {item.id: item for item in run.evidence}
    components = {item.name: item for item in run.components}
    assert len(evidence_by_id) == len(run.evidence) and len({item.id for item in run.components}) == len(run.components)
    result = create(harness)
    expected = {}
    for name, path, kind in (
        ('task44-uv', 'uv.lock', 'lock'), ('task44-poetry', 'poetry.lock', 'lock'),
        ('task44-cdx', 'bom.json', 'sbom'), ('task44-spdx', 'sbom.spdx.json', 'sbom'),
    ):
        component = components[name]
        assert component.version == VERSION and component.license_expression_id is not None
        assert next(item.expression for item in run.licenses if item.id == component.license_expression_id) == 'NOASSERTION'
        evidence, = (evidence_by_id[eid] for eid in component.evidence_ids
                     if evidence_by_id[eid].producer.name == f'openguard.dependency-observations.{kind}')
        assert evidence.locator.partition(':')[0] == path
        assert evidence.content_hash.algorithm == 'sha256' and evidence.content_hash.value == sha(files[path])
        assert evidence.verification_status.value == 'pending'
        row = next(item for item in result['resources'] if item['subject']['resource_id'] == component.id)
        assert row['evidence_source_hashes'][evidence.id] == sha(files[path])
        result = upload(harness, result, row['subject'], MIT)
        expected[component.id] = evidence.id
    view = get(harness, result)
    assert len(view['materials']) == len(expected)
    for material in view['materials']:
        assert material['role'] == 'dependency' and material['role_state'] == 'inferred'
        assert material['role_conflicts'] == []
        assert material['role_basis_evidence_ids'] == [expected[material['subject']['resource_id']]]
    assert not any(item['state'] == 'SUPPORT' for item in view['advice']
                   if item['subject']['resource_id'] in expected)


@pytest.mark.parametrize('lock_directory,locked_version,conflict', [
    ('sub', '2.3.4', True), ('sub', VERSION, False), ('other', '2.3.4', False),
], ids=['same-scope-conflict', 'same-scope-match', 'separate-scope'])
def test_task44_zip_exact_dependency_declaration_and_lock_conflict(base_setup, lock_directory, locked_version, conflict):
    name = 'task44-versioned'
    files = {
        'package.json': _task44_manifest(),
        'sub/pyproject.toml': f'[project]\nname = "task44-app"\nversion = "1.0.0"\n dependencies = ["{name}=={VERSION}"]\n'.encode(),
        f'{lock_directory}/uv.lock': _task44_uv(name, locked_version),
    }
    harness, run = _scan_zip_into_assessment(base_setup, _task44_zip(base_setup, files), index=4403)
    evidence_by_id = {item.id: item for item in run.evidence}
    subjects = [item for item in run.components if item.name == name]
    assert len({item.id for item in subjects}) == len(subjects) == 2
    assert sorted(item.version for item in subjects) == sorted((VERSION, locked_version))
    result = create(harness)
    role_states, source_evidence = {}, set()
    for component in subjects:
        evidence = [evidence_by_id[eid] for eid in component.evidence_ids]
        lock = any(item.producer.name == 'openguard.dependency-observations.lock' for item in evidence)
        role_states[component.id] = 'inferred' if lock else 'observed'
        path = f'{lock_directory}/uv.lock' if lock else 'sub/pyproject.toml'
        source_evidence.update(item.id for item in evidence if item.content_hash and
                               item.locator.partition(':')[0] == path and item.content_hash.value == sha(files[path]))
        row = next(item for item in result['resources'] if item['subject']['resource_id'] == component.id)
        result = upload(harness, result, row['subject'], MIT)
    conflicts = [item for item in run.errors if item.code == 'lock_version_conflict']
    assert len(source_evidence) >= 2
    if conflict:
        assert set(eid for error in conflicts for eid in error.evidence_ids) & source_evidence == source_evidence
    else:
        assert not conflicts
    materials = get(harness, result)['materials']
    assert len(materials) == 2
    for material in materials:
        if conflict:
            assert material['role'] == material['role_state'] == 'unknown'
            assert material['role_conflicts'] == ['lock_version_conflict']
            assert material['role_basis_evidence_ids'] == []
        else:
            assert material['role'] == 'dependency'
            assert material['role_state'] == role_states[material['subject']['resource_id']]
            assert material['role_conflicts'] == []
            assert set(material['role_basis_evidence_ids']) <= source_evidence


@pytest.mark.parametrize('lockfile_version', (2, 3))
def test_task44_existing_npm_lock_license_binding_reaches_v4(base_setup, lockfile_version):
    name = 'task44-npm-locked'
    declared = 'LGPL-3.0-or-later'
    lock = json.dumps({'lockfileVersion': lockfile_version, 'packages': {
        f'node_modules/{name}': {'name': name, 'version': VERSION, 'license': 'lgpl 3.0 or later'},
    }}).encode()
    archive = _task44_zip(base_setup, {'package.json': _task44_manifest(dependencies={name: VERSION}),
                                      'package-lock.json': lock})
    harness, run = _scan_zip_into_assessment(base_setup, archive, index=4404)
    component, = (item for item in run.components if item.name == name)
    assert not any(item.producer.name == 'openguard.dependency-observations.lock' for item in run.evidence)
    evidence = _assert_scanned_license(run, component, declared, f'package-lock.json:/packages/node_modules~1{name}/license', lock)
    result = create(harness)
    subject = next(row['subject'] for row in result['resources'] if row['subject']['resource_id'] == component.id)
    _assert_v4_declaration(get(harness, result), subject, declared, evidence.id, lock)
    final = get(harness, upload(harness, result, subject, MIT))
    advice = [item for item in final['advice'] if item['subject'] == subject]
    assert {item['usage'] for item in advice} == USES
    assert all(item['state'] == 'COUNTER_EVIDENCE' and 'SPDX_TEXT_CONFLICT' in item['reasons'] for item in advice)


def test_task44_npm_v1_zip_keeps_existing_javascript_partial(base_setup):
    name = 'task44-npm-v1'
    lock = json.dumps({'lockfileVersion': 1, 'dependencies': {name: {'version': VERSION}}}).encode()
    archive = _task44_zip(base_setup, {'package.json': _task44_manifest(dependencies={'task44-declared': VERSION}),
                                      'package-lock.json': lock})
    harness, run = _scan_zip_into_assessment(base_setup, archive, index=4405)
    assert run.status.value == 'partial'
    assert any(item.code == 'javascript_dependency_scan_partial' for item in run.errors)
    assert any(item.name == 'task44-declared' for item in run.components)
    component, = (item for item in run.components if item.name == name)
    assert component.version == VERSION
    evidence, = (item for item in run.evidence if item.id in component.evidence_ids
                 and item.producer.name == 'openguard.dependency-observations.lock')
    assert evidence.locator == f'package-lock.json:/dependencies/{name}'
    assert evidence.content_hash.value == sha(lock)
    result = create(harness)
    subject = next(row['subject'] for row in result['resources'] if row['subject']['resource_id'] == component.id)
    view = get(harness, upload(harness, result, subject, MIT))
    material, = view['materials']
    assert (material['role'], material['role_state']) == ('dependency', 'inferred')
    assert material['role_basis_evidence_ids'] == [evidence.id]


def test_task44_zip_observation_budget_preserves_notice_read(notice_env):
    from app.ingestion import ScanReadLimits, ZipIngestionService
    from app.ingestion.notice_ingestion import complete_zip_ingestion
    from app.pipeline.local_zip import _consume_dependencies
    from app.scanners.dependency_observations import MAX_BYTES
    from test_a4_local_zip_pipeline import NOW
    from test_p1_notice_lifecycle_ingestion import archive, lifecycle

    notice = b'TEST_ONLY retained NOTICE\n' + b'x' * 4096
    files = {'package.json': _task44_manifest(), 'NOTICE': notice}
    for name in ('first', 'second'):
        lock = _task44_uv(name, VERSION) + b'#'
        files[f'{name}/uv.lock'] = lock.ljust(MAX_BYTES - 256, b'x')
    zip_path, run = archive(notice_env, files, index=4406)
    limit = 4 * 1024 * 1024
    proof = complete_zip_ingestion(ZipIngestionService(notice_env.workspace),
        archive_path=zip_path, upload_root=notice_env.uploads, scan_id=run.id,
        expected_input_digest=run.provenance.input_digest.value,
        dependency_consumer=lambda session: _consume_dependencies(session, lambda: NOW),
        notice_consumer=lifecycle(notice_env).collect,
        read_limits=ScanReadLimits(single_file_max_bytes=limit, total_max_bytes=limit))
    envelope = proof.result.consumer_result
    mapping, = envelope.dependencies.dependency_observations
    component, = mapping.components
    assert component.name == 'first'
    observed, = envelope.collection.observations
    assert observed.locator == 'NOTICE' and observed.content.text.encode() == notice
    assert envelope.collection.coverage.state == 'completed'
    assert not list(notice_env.workspace.iterdir())


def test_task44_offline_fixed_git_snapshot_observes_lock_and_v4_role(base_setup, monkeypatch):
    import subprocess

    from app.domain.models import ScanRun
    from app.ingestion import git_stream
    from app.pipeline.public_git import build_public_git_dependency_plan
    from test_a4_local_zip_pipeline import NOW

    root = base_setup[-1]
    repo = root / 'git-fixture'
    repo.mkdir(mode=0o700)
    git_env = {'PATH': '/usr/bin:/bin', 'HOME': str(root), 'LC_ALL': 'C', 'GIT_CONFIG_NOSYSTEM': '1',
               'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_ALLOW_PROTOCOL': 'file', 'GIT_TERMINAL_PROMPT': '0'}

    def git(*args):
        return subprocess.run(
            ['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-c', 'user.name=Offline Fixture',
             '-c', 'user.email=fixture@example.invalid', '-C', str(repo), *args],
            env=git_env, check=True, capture_output=True, timeout=10,
        ).stdout

    name = 'task44-git-lock'
    raw = _task44_uv(name, VERSION)
    git('init', '--quiet')
    (repo / 'package.json').write_bytes(_task44_manifest())
    (repo / 'uv.lock').write_bytes(raw)
    git('add', 'package.json', 'uv.lock')
    git('commit', '--quiet', '-m', 'TEST_ONLY fixed Git source')
    revision = git('rev-parse', 'HEAD').decode().strip()
    bundle = root / 'task44-test-only.bundle'
    git('bundle', 'create', str(bundle), 'HEAD')
    bundle_bytes = bundle.read_bytes()
    bundle.chmod(0o444)

    source = 'https://github.com/example/task44-test-only'
    snapshot = git_stream.FixedGitSnapshot(
        bundle_path=bundle, source_url=source, revision=revision, bundle_sha256=sha(bundle_bytes),
        bundle_size=len(bundle_bytes), captured_at='2026-11-22T00:00:00+00:00',
        capture_receipt_sha256=sha(b'TEST_ONLY fixed snapshot provenance'),
    )
    monkeypatch.setattr(git_stream, 'TrustedEgressProxy', lambda *args, **kwargs: pytest.fail('Git egress attempted'))
    workspace = root / 'git-workspaces'
    workspace.mkdir(mode=0o700)
    plan = build_public_git_dependency_plan(source, workspace, clock=lambda: NOW,
        ingestion_factory=lambda directory: git_stream.GitIngestionService(directory, snapshot=snapshot))
    queued = _queued(bundle, index=4407, source_type='git', source=source).model_dump(mode='json')
    queued['provenance']['input_digest']['value'] = sha(source.encode())
    registry, scanned = _run(root, bundle, ScanRun.model_validate(queued), plan=plan)
    with closing(registry):
        run = registry.get(scanned.run.id).run
    assert run.status.value == 'completed' and run.project.revision == revision
    assert any(item.locator == 'source-snapshot/git' for item in run.evidence)
    assert not list(workspace.iterdir())
    component, = (item for item in run.components if (item.name, item.version) == (name, VERSION))
    evidence, = (item for item in run.evidence if item.id in component.evidence_ids
                 and item.producer.name == 'openguard.dependency-observations.lock')
    assert evidence.locator == 'uv.lock:/package/0'
    assert evidence.content_hash.algorithm == 'sha256' and evidence.content_hash.value == sha(raw)
    harness = _bind_scanned_run(base_setup, run)
    result = create(harness)
    subject = next(row['subject'] for row in result['resources'] if row['subject']['resource_id'] == component.id)
    material, = get(harness, upload(harness, result, subject, MIT))['materials']
    assert (material['role'], material['role_state']) == ('dependency', 'inferred')
    assert material['role_basis_evidence_ids'] == [evidence.id]


@pytest.mark.parametrize('mode', ('missing-pin', 'different-bytes', 'notice'))
def test_task43_bsd_notice_and_release_pin_are_required(base_setup, mode):
    harness, old, subject = _task43_endpoint(
        base_setup, 'BSD-3-Clause', _TASK43_BSD3,
        pinned=mode != 'missing-pin', notice=NOTICE if mode == 'notice' else None,
    )
    raw = _TASK43_BSD3.replace(b'\n', b'\r\n') if mode == 'different-bytes' else _TASK43_BSD3
    result = upload(harness, old, subject, raw)
    advice = [item for item in get(harness, result)['advice'] if item['subject'] == subject]
    assert len(advice) == 3 and all(item['state'] == 'UNKNOWN' for item in advice)
    if mode == 'notice':
        assert all('NOTICE_REQUIRES_REVIEW' in item['reasons'] for item in advice)
