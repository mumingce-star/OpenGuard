"""Offline TEST_ONLY transport: real Wire framing, synthetic sockets, no network."""
import hashlib
import ipaddress
import json
import socket
import ssl
from pathlib import Path
import pytest
from app.ingestion import official_http_server as api
from app.ingestion.metadata_types import Limits, MetadataError
from app.ingestion import metadata_wire as net
from app.security.address_policy import PublicEndpoint

LICENSE = b'Copyright (c) 2011-2026 Charlie Robbins, Marak Squires, Jade Michael Thornton and the Contributors.\n\nPermission is hereby granted, free of charge, to any person obtaining\na copy of this software and associated documentation files (the\n"Software"), to deal in the Software without restriction, including\nwithout limitation the rights to use, copy, modify, merge, publish,\ndistribute, sublicense, and/or sell copies of the Software, and to\npermit persons to whom the Software is furnished to do so, subject to\nthe following conditions:\n\nThe above copyright notice and this permission notice shall be\nincluded in all copies or substantial portions of the Software.\n\nTHE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,\nEXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF\nMERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND\nNONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE\nLIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION\nOF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION\nWITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.\n'
NPM = b'{"name":"http-server","version":"14.1.2","license":"MIT"}'

def response(body, media=b'application/json', status=200, framing='length', extra=None):
    headers = [b'Content-Type: '+media] + (extra or [])
    if framing == 'length': headers.append(b'Content-Length: '+str(len(body)).encode())
    if framing == 'chunked':
        headers.append(b'Transfer-Encoding: chunked')
        body = f'{len(body):x}\r\n'.encode()+body+b'\r\n0\r\n\r\n'
    return b'HTTP/1.1 '+str(status).encode()+b' test\r\n'+b'\r\n'.join(headers)+b'\r\n\r\n'+body

class FakeSocket:
    def __init__(self, endpoint, driver):
        self.endpoint, self.driver = endpoint, driver
        self.sent = b''; self.payload = None; self.closed = False
    def settimeout(self, value): pass
    def getpeername(self): return ('8.8.8.8', 443) if self.driver.wrong_peer else self.endpoint.socket_address
    def selected_alpn_protocol(self): return 'http/1.1'
    def sendall(self, raw): self.sent += raw
    def recv(self, size):
        if self.driver.timeout: raise TimeoutError()
        if self.payload is None: self.payload = self.driver.payload(self.sent)
        part, self.payload = self.payload[:size], self.payload[size:]
        return part
    def close(self): self.closed = True

class Context:
    verify_mode=ssl.CERT_REQUIRED
    check_hostname=True
    keylog_filename=None
    def __init__(self, driver): self.driver = driver
    def wrap_socket(self, raw, *, server_hostname):
        self.driver.names.append(server_hostname)
        if self.driver.tls_error: raise ssl.SSLError('synthetic')
        return raw

class Driver:
    def __init__(self, *, license_body=LICENSE, npm=NPM, fail_at=None, status=503,
                 wrong_peer=False, tls_error=False, timeout=False):
        self.license_body, self.npm, self.fail_at, self.status = license_body, npm, fail_at, status
        self.wrong_peer, self.tls_error, self.timeout = wrong_peer, tls_error, timeout
        self.sockets=[]; self.names=[]; self.requests=[]
    def dial(self, endpoint, timeout):
        assert api.allows_connection(endpoint.socket_address)
        sock=FakeSocket(endpoint,self);self.sockets.append(sock);return sock
    def factory(self, owner, job): return api._AuditedWire(owner,job,dialer=self.dial,context_factory=lambda:Context(self))
    def payload(self, request):
        self.requests.append(request)
        if self.fail_at == len(self.requests): return response(b'error',status=self.status)
        if request.startswith(b'POST '):
            query=request.split(b'\r\n\r\n',1)[1]
            qtype=int.from_bytes(query[-4:-2],'big')
            address=ipaddress.ip_address('93.184.216.34' if qtype == 1 else '2606:4700:4700::1111').packed
            dns=query[:2]+bytes.fromhex('81800001000100000000')+query[12:]+b'\xc0\x0c'+query[-4:]+b'\x00\x00\x00\x3c'+len(address).to_bytes(2,'big')+address
            return response(dns, b'application/dns-message')
        if api.GIT_PATH.encode() in request: return response(self.license_body, b'text/plain')
        if api.NPM_PATH.encode() in request: return response(self.npm)
        raise AssertionError('unexpected route')

