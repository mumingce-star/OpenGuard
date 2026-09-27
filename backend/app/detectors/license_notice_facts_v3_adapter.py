"""Read-only adapter for the frozen B03/B04 v3 facts shape.

This adapter deliberately does not translate v3 into B02's v2 input and does
not make a license, NOTICE, authorization, obligation, or report conclusion.
It only produces a version-labelled consumption view for an A-side consumer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import hmac
import json


class V3FactsAdapterError(ValueError):
    def __init__(self) -> None:
        super().__init__("v3_facts_adapter_invalid")


@dataclass(frozen=True, slots=True)
class V3FactConsumption:
    fact_id: str
    subject_canonical_id: str
    authorization_status: str
    license_expression_id: None
    relationship_states: tuple[tuple[str, str], ...]
    gap_codes: tuple[str, ...]
    provenance_evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class V3FactsConsumptionPackage:
    schema_version: str
    source_package_sha256: str
    facts: tuple[V3FactConsumption, ...]


def canonical_v3_facts_sha256(package: Mapping[str, object]) -> str:
    try:
        encoded = json.dumps(package, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError):
        raise V3FactsAdapterError() from None
    return hashlib.sha256(encoded).hexdigest()


def consume_v3_facts(package: Mapping[str, object], *, expected_package_sha256: str) -> V3FactsConsumptionPackage:
    """Validate a v3 package and expose only its already-observed facts."""
    if not isinstance(package, Mapping) or not isinstance(expected_package_sha256, str):
        raise V3FactsAdapterError()
    actual = canonical_v3_facts_sha256(package)
    if not hmac.compare_digest(actual, expected_package_sha256):
        raise V3FactsAdapterError()
    try:
        if package["schema_version"] != "openguard.notice-license-facts/3" or package["package_status"] != "draft_facts_only":
            raise ValueError
        evidence = package["evidence"]
        facts = package["facts"]
        if not isinstance(evidence, list) or not isinstance(facts, list):
            raise ValueError
        evidence_ids = {item["evidence_id"] for item in evidence if isinstance(item, Mapping) and isinstance(item.get("evidence_id"), str)}
        if len(evidence_ids) != len(evidence):
            raise ValueError
        output: list[V3FactConsumption] = []
        seen: set[str] = set()
        for fact in facts:
            if not isinstance(fact, Mapping) or fact.get("authorization_status") != "pending" or fact.get("license_expression_id") is not None:
                raise ValueError
            fact_id = fact.get("fact_id")
            subject = fact.get("subject")
            refs = fact.get("fact_provenance_evidence_ids")
            relations = fact.get("relationships")
            gaps = fact.get("gaps")
            review = fact.get("review")
            if (not isinstance(fact_id, str) or not fact_id or fact_id in seen or not isinstance(subject, Mapping)
                    or not isinstance(subject.get("canonical_id"), str) or not isinstance(refs, list) or not refs
                    or not all(isinstance(ref, str) and ref in evidence_ids for ref in refs)
                    or not isinstance(relations, Mapping) or set(relations) != {"license", "notice", "copyright"}
                    or not isinstance(gaps, list) or review != {"required": True, "reason": "authorization_and_legal_interpretation_out_of_scope"}):
                raise ValueError
            states: list[tuple[str, str]] = []
            for name in ("license", "notice", "copyright"):
                relation = relations[name]
                if not isinstance(relation, Mapping) or relation.get("state") not in {"text_observed", "provider_declared_unverified", "gap"}:
                    raise ValueError
                relation_refs = relation.get("evidence_ids")
                if not isinstance(relation_refs, list) or not all(isinstance(ref, str) and ref in evidence_ids for ref in relation_refs):
                    raise ValueError
                if relation["state"] == "gap" and relation_refs:
                    raise ValueError
                states.append((name, relation["state"]))
            gap_codes = []
            for gap in gaps:
                if not isinstance(gap, Mapping) or not isinstance(gap.get("code"), str) or not gap["code"].startswith("GAP_"):
                    raise ValueError
                gap_codes.append(gap["code"])
            seen.add(fact_id)
            output.append(V3FactConsumption(fact_id, subject["canonical_id"], "pending", None, tuple(states), tuple(gap_codes), tuple(refs)))
    except (KeyError, TypeError, ValueError):
        raise V3FactsAdapterError() from None
    return V3FactsConsumptionPackage("openguard.notice-license-facts-consumption/1", actual, tuple(output))
