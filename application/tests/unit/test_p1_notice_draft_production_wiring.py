"""A3: TEST_ONLY local materials, real CZ/A2/A1 and default factory consumption."""
import hashlib
import json
import sqlite3
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.api import main
from app.notice_source.models import NoticeSourceCollection
from app.p1.notice_draft import NoticeDraftService, NoticeDraftServiceError
from app.p1.notice_draft_store import NoticeDraftStore, NoticeDraftStoreError
from app.p1.notice_source_store import BoundNoticeSourceReader, NoticeSourceStore, NoticeSourceStoreError
from app.p1.report_v2_notice import ReportNoticeReader
from test_p1_contract_schema import validator
from test_p1_diff_api import assessment as make_assessment
from test_p1_notice_draft_backend import FixtureReader
from test_p1_notice_source_adapter import env as source_env, admit, bound

GLOBALS = {'draft_only_not_obligation_fulfillment', 'authorization_pending', 'license_expression_not_inferred'}


def configure(monkeypatch, root, assessments='1', profile='0'):
    monkeypatch.setenv('OPENGUARD_DATA_DIR', str(root))
    for name in ('AI', 'PUBLIC_GIT', 'EXTERNAL_SCANNERS', 'DURABLE_ZIP'):
        monkeypatch.setenv('OPENGUARD_ENABLE_' + name, '0')
    monkeypatch.setenv('OPENGUARD_ENABLE_ASSESSMENTS', assessments)
    monkeypatch.setenv('OPENGUARD_ENABLE_PROFILE_METADATA', profile)
    monkeypatch.setenv('OPENGUARD_OLLAMA_DOCKER_HOST', '0')


def forbidden(*args, **kwargs):
    raise AssertionError('unexpected upstream or side effect')


def business(root):
    result = {}
    for path in sorted(root.glob('*.db')):
        with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as db:
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            result[path.name] = {t: db.execute('SELECT * FROM "' + t.replace('"', '""') +
                                               '" ORDER BY rowid').fetchall() for t in tables}
    return result


def upstream(root):
    return {k: v for k, v in business(root).items() if k not in {'notice_draft.db', 'report_v2.db'}}


@pytest.fixture
def factory(source_env, monkeypatch):
    e = source_env
    configure(monkeypatch, e.path)
    e.app = main.create_default_app()
    e.base = f'/api/v1/scans/{e.run.id}/assessments/{e.assessment.id}'
    with TestClient(e.app) as client:
        e.client = client
        yield e


def post(e, key='a3', assessment_id=None):
    base = e.base if assessment_id is None else f'/api/v1/scans/{e.run.id}/assessments/{assessment_id}'
    return e.client.post(base + '/notice-drafts', json={'idempotency_key': key})


def draft(e, key='a3'):
    response = post(e, key)
    assert response.status_code == 200, response.text
    validator('NoticeDraft').validate(response.json())
    return response.json()


def error(response, status, code, reason):
    assert response.status_code == status, response.text
    assert response.json()['error']['code'] == code
    assert response.json()['error']['details']['reason'] == reason
    assert not any(x in response.text for x in ('Traceback', '/private', '.db', 'SELECT '))


def no_mutation(e, action, status, code, reason):
    before = business(e.path)
    error(action(), status, code, reason)
    assert business(e.path) == before


def report(e, d):
    response = e.client.post(e.base + '/report-v2', json={'idempotency_key': 'report-a3',
        'notice_refs': [{'draft_id': d['draft_id'], 'content_hash': d['content_hash']}]})
    assert response.status_code == 200, response.text
    snapshot = response.json()
    validator('ReportV2Snapshot').validate(snapshot)
    artifacts = {a['format']: e.client.get(a['href']).content for a in snapshot['artifacts']}
    for a in snapshot['artifacts']:
        assert len(artifacts[a['format']]) == a['size_bytes']
        assert hashlib.sha256(artifacts[a['format']]).hexdigest() == a['content_hash']
    return snapshot, artifacts


