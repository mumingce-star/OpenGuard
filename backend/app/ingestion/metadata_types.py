"""Internal A07 transport values, not Frozen P1 DTOs or persistence objects."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math
import re


class ErrorCode(StrEnum):
    DISABLED = 'feature_disabled'
    INPUT = 'unsupported_input'
    POLICY = 'address_policy_rejected'
    DNS = 'dns_failed'
    CONNECT = 'connection_failed'
    TLS = 'tls_failed'
    TIMEOUT = 'timeout'
    REDIRECT = 'redirect_refused'
    SIZE = 'response_too_large'
    PROTOCOL = 'response_invalid'
    JSON = 'json_invalid'
    IDENTITY = 'identity_mismatch'
    REVISION = 'revision_mismatch'
    NOT_FOUND = 'upstream_404'
    ACCESS = 'upstream_access_denied'
    RATE = 'upstream_rate_limited'
    UPSTREAM = 'upstream_unavailable'


class MetadataError(Exception):
    def __init__(self, code: ErrorCode, *, upstream_status: int | None = None):
        self.code = ErrorCode(code)
        if upstream_status is not None and (type(upstream_status) is not int or not 100 <= upstream_status <= 599):
            raise ValueError('invalid upstream status')
        self.upstream_status = upstream_status
        super().__init__(self.code.value)


@dataclass(frozen=True, repr=False)
class MetadataRequest:
    provider: str
    resource_kind: str
    repository_id: str
    revision_mode: str
    requested_revision: str | None

    def __repr__(self):
        return '<MetadataRequest>'


def build_target(request: MetadataRequest) -> str:
    if type(request) is not MetadataRequest:
        raise MetadataError(ErrorCode.INPUT)
    if request.provider != 'huggingface' or request.resource_kind not in ('model', 'dataset'):
        raise MetadataError(ErrorCode.INPUT)
    repo = request.repository_id
    if type(repo) is not str or not 1 <= len(repo) <= 193:
        raise MetadataError(ErrorCode.INPUT)
    parts = repo.split('/')
    if not 1 <= len(parts) <= 2 or any(
        not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,95}', part)
        or part.endswith(('.', '-', '.git')) or '--' in part or '..' in part for part in parts
    ):
        raise MetadataError(ErrorCode.INPUT)
    revision = request.requested_revision
    if request.revision_mode == 'fixed':
        valid = type(revision) is str and re.fullmatch(r'[0-9a-f]{40}', revision)
    elif request.revision_mode == 'symbolic':
        valid = (type(revision) is str and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}', revision)
                 and '..' not in revision and not revision.endswith(('.', '.lock')))
    elif request.revision_mode == 'default_observation':
        valid = revision is None
    else:
        valid = False
    if not valid:
        raise MetadataError(ErrorCode.INPUT)
    path = f'https://huggingface.co/api/{request.resource_kind}s/{repo}'
    return path if revision is None else path + '/revision/' + revision


@dataclass(frozen=True)
class Limits:
    total_seconds: float = 20.0
    operation_seconds: float = 5.0
    body_bytes: int = 1_048_576
    header_bytes: int = 32_768
    header_line_bytes: int = 8192
    header_fields: int = 64
    dns_answers: int = 16
    attempts: int = 2
    json_depth: int = 32
    json_nodes: int = 50_000

    def __post_init__(self):
        for value in (self.total_seconds, self.operation_seconds):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 60:
                raise MetadataError(ErrorCode.INPUT)
        for key, maximum in (('body_bytes', 1_048_576), ('header_bytes', 32_768),
                             ('header_line_bytes', 8192), ('header_fields', 64),
                             ('dns_answers', 16), ('attempts', 4), ('json_depth', 32), ('json_nodes', 50_000)):
            value = getattr(self, key)
            if type(value) is not int or not 1 <= value <= maximum:
                raise MetadataError(ErrorCode.INPUT)


@dataclass(frozen=True)
class SourceDescriptor:
    provider: str
    resource_kind: str
    repository_id: str
    requested_revision: str | None
    revision_mode: str
    resolved_revision: str | None
    revision_locator: str | None
    version_status: str
    source_url: str
    fetched_at: str
    content_type: str
    body_size: int
    body_sha256: str
    transport_version: str = 'hf-metadata-transport/1'
    descriptor_version: str = 'metadata-source/1'
    full_response_replay_available: bool = False


class TemporaryMetadata:
    """Memory-only handoff; no dataclass/asdict/dump exposing raw payload."""
    __slots__ = ('source', '__body')

    def __init__(self, source: SourceDescriptor, body: bytes):
        self.source, self.__body = source, body

    def bounded_bytes(self) -> bytes:
        """Borrow for this call's offline parser only. Never persist/log raw."""
        return self.__body

    def __repr__(self):
        return '<TemporaryMetadata: memory-only bounded body>'

    def __reduce_ex__(self, protocol):
        raise TypeError('temporary metadata cannot be serialized')
