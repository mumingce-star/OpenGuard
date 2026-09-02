"""SQLite-backed, durable P0 ``ScanRun`` snapshots.

This module deliberately exposes no HTTP, worker, or scanner integration.  It
stores only fully validated P0 snapshots and translates all storage failures
into the frozen, non-sensitive internal error vocabulary.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from app.domain.models import ScanRun, ScanStage, ScanStatus


REGISTRY_STORAGE_SCHEMA = "openguard.scan-run-registry"
REGISTRY_STORAGE_VERSION = 1

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SCAN_ID = re.compile(r"^scn_(?:[0-9a-hjkmnp-tv-z]{26}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")
_STAGES = tuple(ScanStage)
_STAGE_INDEX = {stage: index for index, stage in enumerate(_STAGES)}
_TERMINAL = frozenset({ScanStatus.COMPLETED, ScanStatus.PARTIAL, ScanStatus.FAILED, ScanStatus.CANCELLED})
_ALLOWED = {
    ScanStatus.QUEUED: frozenset({ScanStatus.RUNNING, ScanStatus.CANCELLED}),
    ScanStatus.RUNNING: frozenset({ScanStatus.RUNNING, ScanStatus.COMPLETED, ScanStatus.PARTIAL, ScanStatus.FAILED, ScanStatus.CANCELLED}),
    ScanStatus.COMPLETED: frozenset(),
    ScanStatus.PARTIAL: frozenset(),
    ScanStatus.FAILED: frozenset(),
    ScanStatus.CANCELLED: frozenset(),
}
_METADATA_COLUMNS = (
    (0, "schema_name", "TEXT", 1, None, 0),
    (1, "schema_version", "INTEGER", 1, None, 0),
)
_RUN_COLUMNS = (
    (0, "scan_id", "TEXT", 0, None, 1),
    (1, "revision", "INTEGER", 1, None, 0),
    (2, "idempotency_key", "TEXT", 0, None, 0),
    (3, "idempotency_fingerprint", "TEXT", 0, None, 0),
    (4, "created_at", "TEXT", 1, None, 0),
    (5, "status", "TEXT", 1, None, 0),
    (6, "contract_version", "TEXT", 1, None, 0),
    (7, "run_json", "BLOB", 1, None, 0),
)
_RUN_TABLE_SQL = "CREATETABLESCAN_RUNS(SCAN_IDTEXTPRIMARYKEY,REVISIONINTEGERNOTNULLCHECK(REVISION>=1),IDEMPOTENCY_KEYTEXTUNIQUENULL,IDEMPOTENCY_FINGERPRINTTEXTNULL,CREATED_ATTEXTNOTNULL,STATUSTEXTNOTNULL,CONTRACT_VERSIONTEXTNOTNULL,RUN_JSONBLOBNOTNULL)"


@dataclass(frozen=True)
class StoredScanRun:
    run: ScanRun
    revision: int


@dataclass(frozen=True)
class ScanRunPage:
    items: tuple[StoredScanRun, ...]
    next_after_scan_id: str | None


class ScanRegistryError(RuntimeError):
    """Stable, deliberately context-free registry failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise ScanRegistryError(code) from None


