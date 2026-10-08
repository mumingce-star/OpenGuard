"""Bound, small local LICENSE/NOTICE text observations without authorization promotion."""
from __future__ import annotations

import hashlib
import re
from typing import Any

MAX_MATERIAL_BYTES = 64 * 1024
_NAME = re.compile(r"^(?:LICENSE|LICENCE|NOTICE)(?:\.(?:txt|md|rst))?$", re.I)
_SHA = re.compile(r"^[0-9a-f]{64}$")
_EXACT_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")


def parse_local_material(content: bytes, metadata: dict[str, Any],
                         *, known_objects: dict[tuple[str, str], str],
                         known_materials: dict[tuple[str, str, str, str], str] | None = None) -> dict[str, Any]:
    """Accept only object/version-bound bytes; provenance remains a user claim."""
    if not isinstance(metadata, dict) or not isinstance(known_objects, dict):
        raise ValueError("invalid_material_metadata")
    if known_materials is not None and not isinstance(known_materials, dict):
        raise ValueError("invalid_material_history")
    if not isinstance(content, bytes) or not content or len(content) > MAX_MATERIAL_BYTES:
        raise ValueError("material_size_limit")
    filename = metadata.get("filename")
    if not isinstance(filename, str) or not _NAME.fullmatch(filename):
        raise ValueError("unsupported_material_name")
    scan_id, object_id, version = metadata.get("scan_id"), metadata.get("object_id"), metadata.get("version")
    if not isinstance(scan_id, str) or not scan_id or not isinstance(object_id, str) or (scan_id, object_id) not in known_objects:
        raise ValueError("unknown_object")
    if version != known_objects[(scan_id, object_id)]:
        raise ValueError("wrong_object_version")
    if not isinstance(version, str) or not _EXACT_VERSION.fullmatch(version):
        raise ValueError("material_version_not_exact")
    digest = hashlib.sha256(content).hexdigest()
    expected = metadata.get("sha256")
    if not isinstance(expected, str) or not _SHA.fullmatch(expected) or digest != expected:
        raise ValueError("material_hash_mismatch")
    identity = (scan_id, object_id, version, filename.upper())
    if known_materials is not None and identity in known_materials:
        previous = known_materials[identity]
        if not isinstance(previous, str) or not _SHA.fullmatch(previous):
            raise ValueError("invalid_material_history")
        raise ValueError("duplicate_material" if previous == digest else "material_identity_conflict")
    source = metadata.get("source")
    if not isinstance(source, str) or not source.strip() or len(source) > 512:
        raise ValueError("material_source_missing")
    try:
        decoded = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("material_utf8_required") from exc
    if "\x00" in decoded:
        raise ValueError("material_binary_content")
    if not decoded.strip("\ufeff \t\r\n"):
        raise ValueError("material_empty_text")
    return {"kind": "openguard.p2b.local-material/0", "scan_id": scan_id, "object_id": object_id,
            "version": version, "filename": filename, "source_claim": source,
            "content_sha256": digest, "byte_count": len(content), "observation": "text_observed",
            "source_level": "user_supplied_unverified",
            "official_statement": False, "applicability_human_verified": False,
            "authorization_status": "pending", "license_mention": "MIT" if "MIT License" in decoded else None}


def parse_local_material_receipt(content: bytes, metadata: dict[str, Any],
                                 *, known_objects: dict[tuple[str, str], str],
                                 known_materials: dict[tuple[str, str, str, str], str]) -> dict[str, Any]:
    """Return a content-free refusal when a bounded observation is rejected."""
    try:
        return parse_local_material(content, metadata, known_objects=known_objects,
                                    known_materials=known_materials)
    except ValueError as exc:
        return {"kind": "openguard.p2b.local-material/0", "state": "refused",
                "reason": str(exc), "source_level": "user_supplied_unverified",
                "official_statement": False,
                "applicability_human_verified": False, "authorization_status": "pending"}
