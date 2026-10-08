"""Offline validator for one exact npm registry response; transport belongs to A."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Callable

PACKAGE = "is-number"
VERSION = "7.0.0"
SOURCE_URL = "https://registry.npmjs.org/is-number/7.0.0"
MAX_RESPONSE_BYTES = 32 * 1024
PARSER_VERSION = "p2b-npm-metadata/1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("npm_duplicate_json_key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("npm_nonstandard_json")


def parse_official_response(*, body: bytes | None, source_url: str, status: int | None,
                            observed_at: datetime, timed_out: bool = False,
                            expected_sha256: str | None = None) -> dict[str, Any]:
    """Produce a bounded receipt; registry declarations never prove a license grant."""
    if source_url != SOURCE_URL:
        raise ValueError("npm_untrusted_source")
    if not isinstance(observed_at, datetime) or observed_at.tzinfo is None or observed_at.utcoffset() != timezone.utc.utcoffset(observed_at):
        raise ValueError("npm_time_must_be_utc")
    if body is not None and (not isinstance(body, bytes) or len(body) > MAX_RESPONSE_BYTES):
        raise ValueError("npm_response_size_limit")
    response_hash = hashlib.sha256(body).hexdigest() if body is not None else None
    if expected_sha256 is not None and (not isinstance(expected_sha256, str) or not _SHA256.fullmatch(expected_sha256)
                                        or response_hash != expected_sha256):
        raise ValueError("npm_response_hash_mismatch")
    receipt = {"kind": "openguard.p2b.npm-metadata/0", "parser_version": PARSER_VERSION,
               "source": SOURCE_URL, "observed_at": observed_at.isoformat(),
               "response_sha256": response_hash, "response_bytes": len(body) if body is not None else None,
               "source_level": "untrusted_transport", "official_metadata_observed": False,
               "authorization_status": "pending"}
    if timed_out:
        return {**receipt, "state": "failed", "reason": "timeout", "http_status": status}
    if status != 200 or not isinstance(body, bytes):
        return {**receipt, "state": "failed", "reason": "http_failure", "http_status": status}
    if not body:
        raise ValueError("npm_response_size_limit")
    try:
        data = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_pairs,
                          parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("npm_invalid_json") from exc
    if not isinstance(data, dict) or data.get("name") != PACKAGE:
        raise ValueError("npm_wrong_package")
    if data.get("version") != VERSION:
        raise ValueError("npm_wrong_version")
    declared = data.get("license")
    if not isinstance(declared, str) or len(declared) > 100:
        declared = None
    return {**receipt, "state": "parsed_untrusted_transport",
            "package": PACKAGE, "version": VERSION, "declared_license": declared,
            "license_declaration_state": "provider_declared_unverified" if declared else "not_declared",
            "license_text_verified": False,
            "applicability_human_verified": False, "authorization_status": "pending"}


def parse_official_response_receipt(*, body: bytes | None, source_url: str, status: int | None,
                                    observed_at: datetime, timed_out: bool = False,
                                    expected_sha256: str | None = None) -> dict[str, Any]:
    """Return a stable failure receipt for A without reflecting response content."""
    try:
        return parse_official_response(
            body=body, source_url=source_url, status=status, observed_at=observed_at,
            timed_out=timed_out, expected_sha256=expected_sha256,
        )
    except ValueError as exc:
        bounded_body = body if isinstance(body, bytes) and len(body) <= MAX_RESPONSE_BYTES else None
        return {"kind": "openguard.p2b.npm-metadata/0", "parser_version": PARSER_VERSION,
                "state": "failed", "reason": str(exc), "source": SOURCE_URL,
                "source_level": "untrusted_transport",
                "observed_at": observed_at.isoformat() if isinstance(observed_at, datetime) and observed_at.tzinfo else None,
                "http_status": status,
                "response_sha256": hashlib.sha256(bounded_body).hexdigest() if bounded_body is not None else None,
                "response_bytes": len(bounded_body) if bounded_body is not None else None,
                "official_metadata_observed": False, "authorization_status": "pending"}


def parse_attested_response(*, body: bytes, receipt: dict[str, Any],
                            verify_attestation: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
    """Consume only a receipt authenticated by A's trusted egress boundary.

    A owns the verifier and network policy. This function never makes a request.
    """
    if not isinstance(receipt, dict) or not callable(verify_attestation):
        raise ValueError("npm_transport_unverified")
    if (receipt.get("request_method") != "GET" or receipt.get("request_url") != SOURCE_URL
            or receipt.get("final_url") != SOURCE_URL or type(receipt.get("redirect_count")) is not int
            or receipt["redirect_count"] != 0):
        raise ValueError("npm_transport_target_mismatch")
    policy_id = receipt.get("transport_policy_id")
    if not isinstance(policy_id, str) or not policy_id.strip() or len(policy_id) > 128:
        raise ValueError("npm_transport_policy_missing")
    if not isinstance(body, bytes) or type(receipt.get("response_bytes")) is not int or receipt["response_bytes"] != len(body):
        raise ValueError("npm_transport_size_mismatch")
    response_sha256 = receipt.get("response_sha256")
    if not isinstance(response_sha256, str) or not _SHA256.fullmatch(response_sha256):
        raise ValueError("npm_transport_hash_missing")
    try:
        verified = verify_attestation(receipt)
    except Exception as exc:
        raise ValueError("npm_transport_unverified") from exc
    if verified is not True:
        raise ValueError("npm_transport_unverified")
    parsed = parse_official_response(
        body=body, source_url=SOURCE_URL, status=receipt.get("http_status"),
        observed_at=receipt.get("observed_at"),
        expected_sha256=response_sha256,
    )
    if parsed["state"] != "parsed_untrusted_transport":
        return parsed
    return {**parsed, "state": "official_metadata_observed",
            "official_metadata_observed": True, "source_level": "official_registry_metadata",
            "transport_policy_id": policy_id}
