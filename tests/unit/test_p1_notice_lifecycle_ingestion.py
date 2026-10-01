"""A4-2 permanent gates: controlled local inputs, never real apply or network."""
from dataclasses import replace
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import sqlite3
import threading
from types import SimpleNamespace
import zipfile

import pytest
from app.assessment.store import AssessmentStore
from app.ingestion import ZipIngestionService, ScanReadLimits
from app.notice_source.models import NoticeSourceCollection, canonical_json
from app.persistence import SQLiteScanRunRegistry
from app.p1.notice_source_store import NoticeSourceStore, NoticeSourceStoreError
from app.pipeline.dependency_plan import READ_LIMITS
from app.pipeline.local_zip import _consume_dependencies
from test_a4_local_zip_pipeline import _queued, NOW
from test_a2_public_git_ingestion import local_git_service, _git

FILES = {"requirements.txt": "requests==2.32.5\n", "NOTICE": "Owned controlled NOTICE text.\n"}


def api():
    return importlib.import_module("app.ingestion.notice_ingestion")


def lifecycle(e, **kwargs):
    module = importlib.import_module("app.p1.notice_source_lifecycle")
    return module.NoticeSourceLifecycle(e.registry, e.assessments, e.source_store, **kwargs)


def rows(root):
    out = {}
    for p in sorted(root.glob("*.db")):
        with sqlite3.connect(f"file:{p}?mode=ro", uri=True) as db:
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            out[p.name] = {t: db.execute('SELECT * FROM "' + t.replace('"', '""') + '" ORDER BY rowid').fetchall() for t in tables}
    return out


@pytest.fixture
def env(tmp_path):
    tmp_path.chmod(0o700)
    e = SimpleNamespace(path=tmp_path)
    e.uploads = tmp_path / "uploads"; e.uploads.mkdir(mode=0o700)
    e.workspace = tmp_path / "workspaces"; e.workspace.mkdir(mode=0o700)
    e.registry = SQLiteScanRunRegistry(tmp_path / "scans.db")
    e.assessments = AssessmentStore(tmp_path / "assessment.db", min_free_bytes=0); e.assessments.initialize()
    e.source_store = NoticeSourceStore(tmp_path / "notice_source.db", min_free_bytes=0); e.source_store.initialize()
    yield e
    e.registry.close()


def archive(e, files=None, index=1):
    p = e.uploads / f"owned-{index}.zip"
    with zipfile.ZipFile(p, "w", compression=zipfile.ZIP_STORED) as z:
        for name, data in (FILES if files is None else files).items(): z.writestr(name, data)
    p.chmod(0o600)
    return p, _queued(p, index)


def completed(e, *, files=None, index=1, dependency=None, notice=None, service=None, tree=None):
    p, run = archive(e, files, index)
    lc = lifecycle(e)
    proof = api().complete_zip_ingestion(service or ZipIngestionService(e.workspace),
        archive_path=p, upload_root=e.uploads, scan_id=run.id,
        expected_input_digest=run.provenance.input_digest.value,
        dependency_consumer=dependency or (lambda session: _consume_dependencies(session, lambda: NOW)),
        notice_consumer=notice or lc.collect, read_limits=READ_LIMITS, tree_consumer=tree)
    return proof, p, run, lc


def test_w01_real_zip_keeps_original_dependency_and_returns_actual_envelope(env):
    e = env; seen = []; sessions = []
    def dependency(session):
        sessions.append(session); value = _consume_dependencies(session, lambda: NOW); seen.append(value); return value
    proof, _, run, _ = completed(e, dependency=dependency)
    assert proof.scan_id == run.id
    assert proof.result.consumer_result.dependencies is seen[0]
    assert proof.result.consumer_result.collection.observations[0].content.text == FILES["NOTICE"]
    assert proof.result.inventory.entries
    assert list(e.workspace.iterdir()) == []
    with pytest.raises(Exception, match="scan_session_expired"): sessions[0].read_bytes("NOTICE")


