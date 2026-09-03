"""Independent A3-1 API regression for the frozen FastAPI vertical slice.

The expected route set, queued semantics, projections, filters and error
envelope are constructed from the frozen P0/A3-1 contract.  This file does
not import or call implementation-side test helpers.
"""

from __future__ import annotations

import http.client
import json
import os
import socket
import sqlite3
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.domain.models import (
    AIAsset,
    AIAssetType,
    Component,
    DetectionMethod,
    Evidence,
    EvidenceKind,
    FindingOutcome,
    HashValue,
    ProducerRef,
    ProducerType,
    Project,
    ReportFormat,
    ReportLink,
    RiskFinding,
    RunEnvironment,
    RunProvenance,
    ScanRun,
    ScanStage,
    ScanStatus,
    ScanSummary,
    Severity,
    SourceType,
    VerificationStatus,
)
from app.persistence import SQLiteScanRunRegistry


BASE_TIME = datetime(2026, 9, 3, 3, 0, tzinfo=timezone.utc)
VALID_SOURCE = "https://github.com/example/OpenGuard"
MISSING_SCAN_ID = "scn_00000000-0000-0000-0000-000000000000"


@dataclass
class ApiHarness:
    client: TestClient
    registry: SQLiteScanRunRegistry
    database_path: Path


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[ApiHarness]:
    os.chmod(tmp_path, 0o700)
    database_path = tmp_path / "scans.sqlite"
    registry = SQLiteScanRunRegistry(database_path)
    app = create_app(registry)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield ApiHarness(client=client, registry=registry, database_path=database_path)
    registry.close()


def _id(prefix: str, number: int) -> str:
    return f"{prefix}_00000000-0000-0000-0000-{number:012x}"


def _hash(digit: str) -> HashValue:
    return HashValue(algorithm="sha256", value=digit * 64)


def _summary(*, component_count: int = 0, ai_asset_count: int = 0, evidence_count: int = 0, review_count: int = 0) -> ScanSummary:
    return ScanSummary(
        component_count=component_count,
        ai_asset_count=ai_asset_count,
        evidence_count=evidence_count,
        finding_counts={
            FindingOutcome.PASS: 0,
            FindingOutcome.WARNING: 0,
            FindingOutcome.REVIEW_REQUIRED: review_count,
            FindingOutcome.UNKNOWN: 0,
        },
    )


def _queued_run(number: int, *, source: str = VALID_SOURCE) -> ScanRun:
    created_at = BASE_TIME + timedelta(seconds=number)
    return ScanRun(
        contract_version="0.1.1",
        id=_id("scn", number),
        status=ScanStatus.QUEUED,
        stage=ScanStage.QUEUED,
        progress=0,
        project=Project(
            id=_id("prj", number),
            name=f"independent-api-{number}",
            source_type=SourceType.GIT,
            source=source,
            created_at=created_at,
        ),
        summary=_summary(),
        provenance=RunProvenance(
            input_digest=_hash("a"),
            tool_versions=[],
            ruleset_version="independent-api-rules",
            contract_version="0.1.1",
            ai_enabled=False,
            ai_model=None,
            run_environment=RunEnvironment(
                python_version="3.12",
                platform="independent-api-test",
                openguard_version="independent-test",
            ),
        ),
        created_at=created_at,
    )


@dataclass(frozen=True)
class CompletedFixture:
    run: ScanRun
    component: Component
    asset: AIAsset
    finding: RiskFinding
    evidence: Evidence
    report: ReportLink


