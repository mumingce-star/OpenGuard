"""A2: real CZ DTO/validator and A1 stores; all scan inputs are TEST_ONLY."""
import copy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import importlib
import io
import json
import sqlite3
from types import SimpleNamespace
from uuid import UUID
import zipfile

import pytest
from app.assessment.engine import facts_digest
from app.assessment.store import AssessmentStore, AssessmentStoreError
from app.ingestion import ZipIngestionService
from app.notice_source import (
    NoticeSourceCandidate, collect_notice_source_package,
    bind_notice_source_collection, validate_notice_source_package,
)
from app.notice_source.models import NoticeSourceCollection, Producer, canonical_json
from app.p1.notice_source_store import (
    NoticeSourceStore, NoticeSourceStoreError, NoticeSourceBindingService,
    BoundNoticeSourceReader,
)
from app.persistence import SQLiteScanRunRegistry, ScanRegistryError
from test_p1_diff_api import assessment as make_assessment, snapshot
from test_p1_history_api import seed


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def env(tmp_path):
    tmp_path.chmod(0o700)
    e = SimpleNamespace(path=tmp_path)
    e.registry = SQLiteScanRunRegistry(tmp_path / "scans.db")
    e.store = AssessmentStore(tmp_path / "assessment.db", min_free_bytes=0)
    e.store.initialize()
    # Actual local ZIP -> real controlled session -> real CZ collector; no pipeline wiring.
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("NOTICE", b"TEST_ONLY locally authored notice.\n")
        z.writestr("other/NOTICE", b"TEST_ONLY second notice.\n")
    raw = archive.getvalue()
    workspace = tmp_path / "ingestion"
    workspace.mkdir(mode=0o700)
    ingestion = ZipIngestionService(workspace)
    try:
        result = ingestion.ingest_with_consumer(io.BytesIO(raw), lambda session:
            collect_notice_source_package(session,
                observed_at=datetime(2026, 9, 27, tzinfo=timezone.utc),
                collector=Producer(type="collector", name="openguard.notice-source",
                                   version="1", config_digest="4"*64),
                candidates=(NoticeSourceCandidate("one", "NOTICE"),
                            NoticeSourceCandidate("two", "other/NOTICE"))))
    finally:
        ingestion.close()
    e.collection = result.consumer_result
    def provenance(data):
        data["provenance"]["input_digest"]["value"] = sha(raw)
        data["provenance"]["inventory_digest"]["value"] = result.inventory.root_digest
    e.run = snapshot(e, 9201, mutate=provenance, source="fixture.zip", source_type="zip")
    e.assessment = make_assessment(e, e.run)
    e.source = NoticeSourceStore(tmp_path / "notice_source.db", min_free_bytes=0)
    e.source.initialize()
    e.service = NoticeSourceBindingService(e.source, e.registry, e.store)
    e.reader = BoundNoticeSourceReader(e.source)
    e.kw = dict(scan_id=e.run.id, expected_registry_revision=3,
                assessment_id=e.assessment.id, expected_assessment_version=1)
    e.api = importlib.import_module("app.p1.notice_source_adapter")
    e.adapter = e.api.NoticeSourceAdapter(e.registry, e.store)
    try:
        yield e
    finally:
        e.registry.close()


