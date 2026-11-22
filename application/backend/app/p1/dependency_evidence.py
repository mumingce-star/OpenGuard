"""Read-only dependency evidence derived from one saved ScanRun."""

from __future__ import annotations

import json
from bisect import bisect_right
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal
from unicodedata import category
from urllib.parse import quote, unquote

from packaging.version import InvalidVersion, Version

from app.domain.models import (
    Component,
    ComponentType,
    DetectionMethod,
    Evidence,
    EvidenceKind,
    P0Model,
    ProducerRef,
    ProducerType,
    ScanRun,
    ScanStage,
    VerificationStatus,
)
from app.p2b._resource_roles import RoleEvidence, _finding
from app.scanners.dependency_observations import relative_path
from app.scanners.javascript_manifest import _exact as exact_npm_version
from app.scanners.python_p0_mapper import _GROUP_LOCATOR, _OPTIONAL_LOCATOR, _REQ_LOCATOR
from app.security.archive_path import normalize_member_path
from app.security.errors import IngestionSecurityError
from app.security.limits import ZipSafetyLimits

DependencySource = Literal["manifest", "lock", "sbom", "unknown"]
ConflictStatus = Literal["confirmed", "incomplete", "ambiguous"]
RoleState = Literal["observed", "inferred", "unknown"]

MAX_RESOURCE_EVIDENCE = 50
MAX_RESOURCE_CONFLICTS = 8
MAX_CONFLICT_SIDE_EVIDENCE = 8

_PYTHON = "openguard-python-manifest-parser"
_JAVASCRIPT = "openguard.javascript-manifest"
_B58_LOCK = "openguard.dependency-observations.lock"
_B58_SBOM = "openguard.dependency-observations.sbom"
_NPM_LOCK_LICENSE = "openguard.npm-lock-license"
_NPM_DECLARE_FIELDS = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")
_PATH_LIMITS = ZipSafetyLimits()


class DependencyEvidenceRef(P0Model):
    evidence_id: str
    source: DependencySource
    file_path: str | None
    locator: str | None
    source_sha256: str | None
    producer: ProducerRef
    verification_status: VerificationStatus
    kind: EvidenceKind
    start_line: int | None
    end_line: int | None


class DependencyConflictSide(P0Model):
    resource_id: str
    version: str
    evidence: list[DependencyEvidenceRef]
    evidence_total: int
    evidence_returned: int
    incomplete: bool


class DependencyVersionConflict(P0Model):
    code: Literal["lock_version_conflict"] = "lock_version_conflict"
    status: ConflictStatus
    declaration: DependencyConflictSide | None
    lock: DependencyConflictSide | None
    gaps: list[str]


class DependencyEvidenceItem(P0Model):
    resource_id: str
    name: str
    version: str | None
    ecosystem: Literal["pypi", "npm", "unknown"]
    role_state: RoleState
    sources: list[DependencySource]
    evidence: list[DependencyEvidenceRef]
    evidence_total: int
    evidence_returned: int
    conflicts: list[DependencyVersionConflict]
    conflicts_total: int
    conflicts_returned: int
    incomplete: bool
    gaps: list[str]


def _source(entry: Evidence) -> DependencySource:
    if entry.detected_by is not DetectionMethod.MANIFEST_PARSER or entry.producer.type is not ProducerType.PARSER:
        return "unknown"
    name = entry.producer.name
    if name == _B58_SBOM and entry.kind in {EvidenceKind.FILE, EvidenceKind.MANIFEST_FIELD}:
        return "sbom"
    if entry.kind is not EvidenceKind.MANIFEST_FIELD:
        return "unknown"
    if name in {_B58_LOCK, _NPM_LOCK_LICENSE}:
        return "lock"
    if name == _PYTHON:
        return "manifest"
    if name == _JAVASCRIPT:
        path, separator, _ = entry.locator.rpartition(":/")
        if separator and path.rsplit("/", 1)[-1] == "package-lock.json":
            return "lock"
        if separator and path.rsplit("/", 1)[-1] == "package.json":
            return "manifest"
    return "unknown"


