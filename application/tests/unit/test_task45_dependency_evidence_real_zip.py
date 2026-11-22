"""TASK45 P0.1: synthetic test input, actual ZIP ingestion and authenticated ASGI."""

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import socket
from zipfile import ZipFile, ZipInfo

import pytest
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from app.api.main import create_default_app
from app.assessment.engine import facts_digest
from app.domain.models import ComponentType
from app.local_accounts import LocalAccountGateway


ORIGIN = "http://127.0.0.1:48145"
ZIP_ROUTE = "/api/v1/scans"
PROJECTION = "/dependency-evidence"
SCHEMA = "openguard-dependency-evidence/1"
ROOT_PACKAGE = b'{"name":"task45-test-only-root","version":"1.0.0","license":"MIT"}'
ISOLATED_ENV = {
    "OPENGUARD_ENABLE_P2": "0",
    "OPENGUARD_ENABLE_PUBLIC_GIT": "0",
    "OPENGUARD_ENABLE_ASSISTANT": "0",
    "OPENGUARD_ENABLE_P2_AI": "0",
    "OPENGUARD_ENABLE_AI": "0",
    "OPENGUARD_OLLAMA_DOCKER_HOST": "0",
    "OPENGUARD_ENABLE_P2_CHAT": "0",
    "OPENGUARD_ENABLE_ASSESSMENTS": "0",
    "OPENGUARD_ENABLE_EXTERNAL_SCANNERS": "0",
    "OPENGUARD_ENABLE_PROFILE_METADATA": "0",
    "OPENGUARD_ENABLE_DURABLE_ZIP": "0",
    "OPENGUARD_ENABLE_PROGRESS_EVENTS": "0",
    "OPENGUARD_OFFICIAL_SOURCE_AUTO": "0",
    "OPENGUARD_OFFICIAL_JOBS_ENABLED": "0",
    "OPENGUARD_P2_DATA_SCOPE": "TEST_ONLY",
    "OPENGUARD_WEB_ORIGINS": ORIGIN,
}


async def _frontend(scope, receive, send):
    await JSONResponse({"data_scope": "TEST_ONLY"})(scope, receive, send)


def _checked(response, status):
    # Avoid copying request headers, cookies or auth payloads into test capture.
    if response.status_code != status:
        raise AssertionError(f"Expected HTTP {status}; got HTTP {response.status_code}")
    return response


@dataclass
class GatewayHarness:
    client: TestClient
    gateway: LocalAccountGateway
    roots: dict[str, Path]

    def register(self, name):
        initial = _checked(self.client.get("/api/v1/auth/session"), 200).json()
        response = self.client.post(
            "/api/v1/auth/register",
            headers={"Origin": ORIGIN, "X-CSRF-Token": initial["csrf_token"]},
            json={"username": name, "password": "SparseSyntheticOnly45!"},
        )
        return _checked(response, 201).json()

    def logout(self, session):
        response = self.client.post(
            "/api/v1/auth/logout",
            headers={"Origin": ORIGIN, "X-CSRF-Token": session["csrf_token"]},
            json={},
        )
        _checked(response, 200)

    def upload(self, session, files, *, filename="task45-p01-test-only.zip"):
        archive = BytesIO()
        with ZipFile(archive, "w") as output:
            for name, content in sorted(files.items()):
                output.writestr(ZipInfo(name, date_time=(2026, 11, 22, 0, 0, 0)), content)
        raw = archive.getvalue()
        accepted = _checked(self.client.post(
            ZIP_ROUTE,
            headers={"Origin": ORIGIN, "X-CSRF-Token": session["csrf_token"]},
            data={"source_type": "zip"},
            files={"file": (filename, raw, "application/zip")},
        ), 202).json()
        app = self.gateway.apps[session["user"]["id"]]
        registry = app.state.scan_api_service._registry
        stored = registry.get(accepted["scan_id"])
        assert stored.run.provenance.input_digest.value == sha256(raw).hexdigest()
        assert stored.run.project.source_type.value == "zip"
        assert stored.run.provenance.ai_enabled is False
        status = _checked(self.client.get(accepted["status_url"]), 200).json()
        assert status["status"] == stored.run.status.value
        return accepted["status_url"], stored

    def project(self, path, **params):
        response = _checked(self.client.get(path + PROJECTION, params=params), 200)
        assert response.headers.get("cache-control") == "no-store"
        data = response.json()
        assert data["schema_version"] == SCHEMA
        return data


