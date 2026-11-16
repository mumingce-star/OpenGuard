from datetime import timedelta
from app.work_progress import activate, observe, deactivate
from app.pipeline import ScanPipelineWorker
from test_a4_pipeline_worker import _registry, _empty_run, _plan, BASE_TIME

def test_work_phase_observer_receives_real_boundaries():
    seen=[];token=activate('scan-reproduction',lambda *args:seen.append(args))
    try:
        observe(25,'inventory',phase='inventory');observe(30,'consumer',phase='scan')
        assert [e[1:3]for e in seen]==[('ingestion','start'),('ingestion','end'),('inventory','start'),('inventory','end'),('scan','start')]
    finally:deactivate('scan-reproduction',token)

def test_pipeline_does_not_drop_fast_phase_history(tmp_path):
    registry=_registry(tmp_path);run=registry.create(_empty_run(48));seen=[];registry.progress_observer=lambda *args:seen.append(args)
    result=ScanPipelineWorker(registry,clock=lambda:BASE_TIME+timedelta(days=1)).run(run.run.id,_plan())
    assert result.run.status.value=='completed';assert len(seen)>=15;assert seen[-1][2]=='completed';registry.close()
