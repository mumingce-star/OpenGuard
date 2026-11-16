from pathlib import Path
import pytest
from app.ingestion import git_materializer as m
from app.security.errors import IngestionSecurityError
from app.security.limits import GitSafetyLimits


def exercise(monkeypatch, failures):
    ids = ('a'*40, 'b'*40)
    entries = tuple(m.GitTreeEntry('100644', oid, 0, (name,), name, name) for oid, name in zip(ids, ('LICENSE','package.json')))
    monkeypatch.setattr(m, 'inspect_bounded_git_tree', lambda *a, **k: ('c'*40, entries, (), 2))
    monkeypatch.setattr(m, 'materialize_git_blobs', lambda *a, **k: 2)
    monkeypatch.setattr(m, 'time', type('Clock', (), {'monotonic': staticmethod(lambda: 10.0)}))
    calls=[]
    class Runner:
        def fetch_objects(self, repository, objects, **kw): calls.append(('fetch',objects,kw))
        def object_sizes(self, repository, objects, **kw):
            calls.append(('sizes',objects,kw))
            if failures: raise failures.pop(0)
            return dict.fromkeys(objects,1)
    return lambda: m.materialize_bounded_git_tree(Runner(),Path('/synthetic/repo'),object(),home=Path('/synthetic/home'),limits=GitSafetyLimits(),deadline=20.0,proxy_url='http://127.0.0.1:1234'), calls, ids


def test_same_objects_recovered_once_with_original_bounds(monkeypatch):
    run,calls,ids=exercise(monkeypatch,[IngestionSecurityError('invalid_source','git_object_invalid')])
    result=run()
    assert result.revision=='c'*40 and result.file_count==2
    assert [x[0] for x in calls]==['fetch','sizes','fetch','sizes']
    assert all(x[1]==ids and x[2]['deadline']==20.0 for x in calls)
    assert [x[2]['proxy_url'] for x in calls if x[0]=='fetch']==['http://127.0.0.1:1234']*2


def test_permanent_object_error_stops_after_one_recovery(monkeypatch):
    run,calls,_=exercise(monkeypatch,[IngestionSecurityError('invalid_source','git_object_invalid') for _ in range(2)])
    with pytest.raises(IngestionSecurityError):run()
    assert [x[0] for x in calls]==['fetch','sizes','fetch','sizes']


@pytest.mark.parametrize('code,reason',[('scanner_timeout','git_process_timeout'),('invalid_source','git_entry_unsafe'),('scanner_failed','git_object_limit_exceeded')])
def test_other_safety_failures_never_retry(monkeypatch,code,reason):
    run,calls,_=exercise(monkeypatch,[IngestionSecurityError(code,reason)])
    with pytest.raises(IngestionSecurityError):run()
    assert [x[0] for x in calls]==['fetch','sizes']


def test_complete_objects_need_no_recovery(monkeypatch):
    run,calls,_=exercise(monkeypatch,[]);run()
    assert [x[0] for x in calls]==['fetch','sizes']
