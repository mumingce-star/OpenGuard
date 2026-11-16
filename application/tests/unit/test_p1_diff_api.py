"""A03 real read-only HTTP comparisons against isolated persisted P0 facts."""
import copy
import hashlib
import json
from uuid import UUID

import pytest
from app.domain.models import ScanRun
from app.assessment.engine import build_assessment, facts_digest
from app.assessment.models import Assessment
from app.domain.usage import UsageDeclaration
from app.persistence import ScanRegistryError
from app.assessment.store import AssessmentStoreError
from test_p1_history_api import env, seed, SAMPLE, NOW
from test_p1_contract_schema import validator, EXAMPLES


def snapshot(env, number, mutate=None, status='completed', **kwargs):
    running = seed(env, number, 'running', **kwargs)
    value = copy.deepcopy(SAMPLE)
    value.update(id=running.id, project=running.project.model_dump(mode='json'),
                 idempotency_key=None, created_at=NOW, started_at=NOW, finished_at=NOW,
                 report_links=[], status=status, stage='completed' if status=='completed' else 'report',
                 progress=100 if status=='completed' else 95, errors=[])
    # Keep real evidence/license fixtures, but isolate changes from unrelated rules.
    value.update(components=[], ai_assets=[], findings=[], obligations=[], remediations=[])
    if mutate: mutate(value)
    if status=='partial':
        value['errors']=[dict(code='scanner_failed',stage='scan',message='fixture coverage gap',recoverable=True)]
    value['summary'] = dict(component_count=len(value['components']), ai_asset_count=len(value['ai_assets']),
                           evidence_count=len(value['evidence']), finding_counts={k:sum(f['outcome']==k for f in value['findings']) for k in ('pass','warning','review_required','unknown')})
    run=ScanRun.model_validate(value)
    env.registry.replace(run, expected_revision=2)
    return run


def component(number=1, version='1.0', name='requests', purl=True, ecosystem='pypi'):
    c=copy.deepcopy(SAMPLE['components'][0])
    c.update(id='cmp_'+str(UUID(int=number)),name=name,version=version,ecosystem=ecosystem,
             purl=f'pkg:{ecosystem}/{name}@{version}' if purl else None)
    return c


def comps(*items):
    return lambda p:p.update(components=list(items))


def query(env, base, target, **params):
    return env.client.get(f'/api/v1/scans/{target.id}/diff',params={'base_scan_id':base.id,**params})


def diff(env,base,target,**params):
    r=query(env,base,target,**params)
    assert r.status_code==200,r.text
    value=r.json();validator('ScanDiffView').validate(value)
    return value


def err(response,status,code):
    assert response.status_code==status,response.text
    assert response.json()['error']['code']==code
    assert 'request_id' in response.json()['error']


def assessment(env,run,usage='internal',mutate=None,version=1):
    a=build_assessment(run,UsageDeclaration(preset=usage),version=version)
    data=a.model_dump(mode='json')
    if version > 1:
        data['cache_key']=hashlib.sha256((data['cache_key']+str(version)).encode()).hexdigest()
    if mutate:mutate(data)
    a=Assessment.model_validate(data)
    env.store.create(a,idempotency_key=run.id+str(version),run=run)
    return a


def test_same_project_revision_refs_and_identical_resources(env):
    a=snapshot(env,1,comps(component()),revision='aaa')
    b=snapshot(env,2,comps(component(2)),revision='bbb',source='https://github.com/owner/repo.git')
    d=diff(env,a,b)
    assert d['resources']==[]
    assert d['project_identity_key']=='github.com/owner/repo'
    for side,run in [('base',a),('target',b)]:
        assert d[side]['facts_hash']==facts_digest(run)
        assert d[side]['registry_revision']==3
        assert d[side]['input_hash']==run.provenance.input_digest.value
    assert d['assessment_diff']['status']=='unavailable'


