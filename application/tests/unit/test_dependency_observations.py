"""Synthetic parser tests: no target execution, source admission, or POSIX stub."""
import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.ingestion.inventory import Inventory, InventoryEntry
from app.scanners import dependency_observations as parser
from app.security.errors import IngestionSecurityError


UV = b'''version = 1
revision = 3
[[package]]
name = "demo"
version = "1.0.0"
source = { virtual = "." }
dependencies = [{ name = "some_pkg", version = "2.0.0" }]
[[package]]
name = "some-pkg"
version = "2.0.0"
source = { registry = "https://pypi.org/simple" }
dependencies = [{ name = "demo" }]
'''


def bom(**updates):
    data = {"bomFormat": "CycloneDX", "specVersion": "1.5", "components": [
        {"bom-ref": "a", "name": "a", "version": "1.0.0", "purl": "pkg:npm/a@1.0.0"},
        {"bom-ref": "b", "name": "b", "version": "2.0.0", "purl": "pkg:pypi/b@2.0.0"},
    ], "dependencies": [{"ref": "a", "dependsOn": ["b"]}, {"ref": "b", "dependsOn": ["a"]}]}
    data.update(updates)
    return json.dumps(data).encode()


def codes(result):
    return {gap.code for gap in result.gaps}


def test_uv_cycle_and_locations_are_observations():
    result = parser.parse_uv_lock(UV, path="sub/uv.lock")
    assert result.status == "complete"
    assert [(n.name, n.version) for n in result.nodes] == [("demo", "1.0.0"), ("some-pkg", "2.0.0")]
    assert {(e.parent, e.child) for e in result.edges} == {("uv:0", "uv:1"), ("uv:1", "uv:0")}
    assert result.nodes[1].locator == "sub/uv.lock:/package/1"
    assert result.source_sha256 == hashlib.sha256(UV).hexdigest()
    assert "not_installation" in result.semantics
    assert parser.parse_uv_lock(UV, path="sub/uv.lock") == result


@pytest.mark.parametrize("revision", [1, 2, 3])
def test_uv_revisions(revision):
    assert parser.parse_uv_lock(UV.replace(b"revision = 3", f"revision = {revision}".encode())).status == "complete"


@pytest.mark.parametrize("old,new", [(b"version = 1\n", b"version = 2\n"), (b"revision = 3", b"revision = 4"), (b"version = 1\n", b"version = true\n")])
def test_uv_unknown_version_rejected(old, new):
    with pytest.raises(ValueError, match="unsupported_uv"):
        parser.parse_uv_lock(UV.replace(old, new, 1))


def test_uv_multiple_versions_and_unresolved_are_not_guessed():
    raw = UV.replace(b', version = "2.0.0"', b"") + b'''[[package]]
name = "some-pkg"
version = "3.0.0"
source = { registry = "https://pypi.org/simple" }
dependencies = [{name = "absent"}]
'''
    result = parser.parse_uv_lock(raw)
    assert len(result.nodes) == 3
    assert codes(result) == {"dependency_ambiguous", "dependency_unresolved"}
    assert len(result.edges) == 1


@pytest.mark.parametrize("replacement,code", [
    (b'virtual = "../escape"', "workspace_path_unsafe"),
    (b'virtual = "C:/escape"', "workspace_path_unsafe"),
    (b'registry = "https://user:password@example.test/simple"', "source_url_unsupported"),
    (b'unknown = "x"', "source_invalid"),
])
def test_uv_source_rejections(replacement, code):
    result = parser.parse_uv_lock(UV.replace(b'virtual = "."', replacement))
    assert code in codes(result)
    assert all(n.name != "demo" for n in result.nodes)


def test_uv_missing_version_and_conditional_edges():
    raw = UV.replace(b'version = "1.0.0"\n', b"").replace(b'{ name = "demo" }', b'{ name = "demo", marker = "python_version < 4" }')
    result = parser.parse_uv_lock(raw)
    assert result.nodes[0].purl is None
    assert codes(result) == {"version_missing", "conditional_edge_not_evaluated"}