def test_w02_real_git_keeps_revision_runtime_egress_and_notice(local_git_service, env):
    svc, root = local_git_service
    repository = root.parent / "source"
    (repository / "NOTICE").write_text("Owned offline Git notice.\n")
    _git(repository, "add", "NOTICE"); _git(repository, "commit", "--quiet", "-m", "owned notice")
    revision = _git(repository, "rev-parse", "HEAD").decode().strip()
    source = "https://github.com/example/repo"
    proof = api().complete_git_ingestion(svc, source=source, scan_id="controlled-git",
        expected_input_digest=hashlib.sha256(source.encode()).hexdigest(),
        dependency_consumer=lambda session:_consume_dependencies(session, lambda:NOW),
        notice_consumer=lifecycle(env).collect, read_limits=READ_LIMITS)
    assert proof.result.revision == revision and proof.result.runtime_identity.version
    assert proof.result.egress_evidence and isinstance(proof.result.omissions, tuple)
    assert proof.result.consumer_result.collection.observations[0].content.text == "Owned offline Git notice.\n"
    assert list(root.iterdir()) == []


def test_w03_dependency_notice_tree_order_and_one_shared_budget(env):
    e = env; order = []; session_ids = []
    lc = lifecycle(e)
    def dependency(session):
        order.append("dependencies"); session_ids.append(id(session)); session.read_bytes("NOTICE"); return object()
    def notice(session, limits):
        order.append("notice"); session_ids.append(id(session)); assert session.remaining_read_bytes < limits.total_max_bytes
        return lc.collect(session, limits)
    proof, _, _, _ = completed(e, dependency=dependency, notice=notice, tree=lambda *a: order.append("tree"))
    assert order == ["dependencies", "notice", "tree"] and len(set(session_ids)) == 1
    assert proof.result.consumer_result.collection is not None