@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*a,**k): raise AssertionError('REAL NETWORK FORBIDDEN')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(socket,'getaddrinfo',forbidden)


def test_fixed_six_http_and_replay_is_read_only(tmp_path):
    driver=Driver(); client=api.FixedOfficialFetcher(tmp_path,_wire_factory=driver.factory)
    out=client.fetch('job1')
    assert out['status']=='succeeded',out
    assert (out['http_intents'],out['http_dispatched'],out['http_responses'])==(6,6,6)
    assert len(driver.requests)==6 and [r.split(b' ',1)[0] for r in driver.requests]==[b'POST',b'POST',b'GET']*2
    assert [s['kind'] for s in out['sources']]==['git_license','npm_metadata']
    assert out['sources'][0]['sha256']==api.LICENSE_SHA256
    assert out['sources'][1]['source_level']=='provider_declared_unverified'
    assert out['sources'][1]['commit'] is None
    assert client.fetch('job1')==out and len(driver.requests)==6
    assert all(s.closed for s in driver.sockets)
    assert not api.allows_connection(('93.184.216.34',443))
    assert all(Path(r['raw_wire_path']).is_file() and Path(r['request_wire_path']).is_file() for r in out['requests'])


DNS_CAPTURE = Path(__file__).parents[1] / 'fixtures' / 'official_npm_dns_20261023'


class CapturedNpmDNSDriver(Driver):
    """Actual public DoH packets; only bottom socket transport is synthetic."""
    def __init__(self, mode='actual'):
        super().__init__(); self.mode = mode

    def payload(self, request):
        if request.startswith(b'POST ') and b'\x08registry\x05npmjs\x03org\x00' in request:
            self.requests.append(request)
            query = request.split(b'\r\n\r\n', 1)[1]
            qtype = int.from_bytes(query[-4:-2], 'big')
            raw = (DNS_CAPTURE / f'npm-{qtype}.body').read_bytes()
            assert query == (DNS_CAPTURE / f'npm-{qtype}.request.wire').read_bytes().split(b'\r\n\r\n', 1)[1]
            if self.mode == 'actual':
                return (DNS_CAPTURE / f'npm-{qtype}.response.wire').read_bytes()
            if qtype == 28 and self.mode == 'private_tail':
                raw = raw[:-16] + ipaddress.ip_address('::1').packed
            if qtype == 28 and self.mode == 'too_many':
                # 12 A plus 21 AAAA: bounded aggregate overflow, no truncation.
                raw = raw[:6] + (21).to_bytes(2, 'big') + raw[8:] + raw[-28:] * 9
            if qtype == 28 and self.mode == 'wrong_id': raw = b'\0\0' + raw[2:]
            if qtype == 28 and self.mode == 'wrong_question': raw = raw[:13] + b'x' + raw[14:]
            return response(raw, b'application/dns-message')
        return super().payload(request)


def captured_transactions(monkeypatch):
    ids = iter((1, 2, 37624, 31743))
    monkeypatch.setattr(net.secrets, 'randbits', lambda _: next(ids))


def test_actual_npm_twelve_a_and_twelve_aaaa_are_all_bound_before_single_get(tmp_path, monkeypatch):
    captured_transactions(monkeypatch)
    driver = CapturedNpmDNSDriver()
    out = api.FixedOfficialFetcher(tmp_path, _wire_factory=driver.factory).fetch('actual-dns-offline')
    assert out['status'] == 'succeeded', out
    assert len(driver.requests) == 6 and len(driver.sockets) == 6
    assert driver.sockets[-1].endpoint.ip == '104.16.9.34'
    assert out['http_intents'] == 6 and out['http_responses'] == 6
    for qtype in (1, 28):
        raw = (DNS_CAPTURE / f'npm-{qtype}.body').read_bytes()
        assert len(net._parse_dns(raw, int.from_bytes(raw[:2], 'big'), qtype)) == 12


