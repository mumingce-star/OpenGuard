"""Internal CZ v1 / A1 boundary; no persistence, pipeline or factory wiring.

A trusted caller retains the collection from its own controlled scan session.
Hash consistency alone is NOT proof of that provenance. Admission is followed
by public A1 stage() and BindingService.bind(); only that service publishes BOUND.

Carry the admitted value's package_hash (not a later Store lookup) through:
stage(value); bind(..., expected_package_hash=value.package_hash).
Recovery is an explicit trusted caller action, never catch-conflict/overwrite:
store.replace_unbound_stage(new, scan_id=new.scan_id,
                           expected_current_package_hash=old.package_hash)
then bind(..., expected_package_hash=new.package_hash). This adapter remains
read-only; any existing BOUND prohibits replacement, including for other
assessment versions. No automatic retry or replacement policy is installed.
"""
from __future__ import annotations

import hashlib
import json

from app.assessment.engine import facts_digest
from app.assessment.store import AssessmentStore, AssessmentStoreError
from app.ingestion import GitScanSessionResult, ScanSessionResult
from app.ingestion.inventory import Inventory, InventoryEntry, root_digest_v1
from app.notice_source import (
    NoticeSourceCollection, NoticeSourcePackage, bind_notice_source_collection,
    validate_notice_source_package, select_notice_source_candidates,
)
from app.notice_source.models import Binding, MAX_PACKAGE_BYTES, canonical_json
from app.persistence import SQLiteScanRunRegistry, ScanRegistryError
from .notice_source_store import (
    BoundNoticeSource, NoticeSourceStoreError, ValidatedNoticeSourceInput,
)


def _positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def _check_binding(package: NoticeSourcePackage, expected: Binding) -> None:
    value = package.binding.registry_revision
    if (not value.isascii() or not value.isdecimal() or str(int(value)) != value
            or package.binding != expected):
        raise NoticeSourceStoreError("binding_mismatch")


def _metadata(package: NoticeSourcePackage) -> tuple[bytes, str, str]:
    # Include type/config_digest in equality even though A1 has no separate fields.
    collectors = [canonical_json(o.collector.model_dump(mode="json")) for o in package.observations]
    if not collectors or any(c != collectors[0] for c in collectors):
        raise NoticeSourceStoreError("invalid_argument")
    raw = canonical_json(package.model_dump(mode="json", exclude={"package_hash"}))
    if hashlib.sha256(raw).hexdigest() != package.package_hash:
        raise NoticeSourceStoreError("invalid_argument")
    collector = package.observations[0].collector
    return raw, collector.name, collector.version


