"""Read-only P2 v1 material accounting; never admit sources or grant permission."""
from __future__ import annotations

import hashlib
import re
from typing import Any

from app.p2.contract import Material, Result, digest
from .candidates import USAGE_FIELDS
from .materials import parse_local_material

# These are literal text anchors, not a license classifier or new Formal rules.
CLAUSE_ANCHORS = {
    "permission_text": "Permission is hereby granted, free of charge",
    "notice_retention": "The above copyright notice and this permission notice shall be included",
    "warranty_disclaimer": 'THE SOFTWARE IS PROVIDED "AS IS"',
    "liability_disclaimer": "IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE",
}
_EXACT = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")


def _clause_locations(raw: bytes) -> list[dict[str, Any]]:
    """Return byte/line locators without exporting third-party prose."""
    text = raw.decode("utf-8", errors="strict")
    # Whitespace wrapping may vary. Byte offsets always address the original bytes.
    rows = []
    for code, anchor in CLAUSE_ANCHORS.items():
        pattern = r"\s+".join(re.escape(word) for word in anchor.split())
        matches = list(re.finditer(pattern, text))
        rows.append({
            "topic": code,
            "status": "anchor_observed" if len(matches) == 1 else
                      "anchor_missing" if not matches else "anchor_ambiguous",
            "locators": [{
                "start_byte": len(text[:match.start()].encode("utf-8")),
                "end_byte_exclusive": len(text[:match.end()].encode("utf-8")),
                "start_line": text[:match.start()].count("\n") + 1,
                "end_line": text[:match.end()].count("\n") + 1,
            } for match in matches],
        })
    return rows


def audit_existing_material(case: dict[str, Any], *, result_payload: dict[str, Any],
                            content: bytes | None = None) -> dict[str, Any]:
    """Reconcile a published closure row; optional bytes remain an unverified observation.

    DTO/digest checks establish local consistency, not issuer authenticity. This
    helper is never wired into A's admission path or its Result storage.
    """
    material = Material.model_validate(case["material"]).model_dump(mode="json")
    result = Result.model_validate(result_payload).model_dump(mode="json")
    if result["result_sha256"] != digest({k: v for k, v in result.items() if k != "result_sha256"}):
        raise ValueError("result_digest_mismatch")
    if result["data_scope"] != "TEST_ONLY" or material["data_scope"] != "TEST_ONLY":
        raise ValueError("test_only_required")
    saved = case["results"][-1]
    if any(result[key] != saved[key] for key in ("result_id", "revision", "result_sha256")):
        raise ValueError("existing_result_pin_mismatch")
    if material["binding"] != result["binding"] or result["binding"] != case["binding"]:
        raise ValueError("material_parent_binding_mismatch")
    subject = material["subject"]
    resource = case["resource"]
    if subject != {"resource_id": resource["id"], "version": resource["version"]}:
        raise ValueError("material_subject_mismatch")
    if not isinstance(subject["version"], str) or not _EXACT.fullmatch(subject["version"]):
        raise ValueError("material_version_not_exact")
    if set(result["usage"]) != set(USAGE_FIELDS):
        raise ValueError("usage_fields_incomplete")
    if result["usage"] != case["usage_values"] or result["binding"]["usage_hash"] != case["usage_hash"]:
        raise ValueError("existing_usage_pin_mismatch")
    matches = [row for row in result["resources"] if row["subject"] == subject]
    if len(matches) != 1:
        raise ValueError("material_resource_binding_mismatch")
    row = matches[0]
    if (material["material_id"] not in result["material_ids"]
            or material["material_id"] not in row["material_ids"]
            or not set(material["evidence_ids"]) <= set(row["evidence_ids"])):
        raise ValueError("material_reference_closure_invalid")
    observations = [item for item in case["fixed_tag_observations"] if item["role"] == "license_text"]
    if len(observations) != 1:
        raise ValueError("license_observation_not_unique")
    observation = observations[0]
    if (observation["raw_byte_sha256"] != material["source_sha256"]
            or observation["byte_count"] != material["byte_count"]):
        raise ValueError("existing_observation_hash_mismatch")
    clauses = [{"topic": topic, "status": "bytes_not_re_read", "locators": []}
               for topic in CLAUSE_ANCHORS]
    if content is not None:
        parse_local_material(content, {
            "scan_id": material["binding"]["scan_id"], "object_id": subject["resource_id"],
            "version": subject["version"], "filename": material["filename"],
            "sha256": material["source_sha256"], "source": observation["request_url"],
        }, known_objects={(material["binding"]["scan_id"], subject["resource_id"]): subject["version"]})
        blob = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        if len(content) != material["byte_count"] or blob != observation["git_blob_sha1"]:
            raise ValueError("existing_observation_byte_binding_mismatch")
        clauses = _clause_locations(content)

    gaps = {
        "trusted_source_receipt_missing", "immutable_commit_binding_missing",
        "npm_release_content_relationship_unverified", "owner_delivery_scope_unconfirmed",
        "owner_license_applicability_unconfirmed", "obligation_fulfillment_unverified",
        "full_formal_assessment_readback_missing", "old_formal_report_readback_missing",
    }
    if case["scan_status"] != "completed":
        gaps.add("scan_coverage_incomplete")
    for field in USAGE_FIELDS:
        if result["usage"][field] is None:
            gaps.add(f"usage_{field}_unknown")
    gaps.update(row["gaps"])
    return {
        "kind": "openguard.p2b.offline-material-audit/1",
        "case_id": case["case_id"], "data_scope": "TEST_ONLY", "overall": "PARTIAL",
        "binding": material["binding"], "subject": subject,
        "material_id": material["material_id"], "result_id": result["result_id"],
        "content_sha256": material["source_sha256"], "byte_count": material["byte_count"],
        "source_level": material["source_level"], "verification_state": material["verification_state"],
        "observation_accounting": "existing_unverified_observation_reused",
        "new_facts": 0, "new_evidence_ids": [], "new_positive_license_advice": [],
        "formal_effect": "none", "model_calls": 0,
        "usage": result["usage"], "usage_hash": result["binding"]["usage_hash"],
        "byte_verification": "existing_hashes_rechecked" if content is not None else "metadata_only_not_byte_reverification",
        "clause_mapping": clauses,
        "scope_analysis": {
            "text_mapping_is_applicability_proof": False,
            "covers_npm_archive": "unverified", "covers_dependencies_or_vendor": "unverified",
            "delivery_inclusion": "owner_confirmation_required",
            "obligation_fulfillment": "independent_confirmation_required",
        },
        "remaining_gaps": sorted(gaps),
    }
