"""Deterministic Python manifest parsing over a sealed read-only scan session.

This module deliberately has no filesystem, process, or network capability.  It
only consumes the inventory and ``read_bytes`` capability supplied by A2-2.
"""

from __future__ import annotations

import hashlib
import re
import tomllib
from dataclasses import dataclass
from enum import Enum
from typing import Iterable
from urllib.parse import parse_qsl, quote, unquote, urlsplit, urlunsplit

try:  # Import failure is converted to the frozen runtime reason at entrypoint.
    from packaging import __version__ as _packaging_version
    from packaging.requirements import InvalidRequirement, Requirement
    from packaging.utils import canonicalize_name
except ImportError:  # pragma: no cover - exercised in an environment without the lockfile dependency.
    _packaging_version = None
    InvalidRequirement = ValueError
    Requirement = None  # type: ignore[assignment,misc]
    canonicalize_name = None  # type: ignore[assignment]

from app.ingestion import ReadOnlyScanSession
from app.security.errors import IngestionSecurityError


_MAX_CANDIDATES = 64
_MAX_FILE_BYTES = 262_144
_MAX_TOTAL_BYTES = 4_194_304
_MAX_DECLARATIONS = 4_096
_MAX_LOGICAL_LINE = 8_192
_IGNORED_PARTS = frozenset({".git", ".hg", ".svn", ".venv", "venv", "__pycache__", "site-packages", "node_modules"})
_SAFE_FRAGMENT_SUBDIR = re.compile(r"^[^\\\x00-\x1f/][^\\\x00-\x1f]*$")
_HASH = re.compile(r"^[0-9a-fA-F]{64}$")


class ManifestKind(str, Enum):
    REQUIREMENTS = "requirements"
    PYPROJECT = "pyproject"


class DependencyScope(str, Enum):
    RUNTIME = "runtime"
    OPTIONAL = "optional"
    BUILD = "build"


class DependencySourceKind(str, Enum):
    INDEX = "index"
    DIRECT_URL = "direct_url"
    VCS = "vcs"


class ParseStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"


@dataclass(frozen=True)
class ManifestEvidenceDraft:
    manifest_path: str
    field_locator: str | None
    start_line: int | None
    end_line: int | None
    content_sha256: str
    excerpt: str


@dataclass(frozen=True)
class ParsedManifest:
    relative_path: str
    kind: ManifestKind
    size_bytes: int
    content_sha256: str
    status: ParseStatus


@dataclass(frozen=True)
class PythonDependencyDeclaration:
    normalized_name: str
    declared_name: str
    version_specifier: str | None
    marker: str | None
    extras: tuple[str, ...]
    direct_reference: str | None
    source_kind: DependencySourceKind
    scope: DependencyScope
    group: str | None
    hashes: tuple[str, ...]
    raw_declaration: str
    source_manifest: str
    evidence: tuple[ManifestEvidenceDraft, ...]


@dataclass(frozen=True)
class ParserDiagnostic:
    code: str
    severity: str
    manifest_path: str | None
    field_locator: str | None
    start_line: int | None
    end_line: int | None
    message: str


@dataclass(frozen=True)
class PythonManifestParseResult:
    schema_version: str
    status: ParseStatus
    manifests: tuple[ParsedManifest, ...]
    dependencies: tuple[PythonDependencyDeclaration, ...]
    diagnostics: tuple[ParserDiagnostic, ...]


_MESSAGES = {
    "manifest_encoding_invalid": "Manifest text is not valid UTF-8.",
    "manifest_toml_invalid": "Manifest TOML is invalid.",
    "manifest_field_invalid": "Manifest dependency field has an unsupported type.",
    "manifest_logical_line_too_long": "Manifest logical line exceeds the parser limit.",
    "requirement_invalid": "Requirement declaration is invalid.",
    "requirement_include_unsupported": "Requirement include directive is unsupported.",
    "requirement_constraint_unsupported": "Requirement constraint directive is unsupported.",
    "requirement_editable_unsupported": "Editable requirement directive is unsupported.",
    "requirement_option_unsupported": "Requirement option directive is unsupported.",
    "requirement_unnamed_reference_unsupported": "Unnamed requirement reference is unsupported.",
    "requirement_reference_unsafe": "Requirement reference is unsafe or unsupported.",
    "requirement_hash_invalid": "Requirement hash is invalid or unsupported.",
    "pyproject_dynamic_dependencies_unsupported": "Dynamic dependency declarations are unsupported.",
    "pyproject_tool_table_unsupported": "Tool-specific dependency declarations are unsupported.",
    "dependency_duplicate": "Duplicate dependency declaration was merged.",
    "dependency_declaration_conflict": "Dependency declarations conflict.",
    "dependency_multiple_constraints": "Dependency has multiple constraints.",
}


