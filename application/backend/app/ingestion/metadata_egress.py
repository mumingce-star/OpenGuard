"""Default-off HF metadata transport. No persistence, API wiring or parser.

Only this module's fetch entry constructs content targets. Wire is a private
implementation adapter, not a URL-fetch interface for untrusted callers.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import re
import time

from .metadata_types import (ErrorCode, Limits, MetadataError, MetadataRequest,
                             SourceDescriptor, TemporaryMetadata, build_target,
                             modelscope_envelope_succeeded)
from .metadata_wire import Deadline, Wire, public_answers


def _json(body, limits, budget):
    def invalid(*_):
        raise MetadataError(ErrorCode.JSON)
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                invalid()
            result[key] = value
        return result
    def integer(value):
        if len(value) > 100:
            invalid()
        return int(value)
    def floating(value):
        if len(value) > 64:
            invalid()
        result = float(value)
        if not math.isfinite(result):
            invalid()
        return result
    try:
        text = body.decode('utf-8', errors='strict')  # BOM rejected by json.loads
        depth = 0
        string = escape = False
        for offset, char in enumerate(text):
            if offset % 4096 == 0:
                budget.remaining()
            if string:
                if escape:
                    escape = False
                elif char == '\\':
                    escape = True
                elif char == '"':
                    string = False
            elif char == '"':
                string = True
            elif char in '[{':
                depth += 1
                if depth > limits.json_depth:
                    invalid()
            elif char in ']}':
                depth -= 1
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=invalid,
                           parse_int=integer, parse_float=floating)
        if type(value) is not dict:
            invalid()
        stack, count = [value], 0
        while stack:
            item = stack.pop()
            count += 1
            if count > limits.json_nodes:
                invalid()
            if count % 256 == 0:
                budget.remaining()
            if type(item) is str:
                item.encode('utf-8', errors='strict')  # reject lone escaped surrogates
            elif type(item) is dict:
                stack.extend(item.keys())
                stack.extend(item.values())
            elif type(item) is list:
                stack.extend(item)
        budget.remaining()
        return value
    except (UnicodeError, ValueError, RecursionError, OverflowError):
        raise MetadataError(ErrorCode.JSON) from None


class MetadataTransport:
    def __init__(self, *, enabled=False, limits=None):
        if type(enabled) is not bool or (limits is not None and type(limits) is not Limits):
            raise MetadataError(ErrorCode.INPUT)
        self.enabled, self.limits = enabled, limits or Limits()

    def fetch(self, request: MetadataRequest) -> TemporaryMetadata:
        # No resolver, trust store, socket, credential or file access until enable.
        if not self.enabled:
            raise MetadataError(ErrorCode.DISABLED)
        target = build_target(request)
        return self._fetch(request, target, Wire(), time.monotonic)

    def _fetch(self, request, target, wire, clock):
        """Trusted test seam; callers use fetch, never supply network targets."""
        budget = Deadline(self.limits, clock)
        host = {'huggingface': 'huggingface.co', 'modelscope': 'modelscope.cn'}.get(request.provider)
        if host is None:
            raise MetadataError(ErrorCode.INPUT)
        answers = wire.resolve(host, budget, self.limits)
        endpoints = public_answers(host, answers, self.limits)
        body = wire.exchange(host, endpoints, target.removeprefix('https://' + host), budget, self.limits)
        data = _json(body, self.limits, budget)
        if request.provider == 'huggingface':
            identity, revision = data.get('id'), data.get('sha')
        else:
            envelope = data.get('Data')
            success = modelscope_envelope_succeeded(data)
            if data.get('Code') != 200 or not success or type(envelope) is not dict:
                raise MetadataError(ErrorCode.IDENTITY)
            # The public endpoint currently calls the namespace ``Path``;
            # older captures used ``Namespace``. Reject disagreement instead
            # of silently picking one provider identity.
            namespace, name = envelope.get('Namespace', envelope.get('Path')), envelope.get('Name')
            if 'Namespace' in envelope and 'Path' in envelope and envelope['Namespace'] != envelope['Path']:
                raise MetadataError(ErrorCode.IDENTITY)
            identity, revision = (f'{namespace}/{name}' if type(namespace) is str and type(name) is str else None), None
        if identity != request.repository_id:
            raise MetadataError(ErrorCode.IDENTITY)
        if revision is not None and (type(revision) is not str or not re.fullmatch(r'[0-9a-f]{40}', revision)):
            raise MetadataError(ErrorCode.REVISION)
        if request.revision_mode == 'fixed' and revision is not None and revision != request.requested_revision:
            raise MetadataError(ErrorCode.REVISION)
        source = SourceDescriptor(
            provider=request.provider, resource_kind=request.resource_kind, repository_id=request.repository_id,
            requested_revision=request.requested_revision, revision_mode=request.revision_mode,
            resolved_revision=revision, revision_locator='/sha' if revision else None,
            version_status='revision_observed' if revision else 'bounded_content_revision_unconfirmed',
            source_url=target, fetched_at=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            content_type='application/json', body_size=len(body), body_sha256=hashlib.sha256(body).hexdigest())
        if request.provider == 'modelscope':
            source = SourceDescriptor(**{**source.__dict__, 'transport_version': 'modelscope-metadata-transport/1'})
        budget.remaining()
        return TemporaryMetadata(source, body)


__all__ = ['MetadataTransport', 'MetadataRequest', 'MetadataError', 'Limits', 'build_target']
