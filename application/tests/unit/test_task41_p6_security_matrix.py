"""P6 permanent safety invariants, exercised with local TEST_ONLY controls."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import gzip
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
from uuid import uuid4
import zipfile

import pytest
from pydantic import ValidationError

from app.assessment.project_facts import project_fact_view
from app.ingestion.zip_preflight import _is_known_special_member
from app.ingestion.zip_stream import ZipIngestionService
from app.p2.contract import strict_json
from app.p2.material_claims_contract import MaterialClaims, RULE_VERSION, SCHEMA_VERSION
from app.p2.preliminary import _notice_inventory_expanded
from app.security.archive_path import normalize_member_path
from app.security.errors import IngestionSecurityError
from app.security.limits import ZipExtractionBudget, ZipSafetyLimits
from app.security.secure_dir import SecureRoot
from test_p2_ai_analysis import flow as local_semantic_flow, parent_setup
from test_p2_contract import answer_body, counts, create, material_body, variant
from test_p2_preliminary import MIT, admit, base_setup, setup as pinned_setup
from test_task33_material_claims import FIXTURE, get as get_claims


BENCHMARK_DIR = Path(__file__).resolve().parents[2] / 'benchmarks'
MANIFEST_PATH = BENCHMARK_DIR / 'p6_benchmark_manifest.json'
DIGEST_PATTERN = re.compile(r'[0-9a-f]{64}')
PACKAGE_NAME = re.compile(r'(?:@[a-z0-9._-]+/)?[a-z0-9._-]+')
MATERIAL_NAME = re.compile(r'(?:LICENSE|LICENCE|NOTICE)(?:\.(?:txt|md|rst))?', re.IGNORECASE)
USES = {'commercial', 'distributed', 'modified'}
STATES = {'SUPPORT', 'RESTRICTION', 'UNKNOWN', 'COUNTER_EVIDENCE', 'NOT_COVERED'}
OBLIGATION_QUESTION = 'OBLIGATION_FULFILLMENT_IN_DELIVERY'
ANNOTATION_STATUS = 'SINGLE_ANNOTATOR_FROZEN_PENDING_SECOND_HUMAN_REVIEW'
METADATA_REFERENCE_PATHS = {
    'application/frontend/pnpm-lock.yaml',
    'frontend/pnpm-lock.yaml',
    'THIRD_PARTY_LICENSES/vite-8.2.2-LICENSE.md',
}


def _check_error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()['error']['code'] == code


def _current_result(harness, result):
    client, _, base, _, _ = harness
    return client.get(
        base + '/results/' + result['result_id'],
        params={'assessment_version': result['binding']['assessment_version']},
    )


def _add_unreviewed_dependency(scan):
    dependency = deepcopy(scan['components'][0])
    dependency.update(id='cmp_' + str(uuid4()), name='task41-unreviewed-dependency', license_expression_id=None)
    declaration = deepcopy(scan['evidence'][0])
    declaration.update(id='evd_' + str(uuid4()), kind='manifest_field',
                       locator='pyproject.toml:project.dependencies[1]',
                       excerpt='task41-unreviewed-dependency==1.0.0', verification_status='pending')
    scan['evidence'].append(declaration)
    dependency['evidence_ids'] = [declaration['id']]
    scan['components'].append(dependency)


def test_01_evidence_does_not_cross_resource_usage_or_project(pinned_setup):
    client, _, base, _, root = pinned_setup
    _, result, _, _, _ = admit(pinned_setup)
    view = get_claims(pinned_setup, result)
    needs_basis = [item for item in view['advice'] if item['usage'] == 'modified']
    assert needs_basis and all(item['state'] == 'NOT_COVERED' for item in needs_basis)
    assert any(item['state'] == 'SUPPORT' for item in view['advice'] if item['usage'] == 'commercial')

    foreign_project = variant(pinned_setup, _add_unreviewed_dependency)
    foreign_result = create(foreign_project)
    target = next(row for row in foreign_result['resources'] if row['scope'] == 'unknown')
    bound_evidence_id = view['materials'][0]['evidence'][0]['evidence_id']
    wrong_resource = material_body(foreign_result, MIT, key='task41-wrong-resource')
    wrong_resource.update(subject=target['subject'], evidence_ids=[bound_evidence_id])
    wrong_project = material_body(result, MIT, key='task41-wrong-project')
    previous = counts(root)
    _check_error(client.post(foreign_project[2] + '/materials', json=wrong_resource), 409, 'p2_evidence_wrong_resource')
    _check_error(client.post(foreign_project[2] + '/materials', json=wrong_project), 409, 'p2_parent_binding_conflict')
    assert counts(root) == previous
    assert get_claims(pinned_setup, result) == view
    assert get_claims(foreign_project, foreign_result)['materials'] == []
    assert base != foreign_project[2]


def test_02_root_license_does_not_cover_dependencies(base_setup):
    project = variant(base_setup, _add_unreviewed_dependency)
    client, app, base, _, _ = project
    original = create(project)
    run = app.state.assessment_service.run(original['binding']['scan_id'])
    facts = project_fact_view(run)
    assert any(item['locator'] == 'LICENSE' for item in facts['root_license_observations'])
    dependency_id = next(item.id for item in run.components if item.name == 'task41-unreviewed-dependency')
    dependency = next(row for row in original['resources'] if row['subject']['resource_id'] == dependency_id)
    assert dependency['scope'] == 'unknown'
    root_row = next(row for row in original['resources'] if row['subject']['resource_id'] != dependency_id)
    raw_material = material_body(original, MIT)
    raw_material.update(subject=root_row['subject'], evidence_ids=[facts['root_license_observations'][0]['evidence_id']])
    response = client.post(base + '/materials', json=raw_material)
    assert response.status_code == 201, response.text
    saved = response.json()['result']
    assert next(row for row in saved['resources'] if row['subject'] == dependency['subject']) == dependency
    uses = [item for item in get_claims(project, saved)['advice'] if item['subject'] == dependency['subject']]
    assert {item['usage'] for item in uses} == USES
    assert all(item['state'] != 'SUPPORT' for item in uses)


def test_03_path_hint_does_not_exclude_a_retained_resource(base_setup):
    def with_path_hint(scan):
        resource = scan['components'][0]
        hint = deepcopy(scan['evidence'][0])
        hint.update(id='evd_' + str(uuid4()), kind='manifest_field', locator='docs/requirements.txt:1')
        scan['evidence'].append(hint)
        resource['evidence_ids'].append(hint['id'])

    project = variant(base_setup, with_path_hint)
    result = create(project)
    run = project[1].state.assessment_service.run(result['binding']['scan_id'])
    (resource,) = project_fact_view(run)['resource_declarations']
    assert resource['roles'] == ['development']
    assert resource['declarations'][0]['basis'] == 'documentation_path_hint'
    assert resource['scope_confirmed_by_this_view'] is False
    commercial = [a for a in get_claims(project, result)['advice'] if a['usage'] == 'commercial']
    assert [a['subject']['resource_id'] for a in commercial] == [resource['resource_id']]
    assert commercial[0]['state'] != 'NOT_COVERED'


def test_04_user_statement_cannot_promote_its_provenance(base_setup):
    client, app, base, _, root = base_setup
    result = create(base_setup)
    saved_formal = app.state.assessment_service.store.report(result['binding']['scan_id'], result['binding']['assessment_id'])
    request = answer_body(result)
    previous = counts(root)
    _check_error(client.post(base + '/answers', json={**request, 'provenance': 'VERIFIED'}), 422, 'p2_request_invalid')
    assert counts(root) == previous
    accepted = client.post(base + '/answers', json=request)
    assert accepted.status_code == 201, accepted.text
    answer = accepted.json()['answer']
    assert answer['provenance'] == 'USER_ASSERTED'
    assert answer['formal_effect'] == 'none'
    assert app.state.assessment_service.store.report(result['binding']['scan_id'], result['binding']['assessment_id']) == saved_formal
    assert _current_result(base_setup, result).json() == result


def test_05_not_delivered_never_means_fulfilled(pinned_setup):
    client, app, base, _, _ = pinned_setup
    _, result, _, _, _ = admit(pinned_setup)
    question = next(item for item in result['questions'] if item['question_code'] == OBLIGATION_QUESTION)
    prior_formal = app.state.assessment_service.store.get_by_id(result['binding']['assessment_id'])
    assert prior_formal.obligations
    assert all(item.fulfillment != 'fulfilled' for item in prior_formal.obligations)
    request = answer_body(result, key='task41-not-delivered')
    request.update(question_id=question['question_id'], question_code=OBLIGATION_QUESTION,
                   subjects=question['subjects'][:1], answer_code='NOT_DELIVERED_YET')
    response = client.post(base + '/answers', json=request)
    assert response.status_code == 201, response.text
    receipt = response.json()
    answer, updated = receipt['answer'], receipt['result']
    assert answer['answer_code'] == 'NOT_DELIVERED_YET'
    assert answer['provenance'] == 'USER_ASSERTED' and answer['formal_effect'] == 'none'
    resource = next(row for row in updated['resources'] if row['subject'] == request['subjects'][0])
    assert resource['user_assertions'][OBLIGATION_QUESTION] == 'NOT_DELIVERED_YET'
    assert updated['formal_effect'] == 'none'
    assert app.state.assessment_service.store.get_by_id(result['binding']['assessment_id']) == prior_formal
    assert _current_result(pinned_setup, result).json() == result


def test_06_test_only_rows_cannot_be_read_or_extended_as_owner(base_setup, monkeypatch):
    client, app, base, _, root = base_setup
    result = create(base_setup)
    assert result['data_scope'] == get_claims(base_setup, result)['data_scope'] == 'TEST_ONLY'
    previous = counts(root)
    with monkeypatch.context() as patch:
        patch.setattr(app.state.p2_service, 'data_scope', 'OWNER')
        assert _current_result(base_setup, result).status_code == 503
        view = client.get(base + '/results/' + result['result_id'] + '/material-claims',
                          params={'assessment_version': result['binding']['assessment_version']})
        assert view.status_code == 503
        assert client.post(base + '/answers', json=answer_body(result)).status_code == 503
        assert counts(root) == previous
    assert _current_result(base_setup, result).json() == result


def test_07_insufficient_input_is_not_support(pinned_setup):
    client, _, base, _, _ = pinned_setup
    original = create(pinned_setup)
    initial = get_claims(pinned_setup, original)
    assert initial['source_status'] == 'NOT_CONFIGURED'
    assert initial['advice'] and all(item['state'] != 'SUPPORT' for item in initial['advice'])
    request = material_body(original, MIT)
    request.update(completeness='FULL_TEXT_CLAIMED')
    response = client.post(base + '/materials', json=request)
    assert response.status_code == 201, response.text
    updated = get_claims(pinned_setup, response.json()['result'])
    assert updated['materials'][0]['parse_state'] == 'MATCHED_MIT'
    selected = [item for item in updated['advice'] if item['saved_value'] is True]
    assert selected and all(item['state'] == 'UNKNOWN' and not item['conditions'] for item in selected)
    assert get_claims(pinned_setup, original) == initial


def test_08_old_binding_and_v1_v2_v3_projection_contracts_are_refused(base_setup):
    client, _, base, body, root = base_setup
    old_binding = deepcopy(body)
    old_binding['binding']['rule_version'] = 'task41-stale-config'
    previous = counts(root)
    _check_error(client.post(base + '/results', json=old_binding), 409, 'p2_parent_binding_conflict')
    assert counts(root) == previous
    result = create(base_setup)
    fresh = get_claims(base_setup, result)
    assert fresh['schema_version'] == SCHEMA_VERSION
    assert fresh['rule_version'] == RULE_VERSION
    assert MaterialClaims.model_validate(fresh).model_dump(mode='json') == fresh
    for version in (1, 2, 3):
        stale = {**fresh, 'schema_version': f'openguard-material-claims/{version}',
                 'rule_version': f'mit-bound-claim/{version}'}
        with pytest.raises(ValidationError) as error:
            MaterialClaims.model_validate(stale)
        assert {item['loc'] for item in error.value.errors()} == {('schema_version',), ('rule_version',)}


def test_09_semantic_failure_creates_a_stable_receipt_without_automatic_retry(local_semantic_flow):
    client, _, base, root, _, result, _, scripted_provider, request = local_semantic_flow
    assert scripted_provider.model['name'] == 'SYNTHETIC_TEST_ONLY'
    scripted_provider.mutate = lambda value: value['actions'][0].update(
        text='记录许可条款中的声明，确保在任何副本或服务运行中均保留完整原文。'
    )
    initial_result = client.get(base + '/results/' + result['result_id'], params={'assessment_version': 1}).content
    reply = client.post(base + '/ai-analyses', json=request)
    assert reply.status_code == 201, reply.text
    failure = reply.json()
    assert failure['status'] == 'failed' and failure['error_code']
    assert failure['actions'] == failure['clauses'] == failure['changes'] == []
    assert scripted_provider.calls == 1
    previous = counts(root)
    query = {'assessment_version': 1, 'result_id': result['result_id']}
    for _ in range(3):
        saved = client.get(base + '/ai-analyses/' + failure['analysis_id'], params=query)
        assert saved.status_code == 200 and saved.json() == failure
        assert client.post(base + '/ai-analyses', json=request).json() == failure
    assert scripted_provider.calls == 1 and counts(root) == previous
    assert client.get(base + '/results/' + result['result_id'], params={'assessment_version': 1}).content == initial_result


def test_10_rejects_unsafe_archive_metadata_oversize_and_unknown_inputs(base_setup):
    client, _, base, _, root = base_setup
    limits = ZipSafetyLimits(expansion_ratio_max=10)
    with pytest.raises(IngestionSecurityError) as path_error:
        normalize_member_path('fixture/../sample.txt', is_directory=False, limits=limits)
    assert path_error.value.reason == 'archive_path_unsafe'

    member = zipfile.ZipInfo('sample.txt')
    member.create_system = 3
    member.external_attr = (stat.S_IFREG | 0o600) << 16
    assert _is_known_special_member(member, False) is False
    member.external_attr = (stat.S_IFLNK | 0o700) << 16
    assert _is_known_special_member(member, False) is True

    local_directory = root / 'safe-boundary'
    local_directory.mkdir(mode=0o700)
    local_link = root / 'local-directory-link'
    local_link.symlink_to(local_directory, target_is_directory=True)
    with pytest.raises(IngestionSecurityError):
        SecureRoot.open(local_link)
    assert list(local_directory.iterdir()) == []
    local_link.unlink()

    budget = ZipExtractionBudget(limits, upload_size_bytes=100)
    file_budget = budget.begin_file(compressed_size_hint=1)
    file_budget.add(10)
    with pytest.raises(IngestionSecurityError) as ratio_error:
        file_budget.add(1)
    assert ratio_error.value.reason == 'archive_ratio_limit'

    total_budget = ZipExtractionBudget(limits, upload_size_bytes=limits.upload_max_bytes)
    with pytest.raises(IngestionSecurityError) as size_error:
        total_budget.add_file_bytes(limits.uncompressed_max_bytes + 1)
    assert size_error.value.reason == 'archive_total_size_limit'

    archive = gzip.decompress((FIXTURE / 'archive.tgz').read_bytes())
    assert _notice_inventory_expanded(archive)['status'] == 'ABSENT_COMPLETE'
    # A one-byte sentinel tests the strict EOF gate without a nested archive.
    tailed = _notice_inventory_expanded(archive + b'\n')
    assert tailed['status'] == 'INCOMPLETE' and tailed['enumeration_complete'] is False

    zip_root = root / 'zip-boundary'
    zip_root.mkdir(mode=0o700)
    service = ZipIngestionService(zip_root)
    try:
        with pytest.raises(IngestionSecurityError) as unknown_archive:
            service.ingest(io.BytesIO(b'TEST_ONLY plain text'))
        assert unknown_archive.value.reason == 'archive_not_zip'
        assert list(zip_root.iterdir()) == []
    finally:
        service.close()

    result = create(base_setup)
    previous = counts(root)
    oversize = client.post(base + '/materials', json=material_body(result, b'x' * 65537))
    _check_error(oversize, 413, 'p2_material_size_limit')
    unsupported_body = {**material_body(result), 'task41_unknown_field': 'TEST_ONLY'}
    _check_error(client.post(base + '/materials', json=unsupported_body), 422, 'p2_request_invalid')
    assert counts(root) == previous
    assert get_claims(base_setup, result)['materials'] == []


def _read_manifest():
    raw = MANIFEST_PATH.read_bytes()
    expected = os.environ.get('OPENGUARD_P6_MANIFEST_SHA256')
    if expected is not None:
        assert DIGEST_PATTERN.fullmatch(expected)
        assert hashlib.sha256(raw).hexdigest() == expected
    data = strict_json(raw)
    assert data['schema_version'] == 'openguard-p6-benchmark/1'
    assert data['data_scope'] == 'TEST_ONLY'
    assert data['parent_commit'] == 'ab2c1256c4a2efb8714cc90b9f39eda0fc5fc224'
    return data


def _unique_index(rows):
    indexed = {row['id']: row for row in rows}
    assert indexed and len(indexed) == len(rows)
    assert all(isinstance(identity, str) and identity.strip() for identity in indexed)
    return indexed


def _safe_relative(path):
    relative = PurePosixPath(path)
    assert not relative.is_absolute() and relative.parts and '..' not in relative.parts
    assert relative.as_posix() == path and '\\' not in path
    return relative


def _digest_ref(known_files, relative, digest):
    _safe_relative(relative)
    assert DIGEST_PATTERN.fullmatch(digest)
    assert known_files[relative]['sha256'] == digest


def _verify_recorded_file(root, relative, expected_hash, expected_bytes=None):
    path = root / _safe_relative(relative)
    assert path.resolve(strict=True) == path and path.is_file()
    if expected_bytes is not None:
        assert path.stat().st_size == expected_bytes
    with path.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == expected_hash


def test_manifest_integrity_case_identity_and_fixture_hash_closure():
    manifest = _read_manifest()
    projects = _unique_index(manifest['projects'])
    scenarios = _unique_index(manifest['scenarios'])
    cases = _unique_index(manifest['cases'])
    assert Counter(project['split'] for project in projects.values()) == {'development': 6, 'independent_holdout': 2}
    assert len({(row['name'], row['version']) for row in projects.values()}) == len(projects)
    assert all(row['declared_license'] and row['source'] for row in projects.values())
    assert {scenario['project_id'] for scenario in scenarios.values()} == set(projects)

    known_files = manifest['fixtures']
    evidence_dir = os.environ.get('OPENGUARD_P6_EVIDENCE_DIR')
    fixture_root = Path(evidence_dir).resolve(strict=True) / 'tmp-data' if evidence_dir else None
    for relative, entry in known_files.items():
        assert _safe_relative(relative).parts[:2] == ('fixtures', 'p6')
        assert DIGEST_PATTERN.fullmatch(entry['sha256'])
        assert type(entry['bytes']) is int and entry['bytes'] > 0
        if fixture_root is not None:
            _verify_recorded_file(fixture_root, relative, entry['sha256'], entry['bytes'])
    for scenario in scenarios.values():
        assert scenario['project_id'] in projects
        assert set(scenario['usage']) == USES
        assert all(value is None or type(value) is bool for value in scenario['usage'].values())
        source = scenario['source']
        if source is not None:
            profile = (_safe_relative(source['root']) / 'profile.json').as_posix()
            _digest_ref(known_files, profile, source['profile_sha256'])
        _digest_ref(known_files, scenario['zip']['path'], scenario['zip']['sha256'])
        for action in scenario['actions']:
            if action['type'] == 'material':
                _digest_ref(known_files, action['path'], action['sha256'])
                assert MATERIAL_NAME.fullmatch(action['filename'])
            else:
                assert action['type'] == 'answer' and action['answer_code'] == 'NOT_FULFILLED'

    pairs = {(case['project_id'], case['scenario_id'], case['usage']) for case in cases.values()}
    assert len(pairs) == len(cases) >= 40
    assert {case['project_id'] for case in cases.values()} == set(projects)
    assert {case['scenario_id'] for case in cases.values()} == set(scenarios)
    assert {case['expected_state'] for case in cases.values()} == STATES
    split_counts = Counter()
    for case in cases.values():
        scenario = scenarios[case['scenario_id']]
        assert scenario['project_id'] == case['project_id'] and case['usage'] in USES
        assert type(case['support_scope_applicable']) is bool
        assert case['ground_truth']['status'] == ANNOTATION_STATUS
        assert case['ground_truth']['rationale'].strip()
        if case['expected_state'] == 'SUPPORT':
            assert case['required_condition_fragments']
        split_counts[projects[case['project_id']]['split']] += 1
    assert split_counts['development'] >= 32 and split_counts['independent_holdout'] >= 10

    performance = manifest['performance_scenarios']
    assert performance and len(performance) == len(set(performance))
    assert set(performance) <= set(scenarios)


def _local_git(repo, *args):
    environment = {
        **os.environ,
        'GIT_ALLOW_PROTOCOL': 'file',
        'GIT_CONFIG_GLOBAL': os.devnull,
        'GIT_CONFIG_NOSYSTEM': '1',
        'GIT_NO_LAZY_FETCH': '1',
        'GIT_TERMINAL_PROMPT': '0',
    }
    return subprocess.run(
        ['git', '--no-pager', '-C', str(repo), '-c', 'core.quotePath=false', *args],
        env=environment, capture_output=True, text=True, timeout=15, check=False,
    )


def test_manifest_holdout_audit_separates_metadata_from_evaluation_exposure():
    manifest = _read_manifest()
    audit = manifest['holdout_audit']
    assert audit['metadata_exception_confirmed'] is True
    assert audit['zero_prior_repo_references'] is False
    assert audit['zero_prior_evaluation_sample_references_in_audited_scope'] is True
    assert audit['scope'].strip()
    assert audit['path'] == 'logs/holdout-exposure-audit.log' and DIGEST_PATTERN.fullmatch(audit['sha256'])
    evidence_dir = os.environ.get('OPENGUARD_P6_EVIDENCE_DIR')
    if evidence_dir is not None:
        _verify_recorded_file(Path(evidence_dir).resolve(strict=True), audit['path'], audit['sha256'])

    holdouts = [project for project in manifest['projects'] if project['split'] == 'independent_holdout']
    development_names = {project['name'] for project in manifest['projects'] if project['split'] == 'development'}
    assert len(holdouts) == 2 and not {project['name'] for project in holdouts} & development_names
    repo = BENCHMARK_DIR.parents[1]
    history = _local_git(repo, 'rev-list', manifest['parent_commit'])
    assert history.returncode == 0, history.stderr
    revisions = history.stdout.splitlines()
    assert revisions and revisions[0] == manifest['parent_commit']

    for project in holdouts:
        exposure = project['exposure_history']
        assert exposure['has_prior_sample_uses'] is False and exposure['zero_prior_repo_references'] is False
        assert exposure['basis'].strip()
        assert PACKAGE_NAME.fullmatch(project['name'])
        matching_paths = set()
        for revision in revisions:
            match = _local_git(repo, 'grep', '-F', '-l', '-e', project['name'], revision, '--')
            assert match.returncode in (0, 1), match.stderr
            matching_paths.update(line.split(':', 1)[1] for line in match.stdout.splitlines())
        assert matching_paths and matching_paths <= METADATA_REFERENCE_PATHS, matching_paths
