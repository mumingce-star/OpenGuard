"""A07 adversarial synthetic wire cases. No real TLS handshake claimed."""
import json
import socket
import ssl
import importlib.util
from pathlib import Path

import pytest

# Load synthetic support by repository-relative path; also runs standalone.
_spec = importlib.util.spec_from_file_location('metadata_test_support',
    Path(__file__).resolve().parents[1] / 'unit/test_p1_metadata_transport.py')
_support = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_support)
REQUEST, BODY, PUBLIC = _support.REQUEST, _support.BODY, _support.PUBLIC
Context, Socket = _support.Context, _support.Socket
harness, response, no_external = _support.harness, _support.response, _support.no_external
from app.ingestion import metadata_egress as api, metadata_wire as net
from app.ingestion.metadata_types import Limits, MetadataError, MetadataRequest


@pytest.mark.parametrize('ip', ['127.0.0.1','10.0.0.1','169.254.169.254','::1','::ffff:93.184.216.34','fe80::1','fc00::1'])
def test_mixed_dns_never_dials(monkeypatch, ip):
    ipv6 = ':' in ip
    bad = (socket.AF_INET6 if ipv6 else socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '',
           (ip,443,0,0) if ipv6 else (ip,443))
    h = harness(monkeypatch, answers=[PUBLIC, bad])
    with pytest.raises(MetadataError, match='address_policy_rejected'): h.client.fetch(REQUEST)
    assert not h.calls and not h.context.names


@pytest.mark.parametrize('answers', [[], [PUBLIC]*17, [(1,)], 'not-addresses'])
def test_empty_malformed_excess_dns(monkeypatch, answers):
    h = harness(monkeypatch, answers=answers)
    with pytest.raises(MetadataError): h.client.fetch(REQUEST)
    assert not h.calls


@pytest.mark.parametrize('error', [ssl.SSLCertVerificationError('SECRET cert'), ssl.SSLError('SECRET hostname')])
def test_tls_failure_no_fallback(monkeypatch, error):
    h = harness(monkeypatch, answers=[PUBLIC, PUBLIC], context=Context(error))
    with pytest.raises(MetadataError, match='tls_failed') as caught: h.client.fetch(REQUEST)
    assert h.raw.closed and len(h.calls) == 1 and 'SECRET' not in str(caught.value)


def test_peer_mismatch_closes(monkeypatch):
    h = harness(monkeypatch)
    h.raw.peer = ('93.184.216.35',443)
    with pytest.raises(MetadataError, match='address_policy_rejected'): h.client.fetch(REQUEST)
    assert h.raw.closed and not h.context.names


@pytest.mark.parametrize('headers,body', [
    ([b'Content-Type: application/json', b'Content-Length: 100000000'], b''),
    ([b'Content-Type: text/html'], b'<html>SECRET</html>'),
    ([b'Content-Type: application/json', b'Content-Encoding: gzip'], b'compressed'),
    ([b'Content-Type: application/json', b'Content-Type: application/json'], BODY),
    ([b'Content-Type: application/json', b'Content-Length: 1', b'Content-Length: 2'], BODY),
    ([b'Content-Type: application/json', b'Content-Length: 1', b'Transfer-Encoding: chunked'], b'0\r\n\r\n'),
    ([b'Content-Type: application/json', b'Content-Length: 500'], b'{}'),
    ([b'Content-Type: application/json', b'Content-Length: 1'], BODY),
    ([b'Content-Type: application/json', b'Transfer-Encoding: chunked'], b'5\r\n{}'),
    ([b'Content-Type: application/json', b'Transfer-Encoding: chunked'], b'2\r\n{}\r\n0\r\nX-Trailer: secret\r\n\r\n'),
    ([b'Content-Type: application/json', b'X-Large: '+b'x'*8192], BODY),
    ([b'Content-Type: application/json']+[f'X-{i}: x'.encode() for i in range(65)], BODY),
])
def test_protocol_rejects_on_real_read_path(monkeypatch, headers, body):
    h = harness(monkeypatch, response(body, headers))
    with pytest.raises(MetadataError) as error: h.client.fetch(REQUEST)
    assert h.raw.closed and 'SECRET' not in str(error.value)


