"""Candidate adapter for A's fixed source readback capability.

A authenticates and reads the fixed record and obtains current revocation
state. The normalized fields below are private to this candidate. They do not
specify an HTTP route, public schema, or issuer implementation.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from app.p2.contract import strict_json

_TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,200}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_MAX_RECORD = 32 * 1024
_MAX_CONTENT = 64 * 1024


@dataclass(frozen=True)
class SourcePin:
    receipt_id: str
    receipt_version: int
    receipt_sha256: str
    scan_id: str
    resource_id: str
    resource_version: str
    scope_id: str
    role: str


@dataclass(frozen=True)
class IssuerReadback:
    """Result from A's authenticated reader, including current issuer state."""

    record_bytes: bytes
    current_status: str


@dataclass(frozen=True)
class SourceObservation:
    pin: SourcePin
    issuer: str
    policy: str
    policy_version: str
    observed_at: datetime
    content_sha256: str


def consume_source_readback(
    pin: SourcePin, content: bytes, *,
    issuer_policies: frozenset[tuple[str, str, str]],
    read_authenticated: Callable[[str, int], IssuerReadback],
) -> SourceObservation:
    """Validate exact binding and source bytes after an authenticated GET.

    A must supply the reader and policy allowlist from server configuration.
    This adapter does not accept a per-request verification boolean or an
    arbitrary URL. The returned observation establishes no use or fulfillment.
    """
    if type(pin) is not SourcePin or type(pin.receipt_version) is not int or pin.receipt_version < 1:
        raise ValueError("source_pin_invalid")
    fields = {"receipt_id": pin.receipt_id, "scan_id": pin.scan_id, "resource_id": pin.resource_id,
              "resource_version": pin.resource_version, "scope_id": pin.scope_id, "role": pin.role}
    if (any(type(value) is not str or not _TOKEN.fullmatch(value) for value in fields.values())
            or type(pin.receipt_sha256) is not str or not _HASH.fullmatch(pin.receipt_sha256)):
        raise ValueError("source_pin_invalid")
    if type(content) is not bytes or not 0 < len(content) <= _MAX_CONTENT:
        raise ValueError("source_content_limit")
    try:
        response = read_authenticated(pin.receipt_id, pin.receipt_version)
    except Exception as exc:
        raise ValueError("source_readback_unavailable") from exc
    if type(response) is not IssuerReadback:
        raise ValueError("source_readback_invalid")
    if response.current_status != "accepted":
        raise ValueError("source_not_currently_accepted")
    raw = response.record_bytes
    if type(raw) is not bytes or not 0 < len(raw) <= _MAX_RECORD:
        raise ValueError("source_record_limit")
    if hashlib.sha256(raw).hexdigest() != pin.receipt_sha256:
        raise ValueError("source_receipt_hash_mismatch")
    try:
        value = strict_json(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("source_receipt_invalid_json") from exc
    required = set(fields) | {"receipt_version", "issuer", "policy", "policy_version", "status",
                              "observed_at", "content_bytes", "content_sha256"}
    if type(value) is not dict or set(value) != required:
        raise ValueError("source_receipt_fields_invalid")
    if (type(value["receipt_version"]) is not int or value["receipt_version"] != pin.receipt_version
            or any(value[key] != expected for key, expected in fields.items())):
        raise ValueError("source_receipt_binding_mismatch")
    issuer_policy = tuple(value[key] for key in ("issuer", "policy", "policy_version"))
    if any(type(item) is not str or not _TOKEN.fullmatch(item) for item in issuer_policy) or issuer_policy not in issuer_policies:
        raise ValueError("source_issuer_policy_untrusted")
    if value["status"] != "accepted":
        raise ValueError("source_receipt_not_accepted")
    observed_at = value["observed_at"]
    try:
        if type(observed_at) is not str or len(observed_at) > 40:
            raise ValueError()
        timestamp = datetime.fromisoformat(observed_at)
        if timestamp.tzinfo is None or timestamp.utcoffset() != timezone.utc.utcoffset(timestamp):
            raise ValueError()
    except ValueError as exc:
        raise ValueError("source_observation_time_invalid") from exc
    content_sha = hashlib.sha256(content).hexdigest()
    if type(value["content_bytes"]) is not int or value["content_bytes"] != len(content) or content_sha != value["content_sha256"]:
        raise ValueError("source_content_pin_mismatch")
    return SourceObservation(pin, *issuer_policy, timestamp.astimezone(timezone.utc), content_sha)
