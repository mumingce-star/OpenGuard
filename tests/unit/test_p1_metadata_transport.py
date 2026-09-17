"""Synthetic inputs only; the first run requires the not-yet-implemented module."""
import pytest
import hashlib
import json
import socket
import ssl
from types import SimpleNamespace

from app.ingestion import metadata_egress as api, metadata_wire as net
from app.ingestion.metadata_types import Limits, ErrorCode

from app.ingestion.metadata_egress import MetadataTransport, MetadataRequest, MetadataError, build_target


def test_disabled_before_resolution():
    with pytest.raises(MetadataError, match='feature_disabled'):
        MetadataTransport().fetch(MetadataRequest('huggingface', 'model', 'synthetic/Model', 'symbolic', 'main'))


@pytest.mark.parametrize('kind', ['model', 'dataset'])
def test_target(kind):
    req = MetadataRequest('huggingface', kind, 'synthetic/Case', 'symbolic', 'v1.0')
    assert build_target(req) == f'https://huggingface.co/api/{kind}s/synthetic/Case/revision/v1.0'


@pytest.mark.parametrize('repo', ['https://evil.invalid/a', '../a', 'a/%2f', 'a/%252f', 'a/b?x', 'a/b#x', 'a\\b', 'a/b\r\nX: y'])
def test_invalid_target(repo):
    with pytest.raises(MetadataError):
        build_target(MetadataRequest('huggingface', 'model', repo, 'default_observation', None))


REQUEST = MetadataRequest('huggingface', 'model', 'synthetic/Model', 'symbolic', 'main')
BODY = json.dumps({'id': 'synthetic/Model', 'sha': 'a' * 40, 'synthetic': True}).encode()
PUBLIC = (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('93.184.216.34', 443))


def response(body=BODY, headers=None, status=200):
    if headers is None:
        headers = [b'Content-Type: application/json', b'Content-Length: ' + str(len(body)).encode()]
    return b'HTTP/1.1 ' + str(status).encode() + b' synthetic\r\n' + b'\r\n'.join(headers) + b'\r\n\r\n' + body


class Socket:
    def __init__(self, payload, peer=('93.184.216.34', 443), piece=4096, tick=None):
        self.payload, self.peer, self.piece, self.tick = payload, peer, piece, tick
        self.sent = b''
        self.closed = False
        self.timeouts = []
    def settimeout(self, value): self.timeouts.append(value)
    def getpeername(self): return self.peer
    def selected_alpn_protocol(self): return 'http/1.1'
    def sendall(self, data): self.sent += data
    def recv(self, size):
        if self.tick: self.tick()
        piece = min(size, self.piece)
        result, self.payload = self.payload[:piece], self.payload[piece:]
        return result
    def close(self): self.closed = True


class Context:
    verify_mode = ssl.CERT_REQUIRED
    check_hostname = True
    keylog_filename = None
    def __init__(self, error=None): self.names, self.error = [], error
    def wrap_socket(self, raw, *, server_hostname):
        self.names.append(server_hostname)
        if self.error: raise self.error
        return raw


@pytest.fixture(autouse=True)
def no_external(monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('unexpected real network/resolver')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)
    from app.security import doh_resolver
    monkeypatch.setattr(doh_resolver, 'resolve_via_doh', forbidden)


def harness(monkeypatch, payload=None, *, answers=None, piece=4096, context=None, limits=None, tick=None):
    raw = Socket(response() if payload is None else payload, piece=piece, tick=tick)
    context = context or Context()
    calls = []
    def dialer(endpoint, timeout):
        calls.append((endpoint, timeout))
        return raw
    wire = net.Wire(dialer=dialer, context_factory=lambda: context)
    resolutions = []
    def resolve(host, budget, limits):
        resolutions.append(host)
        return [PUBLIC] if answers is None else answers
    wire.resolve = resolve
    monkeypatch.setattr(api, 'Wire', lambda: wire)
    return SimpleNamespace(raw=raw, context=context, calls=calls, resolutions=resolutions,
                           client=api.MetadataTransport(enabled=True, limits=limits), wire=wire)


