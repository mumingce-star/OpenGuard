"""Bounded DNS wireformat queries over pinned-bootstrap HTTPS."""

from __future__ import annotations

import ipaddress
import secrets
import socket
import ssl
import struct

from .address_policy import AddressInfo


_DOH_HOST = "cloudflare-dns.com"
_DOH_BOOTSTRAP = ("1.1.1.1", "1.0.0.1")
_DNS_HEADER = struct.Struct("!HHHHHH")
_RECORD_HEADER = struct.Struct("!HHIH")
_MAX_RESPONSE_BYTES = 80 * 1024


def _query(host: str, query_type: int, transaction_id: int) -> bytes:
    labels = host.split(".")
    if any(not label or len(label.encode("ascii")) > 63 for label in labels):
        raise OSError("invalid DNS name")
    question = b"".join(bytes((len(label),)) + label.encode("ascii") for label in labels) + b"\0"
    return _DNS_HEADER.pack(transaction_id, 0x0100, 1, 0, 0, 0) + question + struct.pack("!HH", query_type, 1)


def _read_http_response(payload: bytes, *, timeout: float) -> bytes:
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.set_alpn_protocols(["http/1.1"])
    request = (
        b"POST /dns-query HTTP/1.1\r\n"
        b"Host: cloudflare-dns.com\r\n"
        b"Accept: application/dns-message\r\n"
        b"Content-Type: application/dns-message\r\n"
        + f"Content-Length: {len(payload)}\r\n".encode("ascii")
        + b"Connection: close\r\n\r\n"
        + payload
    )
    last_error: OSError | None = None
    for address in _DOH_BOOTSTRAP:
        raw: socket.socket | None = None
        tls: ssl.SSLSocket | None = None
        try:
            raw = socket.create_connection((address, 443), timeout=timeout)
            tls = context.wrap_socket(raw, server_hostname=_DOH_HOST)
            raw = None
            tls.settimeout(timeout)
            tls.sendall(request)
            response = bytearray()
            while True:
                chunk = tls.recv(16 * 1024)
                if not chunk:
                    break
                response.extend(chunk)
                if len(response) > _MAX_RESPONSE_BYTES:
                    raise OSError("DoH response exceeds limit")
            return _parse_http(bytes(response))
        except (OSError, ssl.SSLError) as error:
            last_error = OSError("DoH request failed")
            last_error.__cause__ = error
        finally:
            if tls is not None:
                tls.close()
            if raw is not None:
                raw.close()
    raise OSError("DoH resolver unavailable") from last_error


def _parse_http(response: bytes) -> bytes:
    try:
        raw_headers, body = response.split(b"\r\n\r\n", 1)
        lines = raw_headers.split(b"\r\n")
        if lines[0] != b"HTTP/1.1 200 OK":
            raise ValueError
        headers: dict[bytes, bytes] = {}
        for line in lines[1:]:
            name, value = line.split(b":", 1)
            key = name.strip().lower()
            if key in headers:
                raise ValueError
            headers[key] = value.strip().lower()
        if headers.get(b"content-type", b"").split(b";", 1)[0] != b"application/dns-message":
            raise ValueError
        if b"transfer-encoding" in headers:
            raise ValueError
        length = int(headers[b"content-length"])
    except (KeyError, ValueError) as error:
        raise OSError("invalid DoH HTTP response") from error
    if length != len(body) or length > 64 * 1024:
        raise OSError("invalid DoH HTTP response")
    return body


def _skip_name(message: bytes, offset: int) -> int:
    visited = 0
    while True:
        if offset >= len(message) or visited > 255:
            raise OSError("invalid DNS name")
        length = message[offset]
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(message):
                raise OSError("invalid DNS name")
            pointer = ((length & 0x3F) << 8) | message[offset + 1]
            if pointer >= len(message):
                raise OSError("invalid DNS name")
            return offset + 2
        if length & 0xC0 or length > 63:
            raise OSError("invalid DNS name")
        offset += 1
        if length == 0:
            return offset
        if offset + length > len(message):
            raise OSError("invalid DNS name")
        offset += length
        visited += length + 1


def _parse_dns(message: bytes, transaction_id: int, query_type: int) -> tuple[str, ...]:
    if len(message) < _DNS_HEADER.size:
        raise OSError("invalid DNS response")
    response_id, flags, questions, answers, _authority, _additional = _DNS_HEADER.unpack_from(message)
    if response_id != transaction_id or questions != 1 or not flags & 0x8000 or flags & 0x0200 or flags & 0x000F:
        raise OSError("invalid DNS response")
    offset = _skip_name(message, _DNS_HEADER.size)
    if offset + 4 > len(message):
        raise OSError("invalid DNS response")
    question_type, question_class = struct.unpack_from("!HH", message, offset)
    if question_type != query_type or question_class != 1:
        raise OSError("invalid DNS response")
    offset += 4
    addresses: list[str] = []
    for _ in range(answers):
        offset = _skip_name(message, offset)
        if offset + _RECORD_HEADER.size > len(message):
            raise OSError("invalid DNS response")
        record_type, record_class, _ttl, data_length = _RECORD_HEADER.unpack_from(message, offset)
        offset += _RECORD_HEADER.size
        if offset + data_length > len(message):
            raise OSError("invalid DNS response")
        data = message[offset : offset + data_length]
        offset += data_length
        if record_class == 1 and record_type == query_type:
            expected = 4 if query_type == 1 else 16
            if data_length != expected:
                raise OSError("invalid DNS response")
            addresses.append(ipaddress.ip_address(data).compressed)
    return tuple(addresses)


def resolve_via_doh(host: str, port: int) -> tuple[AddressInfo, ...]:
    """Resolve A and AAAA using a fixed, TLS-authenticated DoH bootstrap."""

    if type(host) is not str or not host or port != 443:
        raise OSError("invalid DoH query")
    answers: list[AddressInfo] = []
    for query_type, family in ((1, socket.AF_INET), (28, socket.AF_INET6)):
        transaction_id = secrets.randbits(16)
        payload = _query(host, query_type, transaction_id)
        response = _read_http_response(payload, timeout=5.0)
        for address in _parse_dns(response, transaction_id, query_type):
            socket_address: tuple[object, ...]
            if family == socket.AF_INET:
                socket_address = (address, port)
            else:
                socket_address = (address, port, 0, 0)
            answers.append((family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", socket_address))
    if not answers:
        raise OSError("DoH returned no address")
    return tuple(answers)


__all__ = ["resolve_via_doh"]
