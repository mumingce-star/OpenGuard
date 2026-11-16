"""TASK33 permanent cases. Authored only; NOT_RUN under current Owner scope.

Controlled HTTP cases use synthetic source profiles. The separately named real
ZIP case uses preserved is-number release bytes, never old resource/evidence IDs.
"""
import hashlib
import json
from copy import deepcopy
from pathlib import Path
import pytest
from test_p2_contract import setup as base_setup, create, material_body, variant, seed
from test_p2_preliminary import setup, admit, MIT
from app.p2.contract import P2Error
from app.p2.material_claims import project
from app.p2b.material_claims import parse_claim_material

FIXTURE = Path(__file__).resolve().parents[1] / 'fixtures/task33/is-number-7.0.0'


def path(base, result):
    return base + '/results/' + result['result_id'] + '/material-claims?assessment_version=1'


def get(h, result):
    reply = h[0].get(path(h[2], result))
    assert reply.status_code == 200, reply.text
    return reply.json()


def commercial(v):
    return next(a for a in v['advice'] if a['usage'] == 'commercial')


def inputs(h, result):
    svc = h[1].state.p2_service
    _, _, _, resources = svc.context(result['binding']['scan_id'], result['binding']['assessment_id'])
    with svc.store.connection() as db:
        materials = []
        for mid in result['material_ids']:
            m = svc.store.get(db, 'material', mid, result['binding']['scan_id'], result['binding']['assessment_id'])
            materials.append((m, svc.store.material_bytes(db, m)))
    return resources, materials, svc.public_source_root, svc.public_source_profile_sha256


def test_perf_evidence_closure_once_per_resource_and_never_across_requests(setup, monkeypatch):
    """The same complete DTO survives request-local index reuse, with fresh reads."""
    _, result, _, _, _ = admit(setup)
    expected = get(setup, result)
    service = setup[1].state.p2_service
    resources = service.context(result['binding']['scan_id'], result['binding']['assessment_id'])[3]
    original = type(service)._evidence
    observed = []
    def counted(run, resource):
        observed.append(resource.id)
        return original(run, resource)
    monkeypatch.setattr(type(service), '_evidence', staticmethod(counted))
    assert get(setup, result) == expected
    assert sorted(observed) == sorted(resources)
    observed.clear()
    assert get(setup, result) == expected
    assert sorted(observed) == sorted(resources)


def test_perf_source_expansion_shared_only_inside_one_load(setup, monkeypatch):
    """Both parsers see one validated immutable buffer, then recheck next request."""
    from app.p2 import preliminary
    _, result, _, _, _ = admit(setup)
    _, _, root, profile_sha = inputs(setup, result)
    expand = preliminary._bounded_gzip_bytes
    package = preliminary._package_files_expanded
    notice = preliminary._notice_inventory_expanded
    expansions, inputs_seen = [], []
    def counted(raw):
        output = expand(raw)
        expansions.append(output)
        return output
    def package_checked(expanded, member):
        inputs_seen.append(('package', expanded))
        return package(expanded, member)
    def notice_checked(expanded):
        inputs_seen.append(('notice', expanded))
        return notice(expanded)
    monkeypatch.setattr(preliminary, '_bounded_gzip_bytes', counted)
    monkeypatch.setattr(preliminary, '_package_files_expanded', package_checked)
    monkeypatch.setattr(preliminary, '_notice_inventory_expanded', notice_checked)
    first = preliminary.load_sources(root, profile_sha, result['data_scope'], inspect_notices=True)
    assert len(expansions) == 1 and [kind for kind, _ in inputs_seen] == ['package', 'notice']
    assert inputs_seen[0][1] is inputs_seen[1][1] is expansions[0]
    second = preliminary.load_sources(root, profile_sha, result['data_scope'], inspect_notices=True)
    assert first == second and len(expansions) == 2
    assert inputs_seen[2][1] is inputs_seen[3][1] is expansions[1]
    # A later read must still check disk bytes against the immutable source pin.
    source = Path(root) / 'source.tgz'
    source.write_bytes(source.read_bytes() + b'TEST_ONLY_CORRUPTION')
    with pytest.raises(P2Error) as error:
        preliminary.load_sources(root, profile_sha, result['data_scope'], inspect_notices=True)
    assert error.value.code == 'p2_public_source_invalid'
    assert len(expansions) == 2  # mismatch is rejected before using the parser



def declaration_facts(h, result):
    from app.p2.material_claims import evidence_context
    svc = h[1].state.p2_service
    run, _, _, resources = svc.context(result['binding']['scan_id'], result['binding']['assessment_id'])
    return evidence_context(run, resources, result)[0]


