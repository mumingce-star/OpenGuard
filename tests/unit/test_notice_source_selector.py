"""Production-candidate selection stays metadata-only and conservative."""

import hashlib
from datetime import datetime, timezone

import pytest

from app.ingestion.inventory import Inventory, InventoryEntry
from app.notice_source import (
    MAX_ITEMS,
    SelectorResult,
    select_notice_source_candidates,
)
from app.notice_source.collector import collect_notice_source_package
from app.notice_source.models import Producer


def inventory(*paths: str) -> Inventory:
    entries = tuple(
        InventoryEntry(path, len(path), hashlib.sha256(path.encode("utf-8")).hexdigest())
        for path in paths
    )
    return Inventory(entries=entries, root_digest="0" * 64)


def test_selects_root_nested_and_allowed_case_insensitive_notice_families():
    result = select_notice_source_candidates(inventory(
        "README.md", "NOTICE", "LICENSE.md", "vendor/LICENCE.txt", "third_party/COPYING",
        "src/license.py", "NOTICE.rst",
    ))
    assert isinstance(result, SelectorResult)
    assert [item.locator for item in result.candidates] == [
        "LICENSE.md", "NOTICE", "third_party/COPYING", "vendor/LICENCE.txt",
    ]
    assert all(item.relation_state == "unresolved" and item.subject is None for item in result.candidates)
    assert {item.basis for item in result.candidates} == {"inventory_path_candidate_only"}
    assert result.truncated is False and result.omitted_count == 0


def test_result_is_stable_exact_and_safe_for_collector():
    source = inventory("第三方/NOTICE.TXT", "NOTICE", "README")
    reversed_source = Inventory(tuple(reversed(source.entries)), source.root_digest)
    left = select_notice_source_candidates(source)
    right = select_notice_source_candidates(reversed_source)
    assert left == right
    assert left.candidates[1].locator == "第三方/NOTICE.TXT"
    assert all(item.observation_key.startswith("notice-source-candidate:") for item in left.candidates)

    class Session:
        inventory = source
        remaining_read_bytes = 1024

        def read_bytes(self, path: str, *, max_bytes: int) -> bytes:
            return path.encode("utf-8")

    package = collect_notice_source_package(
        Session(), observed_at=datetime(2026, 9, 29, tzinfo=timezone.utc), candidates=left.candidates,
        collector=Producer(type="collector", name="test", version="1"),
    )
    assert tuple(item.locator for item in package.observations) == tuple(item.locator for item in left.candidates)


def test_zero_candidates_and_invalid_inventory_are_distinguished():
    assert select_notice_source_candidates(inventory("README.md", "src/main.py")).candidates == ()
    with pytest.raises(ValueError, match="notice_source_inventory_invalid"):
        select_notice_source_candidates(object())  # type: ignore[arg-type]


def test_capacity_is_explicit_and_not_silent():
    paths = tuple(f"third_party/{index:04d}/NOTICE" for index in range(MAX_ITEMS + 1))
    result = select_notice_source_candidates(inventory(*paths))
    assert len(result.candidates) == MAX_ITEMS
    assert result.truncated is True
    assert result.omitted_count == 1
    assert [item.locator for item in result.candidates] == sorted(paths, key=lambda item: item.encode("utf-8"))[:MAX_ITEMS]
