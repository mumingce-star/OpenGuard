"""Independent A06 integrity, replay security, atomicity and privacy checks.

Only disposable SQLite fixtures and TestClient are used; no live ports or models.
The expected hashes and SQLite row counts are computed outside production helpers.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from threading import Barrier

import pytest
from pydantic import ValidationError
from jsonschema import FormatChecker

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))
from test_p1_report_v2_service import report_env, create_report  # noqa: E402,F401
from test_p1_report_v2_api import http_env, create, error  # noqa: E402,F401
from test_p1_contract_schema import validator  # noqa: E402
from app.p1.models import P1ReportV2Snapshot, P1TaskRef  # noqa: E402
from app.p1.report_v2_store import ReportV2Store, ReportV2StoreError  # noqa: E402


def strict_report_validator():
    # The fixed offline image lacks jsonschema's optional RFC3339 dependency.
    # Register on this test-local instance only: absent format plugins must not
    # turn the Frozen Schema date-time assertion into a silent no-op.
    checker = FormatChecker()

    @checker.checks("date-time")
    def utc_datetime(value):
        if not isinstance(value, str):
            return True  # Schema's type constraint handles non-string input.
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z", value) is None:
            return False
        try:
            datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError:
            return False
        return True

    return validator("ReportV2Snapshot").evolve(format_checker=checker)


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def state(store):
    """Exact DB and journal bytes: failed reads/replay must not repair data."""
    return {p.name: sha(p.read_bytes()) for p in store.path.parent.glob(store.path.name + "*")
            if p.is_file()}


def counts(store):
    with sqlite3.connect(store.path) as db:
        return tuple(db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                     for table in ("report_snapshots", "report_artifacts", "report_requests"))


def saved_bundle(env):
    report = create_report(env, key="original-independent")
    payloads = {fmt: env.service.artifact(env.run.id, env.assessment.id, report.snapshot_id, fmt)
                for fmt in ("json", "html")}
    return report.model_dump(mode="json"), payloads


def fresh_store(env, name):
    store = ReportV2Store(env.path / name / "report_v2.db", min_free_bytes=0)
    store.initialize()
    return store


def store_call(store, snapshot, artifacts, key="independent", fingerprint="request-v1"):
    return store.create(snapshot["binding"]["scan_ref"]["scan_id"],
                        snapshot["binding"]["assessment_ref"]["assessment_id"],
                        key, fingerprint, snapshot, artifacts)


def test_artifact_insert_fault_after_snapshot_insert_rolls_back_all_tables(report_env, monkeypatch):
    env = report_env
    snapshot, artifacts = saved_bundle(env)
    target = fresh_store(env, "mid-transaction")
    # This trigger fires after the snapshot INSERT, unlike argument validation faults.
    with sqlite3.connect(target.path) as db:
        db.execute("""CREATE TRIGGER fail_artifact BEFORE INSERT ON report_artifacts
                      BEGIN SELECT observe_then_fail(); END""")
    connect = target._connect
    observed = []

    def instrumented(*, readonly=False):
        db = connect(readonly=readonly)
        if not readonly:
            def fail():
                observed.append(db.execute("SELECT count(*) FROM report_snapshots").fetchone()[0])
                raise sqlite3.OperationalError("synthetic artifact write failure")
            db.create_function("observe_then_fail", 0, fail)
        return db

    monkeypatch.setattr(target, "_connect", instrumented)
    with pytest.raises(ReportV2StoreError) as raised:
        store_call(target, snapshot, artifacts)
    assert raised.value.code == "storage_unavailable"
    assert observed == [1], "Fault must occur after the first successful INSERT"
    assert counts(target) == (0, 0, 0)
    assert target.request_fingerprint(env.run.id, env.assessment.id, "independent") is None
    assert counts(env.report_store) == (1, 2, 1)


def test_four_independent_connections_same_key_produce_exactly_one_bundle(report_env):
    env = report_env
    snapshot, artifacts = saved_bundle(env)
    target = fresh_store(env, "concurrent")
    barrier = Barrier(4)

    def worker(_):
        connection_owner = ReportV2Store(target.path, min_free_bytes=0)
        barrier.wait(timeout=10)
        return store_call(connection_owner, deepcopy(snapshot), dict(artifacts))

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(worker, range(4)))
    assert all(result == snapshot for result in results)
    assert counts(target) == (1, 2, 1)
    for fmt, expected in artifacts.items():
        assert target.get_artifact(env.run.id, env.assessment.id, snapshot["snapshot_id"], fmt) == expected


def test_queried_a_row_cannot_return_valid_b_payload_even_with_correct_payload_hash(report_env):
    env = report_env
    first = create_report(env, key="report-a")
    second = create_report(env, key="report-b")
    with sqlite3.connect(env.report_store.path) as db:
        payload, payload_hash = db.execute(
            "SELECT payload,payload_hash FROM report_snapshots WHERE snapshot_id=?",
            (second.snapshot_id,)).fetchone()
        db.execute("UPDATE report_snapshots SET payload=?,payload_hash=? WHERE snapshot_id=?",
                   (payload, payload_hash, first.snapshot_id))
    before = state(env.report_store)
    for action in (
        lambda: env.report_store.get(env.run.id, env.assessment.id, first.snapshot_id),
        lambda: env.report_store.get_artifact(env.run.id, env.assessment.id, first.snapshot_id, "json"),
    ):
        with pytest.raises(ReportV2StoreError) as raised:
            action()
        assert raised.value.code == "storage_unavailable"
    assert state(env.report_store) == before


@pytest.mark.parametrize("fmt", ["html", "json"])
def test_artifact_self_hash_is_insufficient_when_snapshot_metadata_disagrees(report_env, fmt):
    env = report_env
    snapshot, artifacts = saved_bundle(env)
    fingerprint = env.report_store.request_fingerprint(env.run.id, env.assessment.id,
                                                        "original-independent")
    # Whitespace keeps JSON parseable, but changes its stored bytes and digest.
    altered = artifacts[fmt] + b"\n "
    with sqlite3.connect(env.report_store.path) as db:
        db.execute("""UPDATE report_artifacts SET payload=?,payload_hash=?,size_bytes=?
                      WHERE snapshot_id=? AND format=?""",
                   (altered, sha(altered), len(altered), snapshot["snapshot_id"], fmt))
    before = state(env.report_store)
    actions = (
        lambda: env.report_store.get(env.run.id, env.assessment.id, snapshot["snapshot_id"]),
        lambda: env.report_store.get_artifact(env.run.id, env.assessment.id, snapshot["snapshot_id"], fmt),
        lambda: store_call(env.report_store, snapshot, artifacts, "original-independent", fingerprint),
    )
    for action in actions:
        with pytest.raises(ReportV2StoreError) as raised:
            action()
        assert raised.value.code == "storage_unavailable"
    assert state(env.report_store) == before


@pytest.mark.parametrize("path,value", [
    (("created_at",), "Z"),
    (("created_at",), "2026-02-30T12:00:00Z"),
    (("created_at",), "2026-09-14T12:00:00+00:00"),
    (("provenance", "generated_at"), "Z"),
    (("binding", "assessment_ref", "version"), True),
    (("binding", "scan_ref", "registry_revision"), True),
    (("artifacts", 0, "size_bytes"), True),
    (("provenance", "assessment_refs", 0, "version"), True),
])
def test_a06_boundary_rejects_invalid_utc_and_boolean_integers(report_env, path, value):
    env = report_env
    snapshot, artifacts = saved_bundle(env)
    cursor = snapshot
    for token in path[:-1]:
        cursor = cursor[token]
    cursor[path[-1]] = value
    assert list(strict_report_validator().iter_errors(snapshot)), "Frozen Schema must also reject this input"
    with pytest.raises(ValidationError):
        P1ReportV2Snapshot.model_validate(snapshot)
    target = fresh_store(env, "strict-boundary")
    before = state(target)
    with pytest.raises(ReportV2StoreError) as raised:
        store_call(target, snapshot, artifacts)
    assert raised.value.code == "invalid_argument"
    assert counts(target) == (0, 0, 0)
    assert state(target) == before


@pytest.mark.parametrize("scenario,status,code", [
    ("cross-site", 403, "origin_rejected"),
    ("content-type", 400, "invalid_argument"),
    ("invalid-reference", 400, "invalid_argument"),
    ("oversized-stream", 413, "request_too_large"),
])
def test_existing_key_never_bypasses_http_security_validation(http_env, scenario, status, code):
    http = http_env
    initial = create(http, key="existing-secure")
    assert initial.status_code == 200
    before = state(http.env.report_store)
    body = {"idempotency_key": "existing-secure"}
    if scenario == "cross-site":
        response = http.client.post(http.base, json=body, headers={"sec-fetch-site": "cross-site"})
    elif scenario == "content-type":
        response = http.client.post(http.base, content=canonical(body), headers={"content-type": "text/plain"})
    elif scenario == "invalid-reference":
        response = http.client.post(http.base, json={**body, "task_refs": None})
    else:
        response = http.client.post(http.base, content=iter([canonical(body), b" " * 16384]),
                                    headers={"content-type": "application/json"})
    error(response, status, code)
    assert state(http.env.report_store) == before
    assert counts(http.env.report_store) == (1, 2, 1)


def test_audit_report_keeps_synthetic_private_text_with_escaping_and_matching_hash(report_env):
    env = report_env
    note = '<script>alert("SYNTHETIC-NOT-A-REAL-SECRET")</script> /Users/synthetic/private'
    updated = env.task_store.patch(env.run.id, env.assessment.id, env.task.task_id,
                                   env.task.version, {"note": note})
    report = create_report(env, key="full-audit-privacy",
                           task_refs=[P1TaskRef(task_id=env.task.task_id, version=updated["version"])])
    artifacts = {fmt: env.service.artifact(env.run.id, env.assessment.id, report.snapshot_id, fmt)
                 for fmt in ("json", "html")}
    document = json.loads(artifacts["json"])
    workflow = next(section for section in document["sections"] if section["authority"] == "workflow")
    assert workflow["content"]["tasks"][0]["note"] == note
    html = artifacts["html"].decode()
    assert "折叠不是脱敏" in html
    assert "SYNTHETIC-NOT-A-REAL-SECRET" in html
    assert "/Users/synthetic/private" in html
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    for metadata in report.artifacts:
        assert sha(artifacts[metadata.format]) == metadata.content_hash
        assert len(artifacts[metadata.format]) == metadata.size_bytes
    strict_report_validator().validate(report.model_dump(mode="json"))