def test_exact_text_source_evidence_and_old_revision(setup):
    old, new, _, _, _ = admit(setup)
    view = get(setup, new)
    assert commercial(view)['state'] == 'SUPPORT'
    assert commercial(view)['conditions'] and commercial(view)['limitations']
    assert view['result_sha256'] == new['result_sha256']
    assert view['formal_effect'] == 'none' and view['applicability_review'] == 'NOT_SIGNED'
    assert view['materials'][0]['license_version'] is None
    assert len(view['materials'][0]['clauses']) == 5
    for clause in view['materials'][0]['clauses']:
        raw = MIT[clause['byte_start']:clause['byte_end']]
        assert raw.decode() == clause['quote']
        assert hashlib.sha256(raw).hexdigest() == clause['quote_sha256']
    assert commercial(get(setup, old))['state'] == 'UNKNOWN'
    assert get(setup, old)['materials'] == []  # never borrow a later material
    assert setup[0].get(setup[2]+'/results/'+old['result_id']+'?assessment_version=1').json() == old
    assert get(setup, new) == view  # GET deterministic and never creates a revision


@pytest.mark.parametrize('source_version', ['0.0.0', '99.0.0'])
def test_same_name_wrong_release_version_never_supports(setup, source_version):
    _, result, _, _, _ = admit(setup, source_version=source_version)
    assert commercial(get(setup, result))['state'] == 'UNKNOWN'


@pytest.mark.parametrize('change', ['version', 'foreign_evidence'])
def test_post_rejects_wrong_subject_or_cross_resource_evidence(setup, change):
    old = create(setup)
    request = material_body(old, MIT)
    if change == 'version': request['subject'] = {**request['subject'], 'version':'99.0.0'}
    else: request['evidence_ids'] = ['evd_foreign_resource']
    response = setup[0].post(setup[2]+'/materials', json=request)
    assert response.status_code in {409, 422}
    assert get(setup, old)['materials'] == []


@pytest.mark.parametrize('expression,normalized,state', [
    ('GPL-3.0-only',['GPL-3.0-only'],'COUNTER_EVIDENCE'),
    ('MIT AND Apache-2.0',['MIT','Apache-2.0'],'UNKNOWN'),
    ('MIT OR Apache-2.0',['MIT','Apache-2.0'],'UNKNOWN'),
])
def test_spdx_text_conflict_and_multiple_license_do_not_grant(setup, expression, normalized, state):
    def change(p):
        p['licenses'][0].update(expression=expression, normalized_ids=normalized, verification_status='pending')
    h = variant(setup, change)
    _, result, _, _, _ = admit(h)
    view = get(h, result)
    assert commercial(view)['state'] == state
    if state == 'COUNTER_EVIDENCE':
        assert view['claims'][0]['counter_evidence'][0]['code'] == 'SPDX_TEXT_CONFLICT'


def test_no_material_or_no_source_never_grants(setup):
    old = create(setup)
    assert commercial(get(setup, old))['state'] == 'UNKNOWN'
    request = material_body(old, MIT); request['completeness']='FULL_TEXT_CLAIMED'
    response = setup[0].post(setup[2]+'/materials', json=request)
    assert response.status_code == 201
    view = get(setup, response.json()['result'])
    assert view['materials'][0]['parse_state'] == 'MATCHED_MIT'
    assert commercial(view)['state'] == 'UNKNOWN'


@pytest.mark.parametrize('filename,raw,state', [
    ('LICENCE', b'Other conditions apply.', 'COUNTER_EVIDENCE'),
    ('NOTICE', b'Preserve this notice.', 'UNKNOWN'),
])
def test_additional_license_or_notice_preserves_counterevidence(setup, filename, raw, state):
    _, previous, _, _, _ = admit(setup)
    request = material_body(previous, raw, key='second-material-task33')
    request.update(filename=filename, completeness='FULL_TEXT_CLAIMED')
    response = setup[0].post(setup[2]+'/materials', json=request)
    assert response.status_code == 201, response.text
    view = get(setup, response.json()['result'])
    assert commercial(view)['state'] == state
    assert view['claims'][0]['counter_evidence']
    assert commercial(get(setup, previous))['state'] == 'SUPPORT'


def test_same_filename_different_hash_refused_and_parent_not_overwritten(setup):
    old, current, _, _, _ = admit(setup)
    response = setup[0].post(setup[2]+'/materials', json=material_body(current, MIT+b'Additional terms', key='conflict-task33'))
    assert response.status_code == 409
    stale = setup[0].post(setup[2]+'/materials', json=material_body(old, MIT, key='stale-task33'))
    assert stale.status_code == 409
    for saved in (old, current):
        assert setup[0].get(setup[2]+'/results/'+saved['result_id']+'?assessment_version=1').json() == saved


@pytest.mark.parametrize('raw,state', [(b'MIT License','UNSUPPORTED'), (b'\xff','FAILED'), (b'\x00','FAILED'), (b'','FAILED'), (b'a'*65537,'FAILED')])
def test_parser_unknown_or_invalid_never_invents_clauses(raw, state):
    p = parse_claim_material(raw, 'LICENSE')
    assert p['parse_state'] == state and p['spans'] == []