def _reject_constant(_: str) -> None:
    raise ValueError("non-finite number")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _canonical(run: ScanRun) -> tuple[ScanRun, bytes, dict[str, Any]]:
    if type(run) is not ScanRun:
        _fail("registry_invalid_argument")
    try:
        payload = run.model_dump(mode="json")
        validated = ScanRun.model_validate(payload)
        canonical_payload = validated.model_dump(mode="json")
        data = json.dumps(canonical_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except Exception:
        _fail("registry_invalid_argument")
    return validated, data, canonical_payload


def _validate_scan_id(value: object) -> str:
    if type(value) is not str or not _SCAN_ID.fullmatch(value):
        _fail("registry_invalid_argument")
    return value


def _validate_fingerprint(value: object) -> str:
    if type(value) is not str or not _SHA256.fullmatch(value):
        _fail("registry_invalid_argument")
    return value


class SQLiteScanRunRegistry:
    """A small SQLite registry with durable idempotency and CAS semantics."""

    def __init__(self, database_path: Path, *, busy_timeout_ms: int = 5_000) -> None:
        self._state_lock = threading.Lock()
        self._active = 0
        self._closed = False
        self._busy_timeout_ms = self._validate_busy_timeout(busy_timeout_ms)
        self._database_path = self._validate_database_path(database_path)
        try:
            self._initialize_or_verify()
        except ScanRegistryError:
            raise
        except Exception:
            _fail("registry_io_failed")

    @staticmethod
    def _validate_busy_timeout(value: object) -> int:
        if type(value) is not int or not 1 <= value <= 30_000:
            _fail("registry_invalid_argument")
        return value

    @staticmethod
    def _private_stat(path: Path, *, directory: bool) -> os.stat_result:
        try:
            info = path.lstat()
        except FileNotFoundError:
            _fail("registry_path_invalid")
        except PermissionError:
            _fail("registry_permission_denied")
        except OSError:
            _fail("registry_path_invalid")
        if stat.S_ISLNK(info.st_mode) or (directory and not stat.S_ISDIR(info.st_mode)) or (not directory and not stat.S_ISREG(info.st_mode)):
            _fail("registry_path_invalid")
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            _fail("registry_permission_denied")
        return info

    def _validate_database_path(self, value: object) -> Path:
        if not isinstance(value, Path):
            _fail("registry_invalid_argument")
        rendered = os.fspath(value)
        if not rendered or "\x00" in rendered or rendered == ":memory:" or rendered.startswith("file:"):
            _fail("registry_path_invalid")
        path = Path(rendered)
        parent = path.parent
        parent_info = self._private_stat(parent, directory=True)
        if not parent_info.st_mode & stat.S_IRUSR or not parent_info.st_mode & stat.S_IWUSR or not parent_info.st_mode & stat.S_IXUSR:
            _fail("registry_permission_denied")
        try:
            existing = path.lstat()
        except FileNotFoundError:
            try:
                descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
                os.close(descriptor)
            except FileExistsError:
                return self._validate_database_path(path)
            except PermissionError:
                _fail("registry_permission_denied")
            except OSError:
                _fail("registry_path_invalid")
        except PermissionError:
            _fail("registry_permission_denied")
        except OSError:
            _fail("registry_path_invalid")
        else:
            if stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode):
                _fail("registry_path_invalid")
            if existing.st_uid != os.geteuid() or existing.st_mode & 0o077:
                _fail("registry_permission_denied")
        return path

    @contextmanager
    def _activity(self) -> Iterator[None]:
        with self._state_lock:
            if self._closed:
                _fail("registry_closed")
            self._active += 1
        try:
            yield
        finally:
            with self._state_lock:
                self._active -= 1

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(os.fspath(self._database_path), timeout=self._busy_timeout_ms / 1000, isolation_level=None, uri=False)
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
            return connection
        except sqlite3.OperationalError as error:
            self._sqlite_failure(error)
        except (sqlite3.Error, OSError):
            _fail("registry_io_failed")
        raise AssertionError("unreachable")

    @staticmethod
    def _sqlite_failure(error: sqlite3.Error) -> None:
        text = str(error).lower()
        if "locked" in text or "busy" in text:
            _fail("registry_busy")
        if "malformed" in text or "corrupt" in text or "not a database" in text:
            _fail("registry_corrupt")
        _fail("registry_io_failed")

    def _initialize_or_verify(self) -> None:
        try:
            is_empty = self._database_path.stat().st_size == 0
        except OSError:
            _fail("registry_io_failed")
        connection = self._connect()
        try:
            if is_empty:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("CREATE TABLE registry_metadata (schema_name TEXT NOT NULL, schema_version INTEGER NOT NULL)")
                connection.execute("CREATE TABLE scan_runs (scan_id TEXT PRIMARY KEY, revision INTEGER NOT NULL CHECK (revision >= 1), idempotency_key TEXT UNIQUE NULL, idempotency_fingerprint TEXT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL, contract_version TEXT NOT NULL, run_json BLOB NOT NULL)")
                connection.execute("INSERT INTO registry_metadata (schema_name, schema_version) VALUES (?, ?)", (REGISTRY_STORAGE_SCHEMA, REGISTRY_STORAGE_VERSION))
                connection.execute("PRAGMA user_version = 1")
                connection.execute("COMMIT")
            self._verify_schema(connection)
        except ScanRegistryError:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        except sqlite3.OperationalError as error:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            self._sqlite_failure(error)
        except sqlite3.DatabaseError:
            _fail("registry_schema_unsupported")
        finally:
            connection.close()

    @staticmethod
    def _verify_schema(connection: sqlite3.Connection) -> None:
        try:
            version = connection.execute("PRAGMA user_version").fetchone()
            metadata = connection.execute("SELECT schema_name, schema_version FROM registry_metadata").fetchall()
            metadata_columns = tuple(connection.execute("PRAGMA table_info(registry_metadata)").fetchall())
            run_columns = tuple(connection.execute("PRAGMA table_info(scan_runs)").fetchall())
            indexes = tuple(connection.execute("PRAGMA index_list(scan_runs)").fetchall())
            table_sql = connection.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'scan_runs'").fetchone()
            objects = tuple(connection.execute("SELECT type, name, tbl_name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name").fetchall())
        except sqlite3.DatabaseError:
            _fail("registry_schema_unsupported")
        if (
            version != (REGISTRY_STORAGE_VERSION,)
            or metadata != [(REGISTRY_STORAGE_SCHEMA, REGISTRY_STORAGE_VERSION)]
            or metadata_columns != _METADATA_COLUMNS
            or run_columns != _RUN_COLUMNS
            or table_sql is None
            or type(table_sql[0]) is not str
            or re.sub(r"\s+", "", table_sql[0]).upper() != _RUN_TABLE_SQL
            or objects != (("table", "registry_metadata", "registry_metadata"), ("table", "scan_runs", "scan_runs"))
        ):
            _fail("registry_schema_unsupported")
        if len(indexes) != 2:
            _fail("registry_schema_unsupported")
        index_columns: set[tuple[str, ...]] = set()
        for index in indexes:
            if len(index) != 5 or index[2] != 1 or index[4] != 0 or index[3] not in {"pk", "u"} or type(index[1]) is not str:
                _fail("registry_schema_unsupported")
            escaped = index[1].replace('"', '""')
            try:
                columns = tuple(row[2] for row in connection.execute(f'PRAGMA index_info("{escaped}")').fetchall())
            except sqlite3.DatabaseError:
                _fail("registry_schema_unsupported")
            index_columns.add(columns)
        if index_columns != {("scan_id",), ("idempotency_key",)}:
            _fail("registry_schema_unsupported")

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        began = False
        try:
            self._verify_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            began = True
            yield connection
            connection.execute("COMMIT")
        except ScanRegistryError:
            if began:
                try:
                    connection.execute("ROLLBACK")
                except sqlite3.Error:
                    self._closed = True
                    _fail("registry_io_failed")
            raise
        except sqlite3.OperationalError as error:
            if began:
                try:
                    connection.execute("ROLLBACK")
                except sqlite3.Error:
                    self._closed = True
                    _fail("registry_io_failed")
            self._sqlite_failure(error)
        except sqlite3.DatabaseError:
            if began:
                try:
                    connection.execute("ROLLBACK")
                except sqlite3.Error:
                    self._closed = True
                    _fail("registry_io_failed")
            _fail("registry_corrupt")
        finally:
            connection.close()

    @staticmethod
    def _row_to_stored(row: tuple[Any, ...]) -> StoredScanRun:
        if len(row) != 8:
            _fail("registry_corrupt")
        scan_id, revision, key, fingerprint, created_at, status, contract_version, raw = row
        if type(scan_id) is not str or type(revision) is not int or type(created_at) is not str or type(status) is not str or type(contract_version) is not str or type(raw) is not bytes:
            _fail("registry_corrupt")
        if revision < 1 or (key is not None and type(key) is not str) or (fingerprint is not None and type(fingerprint) is not str):
            _fail("registry_corrupt")
        if contract_version != "0.1.1":
            _fail("registry_schema_unsupported")
        if key is None and fingerprint is not None:
            _fail("registry_corrupt")
        if key is not None and (not key or _SHA256.fullmatch(fingerprint or "") is None):
            _fail("registry_corrupt")
        try:
            payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_reject_constant)
            if type(payload) is not dict:
                raise ValueError("root")
            run = ScanRun.model_validate(payload)
            canonical = json.dumps(run.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        except Exception:
            _fail("registry_corrupt")
        if canonical != raw or run.id != scan_id or run.created_at.isoformat().replace("+00:00", "Z") != created_at or run.status.value != status or run.contract_version != contract_version or run.idempotency_key != key:
            _fail("registry_corrupt")
        return StoredScanRun(run=run, revision=revision)

    @staticmethod
    def _initial_valid(run: ScanRun) -> bool:
        return run.status is ScanStatus.QUEUED and run.stage is ScanStage.QUEUED and run.progress == 0 and run.started_at is None and run.finished_at is None

    @staticmethod
    def _transition_valid(old: ScanRun, new: ScanRun) -> bool:
        if new.status not in _ALLOWED[old.status] or old.id != new.id or old.idempotency_key != new.idempotency_key or old.created_at != new.created_at:
            return False
        if old.project.id != new.project.id or old.project.name != new.project.name or old.project.source_type != new.project.source_type or old.project.source != new.project.source or old.project.created_at != new.project.created_at:
            return False
        if old.project.revision is not None and new.project.revision != old.project.revision:
            return False
        if old.project.root_digest is not None and new.project.root_digest != old.project.root_digest:
            return False
        if old.project.revision is None and new.project.revision is not None and not new.project.revision:
            return False
        if old.progress > new.progress or _STAGE_INDEX[new.stage] < _STAGE_INDEX[old.stage]:
            return False
        if old.started_at is not None and new.started_at != old.started_at:
            return False
        if old.status is ScanStatus.QUEUED and new.status is ScanStatus.RUNNING:
            if new.started_at is None or new.started_at < new.created_at:
                return False
        if new.status is ScanStatus.RUNNING and new.stage not in _STAGES[1:-1]:
            return False
        if new.status in _TERMINAL:
            if new.finished_at is None or new.finished_at < (new.started_at or new.created_at):
                return False
        if new.status is ScanStatus.COMPLETED and (new.stage is not ScanStage.COMPLETED or new.progress != 100):
            return False
        if old.status is ScanStatus.QUEUED and new.status is ScanStatus.CANCELLED and (new.stage is not ScanStage.QUEUED or new.progress != 0 or new.started_at is not None):
            return False
        return True

    def create(self, run: ScanRun, *, idempotency_fingerprint: str | None = None) -> StoredScanRun:
        with self._activity():
            validated, canonical, payload = _canonical(run)
            if not self._initial_valid(validated):
                _fail("registry_invalid_argument")
            key = validated.idempotency_key
            if key is None:
                if idempotency_fingerprint is not None:
                    _fail("registry_invalid_argument")
            else:
                _validate_fingerprint(idempotency_fingerprint)
            with self._transaction() as connection:
                if key is not None:
                    existing = connection.execute("SELECT scan_id, revision, idempotency_key, idempotency_fingerprint, created_at, status, contract_version, run_json FROM scan_runs WHERE idempotency_key = ?", (key,)).fetchone()
                    if existing is not None:
                        stored = self._row_to_stored(existing)
                        if existing[3] == idempotency_fingerprint:
                            return stored
                        _fail("registry_idempotency_conflict")
                duplicate = connection.execute("SELECT scan_id FROM scan_runs WHERE scan_id = ?", (validated.id,)).fetchone()
                if duplicate is not None:
                    _fail("registry_already_exists")
                connection.execute("INSERT INTO scan_runs (scan_id, revision, idempotency_key, idempotency_fingerprint, created_at, status, contract_version, run_json) VALUES (?, 1, ?, ?, ?, ?, ?, ?)", (validated.id, key, idempotency_fingerprint, payload["created_at"], payload["status"], payload["contract_version"], canonical))
                return StoredScanRun(validated, 1)

    def get(self, scan_id: str) -> StoredScanRun:
        with self._activity():
            valid_id = _validate_scan_id(scan_id)
            connection = self._connect()
            try:
                self._verify_schema(connection)
                row = connection.execute("SELECT scan_id, revision, idempotency_key, idempotency_fingerprint, created_at, status, contract_version, run_json FROM scan_runs WHERE scan_id = ?", (valid_id,)).fetchone()
                if row is None:
                    _fail("registry_not_found")
                return self._row_to_stored(row)
            except ScanRegistryError:
                raise
            except sqlite3.OperationalError as error:
                self._sqlite_failure(error)
            except sqlite3.DatabaseError:
                _fail("registry_corrupt")
            finally:
                connection.close()
        raise AssertionError("unreachable")

    def replace(self, run: ScanRun, *, expected_revision: int) -> StoredScanRun:
        with self._activity():
            if type(expected_revision) is not int or expected_revision < 1:
                _fail("registry_invalid_argument")
            validated, canonical, payload = _canonical(run)
            with self._transaction() as connection:
                row = connection.execute("SELECT scan_id, revision, idempotency_key, idempotency_fingerprint, created_at, status, contract_version, run_json FROM scan_runs WHERE scan_id = ?", (validated.id,)).fetchone()
                if row is None:
                    _fail("registry_not_found")
                stored = self._row_to_stored(row)
                if stored.revision != expected_revision:
                    _fail("registry_revision_conflict")
                if canonical == row[7]:
                    return stored
                if not self._transition_valid(stored.run, validated):
                    _fail("registry_transition_invalid")
                cursor = connection.execute("UPDATE scan_runs SET revision = ?, created_at = ?, status = ?, contract_version = ?, run_json = ? WHERE scan_id = ? AND revision = ?", (stored.revision + 1, payload["created_at"], payload["status"], payload["contract_version"], canonical, validated.id, stored.revision))
                if cursor.rowcount != 1:
                    _fail("registry_revision_conflict")
                return StoredScanRun(validated, stored.revision + 1)

    def list_runs(self, *, limit: int = 100, after_scan_id: str | None = None) -> ScanRunPage:
        with self._activity():
            if type(limit) is not int or not 1 <= limit <= 100 or (after_scan_id is not None and type(after_scan_id) is not str):
                _fail("registry_invalid_argument")
            connection = self._connect()
            try:
                self._verify_schema(connection)
                parameters: tuple[Any, ...]
                if after_scan_id is None:
                    query = "SELECT scan_id, revision, idempotency_key, idempotency_fingerprint, created_at, status, contract_version, run_json FROM scan_runs ORDER BY created_at DESC, scan_id ASC LIMIT ?"
                    parameters = (limit + 1,)
                else:
                    anchor_id = _validate_scan_id(after_scan_id)
                    anchor = connection.execute("SELECT scan_id, revision, idempotency_key, idempotency_fingerprint, created_at, status, contract_version, run_json FROM scan_runs WHERE scan_id = ?", (anchor_id,)).fetchone()
                    if anchor is None:
                        _fail("registry_not_found")
                    anchor_stored = self._row_to_stored(anchor)
                    created = anchor_stored.run.created_at.isoformat().replace("+00:00", "Z")
                    query = "SELECT scan_id, revision, idempotency_key, idempotency_fingerprint, created_at, status, contract_version, run_json FROM scan_runs WHERE created_at < ? OR (created_at = ? AND scan_id > ?) ORDER BY created_at DESC, scan_id ASC LIMIT ?"
                    parameters = (created, created, anchor_id, limit + 1)
                rows = connection.execute(query, parameters).fetchall()
                items = tuple(self._row_to_stored(row) for row in rows[:limit])
                return ScanRunPage(items=items, next_after_scan_id=items[-1].run.id if len(rows) > limit else None)
            except ScanRegistryError:
                raise
            except sqlite3.OperationalError as error:
                self._sqlite_failure(error)
            except sqlite3.DatabaseError:
                _fail("registry_corrupt")
            finally:
                connection.close()
        raise AssertionError("unreachable")

    def close(self) -> None:
        with self._state_lock:
            if self._closed:
                return
            if self._active:
                _fail("registry_busy")
            self._closed = True

    def __enter__(self) -> "SQLiteScanRunRegistry":
        with self._state_lock:
            if self._closed:
                _fail("registry_closed")
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
