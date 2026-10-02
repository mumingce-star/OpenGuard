"""A4-2 actual-saved boundary, recovery, fixed Report and read-only gates."""
from dataclasses import replace
import hashlib
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from app.assessment.service import AssessmentService
from app.assessment.engine import facts_digest
from app.p1.notice_source_store import BoundNoticeSourceReader, NoticeSourceStore, NoticeSourceBindingService, NoticeSourceStoreError
from app.assessment.store import AssessmentStore
from app.api import create_default_app
from test_p1_notice_lifecycle_ingestion import env,lifecycle,rows
from test_p1_notice_lifecycle_terminal import execute
from test_p1_notice_draft_production_wiring import configure


def service(e,observer=None):
    s=AssessmentService(e.registry,e.assessments,assessment_saved_observer=observer)
    s.initialize();return s


def generate(s,run,rid="explicit-one"):
    _,work=s.reserve_assessment(run.id,run.project.usage,rid)
    if work:s.generate_assessment(*work)
    job=s.job(run.id,rid)
    return job,s.store.get(run.id,job["assessment_id"]) if job["assessment_id"] else None


def bound(e,saved):
    return BoundNoticeSourceReader(e.source_store).read(saved.scan_id,saved.facts_hash,saved.id,saved.version)


def test_w17_saved_callback_uses_actual_identity_and_cached_saved_version(env):
    e=env;result,_,lc=execute(e);seen=[]
    s=None
    def observe(saved):
        assert s.job(saved.scan_id,current[0])["status"]=="succeeded"
        assert s._slots.acquire(blocking=False);s._slots.release()
        assert e.assessments.get(saved.scan_id,saved.id)==saved
        seen.append(saved);lc.on_assessment_saved(saved)
    s=service(e,observe);current=["one"]
    _,a=generate(s,result.run,current[0]);current[0]="two"
    _,b=generate(s,result.run,current[0])
    assert a.id==b.id and a.version==b.version==1
    assert [x.id for x in seen]==[a.id,b.id]
    assert bound(e,a) is not None


@pytest.mark.parametrize("fault", ["bind", "diagnostic", "observer"])
def test_w18_observer_bind_failure_never_reclassifies_success_or_leaks_slot(env,monkeypatch,fault):
    e=env;lc=lifecycle(e);result,_,_=execute(e,lc=lc)
    def failure(*a,**k):raise OSError("controlled observer failure")
    if fault=="bind":monkeypatch.setattr(lc.binding,"bind",failure)
    if fault=="diagnostic":
        lc.diagnostic=failure;monkeypatch.setattr(lc.binding,"bind",failure)
    s=service(e,failure if fault=="observer" else lc.on_assessment_saved)
    before=e.registry.get(result.run.id)
    job,a=generate(s,result.run)
    assert job["status"]=="succeeded" and job["error"] is None and a is not None
    assert e.registry.get(result.run.id)==before
    assert s._slots.acquire(blocking=False) and s._slots.acquire(blocking=False)
    s._slots.release();s._slots.release()


def test_w19_create_failure_retains_stage_later_explicit_generation_binds(env,monkeypatch):
    e=env;result,_,lc=execute(e);s=service(e,lc.on_assessment_saved)
    real=e.assessments.create
    def failure(*a,**k):raise OSError("save failure")
    monkeypatch.setattr(e.assessments,"create",failure)
    job,a=generate(s,result.run,"first-failed")
    assert job["status"]=="failed" and a is None
    assert e.source_store._read_staged(result.run.id) is not None
    monkeypatch.setattr(e.assessments,"create",real)
    job,a=generate(s,result.run,"later-explicit")
    assert job["status"]=="succeeded" and bound(e,a) is not None


@pytest.mark.parametrize("boundary", ["update", "commit"])
def test_w17_no_observer_after_saved_assessment_but_job_persistence_fails(env,monkeypatch,boundary):
    e=env;result,_,lc=execute(e);seen=[];s=service(e,lambda a:seen.append(a))
    _,work=s.reserve_assessment(result.run.id,None,"job-boundary")
    real=e.assessments._connect;armed=[True]
    class Connection:
        marked=False
        def __init__(self,db):self.db=db
        def __enter__(self):self.db.__enter__();return self
        def __exit__(self,kind,error,trace):
            if self.marked:
                armed[0]=False;failure=OSError("controlled job commit failure")
                self.db.__exit__(OSError,failure,None);raise failure
            return self.db.__exit__(kind,error,trace)
        def close(self):self.db.close()
        def execute(self,query,*args):
            if armed[0] and "UPDATE assessment_jobs SET status='succeeded'" in query:
                if boundary=="update":armed[0]=False;raise OSError("controlled job update failure")
                self.marked=True
            return self.db.execute(query,*args)
        def __getattr__(self,name):return getattr(self.db,name)
    monkeypatch.setattr(e.assessments,"_connect",lambda *a,**kw:Connection(real(*a,**kw)))
    s.generate_assessment(*work)
    assert e.assessments.list(result.run.id) and seen==[]
    assert s.job(result.run.id,"job-boundary")["status"]=="failed"
    assert e.source_store._read_staged(result.run.id) is not None
    assert s._slots.acquire(blocking=False) and s._slots.acquire(blocking=False)
    s._slots.release();s._slots.release()


