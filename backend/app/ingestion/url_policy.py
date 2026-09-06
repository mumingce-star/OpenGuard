"""Synchronous syntax gate for the public-HTTPS Git source boundary."""

from __future__ import annotations

import ipaddress
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit, urlunsplit

from app.security.errors import IngestionSecurityError


_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_BAD_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")
_ENCODED_SEPARATOR = frozenset("/\\?#@")


@dataclass(frozen=True)
class PublicGitUrl:
    canonical: str
    host: str


def _reject(reason: str) -> None:
    raise IngestionSecurityError("invalid_source", reason)


def _has_control(value: str) -> bool:
    return any(unicodedata.category(character) == "Cc" for character in value)


def _validate_segment(raw: str) -> str:
    if not raw or _BAD_PERCENT.search(raw):
        _reject("path_invalid")
    once = unquote(raw)
    twice = unquote(once)
    if _has_control(once) or _has_control(twice):
        _reject("url_invalid")
    if once in {".", ".."} or twice in {".", ".."}:
        _reject("path_invalid")
    if any(character in _ENCODED_SEPARATOR for character in once) or any(
        character in _ENCODED_SEPARATOR for character in twice
    ):
        _reject("path_invalid")
    return raw


def parse_public_git_url(value: str) -> PublicGitUrl:
    """Return the only URL representation that may reach the Git process.

    This performs no DNS or network activity. Address classification is repeated
    by ``TrustedEgress`` immediately before every outbound connection.
    """

    if type(value) is not str or not value or value != value.strip():
        _reject("url_invalid")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        _reject("url_invalid")
    if len(encoded) > 2_048 or _has_control(value):
        _reject("url_invalid")

    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        _reject("url_invalid")
    hostname = parsed.hostname
    if (
        parsed.scheme != "https"
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port not in {None, 443}
        or not parsed.path.startswith("/")
    ):
        _reject("url_invalid")

    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        _reject("host_not_public")

    lowered = hostname.rstrip(".").lower()
    if not lowered or lowered == "localhost" or lowered.endswith(".localhost") or "%" in lowered:
        _reject("host_not_public")
    try:
        ascii_host = lowered.encode("idna").decode("ascii")
    except UnicodeError:
        _reject("host_invalid")
    if len(ascii_host) > 253 or any(_DNS_LABEL.fullmatch(label) is None for label in ascii_host.split(".")):
        _reject("host_invalid")

    raw_segments = parsed.path.split("/")[1:]
    if not raw_segments or any(not segment for segment in raw_segments):
        _reject("path_invalid")
    for segment in raw_segments:
        _validate_segment(segment)

    canonical = urlunsplit(("https", ascii_host, parsed.path, "", ""))
    return PublicGitUrl(canonical=canonical, host=ascii_host)


__all__ = ["PublicGitUrl", "parse_public_git_url"]
