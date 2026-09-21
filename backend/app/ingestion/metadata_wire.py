"""Metadata-local pinned TLS/HTTP adapter. No environment proxy or DNS fallback.

h11 is already in the locked API runtime closure (0.16.0); no httpx/Hub SDK.
The injectable seams are trusted application/test code, never request fields.
"""
from __future__ import annotations

from dataclasses import replace
import ipaddress
import secrets
import socket
import ssl
import time

import h11

from app.security.address_policy import PublicEndpoint, resolve_and_require_public
from app.security.doh_resolver import _query, _parse_dns
from app.security.errors import IngestionSecurityError
from .metadata_types import ErrorCode, Limits, MetadataError


class Deadline:
    def __init__(self, limits: Limits, clock=time.monotonic):
        self.clock, self.operation = clock, limits.operation_seconds
        self.end = clock() + limits.total_seconds

    def remaining(self):
        remaining = self.end - self.clock()
        if remaining <= 0:
            raise MetadataError(ErrorCode.TIMEOUT)
        return min(self.operation, remaining)


def tls_context():
    # Unlike create_default_context(), this constructor does not consult
    # SSLKEYLOGFILE. No caller-supplied trust roots or verification switches.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_default_certs(ssl.Purpose.SERVER_AUTH)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.set_alpn_protocols(['http/1.1'])
    return context


def dial(endpoint: PublicEndpoint, timeout: float):
    raw = socket.socket(endpoint.family, socket.SOCK_STREAM, socket.IPPROTO_TCP)
    try:
        raw.settimeout(timeout)
        raw.connect(endpoint.socket_address)  # numeric address, never getaddrinfo
        return raw
    except BaseException:
        raw.close()
        raise


def public_answers(host, answers, limits):
    if type(answers) not in (tuple, list) or not 1 <= len(answers) <= limits.dns_answers:
        raise MetadataError(ErrorCode.DNS)
    try:
        return resolve_and_require_public(host, resolver=lambda *_: answers).endpoints
    except IngestionSecurityError:
        raise MetadataError(ErrorCode.POLICY) from None


def _peer(sock, endpoint):
    value = sock.getpeername()
    if ipaddress.ip_address(value[0]).compressed != endpoint.ip or value[1] != 443:
        raise MetadataError(ErrorCode.POLICY)


def _header_gate(raw, limits):
    lines = raw.split(b'\r\n')
    if len(raw) > limits.header_bytes or any(len(line) > limits.header_line_bytes for line in lines):
        raise MetadataError(ErrorCode.SIZE)
    if len(lines) - 3 > limits.header_fields:
        raise MetadataError(ErrorCode.SIZE)
    seen = set()
    for line in lines[1:-2]:
        if b':' not in line or line[:1] in (b' ', b'\t'):
            raise MetadataError(ErrorCode.PROTOCOL)
        key = line.split(b':', 1)[0].lower()
        if key in seen:
            raise MetadataError(ErrorCode.PROTOCOL)
        seen.add(key)


def _response(tls, request, budget, limits, content_type):
    parser = h11.Connection(h11.CLIENT, max_incomplete_event_size=limits.header_bytes)
    for event in request:
        data = parser.send(event)
        tls.settimeout(budget.remaining())
        tls.sendall(data)
    body, head = bytearray(), bytearray()
    headers_done = False
    eof = False
    wire_bytes = 0
    while True:
        budget.remaining()
        event = parser.next_event()
        if event is h11.NEED_DATA:
            if eof:
                raise MetadataError(ErrorCode.PROTOCOL)
            tls.settimeout(budget.remaining())
            chunk = tls.recv(4096)
            budget.remaining()
            eof = not chunk
            wire_bytes += len(chunk)
            # Also bounds chunk extensions, tiny chunks and trailer framing.
            if wire_bytes > 2 * limits.body_bytes + limits.header_bytes:
                raise MetadataError(ErrorCode.SIZE)
            if not headers_done:
                head.extend(chunk)
                end = head.find(b'\r\n\r\n')
                if end < 0:
                    if len(head) > limits.header_bytes or any(len(x) > limits.header_line_bytes for x in head.split(b'\r\n')):
                        raise MetadataError(ErrorCode.SIZE)
                    if eof:
                        raise MetadataError(ErrorCode.PROTOCOL)
                    continue
                _header_gate(bytes(head[:end + 4]), limits)
                parser.receive_data(bytes(head))
                head.clear()
                headers_done = True
            else:
                parser.receive_data(chunk)
        elif isinstance(event, h11.Response):
            status = event.status_code
            if 300 <= status < 400:
                raise MetadataError(ErrorCode.REDIRECT, upstream_status=status)
            code = ({401: ErrorCode.ACCESS, 403: ErrorCode.ACCESS, 404: ErrorCode.NOT_FOUND,
                     429: ErrorCode.RATE}.get(status, ErrorCode.UPSTREAM))
            if status != 200:
                raise MetadataError(code, upstream_status=status)
            headers = dict(event.headers)
            if headers.get(b'content-type', b'').lower() not in (
                    content_type, content_type + b'; charset=utf-8', content_type + b';charset=utf-8'):
                raise MetadataError(ErrorCode.PROTOCOL)
            if headers.get(b'content-encoding', b'identity').lower() != b'identity':
                raise MetadataError(ErrorCode.PROTOCOL)
            if b'transfer-encoding' in headers and (headers[b'transfer-encoding'].lower() != b'chunked' or b'content-length' in headers):
                raise MetadataError(ErrorCode.PROTOCOL)
            if b'content-length' in headers and int(headers[b'content-length']) > limits.body_bytes:
                raise MetadataError(ErrorCode.SIZE)
        elif isinstance(event, h11.Data):
            body.extend(event.data)
            if len(body) > limits.body_bytes:
                raise MetadataError(ErrorCode.SIZE)
        elif isinstance(event, h11.EndOfMessage):
            if event.headers or parser.trailing_data[0]:
                raise MetadataError(ErrorCode.PROTOCOL)
            return bytes(body)
        else:  # no interim response, upgrade or pipelined response
            raise MetadataError(ErrorCode.PROTOCOL)


