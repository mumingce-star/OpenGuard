"""TEST_ONLY ZIP → production scanner → authenticated ASGI → immutable reports."""

from base64 import b64encode
from hashlib import sha256
from html import escape
import json
from pathlib import Path

import pytest

from app.domain.models import ComponentType
from test_task45_dependency_evidence_real_zip import ORIGIN, _checked, _match_evidence, _open_zip_gateway


_CHECKSUM = b64encode(sha256(b"task54-test-only-go-entry").digest()).decode("ascii")
_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
_CARGO_TOML = b'''[package]
name = "task54-cargo-root"
version = "2.1.0+test.4"
license = "MIT"

[dependencies]
alias = { package = "cargo-watch", version = "=1.2.3" }
cargo-range = "^2.0.0"
'''
_POM = b'''<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>org.task54</groupId><artifactId>java-root</artifactId><version>2.1.Final</version>
  <licenses><license><name>MIT</name></license></licenses>
  <properties><watch.version>1.0.Final</watch.version></properties>
  <dependencies>
    <dependency><groupId>org.task54</groupId><artifactId>watch</artifactId><version>${watch.version}</version></dependency>
  </dependencies>
</project>
'''


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENGUARD_ENABLE_REPORT_V2_1_1_WRITES", "1")
    yield from _open_zip_gateway(tmp_path, monkeypatch, assessment_and_p2=True)


def _headers(session):
    return {"Origin": ORIGIN, "X-CSRF-Token": session["csrf_token"]}


def _assessment(gateway, session, path, scan_ref):
    request_id = "task54-formal-multi-ecosystem"
    _checked(gateway.client.post(path + "/assessments", headers=_headers(session), json={
        "request_id": request_id, "usage": {"commercial": True, "distributed": True, "modified": True},
    }), 202)
    job = _checked(gateway.client.get(path + f"/assessments/jobs/{request_id}"), 200).json()
    assert job["status"] == "succeeded" and job["model_calls"] == 0
    assessment_path = path + f'/assessments/{job["assessment_id"]}'
    assessment = _checked(gateway.client.get(assessment_path), 200).json()
    assert assessment["formal"] and assessment["scan_id"] == scan_ref["scan_id"]
    assert assessment["facts_hash"] == scan_ref["facts_hash"]
    return assessment_path, assessment


def _sum_line(name, version):
    return f"{name} {version} h1:{_CHECKSUM}\n".encode("ascii")


def _mixed_members():
    return {
        "package.json": b'{"name":"task54-js-root","version":"1.0.0","license":"MIT","dependencies":{"legacy-js":"2.1.0"}}',
        "requirements.txt": b"legacy-pep==2.0.0\n",
        "go.mod": b"""module example.invalid/Task54Root

require (
    example.invalid/GoWatch v1.0.0
    example.invalid/GoHistory v1.0.0
    example.invalid/GoOtherDir v1.0.0
    example.invalid/GoModOnly v1.0.0
    example.invalid/CaseWatch v1.0.0
)
""",
        "go.sum": b"".join([
            _sum_line("example.invalid/GoWatch", "v1.2.0/go.mod"),
            _sum_line("example.invalid/GoWatch", "v1.2.0"),
            _sum_line("example.invalid/GoHistory", "v1.2.0"),
            _sum_line("example.invalid/GoHistory", "v1.3.0"),
            _sum_line("example.invalid/GoModOnly", "v1.2.0/go.mod"),
            _sum_line("example.invalid/casewatch", "v1.2.0"),
        ]),
        "independent/go.sum": _sum_line("example.invalid/GoOtherDir", "v1.2.0"),
        "Cargo.toml": _CARGO_TOML,
        "Cargo.lock": b'''version = 4

[[package]]
name = "cargo-watch"
version = "1.3.0"
source = "registry+https://example.invalid/cargo"

[[package]]
name = "cargo-range"
version = "3.0.0"
source = "registry+https://example.invalid/cargo"
''',
        "pom.xml": _POM,
        "gradle.lockfile": b"org.task54:watch:2.0.Final=compileClasspath\n",
        "task54.cdx.json": json.dumps({
            "bomFormat": "CycloneDX", "specVersion": "1.5", "components": [
                {"bom-ref": "task54-java-sbom", "type": "library", "group": "org.task54",
                 "name": "from-sbom", "version": "1.2.Final", "purl": "pkg:maven/org.task54/from-sbom@1.2.Final"},
            ],
        }).encode(),
    }