def test_real_license_and_utf8_crlf_offsets():
    raw = (FIXTURE/'license.txt').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == '35bdd8a44339719441900fb50fbefc5e2dca1ca662cbaed7a687de842c8b70f2'
    for content in (raw, MIT.replace(b'Synthetic Contract Fixture', '来源示例'.encode()).replace(b'\n',b'\r\n')):
        p = parse_claim_material(content, 'LICENSE')
        assert p['parse_state'] == 'MATCHED_MIT'
        for s in p['spans']:
            assert content[s['byte_start']:s['byte_end']].decode() == s['quote']
            assert s['line_start'] == content[:s['byte_start']].count(b'\n')+1


@pytest.mark.parametrize('mutation', ['foreign_subject','foreign_evidence','future_material','raw_hash'])
def test_projection_rejects_tampered_binding_even_without_http(setup, mutation):
    _, result, _, _, _ = admit(setup)
    resources, materials, root, pin = inputs(setup, result)
    materials = deepcopy(materials); m, raw = materials[0]
    if mutation == 'foreign_subject': m['subject']['resource_id']='cmp_other'
    elif mutation == 'foreign_evidence': m['evidence_ids']=['evd_other']
    elif mutation == 'future_material': m['material_id']='p2mat_future'
    else: materials[0]=(m, raw+b' ')
    with pytest.raises(P2Error):
        project(result, resources, materials, root, pin, {rid:'MIT' for rid in resources})


def test_user_reported_unfulfilled_condition_is_restriction(setup):
    _, result, _, _, _ = admit(setup)
    resources, materials, root, pin = inputs(setup, result)
    candidate = deepcopy(result)
    candidate['resources'][0]['user_assertions']['OBLIGATION_FULFILLMENT_IN_DELIVERY']='NOT_FULFILLED'
    view = project(candidate, resources, materials, root, pin, {rid:'MIT' for rid in resources}, declaration_facts=declaration_facts(setup,candidate))
    assert commercial(view)['state'] == 'RESTRICTION'
    assert commercial(view)['conditions']


def test_real_derived_zip_to_resource_material_claim_and_revision(base_setup, tmp_path):
    # Real archived bytes, isolated test DB only. No synthetic scan result or old IDs.
    from test_a4_local_zip_pipeline import _queued, _run
    from app.domain.usage import UsageDeclaration
    c, app, _, _, _ = base_setup
    archive = FIXTURE/'is-number-7.0.0-derived.zip'
    registry, output = _run(tmp_path, archive, _queued(archive, index=3301))
    try:
        component = next(x for x in output.run.components if x.name == 'is-number' and x.version == '7.0.0')
        usage = UsageDeclaration(commercial=True, distributed=True, modified=True, network_service=False,
                                 training=False, redistributed_assets=False, source_disclosure=False)
        assessment = seed(app, output.run, usage)
        base = f'/api/v1/scans/{assessment.scan_id}/assessments/{assessment.id}/p2'
        binding = c.get(base+'/binding').json()
        h = (c, app, base, {'binding':binding,'expected_revision':0,'parent_result_id':None,'idempotency_key':'task33-real-create'}, tmp_path)
        old = create(h)
        row = next(x for x in old['resources'] if x['subject']['resource_id'] == component.id)
        svc = app.state.p2_service
        svc.public_source_root = str(FIXTURE)
        svc.public_source_profile_sha256 = hashlib.sha256((FIXTURE/'profile.json').read_bytes()).hexdigest()
        request = material_body(old, (FIXTURE/'license.txt').read_bytes(), key='task33-real-license')
        request.update(subject=row['subject'], evidence_ids=row['evidence_ids'], completeness='FULL_TEXT_CLAIMED',
                       source_description='Preserved is-number@7.0.0 TGZ member package/LICENSE; applicability NOT_SIGNED')
        reply = c.post(base+'/materials', json=request)
        assert reply.status_code == 201, reply.text
        new = reply.json()['result']; view = get(h, new)
        exact = [a for a in view['advice'] if a['subject'] == row['subject']]
        assert len(exact) == 3 and all(a['state'] == 'SUPPORT' for a in exact)
        assert view['materials'][0]['role'] == 'root_package'
        assert get(h, old)['materials'] == []
        assert c.get(base+'/results/'+old['result_id']+'?assessment_version=1').json() == old
    finally:
        registry.close()