@pytest.fixture
def zip_gateway(tmp_path, monkeypatch):
    for key, value in ISOLATED_ENV.items():
        monkeypatch.setenv(key, value)

    network_attempts = []

    def deny(operation):
        network_attempts.append(operation)
        raise AssertionError("Unexpected network operation in in-process ZIP validation")

    def guard_socket_method(method, operation):
        def guarded(sock, *args, **kwargs):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                deny(operation)
            return method(sock, *args, **kwargs)

        return guarded

    for operation in ("connect", "connect_ex", "sendto", "sendmsg"):
        method = getattr(socket.socket, operation, None)
        if method is not None:
            monkeypatch.setattr(socket.socket, operation, guard_socket_method(method, operation))

    def guard_resolver(operation):
        def guarded(*args, **kwargs):
            deny(operation)

        return guarded

    for operation in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo"):
        monkeypatch.setattr(socket, operation, guard_resolver(operation))

    account_roots = {}

    def factory(path):
        app = create_default_app(data_dir=path)
        assert app.state.p2_service is None
        assert app.state.git_scan_runtime is None
        assert app.state.assistant_service is None
        assert app.state.assessment_service is None
        assert app.state.report_v2_service is None
        assert app.state.zip_dispatcher is None
        assert app.state.zip_scan_runtime._ai_provider is None
        assert app.state.zip_scan_runtime._ai_enabled is False
        assert app.state.zip_scan_runtime._external_scanners is False
        # These are synthetic, separate private roots selected by the real gateway.
        account_roots[path.name] = path
        return app

    gateway = LocalAccountGateway(
        root=tmp_path / "accounts", origins=(ORIGIN,), cookie_name="og_session_450145014501",
        app_factory=factory, frontend=_frontend,
    )
    print("P0_1_ACTIVE_ASGI_ENV=" + json.dumps({key: os.environ[key] for key in ISOLATED_ENV}, sort_keys=True))
    with TestClient(gateway, base_url=ORIGIN) as client:
        yield GatewayHarness(client, gateway, account_roots)

    assert account_roots
    for tenant_root in account_roots.values():
        assert (tenant_root / "scans.db").is_file()
        for db in ("p2.db", "assistant.db", "assessment.db", "report_v2.db"):
            assert not (tenant_root / db).exists()
        assert not list((tenant_root / "uploads").iterdir())
        assert not list((tenant_root / "workspaces").iterdir())
    assert not network_attempts
    print(
        "P0_1_ASGI_EFFECTIVE_STATE="
        + json.dumps({
            "tenant_scan_registries": len(account_roots),
            "git_runtime": "absent", "p2_service_and_database": "absent",
            "assistant_service_and_database": "absent", "assessment_service_and_database": "absent",
            "ai_provider": "absent", "external_scanners_enabled": False,
            "network_attempts": len(network_attempts), "asgi_mode": "in_process_testclient",
        }, sort_keys=True)
    )


def _uv(name, version):
    return (
        f'version = 1\nrevision = 3\n[[package]]\nname = "{name}"\nversion = "{version}"\n'
        'source = { registry = "https://pypi.org/simple" }\n'
    ).encode()


def _sha(raw):
    return sha256(raw).hexdigest()