class NoticeSourceAdapter:
    """Read authoritative terminal facts, without selecting a latest assessment."""

    def __init__(self, scan_registry: SQLiteScanRunRegistry, assessment_store: AssessmentStore):
        self.scan_registry = scan_registry
        self.assessment_store = assessment_store

    def admit_terminal(self, collection: NoticeSourceCollection, *, scan_id: str,
                       expected_registry_revision: int,
                       ingestion_result: ScanSessionResult[NoticeSourceCollection],
                       source_input: bytes | str) -> ValidatedNoticeSourceInput:
        """Read-only terminal admission, deliberately independent of Assessment.

        The trusted internal caller must retain the SUCCESSFUL result returned by
        its controlled ingestion and its original immutable ZIP bytes / Git URL.
        Do not pass a provisional callback result after ingestion failed. DTOs
        and hashes are cross-checks, not authentication of arbitrary Python code.
        No public admission API, automatic stage/bind or lifecycle hook exists.

        Pass this result's package_hash to the later explicit trusted bind; a
        STAGED metadata read is only a point-in-time CAS expectation, not latest.
        Selector truncation still requires a separate future coverage contract.
        """
        if (type(scan_id) is not str or not scan_id
                or not _positive_int(expected_registry_revision)
                or not isinstance(collection, NoticeSourceCollection)
                or not isinstance(ingestion_result, ScanSessionResult)):
            raise NoticeSourceStoreError("invalid_argument")
        try:
            stored = self.scan_registry.get(scan_id)
            if stored is None:
                raise NoticeSourceStoreError("not_found")
            run = stored.run
            if run.status.value not in ("completed", "partial"):
                raise NoticeSourceStoreError("not_ready")
            if (run.id != scan_id or not _positive_int(stored.revision)
                    or stored.revision != expected_registry_revision
                    or run.provenance.inventory_digest is None
                    or ingestion_result.consumer_result is not collection):
                raise NoticeSourceStoreError("binding_mismatch")
            inventory = ingestion_result.inventory
            if (not isinstance(inventory, Inventory) or type(inventory.entries) is not tuple
                    or any(not isinstance(e, InventoryEntry)
                           or type(e.relative_path) is not str or not e.relative_path
                           or type(e.size_bytes) is not int or e.size_bytes < 0
                           or type(e.sha256) is not str for e in inventory.entries)):
                raise NoticeSourceStoreError("invalid_argument")
            entries = {e.relative_path: e for e in inventory.entries}
            if (len(entries) != len(inventory.entries)
                    or root_digest_v1(inventory.entries) != inventory.root_digest
                    or inventory.root_digest != run.provenance.inventory_digest.value):
                raise NoticeSourceStoreError("binding_mismatch")
            # Do not turn a collector's completed subset into complete selection
            # coverage. Until the future truncation contract is frozen, refuse
            # terminal admission rather than invent omissions or alter payloads.
            if select_notice_source_candidates(inventory).truncated:
                raise NoticeSourceStoreError("not_ready")
            if run.project.source_type == "zip":
                if type(source_input) is not bytes or isinstance(ingestion_result, GitScanSessionResult):
                    raise NoticeSourceStoreError("invalid_argument")
                input_hash = hashlib.sha256(source_input).hexdigest()
            elif run.project.source_type == "git":
                if type(source_input) is not str or not isinstance(ingestion_result, GitScanSessionResult):
                    raise NoticeSourceStoreError("invalid_argument")
                if source_input != run.project.source or ingestion_result.revision != run.project.revision:
                    raise NoticeSourceStoreError("binding_mismatch")
                input_hash = hashlib.sha256(source_input.encode("utf-8")).hexdigest()
            else:
                raise NoticeSourceStoreError("invalid_argument")
            if input_hash != run.provenance.input_digest.value:
                raise NoticeSourceStoreError("binding_mismatch")
            # Revalidate typed DTOs before using any content or producer fields.
            source = NoticeSourceCollection.model_validate(collection.model_dump(mode="json"))
            for observation in source.observations:
                entry = entries.get(observation.locator)
                content = observation.content
                if (entry is None or (content.state in ("full", "excerpt")
                        and (content.whole_bytes_sha256 != entry.sha256
                             or content.byte_range[1] > entry.size_bytes
                             or (content.state == "full" and content.byte_range[1] != entry.size_bytes)))):
                    raise NoticeSourceStoreError("binding_mismatch")
            actual = Binding(scan_id=run.id, registry_revision=str(stored.revision),
                             input_digest=input_hash, inventory_digest=inventory.root_digest,
                             facts_hash=facts_digest(run))
            terminal = bind_notice_source_collection(source, binding=actual)
            package = validate_notice_source_package(terminal.model_dump(mode="json"))
            _check_binding(package, actual)
            raw, producer, version = _metadata(package)
            return ValidatedNoticeSourceInput(
                scan_id=run.id, canonical_package_bytes=raw, package_hash=package.package_hash,
                collector_schema_version=package.schema_version, producer=producer,
                producer_version=version, observed_input_digest=actual.input_digest,
                observed_inventory_digest=actual.inventory_digest,
                coverage_status=package.coverage.state,
                omissions=list(package.coverage.omissions), gap_codes=list(package.coverage.gap_codes))
        except ScanRegistryError as error:
            code = {"registry_not_found": "not_found",
                    "registry_invalid_argument": "invalid_argument"}.get(error.code, "storage_unavailable")
            raise NoticeSourceStoreError(code) from error
        except OSError as error:
            raise NoticeSourceStoreError("storage_unavailable") from error
        except (ValueError, TypeError, RecursionError) as error:
            raise NoticeSourceStoreError("invalid_argument") from error

    def admit(self, collection: NoticeSourceCollection, *, scan_id: str,
              expected_registry_revision: int, assessment_id: str,
              expected_assessment_version: int) -> ValidatedNoticeSourceInput:
        if (type(scan_id) is not str or not scan_id or type(assessment_id) is not str or not assessment_id
                or not _positive_int(expected_registry_revision)
                or not _positive_int(expected_assessment_version)
                or not isinstance(collection, NoticeSourceCollection)):
            raise NoticeSourceStoreError("invalid_argument")
        try:
            stored = self.scan_registry.get(scan_id)
            if stored is None:
                raise NoticeSourceStoreError("not_found")
            run = stored.run
            if run.status.value not in ("completed", "partial"):
                raise NoticeSourceStoreError("not_ready")
            if (run.id != scan_id or not _positive_int(stored.revision)
                    or stored.revision != expected_registry_revision
                    or run.provenance.inventory_digest is None):
                raise NoticeSourceStoreError("binding_mismatch")
            facts_hash = facts_digest(run)
            assessment = self.assessment_store.get(scan_id, assessment_id)
            if (assessment is None or assessment.id != assessment_id
                    or not _positive_int(assessment.version)
                    or assessment.version != expected_assessment_version
                    or assessment.scan_id != scan_id or assessment.formal is not True
                    or assessment.facts_hash != facts_hash):
                raise NoticeSourceStoreError("binding_mismatch")
            actual = Binding(scan_id=run.id, registry_revision=str(stored.revision),
                             input_digest=run.provenance.input_digest.value,
                             inventory_digest=run.provenance.inventory_digest.value,
                             facts_hash=facts_hash)
            # Revalidate even an in-process DTO: model_copy/construct bypass validation.
            source = NoticeSourceCollection.model_validate(collection.model_dump(mode="json"))
            terminal = bind_notice_source_collection(source, binding=actual)
            package = validate_notice_source_package(terminal.model_dump(mode="json"))
            _check_binding(package, actual)
            raw, producer, version = _metadata(package)
            return ValidatedNoticeSourceInput(
                scan_id=run.id, canonical_package_bytes=raw, package_hash=package.package_hash,
                collector_schema_version=package.schema_version, producer=producer,
                producer_version=version, observed_input_digest=actual.input_digest,
                observed_inventory_digest=actual.inventory_digest,
                coverage_status=package.coverage.state,
                omissions=list(package.coverage.omissions), gap_codes=list(package.coverage.gap_codes))
        except ScanRegistryError as error:
            code = {"registry_not_found": "not_found",
                    "registry_invalid_argument": "invalid_argument"}.get(error.code, "storage_unavailable")
            raise NoticeSourceStoreError(code) from error
        except (AssessmentStoreError, OSError) as error:
            raise NoticeSourceStoreError("storage_unavailable") from error
        except (ValueError, TypeError, RecursionError) as error:
            raise NoticeSourceStoreError("invalid_argument") from error