# TASK34 additions. All preceding TASK33 cases retained; no runtime result claimed.
def install_test_archive_notices(h, source, profile_obj, entries):
    """Synthetic test package extension, never the preserved real is-number files."""
    import base64
    import io
    import tarfile
    profile_obj = deepcopy(profile_obj)
    tarpath = source / 'source.tgz'
    with tarfile.open(fileobj=io.BytesIO(tarpath.read_bytes()), mode='r:gz') as old:
        content = [(m.name, old.extractfile(m).read()) for m in old if m.isreg()]
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz') as archive:
        for name, raw in [*content, *entries]:
            info = tarfile.TarInfo(name); info.size = len(raw)
            archive.addfile(info, io.BytesIO(raw))
    raw = output.getvalue(); tarpath.write_bytes(raw)
    metadata = json.loads((source/'metadata.json').read_bytes())
    metadata['dist']['integrity'] = 'sha512-' + base64.b64encode(hashlib.sha512(raw).digest()).decode()
    metadata['dist']['shasum'] = hashlib.sha1(raw).hexdigest()
    metadata_bytes = json.dumps(metadata).encode(); (source/'metadata.json').write_bytes(metadata_bytes)
    profile_obj['packages'][0]['tarball_sha256'] = hashlib.sha256(raw).hexdigest()
    profile_obj['packages'][0]['metadata_sha256'] = hashlib.sha256(metadata_bytes).hexdigest()
    profile_bytes = json.dumps(profile_obj).encode(); (source/'profile.json').write_bytes(profile_bytes)
    h[1].state.p2_service.public_source_profile_sha256 = hashlib.sha256(profile_bytes).hexdigest()


def test_task34_real_four_member_archive_complete_and_unchanged():
    from app.p2.preliminary import _notice_inventory
    raw = (FIXTURE/'archive.tgz').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == '7b75c1057198cf97696909a9bee176c9c5e9bcb5b03bf3ecef2f484defadd51e'
    observed = _notice_inventory(raw)
    assert observed['status'] == 'ABSENT_COMPLETE'
    assert observed['enumeration_complete'] is True and observed['member_count'] == 4
    assert observed['members'] == [] and observed['raw_notices'] == {}


@pytest.mark.parametrize('name,raw,status,member_state', [
    ('package/NOTICE', b'Additional notice.', 'PRESENT_UNREVIEWED','EXTRACTED_UNREVIEWED'),
    ('package/docs/nOtIcE.Md', b'Nested notice.', 'PRESENT_UNREVIEWED','EXTRACTED_UNREVIEWED'),
    ('package/NOTICE.txt', b'x'*65537, 'INVALID','LIMIT_EXCEEDED'),
    ('package/NOTICE', b'\xff', 'INVALID','PARSE_FAILED'),
    ('package/NOTICE.html', b'<p>terms</p>', 'INVALID','UNSUPPORTED_FORMAT'),
])
def test_task34_source_notice_not_uploaded_blocks_only_new_view(setup, name, raw, status, member_state):
    _, result, old_path, source, obj = admit(setup)
    install_test_archive_notices(setup, source, obj, [(name, raw)])
    view = get(setup, result)
    assert commercial(view)['state'] == 'UNKNOWN'
    assert len(view['materials']) == 1  # no fabricated uploaded NOTICE
    observed = view['source_observations'][0]
    assert observed['notice_status'] == status and observed['enumeration_complete'] is True
    member = observed['notices'][0]
    assert member['path'] == name and member['bytes'] == len(raw) and member['inspection_state'] == member_state
    if len(raw) <= 65536: assert member['sha256'] == hashlib.sha256(raw).hexdigest()
    else: assert member['sha256'] is None
    counter = view['claims'][0]['counter_evidence'][0]
    assert counter['material_ids'] == [] and counter['evidence_ids'] == []
    assert counter['source_observation_ids'] == [observed['source_observation_id']]
    # Explicit compatibility boundary: legacy ignores unuploaded archive NOTICE.
    legacy = setup[0].get(old_path)
    assert legacy.status_code == 200
    assert legacy.json()['supported_resource_ids'] == [result['resources'][0]['subject']['resource_id']]
    assert setup[0].get(setup[2]+'/results/'+result['result_id']+'?assessment_version=1').json() == result


def test_task34_notice_count_is_incomplete_not_absent(setup):
    _, result, _, source, obj = admit(setup)
    install_test_archive_notices(setup, source, obj, [(f'package/d{i}/NOTICE',b'terms') for i in range(21)])
    view = get(setup, result)
    assert view['source_observations'][0]['notice_status'] == 'INCOMPLETE'
    assert view['source_observations'][0]['enumeration_complete'] is False
    assert commercial(view)['state'] == 'UNKNOWN'


def test_task34_notice_read_failure_and_hidden_trailing_archive(setup, monkeypatch):
    import gzip
    import tarfile
    from app.p2.preliminary import _notice_inventory
    _, _, _, source, obj = admit(setup)
    install_test_archive_notices(setup, source, obj, [('package/NOTICE',b'terms')])
    raw = (source/'source.tgz').read_bytes()
    original = tarfile.TarFile.extractfile
    def unavailable(archive, member):
        if getattr(member, 'name', member) == 'package/NOTICE': return None
        return original(archive, member)
    with monkeypatch.context() as patch:
        patch.setattr(tarfile.TarFile, 'extractfile', unavailable)
        assert _notice_inventory(raw)['status'] == 'INCOMPLETE'
    # A second tar hidden after zero blocks cannot establish NOTICE absence.
    joined = gzip.compress(gzip.decompress((FIXTURE/'archive.tgz').read_bytes()) + gzip.decompress(raw))
    assert _notice_inventory(joined)['status'] == 'INCOMPLETE'


