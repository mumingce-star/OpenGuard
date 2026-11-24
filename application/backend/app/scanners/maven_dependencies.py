"""Bounded Maven POM and Gradle lock observations from sealed bytes."""

from __future__ import annotations

import hashlib
import io
import re
import xml.etree.ElementTree as ET
from dataclasses import replace
from urllib.parse import quote

from .dependency_observations import (
    MAX_BYTES, MAX_DEPTH, MAX_NODES, DependencyObservations, Gap, Node, RootObservation,
    _result, relative_path,
)

_MAVEN_NAMESPACE = "{http://maven.apache.org/POM/4.0.0}"
_XINCLUDE_NAMESPACE = "{http://www.w3.org/2001/XInclude}"
_XML_DECLARATION = re.compile(r"^\ufeff?<\?xml\s[^?]*\?>")
_XML_ENCODING = re.compile(r"\bencoding\s*=\s*(['\"])([^'\"]+)\1")
_XML_DTD_OR_ENTITY = re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
_GROUP = re.compile(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*")
_ARTIFACT = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]*")
_CONFIGURATIONS = re.compile(r"[A-Za-z0-9_.-]+(?:,[A-Za-z0-9_.-]+)*")
_PROPERTY_NAME = re.compile(r"[A-Za-z0-9_.-]{1,128}")
_PROPERTY = re.compile(r"\$\{([A-Za-z0-9_.-]{1,128})\}")
_VERSION_EXCERPT = re.compile(r"[A-Za-z0-9_.,+\-()\[\] ${}]{1,200}")


def valid_maven_group(value: object) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 200 and _GROUP.fullmatch(value) is not None


def valid_maven_artifact(value: object) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 200 and _ARTIFACT.fullmatch(value) is not None


def valid_maven_version(value: object) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= 200 and _VERSION.fullmatch(value) is not None
            and value.upper() not in {"LATEST", "RELEASE"} and not value.endswith("+"))


def _maven_purl(group: str, artifact: str, version: str) -> str:
    return f"pkg:maven/{quote(group, safe='')}/{quote(artifact, safe='')}@{quote(version, safe='')}"


def _decode(raw: bytes, path: str) -> str:
    relative_path(path)
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise ValueError("input_limit_exceeded")
    try:
        return raw.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("invalid_document") from exc


def _parse_xml(text: str) -> ET.Element:
    if "\0" in text or _XML_DTD_OR_ENTITY.search(text):
        raise ValueError("xml_dtd_or_entity_forbidden")
    declaration = _XML_DECLARATION.match(text)
    encoding = _XML_ENCODING.search(declaration.group()) if declaration else None
    if encoding and encoding.group(2).lower() != "utf-8":
        raise ValueError("invalid_xml_encoding")

    parser = ET.XMLPullParser(events=("start", "end"))
    root = None
    depth = count = 0
    try:
        for offset in range(0, len(text), 8192):
            parser.feed(text[offset:offset + 8192])
            for event, element in parser.read_events():
                if event == "end":
                    depth -= 1
                    continue
                count += 1
                if depth > MAX_DEPTH or count > MAX_NODES:
                    raise ValueError("structure_limit_exceeded")
                depth += 1
                if element.tag.startswith(_XINCLUDE_NAMESPACE):
                    raise ValueError("xml_xinclude_forbidden")
                if root is None:
                    root = element
        parser.close()
    except (ET.ParseError, RecursionError) as exc:
        raise ValueError("invalid_xml_document") from exc
    if root is None:
        raise ValueError("invalid_xml_document")
    return root


def _single(element: ET.Element, tag: str) -> ET.Element | None:
    children = element.findall(tag)
    if len(children) > 1:
        raise ValueError("duplicate_xml_field")
    return children[0] if children else None


def _literal(element: ET.Element) -> str:
    if len(element):
        raise ValueError("invalid_xml_scalar_field")
    return (element.text or "").strip()


def _field(element: ET.Element, tag: str) -> str | None:
    child = _single(element, tag)
    return _literal(child) if child is not None else None


class _PropertyError(ValueError):
    pass


