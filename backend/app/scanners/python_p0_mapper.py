"""Deterministically map frozen Python manifest DTOs into P0 objects."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote, unquote

try:
    from packaging.markers import InvalidMarker, Marker
    from packaging.specifiers import InvalidSpecifier, SpecifierSet
    from packaging.utils import canonicalize_name
    from packaging.version import InvalidVersion, Version
except ImportError:  # B1 parser reports its frozen unavailable reason before mapping.
    InvalidMarker = InvalidSpecifier = ValueError
    Marker = SpecifierSet = canonicalize_name = None  # type: ignore[assignment,misc]
    InvalidVersion = ValueError
    Version = None  # type: ignore[assignment,misc]

from app.domain.models import (
    Component,
    ComponentType,
    DetectionMethod,
    Evidence,
    EvidenceKind,
    HashValue,
    ProducerRef,
    ProducerType,
    VerificationStatus,
)
from app.scanners.python_manifest import (
    DependencyScope,
    DependencySourceKind,
    ManifestEvidenceDraft,
    ManifestKind,
    ParseStatus,
    ParsedManifest,
    ParserDiagnostic,
    PythonDependencyDeclaration,
    PythonManifestParseResult,
    _MESSAGES,
    _canonical_reference,
)
from app.security.errors import IngestionSecurityError


MAPPER_SCHEMA_VERSION = "b1-python-p0/v1"
PYTHON_P0_NAMESPACE = uuid.UUID("7d857170-1410-582b-a296-bb0fc9a9f057")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REQ_LOCATOR = re.compile(r"^(?:project\.dependencies|build-system\.requires)\[(\d+)]$")
_OPTIONAL_LOCATOR = re.compile(r"^project\.optional-dependencies\.((?:[A-Za-z0-9._-]|%[0-9A-F]{2})+)\[(\d+)]$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SENSITIVE = re.compile(r"(?i)(?:api[_-]?key|secret|token|password)\s*[=:]")
_DIAGNOSTIC_SEVERITY = {
    "manifest_encoding_invalid": "error", "manifest_toml_invalid": "error",
    "manifest_field_invalid": "error", "manifest_logical_line_too_long": "error",
    "requirement_invalid": "error", "requirement_include_unsupported": "warning",
    "requirement_constraint_unsupported": "warning", "requirement_editable_unsupported": "warning",
    "requirement_option_unsupported": "warning", "requirement_unnamed_reference_unsupported": "error",
    "requirement_reference_unsafe": "error", "requirement_hash_invalid": "error",
    "pyproject_dynamic_dependencies_unsupported": "warning", "pyproject_tool_table_unsupported": "warning",
    "dependency_duplicate": "warning", "dependency_declaration_conflict": "error",
    "dependency_multiple_constraints": "warning",
}
_PYPROJECT_DIAGNOSTIC_LOCATOR = re.compile(
    r"^(?:project|project\.dynamic|project\.dependencies|project\.optional-dependencies(?:\.[A-Za-z0-9._%\-]+)?|build-system|build-system\.requires|tool)$"
)


@dataclass(frozen=True)
class PythonP0MappingResult:
    schema_version: str
    status: ParseStatus
    components: tuple[Component, ...]
    evidence: tuple[Evidence, ...]
    diagnostics: tuple[ParserDiagnostic, ...]


def _error() -> IngestionSecurityError:
    return IngestionSecurityError("scanner_failed", "python_p0_mapper_failed")


def _relative_path(value: object) -> bool:
    return (
        type(value) is str
        and bool(value)
        and not value.startswith("/")
        and "\\" not in value
        and all(part and part not in {".", ".."} and "\x00" not in part for part in value.split("/"))
    )


def _uuid(prefix: str, material: list[object]) -> str:
    name = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{prefix}_{uuid.uuid5(PYTHON_P0_NAMESPACE, name)}"


def _validate_context(result: PythonManifestParseResult, root_digest: str, observed_at: datetime) -> dict[str, ParsedManifest]:
    if type(result) is not PythonManifestParseResult or result.schema_version != "b1-python-manifest/v1":
        raise _error()
    if type(root_digest) is not str or not _SHA256.fullmatch(root_digest):
        raise _error()
    if type(observed_at) is not datetime or observed_at.tzinfo is None or observed_at.utcoffset() != timezone.utc.utcoffset(observed_at):
        raise _error()
    if not all(type(container) is tuple for container in (result.manifests, result.dependencies, result.diagnostics)):
        raise _error()
    if type(result.status) is not ParseStatus or any(type(item) is not ParsedManifest for item in result.manifests):
        raise _error()
    manifests: dict[str, ParsedManifest] = {}
    for manifest in result.manifests:
        if (
            not _relative_path(manifest.relative_path)
            or type(manifest.kind) is not ManifestKind
            or type(manifest.size_bytes) is not int
            or manifest.size_bytes < 0
            or not _SHA256.fullmatch(manifest.content_sha256)
            or type(manifest.status) is not ParseStatus
            or manifest.relative_path in manifests
        ):
            raise _error()
        manifests[manifest.relative_path] = manifest
    if tuple(manifest.relative_path for manifest in result.manifests) != tuple(sorted(manifests, key=lambda value: value.encode("utf-8"))):
        raise _error()
    if (result.diagnostics and result.status is not ParseStatus.PARTIAL) or (not result.diagnostics and result.status is not ParseStatus.COMPLETE):
        raise _error()
    if any(item.status is ParseStatus.PARTIAL for item in result.manifests) and not result.diagnostics:
        raise _error()
    for item in result.diagnostics:
        _diagnostic_valid(item, manifests)
    diagnostic_key = lambda item: ((item.manifest_path or "").encode("utf-8"), item.start_line or 0, (item.field_locator or "").encode("utf-8"), item.code, item.severity)
    if tuple(result.diagnostics) != tuple(sorted(result.diagnostics, key=diagnostic_key)):
        raise _error()
    return manifests


def _encoded_path(path: str) -> str:
    encoded = quote(path, safe="/-._~")
    if unquote(encoded) != path or quote(unquote(encoded), safe="/-._~") != encoded:
        raise _error()
    return encoded


def _locator(draft: ManifestEvidenceDraft, manifest: ParsedManifest) -> str:
    if type(draft.manifest_path) is not str or draft.manifest_path != manifest.relative_path:
        raise _error()
    path = _encoded_path(draft.manifest_path)
    if draft.field_locator is None:
        if type(draft.start_line) is not int or type(draft.end_line) is not int or draft.start_line < 1 or draft.end_line < draft.start_line:
            raise _error()
        locator = path
    else:
        if draft.start_line is not None or draft.end_line is not None or not isinstance(draft.field_locator, str):
            raise _error()
        optional = _OPTIONAL_LOCATOR.fullmatch(draft.field_locator)
        if not (_REQ_LOCATOR.fullmatch(draft.field_locator) or optional):
            raise _error()
        if optional:
            encoded_group = optional.group(1)
            if quote(unquote(encoded_group), safe="A-Za-z0-9._-") != encoded_group:
                raise _error()
        locator = f"{path}:{draft.field_locator}"
    if not 1 <= len(locator) <= 2048:
        raise _error()
    return locator


def _diagnostic_valid(item: ParserDiagnostic, manifests: dict[str, ParsedManifest]) -> None:
    if (
        type(item) is not ParserDiagnostic
        or item.code not in _MESSAGES
        or item.severity != _DIAGNOSTIC_SEVERITY[item.code]
        or item.message != _MESSAGES[item.code]
        or _SENSITIVE.search(item.message)
        or type(item.manifest_path) is not str
        or item.manifest_path not in manifests
        or not _relative_path(item.manifest_path)
    ):
        raise _error()
    manifest = manifests[item.manifest_path]
    if manifest.kind is ManifestKind.REQUIREMENTS:
        if item.code in {"manifest_toml_invalid", "manifest_field_invalid", "pyproject_dynamic_dependencies_unsupported", "pyproject_tool_table_unsupported"}:
            raise _error()
        if item.field_locator is not None:
            raise _error()
        if item.code == "manifest_encoding_invalid":
            if item.start_line is not None or item.end_line is not None:
                raise _error()
        elif (
            type(item.start_line) is not int
            or type(item.end_line) is not int
            or item.start_line < 1
            or item.end_line < item.start_line
        ):
            raise _error()
        return
    if manifest.kind is not ManifestKind.PYPROJECT or item.start_line is not None or item.end_line is not None:
        raise _error()
    if item.code in {"manifest_logical_line_too_long", "requirement_include_unsupported", "requirement_constraint_unsupported", "requirement_editable_unsupported", "requirement_option_unsupported", "requirement_unnamed_reference_unsupported"}:
        raise _error()
    if item.code in {"manifest_encoding_invalid", "manifest_toml_invalid"}:
        if item.field_locator is not None:
            raise _error()
    elif type(item.field_locator) is not str or not (
        _PYPROJECT_DIAGNOSTIC_LOCATOR.fullmatch(item.field_locator)
        or _REQ_LOCATOR.fullmatch(item.field_locator)
        or _OPTIONAL_LOCATOR.fullmatch(item.field_locator)
    ):
        raise _error()


def _exact_version(declaration: PythonDependencyDeclaration, conflicted: bool) -> str | None:
    if conflicted or declaration.source_kind is not DependencySourceKind.INDEX or declaration.direct_reference is not None or declaration.marker is not None:
        return None
    specifier = declaration.version_specifier
    matched = re.fullmatch(r"==([^,*]+)", specifier or "")
    if matched is None or "*" in matched.group(1):
        return None
    try:
        if Version is None:
            raise _error()
        return str(Version(matched.group(1)))
    except IngestionSecurityError:
        raise
    except InvalidVersion:
        return None


def _dependency_valid(declaration: PythonDependencyDeclaration, manifests: dict[str, ParsedManifest]) -> None:
    if type(declaration) is not PythonDependencyDeclaration or type(declaration.evidence) is not tuple or not declaration.evidence:
        raise _error()
    if (
        type(declaration.normalized_name) is not str
        or not re.fullmatch(r"[a-z0-9]+(?:[-_.][a-z0-9]+)*", declaration.normalized_name)
        or type(declaration.declared_name) is not str
        or not declaration.declared_name
        or not _NAME.fullmatch(declaration.declared_name)
        or canonicalize_name is None
        or canonicalize_name(declaration.declared_name) != declaration.normalized_name
        or declaration.version_specifier is not None and type(declaration.version_specifier) is not str
        or declaration.marker is not None and type(declaration.marker) is not str
        or type(declaration.extras) is not tuple
        or any(type(item) is not str or not _NAME.fullmatch(item) or canonicalize_name is None or canonicalize_name(item) != item for item in declaration.extras)
        or tuple(declaration.extras) != tuple(sorted(set(declaration.extras), key=lambda item: item.encode("utf-8")))
        or type(declaration.scope) is not DependencyScope
        or type(declaration.source_kind) is not DependencySourceKind
        or declaration.group is not None and (type(declaration.group) is not str or not _NAME.fullmatch(declaration.group) or canonicalize_name is None or canonicalize_name(declaration.group) != declaration.group)
        or declaration.scope is DependencyScope.OPTIONAL and not declaration.group
        or declaration.scope is not DependencyScope.OPTIONAL and declaration.group is not None
        or type(declaration.hashes) is not tuple
        or any(type(item) is not str or not _SHA256.fullmatch(item) for item in declaration.hashes)
        or tuple(declaration.hashes) != tuple(sorted(set(declaration.hashes)))
        or type(declaration.raw_declaration) is not str
        or not 1 <= len(declaration.raw_declaration) <= 1000
        or type(declaration.source_manifest) is not str
        or declaration.source_manifest not in manifests
    ):
        raise _error()
    if declaration.source_kind is DependencySourceKind.INDEX and declaration.direct_reference is not None:
        raise _error()
    if declaration.source_kind is not DependencySourceKind.INDEX:
        reference = _canonical_reference(declaration.direct_reference) if type(declaration.direct_reference) is str else None
        if reference is None or reference != (declaration.direct_reference, declaration.source_kind) or declaration.version_specifier is not None:
            raise _error()
    elif declaration.version_specifier is not None:
        try:
            if SpecifierSet is None or str(SpecifierSet(declaration.version_specifier)) != declaration.version_specifier:
                raise _error()
        except IngestionSecurityError:
            raise
        except InvalidSpecifier as error:
            raise _error() from error
    if declaration.marker is not None:
        try:
            if Marker is None or str(Marker(declaration.marker)) != declaration.marker:
                raise _error()
        except IngestionSecurityError:
            raise
        except InvalidMarker as error:
            raise _error() from error
    canonical_name = declaration.normalized_name + ("[" + ",".join(declaration.extras) + "]" if declaration.extras else "")
    raw = f"{canonical_name} @ {declaration.direct_reference}" if declaration.direct_reference else canonical_name + (declaration.version_specifier or "")
    if declaration.marker:
        raw += f" ; {declaration.marker}"
    raw += "".join(f" --hash=sha256:{item}" for item in declaration.hashes)
    if declaration.raw_declaration != raw:
        raise _error()
    for draft in declaration.evidence:
        if type(draft) is not ManifestEvidenceDraft or draft.manifest_path not in manifests:
            raise _error()
        manifest = manifests[draft.manifest_path]
        if draft.content_sha256 != manifest.content_sha256 or not _SHA256.fullmatch(draft.content_sha256):
            raise _error()
        if type(draft.excerpt) is not str or not draft.excerpt or len(draft.excerpt) > 1000 or _SENSITIVE.search(draft.excerpt) or draft.excerpt != declaration.raw_declaration[:512]:
            raise _error()
        _locator(draft, manifest)
        if (manifest.kind is ManifestKind.REQUIREMENTS) != (draft.field_locator is None):
            raise _error()
        if manifest.kind is ManifestKind.REQUIREMENTS and (
            declaration.scope is not DependencyScope.RUNTIME or declaration.group is not None
        ):
            raise _error()
        if draft.field_locator is not None:
            optional = _OPTIONAL_LOCATOR.fullmatch(draft.field_locator)
            if declaration.scope is DependencyScope.RUNTIME and not _REQ_LOCATOR.fullmatch(draft.field_locator):
                raise _error()
            if declaration.scope is DependencyScope.BUILD and not draft.field_locator.startswith("build-system.requires["):
                raise _error()
            if declaration.scope is DependencyScope.OPTIONAL and (
                optional is None or canonicalize_name is None or canonicalize_name(unquote(optional.group(1))) != declaration.group
            ):
                raise _error()
    if declaration.source_manifest != min((draft.manifest_path for draft in declaration.evidence), key=lambda value: value.encode("utf-8")):
        raise _error()


def _conflicted(declarations: tuple[PythonDependencyDeclaration, ...], declaration: PythonDependencyDeclaration) -> bool:
    group = [item for item in declarations if (item.normalized_name, item.scope, item.group) == (declaration.normalized_name, declaration.scope, declaration.group)]
    exact_or_direct = {item.direct_reference for item in group if item.direct_reference} | {
        item.version_specifier
        for item in group
        if item.version_specifier and re.fullmatch(r"==[^,*]+", item.version_specifier) and "*" not in item.version_specifier
    }
    return len(exact_or_direct) > 1


def _declaration_sort_key(item: PythonDependencyDeclaration) -> tuple[bytes, ...]:
    values: tuple[object, ...] = (
        item.normalized_name, item.scope.value, item.group, item.extras, item.version_specifier,
        item.marker, item.source_kind.value, item.direct_reference, item.hashes,
    )
    return tuple(
        b"" if value is None else b"\0".join(str(part).encode("utf-8") for part in value) if isinstance(value, tuple) else str(value).encode("utf-8")
        for value in values
    )


def map_python_manifest_result(result: PythonManifestParseResult, *, root_digest: str, observed_at: datetime) -> PythonP0MappingResult:
    """Map a parser result without reading files, changing diagnostics, or using clocks."""
    try:
        manifests = _validate_context(result, root_digest, observed_at)
        if any(type(item) is not PythonDependencyDeclaration for item in result.dependencies):
            raise _error()
        if tuple(result.dependencies) != tuple(sorted(result.dependencies, key=_declaration_sort_key)):
            raise _error()
        identities = {
            (
                item.normalized_name, item.scope, item.group, item.extras, item.version_specifier,
                item.marker, item.source_kind, item.direct_reference, item.hashes,
            )
            for item in result.dependencies
        }
        if len(identities) != len(result.dependencies):
            raise _error()
        evidence_by_id: dict[str, Evidence] = {}
        evidence_for_declaration: dict[int, list[str]] = {}
        seen_locator: dict[tuple[str, int | None, int | None], tuple[str, str]] = {}
        for index, declaration in enumerate(result.dependencies):
            _dependency_valid(declaration, manifests)
            if len(set(declaration.evidence)) != len(declaration.evidence):
                raise _error()
            if tuple(declaration.evidence) != tuple(sorted(declaration.evidence, key=lambda value: (value.manifest_path.encode("utf-8"), (value.field_locator or "").encode("utf-8"), value.start_line if value.start_line is not None else -1, value.end_line if value.end_line is not None else -1, value.content_sha256))):
                raise _error()
            ids: list[str] = []
            for draft in declaration.evidence:
                manifest = manifests[draft.manifest_path]
                locator = _locator(draft, manifest)
                key = (locator, draft.start_line, draft.end_line)
                prior = seen_locator.get(key)
                if prior is not None and prior != (draft.content_sha256, draft.excerpt):
                    raise _error()
                seen_locator[key] = (draft.content_sha256, draft.excerpt)
                material: list[object] = ["evidence", "v1", root_digest, locator, draft.start_line, draft.end_line, draft.content_sha256, draft.excerpt]
                evidence_id = _uuid("evd", material)
                item = Evidence(
                    id=evidence_id, kind=EvidenceKind.MANIFEST_FIELD, locator=locator, excerpt=draft.excerpt,
                    start_line=draft.start_line, end_line=draft.end_line,
                    content_hash=HashValue(algorithm="sha256", value=draft.content_sha256),
                    detected_by=DetectionMethod.MANIFEST_PARSER,
                    producer=ProducerRef(type=ProducerType.PARSER, name="openguard-python-manifest-parser", version="0.1.0"),
                    observed_at=observed_at, verification_status=VerificationStatus.VERIFIED,
                )
                previous = evidence_by_id.get(evidence_id)
                if previous is not None and previous != item:
                    raise _error()
                evidence_by_id[evidence_id] = item
                ids.append(evidence_id)
            evidence_for_declaration[index] = sorted(set(ids))

        components_by_key: dict[tuple[str, str | None], dict[str, object]] = {}
        component_material_by_id: dict[str, tuple[str, str | None]] = {}
        for index, declaration in enumerate(result.dependencies):
            version = _exact_version(declaration, _conflicted(result.dependencies, declaration))
            key = (declaration.normalized_name, version)
            group = components_by_key.setdefault(key, {"declarations": [], "evidence_ids": set()})
            group["declarations"].append(declaration)  # type: ignore[index]
            group["evidence_ids"].update(evidence_for_declaration[index])  # type: ignore[index]
        components: list[Component] = []
        for (name, version), group in components_by_key.items():
            declarations = group["declarations"]  # type: ignore[assignment]
            direct_urls = {item.direct_reference for item in declarations if item.source_kind is DependencySourceKind.DIRECT_URL}
            source_url = next(iter(direct_urls)) if len(direct_urls) == 1 and len(direct_urls) == len({item.direct_reference for item in declarations}) and all(item.source_kind is DependencySourceKind.DIRECT_URL for item in declarations) else None
            component_id = _uuid("cmp", ["component", "v1", root_digest, "pypi", name, version])
            prior_material = component_material_by_id.get(component_id)
            if prior_material is not None and prior_material != (name, version):
                raise _error()
            component_material_by_id[component_id] = (name, version)
            components.append(Component(
                id=component_id, name=name, version=version, ecosystem="pypi", component_type=ComponentType.LIBRARY,
                purl=None, source_url=source_url, license_expression_id=None,
                evidence_ids=sorted(group["evidence_ids"]), detected_by=[DetectionMethod.MANIFEST_PARSER], confidence=1.0,
            ))
        evidence = sorted(evidence_by_id.values(), key=lambda item: (item.locator.encode("utf-8"), item.start_line or 0, item.end_line or 0, item.content_hash.value if item.content_hash else "", (item.excerpt or "").encode("utf-8"), item.id))
        components.sort(key=lambda item: (item.ecosystem.encode("utf-8"), item.name.encode("utf-8"), (item.version or "").encode("utf-8"), (item.purl or "").encode("utf-8"), (item.source_url or "").encode("utf-8"), item.id))
        return PythonP0MappingResult(MAPPER_SCHEMA_VERSION, result.status, tuple(components), tuple(evidence), result.diagnostics)
    except IngestionSecurityError:
        raise
    except Exception as error:
        raise _error() from error
