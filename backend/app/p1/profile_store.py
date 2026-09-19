"""Explicit, fail-closed metadata sidecar. Only validated normalized DTOs persist."""
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
from urllib.parse import quote
from uuid import uuid4
from .profile_models import MetadataObservation, RefreshJob

VERSION=1
ALGORITHM='resource-profile/1'


class ProfileError(RuntimeError):
    def __init__(self,code):
        self.code=code
        super().__init__(code)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()


def digest(value): return hashlib.sha256(canonical(value)).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')


def semantic(observation):
    value=json.loads(canonical(observation))
    value.pop('observation_id',None)
    value.pop('fetched_at',None)
    value['provenance'].pop('generated_at',None)
    return value


DDL='''
CREATE TABLE metadata_observations (
 observation_id TEXT PRIMARY KEY NOT NULL, scan_id TEXT NOT NULL,
 resource_id TEXT NOT NULL, facts_hash TEXT NOT NULL,
 observation_json TEXT NOT NULL, observation_hash TEXT NOT NULL,
 semantic_hash TEXT NOT NULL);
CREATE INDEX observation_scope ON metadata_observations(scan_id,resource_id,facts_hash,observation_id);
CREATE TABLE profile_refresh_jobs (
 job_id TEXT PRIMARY KEY NOT NULL, scan_id TEXT NOT NULL,
 job_json TEXT NOT NULL, job_hash TEXT NOT NULL,
 claimed INTEGER NOT NULL CHECK(claimed IN (0,1)));
CREATE TABLE profile_refresh_requests (
 scan_id TEXT NOT NULL, request_key TEXT NOT NULL, fingerprint TEXT NOT NULL,
 job_id TEXT NOT NULL REFERENCES profile_refresh_jobs(job_id),
 PRIMARY KEY(scan_id,request_key));
'''


