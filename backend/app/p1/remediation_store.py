"""Bounded workflow sidecar; formal assessments and scan facts are never written.

Initialization is explicit. Reads open an existing database in SQLite read-only
mode; version snapshots are append-only and mutations serialize with CAS.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
from urllib.parse import quote

from .models import P1RemediationTask


class RemediationStoreError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


# Kept explicit so callers need no knowledge of sqlite exceptions.
RemediationTaskStoreError = RemediationStoreError

# Fixed row shapes consumed by the two binding decoders below.
_TASK_COLUMNS = "task_id,scan_id,assessment_id,origin_key,created_at,version,payload,payload_hash"
_VERSION_COLUMNS = "v.task_id,v.version,t.scan_id,t.assessment_id,v.payload,v.payload_hash"


def _bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class RemediationTaskStore:
    def __init__(self, path: str | Path, *, max_record_bytes: int = 8 * 1024 * 1024,
                 max_database_bytes: int = 128 * 1024 * 1024,
                 min_free_bytes: int = 512 * 1024 * 1024):
        self.path = Path(path).absolute()
        self.max_record_bytes = max_record_bytes
        self.max_database_bytes = max_database_bytes
        self.min_free_bytes = min_free_bytes
        if min(max_record_bytes, max_database_bytes) <= 0 or min_free_bytes < 0:
            raise ValueError("invalid remediation storage budget")

    def _guard(self, *, create: bool = False) -> bool:
        if self.path.name != "remediation.db":
            raise RemediationStoreError("storage_unavailable")
        # Reject ancestor links as well as a linked database or private directory.
        if any(p.is_symlink() for p in (self.path, *self.path.parents)):
            raise RemediationStoreError("storage_unavailable")
        parent = self.path.parent
        if create:
            parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not parent.exists():
            return False
        info = parent.stat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
            raise RemediationStoreError("storage_unavailable")
        for path in (self.path, *(Path(str(self.path) + suffix) for suffix in ("-journal", "-wal", "-shm"))):
            if path.is_symlink():
                raise RemediationStoreError("storage_unavailable")
            if path.exists():
                info = path.stat()
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077:
                    raise RemediationStoreError("storage_unavailable")
        return self.path.exists()

    @staticmethod
    def _error(error: Exception) -> RemediationStoreError:
        capacity = isinstance(error, sqlite3.Error) and getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_FULL
        return RemediationStoreError("storage_capacity_exceeded" if capacity else "storage_unavailable")

    def _connect(self, *, readonly: bool = False):
        if not self._guard():
            if readonly:
                return None
            raise RemediationStoreError("storage_unavailable")
        mode = "ro" if readonly else "rw"
        db = sqlite3.connect(f"file:{quote(str(self.path), safe='/')}?mode={mode}", uri=True, timeout=1)
        try:
            if readonly:
                db.execute("PRAGMA query_only=ON")
            else:
                db.execute("PRAGMA journal_mode=DELETE")
                db.execute("PRAGMA synchronous=FULL")
                page_size = db.execute("PRAGMA page_size").fetchone()[0]
                db.execute(f"PRAGMA max_page_count={max(1, self.max_database_bytes // page_size)}")
            return db
        except Exception:
            db.close()
            raise

    def initialize(self) -> None:
        try:
            if not self._guard(create=True):
                if self.max_database_bytes < 65536 or shutil.disk_usage(self.path.parent).free < self.min_free_bytes + 65536:
                    raise RemediationStoreError("storage_capacity_exceeded")
                try:
                    fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
                    os.close(fd)
                except FileExistsError:
                    self._guard()
            with closing(self._connect()) as db, db:
                db.executescript('''
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY, scan_id TEXT NOT NULL,
                    assessment_id TEXT NOT NULL, origin_key TEXT NOT NULL,
                    created_at TEXT NOT NULL, version INTEGER NOT NULL,
                    payload BLOB NOT NULL, payload_hash TEXT NOT NULL,
                    UNIQUE(scan_id, assessment_id, origin_key));
                CREATE INDEX IF NOT EXISTS task_page ON tasks(scan_id, assessment_id, created_at, task_id);
                CREATE TABLE IF NOT EXISTS task_versions (
                    task_id TEXT NOT NULL, version INTEGER NOT NULL,
                    payload BLOB NOT NULL, payload_hash TEXT NOT NULL,
                    PRIMARY KEY(task_id, version));
                CREATE TABLE IF NOT EXISTS derive_requests (
                    scan_id TEXT NOT NULL, assessment_id TEXT NOT NULL,
                    request_key TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    task_ids BLOB NOT NULL, task_ids_hash TEXT NOT NULL,
                    PRIMARY KEY(scan_id, assessment_id, request_key));
                COMMIT;
                ''')
        except (OSError, sqlite3.Error) as error:
            raise self._error(error) from error

    @staticmethod
    def _validate(task: dict) -> None:
        try:
            P1RemediationTask.model_validate(task)
            note = task["note"]
            if (not isinstance(note, str) or len(note) > 2000
                    or task["status"] not in {"todo", "in_progress", "done", "dismissed"}
                    or (task["status"] in {"done", "dismissed"} and not note.strip())
                    or type(task["version"]) is not int or task["version"] < 1
                    or not task["task_id"].startswith("tsk_")
                    or task["scan_id"] != task["assessment_ref"]["scan_id"]
                    or task["assessment_ref"]["formal"] is not True):
                raise ValueError("invalid task")
        except (KeyError, TypeError, AttributeError, ValueError) as error:
            raise RemediationStoreError("invalid_argument") from error

    def _decode(self, row) -> dict:
        try:
            payload, expected = row
            if len(payload) > self.max_record_bytes or _digest(payload) != expected:
                raise ValueError("payload integrity")
            task = json.loads(payload)
            self._validate(task)
            return task
        except (ValueError, TypeError, RemediationStoreError) as error:
            raise RemediationStoreError("storage_unavailable") from error

    def _decode_task_row(self, row) -> dict:
        """Bind _TASK_COLUMNS metadata to the hash-checked current payload."""
        task_id, scan_id, assessment_id, origin_key, created_at, version, payload, sha = row
        task = self._decode((payload, sha))
        expected_origin = _digest(_bytes([task["assessment_ref"]["version"], task["origin"]]))
        if (task_id, scan_id, assessment_id, origin_key, created_at, version) != (
                task["task_id"], task["scan_id"], task["assessment_ref"]["assessment_id"],
                expected_origin, task["created_at"], task["version"]):
            raise RemediationStoreError("storage_unavailable")
        return task

    def _decode_task_version_row(self, row) -> dict:
        """Bind _VERSION_COLUMNS to snapshot identity and the parent SQL scope.

        Historical version is compared to v.version, never the current version;
        current payload is neither loaded nor required for fixed-version reads.
        """
        task_id, version, scan_id, assessment_id, payload, sha = row
        task = self._decode((payload, sha))
        if (task_id, version, scan_id, assessment_id) != (
                task["task_id"], task["version"], task["scan_id"],
                task["assessment_ref"]["assessment_id"]):
            raise RemediationStoreError("storage_unavailable")
        return task

    def _capacity(self, db, size: int) -> None:
        page_size = db.execute("PRAGMA page_size").fetchone()[0]
        used = db.execute("PRAGMA page_count").fetchone()[0] * page_size
        if used + size + 16384 > self.max_database_bytes or shutil.disk_usage(self.path.parent).free < self.min_free_bytes + size + 16384:
            raise RemediationStoreError("storage_capacity_exceeded")

    def _payload(self, task: dict) -> bytes:
        self._validate(task)
        try:
            payload = _bytes(task)
        except (ValueError, TypeError) as error:
            raise RemediationStoreError("invalid_argument") from error
        if len(payload) > self.max_record_bytes:
            raise RemediationStoreError("storage_capacity_exceeded")
        return payload

    def _read(self, query: str, args: tuple, *, version_rows: bool = False) -> list[dict]:
        try:
            db = self._connect(readonly=True)
            if db is None:
                return []
            with closing(db):
                decode = self._decode_task_version_row if version_rows else self._decode_task_row
                return [decode(row) for row in db.execute(query, args)]
        except (OSError, sqlite3.Error) as error:
            raise self._error(error) from error

    def request_fingerprint(self, scan_id: str, assessment_id: str,
                            idempotency_key: str) -> str | None:
        """Inspect a scoped request without creating storage or writing an alias."""
        try:
            db = self._connect(readonly=True)
            if db is None:
                return None
            with closing(db):
                row = db.execute(
                    "SELECT fingerprint FROM derive_requests WHERE scan_id=? AND assessment_id=? AND request_key=?",
                    (scan_id, assessment_id, idempotency_key)).fetchone()
                return row[0] if row else None
        except (OSError, sqlite3.Error) as error:
            raise self._error(error) from error

    def get(self, scan_id: str, assessment_id: str, task_id: str) -> dict | None:
        rows = self._read(f"SELECT {_TASK_COLUMNS} FROM tasks WHERE scan_id=? AND assessment_id=? AND task_id=?", (scan_id, assessment_id, task_id))
        return rows[0] if rows else None

    def get_version(self, scan_id: str, assessment_id: str, task_id: str,
                    version: int) -> dict | None:
        """Read exactly one scoped audit snapshot, without loading all history."""
        if type(version) is not int or version < 1:
            raise RemediationStoreError("invalid_argument")
        rows = self._read(
            f"SELECT {_VERSION_COLUMNS} FROM task_versions v JOIN tasks t "
            "ON t.task_id=v.task_id WHERE t.scan_id=? AND t.assessment_id=? "
            "AND v.task_id=? AND v.version=?",
            (scan_id, assessment_id, task_id, version), version_rows=True)
        return rows[0] if rows else None

    def page(self, scan_id: str, assessment_id: str, *, limit: int = 20,
             after: tuple[str, str] | None = None) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 100 or (after is not None and (not isinstance(after, tuple) or len(after) != 2 or not all(isinstance(x, str) for x in after))):
            raise RemediationStoreError("invalid_argument")
        condition = " AND (created_at,task_id) > (?,?)" if after is not None else ""
        return self._read(f"SELECT {_TASK_COLUMNS} FROM tasks WHERE scan_id=? AND assessment_id=?" + condition + " ORDER BY created_at,task_id LIMIT ?", (scan_id, assessment_id, *(after or ()), limit + 1))

    def history(self, task_id: str) -> list[dict]:
        """Internal audit inspection; deliberately not exposed as an HTTP API."""
        return self._read(f"SELECT {_VERSION_COLUMNS} FROM task_versions v LEFT JOIN tasks t "
                          "ON t.task_id=v.task_id WHERE v.task_id=? ORDER BY v.version",
                          (task_id,), version_rows=True)

    def derive(self, scan_id: str, assessment_id: str, idempotency_key: str,
               fingerprint: str, tasks: list[dict]) -> list[dict]:
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 200 or not idempotency_key.strip() or not isinstance(fingerprint, str) or not 1 <= len(fingerprint) <= 256:
            raise RemediationStoreError("invalid_argument")
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                request = db.execute("SELECT fingerprint,task_ids,task_ids_hash FROM derive_requests WHERE scan_id=? AND assessment_id=? AND request_key=?", (scan_id, assessment_id, idempotency_key)).fetchone()
                if request:
                    if request[0] != fingerprint:
                        raise RemediationStoreError("idempotency_conflict")
                    if _digest(request[1]) != request[2]:
                        raise RemediationStoreError("storage_unavailable")
                    try:
                        ids = json.loads(request[1])
                        if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
                            raise ValueError("invalid task manifest")
                    except (ValueError, TypeError) as error:
                        raise RemediationStoreError("storage_unavailable") from error
                    saved = []
                    for task_id in ids:
                        row = db.execute(f"SELECT {_TASK_COLUMNS} FROM tasks WHERE scan_id=? AND assessment_id=? AND task_id=?", (scan_id, assessment_id, task_id)).fetchone()
                        if row is None:
                            raise RemediationStoreError("storage_unavailable")
                        saved.append(self._decode_task_row(row))
                    return saved
                saved, seen = [], set()
                for task in tasks:
                    payload = self._payload(task)
                    if task["scan_id"] != scan_id or task["assessment_ref"]["assessment_id"] != assessment_id or task["version"] != 1 or task["status"] != "todo":
                        raise RemediationStoreError("invalid_argument")
                    origin_key = _digest(_bytes([task["assessment_ref"]["version"], task["origin"]]))
                    row = db.execute(f"SELECT {_TASK_COLUMNS} FROM tasks WHERE scan_id=? AND assessment_id=? AND origin_key=?", (scan_id, assessment_id, origin_key)).fetchone()
                    if row:
                        stored = self._decode_task_row(row)
                        if stored["task_id"] != task["task_id"]:
                            raise RemediationStoreError("invalid_argument")
                    else:
                        self._capacity(db, 2 * len(payload))
                        digest = _digest(payload)
                        db.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?)", (task["task_id"], scan_id, assessment_id, origin_key, task["created_at"], 1, payload, digest))
                        db.execute("INSERT INTO task_versions VALUES (?,?,?,?)", (task["task_id"], 1, payload, digest))
                        stored = json.loads(payload)
                    if stored["task_id"] not in seen:
                        saved.append(stored)
                        seen.add(stored["task_id"])
                ids = _bytes([task["task_id"] for task in saved])
                if len(ids) > self.max_record_bytes:
                    raise RemediationStoreError("storage_capacity_exceeded")
                self._capacity(db, len(ids) + len(idempotency_key.encode()) + len(fingerprint.encode()))
                db.execute("INSERT INTO derive_requests VALUES (?,?,?,?,?,?)", (scan_id, assessment_id, idempotency_key, fingerprint, ids, _digest(ids)))
                return saved
        except (OSError, sqlite3.Error) as error:
            raise self._error(error) from error

    def patch(self, scan_id: str, assessment_id: str, task_id: str,
              expected_version: int, changes: dict) -> dict:
        if type(expected_version) is not int or expected_version < 1 or not isinstance(changes, dict) or not changes or set(changes) - {"status", "note"}:
            raise RemediationStoreError("invalid_argument")
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(f"SELECT {_TASK_COLUMNS} FROM tasks WHERE scan_id=? AND assessment_id=? AND task_id=?", (scan_id, assessment_id, task_id)).fetchone()
                if row is None:
                    raise RemediationStoreError("not_found")
                task = self._decode_task_row(row)
                if task["version"] != expected_version:
                    raise RemediationStoreError("stale_version")
                task.update(changes)
                task["version"] += 1
                task["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                payload = self._payload(task)
                self._capacity(db, 2 * len(payload))
                digest = _digest(payload)
                changed = db.execute("UPDATE tasks SET version=?,payload=?,payload_hash=? WHERE task_id=? AND version=?", (task["version"], payload, digest, task_id, expected_version)).rowcount
                if changed != 1:
                    raise RemediationStoreError("storage_unavailable")
                db.execute("INSERT INTO task_versions VALUES (?,?,?,?)", (task_id, task["version"], payload, digest))
                return task
        except (OSError, sqlite3.Error) as error:
            raise self._error(error) from error