def test_a3_01_12_15_20_real_default_cz_a2_draft_report(factory, monkeypatch):
    e = factory
    seen = []
    real_validate = e.api.validate_notice_source_package
    def validate(value):
        seen.append(value)
        return real_validate(value)
    monkeypatch.setattr(e.api, 'validate_notice_source_package', validate)
    fixed = bound(e)  # real CZ collector -> A2 -> A1 stage/trusted bind
    before = upstream(e.path)
    original_run = e.registry.get(e.run.id).run.model_dump_json()
    original_assessment = e.store.get(e.run.id, e.assessment.id).model_dump_json()
    service = e.app.state.notice_draft_service
    assert isinstance(service, NoticeDraftService)
    assert service.facts_reader is None
    assert type(service.bound_source_reader) is BoundNoticeSourceReader
    assert type(e.app.state.report_v2_service.notice_reader) is ReportNoticeReader
    assert e.app.state.report_v2_service.notice_reader.store is service.store
    d = draft(e)
    assert len(seen) >= 2  # real validator both at admission and production decode
    assert d['schema_version'] == '1.0'
    assert d['generator_version'] == d['provenance']['algorithm_version'] == 'notice-bound/1.0'
    assert d['provenance']['parameters_hash'] == fixed.package_hash
    assert d['binding']['scan_ref']['registry_revision'] == fixed.registry_revision
    assert d['binding']['assessment_ref']['version'] == e.assessment.version
    snapshot, artifacts = report(e, d)
    notices = [s['content'] for s in json.loads(artifacts['json'])['sections']
               if s['authority'] == 'observation' and 'draft_id' in s['content']]
    assert notices == [d]
    assert snapshot['binding']['notice_refs'] == [{'draft_id': d['draft_id'], 'content_hash': d['content_hash']}]
    assert upstream(e.path) == before
    assert e.registry.get(e.run.id).run.model_dump_json() == original_run
    assert e.store.get(e.run.id, e.assessment.id).model_dump_json() == original_assessment


@pytest.mark.parametrize('state', ['absent', 'staged', 'other_assessment'])
def test_a3_02_03_05_no_exact_bound_does_not_write(factory, state):
    e = factory
    assessment_id = None
    if state == 'staged':
        e.source.stage(admit(e))
    if state == 'other_assessment':
        bound(e)
        assessment_id = make_assessment(e, e.run, version=2).id
    no_mutation(e, lambda: post(e, assessment_id=assessment_id), 409, 'not_ready', 'notice_source_not_bound')


@pytest.mark.parametrize('field,value', [
    ('scan_id', 'scn_other'), ('registry_revision', 99), ('input_digest', '1'*64),
    ('inventory_digest', '2'*64), ('facts_hash', '3'*64), ('assessment_id', 'asm_other'),
    ('assessment_version', 99), ('assessment_facts_hash', '4'*64),
])
def test_a3_04_05_all_current_binding_fields_independently_rejected(factory, monkeypatch, field, value):
    e = factory
    fixed = bound(e)
    monkeypatch.setattr(e.app.state.notice_draft_service.bound_source_reader, 'read',
                        lambda *args: replace(fixed, **{field: value}))
    no_mutation(e, lambda: post(e), 409, 'conflict', 'notice_source_binding_mismatch')