def test_task54_multilanguage_zip_to_filtered_resources_and_frozen_report(gateway):
    session = gateway.register("task54_report")
    files = _mixed_members()
    path, stored = gateway.upload(session, files, filename="task54-five-ecosystems.zip")
    run = stored.run
    assert run.status.value == "partial" and not run.provenance.ai_enabled
    assert {item.ecosystem for item in run.components} == {"golang", "cargo", "maven", "pypi", "npm"}
    for ecosystem in ("golang", "cargo", "maven", "pypi", "npm"):
        response = _checked(gateway.client.get(path + "/resources", params={"ecosystem": ecosystem}), 200).json()
        assert response["filters"]["ecosystem"] == ecosystem
        resources = {entry["resource"]["id"]: entry["resource"] for entry in response["items"]}
        assert set(resources) == {item.id for item in run.components if item.ecosystem == ecosystem}
        assert response["total"] == len(resources) and all(item["ecosystem"] == ecosystem for item in resources.values())
    _checked(gateway.client.get(path + "/resources", params={"ecosystem": "unsupported-task54"}), 422)

    roots = {item.ecosystem: item for item in run.components if item.component_type is ComponentType.APPLICATION}
    assert set(roots) == {"cargo", "maven", "npm"}
    assert roots["cargo"].purl == "pkg:cargo/task54-cargo-root@2.1.0%2Btest.4"
    assert roots["maven"].purl == "pkg:maven/org.task54/java-root@2.1.Final"

    page = gateway.project(path)
    rows = page["items"]
    assert page["next_cursor"] is None and page["returned"] == page["total"] == len(run.components) - len(roots)
    assert {row["resource_id"] for row in rows}.isdisjoint(item.id for item in roots.values())
    evidence = {entry.id: entry for entry in run.evidence}
    for row in rows:
        for ref in row["evidence"]:
            _match_evidence(ref, evidence[ref["evidence_id"]], ref["file_path"], files)
    assert len([error for error in run.errors if error.code == "lock_version_conflict"]) == 3
    expected = {
        ("golang", "example.invalid/GoWatch"): ("go.mod", "v1.0.0", "go.sum", "v1.2.0"),
        ("cargo", "cargo-watch"): ("Cargo.toml", "1.2.3", "Cargo.lock", "1.3.0"),
        ("maven", "org.task54:watch"): ("pom.xml", "1.0.Final", "gradle.lockfile", "2.0.Final"),
    }
    assert {(row["ecosystem"], row["name"]) for row in rows if row["conflicts"]} == set(expected)
    for row in rows:
        key = (row["ecosystem"], row["name"])
        if key not in expected:
            continue
        declaration, declared_version, locked, locked_version = expected[key]
        (conflict,) = row["conflicts"]
        assert row["role_state"] == "unknown" and conflict["status"] == "confirmed"
        assert conflict["code"] == "lock_version_conflict"
        for side, expected_file, version in (
            ("declaration", declaration, declared_version), ("lock", locked, locked_version),
        ):
            assert conflict[side]["version"] == version
            (ref,) = conflict[side]["evidence"]
            _match_evidence(ref, evidence[ref["evidence_id"]], expected_file, files)
    assert {row["version"] for row in rows if row["name"] == "example.invalid/GoHistory"} == {
        "v1.0.0", "v1.2.0", "v1.3.0",
    }
    assert {row["version"] for row in rows if row["name"] == "example.invalid/GoModOnly"} == {"v1.0.0"}
    assert {row["version"] for row in rows if row["name"] == "cargo-range"} == {None, "3.0.0"}
    (sbom,) = [row for row in rows if row["name"] == "org.task54:from-sbom"]
    assert sbom["ecosystem"] == "maven" and sbom["sources"] == ["sbom"]

    assessment_path, assessment = _assessment(gateway, session, path, page["scan_ref"])
    assert set(assessment["resource_ids"]) == {item.id for item in run.components}
    snapshot = _checked(gateway.client.post(assessment_path + "/report-v2", headers=_headers(session), json={
        "idempotency_key": "task54-report-archive", "schema_version": "1.1",
    }), 200).json()
    assert snapshot["schema_version"] == "1.1"
    assert snapshot["binding"]["assessment_ref"]["assessment_id"] == assessment["id"]
    assert snapshot["binding"]["scan_ref"] == page["scan_ref"]
    artifacts = {}
    for descriptor in snapshot["artifacts"]:
        response = _checked(gateway.client.get(descriptor["href"]), 200)
        digest = sha256(response.content)
        assert len(response.content) == descriptor["size_bytes"]
        assert digest.hexdigest() == descriptor["content_hash"]
        assert response.headers["Content-Digest"] == f"sha-256=:{b64encode(digest.digest()).decode('ascii')}:"
        artifacts[descriptor["format"]] = response.content
    assert set(artifacts) == {"json", "html"}
    document = json.loads(artifacts["json"])
    assert document["snapshot_id"] == snapshot["snapshot_id"] and document["binding"] == snapshot["binding"]
    (section,) = [s for s in document["sections"] if s["schema_version"] == "openguard-report-v2-dependency-evidence/1"]
    assert section["authority"] == "observation"
    assert section["content"]["items"] == rows
    assert section["content"]["scan_ref"] == page["scan_ref"]
    rendered = artifacts["html"].decode("utf-8")
    assert 'id="report-dependency-evidence"' in rendered
    for row in rows:
        assert row["resource_id"] in rendered and escape(row["name"]) in rendered
        assert f'<dd><code>{row["ecosystem"]}</code></dd>' in rendered
        for ref in row["evidence"]:
            assert ref["evidence_id"] in rendered and ref["source_sha256"] in rendered
    print("TASK54_ACTUAL_ZIP_REPORT=PASS ecosystems=5 conflicts=3 formats=html,json")


