from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.detectors.license_notice_facts_v3_adapter import (
    V3FactsAdapterError, canonical_v3_facts_sha256, consume_v3_facts,
)


def _facts() -> dict:
    return json.loads((Path(__file__).parents[1] / "fixtures" / "notice-license-facts-v3" / "facts.json").read_text("utf-8"))


def test_v3_adapter_is_hash_pinned_and_preserves_only_pending_observations() -> None:
    facts = _facts()
    result = consume_v3_facts(facts, expected_package_sha256=canonical_v3_facts_sha256(facts))
    assert result.schema_version == "openguard.notice-license-facts-consumption/1"
    assert len(result.facts) == len(facts["facts"])
    assert all(item.authorization_status == "pending" and item.license_expression_id is None for item in result.facts)
    assert all(dict(item.relationship_states)["notice"] in {"gap", "text_observed", "provider_declared_unverified"} for item in result.facts)


def test_v3_adapter_rejects_hash_tampering_and_notice_to_license_promotion() -> None:
    facts = _facts()
    pinned = canonical_v3_facts_sha256(facts)
    facts["facts"][0]["license_expression_id"] = "MIT"
    with pytest.raises(V3FactsAdapterError):
        consume_v3_facts(facts, expected_package_sha256=pinned)