def test_w03_two_plan_local_proofs_do_not_mix(env):
    barrier = threading.Barrier(2)
    def dependency(session):
        barrier.wait(timeout=10)
        return _consume_dependencies(session, lambda: NOW)
    def run(index):
        return completed(env, index=index, dependency=dependency,
            files={**FILES, "NOTICE": f"Owned parallel notice {index}."})[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = list(pool.map(run, [1, 2]))
    assert a is not b and a.scan_id != b.scan_id
    assert [p.result.consumer_result.collection.observations[0].content.text for p in (a, b)] == [
        "Owned parallel notice 1.", "Owned parallel notice 2."]
    assert not list(env.workspace.iterdir())


@pytest.mark.parametrize("case", ["zero", "truncated", "ordinary_error"])
def test_w04_w05_w06_normal_notice_failure_keeps_original_dependencies(env, monkeypatch, case):
    lc = lifecycle(env); m = importlib.import_module("app.p1.notice_source_lifecycle"); calls = []
    real = m.collect_notice_source_package
    def collector(*args, **kw):
        calls.append(1)
        if case == "ordinary_error": raise ValueError("untrusted detail not in diagnostic")
        return real(*args, **kw)
    monkeypatch.setattr(m, "collect_notice_source_package", collector)
    files = {"requirements.txt": FILES["requirements.txt"]} if case == "zero" else FILES
    if case == "truncated": files = {**files, **{f"p{i:04}/NOTICE": "n" for i in range(1025)}}
    proof, _, _, _ = completed(env, files=files, notice=lc.collect)
    assert proof.result.consumer_result.dependencies.lanes
    assert proof.result.consumer_result.collection is None
    assert len(calls) == (1 if case == "ordinary_error" else 0)
    assert not env.source_store._read_staged(proof.scan_id)


@pytest.mark.parametrize("fault", ["latch", "tree", "cleanup", "service_close", "input_close"])
def test_w06_no_completion_on_safety_or_final_cleanup_close_failure(env, monkeypatch, fault):
    m = api(); lc = lifecycle(env)
    svc = ZipIngestionService(env.workspace); issued = []
    def dependency(session):
        if fault == "latch":
            try: session.read_bytes("not-in-inventory")
            except Exception: pass
        return object()
    def fail(*a, **k): raise OSError("controlled final boundary failure")
    if fault == "cleanup": monkeypatch.setattr(svc._workspaces, "cleanup", fail)
    if fault == "service_close": monkeypatch.setattr(svc, "close", fail)
    if fault == "input_close": monkeypatch.setattr(m, "_close_input", fail)
    with pytest.raises(Exception):
        issued.append(completed(env, service=svc, dependency=dependency, tree=fail if fault == "tree" else None)[0])
    assert issued == [] and not env.source_store._read_staged("controlled")


def test_w07_path_replacement_rejects_ctime_change_without_reopen(env):
    p, run = archive(env); original = p.read_bytes(); lc = lifecycle(env)
    def dependency(session):
        old = p.with_suffix(".retained"); p.rename(old); p.write_bytes(b"wrong replacement"); p.chmod(0o600)
        return _consume_dependencies(session, lambda: NOW)
    m = api()
    with pytest.raises(m.NoticeIngestionError, match="input_identity_changed"):
        m.complete_zip_ingestion(ZipIngestionService(env.workspace), archive_path=p,
            upload_root=env.uploads, scan_id=run.id, expected_input_digest=hashlib.sha256(original).hexdigest(),
            dependency_consumer=dependency, notice_consumer=lc.collect, read_limits=READ_LIMITS)
    assert p.read_bytes() == b"wrong replacement"


@pytest.mark.parametrize("case", ["symlink", "outside_root", "public", "hardlink", "wrong_digest", "growth"])
def test_w07_w08_unsafe_input_never_issues_proof(env, case):
    p, run = archive(env); lc = lifecycle(env); expected = run.provenance.input_digest.value
    if case == "symlink":
        target = p.with_suffix(".data"); p.rename(target); p.symlink_to(target)
    if case == "outside_root":
        target = env.path / p.name; p.rename(target); p = target
    if case == "public": p.chmod(0o644)
    if case == "hardlink": os.link(p, p.with_suffix(".link"))
    if case == "wrong_digest": expected = "0" * 64
    def dep(session):
        if case == "growth":
            with p.open("ab") as f: f.write(b"changed")
        return object()
    with pytest.raises(Exception):
        api().complete_zip_ingestion(ZipIngestionService(env.workspace), archive_path=p,
            upload_root=env.uploads, scan_id=run.id, expected_input_digest=expected,
            dependency_consumer=dep, notice_consumer=lc.collect, read_limits=READ_LIMITS)


@pytest.mark.parametrize("case", ["short_legal", "exact", "plus_one", "early_eof", "non_eof", "not_bytes", "read_zero"])
def test_w08_bounded_reader_true_eof_and_stream_accounting(tmp_path, case):
    m = api(); p = tmp_path / "owned"; p.write_bytes(b"12345"); p.chmod(0o600)
    with p.open("rb") as raw:
        class Chunks:
            def read(self, size):
                if case == "not_bytes": return "x"
                if case == "early_eof": return b""
                if case == "non_eof": return b"x" * min(size, 2)
                return raw.read(min(size, 2))
        r = m._BoundedDigestReader(Chunks(), expected_size=5, max_bytes=4 if case == "plus_one" else 5)
        def consume():
            if case == "read_zero": assert r.read(0) == b"" and r.eof is False
            while r.read(65536): pass
            r.verify(hashlib.sha256(b"12345").hexdigest())
        if case in {"plus_one", "early_eof", "non_eof", "not_bytes"}:
            with pytest.raises(Exception): consume()
        else:
            consume(); assert r.count == 5 and r.eof is True


@pytest.mark.parametrize("kind", ["copy", "deepcopy", "constructed", "altered_inventory", "altered_scan"])
def test_w09_completion_is_not_constructible_copyable_or_mutable(env, kind):
    proof, _, _, _ = completed(env)
    with pytest.raises(Exception):
        if kind == "copy": api().validate_completed_ingestion(copy.copy(proof))
        elif kind == "deepcopy": api().validate_completed_ingestion(copy.deepcopy(proof))
        elif kind == "constructed": api().CompletedNoticeIngestion(proof.result, proof.input_digest)
        elif kind == "altered_inventory":
            object.__setattr__(proof.result.inventory, "root_digest", "f" * 64); api().validate_completed_ingestion(proof)
        else:
            object.__setattr__(proof, "scan_id", "other"); api().validate_completed_ingestion(proof)


@pytest.mark.parametrize("field", ["observed_at", "coverage", "producer", "relation", "text", "locator", "key"])
def test_w09_full_collection_seal_rejects_format_legal_mutation(env, field):
    proof, _, _, _ = completed(env); c = proof.result.consumer_result.collection
    data = c.model_dump(mode="json")
    if field == "observed_at": data[field] = "2026-10-01T00:00:01Z"
    elif field == "coverage": data[field] = {"state": "partial", "omissions": ["NOTICE"], "gap_codes": ["read_failed"]}
    elif field == "producer": data["observations"][0]["collector"]["version"] = "1.0.1"
    elif field == "relation": data["observations"][0]["relation"]["basis"] = "valid_different_basis"
    elif field == "locator": data["observations"][0]["locator"] = "requirements.txt"
    elif field == "key": data["observations"][0]["observation_key"] = "valid-other-key"
    else:
        o = data["observations"][0]["content"]; o["text"] = "Modified legal text."
        h = hashlib.sha256(o["text"].encode()).hexdigest(); o.update(byte_range=[0, len(o["text"].encode())], retained_bytes_sha256=h, whole_bytes_sha256=h)
    valid = NoticeSourceCollection.model_validate(data)  # legal DTO, not a parsing-negative shortcut
    for key in type(c).model_fields: object.__setattr__(c, key, getattr(valid, key))
    with pytest.raises(Exception): api().validate_completed_ingestion(proof)


def test_w10_proof_contains_no_session_fd_stream_workspace_capability(env):
    proof, p, _, _ = completed(env)
    p.unlink()
    api().validate_completed_ingestion(proof)  # no re-open
    assert set(proof.__slots__) == {"scan_id", "source", "source_type", "input_digest", "result", "_verify"}
    assert list(env.workspace.iterdir()) == []


def test_producer_config_reproducible_effective_and_not_test_identity(env):
    m = importlib.import_module("app.p1.notice_source_lifecycle")
    config = m.producer_configuration(READ_LIMITS)
    assert config == m.producer_configuration(READ_LIMITS)
    producer = lifecycle(env).producer_for(READ_LIMITS)
    assert (producer.type, producer.name, producer.version) == ("collector", "openguard-notice-source-collector", "1.0.0")
    assert producer.config_digest == hashlib.sha256(canonical_json(config)).hexdigest()
    lower = ScanReadLimits(single_file_max_bytes=65536, total_max_bytes=1024*1024)
    assert m.producer_configuration(lower) != config
    assert lifecycle(env).producer_for(lower).config_digest != producer.config_digest
    text = canonical_json(config).decode()
    assert not any(secret in text for secret in (str(env.path), "TEST_ONLY", "scan_id", "assessment_id", "observed_at"))


def test_w03_w06_exhausted_budget_is_partial_before_read_no_quota_reset(env):
    files = {"NOTICE": "n", **{f"large{i}": b"x"*(4*1024*1024) for i in range(4)}}
    def dependency(session):
        for i in range(4): session.read_bytes(f"large{i}")
        assert session.remaining_read_bytes == 0
        return object()
    proof,_,_,_=completed(env,files=files,dependency=dependency)
    c=proof.result.consumer_result.collection
    assert c.coverage.state=="partial" and c.coverage.omissions==["NOTICE"]
    assert c.coverage.gap_codes==["read_budget_exhausted"]
    assert c.observations[0].content.state=="not_scanned"


def test_w06_final_tree_integrity_failure_discards_provisional_notice(env):
    def tamper(tree,inventory):
        fd=os.open("NOTICE",os.O_WRONLY|os.O_TRUNC,dir_fd=tree._directory_fd)
        try:os.write(fd,b"tampered after collection")
        finally:os.close(fd)
    from app.security.errors import IngestionSecurityError
    with pytest.raises(IngestionSecurityError):completed(env,tree=tamper)
    assert list(env.workspace.iterdir())==[]


def test_w09_reconstructed_callback_result_cannot_be_signed(env,monkeypatch):
    m=api();svc=ZipIngestionService(env.workspace);real=svc.ingest_with_consumer
    def forged(*args,**kw):
        actual=real(*args,**kw)
        return replace(actual,consumer_result=replace(actual.consumer_result))
    monkeypatch.setattr(svc,"ingest_with_consumer",forged)
    with pytest.raises(m.NoticeIngestionError,match="callback_mismatch"):
        completed(env,service=svc)


@pytest.mark.parametrize("extra", [0,1])
def test_w08_effective_service_upload_limit_exact_and_plus_one(env,extra):
    from app.security.limits import ZipSafetyLimits
    p,run=archive(env,{"payload.bin":""},index=77)
    overhead=p.stat().st_size;limit=8*1024*1024
    p,run=archive(env,{"payload.bin":b"x"*(limit-overhead+extra)},index=78)
    assert p.stat().st_size==limit+extra
    svc=ZipIngestionService(env.workspace,limits=ZipSafetyLimits(upload_max_bytes=limit))
    m=api();lc=lifecycle(env)
    def call():return m.complete_zip_ingestion(svc,archive_path=p,upload_root=env.uploads,
        scan_id=run.id,expected_input_digest=run.provenance.input_digest.value,
        dependency_consumer=lambda s:object(),notice_consumer=lc.collect,read_limits=READ_LIMITS)
    if extra:
        with pytest.raises(m.NoticeIngestionError):call()
    else:assert m.validate_completed_ingestion(call()).inventory.entries[0].size_bytes==limit-overhead


@pytest.mark.parametrize("field", ["name", "version", "config_digest"])
def test_factory_producer_mismatch_is_rejected_not_just_cross_observation_equality(env,monkeypatch,field):
    import app.p1.notice_source_lifecycle as m
    real=m.collect_notice_source_package
    def wrong(*a,**kw):
        original=real(*a,**kw);data=original.model_dump(mode="json")
        for observation in data["observations"]:
            observation["collector"][field]="0"*64 if field=="config_digest" else "other-valid-identity"
        return NoticeSourceCollection.model_validate(data)
    monkeypatch.setattr(m,"collect_notice_source_package",wrong)
    proof,_,_,_=completed(env)
    assert proof.result.consumer_result.collection is None
    assert proof.result.consumer_result.dependencies.lanes


@pytest.mark.parametrize("count", [1024,1025])
def test_w05_real_inventory_capacity_exact_count_with_shared_budget(env,count):
    files={**{f"p{i:04}/NOTICE":"n" for i in range(count)},**{f"large{i}":b"x"*(4*1024*1024) for i in range(4)}}
    def dependency(session):
        for i in range(4):session.read_bytes(f"large{i}")
        return object()
    proof,_,_,_=completed(env,files=files,dependency=dependency)
    notice=proof.result.consumer_result.notice
    assert len(notice.selection.candidates)==1024 and notice.selection.omitted_count==count-1024
    if count==1024:
        assert notice.selection.truncated is False and len(notice.collection.observations)==1024
        assert notice.collection.coverage.gap_codes==["read_budget_exhausted"]
    else:assert notice.selection.truncated is True and notice.collection is None