def test_cdx_multiversion_cycle_and_purl():
    result = parser.parse_cyclonedx_json(bom())
    assert result.status == "complete"
    assert {(e.parent, e.child) for e in result.edges} == {("a", "b"), ("b", "a")}
    assert result.nodes[1].purl == "pkg:pypi/b@2.0.0"


def test_cdx_scoped_package_and_same_name_instances():
    raw = bom(components=[
        {"bom-ref": "a", "group": "@scope", "name": "lib", "version": "1", "purl": "pkg:npm/%40scope/lib@1"},
        {"bom-ref": "b", "group": "@scope", "name": "lib", "version": "2", "purl": "pkg:npm/%40scope/lib@2"},
    ])
    result = parser.parse_cyclonedx_json(raw)
    assert len(result.nodes) == 2 and result.status == "complete"


def test_cdx_conflict_and_nested_are_explicit():
    raw = bom(components=[{"bom-ref": "a", "name": "a", "version": "1", "purl": "pkg:npm/other@2", "components": [{"name": "nested"}]}])
    result = parser.parse_cyclonedx_json(raw)
    assert {"purl_identity_conflict", "nested_components_unsupported", "dependency_unresolved", "dependency_parent_unresolved"} <= codes(result)
    assert result.nodes[0].purl is None


def test_cdx_duplicate_refs_rejected():
    raw = bom(components=[{"bom-ref": "a", "name": "a"}, {"bom-ref": "a", "name": "b"}])
    with pytest.raises(ValueError, match="duplicate_bom_ref"):
        parser.parse_cyclonedx_json(raw)


def test_cdx_orphans_duplicates_and_missing_graph():
    result = parser.parse_cyclonedx_json(bom(dependencies=[{"ref": "a", "dependsOn": ["b", "b", "absent"]}]))
    assert len(result.edges) == 1
    assert codes(result) == {"duplicate_dependency_edge", "dependency_unresolved"}
    assert "dependency_graph_not_provided" in codes(parser.parse_cyclonedx_json(bom(dependencies=[])))


@pytest.mark.parametrize("raw", [b"{", b"[]", b'{"a":1,"a":2}', b'{"a":NaN}', b"\xff", b'{"a":"\\ud800"}'])
def test_invalid_json(raw):
    with pytest.raises(ValueError):
        parser.parse_cyclonedx_json(raw)


@pytest.mark.parametrize("version", ["1.4", "1.6", 1.5, None])
def test_cdx_unknown_version(version):
    with pytest.raises(ValueError, match="unsupported_cyclonedx"):
        parser.parse_cyclonedx_json(bom(specVersion=version))


@pytest.mark.parametrize("path", ["../bom.json", "/bom.json", "C:/bom.json", "a\\bom.json", "a//bom.json", "a/./bom.json"])
def test_path_rejected_before_read(path):
    with pytest.raises(ValueError, match="unsafe_source_path"):
        parser.read_dependency_observations(None, path, format="uv")


def test_limits(monkeypatch):
    monkeypatch.setattr(parser, "MAX_BYTES", 1)
    with pytest.raises(ValueError, match="input_limit"):
        parser.parse_uv_lock(UV)
    monkeypatch.setattr(parser, "MAX_BYTES", 100000)
    monkeypatch.setattr(parser, "MAX_NODES", 1)
    with pytest.raises(ValueError):
        parser.parse_cyclonedx_json(bom())
    with pytest.raises(ValueError):
        parser.parse_uv_lock(UV)


def test_session_hash_size_and_allowlist():
    entry = SimpleNamespace(relative_path="uv.lock", size_bytes=len(UV), sha256=hashlib.sha256(UV).hexdigest())
    calls = []
    def read(path, *, max_bytes):
        calls.append((path, max_bytes))
        return UV
    session = SimpleNamespace(inventory=SimpleNamespace(entries=[entry]), read_bytes=read)
    assert parser.read_dependency_observations(session, "uv.lock", format="uv").status == "complete"
    assert calls == [("uv.lock", parser.MAX_BYTES)]
    entry.sha256 = "0" * 64
    with pytest.raises(ValueError, match="inventory_bytes_mismatch"):
        parser.read_dependency_observations(session, "uv.lock", format="uv")
    with pytest.raises(ValueError, match="inventory_entry_invalid"):
        parser.read_dependency_observations(session, "other.lock", format="uv")