def test_task34_counter_edges_exclude_unrelated_resource_evidence(setup):
    from app.p2.material_claims import evidence_context
    _, result, _, _, _ = admit(setup)
    resources, materials, root, pin = inputs(setup, result)
    svc = setup[1].state.p2_service
    run, _, _, _ = svc.context(result['binding']['scan_id'], result['binding']['assessment_id'])
    declarations, roles = evidence_context(run, resources, result)
    candidate = deepcopy(result); row = candidate['resources'][0]; rid = row['subject']['resource_id']
    row['evidence_ids'].append('evd_unrelated_readme'); row['evidence_source_hashes']['evd_unrelated_readme']='e'*64
    d = {rid:{**declarations[rid], 'expression':'GPL-3.0-only','normalized_ids':['GPL-3.0-only']}}
    view = project(candidate, resources, materials, root, pin, {rid:'GPL-3.0-only'}, declaration_facts=d, role_facts=roles)
    counter = view['claims'][0]['counter_evidence'][0]
    expected = set(materials[0][0]['evidence_ids']) | set(d[rid]['evidence_ids'])
    assert set(counter['evidence_ids']) == expected
    assert 'evd_unrelated_readme' not in counter['evidence_ids']
    # Explicit known conflict, incomplete provenance is a separate field.
    d[rid]['evidence_ids']=[]; d[rid]['complete']=False
    unknown = project(candidate, resources, materials, root, pin, {rid:'GPL-3.0-only'}, declaration_facts=d)
    assert commercial(unknown)['state'] == 'COUNTER_EVIDENCE'
    assert unknown['claims'][0]['counter_evidence'][0]['evidence_status'] == 'UNKNOWN'


def test_task34_normalization_conflict_new_projection_and_unchanged_creation_gate(setup):
    _, result, _, _, _ = admit(setup)
    resources, materials, root, pin = inputs(setup, result)
    rid = result['resources'][0]['subject']['resource_id']
    facts = {rid:{'expression':'MIT','normalized_ids':['Apache-2.0'], 'evidence_ids':materials[0][0]['evidence_ids'], 'complete':True}}
    view = project(result, resources, materials, root, pin, {rid:'CONFLICT_OR_UNSUPPORTED'}, declaration_facts=facts)
    assert commercial(view)['state'] == 'COUNTER_EVIDENCE'
    assert view['claims'][0]['counter_evidence'][0]['code'] == 'SPDX_NORMALIZATION_CONFLICT'
    def inconsistent(p): p['licenses'][0]['normalized_ids']=['Apache-2.0']
    h = variant(setup, inconsistent)
    rejected = h[0].post(h[2]+'/results', json=h[3])
    assert rejected.status_code == 409
    assert rejected.json()['error']['code'] == 'p2_evidence_conflict'


@pytest.mark.parametrize('filename,raw,code', [('LICENCE',b'Other terms','BOUND_LICENSE_BYTES_CONFLICT'),('NOTICE',b'notice','NOTICE_REQUIRES_REVIEW')])
def test_task34_material_counter_exact_union(setup, filename, raw, code):
    _, parent, _, _, _ = admit(setup)
    request = material_body(parent, raw, key='task34-second')
    request.update(filename=filename, completeness='FULL_TEXT_CLAIMED')
    reply = setup[0].post(setup[2]+'/materials', json=request); assert reply.status_code == 201
    result = reply.json()['result']; resources, materials, root, pin = inputs(setup, result)
    candidate = deepcopy(result); row = candidate['resources'][0]
    row['evidence_ids'].append('evd_unrelated_code'); row['evidence_source_hashes']['evd_unrelated_code']='d'*64
    view = project(candidate, resources, materials, root, pin, {rid:'MIT' for rid in resources}, declaration_facts=declaration_facts(setup,candidate))
    counter = next(c for c in view['claims'][0]['counter_evidence'] if c['code']==code)
    selected = [m for m, _ in materials if m['material_id'] in counter['material_ids']]
    assert set(counter['evidence_ids']) == {eid for m in selected for eid in m['evidence_ids']}
    assert 'evd_unrelated_code' not in counter['evidence_ids'] and counter['source_observation_ids']==[]


