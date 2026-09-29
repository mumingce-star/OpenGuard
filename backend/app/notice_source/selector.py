"""Pure, metadata-only selection of potential NOTICE source files."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid5

from app.ingestion.inventory import Inventory, InventoryEntry

from .collector import NoticeSourceCandidate
from .models import MAX_ITEMS


_OBSERVATION_NAMESPACE = UUID("a669e60d-3d93-58f5-9e41-427b4b5899cb")
_BASENAMES = frozenset({"notice", "license", "licence", "copying"})
_EXTENSIONS = frozenset({"", ".txt", ".md"})
_BASIS = "inventory_path_candidate_only"


@dataclass(frozen=True)
class SelectorResult:
    """Candidates plus explicit capacity loss; never a legal/compliance conclusion."""

    candidates: tuple[NoticeSourceCandidate, ...]
    truncated: bool
    omitted_count: int


def select_notice_source_candidates(inventory: Inventory) -> SelectorResult:
    """Select an ordered, conservative subset using Inventory metadata only.

    This function performs no file, workspace, network, Git, scanner, session, AI,
    Registry, or Assessment access.  A capacity signal means only that candidate
    coverage was limited; it does not characterize omitted files.
    """
    _validate_inventory(inventory)
    selected = sorted(
        (entry for entry in inventory.entries if _is_candidate_path(entry.relative_path)),
        key=lambda entry: entry.relative_path.encode("utf-8"),
    )
    omitted_count = max(0, len(selected) - MAX_ITEMS)
    candidates = tuple(
        NoticeSourceCandidate(
            observation_key=f"notice-source-candidate:{uuid5(_OBSERVATION_NAMESPACE, entry.relative_path)}",
            locator=entry.relative_path,
            relation_state="unresolved",
            subject=None,
            basis=_BASIS,
        )
        for entry in selected[:MAX_ITEMS]
    )
    return SelectorResult(candidates=candidates, truncated=bool(omitted_count), omitted_count=omitted_count)


def _is_candidate_path(relative_path: str) -> bool:
    basename = relative_path.rsplit("/", 1)[-1]
    folded = basename.casefold()
    for stem in _BASENAMES:
        if folded == stem:
            return True
        for extension in _EXTENSIONS - {""}:
            if folded == f"{stem}{extension}":
                return True
    return False


def _validate_inventory(inventory: Inventory) -> None:
    if not isinstance(inventory, Inventory) or type(inventory.entries) is not tuple:
        raise ValueError("notice_source_inventory_invalid")
    paths: set[str] = set()
    for entry in inventory.entries:
        if not isinstance(entry, InventoryEntry) or not entry.relative_path or entry.relative_path in paths:
            raise ValueError("notice_source_inventory_invalid")
        paths.add(entry.relative_path)
