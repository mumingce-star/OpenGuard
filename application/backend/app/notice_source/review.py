"""Independent, read-only review projection for NOTICE source facts.

This module intentionally reports only what a validated source package says:
coverage, retained byte evidence, and caller-supplied relation state.  It does
not interpret licenses, rights, obligations, or a final NOTICE document.
"""

from __future__ import annotations

from typing import Any

from .models import NoticeSourcePackage, validate_notice_source_package


def review_notice_source_package(value: NoticeSourcePackage | object) -> dict[str, Any]:
    """Return a JSON-compatible factual review of one hash-validated package."""
    package = value if isinstance(value, NoticeSourcePackage) else validate_notice_source_package(value)
    observations = package.observations
    retained = [item for item in observations if item.content.state in {"full", "excerpt"}]
    unresolved = [item for item in observations if item.relation.state == "unresolved"]
    unparsed = [item for item in observations if item.content.state not in {"full", "excerpt"}]
    return {
        "schema_version": "openguard.notice-source-review/1",
        "source_package_hash": package.package_hash,
        "coverage": {
            "state": package.coverage.state,
            "observed_count": len(observations),
            "retained_count": len(retained),
            "omitted_count": len(package.coverage.omissions),
            "omissions": list(package.coverage.omissions),
            "gap_codes": list(package.coverage.gap_codes),
        },
        "relations": {
            "resolved": [item.observation_key for item in observations if item.relation.state == "resolved"],
            "unresolved": [item.observation_key for item in unresolved],
        },
        "unparsed": [
            {
                "observation_key": item.observation_key,
                "locator": item.locator,
                "state": item.content.state,
                "reasons": list(item.content.gap_codes),
            }
            for item in unparsed
        ],
        "retained_hashes": [
            {
                "observation_key": item.observation_key,
                "state": item.content.state,
                "retained_bytes_sha256": item.content.retained_bytes_sha256,
                "whole_bytes_sha256": item.content.whole_bytes_sha256,
                "excerpt_bytes_sha256": item.content.excerpt_bytes_sha256,
            }
            for item in retained
        ],
    }
