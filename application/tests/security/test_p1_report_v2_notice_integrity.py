"""Rehashed envelope attacks must not turn Notice observations into trusted facts."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'unit'))
from test_p1_report_v2_service import report_env
from test_p1_report_v2_notice import notice_http, post, state, error, ref
from app.p1.report_v2_store import ReportV2StoreError
from app.p1.notice_draft_store import content_hash


def raw(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def rehash(snapshot,document,payloads):
    base=snapshot['artifacts'][0]['href'].split('?')[0]
    for i,row in enumerate(document['sections']):
        row['content_hash']=sha(raw(row['content']))
        row['snapshot_ref']=base+f'?format=json#/sections/{i}/content'
    snapshot['sections']=[{k:v for k,v in row.items() if k!='content'} for row in document['sections']]
    document['binding']=copy.deepcopy(snapshot['binding'])
    payloads['json']=raw(document)
    for a in snapshot['artifacts']:
        a['content_hash']=sha(payloads[a['format']]);a['size_bytes']=len(payloads[a['format']])
    snapshot['content_hash']=sha(raw({k:v for k,v in snapshot.items() if k not in ('content_hash','artifacts')}))


@pytest.mark.parametrize('attack', ['text','inner_rehash','scan_binding','assessment_binding','missing_section',
    'unreferenced','duplicate_section','source_id','schema_version','graph_disguise','extra_field','missing_field'])
def test_rehashed_report_notice_tamper_rejected(notice_http,attack):
    h=notice_http;snapshot=post(h).json()
    payloads={a['format']:h.client.get(a['href']).content for a in snapshot['artifacts']}
    document=json.loads(payloads['json'])
    row=next(r for r in document['sections'] if r['authority']=='observation');draft=row['content']
    if attack in ('text','inner_rehash'):
        draft['entries'][0]['text']='altered'
        if attack=='inner_rehash':draft['content_hash']=content_hash(draft)
    elif attack in ('scan_binding','assessment_binding'):
        if attack=='scan_binding':draft['binding']['scan_ref']['registry_revision']+=1
        else:draft['binding']['assessment_ref']['rule_version']='other-rules'
        draft['provenance']['source_refs']=[copy.deepcopy(draft['binding']['scan_ref'])]
        draft['provenance']['assessment_refs']=[copy.deepcopy(draft['binding']['assessment_ref'])]
        draft['content_hash']=content_hash(draft)
        snapshot['binding']['notice_refs'][0]['content_hash']=draft['content_hash']
    elif attack=='missing_section':document['sections'].remove(row)
    elif attack=='unreferenced':snapshot['binding']['notice_refs']=[]
    elif attack=='duplicate_section':document['sections'].append(copy.deepcopy(row))
    elif attack=='source_id':row['source_ids']=['ntc_wrong']
    elif attack=='schema_version':row['schema_version']='2.0'
    elif attack=='graph_disguise':
        reference,graph=h.graph.capture(h.env.registry.get(h.env.run.id));row['content']=graph
    elif attack=='extra_field':draft['unknown']='extension'
    elif attack=='missing_field':del draft['entries'][0]['missing']
    rehash(snapshot,document,payloads)
    before=state(h.env)
    with pytest.raises(ReportV2StoreError) as caught:
        h.env.report_store.create(h.env.run.id,h.env.assessment.id,'attack','irrelevant',snapshot,payloads)
    assert caught.value.code == "invalid_argument"
    assert state(h.env)==before


def test_corrupt_saved_report_download_rejected_without_repair(notice_http):
    h=notice_http;snapshot=post(h).json()
    payloads={a['format']:h.client.get(a['href']).content for a in snapshot['artifacts']}
    document=json.loads(payloads['json'])
    draft=next(r['content'] for r in document['sections'] if r['authority']=='observation')
    draft['entries'][0]['text']='tamper';draft['content_hash']=content_hash(draft)
    rehash(snapshot,document,payloads)
    with sqlite3.connect(h.env.report_store.path) as db:
        db.execute('UPDATE report_snapshots SET payload=?,payload_hash=?',(raw(snapshot),sha(raw(snapshot))))
        db.execute("UPDATE report_artifacts SET payload=?,payload_hash=?,size_bytes=? WHERE format='json'",
                   (payloads['json'],sha(payloads['json']),len(payloads['json'])))
    before=state(h.env)
    for a in snapshot['artifacts']:
        error(h.client.get(a['href']),503,'upstream_unavailable')
    assert state(h.env)==before


def test_later_notice_failure_has_no_partial_report(notice_http,monkeypatch):
    h=notice_http;calls=[];read=h.reader.read
    def spy(*a):calls.append(a[2].draft_id);return read(*a)
    monkeypatch.setattr(h.reader,'read',spy)
    before=state(h.env)
    error(post(h,refs=[ref(h.draft),dict(draft_id='ntc_zzzz',content_hash='0'*64)]),404,'not_found')
    assert calls==[h.draft['draft_id'],'ntc_zzzz']
    assert state(h.env)==before
    with sqlite3.connect(h.env.report_store.path) as db:
        for table in ('report_requests','report_snapshots','report_artifacts'):
            assert db.execute(f'SELECT count(*) FROM {table}').fetchone()==(0,)
