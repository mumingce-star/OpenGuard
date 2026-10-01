"""A4-2 terminal CAS, pipeline pass-through, factory and durable gates."""
from dataclasses import replace
import hashlib
import importlib
import io
import json
import time
import zipfile

import pytest
from fastapi.testclient import TestClient
from app.api import create_app, create_default_app
from app.api.zip_scan import ZipScanRuntime
from app.domain.models import ScanStatus, ScanStage
from app.pipeline import ScanPipelineWorker
from app.pipeline.local_zip import build_local_zip_dependency_plan
from app.pipeline.worker import PipelineStep, PipelinePlan, PipelineError, PipelineStageFailure
from app.persistence import ScanRegistryError, ZipDispatchStore
from app.pipeline.zip_dispatcher import ZipDispatcher
from test_p1_notice_lifecycle_ingestion import env, archive, lifecycle, rows, FILES, NOW
from test_p1_notice_draft_production_wiring import configure
from test_a2_public_git_ingestion import local_git_service, _git


def execute(e, *, index=1, lc=None, status="partial", publisher=None):
    lc = lc or lifecycle(e)
    p, run = archive(e, index=index)
    e.registry.create(run)
    plan = build_local_zip_dependency_plan(p, e.workspace, clock=lambda: NOW,
        notice_lifecycle=lc, upload_root=e.uploads)
    if status == "completed":
        plan = replace(plan, steps=tuple(PipelineStep(s.stage, lambda r:r) if s.stage in {ScanStage.RULES,ScanStage.REPORT} else s for s in plan.steps))
    result = ScanPipelineWorker(e.registry, clock=lambda: NOW, terminal_publisher=publisher).run(run.id, plan)
    return result, plan, lc


@pytest.mark.parametrize("status", ["completed", "partial", "publisher_partial"])
def test_w11_w12_terminal_uses_final_persisted_revision_and_precedes_assessment(env, status):
    e = env; seen = []
    def observe(run):
        saved = e.registry.get(run.id); stage = e.source_store._read_staged(run.id)
        seen.append((saved, stage)); assert stage is not None
    e.registry.assessment_observer = observe
    def fail_publish(run): raise OSError("publisher controlled failure")
    result, _, _ = execute(e, status="completed" if status != "partial" else "partial",
        publisher=fail_publish if status == "publisher_partial" else None)
    assert result.run.status == (ScanStatus.COMPLETED if status == "completed" else ScanStatus.PARTIAL)
    raw = e.source_store._load_stage  # read package through existing store details, no mutation
    with e.source_store._connect() as db:
        metadata, package = raw(db, result.run.id)
    assert json.loads(package)["binding"]["registry_revision"] == str(result.revision)
    assert seen[0][0] == result and seen[0][1].package_hash == metadata["package_hash"]


@pytest.mark.parametrize("case", ["failed", "cancelled", "cas_conflict"])
def test_w12_no_stage_without_successful_completed_partial_terminal(env, case, monkeypatch):
    e = env; lc = lifecycle(e); p, run = archive(e); e.registry.create(run)
    plan = build_local_zip_dependency_plan(p, e.workspace, clock=lambda: NOW, notice_lifecycle=lc, upload_root=e.uploads)
    if case in {"failed", "cancelled"}:
        def stop(current):
            if case == "cancelled":
                data=current.model_dump(mode="python"); data.update(status="cancelled",finished_at=NOW)
                from app.domain.models import ScanRun
                e.registry.replace(ScanRun.model_validate(data),expected_revision=e.registry.get(current.id).revision)
                return current
            raise PipelineStageFailure("controlled_failure", "Controlled failure.", False)
        plan = replace(plan, steps=tuple(PipelineStep(s.stage,stop) if s.stage==ScanStage.RULES else s for s in plan.steps))
    else:
        real=e.registry.replace
        def conflict(candidate, **kw):
            if candidate.status in {ScanStatus.PARTIAL,ScanStatus.COMPLETED}: raise ScanRegistryError("registry_revision_conflict")
            return real(candidate,**kw)
        monkeypatch.setattr(e.registry,"replace",conflict)
    try: ScanPipelineWorker(e.registry,clock=lambda:NOW).run(run.id,plan)
    except PipelineError:
        assert case == "cas_conflict"
    assert e.source_store._read_staged(run.id) is None


@pytest.mark.parametrize("where", ["admission", "stage", "diagnostic"])
def test_w13_sidecar_failure_preserves_terminal_and_original_observer(env, monkeypatch, where):
    e=env; seen=[]
    def bad(*a,**k): raise OSError("not public path or data")
    lc=lifecycle(e,diagnostic=bad if where=="diagnostic" else None)
    if where=="admission": monkeypatch.setattr(lc.adapter,"admit_terminal_ingestion",bad)
    if where=="stage": monkeypatch.setattr(e.source_store,"stage",bad)
    if where=="diagnostic":
        m=importlib.import_module("app.p1.notice_source_lifecycle"); monkeypatch.setattr(m,"collect_notice_source_package",bad)
    e.registry.assessment_observer=lambda run:seen.append(run)
    result,_,_=execute(e,lc=lc)
    assert seen==[result.run] and result.run.status==ScanStatus.PARTIAL
    assert [x.code for x in result.run.errors]==["rules_stage_not_connected"]
    assert e.source_store._read_staged(result.run.id) is None