@pytest.mark.parametrize('mode,code', [('private_tail', 'address_policy_rejected'),
    ('too_many', 'dns_failed'), ('wrong_id', 'dns_failed'), ('wrong_question', 'dns_failed')])
def test_actual_npm_dns_tail_and_identity_fail_closed(tmp_path, monkeypatch, mode, code):
    captured_transactions(monkeypatch)
    driver = CapturedNpmDNSDriver(mode)
    out = api.FixedOfficialFetcher(tmp_path, _wire_factory=driver.factory).fetch('reject-dns-offline')
    assert out['status'] == 'failed' and out['error_code'] == code, out
    assert out['http_intents'] == 5 and len(driver.requests) == 5
    assert not any(b'GET /http-server/14.1.2 ' in item for item in driver.requests)


def test_legacy_wire_aggregate_answer_limit_stays_sixteen(monkeypatch):
    ids = iter((37624, 31743))
    monkeypatch.setattr(net.secrets, 'randbits', lambda _: next(ids))
    wire = net.Wire()
    monkeypatch.setattr(wire, 'exchange', lambda *a, dns_body, **k:
        (DNS_CAPTURE / f'npm-{int.from_bytes(dns_body[-4:-2], "big")}.body').read_bytes())
    with pytest.raises(MetadataError, match='dns_failed'):
        wire.resolve(api.NPM_HOST, net.Deadline(Limits()), Limits())


def test_eighteen_shared_across_instances(tmp_path):
    driver=Driver()
    for i in range(3): assert api.FixedOfficialFetcher(tmp_path,_wire_factory=driver.factory).fetch(f'job{i}')['status']=='succeeded'
    out=api.FixedOfficialFetcher(tmp_path,_wire_factory=driver.factory).fetch('fourth')
    assert out['error_code']=='official_source_http_budget_exhausted' and out['http_intents']==0
    assert len(driver.requests)==18

@pytest.mark.parametrize('number,status',[(1,503),(3,301),(3,404),(6,429)])
def test_failure_consumes_stops_and_never_replays(tmp_path,number,status):
    driver=Driver(fail_at=number,status=status);client=api.FixedOfficialFetcher(tmp_path,_wire_factory=driver.factory)
    out=client.fetch('failed')
    assert out['status']=='failed' and out['http_intents']==number
    assert out['requests'][-1]['http_status']==status
    assert client.fetch('failed')==out and len(driver.requests)==number

@pytest.mark.parametrize('kwargs', [{'wrong_peer':True},{'tls_error':True},{'timeout':True}])
def test_bad_peer_tls_timeout_no_retry(tmp_path,kwargs):
    driver=Driver(**kwargs);out=api.FixedOfficialFetcher(tmp_path,_wire_factory=driver.factory).fetch('bad')
    assert out['status']=='failed' and out['http_intents']==1 and len(driver.sockets)==1
    assert not api.allows_connection(('1.1.1.1',443))

@pytest.mark.parametrize('license_body,npm,expected',[(LICENSE+b'x',NPM,3),(LICENSE,b'{"name":"other","version":"14.1.2"}',6),(LICENSE,b'{"name":"http-server","version":"0.1"}',6),(LICENSE,b'{"name":"http-server","name":"http-server","version":"14.1.2"}',6)])
def test_hash_name_version_duplicate_refusal(tmp_path,license_body,npm,expected):
    driver=Driver(license_body=license_body,npm=npm);out=api.FixedOfficialFetcher(tmp_path,_wire_factory=driver.factory).fetch('bad')
    assert out['status']=='failed' and out['http_intents']==expected


def test_unknown_inflight_job_does_not_replay(tmp_path):
    client=api.FixedOfficialFetcher(tmp_path)
    (tmp_path/'HTTP_BUDGET.json').write_text(json.dumps({'version':api.VERSION_ID,'max_task_http':18,'max_job_http':6,'requests':[],'jobs':{client.namespace+':inflight':{'status':'running'}}}))
    assert client.fetch('inflight')['status']=='outcome_unknown'

