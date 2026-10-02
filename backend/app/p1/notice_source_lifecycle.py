"""Opt-in NOTICE sidecar; no facts mutation, retry, GET hooks or legal inference."""
from __future__ import annotations

import hashlib

from app.ingestion import ScanReadLimits
from app.ingestion.notice_ingestion import CollectedNotice
from app.notice_source import select_notice_source_candidates, collect_notice_source_package
from app.notice_source.models import (Producer, NoticeSourceCollection, canonical_json,
    MAX_ITEMS, MAX_FULL_BYTES, MAX_EXCERPT_BYTES, MAX_ITEM_JSON_BYTES, MAX_PACKAGE_BYTES)
from app.assessment.engine import facts_digest
from app.assessment.models import Assessment
from .notice_source_adapter import NoticeSourceAdapter
from .notice_source_store import NoticeSourceBindingService, StagedNoticeSourceReader


def producer_configuration(limits: ScanReadLimits) -> dict:
    if (type(limits) is not ScanReadLimits or type(limits.single_file_max_bytes) is not int
            or type(limits.total_max_bytes) is not int or not 0 < limits.single_file_max_bytes <= limits.total_max_bytes):
        raise ValueError("notice_effective_read_limits_invalid")
    return {
        "collector": {"schema_version": "openguard.notice-source/1", "type": "collector",
            "name": "openguard-notice-source-collector", "version": "1.0.0"},
        "selector": {"strategy": "CZ-S1", "sort": "relative_path_utf8_ascending",
            "basenames": ["copying", "licence", "license", "notice"], "extensions": ["", ".md", ".txt"],
            "max_items": MAX_ITEMS, "relation_state": "unresolved", "relation_basis": "inventory_path_candidate_only"},
        "session": {"single_file_max_bytes": limits.single_file_max_bytes, "total_max_bytes": limits.total_max_bytes},
        "retention": {"max_full_bytes": MAX_FULL_BYTES, "max_excerpt_bytes": MAX_EXCERPT_BYTES,
            "max_item_json_bytes": MAX_ITEM_JSON_BYTES, "max_package_bytes": MAX_PACKAGE_BYTES},
        "content": {"encoding": "utf-8-strict", "normalization": "none"},
        "coverage": {"source": "trusted_inventory_selected_candidates", "zero_candidates": "no_collection",
            "truncated": "reject_before_collection"},
    }


class NoticeSourceLifecycle:
    def __init__(self, registry, assessment_store, source_store, *, diagnostic=None):
        if diagnostic is not None and not callable(diagnostic):
            raise ValueError("notice_diagnostic_invalid")
        self.registry = registry
        self.adapter = NoticeSourceAdapter(registry, assessment_store)
        self.source_store = source_store
        self.binding = NoticeSourceBindingService(source_store, registry, assessment_store)
        self.staged_reader = StagedNoticeSourceReader(source_store)
        self.diagnostic = diagnostic

    def _diagnose(self, code):
        # Only fixed, non-authoritative internal codes. Never include an exception,
        # filename, scan facts, content or a synthetic coverage observation.
        if self.diagnostic is not None:
            try: self.diagnostic(code)
            except Exception: pass

    @staticmethod
    def producer_for(limits: ScanReadLimits) -> Producer:
        config = producer_configuration(limits)
        return Producer(type="collector", name=config["collector"]["name"], version=config["collector"]["version"],
            config_digest=hashlib.sha256(canonical_json(config)).hexdigest())

    def collect(self, session, limits: ScanReadLimits) -> CollectedNotice:
        producer = self.producer_for(limits)
        selection = select_notice_source_candidates(session.inventory)
        if not selection.candidates:
            self._diagnose("NO_NOTICE_CANDIDATES_SELECTED")
            return CollectedNotice(None, producer, selection)
        if selection.truncated:
            self._diagnose("NOTICE_SELECTOR_TRUNCATED")
            return CollectedNotice(None, producer, selection)
        # CZ v1's read call is fixed at 4 MiB. Do not widen a narrower session or
        # create a sticky safety failure merely to collect optional observations.
        if limits.single_file_max_bytes < 4 * 1024 * 1024:
            self._diagnose("NOTICE_READ_POLICY_UNSUPPORTED")
            return CollectedNotice(None, producer, selection)
        try:
            from datetime import datetime, timezone
            collection = collect_notice_source_package(session, observed_at=datetime.now(timezone.utc),
                candidates=selection.candidates, collector=producer)
            collection = NoticeSourceCollection.model_validate(collection.model_dump(mode="json"))
            if any(item.collector != producer for item in collection.observations):
                raise ValueError("notice_producer_mismatch")
            return CollectedNotice(collection, producer, selection)
        except Exception:
            self._diagnose("NOTICE_COLLECTION_UNAVAILABLE")
            # Ingestion's own latch/final checks still govern shared safety.
            return CollectedNotice(None, producer, selection)

    def on_terminal(self, completed, stored):
        if completed is None or stored.run.status.value not in {"completed", "partial"}:
            return
        try:
            if completed.result.consumer_result.collection is None:
                return
            value = self.adapter.admit_terminal_ingestion(completed, scan_id=stored.run.id,
                expected_registry_revision=stored.revision)
            self.source_store.stage(value)
        except Exception:
            self._diagnose("NOTICE_TERMINAL_ADMISSION_UNAVAILABLE")

    def on_assessment_saved(self, saved: Assessment):
        # Callback is installed only on the explicit successful-save boundary,
        # never on startup/list/GET or a pre-save candidate.
        try:
            if type(saved) is not Assessment or saved.formal is not True:
                return
            staged = self.staged_reader.read(saved.scan_id)
            if staged is None:
                return
            current = self.registry.get(saved.scan_id)
            if current.run.status.value not in {"completed", "partial"} or facts_digest(current.run) != saved.facts_hash:
                return
            self.binding.bind(scan_id=saved.scan_id, expected_registry_revision=current.revision,
                assessment_id=saved.id, expected_assessment_version=saved.version,
                expected_package_hash=staged.package_hash)
        except Exception:
            self._diagnose("NOTICE_ASSESSMENT_BIND_UNAVAILABLE")