@pytest.mark.parametrize('source,source_type', [('https://github.com/owner/other','git'),('local/input.zip','zip'),('local/input','local')])
def test_project_identity_gate(env,source,source_type):
    a=snapshot(env,1,source=source,source_type=source_type)
    b=snapshot(env,2,source='https://github.com/owner/repo' if source_type=='git' else source,source_type=source_type)
    err(query(env,a,b),409,'not_comparable')


@pytest.mark.parametrize('state,code',[('queued','not_ready'),('running','not_ready'),('failed','not_comparable'),('cancelled','not_comparable')])
@pytest.mark.parametrize('side',['base','target'])
def test_terminal_gate(env,state,code,side):
    a=seed(env,1,state);b=snapshot(env,2)
    err(query(env,*( (a,b) if side=='base' else (b,a))),409,code)


def test_parameters_and_missing_scan(env):
    a=snapshot(env,1);b=snapshot(env,2)
    err(query(env,a,a),400,'invalid_argument')
    err(env.client.get(f'/api/v1/scans/{b.id}/diff'),400,'invalid_argument')
    err(query(env,a,b,base_assessment_id='asmt_missing'),400,'invalid_argument')
    err(query(env,a,b,target_assessment_id='asmt_missing'),400,'invalid_argument')
    err(query(env,a,b,base_assessment_id='',target_assessment_id=''),400,'invalid_argument')
    err(env.client.get(f'/api/v1/scans/{b.id}/diff',params={'base_scan_id':'scn_'+str(UUID(int=999))}),404,'not_found')


@pytest.mark.parametrize('before',[None,'','1.0'])
def test_version_change_preserves_scalar(env,before):
    a=snapshot(env,1,comps(component(version=before,purl=False)))
    b=snapshot(env,2,comps(component(2,version='2.0',purl=False)))
    d=diff(env,a,b);assert len(d['resources'])==1
    c=d['resources'][0];assert c['kind']=='changed'
    v=next(x for x in c['field_changes'] if x['path'].endswith('/version'))
    assert v['before']==before and v['after']=='2.0'
    refs={(x['scan_id'],x['evidence_id']) for x in c['evidence_refs']}
    assert refs=={(a.id,a.components[0].evidence_ids[0]),(b.id,b.components[0].evidence_ids[0])}


def test_exact_instance_priority_then_unique_identity(env):
    a=snapshot(env,1,comps(component(1,'1'),component(2,'2')))
    b=snapshot(env,2,comps(component(3,'2'),component(4,'3')))
    rows=diff(env,a,b)['resources']
    assert len(rows)==1 and rows[0]['kind']=='changed'
    assert rows[0]['before']['resource_id']==a.components[0].id
    assert rows[0]['after']['resource_id']==b.components[1].id


def test_duplicate_identities_are_ambiguous_and_never_force_pair(env):
    a=snapshot(env,1,comps(component(1,'1'),component(2,'2')))
    b=snapshot(env,2,comps(component(3,'3'),component(4,'4')))
    rows=diff(env,a,b)['resources']
    assert len(rows)==4 and {r['kind'] for r in rows}=={'ambiguous'}
    assert all((r['before'] is None)!=(r['after'] is None) for r in rows)
    assert all(r['removal_confirmed'] is None for r in rows)


def test_unknown_identity_keeps_null_and_unmatched(env):
    a=snapshot(env,1,comps(component(ecosystem='unknown',purl=False)))
    b=snapshot(env,2,comps(component(2,ecosystem='unknown',purl=False)))
    rows=diff(env,a,b)['resources'];assert len(rows)==2
    assert all(r['kind']=='unmatched' and (r['before'] or r['after'])['resource_identity_key'] is None for r in rows)


