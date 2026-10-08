"""Offline, conservative L1 candidate advice over explicitly bound observations.

This module deliberately does not construct a formal Assessment. A must validate
and admit candidate facts against its frozen P2 contract before any publication.
"""
from __future__ import annotations

import re
from typing import Any

MIT_SOURCE = "https://opensource.org/license/mit"
USAGE_FIELDS = ("commercial", "modified", "distributed", "network_service", "training",
                "redistributed_assets", "source_disclosure")
SUPPORTED_USES = ("commercial", "modified", "distributed", "network_service", "redistributed_assets")
EXACT_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def evaluate_candidate(
    *, scan_id: str, object_id: str, object_kind: str, name: str,
    version: str, resource_evidence_ids: list[str], known_evidence: dict[str, dict[str, Any]],
    usage: dict[str, bool | None], scan_status: str = "completed",
    model_status: str = "not_requested",
) -> dict[str, Any]:
    """Return a scoped candidate and concrete gaps; never assert authorization."""
    if not scan_id or not object_id or not name:
        raise ValueError("missing_scan_or_object_identity")
    if object_kind not in {"component", "ai_asset"}:
        raise ValueError("unsupported_object_kind")
    if any(type(value) not in (bool, type(None)) for value in usage.values()):
        raise ValueError("invalid_usage_state")
    if any(key not in USAGE_FIELDS for key in usage):
        raise ValueError("unsupported_usage_field")
    ids = resource_evidence_ids
    if any(not isinstance(i, str) or i not in known_evidence for i in ids) or len(ids) != len(set(ids)):
        raise ValueError("dangling_or_duplicate_evidence")
    evidence = []
    for evidence_id in ids:
        item = known_evidence[evidence_id]
        if not isinstance(item, dict) or item.get("id") != evidence_id:
            raise ValueError("evidence_snapshot_mismatch")
        evidence.append(item)

    gaps: list[str] = []
    if not EXACT_VERSION.fullmatch(version):
        gaps.append("exact_version_missing")
    if scan_status != "completed":
        gaps.append("scan_coverage_incomplete")
    if model_status in {"failed", "fallback"}:
        gaps.append("model_explanation_unavailable")
    if object_kind == "ai_asset":
        gaps.append("ai_asset_independent_license_required")

    bound: list[dict[str, Any]] = []
    for item in evidence:
        if item.get("scan_id") != scan_id or item.get("object_id") != object_id:
            gaps.append("evidence_wrong_object")
        elif item.get("version") != version:
            gaps.append("evidence_wrong_version")
        else:
            bound.append(item)
    texts = [e for e in bound if e.get("role") == "license_text" and e.get("source_status") == "upstream_verified"
             and e.get("verification_status") == "verified" and e.get("license_expression") == "MIT"
             and e.get("applicability") == "human_verified"
             and isinstance(e.get("content_sha256"), str) and SHA256.fullmatch(e["content_sha256"])]
    scopes = [e for e in bound if e.get("role") == "scope_attestation" and e.get("producer") == "human"
              and e.get("verification_status") == "verified" and e.get("scope") in {"project_code", "runtime_dependency"}]
    if not texts:
        gaps.append("license_text_and_applicability_unverified")
    if not scopes:
        gaps.append("object_scope_unverified")
    for key in USAGE_FIELDS:
        if usage.get(key) is None:
            gaps.append(f"usage_{key}_unknown")
    for key in ("training", "source_disclosure"):
        if usage.get(key) is True:
            gaps.append(f"usage_{key}_outside_l1_matrix")

    eligible = bool(object_kind == "component" and EXACT_VERSION.fullmatch(version)
                    and scan_status == "completed" and texts and scopes
                    and "evidence_wrong_object" not in gaps and "evidence_wrong_version" not in gaps
                    and not any(gap.endswith("_outside_l1_matrix") for gap in gaps))
    basis = sorted({e["id"] for e in [*texts, *scopes]}) if eligible else []
    suggestions = []
    if eligible:
        for key in SUPPORTED_USES:
            if usage.get(key) is True:
                suggestions.append({"usage": key, "state": "conditional_candidate",
                                    "conditions": ["保留该对象的版权与许可声明", "人工确认实际履行及适用范围"],
                                    "outstanding_actions": ["核实实际复制或分发的对象范围",
                                                            "核查版权与许可声明是否随适用副本保留",
                                                            "记录人工履行复核结论"],
                                    "basis_evidence_ids": basis, "rule_id": "V4-MIT", "rule_source": MIT_SOURCE})
    return {"kind": "openguard.p2b.l1-candidate/0", "scan_id": scan_id,
            "object_id": object_id, "object_kind": object_kind, "name": name, "version": version,
            "verification_state": "candidate_only", "suggestions": suggestions,
            "basis_evidence_ids": basis, "gaps": sorted(set(gaps))}