def test_actual_adapter_identity_bytes_and_cleanup(monkeypatch):
    h = harness(monkeypatch, piece=1)
    result = h.client.fetch(REQUEST)
    assert result.bounded_bytes() == BODY
    assert result.source.body_sha256 == hashlib.sha256(BODY).hexdigest()
    assert result.source.body_size == len(BODY)
    assert result.source.resolved_revision == 'a' * 40
    assert result.source.requested_revision == 'main'
    assert result.source.revision_locator == '/sha'
    assert result.source.fetched_at.endswith('Z')
    assert h.resolutions == ['huggingface.co'] and len(h.calls) == 1
    assert h.calls[0][0].socket_address == ('93.184.216.34', 443)
    assert h.context.names == ['huggingface.co'] and h.raw.closed
    assert b'Host: huggingface.co' in h.raw.sent
    assert 'synthetic' not in repr(result) and 'Model' not in repr(REQUEST)
    with pytest.raises(TypeError): json.dumps(result)
    import pickle
    with pytest.raises(TypeError): pickle.dumps(result)


@pytest.mark.parametrize('framing', ['length', 'close', 'chunked'])
def test_framing(monkeypatch, framing):
    headers = [b'Content-Type: application/json']
    body = BODY
    if framing == 'length': headers += [b'Content-Length: ' + str(len(body)).encode()]
    if framing == 'chunked':
        headers += [b'Transfer-Encoding: chunked']
        body = f'{len(body):x}\r\n'.encode() + body + b'\r\n0\r\n\r\n'
    h = harness(monkeypatch, response(body, headers), piece=3)
    assert h.client.fetch(REQUEST).bounded_bytes() == BODY and h.raw.closed


@pytest.mark.parametrize('body,code', [
    (b'[]', 'json_invalid'), (b'{"id":"other"}', 'identity_mismatch'),
    (b'{"id":"synthetic/Model","id":"synthetic/Model"}', 'json_invalid'),
    (b'{"x":NaN}', 'json_invalid'), (b'{"x":Infinity}', 'json_invalid'),
    (b'{"x":1e999}', 'json_invalid'), (b'{"x":' + b'9' * 101 + b'}', 'json_invalid'),
    (b'{"x":"\\ud800"}', 'json_invalid'), (b'\xef\xbb\xbf{}', 'json_invalid'),
    (b'\xff', 'json_invalid'), (b'[' * 33 + b'0' + b']' * 33, 'json_invalid'),
    (b'{"id":"synthetic/Model","sha":"main"}', 'revision_mismatch'),
])
def test_json_and_binding_fail_closed(monkeypatch, body, code):
    h = harness(monkeypatch, response(body))
    with pytest.raises(MetadataError) as error: h.client.fetch(REQUEST)
    assert error.value.code == code and h.raw.closed
    assert body.decode('utf-8', errors='replace') not in str(error.value)


def test_missing_revision_is_not_fabricated(monkeypatch):
    h = harness(monkeypatch, response(b'{"id":"synthetic/Model"}'))
    result = h.client.fetch(REQUEST)
    assert result.source.resolved_revision is None and result.source.revision_locator is None
    assert result.source.version_status == 'bounded_content_revision_unconfirmed'


def test_fixed_revision_mismatch(monkeypatch):
    h = harness(monkeypatch)
    with pytest.raises(MetadataError, match='revision_mismatch'):
        h.client.fetch(MetadataRequest('huggingface', 'model', 'synthetic/Model', 'fixed', 'b' * 40))
    assert h.raw.closed


@pytest.mark.parametrize('status,code', [(301,'redirect_refused'), (302,'redirect_refused'),
    (303,'redirect_refused'), (307,'redirect_refused'), (308,'redirect_refused'), (404,'upstream_404'),
    (401,'upstream_access_denied'), (403,'upstream_access_denied'), (429,'upstream_rate_limited'), (503,'upstream_unavailable')])
def test_status_no_retry_or_error_body(monkeypatch, status, code):
    h = harness(monkeypatch, response(b'secret-upstream-error', [b'Location: https://outside.invalid/secret'], status))
    with pytest.raises(MetadataError) as error: h.client.fetch(REQUEST)
    assert error.value.code == code and len(h.calls) == 1 and h.raw.closed
    assert error.value.upstream_status == status
    assert 'secret' not in str(error.value) and 'outside' not in repr(error.value)


def test_default_observation_is_explicit():
    req = MetadataRequest('huggingface', 'dataset', 'synthetic/Data', 'default_observation', None)
    assert build_target(req) == 'https://huggingface.co/api/datasets/synthetic/Data'
    with pytest.raises(MetadataError): build_target(MetadataRequest('huggingface', 'model', 'x', 'symbolic', None))


@pytest.mark.parametrize('revision', ['refs/pr/1', '..', '%2f', 'a?b', 'a#b', 'a\\b', 'x\r\n', 'a'*129])
def test_complex_revisions_unsupported(revision):
    with pytest.raises(MetadataError): build_target(MetadataRequest('huggingface','model','synthetic/Model','symbolic',revision))
