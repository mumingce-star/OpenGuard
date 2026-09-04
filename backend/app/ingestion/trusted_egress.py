"""Task-scoped CONNECT proxy that owns DNS validation and the actual dial."""

from __future__ import annotations

import selectors
import socket
import socketserver
import threading
from collections.abc import Callable
from dataclasses import dataclass

from app.security.address_policy import PublicEndpoint, PublicResolution, Resolver, resolve_and_require_public
from app.security.errors import IngestionSecurityError


Connector = Callable[[PublicEndpoint, float], socket.socket]
_HEADER_MAX_BYTES = 8 * 1024
_COPY_CHUNK = 64 * 1024


@dataclass(frozen=True)
class EgressConnectionEvidence:
    host: str
    resolved_addresses: tuple[str, ...]
    dialed_address: str
    tls_server_name: str


class _TransferLedger:
    def __init__(self, maximum: int) -> None:
        self._maximum = maximum
        self._used = 0
        self._lock = threading.Lock()

    @property
    def used(self) -> int:
        with self._lock:
            return self._used

    def add(self, amount: int) -> None:
        with self._lock:
            if amount < 0 or self._used + amount > self._maximum:
                raise IngestionSecurityError("scanner_failed", "git_fetch_limit_exceeded")
            self._used += amount


def _default_connector(endpoint: PublicEndpoint, timeout: float) -> socket.socket:
    outbound = socket.socket(endpoint.family, socket.SOCK_STREAM, socket.IPPROTO_TCP)
    try:
        outbound.settimeout(timeout)
        outbound.connect(endpoint.socket_address)
        return outbound
    except Exception:
        outbound.close()
        raise


class _ProxyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = False
    daemon_threads = True

    def __init__(self, owner: "TrustedEgressProxy") -> None:
        self.owner = owner
        super().__init__(("127.0.0.1", 0), _ConnectHandler, bind_and_activate=True)


class _ConnectHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        owner = self.server.owner  # type: ignore[attr-defined]
        outbound: socket.socket | None = None
        try:
            self.request.settimeout(owner.connect_timeout_s)
            header = bytearray()
            while b"\r\n\r\n" not in header:
                chunk = self.request.recv(min(1024, _HEADER_MAX_BYTES + 1 - len(header)))
                if not chunk:
                    raise IngestionSecurityError("invalid_source", "source_connect_invalid")
                header.extend(chunk)
                if len(header) > _HEADER_MAX_BYTES:
                    raise IngestionSecurityError("invalid_source", "source_connect_invalid")
            request_head, remainder = bytes(header).split(b"\r\n\r\n", 1)
            try:
                request_line = request_head.split(b"\r\n", 1)[0].decode("ascii")
                method, authority, version = request_line.split(" ")
            except (UnicodeDecodeError, ValueError) as error:
                raise IngestionSecurityError("invalid_source", "source_connect_invalid") from error
            if method != "CONNECT" or authority.lower() != f"{owner.host}:443" or version not in {"HTTP/1.0", "HTTP/1.1"}:
                raise IngestionSecurityError("invalid_source", "source_connect_not_allowed")

            resolution = resolve_and_require_public(owner.host, resolver=owner.resolver)
            outbound, endpoint = owner.connect(resolution)
            owner.record(resolution, endpoint)
            self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            if remainder:
                owner.ledger.add(len(remainder))
                outbound.sendall(remainder)
            self._tunnel(owner, outbound)
        except IngestionSecurityError as error:
            owner.fail(error.reason)
            try:
                self.request.sendall(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
            except OSError:
                pass
        except (OSError, TimeoutError):
            owner.fail("source_connection_failed")
        finally:
            if outbound is not None:
                outbound.close()

    def _tunnel(self, owner: "TrustedEgressProxy", outbound: socket.socket) -> None:
        self.request.settimeout(owner.connect_timeout_s)
        outbound.settimeout(owner.connect_timeout_s)
        selector = selectors.DefaultSelector()
        selector.register(self.request, selectors.EVENT_READ, outbound)
        selector.register(outbound, selectors.EVENT_READ, self.request)
        try:
            while True:
                events = selector.select(timeout=owner.connect_timeout_s)
                if not events:
                    raise TimeoutError
                for key, _ in events:
                    source = key.fileobj
                    destination = key.data
                    chunk = source.recv(_COPY_CHUNK)
                    if not chunk:
                        return
                    owner.ledger.add(len(chunk))
                    destination.sendall(chunk)
        finally:
            selector.close()


class TrustedEgressProxy:
    """A single-source proxy with no direct-network fallback.

    The proxy never terminates TLS. Git negotiates TLS end-to-end using the
    canonical repository host, while this layer pins the socket to an address
    from the immediately validated DNS answer set.
    """

    def __init__(
        self,
        host: str,
        *,
        transfer_max_bytes: int,
        connect_timeout_s: int,
        resolver: Resolver | None = None,
        connector: Connector | None = None,
    ) -> None:
        if (
            type(host) is not str
            or not host
            or type(transfer_max_bytes) is not int
            or transfer_max_bytes <= 0
            or type(connect_timeout_s) is not int
            or connect_timeout_s <= 0
        ):
            raise ValueError("invalid trusted egress configuration")
        self.host = host
        self.connect_timeout_s = connect_timeout_s
        self.resolver = resolver
        self._connector = connector or _default_connector
        self.ledger = _TransferLedger(transfer_max_bytes)
        self._evidence: list[EgressConnectionEvidence] = []
        self._failure_reason: str | None = None
        self._lock = threading.Lock()
        self._server: _ProxyServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def proxy_url(self) -> str:
        server = self._server
        if server is None:
            raise RuntimeError("trusted egress is not running")
        host, port = server.server_address
        return f"http://{host}:{port}"

    @property
    def evidence(self) -> tuple[EgressConnectionEvidence, ...]:
        with self._lock:
            return tuple(self._evidence)

    @property
    def failure_reason(self) -> str | None:
        with self._lock:
            return self._failure_reason

    def connect(self, resolution: PublicResolution) -> tuple[socket.socket, PublicEndpoint]:
        last_error: OSError | None = None
        for endpoint in resolution.endpoints:
            try:
                return self._connector(endpoint, float(self.connect_timeout_s)), endpoint
            except OSError as error:
                last_error = error
        raise IngestionSecurityError("invalid_source", "source_connection_failed") from last_error

    def record(self, resolution: PublicResolution, endpoint: PublicEndpoint) -> None:
        item = EgressConnectionEvidence(
            host=self.host,
            resolved_addresses=resolution.addresses,
            dialed_address=endpoint.ip,
            tls_server_name=self.host,
        )
        with self._lock:
            self._evidence.append(item)

    def fail(self, reason: str) -> None:
        with self._lock:
            if self._failure_reason is None:
                self._failure_reason = reason

    def start(self) -> "TrustedEgressProxy":
        if self._server is not None:
            raise RuntimeError("trusted egress already started")
        try:
            self._server = _ProxyServer(self)
        except OSError as error:
            raise IngestionSecurityError("scanner_failed", "trusted_egress_unavailable") from error
        self._thread = threading.Thread(target=self._server.serve_forever, name="openguard-trusted-egress", daemon=True)
        self._thread.start()
        return self

    def close(self) -> None:
        server = self._server
        thread = self._thread
        self._server = None
        self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=2)

    def __enter__(self) -> "TrustedEgressProxy":
        return self.start()

    def __exit__(self, *_: object) -> None:
        self.close()


__all__ = ["EgressConnectionEvidence", "TrustedEgressProxy"]