@pytest.mark.parametrize('state,gap', [
    ('full', None), ('excerpt', 'notice_source_excerpt_truncated'),
    ('not_observed', 'notice_text_not_observed'), ('not_scanned', 'notice_text_not_scanned'),
    ('read_failed', 'notice_text_read_failed'),
])
@pytest.mark.parametrize('relation', ['resolved', 'unresolved'])
def test_a3_06_11_content_and_no_authority_escalation(factory, state, gap, relation):
    e = factory
    value = e.collection.model_dump(mode='json')
    item = value['observations'][0]
    if state == 'excerpt':
        text = item['content']['text'][:9]
        item['content'].update(state=state, text=text, byte_range=[0, len(text.encode())],
                              truncated=True, retained_bytes_sha256=hashlib.sha256(text.encode()).hexdigest())
    elif state != 'full':
        item['content'] = dict(state=state, gap_codes=[] if state == 'not_observed' else ['test_read_gap'])
    # Collector-local subject, not a ScanRun component ID (this seed has none).
    item['relation'] = dict(state=relation, subject='cmp_TEST_ONLY_unmapped' if relation == 'resolved' else None,
                            basis='TEST_ONLY relation is not a formal Resource binding')
    e.collection = NoticeSourceCollection.model_validate(value)
    bound(e)
    d = draft(e)
    entries = {x['entry_id']: x for x in d['entries']}
    assert list(entries) == sorted(o.observation_key for o in e.collection.observations)
    for observation in e.collection.observations:
        row = entries[observation.observation_key]
        assert row['text'] == observation.content.text
        for name in ('resource_ids', 'evidence_refs', 'license_expression_ids', 'obligation_refs'):
            assert row[name] == []
        assert set(observation.content.gap_codes) <= set(row['missing'])
    first = entries[item['observation_key']]
    assert ('resource_relation_unresolved' if relation == 'unresolved'
            else 'resource_relation_not_formalized') in first['missing']
    if gap:
        assert gap in first['missing'] and gap in d['coverage_gaps']
    assert GLOBALS <= set(d['coverage_gaps'])


@pytest.mark.parametrize('coverage', [
    dict(state='completed', omissions=[], gap_codes=[]),
    dict(state='partial', omissions=['TEST_ONLY omitted path'], gap_codes=[]),
    dict(state='partial', omissions=[], gap_codes=['test_package_gap']),
    dict(state='partial', omissions=['z', 'a'], gap_codes=['test_package_gap']),
])
def test_coverage_exact_source_and_stable_draft(factory, coverage):
    e = factory
    value = e.collection.model_dump(mode='json')
    value['coverage'] = coverage
    e.collection = NoticeSourceCollection.model_validate(value)
    fixed = bound(e)
    before = upstream(e.path)
    d = draft(e)
    assert draft(e) == d
    assert draft(e, 'another-key') == d
    gaps = d['coverage_gaps']
    assert ('notice_source_partial' in gaps) == (coverage['state'] == 'partial')
    assert ('notice_source_omissions_present' in gaps) == bool(coverage['omissions'])
    assert set(coverage['gap_codes']) <= set(gaps)
    assert gaps == sorted(set(gaps))
    assert e.api.decode_bound_notice_source(e.reader.read(
        e.run.id, e.assessment.facts_hash, e.assessment.id, e.assessment.version)).coverage.model_dump() == coverage
    assert upstream(e.path) == before
    assert d['provenance']['parameters_hash'] == fixed.package_hash


@pytest.mark.parametrize('failure', ['database', 'reader', 'decode'])
def test_a3_17_source_failure_is_sanitized_and_atomic(factory, monkeypatch, failure):
    e = factory
    fixed = bound(e)
    service = e.app.state.notice_draft_service
    reason = 'notice_source_unavailable'
    if failure == 'database':
        with sqlite3.connect(e.source.path) as db:
            db.execute('UPDATE notice_source_bindings SET binding_hash=?', ('0'*64,))
    elif failure == 'reader':
        def unavailable(*args):
            raise NoticeSourceStoreError('private path /private/example.db SELECT secret')
        monkeypatch.setattr(service.bound_source_reader, 'read', unavailable)
    else:
        monkeypatch.setattr(service.bound_source_reader, 'read',
                            lambda *args: replace(fixed, canonical_package_bytes=b'broken'))
        reason = 'notice_source_invalid'
    no_mutation(e, lambda: post(e), 503, 'upstream_unavailable', reason)