def rows(env):
    result = {}
    for name in ("scans.db", "assessment.db", "notice_source.db"):
        with sqlite3.connect(f"file:{env.path/name}?mode=ro", uri=True) as db:
            tables = [r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            result[name] = {t: db.execute(f'SELECT * FROM "{t}" ORDER BY rowid').fetchall()
                            for t in tables}
    return result


def admit(e, collection=None, **kw):
    return e.adapter.admit(collection if collection is not None else e.collection, **{**e.kw, **kw})


def bound(e):
    value = admit(e)
    assert e.source.stage(value).state == "STAGED"
    assert e.reader.read(e.run.id, facts_digest(e.run), e.assessment.id, 1) is None
    e.service.bind(**e.kw, expected_package_hash=value.package_hash)
    return e.reader.read(e.run.id, facts_digest(e.run), e.assessment.id, 1)


def rejected(e, fn, code):
    before = rows(e)
    with pytest.raises(NoticeSourceStoreError) as caught:
        fn()
    assert caught.value.code == code
    assert rows(e) == before


def rehash(value):
    result = copy.deepcopy(value)
    result["package_hash"] = sha(canonical_json({k: v for k, v in result.items() if k != "package_hash"}))
    return result


def corrupt_binder(e, monkeypatch, mutate, rehashed=True):
    def build(collection, *, binding):
        data = bind_notice_source_collection(collection, binding=binding).model_dump(mode="json")
        mutate(data)
        if rehashed:
            data = rehash(data)
            # Most negative cases are valid CZ output, not merely invalid package hashes.
            validate_notice_source_package(data)
        return SimpleNamespace(model_dump=lambda **_: data)
    monkeypatch.setattr(e.api, "bind_notice_source_collection", build)


def test_a2_01_real_cz_to_a1_round_trip(env, monkeypatch):
    seen = []
    real_validator = env.api.validate_notice_source_package
    def validate(data):
        seen.append(copy.deepcopy(data))
        return real_validator(data)
    monkeypatch.setattr(env.api, "validate_notice_source_package", validate)
    upstream_before = rows(env)
    saved = bound(env)
    package = env.api.decode_bound_notice_source(saved)
    assert len(seen) >= 2
    assert package.model_dump(mode="json") == seen[0] == seen[-1]
    assert sha(saved.canonical_package_bytes) == package.package_hash
    assert "package_hash" not in json.loads(saved.canonical_package_bytes)
    assert package.binding.registry_revision == "3"
    assert package.observations == env.collection.observations
    assert package.observations[0].relation.state == "unresolved"
    assert not {"license_expression_id", "verified", "obligations", "evidence_ids"} & set(
        package.model_dump(mode="json"))
    after = rows(env)
    assert after["scans.db"] == upstream_before["scans.db"]
    assert after["assessment.db"] == upstream_before["assessment.db"]
    stable = rows(env)
    assert env.api.decode_bound_notice_source(env.reader.read(
        env.run.id, facts_digest(env.run), env.assessment.id, 1)) == package
    assert rows(env) == stable


def test_a2_02_completed(env):
    value = admit(env)
    assert (value.coverage_status, value.omissions, value.gap_codes) == ("completed", [], [])


@pytest.mark.parametrize("coverage", [
    dict(state="partial", omissions=["z.txt", "a.txt"], gap_codes=["read_failed", "prior_read_failed"]),
    dict(state="partial", omissions=["missing.txt"], gap_codes=[]),
    dict(state="partial", omissions=[], gap_codes=["read_failed"]),
])
def test_a2_03_partial_preserved(env, coverage):
    data = env.collection.model_dump(mode="json")
    data["coverage"] = coverage
    env.collection = NoticeSourceCollection.model_validate(data)
    saved = bound(env)
    assert env.api.decode_bound_notice_source(saved).coverage.model_dump() == coverage
    assert list(saved.omissions) == coverage["omissions"]
    assert list(saved.gap_codes) == coverage["gap_codes"]


@pytest.mark.parametrize("case", ["hash", "preimage"])
def test_a2_04_05_tamper(env, monkeypatch, case):
    def change(data):
        if case == "hash":
            data["package_hash"] = "0"*64
        else:
            data["observed_at"] = "2026-09-26T00:00:00Z"
    corrupt_binder(env, monkeypatch, change, rehashed=False)
    rejected(env, lambda: admit(env), "invalid_argument")


@pytest.mark.parametrize("field,value", [
    ("scan_id", "scn_"+str(UUID(int=9999))),
    ("registry_revision", "4"),
    ("registry_revision", "01"), ("registry_revision", "r1"),
    ("registry_revision", "latest"), ("registry_revision", "3 "),
    ("input_digest", "1"*64), ("inventory_digest", "2"*64),
    ("facts_hash", "3"*64),
])
def test_a2_06_10_12_rehashed_binding_mismatch(env, monkeypatch, field, value):
    corrupt_binder(env, monkeypatch, lambda p: p["binding"].update({field: value}))
    rejected(env, lambda: admit(env), "binding_mismatch")


def test_a2_11_missing_terminal_inventory(env):
    env.run = snapshot(env, 9202, mutate=lambda p: p["provenance"].update(inventory_digest=None))
    env.assessment = make_assessment(env, env.run)
    rejected(env, lambda: admit(env, scan_id=env.run.id, assessment_id=env.assessment.id), "binding_mismatch")


@pytest.mark.parametrize("kw", [
    {"assessment_id": "asm_"+str(UUID(int=9999))},
    {"expected_assessment_version": 2}, {"expected_registry_revision": 4},
])
def test_a2_13_14_explicit_selection_only(env, kw):
    rejected(env, lambda: admit(env, **kw), "binding_mismatch")


@pytest.mark.parametrize("field,value", [
    ("facts_hash", "1"*64), ("id", "asm_"+str(UUID(int=9999))),
    ("scan_id", "scn_"+str(UUID(int=9999))), ("formal", False), ("version", 2),
])
def test_a2_15_independent_assessment_check(env, monkeypatch, field, value):
    # Fault injection at the authoritative store seam, never into actual persisted facts.
    monkeypatch.setattr(env.store, "get", lambda *_: env.assessment.model_copy(update={field: value}))
    rejected(env, lambda: admit(env), "binding_mismatch")


@pytest.mark.parametrize("state", ["queued", "running", "failed", "cancelled"])
def test_a2_16_nonterminal(env, state):
    run = seed(env, 9203, state)
    rejected(env, lambda: admit(env, scan_id=run.id), "not_ready")


@pytest.mark.parametrize("field,value", [
    ("name", "another.collector"), ("version", "2"), ("config_digest", "5"*64),
])
def test_a2_17_mixed_collectors(env, field, value):
    data = env.collection.model_dump(mode="json")
    data["observations"][1]["collector"][field] = value
    rejected(env, lambda: admit(env, NoticeSourceCollection.model_validate(data)), "invalid_argument")


def test_a2_17_zero_observations_and_illegal_type(env):
    for observations in ([], [env.collection.observations[0].model_copy(update={
        "collector": env.collection.observations[0].collector.model_copy(update={"type": "other"})})]):
        rejected(env, lambda: admit(env, env.collection.model_copy(update={"observations": observations})),
                 "invalid_argument")


def test_a2_18_oversize(env):
    data = env.collection.model_dump(mode="json")
    item = data["observations"][0]
    text = "T"*65536
    item["content"].update(text=text, byte_range=[0,len(text)],
                          retained_bytes_sha256=sha(text.encode()), whole_bytes_sha256=sha(text.encode()))
    data["observations"] = [{**copy.deepcopy(item), "observation_key": str(i)} for i in range(129)]
    collection = NoticeSourceCollection.model_validate(data)  # Legal items, oversized terminal package.
    rejected(env, lambda: admit(env, collection), "invalid_argument")


def test_a2_19_replay_and_conflict(env):
    saved = bound(env)
    stable = rows(env)
    assert env.source.stage(admit(env)).state == "STAGED"
    assert env.service.bind(**env.kw, expected_package_hash=saved.package_hash) == saved
    assert rows(env) == stable
    changed = env.collection.model_copy(update={"observed_at": "2026-09-26T00:00:00Z"})
    rejected(env, lambda: env.source.stage(admit(env, changed)), "conflict")


def test_a2_20_restart_and_a2_21_wrong_reader_query(env):
    saved = bound(env)
    reopened = NoticeSourceStore(env.source.path, min_free_bytes=0)
    reader = BoundNoticeSourceReader(reopened)
    stable = rows(env)
    assert reader.read(env.run.id, "0"*64, env.assessment.id, 1) is None
    assert reader.read(env.run.id, facts_digest(env.run), env.assessment.id, 2) is None
    reread = reader.read(env.run.id, facts_digest(env.run), env.assessment.id, 1)
    assert reread == saved
    assert env.api.decode_bound_notice_source(reread).package_hash == saved.package_hash
    assert rows(env) == stable


def test_a2_22_stricter_a1_limits_reject_without_reserving_identity(env):
    data = env.collection.model_dump(mode="json")
    data["coverage"] = dict(state="partial", omissions=["x"*513], gap_codes=[])
    collection = NoticeSourceCollection.model_validate(data)  # CZ accepts; A1 must not normalize it.
    rejected(env, lambda: env.source.stage(admit(env, collection)), "invalid_argument")
    assert bound(env).state == "BOUND"  # Same lawful identity remains available.


@pytest.mark.parametrize("field,value", [
    ("state", "STAGED"), ("registry_revision", 4), ("facts_hash", "0"*64),
    ("scan_id", "other"), ("input_digest", "0"*64), ("inventory_digest", "0"*64),
    ("package_hash", "0"*64), ("producer", "other"), ("coverage_status", "partial"),
])
def test_read_side_rejects_mismatched_bound_metadata(env, field, value):
    saved = bound(env)
    rejected(env, lambda: env.api.decode_bound_notice_source(replace(saved, **{field:value})),
             "binding_mismatch" if field != "package_hash" else "invalid_argument")


def test_read_side_rejects_changed_noncanonical_and_duplicate_bytes(env):
    saved = bound(env)
    data = json.loads(saved.canonical_package_bytes)
    for raw in (saved.canonical_package_bytes+b" ", b'{"schema_version":"bad",'+saved.canonical_package_bytes[1:]):
        # Even a caller-rehashed noncanonical preimage is not the A1 canonical representation.
        rejected(env, lambda: env.api.decode_bound_notice_source(
            replace(saved, canonical_package_bytes=raw, package_hash=sha(raw))), "invalid_argument")
    data["observed_at"] = "2026-09-26T00:00:00Z"
    rejected(env, lambda: env.api.decode_bound_notice_source(
        replace(saved, canonical_package_bytes=canonical_json(data))), "invalid_argument")


def test_terminal_partial_and_explicit_old_assessment_do_not_drift(env):
    env.run = snapshot(env, 9204, status="partial")
    env.assessment = make_assessment(env, env.run)
    newer = make_assessment(env, env.run, version=2)
    assert newer.id != env.assessment.id
    env.kw.update(scan_id=env.run.id, assessment_id=env.assessment.id)
    saved = bound(env)
    assert (saved.assessment_id, saved.assessment_version) == (env.assessment.id, 1)
    assert env.api.decode_bound_notice_source(saved).binding.facts_hash == facts_digest(env.run)


def test_binding_rechecks_registry_after_admission(env, monkeypatch):
    value = admit(env)
    env.source.stage(value)
    stored = env.registry.get(env.run.id)
    with monkeypatch.context() as patch:
        patch.setattr(env.registry, "get", lambda _: replace(stored, revision=4))
        rejected(env, lambda: env.service.bind(**env.kw, expected_package_hash=value.package_hash), "binding_mismatch")
    # The rejected bind created no false BOUND and cannot reserve the binding identity.
    assert env.service.bind(**env.kw, expected_package_hash=value.package_hash).state == "BOUND"


def test_read_side_checks_byte_limit_before_json_decode(env, monkeypatch):
    saved = bound(env)
    raw = b" " * (8*1024*1024+1)
    with monkeypatch.context() as patch:
        def forbidden(*_):
            raise AssertionError("oversize bytes reached JSON parser")
        patch.setattr(env.api.json, "loads", forbidden)
        rejected(env, lambda: env.api.decode_bound_notice_source(
            replace(saved, canonical_package_bytes=raw, package_hash=sha(raw))), "invalid_argument")


def test_read_side_rejects_embedded_hash_field(env):
    saved = bound(env)
    data = json.loads(saved.canonical_package_bytes)
    raw = canonical_json({**data, "package_hash": saved.package_hash})
    rejected(env, lambda: env.api.decode_bound_notice_source(
        replace(saved, canonical_package_bytes=raw, package_hash=sha(raw))), "invalid_argument")


def test_missing_registry_entry(env):
    rejected(env, lambda: admit(env, scan_id="scn_"+str(UUID(int=99999))), "not_found")


def test_malformed_registry_key(env):
    rejected(env, lambda: admit(env, scan_id="not-a-scan-id"), "invalid_argument")


def test_adapter_recomputes_hash_independently_of_validator(env, monkeypatch):
    original = env.api.validate_notice_source_package
    monkeypatch.setattr(env.api, "validate_notice_source_package",
                        lambda data: original(data).model_copy(update={"package_hash": "0"*64}))
    rejected(env, lambda: admit(env), "invalid_argument")


@pytest.mark.parametrize("kw", [{"expected_registry_revision":True}, {"expected_registry_revision":"3"},
                                 {"expected_assessment_version":True}, {"expected_assessment_version":0}])
def test_strict_integer_selection(env, kw):
    rejected(env, lambda: admit(env, **kw), "invalid_argument")


@pytest.mark.parametrize("which", ["registry", "assessment"])
def test_storage_failure_is_fail_closed(env, monkeypatch, which):
    def fail(*_):
        raise (ScanRegistryError("registry_storage_unavailable") if which == "registry"
               else AssessmentStoreError("storage_unavailable"))
    monkeypatch.setattr(env.registry if which == "registry" else env.store, "get", fail)
    rejected(env, lambda: admit(env), "storage_unavailable")


# A2 R1: explicit TEST_ONLY recovery; never last-write-wins or private SQL writes.
def r1_packages(env):
    first = admit(env)
    data = env.collection.model_dump(mode="json")
    # A second lawful collection from the same inventory; no invented content.
    data["observations"] = data["observations"][:1]
    second = admit(env, NoticeSourceCollection.model_validate(data))
    assert first.package_hash != second.package_hash
    for value in (first, second):
        validate_notice_source_package({
            **json.loads(value.canonical_package_bytes), "package_hash": value.package_hash})
    return first, second


def r1_bind(env, value, **changes):
    return env.service.bind(**{**env.kw, "expected_package_hash": value.package_hash, **changes})


def r1_replace(env, old, new):
    return env.source.replace_unbound_stage(
        new, scan_id=env.run.id, expected_current_package_hash=old.package_hash)


def test_r1_01_failed_bind_explicit_replacement_recovers(env):
    first, second = r1_packages(env)
    env.source.stage(first)
    constrained = NoticeSourceStore(env.source.path, min_free_bytes=10**30)
    service = NoticeSourceBindingService(constrained, env.registry, env.store)
    rejected(env, lambda: service.bind(**env.kw, expected_package_hash=first.package_hash),
             "storage_capacity_exceeded")
    assert env.reader.read(env.run.id, facts_digest(env.run), env.assessment.id, 1) is None
    rejected(env, lambda: env.source.stage(second), "conflict")  # Never implicit replacement.
    staged = r1_replace(env, first, second)
    assert staged.package_hash == second.package_hash
    assert env.reader.read(env.run.id, facts_digest(env.run), env.assessment.id, 1) is None
    assert r1_bind(env, second).package_hash == second.package_hash


def test_r1_02_any_bound_freezes_stage_even_for_another_assessment(env):
    first, second = r1_packages(env)
    env.source.stage(first)
    saved = r1_bind(env, first)
    newer = make_assessment(env, env.run, version=2)
    rejected(env, lambda: r1_replace(env, first, second), "conflict")
    # Even replacement with identical bytes is not an escape from BOUND freeze.
    rejected(env, lambda: r1_replace(env, first, first), "conflict")
    assert env.reader.read(env.run.id, facts_digest(env.run), env.assessment.id, 1) == saved
    fixed = r1_bind(env, first, assessment_id=newer.id, expected_assessment_version=2)
    assert fixed.package_hash == saved.package_hash
    assert env.reader.read(env.run.id, facts_digest(env.run), env.assessment.id, 1) == saved


def test_r1_03_wrong_replacement_cas_keeps_original(env):
    first, second = r1_packages(env)
    env.source.stage(first)
    rejected(env, lambda: env.source.replace_unbound_stage(
        second, scan_id=env.run.id, expected_current_package_hash="0"*64), "conflict")
    assert env.source.stage(first).package_hash == first.package_hash


def test_r1_04_interleaved_old_caller_cannot_bind_replacement(env):
    first, second = r1_packages(env)
    env.source.stage(first)  # Caller A holds first.package_hash.
    r1_replace(env, first, second)  # Caller B commits.
    rejected(env, lambda: r1_bind(env, first), "binding_mismatch")
    assert env.reader.read(env.run.id, facts_digest(env.run), env.assessment.id, 1) is None


def test_r1_05_new_caller_binds_exact_replacement(env):
    first, second = r1_packages(env)
    env.source.stage(first)
    r1_replace(env, first, second)
    saved = r1_bind(env, second)
    assert saved.package_hash == second.package_hash
    assert env.api.decode_bound_notice_source(saved).package_hash == second.package_hash


def test_r1_06_exact_retry_and_stale_replacement_cas(env):
    first, second = r1_packages(env)
    env.source.stage(first)
    assert env.source.stage(first).package_hash == first.package_hash
    r1_replace(env, first, second)
    rejected(env, lambda: r1_replace(env, first, second), "conflict")
    before = rows(env)
    assert env.source.stage(second).package_hash == second.package_hash
    assert rows(env) == before
    saved = r1_bind(env, second)
    before = rows(env)
    assert env.source.stage(second).package_hash == second.package_hash
    assert r1_bind(env, second) == saved
    assert rows(env) == before


def test_r1_10_bound_replacement_refused_and_restart_preserves_hash(env):
    first, second = r1_packages(env)
    env.source.stage(first)
    saved = r1_bind(env, first)
    rejected(env, lambda: r1_replace(env, first, second), "conflict")
    reopened = BoundNoticeSourceReader(NoticeSourceStore(env.source.path, min_free_bytes=0))
    reread = reopened.read(env.run.id, facts_digest(env.run), env.assessment.id, 1)
    assert reread == saved
    assert env.api.decode_bound_notice_source(reread).package_hash == first.package_hash


def test_r1_11_wrong_bind_package_hash_has_zero_bound_mutation(env):
    first, _ = r1_packages(env)
    env.source.stage(first)
    rejected(env, lambda: r1_bind(env, first, expected_package_hash="0"*64), "binding_mismatch")
    assert env.reader.read(env.run.id, facts_digest(env.run), env.assessment.id, 1) is None


def test_r1_12_old_hash_fails_then_new_hash_succeeds(env):
    first, second = r1_packages(env)
    env.source.stage(first)
    r1_replace(env, first, second)
    rejected(env, lambda: r1_bind(env, first), "binding_mismatch")
    saved = r1_bind(env, second)
    assert saved.package_hash == second.package_hash
    # A stale caller cannot replay B's BOUND under A's package identity either.
    rejected(env, lambda: r1_bind(env, first), "binding_mismatch")


def test_r1_13_replacement_cz_round_trip_is_store_only(env, monkeypatch):
    first, second = r1_packages(env)
    env.source.stage(first)
    r1_replace(env, first, second)
    saved = r1_bind(env, second)
    before = rows(env)
    def forbidden(*args, **kwargs):
        raise AssertionError("TEST_ONLY: read unexpectedly accessed upstream")
    monkeypatch.setattr(env.registry, "get", forbidden)
    monkeypatch.setattr(env.store, "get", forbidden)
    monkeypatch.setattr(env.api, "bind_notice_source_collection", forbidden)
    reader = BoundNoticeSourceReader(NoticeSourceStore(env.source.path, min_free_bytes=0))
    reread = reader.read(env.run.id, facts_digest(env.run), env.assessment.id, 1)
    package = env.api.decode_bound_notice_source(reread)
    assert reread == saved and package.package_hash == second.package_hash
    assert validate_notice_source_package(package.model_dump(mode="json")) == package
    assert rows(env) == before


@pytest.mark.parametrize("bad_hash", [None, True, "", "A"*64, "f"*63, "f"*64+" "])
def test_r1_bind_requires_canonical_package_hash(env, bad_hash):
    first, _ = r1_packages(env)
    env.source.stage(first)
    rejected(env, lambda: r1_bind(env, first, expected_package_hash=bad_hash), "invalid_argument")


def test_r1_missing_bind_package_hash_cannot_publish(env):
    env.source.stage(admit(env))
    before = rows(env)
    with pytest.raises(TypeError):
        env.service.bind(**env.kw)  # Intentionally omitted; no permissive default allowed.
    assert rows(env) == before
