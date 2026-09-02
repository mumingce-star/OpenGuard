"""Implementation-side A3-0 registry regression tests using only stdlib SQLite."""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.domain.models import ScanRun
from app.persistence import SQLiteScanRunRegistry, ScanRegistryError


ROOT = Path(__file__).resolve().parents[2]
SAMPLE = json.loads((ROOT / "examples" / "sample-scan-result.json").read_text())
POSITIVE_IDS = tuple(f"POS-A3-REG-{value:03d}" for value in range(1, 9))
NEGATIVE_IDS = tuple(f"NEG-A3-REG-{value:03d}" for value in range(1, 17))
BASE_TIME = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _run(index: int = 1, **changes: object) -> ScanRun:
    value = copy.deepcopy(SAMPLE)
    value["id"] = f"scn_123e4567-e89b-12d3-a456-426614174{index:03d}"
    value["project"]["id"] = f"prj_123e4567-e89b-12d3-a456-426614174{index:03d}"
    value["created_at"] = (BASE_TIME + timedelta(seconds=index)).isoformat().replace("+00:00", "Z")
    value.update(status="queued", stage="queued", progress=0, started_at=None, finished_at=None, errors=[], idempotency_key=None)
    value.update(changes)
    return ScanRun.model_validate(value)


def _changed(run: ScanRun, **changes: object) -> ScanRun:
    value = run.model_dump(mode="json")
    value.update(changes)
    return ScanRun.model_validate(value)


def _registry(tmp_path: Path, name: str = "registry.sqlite", **kwargs: object) -> SQLiteScanRunRegistry:
    return SQLiteScanRunRegistry(tmp_path / name, **kwargs)


def _error(callable_: object, code: str) -> None:
    with pytest.raises(ScanRegistryError) as raised:
        callable_()  # type: ignore[operator]
    assert raised.value.code == code
    assert raised.value.args == (code,)
    assert raised.value.__cause__ is None


@pytest.mark.parametrize("case_id", [*POSITIVE_IDS, *NEGATIVE_IDS])
def test_a3_frozen_case_ids_are_discoverable(case_id: str) -> None:
    assert case_id.startswith(("POS-A3-REG-", "NEG-A3-REG-"))