@pytest.mark.parametrize('base_state,target_state',[('completed','completed'),('completed','partial'),('partial','completed')])
def test_added_not_observed_and_coverage(env,base_state,target_state):
    a=snapshot(env,1,comps(component(name='old')),status=base_state)
    b=snapshot(env,2,comps(component(2,name='new')),status=target_state)
    d=diff(env,a,b);removed=next(r for r in d['resources'] if r['kind']=='not_observed_in_target')
    assert removed['removal_confirmed'] is (True if base_state==target_state=='completed' else None)
    assert any(r['kind']=='added' for r in d['resources'])
    assert d['coverage']['base_complete']==(base_state=='completed')
    assert d['coverage']['target_complete']==(target_state=='completed')
    assert bool(d['coverage']['gaps'])==(base_state=='partial' or target_state=='partial')
    assert 'SECRET' not in json.dumps(d) and '/private/internal' not in json.dumps(d)


def asset(number=1,**changes):
    a=copy.deepcopy(SAMPLE['ai_assets'][0]);a.update(id='ast_'+str(UUID(int=number)),**changes);return a


def test_runtime_provider_evidence_not_resource_identity(env):
    def mutate(p,number,runtime):
        p['ai_assets']=[asset(number)]
        p['evidence'][1]['excerpt']=f'runtime provider={runtime}'
    a=snapshot(env,1,lambda p:mutate(p,1,'together'))
    b=snapshot(env,2,lambda p:mutate(p,2,'ollama'))
    assert diff(env,a,b)['resources']==[]


def test_asset_kinds_are_distinct_identity(env):
    a=snapshot(env,1,lambda p:p.update(ai_assets=[asset(asset_type='model')]))
    b=snapshot(env,2,lambda p:p.update(ai_assets=[asset(2,asset_type='dataset')]))
    assert {r['kind'] for r in diff(env,a,b)['resources']}=={'added','not_observed_in_target'}


def test_license_and_verification_are_separate_facts(env):
    def mutate(p):
        p['components']=[component(2)]
        p['licenses'][0].update(expression='Apache-2.0',normalized_ids=['Apache-2.0'],verification_status='verified')
        p['ai_assets']=[asset(2,authorization_status='verified')]
        p['evidence'][0]['verification_status']='verified'
    a=snapshot(env,1,lambda p:p.update(components=[component()],ai_assets=[asset()]))
    b=snapshot(env,2,mutate)
    d=diff(env,a,b)
    assert any(c['before']=='MIT' and c['after']=='Apache-2.0' for c in d['license_observation_changes'])
    assert any(c['before']=='pending' and c['after']=='verified' for c in d['verification_changes'])
    assert all('verification_status' not in c['path'] for c in d['license_observation_changes'])
    assert all('license_expression_id' not in c['path'] for c in d['license_observation_changes'])
    assert all('authorization_status' not in change['path'] and 'license_expression_id' not in change['path']
               for row in d['resources'] for change in row['field_changes'])
    for group in ['license_observation_changes','verification_changes']:
        assert d[group]
        for c in d[group]:
            assert c['source_ids_before'] or c['source_ids_after']
            for ref in c['evidence_refs']:
                run={a.id:a,b.id:b}[ref['scan_id']]
                assert ref['evidence_id'] in {e.id for e in run.evidence}


def test_finding_pairs_resource_and_rule_not_description(env):
    def mutate(p,number,severity):
        c=component(number);p['components']=[c]
        f=copy.deepcopy(SAMPLE['findings'][0]);f.update(id='rsk_'+str(UUID(int=number)),resource_id=c['id'],severity=severity,description=f'text {number}',obligation_ids=[],remediation_id=None)
        p['findings']=[f]
    a=snapshot(env,1,lambda p:mutate(p,1,'low'))
    b=snapshot(env,2,lambda p:mutate(p,2,'high'))
    changes=diff(env,a,b)['finding_changes']
    c=next(c for c in changes if c['path'].endswith('/severity'))
    assert (c['before'],c['after'])==('low','high')
    assert c['source_ids_before']==[a.findings[0].id] and c['source_ids_after']==[b.findings[0].id]


