"""Exact pure automatic-review GET integration; isolated synthetic fixtures."""
import hashlib
import pytest
from test_p2_contract import setup, create

def snapshot(root):
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.db')}

def test_automatic_get_is_stable_pure_and_preserves_parent(setup):
    c,app,base,_,root=setup
    result=create(setup)
    before=snapshot(root)
    path=base+'/results/'+result['result_id']+'/automatic-review?assessment_version=1'
    reply=c.get(path)
    assert reply.status_code==200,reply.text
    value=reply.json()
    assert value['source_status']=='NOT_CONFIGURED'
    assert value['result_sha256']==result['result_sha256']
    assert value['binding']==result['binding'] and value['usage']==result['usage']
    assert value['formal_effect']=='none' and value['model_calls']==0
    assert value['applicability_review']=='NOT_SIGNED'
    assert value['summary']['total_resources']==len(result['resources'])
    assert sum(value['summary']['priority_counts'].values())==len(result['resources'])
    assert c.get(path).content==reply.content
    assert c.get(base+'/results/'+result['result_id']+'?assessment_version=1').json()==result
    assert snapshot(root)==before

@pytest.mark.parametrize('version,status',[(0,422),(2,409)])
def test_automatic_get_keeps_version_binding(setup,version,status):
    c,_,base,_,_=setup;r=create(setup)
    assert c.get(base+'/results/'+r['result_id']+'/automatic-review?assessment_version='+str(version)).status_code==status

def test_missing_source_pin_is_503_without_path_disclosure(setup):
    c,app,base,_,_=setup;r=create(setup)
    app.state.p2_service.automatic_source_root='/private/not-to-be-disclosed'
    app.state.p2_service.automatic_source_profile_sha256='0'*64
    response=c.get(base+'/results/'+r['result_id']+'/automatic-review?assessment_version=1')
    assert response.status_code==503
    assert response.json()['error']['code']=='p2_automatic_source_invalid'
    assert '/private/' not in response.text

def test_missing_result_is_404_not_generated(setup):
    c,_,base,_,root=setup;before=snapshot(root)
    assert c.get(base+'/results/p2res_missing/automatic-review?assessment_version=1').status_code==404
    assert snapshot(root)==before

@pytest.mark.parametrize('expression,normalized,expected',[
    ('NOASSERTION', ['GPL-3.0-only'], 'CONFLICT_OR_UNSUPPORTED'),
    ('NONE', ['MIT'], 'CONFLICT_OR_UNSUPPORTED'),
    ('MIT', ['ISC'], 'CONFLICT_OR_UNSUPPORTED'),
    ('ISC', [], 'CONFLICT_OR_UNSUPPORTED'),
    ('MIT', ['MIT'], 'MIT'),
    ('ISC', ['ISC'], 'ISC'),
    ('NOASSERTION', [], 'UNOBSERVED'),
])
def test_normalized_license_conflict_is_not_erased(setup,monkeypatch,expression,normalized,expected):
    import app.p2.automatic_review as review
    c,app,base,_,_=setup;result=create(setup)
    svc=app.state.p2_service
    run,a,binding,resources=svc.context(result['binding']['scan_id'],result['binding']['assessment_id'])
    resource=next(iter(resources.values()))
    license_=next(l for l in run.licenses if l.id==resource.license_expression_id)
    license_.expression=expression;license_.normalized_ids=normalized
    monkeypatch.setattr(svc,'context',lambda *args:(run,a,binding,resources))
    original=review.project;captured=[]
    def observe(*args,**kwargs):
        captured.append(kwargs['declared_licenses'][resource.id])
        return original(*args,**kwargs)
    monkeypatch.setattr(review,'project',observe)
    response=c.get(base+'/results/'+result['result_id']+'/automatic-review?assessment_version=1')
    assert response.status_code==200,response.text
    assert captured==[expected]