def test_pos_a3_reg_001_002_create_get_canonical_and_idempotency(tmp_path: Path) -> None:
    run = _run(1, idempotency_key="request-1")
    fingerprint = hashlib.sha256(b"request-1").hexdigest()
    with _registry(tmp_path) as registry:
        created = registry.create(run, idempotency_fingerprint=fingerprint)
        assert created.revision == 1 and registry.get(run.id) == created
        duplicate = registry.create(_run(2, idempotency_key="request-1"), idempotency_fingerprint=fingerprint)
        assert duplicate == created
    raw = sqlite3.connect(tmp_path / "registry.sqlite").execute("SELECT run_json FROM scan_runs").fetchone()[0]
    assert raw == json.dumps(run.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def test_pos_a3_reg_003_004_transitions_cas_and_noop(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    queued = registry.create(_run())
    running = _changed(queued.run, status="running", stage="ingestion", progress=1, started_at=queued.run.created_at)
    first = registry.replace(running, expected_revision=1)
    assert first.revision == 2
    assert registry.replace(running, expected_revision=2) == first
    completed = _changed(running, status="completed", stage="completed", progress=100, finished_at=running.created_at + timedelta(seconds=1))
    assert registry.replace(completed, expected_revision=2).revision == 3


def test_pos_a3_reg_005_006_007_008_paging_restart_cas_and_terminal_paths(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    stored = [registry.create(_run(index)) for index in range(1, 4)]
    first = registry.list_runs(limit=1)
    second = registry.list_runs(limit=100, after_scan_id=first.next_after_scan_id)
    assert first.next_after_scan_id == first.items[-1].run.id
    assert {item.run.id for item in (*first.items, *second.items)} == {item.run.id for item in stored}
    winner = _changed(stored[0].run, status="cancelled", stage="queued", progress=0, finished_at=stored[0].run.created_at)
    assert registry.replace(winner, expected_revision=1).revision == 2
    _error(lambda: registry.replace(winner, expected_revision=1), "registry_revision_conflict")
    registry.close()
    reopened = _registry(tmp_path)
    assert reopened.get(winner.id).run.status.value == "cancelled"
    for terminal in ("partial", "failed", "cancelled"):
        base = reopened.create(_run(len(terminal) + 10))
        running = _changed(base.run, status="running", stage="scan", progress=20, started_at=base.run.created_at)
        active = reopened.replace(running, expected_revision=1)
        changes: dict[str, object] = {"status": terminal, "stage": "report", "progress": 50, "finished_at": running.created_at + timedelta(seconds=1)}
        if terminal == "partial":
            changes["errors"] = [{"code": "partial", "stage": "scan", "message": "recoverable scanner result", "recoverable": True}]
        if terminal == "failed":
            changes["errors"] = [{"code": "failed", "stage": "scan", "message": "scanner failure", "recoverable": False}]
        assert reopened.replace(_changed(running, **changes), expected_revision=active.revision).run.status.value == terminal
    reopened.close()
    reopened.close()


def test_neg_a3_reg_001_through_010_arguments_idempotency_and_transitions(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    _error(lambda: registry.get("bad"), "registry_invalid_argument")
    _error(lambda: registry.list_runs(limit=True), "registry_invalid_argument")
    _error(lambda: registry.create(_run(), idempotency_fingerprint="0" * 64), "registry_invalid_argument")
    keyed = _run(2, idempotency_key="key")
    _error(lambda: registry.create(keyed), "registry_invalid_argument")
    fingerprint = "a" * 64
    created = registry.create(keyed, idempotency_fingerprint=fingerprint)
    _error(lambda: registry.create(_run(3, idempotency_key="key"), idempotency_fingerprint="b" * 64), "registry_idempotency_conflict")
    plain = _run(4)
    registry.create(plain)
    _error(lambda: registry.create(plain), "registry_already_exists")
    _error(lambda: registry.get(_run(9).id), "registry_not_found")
    _error(lambda: registry.replace(created.run, expected_revision=True), "registry_invalid_argument")
    completed = _changed(created.run, status="completed", stage="completed", progress=100, finished_at=created.run.created_at)
    _error(lambda: registry.replace(completed, expected_revision=1), "registry_transition_invalid")
    running = _changed(created.run, status="running", stage="scan", progress=10, started_at=created.run.created_at)
    active = registry.replace(running, expected_revision=1)
    backwards = _changed(running, status="running", stage="ingestion", progress=1, started_at=running.created_at)
    _error(lambda: registry.replace(backwards, expected_revision=active.revision), "registry_transition_invalid")
    immutable = _changed(running, project={**running.project.model_dump(mode="json"), "name": "changed"})
    _error(lambda: registry.replace(immutable, expected_revision=active.revision), "registry_transition_invalid")


def test_neg_a3_reg_011_012_corruption_and_schema_fail_closed(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    created = registry.create(_run())
    connection = sqlite3.connect(tmp_path / "registry.sqlite")
    connection.execute("UPDATE scan_runs SET run_json = ? WHERE scan_id = ?", (b'{"x":NaN}', created.run.id))
    connection.commit()
    connection.close()
    _error(lambda: registry.get(created.run.id), "registry_corrupt")
    other = tmp_path / "unknown.sqlite"
    unknown = sqlite3.connect(other)
    unknown.execute("CREATE TABLE unrelated (x INTEGER)")
    unknown.commit()
    unknown.close()
    other.chmod(0o600)
    _error(lambda: SQLiteScanRunRegistry(other), "registry_schema_unsupported")


def test_neg_a3_reg_013_014_015_016_path_busy_close_and_sanitized_errors(tmp_path: Path) -> None:
    _error(lambda: SQLiteScanRunRegistry(Path(":memory:")), "registry_path_invalid")
    link = tmp_path / "link.sqlite"
    link.symlink_to(tmp_path / "target.sqlite")
    _error(lambda: SQLiteScanRunRegistry(link), "registry_path_invalid")
    registry = _registry(tmp_path, busy_timeout_ms=1)
    created = registry.create(_run())
    lock = sqlite3.connect(tmp_path / "registry.sqlite", isolation_level=None)
    lock.execute("BEGIN IMMEDIATE")
    _error(lambda: registry.replace(created.run, expected_revision=1), "registry_busy")
    lock.execute("ROLLBACK")
    assert registry.get(created.run.id).revision == 1
    registry.close()
    _error(lambda: registry.get(created.run.id), "registry_closed")


def test_schema_declaration_and_constraint_tampering_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "tampered-schema.sqlite"
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE registry_metadata (schema_name TEXT NOT NULL, schema_version INTEGER NOT NULL)")
        connection.execute("CREATE TABLE scan_runs (scan_id BLOB, revision TEXT NOT NULL, idempotency_key TEXT, idempotency_fingerprint INTEGER, created_at BLOB, status BLOB, contract_version BLOB, run_json TEXT)")
        connection.execute("INSERT INTO registry_metadata VALUES (?, ?)", ("openguard.scan-run-registry", 1))
        connection.execute("PRAGMA user_version = 1")
        connection.commit()
    finally:
        connection.close()
    path.chmod(0o600)
    _error(lambda: SQLiteScanRunRegistry(path), "registry_schema_unsupported")


def test_schema_object_allowlist_rejects_extra_table_view_and_trigger(tmp_path: Path) -> None:
    path = tmp_path / "objects.sqlite"
    registry = SQLiteScanRunRegistry(path)
    registry.close()
    cases = (
        ("CREATE TABLE unexpected_table (value TEXT)", "DROP TABLE unexpected_table"),
        ("CREATE VIEW unexpected_view AS SELECT scan_id FROM scan_runs", "DROP VIEW unexpected_view"),
        ("CREATE TRIGGER mutate_revision AFTER INSERT ON scan_runs BEGIN UPDATE scan_runs SET revision = 999 WHERE scan_id = NEW.scan_id; END", "DROP TRIGGER mutate_revision"),
    )
    for create, drop in cases:
        connection = sqlite3.connect(path)
        try:
            connection.execute(create)
            connection.commit()
        finally:
            connection.close()
        _error(lambda: SQLiteScanRunRegistry(path), "registry_schema_unsupported")
        connection = sqlite3.connect(path)
        try:
            connection.execute(drop)
            connection.commit()
        finally:
            connection.close()
    valid = SQLiteScanRunRegistry(path)
    try:
        assert valid.create(_run()).revision == 1
    finally:
        valid.close()
