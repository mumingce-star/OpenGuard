"""Bounded task chat in the assessment SQLite sidecar, with clear generations."""
from __future__ import annotations
from contextlib import closing
from datetime import datetime, timezone
import json
import shutil
from .store import AssessmentStore, AssessmentStoreError


class ChatStore:
    def __init__(self, store: AssessmentStore, *, max_message_chars=2000, max_turns=50,
                 max_session_bytes=256*1024, max_total_bytes=32*1024*1024):
        self.store = store
        self.limits = dict(max_message_chars=max_message_chars,max_turns=max_turns,
                           max_session_bytes=max_session_bytes,max_total_bytes=max_total_bytes)
        if any(type(n) is not int or n <= 0 for n in self.limits.values()):
            raise ValueError('invalid_chat_limits')

    def initialize(self):
        self.store.initialize()
        with closing(self.store._connect()) as db, db:
            db.executescript('''CREATE TABLE IF NOT EXISTS chat_sessions(scan_id TEXT PRIMARY KEY,generation INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS chat_turns(scan_id TEXT NOT NULL,request_id TEXT NOT NULL,generation INTEGER NOT NULL,
                assessment_id TEXT NOT NULL,question TEXT NOT NULL,answer TEXT,evidence_json TEXT NOT NULL,
                status TEXT NOT NULL,error TEXT,created_at TEXT NOT NULL,elapsed_seconds REAL,bytes INTEGER NOT NULL,
                PRIMARY KEY(scan_id,request_id));''')
            # Startup recovery does not replay expensive calls or claim success.
            db.execute("UPDATE chat_turns SET status='failed',error='服务中断，未取得完整答复；可主动发送新问题。',bytes=length(CAST(question AS BLOB))+1024 WHERE status='pending'")

    @staticmethod
    def _turn(row):
        keys = ('request_id','assessment_id','question','answer','evidence_ids','status','error','created_at','elapsed_seconds','generation')
        value = dict(zip(keys,row));value['evidence_ids']=json.loads(value['evidence_ids']);return value

    def history(self, scan_id):
        rows = self.store._read('SELECT generation FROM chat_sessions WHERE scan_id=?',(scan_id,))
        turns = self.store._read('SELECT request_id,assessment_id,question,answer,evidence_json,status,error,created_at,elapsed_seconds,generation FROM chat_turns WHERE scan_id=? ORDER BY created_at,request_id',(scan_id,))
        return {'generation':rows[0][0] if rows else 0,'items':[self._turn(r) for r in turns], 'limits':self.limits}

    def reserve(self,scan_id,assessment_id,request_id,message,generation):
        if not isinstance(message,str) or not message.strip() or len(message)>self.limits['max_message_chars']:
            raise AssessmentStoreError('chat_message_invalid')
        with closing(self.store._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO chat_sessions VALUES (?,0)',(scan_id,))
            current = db.execute('SELECT generation FROM chat_sessions WHERE scan_id=?',(scan_id,)).fetchone()[0]
            if generation != current:
                raise AssessmentStoreError('chat_generation_conflict')
            row=db.execute('SELECT request_id,assessment_id,question,answer,evidence_json,status,error,created_at,elapsed_seconds,generation FROM chat_turns WHERE scan_id=? AND request_id=?',(scan_id,request_id)).fetchone()
            if row:
                if row[1]!=assessment_id or row[2]!=message:
                    raise AssessmentStoreError('chat_idempotency_conflict')
                return self._turn(row),False
            if db.execute("SELECT 1 FROM chat_turns WHERE scan_id=? AND status='pending'",(scan_id,)).fetchone():
                raise AssessmentStoreError('chat_busy')
            count,used=db.execute('SELECT count(*),coalesce(sum(bytes),0) FROM chat_turns WHERE scan_id=?',(scan_id,)).fetchone()
            total=db.execute('SELECT coalesce(sum(bytes),0) FROM chat_turns').fetchone()[0]
            reserve=len(message.encode())+24*1024
            physical=(db.execute('PRAGMA page_count').fetchone()[0]-db.execute('PRAGMA freelist_count').fetchone()[0])*db.execute('PRAGMA page_size').fetchone()[0]
            if (count>=self.limits['max_turns'] or used+reserve>self.limits['max_session_bytes'] or total+reserve>self.limits['max_total_bytes']
                or physical+reserve>self.store.max_database_bytes or shutil.disk_usage(self.store.path.parent).free<self.store.min_free_bytes+reserve):
                raise AssessmentStoreError('chat_capacity_exceeded')
            created=datetime.now(timezone.utc).isoformat()
            db.execute("INSERT INTO chat_turns VALUES (?,?,?,?,?,NULL,'[]','pending',NULL,?,NULL,?)",(scan_id,request_id,current,assessment_id,message,created,reserve))
            return {'request_id':request_id,'assessment_id':assessment_id,'question':message,'answer':None,'evidence_ids':[],
                    'status':'pending','error':None,'created_at':created,'elapsed_seconds':None,'generation':current},True

    def finish(self,scan_id,request_id,generation,*,answer=None,evidence_ids=None,error=None,elapsed_seconds=0):
        if answer is not None and (not isinstance(answer,str) or len(answer)>1800):
            raise AssessmentStoreError('chat_answer_invalid')
        refs=json.dumps(evidence_ids or [])
        with closing(self.store._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT generation FROM chat_sessions WHERE scan_id=?',(scan_id,)).fetchone()
            if not current or current[0]!=generation:
                return False
            row=db.execute("SELECT question FROM chat_turns WHERE scan_id=? AND request_id=? AND generation=? AND status='pending'",(scan_id,request_id,generation)).fetchone()
            if not row:
                return False
            size=len(row[0].encode())+len((answer or '').encode())+len(refs.encode())+1024
            db.execute("UPDATE chat_turns SET answer=?,evidence_json=?,status=?,error=?,elapsed_seconds=?,bytes=? WHERE scan_id=? AND request_id=? AND generation=? AND status='pending'",
                (answer,refs,'failed' if error or answer is None else 'succeeded',error,elapsed_seconds,size,scan_id,request_id,generation))
            return True

    def clear(self,scan_id,generation):
        with closing(self.store._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO chat_sessions VALUES (?,0)',(scan_id,))
            current=db.execute('SELECT generation FROM chat_sessions WHERE scan_id=?',(scan_id,)).fetchone()[0]
            if generation!=current:
                raise AssessmentStoreError('chat_generation_conflict')
            db.execute('DELETE FROM chat_turns WHERE scan_id=?',(scan_id,))
            db.execute('UPDATE chat_sessions SET generation=generation+1 WHERE scan_id=?',(scan_id,))
        return {'generation':current+1,'items':[], 'limits':self.limits}
