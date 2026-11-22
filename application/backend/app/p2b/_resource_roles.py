"""Private role observations over one authorized scan snapshot."""

from __future__ import annotations

import ast
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote

from app.domain.models import Component, DetectionMethod, Evidence, EvidenceKind, VerificationStatus
from app.scanners.javascript_p0_mapper import JavascriptP0MappingResult
from app.scanners.python_p0_mapper import PythonP0MappingResult

Role = Literal["declared", "imported", "build", "delivered"]
Source = Literal["manifest", "lock", "sbom", "import", "build", "delivery"]
_ROLES: tuple[Role, ...] = ("declared", "imported", "build", "delivered")
_BOUND_ROLES: dict[str, Role] = {"import": "imported", "build": "build", "delivery": "delivered"}
_MANIFEST_CONFLICTS = {"dependency_declaration_conflict", "lock_version_conflict", "lock_root_mismatch"}


@dataclass(frozen=True)
class RoleEvidence:
    source: Source
    locator: str
    evidence_id: str | None = None
    sha256: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    present: bool = True


@dataclass(frozen=True)
class RoleConflict:
    code: str
    locator: str | None = None
    start_line: int | None = None


@dataclass(frozen=True)
class BoundRoleEvidence:
    """An authorized fact already associated with an exact component."""

    resource_id: str
    version: str | None
    source: Literal["import", "build", "delivery"]
    evidence_id: str
    present: bool = True


@dataclass(frozen=True)
class RoleFinding:
    role: Role
    status: Literal["observed", "inferred", "unknown"]
    evidence: tuple[RoleEvidence, ...] = ()
    conflicts: tuple[RoleConflict, ...] = ()


@dataclass(frozen=True)
class ResourceRoles:
    resource_id: str
    version: str | None
    roles: tuple[RoleFinding, ...]


def _location(source: Source, evidence: Evidence, present: bool = True) -> RoleEvidence:
    return RoleEvidence(
        source, evidence.locator, evidence.id, evidence.content_hash.value if evidence.content_hash else None,
        evidence.start_line, evidence.end_line, present,
    )