def decode_bound_notice_source(bound: BoundNoticeSource) -> NoticeSourcePackage:
    """Pure round trip of an A1 Reader result; never queries upstream or network.

    Assessment identity and binding_hash integrity remain the A1 Reader's job.
    This helper checks the independent CZ payload/BOUND metadata closure.
    """
    if (not isinstance(bound, BoundNoticeSource) or bound.state != "BOUND"
            or not _positive_int(bound.registry_revision)
            or not _positive_int(bound.assessment_version)
            or bound.assessment_facts_hash != bound.facts_hash
            or bound.inventory_digest is None):
        raise NoticeSourceStoreError("binding_mismatch")
    try:
        raw = bound.canonical_package_bytes
        if (type(raw) is not bytes or len(raw) > MAX_PACKAGE_BYTES
                or hashlib.sha256(raw).hexdigest() != bound.package_hash):
            raise NoticeSourceStoreError("invalid_argument")
        preimage = json.loads(raw)
        if (type(preimage) is not dict or "package_hash" in preimage
                or canonical_json(preimage) != raw):
            raise NoticeSourceStoreError("invalid_argument")
        package = validate_notice_source_package({**preimage, "package_hash": bound.package_hash})
        _check_binding(package, Binding(
            scan_id=bound.scan_id, registry_revision=str(bound.registry_revision),
            input_digest=bound.input_digest, inventory_digest=bound.inventory_digest,
            facts_hash=bound.facts_hash))
        decoded_raw, producer, version = _metadata(package)
        if (decoded_raw != raw or package.package_hash != bound.package_hash
                or package.schema_version != bound.collector_schema_version
                or (producer, version) != (bound.producer, bound.producer_version)
                or package.coverage.state != bound.coverage_status
                or tuple(package.coverage.omissions) != bound.omissions
                or tuple(package.coverage.gap_codes) != bound.gap_codes):
            raise NoticeSourceStoreError("binding_mismatch")
        return package
    except (ValueError, TypeError, RecursionError) as error:
        raise NoticeSourceStoreError("invalid_argument") from error
