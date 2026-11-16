"""DEV/TEST ONLY. Synthetic metadata, never imported by the default factory."""
import hashlib
import json
from app.ingestion.metadata_types import SourceDescriptor, TemporaryMetadata, build_target
from app.p1.profile_models import ParsedMetadataObservation

SENTINEL='RAW_SENTINEL_SHOULD_NEVER_BE_PERSISTED'


class SyntheticMetadataTransport:
    synthetic=True
    def __init__(self): self.calls=0
    def fetch(self,request):
        self.calls+=1
        unconfirmed=request.repository_id.endswith('unconfirmed')
        data=json.dumps({'synthetic':True,'label':'Synthetic field only','unused':SENTINEL}).encode()
        source=SourceDescriptor(provider=request.provider,resource_kind=request.resource_kind,
            repository_id=request.repository_id,requested_revision=request.requested_revision,
            revision_mode=request.revision_mode,resolved_revision=None if unconfirmed else request.requested_revision if request.revision_mode=='fixed' else 'a'*40,
            revision_locator=None if unconfirmed else '/sha',
            version_status='bounded_content_revision_unconfirmed' if unconfirmed else 'revision_observed',
            source_url=build_target(request),fetched_at='2026-09-18T00:00:00Z',content_type='application/json',
            body_size=len(data),body_sha256=hashlib.sha256(data).hexdigest())
        return TemporaryMetadata(source,data)


class SyntheticMetadataParser:
    synthetic=True
    def parse(self,*,provider,resource_kind,resource_identity,temporary_metadata,source_descriptor):
        # Deliberately extracts only one known finite field. No real HF parser.
        data=json.loads(temporary_metadata.bounded_bytes())
        conflict=resource_identity.endswith('conflict')
        return ParsedMetadataObservation(parser_version='synthetic-parser/1',bounded_excerpt='Synthetic observation only.',
            fields=[dict(name='synthetic_label',value=None if conflict else data['label'],locator='/label',
                         verification_status='rejected' if conflict else 'verified')],
            verification_status='pending' if conflict else 'verified',
            coverage_gaps=['synthetic_field_conflict'] if conflict else [])
