"""Bind explicit npm lock declarations to already mapped ZIP components."""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from dataclasses import dataclass
from datetime import datetime

from app.domain.models import Evidence, LicenseExpression, ProducerRef, ScanRun, VerificationStatus
from app.ingestion import ReadOnlyScanSession
from app.licenses import normalize_license
from app.scanners import JavascriptP0MappingResult

_NAMESPACE = uuid.UUID("fd894c31-3dfa-5a9d-831d-7b332b80a4c1")
_MAX_FILE = 2 * 1024 * 1024
_PRODUCER = ProducerRef(type="parser", name="openguard.npm-lock-license", version="1")


@dataclass(frozen=True)
class ManifestLicenseBinding:
    component_id: str
    license: LicenseExpression
    evidence: Evidence


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _bounded(value: object, depth: int = 0) -> None:
    if depth > 32 or (type(value) is str and len(value) > 4096):
        raise ValueError("manifest limit")
    if type(value) is float and not math.isfinite(value):
        raise ValueError("non-finite JSON")
    if type(value) is dict:
        for key, item in value.items():
            _bounded(key, depth + 1)
            _bounded(item, depth + 1)
    elif type(value) is list:
        for item in value:
            _bounded(item, depth + 1)


def collect_manifest_licenses(
    session: ReadOnlyScanSession,
    mapping: JavascriptP0MappingResult | None,
    observed_at: datetime,
    *,
    total_read_budget: int,
) -> tuple[ManifestLicenseBinding, ...]:
    """Read only during A2's callback; never infer a dependency's root license."""
    if mapping is None:
        return ()
    inventory = {item.relative_path: item for item in session.inventory.entries}
    # B1 reads each selected manifest once. All inventory bytes are a safe
    # upper bound; reserve every possible lock reread before touching A2.
    # Exceeding the shared budget poisons the session, so skip enrichment.
    prior_read_bound = sum(item.size_bytes for item in inventory.values())
    lock_read_bound = sum(
        item.size_bytes for path, item in inventory.items()
        if path.rsplit("/", 1)[-1] == "package-lock.json"
    )
    if prior_read_bound + lock_read_bound > total_read_budget:
        return ()
    evidence = {item.id: item for item in mapping.evidence}
    documents: dict[str, dict | None] = {}
    bindings: list[ManifestLicenseBinding] = []
    for component in mapping.components:
        candidates: list[ManifestLicenseBinding] = []
        token = ("node_modules/" + component.name).replace("~", "~0").replace("/", "~1")
        suffix = ":/packages/" + token + "/version"
        for evidence_id in component.evidence_ids:
            source = evidence.get(evidence_id)
            if source is None or not source.locator.endswith(suffix):
                continue
            path = source.locator[:-len(suffix)]
            entry = inventory.get(path)
            if (not path.endswith("package-lock.json") or entry is None
                    or source.content_hash is None or source.content_hash.value != entry.sha256):
                continue
            if path not in documents:
                documents[path] = None
                try:
                    data = session.read_bytes(path, max_bytes=_MAX_FILE)
                    if len(data) != entry.size_bytes or hashlib.sha256(data).hexdigest() != entry.sha256:
                        continue
                    document = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs)
                    _bounded(document)
                    if type(document) is dict and type(document.get("lockfileVersion")) is int and document["lockfileVersion"] in {2, 3}:
                        documents[path] = document
                except (ValueError, OSError, RecursionError):
                    continue
            document = documents[path]
            packages = document.get("packages") if document else None
            record = packages.get("node_modules/" + component.name) if type(packages) is dict else None
            if type(record) is not dict or ("name" in record and record["name"] != component.name):
                continue
            version = record.get("version")
            if (type(version) is not str or version.removeprefix("v") != component.version
                    or source.excerpt != json.dumps(version, ensure_ascii=False, separators=(",", ":"))):
                continue
            text = record.get("license")
            if type(text) is not str or not 1 <= len(text) <= 200 or any(ord(char) < 32 or ord(char) > 126 for char in text):
                continue
            locator = source.locator.removesuffix("version") + "license"
            try:
                item = Evidence.model_validate({
                    **source.model_dump(mode="python"),
                    "id": "evd_" + str(uuid.uuid5(_NAMESPACE, json.dumps([session.inventory.root_digest, locator, entry.sha256, text]))),
                    "locator": locator, "excerpt": json.dumps(text), "producer": _PRODUCER,
                    "observed_at": observed_at, "verification_status": VerificationStatus.PENDING,
                })
                license_expression = normalize_license(text, [item])
            except ValueError:
                continue
            if license_expression.normalized_ids:
                candidates.append(ManifestLicenseBinding(component.id, license_expression, item))
        # Conflicting declarations for one merged component are not guessed away.
        if len({item.license.expression for item in candidates}) == 1:
            bindings.append(sorted(candidates, key=lambda item: item.evidence.id)[0])
    return tuple(bindings)


def apply_manifest_licenses(run: ScanRun, bindings: tuple[ManifestLicenseBinding, ...]) -> ScanRun:
    if not bindings:
        return ScanRun.model_validate(run.model_dump(mode="python"))
    by_component = {item.component_id: item for item in bindings}
    evidence = {item.id: item for item in run.evidence}
    components = []
    licenses = {}
    for component in run.components:
        binding = by_component.get(component.id)
        if binding:
            evidence[binding.evidence.id] = binding.evidence
            expression = binding.license
        else:
            expression = normalize_license("NOASSERTION", [evidence[key] for key in component.evidence_ids])
        licenses[expression.id] = expression
        components.append(component.model_copy(update={"license_expression_id": expression.id}))
    producers = {json.dumps(item.model_dump(mode="json"), sort_keys=True): item for item in run.provenance.tool_versions}
    producers[json.dumps(_PRODUCER.model_dump(mode="json"), sort_keys=True)] = _PRODUCER
    payload = run.model_dump(mode="python")
    payload.update(components=components, licenses=sorted(licenses.values(), key=lambda item: item.id),
                   evidence=sorted(evidence.values(), key=lambda item: (item.locator.encode(), item.id)),
                   summary=run.summary.model_copy(update={"evidence_count": len(evidence)}),
                   provenance=run.provenance.model_copy(update={"tool_versions": [producers[key] for key in sorted(producers)]}))
    return ScanRun.model_validate(payload)
