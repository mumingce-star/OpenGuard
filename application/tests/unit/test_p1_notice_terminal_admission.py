"""A4-1 TEST_ONLY inputs; real ZIP/session, no production lifecycle hooks."""
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import importlib
import io
import json
import sqlite3
from types import SimpleNamespace
import zipfile

import pytest
from app.assessment.engine import facts_digest
from app.assessment.store import AssessmentStore
from app.ingestion import ZipIngestionService
from app.notice_source import select_notice_source_candidates, collect_notice_source_package
from app.notice_source.models import NoticeSourceCollection, Producer, canonical_json
from app.p1.notice_source_store import NoticeSourceStore, NoticeSourceStoreError, NoticeSourceBindingService, BoundNoticeSourceReader
from app.persistence import SQLiteScanRunRegistry
from test_p1_diff_api import snapshot, assessment as save_assessment
from test_p1_history_api import seed

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def business_rows(e):
    values = {}
    for name in ("scans.db", "assessment.db", "notice_source.db"):
        path = e.path / name
        if not path.exists():
            values[name] = None
            continue
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
            values[name] = {name: db.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall() for name, in tables}
    return values

class ForbiddenAssessment:
    def get(self, *a, **kw):
        raise AssertionError("terminal entry queried Assessment")
    create = initialize = get

@pytest.fixture
def terminal_env(tmp_path):
    tmp_path.chmod(0o700)
    e = SimpleNamespace(path=tmp_path)
    e.registry = SQLiteScanRunRegistry(tmp_path / "scans.db")
    e.store = AssessmentStore(tmp_path / "assessment.db", min_free_bytes=0)
    e.store.initialize()
    e.source = NoticeSourceStore(tmp_path / "notice_source.db", min_free_bytes=0)
    e.source.initialize()
    e.api = importlib.import_module("app.p1.notice_source_adapter")
    e.store_api = importlib.import_module("app.p1.notice_source_store")
    e.adapter = e.api.NoticeSourceAdapter(e.registry, ForbiddenAssessment())
    e.service = NoticeSourceBindingService(e.source, e.registry, e.store)
    e.bound_reader = BoundNoticeSourceReader(e.source)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as z:
        z.writestr("NOTICE", b"TEST_ONLY owned notice.\n")
        z.writestr("nested/LICENSE.md", "TEST_ONLY local license observation.\n")
    e.raw = buffer.getvalue()
    e.workspace = tmp_path / "ingestion"
    e.workspace.mkdir(mode=0o700)
    def capture(observed_at="2026-10-01T00:00:00Z"):
        svc = ZipIngestionService(e.workspace)
        try:
            return svc.ingest_with_consumer(io.BytesIO(e.raw), lambda session:
                collect_notice_source_package(session,
                    candidates=select_notice_source_candidates(session.inventory).candidates,
                    observed_at=datetime.fromisoformat(observed_at.replace("Z", "+00:00")),
                    collector=Producer(type="collector", name="TEST_ONLY_real_session", version="1")))
        finally:
            svc.close()
    e.capture = capture
    e.ingestion = capture()
    e.collection = e.ingestion.consumer_result
    def provenance(data):
        data["provenance"]["input_digest"]["value"] = sha(e.raw)
        data["provenance"]["inventory_digest"]["value"] = e.ingestion.inventory.root_digest
    e.provenance = provenance
    e.run = snapshot(e, 9401, mutate=provenance, source="TEST_ONLY.zip", source_type="zip")
    e.kw = dict(scan_id=e.run.id, expected_registry_revision=3,
                ingestion_result=e.ingestion, source_input=e.raw)
    yield e
    e.registry.close()

def terminal(e, **kwargs):
    return e.adapter.admit_terminal(e.collection, **{**e.kw, **kwargs})

def reject(e, fn, code):
    before = business_rows(e)
    with pytest.raises(NoticeSourceStoreError) as caught:
        fn()
    assert caught.value.code == code
    assert business_rows(e) == before

@pytest.mark.parametrize("status", ["completed", "partial"])
def test_terminal_without_assessment_stages_no_assessment_write(terminal_env, status):
    e = terminal_env
    if status == "partial":
        e.run = snapshot(e, 9402, mutate=e.provenance, status=status, source="TEST_ONLY.zip", source_type="zip")
        e.kw["scan_id"] = e.run.id
    before = business_rows(e)
    value = terminal(e)
    assert business_rows(e) == before
    assert e.source.stage(value).state == "STAGED"
    after = business_rows(e)
    assert after["assessment.db"] == before["assessment.db"]
    assert after["scans.db"] == before["scans.db"]
    package = json.loads(value.canonical_package_bytes)
    assert package["binding"]["facts_hash"] == facts_digest(e.run)
    assert package["binding"]["registry_revision"] == "3"
    assert sha(value.canonical_package_bytes) == value.package_hash
    assert "package_hash" not in package

