"""Deterministic P0 mapping for frozen JavaScript manifest DTOs."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.domain.models import Component, ComponentType, DetectionMethod, Evidence, EvidenceKind, HashValue, ProducerRef, ProducerType, VerificationStatus
from app.scanners.javascript_manifest import (
    JavascriptDependencyDeclaration, JavascriptEvidenceDraft, JavascriptManifestParseResult,
    JavascriptDependencyScope, JavascriptManifestKind, JavascriptParseStatus, JavascriptParserDiagnostic,
    ParsedJavascriptManifest, _MESSAGES, _SEVERITY, _canonical_url, _exact, _name, _selector,
)
from app.security.errors import IngestionSecurityError


MAPPER_SCHEMA_VERSION = "b1-javascript-p0/v1"
JAVASCRIPT_P0_NAMESPACE = uuid.UUID("2cda82be-8c98-5d1e-8078-0e18c6ec3bd5")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SENSITIVE = re.compile(r"(?i)(?:api[_-]?key|secret|token|password)\s*[=:]")
_SOURCE_FIELDS = frozenset({"dependencies", "devDependencies", "optionalDependencies", "peerDependencies"})
_DOCUMENT_FAILURE_CODES = frozenset({"manifest_encoding_invalid", "manifest_json_invalid", "manifest_duplicate_key"})
_PACKAGE_DIAGNOSTICS = frozenset({"manifest_encoding_invalid", "manifest_json_invalid", "manifest_duplicate_key", "manifest_field_invalid", "package_name_invalid", "dependency_selector_unsafe", "dependency_duplicate", "dependency_declaration_conflict"})
_LOCK_DIAGNOSTICS = frozenset({"lockfile_version_unsupported", "lock_root_mismatch", "lock_entry_invalid", "lock_entry_missing", "lock_version_conflict"})


@dataclass(frozen=True)
class JavascriptP0MappingResult:
    schema_version: str
    status: JavascriptParseStatus
    components: tuple[Component, ...]
    evidence: tuple[Evidence, ...]
    diagnostics: tuple[JavascriptParserDiagnostic, ...]


def _error() -> IngestionSecurityError:
    return IngestionSecurityError("scanner_failed", "javascript_p0_mapper_failed")


def _uuid(prefix: str, material: list[object]) -> str:
    return f"{prefix}_{uuid.uuid5(JAVASCRIPT_P0_NAMESPACE, json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(',', ':')))}"


def _valid_path(path: object) -> bool:
    return type(path) is str and bool(path) and not path.startswith("/") and "\\" not in path and all(part and part not in {".", ".."} for part in path.split("/"))


def _valid_locator(value: object, path: str) -> bool:
    if type(value) is not str or not value.startswith(path + ":/"):
        return False
    for token in value.removeprefix(path + ":/").split("/"):
        if not token:
            return False
        index = 0
        while index < len(token):
            if token[index] == "~":
                if index + 1 == len(token) or token[index + 1] not in {"0", "1"}:
                    return False
                index += 2
            else:
                index += 1
    return True


def _pointer_tokens(value: str, path: str) -> tuple[str, ...] | None:
    if not _valid_locator(value, path):
        return None
    decoded: list[str] = []
    for token in value.removeprefix(path + ":/").split("/"):
        output: list[str] = []
        index = 0
        while index < len(token):
            if token[index] == "~":
                output.append("~" if token[index + 1] == "0" else "/")
                index += 2
            else:
                output.append(token[index])
                index += 1
        decoded.append("".join(output))
    return tuple(decoded)


def _expected_kind(path: str) -> JavascriptManifestKind | None:
    filename = path.rsplit("/", 1)[-1]
    if filename == "package.json":
        return JavascriptManifestKind.PACKAGE_JSON
    if filename == "package-lock.json":
        return JavascriptManifestKind.PACKAGE_LOCK
    return None


def _compact_string(value: object) -> str | None:
    if type(value) is not str:
        return None
    canonical = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return canonical


def _valid_diagnostic(item: JavascriptParserDiagnostic, manifests: dict[str, ParsedJavascriptManifest]) -> None:
    if (
        type(item) is not JavascriptParserDiagnostic or item.code not in _MESSAGES
        or item.severity != _SEVERITY[item.code] or item.message != _MESSAGES[item.code]
        or _SENSITIVE.search(item.message) or item.manifest_path not in manifests
        or item.start_line is not None or item.end_line is not None
        or item.field_locator is not None and not _valid_locator(item.field_locator, item.manifest_path)
    ):
        raise _error()
    manifest = manifests[item.manifest_path]
    if item.code in _PACKAGE_DIAGNOSTICS and manifest.kind is not JavascriptManifestKind.PACKAGE_JSON:
        raise _error()
    if item.code in _LOCK_DIAGNOSTICS and manifest.kind is not JavascriptManifestKind.PACKAGE_LOCK:
        raise _error()
    if item.code in _DOCUMENT_FAILURE_CODES and item.field_locator is not None:
        raise _error()
    if item.code == "lock_root_mismatch" and item.field_locator is not None:
        raise _error()
    if item.code in {"dependency_duplicate", "dependency_declaration_conflict"}:
        tokens = _pointer_tokens(item.field_locator, item.manifest_path) if item.field_locator else None
        if tokens is None or len(tokens) != 2 or tokens[0] not in _SOURCE_FIELDS or not _name(tokens[1]):
            raise _error()


def _manifest_status_is_valid(manifest: ParsedJavascriptManifest, diagnostics: tuple[JavascriptParserDiagnostic, ...]) -> bool:
    document_failure = any(
        item.manifest_path == manifest.relative_path
        and (item.code in _DOCUMENT_FAILURE_CODES or (item.code == "manifest_field_invalid" and item.field_locator is None))
        for item in diagnostics
    )
    return manifest.status is (JavascriptParseStatus.PARTIAL if document_failure else JavascriptParseStatus.COMPLETE)


def _purl(name: str, version: str | None) -> str:
    base = name.replace("@", "%40", 1) if name.startswith("@") else name
    return f"pkg:npm/{base}" + (f"@{version}" if version else "")


def map_javascript_manifest_result(result: JavascriptManifestParseResult, *, root_digest: str, observed_at: datetime) -> JavascriptP0MappingResult:
    """Map parser DTOs without I/O, clocks, npm resolution, or network access."""
    try:
        if type(result) is not JavascriptManifestParseResult or result.schema_version != "b1-javascript-manifest/v1" or type(root_digest) is not str or not _SHA256.fullmatch(root_digest):
            raise _error()
        if type(observed_at) is not datetime or observed_at.tzinfo is None or observed_at.utcoffset() != timezone.utc.utcoffset(observed_at):
            raise _error()
        if type(result.status) is not JavascriptParseStatus or not all(type(item) is tuple for item in (result.manifests, result.dependencies, result.diagnostics)):
            raise _error()
        if (result.diagnostics and result.status is not JavascriptParseStatus.PARTIAL) or (not result.diagnostics and result.status is not JavascriptParseStatus.COMPLETE):
            raise _error()
        if any(type(item) is not ParsedJavascriptManifest for item in result.manifests):
            raise _error()
        paths: dict[str, ParsedJavascriptManifest] = {}
        for manifest in result.manifests:
            if (
                not _valid_path(manifest.relative_path) or manifest.relative_path in paths
                or type(manifest.size_bytes) is not int or manifest.size_bytes < 0
                or type(manifest.content_sha256) is not str or not _SHA256.fullmatch(manifest.content_sha256)
                or type(manifest.status) is not JavascriptParseStatus or type(manifest.kind) is not JavascriptManifestKind
                or _expected_kind(manifest.relative_path) is not manifest.kind
            ):
                raise _error()
            paths[manifest.relative_path] = manifest
        if tuple(item.relative_path for item in result.manifests) != tuple(sorted(paths, key=lambda path: path.encode("utf-8"))):
            raise _error()
        for diagnostic in result.diagnostics:
            _valid_diagnostic(diagnostic, paths)
        if tuple(result.diagnostics) != tuple(sorted(result.diagnostics, key=lambda item: (item.manifest_path.encode("utf-8"), (item.field_locator or "").encode("utf-8"), item.code, item.severity))):
            raise _error()
        if not all(_manifest_status_is_valid(manifest, result.diagnostics) for manifest in result.manifests):
            raise _error()
        if any(type(item) is not JavascriptDependencyDeclaration for item in result.dependencies) or tuple(result.dependencies) != tuple(sorted(result.dependencies, key=lambda item: (item.normalized_name.encode("utf-8"), item.scope.value, item.requested_spec.encode("utf-8")))):
            raise _error()
        evidence_by_id: dict[str, Evidence] = {}
        components: list[Component] = []
        seen_names: set[str] = set()
        for declaration in result.dependencies:
            if type(declaration) is not JavascriptDependencyDeclaration or type(declaration.evidence) is not tuple or not declaration.evidence:
                raise _error()
            if (
                declaration.normalized_name != declaration.declared_name or not _name(declaration.normalized_name)
                or declaration.normalized_name in seen_names or declaration.source_manifest not in paths
                or paths[declaration.source_manifest].kind is not JavascriptManifestKind.PACKAGE_JSON
            ):
                raise _error()
            seen_names.add(declaration.normalized_name)
            if (
                declaration.lock_manifest is not None
                and (
                    declaration.lock_manifest not in paths
                    or paths[declaration.lock_manifest].kind is not JavascriptManifestKind.PACKAGE_LOCK
                    or declaration.lock_manifest != declaration.source_manifest.removesuffix("package.json") + "package-lock.json"
                )
            ):
                raise _error()
            if not _selector(declaration.requested_spec) or type(declaration.scope) is not JavascriptDependencyScope:
                raise _error()
            if declaration.resolved_version is not None and _exact(declaration.resolved_version) != declaration.resolved_version:
                raise _error()
            if declaration.resolved_url is not None and _canonical_url(declaration.resolved_url) != declaration.resolved_url:
                raise _error()
            if declaration.lock_manifest is None and declaration.resolved_url is not None:
                raise _error()
            if len(set(declaration.evidence)) != len(declaration.evidence) or tuple(declaration.evidence) != tuple(sorted(declaration.evidence, key=lambda item: (item.field_locator.encode("utf-8"), item.content_sha256, item.excerpt.encode("utf-8")))):
                raise _error()
            ids: list[str] = []
            has_source_evidence = False
            lock_version: str | None = None
            lock_url: str | None = None
            for draft in declaration.evidence:
                if type(draft) is not JavascriptEvidenceDraft or draft.manifest_path not in paths or not _valid_locator(draft.field_locator, draft.manifest_path) or not _SHA256.fullmatch(draft.content_sha256) or paths[draft.manifest_path].content_sha256 != draft.content_sha256 or type(draft.excerpt) is not str or not draft.excerpt or len(draft.excerpt) > 512 or _SENSITIVE.search(draft.excerpt):
                    raise _error()
                tokens = _pointer_tokens(draft.field_locator, draft.manifest_path)
                if tokens is None:
                    raise _error()
                if draft.manifest_path == declaration.source_manifest:
                    if len(tokens) != 2 or tokens[0] not in _SOURCE_FIELDS or tokens[1] != declaration.normalized_name:
                        raise _error()
                    try:
                        excerpt_value = json.loads(draft.excerpt)
                    except (TypeError, ValueError, json.JSONDecodeError):
                        raise _error()
                    if _compact_string(excerpt_value) != draft.excerpt or not _selector(excerpt_value):
                        raise _error()
                    has_source_evidence = True
                elif draft.manifest_path == declaration.lock_manifest:
                    expected_package = "node_modules/" + declaration.normalized_name
                    if len(tokens) != 3 or tokens[:2] != ("packages", expected_package) or tokens[2] not in {"version", "resolved"}:
                        raise _error()
                    try:
                        excerpt_value = json.loads(draft.excerpt)
                    except (TypeError, ValueError, json.JSONDecodeError):
                        raise _error()
                    if _compact_string(excerpt_value) != draft.excerpt:
                        raise _error()
                    if tokens[2] == "version":
                        if _exact(excerpt_value) != excerpt_value or lock_version is not None:
                            raise _error()
                        lock_version = excerpt_value
                    else:
                        if _canonical_url(excerpt_value) != excerpt_value or lock_url is not None:
                            raise _error()
                        lock_url = excerpt_value
                else:
                    raise _error()
                evidence_id = _uuid("evd", ["javascript-evidence", root_digest, draft.field_locator, draft.content_sha256, draft.excerpt])
                evidence = Evidence(id=evidence_id, kind=EvidenceKind.MANIFEST_FIELD, locator=draft.field_locator, excerpt=draft.excerpt, start_line=None, end_line=None, content_hash=HashValue(algorithm="sha256", value=draft.content_sha256), detected_by=DetectionMethod.MANIFEST_PARSER, producer=ProducerRef(type=ProducerType.PARSER, name="openguard.javascript-manifest", version="b1-javascript-manifest/v1", config_digest=HashValue(algorithm="sha256", value=root_digest)), observed_at=observed_at, verification_status=VerificationStatus.VERIFIED)
                if evidence_id in evidence_by_id and evidence_by_id[evidence_id] != evidence:
                    raise _error()
                evidence_by_id[evidence_id] = evidence
                ids.append(evidence_id)
            if not has_source_evidence or (lock_version is not None and declaration.resolved_version != lock_version) or (lock_url is not None and declaration.resolved_url != lock_url):
                raise _error()
            version = declaration.resolved_version
            component_id = _uuid("cmp", ["javascript-component", root_digest, declaration.normalized_name, declaration.scope.value, declaration.requested_spec, version, declaration.resolved_url])
            components.append(Component(id=component_id, name=declaration.normalized_name, version=version, ecosystem="npm", component_type=ComponentType.LIBRARY, purl=_purl(declaration.normalized_name, version), source_url=declaration.resolved_url, license_expression_id=None, evidence_ids=sorted(set(ids)), detected_by=[DetectionMethod.MANIFEST_PARSER], confidence=1.0))
        evidence = sorted(evidence_by_id.values(), key=lambda item: (item.locator.encode("utf-8"), item.content_hash.value if item.content_hash else "", (item.excerpt or "").encode("utf-8"), item.id))
        components.sort(key=lambda item: (item.ecosystem.encode("utf-8"), item.name.encode("utf-8"), (item.version or "").encode("utf-8"), (item.purl or "").encode("utf-8"), (item.source_url or "").encode("utf-8"), item.id))
        return JavascriptP0MappingResult(MAPPER_SCHEMA_VERSION, result.status, tuple(components), tuple(evidence), result.diagnostics)
    except IngestionSecurityError:
        raise
    except Exception as error:
        raise _error() from error
