"""Provider-fixed metadata parser dispatch for the optional Profile sidecar."""
from __future__ import annotations

from app.ingestion.metadata_types import SourceDescriptor, TemporaryMetadata
from app.p1.profile_models import ParsedMetadataObservation
from .huggingface_metadata import HuggingFaceMetadataParser
from .modelscope_metadata import ModelScopeMetadataParser


class ProviderMetadataParser:
    """Dispatch only to a parser selected from the transport-owned descriptor."""

    def __init__(self):
        self._parsers = {
            'huggingface': HuggingFaceMetadataParser(),
            'modelscope': ModelScopeMetadataParser(),
        }

    def parse(self, *, provider: str, resource_kind: str, resource_identity: str,
              temporary_metadata: TemporaryMetadata, source_descriptor: SourceDescriptor) -> ParsedMetadataObservation:
        if source_descriptor is not temporary_metadata.source or source_descriptor.provider != provider:
            raise ValueError('metadata_invalid')
        parser = self._parsers.get(provider)
        if parser is None:
            raise ValueError('metadata_invalid')
        return parser.parse(provider=provider, resource_kind=resource_kind, resource_identity=resource_identity,
                            temporary_metadata=temporary_metadata, source_descriptor=source_descriptor)


__all__ = ['ProviderMetadataParser']