def _complete_run(registry: SQLiteScanRunRegistry, number: int = 900) -> CompletedFixture:
    queued = _queued_run(number)
    created = registry.create(queued)
    started_at = queued.created_at + timedelta(seconds=1)
    running_payload = queued.model_dump(mode="json")
    running_payload.update(
        status="running",
        stage="ingestion",
        progress=10,
        started_at=started_at.isoformat(),
    )
    running = ScanRun.model_validate(running_payload)
    registry.replace(running, expected_revision=created.revision)

    producer = ProducerRef(type=ProducerType.HUMAN, name="independent-api-fixture", version="1")
    evidence = Evidence(
        id=_id("evd", number),
        kind=EvidenceKind.MANIFEST_FIELD,
        locator="pyproject.toml:project.dependencies[0]",
        excerpt="requests>=2.0",
        start_line=1,
        end_line=1,
        content_hash=_hash("b"),
        detected_by=DetectionMethod.MANUAL,
        producer=producer,
        observed_at=started_at,
        verification_status=VerificationStatus.VERIFIED,
    )
    component = Component(
        id=_id("cmp", number),
        name="requests",
        version="2.0.0",
        ecosystem="pypi",
        purl="pkg:pypi/requests@2.0.0",
        evidence_ids=[evidence.id],
        detected_by=[DetectionMethod.MANIFEST_PARSER],
        confidence=1.0,
    )
    asset = AIAsset(
        id=_id("ast", number),
        asset_type=AIAssetType.MODEL,
        name="demo-model",
        provider="hugging_face",
        version="1.0",
        source_url="https://huggingface.co/example/demo-model",
        authorization_status=VerificationStatus.PENDING,
        evidence_ids=[evidence.id],
        detected_by=[DetectionMethod.STATIC_PATTERN],
        confidence=0.8,
    )
    finding = RiskFinding(
        id=_id("rsk", number),
        resource_kind="component",
        resource_id=component.id,
        outcome=FindingOutcome.REVIEW_REQUIRED,
        severity=Severity.HIGH,
        title="Independent API review finding",
        description="Evidence requires a human review.",
        rule_id="independent.rule",
        rule_version="1",
        trigger="fixture trigger",
        evidence_ids=[evidence.id],
        confidence=0.9,
    )
    report = ReportLink(
        format=ReportFormat.HTML,
        href=f"reports/{number}.html",
        content_hash=_hash("c"),
        generated_at=started_at + timedelta(seconds=1),
    )
    finished_payload = running.model_dump(mode="json")
    finished_payload.update(
        status="completed",
        stage="completed",
        progress=100,
        components=[component.model_dump(mode="json")],
        ai_assets=[asset.model_dump(mode="json")],
        evidence=[evidence.model_dump(mode="json")],
        findings=[finding.model_dump(mode="json")],
        summary=_summary(component_count=1, ai_asset_count=1, evidence_count=1, review_count=1).model_dump(mode="json"),
        report_links=[report.model_dump(mode="json")],
        finished_at=(started_at + timedelta(seconds=1)).isoformat(),
    )
    completed = ScanRun.model_validate(finished_payload)
    final = registry.replace(completed, expected_revision=2)
    assert final.revision == 3
    return CompletedFixture(
        run=final.run,
        component=component,
        asset=asset,
        finding=finding,
        evidence=evidence,
        report=report,
    )


def _create(harness: ApiHarness, *, source: str = VALID_SOURCE, key: str | None = None) -> dict[str, Any]:
    payload: dict[str, str] = {"source_type": "git", "source": source}
    if key is not None:
        payload["idempotency_key"] = key
    response = harness.client.post("/api/v1/scans", json=payload)
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["status_url"] == f"/api/v1/scans/{body['scan_id']}"
    assert response.headers["x-request-id"].startswith("req_")
    return body


def _assert_error(response: Any, *, status_code: int, code: str, reason: str) -> None:
    assert response.status_code == status_code
    payload = response.json()
    assert set(payload) == {"error"}
    assert set(payload["error"]) == {"code", "message", "request_id", "details"}
    assert payload["error"]["code"] == code
    assert payload["error"]["details"] == {"reason": reason}
    assert payload["error"]["request_id"].startswith("req_")
    assert response.headers["x-request-id"] == payload["error"]["request_id"]


def _assert_error_shape(response: Any, *, status_code: int) -> None:
    assert response.status_code == status_code
    payload = response.json()
    assert set(payload) == {"error"}
    assert set(payload["error"]) == {"code", "message", "request_id", "details"}
    assert type(payload["error"]["code"]) is str
    assert type(payload["error"]["message"]) is str
    assert payload["error"]["request_id"].startswith("req_")
    assert type(payload["error"]["details"]) is dict
    assert response.headers["x-request-id"] == payload["error"]["request_id"]


def test_openapi_exposes_exactly_the_six_frozen_business_routes(harness: ApiHarness) -> None:
    response = harness.client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["paths"] == {
        "/api/v1/scans": {"post": response.json()["paths"]["/api/v1/scans"]["post"]},
        "/api/v1/scans/{scan_id}": {"get": response.json()["paths"]["/api/v1/scans/{scan_id}"]["get"]},
        "/api/v1/scans/{scan_id}/evidence/{evidence_id}": {"get": response.json()["paths"]["/api/v1/scans/{scan_id}/evidence/{evidence_id}"]["get"]},
        "/api/v1/scans/{scan_id}/report": {"get": response.json()["paths"]["/api/v1/scans/{scan_id}/report"]["get"]},
        "/api/v1/scans/{scan_id}/resources": {"get": response.json()["paths"]["/api/v1/scans/{scan_id}/resources"]["get"]},
        "/api/v1/scans/{scan_id}/risks": {"get": response.json()["paths"]["/api/v1/scans/{scan_id}/risks"]["get"]},
    }
    assert harness.client.get("/docs").status_code == 200