def test_assessments_missing_one_or_explicit_missing(env):
    a=snapshot(env,1);b=snapshot(env,2);aa=assessment(env,a)
    assert diff(env,a,b)['assessment_diff']['status']=='unavailable'
    d=diff(env,a,b,base_assessment_id='asmt_missing_base',target_assessment_id='asmt_missing_target')
    assert d['assessment_diff']['status']=='unavailable'


def test_explicit_assessment_ids_bound_to_wrong_scans_are_rejected(env):
    a=snapshot(env,1);b=snapshot(env,2);aa=assessment(env,a);bb=assessment(env,b)
    err(query(env,a,b,base_assessment_id=bb.id,target_assessment_id=aa.id),400,'invalid_argument')


def test_assessment_formal_change_and_ai_excluded(env):
    a=snapshot(env,1);b=snapshot(env,2)
    aa=assessment(env,a)
    def change(p):
        p.update(ai_summary='UNTRUSTED QWEN TEXT',ai_status='succeeded')
        p['dimensions'][0].update(status='restricted',restrictions=['retain notice'])
    bb=assessment(env,b,mutate=change)
    d=diff(env,a,b)['assessment_diff']
    assert d['status']=='compared' and d['base']['assessment_id']==aa.id and d['target']['assessment_id']==bb.id
    assert any(c['path'].endswith('/status') and c['after']=='restricted' for c in d['changes'])
    assert any(c['after']=='retain notice' for c in d['changes'])
    assert 'UNTRUSTED' not in json.dumps(d)


def test_only_ai_change_produces_no_formal_change(env):
    a=snapshot(env,1);b=snapshot(env,2)
    assessment(env,a);assessment(env,b,mutate=lambda p:p.update(ai_summary='MODEL_TEXT',ai_status='succeeded'))
    assert diff(env,a,b)['assessment_diff']['changes']==[]


def test_usage_mismatch_and_rule_attribution(env):
    a=snapshot(env,1);b=snapshot(env,2)
    assessment(env,a);assessment(env,b,usage='unknown')
    d=diff(env,a,b)['assessment_diff'];assert d['status']=='not_comparable' and 'usage' in d['reason'] and not d['changes']
    assessment(env,b,version=2,mutate=lambda p:p.update(rule_version='changed-rules'))
    d=diff(env,a,b)['assessment_diff'];assert d['status']=='compared' and 'rule' in d['reason']


@pytest.mark.parametrize('corruption',['facts_hash','scan_id','formal'])
@pytest.mark.parametrize('missing_other',[False,True])
def test_assessment_integrity_before_comparison(env,monkeypatch,corruption,missing_other):
    a=snapshot(env,1);b=snapshot(env,2);aa=assessment(env,a)
    bb=None if missing_other else assessment(env,b)
    broken=aa.model_copy(update={corruption: {'facts_hash':'0'*64,'scan_id':b.id,'formal':False}[corruption]})
    monkeypatch.setattr(env.store,'latest',lambda sid:broken if sid==a.id else bb)
    err(query(env,a,b),503,'upstream_unavailable')


def test_explicit_assessment_selection_and_latest_view_binding(env):
    a=snapshot(env,1);b=snapshot(env,2);aa=assessment(env,a);bb=assessment(env,b)
    first=diff(env,a,b)
    assessment(env,b,version=2)
    second=diff(env,a,b)
    assert first['view_id']!=second['view_id']
    old=diff(env,a,b,base_assessment_id=aa.id,target_assessment_id=bb.id)
    assert old['assessment_diff']['target']['version']==1