def _failure(reason: str) -> IngestionSecurityError:
    return IngestionSecurityError("scanner_failed", reason)


def _diag(code: str, path: str | None, locator: str | None = None, start: int | None = None, end: int | None = None, severity: str = "warning") -> ParserDiagnostic:
    return ParserDiagnostic(code, severity, path, locator, start, end, _MESSAGES[code])


def _is_candidate(path: str) -> ManifestKind | None:
    parts = path.split("/")
    if any(part in _IGNORED_PARTS for part in parts[:-1]):
        return None
    name = parts[-1]
    if name == "pyproject.toml":
        return ManifestKind.PYPROJECT
    if name.startswith("requirements") and name.endswith(".txt"):
        return ManifestKind.REQUIREMENTS
    return None


def _inventory_candidates(session: ReadOnlyScanSession) -> list[tuple[str, int, str, ManifestKind]]:
    candidates: list[tuple[str, int, str, ManifestKind]] = []
    seen_paths: set[str] = set()
    for entry in session.inventory.entries:
        if type(entry.relative_path) is not str or type(entry.size_bytes) is not int or type(entry.sha256) is not str:
            raise _failure("python_manifest_parser_failed")
        if entry.size_bytes < 0 or not re.fullmatch(r"[0-9a-f]{64}", entry.sha256):
            raise _failure("python_manifest_parser_failed")
        if entry.relative_path in seen_paths:
            raise _failure("python_manifest_parser_failed")
        seen_paths.add(entry.relative_path)
        kind = _is_candidate(entry.relative_path)
        if kind is not None:
            candidates.append((entry.relative_path, entry.size_bytes, entry.sha256, kind))
    candidates.sort(key=lambda value: value[0].encode("utf-8"))
    if len(candidates) > _MAX_CANDIDATES or any(value[1] > _MAX_FILE_BYTES for value in candidates) or sum(value[1] for value in candidates) > _MAX_TOTAL_BYTES:
        raise _failure("python_manifest_limit_exceeded")
    return candidates


def _logical_lines(text: str) -> Iterable[tuple[str, int, int, bool]]:
    # Only CRLF, LF, and bare CR are physical line endings.  In particular,
    # Unicode separators such as U+2028 remain untrusted declaration bytes.
    lines = re.split(r"\r\n|\n|\r", text)
    current: list[str] = []
    start = 1
    for number, line in enumerate(lines, 1):
        if not current:
            start = number
        stripped = line.rstrip(" \t")
        slash_count = len(stripped) - len(stripped.rstrip("\\"))
        if slash_count % 2:
            current.append(stripped[:-1])
            continue
        current.append(line)
        yield "".join(current), start, number, False
        current = []
    if current:
        yield "".join(current), start, len(lines) or 1, True


def _strip_comment(value: str) -> str:
    quote_char: str | None = None
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif quote_char:
            if char == quote_char:
                quote_char = None
        elif char in "'\"":
            quote_char = char
        elif char == "#" and index and value[index - 1] in " \t":
            return value[:index].rstrip(" \t")
    return value.rstrip(" \t")


def _canonical_reference(value: str) -> tuple[str, DependencySourceKind] | None:
    if any(ord(char) < 32 or char == "\\" for char in value):
        return None
    vcs = value.startswith("git+https://")
    raw = value[4:] if vcs else value
    parsed = urlsplit(raw)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query:
        return None
    try:
        hostname = parsed.hostname.encode("ascii").decode("ascii").lower()
    except UnicodeError:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    host = f"[{hostname}]" if ":" in hostname else hostname
    host += f":{port}" if port else ""
    fragments: list[tuple[str, str]] = []
    if parsed.fragment:
        try:
            fragments = parse_qsl(parsed.fragment, keep_blank_values=True, strict_parsing=True)
        except ValueError:
            return None
        for key, item in fragments:
            if key == "subdirectory":
                decoded = unquote(item)
                if (sum(1 for fragment_key, _ in fragments if fragment_key == "subdirectory") != 1
                    or not decoded or decoded.startswith("/")
                    or any(not part or part in {".", ".."} for part in decoded.split("/"))
                    or not _SAFE_FRAGMENT_SUBDIR.fullmatch(decoded)):
                    return None
            elif key == "sha256" and _HASH.fullmatch(item):
                pass
            else:
                return None
    fragment = "&".join(f"{quote(key, safe='') }={quote(item.lower() if key == 'sha256' else item, safe='/-_.')}" for key, item in sorted(fragments))
    canonical = urlunsplit(("https", host, parsed.path, "", fragment))
    if vcs:
        canonical = "git+" + canonical
    if len(canonical) > 1000:
        return None
    return canonical, DependencySourceKind.VCS if vcs else DependencySourceKind.DIRECT_URL


