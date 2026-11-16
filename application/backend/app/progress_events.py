"""Opt-in progress observations, independent of ScanRun and Formal results."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Literal
import os, sqlite3, stat
from pydantic import BaseModel, ConfigDict, Field

Phase = Literal['ingestion','inventory','scan','normalize','rules','ai_assist','report']
EventState = Literal['start','end','completed','partial','failed','cancelled']
class ProgressEvent(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    sequence: int = Field(ge=1, le=64)
    phase: Phase
    state: EventState
    percent: int = Field(ge=0, le=100)
    observed_at: str
class ProgressEventView(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    schema_version: Literal['openguard.progress-events/1'] = 'openguard.progress-events/1'
    scan_id: str
    terminal_status: str
    source: str | None = None
    project_name: str | None = None
    events: list[ProgressEvent] = Field(max_length=64)
    recording_complete: bool

class ProgressEventStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = RLock()
    def initialize(self):
        parent = self.path.parent.lstat()
        if not stat.S_ISDIR(parent.st_mode) or stat.S_ISLNK(parent.st_mode) or parent.st_uid != os.geteuid() or parent.st_mode & 0o077:
            raise ValueError('progress_store_unavailable')
        if self.path.exists() or self.path.is_symlink():
            info = self.path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise ValueError('progress_store_unavailable')
        else:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS events (scan_id TEXT NOT NULL, sequence INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(scan_id,sequence))')
    def write(self, scan_id: str, phase: Phase, state: EventState, percent: int):
        import json
        if type(scan_id) is not str or not scan_id or len(scan_id)>100:
            raise ValueError('progress_event_invalid')
        with self._lock, sqlite3.connect(self.path) as db:
            sequence = db.execute('SELECT count(*) FROM events WHERE scan_id=?',(scan_id,)).fetchone()[0]+1
            event = ProgressEvent(sequence=sequence,phase=phase,state=state,percent=percent,observed_at=datetime.now(timezone.utc).isoformat())
            db.execute('INSERT INTO events VALUES (?,?,?)',(scan_id,sequence,json.dumps(event.model_dump(),separators=(',',':'))))
    def read(self, scan_id: str, terminal_status: str) -> ProgressEventView:
        import json
        # GET opens the existing sidecar read-only; it never initializes or repairs it.
        with self._lock, sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True) as db:
            db.execute('PRAGMA query_only=ON')
            rows = db.execute('SELECT payload FROM events WHERE scan_id=? ORDER BY sequence LIMIT 65',(scan_id,)).fetchall()
        events = [ProgressEvent.model_validate(json.loads(row[0])) for row in rows]
        required = {'ingestion','inventory','scan','normalize','rules','report'}
        ended = {e.phase for e in events if e.state=='end'}
        complete = terminal_status=='completed' and required<=ended and bool(events) and events[-1].state=='completed'
        return ProgressEventView(scan_id=scan_id,terminal_status=terminal_status,events=events,recording_complete=complete)
