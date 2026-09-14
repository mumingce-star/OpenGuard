"""A05 isolated HTTP, source, persistence and workflow tests. No live services."""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from app.api.main import create_app
from app.assessment.engine import canonical_bytes, build_assessment
from app.assessment.models import Assessment
from app.assessment.store import AssessmentStore
from app.persistence import SQLiteScanRunRegistry
from app.p1.remediation import RemediationService
from app.p1.remediation_store import RemediationTaskStore, RemediationStoreError
from test_p1_history_api import seed
from test_p1_diff_api import assessment
from test_p1_contract_schema import validator


@pytest.fixture
def task_env(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    env = SimpleNamespace(path=tmp_path)
    env.registry = SQLiteScanRunRegistry(tmp_path/'scans.db')
    env.store = AssessmentStore(tmp_path/'assessment.db', min_free_bytes=0)
    env.store.initialize()
    env.run = seed(env, 1, 'completed')
    def canonical_sources(data):
        row=data['resource_evaluations'][0]
        row.update(conditions=['保留许可声明'], restrictions={'closed/distribution~scope':['核对交付范围']}, gaps=['补充许可证据'],next_steps=['核对该固定版本来源'])
        data['obligations']=[dict(id='a05-obligation',action='保留声明',requirement='随交付保留原声明',
            trigger='交付时',fulfillment='pending',resource_ids=[row['resource_id']],
            evidence_ids=row['evidence_ids'],rule_id='fixture-rule',rule_version=data['rule_version'])]
        # Other resource evaluation remains valid and contributes its own sources.
    env.assessment = assessment(env,env.run,mutate=canonical_sources)
    env.tasks = RemediationTaskStore(tmp_path/'tasks'/'remediation.db', min_free_bytes=0)
    env.tasks.initialize()
    env.service = RemediationService(env.registry,env.store,env.tasks,cursor_key=b'fixed-test-only-key')
    env.app = create_app(env.registry, remediation_service=env.service)
    def forbidden(*args,**kwargs):raise AssertionError('A05 must not invoke live network or subprocess')
    monkeypatch.setattr('subprocess.Popen',forbidden)
    monkeypatch.setattr('socket.socket.connect',forbidden)
    with TestClient(env.app) as client:
        env.client=client
        yield env
    env.registry.close()


def base(env, aid=None, sid=None):
    return f'/api/v1/scans/{sid or env.run.id}/assessments/{aid or env.assessment.id}/remediation-tasks'


def derive(env,key='first',**overrides):
    body=dict(idempotency_key=key,expected_facts_hash=env.assessment.facts_hash)
    body.update(overrides)
    return env.client.post(base(env)+'/derive',json=body)


def tasks(env):
    response=derive(env)
    assert response.status_code==200,response.text
    return response.json()['items']


def patch(env,task,**changes):
    return env.client.patch(base(env)+'/'+task['task_id'],json={'expected_version':task['version'],**changes})


def check_error(response,status,reason=None):
    assert response.status_code==status,response.text
    body=response.json()['error']
    assert body['request_id']==response.headers['x-request-id']
    if reason:assert body['details']['reason']==reason


def pointer(doc,path):
    for token in path[1:].split('/'):
        token=token.replace('~1','/').replace('~0','~')
        doc=doc[int(token)] if isinstance(doc,list) else doc[token]
    return doc


def db_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_frozen_schema_source_hash_refs_and_all_canonical_kinds(task_env):
    env=task_env; values=tasks(env); document=env.assessment.model_dump(mode='json')
    assert values
    kinds={t['origin']['kind'] for t in values}
    assert {'condition','restriction','gap','next_step'}<=kinds
    assert 'obligation' in kinds
    obligation=next(t for t in values if t['origin']['kind']=='obligation')
    assert obligation['origin']['source_pointer']=='/obligations/0'
    assert obligation['resource_ids']==env.assessment.obligations[0].resource_ids
    assert [e['evidence_id'] for e in obligation['evidence_refs']]==sorted(set(env.assessment.obligations[0].evidence_ids))
    for task in values:
        validator('RemediationTask').validate(task)
        assert task['note']=='' and task['version']==1 and task['status']=='todo'
        assert task['assessment_ref']['assessment_id']==env.assessment.id
        assert task['provenance']['assessment_refs']==[task['assessment_ref']]
        assert task['provenance']['source_refs'][0]['facts_hash']==env.assessment.facts_hash
        value=pointer(document,task['origin']['source_pointer'])
        assert hashlib.sha256(canonical_bytes(value)).hexdigest()==task['origin']['source_hash']
        if task['origin']['source_pointer'].startswith('/resource_evaluations/'):
            parent=document['resource_evaluations'][int(task['origin']['source_pointer'].split('/')[2])]
            assert task['resource_ids']==[parent['resource_id']]
            assert [e['evidence_id'] for e in task['evidence_refs']]==sorted(set(parent['evidence_ids']))
        assert all(e['scan_id']==env.run.id and e['namespace']=='scan' for e in task['evidence_refs'])
    assert any('closed~1distribution~0scope' in t['origin']['source_pointer'] for t in values)


def test_expected_hash_and_cross_scan_rejected(task_env):
    env=task_env
    check_error(derive(env,expected_facts_hash='0'*64),409,'facts_hash_mismatch')
    r=env.client.post(base(env,sid='other')+'/derive',json={'idempotency_key':'x','expected_facts_hash':env.assessment.facts_hash})
    check_error(r,409,'assessment_scan_mismatch')
    assert env.tasks.page(env.run.id,env.assessment.id,limit=100,after=None)==[]


def test_derive_idempotency_preserves_patch_and_audit(task_env):
    env=task_env; initial=tasks(env); first=initial[0]
    updated=patch(env,first,status='in_progress',note=' 原样备注 ').json()
    before=db_hash(env.tasks.path)
    replay=derive(env).json()['items']
    assert next(t for t in replay if t['task_id']==first['task_id'])==updated
    assert db_hash(env.tasks.path)==before
    alternate=derive(env,key='second').json()['items']
    assert {t['task_id'] for t in alternate}=={t['task_id'] for t in initial}
    assert next(t for t in alternate if t['task_id']==first['task_id'])==updated
    assert len(env.tasks.history(first['task_id']))==2
    check_error(derive(env,expected_facts_hash='a'*64),409,'idempotency_conflict')


def test_deterministic_ids_across_independent_stores(task_env):
    env=task_env; initial=tasks(env)
    second=RemediationTaskStore(env.path/'other'/'remediation.db',min_free_bytes=0);second.initialize()
    from app.p1.models import P1TaskDeriveRequest
    other=RemediationService(env.registry,env.store,second).derive(env.run.id,env.assessment.id,P1TaskDeriveRequest(idempotency_key='new',expected_facts_hash=env.assessment.facts_hash))
    assert {t.task_id for t in other.items}=={t['task_id'] for t in initial}


def test_workflow_audit_and_formal_facts_unchanged(task_env):
    env=task_env; task=next(t for t in tasks(env) if t['origin']['kind']=='obligation')
    before=(db_hash(env.store.path),db_hash(env.path/'scans.db'),env.store.get(env.run.id,env.assessment.id).model_dump_json())
    for status,note in [('in_progress','核对中'),('done',' 已人工核对材料 '),('todo',''),('dismissed','暂不处理'),('todo','')]:
        old=task
        response=patch(env,task,status=status,note=note)
        assert response.status_code==200,response.text
        task=response.json();validator('RemediationTask').validate(task)
        assert task['version']==old['version']+1 and task['note']==note
    history=env.tasks.history(task['task_id'])
    assert [h['version'] for h in history]==list(range(1,7))
    assert [h['status'] for h in history]==['todo','in_progress','done','todo','dismissed','todo']
    assert before==(db_hash(env.store.path),db_hash(env.path/'scans.db'),env.store.get(env.run.id,env.assessment.id).model_dump_json())


@pytest.mark.parametrize('changes', [dict(status='done'),dict(status='dismissed'),dict(status='done',note='   '),dict(status='dismissed',note='\t')])
def test_final_nonblank_note_enforced_atomically(task_env,changes):
    env=task_env; task=tasks(env)[0]; before=db_hash(env.tasks.path)
    check_error(patch(env,task,**changes),400)
    assert db_hash(env.tasks.path)==before and len(env.tasks.history(task['task_id']))==1


@pytest.mark.parametrize('changes',[{'note':None},{'note':123},{'note':'x'*2001},{'status':None},{'status':'invalid'},{'superseded':True},{'formal':True},
    {'note':'ok','expected_version':0},{'note':'ok','expected_version':'1'},{'note':'ok','expected_version':True}])
def test_invalid_patch_does_not_write(task_env,changes):
    env=task_env; task=tasks(env)[0]; before=db_hash(env.tasks.path)
    response=patch(env,task,**changes)
    check_error(response,400,'request_invalid')
    assert response.json()['error']['code']=='invalid_argument'
    assert next(t for t in env.client.get(base(env)).json()['items'] if t['task_id']==task['task_id'])==task
    assert db_hash(env.tasks.path)==before
    assert len(env.tasks.history(task['task_id']))==1


def test_note_omitted_preserved_and_note_only_terminal_check(task_env):
    env=task_env; task=tasks(env)[0]
    task=patch(env,task,note='  已核验\n').json()
    task=patch(env,task,status='done').json()
    assert task['note']=='  已核验\n'
    before=db_hash(env.tasks.path)
    check_error(patch(env,task,note=''),400)
    assert db_hash(env.tasks.path)==before
    task=patch(env,task,note=' 保留原始字符串 ').json()
    assert task['status']=='done' and task['note']==' 保留原始字符串 '


def test_stale_cas_has_no_audit_write(task_env):
    env=task_env; task=tasks(env)[0]
    assert patch(env,task,status='in_progress').status_code==200
    before=db_hash(env.tasks.path)
    check_error(patch(env,task,status='done',note='old client'),409,'stale_version')
    assert db_hash(env.tasks.path)==before
    assert len(env.tasks.history(task['task_id']))==2


def test_pagination_stable_scoped_and_readonly(task_env):
    env=task_env; all_tasks=tasks(env);before=db_hash(env.tasks.path)
    page=env.client.get(base(env),params={'limit':1}).json()
    values=list(page['items']);cursor=page['next_cursor'];first=cursor
    while cursor:
        page=env.client.get(base(env),params={'limit':1,'cursor':cursor}).json()
        values.extend(page['items']);cursor=page['next_cursor']
    assert len(values)==len(all_tasks) and len({t['task_id'] for t in values})==len(values)
    assert [(t['created_at'],t['task_id']) for t in values]==sorted((t['created_at'],t['task_id']) for t in values)
    check_error(env.client.get(base(env),params={'cursor':first+'x'}),400,'cursor_invalid')
    assert db_hash(env.tasks.path)==before


def test_superseded_read_view_no_state_or_audit_change(task_env):
    env=task_env; old=tasks(env); first=old[0]
    fixed=db_hash(env.tasks.path)
    newer=assessment(env,env.run,version=2)
    assert newer.version==2
    values=env.client.get(base(env),params={'limit':100}).json()['items']
    assert all(t['superseded'] for t in values)
    assert all(t['version']==1 and t['status']=='todo' for t in values)
    assert db_hash(env.tasks.path)==fixed and len(env.tasks.history(first['task_id']))==1


def test_missing_sidecar_read_and_disabled_service_create_nothing(task_env):
    env=task_env
    absent=RemediationTaskStore(env.path/'absent'/'remediation.db',min_free_bytes=0)
    env.app.state.remediation_service=RemediationService(env.registry,env.store,absent)
    assert env.client.get(base(env)).json()['items']==[]
    assert not absent.path.parent.exists()
    env.app.state.remediation_service=None
    check_error(env.client.get(base(env)),503)
    check_error(derive(env),503)
    assert not absent.path.parent.exists()


def test_empty_evidence_not_invented_and_nonformal_rejected(task_env):
    env=task_env
    new=assessment(env,env.run,version=2,mutate=lambda p:[r.update(evidence_ids=[]) for r in p['resource_evaluations']])
    response=env.client.post(base(env,aid=new.id)+'/derive',json={'idempotency_key':'new','expected_facts_hash':new.facts_hash})
    assert response.status_code==200,response.text
    assert all(not t['evidence_refs'] for t in response.json()['items'] if t['origin']['kind']!='obligation')
    nonformal=assessment(env,env.run,version=3,mutate=lambda p:p.update(formal=False))
    response=env.client.post(base(env,aid=nonformal.id)+'/derive',json={'idempotency_key':'nf','expected_facts_hash':nonformal.facts_hash})
    check_error(response,409,'assessment_not_formal')


@pytest.mark.parametrize('limit',['0','101','no','1.5'])
def test_invalid_page_limit(task_env,limit):
    check_error(task_env.client.get(base(task_env),params={'limit':limit}),400)


def test_cursor_cannot_cross_assessment_binding(task_env):
    env=task_env;tasks(env)
    first=env.client.get(base(env),params={'limit':1}).json()['next_cursor']
    newer=assessment(env,env.run,version=2)
    check_error(env.client.get(base(env,aid=newer.id),params={'cursor':first}),400,'cursor_invalid')


def test_missing_assessment_and_cross_bound_task(task_env):
    env=task_env;first=tasks(env)[0]
    check_error(env.client.get(base(env,aid='missing')),404)
    newer=assessment(env,env.run,version=2)
    response=env.client.patch(base(env,aid=newer.id)+'/'+first['task_id'],json={'expected_version':1,'status':'in_progress'})
    check_error(response,404)
    assert len(env.tasks.history(first['task_id']))==1


def test_derive_does_not_select_latest_or_use_qwen_text(task_env,monkeypatch):
    env=task_env
    def forbidden(*args,**kwargs):raise AssertionError('derive must not select latest or generate')
    monkeypatch.setattr(env.store,'latest',forbidden)
    monkeypatch.setattr(env.store,'list',forbidden)
    values=tasks(env)
    assert all(not t['origin']['source_pointer'].startswith(('/dimensions','/ai_')) for t in values)


@pytest.mark.parametrize('ref', [
    {'namespace':'scan','scan_id':'scan-example','evidence_id':'evidence-example'},
    {'namespace':'profile_observation','observation_id':'observation-example'},
])
def test_task_accepts_frozen_common_evidence_ref(task_env,ref):
    from app.p1.models import P1RemediationTask
    task=tasks(task_env)[0]
    task['evidence_refs']=[ref]
    validator('RemediationTask').validate(task)
    assert P1RemediationTask.model_validate(task).model_dump(mode='json')['evidence_refs']==[ref]


def test_diff_evidence_ref_remains_scan_only():
    from pydantic import ValidationError
    from app.p1.models import P1DiffEvidenceRef
    assert P1DiffEvidenceRef(scan_id='s',evidence_id='e').namespace=='scan'
    with pytest.raises(ValidationError):
        P1DiffEvidenceRef.model_validate({'namespace':'profile_observation','observation_id':'o'})


@pytest.mark.parametrize('overrides', [
    {'idempotency_key':'   '}, {'expected_facts_hash':'invalid'},
])
def test_invalid_derive_does_not_write(task_env,overrides):
    env=task_env; tasks(env)
    initial=env.client.get(base(env),params={'limit':100}).json()['items']
    before=db_hash(env.tasks.path)
    response=derive(env,key='invalid-request',**overrides)
    check_error(response,400,'request_invalid')
    assert response.json()['error']['code']=='invalid_argument'
    assert db_hash(env.tasks.path)==before
    assert env.client.get(base(env),params={'limit':100}).json()['items']==initial
    assert all(len(env.tasks.history(t['task_id']))==1 for t in initial)


def test_p0_invalid_scan_request_keeps_422(task_env):
    response=task_env.client.post('/api/v1/scans',json={})
    check_error(response,422,'request_invalid')
    assert response.json()['error']['code']=='invalid_source'


def test_patch_openapi_omission_preserves_without_advertised_defaults(task_env):
    schema=task_env.client.get('/openapi.json').json()['components']['schemas']['P1TaskPatchRequest']
    for name in ('status','note'):
        field=schema['properties'][name]
        assert name not in schema['required']
        assert 'default' not in field
        assert field['type']=='string'
        assert 'preserve current' in field['description']
        assert 'null is invalid' in field['description']