def _safe_path(path: str, *, native: bool = False) -> str | None:
    try:
        if native:
            saved = normalize_member_path(path, is_directory=False, limits=_PATH_LIMITS)
            return path if saved.relative_path == path else None
        return relative_path(path)
    except (ValueError, IngestionSecurityError):
        return None


def _file_location(entry: Evidence, source: DependencySource) -> tuple[str | None, str]:
    if source == "unknown" or any(category(char) in {"Cc", "Cf", "Cs"} for char in entry.locator):
        return None, ""
    if entry.kind is EvidenceKind.FILE:
        return _safe_path(entry.locator), ""

    path, separator, field = entry.locator.partition(":")
    if entry.producer.name == _PYTHON:
        # The Python mapper percent-encodes the file path, not the field syntax.
        try:
            decoded = unquote(path, errors="strict")
        except UnicodeDecodeError:
            return None, ""
        if quote(decoded, safe="/-._~") != path or any(category(char) in {"Cc", "Cf", "Cs"} for char in decoded):
            return None, ""
        filename = decoded.rsplit("/", 1)[-1]
        if separator:
            valid = filename == "pyproject.toml" and any(
                pattern.fullmatch(field) for pattern in (_REQ_LOCATOR, _OPTIONAL_LOCATOR, _GROUP_LOCATOR)
            )
        else:
            valid = entry.start_line is not None and filename.startswith("requirements") and filename.endswith(".txt")
        if not valid:
            return None, ""
        return _safe_path(decoded, native=True), field
    if entry.producer.name in {_JAVASCRIPT, _NPM_LOCK_LICENSE}:
        path, separator, field = entry.locator.rpartition(":/")
        if not separator or not field:
            return None, ""
        return _safe_path(path, native=True), f"/{field}"
    if separator and field.startswith("/") and len(field) > 1:
        return _safe_path(path), field
    return None, ""


@dataclass(frozen=True)
class _Fact:
    entry: Evidence
    source: DependencySource
    path: str | None
    field: str

    @property
    def sha256(self) -> str | None:
        digest = self.entry.content_hash
        if self.path is None:
            return None
        return digest.value if digest is not None and digest.algorithm == "sha256" else None

    def ref(self) -> DependencyEvidenceRef:
        return DependencyEvidenceRef(
            evidence_id=self.entry.id,
            source=self.source,
            file_path=self.path,
            locator=self.entry.locator if self.path is not None else None,
            source_sha256=self.sha256,
            producer=self.entry.producer,
            verification_status=self.entry.verification_status,
            kind=self.entry.kind,
            start_line=self.entry.start_line,
            end_line=self.entry.end_line,
        )


def _fact(entry: Evidence, source: DependencySource) -> _Fact:
    path, field = _file_location(entry, source)
    return _Fact(entry, source, path, field)


def _pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _role_basis(component: Component, fact: _Fact) -> bool:
    if fact.path is None or fact.sha256 is None or fact.entry.verification_status is VerificationStatus.REJECTED:
        return False
    producer = fact.entry.producer.name
    if producer == _JAVASCRIPT:
        token = _pointer_token(component.name)
        if fact.source == "manifest":
            return fact.field in {f"/{field}/{token}" for field in _NPM_DECLARE_FIELDS}
        token = _pointer_token("node_modules/" + component.name)
        return fact.field in {f"/packages/{token}/version", f"/packages/{token}/resolved"}
    return fact.source != "unknown" and producer != _NPM_LOCK_LICENSE


def _role(component: Component, facts: list[_Fact]) -> RoleState:
    references = {
        RoleEvidence(
            fact.source, fact.entry.locator, fact.entry.id, fact.sha256,
            fact.entry.start_line, fact.entry.end_line,
        )
        for fact in facts if fact.source != "unknown" and _role_basis(component, fact)
    }
    return _finding("declared", references, set()).status


