"""A04 HTTP/schema/capacity gates on stored facts only."""
import copy
import pytest
from test_p1_history_api import env, seed, SAMPLE
from test_p1_diff_api import snapshot, component, asset
from test_p1_contract_schema import validator


def graph(env, run, **params):
    return env.client.get(f'/api/v1/scans/{run.id}/graph', params=params)


@pytest.mark.parametrize('params', [{}, {'resource_kinds':'component'}, {'resource_kinds':'ai_asset'}])
def test_http_matches_frozen_schema_and_counts(env, params):
    run = seed(env, 1, 'completed')
    response = graph(env, run, **params)
    assert response.status_code == 200, response.text
    value = response.json()
    validator('ResourceGraphView').validate(value)
    assert value['coverage']['node_count'] == len(value['nodes'])
    assert value['coverage']['edge_count'] == len(value['edges'])
    assert value['coverage']['scan_gaps'] == []
    assert value['provenance']['assessment_refs'] == []
    assert value['nodes'] == sorted(value['nodes'],key=lambda n:(n['kind'],n['source_id']))
    assert value['edges'] == sorted(value['edges'],key=lambda e:(e['type'],e['source'],e['target'],e['id']))
    again = graph(env,run,**params).json()
    again['provenance']['generated_at'] = value['provenance']['generated_at']
    assert again == value


@pytest.mark.parametrize('dimension', ['nodes','edges'])
def test_capacity_exact_boundary_and_overflow(env, dimension):
    run=seed(env,1,'completed')
    full=graph(env,run).json()
    count=len(full[dimension])
    setattr(env.app.state, 'p1_graph_max_'+dimension, count)
    assert graph(env,run).status_code == 200
    setattr(env.app.state, 'p1_graph_max_'+dimension, count-1)
    response=graph(env,run)
    assert response.status_code == 413
    value=response.json()
    assert value['error']['code']=='graph_capacity_exceeded'
    details=value['error']['details']
    assert details['count_basis']=='actual'
    assert details['node_count']==len(full['nodes'])
    assert details['edge_count']==len(full['edges'])
    assert details['configured_capacity']['max_'+dimension]==count-1
    assert 'nodes' not in value and 'edges' not in value


def test_filtered_capacity_can_return_complete_selection(env):
    run=seed(env,1,'completed')
    selected=graph(env,run,resource_kinds='ai_asset').json()
    env.app.state.p1_graph_max_nodes=len(selected['nodes'])
    assert graph(env,run).status_code==413
    result=graph(env,run,resource_kinds='ai_asset')
    assert result.status_code==200
    assert result.json()['coverage']['view_complete'] is True
    validator('ResourceGraphView').validate(result.json())


def test_project_only_filtered_at_capacity_one(env):
    run=seed(env,1,'completed')
    env.app.state.p1_graph_max_nodes=1
    env.app.state.p1_graph_max_edges=1
    value=graph(env,run,resource_ids=run.components[0].id,resource_kinds='ai_asset').json()
    assert value['coverage']==dict(view_complete=True,scope='filtered',node_count=1,edge_count=0,scan_gaps=[])


def test_no_resource_license_or_finding_obligation_is_invented(env):
    c=component(); c['license_expression_id']=None
    finding=copy.deepcopy(SAMPLE['findings'][0])
    finding.update(resource_id=c['id'],obligation_ids=[],remediation_id=None)
    run=snapshot(env,1,lambda p:p.update(components=[c],findings=[finding],obligations=copy.deepcopy(SAMPLE['obligations'])))
    value=graph(env,run).json()
    types={e['type'] for e in value['edges']}
    assert 'RESOURCE_HAS_LICENSE_OBSERVATION' not in types
    assert 'FINDING_REFERENCES_OBLIGATION' not in types
    assert 'LICENSE_HAS_RULE_OBLIGATION' in types
    assert len([n for n in value['nodes'] if n['kind']=='license_observation'])==len(run.licenses)


@pytest.mark.parametrize('key',['next_cursor','page_size','anything'])
def test_all_unknown_queries_rejected_without_echo(env,key):
    run=seed(env,1,'completed')
    response=graph(env,run,**{key:'private-marker'})
    assert response.status_code==400
    assert response.json()['error']['code']=='invalid_argument'
    assert 'private-marker' not in response.text


def test_missing_scan_safe_404(env):
    response=env.client.get('/api/v1/scans/scn_00000000-0000-4000-8000-000000000099/graph')
    assert response.status_code==404


def test_filter_selects_original_source_index(env):
    a,b=component(1),component(2)
    run=snapshot(env,1,lambda p:p.update(components=[a,b]))
    value=graph(env,run,resource_ids=b['id']).json()
    refs=[r['pointer'] for e in value['edges'] for r in e['source_refs']]
    assert '/components/1' in refs
    assert '/components/0' not in refs


def test_get_no_assessment_reads_and_no_ai_or_network(env,monkeypatch):
    run=seed(env,1,'completed')
    class Forbidden:
        def __getattribute__(self,name):
            raise AssertionError('Graph read assessment/generator service')
    env.app.state.assessment_service=Forbidden()
    def forbidden(*args,**kwargs):raise AssertionError('Graph external side effect')
    monkeypatch.setattr('socket.create_connection',forbidden)
    monkeypatch.setattr('subprocess.Popen',forbidden)
    assert graph(env,run).status_code==200


@pytest.mark.parametrize('status,http_status,code', [
    ('queued',409,'not_ready'), ('running',409,'not_ready'),
    ('failed',409,'not_comparable'), ('cancelled',409,'not_comparable'),
    ('completed',400,'invalid_argument'), ('partial',400,'invalid_argument'),
])
def test_scan_status_precedes_resource_existence(env,status,http_status,code):
    run=seed(env,1,status)
    response=graph(env,run,resource_ids='missing')
    assert response.status_code==http_status, response.text
    assert response.json()['error']['code']==code


@pytest.mark.parametrize('params', [
    {'resource_ids':''}, {'resource_ids':'   '},
    {'resource_kinds':'Component'}, {'resource_kinds':' '}, {'cursor':'x'},
])
def test_graph_query_syntax_precedes_scan_read(env,monkeypatch,params):
    def forbidden(*args,**kwargs):
        raise AssertionError('Invalid query must not read scan storage')
    monkeypatch.setattr(env.registry,'get',forbidden)
    response=env.client.get('/api/v1/scans/scn_00000000-0000-4000-8000-000000000099/graph',params=params)
    assert response.status_code==400
    assert response.json()['error']['code']=='invalid_argument'


def test_missing_scan_precedes_resource_existence(env):
    response=env.client.get('/api/v1/scans/scn_00000000-0000-4000-8000-000000000099/graph',params={'resource_ids':'missing'})
    assert response.status_code==404
    assert response.json()['error']['code']=='not_found'