def test_task34_general_user_assertion_not_specific_notice_violation(setup):
    _, result, _, _, _ = admit(setup)
    resources, materials, root, pin = inputs(setup, result)
    candidate=deepcopy(result);candidate['resources'][0]['user_assertions']['OBLIGATION_FULFILLMENT_IN_DELIVERY']='NOT_FULFILLED'
    view=project(candidate,resources,materials,root,pin,{rid:'MIT' for rid in resources},declaration_facts=declaration_facts(setup,candidate))
    advice=commercial(view)
    assert advice['state']=='RESTRICTION'
    assert advice['reasons']==['USER_REPORTS_DELIVERY_OBLIGATION_UNFULFILLED']
    assert all('NOTICE' not in x for x in advice['conditions'])
    assert '具体条款' in advice['conditions'][0]


def test_task34_role_requires_matching_scan_origin_not_upload_selection(setup):
    from app.p2.material_claims import evidence_context
    from app.domain.models import Evidence
    _, result, _, _, _ = admit(setup)
    resources, materials, root, pin=inputs(setup,result)
    svc=setup[1].state.p2_service
    run,_,_,_=svc.context(result['binding']['scan_id'],result['binding']['assessment_id'])
    declarations,roles=evidence_context(run,resources,result)
    rid=result['resources'][0]['subject']['resource_id']
    assert roles[rid]=={'role':'unknown','state':'unknown','evidence_ids':[]}
    view=project(result,resources,materials,root,pin,{rid:'MIT'},declaration_facts=declarations,role_facts=roles)
    assert view['materials'][0]['evidence'] and view['materials'][0]['role_basis_evidence_ids']==[]
    candidate=deepcopy(result);row=candidate['resources'][0];resource=resources[rid].model_copy(update={'component_type':'application'})
    fields=[]
    for i,field in enumerate(['name','version']):
        obj=run.evidence[0].model_dump(mode='json')
        obj.update(id=f'evd_123e4567-e89b-12d3-a456-4266141748{i:02}',kind='manifest_field',locator='package.json:/'+field,
                   excerpt=json.dumps(getattr(resource,field)),detected_by='manifest_parser',producer={'type':'parser','name':'openguard.root-package-manifest','version':'1'},
                   content_hash={'algorithm':'sha256','value':'c'*64},verification_status='pending')
        fields.append(Evidence.model_validate(obj));row['evidence_ids'].append(obj['id']);row['evidence_source_hashes'][obj['id']]='c'*64
    new_run=run.model_copy(update={'evidence':[*run.evidence,*fields]})
    resource=resource.model_copy(update={'evidence_ids':[*resource.evidence_ids,*(e.id for e in fields)]})
    new_resources={**resources,rid:resource}
    d,roles=evidence_context(new_run,new_resources,candidate)
    assert roles[rid]['state']=='inferred'
    assert roles[rid]['evidence_ids']==sorted(e.id for e in fields)
    assert set(roles[rid]['evidence_ids']).isdisjoint(materials[0][0]['evidence_ids'])
    view=project(candidate,new_resources,materials,root,pin,{rid:'MIT'},declaration_facts=d,role_facts=roles)
    assert view['materials'][0]['role_basis_evidence_ids']==roles[rid]['evidence_ids']


# TASK35 permanent regressions. Source authored only; none executed in this task.
def test_task35_declaration_complete_identity_and_claim_closure(setup):
    old, result, _, _, _ = admit(setup)
    view = get(setup, result)
    assert view['schema_version'] == 'openguard-material-claims/3'
    assert view['rule_version'] == 'mit-bound-claim/3'
    facts = declaration_facts(setup, result)
    assert len(view['declaration_observations']) == len(result['resources'])
    for d in view['declaration_observations']:
        row = next(r for r in result['resources'] if r['subject'] == d['subject'])
        expected = facts[d['subject']['resource_id']]
        assert d['expression'] == expected['expression']
        assert d['normalized_ids'] == expected['normalized_ids']
        assert d['declaration_evidence_ids'] == expected['evidence_ids']
        assert d['evidence_status'] == 'COMPLETE'
        assert d['evidence'] == [{'evidence_id': e, 'source_sha256': row['evidence_source_hashes'][e]} for e in expected['evidence_ids']]
        for link in view['claims']:
            if link['subject'] == d['subject']:
                assert set(d['declaration_evidence_ids']) <= {e['evidence_id'] for e in link['evidence']}
    assert setup[0].get(setup[2]+'/results/'+old['result_id']+'?assessment_version=1').json() == old


