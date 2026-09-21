"""Explicit, durable V4 jobs. No read endpoint invokes models or scanners."""
from __future__ import annotations
from contextlib import closing
from datetime import datetime,timezone
import hashlib,json,threading,time,uuid,shutil
from app.ai.project import PROMPT_VERSION, context, validate, canonical
from app.domain.usage import UsageDeclaration
from .engine import build_assessment
from .store import AssessmentStore,AssessmentStoreError
from .chat import ChatStore

ERRORS={
 'chat_busy':'当前任务正在生成答复，请等待后再发送。',
 'model_busy':'本地模型正在处理扫描或其他问答，请稍后重试。',
 'chat_capacity_exceeded':'聊天容量已满；历史已保留，请先确认清空当前聊天再发送。',
 'project_context_limit':'当前项目摘要与历史超出模型输入预算；正式评估和证据仍可读取。',
 'assessment_capacity_exceeded':'评估存储容量不足；已有扫描、聊天和报告均保留。',
 'project_failed':'AI说明暂不可用：模型未返回有效且符合证据约束的完整答复。',
}

class AssessmentService:
    def __init__(self,registry,store:AssessmentStore,provider=None):
        self.registry,self.store,self.provider=registry,store,provider
        self.chat=ChatStore(store)
        self._lock=threading.RLock()
        self._slots=threading.BoundedSemaphore(2)

    def initialize(self):
        self.store.initialize();self.chat.initialize()
        with closing(self.store._connect()) as db,db:
            db.execute('''CREATE TABLE IF NOT EXISTS assessment_jobs(scan_id TEXT NOT NULL,request_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL,status TEXT NOT NULL,assessment_id TEXT,error TEXT,created_at TEXT NOT NULL,
                elapsed_seconds REAL,model_calls INTEGER NOT NULL DEFAULT 0,cache_hit INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(scan_id,request_id))''')
            db.execute("UPDATE assessment_jobs SET status='failed',error='服务中断，未生成完整评估；可显式重新评估。' WHERE status='pending'")

    def run(self,sid):
        return self.registry.get(sid).run

    def job(self,sid,rid):
        rows=self.store._read('SELECT request_id,status,assessment_id,error,created_at,elapsed_seconds,model_calls,cache_hit FROM assessment_jobs WHERE scan_id=? AND request_id=?',(sid,rid))
        return dict(zip(('request_id','status','assessment_id','error','created_at','elapsed_seconds','model_calls','cache_hit'),rows[0])) if rows else None

    def reserve_assessment(self,sid,usage,rid):
        run=self.run(sid)
        if run.status.value not in ('completed','partial','failed','cancelled'):
            raise AssessmentStoreError('assessment_scan_not_ready')
        usage=usage or run.project.usage or UsageDeclaration()
        model=getattr(getattr(self.provider,'producer',None),'model_id',None) or 'none'
        latest=self.store.latest(sid)
        candidate=build_assessment(run,usage,version=latest.version+1 if latest else 1,model_version=model,prompt_version=PROMPT_VERSION)
        with self._lock,closing(self.store._connect()) as db,db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT fingerprint FROM assessment_jobs WHERE scan_id=? AND request_id=?',(sid,rid)).fetchone()
            if old:
                if old[0]!=candidate.cache_key:raise AssessmentStoreError('assessment_idempotency_conflict')
                return self.job(sid,rid),None
            if db.execute("SELECT 1 FROM assessment_jobs WHERE scan_id=? AND status='pending'",(sid,)).fetchone():
                raise AssessmentStoreError('assessment_busy')
            if db.execute('SELECT count(*) FROM assessment_jobs').fetchone()[0]>=10000:
                raise AssessmentStoreError('assessment_capacity_exceeded')
            if shutil.disk_usage(self.store.path.parent).free < self.store.min_free_bytes + self.store.max_record_bytes:
                raise AssessmentStoreError('assessment_capacity_exceeded')
            if not self._slots.acquire(blocking=False):raise AssessmentStoreError('model_busy')
            try:
                db.execute("INSERT INTO assessment_jobs VALUES (?,?,?,'pending',NULL,NULL,?,NULL,0,0)",(sid,rid,candidate.cache_key,datetime.now(timezone.utc).isoformat()))
                db.commit()
            except Exception:
                self._slots.release();raise
        return self.job(sid,rid),(run,candidate,rid)

    def generate_assessment(self,run,candidate,rid):
        started=time.monotonic();calls=0;cached=False
        try:
            matches=self.store._read('SELECT a.id FROM assessments a JOIN assessment_jobs j ON a.id=j.assessment_id WHERE a.scan_id=? AND j.fingerprint=? ORDER BY a.version DESC',(run.id,candidate.cache_key))
            prior=[self.store.get(run.id,row[0]) for row in matches]
            reusable=next((a for a in prior if a.ai_status not in ('fallback','failed')),None)
            if reusable is not None:
                candidate=reusable;cached=True
            else:
                if prior:
                    retry_key=hashlib.sha256((candidate.cache_key+':retry:'+rid).encode()).hexdigest()
                    candidate=candidate.model_copy(update={'cache_key':retry_key,'id':'asm_'+str(uuid.uuid5(uuid.NAMESPACE_URL,retry_key+':'+str(candidate.version)))})
            if not cached and self.provider is not None:
                try:
                    if self.registry.active_count():raise AssessmentStoreError('model_busy')
                    payload=context(run,candidate,'请概括当前项目在声明用途下的整体结论、最重要的原因和接下来应核对的材料。',[])
                    calls=1
                    reply=validate(self.provider.generate_project(payload,30.0),payload)
                    candidate=candidate.model_copy(update={'ai_status':'succeeded','ai_summary':reply['answer'],'ai_evidence_ids':reply['evidence_ids']})
                except Exception:
                    candidate=candidate.model_copy(update={'ai_status':'fallback','ai_summary':None})
            saved=self.store.create(candidate,idempotency_key=rid,run=run)
            with closing(self.store._connect()) as db,db:
                db.execute("UPDATE assessment_jobs SET status='succeeded',assessment_id=?,elapsed_seconds=?,model_calls=?,cache_hit=? WHERE scan_id=? AND request_id=?",(saved.id,time.monotonic()-started,calls,int(cached),run.id,rid))
        except Exception as e:
            code=getattr(e,'code','project_failed')
            with closing(self.store._connect()) as db,db:
                db.execute("UPDATE assessment_jobs SET status='failed',error=?,elapsed_seconds=?,model_calls=? WHERE scan_id=? AND request_id=?",(ERRORS.get(code,'评估未保存成功；旧扫描与报告保留。'),time.monotonic()-started,calls,run.id,rid))
        finally:self._slots.release()

    def on_terminal(self,run):
        # Called after the existing terminal commit, not by a GET or on old-run startup.
        try:
            _,work=self.reserve_assessment(run.id,run.project.usage,'initial-'+run.id)
            if work:self.generate_assessment(*work)
        except Exception:
            # Never rewrite a scan terminal because its independent assessment failed.
            return

    def reserve_chat(self,sid,aid,rid,message,generation):
        self.run(sid)
        a=self.store.get(sid,aid)
        if a is None:raise AssessmentStoreError('assessment_not_found')
        with self._lock:
            existing=next((x for x in self.chat.history(sid)['items'] if x['request_id']==rid),None)
            if existing:
                return self.chat.reserve(sid,aid,rid,message,generation)[0],None
            if self.provider is None:raise AssessmentStoreError('project_ai_disabled')
            if self.registry.active_count():raise AssessmentStoreError('model_busy')
            if not self._slots.acquire(blocking=False):raise AssessmentStoreError('model_busy')
            try:
                turn,created=self.chat.reserve(sid,aid,rid,message,generation)
            except Exception:
                self._slots.release();raise
            if not created:self._slots.release();return turn,None
            return turn,(sid,a,rid,message,generation)

    def generate_chat(self,sid,a,rid,message,generation):
        started=time.monotonic()
        try:
            history=self.chat.history(sid)['items']
            payload=context(self.run(sid),a,message,[h for h in history if h['assessment_id']==a.id])
            result=validate(self.provider.generate_project(payload,30.0),payload)
            self.chat.finish(sid,rid,generation,answer=result['answer'],evidence_ids=result['evidence_ids'],elapsed_seconds=time.monotonic()-started)
        except Exception as e:
            code=getattr(e,'code',str(e))
            self.chat.finish(sid,rid,generation,error=ERRORS.get(code,ERRORS['project_failed']),elapsed_seconds=time.monotonic()-started)
        finally:self._slots.release()
