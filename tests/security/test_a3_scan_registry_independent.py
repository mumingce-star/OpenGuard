"""Independent A3-0 security regression for the durable ScanRun registry.

The expected JSON, status transitions, and error envelope in this file are
constructed from the frozen contract.  No implementation-side helper is used
to decide expected values.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import pytest

from app.domain.models import (
    Component,
    DetectionMethod,
    FindingOutcome,
    HashValue,
    Project,
    ProducerType,
    RunEnvironment,
    RunProvenance,
    ScanError,
    ScanRun,
    ScanStage,
    ScanStatus,
    ScanSummary,
    SourceType,
    VerificationStatus,
)
from app.persistence import SQLiteScanRunRegistry, ScanRegistryError


BASE_TIME = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
POSITIVE_IDS = tuple(f"POS-A3-REG-{value:03d}" for value in range(1, 9))
NEGATIVE_IDS = tuple(f"NEG-A3-REG-{value:03d}" for value in range(1, 17))
_MISSING = object()


def _uuid(prefix: str, index: int) -> str:
    return f"{prefix}_123e4567-e89b-12d3-a456-42661417{index:04x}"


def _hash(digit: str) -> HashValue:
    return HashValue(algorithm="sha256", value=digit * 64)


def _summary() -> ScanSummary:
    return ScanSummary(
        component_count=0,
        ai_asset_count=0,
        evidence_count=0,
        finding_counts={
            FindingOutcome.PASS: 0,
            FindingOutcome.WARNING: 0,
            FindingOutcome.REVIEW_REQUIRED: 0,
            FindingOutcome.UNKNOWN: 0,
        },
    )


def _run(
    index: int = 1,
    *,
    at: datetime | None = None,
    idempotency_key: str | None = None,
    status: ScanStatus = ScanStatus.QUEUED,
    stage: ScanStage = ScanStage.QUEUED,
    progress: int = 0,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    errors: list[ScanError] | None = None,
    project_revision: str | None = None,
    root_digest: HashValue | None = None,
) -> ScanRun:
    created_at = at or (BASE_TIME + timedelta(seconds=index))
    project = Project(
        id=_uuid("prj", index),
        name=f"registry-project-{index}",
        source_type=SourceType.LOCAL,
        source=f"local-project-{index}",
        revision=project_revision,
        root_digest=root_digest,
        created_at=created_at,
    )
    provenance = RunProvenance(
        input_digest=_hash("c"),
        inventory_digest=None,
        tool_versions=[],
        ruleset_version="rules-0.1",
        contract_version="0.1.1",
        ai_enabled=False,
        ai_model=None,
        run_environment=RunEnvironment(
            python_version="3.12",
            platform="independent-test",
            openguard_version="test",
        ),
    )
    return ScanRun(
        contract_version="0.1.1",
        id=_uuid("scn", index),
        idempotency_key=idempotency_key,
        status=status,
        stage=stage,
        progress=progress,
        project=project,
        components=[],
        ai_assets=[],
        licenses=[],
        evidence=[],
        obligations=[],
        findings=[],
        remediations=[],
        summary=_summary(),
        provenance=provenance,
        errors=list(errors or []),
        report_links=[],
        created_at=created_at,
        started_at=started_at,
        finished_at=finished_at,
    )


def _changed(run: ScanRun, **changes: object) -> ScanRun:
    payload = run.model_dump(mode="json")
    payload.update(changes)
    return ScanRun.model_validate(payload)


def _recoverable_error() -> ScanError:
    return ScanError(
        code="controlled_partial",
        stage=ScanStage.SCAN,
        message="a recoverable scanner result",
        recoverable=True,
    )


def _fatal_error() -> ScanError:
    return ScanError(
        code="controlled_failure",
        stage=ScanStage.SCAN,
        message="a controlled scanner failure",
        recoverable=False,
    )


def _canonical_bytes(run: ScanRun) -> bytes:
    payload = run.model_dump(mode="json")
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _registry(tmp_path: Path, name: str = "registry.sqlite", **kwargs: object) -> SQLiteScanRunRegistry:
    return SQLiteScanRunRegistry(tmp_path / name, **kwargs)


def _sql(path: Path, statement: str, parameters: tuple[Any, ...] = ()) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(statement, parameters)
        connection.commit()
    finally:
        connection.close()


def _expect_error(
    call: Callable[[], object],
    code: str,
    *,
    forbidden: tuple[str, ...] = (),
) -> ScanRegistryError:
    with pytest.raises(ScanRegistryError) as raised:
        call()
    error = raised.value
    assert error.code == code
    assert error.args == (code,)
    assert str(error) == code
    assert error.__cause__ is None
    assert error.__suppress_context__ is True
    rendered = "".join(traceback.format_exception_only(type(error), error))
    for fragment in forbidden:
        assert fragment not in rendered
    return error


def test_frozen_a3_case_ids_are_present_once_in_this_suite() -> None:
    assert len(POSITIVE_IDS) == 8
    assert len(NEGATIVE_IDS) == 16
    assert len(set(POSITIVE_IDS + NEGATIVE_IDS)) == 24


def test_pos_a3_reg_001_create_get_uses_p0_canonical_blob(tmp_path: Path) -> None:
    path = tmp_path / "canonical.sqlite"
    run = _run(1)
    registry = SQLiteScanRunRegistry(path)
    try:
        stored = registry.create(run)
        assert stored.revision == 1
        assert stored.run == run
        assert registry.get(run.id) == stored
    finally:
        registry.close()

    # This is a second, independently opened SQLite connection.  The expected
    # bytes are built directly from the frozen serialization rule above.
    connection = sqlite3.connect(path)
    try:
        row = connection.execute(
            "SELECT scan_id, revision, idempotency_key, idempotency_fingerprint, created_at, status, contract_version, run_json FROM scan_runs"
        ).fetchone()
        assert row is not None
        assert row[:2] == (run.id, 1)
        assert row[2:4] == (None, None)
        assert row[4] == run.created_at.isoformat().replace("+00:00", "Z")
        assert row[5:7] == ("queued", "0.1.1")
        assert type(row[7]) is bytes
        assert row[7] == _canonical_bytes(run)
        assert connection.execute("SELECT count(*) FROM scan_runs").fetchone() == (1,)
    finally:
        connection.close()


def test_pos_a3_reg_002_idempotency_is_cross_instance_and_single_row(tmp_path: Path) -> None:
    path = tmp_path / "idempotency.sqlite"
    first_registry = SQLiteScanRunRegistry(path)
    second_registry = SQLiteScanRunRegistry(path)
    key = "request-key-002"
    fingerprint = hashlib.sha256(b"normalized-request-002").hexdigest()
    try:
        first = first_registry.create(_run(1, idempotency_key=key), idempotency_fingerprint=fingerprint)
        retry = second_registry.create(_run(2, idempotency_key=key), idempotency_fingerprint=fingerprint)
        assert retry == first
        assert second_registry.get(first.run.id) == first
    finally:
        first_registry.close()
        second_registry.close()
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT count(*) FROM scan_runs").fetchone() == (1,)
        assert connection.execute(
            "SELECT idempotency_key, idempotency_fingerprint, revision FROM scan_runs"
        ).fetchone() == (key, fingerprint, 1)
    finally:
        connection.close()


def test_pos_a3_reg_003_cas_transitions_increment_once_and_complete_at_100(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    try:
        queued = registry.create(_run(1))
        running = _changed(
            queued.run,
            status="running",
            stage="ingestion",
            progress=10,
            started_at=queued.run.created_at,
        )
        active = registry.replace(running, expected_revision=1)
        assert active.revision == 2
        progressed = _changed(running, stage="scan", progress=45)
        progressed_stored = registry.replace(progressed, expected_revision=2)
        assert progressed_stored.revision == 3
        completed = _changed(
            progressed,
            status="completed",
            stage="completed",
            progress=100,
            finished_at=progressed.created_at + timedelta(seconds=1),
        )
        final = registry.replace(completed, expected_revision=3)
        assert final.revision == 4
        assert final.run.status is ScanStatus.COMPLETED
        assert final.run.stage is ScanStage.COMPLETED
        assert final.run.progress == 100
        assert final.run.started_at == queued.run.created_at
        assert final.run.finished_at is not None
    finally:
        registry.close()


def test_pos_a3_reg_004_matching_canonical_json_is_a_revision_and_wal_noop(tmp_path: Path) -> None:
    path = tmp_path / "noop.sqlite"
    registry = SQLiteScanRunRegistry(path)
    run = _run(1)
    try:
        created = registry.create(run)
        connection = sqlite3.connect(path)
        try:
            before = connection.execute(
                "SELECT revision, run_json FROM scan_runs WHERE scan_id = ?", (run.id,)
            ).fetchone()
            before_data_version = connection.execute("PRAGMA data_version").fetchone()[0]
            assert registry.replace(run, expected_revision=1) == created
            after = connection.execute(
                "SELECT revision, run_json FROM scan_runs WHERE scan_id = ?", (run.id,)
            ).fetchone()
            after_data_version = connection.execute("PRAGMA data_version").fetchone()[0]
        finally:
            connection.close()
        assert after == before
        assert after_data_version == before_data_version
    finally:
        registry.close()


def test_pos_a3_reg_005_list_keyset_order_and_100_boundary(tmp_path: Path) -> None:
    path = tmp_path / "paging.sqlite"
    registry = SQLiteScanRunRegistry(path)
    try:
        created = [registry.create(_run(index)) for index in range(1, 102)]
        first = registry.list_runs(limit=100)
        assert len(first.items) == 100
        assert first.next_after_scan_id == first.items[-1].run.id
        second = registry.list_runs(limit=100, after_scan_id=first.next_after_scan_id)
        assert len(second.items) == 1
        assert second.next_after_scan_id is None
        all_items = (*first.items, *second.items)
        expected = tuple(sorted(created, key=lambda item: (-item.run.created_at.timestamp(), item.run.id)))
        assert all_items == expected
        assert len({item.run.id for item in all_items}) == 101

        tie_path = tmp_path / "paging-tie.sqlite"
        tie_registry = SQLiteScanRunRegistry(tie_path)
        try:
            same_time = BASE_TIME + timedelta(days=3)
            low = tie_registry.create(_run(200, at=same_time))
            high = tie_registry.create(_run(201, at=same_time))
            tied = tie_registry.list_runs(limit=2)
            assert [item.run.id for item in tied.items] == sorted([low.run.id, high.run.id])
        finally:
            tie_registry.close()
    finally:
        registry.close()


def test_pos_a3_reg_006_restart_preserves_running_queued_and_idempotency(tmp_path: Path) -> None:
    path = tmp_path / "restart.sqlite"
    key = "restart-key"
    fingerprint = hashlib.sha256(b"restart-request").hexdigest()
    first_registry = SQLiteScanRunRegistry(path)
    queued = first_registry.create(_run(1, idempotency_key=key), idempotency_fingerprint=fingerprint)
    running = _changed(
        queued.run,
        status="running",
        stage="inventory",
        progress=20,
        started_at=queued.run.created_at,
    )
    active = first_registry.replace(running, expected_revision=1)
    still_queued = first_registry.create(_run(2))
    first_registry.close()

    second_registry = SQLiteScanRunRegistry(path)
    try:
        assert second_registry.get(active.run.id) == active
        assert second_registry.get(active.run.id).run.status is ScanStatus.RUNNING
        assert second_registry.get(still_queued.run.id).run.status is ScanStatus.QUEUED
        assert second_registry.get(still_queued.run.id).run.started_at is None
        assert second_registry.create(_run(3, idempotency_key=key), idempotency_fingerprint=fingerprint) == active
    finally:
        second_registry.close()


def test_pos_a3_reg_007_two_independent_instances_have_one_cas_winner(tmp_path: Path) -> None:
    path = tmp_path / "cas.sqlite"
    first_registry = SQLiteScanRunRegistry(path)
    second_registry = SQLiteScanRunRegistry(path)
    try:
        created = first_registry.create(_run(1))
        candidate = _changed(
            created.run,
            status="running",
            stage="scan",
            progress=30,
            started_at=created.run.created_at,
        )
        barrier = threading.Barrier(3)

        def attempt(registry: SQLiteScanRunRegistry) -> tuple[str, object]:
            barrier.wait(timeout=2)
            try:
                return ("ok", registry.replace(candidate, expected_revision=1))
            except ScanRegistryError as error:
                return ("error", error.code)

        with ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(attempt, first_registry)
            second_future = executor.submit(attempt, second_registry)
            barrier.wait(timeout=2)
            results = [first_future.result(timeout=3), second_future.result(timeout=3)]
        assert sorted(result[0] for result in results) == ["error", "ok"]
        assert [result[1] for result in results if result[0] == "error"] == ["registry_revision_conflict"]
        winner = first_registry.get(created.run.id)
        assert winner.revision == 2
        assert winner.run.status is ScanStatus.RUNNING
        assert winner.run.progress == 30
    finally:
        first_registry.close()
        second_registry.close()


def test_pos_a3_reg_008_terminal_paths_and_context_close_are_reopenable(tmp_path: Path) -> None:
    registry = _registry(tmp_path, "terminal.sqlite")
    try:
        cancelled = registry.create(_run(1))
        cancelled_run = _changed(
            cancelled.run,
            status="cancelled",
            stage="queued",
            progress=0,
            finished_at=cancelled.run.created_at,
        )
        assert registry.replace(cancelled_run, expected_revision=1).run.status is ScanStatus.CANCELLED

        for index, terminal, error in (
            (2, "partial", _recoverable_error()),
            (3, "failed", _fatal_error()),
            (4, "cancelled", None),
        ):
            queued = registry.create(_run(index))
            running = _changed(
                queued.run,
                status="running",
                stage="scan",
                progress=25,
                started_at=queued.run.created_at,
            )
            active = registry.replace(running, expected_revision=1)
            changes: dict[str, object] = {
                "status": terminal,
                "stage": "report",
                "progress": 60,
                "finished_at": running.created_at + timedelta(seconds=1),
            }
            if error is not None:
                changes["errors"] = [error]
            final = registry.replace(_changed(running, **changes), expected_revision=active.revision)
            assert final.run.status.value == terminal
            assert final.run.finished_at is not None
    finally:
        registry.close()

    context_path = tmp_path / "context.sqlite"
    with SQLiteScanRunRegistry(context_path) as context_registry:
        context_run = context_registry.create(_run(10))
    _expect_error(lambda: context_registry.get(context_run.run.id), "registry_closed")
    context_registry.close()
    reopened = SQLiteScanRunRegistry(context_path)
    try:
        assert reopened.get(context_run.run.id) == context_run
    finally:
        reopened.close()


def test_neg_a3_reg_001_exact_types_p0_and_argument_validation_are_write_free(tmp_path: Path) -> None:
    path = tmp_path / "arguments.sqlite"
    registry = SQLiteScanRunRegistry(path)
    try:
        _expect_error(lambda: registry.create(object()), "registry_invalid_argument")
        invalid_p0 = _run(1)
        object.__setattr__(invalid_p0, "progress", -1)
        _expect_error(lambda: registry.create(invalid_p0), "registry_invalid_argument")
        _expect_error(lambda: registry.get("scn_invalid"), "registry_invalid_argument")
        _expect_error(lambda: registry.list_runs(limit=True), "registry_invalid_argument")
        _expect_error(lambda: registry.list_runs(limit=0), "registry_invalid_argument")
        _expect_error(lambda: registry.list_runs(limit=101), "registry_invalid_argument")
        _expect_error(lambda: registry.replace(_run(1), expected_revision=True), "registry_invalid_argument")
        _expect_error(lambda: registry.create(_run(1), idempotency_fingerprint="a" * 64), "registry_invalid_argument")
        with sqlite3.connect(path) as connection:
            assert connection.execute("SELECT count(*) FROM scan_runs").fetchone() == (0,)
    finally:
        registry.close()

    class DerivedScanRun(ScanRun):
        pass

    derived = DerivedScanRun.model_validate(_run(2).model_dump(mode="json"))
    another_registry = SQLiteScanRunRegistry(tmp_path / "derived.sqlite")
    try:
        _expect_error(lambda: another_registry.create(derived), "registry_invalid_argument")
    finally:
        another_registry.close()
    _expect_error(lambda: SQLiteScanRunRegistry(tmp_path / "bad-timeout.sqlite", busy_timeout_ms=True), "registry_invalid_argument")


def test_neg_a3_reg_002_nonqueued_or_nonempty_initial_snapshot_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "initial.sqlite"
    registry = _registry(tmp_path, "initial.sqlite")
    try:
        running = _run(1, status=ScanStatus.RUNNING, stage=ScanStage.INGESTION, progress=1, started_at=BASE_TIME)
        _expect_error(lambda: registry.create(running), "registry_invalid_argument")
        completed = _run(2, status=ScanStatus.COMPLETED, stage=ScanStage.COMPLETED, progress=100, finished_at=BASE_TIME)
        _expect_error(lambda: registry.create(completed), "registry_invalid_argument")
        queued_with_started = _run(3, started_at=BASE_TIME)
        _expect_error(lambda: registry.create(queued_with_started), "registry_invalid_argument")
        with sqlite3.connect(path) as connection:
            assert connection.execute("SELECT count(*) FROM scan_runs").fetchone() == (0,)
    finally:
        registry.close()


def test_neg_a3_reg_003_key_and_fingerprint_pairing_is_strict(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    try:
        _expect_error(lambda: registry.create(_run(1), idempotency_fingerprint="a" * 64), "registry_invalid_argument")
        _expect_error(lambda: registry.create(_run(2, idempotency_key="key-without-fingerprint")), "registry_invalid_argument")
        for index, fingerprint in ((3, "g" * 64), (4, "A" * 64), (5, "a" * 63)):
            _expect_error(
                lambda fingerprint=fingerprint, index=index: registry.create(
                    _run(index, idempotency_key=f"key-{index}"),
                    idempotency_fingerprint=fingerprint,
                ),
                "registry_invalid_argument",
            )
        with sqlite3.connect(tmp_path / "registry.sqlite") as connection:
            assert connection.execute("SELECT count(*) FROM scan_runs").fetchone() == (0,)
    finally:
        registry.close()


def test_neg_a3_reg_004_duplicate_id_and_idempotency_conflict_do_not_leak_inputs(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    key = "secret-idempotency-key"
    first_fingerprint = "a" * 64
    second_fingerprint = "b" * 64
    try:
        plain = registry.create(_run(1))
        duplicate_error = _expect_error(lambda: registry.create(_run(1)), "registry_already_exists")
        assert str(duplicate_error) == "registry_already_exists"
        registry.create(_run(2, idempotency_key=key), idempotency_fingerprint=first_fingerprint)
        _expect_error(
            lambda: registry.create(_run(3, idempotency_key=key), idempotency_fingerprint=second_fingerprint),
            "registry_idempotency_conflict",
            forbidden=(key, first_fingerprint, second_fingerprint),
        )
        assert registry.get(plain.run.id) == plain
        with sqlite3.connect(tmp_path / "registry.sqlite") as connection:
            assert connection.execute("SELECT count(*) FROM scan_runs").fetchone() == (2,)
    finally:
        registry.close()


def test_neg_a3_reg_005_missing_get_replace_anchor_and_true_empty_page(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    try:
        empty = registry.list_runs()
        assert empty.items == ()
        assert empty.next_after_scan_id is None
        missing_id = _uuid("scn", 900)
        _expect_error(lambda: registry.get(missing_id), "registry_not_found")
        _expect_error(lambda: registry.replace(_run(900), expected_revision=1), "registry_not_found")
        _expect_error(lambda: registry.list_runs(after_scan_id=missing_id), "registry_not_found")
    finally:
        registry.close()


def test_neg_a3_reg_006_stale_revision_never_overwrites_winner(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    try:
        created = registry.create(_run(1))
        winner = _changed(created.run, status="running", stage="scan", progress=30, started_at=created.run.created_at)
        committed = registry.replace(winner, expected_revision=1)
        stale = _changed(created.run, status="running", stage="scan", progress=90, started_at=created.run.created_at)
        _expect_error(lambda: registry.replace(stale, expected_revision=1), "registry_revision_conflict")
        assert registry.get(created.run.id) == committed
    finally:
        registry.close()


def test_neg_a3_reg_007_disallowed_queued_and_terminal_transitions_are_rejected(tmp_path: Path) -> None:
    for index, status, stage, progress, errors in (
        (1, "completed", "completed", 100, []),
        (2, "partial", "report", 50, [_recoverable_error()]),
        (3, "failed", "report", 50, [_fatal_error()]),
    ):
        registry = _registry(tmp_path, f"transition-{index}.sqlite")
        try:
            queued = registry.create(_run(index + 10))
            candidate = _changed(
                queued.run,
                status=status,
                stage=stage,
                progress=progress,
                errors=errors,
                finished_at=queued.run.created_at,
            )
            _expect_error(lambda: registry.replace(candidate, expected_revision=1), "registry_transition_invalid")
        finally:
            registry.close()

    terminal_registry = _registry(tmp_path, "terminal-transition.sqlite")
    try:
        queued = terminal_registry.create(_run(30))
        running = _changed(queued.run, status="running", stage="scan", progress=20, started_at=queued.run.created_at)
        active = terminal_registry.replace(running, expected_revision=1)
        complete = _changed(running, status="completed", stage="completed", progress=100, finished_at=running.created_at)
        terminal = terminal_registry.replace(complete, expected_revision=active.revision)
        candidate = _changed(terminal.run, status="cancelled", stage="completed", progress=100, finished_at=terminal.run.finished_at)
        _expect_error(lambda: terminal_registry.replace(candidate, expected_revision=terminal.revision), "registry_transition_invalid")
    finally:
        terminal_registry.close()


def test_neg_a3_reg_008_running_regression_and_bad_completed_progress_are_rejected(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    try:
        queued = registry.create(_run(1))
        running = _changed(queued.run, status="running", stage="scan", progress=40, started_at=queued.run.created_at)
        active = registry.replace(running, expected_revision=1)
        stage_back = _changed(running, stage="inventory", progress=45)
        _expect_error(lambda: registry.replace(stage_back, expected_revision=active.revision), "registry_transition_invalid")
        progress_back = _changed(running, stage="scan", progress=39)
        _expect_error(lambda: registry.replace(progress_back, expected_revision=active.revision), "registry_transition_invalid")
        bad_completed = _changed(running, status="completed", stage="completed", progress=99, finished_at=running.created_at)
        _expect_error(lambda: registry.replace(bad_completed, expected_revision=active.revision), "registry_transition_invalid")
        assert registry.get(queued.run.id) == active
    finally:
        registry.close()


def test_neg_a3_reg_009_immutable_identity_and_project_fields_are_rejected(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    try:
        queued = registry.create(_run(1, idempotency_key="fixed-key"), idempotency_fingerprint="a" * 64)
        running = _changed(queued.run, status="running", stage="scan", progress=20, started_at=queued.run.created_at)
        active = registry.replace(running, expected_revision=1)

        changed_key = _changed(running, idempotency_key="other-key")
        changed_created = _changed(running, created_at=running.created_at + timedelta(seconds=1))
        for candidate in (changed_key, changed_created):
            _expect_error(lambda candidate=candidate: registry.replace(candidate, expected_revision=active.revision), "registry_transition_invalid")

        project_payload = running.project.model_dump(mode="json")
        for field, value in (
            ("id", _uuid("prj", 99)),
            ("name", "different-project"),
            ("source_type", "zip"),
            ("source", "different-source"),
            ("created_at", (running.project.created_at + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")),
        ):
            mutated = dict(project_payload)
            mutated[field] = value
            candidate = _changed(running, project=mutated)
            _expect_error(lambda candidate=candidate: registry.replace(candidate, expected_revision=active.revision), "registry_transition_invalid")

        identified = _changed(
            running,
            project={**project_payload, "revision": "rev-1", "root_digest": {"algorithm": "sha256", "value": "e" * 64}},
        )
        identified_stored = registry.replace(identified, expected_revision=active.revision)
        assert identified_stored.revision == 3
        for revision, root_digest in (
            ("rev-2", {"algorithm": "sha256", "value": "f" * 64}),
            (None, {"algorithm": "sha256", "value": "e" * 64}),
            ("rev-1", None),
        ):
            mutated = _changed(
                identified,
                project={**project_payload, "revision": revision, "root_digest": root_digest},
            )
            _expect_error(lambda mutated=mutated: registry.replace(mutated, expected_revision=identified_stored.revision), "registry_transition_invalid")

        different_id = _run(99, status=ScanStatus.RUNNING, stage=ScanStage.SCAN, progress=20, started_at=running.created_at, idempotency_key="fixed-key")
        _expect_error(lambda: registry.replace(different_id, expected_revision=active.revision), "registry_not_found")
        assert registry.get(running.id) == identified_stored
    finally:
        registry.close()


def test_neg_a3_reg_010_time_and_p0_reference_invariants_fail_closed(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    try:
        queued = registry.create(_run(1))
        running = _changed(queued.run, status="running", stage="scan", progress=20, started_at=queued.run.created_at)
        active = registry.replace(running, expected_revision=1)
        missing_started = _changed(running, started_at=None)
        changed_started = _changed(running, started_at=running.created_at + timedelta(seconds=2))
        for candidate in (missing_started, changed_started):
            _expect_error(lambda candidate=candidate: registry.replace(candidate, expected_revision=active.revision), "registry_transition_invalid")

        early_partial = _changed(
            running,
            status="partial",
            stage="report",
            progress=60,
            errors=[_recoverable_error()],
            finished_at=running.created_at - timedelta(seconds=1),
        )
        _expect_error(lambda: registry.replace(early_partial, expected_revision=active.revision), "registry_transition_invalid")

        invalid_component = Component(
            id=_uuid("cmp", 1),
            name="unreferenced-component",
            version=None,
            ecosystem="unknown",
            evidence_ids=[_uuid("evd", 1)],
            detected_by=[DetectionMethod.MANUAL],
            confidence=1.0,
        )
        invalid_reference = _changed(running)
        object.__setattr__(invalid_reference, "components", [invalid_component])
        _expect_error(lambda: registry.replace(invalid_reference, expected_revision=active.revision), "registry_invalid_argument")

        invalid_summary = _changed(running)
        object.__setattr__(invalid_summary, "summary", _summary().model_copy(update={"component_count": 1}))
        _expect_error(lambda: registry.replace(invalid_summary, expected_revision=active.revision), "registry_invalid_argument")
        assert registry.get(running.id) == active
    finally:
        registry.close()


@pytest.mark.parametrize(
    "case_name,raw",
    [
        ("non_utf8", b"\xff"),
        ("duplicate_key", b'{"contract_version":"0.1.1","contract_version":"0.1.1"}'),
        ("nan", b'{"value":NaN}'),
        ("non_object", b"[]"),
        ("noncanonical", b" {\"status\": \"queued\"} \n"),
    ],
)
def test_neg_a3_reg_011_hand_injected_json_bytes_never_yield_partial_rows(tmp_path: Path, case_name: str, raw: bytes) -> None:
    path = tmp_path / f"corrupt-{case_name}.sqlite"
    registry = SQLiteScanRunRegistry(path)
    run = _run(1)
    registry.create(run)
    registry.close()
    _sql(path, "UPDATE scan_runs SET run_json = ? WHERE scan_id = ?", (raw, run.id))
    reader = SQLiteScanRunRegistry(path)
    try:
        _expect_error(lambda: reader.get(run.id), "registry_corrupt")
        _expect_error(lambda: reader.list_runs(), "registry_corrupt")
        _expect_error(lambda: reader.replace(run, expected_revision=1), "registry_corrupt")
    finally:
        reader.close()


def test_neg_a3_reg_011_p0_invalid_and_mirror_column_corruption_fail_whole_operation(tmp_path: Path) -> None:
    cases = {
        "invalid-p0": _canonical_bytes(_run(1)).replace(b'"progress":0', b'"progress":101'),
        "column-status": _canonical_bytes(_run(2)),
        "column-id": _canonical_bytes(_run(3)),
        "text-blob": _canonical_bytes(_run(4)),
    }
    for name, raw in cases.items():
        path = tmp_path / f"mirror-{name}.sqlite"
        registry = SQLiteScanRunRegistry(path)
        run = _run(int(name[-1]) if name[-1].isdigit() else 1)
        registry.create(run)
        registry.close()
        if name == "invalid-p0":
            _sql(path, "UPDATE scan_runs SET run_json = ? WHERE scan_id = ?", (raw, run.id))
        elif name == "column-status":
            _sql(path, "UPDATE scan_runs SET status = ? WHERE scan_id = ?", ("running", run.id))
        elif name == "column-id":
            lookup_id = _uuid("scn", 77)
            _sql(path, "UPDATE scan_runs SET scan_id = ? WHERE scan_id = ?", (lookup_id, run.id))
        else:
            _sql(path, "UPDATE scan_runs SET run_json = CAST(? AS TEXT) WHERE scan_id = ?", (raw.decode("utf-8"), run.id))
        reader = SQLiteScanRunRegistry(path)
        try:
            lookup_id = lookup_id if name == "column-id" else run.id
            _expect_error(lambda: reader.get(lookup_id), "registry_corrupt")
            _expect_error(lambda: reader.list_runs(), "registry_corrupt")
        finally:
            reader.close()


def _make_schema_variant(path: Path, *, metadata_name: str = "openguard.scan-run-registry", metadata_version: int = 1, user_version: int = 1) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE registry_metadata (schema_name TEXT NOT NULL, schema_version INTEGER NOT NULL)")
        connection.execute("CREATE TABLE unrelated (value TEXT)")
        connection.execute("INSERT INTO registry_metadata VALUES (?, ?)", (metadata_name, metadata_version))
        connection.execute(f"PRAGMA user_version = {user_version}")
        connection.commit()
    finally:
        connection.close()


def _schema_snapshot(path: Path) -> tuple[tuple[tuple[str, str | None], ...], tuple[object, ...], tuple[object, ...]]:
    connection = sqlite3.connect(path)
    try:
        tables = tuple(
            connection.execute(
                "SELECT name, sql FROM sqlite_master WHERE type = 'table' ORDER BY name"
            ).fetchall()
        )
        metadata = tuple(connection.execute("SELECT * FROM registry_metadata").fetchall()) if ("registry_metadata",) in {(row[0],) for row in tables} else ()
        user_version = tuple(connection.execute("PRAGMA user_version").fetchone() or ())
        return tables, metadata, user_version
    finally:
        connection.close()


def test_neg_a3_reg_012_unknown_metadata_version_and_missing_schema_never_rebuild(tmp_path: Path) -> None:
    for name, kwargs in (
        ("metadata-name", {"metadata_name": "unknown.registry"}),
        ("metadata-version", {"metadata_version": 2}),
        ("user-version", {"user_version": 2}),
    ):
        path = tmp_path / f"schema-{name}.sqlite"
        _make_schema_variant(path, **kwargs)
        path.chmod(0o600)
        before = _schema_snapshot(path)
        _expect_error(lambda path=path: SQLiteScanRunRegistry(path), "registry_schema_unsupported")
        assert _schema_snapshot(path) == before

    missing = tmp_path / "schema-missing.sqlite"
    connection = sqlite3.connect(missing)
    try:
        connection.execute("CREATE TABLE unrelated (value TEXT)")
        connection.execute("PRAGMA user_version = 1")
        connection.commit()
    finally:
        connection.close()
    missing.chmod(0o600)
    before = _schema_snapshot(missing)
    _expect_error(lambda: SQLiteScanRunRegistry(missing), "registry_schema_unsupported")
    assert _schema_snapshot(missing) == before

    row_path = tmp_path / "schema-row.sqlite"
    registry = SQLiteScanRunRegistry(row_path)
    run = _run(1)
    registry.create(run)
    registry.close()
    _sql(row_path, "UPDATE scan_runs SET contract_version = ? WHERE scan_id = ?", ("9.9.9", run.id))
    reader = SQLiteScanRunRegistry(row_path)
    try:
        _expect_error(lambda: reader.get(run.id), "registry_schema_unsupported")
    finally:
        reader.close()


def test_hardening_schema_declared_types_and_constraints_are_verified(tmp_path: Path) -> None:
    path = tmp_path / "tampered-declaration.sqlite"
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE registry_metadata (schema_name TEXT NOT NULL, schema_version INTEGER NOT NULL)")
        # Same column names, deliberately wrong declared types and no PK,
        # CHECK, or idempotency UNIQUE constraint.
        connection.execute(
            "CREATE TABLE scan_runs (scan_id BLOB, revision TEXT NOT NULL, idempotency_key TEXT, idempotency_fingerprint INTEGER, created_at BLOB, status BLOB, contract_version BLOB, run_json TEXT)"
        )
        connection.execute("INSERT INTO registry_metadata VALUES (?, ?)", ("openguard.scan-run-registry", 1))
        connection.execute("PRAGMA user_version = 1")
        connection.commit()
    finally:
        connection.close()
    path.chmod(0o600)
    _expect_error(lambda: SQLiteScanRunRegistry(path), "registry_schema_unsupported")


_VALID_METADATA_SQL = "CREATE TABLE registry_metadata (schema_name TEXT NOT NULL, schema_version INTEGER NOT NULL)"
_VALID_RUN_SQL = "CREATE TABLE scan_runs (scan_id TEXT PRIMARY KEY, revision INTEGER NOT NULL CHECK (revision >= 1), idempotency_key TEXT UNIQUE NULL, idempotency_fingerprint TEXT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL, contract_version TEXT NOT NULL, run_json BLOB NOT NULL)"


def _make_declared_schema_probe(
    path: Path,
    *,
    metadata_sql: str = _VALID_METADATA_SQL,
    run_sql: str = _VALID_RUN_SQL,
    extra_sql: tuple[str, ...] = (),
) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(metadata_sql)
        connection.execute(run_sql)
        for statement in extra_sql:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO registry_metadata (schema_name, schema_version) VALUES (?, ?)",
            ("openguard.scan-run-registry", 1),
        )
        connection.execute("PRAGMA user_version = 1")
        connection.commit()
    finally:
        connection.close()
    path.chmod(0o600)


@pytest.mark.parametrize(
    "case_name,metadata_sql,run_sql,extra_sql",
    [
        (
            "metadata-type",
            "CREATE TABLE registry_metadata (schema_name BLOB NOT NULL, schema_version INTEGER NOT NULL)",
            _VALID_RUN_SQL,
            (),
        ),
        (
            "metadata-notnull",
            "CREATE TABLE registry_metadata (schema_name TEXT, schema_version INTEGER NOT NULL)",
            _VALID_RUN_SQL,
            (),
        ),
        (
            "metadata-extra-column",
            "CREATE TABLE registry_metadata (schema_name TEXT NOT NULL, schema_version INTEGER NOT NULL, extra TEXT)",
            _VALID_RUN_SQL,
            (),
        ),
        (
            "scan-type",
            _VALID_METADATA_SQL,
            "CREATE TABLE scan_runs (scan_id BLOB PRIMARY KEY, revision INTEGER NOT NULL CHECK (revision >= 1), idempotency_key TEXT UNIQUE NULL, idempotency_fingerprint TEXT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL, contract_version TEXT NOT NULL, run_json BLOB NOT NULL)",
            (),
        ),
        (
            "revision-type",
            _VALID_METADATA_SQL,
            "CREATE TABLE scan_runs (scan_id TEXT PRIMARY KEY, revision TEXT NOT NULL CHECK (revision >= 1), idempotency_key TEXT UNIQUE NULL, idempotency_fingerprint TEXT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL, contract_version TEXT NOT NULL, run_json BLOB NOT NULL)",
            (),
        ),
        (
            "run-json-type",
            _VALID_METADATA_SQL,
            "CREATE TABLE scan_runs (scan_id TEXT PRIMARY KEY, revision INTEGER NOT NULL CHECK (revision >= 1), idempotency_key TEXT UNIQUE NULL, idempotency_fingerprint TEXT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL, contract_version TEXT NOT NULL, run_json TEXT NOT NULL)",
            (),
        ),
        (
            "revision-notnull",
            _VALID_METADATA_SQL,
            "CREATE TABLE scan_runs (scan_id TEXT PRIMARY KEY, revision INTEGER CHECK (revision >= 1), idempotency_key TEXT UNIQUE NULL, idempotency_fingerprint TEXT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL, contract_version TEXT NOT NULL, run_json BLOB NOT NULL)",
            (),
        ),
        (
            "scan-id-no-primary-key",
            _VALID_METADATA_SQL,
            "CREATE TABLE scan_runs (scan_id TEXT UNIQUE NULL, revision INTEGER NOT NULL CHECK (revision >= 1), idempotency_key TEXT UNIQUE NULL, idempotency_fingerprint TEXT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL, contract_version TEXT NOT NULL, run_json BLOB NOT NULL)",
            (),
        ),
        (
            "revision-check",
            _VALID_METADATA_SQL,
            "CREATE TABLE scan_runs (scan_id TEXT PRIMARY KEY, revision INTEGER NOT NULL CHECK (revision > 1), idempotency_key TEXT UNIQUE NULL, idempotency_fingerprint TEXT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL, contract_version TEXT NOT NULL, run_json BLOB NOT NULL)",
            (),
        ),
        (
            "idempotency-no-unique",
            _VALID_METADATA_SQL,
            "CREATE TABLE scan_runs (scan_id TEXT PRIMARY KEY, revision INTEGER NOT NULL CHECK (revision >= 1), idempotency_key TEXT NULL, idempotency_fingerprint TEXT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL, contract_version TEXT NOT NULL, run_json BLOB NOT NULL)",
            (),
        ),
        (
            "extra-index",
            _VALID_METADATA_SQL,
            _VALID_RUN_SQL,
            ("CREATE INDEX unexpected_status_index ON scan_runs(status)",),
        ),
        (
            "scan-extra-column",
            _VALID_METADATA_SQL,
            "CREATE TABLE scan_runs (scan_id TEXT PRIMARY KEY, revision INTEGER NOT NULL CHECK (revision >= 1), idempotency_key TEXT UNIQUE NULL, idempotency_fingerprint TEXT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL, contract_version TEXT NOT NULL, run_json BLOB NOT NULL, extra TEXT)",
            (),
        ),
    ],
)
def test_hardening_each_declared_schema_component_fails_closed(
    tmp_path: Path,
    case_name: str,
    metadata_sql: str,
    run_sql: str,
    extra_sql: tuple[str, ...],
) -> None:
    path = tmp_path / f"tampered-{case_name}.sqlite"
    _make_declared_schema_probe(path, metadata_sql=metadata_sql, run_sql=run_sql, extra_sql=extra_sql)
    _expect_error(lambda: SQLiteScanRunRegistry(path), "registry_schema_unsupported")


def test_hardening_valid_schema_reopens_after_close(tmp_path: Path) -> None:
    path = tmp_path / "valid-reopen.sqlite"
    first = SQLiteScanRunRegistry(path)
    try:
        stored = first.create(_run(71))
    finally:
        first.close()

    reopened = SQLiteScanRunRegistry(path)
    try:
        assert reopened.get(stored.run.id) == stored
    finally:
        reopened.close()


def test_final_a3_001_extra_sqlite_objects_fail_closed_and_clean_reopen(tmp_path: Path) -> None:
    path = tmp_path / "sqlite-master-objects.sqlite"
    registry = SQLiteScanRunRegistry(path)
    try:
        stored = registry.create(_run(72))
    finally:
        registry.close()

    objects = (
        (
            "table",
            "CREATE TABLE unexpected_table (value TEXT)",
            "DROP TABLE unexpected_table",
        ),
        (
            "view",
            "CREATE VIEW unexpected_view AS SELECT scan_id, revision FROM scan_runs",
            "DROP VIEW unexpected_view",
        ),
        (
            "trigger",
            "CREATE TRIGGER unexpected_revision_trigger AFTER INSERT ON scan_runs BEGIN UPDATE scan_runs SET revision = 999 WHERE scan_id = NEW.scan_id; END",
            "DROP TRIGGER unexpected_revision_trigger",
        ),
    )
    for _, create_statement, drop_statement in objects:
        _sql(path, create_statement)
        _expect_error(lambda: SQLiteScanRunRegistry(path), "registry_schema_unsupported")
        _sql(path, drop_statement)

        reopened = SQLiteScanRunRegistry(path)
        try:
            recovered = reopened.get(stored.run.id)
            assert recovered.revision == 1
            assert recovered.run == stored.run
        finally:
            reopened.close()


def test_neg_a3_reg_013_real_posix_path_modes_fifo_and_symlink_gates(tmp_path: Path) -> None:
    uri_path = Path("file:registry.sqlite?mode=memory&cache=shared")
    _expect_error(lambda: SQLiteScanRunRegistry(uri_path), "registry_path_invalid")

    directory = tmp_path / "database-directory"
    directory.mkdir()
    _expect_error(lambda: SQLiteScanRunRegistry(directory), "registry_path_invalid")

    fifo = tmp_path / "database.fifo"
    os.mkfifo(fifo)
    _expect_error(lambda: SQLiteScanRunRegistry(fifo), "registry_path_invalid")

    target = tmp_path / "target.sqlite"
    target.write_bytes(b"")
    db_link = tmp_path / "database-link.sqlite"
    db_link.symlink_to(target)
    _expect_error(lambda: SQLiteScanRunRegistry(db_link), "registry_path_invalid")

    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    parent_link = tmp_path / "parent-link"
    parent_link.symlink_to(real_parent, target_is_directory=True)
    _expect_error(lambda: SQLiteScanRunRegistry(parent_link / "registry.sqlite"), "registry_path_invalid")

    private_path = tmp_path / "private.sqlite"
    private_registry = SQLiteScanRunRegistry(private_path)
    private_registry.close()
    assert stat.S_IMODE(private_path.stat().st_mode) == 0o600
    private_path.chmod(0o640)
    _expect_error(lambda: SQLiteScanRunRegistry(private_path), "registry_permission_denied")
    private_path.chmod(0o600)

    public_parent = tmp_path / "public-parent"
    public_parent.mkdir()
    public_parent.chmod(0o755)
    try:
        _expect_error(lambda: SQLiteScanRunRegistry(public_parent / "registry.sqlite"), "registry_permission_denied")
    finally:
        public_parent.chmod(0o700)


def test_neg_a3_reg_014_external_sqlite_writer_lock_maps_to_busy_and_rolls_back(tmp_path: Path) -> None:
    path = tmp_path / "busy.sqlite"
    registry = SQLiteScanRunRegistry(path, busy_timeout_ms=50)
    run = _run(1)
    registry.create(run)
    lock = sqlite3.connect(path, timeout=0, isolation_level=None)
    try:
        lock.execute("BEGIN IMMEDIATE")
        _expect_error(lambda: registry.replace(_changed(run, status="running", stage="scan", progress=1, started_at=run.created_at), expected_revision=1), "registry_busy")
    finally:
        lock.execute("ROLLBACK")
        lock.close()
    try:
        assert registry.get(run.id).revision == 1
    finally:
        registry.close()


def test_neg_a3_reg_015_close_during_activity_is_busy_then_closed_is_terminal(tmp_path: Path) -> None:
    path = tmp_path / "close-activity.sqlite"
    registry = SQLiteScanRunRegistry(path, busy_timeout_ms=100)
    run = _run(1)
    registry.create(run)
    lock = sqlite3.connect(path, timeout=0, isolation_level=None)
    lock.execute("BEGIN IMMEDIATE")
    started = threading.Event()
    finished = threading.Event()
    worker_errors: list[str] = []

    def blocked_write() -> None:
        started.set()
        try:
            registry.replace(
                _changed(run, status="running", stage="scan", progress=1, started_at=run.created_at),
                expected_revision=1,
            )
        except ScanRegistryError as error:
            worker_errors.append(error.code)
        finally:
            finished.set()

    thread = threading.Thread(target=blocked_write)
    thread.start()
    assert started.wait(timeout=1)
    deadline = time.monotonic() + 1
    while getattr(registry, "_active", 0) == 0 and time.monotonic() < deadline:
        time.sleep(0.005)
    assert getattr(registry, "_active", 0) > 0
    _expect_error(registry.close, "registry_busy")
    assert not registry._closed
    assert finished.wait(timeout=2)
    thread.join(timeout=1)
    assert worker_errors == ["registry_busy"]
    lock.execute("ROLLBACK")
    lock.close()
    assert registry.get(run.id).revision == 1
    registry.close()
    registry.close()
    _expect_error(lambda: registry.get(run.id), "registry_closed")


def test_neg_a3_reg_016_low_level_sqlite_failure_is_fixed_and_sanitized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "sanitized.sqlite"
    registry = SQLiteScanRunRegistry(path)
    run = _run(1, idempotency_key="sensitive-request-key")
    registry.create(run, idempotency_fingerprint="a" * 64)
    secret_path = str(path)
    secret_sql = "SELECT run_json FROM scan_runs"

    def poisoned_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        raise sqlite3.OperationalError(
            f"disk I/O failure path={secret_path} sql={secret_sql} key={run.idempotency_key} fingerprint={'a' * 64} source=/private/tmp/secret-source"
        )

    monkeypatch.setattr(sqlite3, "connect", poisoned_connect)
    try:
        _expect_error(
            lambda: registry.get(run.id),
            "registry_io_failed",
            forbidden=(secret_path, secret_sql, run.idempotency_key or "", "a" * 64, "/private/tmp/secret-source"),
        )
    finally:
        monkeypatch.undo()
    try:
        assert registry.get(run.id).revision == 1
    finally:
        registry.close()