def test_git_create_is_canonical_durable_queued_and_idempotent(harness: ApiHarness) -> None:
    first = harness.client.post(
        "/api/v1/scans",
        json={
            "source_type": "git",
            "source": "https://GitHub.COM:443/example/OpenGuard.git",
            "idempotency_key": "independent-request-001",
        },
    )
    assert first.status_code == 202
    first_body = first.json()
    assert first_body["status"] == "queued"
    assert first_body["status_url"] == f"/api/v1/scans/{first_body['scan_id']}"
    assert first.headers["x-request-id"].startswith("req_")

    stored = harness.registry.get(first_body["scan_id"])
    assert stored.revision == 1
    assert stored.run.status is ScanStatus.QUEUED
    assert stored.run.stage is ScanStage.QUEUED
    assert stored.run.progress == 0
    assert stored.run.project.source == "https://github.com/example/OpenGuard.git"
    assert stored.run.project.name == "OpenGuard"
    assert stored.run.components == []
    assert stored.run.ai_assets == []
    assert stored.run.evidence == []
    assert stored.run.findings == []

    retry = harness.client.post(
        "/api/v1/scans",
        json={
            "source_type": "git",
            "source": "https://github.com/example/OpenGuard.git",
            "idempotency_key": "independent-request-001",
        },
    )
    assert retry.status_code == 202
    assert retry.json() == first_body

    second_registry = SQLiteScanRunRegistry(harness.database_path)
    try:
        assert second_registry.get(first_body["scan_id"]) == stored
        assert len(second_registry.list_runs().items) == 1
    finally:
        second_registry.close()

    with sqlite3.connect(harness.database_path) as connection:
        row = connection.execute(
            "SELECT scan_id, revision, idempotency_key, status, contract_version, run_json FROM scan_runs"
        ).fetchone()
        assert row is not None
        assert row[:5] == (
            first_body["scan_id"],
            1,
            "independent-request-001",
            "queued",
            "0.1.1",
        )
        assert type(row[5]) is bytes

    conflict = harness.client.post(
        "/api/v1/scans",
        json={
            "source_type": "git",
            "source": "https://github.com/example/other.git",
            "idempotency_key": "independent-request-001",
        },
    )
    _assert_error(conflict, status_code=409, code="invalid_source", reason="idempotency_conflict")
    assert "other.git" not in conflict.text


@pytest.mark.parametrize(
    "source,reason",
    [
        ("http://github.com/example/repo", "url_invalid"),
        ("https://user:secret@github.com/example/repo", "url_invalid"),
        ("https://github.com/example/repo?token=secret", "url_invalid"),
        ("https://github.com/example/repo#fragment", "url_invalid"),
        ("https://github.com:8443/example/repo", "url_invalid"),
        ("https://127.0.0.1/example/repo", "host_not_public"),
        ("https://localhost/example/repo", "host_not_public"),
        ("https://github.com/", "path_invalid"),
        ("https://github.com/example/%2e%2e/repo", "path_invalid"),
        (" https://github.com/example/repo", "request_invalid"),
    ],
)
def test_git_source_canonicalization_rejects_non_public_or_non_canonical_inputs(
    harness: ApiHarness,
    source: str,
    reason: str,
) -> None:
    response = harness.client.post("/api/v1/scans", json={"source_type": "git", "source": source})
    _assert_error(response, status_code=422, code="invalid_source", reason=reason)
    assert "secret" not in response.text
    assert "token" not in response.text


@pytest.mark.parametrize(
    "source",
    [
        "https://git\nhub.com/example/repo",
        "https://github.com/example/\rOpenGuard",
        "https://github.com/example/\tOpenGuard",
    ],
)
def test_git_source_rejects_raw_control_characters_before_url_normalization(
    harness: ApiHarness,
    source: str,
) -> None:
    response = harness.client.post("/api/v1/scans", json={"source_type": "git", "source": source})
    _assert_error(response, status_code=422, code="invalid_source", reason="url_invalid")


def test_git_source_enforces_the_2048_utf8_byte_limit_not_code_points(harness: ApiHarness) -> None:
    source = "https://github.com/example/" + ("汉" * 700)
    assert len(source) < 2048
    assert len(source.encode("utf-8")) > 2048

    response = harness.client.post("/api/v1/scans", json={"source_type": "git", "source": source})
    _assert_error_shape(response, status_code=422)
    assert response.json()["error"]["code"] == "invalid_source"
    assert source not in response.text


