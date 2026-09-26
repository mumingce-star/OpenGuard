"""A-owned NOTICE source admission, fixed terminal binding and store-only reader.

This is an internal boundary, not the CZ collector DTO or a public API. The
caller may stage only bytes already validated by a trusted collector adapter.
No production adapter is installed in Phase A1.

Supported writes are Store.initialize/Store.stage and BindingService.bind.
Only bind constructs and publishes BOUND after authoritative upstream checks;
there is no Store writer accepting a caller-built BOUND. Underscored SQLite
helpers are implementation details, not an isolation boundary against malicious
same-process Python or an actor with direct database write access.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
from urllib.parse import quote

from app.assessment.engine import canonical_bytes, facts_digest
from app.assessment.store import AssessmentStoreError
from app.persistence.scan_registry import ScanRegistryError


PACKAGE_LIMIT = 8 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_BOUND_KEYS = frozenset({
    'scan_id', 'registry_revision', 'input_digest', 'inventory_digest', 'facts_hash',
    'assessment_id', 'assessment_version', 'assessment_facts_hash', 'package_hash',
    'collector_schema_version', 'producer', 'producer_version', 'coverage_status',
    'omissions', 'gap_codes', 'bound_at',
})
_DDL = (
    'CREATE TABLE notice_source_meta (version INTEGER NOT NULL CHECK(version=1))',
    'CREATE TABLE notice_source_staged (scan_id TEXT PRIMARY KEY NOT NULL, input_json BLOB NOT NULL, '
    'input_hash TEXT NOT NULL, package_bytes BLOB NOT NULL, package_hash TEXT NOT NULL)',
    'CREATE TABLE notice_source_bindings (scan_id TEXT NOT NULL, assessment_id TEXT NOT NULL, '
    'assessment_version INTEGER NOT NULL, payload BLOB NOT NULL, binding_hash TEXT NOT NULL, '
    'PRIMARY KEY(scan_id,assessment_id,assessment_version))',
)


class NoticeSourceStoreError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _text(value: object, *, max_bytes: int = 256) -> bool:
    return (type(value) is str and bool(value.strip()) and len(value.encode('utf-8')) <= max_bytes
            and not value.startswith(('/', '\\', 'file://'))
            and re.match(r'^[A-Za-z]:[\\/]', value) is None)


@dataclass(frozen=True)
class ValidatedNoticeSourceInput:
    scan_id: str
    canonical_package_bytes: bytes
    package_hash: str
    collector_schema_version: str
    producer: str
    producer_version: str
    observed_input_digest: str
    observed_inventory_digest: str | None
    coverage_status: str
    omissions: list[str]
    gap_codes: list[str]


@dataclass(frozen=True)
class StagedNoticeSource:
    state: str
    scan_id: str
    package_hash: str
    collector_schema_version: str
    producer: str
    producer_version: str
    observed_input_digest: str
    observed_inventory_digest: str | None
    coverage_status: str
    omissions: tuple[str, ...]
    gap_codes: tuple[str, ...]


@dataclass(frozen=True)
class BoundNoticeSource:
    state: str
    scan_id: str
    registry_revision: int
    input_digest: str
    inventory_digest: str | None
    facts_hash: str
    assessment_id: str
    assessment_version: int
    assessment_facts_hash: str
    package_hash: str
    collector_schema_version: str
    producer: str
    producer_version: str
    coverage_status: str
    omissions: tuple[str, ...]
    gap_codes: tuple[str, ...]
    bound_at: str
    binding_hash: str
    canonical_package_bytes: bytes


def _admission(value: ValidatedNoticeSourceInput | dict) -> tuple[dict, bytes]:
    try:
        data = vars(value).copy() if type(value) is ValidatedNoticeSourceInput else value.copy()
        expected = set(ValidatedNoticeSourceInput.__dataclass_fields__)
        if type(data) is not dict or set(data) != expected:
            raise ValueError('fields')
        raw = data.pop('canonical_package_bytes')
        if type(raw) is not bytes:
            raise ValueError('package_bytes')
        if len(raw) > PACKAGE_LIMIT:
            raise NoticeSourceStoreError('storage_capacity_exceeded')
        if not _text(data['scan_id']) or not _SHA.fullmatch(data['package_hash']) or _sha(raw) != data['package_hash']:
            raise ValueError('package_identity')
        for field in ('collector_schema_version', 'producer', 'producer_version'):
            if not _text(data[field]):
                raise ValueError(field)
        if not _SHA.fullmatch(data['observed_input_digest']):
            raise ValueError('input_digest')
        inventory = data['observed_inventory_digest']
        if inventory is not None and (type(inventory) is not str or not _SHA.fullmatch(inventory)):
            raise ValueError('inventory_digest')
        if data['coverage_status'] not in ('completed', 'partial'):
            raise ValueError('coverage_status')
        for field in ('omissions', 'gap_codes'):
            items = data[field]
            if type(items) is not list or len(items) > 512 or any(not _text(x, max_bytes=512) for x in items):
                raise ValueError(field)
        if data['coverage_status'] == 'completed' and (data['omissions'] or data['gap_codes']):
            raise ValueError('completed_gaps')
        if data['coverage_status'] == 'partial' and not (data['omissions'] or data['gap_codes']):
            raise ValueError('partial_gaps')
        if len(canonical_bytes(data)) > 65536:
            raise ValueError('metadata_capacity')
        return data, raw
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError) as error:
        raise NoticeSourceStoreError('invalid_argument') from error


def _staged(data: dict) -> StagedNoticeSource:
    return StagedNoticeSource('STAGED', data['scan_id'], data['package_hash'],
        data['collector_schema_version'], data['producer'], data['producer_version'],
        data['observed_input_digest'], data['observed_inventory_digest'],
        data['coverage_status'], tuple(data['omissions']), tuple(data['gap_codes']))


class NoticeSourceStore:
    def __init__(self, path: str | Path, *, max_database_bytes: int = 128 * 1024 * 1024,
                 min_free_bytes: int = 512 * 1024 * 1024):
        self.path = Path(path).absolute()
        self.max_database_bytes = max_database_bytes
        self.min_free_bytes = min_free_bytes
        if type(max_database_bytes) is not int or max_database_bytes < 65536 or type(min_free_bytes) is not int or min_free_bytes < 0:
            raise ValueError('invalid notice source storage budget')

    def _guard(self, *, create: bool = False) -> bool:
        if self.path.name != 'notice_source.db' or any(p.is_symlink() for p in (self.path, *self.path.parents)):
            raise NoticeSourceStoreError('storage_unavailable')
        parent = self.path.parent
        if create:
            parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not parent.exists():
            return False
        info = parent.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise NoticeSourceStoreError('storage_unavailable')
        for p in (self.path, *(Path(str(self.path) + suffix) for suffix in ('-wal', '-shm', '-journal'))):
            try:
                info = p.lstat()
            except FileNotFoundError:
                continue
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077):
                raise NoticeSourceStoreError('storage_unavailable')
        return self.path.exists()

    @staticmethod
    def _schema(db: sqlite3.Connection) -> None:
        expected = sorted((sql.split()[2], sql) for sql in _DDL)
        actual = db.execute("SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        if (actual != expected or db.execute('PRAGMA user_version').fetchone() != (1,)
                or db.execute('SELECT version FROM notice_source_meta').fetchall() != [(1,)]
                or db.execute('PRAGMA quick_check').fetchall() != [('ok',)]):
            raise NoticeSourceStoreError('storage_unavailable')

    def _connect(self, *, readonly: bool = True) -> sqlite3.Connection | None:
        if not self._guard():
            if readonly:
                return None
            raise NoticeSourceStoreError('storage_unavailable')
        with self.path.open('rb') as stream:
            header = stream.read(20)
        if header[:16] != b'SQLite format 3\x00' or header[18:20] != b'\x01\x01':
            raise NoticeSourceStoreError('storage_unavailable')
        if any(Path(str(self.path) + suffix).exists() for suffix in ('-wal', '-shm')):
            raise NoticeSourceStoreError('storage_unavailable')
        db = sqlite3.connect(f"file:{quote(str(self.path), safe='/')}?mode={'ro' if readonly else 'rw'}", uri=True, timeout=1)
        try:
            db.execute('PRAGMA query_only=ON' if readonly else 'PRAGMA foreign_keys=ON')
            self._schema(db)
            if not readonly:
                db.execute('PRAGMA synchronous=FULL')
                page_size = db.execute('PRAGMA page_size').fetchone()[0]
                db.execute(f'PRAGMA max_page_count={self.max_database_bytes // page_size}')
            return db
        except Exception:
            db.close()
            raise

    def initialize(self) -> None:
        try:
            if self._guard(create=True):
                with closing(self._connect()):
                    return
            if shutil.disk_usage(self.path.parent).free < self.min_free_bytes + 65536:
                raise NoticeSourceStoreError('storage_capacity_exceeded')
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            os.close(fd)
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute('BEGIN IMMEDIATE')
                for sql in _DDL:
                    db.execute(sql)
                db.execute('INSERT INTO notice_source_meta VALUES (1)')
                db.execute('PRAGMA user_version=1')
            with closing(self._connect()):
                pass
        except (OSError, sqlite3.Error) as error:
            raise self._error(error) from error

    @staticmethod
    def _error(error: Exception) -> NoticeSourceStoreError:
        full = isinstance(error, sqlite3.Error) and getattr(error, 'sqlite_errorcode', None) == sqlite3.SQLITE_FULL
        return NoticeSourceStoreError('storage_capacity_exceeded' if full else 'storage_unavailable')

    def _capacity(self, db: sqlite3.Connection, size: int) -> None:
        used = db.execute('PRAGMA page_count').fetchone()[0] * db.execute('PRAGMA page_size').fetchone()[0]
        if used + size + 16384 > self.max_database_bytes or shutil.disk_usage(self.path.parent).free < self.min_free_bytes + size + 16384:
            raise NoticeSourceStoreError('storage_capacity_exceeded')

    @staticmethod
    def _load_stage(db: sqlite3.Connection, scan_id: str) -> tuple[dict, bytes] | None:
        row = db.execute('SELECT input_json,input_hash,package_bytes,package_hash FROM notice_source_staged WHERE scan_id=?', (scan_id,)).fetchone()
        if row is None:
            return None
        try:
            meta, meta_hash, raw, package_hash = row
            if type(meta) is not bytes or type(raw) is not bytes or len(meta) > 65536 or len(raw) > PACKAGE_LIMIT:
                raise ValueError('size')
            if _sha(meta) != meta_hash or _sha(raw) != package_hash:
                raise ValueError('hash')
            data = json.loads(meta)
            if canonical_bytes(data) != meta or data['scan_id'] != scan_id or data['package_hash'] != package_hash:
                raise ValueError('row')
            _admission({**data, 'canonical_package_bytes': raw})
            return data, raw
        except (ValueError, KeyError, TypeError, RecursionError, NoticeSourceStoreError) as error:
            raise NoticeSourceStoreError('storage_unavailable') from error

    @staticmethod
    def _load_bound(db: sqlite3.Connection, scan_id: str, assessment_id: str, assessment_version: int) -> tuple[dict, str] | None:
        row = db.execute('SELECT payload,binding_hash FROM notice_source_bindings WHERE scan_id=? AND assessment_id=? AND assessment_version=?',
                         (scan_id, assessment_id, assessment_version)).fetchone()
        if row is None:
            return None
        try:
            raw, sha = row
            if type(raw) is not bytes or len(raw) > 65536 or _sha(raw) != sha:
                raise ValueError('hash')
            data = json.loads(raw)
            if (type(data) is not dict or set(data) != _BOUND_KEYS or canonical_bytes(data) != raw
                    or (data['scan_id'], data['assessment_id'], data['assessment_version']) != (scan_id, assessment_id, assessment_version)):
                raise ValueError('row')
            return data, sha
        except (ValueError, KeyError, TypeError, RecursionError) as error:
            raise NoticeSourceStoreError('storage_unavailable') from error

    @staticmethod
    def _bound(data: dict, sha: str, package: bytes) -> BoundNoticeSource:
        try:
            return BoundNoticeSource('BOUND', data['scan_id'], data['registry_revision'],
                data['input_digest'], data['inventory_digest'], data['facts_hash'],
                data['assessment_id'], data['assessment_version'], data['assessment_facts_hash'],
                data['package_hash'], data['collector_schema_version'], data['producer'],
                data['producer_version'], data['coverage_status'], tuple(data['omissions']),
                tuple(data['gap_codes']), data['bound_at'], sha, package)
        except (KeyError, TypeError, ValueError) as error:
            raise NoticeSourceStoreError('storage_unavailable') from error

    def stage(self, value: ValidatedNoticeSourceInput | dict) -> StagedNoticeSource:
        data, raw = _admission(value)
        encoded = canonical_bytes(data)
        try:
            with closing(self._connect(readonly=False)) as db, db:
                db.execute('BEGIN IMMEDIATE')
                old = self._load_stage(db, data['scan_id'])
                if old is not None:
                    if old != (data, raw):
                        raise NoticeSourceStoreError('conflict')
                    return _staged(data)
                self._capacity(db, len(raw) + len(encoded))
                db.execute('INSERT INTO notice_source_staged VALUES (?,?,?,?,?)',
                           (data['scan_id'], encoded, _sha(encoded), raw, data['package_hash']))
                return _staged(data)
        except (OSError, sqlite3.Error) as error:
            raise self._error(error) from error

    @staticmethod
    def _validated_bound(data: dict, sha: str, staged: tuple[dict, bytes]) -> BoundNoticeSource:
        """Pure closure validation shared by write-before-INSERT and read paths."""
        try:
            meta, package = staged
            encoded = canonical_bytes(data)
            if (type(data) is not dict or set(data) != _BOUND_KEYS or len(encoded) > 65536
                    or _sha(encoded) != sha or data['scan_id'] != meta['scan_id']):
                raise ValueError('binding_identity')
            for key in ('package_hash', 'collector_schema_version', 'producer', 'producer_version',
                        'coverage_status', 'omissions', 'gap_codes'):
                if data[key] != meta[key]:
                    raise ValueError('stage_binding')
            # Also verify the actual bytes: an internally malformed candidate must
            # not be committed merely because it copied its claimed stage hash.
            _admission({**meta, 'canonical_package_bytes': package})
            if (data['input_digest'] != meta['observed_input_digest']
                    or data['inventory_digest'] != meta['observed_inventory_digest']
                    or data['assessment_facts_hash'] != data['facts_hash']
                    or type(data['registry_revision']) is not int or data['registry_revision'] < 1
                    or type(data['assessment_version']) is not int or data['assessment_version'] < 1
                    or type(data['facts_hash']) is not str or not _SHA.fullmatch(data['facts_hash'])
                    or type(data['bound_at']) is not str or not _text(data['assessment_id'])):
                raise ValueError('binding_fields')
            return NoticeSourceStore._bound(data, sha, package)
        except (KeyError, TypeError, ValueError, RecursionError, NoticeSourceStoreError) as error:
            raise NoticeSourceStoreError('storage_unavailable') from error

    def _read_bound(self, scan_id: str, assessment_id: str, assessment_version: int) -> BoundNoticeSource | None:
        try:
            db = self._connect()
            if db is None:
                return None
            with closing(db):
                saved = self._load_bound(db, scan_id, assessment_id, assessment_version)
                if saved is None:
                    return None
                data, sha = saved
                staged = self._load_stage(db, scan_id)
                if staged is None:
                    raise NoticeSourceStoreError('storage_unavailable')
                return self._validated_bound(data, sha, staged)
        except (OSError, sqlite3.Error) as error:
            raise self._error(error) from error


class NoticeSourceBindingService:
    def __init__(self, source_store: NoticeSourceStore, scan_registry, assessment_store):
        self.source_store = source_store
        self.scan_registry = scan_registry
        self.assessment_store = assessment_store

    def bind(self, *, scan_id: str, expected_registry_revision: int,
             assessment_id: str, expected_assessment_version: int) -> BoundNoticeSource:
        if (not _text(scan_id) or not _text(assessment_id) or type(expected_registry_revision) is not int
                or expected_registry_revision < 1 or type(expected_assessment_version) is not int
                or expected_assessment_version < 1):
            raise NoticeSourceStoreError('invalid_argument')
        try:
            store = self.source_store
            with closing(store._connect(readonly=False)) as db, db:
                db.execute('BEGIN IMMEDIATE')
                stored = self.scan_registry.get(scan_id)
                if stored is None:
                    raise NoticeSourceStoreError('not_found')
                run = stored.run
                if run.status.value not in ('completed', 'partial'):
                    raise NoticeSourceStoreError('not_ready')
                staged = store._load_stage(db, scan_id)
                if staged is None:
                    raise NoticeSourceStoreError('not_ready')
                meta, _ = staged
                input_digest = run.provenance.input_digest.value
                inventory = run.provenance.inventory_digest.value if run.provenance.inventory_digest else None
                if (stored.revision != expected_registry_revision or run.id != scan_id or meta['scan_id'] != scan_id
                        or meta['observed_input_digest'] != input_digest
                        or meta['observed_inventory_digest'] != inventory):
                    raise NoticeSourceStoreError('binding_mismatch')
                assessment = self.assessment_store.get(scan_id, assessment_id)
                facts_hash = facts_digest(run)
                if (assessment is None or assessment.id != assessment_id or assessment.version != expected_assessment_version
                        or assessment.scan_id != scan_id or assessment.formal is not True or assessment.facts_hash != facts_hash):
                    raise NoticeSourceStoreError('binding_mismatch')
                # Only this trusted path builds BOUND. No caller-supplied record,
                # state, facts hash or publication token is accepted.
                data = dict(scan_id=scan_id, registry_revision=stored.revision, input_digest=input_digest,
                            inventory_digest=inventory, facts_hash=facts_hash, assessment_id=assessment_id,
                            assessment_version=assessment.version, assessment_facts_hash=assessment.facts_hash,
                            package_hash=meta['package_hash'], collector_schema_version=meta['collector_schema_version'],
                            producer=meta['producer'], producer_version=meta['producer_version'],
                            coverage_status=meta['coverage_status'], omissions=meta['omissions'],
                            gap_codes=meta['gap_codes'], bound_at=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'))
                encoded = canonical_bytes(data)
                if len(encoded) > 65536:
                    raise NoticeSourceStoreError('storage_capacity_exceeded')
                sha = _sha(encoded)
                candidate = store._validated_bound(data, sha, staged)
                existing = store._load_bound(db, scan_id, assessment_id, assessment.version)
                if existing is not None:
                    saved = store._validated_bound(*existing, staged)
                    # bound_at is generated only once, on the first exact bind.
                    if {k: v for k, v in existing[0].items() if k != 'bound_at'} != {k: v for k, v in data.items() if k != 'bound_at'}:
                        raise NoticeSourceStoreError('conflict')
                    return saved
                store._capacity(db, len(encoded))
                # Private SQL detail of bind, not a generic Store publication API.
                # All semantic checks and result construction precede INSERT.
                # Returning inside the connection context commits before return;
                # any SQL/internal exception instead rolls back the same transaction.
                db.execute('INSERT INTO notice_source_bindings VALUES (?,?,?,?,?)',
                           (scan_id, assessment_id, assessment.version, encoded, sha))
                return candidate
        except (ScanRegistryError, AssessmentStoreError) as error:
            raise NoticeSourceStoreError('storage_unavailable') from error
        except (OSError, sqlite3.Error) as error:
            raise self.source_store._error(error) from error


class BoundNoticeSourceReader:
    """Read only immutable BOUND material; never query scanner, registry or network."""
    def __init__(self, source_store: NoticeSourceStore):
        self.source_store = source_store

    def read(self, scan_id: str, facts_hash: str, assessment_id: str,
             assessment_version: int) -> BoundNoticeSource | None:
        if not _text(scan_id) or not _text(assessment_id) or type(assessment_version) is not int or assessment_version < 1:
            raise NoticeSourceStoreError('invalid_argument')
        if type(facts_hash) is not str or not _SHA.fullmatch(facts_hash):
            raise NoticeSourceStoreError('invalid_argument')
        result = self.source_store._read_bound(scan_id, assessment_id, assessment_version)
        return result if result is not None and result.facts_hash == facts_hash else None
