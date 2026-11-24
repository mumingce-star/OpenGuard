"""SBOM observations preserve explicit coordinates without upgrading evidence."""

import json
from urllib.parse import quote
from xml.etree.ElementTree import Element, SubElement, tostring

import pytest

import app.api  # Initialize the API package before loading its diff reader.
from app.p1.diff import _package_name, _purl_keys
from app.scanners.dependency_observations import (
    parse_cyclonedx_json, parse_cyclonedx_xml, parse_spdx_json, parse_spdx_tag_value,
)
from app.scanners.external_tools import _ecosystem_from_purl


def parse_document(kind, name, version, purl, group=None):
    if kind == "cyclonedx-json":
        item = {"bom-ref": "a", "name": name, "version": version, "purl": purl}
        if group is not None:
            item["group"] = group
        doc = {"bomFormat": "CycloneDX", "specVersion": "1.5", "components": [item]}
        return parse_cyclonedx_json(json.dumps(doc).encode())
    if kind == "cyclonedx-xml":
        bom = Element("bom", {"xmlns": "http://cyclonedx.org/schema/bom/1.5"})
        item = SubElement(SubElement(bom, "components"), "component", {"bom-ref": "a"})
        for label, value in (("name", name), ("version", version), ("purl", purl), ("group", group)):
            if value is not None:
                SubElement(item, label).text = value
        return parse_cyclonedx_xml(tostring(bom, encoding="utf-8"))
    if kind == "spdx-json":
        item = {"SPDXID": "SPDXRef-a", "name": name, "versionInfo": version, "externalRefs": [{
            "referenceCategory": "PACKAGE-MANAGER", "referenceType": "purl", "referenceLocator": purl,
        }]}
        return parse_spdx_json(json.dumps({"spdxVersion": "SPDX-2.3", "packages": [item]}).encode())
    document = (
        "SPDXVersion: SPDX-2.3\nDataLicense: CC0-1.0\nSPDXID: SPDXRef-DOCUMENT\n"
        f"PackageName: {name}\nSPDXID: SPDXRef-a\nPackageVersion: {version}\n"
        f"ExternalRef: PACKAGE-MANAGER purl {purl}\n"
    )
    return parse_spdx_tag_value(document.encode())


@pytest.mark.parametrize("kind", ["cyclonedx-json", "cyclonedx-xml", "spdx-json", "spdx-tag-value"])
@pytest.mark.parametrize(("ecosystem", "name", "version", "coordinate"), [
    ("golang", "example.com/Owner/module", "v1.2.3+incompatible", "example.com/Owner/module"),
    ("cargo", "demo_crate", "1.2.3-beta.1", "demo_crate"),
    ("maven", "org.demo:library", "1.2.Final", "org.demo/library"),
])
def test_valid_new_ecosystem_purls(kind, ecosystem, name, version, coordinate):
    purl = f"pkg:{ecosystem}/{coordinate}@{quote(version, safe='')}"
    group = None
    source_name = name
    if ecosystem == "maven" and kind.startswith("cyclonedx"):
        group, source_name = name.split(":")
    observed = parse_document(kind, source_name, version, purl, group=group)
    (node,) = observed.nodes
    assert (node.purl, node.name, node.version) == (purl, name, version)
    assert _ecosystem_from_purl(node.purl) == ecosystem
    assert not any(gap.code.startswith("purl_") for gap in observed.gaps)


@pytest.mark.parametrize(("name", "version", "purl", "reason"), [
    ("example.com/Owner/module", "v1.2.3", "pkg:golang/example.com/owner/module@v1.2.3", "purl_identity_conflict"),
    ("example.com/a", "v1.2.3", "pkg:golang/example.com/%2E%2E/a@v1.2.3", "purl_unsupported"),
    ("example.com/a", "v1.2.3", "pkg:golang/example.com%2Fa@v1.2.3", "purl_unsupported"),
    ("a", "1.2.3", "pkg:cargo/a@1.2.3?repository_url=x", "purl_unsupported"),
    ("a", "1.2.3", "pkg:cargo/a@1.2.3#src", "purl_unsupported"),
    ("a", "1.2.3", "pkg:cargo/a%00@1.2.3", "purl_unsupported"),
    ("a", "1.2.3", "pkg:cargo/a@1.2.3%0A", "purl_unsupported"),
    ("a", "1.2.3", "pkg:cargo/a@1.2.4", "purl_identity_conflict"),
    ("a", "1.0", "pkg:maven/org.demo/a@1.0", "purl_identity_conflict"),
    ("org.demo:a", "1.0", "pkg:maven/org.other/a@1.0", "purl_identity_conflict"),
])
def test_new_sbom_purls_never_override_declared_coordinates(name, version, purl, reason):
    report = parse_document("spdx-json", name, version, purl)
    (node,) = report.nodes
    assert node.purl is None
    assert node.name == name
    assert any(gap.code == reason for gap in report.gaps)


def test_diff_keys_keep_maven_identity_and_case_sensitive_go_modules():
    left = "example.com/Owner/module"
    right = "example.com/owner/module"
    assert _package_name("golang", left) == left
    assert _purl_keys(f"pkg:golang/{left}@v1.2.3") != _purl_keys(f"pkg:golang/{right}@v1.2.3")
    assert _purl_keys("pkg:maven/org.demo/library@1.0") == (
        "pkg:maven/org.demo/library", "pkg:maven/org.demo/library@1.0",
    )
    assert _purl_keys("pkg:cargo/a@1.2.3?name=value") == (None, None)