def _parse_requirement(value: str, *, path: str, locator: str | None, start: int | None, end: int | None, sha256: str, scope: DependencyScope, group: str | None, hashes: tuple[str, ...] = ()) -> tuple[PythonDependencyDeclaration | None, ParserDiagnostic | None]:
    if Requirement is None or canonicalize_name is None:
        raise _failure("python_manifest_parser_unavailable")
    try:
        requirement = Requirement(value)
    except InvalidRequirement:
        return None, _diag("requirement_invalid", path, locator, start, end, "error")
    direct: str | None = None
    source = DependencySourceKind.INDEX
    if requirement.url:
        reference = _canonical_reference(requirement.url)
        if reference is None:
            return None, _diag("requirement_reference_unsafe", path, locator, start, end, "error")
        direct, source = reference
    marker = str(requirement.marker) if requirement.marker is not None else None
    version_specifier = str(requirement.specifier) or None
    extras = tuple(sorted({canonicalize_name(extra) for extra in requirement.extras}, key=lambda item: item.encode("utf-8")))
    canonical_name = canonicalize_name(requirement.name) + ("[" + ",".join(extras) + "]" if extras else "")
    raw = f"{canonical_name} @ {direct}" if direct else canonical_name + (version_specifier or "")
    if marker:
        raw += f" ; {marker}"
    if hashes:
        raw += "".join(f" --hash=sha256:{item}" for item in hashes)
    if len(raw) > 1000:
        return None, _diag("requirement_invalid", path, locator, start, end, "error")
    evidence = ManifestEvidenceDraft(path, locator, start, end, sha256, raw[:512])
    return PythonDependencyDeclaration(
        normalized_name=canonicalize_name(requirement.name), declared_name=requirement.name,
        version_specifier=version_specifier, marker=marker, extras=extras,
        direct_reference=direct, source_kind=source, scope=scope, group=group,
        hashes=hashes, raw_declaration=raw, source_manifest=path, evidence=(evidence,),
    ), None


def _requirements(text: str, path: str, sha256: str) -> tuple[list[PythonDependencyDeclaration], list[ParserDiagnostic]]:
    parsed: list[PythonDependencyDeclaration] = []
    diagnostics: list[ParserDiagnostic] = []
    for logical, start, end, dangling in _logical_lines(text):
        if dangling:
            diagnostics.append(_diag("requirement_invalid", path, None, start, end, "error"))
            continue
        if len(logical.encode("utf-8")) > _MAX_LOGICAL_LINE:
            diagnostics.append(_diag("manifest_logical_line_too_long", path, None, start, end, "error")); continue
        value = _strip_comment(logical).strip(" \t")
        if not value or value.startswith("#"):
            continue
        lowered = value.lower()
        directive = None
        if lowered.startswith(("-r ", "--requirement ")): directive = "requirement_include_unsupported"
        elif lowered.startswith(("-c ", "--constraint ")): directive = "requirement_constraint_unsupported"
        elif lowered.startswith(("-e ", "--editable ")): directive = "requirement_editable_unsupported"
        elif value.startswith("-"): directive = "requirement_option_unsupported"
        if directive:
            diagnostics.append(_diag(directive, path, None, start, end, "warning")); continue
        if "://" in value and not re.match(r"^[A-Za-z0-9_.-]+(?:\[[^]]+\])?\s*@\s*", value):
            diagnostics.append(_diag("requirement_unnamed_reference_unsupported", path, None, start, end, "error")); continue
        pieces = re.split(r"[ \t]+", value)
        hashes: list[str] = []
        kept: list[str] = []
        invalid_hash = False
        for piece in pieces:
            if piece.startswith("--hash="):
                candidate = piece.removeprefix("--hash=")
                if not candidate.startswith("sha256:") or not _HASH.fullmatch(candidate[7:]): invalid_hash = True
                else: hashes.append(candidate[7:].lower())
            else: kept.append(piece)
        if invalid_hash:
            diagnostics.append(_diag("requirement_hash_invalid", path, None, start, end, "error")); continue
        declaration, diagnostic = _parse_requirement(" ".join(kept), path=path, locator=None, start=start, end=end, sha256=sha256, scope=DependencyScope.RUNTIME, group=None, hashes=tuple(sorted(set(hashes))))
        if diagnostic: diagnostics.append(diagnostic)
        elif declaration: parsed.append(declaration)
    return parsed, diagnostics


