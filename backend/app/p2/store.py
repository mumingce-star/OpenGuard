"""Atomic P2 publications in a private sidecar; reads never initialize/repair."""
from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

from .contract import P2Error, canonical, strict_json


class P2Store:
    def __init__(self, path):
        self.path = Path(path).absolute()

    def guard(self):
        if self.path.name != "p2.db":
            raise P2Error("p2_storage_invalid", 503)
        for path in (self.path.parent, self.path):
            info = path.lstat()
            if (stat.S_ISLNK(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077 or (path == self.path and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1))):
                raise P2Error("p2_storage_invalid", 503)

    def initialize(self):
        # Called only by the explicit enabled factory, never by a read/write route.
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not self.path.exists():
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        with self.connection(write=True) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS p2_meta(version INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS p2_objects(
                    kind TEXT NOT NULL,id TEXT PRIMARY KEY,scan_id TEXT NOT NULL,assessment_id TEXT NOT NULL,
                    payload BLOB NOT NULL,sha256 TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS p2_heads(
                    scan_id TEXT,assessment_id TEXT,result_id TEXT NOT NULL,revision INTEGER NOT NULL,
                    PRIMARY KEY(scan_id,assessment_id));
                CREATE TABLE IF NOT EXISTS p2_requests(
                    scan_id TEXT,assessment_id TEXT,key TEXT,fingerprint TEXT NOT NULL,
                    payload BLOB NOT NULL,sha256 TEXT NOT NULL,PRIMARY KEY(scan_id,assessment_id,key));
                CREATE TABLE IF NOT EXISTS p2_material_content(id TEXT PRIMARY KEY,content BLOB NOT NULL,sha256 TEXT NOT NULL);
            """)
            versions = db.execute("SELECT version FROM p2_meta").fetchall()
            if not versions:
                db.execute("INSERT INTO p2_meta VALUES(1)")
            elif versions != [(1,)]:
                raise P2Error("p2_schema_unsupported", 503)

    @contextmanager
    def connection(self, *, write=False):
        db = None
        try:
            self.guard()
            db = sqlite3.connect(f"file:{quote(str(self.path), safe='/')}?mode={'rw' if write else 'ro'}", uri=True, timeout=2)
            if write:
                db.execute("PRAGMA journal_mode=DELETE")
                db.execute("PRAGMA synchronous=FULL")
                page_size = db.execute('PRAGMA page_size').fetchone()[0]
                db.execute(f"PRAGMA max_page_count={128 * 1024 * 1024 // page_size}")
                db.execute("BEGIN IMMEDIATE")
            else:
                db.execute("PRAGMA query_only=ON")
                db.execute("BEGIN")
            yield db
            if write:
                db.commit()
        except (sqlite3.Error, OSError) as exc:
            raise P2Error("p2_storage_unavailable", 503) from exc
        finally:
            if db is not None:
                db.close()  # uncommitted exception path rolls back all publication rows

    @staticmethod
    def decode(row):
        if row is None:
            return None
        raw, expected = row
        if not isinstance(raw, bytes) or hashlib.sha256(raw).hexdigest() != expected:
            raise P2Error("p2_integrity_error", 503)
        try:
            value = strict_json(raw)
            if canonical(value) != raw:
                raise ValueError()
            return value
        except (ValueError, TypeError, UnicodeError) as exc:
            raise P2Error("p2_integrity_error", 503) from exc

    def get(self, db, kind, identity, sid, aid):
        row = db.execute("SELECT kind,scan_id,assessment_id,payload,sha256 FROM p2_objects WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise P2Error("p2_not_found", 404)
        if row[:3] != (kind, sid, aid):
            raise P2Error("p2_binding_conflict")
        value = self.decode(row[3:])
        id_field = {'result': 'result_id', 'answer': 'answer_id', 'material': 'material_id', 'summary': 'summary_id'}[kind]
        if (not isinstance(value, dict) or value.get(id_field) != identity
                or not isinstance(value.get('binding'), dict)
                or value['binding'].get('scan_id') != sid or value['binding'].get('assessment_id') != aid):
            raise P2Error('p2_integrity_error', 503)
        return value

    def put(self, db, kind, identity, binding, value):
        raw = canonical(value)
        if len(raw) > 8 * 1024 * 1024:
            raise P2Error("p2_result_too_large", 413)
        db.execute("INSERT INTO p2_objects VALUES(?,?,?,?,?,?)", (kind, identity, binding['scan_id'], binding['assessment_id'], raw, hashlib.sha256(raw).hexdigest()))

    def head(self, db, sid, aid):
        return db.execute("SELECT result_id,revision FROM p2_heads WHERE scan_id=? AND assessment_id=?", (sid, aid)).fetchone()

    def replay(self, db, sid, aid, key, fingerprint):
        row = db.execute("SELECT fingerprint,payload,sha256 FROM p2_requests WHERE scan_id=? AND assessment_id=? AND key=?", (sid, aid, key)).fetchone()
        if row is None:
            return None
        if row[0] != fingerprint:
            raise P2Error("p2_idempotency_conflict")
        return self.decode(row[1:])

    def request(self, db, sid, aid, key, fingerprint, value):
        if db.execute("SELECT count(*) FROM p2_requests").fetchone()[0] >= 10000:
            raise P2Error("p2_capacity_exceeded", 503)
        raw = canonical(value)
        db.execute("INSERT INTO p2_requests VALUES(?,?,?,?,?,?)", (sid, aid, key, fingerprint, raw, hashlib.sha256(raw).hexdigest()))

    def material_bytes(self, db, material):
        row = db.execute("SELECT content,sha256 FROM p2_material_content WHERE id=?", (material['material_id'],)).fetchone()
        if row is None or row[1] != material['source_sha256'] or len(row[0]) != material['byte_count'] or hashlib.sha256(row[0]).hexdigest() != row[1]:
            raise P2Error("p2_integrity_error", 503)
        return row[0]
