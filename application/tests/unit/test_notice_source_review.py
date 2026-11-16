import hashlib
import json
from pathlib import Path

import pytest

from app.notice_source import (bind_notice_source_collection, review_notice_source_package,
                               validate_notice_source_package)
from app.notice_source.models import Binding, Content


FIXTURE = Path("tests/fixtures/notice-source-v1/public-collection.json")


def _binding():
    return Binding(scan_id="fixture-scan", registry_revision="7", input_digest="1" * 64,
                   inventory_digest="2" * 64, facts_hash="3" * 64)


def test_public_fixture_is_hash_bound_and_reports_only_source_facts():
    collection = json.loads(FIXTURE.read_text(encoding="utf-8"))
    package = bind_notice_source_collection(collection, binding=_binding())
    reviewed = review_notice_source_package(package.model_dump(mode="json"))
    assert reviewed["coverage"] == {
        "state": "partial", "observed_count": 5, "retained_count": 4,
        "omitted_count": 1, "omissions": ["MISSING-NOTICE"],
        "gap_codes": ["path_not_in_inventory"],
    }
    assert reviewed["relations"] == {"resolved": ["dependency-notice"],
                                      "unresolved": ["root-notice", "empty-notice", "duplicate-notice", "missing-notice"]}
    assert reviewed["unparsed"] == [{"observation_key": "missing-notice", "locator": "MISSING-NOTICE",
                                      "state": "not_scanned", "reasons": ["path_not_in_inventory"]}]
    hashes = {item["observation_key"]: item for item in reviewed["retained_hashes"]}
    assert hashes["empty-notice"]["retained_bytes_sha256"] == hashlib.sha256(b"").hexdigest()
    assert hashes["dependency-notice"]["excerpt_bytes_sha256"] == hashes["dependency-notice"]["retained_bytes_sha256"]
    assert "obligation" not in json.dumps(reviewed).lower()


def test_excerpt_hash_cannot_diverge_from_retained_hash_and_full_content_has_no_excerpt_hash():
    excerpt = "short excerpt"
    digest = hashlib.sha256(excerpt.encode()).hexdigest()
    with pytest.raises(Exception, match="excerpt_content_invalid"):
        Content(state="excerpt", text=excerpt, encoding="utf-8", byte_range=[0, len(excerpt)], truncated=True,
                retained_bytes_sha256=digest, excerpt_bytes_sha256="0" * 64, whole_bytes_sha256="1" * 64)
    with pytest.raises(Exception, match="full_content_invalid"):
        Content(state="full", text=excerpt, encoding="utf-8", byte_range=[0, len(excerpt)], truncated=False,
                retained_bytes_sha256=digest, excerpt_bytes_sha256=digest, whole_bytes_sha256=digest)


def test_review_rejects_package_hash_tampering_before_projecting_facts():
    collection = json.loads(FIXTURE.read_text(encoding="utf-8"))
    package = bind_notice_source_collection(collection, binding=_binding()).model_dump(mode="json")
    package["package_hash"] = "0" * 64
    with pytest.raises(Exception):
        validate_notice_source_package(package)
    with pytest.raises(Exception):
        review_notice_source_package(package)