@pytest.mark.parametrize('job',['../escape','x/y','', 'x'*97])
def test_job_path_rejected(tmp_path,job):
    with pytest.raises(ValueError): api.FixedOfficialFetcher(tmp_path).fetch(job)


def test_permission_window_exact_thread_and_port():
    endpoint=PublicEndpoint(socket.AF_INET,('93.184.216.34',443),'93.184.216.34')
    assert not api.allows_connection(endpoint.socket_address)
    with api.connection_window(endpoint):
        assert api.allows_connection(endpoint.socket_address)
        assert not api.allows_connection(('93.184.216.34',80))
        assert not api.allows_connection(('1.1.1.1',443))
        assert not api.allows_connection(('registry.npmjs.org',443))
    assert not api.allows_connection(endpoint.socket_address)

class RawSocket:
    def __init__(self,data):self.data=data;self.sent=b''
    def settimeout(self,t):pass
    def sendall(self,b):self.sent+=b
    def recv(self,n):out,self.data=self.data[:n],self.data[n:];return out

@pytest.mark.parametrize('framing',['length','chunked','close'])
def test_exact_32k_body_boundary_including_coalesced_headers(framing):
    limit=Limits(body_bytes=32768,header_bytes=32768,attempts=1)
    for size,success in ((32768,True),(32769,False)):
        raw=RawSocket(response(b'x'*size,b'text/plain',framing=framing))
        request=[net.h11.Request(method=b'GET',target=b'/',headers=[(b'Host',b'example.com')]),net.h11.EndOfMessage()]
        if success: assert len(net._response(raw,request,net.Deadline(limit),limit,b'text/plain'))==32768
        else:
            with pytest.raises(MetadataError):net._response(raw,request,net.Deadline(limit),limit,b'text/plain')


def test_oversized_headers_and_ambiguous_framing():
    for headers in ([b'X-Long: '+b'x'*32768],[b'Transfer-Encoding: chunked',b'Content-Length: 1']):
        limit=Limits(body_bytes=32768,header_bytes=32768,attempts=1)
        raw=RawSocket(response(b'x',framing='close',extra=headers))
        request=[net.h11.Request(method=b'GET',target=b'/',headers=[(b'Host',b'example.com')]),net.h11.EndOfMessage()]
        with pytest.raises((MetadataError,net.h11.ProtocolError)):net._response(raw,request,net.Deadline(limit),limit,b'application/json')


def test_exact_header_total_limit_and_overflow():
    limit=Limits(body_bytes=32768,header_bytes=32768,attempts=1)
    prefix=b'HTTP/1.1 200 test\r\nContent-Type: application/json\r\nContent-Length: 1\r\n'
    fixed=prefix+b''.join(f'X-{i}: '.encode()+b'x'*4000+b'\r\n' for i in range(7))+b'X-final: '
    for size,ok in ((32768,True),(32769,False)):
        header=fixed+b'x'*(size-len(fixed)-4)+b'\r\n\r\n'
        assert len(header)==size
        raw=RawSocket(header+b'x')
        request=[net.h11.Request(method=b'GET',target=b'/',headers=[(b'Host',b'example.com')]),net.h11.EndOfMessage()]
        if ok: assert net._response(raw,request,net.Deadline(limit),limit,b'application/json')==b'x'
        else:
            with pytest.raises((MetadataError,net.h11.ProtocolError)):net._response(raw,request,net.Deadline(limit),limit,b'application/json')

@pytest.mark.parametrize('payload',[
 b'HTTP/1.1 200 ok\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\n\r\nzz\r\nx\r\n0\r\n\r\n',
 b'HTTP/1.1 200 ok\r\nContent-Type: application/json\r\nContent-Length: 4\r\n\r\nx',
 b'HTTP/1.1 200 ok\r\nContent-Type: application/json\r\nContent-Encoding: gzip\r\nContent-Length: 1\r\n\r\nx',
 b'HTTP/1.1 200 ok\r\nContent-Type: text/html\r\nContent-Length: 1\r\n\r\nx',
])
def test_malformed_framing_content_refused(payload):
    limit=Limits(body_bytes=32768,header_bytes=32768,attempts=1)
    request=[net.h11.Request(method=b'GET',target=b'/',headers=[(b'Host',b'example.com')]),net.h11.EndOfMessage()]
    with pytest.raises((MetadataError,net.h11.ProtocolError)):net._response(RawSocket(payload),request,net.Deadline(limit),limit,b'application/json')


