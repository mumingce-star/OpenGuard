"""Private SQLite conversations, immutable request identities and persisted events."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import time
from uuid import uuid4
from app.p2.store import P2Store
from app.p2.contract import canonical, digest, P2Error

VERSION='openguard-assistant/1'
TERMINAL={'completed','stopped','failed'}
LIMITS={'total_call_limit':None,'max_requests_per_minute':10,'concurrent':1,
        'request_timeout_seconds':120,'max_question_chars':8000,'project_max_question_chars':2000}

def utc():return datetime.now(timezone.utc).isoformat()

class AssistantError(Exception):
    def __init__(self,code,status=409):self.code,self.status=code,status;super().__init__(code)

class AssistantStore(P2Store):
    def guard(self):
        if self.path.name!='assistant.db':raise AssistantError('assistant_storage_invalid',503)
        for path in (self.path.parent,self.path):
            info=path.lstat()
            if (stat.S_ISLNK(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o077
                or path==self.path and (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1)):
                raise AssistantError('assistant_storage_invalid',503)
    def initialize(self):
        self.path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        if not self.path.exists():
            fd=os.open(self.path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.close(fd)
        with self.connection(write=True) as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS assistant_conversations(
                id TEXT PRIMARY KEY,request_id TEXT UNIQUE,fingerprint TEXT NOT NULL,payload BLOB NOT NULL,sha256 TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS assistant_messages(
                seq INTEGER PRIMARY KEY AUTOINCREMENT,cid TEXT NOT NULL,request_id TEXT NOT NULL,role TEXT NOT NULL,
                fingerprint TEXT NOT NULL,created_epoch REAL NOT NULL,payload BLOB NOT NULL,sha256 TEXT NOT NULL,
                UNIQUE(cid,request_id,role));
                CREATE TABLE IF NOT EXISTS assistant_events(cid TEXT,request_id TEXT,seq INTEGER,payload BLOB NOT NULL,sha256 TEXT NOT NULL,
                PRIMARY KEY(cid,request_id,seq));
                CREATE TABLE IF NOT EXISTS assistant_audit(cid TEXT,request_id TEXT,payload BLOB NOT NULL,sha256 TEXT NOT NULL,
                PRIMARY KEY(cid,request_id));''')
        # Factory-only recovery: never replay an interrupted generation from GET.
        with self.connection() as db:
            rows=db.execute("SELECT cid,request_id,payload,sha256 FROM assistant_messages WHERE role='assistant'").fetchall()
        for cid,rid,raw,sha in rows:
            if self.decode((raw,sha))['status'] not in TERMINAL:
                self.finish(cid,rid,'failed',error='assistant_interrupted_no_retry')
    @staticmethod
    def _save(db,table,identity,value):
        raw=canonical(value)
        if table=='assistant_conversations':db.execute('UPDATE assistant_conversations SET payload=?,sha256=? WHERE id=?',(raw,hashlib.sha256(raw).hexdigest(),identity))
    def _conversation(self,db,cid):
        row=db.execute('SELECT payload,sha256 FROM assistant_conversations WHERE id=?',(cid,)).fetchone()
        if row is None:raise AssistantError('assistant_conversation_not_found',404)
        return self.decode(row)
    def conversation(self,cid):
        with self.connection() as db:return self._conversation(db,cid)
    def create(self,request_id,context):
        fingerprint=digest({'context':context})
        with self.connection(write=True) as db:
            old=db.execute('SELECT fingerprint,payload,sha256 FROM assistant_conversations WHERE request_id=?',(request_id,)).fetchone()
            if old:
                if old[0]!=fingerprint:raise AssistantError('assistant_idempotency_conflict',409)
                return self.decode(old[1:])
            stamp=utc();value={'id':'chat_'+uuid4().hex,'title':'新对话','created_at':stamp,'updated_at':stamp,'context':context}
            raw=canonical(value)
            db.execute('INSERT INTO assistant_conversations VALUES(?,?,?,?,?)',(value['id'],request_id,fingerprint,raw,hashlib.sha256(raw).hexdigest()))
            return value
    def conversations(self,cursor=None,limit=100):
        before=float(cursor) if cursor else float('inf')
        with self.connection() as db:
            rows=db.execute('SELECT rowid,payload,sha256 FROM assistant_conversations WHERE rowid<? ORDER BY rowid DESC LIMIT ?',(before,limit+1)).fetchall()
        return {'schema_version':VERSION,'items':[self.decode(r[1:]) for r in rows[:limit]],'limits':LIMITS,
                'has_more':len(rows)>limit,'cursor':str(rows[limit-1][0]) if len(rows)>limit else None}
    def messages(self,cid,cursor=None,limit=100):
        with self.connection() as db:
            conv=self._conversation(db,cid)
            rows=db.execute('SELECT seq,payload,sha256 FROM assistant_messages WHERE cid=? AND seq<? ORDER BY seq DESC LIMIT ?',
                            (cid,int(cursor) if cursor else 9223372036854775807,limit+1)).fetchall()
        return {'schema_version':VERSION,'conversation':conv,'items':[self.decode(r[1:]) for r in reversed(rows[:limit])],
                'limits':LIMITS,'has_more':len(rows)>limit,'cursor':str(rows[limit-1][0]) if len(rows)>limit else None,
                'context_policy':{'max_recent_characters':30000,'max_output_characters':24000,
                'description':'完整历史保存在本账号；模型只接收最近有界上下文，不执行隐藏摘要。','model_receives_full_history':False}}
    def history(self,cid):
        # Only bounded recent records are loaded into inference memory; persisted history is paginated separately.
        with self.connection() as db:
            rows=db.execute('SELECT payload,sha256 FROM assistant_messages WHERE cid=? ORDER BY seq DESC LIMIT 40',(cid,)).fetchall()
        return list(reversed([self.decode(r) for r in rows]))
    def existing(self,cid,request_id,body=None):
        with self.connection() as db:
            self._conversation(db,cid)
            row=db.execute("SELECT fingerprint,payload,sha256 FROM assistant_messages WHERE cid=? AND request_id=? AND role='assistant'",(cid,request_id)).fetchone()
        if row is None:return None
        if body is not None and row[0]!=digest(body):raise AssistantError('assistant_idempotency_conflict',409)
        return self.decode(row[1:])
    def _event(self,db,cid,rid,kind,**kwargs):
        seq=db.execute('SELECT COALESCE(MAX(seq),0)+1 FROM assistant_events WHERE cid=? AND request_id=?',(cid,rid)).fetchone()[0]
        value={'seq':seq,'type':kind,**kwargs};raw=canonical(value)
        db.execute('INSERT INTO assistant_events VALUES(?,?,?,?,?)',(cid,rid,seq,raw,hashlib.sha256(raw).hexdigest()))
    def reserve(self,cid,rid,question):
        body={'request_id':rid,'message':question};fingerprint=digest(body)
        with self.connection(write=True) as db:
            conv=self._conversation(db,cid)
            old=db.execute("SELECT fingerprint,payload,sha256 FROM assistant_messages WHERE cid=? AND request_id=? AND role='assistant'",(cid,rid)).fetchone()
            if old:
                if old[0]!=fingerprint:raise AssistantError('assistant_idempotency_conflict',409)
                return self.decode(old[1:]),False
            count=db.execute("SELECT COUNT(*) FROM assistant_messages WHERE role='assistant' AND created_epoch>?",(time.time()-60,)).fetchone()[0]
            if count>=10:raise AssistantError('assistant_rate_limited',429)
            rows=db.execute("SELECT payload,sha256 FROM assistant_messages WHERE role='assistant' AND cid=? ORDER BY seq DESC LIMIT 1",(cid,)).fetchall()
            if any(self.decode(row)['status'] not in TERMINAL for row in rows):raise AssistantError('assistant_conversation_busy',409)
            stamp=utc()
            base={'request_id':rid,'created_at':stamp,'error_code':None,'citations':[]}
            user={**base,'id':'msg_'+uuid4().hex,'role':'user','text':question,'status':'completed'}
            answer={**base,'id':'msg_'+uuid4().hex,'role':'assistant','text':'','status':'pending'}
            for value in (user,answer):
                raw=canonical(value);db.execute('INSERT INTO assistant_messages(cid,request_id,role,fingerprint,created_epoch,payload,sha256) VALUES(?,?,?,?,?,?,?)',
                    (cid,rid,value['role'],fingerprint,time.time(),raw,hashlib.sha256(raw).hexdigest()))
            conv['updated_at']=stamp
            if conv['title']=='新对话':conv['title']=' '.join(question.split())[:40]
            self._save(db,'assistant_conversations',cid,conv)
            self._event(db,cid,rid,'start')
            return answer,True
    def delta(self,cid,rid,text):
        with self.connection(write=True) as db:
            row=db.execute("SELECT payload,sha256 FROM assistant_messages WHERE cid=? AND request_id=? AND role='assistant'",(cid,rid)).fetchone()
            value=self.decode(row)
            if value is None or value['status'] in TERMINAL:return False
            value.update(text=value['text']+text,status='streaming')
            if len(value['text'])>24000:raise AssistantError('assistant_output_limit',413)
            raw=canonical(value);db.execute("UPDATE assistant_messages SET payload=?,sha256=? WHERE cid=? AND request_id=? AND role='assistant'",(raw,hashlib.sha256(raw).hexdigest(),cid,rid))
            self._event(db,cid,rid,'delta',text=text);return True
    def finish(self,cid,rid,status,*,error=None,text=None,citations=None):
        with self.connection(write=True) as db:
            row=db.execute("SELECT payload,sha256 FROM assistant_messages WHERE cid=? AND request_id=? AND role='assistant'",(cid,rid)).fetchone()
            value=self.decode(row)
            if value is None:raise AssistantError('assistant_message_not_found',404)
            if value['status'] in TERMINAL:return value
            value.update(status=status,error_code=error)
            if text is not None:value['text']=text
            if citations is not None:value['citations']=citations
            raw=canonical(value);db.execute("UPDATE assistant_messages SET payload=?,sha256=? WHERE cid=? AND request_id=? AND role='assistant'",(raw,hashlib.sha256(raw).hexdigest(),cid,rid))
            self._event(db,cid,rid,{'completed':'final','stopped':'stopped','failed':'error'}[status],message=value)
            conv=self._conversation(db,cid);conv['updated_at']=utc();self._save(db,'assistant_conversations',cid,conv)
            return value
    def events(self,cid,rid,after):
        with self.connection() as db:
            self._conversation(db,cid)
            row=db.execute("SELECT payload,sha256 FROM assistant_messages WHERE cid=? AND request_id=? AND role='assistant'",(cid,rid)).fetchone()
            if row is None:raise AssistantError('assistant_message_not_found',404)
            rows=db.execute('SELECT payload,sha256 FROM assistant_events WHERE cid=? AND request_id=? AND seq>? ORDER BY seq',(cid,rid,after)).fetchall()
            return [self.decode(r) for r in rows],self.decode(row)['status'] in TERMINAL
    def audit(self,cid,rid,value):
        raw=canonical(value)
        with self.connection(write=True) as db:db.execute('INSERT OR REPLACE INTO assistant_audit VALUES(?,?,?,?)',(cid,rid,raw,hashlib.sha256(raw).hexdigest()))