def test_plan_rejects_invalid_optional_terminal_observer(env):
    from app.pipeline.worker import _STAGES
    plan=PipelinePlan(tuple(PipelineStep(s,lambda r:r) for s,_ in _STAGES),notice_terminal_observer=1)
    with pytest.raises(PipelineError,match="pipeline_invalid_argument"):
        ScanPipelineWorker(env.registry).run("x",plan)


def test_w04_zero_candidates_enabled_disabled_exact_facts_match(env,monkeypatch):
    from types import SimpleNamespace
    from app.persistence import SQLiteScanRunRegistry
    from app.assessment.store import AssessmentStore
    from app.p1.notice_source_store import NoticeSourceStore
    import app.p1.notice_source_lifecycle as module
    e=env;other_root=e.path/"disabled";other_root.mkdir(mode=0o700)
    other=SimpleNamespace(path=other_root,uploads=other_root/"uploads",workspace=other_root/"workspaces")
    other.uploads.mkdir(mode=0o700);other.workspace.mkdir(mode=0o700)
    other.registry=SQLiteScanRunRegistry(other_root/"scans.db")
    other.assessments=AssessmentStore(other_root/"assessment.db",min_free_bytes=0);other.assessments.initialize()
    other.source_store=NoticeSourceStore(other_root/"notice_source.db",min_free_bytes=0);other.source_store.initialize()
    enabled_path,run=archive(e,{"requirements.txt":FILES["requirements.txt"]})
    disabled_path=other.uploads/enabled_path.name
    disabled_path.write_bytes(enabled_path.read_bytes());disabled_path.chmod(0o600)
    calls=[]
    def forbidden(*args,**kw):calls.append(1);raise AssertionError("zero candidates called collector")
    monkeypatch.setattr(module,"collect_notice_source_package",forbidden)
    try:
        e.registry.create(run);other.registry.create(run)
        enabled=build_local_zip_dependency_plan(enabled_path,e.workspace,clock=lambda:NOW,
            notice_lifecycle=lifecycle(e),upload_root=e.uploads)
        disabled=build_local_zip_dependency_plan(disabled_path,other.workspace,clock=lambda:NOW)
        a=ScanPipelineWorker(e.registry,clock=lambda:NOW).run(run.id,enabled)
        b=ScanPipelineWorker(other.registry,clock=lambda:NOW).run(run.id,disabled)
        assert calls==[] and a==b
        for item in (e,other):
            assert item.source_store._read_staged(run.id) is None
            assert rows(item.path)["notice_source.db"]["notice_source_bindings"]==[]
    finally:other.registry.close()


def test_w14_direct_zip_http_stages_only_after_real_ingestion_and_cleans_upload(env):
    e=env; lc=lifecycle(e); p,_=archive(e); raw=p.read_bytes(); p.unlink()
    runtime=ZipScanRuntime(e.registry,upload_root=e.uploads,workspace_root=e.workspace,notice_lifecycle=lc)
    with TestClient(create_app(e.registry,zip_runtime=runtime)) as client:
        response=client.post("/api/v1/scans",data={"source_type":"zip"},files={"file":("owned.zip",raw,"application/zip")})
        assert response.status_code==202,response.text
        sid=response.json()["scan_id"]
        assert e.registry.get(sid).run.status in {ScanStatus.PARTIAL,ScanStatus.COMPLETED}
        assert e.source_store._read_staged(sid) is not None
    assert not list(e.uploads.iterdir()) and not list(e.workspace.iterdir())


def test_w14_real_git_http_preserves_notice_hook_when_plan_wraps_scan(env,local_git_service):
    from app.api.git_scan import GitScanRuntime
    e=env;svc,root=local_git_service;repository=root.parent/"source"
    (repository/"NOTICE").write_text("Owned controlled Git NOTICE.")
    _git(repository,"add","NOTICE");_git(repository,"commit","--quiet","-m","owned notice")
    revision=_git(repository,"rev-parse","HEAD").decode().strip();lc=lifecycle(e)
    runtime=GitScanRuntime(e.registry,workspace_root=root,ingestion_factory=lambda _:svc,notice_lifecycle=lc)
    with TestClient(create_app(e.registry,git_runtime=runtime)) as client:
        response=client.post("/api/v1/scans",json={"source_type":"git","source":"https://github.com/example/repo"})
        assert response.status_code==202,response.text;sid=response.json()["scan_id"]
        run=e.registry.get(sid).run
        assert run.project.revision==revision and run.status in {ScanStatus.COMPLETED,ScanStatus.PARTIAL}
        assert e.source_store._read_staged(sid) is not None
    assert list(root.iterdir())==[]