@pytest.mark.parametrize("format,header", [
    ("poetry", '[metadata]\nlock-version = "2.1"'),
    ("pdm", '[metadata]\nlock_version = "4.5"'),
])
def test_selected_python_lock_schemas(format, header):
    raw = (header + '\n[[package]]\nname="Some_Pkg"\nversion="1.0"\n[[package]]\nname="Some-Pkg"\nversion="2.0"\n').encode()
    result = parser.parse_python_lock(raw, format=format, path=format + '.lock')
    assert [node.version for node in result.nodes] == ["1.0", "2.0"]
    assert all(node.name == "some-pkg" for node in result.nodes)
    assert codes(result) == {"dependency_graph_not_extracted"}
    with pytest.raises(ValueError, match="unsupported"):
        parser.parse_python_lock(raw.replace(b'"2.1"', b'"0.0"').replace(b'"4.5"', b'"0.0"'), format=format, path=format + '.lock')


def test_pipfile_scope_and_nonexact_version():
    raw = json.dumps({"_meta": {"pipfile-spec": 6}, "default": {"pkg": {"version": "==1.0"}}, "develop": {"pkg": {"version": "==2.*"}}}).encode()
    result = parser.parse_python_lock(raw, format="pipfile", path="Pipfile.lock")
    assert [node.version for node in result.nodes] == ["1.0", None]
    assert result.nodes[0].locator == "Pipfile.lock:/default/pkg"
    assert "version_missing" in codes(result)


def test_npm_nested_scope_closest_instance_and_cycle():
    raw = json.dumps({"lockfileVersion": 1, "dependencies": {
        "a": {"version": "1.0.0", "requires": {"b": "2.0.0"}, "dependencies": {
            "b": {"version": "2.0.0", "requires": {"a": "1.0.0"}}
        }}, "b": {"version": "3.0.0"}, "@scope/pkg": {"version": "1.0.0"}
    }}).encode()
    result = parser.parse_npm_lock_v1(raw, path="npm-shrinkwrap.json")
    assert result.status == "complete"
    assert len(result.nodes) == 4
    assert {(e.parent, e.child) for e in result.edges} == {("npm:a", "npm:a/node_modules/b"), ("npm:a/node_modules/b", "npm:a")}
    assert result.nodes[0].purl == "pkg:npm/%40scope/pkg@1.0.0"


def test_npm_alias_ranges_missing_and_bool_version():
    raw = json.dumps({"lockfileVersion": 1, "dependencies": {
        "alias": {"version": "npm:real@1.0.0"},
        "a": {"version": "1.0.0", "requires": {"a": "^1.0.0", "b": "1.0.0"}}
    }}).encode()
    result = parser.parse_npm_lock_v1(raw)
    assert codes(result) == {"version_or_alias_unsupported", "dependency_constraint_unverified", "dependency_unresolved"}
    assert result.edges == ()
    with pytest.raises(ValueError, match="unsupported_npm"):
        parser.parse_npm_lock_v1(raw.replace(b'"lockfileVersion": 1', b'"lockfileVersion": true'))


