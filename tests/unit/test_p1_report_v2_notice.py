"""Persisted real Notice -> real Report; preparation never runs during consumption."""
import json
import copy
import hashlib
import html
import re
import sqlite3
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from app.api.main import create_app

from app.p1.models import P1NoticeRef
from app.p1.notice_draft import NoticeDraftService
from app.p1.notice_draft_store import NoticeDraftStore
from app.p1.notice_draft_store import content_hash, fingerprint
from app.p1.report_v2 import ReportV2Service
from app.p1.report_v2_notice import ReportNoticeReader
from app.p1.report_v2_graph import ReportGraphReader
from app.p1.report_v2_store import ReportV2Store
from app.p1.models import P1TaskRef
from test_p1_contract_schema import validator
from test_p1_notice_draft_backend import FixtureReader
from test_p1_report_v2_service import report_env


def saved_notice(env, key='notice'):
    store = NoticeDraftStore(env.path/'notices'/'notice_draft.db', min_free_bytes=0)
    store.initialize()
    service = NoticeDraftService(env.registry, env.assessment_store, store, facts_reader=FixtureReader())
    draft = service.create(env.run.id, env.assessment.id, idempotency_key=key)
    return store, draft


def test_saved_notice_is_embedded_in_real_report(report_env):
    env = report_env
    store, draft = saved_notice(env)
    # Exercise the existing service path before the production adapter exists.
    env.service.notice_reader = SimpleNamespace(read=lambda scan, assessment, ref: store.get(scan, assessment, ref.draft_id))
    result = env.service.create(env.run.id, env.assessment.id, idempotency_key='with-notice',
                                notice_refs=[P1NoticeRef(draft_id=draft.draft_id, content_hash=draft.content_hash)])
    document = json.loads(env.service.artifact(env.run.id, env.assessment.id, result.snapshot_id, 'json'))
    rows = [s for s in document['sections'] if s['authority']=='observation']
    assert len(rows)==1 and rows[0]['content']==draft.model_dump(mode='json')


