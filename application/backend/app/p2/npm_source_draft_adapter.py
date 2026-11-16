"""Internal TEST_ONLY bridge; no transport, issuer, public DTO or persistence.

An authenticated-transport callback is an A-owned dependency, not an issuer
implemented here. Its observation and the unchanged historical byte-consistency
draft remain separate. Equal metadata bytes never authenticate an older event.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Callable

from ..p2b.npm_metadata import parse_attested_response
from .source_admission_draft import validate_draft

VERSION = "openguard-p2-npm-source-draft-adapter/1"
ASSOCIATION = "SAME_METADATA_BYTES_NOT_SAME_ACQUISITION_EVENT"


class AdapterError(ValueError):
    """Internal, code-owned errors; these are not new public API errors."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _snapshot(value, *, depth=0, budget=None):
    """Copy plain data without custom hooks; fingerprint retains exact types."""
    if budget is None:
        budget = [1024]
    budget[0] -= 1
    if budget[0] < 0 or depth > 32:
        raise AdapterError("ADAPTER_INPUT_INVALID")
    kind = type(value)
    if value is None or kind in (bool, int, str, bytes):
        if kind in (str, bytes) and len(value) > 65536:
            raise AdapterError("ADAPTER_INPUT_INVALID")
        if kind is int and value.bit_length() > 4096:
            raise AdapterError("ADAPTER_INPUT_INVALID")
        return value, (kind.__name__, value)
    if kind is float and math.isfinite(value):
        return value, ("float", value.hex())
    if kind is datetime:
        # No arbitrary tzinfo/copy callbacks at this private input boundary.
        if value.tzinfo is not None and type(value.tzinfo) is not timezone:
            raise AdapterError("ADAPTER_INPUT_INVALID")
        return value, ("datetime", value.isoformat(), value.fold)
    if kind in (tuple, list):
        copied, fingerprints = [], []
        for item in value:
            child, fingerprint = _snapshot(item, depth=depth+1, budget=budget)
            copied.append(child)
            fingerprints.append(fingerprint)
        return (tuple(copied) if kind is tuple else copied), (kind.__name__, tuple(fingerprints))
    if kind is dict:
        if any(type(key) is not str for key in value):
            raise AdapterError("ADAPTER_INPUT_INVALID")
        copied, fingerprints = {}, []
        for key, item in value.items():
            child, fingerprint = _snapshot(item, depth=depth+1, budget=budget)
            copied[key] = child
            fingerprints.append((key, fingerprint))
        return copied, ("dict", tuple(sorted(fingerprints)))
    raise AdapterError("ADAPTER_INPUT_INVALID")


def adapt_npm_source_draft(
    *, body: bytes, transport_receipt: dict,
    verify_attestation: Callable[[dict], bool], claim: bytes,
    pins: tuple, blobs: dict, event_indices: tuple,
) -> dict:
    """Join strict observation and existing draft by exact metadata bytes only.

    Task-owned pins/selectors are consistency inputs, never caller-issued trust.
    Only ordinary receipt data and built-in datetime/timezone are supported.
    The callback must itself be side-effect free. Copies protect the values this
    bridge consumes; they cannot sandbox arbitrary callback closure side effects.
    """
    if (type(body) is not bytes or type(claim) is not bytes
            or type(transport_receipt) is not dict or not callable(verify_attestation)
            or type(blobs) is not dict or type(pins) is not tuple
            or type(event_indices) is not tuple
            or any(type(k) is not str or type(v) is not bytes for k, v in blobs.items())):
        raise AdapterError("ADAPTER_INPUT_INVALID")
    # Freeze every consumed input before invoking the A-owned callback. Bytes
    # are immutable; the outer blob mapping and selector/pin containers are not
    # permitted to redirect the later validation through a callback closure.
    frozen_blobs = dict(blobs)
    frozen_pins, _ = _snapshot(pins)
    frozen_indices, _ = _snapshot(event_indices)
    private_receipt, _ = _snapshot(transport_receipt)
    mutated = False

    def verify_private(receipt):
        nonlocal mutated
        callback_receipt, before = _snapshot(receipt)
        try:
            answer = verify_attestation(callback_receipt)
        finally:
            try:
                _, after = _snapshot(callback_receipt)
                mutated = before != after
            except AdapterError:
                mutated = True
            if mutated:
                raise AdapterError("ADAPTER_VERIFIER_MUTATED_RECEIPT")
        return answer

    try:
        observation = parse_attested_response(
            body=body, receipt=private_receipt, verify_attestation=verify_private)
    except ValueError:
        # The existing strict parser bounds callback exceptions. Retain this
        # bridge's specific mutation diagnosis without changing that parser.
        if mutated:
            raise AdapterError("ADAPTER_VERIFIER_MUTATED_RECEIPT") from None
        raise
    if (observation.get("state") != "official_metadata_observed"
            or observation.get("official_metadata_observed") is not True):
        raise AdapterError("ADAPTER_TRANSPORT_NOT_OBSERVED")
    if body != frozen_blobs.get("metadata"):
        raise AdapterError("ADAPTER_METADATA_BYTES_MISMATCH")
    draft = validate_draft(
        claim, pins=frozen_pins, blobs=frozen_blobs, event_indices=frozen_indices)
    return {
        "version": VERSION, "association": ASSOCIATION,
        "transport_observation": observation, "historical_draft": draft,
        "data_scope": "TEST_ONLY", "formal_effect": "none",
        "historical_receipt_authenticated": False,
        "source_issuance_performed": False, "public_contract_approved": False,
        "m1_complete": False,
    }