def test_p0_mapping_keeps_workspace_instances_and_pending_evidence():
    from datetime import datetime, timezone
    from app.scanners.dependency_observation_mapper import map_sealed_dependency_document
    from app.p2b._resource_roles import assess_resource_roles
    paths = ["one/uv.lock", "two/uv.lock"]
    entries = [SimpleNamespace(relative_path=p, size_bytes=len(UV), sha256=hashlib.sha256(UV).hexdigest()) for p in paths]
    session = SimpleNamespace(inventory=SimpleNamespace(entries=entries, root_digest="a" * 64), read_bytes=lambda path, max_bytes: UV)
    now = datetime(2026, 11, 16, tzinfo=timezone.utc)
    mapped = [map_sealed_dependency_document(session, path, format="uv", observed_at=now) for path in paths]
    assert set(c.id for c in mapped[0].components).isdisjoint(c.id for c in mapped[1].components)
    for result in mapped:
        assert all(e.verification_status.value == "pending" and e.excerpt is None for e in result.evidence)
        assert all(c.license_expression_id is None and c.source_url is None for c in result.components)
        ids = {c.id for c in result.components}
        assert all(e.parent in ids and e.child in ids for e in result.edges)
        assert result.status == "complete"
        for row in assess_resource_roles(result.components, result.evidence):
            roles = {item.role: item for item in row.roles}
            assert roles["declared"].status == "inferred"
            assert roles["declared"].evidence[0].source == "lock"
            assert roles["build"].status == roles["delivered"].status == "unknown"
    assert mapped[0] == map_sealed_dependency_document(session, paths[0], format="uv", observed_at=now)
    with pytest.raises(ValueError, match="observation_time"):
        map_sealed_dependency_document(session, paths[0], format="uv", observed_at=datetime(2026, 11, 16))


def test_cyclonedx_xml_matches_json_instances_and_edges():
    raw = b'''<bom xmlns="http://cyclonedx.org/schema/bom/1.5">
<components><component bom-ref="a"><name>a</name><version>1.0.0</version><purl>pkg:npm/a@1.0.0</purl></component>
<component bom-ref="b"><name>b</name><version>2.0.0</version><purl>pkg:pypi/b@2.0.0</purl></component></components>
<dependencies><dependency ref="a"><dependency ref="b"/></dependency><dependency ref="b"><dependency ref="a"/></dependency></dependencies></bom>'''
    xml, js = parser.parse_cyclonedx_xml(raw), parser.parse_cyclonedx_json(bom())
    assert xml.status == js.status == "complete"
    assert [n.purl for n in xml.nodes] == [n.purl for n in js.nodes]
    assert [(e.parent, e.child) for e in xml.edges] == [(e.parent, e.child) for e in js.edges]


@pytest.mark.parametrize("raw,error", [
    (b'<!DOCTYPE bom SYSTEM "http://example.test/evil"><bom/>', "dtd_or_entity"),
    (b'<!DOCTYPE bom [<!ENTITY evil SYSTEM "file:///outside">]><bom>&evil;</bom>', "dtd_or_entity"),
    (b'<bom xmlns="http://cyclonedx.org/schema/bom/1.6"/>', "unsupported_cyclonedx"),
    (b'<bom xmlns="http://cyclonedx.org/schema/bom/1.5"><include xmlns="http://www.w3.org/2001/XInclude" href="outside"/></bom>', "xinclude"),
    (b'<bom', "invalid_xml"),
])
def test_xml_fail_closed(raw, error):
    with pytest.raises(ValueError, match=error):
        parser.parse_cyclonedx_xml(raw)


SPDX = b'''SPDXVersion: SPDX-2.3
SPDXID: SPDXRef-DOCUMENT
PackageName: a
SPDXID: SPDXRef-A
PackageVersion: 1.0.0
ExternalRef: PACKAGE-MANAGER purl pkg:npm/a@1.0.0
PackageName: b
SPDXID: SPDXRef-B
PackageVersion: 2.0.0
PackageComment: <text>line
PackageName: ignored
</text>
Relationship: SPDXRef-B DEPENDENCY_OF SPDXRef-A
'''


def test_spdx_tag_value_ignores_multiline_text_and_retains_orig_positions():
    result = parser.parse_spdx_tag_value(SPDX)
    assert [node.name for node in result.nodes] == ["a", "b"]
    assert result.nodes[0].locator == "sbom.spdx#L3"
    assert result.nodes[0].purl == "pkg:npm/a@1.0.0"
    assert result.edges == (parser.Edge("SPDXRef-A", "SPDXRef-B", "sbom.spdx#L13"),)