def forbid_upstreams(monkeypatch, app):
    service = app.state.notice_draft_service
    for obj, name in [(service.registry, 'get'), (service.assessment_store, 'get'),
                      (service.assessment_store, 'get_by_id'), (service.bound_source_reader, 'read'),
                      (app.state.report_v2_service.notice_reader, 'read')]:
        monkeypatch.setattr(obj, name, forbidden)
    import app.p1.notice_draft_bound_source as consumption
    monkeypatch.setattr(consumption, 'decode_bound_notice_source', forbidden)
    monkeypatch.setattr('app.notice_source.collect_notice_source_package', forbidden)
    monkeypatch.setattr('socket.socket.connect', forbidden)
    monkeypatch.setattr('subprocess.Popen', forbidden)
    for obj, name in [(service, 'create'), (app.state.report_v2_service, 'create'), (NoticeSourceStore, 'stage')]:
        monkeypatch.setattr(obj, name, forbidden)


@pytest.mark.parametrize('restart', [False, True])
def test_a3_13_14_16_18_get_and_restart_store_only(factory, monkeypatch, restart):
    e = factory
    bound(e)
    d = draft(e)
    snapshot, artifacts = report(e, d)
    href = e.base + '/notice-drafts/' + d['draft_id']
    before = business(e.path)
    if restart:
        app = main.create_default_app()
        assert business(e.path) == before
        with TestClient(app) as client:
            forbid_upstreams(monkeypatch, app)
            assert client.get(href).json() == d
            for a in snapshot['artifacts']:
                assert client.get(a['href']).content == artifacts[a['format']]
    else:
        forbid_upstreams(monkeypatch, e.app)
        assert e.client.get(href).json() == d
        for a in snapshot['artifacts']:
            assert e.client.get(a['href']).content == artifacts[a['format']]
    assert business(e.path) == before


def test_both_none_store_only_and_create_disabled(factory):
    e = factory
    bound(e)
    d = draft(e)
    service = NoticeDraftService(None, None, NoticeDraftStore(e.path/'notice_draft.db', min_free_bytes=0))
    before = business(e.path)
    assert service.get(e.run.id, e.assessment.id, d['draft_id']).model_dump(mode='json') == d
    with pytest.raises(NoticeDraftServiceError) as caught:
        service.create(e.run.id, e.assessment.id, idempotency_key='off')
    assert caught.value.code == 'feature_disabled'
    assert business(e.path) == before


def test_ambiguous_reader_configuration_fails_at_construction(source_env):
    e = source_env
    before = business(e.path)
    with pytest.raises(ValueError, match='ambiguous_notice_source_configuration'):
        NoticeDraftService(e.registry, e.store, None, facts_reader=FixtureReader(), bound_source_reader=e.reader)
    assert business(e.path) == before


def test_a3_19_legacy_and_production_fingerprints_are_separate(factory):
    e = factory
    bound(e)
    d = draft(e)
    legacy = NoticeDraftService(e.registry, e.store, e.app.state.notice_draft_service.store, facts_reader=FixtureReader())
    with pytest.raises(NoticeDraftServiceError) as caught:
        legacy.create(e.run.id, e.assessment.id, idempotency_key='a3')
    assert caught.value.code == 'conflict'
    old = legacy.create(e.run.id, e.assessment.id, idempotency_key='legacy')
    assert old.generator_version == old.provenance.algorithm_version == 'notice/1.0'
    assert old.schema_version == '1.0' and old.draft_id != d['draft_id']
    assert old.provenance.parameters_hash != d['provenance']['parameters_hash']
    assert legacy.get(e.run.id, e.assessment.id, d['draft_id']).model_dump(mode='json') == d


@pytest.mark.parametrize('assessments', ['0', '1'])
@pytest.mark.parametrize('profile', ['0', '1'])
def test_factory_matrix_startup_no_collection_or_business_writes(tmp_path, monkeypatch, assessments, profile):
    root = tmp_path/'data'
    configure(monkeypatch, root, assessments, profile)
    for path in ('socket.socket.connect', 'subprocess.Popen', 'app.notice_source.collect_notice_source_package',
                 'app.p1.notice_source_adapter.NoticeSourceAdapter.admit',
                 'app.p1.notice_source_store.NoticeSourceBindingService.bind'):
        monkeypatch.setattr(path, forbidden)
    monkeypatch.setattr(NoticeSourceStore, 'stage', forbidden)
    monkeypatch.setattr(NoticeDraftService, 'create', forbidden)
    with TestClient(main.create_default_app()) as client:
        service = client.app.state.notice_draft_service
        assert (service is not None) == (assessments == '1')
        for name in ('notice_source.db', 'notice_draft.db'):
            assert (root/name).exists() == (assessments == '1')
        if service is not None:
            for name in ('notice_source.db', 'notice_draft.db'):
                assert all(not rows for table, rows in business(root)[name].items()
                           if table not in {'notice_meta', 'notice_source_meta'})
            assert service.bound_source_reader.source_store.path == root/'notice_source.db'
            assert service.store.path == root/'notice_draft.db'
        assert (client.app.state.profile_service.store is not None) == (profile == '1')


