"""Bounded Cargo declarations and recorded lock identities from sealed bytes."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import replace
from urllib.parse import quote, urlsplit

from .dependency_observations import (
    MAX_EDGES, MAX_NODES, DependencyObservations, Edge, Gap, Node, RootObservation,
    _load, _result, _text,
)


_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]*")
_NUMBER = r"(?:0|[1-9][0-9]*)"
_IDENTIFIERS = r"[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*"
_SEMVER = re.compile(
    rf"{_NUMBER}\.{_NUMBER}\.{_NUMBER}(?:-({_IDENTIFIERS}))?(?:\+{_IDENTIFIERS})?"
)
_RANGE_TERM = re.compile(
    rf"(?:\^|~|=|>=|<=|>|<)? *"
    rf"(?:{_NUMBER}(?:\.(?:{_NUMBER}|[xX*])){{0,2}}(?:-{_IDENTIFIERS})?(?:\+{_IDENTIFIERS})?|[xX*])"
)
_DEPENDENCY_TABLES = ("dependencies", "dev-dependencies", "build-dependencies")


def valid_cargo_name(value: object) -> bool:
    return type(value) is str and 1 <= len(value) <= 200 and _NAME.fullmatch(value) is not None


def valid_cargo_version(value: object) -> bool:
    if type(value) is not str or not 1 <= len(value) <= 200:
        return False
    version = _SEMVER.fullmatch(value)
    if version is None:
        return False
    prerelease = version.group(1)
    return prerelease is None or all(
        not (part.isdecimal() and len(part) > 1 and part.startswith("0")) for part in prerelease.split(".")
    )


def exact_cargo_dependency_version(selector: object) -> str | None:
    if type(selector) is not str or not 1 <= len(selector) <= 200:
        return None
    selector = selector.strip(" ")
    if not selector.startswith("="):
        return None
    version = selector[1:].lstrip(" ")
    # Cargo ignores build metadata when matching a version requirement.
    return version if "+" not in version and valid_cargo_version(version) else None


def _range_excerpt(value: object) -> str | None:
    if (type(value) is str and 1 <= len(value) <= 200
            and all(_RANGE_TERM.fullmatch(term.strip(" ")) for term in value.split(","))):
        return value
    return None


def _purl(name: str, version: str) -> str:
    return f"pkg:cargo/{quote(name, safe='')}@{quote(version, safe='')}"


def _root(document: dict, path: str, gaps: list[Gap]) -> RootObservation | None:
    if path != "Cargo.toml" or "package" not in document:
        return None
    package = document["package"]
    if type(package) is not dict or not valid_cargo_name(package.get("name")) or not valid_cargo_version(package.get("version")):
        gaps.append(Gap("cargo_root_identity_unresolved", f"{path}:/package"))
        return None
    name, version = package["name"], package["version"]
    license_text = package.get("license")
    license = None
    if ("license-file" not in package and type(license_text) is str
            and 1 <= len(license_text) <= 200 and all(32 <= ord(c) <= 126 for c in license_text)):
        license = ("/package/license", license_text)
    return RootObservation(name, version, _purl(name, version),
                           (("/package/name", name), ("/package/version", version)), license)


def parse_cargo_toml(raw: bytes, *, path: str = "Cargo.toml") -> DependencyObservations:
    data, digest = _load(raw, path, toml=True)
    nodes: list[Node] = []
    gaps: list[Gap] = []
    dependency_count = 0
    for section in _DEPENDENCY_TABLES:
        table = data.get(section, {})
        table_locator = f"{path}:/{section}"
        if type(table) is not dict:
            gaps.append(Gap("cargo_dependency_table_invalid", table_locator))
            continue
        dependency_count += len(table)
        if dependency_count > MAX_NODES:
            raise ValueError("graph_limit_exceeded")
        for index, (alias, spec) in enumerate(table.items()):
            if not valid_cargo_name(alias):
                gaps.append(Gap("cargo_dependency_name_invalid", table_locator))
                continue
            locator = f"{table_locator}/{alias}"
            if type(spec) is str:
                name, version_value = alias, spec
                require_non_registry = False
            elif type(spec) is dict:
                name = spec.get("package", alias)
                if not valid_cargo_name(name):
                    gaps.append(Gap("cargo_dependency_name_invalid", f"{locator}/package"))
                    continue
                version_value = spec.get("version")
                unsupported = [
                    ("workspace", spec.get("workspace", False) is not False),
                    ("path", "path" in spec),
                    ("git", "git" in spec),
                    ("registry", spec.get("registry", "crates-io") != "crates-io" or "registry-index" in spec),
                ]
                fields = [field for field, found in unsupported if found]
                for field in fields:
                    field_path = "registry-index" if field == "registry" and "registry" not in spec else field
                    gaps.append(Gap(f"cargo_{field}_dependency_not_evaluated", f"{locator}/{field_path}"))
                require_non_registry = bool(fields)
                if "version" in spec:
                    locator += "/version"
            else:
                gaps.append(Gap("dependency_invalid", locator))
                continue
            excerpt = _range_excerpt(version_value)
            if excerpt is None and (version_value is not None or not require_non_registry):
                gaps.append(Gap("cargo_version_selector_invalid", locator))
            version = None if require_non_registry else exact_cargo_dependency_version(excerpt)
            nodes.append(Node(f"cargo-toml:{section}:{index}", name, version,
                              _purl(name, version) if version is not None else None, locator, "manifest", excerpt))
    root = _root(data, path, gaps)
    result = _result("cargo-toml/1", path, digest, nodes, [], gaps)
    return replace(result, root=root)


def _lock_source_kind(source: object) -> str | None:
    if not _text(source) or any(char.isspace() for char in source):
        return None
    kind, separator, url = source.partition("+")
    if not separator or kind not in {"registry", "sparse", "git"}:
        return None
    try:
        value = urlsplit(url)
        allowed = {"http", "https", "ssh", "git"} if kind == "git" else {"http", "https"}
        if (value.scheme not in allowed or not value.hostname or value.username is not None
                or value.password is not None or "\\" in url or (value.port is not None and value.port == 0)):
            return None
    except ValueError:
        return None
    return kind


def _lock_reference(value: object) -> tuple[str, str | None, str | None] | None:
    if not _text(value):
        return None
    fields = value.split(maxsplit=2)
    if not fields or not valid_cargo_name(fields[0]):
        return None
    name = fields[0]
    version = fields[1] if len(fields) >= 2 else None
    if version is not None and not valid_cargo_version(version):
        return None
    source = None
    if len(fields) == 3:
        source = fields[2]
        if not source.startswith("(") or not source.endswith(")"):
            return None
        source = source[1:-1]
        if _lock_source_kind(source) is None:
            return None
    return name, version, source


def parse_cargo_lock(raw: bytes, *, path: str = "Cargo.lock") -> DependencyObservations:
    data, digest = _load(raw, path, toml=True)
    lock_version = data.get("version")
    if type(lock_version) is not int or lock_version not in {3, 4}:
        raise ValueError("unsupported_cargo_lock_version")
    packages = data.get("package", [])
    if type(packages) is not list or len(packages) > MAX_NODES:
        raise ValueError("invalid_cargo_packages")
    nodes: list[Node] = []
    edges: list[Edge] = []
    gaps: list[Gap] = []
    entries = []
    choices: dict[tuple[str, str | None, str | None], list[str]] = defaultdict(list)
    for index, package in enumerate(packages):
        locator = f"{path}:/package/{index}"
        if type(package) is not dict or not valid_cargo_name(package.get("name")):
            gaps.append(Gap("package_name_invalid", f"{locator}/name"))
            continue
        name, version = package["name"], package.get("version")
        if not valid_cargo_version(version):
            gaps.append(Gap("package_version_invalid", f"{locator}/version"))
            continue
        source = package.get("source")
        source_kind = "workspace" if source is None else _lock_source_kind(source)
        if source_kind is None:
            gaps.append(Gap("source_invalid", f"{locator}/source"))
            continue
        identity = f"cargo-lock:{index}"
        nodes.append(Node(identity, name, version, _purl(name, version), f"{locator}/version", source_kind))
        entries.append((identity, package, locator))
        for key in {(name, None, None), (name, version, None), (name, version, source)}:
            choices[key].append(identity)
    reference_count = 0
    for identity, package, locator in entries:
        dependencies = package.get("dependencies", [])
        if type(dependencies) is not list:
            raise ValueError("invalid_cargo_dependencies")
        reference_count += len(dependencies)
        if reference_count > MAX_EDGES:
            raise ValueError("graph_limit_exceeded")
        for index, value in enumerate(dependencies):
            field = f"{locator}/dependencies/{index}"
            reference = _lock_reference(value)
            if reference is None:
                gaps.append(Gap("dependency_invalid", field))
                continue
            candidates = choices.get(reference, ())
            if len(candidates) != 1:
                gaps.append(Gap("dependency_ambiguous" if candidates else "dependency_unresolved", field))
                continue
            edges.append(Edge(identity, candidates[0], field))
    return _result(f"cargo-lock/{lock_version}", path, digest, nodes, edges, gaps)