def test_spdx_json_orphan_conflicting_purl_and_orig_positions():
    raw = json.dumps({"spdxVersion": "SPDX-2.3", "packages": [{"name": "a", "SPDXID": "SPDXRef-A", "versionInfo": "1",
        "externalRefs": [{"referenceCategory": "PACKAGE-MANAGER", "referenceType": "purl", "referenceLocator": "pkg:npm/a@2"}]}],
        "relationships": [{"spdxElementId": "SPDXRef-A", "relatedSpdxElement": "SPDXRef-B", "relationshipType": "DEPENDS_ON"}]}).encode()
    result = parser.parse_spdx_json(raw)
    assert {g.locator for g in result.gaps} == {"sbom.spdx.json:/packages/0", "sbom.spdx.json:/relationships/0"}
    assert codes(result) == {"purl_identity_conflict", "dependency_unresolved"}
    assert result.edges == ()
    assert result.nodes[0].purl is None


@pytest.mark.parametrize("raw,error", [
    (SPDX.replace(b"2.3", b"2.2", 1), "unsupported_spdx"),
    (SPDX.replace(b"</text>", b""), "unterminated_spdx"),
    (SPDX.replace(b"SPDXRef-B", b"SPDXRef-A"), "duplicate_spdx_id"),
])
def test_spdx_negative_cases(raw, error):
    with pytest.raises(ValueError, match=error):
        parser.parse_spdx_tag_value(raw)


class ObservationSession:
    def __init__(self, documents, *, quota=None):
        self.documents = documents
        self.inventory = Inventory(
            tuple(InventoryEntry(path, len(raw), hashlib.sha256(raw).hexdigest())
                  for path, raw in documents.items()),
            "a" * 64,
        )
        self.remaining_read_bytes = sum(map(len, documents.values())) if quota is None else quota
        self.reads = []

    def read_many_bytes(self, paths, *, max_bytes):
        assert paths and len(set(paths)) == len(paths)
        documents = {path: self.documents[path] for path in paths}
        assert all(0 < len(raw) <= max_bytes for raw in documents.values())
        size = sum(map(len, documents.values()))
        assert size <= self.remaining_read_bytes
        self.remaining_read_bytes -= size
        self.reads.extend(paths)
        return documents

    def read_bytes(self, path, *, max_bytes):
        return self.read_many_bytes((path,), max_bytes=max_bytes)[path]


def collect_observations(session, *, remaining_budget):
    from app.scanners.dependency_observation_mapper import collect_dependency_observations

    return collect_dependency_observations(
        session, datetime(2026, 11, 22, tzinfo=timezone.utc), remaining_budget=remaining_budget,
    )


NPM_V1 = b'{"lockfileVersion":1,"dependencies":{"a":{"version":"1.0.0"}}}'
POETRY = b'''[[package]]
name = "a"
version = "1.0"
[metadata]
lock-version = "2.1"
'''
PDM = POETRY.replace(b'lock-version = "2.1"', b'lock_version = "4.5"')
PIPFILE = b'{"_meta":{"pipfile-spec":6},"default":{"a":{"version":"==1.0"}},"develop":{}}'
CDX_XML = b'''<bom xmlns="http://cyclonedx.org/schema/bom/1.5"><components>
<component bom-ref="a"><name>a</name><version>1.0</version></component>
</components></bom>'''
SPDX_JSON = b'''{"spdxVersion":"SPDX-2.3","packages":[
{"name":"a","SPDXID":"SPDXRef-A","versionInfo":"1.0"}
]}'''


@pytest.mark.parametrize("path,raw,source_kind", [
    ("work/uv.lock", UV, "lock"),
    ("work/poetry.lock", POETRY, "lock"),
    ("work/pdm.lock", PDM, "lock"),
    ("work/Pipfile.lock", PIPFILE, "lock"),
    ("work/package-lock.json", NPM_V1, "lock"),
    ("work/npm-shrinkwrap.json", NPM_V1, "lock"),
    ("work/bom.json", bom(), "sbom"),
    ("work/release.cdx.json", bom(), "sbom"),
    ("work/bom.xml", CDX_XML, "sbom"),
    ("work/release.cdx.xml", CDX_XML, "sbom"),
    ("work/sbom.spdx.json", SPDX_JSON, "sbom"),
    ("work/sbom.spdx", SPDX, "sbom"),
])
def test_collector_routes_supported_documents(path, raw, source_kind):
    session = ObservationSession({path: raw})
    (mapping,) = collect_observations(session, remaining_budget=len(raw))
    assert session.reads == [path]
    assert mapping.components and mapping.evidence
    for evidence in mapping.evidence:
        assert evidence.locator.partition(":")[0] == path
        assert evidence.producer.name == f"openguard.dependency-observations.{source_kind}"
        assert evidence.content_hash.value == hashlib.sha256(raw).hexdigest()
        assert evidence.verification_status.value == "pending"