def python_import_locations(
    source: Evidence, raw: bytes, *, reviewed_module_bindings: Mapping[str, Component],
) -> dict[str, tuple[RoleEvidence, ...]]:
    """Recognize absolute Python AST imports using explicit module-to-distribution bindings."""
    if (
        source.kind != EvidenceKind.FILE or not source.locator.endswith(".py") or len(raw) > 256 * 1024
        or source.content_hash is None or source.content_hash.algorithm != "sha256"
        or hashlib.sha256(raw).hexdigest() != source.content_hash.value
        or source.verification_status != VerificationStatus.VERIFIED
    ):
        raise ValueError("invalid_import_source")
    tree = ast.parse(raw.decode("utf-8"))
    hits: dict[str, set[RoleEvidence]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules = [node.module]
        else:
            continue
        for module in modules:
            target = reviewed_module_bindings.get(module.partition(".")[0])
            if target is None or target.ecosystem != "pypi":
                continue
            hits.setdefault(target.id, set()).add(RoleEvidence(
                "import", source.locator, source.id, source.content_hash.value, node.lineno, node.end_lineno,
            ))
    return {resource: _ordered(locations) for resource, locations in sorted(hits.items())}


def assess_resource_roles(
    components: Sequence[Component],
    evidence: Sequence[Evidence],
    *,
    manifests: Sequence[JavascriptP0MappingResult | PythonP0MappingResult] = (),
    facts: Sequence[BoundRoleEvidence] = (),
    import_sources: Sequence[tuple[Evidence, bytes, Mapping[str, Component]]] = (),
) -> tuple[ResourceRoles, ...]:
    """Use mapper references and reviewed facts; the caller owns snapshot and source authorization."""
    by_id = {entry.id: entry for entry in evidence}
    resources = {item.id: item for item in components}
    if len(by_id) != len(evidence) or len(resources) != len(components):
        raise ValueError("duplicate_role_input_identity")
    locations: dict[str, dict[Role, set[RoleEvidence]]] = {
        item.id: {role: set() for role in _ROLES} for item in components
    }
    conflicts: dict[str, dict[Role, set[RoleConflict]]] = {
        item.id: {role: set() for role in _ROLES} for item in components
    }
    resources_by_locator: dict[str, set[str]] = {}
    resources_by_manifest: dict[str, set[str]] = {}
    resources_by_lock_entry: dict[str, set[str]] = {}
    for item in components:
        for evidence_id in item.evidence_ids:
            entry = by_id.get(evidence_id)
            if entry is None:
                raise ValueError("unresolved_component_evidence")
            if entry.verification_status == VerificationStatus.REJECTED:
                continue
            if entry.detected_by == DetectionMethod.MANIFEST_PARSER:
                path, _, field = entry.locator.partition(":")
                resources_by_locator.setdefault(entry.locator, set()).add(item.id)
                if entry.producer.name == "openguard.dependency-observations.sbom":
                    locations[item.id]["declared"].add(_location("sbom", entry))
                elif (entry.producer.name == "openguard.dependency-observations.lock"
                      or path.rsplit("/", 1)[-1] == "package-lock.json"):
                    locations[item.id]["declared"].add(_location("lock", entry))
                else:
                    locations[item.id]["declared"].add(_location("manifest", entry))
                    resources_by_manifest.setdefault(path, set()).add(item.id)
                    if item.ecosystem == "npm" and path.rsplit("/", 1)[-1] == "package.json":
                        lock_path = path.removesuffix("package.json") + "package-lock.json"
                        token = ("node_modules/" + item.name).replace("~", "~0").replace("/", "~1")
                        locator = f"{lock_path}:/packages/{token}/version"
                        resources_by_lock_entry.setdefault(locator, set()).add(item.id)
                    if field.startswith("build-system.requires["):
                        locations[item.id]["build"].add(_location("manifest", entry))
            elif entry.detected_by == DetectionMethod.SYFT:
                locations[item.id]["declared"].add(_location("sbom", entry))

    for mapped in manifests:
        for diagnostic in mapped.diagnostics:
            if diagnostic.code not in _MANIFEST_CONFLICTS:
                continue
            if isinstance(mapped, PythonP0MappingResult):
                locator = quote(diagnostic.manifest_path, safe="/-._~")
                if diagnostic.field_locator:
                    locator += f":{diagnostic.field_locator}"
                for resource_id in resources_by_locator.get(locator, ()):
                    for entry in locations[resource_id]["declared"]:
                        if entry.locator == locator and entry.start_line == diagnostic.start_line:
                            conflicts[resource_id]["declared"].add(RoleConflict(
                                diagnostic.code, locator, diagnostic.start_line,
                            ))
                continue
            locator = diagnostic.field_locator or diagnostic.manifest_path
            if diagnostic.code == "lock_root_mismatch":
                sibling = diagnostic.manifest_path.removesuffix("package-lock.json") + "package.json"
                affected = resources_by_manifest.get(sibling, ())
            elif diagnostic.code == "lock_version_conflict":
                affected = resources_by_lock_entry.get(locator, ())
            else:
                affected = resources_by_locator.get(locator, ())
            for resource_id in affected:
                conflicts[resource_id]["declared"].add(RoleConflict(diagnostic.code, locator))

    for fact in facts:
        item = resources.get(fact.resource_id)
        entry = by_id.get(fact.evidence_id)
        if (
            item is None or item.version != fact.version or entry is None
            or entry.verification_status != VerificationStatus.VERIFIED
            or entry.content_hash is None or entry.content_hash.algorithm != "sha256"
            or fact.source not in _BOUND_ROLES or (fact.source == "delivery" and item.version is None)
        ):
            raise ValueError("unresolved_role_fact")
        locations[item.id][_BOUND_ROLES[fact.source]].add(_location(fact.source, entry, fact.present))

    for source, raw, reviewed_modules in import_sources:
        if by_id.get(source.id) != source or any(resources.get(item.id) != item for item in reviewed_modules.values()):
            raise ValueError("unresolved_import_binding")
        for resource_id, imports in python_import_locations(source, raw, reviewed_module_bindings=reviewed_modules).items():
            locations[resource_id]["imported"].update(imports)

    return tuple(
        ResourceRoles(item.id, item.version, tuple(
            _finding(role, locations[item.id][role], conflicts[item.id][role]) for role in _ROLES
        ))
        for item in sorted(components, key=lambda item: item.id)
    )


def _ordered(locations: set[RoleEvidence]) -> tuple[RoleEvidence, ...]:
    return tuple(sorted(locations, key=lambda entry: (
        entry.source, entry.locator, entry.evidence_id or "", entry.sha256 or "",
        entry.start_line or 0, entry.end_line or 0, entry.present,
    )))


def _finding(role: Role, locations: set[RoleEvidence], conflicts: set[RoleConflict]) -> RoleFinding:
    positive = {entry.source for entry in locations if entry.present}
    negative = any(not entry.present for entry in locations)
    if positive and negative:
        conflicts.add(RoleConflict("contradictory_role_evidence"))
    if conflicts or not positive:
        status = "unknown"
    elif positive <= {"lock", "sbom"} or role == "build" and positive == {"manifest"}:
        status = "inferred"
    else:
        status = "observed"
    return RoleFinding(role, status, _ordered(locations), tuple(sorted(
        conflicts, key=lambda conflict: (conflict.code, conflict.locator or "", conflict.start_line or 0),
    )))