@pytest.mark.parametrize('mode', ['missing', 'foreign_resource', 'missing_hash'])
def test_task35_missing_or_foreign_declaration_is_unknown(setup, mode):
    from app.p2.material_claims import evidence_context
    _, result, _, _, _ = admit(setup)
    resources, materials, root, pin = inputs(setup,result)
    svc=setup[1].state.p2_service
    run,_,_,_=svc.context(result['binding']['scan_id'],result['binding']['assessment_id'])
    candidate=deepcopy(result);rid=candidate['resources'][0]['subject']['resource_id']
    resource=resources[rid];lic=next(l for l in run.licenses if l.id==resource.license_expression_id)
    if mode=='missing':
        changed=lic.model_copy(update={'evidence_ids':[]})
        run=run.model_copy(update={'licenses':[changed if l.id==lic.id else l for l in run.licenses]})
    elif mode=='foreign_resource':
        # Global scan/Result membership alone does not authorize this resource edge.
        resource=resource.model_copy(update={'evidence_ids':[]});resources={**resources,rid:resource}
    else:
        for eid in lic.evidence_ids: candidate['resources'][0]['evidence_source_hashes'].pop(eid,None)
    facts,_=evidence_context(run,resources,candidate)
    view=project(candidate,resources,materials,root,pin,{rid:'MIT'},declaration_facts=facts)
    assert view['declaration_observations'][0]['evidence_status']=='UNKNOWN'
    assert view['declaration_observations'][0]['declaration_evidence_ids']==[]
    assert commercial(view)['state']=='UNKNOWN'
    assert all(m['adoption_state']=='OBSERVATION_ONLY' for m in view['materials'])


@pytest.mark.parametrize('expression,normalized,code', [
    ('GPL-3.0-only',['GPL-3.0-only'],'SPDX_TEXT_CONFLICT'),
    ('MIT',['Apache-2.0'],'SPDX_NORMALIZATION_CONFLICT'),
])
def test_task35_exact_spdx_counter_sets_and_missing_provenance(setup,expression,normalized,code):
    _,result,_,_,_=admit(setup)
    resources,materials,root,pin=inputs(setup,result);rid=result['resources'][0]['subject']['resource_id']
    facts=declaration_facts(setup,result);facts[rid].update(expression=expression,normalized_ids=normalized)
    for missing in [False,True]:
        if missing:facts[rid].update(evidence_ids=[],complete=False)
        view=project(result,resources,materials,root,pin,{rid:expression},declaration_facts=facts)
        e=next(c for c in view['claims'][0]['counter_evidence'] if c['code']==code)
        assert e['declaration_evidence_ids']==facts[rid]['evidence_ids']
        expected=set(facts[rid]['evidence_ids'])
        if code=='SPDX_TEXT_CONFLICT':
            assert e['material_ids']==result['material_ids']
            expected.update(eid for m,_ in materials for eid in m['evidence_ids'])
        else:assert e['material_ids']==[]
        assert set(e['evidence_ids'])==expected
        assert e['source_observation_ids']==[]
        assert e['evidence_status']==('UNKNOWN' if missing else 'COMPLETE')
        assert commercial(view)['state']=='COUNTER_EVIDENCE'


def _task35_corrupt_gzip(raw,case):
    import gzip
    expanded=gzip.decompress(raw)  # Future TEST_ONLY fixture preparation, not a product fallback.
    canonical=gzip.compress(expanded,mtime=0)
    if case=='normal':return canonical
    if case=='truncated':return canonical[:-3]
    if case=='deflate':
        damaged=bytearray(canonical);damaged[10]=(damaged[10]&~6)|6 # reserved BTYPE=11
        return bytes(damaged)
    if case=='crc':
        damaged=bytearray(canonical);damaged[-8]^=1;return bytes(damaged)
    if case=='nonzero_tail':return canonical+b'not-a-gzip-member'
    if case=='second_tar':return gzip.compress(expanded+expanded,mtime=0)
    raise AssertionError('unknown test case')


def _task35_rebind_synthetic_archive(h,source,obj,raw):
    import base64
    (source/'source.tgz').write_bytes(raw)
    metadata=json.loads((source/'metadata.json').read_bytes())
    metadata['dist']['integrity']='sha512-'+base64.b64encode(hashlib.sha512(raw).digest()).decode()
    metadata['dist']['shasum']=hashlib.sha1(raw).hexdigest()
    metadata_raw=json.dumps(metadata).encode();(source/'metadata.json').write_bytes(metadata_raw)
    obj['packages'][0]['tarball_sha256']=hashlib.sha256(raw).hexdigest()
    obj['packages'][0]['metadata_sha256']=hashlib.sha256(metadata_raw).hexdigest()
    profile_raw=json.dumps(obj).encode();(source/'profile.json').write_bytes(profile_raw)
    h[1].state.p2_service.public_source_profile_sha256=hashlib.sha256(profile_raw).hexdigest()