def _exact_version(component: Component, fact: _Fact) -> str | Version | None:
    if not _role_basis(component, fact) or component.version is None:
        return None
    producer = fact.entry.producer.name
    if component.ecosystem == "pypi" and producer in {_PYTHON, _B58_LOCK}:
        try:
            return Version(component.version)
        except InvalidVersion:
            return None
    if component.ecosystem != "npm" or exact_npm_version(component.version) != component.version:
        return None
    if fact.source == "manifest" and producer == _JAVASCRIPT:
        # Do not use a lock-enriched Component.version as a requested version.
        if fact.entry.excerpt in {json.dumps(component.version), json.dumps(f"v{component.version}")}:
            return component.version
    if fact.source == "lock" and producer == _B58_LOCK:
        if fact.field == f"/dependencies/{_pointer_token(component.name)}":
            return component.version
    return None


@dataclass(frozen=True)
class _ConflictSide:
    component: Component
    facts: list[_Fact]
    scope: tuple[str, str, str]
    version: str | Version

    def ref(self) -> DependencyConflictSide:
        refs = [fact.ref() for fact in self.facts[:MAX_CONFLICT_SIDE_EVIDENCE]]
        assert self.component.version is not None
        return DependencyConflictSide(
            resource_id=self.component.id,
            version=self.component.version,
            evidence=refs,
            evidence_total=len(self.facts),
            evidence_returned=len(refs),
            incomplete=len(refs) < len(self.facts),
        )


def _conflict(
    evidence_ids: tuple[str, ...],
    owners: dict[str, list[Component]],
    get_fact: Callable[[str], _Fact | None],
) -> DependencyVersionConflict:
    sides: dict[DependencySource, dict[tuple[str, str], _ConflictSide]] = {
        "manifest": {}, "lock": {},
    }
    ambiguous = False
    gaps: set[str] = set()
    for evidence_id in evidence_ids:
        fact = get_fact(evidence_id)
        if fact is None:
            gaps.add("conflict_evidence_missing")
            continue
        linked = owners.get(evidence_id, [])
        if len(linked) > 1:
            ambiguous = True
            continue
        if not linked or linked[0].component_type is ComponentType.APPLICATION:
            gaps.add("conflict_evidence_unbound")
            continue
        component = linked[0]
        version = _exact_version(component, fact)
        if fact.source not in sides or fact.path is None or version is None:
            gaps.add("conflict_evidence_incomplete")
            continue
        scope = (fact.path.rpartition("/")[0], component.ecosystem, component.name)
        key = (component.id, scope[0])
        if key not in sides[fact.source]:
            sides[fact.source][key] = _ConflictSide(component, [], scope, version)
        sides[fact.source][key].facts.append(fact)

    declaration = next(iter(sides["manifest"].values())) if len(sides["manifest"]) == 1 else None
    lock = next(iter(sides["lock"].values())) if len(sides["lock"]) == 1 else None
    ambiguous = ambiguous or any(len(entries) > 1 for entries in sides.values())
    if declaration is not None and lock is not None and (
        declaration.scope != lock.scope or declaration.version == lock.version
    ):
        # The stored references do not establish the same-scope conflicting pair.
        declaration = None
        lock = None
        ambiguous = True
    declaration_ref = declaration.ref() if declaration is not None else None
    lock_ref = lock.ref() if lock is not None else None
    if declaration_ref is None:
        gaps.add("declaration_side_unavailable")
    if lock_ref is None:
        gaps.add("lock_side_unavailable")
    if ambiguous:
        gaps.add("conflict_ambiguous")
    if any(side is not None and side.incomplete for side in (declaration_ref, lock_ref)):
        gaps.add("conflict_side_evidence_limit_exceeded")

    status: ConflictStatus = "ambiguous" if ambiguous else "incomplete" if gaps else "confirmed"
    return DependencyVersionConflict(
        status=status,
        declaration=declaration_ref,
        lock=lock_ref,
        gaps=sorted(gaps),
    )


