"""Immutable Report V2 snapshot sidecar storage.

This store owns only Report V2 snapshots, idempotency records, and rendered
artifact bytes. Scan facts, Formal Assessments, Tasks, and Notices are read-only
inputs and are never mutated here.
"""

from __future__ import annotations

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
from urllib.parse import quote
from uuid import UUID

from .models import P1ReportV2Snapshot


class ReportV2StoreError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _bytes(value: object) -> bytes:
    """Canonical P1 JSON bytes."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _report_content_hash(snapshot: dict) -> str:
    """Calculate the immutable Report V2 snapshot semantic hash.

    Frozen Contract:
    - exclude the snapshot's own content_hash;
    - Report V2 additionally excludes artifacts to avoid circular hashing.
    """
    value = dict(snapshot)
    value.pop("content_hash", None)
    value.pop("artifacts", None)
    return _digest(_bytes(value))


class ReportV2Store:
    def __init__(
        self,
        path: str | Path,
        *,
        max_snapshot_bytes: int = 16 * 1024 * 1024,
        max_artifact_bytes: int = 32 * 1024 * 1024,
        max_database_bytes: int = 256 * 1024 * 1024,
        min_free_bytes: int = 512 * 1024 * 1024,
    ):
        self.path = Path(path).absolute()
        self.max_snapshot_bytes = max_snapshot_bytes
        self.max_artifact_bytes = max_artifact_bytes
        self.max_database_bytes = max_database_bytes
        self.min_free_bytes = min_free_bytes

        if (
            min(
                max_snapshot_bytes,
                max_artifact_bytes,
                max_database_bytes,
            )
            <= 0
            or min_free_bytes < 0
        ):
            raise ValueError("invalid report storage budget")

    def _guard(self, *, create: bool = False) -> bool:
        if self.path.name != "report_v2.db":
            raise ReportV2StoreError("storage_unavailable")

        # Reject the DB path and ancestor symlinks.
        if any(
            path.is_symlink()
            for path in (self.path, *self.path.parents)
        ):
            raise ReportV2StoreError("storage_unavailable")

        parent = self.path.parent

        if create:
            parent.mkdir(
                mode=0o700,
                parents=True,
                exist_ok=True,
            )

        if not parent.exists():
            return False

        parent_info = parent.stat()

        if (
            not stat.S_ISDIR(parent_info.st_mode)
            or stat.S_IMODE(parent_info.st_mode) & 0o077
        ):
            raise ReportV2StoreError("storage_unavailable")

        related_paths = (
            self.path,
            Path(str(self.path) + "-journal"),
            Path(str(self.path) + "-wal"),
            Path(str(self.path) + "-shm"),
        )

        for path in related_paths:
            if path.is_symlink():
                raise ReportV2StoreError("storage_unavailable")

            if path.exists():
                info = path.stat()

                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_nlink != 1
                    or stat.S_IMODE(info.st_mode) & 0o077
                ):
                    raise ReportV2StoreError(
                        "storage_unavailable"
                    )

        return self.path.exists()

    @staticmethod
    def _error(error: Exception) -> ReportV2StoreError:
        capacity = (
            isinstance(error, sqlite3.Error)
            and getattr(
                error,
                "sqlite_errorcode",
                None,
            )
            == sqlite3.SQLITE_FULL
        )

        return ReportV2StoreError(
            "storage_capacity_exceeded"
            if capacity
            else "storage_unavailable"
        )

    def _connect(self, *, readonly: bool = False):
        if not self._guard():
            if readonly:
                return None

            raise ReportV2StoreError(
                "storage_unavailable"
            )

        mode = "ro" if readonly else "rw"

        db = sqlite3.connect(
            (
                f"file:"
                f"{quote(str(self.path), safe='/')}"
                f"?mode={mode}"
            ),
            uri=True,
            timeout=1,
        )

        try:
            if readonly:
                db.execute("PRAGMA query_only=ON")
            else:
                db.execute("PRAGMA journal_mode=DELETE")
                db.execute("PRAGMA synchronous=FULL")

                page_size = db.execute(
                    "PRAGMA page_size"
                ).fetchone()[0]

                db.execute(
                    "PRAGMA max_page_count="
                    f"{max(1, self.max_database_bytes // page_size)}"
                )

            return db

        except Exception:
            db.close()
            raise

    def initialize(self) -> None:
        """Explicitly initialize the Report V2 sidecar."""

        try:
            if not self._guard(create=True):
                required = 65536

                if (
                    self.max_database_bytes < required
                    or shutil.disk_usage(
                        self.path.parent
                    ).free
                    < self.min_free_bytes + required
                ):
                    raise ReportV2StoreError(
                        "storage_capacity_exceeded"
                    )

                try:
                    fd = os.open(
                        self.path,
                        os.O_WRONLY
                        | os.O_CREAT
                        | os.O_EXCL
                        | getattr(
                            os,
                            "O_NOFOLLOW",
                            0,
                        ),
                        0o600,
                    )
                    os.close(fd)

                except FileExistsError:
                    self._guard()

            with closing(self._connect()) as db, db:
                db.executescript(
                    """
                    BEGIN IMMEDIATE;

                    CREATE TABLE IF NOT EXISTS report_snapshots (
                        snapshot_id TEXT PRIMARY KEY,
                        scan_id TEXT NOT NULL,
                        assessment_id TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        payload BLOB NOT NULL,
                        payload_hash TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS report_scope
                    ON report_snapshots(
                        scan_id,
                        assessment_id,
                        created_at,
                        snapshot_id
                    );

                    CREATE TABLE IF NOT EXISTS report_artifacts (
                        snapshot_id TEXT NOT NULL,
                        format TEXT NOT NULL,
                        payload BLOB NOT NULL,
                        payload_hash TEXT NOT NULL,
                        size_bytes INTEGER NOT NULL,
                        PRIMARY KEY(
                            snapshot_id,
                            format
                        )
                    );

                    CREATE TABLE IF NOT EXISTS report_requests (
                        scan_id TEXT NOT NULL,
                        assessment_id TEXT NOT NULL,
                        request_key TEXT NOT NULL,
                        fingerprint TEXT NOT NULL,
                        snapshot_id TEXT NOT NULL,
                        PRIMARY KEY(
                            scan_id,
                            assessment_id,
                            request_key
                        )
                    );

                    COMMIT;
                    """
                )

        except ReportV2StoreError:
            raise

        except (OSError, sqlite3.Error) as error:
            raise self._error(error) from error

    @staticmethod
    def _validate_snapshot(
        snapshot: dict,
        scan_id: str,
        assessment_id: str,
    ) -> None:
        """Validate structural and cross-object snapshot invariants."""

        try:
            P1ReportV2Snapshot.model_validate(snapshot)

            snapshot_id = snapshot["snapshot_id"]

            if not snapshot_id.startswith("rptv2_"):
                raise ValueError(
                    "invalid snapshot id"
                )

            suffix = snapshot_id[len("rptv2_") :]

            if not suffix:
                raise ValueError(
                    "invalid snapshot id"
                )

            # Contract requires rptv2_ identifiers to use UUIDs.
            UUID(suffix)

            binding = snapshot["binding"]
            scan_ref = binding["scan_ref"]
            assessment_ref = binding[
                "assessment_ref"
            ]

            if scan_ref["scan_id"] != scan_id:
                raise ValueError(
                    "scan binding mismatch"
                )

            if (
                assessment_ref["assessment_id"]
                != assessment_id
            ):
                raise ValueError(
                    "assessment binding mismatch"
                )

            if (
                assessment_ref["scan_id"]
                != scan_id
            ):
                raise ValueError(
                    "assessment scan mismatch"
                )

            if (
                scan_ref["facts_hash"]
                != assessment_ref["facts_hash"]
            ):
                raise ValueError(
                    "facts hash mismatch"
                )

            if assessment_ref["formal"] is not True:
                raise ValueError(
                    "assessment must be formal"
                )

            if (
                snapshot["content_hash"]
                != _report_content_hash(snapshot)
            ):
                raise ValueError(
                    "report content hash mismatch"
                )

            artifact_formats = [
                artifact["format"]
                for artifact in snapshot["artifacts"]
            ]

            # Report V2 V1 requires one HTML and one JSON artifact.
            if sorted(artifact_formats) != [
                "html",
                "json",
            ]:
                raise ValueError(
                    "report requires exactly one "
                    "html and one json artifact"
                )

            task_refs = binding["task_refs"]

            if (
                len(
                    {
                        task["task_id"]
                        for task in task_refs
                    }
                )
                != len(task_refs)
            ):
                raise ValueError(
                    "duplicate task ref"
                )

            notice_refs = binding["notice_refs"]

            if (
                len(
                    {
                        notice["draft_id"]
                        for notice in notice_refs
                    }
                )
                != len(notice_refs)
            ):
                raise ValueError(
                    "duplicate notice ref"
                )

            algorithm_refs = binding[
                "algorithm_refs"
            ]

            if (
                len(
                    {
                        algorithm["kind"]
                        for algorithm
                        in algorithm_refs
                    }
                )
                != len(algorithm_refs)
            ):
                raise ValueError(
                    "duplicate algorithm ref"
                )

        except (
            KeyError,
            TypeError,
            AttributeError,
            ValueError,
        ) as error:
            raise ReportV2StoreError(
                "invalid_argument"
            ) from error

    def _snapshot_payload(
        self,
        snapshot: dict,
        scan_id: str,
        assessment_id: str,
    ) -> bytes:
        self._validate_snapshot(
            snapshot,
            scan_id,
            assessment_id,
        )

        try:
            payload = _bytes(snapshot)

        except (TypeError, ValueError) as error:
            raise ReportV2StoreError(
                "invalid_argument"
            ) from error

        if len(payload) > self.max_snapshot_bytes:
            raise ReportV2StoreError(
                "storage_capacity_exceeded"
            )

        return payload

    def _artifact_payloads(
        self,
        snapshot: dict,
        artifacts: dict[str, bytes],
    ) -> dict[str, bytes]:
        """Verify artifact bytes against immutable snapshot metadata."""

        if (
            not isinstance(artifacts, dict)
            or set(artifacts) != {"html", "json"}
        ):
            raise ReportV2StoreError(
                "invalid_argument"
            )

        metadata = {
            artifact["format"]: artifact
            for artifact in snapshot["artifacts"]
        }

        if set(metadata) != {"html", "json"}:
            raise ReportV2StoreError(
                "invalid_argument"
            )

        result: dict[str, bytes] = {}

        for format_name in ("html", "json"):
            payload = artifacts[format_name]

            if not isinstance(payload, bytes):
                raise ReportV2StoreError(
                    "invalid_argument"
                )

            # Contract examples may contain zero-byte placeholders,
            # but runtime downloadable product artifacts must be real.
            if not payload:
                raise ReportV2StoreError(
                    "invalid_argument"
                )

            if len(payload) > self.max_artifact_bytes:
                raise ReportV2StoreError(
                    "storage_capacity_exceeded"
                )

            artifact = metadata[format_name]

            if artifact["size_bytes"] != len(payload):
                raise ReportV2StoreError(
                    "invalid_argument"
                )

            if (
                artifact["content_hash"]
                != _digest(payload)
            ):
                raise ReportV2StoreError(
                    "invalid_argument"
                )

            result[format_name] = payload

        return result

    def _capacity(
        self,
        db,
        size: int,
    ) -> None:
        page_size = db.execute(
            "PRAGMA page_size"
        ).fetchone()[0]

        used = (
            db.execute(
                "PRAGMA page_count"
            ).fetchone()[0]
            * page_size
        )

        reserve = 16384

        if (
            used + size + reserve
            > self.max_database_bytes
            or shutil.disk_usage(
                self.path.parent
            ).free
            < self.min_free_bytes
            + size
            + reserve
        ):
            raise ReportV2StoreError(
                "storage_capacity_exceeded"
            )

    def _decode_snapshot(
        self,
        row,
    ) -> dict:
        try:
            payload, expected_hash = row

            if (
                len(payload)
                > self.max_snapshot_bytes
                or _digest(payload)
                != expected_hash
            ):
                raise ValueError(
                    "snapshot integrity"
                )

            snapshot = json.loads(payload)

            binding = snapshot["binding"]

            self._validate_snapshot(
                snapshot,
                binding["scan_ref"]["scan_id"],
                binding[
                    "assessment_ref"
                ]["assessment_id"],
            )

            return snapshot

        except (
            KeyError,
            ValueError,
            TypeError,
            ReportV2StoreError,
        ) as error:
            raise ReportV2StoreError(
                "storage_unavailable"
            ) from error

    def create(
        self,
        scan_id: str,
        assessment_id: str,
        idempotency_key: str,
        fingerprint: str,
        snapshot: dict,
        artifacts: dict[str, bytes],
    ) -> dict:
        """Atomically persist one immutable Report V2 snapshot.

        Same scoped idempotency key + same fingerprint:
            return the original stored snapshot.

        Same scoped idempotency key + different fingerprint:
            idempotency_conflict.

        Reusing an existing snapshot_id with a new request:
            conflict.
        """

        if (
            not isinstance(scan_id, str)
            or not scan_id
            or not isinstance(assessment_id, str)
            or not assessment_id
            or not isinstance(
                idempotency_key,
                str,
            )
            or not 1 <= len(idempotency_key) <= 200
            or not idempotency_key.strip()
            or not isinstance(fingerprint, str)
            or not 1 <= len(fingerprint) <= 256
        ):
            raise ReportV2StoreError(
                "invalid_argument"
            )

        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")

                request = db.execute(
                    """
                    SELECT
                        fingerprint,
                        snapshot_id
                    FROM report_requests
                    WHERE scan_id=?
                      AND assessment_id=?
                      AND request_key=?
                    """,
                    (
                        scan_id,
                        assessment_id,
                        idempotency_key,
                    ),
                ).fetchone()

                if request is not None:
                    (
                        stored_fingerprint,
                        stored_snapshot_id,
                    ) = request

                    if (
                        stored_fingerprint
                        != fingerprint
                    ):
                        raise ReportV2StoreError(
                            "idempotency_conflict"
                        )

                    row = db.execute(
                        """
                        SELECT
                            payload,
                            payload_hash
                        FROM report_snapshots
                        WHERE scan_id=?
                          AND assessment_id=?
                          AND snapshot_id=?
                        """,
                        (
                            scan_id,
                            assessment_id,
                            stored_snapshot_id,
                        ),
                    ).fetchone()

                    if row is None:
                        raise ReportV2StoreError(
                            "storage_unavailable"
                        )

                    artifact_rows = db.execute(
                        """
                        SELECT
                            format,
                            payload,
                            payload_hash,
                            size_bytes
                        FROM report_artifacts
                        WHERE snapshot_id=?
                        ORDER BY format
                        """,
                        (
                            stored_snapshot_id,
                        ),
                    ).fetchall()

                    if len(artifact_rows) != 2:
                        raise ReportV2StoreError(
                            "storage_unavailable"
                        )

                    formats = set()

                    for (
                        format_name,
                        artifact_payload,
                        artifact_hash,
                        size_bytes,
                    ) in artifact_rows:
                        if (
                            format_name
                            not in {"html", "json"}
                            or format_name
                            in formats
                            or len(artifact_payload)
                            != size_bytes
                            or len(artifact_payload)
                            > self.max_artifact_bytes
                            or _digest(
                                artifact_payload
                            )
                            != artifact_hash
                        ):
                            raise ReportV2StoreError(
                                "storage_unavailable"
                            )

                        formats.add(format_name)

                    if formats != {"html", "json"}:
                        raise ReportV2StoreError(
                            "storage_unavailable"
                        )

                    return self._decode_snapshot(
                        row
                    )

                snapshot_payload = (
                    self._snapshot_payload(
                        snapshot,
                        scan_id,
                        assessment_id,
                    )
                )

                artifact_payloads = (
                    self._artifact_payloads(
                        snapshot,
                        artifacts,
                    )
                )

                existing = db.execute(
                    """
                    SELECT 1
                    FROM report_snapshots
                    WHERE snapshot_id=?
                    """,
                    (
                        snapshot["snapshot_id"],
                    ),
                ).fetchone()

                if existing is not None:
                    raise ReportV2StoreError(
                        "conflict"
                    )

                total_size = (
                    len(snapshot_payload)
                    + sum(
                        len(payload)
                        for payload
                        in artifact_payloads.values()
                    )
                    + len(
                        idempotency_key.encode(
                            "utf-8"
                        )
                    )
                    + len(
                        fingerprint.encode(
                            "utf-8"
                        )
                    )
                )

                self._capacity(
                    db,
                    total_size,
                )

                snapshot_payload_hash = (
                    _digest(snapshot_payload)
                )

                db.execute(
                    """
                    INSERT INTO report_snapshots(
                        snapshot_id,
                        scan_id,
                        assessment_id,
                        created_at,
                        payload,
                        payload_hash
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot["snapshot_id"],
                        scan_id,
                        assessment_id,
                        snapshot["created_at"],
                        snapshot_payload,
                        snapshot_payload_hash,
                    ),
                )

                for format_name in (
                    "html",
                    "json",
                ):
                    payload = artifact_payloads[
                        format_name
                    ]

                    db.execute(
                        """
                        INSERT INTO report_artifacts(
                            snapshot_id,
                            format,
                            payload,
                            payload_hash,
                            size_bytes
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            snapshot["snapshot_id"],
                            format_name,
                            payload,
                            _digest(payload),
                            len(payload),
                        ),
                    )

                db.execute(
                    """
                    INSERT INTO report_requests(
                        scan_id,
                        assessment_id,
                        request_key,
                        fingerprint,
                        snapshot_id
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        scan_id,
                        assessment_id,
                        idempotency_key,
                        fingerprint,
                        snapshot["snapshot_id"],
                    ),
                )

                return json.loads(
                    snapshot_payload
                )

        except ReportV2StoreError:
            raise

        except sqlite3.IntegrityError as error:
            raise ReportV2StoreError(
                "conflict"
            ) from error

        except (OSError, sqlite3.Error) as error:
            raise self._error(error) from error

    def request_fingerprint(
        self,
        scan_id: str,
        assessment_id: str,
        idempotency_key: str,
    ) -> str | None:
        """Read an existing scoped idempotency fingerprint.

        This operation must never initialize or mutate storage.
        """

        try:
            db = self._connect(readonly=True)

            if db is None:
                return None

            with closing(db):
                row = db.execute(
                    """
                    SELECT fingerprint
                    FROM report_requests
                    WHERE scan_id=?
                      AND assessment_id=?
                      AND request_key=?
                    """,
                    (
                        scan_id,
                        assessment_id,
                        idempotency_key,
                    ),
                ).fetchone()

                return row[0] if row else None

        except (OSError, sqlite3.Error) as error:
            raise self._error(error) from error

    def get(
        self,
        scan_id: str,
        assessment_id: str,
        snapshot_id: str,
    ) -> dict | None:
        """Read one immutable snapshot without creating storage."""

        try:
            db = self._connect(readonly=True)

            if db is None:
                return None

            with closing(db):
                row = db.execute(
                    """
                    SELECT
                        payload,
                        payload_hash
                    FROM report_snapshots
                    WHERE scan_id=?
                      AND assessment_id=?
                      AND snapshot_id=?
                    """,
                    (
                        scan_id,
                        assessment_id,
                        snapshot_id,
                    ),
                ).fetchone()

                if row is None:
                    return None

                return self._decode_snapshot(
                    row
                )

        except (OSError, sqlite3.Error) as error:
            raise self._error(error) from error

    def get_artifact(
        self,
        scan_id: str,
        assessment_id: str,
        snapshot_id: str,
        format: str,
    ) -> bytes | None:
        """Read one immutable artifact within its fixed report scope."""

        if format not in {"html", "json"}:
            raise ReportV2StoreError(
                "invalid_argument"
            )

        try:
            db = self._connect(readonly=True)

            if db is None:
                return None

            with closing(db):
                row = db.execute(
                    """
                    SELECT
                        artifact.payload,
                        artifact.payload_hash,
                        artifact.size_bytes
                    FROM report_artifacts AS artifact
                    JOIN report_snapshots AS snapshot
                      ON snapshot.snapshot_id
                         = artifact.snapshot_id
                    WHERE snapshot.scan_id=?
                      AND snapshot.assessment_id=?
                      AND artifact.snapshot_id=?
                      AND artifact.format=?
                    """,
                    (
                        scan_id,
                        assessment_id,
                        snapshot_id,
                        format,
                    ),
                ).fetchone()

                if row is None:
                    return None

                (
                    payload,
                    expected_hash,
                    size_bytes,
                ) = row

                if (
                    len(payload) != size_bytes
                    or len(payload)
                    > self.max_artifact_bytes
                    or _digest(payload)
                    != expected_hash
                ):
                    raise ReportV2StoreError(
                        "storage_unavailable"
                    )

                return bytes(payload)

        except ReportV2StoreError:
            raise

        except (OSError, sqlite3.Error) as error:
            raise self._error(error) from error