def _scan_ref(page, stored):
    run = stored.run
    assert page["scan_ref"]["scan_id"] == run.id
    assert page["scan_ref"]["registry_revision"] == stored.revision
    assert page["scan_ref"]["revision"] is None
    assert page["scan_ref"]["status"] == run.status.value
    assert page["scan_ref"]["facts_hash"] == facts_digest(run)
    assert page["scan_ref"]["input_hash"] == run.provenance.input_digest.value
    assert page["scan_ref"]["inventory_hash"] == run.provenance.inventory_digest.value


def _match_evidence(row, expected, path, files):
    assert row["evidence_id"] == expected.id
    assert row["file_path"] == path
    assert row["locator"] == expected.locator
    assert row["source_sha256"] == expected.content_hash.value == _sha(files[path])
    assert row["kind"] == expected.kind.value
    assert row["start_line"] == expected.start_line
    assert row["end_line"] == expected.end_line
    assert row["verification_status"] == expected.verification_status.value
    assert row["producer"]["name"] == expected.producer.name
    assert row["producer"]["type"] == expected.producer.type.value
    assert row["producer"]["version"] == expected.producer.version


def test_actual_completed_zip_exposes_manifest_lock_cyclonedx_and_two_spdx_formats(zip_gateway):
    session = zip_gateway.register("task45_observations")
    files = {
        "package.json": ROOT_PACKAGE,
        "requirements.txt": b"p01-manifest==1.2.3\n",
        "uv.lock": _uv("p01-uv", "1.2.3"),
        "bom.json": json.dumps(
            {"bomFormat": "CycloneDX", "specVersion": "1.5", "components": [
                {"bom-ref": "cdx", "name": "p01-cdx", "version": "1.2.3",
                 "purl": "pkg:npm/p01-cdx@1.2.3"},
            ]},
        ).encode(),
        "sbom.spdx.json": json.dumps(
            {"spdxVersion": "SPDX-2.3", "packages": [
                {"name": "p01-spdx-json", "SPDXID": "SPDXRef-Test", "versionInfo": "1.2.3",
                 "externalRefs": [
                     {"referenceCategory": "PACKAGE-MANAGER", "referenceType": "purl",
                      "referenceLocator": "pkg:pypi/p01-spdx-json@1.2.3"},
                 ]},
            ]},
        ).encode(),
        "sbom.spdx": (
            b"SPDXVersion: SPDX-2.3\nSPDXID: SPDXRef-DOCUMENT\n"
            b"PackageName: p01-spdx-tag\nSPDXID: SPDXRef-Tag\nPackageVersion: 1.2.3\n"
            b"ExternalRef: PACKAGE-MANAGER purl pkg:npm/p01-spdx-tag@1.2.3\n"
        ),
    }
    path, stored = zip_gateway.upload(session, files)
    assert stored.run.status.value == "completed"
    page = zip_gateway.project(path)
    _scan_ref(page, stored)
    assert page["source"] is None and page["limit"] == 50 and page["next_cursor"] is None
    assert page["total"] == page["returned"] == 5
    by_name = {item["name"]: item for item in page["items"]}
    components = {item.name: item for item in stored.run.components}
    evidence = {item.id: item for item in stored.run.evidence}
    for name, source, file_path, role, verification in (
        ("p01-manifest", "manifest", "requirements.txt", "observed", "verified"),
        ("p01-uv", "lock", "uv.lock", "inferred", "pending"),
        ("p01-cdx", "sbom", "bom.json", "inferred", "pending"),
        ("p01-spdx-json", "sbom", "sbom.spdx.json", "inferred", "pending"),
        ("p01-spdx-tag", "sbom", "sbom.spdx", "inferred", "pending"),
    ):
        item = by_name[name]
        assert item["resource_id"] == components[name].id
        assert item["version"] == components[name].version == "1.2.3"
        assert item["ecosystem"] == components[name].ecosystem
        assert item["sources"] == [source]
        assert item["role_state"] == role
        assert item["evidence_total"] == item["evidence_returned"] == 1
        (reference,) = item["evidence"]
        (evidence_id,) = components[name].evidence_ids
        _match_evidence(reference, evidence[evidence_id], file_path, files)
        assert reference["source"] == source and reference["verification_status"] == verification
        assert reference["source_sha256"] != page["scan_ref"]["facts_hash"]
        assert item["conflicts_total"] == 0 and not item["conflicts"]
    for category, count in (("manifest", 1), ("lock", 1), ("sbom", 3), ("unknown", 0)):
        filtered = zip_gateway.project(path, source=category)
        assert filtered["source"] == category and filtered["total"] == filtered["returned"] == count
        assert all(category in item["sources"] for item in filtered["items"])
    selected_app = zip_gateway.gateway.apps[session["user"]["id"]]
    assert selected_app.state.scan_api_service._registry.get(stored.run.id) == stored
    print("P0_1_REAL_ZIP=COMPLETED dependencies=5 manifest=1 lock=1 cyclonedx=1 spdx=2")


