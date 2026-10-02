"""A4-1 TEST_ONLY STAGED metadata: no init, no repair, no automatic binding."""
from dataclasses import FrozenInstanceError
import importlib
import sqlite3

import pytest
from app.p1.notice_source_store import NoticeSourceStore, NoticeSourceStoreError
from test_p1_notice_terminal_admission import terminal_env, terminal, business_rows, save_assessment, facts_digest, reject

def reader(source):
    api = importlib.import_module("app.p1.notice_source_store")
    return api.StagedNoticeSourceReader(source)

def test_missing_reader_does_not_initialize_or_create_directory(tmp_path):
    source = NoticeSourceStore(tmp_path/"absent"/"notice_source.db", min_free_bytes=0)
    assert reader(source).read("scn_TEST_ONLY") is None
    assert not (tmp_path/"absent").exists()

def test_initialized_empty_reader_does_not_write(terminal_env):
    e = terminal_env
    before = business_rows(e)
    assert reader(e.source).read(e.run.id) is None
    assert business_rows(e) == before

def test_stage_reader_restart_readonly_frozen_metadata_no_bytes(terminal_env, monkeypatch):
    e = terminal_env
    saved = e.source.stage(terminal(e))
    before = business_rows(e)
    def forbidden(*a, **kw):
        raise AssertionError("reader tried a write/init/upstream lookup")
    monkeypatch.setattr(e.source, "stage", forbidden)
    monkeypatch.setattr(e.source, "initialize", forbidden)
    monkeypatch.setattr(e.registry, "get", forbidden)
    monkeypatch.setattr(e.store, "get", forbidden)
    assert reader(e.source).read(e.run.id) == saved
    reopened = NoticeSourceStore(e.path/"notice_source.db", min_free_bytes=0)
    result = reader(reopened).read(e.run.id)
    assert result == saved
    assert not hasattr(result, "canonical_package_bytes")
    assert not hasattr(result, "bind") and not hasattr(result, "stage")
    with pytest.raises(FrozenInstanceError):
        result.package_hash = "0"*64
    assert business_rows(e) == before

@pytest.mark.parametrize("scan_id", ["", None, "/unsafe", True])
def test_reader_invalid_scan_identity(terminal_env, scan_id):
    e = terminal_env
    reject(e, lambda: reader(e.source).read(scan_id), "invalid_argument")

@pytest.mark.parametrize("column", ["input_json", "input_hash", "package_bytes", "package_hash"])
def test_reader_corruption_not_absence_and_no_repair(terminal_env, column):
    e = terminal_env
    e.source.stage(terminal(e))
    with sqlite3.connect(e.source.path) as db:
        db.execute(f"UPDATE notice_source_staged SET {column}=?", (b"corrupt" if column in ("input_json","package_bytes") else "0"*64,))
    reject(e, lambda: reader(e.source).read(e.run.id), "storage_unavailable")

@pytest.mark.parametrize("failure", ["db_symlink", "db_mode", "wal", "shm", "journal", "schema", "corrupt_db"])
def test_reader_unsafe_sidecar_fails_closed_without_mutation(terminal_env, failure):
    e = terminal_env
    e.source.stage(terminal(e))
    path = e.source.path
    if failure == "db_symlink":
        target = e.path/"TEST_ONLY_original.db"
        path.rename(target)
        path.symlink_to(target)
    elif failure == "db_mode":
        path.chmod(0o644)
    elif failure in ("wal", "shm", "journal"):
        sidecar = e.path/f"notice_source.db-{failure}"
        sidecar.write_bytes(b"TEST_ONLY unsafe")
        sidecar.chmod(0o644)
    elif failure == "schema":
        with sqlite3.connect(path) as db:
            db.execute("PRAGMA user_version=99")
    else:
        path.write_bytes(b"TEST_ONLY corrupt database")
    original = path.read_bytes()
    with pytest.raises(NoticeSourceStoreError) as caught:
        reader(e.source).read(e.run.id)
    assert caught.value.code == "storage_unavailable"
    assert path.read_bytes() == original

def test_reader_snapshot_stale_hash_is_not_auto_refreshed_for_bind(terminal_env):
    e = terminal_env
    e.source.stage(terminal(e))
    old = reader(e.source).read(e.run.id)
    newer = e.capture("2026-10-01T00:01:00Z")
    e.collection = newer.consumer_result
    e.kw["ingestion_result"] = newer
    new_value = terminal(e)
    e.source.replace_unbound_stage(new_value, scan_id=e.run.id, expected_current_package_hash=old.package_hash)
    current = reader(e.source).read(e.run.id)
    assert current.package_hash != old.package_hash
    a = save_assessment(e, e.run)
    kw = dict(scan_id=e.run.id, expected_registry_revision=3, assessment_id=a.id, expected_assessment_version=1)
    reject(e, lambda:e.service.bind(**kw, expected_package_hash=old.package_hash), "binding_mismatch")
    assert e.bound_reader.read(e.run.id, facts_digest(e.run), a.id, 1) is None
    assert e.service.bind(**kw, expected_package_hash=current.package_hash).package_hash == current.package_hash

def test_reader_does_not_relax_bound_freeze_or_required_hash(terminal_env):
    e = terminal_env
    e.source.stage(terminal(e))
    a = save_assessment(e, e.run)
    kw = dict(scan_id=e.run.id, expected_registry_revision=3, assessment_id=a.id, expected_assessment_version=1)
    old = reader(e.source).read(e.run.id)
    e.service.bind(**kw, expected_package_hash=old.package_hash)
    new = e.capture("2026-10-01T00:01:00Z")
    e.collection, e.kw["ingestion_result"] = new.consumer_result, new
    reject(e, lambda:e.source.replace_unbound_stage(terminal(e), scan_id=e.run.id,
        expected_current_package_hash=old.package_hash), "conflict")
    with pytest.raises(TypeError):
        e.service.bind(**kw)

def test_failed_bind_rolls_back_and_reader_keeps_stage(terminal_env, monkeypatch):
    e = terminal_env
    stage = e.source.stage(terminal(e))
    a = save_assessment(e, e.run)
    def fail(*args):
        raise sqlite3.OperationalError("TEST_ONLY failure before publication")
    monkeypatch.setattr(e.source, "_capacity", fail)
    reject(e, lambda:e.service.bind(scan_id=e.run.id, expected_registry_revision=3,
        assessment_id=a.id, expected_assessment_version=1, expected_package_hash=stage.package_hash),
        "storage_unavailable")
    assert reader(e.source).read(e.run.id) == stage
    assert e.bound_reader.read(e.run.id, facts_digest(e.run), a.id, 1) is None
