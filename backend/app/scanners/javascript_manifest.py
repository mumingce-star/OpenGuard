"""Bounded, non-executing JavaScript manifest parsing over an A2 session."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

from app.ingestion import ReadOnlyScanSession
from app.security.errors import IngestionSecurityError


_MAX_CANDIDATES = 64
_MAX_FILE = 2 * 1024 * 1024
_MAX_TOTAL = 8 * 1024 * 1024
_MAX_DEPTH = 64
_MAX_STRING = 8192
_MAX_DECLARATIONS = 4096
_IGNORED = frozenset({".git", ".hg", ".svn", ".venv", "venv", "__pycache__", "site-packages", "node_modules"})
_NAME_TOKEN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,213}$")
_EXACT = re.compile(r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$")
_SENSITIVE = re.compile(r"(?i)(?:api[_-]?key|secret|token|password)\s*[=:]")


class JavascriptManifestKind(str, Enum):
    PACKAGE_JSON = "package_json"
    PACKAGE_LOCK = "package_lock"


class JavascriptDependencyScope(str, Enum):
    RUNTIME = "runtime"
    DEVELOPMENT = "development"
    OPTIONAL = "optional"
    PEER = "peer"


class JavascriptParseStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"


@dataclass(frozen=True)
class JavascriptEvidenceDraft:
    manifest_path: str
    field_locator: str
    content_sha256: str
    excerpt: str


@dataclass(frozen=True)
class ParsedJavascriptManifest:
    relative_path: str
    kind: JavascriptManifestKind
    size_bytes: int
    content_sha256: str
    status: JavascriptParseStatus


@dataclass(frozen=True)
class JavascriptDependencyDeclaration:
    normalized_name: str
    declared_name: str
    requested_spec: str
    resolved_version: str | None
    scope: JavascriptDependencyScope
    source_manifest: str
    lock_manifest: str | None
    resolved_url: str | None
    evidence: tuple[JavascriptEvidenceDraft, ...]


@dataclass(frozen=True)
class JavascriptParserDiagnostic:
    code: str
    severity: str
    manifest_path: str
    field_locator: str | None
    start_line: None
    end_line: None
    message: str


@dataclass(frozen=True)
class JavascriptManifestParseResult:
    schema_version: str
    status: JavascriptParseStatus
    manifests: tuple[ParsedJavascriptManifest, ...]
    dependencies: tuple[JavascriptDependencyDeclaration, ...]
    diagnostics: tuple[JavascriptParserDiagnostic, ...]


_MESSAGES = {
    "manifest_encoding_invalid": "Manifest text is not valid UTF-8.",
    "manifest_json_invalid": "Manifest JSON is invalid.",
    "manifest_duplicate_key": "Manifest JSON contains a duplicate key.",
    "manifest_field_invalid": "Manifest dependency field has an unsupported type.",
    "package_name_invalid": "Package name is invalid or unsupported.",
    "dependency_selector_unsafe": "Dependency selector is unsafe or unsupported.",
    "lockfile_version_unsupported": "Package lock version is unsupported.",
    "lock_root_mismatch": "Package lock root dependencies do not match package.json.",
    "lock_entry_invalid": "Package lock entry is invalid.",
    "lock_entry_missing": "Package lock entry is missing.",
    "lock_version_conflict": "Declared and locked dependency versions conflict.",
    "dependency_duplicate": "Duplicate dependency declaration was merged.",
    "dependency_declaration_conflict": "Dependency declarations conflict.",
}
_SEVERITY = {key: "warning" for key in ("lock_entry_missing", "dependency_duplicate")}
_SEVERITY.update({key: "error" for key in _MESSAGES if key not in _SEVERITY})
_FIELDS = (
    ("dependencies", JavascriptDependencyScope.RUNTIME),
    ("devDependencies", JavascriptDependencyScope.DEVELOPMENT),
    ("optionalDependencies", JavascriptDependencyScope.OPTIONAL),
    ("peerDependencies", JavascriptDependencyScope.PEER),
)
_PRIORITY = {JavascriptDependencyScope.OPTIONAL: 0, JavascriptDependencyScope.RUNTIME: 1, JavascriptDependencyScope.DEVELOPMENT: 2, JavascriptDependencyScope.PEER: 3}


class _DuplicateKey(ValueError):
    pass


def _failure(reason: str) -> IngestionSecurityError:
    return IngestionSecurityError("scanner_failed", reason)


def _diag(code: str, path: str, locator: str | None = None) -> JavascriptParserDiagnostic:
    return JavascriptParserDiagnostic(code, _SEVERITY[code], path, locator, None, None, _MESSAGES[code])


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _locator(path: str, *tokens: str) -> str:
    return path + ":/" + "/".join(_escape(token) for token in tokens)


def _name(value: object) -> bool:
    if type(value) is not str or len(value) > 214:
        return False
    if value.startswith("@"):
        parts = value[1:].split("/")
        return len(parts) == 2 and bool(parts[0]) and bool(parts[1]) and all(_NAME_TOKEN.fullmatch(part) for part in parts)
    return bool(_NAME_TOKEN.fullmatch(value))


def _exact(value: object) -> str | None:
    if type(value) is not str:
        return None
    matched = _EXACT.fullmatch(value)
    if not matched:
        return None
    return value[1:] if value.startswith("v") else value


def _selector(value: object) -> bool:
    if type(value) is not str or not 1 <= len(value) <= 200 or _SENSITIVE.search(value):
        return False
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 or char == "\\" for char in value):
        return False
    lowered = value.lower()
    return not (
        "://" in value or lowered.startswith(("file:", "link:", "workspace:", "npm:", "git", "http:", "https:", "ssh:"))
        or value.startswith(("/", "./", "../", "~/"))
    )


def _canonical_url(value: object) -> str | None:
    if type(value) is not str or len(value) > 1000 or _SENSITIVE.search(value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            return None
        if any(unquote(segment) in {".", ".."} for segment in parsed.path.split("/")):
            return None
        host = parsed.hostname.encode("ascii").decode("ascii").lower()
        port = parsed.port
    except (UnicodeError, ValueError):
        return None
    netloc = f"[{host}]" if ":" in host else host
    if port and port != 443:
        netloc += f":{port}"
    canonical = urlunsplit(("https", netloc, parsed.path, "", ""))
    return canonical if canonical == value else None


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey()
        result[key] = value
    return result


def _reject_json_constant(_: str) -> None:
    raise ValueError("non-finite JSON number")


def _bounded(value: Any, depth: int = 0) -> None:
    if depth > _MAX_DEPTH:
        raise _failure("javascript_manifest_limit_exceeded")
    if type(value) is str:
        if len(value) > _MAX_STRING:
            raise _failure("javascript_manifest_limit_exceeded")
    elif type(value) is dict:
        for key, item in value.items():
            if type(key) is not str or len(key) > _MAX_STRING:
                raise _failure("javascript_manifest_limit_exceeded")
            _bounded(item, depth + 1)
    elif type(value) is list:
        for item in value:
            _bounded(item, depth + 1)


def _load(data: bytes, path: str) -> tuple[dict[str, Any] | None, JavascriptParserDiagnostic | None]:
    if data.startswith(b"\xef\xbb\xbf"):
        return None, _diag("manifest_encoding_invalid", path)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None, _diag("manifest_encoding_invalid", path)
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_reject_json_constant)
    except _DuplicateKey:
        return None, _diag("manifest_duplicate_key", path)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, _diag("manifest_json_invalid", path)
    _bounded(value)
    return (value, None) if type(value) is dict else (None, _diag("manifest_field_invalid", path))


def _candidate(path: str) -> JavascriptManifestKind | None:
    parts = path.split("/")
    if any(part in _IGNORED for part in parts[:-1]):
        return None
    if parts[-1] == "package.json":
        return JavascriptManifestKind.PACKAGE_JSON
    if parts[-1] == "package-lock.json":
        return JavascriptManifestKind.PACKAGE_LOCK
    return None


def _inventory(session: ReadOnlyScanSession) -> list[tuple[str, int, str, JavascriptManifestKind]]:
    candidates: list[tuple[str, int, str, JavascriptManifestKind]] = []
    seen: set[str] = set()
    for entry in session.inventory.entries:
        if type(entry.relative_path) is not str or type(entry.size_bytes) is not int or type(entry.sha256) is not str or entry.relative_path in seen or entry.size_bytes < 0 or not re.fullmatch(r"[0-9a-f]{64}", entry.sha256):
            raise _failure("javascript_manifest_parser_failed")
        seen.add(entry.relative_path)
        kind = _candidate(entry.relative_path)
        if kind is not None:
            candidates.append((entry.relative_path, entry.size_bytes, entry.sha256, kind))
    candidates.sort(key=lambda item: item[0].encode("utf-8"))
    if len(candidates) > _MAX_CANDIDATES or any(item[1] > _MAX_FILE for item in candidates) or sum(item[1] for item in candidates) > _MAX_TOTAL:
        raise _failure("javascript_manifest_limit_exceeded")
    return candidates


def _draft(path: str, field: str, name: str, sha: str, value: str) -> JavascriptEvidenceDraft:
    return JavascriptEvidenceDraft(path, _locator(path, field, name), sha, json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def parse_javascript_manifests(session: ReadOnlyScanSession) -> JavascriptManifestParseResult:
    """Parse only package.json/package-lock v2/v3 through the sealed capability."""
    try:
        documents: dict[str, tuple[dict[str, Any], str]] = {}
        manifests: list[ParsedJavascriptManifest] = []
        diagnostics: list[JavascriptParserDiagnostic] = []
        for path, size, sha, kind in _inventory(session):
            data = session.read_bytes(path, max_bytes=_MAX_FILE)
            if type(data) is not bytes or len(data) != size or hashlib.sha256(data).hexdigest() != sha:
                raise _failure("javascript_manifest_parser_failed")
            document, problem = _load(data, path)
            manifests.append(ParsedJavascriptManifest(path, kind, size, sha, JavascriptParseStatus.PARTIAL if problem else JavascriptParseStatus.COMPLETE))
            if problem:
                diagnostics.append(problem)
            elif document is not None:
                documents[path] = (document, sha)

        declarations: list[JavascriptDependencyDeclaration] = []
        package_fields: dict[str, dict[str, Any]] = {}
        for path, (document, sha) in documents.items():
            if _candidate(path) is not JavascriptManifestKind.PACKAGE_JSON:
                continue
            package_fields[path] = document
            for field, scope in _FIELDS:
                values = document.get(field, {})
                if values == {}:
                    continue
                if type(values) is not dict:
                    diagnostics.append(_diag("manifest_field_invalid", path, _locator(path, field)))
                    continue
                for name, selector in values.items():
                    locator = _locator(path, field, str(name))
                    if not _name(name):
                        diagnostics.append(_diag("package_name_invalid", path, locator if name else None)); continue
                    if not _selector(selector):
                        diagnostics.append(_diag("dependency_selector_unsafe", path, locator)); continue
                    declarations.append(JavascriptDependencyDeclaration(name, name, selector, _exact(selector), scope, path, None, None, (_draft(path, field, name, sha, selector),)))
        if len(declarations) > _MAX_DECLARATIONS:
            raise _failure("javascript_manifest_limit_exceeded")

        lock_data: dict[str, tuple[dict[str, Any], str]] = {path: value for path, value in documents.items() if _candidate(path) is JavascriptManifestKind.PACKAGE_LOCK}
        lock_bad: set[str] = set()
        for path, (document, _) in lock_data.items():
            version = document.get("lockfileVersion")
            packages = document.get("packages")
            if type(version) is not int or type(version) is bool or version not in {2, 3}:
                diagnostics.append(_diag("lockfile_version_unsupported", path)); lock_bad.add(path); continue
            if type(packages) is not dict or ("" in packages and type(packages[""]) is not dict):
                diagnostics.append(_diag("lock_entry_invalid", path)); lock_bad.add(path); continue
            package_path = path.removesuffix("package-lock.json") + "package.json"
            package = package_fields.get(package_path)
            root = packages.get("")
            if package is not None and type(root) is dict:
                for field, _ in _FIELDS:
                    if field in root and root[field] != package.get(field):
                        diagnostics.append(_diag("lock_root_mismatch", path)); lock_bad.add(path); break

        enriched: list[JavascriptDependencyDeclaration] = []
        for declaration in declarations:
            lock_path = declaration.source_manifest.removesuffix("package.json") + "package-lock.json"
            lock = lock_data.get(lock_path)
            if lock is None or lock_path in lock_bad:
                enriched.append(declaration); continue
            packages, lock_sha = lock[0]["packages"], lock[1]
            entry_path = "node_modules/" + declaration.normalized_name
            entry = packages.get(entry_path)
            if entry is None:
                diagnostics.append(_diag("lock_entry_missing", lock_path, _locator(lock_path, "packages", entry_path)))
                enriched.append(declaration); continue
            if type(entry) is not dict:
                diagnostics.append(_diag("lock_entry_invalid", lock_path, _locator(lock_path, "packages", entry_path))); enriched.append(declaration); continue
            version = _exact(entry.get("version")) if "version" in entry else None
            resolved = _canonical_url(entry.get("resolved")) if "resolved" in entry else None
            if ("version" in entry and version is None) or ("resolved" in entry and resolved is None):
                diagnostics.append(_diag("lock_entry_invalid", lock_path, _locator(lock_path, "packages", entry_path))); enriched.append(declaration); continue
            if declaration.resolved_version is not None and version is not None and declaration.resolved_version != version:
                diagnostics.append(_diag("lock_version_conflict", lock_path, _locator(lock_path, "packages", entry_path, "version")))
                enriched.append(replace(declaration, resolved_version=None)); continue
            evidence = list(declaration.evidence)
            if version is not None:
                evidence.append(JavascriptEvidenceDraft(lock_path, _locator(lock_path, "packages", entry_path, "version"), lock_sha, json.dumps(entry["version"], ensure_ascii=False, separators=(",", ":"))))
            if resolved is not None:
                evidence.append(JavascriptEvidenceDraft(lock_path, _locator(lock_path, "packages", entry_path, "resolved"), lock_sha, json.dumps(resolved, ensure_ascii=False, separators=(",", ":"))))
            enriched.append(replace(declaration, resolved_version=version or declaration.resolved_version, lock_manifest=lock_path, resolved_url=resolved, evidence=tuple(sorted(evidence, key=lambda item: (item.field_locator.encode("utf-8"), item.content_sha256, item.excerpt.encode("utf-8"))))))

        grouped: dict[str, list[JavascriptDependencyDeclaration]] = {}
        for item in enriched:
            grouped.setdefault(item.normalized_name, []).append(item)
        merged: list[JavascriptDependencyDeclaration] = []
        for name, values in grouped.items():
            values.sort(key=lambda item: (_PRIORITY[item.scope], item.requested_spec.encode("utf-8"), item.source_manifest.encode("utf-8")))
            selectors = {item.requested_spec for item in values}
            if len(values) > 1:
                chosen = values[0]
                evidence = tuple(sorted({draft for item in values for draft in item.evidence}, key=lambda item: (item.field_locator.encode("utf-8"), item.content_sha256, item.excerpt.encode("utf-8"))))
                code = "dependency_duplicate" if len(selectors) == 1 else "dependency_declaration_conflict"
                field = next(field for field, scope in _FIELDS if scope is chosen.scope)
                diagnostics.append(_diag(code, chosen.source_manifest, _locator(chosen.source_manifest, field, chosen.declared_name)))
                if code == "dependency_declaration_conflict":
                    chosen = replace(chosen, resolved_version=None, resolved_url=None)
                merged.append(replace(chosen, evidence=evidence))
            else:
                merged.append(values[0])
        diagnostics.sort(key=lambda item: (item.manifest_path.encode("utf-8"), (item.field_locator or "").encode("utf-8"), item.code, item.severity))
        manifests.sort(key=lambda item: item.relative_path.encode("utf-8"))
        merged.sort(key=lambda item: (item.normalized_name.encode("utf-8"), _PRIORITY[item.scope], item.requested_spec.encode("utf-8")))
        return JavascriptManifestParseResult("b1-javascript-manifest/v1", JavascriptParseStatus.PARTIAL if diagnostics else JavascriptParseStatus.COMPLETE, tuple(manifests), tuple(merged), tuple(diagnostics))
    except IngestionSecurityError:
        raise
    except Exception as error:
        raise _failure("javascript_manifest_parser_failed") from error