def test_w19_idempotent_request_and_read_job_do_not_notify_or_rebind(env):
    e=env;result,_,lc=execute(e);seen=[]
    s=service(e,lambda saved:(seen.append(saved.id),lc.on_assessment_saved(saved)))
    _,a=generate(s,result.run,"once")
    before=rows(e.path)
    job,work=s.reserve_assessment(result.run.id,None,"once")
    assert work is None and job["status"]=="succeeded"
    assert s.job(result.run.id,"once")==job and seen==[a.id] and rows(e.path)==before


def test_w20_store_restart_no_batch_bind_explicit_saved_event_binds(env):
    e=env;result,_,_=execute(e)
    new_source=NoticeSourceStore(e.source_store.path,min_free_bytes=0)
    new_assessment=AssessmentStore(e.assessments.path,min_free_bytes=0)
    from app.p1.notice_source_lifecycle import NoticeSourceLifecycle
    lc=NoticeSourceLifecycle(e.registry,new_assessment,new_source)
    before=rows(e.path);s=AssessmentService(e.registry,new_assessment,assessment_saved_observer=lc.on_assessment_saved);s.initialize()
    assert rows(e.path)["notice_source.db"]==before["notice_source.db"]
    job,a=generate(s,result.run,"explicit-after-restart")
    assert job["status"]=="succeeded" and bound(e,a) is not None


def test_w20_pending_assessment_restart_keeps_existing_failed_job_policy_no_bind(env):
    e=env;result,_,lc=execute(e);s=service(e,lc.on_assessment_saved)
    job,work=s.reserve_assessment(result.run.id,None,"interrupted-job")
    assert job["status"]=="pending";s._slots.release()  # simulate loss of the old process, not job execution
    before=rows(e.path)["notice_source.db"]
    restarted=service(e,lc.on_assessment_saved)
    assert restarted.job(result.run.id,"interrupted-job")["status"]=="failed"
    assert rows(e.path)["notice_source.db"]==before
    job,a=generate(restarted,result.run,"new-explicit-job")
    assert job["status"]=="succeeded" and bound(e,a) is not None


@pytest.mark.parametrize("fault", ["missing", "hash", "revision", "permissions"])
def test_w21_recovery_fail_closed_no_hash_refresh_retry(env,monkeypatch,fault):
    e=env;result,_,lc=execute(e);s=service(e);_,a=generate(s,result.run)
    attempts=[];real=lc.binding.bind
    def spy(*args,**kw):attempts.append(kw);return real(*args,**kw)
    monkeypatch.setattr(lc.binding,"bind",spy)
    if fault=="missing":monkeypatch.setattr(lc.staged_reader,"read",lambda _:None)
    if fault=="hash":
        staged=lc.staged_reader.read(result.run.id);monkeypatch.setattr(lc.staged_reader,"read",lambda _:replace(staged,package_hash="0"*64))
    if fault=="revision":
        original=e.registry.get;monkeypatch.setattr(e.registry,"get",lambda sid:replace(original(sid),revision=original(sid).revision+1) if len(attempts)==0 else original(sid))
    if fault=="permissions":e.source_store.path.chmod(0o644)
    before=rows(e.path);lc.on_assessment_saved(a)
    assert rows(e.path)==before
    assert len(attempts)<=1
    if fault=="permissions":e.source_store.path.chmod(0o600)
    assert bound(e,a) is None


def test_w22_exact_replay_bound_freeze_and_independent_assessment_identity(env):
    e=env;result,_,lc=execute(e);s=service(e,lc.on_assessment_saved);_,a=generate(s,result.run)
    before=rows(e.path);lc.on_assessment_saved(a);assert rows(e.path)==before
    original=bound(e,a);assert original is not None
    from test_p1_diff_api import assessment
    e.store=e.assessments
    other=assessment(e,result.run,usage="service",version=2)
    lc.on_assessment_saved(other)
    assert bound(e,other).assessment_id==other.id and bound(e,a)==original


def test_w23_w24_real_lifecycle_to_draft_report_and_idle_get_restart_immutable(env,monkeypatch):
    e=env;result,_,lc=execute(e);s=service(e,lc.on_assessment_saved);_,a=generate(s,result.run)
    assert bound(e,a) is not None
    from app.notice_source import validate_notice_source_package
    value=json.loads(bound(e,a).canonical_package_bytes);value["package_hash"]=bound(e,a).package_hash
    assert validate_notice_source_package(value).package_hash==bound(e,a).package_hash
    configure(monkeypatch,e.path)
    app=create_default_app();base=f"/api/v1/scans/{result.run.id}/assessments/{a.id}"
    with TestClient(app) as client:
        d=client.post(base+"/notice-drafts",json={"idempotency_key":"owned-draft"});assert d.status_code==200,d.text
        draft=d.json();assert draft["generator_version"]=="notice-bound/1.0"
        r=client.post(base+"/report-v2",json={"idempotency_key":"owned-report","notice_refs":[{"draft_id":draft["draft_id"],"content_hash":draft["content_hash"]}]})
        assert r.status_code==200,r.text;report=r.json()
        artifacts={item["href"]:client.get(item["href"]).content for item in report["artifacts"]}
        for item in report["artifacts"]:assert hashlib.sha256(artifacts[item["href"]]).hexdigest()==item["content_hash"]
        before=rows(e.path)
        for href,raw in artifacts.items():assert client.get(href).content==raw
        assert rows(e.path)==before
    app=create_default_app()
    with TestClient(app) as client:
        before=rows(e.path)
        for href,raw in artifacts.items():assert client.get(href).content==raw
        assert client.get(base).status_code in {200,404}
        assert rows(e.path)==before