def test_disabled_preserves_existing_notice_files(factory, monkeypatch):
    e = factory
    bound(e)
    draft(e)
    before = {p.name: p.read_bytes() for p in e.path.glob('notice*.db*')}
    configure(monkeypatch, e.path, '0')
    monkeypatch.setattr(NoticeSourceStore, 'initialize', forbidden)
    monkeypatch.setattr(NoticeDraftStore, 'initialize', forbidden)
    with TestClient(main.create_default_app()) as client:
        assert client.app.state.notice_draft_service is None
        error(client.post(e.base+'/notice-drafts', json={'idempotency_key': 'off'}),
              503, 'feature_disabled', 'notice_not_configured')
        error(client.get(e.base+'/notice-drafts/ntc_absent'), 404, 'not_found', 'notice_not_found')
    assert {p.name: p.read_bytes() for p in e.path.glob('notice*.db*')} == before


@pytest.mark.parametrize('name', ['notice_source.db', 'notice_draft.db'])
@pytest.mark.parametrize('failure', ['corrupt', 'symlink', 'capacity'])
def test_new_sidecar_initialization_failure_rejects_factory(factory, monkeypatch, name, failure):
    e = factory
    path = e.path/name
    if failure == 'corrupt':
        path.write_bytes(b'TEST_ONLY invalid database')
    elif failure == 'symlink':
        if path.exists():
            path.rename(e.path/('saved-'+name))
        path.symlink_to(e.path/('saved-'+name))
    else:
        def reject(self):
            raise (NoticeSourceStoreError if name == 'notice_source.db' else NoticeDraftStoreError)('storage_capacity_exceeded')
        monkeypatch.setattr(NoticeSourceStore if name == 'notice_source.db' else NoticeDraftStore, 'initialize', reject)
    before = {p.name: p.read_bytes() for p in e.path.glob('*.db') if not p.is_symlink()}
    called = []
    monkeypatch.setattr(main, 'create_app', lambda *args, **kwargs: called.append(True))
    with pytest.raises((NoticeSourceStoreError, NoticeDraftStoreError)):
        main.create_default_app()
    assert not called
    assert {p.name: p.read_bytes() for p in e.path.glob('*.db') if not p.is_symlink()} == before


def test_configured_report_missing_draft_is_404(factory):
    e = factory
    no_mutation(e, lambda: e.client.post(e.base+'/report-v2', json={
        'idempotency_key': 'missing', 'notice_refs': [{'draft_id': 'ntc_missing', 'content_hash': '0'*64}]}),
        404, 'not_found', 'notice_draft_not_found')


def test_invalid_scan_rejected_before_source_read(factory, monkeypatch):
    e = factory
    monkeypatch.setattr(e.app.state.notice_draft_service.bound_source_reader, 'read', forbidden)
    no_mutation(e, lambda: e.client.post('/api/v1/scans/not-a-scan-id/assessments/x/notice-drafts',
                json={'idempotency_key': 'bad'}), 400, 'invalid_argument', 'scan_id_invalid')


def test_capacity_rejection_preserves_business(factory):
    e = factory
    bound(e)
    e.app.state.notice_draft_service.store.max_record_bytes = 1
    no_mutation(e, lambda: post(e), 503, 'upstream_unavailable', 'storage_capacity_exceeded')
