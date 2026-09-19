"""Scan facts project identity/authorization; metadata stays an observation."""
import hashlib
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pydantic import ValidationError
from app.ingestion.metadata_types import MetadataRequest, MetadataError, TemporaryMetadata, SourceDescriptor, build_target
from .diff import _resources
from .graph import GraphReader
from .profile_models import MetadataParser, ParsedMetadataObservation, MetadataObservation, ResourceProfile, RefreshRequest
from .profile_store import MetadataStore, ProfileError, ALGORITHM, canonical, digest, semantic


def provenance(ref,parameters,at,producer='openguard-profile',version=ALGORITHM):
    return dict(producer=dict(name=producer,version=version),source_refs=[ref],assessment_refs=[],
        generated_at=at,algorithm_version=ALGORITHM,parameters_hash=digest(parameters))


class ProfileService:
    def __init__(self,registry,store=None,*,transport=None,parser=None):
        self.registry,self.store,self.transport,self.parser=registry,store,transport,parser

    def _stored(self,scan_id):
        stored=GraphReader(self.registry)._stored(scan_id)
        if stored.run.status in {'queued','running'}: raise ProfileError('not_ready')
        if stored.run.status not in {'completed','partial'}: raise ProfileError('not_comparable')
        return stored

    @staticmethod
    def _row(stored,resource_id):
        row=next((r for r in _resources(stored.run) if r['item'].id==resource_id),None)
        if row is None: raise ProfileError('not_found')
        return row

    @staticmethod
    def metadata_request(row):
        item=row['item']
        if row['ref']['resource_kind']!='ai_asset' or item.provider!='huggingface' or item.asset_type not in {'model','dataset'}:
            raise ProfileError('unsupported_input')
        revision=item.version
        mode='default_observation' if revision is None else 'fixed' if re.fullmatch('[0-9a-f]{40}',revision) else 'symbolic'
        request=MetadataRequest('huggingface',item.asset_type.value,item.name,mode,revision)
        build_target(request)  # pure validation, never URL input from client
        return request

    def get(self,scan_id,resource_id):
        stored=self._stored(scan_id); run=stored.run
        row=self._row(stored,resource_id); item=row['item']; ref=GraphReader._ref(stored)
        observations=self.store.observations(scan_id,resource_id,ref['facts_hash']) if self.store else []
        gaps=GraphReader._scan_gaps(run)
        if not observations: gaps.append('metadata_observation_unavailable')
        if item.version=='': gaps.append('identity_version_empty_normalized_to_unknown')
        kind=row['ref']['resource_kind']
        if kind=='ai_asset' and item.provider=='':
            gaps.append('identity_provider_empty_normalized_to_unknown')
        identity=dict(name=item.name,version=None if item.version=='' else item.version,
            ecosystem=(item.ecosystem if item.ecosystem!='unknown' else None) if kind=='component' else None,
            provider=(None if item.provider=='' else item.provider) if kind=='ai_asset' else None,source_url=item.source_url)
        evidence={e.id for e in run.evidence}
        refs=lambda ids:[dict(namespace='scan',scan_id=scan_id,evidence_id=e) for e in sorted(set(ids)) if e in evidence]
        licenses=[]
        for lic in run.licenses:
            if lic.id==item.license_expression_id:
                licenses.append(dict(license_expression_id=lic.id,expression=lic.expression,
                    relation_scope='resource_license_expression_id',evidence_refs=refs(item.evidence_ids+lic.evidence_ids),
                    verification_status=lic.verification_status.value))
        authorization=None
        if kind=='ai_asset':
            index=next(i for i,a in enumerate(run.ai_assets) if a.id==item.id)
            authorization=dict(status=item.authorization_status.value,source_ref=dict(scan_id=scan_id,pointer=f'/ai_assets/{index}/authorization_status'))
        for observation in observations: gaps.extend(observation['coverage_gaps'])
        at=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
        value=dict(schema_version='1.0',profile_id='pending',scan_ref=ref,resource_ref=row['ref'],identity=identity,
            license_observations=licenses,authorization_fact=authorization,metadata_observations=observations,
            coverage_gaps=sorted(set(gaps)),evidence_refs=refs(item.evidence_ids)+[
                dict(namespace='profile_observation',observation_id=o['observation_id']) for o in observations],
            provenance=provenance(ref,{'resource':row['ref'],'observations':[o['observation_id'] for o in observations]},at))
        content={k:v for k,v in value.items() if k!='profile_id'}
        content['provenance']={k:v for k,v in value['provenance'].items() if k!='generated_at'}
        value['profile_id']='profile_'+digest(content)
        try: return ResourceProfile.model_validate(value).model_dump(mode='json')
        except (ValueError,TypeError): raise ProfileError('upstream_unavailable') from None

    def _observation(self,stored,row,request):
        temporary=self.transport.fetch(request)
        if type(temporary) is not TemporaryMetadata: raise ProfileError('metadata_invalid')
        source=temporary.source; raw=temporary.bounded_bytes()
        # Descriptor is transport-owned, never parser-overridable. Verify even
        # injected transport results before handing bytes to a trusted parser.
        if (type(source) is not SourceDescriptor or type(raw) is not bytes or not raw or len(raw)>1_048_576 or source.body_size!=len(raw)
            or source.body_sha256!=hashlib.sha256(raw).hexdigest() or source.source_url!=build_target(request)
            or any(getattr(source,k)!=getattr(request,k) for k in ('provider','resource_kind','repository_id','requested_revision','revision_mode'))
            or source.full_response_replay_available is not False or source.content_type!='application/json'
            or source.descriptor_version!='metadata-source/1' or source.transport_version!='hf-metadata-transport/1'):
            raise ProfileError('metadata_invalid')
        unconfirmed=source.version_status=='bounded_content_revision_unconfirmed'
        if unconfirmed:
            if source.resolved_revision is not None or source.revision_locator is not None: raise ProfileError('metadata_invalid')
        elif source.version_status!='revision_observed' or not re.fullmatch('[0-9a-f]{40}',source.resolved_revision or '') or source.revision_locator!='/sha':
            raise ProfileError('metadata_invalid')
        if request.revision_mode=='fixed' and source.resolved_revision is not None and source.resolved_revision!=request.requested_revision:
            raise ProfileError('metadata_invalid')
        parsed=self.parser.parse(provider=source.provider,resource_kind=source.resource_kind,
            resource_identity=source.repository_id,temporary_metadata=temporary,source_descriptor=source)
        if type(parsed) is not ParsedMetadataObservation: raise ProfileError('metadata_invalid')
        # Revalidate: model_construct/mutated list must not bypass the boundary.
        result=ParsedMetadataObservation.model_validate(parsed.model_dump(mode='json')).model_dump(mode='json')
        # A small complete response is still raw, even if it fits the excerpt
        # budget. Reject exact complete-response copies in every parser string.
        raw_text=raw.decode('utf-8')
        strings=[result['parser_version'],result['bounded_excerpt'],*result['coverage_gaps']]
        strings += [value for field in result['fields'] for value in field.values() if isinstance(value,str)]
        if any(raw_text in value for value in strings): raise ProfileError('metadata_invalid')
        result['fields']=sorted(result['fields'],key=lambda f:canonical(f))
        result['coverage_gaps']=sorted(set(result['coverage_gaps'])|({'metadata_revision_unconfirmed'} if unconfirmed else set()))
        if unconfirmed and result['verification_status']=='verified': result['verification_status']='pending'
        ref=GraphReader._ref(stored)
        value=dict(**result,observation_id='pending',provider=source.provider,
            resource_identity_key=row['ref']['resource_identity_key'],requested_revision=source.requested_revision,
            resolved_revision=source.resolved_revision,source_url=source.source_url,fetched_at=source.fetched_at,
            content_hash=source.body_sha256,producer=dict(name='metadata-parser',version=result['parser_version']),
            provenance=provenance(ref,{'request':asdict(request),'resource':row['ref']},datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
                producer='metadata-parser',version=result['parser_version']),full_response_replay_available=False)
        value['observation_id']='obs_'+digest({'scan_id':ref['scan_id'],'resource':row['ref'],
            'revision_mode':request.revision_mode,'algorithm':ALGORITHM,'observation':semantic(value)})
        return MetadataObservation.model_validate(value).model_dump(mode='json')

    def refresh(self,scan_id,request):
        if not self.store or not self.transport or not self.parser: raise ProfileError('feature_disabled')
        request=RefreshRequest.model_validate(request.model_dump())
        stored=self._stored(scan_id)
        if request.expected_facts_hash!=GraphReader._ref(stored)['facts_hash']: raise ProfileError('conflict')
        for resource_id in request.resource_ids:
            try: self.metadata_request(self._row(stored,resource_id))
            except MetadataError: raise ProfileError('invalid_argument') from None
            except ProfileError as error:
                if error.code in {'unsupported_input','not_found'}: raise ProfileError('invalid_argument') from None
                raise
        job,created=self.store.reserve(scan_id,request)
        if created: self.refresh_once(scan_id,job['job_id'])
        return self.store.job(scan_id,job['job_id'])

    def refresh_once(self,scan_id,job_id):
        job=self.store.claim(scan_id,job_id)
        if job is None: return
        for resource_id in job['resource_ids']:
            try:
                stored=self._stored(scan_id)
                if GraphReader._ref(stored)['facts_hash']!=job['facts_hash']: raise ProfileError('conflict')
                row=self._row(stored,resource_id)
                value=self._observation(stored,row,self.metadata_request(row))
                self.store.finish_item(scan_id,job_id,resource_id,observation=value)
            except MetadataError as error: self.store.finish_item(scan_id,job_id,resource_id,error=error.code.value)
            except (ValidationError,ValueError,TypeError): self.store.finish_item(scan_id,job_id,resource_id,error='metadata_invalid')
            except ProfileError as error: self.store.finish_item(scan_id,job_id,resource_id,error=error.code)
            except Exception: self.store.finish_item(scan_id,job_id,resource_id,error='metadata_invalid')

    def job(self,scan_id,job_id):
        if self.store is None: raise ProfileError('feature_disabled')
        self._stored(scan_id)
        return self.store.job(scan_id,job_id)