class MetadataStore:
    def __init__(self,path,*,min_free_bytes=512*1024*1024,max_database_bytes=128*1024*1024):
        self.path=Path(path).absolute()
        self.min_free_bytes=min_free_bytes
        self.max_database_bytes=max_database_bytes
        if min_free_bytes<0 or max_database_bytes<65536: raise ValueError('invalid capacity')

    def _guard(self):
        if self.path.name!='metadata.db' or any(p.is_symlink() for p in (self.path,*self.path.parents)):
            raise ProfileError('upstream_unavailable')
        if not self.path.parent.exists(): return False
        info=self.path.parent.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:
            raise ProfileError('upstream_unavailable')
        for p in (self.path,*(Path(str(self.path)+s) for s in ('-wal','-shm','-journal'))):
            if p.is_symlink(): raise ProfileError('upstream_unavailable')
            if p.exists():
                st=p.stat()
                if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.getuid() or st.st_nlink!=1 or st.st_mode&0o077:
                    raise ProfileError('upstream_unavailable')
        return self.path.exists()

    @staticmethod
    def _schema(db):
        # Exact implementation-owned schema, including indexes/constraints;
        # compare with an in-memory reference, never migrate an unknown DB.
        query="SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
        with closing(sqlite3.connect(':memory:')) as expected:
            expected.executescript(DDL)
            if db.execute(query).fetchall()!=expected.execute(query).fetchall() or db.execute('PRAGMA user_version').fetchone()[0]!=VERSION:
                raise ProfileError('upstream_unavailable')

    @contextmanager
    def connection(self,*,write=False):
        db=None
        try:
            if not self._guard(): raise ProfileError('upstream_unavailable')
            db=sqlite3.connect(f"file:{quote(str(self.path),safe='/')}?mode={'rw' if write else 'ro'}",uri=True,timeout=2)
            db.execute('PRAGMA busy_timeout=2000')
            db.execute('PRAGMA foreign_keys=ON')
            if not write: db.execute('PRAGMA query_only=ON')
            self._schema(db)
            if write:
                db.execute('PRAGMA synchronous=FULL')
                db.execute(f'PRAGMA max_page_count={self.max_database_bytes//db.execute("PRAGMA page_size").fetchone()[0]}')
                db.execute('BEGIN IMMEDIATE')
            yield db
            if write: db.commit()
        except ProfileError: raise
        except (OSError,sqlite3.Error,ValueError,TypeError,KeyError):
            raise ProfileError('upstream_unavailable') from None
        finally:
            if db is not None: db.close()

    def initialize(self):
        if self._guard():
            with self.connection(): pass
            return
        self.path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        self._guard()
        if shutil.disk_usage(self.path.parent).free<self.min_free_bytes+65536:
            raise ProfileError('upstream_unavailable')
        try:
            fd=os.open(self.path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
            os.close(fd)
            with closing(sqlite3.connect(self.path)) as db:
                db.executescript('BEGIN IMMEDIATE;'+DDL+f'PRAGMA user_version={VERSION};COMMIT;')
        except (OSError,sqlite3.Error): raise ProfileError('upstream_unavailable') from None

    def _capacity(self,db,size):
        used=db.execute('PRAGMA page_count').fetchone()[0]*db.execute('PRAGMA page_size').fetchone()[0]
        if size>128*1024 or used+size+16384>self.max_database_bytes or shutil.disk_usage(self.path.parent).free<self.min_free_bytes+size+16384:
            raise ProfileError('upstream_unavailable')

    @staticmethod
    def _decode(text,sha,model):
        value=json.loads(text)
        if digest(value)!=sha: raise ProfileError('upstream_unavailable')
        return model.model_validate(value).model_dump(mode='json')

    def observations(self,scan_id,resource_id,facts_hash):
        if not self._guard(): return []
        with self.connection() as db:
            result=[]
            rows=db.execute('SELECT observation_id,observation_json,observation_hash,semantic_hash FROM metadata_observations WHERE scan_id=? AND resource_id=? AND facts_hash=? ORDER BY observation_id LIMIT 257',(scan_id,resource_id,facts_hash)).fetchall()
            if len(rows)>256: raise ProfileError('upstream_unavailable')
            for oid,text,sha,sem in rows:
                value=self._decode(text,sha,MetadataObservation)
                if value['observation_id']!=oid or digest(semantic(value))!=sem or any(r['scan_id']!=scan_id or r['facts_hash']!=facts_hash for r in value['provenance']['source_refs']):
                    raise ProfileError('upstream_unavailable')
                result.append(value)
            return result

    def _job(self,db,scan_id,job_id):
        row=db.execute('SELECT job_json,job_hash FROM profile_refresh_jobs WHERE scan_id=? AND job_id=?',(scan_id,job_id)).fetchone()
        if row is None: raise ProfileError('not_found')
        value=self._decode(*row,RefreshJob)
        if value['scan_id']!=scan_id or value['job_id']!=job_id: raise ProfileError('upstream_unavailable')
        return value

    def job(self,scan_id,job_id):
        with self.connection() as db: return self._job(db,scan_id,job_id)

    def reserve(self,scan_id,request):
        fp=digest(request.model_dump(exclude={'idempotency_key'}))
        with self.connection(write=True) as db:
            existing=db.execute('SELECT fingerprint,job_id FROM profile_refresh_requests WHERE scan_id=? AND request_key=?',(scan_id,request.idempotency_key)).fetchone()
            if existing:
                if existing[0]!=fp: raise ProfileError('conflict')
                return self._job(db,scan_id,existing[1]),False
            job=RefreshJob(job_id='prj_'+uuid4().hex,scan_id=scan_id,facts_hash=request.expected_facts_hash,
                resource_ids=request.resource_ids,status='pending',items=[dict(resource_id=r,status='pending',observation_id=None,error_code=None) for r in request.resource_ids],
                created_at=now(),completed_at=None,algorithm_version=ALGORITHM).model_dump(mode='json')
            data=canonical(job).decode()
            self._capacity(db,len(data.encode()))
            db.execute('INSERT INTO profile_refresh_jobs VALUES (?,?,?,?,0)',(job['job_id'],scan_id,data,digest(job)))
            db.execute('INSERT INTO profile_refresh_requests VALUES (?,?,?,?)',(scan_id,request.idempotency_key,fp,job['job_id']))
            return job,True

    def claim(self,scan_id,job_id):
        with self.connection(write=True) as db:
            job=self._job(db,scan_id,job_id)
            return job if db.execute('UPDATE profile_refresh_jobs SET claimed=1 WHERE job_id=? AND claimed=0',(job_id,)).rowcount==1 else None

    def finish_item(self,scan_id,job_id,resource_id,observation=None,error=None):
        with self.connection(write=True) as db:
            job=self._job(db,scan_id,job_id)
            item=next((x for x in job['items'] if x['resource_id']==resource_id),None)
            if item is None or item['status']!='pending': raise ProfileError('conflict')
            if observation is not None:
                value=MetadataObservation.model_validate(observation).model_dump(mode='json')
                oid=value['observation_id']; sem=digest(semantic(value))
                row=db.execute('SELECT scan_id,resource_id,facts_hash,observation_json,observation_hash,semantic_hash FROM metadata_observations WHERE observation_id=?',(oid,)).fetchone()
                if row:
                    stored=self._decode(row[3],row[4],MetadataObservation)
                    if tuple(row[:3])!=(scan_id,resource_id,job['facts_hash']) or row[5]!=sem or semantic(stored)!=semantic(value):
                        raise ProfileError('conflict')
                else:
                    data=canonical(value).decode(); self._capacity(db,len(data.encode()))
                    db.execute('INSERT INTO metadata_observations VALUES (?,?,?,?,?,?,?)',(oid,scan_id,resource_id,job['facts_hash'],data,digest(value),sem))
                item.update(status='succeeded',observation_id=oid,error_code=None)
            else:
                from app.ingestion.metadata_types import ErrorCode
                safe={e.value for e in ErrorCode}|{'metadata_invalid','conflict','not_ready','not_comparable'}
                item.update(status='failed',observation_id=None,error_code=error if error in safe else 'upstream_unavailable')
            if all(i['status']!='pending' for i in job['items']):
                job['status']='succeeded' if all(i['status']=='succeeded' for i in job['items']) else 'failed'
                job['completed_at']=now()
            job=RefreshJob.model_validate(job).model_dump(mode='json')
            self._capacity(db,len(canonical(job)))
            db.execute('UPDATE profile_refresh_jobs SET job_json=?,job_hash=? WHERE job_id=?',(canonical(job).decode(),digest(job),job_id))
