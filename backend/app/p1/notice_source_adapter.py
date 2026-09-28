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
from app.notice_source import (
    NoticeSourceCollection, NoticeSourcePackage, bind_notice_source_collection,
    validate_notice_source_package,
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