def test_repeated_get_readonly_and_deterministic(env,monkeypatch):
    a=snapshot(env,1,comps(component()));b=snapshot(env,2,comps(component(2,'2.0')))
    assessment(env,a);assessment(env,b)
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in env.path.iterdir() if p.is_file()}
    revisions=[env.registry.get(r.id).revision for r in [a,b]]
    def forbidden(*args,**kwargs):raise AssertionError('Diff GET invoked side effect')
    for method in ['create','replace']:monkeypatch.setattr(env.registry,method,forbidden)
    monkeypatch.setattr(env.store,'create',forbidden)
    monkeypatch.setattr('subprocess.Popen',forbidden)
    monkeypatch.setattr('socket.create_connection',forbidden)
    monkeypatch.setattr('app.assessment.engine.build_assessment',forbidden)
    monkeypatch.setattr('app.assessment.service.AssessmentService.generate_assessment',forbidden)
    monkeypatch.setattr('app.ai.OllamaProvider.generate',forbidden)
    monkeypatch.setattr('app.ai.OllamaProvider.generate_project',forbidden)
    values=[diff(env,a,b) for _ in range(3)]
    for value in values:value['provenance'].pop('generated_at')
    assert values[0]==values[1]==values[2]
    after={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in env.path.iterdir() if p.is_file()}
    assert before==after and revisions==[env.registry.get(r.id).revision for r in [a,b]]


@pytest.mark.parametrize('store',['registry','assessment'])
def test_storage_errors_are_safe_503(env,monkeypatch,store):
    a=snapshot(env,1);b=snapshot(env,2)
    def broken(*args):
        raise (ScanRegistryError('registry_io_failed') if store=='registry' else AssessmentStoreError('assessment_store_unavailable'))
    monkeypatch.setattr(env.registry if store=='registry' else env.store,'get' if store=='registry' else 'latest',broken)
    r=query(env,a,b);err(r,503,'upstream_unavailable')
    assert 'Traceback' not in r.text and str(env.path) not in r.text


@pytest.mark.parametrize('empty',[None,''])
def test_erratum_schema_empty_and_null(empty):
    value=copy.deepcopy(EXAMPLES['ScanDiffView'])
    value['resources'][0]['field_changes']=[dict(path='/version',before=empty,after='2.0')]
    validator('ScanDiffView').validate(value)
    assert json.dumps(value['resources'][0]['field_changes'][0]['before'])==('null' if empty is None else '""')


@pytest.mark.parametrize('field',['path','view_id','resource_id','rule_version'])
def test_erratum_does_not_relax_identifiers(field):
    value=copy.deepcopy(EXAMPLES['ScanDiffView'])
    if field=='path':value['resources'][0]['field_changes'][0]['path']=''
    elif field=='view_id':value['view_id']=''
    elif field=='resource_id':value['resources'][0]['before']['resource_id']=''
    else:
        value['assessment_diff']['base']=copy.deepcopy(EXAMPLES['RemediationTask']['assessment_ref'])
        value['assessment_diff']['base']['rule_version']=''
    assert list(validator('ScanDiffView').iter_errors(value))


@pytest.mark.parametrize('purl',[True,False])
def test_python_package_name_normalization_without_changing_facts(env,purl):
    a=snapshot(env,1,comps(component(name='Example_Package',purl=purl)))
    b=snapshot(env,2,comps(component(2,name='example-package',purl=purl)))
    rows=diff(env,a,b)['resources']
    assert len(rows)==1 and rows[0]['kind']=='changed'
    assert rows[0]['before']['resource_identity_key']==rows[0]['after']['resource_identity_key']=='pkg:pypi/example-package'
    assert any(c['before']=='Example_Package' and c['after']=='example-package' for c in rows[0]['field_changes'])