def project_dependency_evidence(
    run: ScanRun,
    *,
    source: DependencySource | None,
    after: str | None,
    limit: int,
) -> tuple[list[DependencyEvidenceItem], int, bool]:
    """Return one stable page, counting all matching recorded components."""
    evidence = {entry.id: entry for entry in run.evidence}
    sources = {key: _source(entry) for key, entry in evidence.items()}
    candidates = []
    for component in sorted(run.components, key=lambda item: item.id):
        if component.component_type is ComponentType.APPLICATION:
            continue
        component_sources = sorted({sources.get(eid, "unknown") for eid in component.evidence_ids})
        if source is None or source in component_sources:
            candidates.append((component, component_sources))

    page_start = bisect_right(candidates, after, key=lambda candidate: candidate[0].id) if after is not None else 0
    page = candidates[page_start:page_start + limit]
    if not page:
        return [], len(candidates), False

    # Reverse-index only IDs named in saved conflicts, including owners outside this page.
    recorded = sorted({
        tuple(error.evidence_ids) for error in run.errors
        if error.code == "lock_version_conflict" and error.stage is ScanStage.SCAN and error.evidence_ids
    })
    involved = {eid for group in recorded for eid in group}
    owners: dict[str, list[Component]] = defaultdict(list)
    for component in run.components:
        for evidence_id in component.evidence_ids:
            if evidence_id in involved:
                owners[evidence_id].append(component)
    page_ids = {component.id for component, _ in page}
    conflicts: dict[str, list[tuple[str, ...]]] = defaultdict(list)
    for group in recorded:
        affected = {item.id for eid in group for item in owners.get(eid, ()) if item.id in page_ids}
        for resource_id in affected:
            conflicts[resource_id].append(group)

    facts: dict[str, _Fact] = {}

    def get_fact(evidence_id: str) -> _Fact | None:
        entry = evidence.get(evidence_id)
        if entry is None:
            return None
        if evidence_id not in facts:
            facts[evidence_id] = _fact(entry, sources[evidence_id])
        return facts[evidence_id]

    conflict_cache: dict[tuple[str, ...], DependencyVersionConflict] = {}
    items = []
    for component, actual in page:
        related = conflicts[component.id]
        full = [fact for eid in component.evidence_ids if (fact := get_fact(eid)) is not None]
        refs = [fact.ref() for fact in full[:MAX_RESOURCE_EVIDENCE]]
        gaps: set[str] = set()
        if len(full) != len(component.evidence_ids):
            gaps.add("evidence_reference_missing")
        if any(fact.sha256 is None for fact in full):
            gaps.add("source_sha256_missing")
        if any(fact.path is None for fact in full):
            gaps.add("file_path_unavailable")
        if "unknown" in actual:
            gaps.add("source_unclassified")
        if component.version is None:
            gaps.add("version_unavailable")
        if len(refs) < len(full):
            gaps.add("evidence_limit_exceeded")
        if len(related) > MAX_RESOURCE_CONFLICTS:
            gaps.add("conflict_limit_exceeded")
        visible_conflicts = []
        for group in related[:MAX_RESOURCE_CONFLICTS]:
            if group not in conflict_cache:
                conflict_cache[group] = _conflict(group, owners, get_fact)
            item = conflict_cache[group]
            visible_conflicts.append(item)
            gaps.update(item.gaps)
        role = "unknown" if related else _role(component, full)
        if role == "unknown" and not related:
            gaps.add("role_evidence_unavailable")
        items.append(DependencyEvidenceItem(
            resource_id=component.id,
            name=component.name,
            version=component.version,
            ecosystem=component.ecosystem,
            role_state=role,
            sources=actual,
            evidence=refs,
            evidence_total=len(component.evidence_ids),
            evidence_returned=len(refs),
            conflicts=visible_conflicts,
            conflicts_total=len(related),
            conflicts_returned=len(visible_conflicts),
            incomplete=bool(gaps),
            gaps=sorted(gaps),
        ))
    return items, len(candidates), len(candidates) > page_start + len(page)