@pytest.mark.parametrize('case',['normal','truncated','deflate','crc','nonzero_tail','second_tar'])
def test_task35_gzip_complete_read_errors_and_immutable_result(setup,case):
    from app.p2.preliminary import _notice_inventory
    from test_p2_contract import counts
    old,result,legacy,source,obj=admit(setup)
    raw=_task35_corrupt_gzip((source/'source.tgz').read_bytes(),case)
    _task35_rebind_synthetic_archive(setup,source,obj,raw)
    before=counts(setup[4])
    inventory=_notice_inventory(raw)
    reply=setup[0].get(path(setup[2],result))
    old_reply=setup[0].get(legacy)
    if case=='normal':
        assert inventory['status']=='ABSENT_COMPLETE'
        assert reply.status_code==200 and commercial(reply.json())['state']=='SUPPORT'
        assert old_reply.status_code==200
    elif case=='second_tar':
        assert inventory['status']=='INCOMPLETE'
        assert reply.status_code==200 and commercial(reply.json())['state']=='UNKNOWN'
        assert old_reply.status_code==200 # Existing legacy member policy retained.
    else:
        assert inventory['status']=='INCOMPLETE' and not inventory['enumeration_complete']
        assert reply.status_code==old_reply.status_code==503
        assert reply.json()['error']['code']=='p2_public_source_invalid'
        assert old_reply.json()['error']['code']=='p2_public_source_invalid'
    for saved in [old,result]:
        assert setup[0].get(setup[2]+'/results/'+saved['result_id']+'?assessment_version=1').json()==saved
    assert counts(setup[4])==before


# TASK36 targeted state regressions. Authored only, NOT_RUN.
def test_task36_real_four_member_inventory_has_fresh_state_each_call():
    from app.p2.preliminary import _notice_inventory
    raw = (FIXTURE/'archive.tgz').read_bytes()
    for _ in range(2):
        inventory = _notice_inventory(raw)
        assert inventory['status'] == 'ABSENT_COMPLETE'
        assert inventory['reason'] == 'COMPLETE_SUPPORTED_ARCHIVE_NO_NOTICE'
        assert inventory['enumeration_complete'] is True
        assert inventory['member_count'] == 4
        assert inventory['members'] == [] and inventory['raw_notices'] == {}


@pytest.mark.parametrize('content,expected', [(b'Preserve this NOTICE.', 'PRESENT_UNREVIEWED'),
                                             (b'\xff', 'INVALID'), (b'', 'INVALID')])
def test_task36_notice_state_does_not_leak_to_next_inventory(setup, content, expected):
    from app.p2.preliminary import _notice_inventory
    old, result, _, source, obj = admit(setup)
    install_test_archive_notices(setup, source, obj, [('package/NOTICE', content)])
    inventory = _notice_inventory((source/'source.tgz').read_bytes())
    assert inventory['status'] == expected
    assert inventory['enumeration_complete'] is True
    assert len(inventory['members']) == 1
    assert inventory['members'][0]['sha256'] == hashlib.sha256(content).hexdigest()
    assert inventory['raw_notices']['package/NOTICE'] == content
    assert _notice_inventory((FIXTURE/'archive.tgz').read_bytes())['status'] == 'ABSENT_COMPLETE'
    # Existing failure/incompleteness paths must not mutate saved results or DB.
    from test_p2_contract import counts
    before = counts(setup[4])
    assert commercial(get(setup, result))['state'] == 'UNKNOWN'
    for saved in [old, result]:
        assert setup[0].get(setup[2]+'/results/'+saved['result_id']+'?assessment_version=1').json() == saved
    assert counts(setup[4]) == before


@pytest.mark.parametrize('case', ['empty_tar', 'second_tar', 'nonzero_tar_tail'])
def test_task36_empty_and_hidden_tar_never_report_notice_absence(case):
    import gzip
    import io
    import tarfile
    from app.p2.preliminary import _notice_inventory
    expanded = gzip.decompress((FIXTURE/'archive.tgz').read_bytes())
    if case == 'empty_tar':
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode='w'):
            pass
        raw = gzip.compress(output.getvalue(), mtime=0)
    elif case == 'second_tar':
        raw = gzip.compress(expanded + expanded, mtime=0)
    else:
        raw = gzip.compress(expanded + b'\x01', mtime=0)
    inventory = _notice_inventory(raw)
    assert inventory['status'] == 'INCOMPLETE'
    assert inventory['enumeration_complete'] is False
    assert inventory['reason'] == 'SOURCE_MEMBER_INSPECTION_INCOMPLETE'
    if case == 'empty_tar':
        assert inventory['member_count'] == 0
        assert inventory['members'] == []


def test_task37_hashless_material_evidence_still_unknown(setup):
    """Do not weaken the v3 gate when fixing the old positive fixture."""
    _, result, _, _, _ = admit(setup)
    resources, materials, root, pin = inputs(setup, result)
    row = result['resources'][0]
    missing = next(e for e in row['evidence_ids'] if e not in row['evidence_source_hashes'])
    materials = deepcopy(materials)
    materials[0][0]['evidence_ids'] = [missing]
    view = project(result, resources, materials, root, pin,
                   {rid: 'MIT' for rid in resources}, declaration_facts=declaration_facts(setup, result))
    assert view['declaration_observations'][0]['evidence_status'] == 'COMPLETE'
    assert commercial(view)['state'] == 'UNKNOWN'
    assert view['materials'][0]['adoption_state'] == 'OBSERVATION_ONLY'