def test_case_sensitive_purl_and_qualifier_identity(env):
    c=component();c.update(ecosystem='unknown',purl='pkg:maven/Group/Artifact@1?type=jar&classifier=sources')
    equivalent={**c,'id':'cmp_'+str(UUID(int=2)),'purl':'pkg:maven/Group/Artifact@2?classifier=sources&type=jar','version':'2'}
    a=snapshot(env,1,comps(c));b=snapshot(env,2,comps(equivalent))
    rows=diff(env,a,b)['resources'];assert len(rows)==1 and rows[0]['kind']=='changed'
    assert rows[0]['before']['resource_identity_key']==rows[0]['after']['resource_identity_key']
    different={**equivalent,'purl':'pkg:maven/group/Artifact@2?classifier=sources&type=jar'}
    other=snapshot(env,3,comps(different))
    assert {r['kind'] for r in diff(env,a,other)['resources']}=={'added','not_observed_in_target'}


def test_ai_verification_uses_same_paired_resource(env):
    a=snapshot(env,1,lambda p:p.update(ai_assets=[asset()]))
    b=snapshot(env,2,lambda p:p.update(ai_assets=[asset(2,authorization_status='rejected')]))
    c=next(c for c in diff(env,a,b)['verification_changes'] if c['path'].endswith('/authorization_status'))
    assert (c['before'],c['after'])==('pending','rejected')
    assert c['source_ids_before']==[a.ai_assets[0].id] and c['source_ids_after']==[b.ai_assets[0].id]


def test_finding_outcome_rule_version_and_duplicates(env):
    def facts(p,number,outcome,duplicate=False):
        c=component(number);p['components']=[c]
        f=copy.deepcopy(SAMPLE['findings'][0]);f.update(id='rsk_'+str(UUID(int=number)),resource_id=c['id'],outcome=outcome,rule_version=str(number),obligation_ids=[],remediation_id=None)
        p['findings']=[f]
        if duplicate:p['findings'].append({**f,'id':'rsk_'+str(UUID(int=number+10)),'severity':'high'})
    a=snapshot(env,1,lambda p:facts(p,1,'review_required'))
    b=snapshot(env,2,lambda p:facts(p,2,'warning'))
    changes=diff(env,a,b)['finding_changes']
    assert any(c['before']=='review_required' and c['after']=='warning' for c in changes)
    assert any(c['before']=='1' and c['after']=='2' for c in changes)
    c=snapshot(env,3,lambda p:facts(p,3,'warning',True))
    changes=diff(env,a,c)['finding_changes']
    assert all(not(row['source_ids_before'] and row['source_ids_after']) for row in changes)
    assert {rid for row in changes for rid in row['source_ids_after']}=={f.id for f in c.findings}


def test_same_local_resource_id_does_not_override_unknown_identity(env):
    a=snapshot(env,1,comps(component(ecosystem='unknown',purl=False)))
    b=snapshot(env,2,comps(component(ecosystem='unknown',purl=False)))
    d=diff(env,a,b)
    assert all(r['kind']=='unmatched' for r in d['resources'])
    assert all(not(c['source_ids_before'] and c['source_ids_after']) for c in d['license_observation_changes'])


def test_empty_scan_reference_is_safe_integrity_error_not_normalized(env):
    a=snapshot(env,1,revision='');b=snapshot(env,2,revision='abc')
    err(query(env,a,b),503,'upstream_unavailable')
    assert env.registry.get(a.id).run.project.revision==''


def test_completed_with_diagnostics_does_not_confirm_removal(env):
    def facts(p):
        p['components']=[component()]
        p['errors']=[dict(code='scanner_failed',stage='scan',message='coverage diagnostic',recoverable=True)]
    a=snapshot(env,1,facts);b=snapshot(env,2)
    d=diff(env,a,b)
    assert d['resources'][0]['removal_confirmed'] is None
    assert d['coverage']['gaps'] and d['coverage']['base_complete']


def test_invalid_package_name_does_not_invent_identity(env):
    a=snapshot(env,1,comps(component(name=' ',purl=False)))
    b=snapshot(env,2,comps(component(2,name=' ',purl=False)))
    assert all(r['kind']=='unmatched' for r in diff(env,a,b)['resources'])
