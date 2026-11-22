"""Private, bounded lock/SBOM observations; no installation or authorization claims.

Callers supply bytes from an authorized read session. This module never reads a
path, resolves a dependency, or changes the public Component/Evidence contract.
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from urllib.parse import quote, unquote, urlsplit

from packaging.version import InvalidVersion, Version

MAX_BYTES = 2 * 1024 * 1024
MAX_NODES = 4096
MAX_EDGES = 16384
MAX_DEPTH = 48


@dataclass(frozen=True, order=True)
class Gap:
    code: str
    locator: str


@dataclass(frozen=True)
class Node:
    instance_id: str
    name: str
    version: str | None
    purl: str | None
    locator: str
    source_kind: str


@dataclass(frozen=True, order=True)
class Edge:
    parent: str
    child: str
    locator: str


@dataclass(frozen=True)
class DependencyObservations:
    format: str
    source_path: str
    source_sha256: str
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    gaps: tuple[Gap, ...]
    semantics: str = "parsed_observation_not_installation_or_authorization"

    @property
    def status(self) -> str:
        return "partial" if self.gaps else "complete"


def relative_path(value: object) -> str:
    if (type(value) is not str or not value or len(value) > 1024
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
            or "\\" in value or ":" in value or value.startswith("/")
            or any(p in {"", ".", ".."} for p in value.split("/"))):
        raise ValueError("unsafe_source_path")
    return value


def _text(value: object) -> bool:
    return (type(value) is str and 0 < len(value) <= 2048
            and not any(ord(c) < 32 or ord(c) == 127 for c in value))


def _python_version(value: object) -> str | None:
    if not _text(value):
        return None
    try:
        Version(value)
    except InvalidVersion:
        return None
    return value


def _bounded(value: object) -> None:
    stack = [(value, 0)]
    count = 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if depth > MAX_DEPTH or count > 131072:
            raise ValueError("structure_limit_exceeded")
        if isinstance(item, dict):
            stack.extend((v, depth + 1) for v in item.values())
            if any(not _text(k) for k in item):
                raise ValueError("invalid_key")
        elif isinstance(item, list):
            stack.extend((v, depth + 1) for v in item)
        elif isinstance(item, str) and (len(item) > 8192 or any(0xD800 <= ord(c) <= 0xDFFF for c in item)):
            raise ValueError("invalid_string")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _load(raw: bytes, path: str, *, toml: bool = False) -> tuple[dict, str]:
    relative_path(path)
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise ValueError("input_limit_exceeded")
    try:
        text = raw.decode("utf-8")
        data = tomllib.loads(text) if toml else json.loads(
            text, object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid_json_number")),
        )
        if type(data) is not dict:
            raise ValueError("document_not_object")
        _bounded(data)
    except (UnicodeError, RecursionError, tomllib.TOMLDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_document") from exc
    return data, hashlib.sha256(raw).hexdigest()


def _result(fmt, path, digest, nodes, edges, gaps):
    if len(nodes) > MAX_NODES or len(edges) > MAX_EDGES:
        raise ValueError("graph_limit_exceeded")
    unique = {}
    for edge in edges:
        key = (edge.parent, edge.child)
        if key in unique:
            gaps.append(Gap("duplicate_dependency_edge", edge.locator))
        else:
            unique[key] = edge
    return DependencyObservations(fmt, path, digest, tuple(nodes), tuple(sorted(unique.values())), tuple(sorted(set(gaps))))


def parse_uv_lock(raw: bytes, *, path: str = "uv.lock") -> DependencyObservations:
    """uv lock schema 1, revisions 1–3 (or legacy absent revision).

    Packages are separate instances by source and position. Conditional forks
    without a uniquely matching name/version/source remain unresolved.
    """
    data, digest = _load(raw, path, toml=True)
    if type(data.get("version")) is not int or data["version"] != 1:
        raise ValueError("unsupported_uv_version")
    revision = data.get("revision", 1)
    if type(revision) is not int or revision not in (1, 2, 3):
        raise ValueError("unsupported_uv_revision")
    packages = data.get("package")
    if type(packages) is not list or len(packages) > MAX_NODES:
        raise ValueError("invalid_uv_packages")
    nodes, edges, gaps, entries = [], [], [], []
    names = {}
    for index, item in enumerate(packages):
        loc = f"{path}:/package/{index}"
        if not isinstance(item, dict) or not _text(item.get("name")):
            gaps.append(Gap("package_name_missing", loc)); continue
        name = item["name"]
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", name):
            gaps.append(Gap("package_name_invalid", loc)); continue
        name = re.sub(r"[-_.]+", "-", name).lower()
        version = _python_version(item.get("version"))
        if version is None:
            gaps.append(Gap("version_missing", loc + "/version"))
        source = item.get("source")
        if type(source) is not dict or len(source) != 1 or next(iter(source), None) not in {"registry", "git", "url", "editable", "virtual", "directory"}:
            gaps.append(Gap("source_invalid", loc + "/source")); continue
        kind, value = next(iter(source.items()))
        if not _text(value):
            gaps.append(Gap("source_invalid", loc + "/source")); continue
        if kind in {"editable", "virtual", "directory"}:
            try:
                if value != ".":
                    relative_path(value)
            except ValueError:
                gaps.append(Gap("workspace_path_unsafe", loc + "/source")); continue
        else:
            try:
                parsed = urlsplit(value)
                if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password or parsed.query:
                    raise ValueError()
            except ValueError:
                gaps.append(Gap("source_url_unsupported", loc + "/source")); continue
        identity = f"uv:{index}"
        purl = f"pkg:pypi/{quote(name, safe='')}@{quote(version, safe='')}" if version else None
        nodes.append(Node(identity, name, version, purl, loc, kind))
        entries.append((identity, item, loc))
        names.setdefault(name, []).append((identity, version, source))
        if item.get("optional-dependencies") or item.get("dev-dependencies"):
            gaps.append(Gap("optional_or_dev_edges_not_extracted", loc))
    ref_count = 0
    for identity, item, loc in entries:
        dependencies = item.get("dependencies", [])
        if type(dependencies) is not list or len(dependencies) > MAX_EDGES:
            raise ValueError("invalid_uv_dependencies")
        for index, dep in enumerate(dependencies):
            ref_count += 1
            if ref_count > MAX_EDGES:
                raise ValueError("graph_limit_exceeded")
            position = f"{loc}/dependencies/{index}"
            if type(dep) is not dict or not _text(dep.get("name")):
                gaps.append(Gap("dependency_invalid", position)); continue
            name = re.sub(r"[-_.]+", "-", dep["name"]).lower()
            choices = [entry for entry in names.get(name, [])
                       if ("version" not in dep or dep["version"] == entry[1])
                       and ("source" not in dep or dep["source"] == entry[2])]
            if len(choices) != 1:
                gaps.append(Gap("dependency_ambiguous" if choices else "dependency_unresolved", position))
            else:
                edges.append(Edge(identity, choices[0][0], position))
            if "marker" in dep:
                gaps.append(Gap("conditional_edge_not_evaluated", position))
            if len(edges) > MAX_EDGES:
                raise ValueError("graph_limit_exceeded")
    return _result(f"uv/1.revision-{revision}", path, digest, nodes, edges, gaps)


def parse_cyclonedx_json(raw: bytes, *, path: str = "bom.json") -> DependencyObservations:
    """CycloneDX JSON 1.5 flat components/dependencies; never license admission.

    Unsupported nesting, identity details and locations are explicit gaps. IDs
    are bom-ref, never package names; equal names do not collapse instances.
    """
    data, digest = _load(raw, path)
    return _cyclonedx(data, path, digest, "cyclonedx-json/1.5")


def _cyclonedx(data, path, digest, format):
    if data.get("bomFormat") != "CycloneDX" or data.get("specVersion") != "1.5":
        raise ValueError("unsupported_cyclonedx_version")
    components = data.get("components", [])
    dependencies = data.get("dependencies", [])
    if type(components) is not list or type(dependencies) is not list or len(components) > MAX_NODES or len(dependencies) > MAX_EDGES:
        raise ValueError("graph_limit_exceeded")
    nodes, edges, gaps = [], [], []
    known = set()
    root = data.get("metadata", {}).get("component") if isinstance(data.get("metadata", {}), dict) else None
    items = [(entry, f"{path}:/components/{i}") for i, entry in enumerate(components)]
    if root is not None:
        items.insert(0, (root, f"{path}:/metadata/component"))
    for item, loc in items:
        if type(item) is not dict or not _text(item.get("name")) or not _text(item.get("bom-ref")):
            gaps.append(Gap("component_identity_missing", loc)); continue
        ref = item["bom-ref"]
        if ref in known:
            raise ValueError("duplicate_bom_ref")
        known.add(ref)
        version = item.get("version")
        if not _text(version):
            version = None
            gaps.append(Gap("version_missing", loc + "/version"))
        purl = item.get("purl")
        if purl is not None:
            # Deliberately narrow identity validation; do not normalize unsupported
            # qualifiers, subpaths or percent-encoded delimiters into false matches.
            if not _text(purl) or not re.fullmatch(r"pkg:(npm|pypi)/[^?#\s]+@[^@/?#\s]+", purl):
                gaps.append(Gap("purl_unsupported", loc + "/purl")); purl = None
            else:
                package, _, pversion = purl.rpartition("@")
                pname = unquote(package.split("/", 1)[1])
                declared = (str(item.get("group")) + "/" if item.get("group") else "") + item["name"]
                if package.startswith("pkg:pypi/"):
                    pname, declared = [re.sub(r"[-_.]+", "-", x).lower() for x in (pname, declared)]
                if pname != declared or unquote(pversion) != version:
                    gaps.append(Gap("purl_identity_conflict", loc + "/purl")); purl = None
        if item.get("components"):
            gaps.append(Gap("nested_components_unsupported", loc + "/components"))
        if item.get("evidence") or item.get("properties"):
            gaps.append(Gap("component_locations_not_verified", loc))
        nodes.append(Node(ref, item["name"], version, purl, loc, "sbom"))
    seen = set()
    for i, item in enumerate(dependencies):
        loc = f"{path}:/dependencies/{i}"
        if type(item) is not dict or not _text(item.get("ref")) or type(item.get("dependsOn")) is not list:
            gaps.append(Gap("dependency_invalid", loc)); continue
        if item["ref"] in seen:
            gaps.append(Gap("duplicate_dependency_record", loc))
            continue
        seen.add(item["ref"])
        if item["ref"] not in known:
            gaps.append(Gap("dependency_parent_unresolved", loc)); continue
        if len(item["dependsOn"]) > MAX_EDGES:
            raise ValueError("graph_limit_exceeded")
        targets = set()
        for j, child in enumerate(item["dependsOn"]):
            position = f"{loc}/dependsOn/{j}"
            if not _text(child) or child not in known:
                gaps.append(Gap("dependency_unresolved", position)); continue
            if child in targets:
                gaps.append(Gap("duplicate_dependency_edge", position)); continue
            targets.add(child)
            edges.append(Edge(item["ref"], child, position))
            if len(edges) > MAX_EDGES:
                raise ValueError("graph_limit_exceeded")
    if not dependencies:
        gaps.append(Gap("dependency_graph_not_provided", path + ":/dependencies"))
    return _result(format, path, digest, nodes, edges, gaps)


def parse_cyclonedx_xml(raw: bytes, *, path: str = "bom.xml") -> DependencyObservations:
    """CycloneDX XML 1.5 flat graph. Locators address the equivalent field projection."""
    relative_path(path)
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise ValueError("input_limit_exceeded")
    try:
        text = raw.decode("utf-8")
        # UTF-8 only, no DTD (internal or external), entities or XInclude.
        if "\0" in text or re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I):
            raise ValueError("xml_dtd_or_entity_forbidden")
        root = ET.fromstring(text)
    except (UnicodeError, ET.ParseError, RecursionError) as exc:
        raise ValueError("invalid_xml_document") from exc
    ns = "{http://cyclonedx.org/schema/bom/1.5}"
    if root.tag != ns + "bom":
        raise ValueError("unsupported_cyclonedx_version")
    stack = [(root, 0)]
    count = 0
    while stack:
        element, depth = stack.pop()
        count += 1
        if depth > MAX_DEPTH or count > 131072:
            raise ValueError("structure_limit_exceeded")
        if element.tag == "{http://www.w3.org/2001/XInclude}include":
            raise ValueError("xml_xinclude_forbidden")
        stack.extend((child, depth + 1) for child in element)

    def exactly_one(element, tag):
        items = element.findall(ns + tag)
        if len(items) > 1:
            raise ValueError("duplicate_xml_field")
        return items[0] if items else None

    def component(element):
        item = {"bom-ref": element.get("bom-ref")}
        for field in ("name", "group", "version", "purl"):
            child = exactly_one(element, field)
            if child is not None:
                if len(child):
                    raise ValueError("invalid_xml_component_field")
                item[field] = child.text
        for field in ("components", "evidence", "properties"):
            if exactly_one(element, field) is not None:
                item[field] = True
        return item

    components = exactly_one(root, "components")
    metadata = exactly_one(root, "metadata")
    dependencies = exactly_one(root, "dependencies")
    project = exactly_one(metadata, "component") if metadata is not None else None
    projected = {
        "bomFormat": "CycloneDX", "specVersion": "1.5",
        "components": [component(item) for item in components.findall(ns + "component")] if components is not None else [],
        "dependencies": [{"ref": item.get("ref"), "dependsOn": [child.get("ref") for child in item.findall(ns + "dependency")]}
                         for item in dependencies.findall(ns + "dependency")] if dependencies is not None else [],
    }
    if project is not None:
        projected["metadata"] = {"component": component(project)}
    _bounded(projected)
    return _cyclonedx(projected, path, hashlib.sha256(raw).hexdigest(), "cyclonedx-xml/1.5")


def parse_python_lock(raw: bytes, *, format: str, path: str) -> DependencyObservations:
    """Selected Poetry 2.1, PDM 4.5 and Pipfile 6 schema observations.

    Dependency constraints are deliberately not solved. This first adapter
    extracts instances, keeps source locators and reports unextracted graphs.
    """
    if format == "uv":
        return parse_uv_lock(raw, path=path)
    if format not in {"poetry", "pdm", "pipfile"}:
        raise ValueError("unsupported_format")
    data, digest = _load(raw, path, toml=format != "pipfile")
    nodes, gaps = [], []
    if format == "pipfile":
        meta = data.get("_meta")
        if not isinstance(meta, dict) or type(meta.get("pipfile-spec")) is not int or meta["pipfile-spec"] != 6:
            raise ValueError("unsupported_pipfile_version")
        entries = []
        for group in ("default", "develop"):
            values = data.get(group)
            if not isinstance(values, dict):
                raise ValueError("invalid_pipfile_group")
            for name, item in values.items():
                if not isinstance(item, dict):
                    raise ValueError("invalid_pipfile_entry")
                entries.append(({**item, "name": name}, f"{path}:/{group}/{name}"))
        fmt = "pipfile/6"
    else:
        metadata = data.get("metadata")
        key, expected = ("lock-version", "2.1") if format == "poetry" else ("lock_version", "4.5")
        if not isinstance(metadata, dict) or metadata.get(key) != expected:
            raise ValueError(f"unsupported_{format}_version")
        packages = data.get("package")
        if not isinstance(packages, list):
            raise ValueError("invalid_python_packages")
        entries = [(item, f"{path}:/package/{i}") for i, item in enumerate(packages)]
        fmt = f"{format}/{expected}"
    if len(entries) > MAX_NODES:
        raise ValueError("graph_limit_exceeded")
    for index, (item, loc) in enumerate(entries):
        if not isinstance(item, dict) or not _text(item.get("name")) or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", item["name"]):
            gaps.append(Gap("package_name_invalid", loc)); continue
        name = re.sub(r"[-_.]+", "-", item["name"]).lower()
        version = item.get("version")
        if format == "pipfile":
            version = version[2:] if isinstance(version, str) and version.startswith("==") and "*" not in version else None
        version = _python_version(version)
        if version is None:
            gaps.append(Gap("version_missing", loc + "/version"))
        purl = f"pkg:pypi/{quote(name, safe='')}@{quote(version, safe='')}" if version else None
        nodes.append(Node(f"{format}:{index}", name, version, purl, loc, "lock"))
        if any(field in item for field in ("source", "git", "path", "file", "url", "editable", "index")):
            gaps.append(Gap("package_source_not_bound", loc))
        if item.get("markers") or item.get("marker"):
            gaps.append(Gap("package_condition_not_evaluated", loc))
    gaps.append(Gap("dependency_graph_not_extracted", path))
    return _result(fmt, path, digest, nodes, [], gaps)


def parse_npm_lock_v1(raw: bytes, *, path: str = "package-lock.json") -> DependencyObservations:
    """npm lock/shrinkwrap v1: nested installed-layout observations, not installs.

    A requires edge resolves only to an exact nested/ancestor instance with a
    matching exact version. Ranges and aliases stay unknown without a resolver.
    """
    data, digest = _load(raw, path)
    if type(data.get("lockfileVersion")) is not int or data["lockfileVersion"] != 1:
        raise ValueError("unsupported_npm_lock_version")
    dependencies = data.get("dependencies")
    if type(dependencies) is not dict:
        raise ValueError("invalid_npm_dependencies")
    nodes, edges, gaps, entries, by_scope = [], [], [], [], {}
    stack = [(dependencies, (), path + ":/dependencies")]
    while stack:
        values, scope, prefix = stack.pop()
        if type(values) is not dict:
            raise ValueError("invalid_npm_dependencies")
        for name, item in sorted(values.items()):
            loc = prefix + "/" + name.replace("~", "~0").replace("/", "~1")
            if not re.fullmatch(r"(?:@[a-z0-9._-]+/)?[a-z0-9][a-z0-9._-]*", name) or type(item) is not dict:
                gaps.append(Gap("package_name_invalid", loc)); continue
            version = item.get("version")
            if not _text(version) or not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.+-]+)?", version):
                version = None
                gaps.append(Gap("version_or_alias_unsupported", loc + "/version"))
            identity = "npm:" + "/node_modules/".join((*scope, name))
            purl = f"pkg:npm/{quote(name, safe='/')}@{quote(version, safe='')}" if version else None
            node = Node(identity, name, version, purl, loc, "lock")
            nodes.append(node)
            by_scope[(scope, name)] = node
            entries.append((node, scope, item))
            if len(nodes) > MAX_NODES:
                raise ValueError("graph_limit_exceeded")
            if "dependencies" in item:
                stack.append((item["dependencies"], (*scope, name), loc + "/dependencies"))
    for node, scope, item in entries:
        requires = item.get("requires", {})
        if not isinstance(requires, dict):
            gaps.append(Gap("dependency_invalid", node.locator + "/requires")); continue
        for name, constraint in requires.items():
            loc = node.locator + "/requires/" + name.replace("~", "~0").replace("/", "~1")
            parent_scope = (*scope, node.name)
            found = None
            while True:
                found = by_scope.get((parent_scope, name))
                if found is not None or not parent_scope:
                    break
                parent_scope = parent_scope[:-1]
            if found is None:
                gaps.append(Gap("dependency_unresolved", loc))
            elif found.version is None or constraint != found.version:
                gaps.append(Gap("dependency_constraint_unverified", loc))
            else:
                edges.append(Edge(node.instance_id, found.instance_id, loc))
            if len(edges) > MAX_EDGES:
                raise ValueError("graph_limit_exceeded")
    return _result("npm-lock/1", path, digest, nodes, edges, gaps)


def _spdx(data, path, digest, fmt, positions=None):
    if data.get("spdxVersion") != "SPDX-2.3":
        raise ValueError("unsupported_spdx_version")
    packages = data.get("packages", [])
    relationships = data.get("relationships", [])
    if type(packages) is not list or type(relationships) is not list or len(packages) > MAX_NODES or len(relationships) > MAX_EDGES:
        raise ValueError("graph_limit_exceeded")
    projected, dependencies, gaps = [], [], []
    node_locs, edge_locs = {}, []
    for idx, item in enumerate(packages):
        loc = positions[0][idx] if positions else f"{path}:/packages/{idx}"
        ident = item.get("SPDXID") if type(item) is dict else None
        if not _text(ident) or not re.fullmatch(r"SPDXRef-[A-Za-z0-9.-]+", ident):
            gaps.append(Gap("component_identity_missing", loc)); continue
        if ident in node_locs:
            raise ValueError("duplicate_spdx_id")
        node_locs[ident] = loc
        external = item.get("externalRefs", [])
        if type(external) is not list:
            raise ValueError("spdx_external_refs_invalid")
        purls = [ref.get("referenceLocator") for ref in external if type(ref) is dict
                 and ref.get("referenceCategory") == "PACKAGE-MANAGER" and ref.get("referenceType") == "purl"]
        entry = {"bom-ref": ident, "name": item.get("name"), "version": item.get("versionInfo")}
        if len(purls) == 1 and _text(purls[0]):
            entry["purl"] = purls[0]
        elif purls:
            gaps.append(Gap("purl_ambiguous_or_invalid", loc))
        projected.append(entry)
    by_parent = {}
    for idx, item in enumerate(relationships):
        loc = positions[1][idx] if positions else f"{path}:/relationships/{idx}"
        if type(item) is not dict or not all(_text(item.get(key)) for key in ("spdxElementId", "relationshipType", "relatedSpdxElement")):
            gaps.append(Gap("dependency_invalid", loc)); continue
        parent, kind, child = (item[key] for key in ("spdxElementId", "relationshipType", "relatedSpdxElement"))
        if kind == "DEPENDENCY_OF":
            parent, child = child, parent
        elif kind in {"DESCRIBES", "DESCRIBED_BY"}:
            continue
        elif kind != "DEPENDS_ON":
            gaps.append(Gap("relationship_not_extracted", loc)); continue
        by_parent.setdefault(parent, []).append((child, loc))
    for parent, refs in by_parent.items():
        dependencies.append({"ref": parent, "dependsOn": [child for child, _ in refs]})
        edge_locs.append([loc for _, loc in refs])
    result = _cyclonedx({"bomFormat": "CycloneDX", "specVersion": "1.5", "components": projected,
                         "dependencies": dependencies}, path, digest, fmt)
    def original(locator):
        field = locator.removeprefix(path + ":/").split("/")
        if field[0] == "components" and len(field) > 1:
            return node_locs[projected[int(field[1])]["bom-ref"]]
        if field[0] == "dependencies" and len(field) > 1:
            entries = edge_locs[int(field[1])]
            return entries[int(field[3])] if len(field) > 3 else entries[0]
        return path

    return _result(fmt, path, digest, [replace(n, locator=node_locs[n.instance_id]) for n in result.nodes],
                   [replace(e, locator=original(e.locator)) for e in result.edges],
                   gaps + [Gap(g.code, original(g.locator)) for g in result.gaps])


def parse_spdx_json(raw: bytes, *, path: str = "sbom.spdx.json") -> DependencyObservations:
    data, digest = _load(raw, path)
    return _spdx(data, path, digest, "spdx-json/2.3")


def parse_spdx_tag_value(raw: bytes, *, path: str = "sbom.spdx") -> DependencyObservations:
    """SPDX 2.3 tag/value package sections and simple dependency relationships."""
    relative_path(path)
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise ValueError("input_limit_exceeded")
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("invalid_document") from exc
    packages, relationships, package_locs, relationship_locs = [], [], [], []
    data = {"packages": packages, "relationships": relationships}
    current = None
    block = False
    for line_number, line in enumerate(text.split("\n"), 1):
        if len(line) > 8192 or line_number > 131072:
            raise ValueError("structure_limit_exceeded")
        line = line.rstrip("\r")
        if block:
            if line.endswith("</text>"):
                block = False
            continue
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition(": ")
        if not sep or not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", key):
            raise ValueError("invalid_spdx_tag_value")
        if value.startswith("<text>"):
            if key in {"SPDXVersion", "PackageName", "SPDXID", "PackageVersion", "ExternalRef", "Relationship"}:
                raise ValueError("unexpected_multiline_spdx_field")
            block = not value.endswith("</text>")
            continue
        if key == "SPDXVersion":
            if "spdxVersion" in data:
                raise ValueError("duplicate_spdx_tag")
            data["spdxVersion"] = value
        elif key == "PackageName":
            current = {"name": value, "externalRefs": []}
            packages.append(current)
            package_locs.append(f"{path}#L{line_number}")
        elif key in {"FileName", "SnippetSPDXID", "LicenseID", "Annotator"}:
            current = None
        elif current is not None and key in {"SPDXID", "PackageVersion"}:
            field = "SPDXID" if key == "SPDXID" else "versionInfo"
            if field in current:
                raise ValueError("duplicate_spdx_tag")
            current[field] = value
        elif current is not None and key == "ExternalRef":
            parts = value.split(maxsplit=2)
            if len(parts) != 3:
                raise ValueError("spdx_external_refs_invalid")
            current["externalRefs"].append(dict(zip(("referenceCategory", "referenceType", "referenceLocator"), parts)))
        elif key == "Relationship":
            parts = value.split()
            if len(parts) != 3:
                raise ValueError("spdx_relationship_invalid")
            relationships.append(dict(zip(("spdxElementId", "relationshipType", "relatedSpdxElement"), parts)))
            relationship_locs.append(f"{path}#L{line_number}")
    if block:
        raise ValueError("unterminated_spdx_text")
    return _spdx(data, path, hashlib.sha256(raw).hexdigest(), "spdx-tag-value/2.3", (package_locs, relationship_locs))


def read_dependency_observations(session, path: str, *, format: str) -> DependencyObservations:
    """Read exactly one whitelisted inventory entry through A2's capability."""
    relative_path(path)
    readers = {"uv": parse_uv_lock, "cyclonedx-json": parse_cyclonedx_json, "cyclonedx-xml": parse_cyclonedx_xml,
               "spdx-json": parse_spdx_json, "spdx-tag-value": parse_spdx_tag_value, "npm-v1": parse_npm_lock_v1}
    for kind in ("poetry", "pdm", "pipfile"):
        readers[kind] = lambda raw, path, kind=kind: parse_python_lock(raw, format=kind, path=path)
    if format not in readers:
        raise ValueError("unsupported_format")
    entries = [entry for entry in session.inventory.entries if entry.relative_path == path]
    if len(entries) != 1 or type(entries[0].size_bytes) is not int or not 0 <= entries[0].size_bytes <= MAX_BYTES:
        raise ValueError("inventory_entry_invalid")
    raw = session.read_bytes(path, max_bytes=MAX_BYTES)
    if len(raw) != entries[0].size_bytes or hashlib.sha256(raw).hexdigest() != entries[0].sha256:
        raise ValueError("inventory_bytes_mismatch")
    return readers[format](raw, path=path)