@pytest.mark.parametrize('framing', ['close','length','chunked'])
def test_streamed_body_capacity(monkeypatch, framing):
    body = BODY + b' '*100
    headers = [b'Content-Type: application/json']
    if framing == 'length': headers += [b'Content-Length: '+str(len(body)).encode()]
    if framing == 'chunked':
        headers += [b'Transfer-Encoding: chunked']
        body = f'{len(body):x}\r\n'.encode()+body+b'\r\n0\r\n\r\n'
    h = harness(monkeypatch, response(body, headers), limits=Limits(body_bytes=100), piece=7)
    with pytest.raises(MetadataError, match='response_too_large'): h.client.fetch(REQUEST)
    assert h.raw.closed


def test_slow_reads_share_absolute_budget(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(api.time, 'monotonic', lambda: now[0])
    h = harness(monkeypatch, piece=1, tick=lambda: now.__setitem__(0, now[0]+0.2),
                limits=Limits(total_seconds=1, operation_seconds=1))
    with pytest.raises(MetadataError, match='timeout'): h.client.fetch(REQUEST)
    assert h.raw.closed and now[0] <= 1.2
    assert h.raw.timeouts[-1] < h.raw.timeouts[0]


def test_multi_address_budget_not_reset(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(api.time, 'monotonic', lambda: now[0])
    other = (*PUBLIC[:4], ('93.184.216.35', 443))
    h = harness(monkeypatch, answers=[PUBLIC, other], limits=Limits(total_seconds=1))
    timeouts = []
    def dialer(endpoint, timeout):
        timeouts.append(timeout)
        now[0] += .75
        raise OSError('secret')
    h.wire.dialer = dialer
    with pytest.raises(MetadataError): h.client.fetch(REQUEST)
    assert timeouts == [1.0, .25]


def test_environment_does_not_supply_credentials_proxy_or_keylog(monkeypatch, tmp_path):
    for key in ('HF_TOKEN','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NETRC'):
        monkeypatch.setenv(key, 'SYNTHETIC_SENTINEL_DO_NOT_USE')
    log = tmp_path/'keylog'
    monkeypatch.setenv('SSLKEYLOGFILE', str(log))
    context = net.tls_context()
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert context.keylog_filename is None and not log.exists()
    h = harness(monkeypatch)
    h.client.fetch(REQUEST)
    assert b'SENTINEL' not in h.raw.sent and b'Authorization' not in h.raw.sent
    assert b'Cookie' not in h.raw.sent and b'Origin' not in h.raw.sent


def test_default_and_invalid_request_cannot_construct_wire(monkeypatch):
    monkeypatch.setattr(api, 'Wire', lambda: pytest.fail('wire construction forbidden'))
    with pytest.raises(MetadataError): api.MetadataTransport().fetch(REQUEST)
    with pytest.raises(MetadataError):
        api.MetadataTransport(enabled=True).fetch(MetadataRequest('other','model','x','default_observation',None))


def test_actual_numeric_dial_no_resolver(monkeypatch):
    calls = []
    raw = Socket(b'')
    raw.connect = lambda address: calls.append(address)
    monkeypatch.setattr(net.socket, 'socket', lambda *a: raw)
    endpoint = net.public_answers('huggingface.co', [PUBLIC], Limits())[0]
    assert net.dial(endpoint, 2) is raw
    assert calls == [('93.184.216.34',443)]


def test_doh_uses_same_wire_deadline_and_numeric_bootstrap(monkeypatch):
    sockets, names = [], []
    context = Context()
    class DNS(Socket):
        def recv(self, size):
            if not self.payload:
                query = self.sent.split(b'\r\n\r\n',1)[1]
                qtype = int.from_bytes(query[-4:-2], 'big')
                data = bytes([93,184,216,34]) if qtype == 1 else bytes.fromhex('26062800022000010248189325c81946')
                body = query[:2]+b'\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00'+query[12:]
                body += b'\xc0\x0c'+query[-4:]+b'\x00\x00\x00\x3c'+len(data).to_bytes(2,'big')+data
                self.payload = response(body, [b'Content-Type: application/dns-message', b'Content-Length: '+str(len(body)).encode()])
            return super().recv(size)
    def dialer(endpoint, timeout):
        names.append(endpoint.ip)
        raw = DNS(b'', peer=(endpoint.ip,443))
        sockets.append(raw)
        return raw
    wire = net.Wire(dialer=dialer, context_factory=lambda:context)
    answers = wire.resolve('huggingface.co', net.Deadline(Limits()), Limits())
    assert len(net.public_answers('huggingface.co', answers, Limits())) == 2
    assert names == ['1.1.1.1','1.1.1.1'] and context.names == ['cloudflare-dns.com']*2
    assert all(s.closed and b'POST /dns-query' in s.sent for s in sockets)


def test_slow_doh_is_bounded_on_actual_read_path(monkeypatch):
    now = [0.0]
    raw = Socket(b'HTTP/1.1 200 OK\r\nX-Slow: '+b'x'*100, peer=('1.1.1.1',443), piece=1,
                 tick=lambda: now.__setitem__(0, now[0]+.2))
    wire = net.Wire(dialer=lambda *a:raw, context_factory=Context)
    limits = Limits(total_seconds=1)
    with pytest.raises(MetadataError, match='timeout'):
        wire.resolve('huggingface.co', net.Deadline(limits, lambda:now[0]), limits)
    assert raw.closed and now[0] <= 1.2


@pytest.mark.parametrize('field,value', [('verify_mode',ssl.CERT_NONE),('check_hostname',False),('keylog_filename','SYNTHETIC')])
def test_insecure_context_never_dials(monkeypatch, field, value):
    context = Context()
    setattr(context, field, value)
    h = harness(monkeypatch, context=context)
    with pytest.raises(MetadataError, match='tls_failed'): h.client.fetch(REQUEST)
    assert not h.calls


def test_json_node_and_header_total_budgets(monkeypatch):
    h = harness(monkeypatch, response(b'{"id":"synthetic/Model","many":[1,2,3,4]}'), limits=Limits(json_nodes=3))
    with pytest.raises(MetadataError, match='json_invalid'): h.client.fetch(REQUEST)
    assert h.raw.closed
    headers = [b'Content-Type: application/json']+[f'X-{i}: '.encode()+b'x'*7000 for i in range(5)]
    h = harness(monkeypatch, response(BODY,headers))
    with pytest.raises(MetadataError, match='response_too_large'): h.client.fetch(REQUEST)
    assert h.raw.closed


def test_default_dial_failure_closes_original_socket(monkeypatch):
    raw = Socket(b'')
    def fail(address): raise OSError('SYNTHETIC')
    raw.connect = fail
    monkeypatch.setattr(net.socket,'socket',lambda *a:raw)
    with pytest.raises(OSError): net.dial(net.public_answers('huggingface.co',[PUBLIC],Limits())[0],1)
    assert raw.closed


def test_synthetic_consumer_does_not_persist_or_make_business_claims(monkeypatch):
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1]/'fixtures/p1/metadata-transport/synthetic_consumer.py'
    spec = importlib.util.spec_from_file_location('synthetic_metadata_consumer',path)
    consumer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(consumer)
    h = harness(monkeypatch)
    result = h.client.fetch(REQUEST)
    before = result.bounded_bytes()
    def forbidden(*a, **k): pytest.fail('consumer must not open files')
    monkeypatch.setattr('builtins.open',forbidden)
    observed = consumer.consume(result)
    assert observed['synthetic'] is True and observed['boundary_checked'] is True
    assert 'license' not in observed and 'authorization' not in observed
    assert result.bounded_bytes() == before


@pytest.mark.parametrize('values', [{'body_bytes':0},{'body_bytes':1048577},{'total_seconds':float('nan')},
                                   {'operation_seconds':False},{'dns_answers':17},{'attempts':0}])
def test_invalid_configuration(values):
    with pytest.raises(MetadataError): Limits(**values)


@pytest.mark.parametrize('phase', ['sendall','recv'])
def test_io_failure_closes_without_retry(monkeypatch, phase):
    h = harness(monkeypatch)
    def fail(*args): raise OSError('SYNTHETIC SECRET')
    setattr(h.raw,phase,fail)
    with pytest.raises(MetadataError, match='connection_failed') as caught: h.client.fetch(REQUEST)
    assert h.raw.closed and len(h.calls) == 1 and 'SECRET' not in str(caught.value)


def test_fixed_revision_success(monkeypatch):
    h = harness(monkeypatch)
    result = h.client.fetch(MetadataRequest('huggingface','model','synthetic/Model','fixed','a'*40))
    assert result.source.resolved_revision == result.source.requested_revision == 'a'*40
    assert result.source.body_sha256 != result.source.resolved_revision