def _license_text(family):
    if family == "MIT":
        return (_FIXTURES / "task33/is-number-7.0.0/license.txt").read_bytes()
    source = json.loads((_FIXTURES / "task49-copyleft-licenses.json").read_text(encoding="utf-8"))["licenses"][family]
    raw = source["text"].encode("utf-8")
    assert len(raw) == source["bytes"] and sha256(raw).hexdigest() == source["sha256"]
    return raw


@pytest.mark.parametrize(("ecosystem", "manifest", "version"), [
    ("cargo", "Cargo.toml", "2.1.0+test.4"), ("maven", "pom.xml", "2.1.Final"),
])
@pytest.mark.parametrize(("family", "expected"), [("MIT", "UNKNOWN"), ("GPL-3.0", "COUNTER_EVIDENCE")])
def test_task54_root_local_material_is_never_release_support(gateway, ecosystem, manifest, version, family, expected):
    session = gateway.register("task54_material")
    files = {manifest: _CARGO_TOML if ecosystem == "cargo" else _POM}
    path, stored = gateway.upload(session, files, filename="task54-local-material.zip")
    (root,) = [item for item in stored.run.components if item.component_type is ComponentType.APPLICATION]
    assert root.ecosystem == ecosystem and root.version == version
    (declaration,) = [item for item in stored.run.licenses if item.id == root.license_expression_id]
    assert declaration.expression == "MIT" and declaration.verification_status.value == "pending"
    assessment_path, _ = _assessment(gateway, session, path, gateway.project(path)["scan_ref"])
    p2 = assessment_path + "/p2"
    binding = _checked(gateway.client.get(p2 + "/binding"), 200).json()
    initial = _checked(gateway.client.post(p2 + "/results", headers=_headers(session), json={
        "binding": binding, "expected_revision": 0, "parent_result_id": None,
        "idempotency_key": "task54-root-p2-init",
    }), 201).json()["result"]
    (row,) = [item for item in initial["resources"] if item["subject"]["resource_id"] == root.id]
    assert "exact_version_missing" not in row["gaps"]
    raw = _license_text(family)
    attached = _checked(gateway.client.post(p2 + "/materials", headers=_headers(session), json={
        "binding": binding, "expected_revision": initial["revision"], "parent_result_id": initial["result_id"],
        "idempotency_key": "task54-root-material", "subject": row["subject"], "evidence_ids": row["evidence_ids"],
        "filename": "LICENSE", "content_base64": b64encode(raw).decode("ascii"),
        "source_sha256": sha256(raw).hexdigest(), "source_description": "TEST_ONLY user-supplied license fixture",
        "completeness": "FULL_TEXT_CLAIMED",
    }), 201).json()["result"]
    view = _checked(gateway.client.get(p2 + f'/results/{attached["result_id"]}/material-claims',
                                      params={"assessment_version": binding["assessment_version"]}), 200).json()
    assert view["schema_version"] == "openguard-material-claims/4" and view["model_calls"] == 0
    (observation,) = [entry for entry in view["declaration_observations"] if entry["subject"] == row["subject"]]
    assert observation["evidence_status"] == "COMPLETE" and observation["expression"] == "MIT"
    assert all(entry["source_sha256"] == sha256(files[manifest]).hexdigest() for entry in observation["evidence"])
    (material,) = view["materials"]
    assert material["subject"] == row["subject"] and material["text_license"] == family
    assert material["role"] == "root_package" and material["role_state"] == "inferred"
    assert material["adoption_state"] == "OBSERVATION_ONLY" and material["source_binding"] == "NOT_ESTABLISHED"
    advice = [item for item in view["advice"] if item["subject"] == row["subject"]]
    assert len(advice) == 3 and all(item["state"] == expected for item in advice)
    assert not any(item["state"] == "SUPPORT" for item in view["advice"])
    if expected == "COUNTER_EVIDENCE":
        claims = [item for item in view["claims"] if item["subject"] == row["subject"]]
        assert len(claims) == 3 and all(
            any(item["code"] == "SPDX_TEXT_CONFLICT" for item in claim["counter_evidence"]) for claim in claims
        )