def state(env):
    return {str(p.relative_to(env.path)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in env.path.rglob('*') if p.is_file()}


@pytest.fixture
def notice_http(report_env):
    env = report_env
    store, draft = saved_notice(env)
    reader = ReportNoticeReader(store)
    graph = ReportGraphReader()
    service = ReportV2Service(env.registry, env.assessment_store, env.task_store, env.report_store,
                              notice_reader=reader, graph_reader=graph)
    app = create_app(env.registry, report_v2_service=service)
    with TestClient(app) as client:
        yield SimpleNamespace(env=env, store=store, draft=draft.model_dump(mode='json'), reader=reader,
                              service=service, graph=graph, client=client,
                              base=f'/api/v1/scans/{env.run.id}/assessments/{env.assessment.id}/report-v2')


def ref(draft):
    return dict(draft_id=draft['draft_id'], content_hash=draft['content_hash'])


def post(h, key='binding', refs=None, **extra):
    return h.client.post(h.base, json=dict(idempotency_key=key,
                         notice_refs=[ref(h.draft)] if refs is None else refs, **extra))


def error(response, status, code):
    assert response.status_code==status, response.text
    assert response.json()['error']['code']==code
    assert 'Traceback' not in response.text and '.db' not in response.text


def save_variant(h, mutate):
    draft=copy.deepcopy(h.draft)
    draft['draft_id']='ntc_'+str(uuid4())
    mutate(draft)
    draft['content_hash']=content_hash(draft)
    h.store.create(draft['binding']['scan_ref']['scan_id'],draft['binding']['assessment_ref']['assessment_id'],
                   draft['draft_id'],draft)
    return draft


def test_multiple_notice_task_graph_complete_and_sorted(notice_http, monkeypatch):
    h=notice_http
    # A distinct real Notice Service input creates a second saved immutable draft.
    facts=FixtureReader(); facts.package['producer']['version']='2.0.1'
    from app.p1.notice_facts import digest
    facts.sha=digest(facts.package)
    second=NoticeDraftService(h.env.registry,h.env.assessment_store,h.store,facts_reader=facts).create(
        h.env.run.id,h.env.assessment.id,idempotency_key='second').model_dump(mode='json')
    def forbidden(*a,**k):raise AssertionError('Report must not generate or initialize Notice')
    monkeypatch.setattr(NoticeDraftService,'create',forbidden)
    monkeypatch.setattr(NoticeDraftStore,'initialize',forbidden)
    monkeypatch.setattr(FixtureReader,'read',forbidden)
    algorithm,graph=h.graph.capture(h.env.registry.get(h.env.run.id))
    refs=[ref(second),ref(h.draft)]
    extra=dict(task_refs=[dict(task_id=h.env.task.task_id,version=h.env.task.version)],
               algorithm_refs=[algorithm.model_dump(mode='json')])
    before=state(h.env)
    response=post(h,refs=refs,**extra)
    assert response.status_code==200,response.text
    snapshot=response.json();validator('ReportV2Snapshot').validate(snapshot)
    assert snapshot['binding']['notice_refs']==sorted(refs,key=lambda x:x['draft_id'])
    assert post(h,refs=list(reversed(refs)),**extra).json()==snapshot
    doc=h.client.get(next(a['href'] for a in snapshot['artifacts'] if a['format']=='json')).json()
    observations=[r for r in doc['sections'] if r['authority']=='observation']
    assert len(observations)==3
    notices=[r for r in observations if 'draft_id' in r['content']]
    assert [r['content'] for r in notices]==sorted([second,h.draft],key=lambda d:d['draft_id'])
    for row in notices:
        assert row['source_ids']==[row['content']['draft_id']]
        assert row['schema_version']==row['content']['schema_version']=='1.0'
        validator('NoticeDraft').validate(row['content'])
    assert all(state(h.env)[p]==sha for p,sha in before.items() if not p.startswith('reports/'))


@pytest.mark.parametrize('case,status,code',[
    ('wrong_hash',409,'conflict'),('duplicate',400,'invalid_argument'),
    ('missing',404,'not_found'),('malformed_hash',400,'invalid_argument'),
    ('empty_id',400,'invalid_argument'),('cross_scan',404,'not_found'),
    ('cross_assessment',404,'not_found'),('corrupt_db',503,'upstream_unavailable'),
])
def test_bad_requests_are_atomic(notice_http,case,status,code):
    h=notice_http;refs=[ref(h.draft)]
    if case=='wrong_hash':refs[0]['content_hash']='0'*64
    elif case=='duplicate':refs*=2
    elif case=='missing':refs[0]['draft_id']='ntc_missing'
    elif case=='malformed_hash':refs[0]['content_hash']='bad'
    elif case=='empty_id':refs[0]['draft_id']=''
    elif case in ('cross_scan','cross_assessment'):
        def mutate(d):
            if case=='cross_scan':
                d['binding']['scan_ref']['scan_id']='other-scan'
                d['binding']['assessment_ref']['scan_id']='other-scan'
            else:d['binding']['assessment_ref']['assessment_id']='other-assessment'
            d['provenance']['source_refs']=[copy.deepcopy(d['binding']['scan_ref'])]
            d['provenance']['assessment_refs']=[copy.deepcopy(d['binding']['assessment_ref'])]
        refs=[ref(save_variant(h,mutate))]
    elif case=='corrupt_db':
        with sqlite3.connect(h.store.path) as db:
            db.execute("UPDATE notice_drafts SET payload_hash=?",('0'*64,))
    before=state(h.env)
    error(post(h,refs=refs),status,code)
    assert state(h.env)==before
    assert h.env.report_store.request_fingerprint(h.env.run.id,h.env.assessment.id,'binding') is None


@pytest.mark.parametrize('field', ['registry_revision','inventory_hash','assessment_version','usage_hash','rule_version',
                                  'resource','evidence'])
def test_valid_notice_wrong_full_binding_or_reference_rejected(notice_http,field):
    h=notice_http
    def mutate(d):
        b=d['binding']
        if field=='registry_revision':b['scan_ref'][field]+=1
        elif field=='inventory_hash':b['scan_ref'][field]='1'*64
        elif field=='assessment_version':b['assessment_ref']['version']+=1
        elif field in ('usage_hash','rule_version'):b['assessment_ref'][field]='1'*64
        elif field=='resource':d['entries'][0]['resource_ids']=['unknown-resource']
        else:d['entries'][0]['evidence_refs']=[dict(namespace='scan',scan_id=h.env.run.id,evidence_id='unknown-evidence')]
        d['provenance']['source_refs']=[copy.deepcopy(b['scan_ref'])]
        d['provenance']['assessment_refs']=[copy.deepcopy(b['assessment_ref'])]
        d['provenance']['parameters_hash']='2'*64
    bad=save_variant(h,mutate)
    before=state(h.env)
    error(post(h,refs=[ref(bad)]),409,'conflict')
    assert state(h.env)==before


def test_invalid_saved_content_with_recomputed_row_hash_is_503(notice_http):
    h=notice_http;bad=copy.deepcopy(h.draft)
    bad['entries'][0]['text']='tampered'
    from app.p1.notice_facts import canonical
    raw=canonical(bad)
    with sqlite3.connect(h.store.path) as db:
        db.execute('UPDATE notice_drafts SET payload=?,payload_hash=?',(raw,hashlib.sha256(raw).hexdigest()))
    before=state(h.env)
    error(post(h),503,'upstream_unavailable');assert state(h.env)==before


def test_missing_reader_and_empty_refs_compatibility(notice_http,monkeypatch):
    h=notice_http;h.service.notice_reader=None
    before=state(h.env)
    response=post(h)
    error(response,409,'not_ready')
    assert response.json()['error']['details']['reason']=='notice_snapshot_reader_not_available'
    assert state(h.env)==before
    h.service.notice_reader=SimpleNamespace(read=lambda *a:pytest.fail('empty refs must not read'))
    assert post(h,refs=[]).status_code==200


def test_restart_download_replay_without_any_upstream(notice_http,monkeypatch):
    h=notice_http;snapshot=post(h).json()
    artifacts={a['format']:h.client.get(a['href']).content for a in snapshot['artifacts']}
    before=state(h.env)
    def forbidden(*a,**k):raise AssertionError('immutable report must not reread sources or render')
    for obj,name in [(h.env.registry,'get'),(h.env.assessment_store,'get'),(h.env.task_store,'get_version'),
                     (h.store,'get'),(h.reader,'read'),(h.graph,'read')]:
        monkeypatch.setattr(obj,name,forbidden)
    monkeypatch.setattr('app.p1.report_v2._render_html',forbidden)
    monkeypatch.setattr('app.p1.report_v2._render_json',forbidden)
    h.service.notice_reader=None
    h.service.report_store=ReportV2Store(h.env.report_store.path,min_free_bytes=0)
    assert post(h).json()==snapshot
    error(post(h,refs=[]),409,'conflict')
    for _ in range(3):
        for a in snapshot['artifacts']:
            assert h.client.get(a['href']).content==artifacts[a['format']]
    assert state(h.env)==before


def test_html_escapes_text_and_keeps_full_appendix(notice_http):
    h=notice_http
    def mutate(d):
        d['entries'][0]['text']='<script>alert("x")</script><img src="https://invalid.example/a">'
        d['entries'][0]['missing']=['<missing>']
        d['coverage_gaps'].append('<gap>')
        d['provenance']['parameters_hash']='3'*64
    draft=save_variant(h,mutate)
    snapshot=post(h,refs=[ref(draft)]).json()
    artifacts={a['format']:h.client.get(a['href']).content for a in snapshot['artifacts']}
    page=artifacts['html'].decode()
    assert 'NOTICE 草稿／待人工核验' in page and '摘录不等于完整原文' in page
    assert '材料缺失' in page and '&lt;missing&gt;' in page and '&lt;gap&gt;' in page
    assert '<script>' not in page and '<img ' not in page
    doc=json.loads(artifacts['json'])
    assert json.loads(html.unescape(re.search(r'<pre id="report-document">(.*?)</pre>',page,re.S)[1]))==doc
    assert next(s['content'] for s in doc['sections'] if s['authority']=='observation')==draft


@pytest.mark.parametrize('budget',['items','bytes','store'])
def test_capacity_rejection_never_truncates_or_writes(notice_http,budget):
    h=notice_http
    if budget=='items':
        run=h.env.run
        h.service.max_included_items=1+len(h.env.assessment.resource_evaluations)+sum(len(getattr(run,n)) for n in
            ('components','ai_assets','evidence','findings','licenses','obligations','remediations'))
    elif budget=='bytes':h.service.max_document_bytes=100
    else:h.env.report_store.max_artifact_bytes=100
    before=state(h.env)
    error(post(h),503,'upstream_unavailable');assert state(h.env)==before