def test_actual_partial_zip_projects_exact_manifest_lock_conflict(zip_gateway):
    session = zip_gateway.register("task45_version_conflict")
    files = {
        "package.json": ROOT_PACKAGE,
        "sub/pyproject.toml": (
            b'[project]\nname = "test-only-app"\nversion = "1.0.0"\n'
            b'dependencies = ["p01-versioned==1.2.3"]\n'
        ),
        "sub/uv.lock": _uv("p01-versioned", "2.3.4"),
    }
    path, stored = zip_gateway.upload(session, files)
    assert stored.run.status.value == "partial"
    (error,) = [error for error in stored.run.errors if error.code == "lock_version_conflict"]
    page = zip_gateway.project(path)
    _scan_ref(page, stored)
    assert page["total"] == page["returned"] == 2
    components = {item.id: item for item in stored.run.components}
    evidence = {item.id: item for item in stored.run.evidence}
    for item in page["items"]:
        assert item["name"] == "p01-versioned" and item["role_state"] == "unknown"
        assert item["conflicts_total"] == item["conflicts_returned"] == 1
        (conflict,) = item["conflicts"]
        assert conflict["code"] == error.code and conflict["status"] == "confirmed"
        actual_ids = set()
        for side_name, version, file_path in (
            ("declaration", "1.2.3", "sub/pyproject.toml"),
            ("lock", "2.3.4", "sub/uv.lock"),
        ):
            side = conflict[side_name]
            assert side["version"] == version == components[side["resource_id"]].version
            assert side["evidence_total"] == side["evidence_returned"] == 1
            assert side["incomplete"] is False
            (reference,) = side["evidence"]
            evidence_id = reference["evidence_id"]
            assert evidence_id in components[side["resource_id"]].evidence_ids
            _match_evidence(reference, evidence[evidence_id], file_path, files)
            actual_ids.add(evidence_id)
        assert actual_ids == set(error.evidence_ids)
    print("P0_1_REAL_ZIP=PARTIAL conflict_code=lock_version_conflict declaration=1.2.3 lock=2.3.4")


def test_actual_root_only_zip_has_empty_dependency_projection(zip_gateway):
    session = zip_gateway.register("task45_empty_dependencies")
    path, stored = zip_gateway.upload(session, {"package.json": ROOT_PACKAGE})
    assert stored.run.status.value == "completed"
    (root,) = stored.run.components
    assert root.component_type is ComponentType.APPLICATION
    page = zip_gateway.project(path)
    _scan_ref(page, stored)
    assert page["items"] == [] and page["total"] == page["returned"] == 0
    assert page["next_cursor"] is None
    print("P0_1_REAL_ZIP=COMPLETED dependencies=0")