@pytest.mark.parametrize("path", ["package-lock.json", "npm-shrinkwrap.json"])
@pytest.mark.parametrize("version", [b"2", b"3", b"true"])
def test_collector_accepts_only_real_npm_lock_v1(path, version):
    raw = NPM_V1.replace(b'"lockfileVersion":1', b'"lockfileVersion":' + version)
    session = ObservationSession({path: raw})
    assert collect_observations(session, remaining_budget=len(raw)) == ()


def test_collector_ignores_path_lookalikes_and_unrelated_manifests():
    session = ObservationSession({
        "my-bom.json": bom(),
        "work/release.cdx.json.bak": bom(),
        "work/release.cdx.xml.bak": CDX_XML,
        "work/sbom.spdx.json.bak": SPDX_JSON,
        "work/more.spdx.tmp": SPDX,
        "work/my-poetry.lock": POETRY,
        "work/pipfile.lock": PIPFILE,
        "work/uv.lock.tmp": UV,
        "work/package.json": NPM_V1,
        "work/pyproject.toml": UV,
    })
    assert collect_observations(session, remaining_budget=session.remaining_read_bytes) == ()
    assert session.reads == []


def test_collector_uses_smaller_residual_and_skips_files_that_do_not_fit():
    session = ObservationSession({
        "d/uv.lock": UV,
        "c/uv.lock": UV,
        "b/uv.lock": UV + b"\n" * len(UV),
        "a/uv.lock": UV,
    }, quota=2 * len(UV))
    mappings = collect_observations(session, remaining_budget=4 * len(UV))
    assert session.reads == ["a/uv.lock", "c/uv.lock"]
    assert [mapping.evidence[0].locator for mapping in mappings] == [
        "a/uv.lock:/package/0",
        "c/uv.lock:/package/0",
    ]
    assert session.remaining_read_bytes == 0
    assert collect_observations(session, remaining_budget=len(UV)) == ()
    assert session.reads == ["a/uv.lock", "c/uv.lock"]


def test_collector_bounds_document_size_and_honors_explicit_budget():
    limit = parser.MAX_BYTES
    exact_limit = UV + b"\n" * (limit - len(UV))
    session = ObservationSession({
        "e/uv.lock": UV,
        "d/uv.lock": UV,
        "c/uv.lock": exact_limit,
        "b/uv.lock": exact_limit + b"\n",
        "a/uv.lock": b"",
    })
    assert len(collect_observations(session, remaining_budget=limit + len(UV))) == 2
    assert session.reads == ["c/uv.lock", "d/uv.lock"]


def test_collector_isolates_malformed_documents_without_refunding_bytes():
    malformed = b"{"
    session = ObservationSession({"c/uv.lock": UV, "b/uv.lock": UV, "a/bom.json": malformed})
    (mapping,) = collect_observations(session, remaining_budget=len(malformed) + len(UV))
    assert session.reads == ["a/bom.json", "b/uv.lock"]
    assert all(evidence.locator.startswith("b/uv.lock:/") for evidence in mapping.evidence)


def test_collector_preserves_sealed_session_integrity_failures(monkeypatch):
    session = ObservationSession({"uv.lock": UV})

    def fail_read(*args, **kwargs):
        raise IngestionSecurityError("scanner_failed", "scan_file_integrity_failed")

    monkeypatch.setattr(session, "read_many_bytes", fail_read)
    with pytest.raises(IngestionSecurityError, match="scan_file_integrity_failed"):
        collect_observations(session, remaining_budget=len(UV))
