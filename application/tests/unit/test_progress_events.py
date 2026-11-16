from pathlib import Path
import hashlib, copy, io, zipfile
import pytest
from fastapi.testclient import TestClient
from app.progress_events import ProgressEventStore, ProgressEvent
from app.work_progress import activate, observe, finish, deactivate, get
from app.ingestion import ZipIngestionService
from app.api.main import create_app
from app.domain.models import ScanStage, ScanStatus
from app.pipeline import ScanPipelineWorker, PipelinePlan, PipelineStep
from test_a4_pipeline_worker import _registry, _empty_run, _plan, BASE_TIME
from datetime import timedelta

@pytest.fixture
def store(tmp_path):
    tmp_path.chmod(0o700)
    value=ProgressEventStore(tmp_path/'progress.db');value.initialize();return value

def test_real_zip_boundaries_are_recorded_before_consumer(store,tmp_path):
    root=tmp_path/'tree';root.mkdir();service=ZipIngestionService(root)
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w')as z:z.writestr('package.json','{"name":"offline","dependencies":{"demo":"1"}}')
    token=activate('scan-test',store.write)
    try:
        def consume(session):
            view=store.read('scan-test','running')
            assert [(e.phase,e.state)for e in view.events]==[('ingestion','start'),('ingestion','end'),('inventory','start'),('inventory','end'),('scan','start')]
            assert get('scan-test')['percent']==30
        service.ingest_with_consumer(io.BytesIO(output.getvalue()),consume)
        assert not store.read('scan-test','running').recording_complete
    finally:deactivate('scan-test',token);service.close()

def test_compound_ingestion_does_not_regress_or_repeat_phases(store,tmp_path):
    registry=_registry(tmp_path);queued=registry.create(_empty_run(44));registry.progress_observer=store.write
    def ingestion(run):
        observe(25,'inventory',phase='inventory');observe(30,'dependencies',phase='scan');observe(40,'scancode');observe(70,'scanning done');return run
    plan=_plan();plan=PipelinePlan((PipelineStep(ScanStage.INGESTION,ingestion),*plan.steps[1:]))
    result=ScanPipelineWorker(registry,clock=lambda:BASE_TIME+timedelta(days=1)).run(queued.run.id,plan)
    view=store.read(queued.run.id,result.run.status.value);assert view.recording_complete
    starts=[e.phase for e in view.events if e.state=='start'];assert starts==['ingestion','inventory','scan','normalize','rules','ai_assist','report']
    assert all(a.percent<=b.percent for a,b in zip(view.events,view.events[1:]));assert view.events[-1].percent==100
    registry.close()

def test_observer_failure_cannot_change_scan_results(tmp_path):
    registry=_registry(tmp_path);a=registry.create(_empty_run(45));b=registry.create(_empty_run(46))
    worker=ScanPipelineWorker(registry,clock=lambda:BASE_TIME+timedelta(days=1));first=worker.run(a.run.id,_plan())
    registry.progress_observer=lambda *args:(_ for _ in ()).throw(RuntimeError('do not leak'))
    second=worker.run(b.run.id,_plan());assert first.run.status==second.run.status==ScanStatus.COMPLETED
    assert first.run.summary==second.run.summary;assert first.run.errors==second.run.errors==[];registry.close()

def test_store_persists_exact_events_and_get_is_readonly(store):
    store.write('one','ingestion','start',0);before=hashlib.sha256(store.path.read_bytes()).hexdigest();modified=store.path.stat().st_mtime_ns
    view=ProgressEventStore(store.path).read('one','running');assert view.events[0].sequence==1
    assert ProgressEventStore(store.path).read('foreign','completed').events==[]
    assert hashlib.sha256(store.path.read_bytes()).hexdigest()==before;assert store.path.stat().st_mtime_ns==modified

@pytest.mark.parametrize('field,value',[('phase','other'),('state','verified'),('percent',True),('percent',-1),('percent',101),('sequence',True),('sequence',65)])
def test_event_rejects_wrong_types_and_unknown_values(field,value):
    event=dict(sequence=1,phase='scan',state='start',percent=40,observed_at='2026-10-14T14:00:00Z');event[field]=value
    with pytest.raises(ValueError):ProgressEvent.model_validate(event)

def test_store_bounded_per_scan(store):
    for _ in range(64):store.write('bounded','scan','start',40)
    with pytest.raises(ValueError):store.write('bounded','scan','start',40)
    assert len(store.read('bounded','running').events)==64

def test_terminal_failure_never_creates_later_stages(store):
    token=activate('failure',store.write)
    try:observe(30,'parse',phase='scan');finish('failed',40)
    finally:deactivate('failure',token)
    view=store.read('failure','failed');assert not view.recording_complete;assert view.events[-1].state=='failed';assert all(e.phase in {'ingestion','scan'}for e in view.events)

def test_unknown_prior_scan_does_not_get_fabricated_history(store):
    view=store.read('old','completed');assert view.events==[];assert not view.recording_complete

def test_api_bound_read_is_readonly_and_legacy_status_unchanged(store,tmp_path):
    registry=_registry(tmp_path);run=registry.create(_empty_run(47));store.write(run.run.id,'ingestion','start',0)
    with TestClient(create_app(registry,progress_event_store=store))as client:
        original=client.get('/api/v1/scans/'+run.run.id).content
        before=hashlib.sha256(store.path.read_bytes()).hexdigest()
        response=client.get('/api/v1/scans/'+run.run.id+'/progress-events');assert response.status_code==200;assert response.json()['scan_id']==run.run.id
        assert client.get('/api/v1/scans/'+run.run.id).content==original;assert hashlib.sha256(store.path.read_bytes()).hexdigest()==before
        assert client.get('/api/v1/scans/scn_not_there/progress-events').status_code==404
    registry.close()

def test_opt_in_endpoint_absent_by_default(tmp_path):
    registry=_registry(tmp_path)
    with TestClient(create_app(registry))as client:assert client.get('/api/v1/scans/scn_other/progress-events').status_code==404
    registry.close()

def test_unsafe_store_symlink_is_rejected(tmp_path):
    tmp_path.chmod(0o700);target=tmp_path/'original';target.write_bytes(b'protected');link=tmp_path/'link';link.symlink_to(target)
    with pytest.raises(ValueError):ProgressEventStore(link).initialize()
    assert target.read_bytes()==b'protected'
