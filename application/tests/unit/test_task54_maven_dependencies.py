"""Verify Maven and Gradle parsing without invoking any build tool."""

import hashlib

import pytest

from app.scanners import maven_dependencies as maven


def pom(body: str) -> bytes:
    return f'<project xmlns="http://maven.apache.org/POM/4.0.0">{body}</project>'.encode()


def dependency(group="org.example", artifact="test-kit", version="1.0"):
    version_field = "" if version is None else f"<version>{version}</version>"
    return f"<dependency><groupId>{group}</groupId><artifactId>{artifact}</artifactId>{version_field}</dependency>"


def codes(observations):
    return {gap.code for gap in observations.gaps}


def test_maven_namespaced_root_local_properties_and_exact_evidence():
    raw = pom("""
      <groupId>Com.Example</groupId><artifactId>demo-lib</artifactId><version>${revision}</version>
      <properties>
        <revision>1.2.3</revision><lab.version>${project.version}-dev</lab.version>
      </properties>
      <licenses><license><name>MIT</name></license></licenses>
      <dependencies>
        <dependency><groupId>${project.groupId}</groupId>
          <artifactId>example-kit</artifactId><version>${lab.version}</version></dependency>
        <dependency><groupId>dev.example</groupId>
          <artifactId>tooling</artifactId><version>2.4.1+test</version></dependency>
      </dependencies>
    """)
    result = maven.parse_pom(raw)
    assert result.format == "maven-pom/1" and result.status == "complete"
    assert result.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.source_path == "pom.xml" and not result.edges
    assert result.root.name == "Com.Example:demo-lib"
    assert result.root.version == "1.2.3"
    assert result.root.purl == "pkg:maven/Com.Example/demo-lib@1.2.3"
    assert dict(result.root.fields) == {
        "/project/groupId": "Com.Example", "/project/artifactId": "demo-lib",
        "/project/version": {"raw": "${revision}", "value": "1.2.3"},
    }
    assert result.root.license == ("/project/licenses/license/0/name", "MIT")
    assert result.nodes[0].name == "Com.Example:example-kit"
    assert result.nodes[0].version == "1.2.3-dev"
    assert result.nodes[0].locator == "pom.xml:/project/dependencies/dependency/0"
    assert result.nodes[0].excerpt == "${lab.version}"
    assert result.nodes[1].purl == "pkg:maven/dev.example/tooling@2.4.1%2Btest"


def test_maven_direct_dependencies_inherited_values_never_guessed():
    raw = pom(f"""
      <parent><groupId>foreign</groupId><artifactId>parent</artifactId><version>9.0</version></parent>
      <artifactId>module</artifactId>
      <dependencyManagement><dependencies>{dependency(artifact='managed-hidden')}</dependencies></dependencyManagement>
      <dependencies>
        {dependency(artifact='managed-direct', version=None)}
        {dependency(artifact='parent-version', version='${project.version}')}
        {dependency(artifact='direct-static', version='2.0-SNAPSHOT')}
      </dependencies>
      <profiles><profile><dependencies>{dependency(artifact='profile-only')}</dependencies></profile></profiles>
    """)
    result = maven.parse_pom(raw)
    assert result.root is None
    assert [(n.name, n.version) for n in result.nodes] == [
        ("org.example:managed-direct", None), ("org.example:parent-version", None),
        ("org.example:direct-static", "2.0-SNAPSHOT"),
    ]
    assert {
        "maven_parent_not_evaluated", "maven_dependency_management_not_evaluated",
        "maven_root_identity_not_static", "maven_property_unresolved",
        "maven_dependency_version_missing",
    } <= codes(result)


def test_maven_cyclic_undefined_and_range_selectors_remain_unresolved():
    root = "<groupId>org.example</groupId><artifactId>root</artifactId><version>1.0</version>"
    properties = "<properties><a>${b}</a><b>${a}</b></properties>"
    selectors = ["${a}", "${unknown}", "[1.0,2.0)", "LATEST", "1.+"]
    dependencies = "".join(dependency(artifact=f"case-{i}", version=v) for i, v in enumerate(selectors))
    result = maven.parse_pom(pom(root + properties + f"<dependencies>{dependencies}</dependencies>"))
    assert result.root.version == "1.0"
    assert result.status == "partial"
    assert len(result.nodes) == 5
    assert all(n.version is None and n.purl is None for n in result.nodes)
    assert [n.excerpt for n in result.nodes] == selectors
    assert codes(result) == {"maven_property_cycle", "maven_property_unresolved", "maven_version_not_exact"}