def evaluate_bound_candidate(*, snapshot: dict[str, Any], object_id: str,
                             model_status: str = "not_requested") -> dict[str, Any]:
    """Evaluate an A-supplied read-only object snapshot without guessing bindings.

    The caller must authenticate the snapshot and its digest. This B-only function
    checks its internal identity and Evidence closure before producing candidates.
    """
    if not isinstance(snapshot, dict) or not isinstance(object_id, str) or not object_id:
        raise ValueError("invalid_snapshot")
    if model_status not in {"not_requested", "succeeded", "failed", "fallback"}:
        raise ValueError("invalid_model_status")
    scan_id = snapshot.get("scan_id")
    snapshot_sha256 = snapshot.get("snapshot_sha256")
    objects = snapshot.get("objects")
    known_evidence = snapshot.get("evidence")
    if (not isinstance(scan_id, str) or not scan_id or not isinstance(snapshot_sha256, str)
            or not SHA256.fullmatch(snapshot_sha256) or not isinstance(objects, list)
            or not isinstance(known_evidence, dict)):
        raise ValueError("invalid_snapshot")
    coverage_gaps = snapshot.get("coverage_gaps", [])
    if (not isinstance(coverage_gaps, list)
            or any(not isinstance(gap, str) or not gap or len(gap) > 128 for gap in coverage_gaps)
            or len(coverage_gaps) != len(set(coverage_gaps))):
        raise ValueError("invalid_scan_coverage")
    matches = [item for item in objects if isinstance(item, dict) and item.get("id") == object_id]
    if len(matches) != 1:
        raise ValueError("missing_or_duplicate_object")
    subject = matches[0]
    if subject.get("scan_id") != scan_id:
        raise ValueError("snapshot_identity_mismatch")
    version = subject.get("version")
    name = subject.get("name")
    kind = subject.get("kind")
    scope = subject.get("scope")
    if (kind not in {"component", "ai_asset"} or not isinstance(name, str) or not name
            or not isinstance(version, str) or not EXACT_VERSION.fullmatch(version)
            or scope not in {"project_code", "runtime_dependency", "ai_asset"}):
        raise ValueError("snapshot_identity_mismatch")
    if (kind == "ai_asset") != (scope == "ai_asset"):
        raise ValueError("snapshot_scope_mismatch")
    usage = subject.get("usage")
    if (not isinstance(usage, dict) or not isinstance(usage.get("version"), str)
            or not usage["version"].strip() or len(usage["version"]) > 128):
        raise ValueError("usage_version_missing")
    values = usage.get("values")
    if not isinstance(values, dict) or set(values) != set(USAGE_FIELDS):
        raise ValueError("usage_fields_incomplete")
    ids = subject.get("evidence_ids")
    if (not isinstance(ids, list) or any(not isinstance(i, str) or not i for i in ids)
            or len(ids) != len(set(ids)) or any(i not in known_evidence for i in ids)):
        raise ValueError("evidence_closure_invalid")
    object_evidence_ids = {key for key, item in known_evidence.items()
                           if isinstance(item, dict) and item.get("object_id") == object_id}
    if set(ids) != object_evidence_ids:
        raise ValueError("evidence_closure_invalid")
    for evidence_id in ids:
        evidence = known_evidence[evidence_id]
        if (not isinstance(evidence, dict) or evidence.get("id") != evidence_id
                or evidence.get("scan_id") != scan_id or evidence.get("object_id") != object_id
                or evidence.get("version") != version):
            raise ValueError("evidence_binding_invalid")
        source_sha256 = evidence.get("source_sha256")
        if not isinstance(source_sha256, str) or not SHA256.fullmatch(source_sha256):
            raise ValueError("evidence_source_hash_invalid")
    result = evaluate_candidate(
        scan_id=scan_id, object_id=object_id, object_kind=kind, name=name, version=version,
        resource_evidence_ids=ids, known_evidence=known_evidence, usage=values,
        scan_status="partial" if coverage_gaps else snapshot.get("status", "unknown"),
        model_status=model_status,
    )
    scope_basis = [known_evidence[i] for i in result["basis_evidence_ids"]
                   if known_evidence[i].get("role") == "scope_attestation"]
    if result["suggestions"] and not any(item.get("scope") == scope for item in scope_basis):
        result["suggestions"] = []
        result["basis_evidence_ids"] = []
        result["gaps"] = sorted(set([*result["gaps"], "object_scope_unverified"]))
    result["usage_version"] = usage["version"]
    result["snapshot_sha256"] = snapshot_sha256
    result["scan_coverage_gaps"] = sorted(coverage_gaps)
    result["basis_source_sha256"] = {
        evidence_id: known_evidence[evidence_id]["source_sha256"]
        for evidence_id in result["basis_evidence_ids"]
    }
    result["rule_version"] = "V4-MIT"
    return result
