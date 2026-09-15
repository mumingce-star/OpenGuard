"""Isolated compatibility proof using the preserved, SHA-matched pre-repair writer."""
from pathlib import Path
import importlib.util
import hashlib
from test_p1_report_v2_service import report_env
from app.p1.models import P1TaskRef
from app.p1.report_v2 import ReportV2Service
from app.p1.report_v2_store import ReportV2Store


def load(name,relative):
    path=Path(__file__).resolve().parents[1]/'fixtures'/'p1'/'report-v2-legacy-writer'/Path(relative).name
    expected = {
        'report_v2.py': '3aa1a3ab82f51e096bc3586f2969fb56f16f734921f93b656b229d6488a92272',
        'report_v2_store.py': '007b5c0509b99409d02132d73bf9eba2a365c29d5ee254439befa1e787b5862c',
    }
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected[path.name], 'Legacy writer fixture changed'
    spec=importlib.util.spec_from_file_location('app.p1.'+name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_original_writer_report_replays_and_downloads_without_sources(report_env,monkeypatch):
    env=report_env
    old_store=load('_a06_legacy_store','backend/app/p1/report_v2_store.py').ReportV2Store(env.path/'legacy'/'report_v2.db',min_free_bytes=0)
    old_store.initialize()
    legacy=load('_a06_legacy_service','backend/app/p1/report_v2.py').ReportV2Service(env.registry,env.assessment_store,env.task_store,old_store)
    refs=[P1TaskRef(task_id=env.task.task_id,version=1)]
    original=legacy.create(env.run.id,env.assessment.id,idempotency_key='legacy-original',task_refs=refs)
    raw={fmt:legacy.artifact(env.run.id,env.assessment.id,original.snapshot_id,fmt) for fmt in ('json','html')}
    before=hashlib.sha256(old_store.path.read_bytes()).hexdigest()
    fixed=ReportV2Service(env.registry,env.assessment_store,env.task_store,ReportV2Store(old_store.path,min_free_bytes=0))
    def fail(*args,**kwargs):raise AssertionError('legacy replay consulted sources or renderer')
    for obj,name in ((env.registry,'get'),(env.assessment_store,'get'),(env.task_store,'get_version'),(env.task_store,'history')):
        monkeypatch.setattr(obj,name,fail)
    monkeypatch.setattr('app.p1.report_v2._render_json',fail)
    monkeypatch.setattr('app.p1.report_v2._render_html',fail)
    assert fixed.create(env.run.id,env.assessment.id,idempotency_key='legacy-original',task_refs=refs)==original
    for fmt in raw:assert fixed.artifact(env.run.id,env.assessment.id,original.snapshot_id,fmt)==raw[fmt]
    assert hashlib.sha256(old_store.path.read_bytes()).hexdigest()==before