def test_request_validation_and_query_validation_use_the_same_error_envelope(harness: ApiHarness) -> None:
    extra = harness.client.post(
        "/api/v1/scans",
        json={"source_type": "git", "source": VALID_SOURCE, "unexpected": True},
    )
    _assert_error(extra, status_code=422, code="invalid_source", reason="request_invalid")
    assert "unexpected" not in extra.text

    wrong_type = harness.client.post(
        "/api/v1/scans",
        json={"source_type": "zip", "source": VALID_SOURCE},
    )
    _assert_error(wrong_type, status_code=422, code="invalid_source", reason="request_invalid")

    whitespace_key = harness.client.post(
        "/api/v1/scans",
        json={"source_type": "git", "source": VALID_SOURCE, "idempotency_key": " request "},
    )
    _assert_error(whitespace_key, status_code=422, code="invalid_source", reason="request_invalid")

    scan_id = _create(harness)["scan_id"]
    bad_filter = harness.client.get(f"/api/v1/scans/{scan_id}/resources", params={"kind": "not-a-kind"})
    _assert_error(bad_filter, status_code=422, code="invalid_source", reason="request_invalid")


def test_queued_status_and_result_routes_never_fake_scan_results(harness: ApiHarness) -> None:
    scan_id = _create(harness)["scan_id"]
    status_response = harness.client.get(f"/api/v1/scans/{scan_id}")
    assert status_response.status_code == 200
    assert status_response.json() == {
        "scan_id": scan_id,
        "status": "queued",
        "stage": "queued",
        "progress": 0,
        "summary": {
            "component_count": 0,
            "ai_asset_count": 0,
            "evidence_count": 0,
            "finding_counts": {"pass": 0, "warning": 0, "review_required": 0, "unknown": 0},
        },
        "errors": [],
    }

    for suffix in (
        "resources",
        "risks",
        f"evidence/{_id('evd', 990)}",
    ):
        response = harness.client.get(f"/api/v1/scans/{scan_id}/{suffix}")
        _assert_error(response, status_code=409, code="scan_not_ready", reason="status_not_ready")
    report = harness.client.get(f"/api/v1/scans/{scan_id}/report", params={"format": "html"})
    _assert_error(report, status_code=409, code="report_not_ready", reason="status_not_ready")

    missing = harness.client.get(f"/api/v1/scans/{MISSING_SCAN_ID}")
    _assert_error(missing, status_code=404, code="scan_not_found", reason="not_found")


def test_resource_views_and_filters_preserve_p0_objects(harness: ApiHarness) -> None:
    fixture = _complete_run(harness.registry)
    response = harness.client.get(f"/api/v1/scans/{fixture.run.id}/resources")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["filters"] == {
        "kind": None,
        "ecosystem": None,
        "provider": None,
        "verification_status": None,
    }
    assert body["items"] == [
        {"kind": "ai_asset", "resource": fixture.asset.model_dump(mode="json")},
        {"kind": "component", "resource": fixture.component.model_dump(mode="json")},
    ]

    component = harness.client.get(
        f"/api/v1/scans/{fixture.run.id}/resources",
        params={"kind": "component", "ecosystem": "pypi"},
    ).json()
    assert component["total"] == 1
    assert component["items"] == [{"kind": "component", "resource": fixture.component.model_dump(mode="json")}]

    asset = harness.client.get(
        f"/api/v1/scans/{fixture.run.id}/resources",
        params={"kind": "ai_asset", "provider": "hugging_face", "verification_status": "pending"},
    ).json()
    assert asset["total"] == 1
    assert asset["items"] == [{"kind": "ai_asset", "resource": fixture.asset.model_dump(mode="json")}]

    assert harness.client.get(
        f"/api/v1/scans/{fixture.run.id}/resources",
        params={"kind": "component", "provider": "hugging_face"},
    ).json()["items"] == []
    assert harness.client.get(
        f"/api/v1/scans/{fixture.run.id}/resources",
        params={"kind": "ai_asset", "ecosystem": "pypi"},
    ).json()["items"] == []
    assert harness.client.get(
        f"/api/v1/scans/{fixture.run.id}/resources",
        params={"kind": "component", "verification_status": "pending"},
    ).json()["items"] == []