def test_w14_w15_queued_durable_dispatch_preserves_hook_and_profile(env):
    e=env; lc=lifecycle(e); p,_=archive(e); raw=p.read_bytes(); p.unlink()
    dispatch=e.path/"dispatch"; dispatch.mkdir(mode=0o700)
    store=ZipDispatchStore(dispatch,e.uploads)
    runtime=ZipScanRuntime(e.registry,upload_root=e.uploads,workspace_root=e.workspace,dispatch_store=store,notice_lifecycle=lc)
    with TestClient(create_app(e.registry,zip_runtime=runtime)) as client:
        response=client.post("/api/v1/scans",data={"source_type":"zip"},files={"file":("owned.zip",raw,"application/zip")})
        sid=response.json()["scan_id"]; descriptor=store.read(sid,state="ready")
        assert e.registry.get(sid).run.status==ScanStatus.QUEUED
    dispatcher=ZipDispatcher(e.registry,store,data_dir=e.path,workspace_root=e.workspace,notice_lifecycle=lc)
    dispatcher._dispatch_queued(descriptor,e.registry.get(sid))
    assert e.registry.get(sid).run.status in {ScanStatus.PARTIAL,ScanStatus.COMPLETED}
    assert e.source_store._read_staged(sid) is not None
    assert not list(e.uploads.iterdir())


def test_w15_running_durable_recovery_does_not_recollect_or_stage(env,monkeypatch):
    e=env;lc=lifecycle(e);p,_=archive(e);raw=p.read_bytes();p.unlink()
    dispatch=e.path/"dispatch";dispatch.mkdir(mode=0o700);store=ZipDispatchStore(dispatch,e.uploads)
    runtime=ZipScanRuntime(e.registry,upload_root=e.uploads,workspace_root=e.workspace,dispatch_store=store,notice_lifecycle=lc)
    with TestClient(create_app(e.registry,zip_runtime=runtime)) as client:
        response=client.post("/api/v1/scans",data={"source_type":"zip"},files={"file":("owned.zip",raw,"application/zip")})
        sid=response.json()["scan_id"]
    queued=e.registry.get(sid)
    from app.domain.models import ScanRun
    data=queued.run.model_dump(mode="python");data.update(status="running",stage="ingestion",progress=5,started_at=queued.run.created_at)
    running=e.registry.replace(ScanRun.model_validate(data),expected_revision=queued.revision)
    def forbidden(*a,**kw):raise AssertionError("running recovery called collector")
    import app.p1.notice_source_lifecycle as m
    monkeypatch.setattr(m,"collect_notice_source_package",forbidden)
    dispatcher=ZipDispatcher(e.registry,store,data_dir=e.path,workspace_root=e.workspace,notice_lifecycle=lc)
    dispatcher._recover_running(running)
    actual=e.registry.get(sid).run
    assert actual.status==ScanStatus.FAILED and actual.errors[-1].code=="worker_interrupted"
    assert e.source_store._read_staged(sid) is None


@pytest.mark.parametrize("enabled", ["0", "1"])
def test_w16_factory_idle_initialization_restart_never_collects_or_binds(tmp_path,monkeypatch,enabled):
    root=tmp_path/"app"; root.mkdir(mode=0o700); configure(monkeypatch,root,assessments=enabled)
    m=importlib.import_module("app.p1.notice_source_lifecycle")
    def forbidden(*a,**k): raise AssertionError("idle initialization ran lifecycle")
    monkeypatch.setattr(m,"collect_notice_source_package",forbidden)
    for _ in range(2):
        app=create_default_app()
        with TestClient(app) as client:
            assert client.get("/api/v1/scans").status_code==200
            if enabled=="1":
                assert app.state.zip_scan_runtime._notice_lifecycle is not None
                assert app.state.assessment_service.assessment_saved_observer is not None
            else: assert app.state.zip_scan_runtime._notice_lifecycle is None
    if enabled=="0": assert not (root/"notice_source.db").exists()


def test_w16_disabled_default_three_entrypoints_have_no_lifecycle(tmp_path,monkeypatch):
    root=tmp_path/"app";root.mkdir(mode=0o700);configure(monkeypatch,root,assessments="0")
    monkeypatch.setenv("OPENGUARD_ENABLE_PUBLIC_GIT","1");monkeypatch.setenv("OPENGUARD_ENABLE_DURABLE_ZIP","1")
    app=create_default_app()
    assert app.state.zip_scan_runtime._notice_lifecycle is None
    assert app.state.git_scan_runtime._notice_lifecycle is None
    assert app.state.zip_dispatcher._notice_lifecycle is None
    app.state.scan_api_service._registry.close()


def test_w16_enabled_source_initialization_failure_is_startup_failure(tmp_path,monkeypatch):
    root=tmp_path/"app";root.mkdir(mode=0o700);configure(monkeypatch,root)
    from app.p1.notice_source_store import NoticeSourceStore
    def failure(*a,**k):raise OSError("source initialization failed")
    monkeypatch.setattr(NoticeSourceStore,"initialize",failure)
    with pytest.raises(OSError):create_default_app()