def test_private_endpoint_and_scope_thread_isolation():
    with pytest.raises(MetadataError):
        with api.connection_window(PublicEndpoint(socket.AF_INET,('127.0.0.1',443),'127.0.0.1')):pass
    seen=[]
    import threading
    endpoint=PublicEndpoint(socket.AF_INET,('93.184.216.34',443),'93.184.216.34')
    with api.connection_window(endpoint):
        worker=threading.Thread(target=lambda:seen.append(api.allows_connection(endpoint.socket_address)))
        worker.start();worker.join()
    assert seen==[False]


def test_task_budget_is_not_http_timeout_bool(tmp_path):
    (tmp_path/'HTTP_BUDGET.json').write_text(json.dumps({'version':api.VERSION_ID,'max_task_http':True,'max_job_http':6,'requests':[],'jobs':{}}))
    with pytest.raises(ValueError):api.FixedOfficialFetcher(tmp_path).fetch('invalid')


def test_unknown_target_does_not_consume_http(tmp_path):
    client=api.FixedOfficialFetcher(tmp_path)
    wire=api._AuditedWire(client,{'job_id':'x'})
    with pytest.raises(MetadataError):wire.resolve('evil.invalid',None,None)
    with pytest.raises(MetadataError):wire.exchange('registry.npmjs.org',[], '/other',None,None)
    assert not (tmp_path/'HTTP_BUDGET.json').exists()


def test_task_budget_shared_across_tenants_same_job_id_without_raw_leak(tmp_path):
    budget=tmp_path/'shared.json';driver=Driver()
    a=api.FixedOfficialFetcher(tmp_path/'tenant-a',budget_path=budget,_wire_factory=driver.factory)
    b=api.FixedOfficialFetcher(tmp_path/'tenant-b',budget_path=budget,_wire_factory=driver.factory)
    ra=a.fetch('same');rb=b.fetch('same')
    assert ra['status']==rb['status']=='succeeded' and len(driver.requests)==12
    assert Path(ra['sources'][0]['body_path']).is_relative_to(a.root)
    assert Path(rb['sources'][0]['body_path']).is_relative_to(b.root)
    assert a.fetch('same')==ra and b.fetch('same')==rb and len(driver.requests)==12
    assert a.fetch('third')['status']=='succeeded'
    assert b.fetch('fourth')['error_code']=='official_source_http_budget_exhausted'
    assert len(driver.requests)==18
    assert (tmp_path/'shared.json.lock').is_file()


def test_unknown_and_busy_keep_actual_prior_dispatch_counts(tmp_path):
    client=api.FixedOfficialFetcher(tmp_path)
    key=client.namespace+':inflight'
    request={'job_id':'inflight','job_key':key,'number':1,'dispatch_attempt_utc':'2026-10-23T00:00:00Z',
             'first_sendall_completed_utc':None,'http_status':None,'timed_out':None,'state':'DISPATCH_ATTEMPT_OUTCOME_UNKNOWN'}
    (tmp_path/'HTTP_BUDGET.json').write_text(json.dumps({'version':api.VERSION_ID,'max_task_http':18,'max_job_http':6,
        'requests':[request],'jobs':{key:{'status':'running'}}}))
    unknown=client.fetch('inflight')
    assert unknown['status']=='outcome_unknown'
    assert (unknown['http_intents'],unknown['http_dispatched'],unknown['http_responses'])==(1,1,0)
    assert unknown['requests'][0]['timed_out'] is None
    with api._SERIAL:
        busy=client.fetch('inflight')
        assert busy['error_code']=='official_source_busy'
        assert (busy['http_intents'],busy['http_dispatched'],busy['http_responses'])==(1,1,0)
    assert json.loads((tmp_path/'HTTP_BUDGET.json').read_text())['requests']==[request]
