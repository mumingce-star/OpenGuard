"""V2-only acceptance extension. V1 data, validation and readers stay intact."""
from copy import deepcopy
from types import SimpleNamespace
from app import dev_integration as dev
from app.p1.profile import ProfileService, MetadataStore
from app.p1.profile_models import RefreshRequest
from app.profile_synthetic import SyntheticMetadataTransport, SyntheticMetadataParser


def add_facts(value, *, empty_provider=False):
    from app.frontend_acceptance import _id
    fixture=dev._fixture()
    value['evidence']=deepcopy(fixture['evidence'])
    base=deepcopy(fixture['ai_assets'][0])
    assets=[]
    for n,kind,name in [(1,'model','model'),(2,'dataset','dataset'),(3,'model','unconfirmed'),(4,'dataset','conflict'),
                        (5,'model','unfetched')]:
        item=deepcopy(base)
        item.update(id=_id('ast',40000+n),asset_type=kind,name='synthetic/'+name,provider='huggingface',version=None,
            source_url='https://huggingface.co/'+('datasets/' if kind=='dataset' else '')+'synthetic/'+name,
            license_expression_id=None,authorization_status='pending')
        assets.append(item)
    if empty_provider:
        item=deepcopy(base)
        item.update(id=_id('ast',40006),asset_type='model',name='synthetic/empty-provider',provider='',
            version=None,source_url=None,license_expression_id=None,authorization_status='pending')
        assets.append(item)
    value['ai_assets']=assets
    value['summary'].update(ai_asset_count=len(assets),evidence_count=len(value['evidence']))


def service(root,registry):
    return ProfileService(registry,MetadataStore(root/'metadata.db',min_free_bytes=0),
        transport=SyntheticMetadataTransport(),parser=SyntheticMetadataParser())


def scenarios(registry):
    from app.frontend_acceptance import _id
    scan_id=_id('scn',10009)
    rows={}
    component=registry.get(_id('scn',10002)).run.components[0]
    for label,sid,rid,count,gaps in [('P1',_id('scn',10002),component.id,0,['metadata_observation_unavailable']),
        ('P2',scan_id,_id('ast',40001),1,[]),('P3',scan_id,_id('ast',40002),1,[]),
        ('P4',scan_id,_id('ast',40003),1,['metadata_revision_unconfirmed']),
        ('P5',scan_id,_id('ast',40004),1,['synthetic_field_conflict'])]:
        rows[label]=dict(scan_id=sid,resource_id=rid,scenario=label,expected_metadata_count=count,
            expected_gaps=gaps,synthetic=True,href=f'/api/v1/scans/{sid}/resources/{rid}/profile')
    return rows


def initialize(root,manifest):
    from app.frontend_acceptance import _id
    registry=dev.SQLiteScanRunRegistry(root/'scans.db')
    try:
        svc=service(root,registry); svc.store.initialize()
        sid=_id('scn',10009)
        # P2-P5 start with observations. A separate synthetic resource remains
        # unobserved for explicit real-HTTP empty -> refresh -> observed checks.
        svc.refresh(sid,RefreshRequest(resource_ids=[a.id for a in registry.get(sid).run.ai_assets if a.name!='synthetic/unfetched' and a.provider=='huggingface'],
            expected_facts_hash=dev.facts_digest(registry.get(sid).run),idempotency_key='acceptance-profile-init-v2'))
        manifest['profiles']=scenarios(registry)
        del manifest['unsupported']['profile']
    finally: registry.close()


def validate(root,manifest):
    from app.frontend_acceptance import _readonly_rows, _same
    rows=_readonly_rows(root,'scans.db','SELECT scan_id,revision,idempotency_key,idempotency_fingerprint,created_at,status,contract_version,run_json FROM scan_runs LIMIT 206')
    stored=[dev.SQLiteScanRunRegistry._row_to_stored(r) for r in rows]
    index={s.run.id:s for s in stored}
    registry=SimpleNamespace(get=lambda sid:index[sid])
    store=MetadataStore(root/'metadata.db',min_free_bytes=0)
    with store.connection(): pass  # absent/unknown schema never initialized
    _same(manifest['profiles'],scenarios(registry))
    if set(manifest['unsupported'])!={'notice'}: raise dev.DevIntegrationError('acceptance_manifest_invalid')
    reader=ProfileService(registry,store)
    for row in manifest['profiles'].values():
        profile=reader.get(row['scan_id'],row['resource_id'])
        _same(len(profile['metadata_observations']),row['expected_metadata_count'])
        _same(profile['coverage_gaps'],row['expected_gaps'])