def _pyproject(text: str, path: str, sha256: str) -> tuple[list[PythonDependencyDeclaration], list[ParserDiagnostic]]:
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return [], [_diag("manifest_toml_invalid", path, severity="error")]
    parsed: list[PythonDependencyDeclaration] = []
    diagnostics: list[ParserDiagnostic] = []
    project = document.get("project", {})
    if not isinstance(project, dict):
        diagnostics.append(_diag("manifest_field_invalid", path, "project", severity="error")); project = {}
    dynamic = project.get("dynamic", [])
    if not isinstance(dynamic, list) or any(not isinstance(item, str) for item in dynamic):
        diagnostics.append(_diag("manifest_field_invalid", path, "project.dynamic", severity="error"))
    elif any(item in {"dependencies", "optional-dependencies"} for item in dynamic):
        diagnostics.append(_diag("pyproject_dynamic_dependencies_unsupported", path, "project.dynamic"))
    fields: list[tuple[object, DependencyScope, str | None, str]] = [
        (project.get("dependencies", []), DependencyScope.RUNTIME, None, "project.dependencies"),
    ]
    optional = project.get("optional-dependencies", {})
    if optional != {} and not isinstance(optional, dict):
        diagnostics.append(_diag("manifest_field_invalid", path, "project.optional-dependencies", severity="error")); optional = {}
    if isinstance(optional, dict):
        used_groups: set[str] = set()
        for original, values in optional.items():
            if not isinstance(original, str) or not original or any(ord(char) < 32 for char in original):
                diagnostics.append(_diag("manifest_field_invalid", path, "project.optional-dependencies", severity="error")); continue
            group = canonicalize_name(original)
            if group in used_groups:
                diagnostics.append(_diag("manifest_field_invalid", path, "project.optional-dependencies", severity="error")); continue
            used_groups.add(group)
            fields.append((values, DependencyScope.OPTIONAL, group, f"project.optional-dependencies.{quote(original, safe='A-Za-z0-9._-')}"))
    build = document.get("build-system", {})
    if build != {} and not isinstance(build, dict):
        diagnostics.append(_diag("manifest_field_invalid", path, "build-system", severity="error")); build = {}
    if isinstance(build, dict): fields.append((build.get("requires", []), DependencyScope.BUILD, None, "build-system.requires"))
    tool = document.get("tool", {})
    if "dependency-groups" in document or (isinstance(tool, dict) and any(key in tool for key in ("poetry", "pdm", "hatch"))):
        diagnostics.append(_diag("pyproject_tool_table_unsupported", path, "tool"))
    for values, scope, group, field in fields:
        if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
            diagnostics.append(_diag("manifest_field_invalid", path, field, severity="error")); continue
        for index, value in enumerate(values):
            locator = f"{field}[{index}]"
            declaration, diagnostic = _parse_requirement(value, path=path, locator=locator, start=None, end=None, sha256=sha256, scope=scope, group=group)
            if diagnostic: diagnostics.append(diagnostic)
            elif declaration: parsed.append(declaration)
    return parsed, diagnostics


def _identity(item: PythonDependencyDeclaration) -> tuple[object, ...]:
    return (item.normalized_name, item.scope.value, item.group, item.extras, item.version_specifier, item.marker, item.source_kind.value, item.direct_reference, item.hashes)


def _identity_sort_key(item: PythonDependencyDeclaration) -> tuple[bytes, ...]:
    """Encode each frozen identity field without repr-dependent ordering."""
    encoded: list[bytes] = []
    for value in _identity(item):
        if value is None:
            encoded.append(b"")
        elif isinstance(value, tuple):
            encoded.append(b"\0".join(str(part).encode("utf-8") for part in value))
        else:
            encoded.append(str(value).encode("utf-8"))
    return tuple(encoded)


