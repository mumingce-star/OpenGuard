"""Controlled NOTICE observation collector using only a live read-session capability."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from app.ingestion import ReadOnlyScanSession
from app.security.errors import IngestionSecurityError

from .models import (MAX_EXCERPT_BYTES, MAX_FULL_BYTES, MAX_ITEMS, Content, Coverage,
                     NoticeObservation, NoticeSourceCollection, Producer, Relation)


@dataclass(frozen=True)
class NoticeSourceCandidate:
    """A caller-selected path and conservative resource relation; never a P0 ID."""
    observation_key: str
    locator: str
    relation_state: str = "unresolved"
    subject: str | None = None
    basis: str = "no_unique_resource_binding"


def _excerpt_at_boundary(data: bytes) -> bytes:
    """Return a <=4 KiB valid UTF-8 prefix without replacement or normalization."""
    bounded = data[:MAX_EXCERPT_BYTES]
    while bounded:
        try:
            bounded.decode("utf-8", "strict")
            return bounded
        except UnicodeDecodeError as error:
            bounded = bounded[:error.start]
    raise UnicodeDecodeError("utf-8", data, 0, 1, "no complete character at excerpt boundary")


def collect_notice_source_package(
    session: ReadOnlyScanSession,
    *,
    observed_at: datetime,
    candidates: tuple[NoticeSourceCandidate, ...],
    collector: Producer,
) -> NoticeSourceCollection:
    """Collect candidate NOTICE bytes without widening read quotas or inventing bindings.

    Oversize/non-inventory/budget-exhausted inputs are explicit `not_scanned` gaps.
    A session I/O/integrity failure is represented once as `read_failed`; remaining
    candidates are not attempted because the capability has failed closed.
    """
    if (type(candidates) is not tuple or not candidates or len(candidates) > MAX_ITEMS
            or observed_at.tzinfo is None or observed_at.utcoffset() != timezone.utc.utcoffset(observed_at)):
        raise ValueError("notice_source_arguments_invalid")
    keys = [item.observation_key for item in candidates]
    if len(keys) != len(set(keys)):
        raise ValueError("observation_key_duplicate")
    inventory = {item.relative_path: item for item in session.inventory.entries}
    observations: list[NoticeObservation] = []
    omissions: list[str] = []
    gaps: list[str] = []
    session_failed = False
    for candidate in candidates:
        relation = Relation(state=candidate.relation_state, subject=candidate.subject, basis=candidate.basis)
        entry = inventory.get(candidate.locator)
        gap: str | None = None
        state = "not_scanned"
        if session_failed:
            gap = "prior_read_failed"
        elif entry is None:
            gap = "path_not_in_inventory"
        elif entry.size_bytes > session.remaining_read_bytes:
            gap = "read_budget_exhausted"
        elif entry.size_bytes > 4 * 1024 * 1024:
            gap = "single_file_limit_exceeded"
        else:
            try:
                data = session.read_bytes(candidate.locator, max_bytes=4 * 1024 * 1024)
                if hashlib.sha256(data).hexdigest() != entry.sha256 or len(data) != entry.size_bytes:
                    raise ValueError("inventory_bytes_mismatch")
                try:
                    text = data.decode("utf-8", "strict")
                except UnicodeDecodeError:
                    gap = "utf8_decode_failed"
                    state = "not_scanned"
                else:
                    whole = hashlib.sha256(data).hexdigest()
                    retained = data if len(data) <= MAX_FULL_BYTES else _excerpt_at_boundary(data)
                    content_state = "full" if len(data) <= MAX_FULL_BYTES else "excerpt"
                    observations.append(NoticeObservation(
                        observation_key=candidate.observation_key, locator=candidate.locator,
                        content=Content(state=content_state, text=retained.decode("utf-8", "strict"), encoding="utf-8",
                        byte_range=[0, len(retained)], truncated=content_state == "excerpt",
                        retained_bytes_sha256=hashlib.sha256(retained).hexdigest(), whole_bytes_sha256=whole,
                        gap_codes=[]), collector=collector, relation=relation))
                    continue
            except (IngestionSecurityError, ValueError):
                session_failed = True
                state = "read_failed"
                gap = "read_failed"
        assert gap is not None
        omissions.append(candidate.locator)
        gaps.append(gap)
        observations.append(NoticeObservation(observation_key=candidate.observation_key, locator=candidate.locator,
            content=Content(state=state, gap_codes=[gap]), collector=collector, relation=relation))
    coverage = Coverage(state="partial" if omissions else "completed", omissions=omissions, gap_codes=sorted(set(gaps)))
    payload = {"schema_version": "openguard.notice-source/1", "observed_at": observed_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
               "coverage": coverage.model_dump(mode="json"),
               "observations": [item.model_dump(mode="json") for item in observations]}
    return NoticeSourceCollection.model_validate(payload)