def test_real_zip_paging_and_gateway_tenant_cursor_boundaries(zip_gateway):
    owner = zip_gateway.register("task45_paging_owner")
    many = b"".join(f"test-only-package-{n:03}==1.0.0\n".encode() for n in range(108))
    large_path, large = zip_gateway.upload(owner, {"package.json": ROOT_PACKAGE, "requirements.txt": many})
    ids = sorted(item.id for item in large.run.components if item.component_type is not ComponentType.APPLICATION)
    assert len(ids) == 108
    first = zip_gateway.project(large_path)
    _scan_ref(first, large)
    assert first["limit"] == first["returned"] == 50 and first["total"] == 108
    assert [item["resource_id"] for item in first["items"]] == ids[:50]
    assert zip_gateway.project(large_path)["items"] == first["items"]

    second = zip_gateway.project(large_path, cursor=first["next_cursor"])
    third = zip_gateway.project(large_path, cursor=second["next_cursor"])
    assert second["returned"] == 50 and third["returned"] == 8
    assert third["next_cursor"] is None
    assert [item["resource_id"] for page in (first, second, third) for item in page["items"]] == ids

    max_page = zip_gateway.project(large_path, limit=100)
    assert max_page["limit"] == max_page["returned"] == 100 and max_page["next_cursor"]
    query = zip_gateway.client.get(large_path + PROJECTION, params={"limit": 101})
    assert query.status_code in {400, 422}
    token = first["next_cursor"]
    tampered = ("A" if token[0] != "A" else "B") + token[1:]
    _checked(zip_gateway.client.get(large_path + PROJECTION, params={"cursor": tampered}), 400)

    small = {"package.json": ROOT_PACKAGE, "requirements.txt": b"p01-one==1.0.0\np01-two==2.0.0\n"}
    second_path, _ = zip_gateway.upload(owner, small, filename="task45-p01-other-scan.zip")
    for project_path, params in (
        (second_path, {"cursor": token}),
        (large_path, {"cursor": token, "limit": 49}),
        (large_path, {"cursor": token, "source": "manifest"}),
    ):
        rejected = zip_gateway.client.get(project_path + PROJECTION, params=params)
        assert rejected.status_code in {400, 409}

    zip_gateway.logout(owner)
    _checked(zip_gateway.client.get(large_path + PROJECTION), 401)
    other = zip_gateway.register("task45_paging_other")
    _checked(zip_gateway.client.get(large_path + PROJECTION), 404)
    other_path, _ = zip_gateway.upload(other, small, filename="task45-p01-other-account.zip")
    assert zip_gateway.project(other_path, limit=1)["next_cursor"]
    _checked(zip_gateway.client.get(other_path + PROJECTION, params={"cursor": token}), 400)
    assert len(zip_gateway.roots) == 2
    print("P0_1_REAL_PAGING resources=108 default=50 max=100 tenants=2")


def test_actual_zip_with_many_bound_evidence_records_reports_capacity_gap(zip_gateway):
    session = zip_gateway.register("task45_capacity")
    files = {
        f"workspace-{number:02}/requirements.txt": b"p01-repeated==1.2.3\n"
        for number in range(51)
    }
    files["package.json"] = ROOT_PACKAGE
    path, stored = zip_gateway.upload(session, files)
    component, = [item for item in stored.run.components if item.name == "p01-repeated"]
    assert len(component.evidence_ids) == 51

    page = zip_gateway.project(path)
    _scan_ref(page, stored)
    assert page["total"] == page["returned"] == 1 and page["incomplete"] is True
    item, = page["items"]
    assert item["resource_id"] == component.id and item["incomplete"] is True
    assert item["evidence_total"] == 51 and item["evidence_returned"] == len(item["evidence"]) == 50
    assert "evidence_limit_exceeded" in item["gaps"]
    persisted = {entry.id: entry for entry in stored.run.evidence}
    for reference in item["evidence"]:
        assert reference["evidence_id"] in component.evidence_ids
        expected = persisted[reference["evidence_id"]]
        _match_evidence(reference, expected, expected.locator.partition(":")[0], files)
    print("P0_1_REAL_ZIP_EVIDENCE_CAP persisted=51 returned=50 incomplete=true")