def _resolve(
    raw: str,
    properties: dict[str, str | None],
    cache: dict[str, str],
    active: tuple[str, ...] = (),
) -> str:
    if len(active) > MAX_DEPTH or len(raw) > 200:
        raise _PropertyError("maven_property_limit")

    def expand(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in active:
            raise _PropertyError("maven_property_cycle")
        if name not in cache:
            value = properties.get(name)
            if value is None:
                raise _PropertyError("maven_property_unresolved")
            cache[name] = _resolve(value, properties, cache, (*active, name))
        return cache[name]

    value = _PROPERTY.sub(expand, raw)
    if "${" in value:
        raise _PropertyError("maven_property_unresolved")
    if len(value) > 200:
        raise _PropertyError("maven_property_limit")
    return value


def _optional_license(project: ET.Element, namespace: str) -> tuple[str, str] | None:
    licenses = _single(project, namespace + "licenses")
    if licenses is None:
        return None
    fields = licenses.findall(namespace + "license")
    if len(fields) != 1:
        return None
    name = _field(fields[0], namespace + "name")
    if name:
        return "/project/licenses/license/0/name", name
    return None


def parse_pom(raw: bytes, *, path: str = "pom.xml") -> DependencyObservations:
    """Observe direct Maven coordinates without following parents, BOMs or builds."""
    project = _parse_xml(_decode(raw, path))
    if project.tag not in {"project", _MAVEN_NAMESPACE + "project"}:
        raise ValueError("unsupported_maven_pom_namespace")
    namespace = _MAVEN_NAMESPACE if project.tag != "project" else ""
    fields = ("groupId", "artifactId", "version")
    raw_coordinates = tuple(_field(project, namespace + name) for name in fields)
    parent = _single(project, namespace + "parent")
    management = _single(project, namespace + "dependencyManagement")
    properties_element = _single(project, namespace + "properties")
    properties: dict[str, str | None] = {}
    if properties_element is not None:
        for child in properties_element:
            name = child.tag.removeprefix(namespace)
            if not _PROPERTY_NAME.fullmatch(name):
                continue
            if name in properties:
                raise ValueError("duplicate_xml_field")
            properties[name] = _literal(child)
    # Built-in aliases only derive from this project's direct fields.
    properties.update({"project.groupId": raw_coordinates[0], "project.version": raw_coordinates[2]})
    cache: dict[str, str] = {}
    nodes: list[Node] = []
    gaps: list[Gap] = []
    if parent is not None:
        gaps.append(Gap("maven_parent_not_evaluated", f"{path}:/project/parent"))
    if management is not None:
        gaps.append(Gap("maven_dependency_management_not_evaluated", f"{path}:/project/dependencyManagement"))

    def resolve(value: str | None, locator: str) -> str | None:
        if value is None:
            return None
        try:
            return _resolve(value, properties, cache)
        except _PropertyError as exc:
            gaps.append(Gap(str(exc), locator))
            return None

    root = None
    if path == "pom.xml":
        coordinates = tuple(resolve(value, f"{path}:/project/{name}")
                            for name, value in zip(fields, raw_coordinates))
        group, artifact, version = coordinates
        if (valid_maven_group(group) and valid_maven_artifact(artifact)
                and len(f"{group}:{artifact}") <= 200 and valid_maven_version(version)):
            evidence = tuple((f"/project/{name}", value if original == value else {"raw": original, "value": value})
                             for name, original, value in zip(fields, raw_coordinates, coordinates))
            root = RootObservation(f"{group}:{artifact}", version, _maven_purl(group, artifact, version),
                                   evidence, _optional_license(project, namespace))
        else:
            gaps.append(Gap("maven_root_identity_not_static", f"{path}:/project"))

    dependencies = _single(project, namespace + "dependencies")
    if dependencies is not None:
        for index, child in enumerate(dependencies.findall(namespace + "dependency")):
            loc = f"{path}:/project/dependencies/dependency/{index}"
            group, artifact = (resolve(_field(child, namespace + name), f"{loc}/{name}") for name in fields[:2])
            name = f"{group}:{artifact}"
            if not valid_maven_group(group) or not valid_maven_artifact(artifact) or len(name) > 200:
                gaps.append(Gap("maven_dependency_coordinates_invalid", loc))
                continue
            raw_version = _field(child, namespace + "version")
            version_locator = f"{loc}/version"
            version = resolve(raw_version, version_locator)
            if not valid_maven_version(version):
                code = "maven_dependency_version_missing" if raw_version is None else "maven_version_not_exact"
                gaps.append(Gap(code, version_locator))
                version = None
            purl = _maven_purl(group, artifact, version) if version is not None else None
            excerpt = raw_version if raw_version and _VERSION_EXCERPT.fullmatch(raw_version) else None
            nodes.append(Node(f"maven:{index}", name, version, purl, loc, "manifest", excerpt))
    return replace(_result("maven-pom/1", path, hashlib.sha256(raw).hexdigest(), nodes, [], gaps), root=root)


def parse_gradle_lock(raw: bytes, *, path: str = "gradle.lockfile") -> DependencyObservations:
    """Observe coordinates in Gradle's flat lock format without reading scripts."""
    nodes: list[Node] = []
    gaps: list[Gap] = []
    records = 0
    for line_number, raw_line in enumerate(io.StringIO(_decode(raw, path)), 1):
        if len(raw_line) > 8192 or line_number > 131072:
            raise ValueError("structure_limit_exceeded")
        line = raw_line.rstrip("\r\n").strip(" \t")
        if not line or line.startswith(("#", "empty=")):
            continue
        records += 1
        if records > MAX_NODES:
            raise ValueError("graph_limit_exceeded")
        locator = f"{path}:/lines/{line_number}"
        coordinate, sep, configurations = line.partition("=")
        parts = coordinate.split(":")
        if not sep or len(parts) != 3 or not _CONFIGURATIONS.fullmatch(configurations):
            gaps.append(Gap("gradle_lock_line_invalid", locator))
            continue
        group, artifact, version = parts
        name = f"{group}:{artifact}"
        if (not valid_maven_group(group) or not valid_maven_artifact(artifact)
                or len(name) > 200 or not valid_maven_version(version)):
            gaps.append(Gap("gradle_lock_line_invalid", locator))
            continue
        nodes.append(Node(f"gradle:{line_number}", name, version, _maven_purl(group, artifact, version),
                          locator, "lock"))
    return _result("gradle-lock/1", path, hashlib.sha256(raw).hexdigest(), nodes, [], gaps)
