"""A1 admission/binding tests. Input is TEST_ONLY_NOTICE_SOURCE_INPUT, not CZ output."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from app.assessment.engine import facts_digest
from app.assessment.store import AssessmentStore
from app.persistence import SQLiteScanRunRegistry
from app.p1.notice_source_store import (
    BoundNoticeSource, BoundNoticeSourceReader, NoticeSourceBindingService, NoticeSourceStore,
    NoticeSourceStoreError, ValidatedNoticeSourceInput,
)
from test_p1_diff_api import assessment as make_assessment
from test_p1_history_api import seed


def package_bytes(marker='first'):
    return json.dumps({'test_only': marker}, sort_keys=True, separators=(',', ':')).encode()


@pytest.fixture
def env(tmp_path):
    tmp_path.chmod(0o700)
    state = SimpleNamespace(path=tmp_path)
    state.registry = SQLiteScanRunRegistry(tmp_path / 'scans.db')
    state.store = AssessmentStore(tmp_path / 'assessment.db', min_free_bytes=0)
    state.store.initialize()
    state.run = seed(state, 8101, 'completed')
    state.assessment = make_assessment(state, state.run)
    state.source = NoticeSourceStore(tmp_path / 'notice_source.db', min_free_bytes=0)
    state.source.initialize()
    state.service = NoticeSourceBindingService(state.source, state.registry, state.store)
    state.reader = BoundNoticeSourceReader(state.source)
    yield state
    state.registry.close()


def admission(env, **changes):
    raw = package_bytes()
    value = dict(scan_id=env.run.id, canonical_package_bytes=raw,
                 package_hash=hashlib.sha256(raw).hexdigest(),
                 collector_schema_version='TEST_ONLY_NOTICE_SOURCE_INPUT',
                 producer='test-only', producer_version='1',
                 observed_input_digest=env.run.provenance.input_digest.value,
                 observed_inventory_digest=env.run.provenance.inventory_digest.value,
                 coverage_status='completed', omissions=[], gap_codes=[])
    value.update(changes)
    return ValidatedNoticeSourceInput(**value)


def bind(env, **changes):
    value = dict(scan_id=env.run.id, expected_registry_revision=3,
                 assessment_id=env.assessment.id,
                 expected_assessment_version=env.assessment.version)
    value.update(changes)
    return env.service.bind(**value)


def read(env, **changes):
    value = dict(scan_id=env.run.id, facts_hash=facts_digest(env.run),
                 assessment_id=env.assessment.id,
                 assessment_version=env.assessment.version)
    value.update(changes)
    return env.reader.read(**value)


def test_completed_staged_then_bound_and_read_only(env):
    assert read(env) is None
    staged = env.source.stage(admission(env))
    assert staged.state == 'STAGED' and read(env) is None
    before = env.registry.get(env.run.id)
    fixed = bind(env)
    assert fixed.state == 'BOUND'
    assert fixed.scan_id == env.run.id and fixed.registry_revision == 3
    assert fixed.facts_hash == facts_digest(env.run)
    assert fixed.assessment_id == env.assessment.id and fixed.assessment_version == env.assessment.version
    assert fixed.package_hash == staged.package_hash
    assert read(env) == fixed and env.registry.get(env.run.id) == before
    assert read(env, facts_hash='0' * 64) is None
    assert read(env, assessment_id='asm_wrong') is None
    assert read(env, assessment_version=2) is None
    old = env.path.joinpath('notice_source.db').read_bytes()
    for _ in range(3):
        assert read(env) == fixed
    assert env.path.joinpath('notice_source.db').read_bytes() == old


def test_partial_coverage_keeps_both_lists(env):
    env.run = seed(env, 8102, 'partial')
    env.assessment = make_assessment(env, env.run)
    env.source.stage(admission(env, coverage_status='partial', omissions=['path-limit'], gap_codes=[]))
    fixed = bind(env)
    assert fixed.coverage_status == 'partial'
    assert fixed.omissions == ('path-limit',) and fixed.gap_codes == ()


@pytest.mark.parametrize('changes', [
    {'canonical_package_bytes': package_bytes('tampered')},
    {'package_hash': '0' * 64},
    {'coverage_status': 'completed', 'gap_codes': ['missing']},
    {'coverage_status': 'partial'},
    {'coverage_status': 'partial', 'omissions': None},
    {'coverage_status': 'partial', 'omissions': '', 'gap_codes': []},
    {'coverage_status': 'partial', 'omissions': [], 'gap_codes': []},
    {'coverage_status': 'partial', 'omissions': [], 'gap_codes': None},
    {'coverage_status': 'partial', 'omissions': ['/Users/private/source'], 'gap_codes': []},
])
def test_invalid_admission_rejected_without_stage(env, changes):
    value = admission(env).__dict__.copy()
    value.update(changes)
    if changes == {'coverage_status': 'partial'}:
        value.pop('gap_codes')
    with pytest.raises(NoticeSourceStoreError) as caught:
        env.source.stage(value)
    assert caught.value.code == 'invalid_argument'
    assert read(env) is None


@pytest.mark.parametrize('field', ['scan_id', 'observed_input_digest', 'observed_inventory_digest'])
def test_staged_identity_mismatch_rejected_at_bind(env, field):
    env.source.stage(admission(env, **{field: '0' * 64 if field != 'scan_id' else 'scn_wrong'}))
    with pytest.raises(NoticeSourceStoreError) as caught:
        bind(env)
    assert caught.value.code == ('not_ready' if field == 'scan_id' else 'binding_mismatch')
    assert read(env) is None


def test_stale_revision_and_wrong_assessment_version(env):
    env.source.stage(admission(env))
    for changes in ({'expected_registry_revision': 2}, {'expected_assessment_version': 2}):
        with pytest.raises(NoticeSourceStoreError) as caught:
            bind(env, **changes)
        assert caught.value.code == 'binding_mismatch'
    assert read(env) is None


def test_assessment_binding_fail_closed(env, monkeypatch):
    env.source.stage(admission(env))
    original = env.store.get
    for field, value in [('scan_id', 'scn_wrong'), ('facts_hash', '0' * 64), ('formal', False), ('id', 'asm_wrong')]:
        monkeypatch.setattr(env.store, 'get', lambda *args, f=field, v=value: original(*args).model_copy(update={f: v}))
        with pytest.raises(NoticeSourceStoreError) as caught:
            bind(env)
        assert caught.value.code == 'binding_mismatch'
    assert read(env) is None


@pytest.mark.parametrize('status', ['failed', 'cancelled', 'running'])
def test_non_bindable_scan_status(env, status):
    env.run = seed(env, 8110 + ['failed','cancelled','running'].index(status), status)
    env.source.stage(admission(env))
    with pytest.raises(NoticeSourceStoreError) as caught:
        bind(env)
    assert caught.value.code == 'not_ready'
    assert read(env) is None


def test_replay_conflict_restart_and_tamper(env):
    staged = env.source.stage(admission(env))
    assert env.source.stage(admission(env)) == staged
    fixed = bind(env)
    assert bind(env) == fixed
    changed = package_bytes('different')
    with pytest.raises(NoticeSourceStoreError) as caught:
        env.source.stage(admission(env, canonical_package_bytes=changed,
                                   package_hash=hashlib.sha256(changed).hexdigest()))
    assert caught.value.code == 'conflict'
    reopened = NoticeSourceStore(env.path / 'notice_source.db', min_free_bytes=0)
    reopened.initialize()
    assert BoundNoticeSourceReader(reopened).read(env.run.id, facts_digest(env.run),
                                                env.assessment.id, env.assessment.version) == fixed
    with sqlite3.connect(env.path / 'notice_source.db') as db:
        db.execute("UPDATE notice_source_staged SET package_bytes=? WHERE scan_id=?", (b'tampered', env.run.id))
    with pytest.raises(NoticeSourceStoreError) as caught:
        read(env)
    assert caught.value.code == 'storage_unavailable'


def test_second_formal_version_has_explicit_distinct_binding(env):
    env.source.stage(admission(env))
    first = bind(env)
    second_assessment = make_assessment(env, env.run, version=2)
    second = bind(env, assessment_id=second_assessment.id, expected_assessment_version=2)
    assert second.assessment_id != first.assessment_id
    assert second.assessment_version == 2 and first.assessment_version == 1
    assert read(env) == first
    assert read(env, assessment_id=second_assessment.id, assessment_version=2) == second
    with pytest.raises(NoticeSourceStoreError) as caught:
        bind(env, assessment_id=second_assessment.id, expected_assessment_version=1)
    assert caught.value.code == 'binding_mismatch'


def test_uninitialized_reader_does_not_create_file(env):
    path = env.path / 'uninitialized' / 'notice_source.db'
    reader = BoundNoticeSourceReader(NoticeSourceStore(path, min_free_bytes=0))
    assert reader.read(env.run.id, facts_digest(env.run), env.assessment.id, 1) is None
    assert not path.exists() and not path.parent.exists()


def test_private_storage_modes_and_tampered_binding_row(env):
    env.source.stage(admission(env))
    bind(env)
    assert os.stat(env.path / 'notice_source.db').st_mode & 0o077 == 0
    with sqlite3.connect(env.path / 'notice_source.db') as db:
        db.execute('UPDATE notice_source_bindings SET binding_hash=? WHERE scan_id=?',
                   ('0' * 64, env.run.id))
    with pytest.raises(NoticeSourceStoreError) as caught:
        read(env)
    assert caught.value.code == 'storage_unavailable'


def test_insecure_database_and_sidecar_fail_closed(env):
    env.source.stage(admission(env))
    bind(env)
    path = env.path / 'notice_source.db'
    path.chmod(0o644)
    try:
        with pytest.raises(NoticeSourceStoreError) as caught:
            read(env)
        assert caught.value.code == 'storage_unavailable'
    finally:
        path.chmod(0o600)
    sidecar = env.path / 'notice_source.db-wal'
    sidecar.symlink_to(path)
    with pytest.raises(NoticeSourceStoreError) as caught:
        read(env)
    assert caught.value.code == 'storage_unavailable'


def test_foreign_database_owner_fails_closed_without_chown(env, monkeypatch):
    env.source.stage(admission(env))
    bind(env)
    path = env.path / 'notice_source.db'
    real_lstat = Path.lstat

    def foreign_owner(item):
        info = real_lstat(item)
        if item == path:
            return SimpleNamespace(st_mode=info.st_mode, st_uid=info.st_uid + 1,
                                   st_nlink=info.st_nlink)
        return info

    monkeypatch.setattr(Path, 'lstat', foreign_owner)
    with pytest.raises(NoticeSourceStoreError) as caught:
        read(env)
    assert caught.value.code == 'storage_unavailable'


def test_partial_gap_codes_without_omissions_kept_exactly(env):
    env.source.stage(admission(env, coverage_status='partial', omissions=[], gap_codes=['TEXT_LIMIT']))
    fixed = bind(env)
    assert fixed.omissions == () and fixed.gap_codes == ('TEXT_LIMIT',)


def test_package_limit(env):
    raw = b'x' * (8 * 1024 * 1024)
    env.source.stage(admission(env, canonical_package_bytes=raw,
                               package_hash=hashlib.sha256(raw).hexdigest()))
    other = seed(env, 8199, 'completed')
    huge = raw + b'x'
    with pytest.raises(NoticeSourceStoreError) as caught:
        env.source.stage(admission(env, scan_id=other.id, canonical_package_bytes=huge,
                                   package_hash=hashlib.sha256(huge).hexdigest()))
    assert caught.value.code == 'storage_capacity_exceeded'


def source_rows(env):
    with sqlite3.connect(env.source.path) as db:
        return {table: db.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall()
                for table in ('notice_source_meta', 'notice_source_staged', 'notice_source_bindings')}


def forged_binding(env):
    meta = vars(admission(env))
    return dict(scan_id=env.run.id, registry_revision=999,
                input_digest=meta['observed_input_digest'],
                inventory_digest=meta['observed_inventory_digest'],
                facts_hash='0' * 64, assessment_id='asm_no_such_assessment',
                assessment_version=1, assessment_facts_hash='0' * 64,
                package_hash=meta['package_hash'],
                collector_schema_version=meta['collector_schema_version'],
                producer=meta['producer'], producer_version=meta['producer_version'],
                coverage_status='completed', omissions=[], gap_codes=[],
                bound_at='2026-09-26T00:00:00Z')


def test_bound_record_cannot_be_published_without_trusted_binding_service(env):
    # Supported API boundary, not isolation from malicious same-process Python/SQL.
    staged = env.source.stage(admission(env))
    assert staged.state == 'STAGED' and not hasattr(staged, 'canonical_package_bytes')
    before = source_rows(env)
    for field, value in [('state', 'BOUND'), ('binding_hash', '0' * 64), ('verified', True)]:
        with pytest.raises(NoticeSourceStoreError) as caught:
            env.source.stage({**vars(admission(env)), field: value})
        assert caught.value.code == 'invalid_argument'
    forged = forged_binding(env)
    caller_bound = BoundNoticeSource(state='BOUND', **{**forged, 'omissions': (), 'gap_codes': ()},
                                    binding_hash='0' * 64, canonical_package_bytes=package_bytes())
    with pytest.raises(NoticeSourceStoreError) as caught:
        env.source.stage(caller_bound)
    assert caught.value.code == 'invalid_argument'
    # Exercise the former bypass if it exists; never merely omit the dangerous call.
    for name in ('put', 'save', 'upsert', 'save_binding', '_save_binding'):
        method = getattr(env.source, name, None)
        if callable(method):
            try:
                method(forged)
            except (NoticeSourceStoreError, TypeError):
                pass
    assert env.reader.read(env.run.id, '0' * 64, forged['assessment_id'], 1) is None
    assert source_rows(env) == before
    assert {n for n in dir(env.source) if not n.startswith('_') and callable(getattr(env.source, n))} == {'initialize', 'stage'}
    assert not hasattr(env.source, '_save_binding')
    assert not hasattr(env.source, '_load_for_binding')
    assert read(env) is None
    fixed = bind(env)
    assert fixed == read(env)


def test_failed_binding_leaves_no_bound_or_conflicting_record(env, monkeypatch):
    env.source.stage(admission(env))
    before = source_rows(env)
    original = env.source._load_stage
    loads = 0

    def wrong_candidate_package(db, scan_id):
        nonlocal loads
        result = original(db, scan_id)
        loads += 1
        if loads == 1 and result is not None:
            # Same invalid package candidate as Owner B2, without modifying stored bytes.
            meta, raw = result
            return {**meta, 'package_hash': '0' * 64}, raw
        return result

    with monkeypatch.context() as patch:
        patch.setattr(env.source, '_load_stage', wrong_candidate_package)
        with pytest.raises(NoticeSourceStoreError) as caught:
            bind(env)
        assert caught.value.code == 'storage_unavailable'
    assert source_rows(env) == before
    assert read(env) is None
    fixed = bind(env)
    assert fixed == read(env)
    assert len(source_rows(env)['notice_source_bindings']) == 1


@pytest.mark.parametrize('failure', ['sqlite_full', 'internal_error'])
def test_binding_insert_failure_rolls_back_same_transaction(env, monkeypatch, failure):
    env.source.stage(admission(env))
    before = source_rows(env)
    connect = env.source._connect
    trace = []
    inserts = []

    class FailureConnection:
        def __init__(self, db):
            self.db = db
            self.db.set_trace_callback(trace.append)

        def execute(self, sql, *args):
            cursor = self.db.execute(sql, *args)
            if sql.startswith('INSERT INTO notice_source_bindings'):
                inserts.append(self.db.execute('SELECT COUNT(*) FROM notice_source_bindings').fetchone()[0])
                assert self.db.in_transaction
                if failure == 'sqlite_full':
                    error = sqlite3.OperationalError('TEST_ONLY injected full')
                    error.sqlite_errorcode = sqlite3.SQLITE_FULL
                    raise error
                raise NoticeSourceStoreError('storage_unavailable')
            return cursor

        def __enter__(self):
            self.db.__enter__()
            return self

        def __exit__(self, *args):
            return self.db.__exit__(*args)

        def close(self):
            self.db.close()

    with monkeypatch.context() as patch:
        patch.setattr(env.source, '_connect', lambda **kw: FailureConnection(connect(**kw)))
        with pytest.raises(NoticeSourceStoreError) as caught:
            bind(env)
        assert caught.value.code == ('storage_capacity_exceeded' if failure == 'sqlite_full' else 'storage_unavailable')
    assert inserts == [1]  # The injected failure is after a real INSERT, before commit.
    assert 'BEGIN IMMEDIATE' in trace and 'ROLLBACK' in trace and 'COMMIT' not in trace
    assert not any(sql.startswith('DELETE') for sql in trace)
    assert source_rows(env) == before and read(env) is None
    assert bind(env) == read(env)


def test_binding_conflict_keeps_existing_identity(env, monkeypatch):
    env.source.stage(admission(env))
    fixed = bind(env)
    before = source_rows(env)
    stored = env.registry.get(env.run.id)
    # TEST_ONLY newer CAS snapshot, identical ScanRun; not a real terminal update.
    monkeypatch.setattr(env.registry, 'get', lambda _: SimpleNamespace(run=stored.run, revision=4))
    with pytest.raises(NoticeSourceStoreError) as caught:
        bind(env, expected_registry_revision=4)
    assert caught.value.code == 'conflict'
    assert source_rows(env) == before and read(env) == fixed