class Wire:
    def __init__(self, *, dialer=dial, context_factory=tls_context):
        self.dialer, self.context_factory = dialer, context_factory

    def exchange(self, host, endpoints, path, budget, limits, *, dns_body=None):
        try:
            context = self.context_factory()
        except (OSError, ValueError):
            raise MetadataError(ErrorCode.TLS) from None
        if context.verify_mode != ssl.CERT_REQUIRED or context.check_hostname is not True or context.keylog_filename:
            raise MetadataError(ErrorCode.TLS)
        for endpoint in endpoints[:limits.attempts]:
            raw = tls = None
            try:
                raw = self.dialer(endpoint, budget.remaining())
                _peer(raw, endpoint)
                raw.settimeout(budget.remaining())
                tls = context.wrap_socket(raw, server_hostname=host)
                _peer(tls, endpoint)
                if tls.selected_alpn_protocol() not in (None, 'http/1.1'):
                    raise MetadataError(ErrorCode.TLS)
                media = b'application/json' if dns_body is None else b'application/dns-message'
                headers = [(b'Host', host.encode('ascii')), (b'Accept', media),
                           (b'Accept-Encoding', b'identity'), (b'Connection', b'close')]
                if dns_body is not None:
                    headers += [(b'Content-Type', media), (b'Content-Length', str(len(dns_body)).encode())]
                events = [h11.Request(method=b'GET' if dns_body is None else b'POST', target=path.encode('ascii'), headers=headers)]
                if dns_body is not None:
                    events.append(h11.Data(data=dns_body))
                events.append(h11.EndOfMessage())
                return _response(tls, events, budget, limits, media)
            except ssl.SSLError:
                raise MetadataError(ErrorCode.TLS) from None
            except (socket.timeout, TimeoutError):
                raise MetadataError(ErrorCode.TIMEOUT) from None
            except OSError:
                # Only a failed TCP dial may try the next prevalidated address.
                if raw is not None:
                    raise MetadataError(ErrorCode.CONNECT) from None
            except (h11.ProtocolError, ValueError, OverflowError):
                raise MetadataError(ErrorCode.PROTOCOL) from None
            finally:
                for resource in (tls, raw):
                    if resource is not None:
                        try:
                            resource.close()
                        except OSError:
                            pass
        budget.remaining()
        raise MetadataError(ErrorCode.CONNECT)

    def resolve(self, host, budget, limits):
        """Metadata-local DoH uses the same absolute deadline and wire limits.

        Reuses existing DNS codec, not the existing reset-per-read HTTP loop.
        Bootstrap is infrastructure, never an additional content allowlist.
        """
        bootstrap = tuple((socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (ip, 443))
                          for ip in ('1.1.1.1', '1.0.0.1'))
        endpoints = public_answers('cloudflare-dns.com', bootstrap, replace(limits, dns_answers=16))
        answers = []
        for qtype, family in ((1, socket.AF_INET), (28, socket.AF_INET6)):
            transaction = secrets.randbits(16)
            query = _query(host, qtype, transaction)
            try:
                body = self.exchange('cloudflare-dns.com', endpoints, '/dns-query', budget,
                                     replace(limits, body_bytes=65_536), dns_body=query)
                # Bind question name as well as the existing codec's ID/type.
                if body[12:len(query)] != query[12:]:
                    raise OSError
                ips = _parse_dns(body, transaction, qtype)
            except MetadataError as error:
                if error.code == ErrorCode.TIMEOUT:
                    raise
                raise MetadataError(ErrorCode.DNS) from None
            except (OSError, ValueError):
                raise MetadataError(ErrorCode.DNS) from None
            for ip in ips:
                address = (ip, 443) if family == socket.AF_INET else (ip, 443, 0, 0)
                answers.append((family, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', address))
                if len(answers) > limits.dns_answers:
                    raise MetadataError(ErrorCode.DNS)
        return answers
