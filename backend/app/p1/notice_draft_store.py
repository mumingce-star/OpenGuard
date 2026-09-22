"""Private immutable NoticeDraft sidecar. GET never creates or writes SQLite."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
from urllib.parse import quote

from .models import P1NoticeDraft
from .notice_facts import canonical, digest, unique, utc


class NoticeDraftStoreError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


DDL = (
    'CREATE TABLE notice_meta (version INTEGER NOT NULL CHECK(version=1))',
    'CREATE TABLE notice_drafts (draft_id TEXT PRIMARY KEY NOT NULL, scan_id TEXT NOT NULL, '
    'assessment_id TEXT NOT NULL, fingerprint TEXT NOT NULL, created_at TEXT NOT NULL, '
    'payload BLOB NOT NULL, payload_hash TEXT NOT NULL, UNIQUE(scan_id,assessment_id,fingerprint))',
    'CREATE TABLE notice_requests (scan_id TEXT NOT NULL, assessment_id TEXT NOT NULL, '
    'request_key TEXT NOT NULL, fingerprint TEXT NOT NULL, draft_id TEXT NOT NULL, '
    'binding_hash TEXT NOT NULL, PRIMARY KEY(scan_id,assessment_id,request_key))',
)


def content_hash(snapshot):
    return digest({k: v for k, v in snapshot.items() if k != 'content_hash'})


def fingerprint(snapshot):
    return digest(dict(binding=snapshot['binding'], generator_version=snapshot['generator_version'],
                       package_hash=snapshot['provenance']['parameters_hash']))


def validate_snapshot(snapshot):
    # Strict validation avoids int/bool/string coercion in nested shared DTOs.
    P1NoticeDraft.model_validate_json(canonical(snapshot), strict=True)
    binding = snapshot['binding']
    scan, assessment = binding['scan_ref'], binding['assessment_ref']
    provenance = snapshot['provenance']
    utc(snapshot['created_at'])
    utc(provenance['generated_at'])
    if (not snapshot['draft_id'].startswith('ntc_') or scan['scan_id'] != assessment['scan_id']
            or scan['facts_hash'] != assessment['facts_hash'] or assessment['formal'] is not True
            or scan['status'] not in {'completed', 'partial'}
            or any(binding[k] for k in ('task_refs', 'notice_refs', 'algorithm_refs'))
            or provenance['source_refs'] != [scan] or provenance['assessment_refs'] != [assessment]
            or provenance['generated_at'] != snapshot['created_at']
            or provenance['algorithm_version'] != snapshot['generator_version']
            or content_hash(snapshot) != snapshot['content_hash']):
        raise ValueError('notice_snapshot_integrity')
    unique([e['entry_id'] for e in snapshot['entries']])
    unique(snapshot['coverage_gaps'])
    for entry in snapshot['entries']:
        for name in ('resource_ids', 'license_expression_ids', 'missing'):
            unique(entry[name])
        unique([canonical(e) for e in entry['evidence_refs']])
        if entry['license_expression_ids'] or entry['obligation_refs']:
            raise ValueError('notice_authority_escalation')
        if any(e['namespace'] != 'scan' or e['scan_id'] != scan['scan_id'] for e in entry['evidence_refs']):
            raise ValueError('notice_evidence_binding')


class NoticeDraftStore:
    def __init__(self, path, *, max_record_bytes=8*1024*1024,
                 max_database_bytes=128*1024*1024, min_free_bytes=512*1024*1024):
        self.path = Path(path).absolute()
        self.max_record_bytes, self.max_database_bytes = max_record_bytes, max_database_bytes
        self.min_free_bytes = min_free_bytes
        if any(type(v) is not int or v <= 0 for v in (max_record_bytes, max_database_bytes)) or min_free_bytes < 0:
            raise ValueError('invalid notice storage budget')

    def _guard(self, create=False):
        if self.path.name != 'notice_draft.db' or any(p.is_symlink() for p in (self.path, *self.path.parents)):
            raise NoticeDraftStoreError('storage_unavailable')
        parent = self.path.parent
        if create:
            parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not parent.exists():
            return False
        parent_info = parent.stat()
        if (not stat.S_ISDIR(parent_info.st_mode) or stat.S_IMODE(parent_info.st_mode) & 0o077
                or parent_info.st_uid != os.geteuid()):
            raise NoticeDraftStoreError('storage_unavailable')
        for p in (self.path, *(Path(str(self.path)+s) for s in ('-wal', '-shm', '-journal'))):
            try:
                info = p.lstat()
            except FileNotFoundError:
                # DELETE journals legitimately disappear on another connection's
                # commit. Inspect atomically, without exists()/stat() races.
                continue
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or stat.S_IMODE(info.st_mode) & 0o077 or info.st_uid != os.geteuid()):
                raise NoticeDraftStoreError('storage_unavailable')
        return self.path.exists()

    @staticmethod
    def _schema(db):
        # Includes exact columns, constraints, indexes and rejects extra objects.
        expected = sorted((sql.split()[2], sql) for sql in DDL)
        actual = db.execute("SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        if (actual != expected or db.execute('PRAGMA user_version').fetchone() != (1,)
                or db.execute('SELECT version FROM notice_meta').fetchall() != [(1,)]
                or db.execute('PRAGMA quick_check').fetchall() != [('ok',)]):
            raise NoticeDraftStoreError('storage_unavailable')

    def _connect(self, readonly=True):
        if not self._guard():
            if readonly:
                return None
            raise NoticeDraftStoreError('storage_unavailable')
        # This sidecar uses DELETE journal mode. Do not open externally switched
        # WAL databases: even mode=ro can create shared-memory sidecars.
        with self.path.open('rb') as stream:
            header = stream.read(20)
        if header[:16] != b'SQLite format 3\x00' or header[18:20] != b'\x01\x01':
            raise NoticeDraftStoreError('storage_unavailable')
        if any(p.exists() for p in (Path(str(self.path)+s) for s in ('-wal', '-shm'))):
            raise NoticeDraftStoreError('storage_unavailable')
        db = sqlite3.connect(f"file:{quote(str(self.path), safe='/')}?mode={'ro' if readonly else 'rw'}", uri=True, timeout=1)
        try:
            db.execute('PRAGMA query_only=ON' if readonly else 'PRAGMA foreign_keys=ON')
            self._schema(db)  # Before any journal/write pragma.
            return db
        except Exception:
            db.close()
            raise

    def initialize(self):
        try:
            if self._guard(create=True):
                with closing(self._connect()):
                    return  # Existing DB is checked read-only, never repaired.
            if self.max_database_bytes < 65536 or shutil.disk_usage(self.path.parent).free < self.min_free_bytes + 65536:
                raise NoticeDraftStoreError('storage_capacity_exceeded')
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            os.close(fd)
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute('BEGIN IMMEDIATE')
                for sql in DDL:
                    db.execute(sql)
                db.execute('INSERT INTO notice_meta VALUES (1)')
                db.execute('PRAGMA user_version=1')
            with closing(self._connect()):
                pass
        except (OSError, sqlite3.Error) as error:
            raise NoticeDraftStoreError('storage_unavailable') from error

    def _load(self, db, scan_id, assessment_id, draft_id):
        row = db.execute('SELECT draft_id,scan_id,assessment_id,fingerprint,created_at,payload,payload_hash FROM notice_drafts WHERE scan_id=? AND assessment_id=? AND draft_id=?', (scan_id, assessment_id, draft_id)).fetchone()
        if row is None:
            return None
        try:
            did, sid, aid, fp, created, raw, sha = row
            if not isinstance(raw, bytes) or len(raw) > self.max_record_bytes or hashlib.sha256(raw).hexdigest() != sha:
                raise ValueError('notice_payload_hash')
            value = json.loads(raw)
            # Canonical bytes also reject duplicate JSON keys / NaN / noncanonical aliases.
            if canonical(value) != raw:
                raise ValueError('notice_payload_encoding')
            validate_snapshot(value)
            if (did, sid, aid, fp, created) != (value['draft_id'], value['binding']['scan_ref']['scan_id'],
                    value['binding']['assessment_ref']['assessment_id'], fingerprint(value), value['created_at']):
                raise ValueError('notice_row_binding')
            return value
        except (ValueError, KeyError, TypeError, RecursionError) as error:
            raise NoticeDraftStoreError('storage_unavailable') from error

    def get(self, scan_id, assessment_id, draft_id):
        try:
            db = self._connect()
            if db is None:
                return None
            with closing(db):
                return self._load(db, scan_id, assessment_id, draft_id)
        except (OSError, sqlite3.Error) as error:
            raise NoticeDraftStoreError('storage_unavailable') from error

    def create(self, scan_id, assessment_id, key, snapshot):
        try:
            validate_snapshot(snapshot)
            if (snapshot['binding']['scan_ref']['scan_id'], snapshot['binding']['assessment_ref']['assessment_id']) != (scan_id, assessment_id):
                raise ValueError('scope_mismatch')
            if not isinstance(key, str) or not 1 <= len(key) <= 200 or not key.strip():
                raise ValueError('key_invalid')
            raw = canonical(snapshot)
            if len(raw) > self.max_record_bytes:
                raise NoticeDraftStoreError('storage_capacity_exceeded')
        except (ValueError, KeyError, TypeError, RecursionError) as error:
            raise NoticeDraftStoreError('invalid_argument') from error
        fp = fingerprint(snapshot)
        try:
            with closing(self._connect(False)) as db, db:
                db.execute('BEGIN IMMEDIATE')
                request = db.execute('SELECT fingerprint,draft_id,binding_hash FROM notice_requests WHERE scan_id=? AND assessment_id=? AND request_key=?', (scan_id, assessment_id, key)).fetchone()
                if request:
                    old_fp, old_id, sha = request
                    if sha != digest([scan_id, assessment_id, key, old_fp, old_id]):
                        raise NoticeDraftStoreError('storage_unavailable')
                    saved = self._load(db, scan_id, assessment_id, old_id)
                    if saved is None or fingerprint(saved) != old_fp:
                        raise NoticeDraftStoreError('storage_unavailable')
                    if fp != old_fp:
                        raise NoticeDraftStoreError('idempotency_conflict')
                    return saved
                prior = db.execute('SELECT draft_id FROM notice_drafts WHERE scan_id=? AND assessment_id=? AND fingerprint=?', (scan_id, assessment_id, fp)).fetchone()
                saved = self._load(db, scan_id, assessment_id, prior[0]) if prior else snapshot
                size = len(raw) + len(key.encode()) + 16384
                used = db.execute('PRAGMA page_count').fetchone()[0] * db.execute('PRAGMA page_size').fetchone()[0]
                if used + size > self.max_database_bytes or shutil.disk_usage(self.path.parent).free < self.min_free_bytes + size:
                    raise NoticeDraftStoreError('storage_capacity_exceeded')
                if not prior:
                    db.execute('INSERT INTO notice_drafts VALUES (?,?,?,?,?,?,?)', (snapshot['draft_id'], scan_id, assessment_id, fp, snapshot['created_at'], raw, hashlib.sha256(raw).hexdigest()))
                did = saved['draft_id']
                db.execute('INSERT INTO notice_requests VALUES (?,?,?,?,?,?)', (scan_id, assessment_id, key, fp, did, digest([scan_id, assessment_id, key, fp, did])))
                return saved
        except (OSError, sqlite3.Error) as error:
            raise NoticeDraftStoreError('storage_unavailable') from error
