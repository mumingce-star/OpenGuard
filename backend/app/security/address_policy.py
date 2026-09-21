"""Explicit public-address classification for task-scoped trusted egress."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .errors import IngestionSecurityError


AddressInfo = tuple[int, int, int, str, tuple[object, ...]]
Resolver = Callable[[str, int], Iterable[AddressInfo]]

_DENIED_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.88.99.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "::/128",
        "::1/128",
        "::ffff:0:0/96",
        "64:ff9b:1::/48",
        "100::/64",
        "2001:2::/48",
        "2001:db8::/32",
        "fc00::/7",
        "fe80::/10",
        "ff00::/8",
    )
)


@dataclass(frozen=True)
class PublicEndpoint:
    family: int
    socket_address: tuple[object, ...]
    ip: str


@dataclass(frozen=True)
class PublicResolution:
    host: str
    endpoints: tuple[PublicEndpoint, ...]

    @property
    def addresses(self) -> tuple[str, ...]:
        return tuple(endpoint.ip for endpoint in self.endpoints)


def _system_resolver(host: str, port: int) -> Iterable[AddressInfo]:
    # Local fake-IP/TUN resolvers may intentionally return RFC 2544 addresses.
    # Use the fixed, TLS-authenticated DoH bootstrap so the egress layer can
    # validate and dial the real public address instead of weakening the CIDR
    # deny list for a workstation-specific network mode.
    from .doh_resolver import resolve_via_doh

    return resolve_via_doh(host, port)


def _is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.scope_id is not None:
        return False
    if any(address in network for network in _DENIED_NETWORKS if address.version == network.version):
        return False
    return not (
        address.is_unspecified
        or address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or getattr(address, "is_site_local", False)
        or not address.is_global
    )


def resolve_and_require_public(
    host: str,
    *,
    port: int = 443,
    resolver: Resolver | None = None,
) -> PublicResolution:
    """Resolve every A/AAAA result and fail closed if any answer is non-public."""

    if type(host) is not str or not host or type(port) is not int or port != 443:
        raise IngestionSecurityError("invalid_source", "source_address_not_public")
    try:
        answers = tuple((resolver or _system_resolver)(host, port))
    except (OSError, UnicodeError, ValueError) as error:
        raise IngestionSecurityError("invalid_source", "source_address_unavailable") from error
    if not answers:
        raise IngestionSecurityError("invalid_source", "source_address_unavailable")

    endpoints: list[PublicEndpoint] = []
    seen: set[tuple[int, str, tuple[object, ...]]] = set()
    for answer in answers:
        try:
            family, socktype, protocol, _, socket_address = answer
            if family not in {socket.AF_INET, socket.AF_INET6} or socktype != socket.SOCK_STREAM:
                raise ValueError
            if protocol not in {0, socket.IPPROTO_TCP} or not isinstance(socket_address, tuple):
                raise ValueError
            raw_ip = socket_address[0]
            if type(raw_ip) is not str or "%" in raw_ip:
                raise ValueError
            address = ipaddress.ip_address(raw_ip)
            if socket_address[1] != port or (family == socket.AF_INET) != isinstance(address, ipaddress.IPv4Address):
                raise ValueError
            if family == socket.AF_INET:
                if len(socket_address) != 2:
                    raise ValueError
                canonical_socket_address: tuple[object, ...] = (address.compressed, port)
            else:
                if len(socket_address) != 4 or socket_address[2:] != (0, 0):
                    raise ValueError
                canonical_socket_address = (address.compressed, port, 0, 0)
            if not _is_public(address):
                raise IngestionSecurityError("invalid_source", "source_address_not_public")
        except IngestionSecurityError:
            raise
        except (IndexError, TypeError, ValueError) as error:
            raise IngestionSecurityError("invalid_source", "source_address_not_public") from error
        rendered = address.compressed
        key = (family, rendered, canonical_socket_address)
        if key not in seen:
            seen.add(key)
            endpoints.append(PublicEndpoint(family=family, socket_address=canonical_socket_address, ip=rendered))
    if not endpoints:
        raise IngestionSecurityError("invalid_source", "source_address_unavailable")
    return PublicResolution(host=host, endpoints=tuple(endpoints))


__all__ = ["AddressInfo", "PublicEndpoint", "PublicResolution", "Resolver", "resolve_and_require_public"]
