import hashlib
import json
from dataclasses import replace

import pytest

from app.p2b.source_readback import IssuerReadback, SourcePin, consume_source_readback

SOURCE = b"synthetic evidence bytes"
CONTENT_SHA = hashlib.sha256(SOURCE).hexdigest()
POLICIES = frozenset({("test-issuer", "test-policy", "1")})


def case(**changes):
    fields = {"receipt_id": "test-receipt", "receipt_version": 2, "scan_id": "scan-1",
              "resource_id": "npm:is-number", "resource_version": "7.0.0", "scope_id": "package",
              "role": "license_text"}
    record = json.dumps({**fields, "issuer": "test-issuer", "policy": "test-policy", "policy_version": "1",
                         "observed_at": "2026-11-16T00:00:00Z", "status": "accepted",
                         "content_bytes": len(SOURCE), "content_sha256": CONTENT_SHA, **changes}).encode()
    return SourcePin(**fields, receipt_sha256=hashlib.sha256(record).hexdigest()), record


def consume(pin, record, *, state="accepted", content=SOURCE):
    return consume_source_readback(pin, content, issuer_policies=POLICIES,
                                   read_authenticated=lambda *_: IssuerReadback(record, state))


def test_readback_selects_only_fixed_identity_and_yields_observation():
    pin, record = case()
    calls = []
    def read(receipt_id, version):
        calls.append((receipt_id, version))
        return IssuerReadback(record, "accepted")
    result = consume_source_readback(pin, SOURCE, issuer_policies=POLICIES, read_authenticated=read)
    assert calls == [("test-receipt", 2)]
    assert result.pin == pin and result.content_sha256 == CONTENT_SHA


@pytest.mark.parametrize("state", ["rejected", "conflict", "revoked", "unknown"])
def test_current_state_blocks_even_previously_accepted_receipt(state):
    with pytest.raises(ValueError, match="not_currently_accepted"):
        consume(*case(), state=state)


@pytest.mark.parametrize("changes,error", [
    ({"issuer": "unknown"}, "issuer_policy"), ({"policy_version": "0"}, "issuer_policy"),
    ({"resource_version": "8.0.0"}, "binding"), ({"scan_id": "other"}, "binding"),
    ({"scope_id": "everything"}, "binding"), ({"role": "transport"}, "binding"),
    ({"content_bytes": True}, "content_pin"), ({"status": "revoked"}, "receipt_not_accepted"),
    ({"observed_at": "2026-11-16T08:00:00+08:00"}, "observation_time"),
    ({"verified": True}, "fields_invalid"),
])
def test_rehashed_altered_fields_still_fail(changes, error):
    with pytest.raises(ValueError, match=error):
        consume(*case(**changes))


def test_bytes_pin_false_verifier_and_missing_record_field_fail():
    pin, raw = case()
    with pytest.raises(ValueError, match="receipt_hash"):
        consume(replace(pin, receipt_sha256="0" * 64), raw)
    with pytest.raises(ValueError, match="content_pin"):
        consume(pin, raw, content=b"wrong")
    with pytest.raises(ValueError, match="readback_invalid"):
        consume_source_readback(pin, SOURCE, issuer_policies=POLICIES, read_authenticated=lambda *_: True)
    value = json.loads(raw)
    del value["policy"]
    raw = json.dumps(value).encode()
    with pytest.raises(ValueError, match="fields_invalid"):
        consume(replace(pin, receipt_sha256=hashlib.sha256(raw).hexdigest()), raw)