@pytest.mark.parametrize("status", ["queued", "running", "failed", "cancelled"])
def test_terminal_rejects_nonterminal_without_writes(terminal_env, status):
    e = terminal_env
    run = seed(e, 9410, status, source="TEST_ONLY.zip", source_type="zip")
    revision = e.registry.get(run.id).revision
    reject(e, lambda: terminal(e, scan_id=run.id, expected_registry_revision=revision), "not_ready")

@pytest.mark.parametrize("field", ["scan", "scan_format", "revision", "input", "inventory", "collection_affinity", "inventory_self_hash"])
def test_terminal_rejects_wrong_origin_or_registry(terminal_env, field):
    e = terminal_env
    kw = {}
    code = "binding_mismatch"
    if field == "scan":
        kw["scan_id"] = "scn_00000000-0000-0000-0000-000000009999"
        code = "not_found"
    elif field == "scan_format":
        kw["scan_id"] = "scn_missing"
        code = "invalid_argument"
    elif field == "revision":
        kw["expected_registry_revision"] = 4
    elif field == "input":
        kw["source_input"] = e.raw + b"altered"
    elif field == "inventory":
        kw["ingestion_result"] = replace(e.ingestion, inventory=replace(e.ingestion.inventory, root_digest="b"*64))
    elif field == "collection_affinity":
        kw["ingestion_result"] = replace(e.ingestion, consumer_result=e.collection.model_copy(deep=True))
    else:
        entry = replace(e.ingestion.inventory.entries[0], sha256="b"*64)
        kw["ingestion_result"] = replace(e.ingestion, inventory=replace(e.ingestion.inventory,
            entries=(entry, *e.ingestion.inventory.entries[1:])))
    reject(e, lambda: terminal(e, **kw), code)

@pytest.mark.parametrize("field", ["inventory_digest", "input_digest", "id"])
def test_terminal_independent_registry_identity_check(terminal_env, monkeypatch, field):
    e = terminal_env
    saved = e.registry.get(e.run.id)
    data = saved.run.model_dump(mode="json")
    if field == "inventory_digest":
        data["provenance"][field] = None
    elif field == "input_digest":
        data["provenance"][field]["value"] = "c"*64
    else:
        data["id"] = "scn_" + "00000000-0000-0000-0000-000000000099"
    from app.domain.models import ScanRun
    monkeypatch.setattr(e.registry, "get", lambda _: replace(saved, run=ScanRun.model_validate(data)))
    reject(e, lambda: terminal(e), "binding_mismatch")

@pytest.mark.parametrize("revision", [0, True, "3", None])
def test_terminal_invalid_revision(terminal_env, revision):
    e = terminal_env
    reject(e, lambda: terminal(e, expected_registry_revision=revision), "invalid_argument")

@pytest.mark.parametrize("case", ["typed_invalid", "different_producer", "content_inventory_hash", "unknown_path"])
def test_terminal_revalidates_typed_collection_and_actual_observations(terminal_env, case):
    e = terminal_env
    if case == "typed_invalid":
        changed = e.collection.model_copy(update={"observed_at": "not-a-time"})
        code = "invalid_argument"
    else:
        data = e.collection.model_dump(mode="json")
        if case == "different_producer":
            data["observations"][1]["collector"]["version"] = "2"
            code = "invalid_argument"
        elif case == "content_inventory_hash":
            o = data["observations"][0]["content"]
            o.update(text="changed", byte_range=[0,7], retained_bytes_sha256=sha(b"changed"), whole_bytes_sha256=sha(b"changed"))
            code = "binding_mismatch"
        else:
            data["observations"][0]["locator"] = "unknown/NOTICE"
            code = "binding_mismatch"
        changed = NoticeSourceCollection.model_validate(data)
    e.collection = changed
    e.kw["ingestion_result"] = replace(e.ingestion, consumer_result=changed)
    reject(e, lambda: terminal(e), code)

@pytest.mark.parametrize("coverage", [
    dict(state="partial", omissions=["missing.txt"], gap_codes=[]),
    dict(state="partial", omissions=[], gap_codes=["read_failed"]),
    dict(state="partial", omissions=["missing.txt"], gap_codes=["read_failed"]),
])
def test_terminal_partial_coverage_preserved_exactly(terminal_env, coverage):
    e = terminal_env
    data = e.collection.model_dump(mode="json")
    data["coverage"] = coverage
    e.collection = NoticeSourceCollection.model_validate(data)
    e.kw["ingestion_result"] = replace(e.ingestion, consumer_result=e.collection)
    value = terminal(e)
    assert value.coverage_status == coverage["state"]
    assert value.omissions == coverage["omissions"] and value.gap_codes == coverage["gap_codes"]

