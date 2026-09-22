"""Private exact-schema storage, corruption and immutable request bindings."""
import hashlib
import sqlite3
import os
from pathlib import Path

import pytest
from app.p1.notice_draft_store import NoticeDraftStore, NoticeDraftStoreError
from test_p1_notice_draft_backend import notice_env, create, hashes


def test_missing_read_does_not_create(tmp_path):
    store = NoticeDraftStore(tmp_path/'absent'/'notice_draft.db')
    assert store.get('s','a','d') is None
    assert not store.path.parent.exists()


@pytest.mark.parametrize('sql', [
    'CREATE TABLE surprise (x TEXT)',
    'PRAGMA user_version=2',
    'DELETE FROM notice_meta',
    'CREATE TRIGGER unsafe AFTER INSERT ON notice_drafts BEGIN DELETE FROM notice_requests; END',
])
def test_schema_rejected_before_write(notice_env, sql):
    env = notice_env
    with sqlite3.connect(env.notice_store.path) as db:
        db.execute(sql)
    before = hashes(env)
    with pytest.raises(NoticeDraftStoreError): env.notice_store.initialize()
    with pytest.raises(NoticeDraftStoreError): env.notice_store.get('s','a','d')
    assert hashes(env) == before


@pytest.mark.parametrize('field,value', [('scan_id','other'), ('assessment_id','other'), ('draft_id','ntc_other'), ('created_at','other'), ('fingerprint','0'*64), ('payload_hash','0'*64), ('payload',b'{}')])
def test_row_payload_binding(notice_env, field, value):
    env = notice_env
    draft = create(env)
    with sqlite3.connect(env.notice_store.path) as db:
        db.execute(f'UPDATE notice_drafts SET {field}=?', (value,))
    sid = value if field == 'scan_id' else env.run.id
    aid = value if field == 'assessment_id' else env.assessment.id
    did = value if field == 'draft_id' else draft.draft_id
    with pytest.raises(NoticeDraftStoreError): env.notice_store.get(sid, aid, did)


def test_request_key_tamper_is_detected(notice_env):
    env = notice_env
    create(env)
    with sqlite3.connect(env.notice_store.path) as db:
        db.execute("UPDATE notice_requests SET request_key='renamed'")
    with pytest.raises(Exception) as error: create(env, 'renamed')
    assert error.value.reason == 'storage_unavailable'


def test_query_only_connection(notice_env):
    db = notice_env.notice_store._connect()
    try:
        assert db.execute('PRAGMA query_only').fetchone() == (1,)
        with pytest.raises(sqlite3.OperationalError): db.execute('DELETE FROM notice_meta')
    finally: db.close()


def test_nonprivate_and_symlink_rejected(notice_env, tmp_path):
    env = notice_env
    env.notice_store.path.chmod(0o644)
    with pytest.raises(NoticeDraftStoreError): env.notice_store.get('s','a','d')
    env.notice_store.path.chmod(0o600)
    link = tmp_path/'linked'
    link.symlink_to(env.path, target_is_directory=True)
    with pytest.raises(NoticeDraftStoreError): NoticeDraftStore(link/'notice_draft.db').initialize()


def test_corrupt_db_unchanged(notice_env):
    path = notice_env.notice_store.path
    path.write_bytes(b'corrupt SQLite')
    before = path.read_bytes()
    with pytest.raises(NoticeDraftStoreError): notice_env.notice_store.initialize()
    assert path.read_bytes() == before


def test_wal_mode_rejected_without_creating_sidecars(notice_env):
    env = notice_env
    with sqlite3.connect(env.notice_store.path) as db:
        db.execute('PRAGMA journal_mode=WAL')
    db.close()
    before = {p.name: p.read_bytes() for p in env.path.glob('notice_draft.db*')}
    with pytest.raises(NoticeDraftStoreError): env.notice_store.get('s','a','d')
    assert {p.name:p.read_bytes() for p in env.path.glob('notice_draft.db*')} == before


@pytest.mark.parametrize('target', ['parent','db','-wal','-shm','-journal'])
def test_owner_r1_foreign_ownership_fails_closed(notice_env, monkeypatch, target):
    env = notice_env
    path = env.path if target == 'parent' else env.notice_store.path if target == 'db' else Path(str(env.notice_store.path)+target)
    if target.startswith('-'):
        path.touch(mode=0o600)
    before = {p.name:p.read_bytes() for p in env.path.glob('notice_draft.db*')}
    stat_before, lstat_before = Path.stat, Path.lstat
    def foreign(info):
        values = list(info)
        values[4] = os.geteuid() + 1
        return os.stat_result(values)
    def fake_stat(self, *args, **kwargs):
        info = stat_before(self, *args, **kwargs)
        return foreign(info) if self == path else info
    def fake_lstat(self, *args, **kwargs):
        info = lstat_before(self, *args, **kwargs)
        return foreign(info) if self == path else info
    def no_repair(*args, **kwargs):
        raise AssertionError('ownership must not be repaired')
    monkeypatch.setattr(Path, 'stat', fake_stat)
    monkeypatch.setattr(Path, 'lstat', fake_lstat)
    monkeypatch.setattr(os, 'chmod', no_repair)
    monkeypatch.setattr(os, 'chown', no_repair)
    # Direct guard avoids WAL-format rejection masking a missing owner check.
    with pytest.raises(NoticeDraftStoreError) as error:
        env.notice_store._guard()
    assert error.value.code == 'storage_unavailable'
    for action in (env.notice_store.initialize, lambda: env.notice_store.get('s','a','d')):
        with pytest.raises(NoticeDraftStoreError) as error:
            action()
        assert error.value.code == 'storage_unavailable'
    assert {p.name:p.read_bytes() for p in env.path.glob('notice_draft.db*')} == before