def _merge(dependencies: Iterable[PythonDependencyDeclaration], diagnostics: list[ParserDiagnostic]) -> tuple[PythonDependencyDeclaration, ...]:
    merged: dict[tuple[object, ...], PythonDependencyDeclaration] = {}
    scoped: dict[tuple[str, DependencyScope, str | None], list[PythonDependencyDeclaration]] = {}
    for item in dependencies:
        key = _identity(item)
        existing = merged.get(key)
        if existing is None:
            merged[key] = item
        else:
            evidence = tuple(sorted((*existing.evidence, *item.evidence), key=lambda value: (value.manifest_path.encode("utf-8"), (value.field_locator or "").encode("utf-8"), value.start_line if value.start_line is not None else -1, value.end_line if value.end_line is not None else -1, value.content_sha256)))
            merged[key] = PythonDependencyDeclaration(**{**existing.__dict__, "declared_name": min(existing.declared_name, item.declared_name, key=lambda v: v.encode("utf-8")), "source_manifest": min(existing.source_manifest, item.source_manifest, key=lambda v: v.encode("utf-8")), "evidence": evidence})
            diagnostics.append(_diag("dependency_duplicate", item.source_manifest, item.evidence[0].field_locator, item.evidence[0].start_line, item.evidence[0].end_line))
    for item in merged.values(): scoped.setdefault((item.normalized_name, item.scope, item.group), []).append(item)
    for values in scoped.values():
        if len(values) < 2: continue
        direct_or_pins = {value.direct_reference for value in values if value.direct_reference} | {value.version_specifier for value in values if value.version_specifier and value.version_specifier.startswith("==")}
        code = "dependency_declaration_conflict" if len(direct_or_pins) > 1 else "dependency_multiple_constraints"
        for value in values[1:]:
            evidence = value.evidence[0]
            diagnostics.append(_diag(code, value.source_manifest, evidence.field_locator, evidence.start_line, evidence.end_line, "error" if code.endswith("conflict") else "warning"))
    return tuple(sorted(merged.values(), key=_identity_sort_key))


def parse_python_manifests(session: ReadOnlyScanSession) -> PythonManifestParseResult:
    """Parse only sealed manifest bytes and return immutable, deterministic DTOs."""
    try:
        if _packaging_version != "26.3" or Requirement is None or canonicalize_name is None:
            raise _failure("python_manifest_parser_unavailable")
        candidates = _inventory_candidates(session)
        manifests: list[ParsedManifest] = []
        dependencies: list[PythonDependencyDeclaration] = []
        diagnostics: list[ParserDiagnostic] = []
        for path, size, sha256, kind in candidates:
            data = session.read_bytes(path, max_bytes=_MAX_FILE_BYTES)
            if hashlib.sha256(data).hexdigest() != sha256:
                raise _failure("python_manifest_parser_failed")
            try:
                text = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                diagnostics.append(_diag("manifest_encoding_invalid", path, severity="error"))
                manifests.append(ParsedManifest(path, kind, size, sha256, ParseStatus.PARTIAL))
                continue
            found, file_diagnostics = _requirements(text, path, sha256) if kind is ManifestKind.REQUIREMENTS else _pyproject(text, path, sha256)
            dependencies.extend(found)
            diagnostics.extend(file_diagnostics)
            manifests.append(ParsedManifest(path, kind, size, sha256, ParseStatus.PARTIAL if file_diagnostics else ParseStatus.COMPLETE))
        if len(dependencies) > _MAX_DECLARATIONS:
            raise _failure("python_manifest_limit_exceeded")
        merged = _merge(dependencies, diagnostics)
        diagnostics.sort(key=lambda value: ((value.manifest_path or "").encode("utf-8"), value.start_line or 0, (value.field_locator or "").encode("utf-8"), value.code, value.severity))
        manifests.sort(key=lambda value: value.relative_path.encode("utf-8"))
        return PythonManifestParseResult("b1-python-manifest/v1", ParseStatus.PARTIAL if diagnostics else ParseStatus.COMPLETE, tuple(manifests), merged, tuple(diagnostics))
    except IngestionSecurityError:
        raise
    except Exception as error:
        raise _failure("python_manifest_parser_failed") from error