@pytest.mark.parametrize("case", ["facts", "input", "inventory", "revision", "hash"])
def test_terminal_cz_package_binding_revalidated(terminal_env, monkeypatch, case):
    e = terminal_env
    original = e.api.bind_notice_source_collection
    def corrupt(collection, *, binding):
        raw = original(collection, binding=binding).model_dump(mode="json")
        if case == "hash":
            raw["package_hash"] = "0"*64
        else:
            raw["binding"][{"facts":"facts_hash","input":"input_digest","inventory":"inventory_digest","revision":"registry_revision"}[case]] = "04" if case == "revision" else "f"*64
            raw["package_hash"] = sha(canonical_json({k:v for k,v in raw.items() if k!="package_hash"}))
        return SimpleNamespace(model_dump=lambda **kw:raw)
    monkeypatch.setattr(e.api, "bind_notice_source_collection", corrupt)
    reject(e, lambda: terminal(e), "invalid_argument" if case == "hash" else "binding_mismatch")

def test_terminal_does_not_accept_caller_digest_instead_of_input(terminal_env):
    e = terminal_env
    reject(e, lambda: terminal(e, source_input=sha(e.raw)), "invalid_argument")

@pytest.mark.parametrize("case", ["missing", "wrong_version", "nonformal", "facts"])
def test_legacy_admit_keeps_explicit_assessment_gate(terminal_env, monkeypatch, case):
    e = terminal_env
    a = save_assessment(e, e.run)
    if case == "missing":
        result = None
    else:
        result = a.model_copy(update={"version":2} if case=="wrong_version" else
            {"formal":False} if case=="nonformal" else {"facts_hash":"f"*64})
    monkeypatch.setattr(e.store, "get", lambda *args:result)
    old = e.api.NoticeSourceAdapter(e.registry, e.store)
    reject(e, lambda: old.admit(e.collection, scan_id=e.run.id, expected_registry_revision=3,
        assessment_id=a.id, expected_assessment_version=1), "binding_mismatch")

def test_real_controlled_zip_terminal_stage_then_explicit_assessment_bound(terminal_env):
    e = terminal_env
    scan_before = e.registry.get(e.run.id)
    assert list(e.workspace.iterdir()) == []
    value = terminal(e)
    staged = e.source.stage(value)
    # This exact provisional source is not BOUND just because terminal admission succeeded.
    a = save_assessment(e, e.run)
    assert e.bound_reader.read(e.run.id, facts_digest(e.run), a.id, a.version) is None
    bound = e.service.bind(scan_id=e.run.id, expected_registry_revision=3,
        assessment_id=a.id, expected_assessment_version=1, expected_package_hash=staged.package_hash)
    reopened = BoundNoticeSourceReader(NoticeSourceStore(e.path/"notice_source.db", min_free_bytes=0))
    assert reopened.read(e.run.id, facts_digest(e.run), a.id, 1) == bound
    assert e.api.decode_bound_notice_source(bound).package_hash == value.package_hash
    assert e.registry.get(e.run.id) == scan_before


def recapture_zip(e, files):
    """TEST_ONLY: get a new successful result through the real ingestion service."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as z:
        for path, text in files:
            z.writestr(path, text)
    e.raw = buffer.getvalue()
    e.ingestion = e.capture()
    e.collection = e.ingestion.consumer_result
    e.run = snapshot(e, 9450, mutate=e.provenance, source="TEST_ONLY.zip", source_type="zip")
    e.kw.update(scan_id=e.run.id, ingestion_result=e.ingestion, source_input=e.raw)


def test_terminal_does_not_publish_completed_after_selector_truncation(terminal_env):
    e = terminal_env
    recapture_zip(e, [(f"p{i:04}/NOTICE", b"TEST_ONLY notice") for i in range(1025)])
    selection = select_notice_source_candidates(e.ingestion.inventory)
    assert selection.truncated and selection.omitted_count == 1
    assert e.collection.coverage.state == "completed"  # Collector alone cannot see selection loss.
    reject(e, lambda: terminal(e), "not_ready")


def test_terminal_actual_zip_oversize_package_rejected_before_stage(terminal_env):
    e = terminal_env
    recapture_zip(e, [(f"p{i:04}/NOTICE", b"T"*65536) for i in range(129)])
    assert e.collection.coverage.state == "completed"
    assert len(e.collection.observations) == 129
    reject(e, lambda: terminal(e), "invalid_argument")
