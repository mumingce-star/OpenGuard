"""Read-only before/after accounting for one A-bound scan object."""
from __future__ import annotations

import re
from typing import Any

from .candidates import evaluate_bound_candidate

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _digest(value: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError("invalid_readback_hash")
    return value


def _object(snapshot: dict[str, Any], object_id: str) -> dict[str, Any]:
    matches = [item for item in snapshot["objects"] if isinstance(item, dict) and item.get("id") == object_id]
    if len(matches) != 1:
        raise ValueError("missing_or_duplicate_object")
    return matches[0]


def _unaffected_objects(snapshot: dict[str, Any], object_id: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in snapshot["objects"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            raise ValueError("invalid_snapshot_object")
        if item["id"] == object_id:
            continue
        if item["id"] in result:
            raise ValueError("duplicate_unaffected_object")
        result[item["id"]] = item
    return result


def _unaffected_evidence(snapshot: dict[str, Any], object_id: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for key, value in snapshot["evidence"].items():
        if not isinstance(value, dict):
            raise ValueError("invalid_snapshot_evidence")
        if value.get("object_id") != object_id:
            result[key] = value
    return result


def reconcile_object(*, before: dict[str, Any], after: dict[str, Any], object_id: str,
                     old_assessment_id: str, old_report_id: str,
                     old_assessment_sha256: str, old_assessment_readback_sha256: str,
                     old_report_sha256: str, old_report_readback_sha256: str) -> dict[str, Any]:
    """Compare immutable A snapshots and require old artifact readback equality.

    This does not persist, admit or regenerate a formal Assessment or report.
    """
    if (not isinstance(old_assessment_id, str) or not old_assessment_id
            or not isinstance(old_report_id, str) or not old_report_id):
        raise ValueError("invalid_artifact_identity")
    old_assessment_sha256 = _digest(old_assessment_sha256)
    old_report_sha256 = _digest(old_report_sha256)
    if (_digest(old_assessment_readback_sha256) != old_assessment_sha256
            or _digest(old_report_readback_sha256) != old_report_sha256):
        raise ValueError("old_artifact_changed")
    before_candidate = evaluate_bound_candidate(snapshot=before, object_id=object_id)
    after_candidate = evaluate_bound_candidate(snapshot=after, object_id=object_id)
    if before["scan_id"] != after["scan_id"]:
        raise ValueError("different_scan")
    before_object, after_object = _object(before, object_id), _object(after, object_id)
    for field in ("kind", "name", "version", "scope"):
        if before_object[field] != after_object[field]:
            raise ValueError("object_identity_changed")
    before_others = _unaffected_objects(before, object_id)
    after_others = _unaffected_objects(after, object_id)
    if before_others != after_others:
        raise ValueError("unaffected_object_changed")
    before_other_evidence = _unaffected_evidence(before, object_id)
    after_other_evidence = _unaffected_evidence(after, object_id)
    if before_other_evidence != after_other_evidence:
        raise ValueError("unaffected_evidence_changed")
    before_ids = set(before_object["evidence_ids"])
    after_ids = set(after_object["evidence_ids"])
    if not before_ids <= after_ids:
        raise ValueError("prior_evidence_removed")
    for evidence_id in before_ids:
        if before["evidence"][evidence_id] != after["evidence"].get(evidence_id):
            raise ValueError("prior_evidence_changed")
    added = sorted(after_ids - before_ids)
    before_uses = {item["usage"] for item in before_candidate["suggestions"]}
    after_uses = {item["usage"] for item in after_candidate["suggestions"]}
    before_gaps = set(before_candidate["gaps"])
    after_gaps = set(after_candidate["gaps"])
    return {
        "kind": "openguard.p2b.d4-accounting/0",
        "scan_id": before["scan_id"], "object_id": object_id,
        "version": after_object["version"],
        "before_usage_version": before_object["usage"]["version"],
        "after_usage_version": after_object["usage"]["version"],
        "before_snapshot_sha256": before["snapshot_sha256"],
        "after_snapshot_sha256": after["snapshot_sha256"],
        "added_evidence": [
            {"id": evidence_id, "source_sha256": after["evidence"][evidence_id]["source_sha256"],
             "content_sha256": after["evidence"][evidence_id].get("content_sha256")}
            for evidence_id in added
        ],
        "unchanged_evidence_ids": sorted(before_ids),
        "suggestions_added": sorted(after_uses - before_uses),
        "suggestions_removed": sorted(before_uses - after_uses),
        "gaps_resolved": sorted(before_gaps - after_gaps),
        "gaps_added": sorted(after_gaps - before_gaps),
        "remaining_gaps": sorted(after_gaps),
        "old_assessment_sha256": old_assessment_sha256,
        "old_assessment_id": old_assessment_id,
        "old_report_sha256": old_report_sha256,
        "old_report_id": old_report_id,
        "old_artifacts_unchanged": True,
        "unaffected_objects_unchanged": True,
        "status": "candidate_accounting_only",
    }