def test_risks_evidence_and_report_read_from_one_completed_snapshot(harness: ApiHarness) -> None:
    fixture = _complete_run(harness.registry, number=901)
    risks = harness.client.get(
        f"/api/v1/scans/{fixture.run.id}/risks",
        params={"outcome": "review_required", "severity": "high", "resource_kind": "component"},
    )
    assert risks.status_code == 200
    assert risks.json() == {"items": [fixture.finding.model_dump(mode="json")], "total": 1}

    empty_risks = harness.client.get(
        f"/api/v1/scans/{fixture.run.id}/risks", params={"outcome": "pass"}
    )
    assert empty_risks.status_code == 200
    assert empty_risks.json() == {"items": [], "total": 0}

    evidence = harness.client.get(f"/api/v1/scans/{fixture.run.id}/evidence/{fixture.evidence.id}")
    assert evidence.status_code == 200
    assert evidence.json() == fixture.evidence.model_dump(mode="json")
    missing_evidence = harness.client.get(f"/api/v1/scans/{fixture.run.id}/evidence/{_id('evd', 999)}")
    _assert_error(missing_evidence, status_code=404, code="evidence_not_found", reason="not_found")

    report = harness.client.get(f"/api/v1/scans/{fixture.run.id}/report", params={"format": "html"})
    assert report.status_code == 200
    assert report.json() == fixture.report.model_dump(mode="json")
    missing_report = harness.client.get(f"/api/v1/scans/{fixture.run.id}/report", params={"format": "json"})
    _assert_error(missing_report, status_code=409, code="report_not_ready", reason="not_generated")


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/v1/route-that-does-not-exist"),
        ("post", f"/api/v1/scans/{MISSING_SCAN_ID}"),
        ("delete", "/api/v1/scans"),
    ],
)
def test_unknown_routes_and_methods_use_the_frozen_non_2xx_envelope(
    harness: ApiHarness,
    method: str,
    path: str,
) -> None:
    response = getattr(harness.client, method)(path)
    _assert_error_shape(response, status_code=404 if method == "get" else 405)


def test_unexpected_exception_is_sanitized_and_has_matching_request_id() -> None:
    class ExplodingRegistry:
        def get(self, _: str) -> None:
            raise RuntimeError("/private/api/project token=do-not-leak")

    app = create_app(ExplodingRegistry())  # type: ignore[arg-type]
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(f"/api/v1/scans/{MISSING_SCAN_ID}")
    _assert_error(response, status_code=500, code="internal_error", reason="unexpected_failure")
    assert "/private/api/project" not in response.text
    assert "do-not-leak" not in response.text


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_for_uvicorn(process: subprocess.Popen[bytes], port: int) -> None:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"uvicorn exited before listening with code {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise AssertionError("uvicorn did not listen on loopback within the timeout")


def test_real_uvicorn_loopback_persists_the_queued_scan(tmp_path: Path) -> None:
    os.chmod(tmp_path, 0o700)
    data_dir = tmp_path / "uvicorn-data"
    port = _free_loopback_port()
    project_root = Path(__file__).parents[2]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(project_root / "backend")
    environment["OPENGUARD_DATA_DIR"] = str(data_dir)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.api.main:create_default_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "error",
        ],
        cwd=project_root,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_uvicorn(process, port)
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        try:
            payload = json.dumps(
                {"source_type": "git", "source": VALID_SOURCE, "idempotency_key": "uvicorn-001"}
            ).encode("utf-8")
            connection.request(
                "POST",
                "/api/v1/scans",
                body=payload,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            response = connection.getresponse()
            body = json.loads(response.read().decode("utf-8"))
            assert response.status == 202
            assert body["status"] == "queued"
            assert body["status_url"] == f"/api/v1/scans/{body['scan_id']}"
            assert response.getheader("X-Request-ID", "").startswith("req_")
            scan_id = body["scan_id"]

            connection.request("GET", body["status_url"], headers={"Accept": "application/json"})
            status_response = connection.getresponse()
            status_body = json.loads(status_response.read().decode("utf-8"))
            assert status_response.status == 200
            assert status_body["scan_id"] == scan_id
            assert status_body["status"] == "queued"
        finally:
            connection.close()
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    database_path = data_dir / "scans.db"
    assert stat.S_IMODE(data_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(database_path.stat().st_mode) == 0o600
    registry = SQLiteScanRunRegistry(database_path)
    try:
        persisted = registry.get(scan_id)
        assert persisted.revision == 1
        assert persisted.run.status is ScanStatus.QUEUED
        assert persisted.run.stage is ScanStage.QUEUED
        assert persisted.run.progress == 0
    finally:
        registry.close()