def test_maven_root_only_at_archive_root_and_single_license():
    raw = b"""<project>
      <groupId>org.example</groupId><artifactId>root</artifactId><version>1.0</version>
      <licenses><license><name>MIT</name></license><license><name>Apache-2.0</name></license></licenses>
      <dependencies><dependency><groupId>org.other</groupId><artifactId>pkg</artifactId><version>2</version>
      </dependency></dependencies></project>"""
    assert maven.parse_pom(raw).root.license is None
    nested = maven.parse_pom(raw, path="modules/foo/pom.xml")
    assert nested.root is None
    assert nested.nodes[0].locator == "modules/foo/pom.xml:/project/dependencies/dependency/0"


@pytest.mark.parametrize(("raw", "reason"), [
    (b"<!DOCTYPE project><project/>", "xml_dtd_or_entity_forbidden"),
    (b'<!ENTITY mark "TEST_ONLY"><project/>', "xml_dtd_or_entity_forbidden"),
    (b"<project>\x00</project>", "xml_dtd_or_entity_forbidden"),
    (b'<project xmlns:xi="http://www.w3.org/2001/XInclude"><xi:include href="ignored"/></project>',
     "xml_xinclude_forbidden"),
    (b'<?xml version="1.0" encoding="latin1"?><project/>', "invalid_xml_encoding"),
    (b'<project xmlns="http://example.invalid/foreign"/>', "unsupported_maven_pom_namespace"),
    (b"<project><groupId>a</groupId><groupId>b</groupId></project>", "duplicate_xml_field"),
    (b"<project><version><b/>1</version></project>", "invalid_xml_scalar_field"),
])
def test_maven_unsafe_or_ambiguous_xml_rejected(raw, reason):
    with pytest.raises(ValueError, match=reason):
        maven.parse_pom(raw)


def test_maven_depth_node_and_property_bounds(monkeypatch):
    monkeypatch.setattr(maven, "MAX_DEPTH", 2)
    with pytest.raises(ValueError, match="structure_limit_exceeded"):
        maven.parse_pom(b"<project><a><b><c/></b></a></project>")
    monkeypatch.setattr(maven, "MAX_NODES", 4)
    with pytest.raises(ValueError, match="structure_limit_exceeded"):
        maven.parse_pom(b"<project><a/><b/><c/><d/></project>")
    monkeypatch.setattr(maven, "MAX_BYTES", 10)
    with pytest.raises(ValueError, match="input_limit_exceeded"):
        maven.parse_pom(b"<project/> extra")


def test_gradle_lock_flat_coordinates_and_exact_line_evidence():
    raw = (b"# Generated lock\nempty=testFixtures\n"
           b"org.example:demo:1.2.3=runtimeClasspath,testCompileClasspath\n"
           b"org.example:demo:2.0.0=compileClasspath\n"
           b"org.example:tooling:1.0+metadata=testRuntimeClasspath\n"
           b"org.example:broken:1.+=runtimeClasspath\n"
           b"../x:bad:1.0=runtimeClasspath\n"
           b"org.example:bad:1.0=\n"
           b"unstructured line\n")
    result = maven.parse_gradle_lock(raw, path="sub/gradle.lockfile")
    assert result.format == "gradle-lock/1" and result.status == "partial" and not result.edges
    assert result.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert [(n.name, n.version, n.locator) for n in result.nodes] == [
        ("org.example:demo", "1.2.3", "sub/gradle.lockfile:/lines/3"),
        ("org.example:demo", "2.0.0", "sub/gradle.lockfile:/lines/4"),
        ("org.example:tooling", "1.0+metadata", "sub/gradle.lockfile:/lines/5"),
    ]
    assert result.nodes[-1].purl == "pkg:maven/org.example/tooling@1.0%2Bmetadata"
    assert codes(result) == {"gradle_lock_line_invalid"}
    assert [gap.locator for gap in result.gaps] == [
        f"sub/gradle.lockfile:/lines/{no}" for no in range(6, 10)
    ]


def test_gradle_lock_uses_parser_caps_even_when_records_are_invalid(monkeypatch):
    monkeypatch.setattr(maven, "MAX_NODES", 2)
    with pytest.raises(ValueError, match="graph_limit_exceeded"):
        maven.parse_gradle_lock(b"broken\nbroken\nbroken")
