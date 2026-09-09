from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import count
from pathlib import Path
from typing import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api import create_app, create_default_app
from app.api.service import ScanApiService
from app.domain.models import ScanRun
from app.persistence import SQLiteScanRunRegistry


FIXED_TIME = datetime(2026, 9, 3, 2, 0, tzinfo=timezone.utc)
VALID_SOURCE = "https://github.com/example/OpenGuard"
MISSING_SCAN_ID = "scn_00000000-0000-0000-0000-000000000000"


@dataclass
class ApiHarness:
    client: TestClient
    registry: SQLiteScanRunRegistry


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[ApiHarness]:
    os.chmod(tmp_path, 0o700)
    registry = SQLiteScanRunRegistry(tmp_path / "scans.db")
    ids = count(1)
    app = create_app(registry)
    app.state.scan_api_service = ScanApiService(
        registry,
        clock=lambda: FIXED_TIME,
        id_factory=lambda: UUID(int=next(ids)),
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        yield ApiHarness(client=client, registry=registry)
    registry.close()


def _create(harness: ApiHarness, *, source: str = VALID_SOURCE, key: str | None = None) -> str:
    payload: dict[str, str] = {"source_type": "git", "source": source}
    if key is not None:
        payload["idempotency_key"] = key
    response = harness.client.post("/api/v1/scans", json=payload)
    assert response.status_code == 202
    return response.json()["scan_id"]


def _complete_from_sample(harness: ApiHarness, scan_id: str) -> ScanRun:
    queued = harness.registry.get(scan_id)
    started_at = FIXED_TIME + timedelta(seconds=1)
    running_payload = queued.run.model_dump(mode="json")
    running_payload.update(status="running", stage="ingestion", progress=10, started_at=started_at.isoformat())
    running = ScanRun.model_validate(running_payload)
    harness.registry.replace(running, expected_revision=queued.revision)

    sample_path = Path(__file__).parents[2] / "examples" / "sample-scan-result.json"
    completed_payload = json.loads(sample_path.read_text(encoding="utf-8"))
    completed_payload.update(
        id=queued.run.id,
        idempotency_key=queued.run.idempotency_key,
        project=queued.run.project.model_dump(mode="json"),
        provenance=queued.run.provenance.model_dump(mode="json"),
        created_at=queued.run.created_at.isoformat(),
        started_at=started_at.isoformat(),
        finished_at=(FIXED_TIME + timedelta(seconds=2)).isoformat(),
        report_links=[
            {
                "format": "html",
                "href": f"reports/{scan_id}.html",
                "content_hash": {"algorithm": "sha256", "value": "a" * 64},
                "generated_at": (FIXED_TIME + timedelta(seconds=2)).isoformat(),
            }
        ],
    )
    completed = ScanRun.model_validate(completed_payload)
    harness.registry.replace(completed, expected_revision=2)
    return completed


def _assert_error(response: object, *, status_code: int, code: str, reason: str) -> None:
    assert getattr(response, "status_code") == status_code
    payload = response.json()
    assert payload["error"]["code"] == code
    assert payload["error"]["details"] == {"reason": reason}
    assert payload["error"]["request_id"].startswith("req_")
    assert response.headers["x-request-id"] == payload["error"]["request_id"]
    assert set(payload) == {"error"}


def test_openapi_exposes_only_the_six_frozen_p0_routes(harness: ApiHarness) -> None:
    response = harness.client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert {path: sorted(methods) for path, methods in paths.items()} == {
        "/api/v1/scans": ["post"],
        "/api/v1/scans/{scan_id}": ["get"],
        "/api/v1/scans/{scan_id}/evidence/{evidence_id}": ["get"],
        "/api/v1/scans/{scan_id}/report": ["get"],
        "/api/v1/scans/{scan_id}/resources": ["get"],
        "/api/v1/scans/{scan_id}/risks": ["get"],
    }
    assert harness.client.get("/docs").status_code == 200


def test_create_git_scan_persists_a_real_queued_run(harness: ApiHarness) -> None:
    response = harness.client.post(
        "/api/v1/scans",
        json={"source_type": "git", "source": "https://GitHub.COM:443/example/OpenGuard.git"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body == {
        "scan_id": "scn_00000000-0000-0000-0000-000000000001",
        "status": "queued",
        "status_url": "/api/v1/scans/scn_00000000-0000-0000-0000-000000000001",
    }
    stored = harness.registry.get(body["scan_id"])
    assert stored.revision == 1
    assert stored.run.project.source == "https://github.com/example/OpenGuard.git"
    assert stored.run.project.name == "OpenGuard"
    assert stored.run.status.value == "queued"
    assert stored.run.components == []


def test_create_is_durably_idempotent_and_detects_conflicts(harness: ApiHarness) -> None:
    payload = {"source_type": "git", "source": VALID_SOURCE, "idempotency_key": "demo-001"}
    first = harness.client.post("/api/v1/scans", json=payload)
    second = harness.client.post("/api/v1/scans", json=payload)
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert len(harness.registry.list_runs().items) == 1

    conflict = harness.client.post(
        "/api/v1/scans",
        json={"source_type": "git", "source": "https://github.com/example/other", "idempotency_key": "demo-001"},
    )
    _assert_error(conflict, status_code=409, code="invalid_source", reason="idempotency_conflict")


@pytest.mark.parametrize(
    "source,reason",
    [
        ("http://github.com/example/repo", "url_invalid"),
        ("https://user:secret@github.com/example/repo", "url_invalid"),
        ("https://github.com/example/repo?token=secret", "url_invalid"),
        ("https://127.0.0.1/example/repo", "host_not_public"),
        ("https://localhost/example/repo", "host_not_public"),
        ("https://github.com/", "path_invalid"),
        ("https://github.com/example/%2e%2e/repo", "path_invalid"),
    ],
)
def test_create_rejects_non_public_or_non_canonical_sources(
    harness: ApiHarness,
    source: str,
    reason: str,
) -> None:
    response = harness.client.post("/api/v1/scans", json={"source_type": "git", "source": source})
    _assert_error(response, status_code=422, code="invalid_source", reason=reason)
    assert "secret" not in response.text


def test_request_validation_uses_the_frozen_error_envelope(harness: ApiHarness) -> None:
    response = harness.client.post(
        "/api/v1/scans",
        json={"source_type": "git", "source": VALID_SOURCE, "unexpected": True},
    )
    _assert_error(response, status_code=422, code="invalid_source", reason="request_invalid")
    assert "unexpected" not in response.text


@pytest.mark.parametrize(
    "source",
    [
        "https://git\nhub.com/example/repo",
        "https://github.com/example/%0Arepo",
    ],
)
def test_create_rejects_raw_and_decoded_control_characters(harness: ApiHarness, source: str) -> None:
    response = harness.client.post("/api/v1/scans", json={"source_type": "git", "source": source})
    _assert_error(response, status_code=422, code="invalid_source", reason="url_invalid")


def test_create_enforces_source_limit_in_utf8_bytes(harness: ApiHarness) -> None:
    source = "https://github.com/example/" + ("汉" * 700)
    assert len(source) < 2048 < len(source.encode("utf-8"))
    response = harness.client.post("/api/v1/scans", json={"source_type": "git", "source": source})
    _assert_error(response, status_code=422, code="invalid_source", reason="url_invalid")


@pytest.mark.parametrize(
    "method,path,status_code,reason",
    [
        ("get", "/api/v1/route-that-does-not-exist", 404, "route_not_found"),
        ("post", f"/api/v1/scans/{MISSING_SCAN_ID}", 405, "method_not_allowed"),
        ("delete", "/api/v1/scans", 405, "method_not_allowed"),
    ],
)
def test_unknown_routes_and_methods_use_the_frozen_error_envelope(
    harness: ApiHarness,
    method: str,
    path: str,
    status_code: int,
    reason: str,
) -> None:
    response = getattr(harness.client, method)(path)
    _assert_error(response, status_code=status_code, code="invalid_source", reason=reason)


def test_status_reads_the_persisted_snapshot_and_missing_is_stable(harness: ApiHarness) -> None:
    scan_id = _create(harness)
    response = harness.client.get(f"/api/v1/scans/{scan_id}")
    assert response.status_code == 200
    assert response.json() == {
        "scan_id": scan_id,
        "created_at": "2026-09-03T02:00:00Z",
        "started_at": None,
        "finished_at": None,
        "ai_progress": None,
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
    missing = harness.client.get(f"/api/v1/scans/{MISSING_SCAN_ID}")
    _assert_error(missing, status_code=404, code="scan_not_found", reason="not_found")


def test_result_routes_do_not_fake_results_for_a_queued_scan(harness: ApiHarness) -> None:
    scan_id = _create(harness)
    for suffix in ("resources", "risks", "evidence/evd_00000000-0000-0000-0000-000000000000"):
        response = harness.client.get(f"/api/v1/scans/{scan_id}/{suffix}")
        _assert_error(response, status_code=409, code="scan_not_ready", reason="status_not_ready")
    report = harness.client.get(f"/api/v1/scans/{scan_id}/report", params={"format": "html"})
    _assert_error(report, status_code=409, code="report_not_ready", reason="status_not_ready")


def test_resources_are_tagged_stably_and_apply_frozen_filters(harness: ApiHarness) -> None:
    scan_id = _create(harness)
    completed = _complete_from_sample(harness, scan_id)
    response = harness.client.get(f"/api/v1/scans/{scan_id}/resources")
    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert [(item["kind"], item["resource"]["id"]) for item in response.json()["items"]] == [
        ("ai_asset", completed.ai_assets[0].id),
        ("component", completed.components[0].id),
    ]

    component = harness.client.get(f"/api/v1/scans/{scan_id}/resources", params={"ecosystem": "pypi"}).json()
    assert component["total"] == 1
    assert component["items"][0]["kind"] == "component"
    asset = harness.client.get(
        f"/api/v1/scans/{scan_id}/resources",
        params={"provider": "hugging_face", "verification_status": "pending"},
    ).json()
    assert asset["total"] == 1
    assert asset["items"][0]["kind"] == "ai_asset"


def test_risks_evidence_and_report_are_read_from_the_same_snapshot(harness: ApiHarness) -> None:
    scan_id = _create(harness)
    completed = _complete_from_sample(harness, scan_id)

    risks = harness.client.get(
        f"/api/v1/scans/{scan_id}/risks",
        params={"outcome": "review_required", "severity": "low", "resource_kind": "component"},
    )
    assert risks.status_code == 200
    assert risks.json()["total"] == 1
    assert risks.json()["items"][0]["id"] == completed.findings[0].id

    evidence = harness.client.get(f"/api/v1/scans/{scan_id}/evidence/{completed.evidence[0].id}")
    assert evidence.status_code == 200
    assert evidence.json()["id"] == completed.evidence[0].id
    missing = harness.client.get(
        f"/api/v1/scans/{scan_id}/evidence/evd_00000000-0000-0000-0000-000000000000"
    )
    _assert_error(missing, status_code=404, code="evidence_not_found", reason="not_found")

    report = harness.client.get(f"/api/v1/scans/{scan_id}/report", params={"format": "html"})
    assert report.status_code == 200
    assert report.json()["href"] == f"reports/{scan_id}.html"
    missing_report = harness.client.get(f"/api/v1/scans/{scan_id}/report", params={"format": "json"})
    _assert_error(missing_report, status_code=409, code="report_not_ready", reason="not_generated")


def test_unexpected_failures_do_not_expose_internal_context(tmp_path: Path) -> None:
    class ExplodingRegistry:
        def get(self, _: str) -> None:
            raise RuntimeError("/Users/private/project token=do-not-leak")

    app = create_app(ExplodingRegistry())  # type: ignore[arg-type]
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(f"/api/v1/scans/{MISSING_SCAN_ID}")
    _assert_error(response, status_code=500, code="internal_error", reason="unexpected_failure")
    assert "/Users/" not in response.text
    assert "do-not-leak" not in response.text


def test_default_factory_creates_a_private_runnable_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENGUARD_DATA_DIR", raising=False)
    app = create_default_app()
    with TestClient(app) as client:
        assert client.get("/openapi.json").status_code == 200
    assert stat_mode(tmp_path / "data") == 0o700
    assert stat_mode(tmp_path / "data" / "scans.db") == 0o600


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def test_persistent_capacity_rejects_git_zip_before_read_and_preserves_get(harness, tmp_path):
    from app.api.main import _PersistentCapacity
    existing = _create(harness)
    guard = _PersistentCapacity(tmp_path, harness.registry, limit_bytes=1024, reserve_bytes=512, free_floor_bytes=1)
    app = create_app(harness.registry, persistent_capacity=guard)
    before = harness.registry.get(existing)
    with TestClient(app) as client:
        for headers, body in [({'content-type': 'application/json'}, b'not-json'),
                              ({'content-type': 'multipart/form-data; boundary=x'}, b'not-multipart')]:
            response = client.post('/api/v1/scans', headers=headers, content=body)
            assert response.status_code == 503
            assert response.json()['error']['details']['reason'] == 'persistent_capacity_exceeded'
        assert client.get('/api/v1/scans/' + existing).status_code == 200
    assert harness.registry.get(existing) == before
    assert harness.registry.active_count() == 1
    assert not (tmp_path / 'uploads').exists()


def test_capacity_queued_reservation_survives_new_guard_and_failure_releases_lock(harness, tmp_path):
    from app.api.main import _PersistentCapacity
    mib = 1024**2
    guard = _PersistentCapacity(tmp_path, harness.registry, limit_bytes=3*mib, reserve_bytes=mib, free_floor_bytes=1)
    with TestClient(create_app(harness.registry, persistent_capacity=guard)) as client:
        assert client.post('/api/v1/scans', json={'source_type':'git','source':VALID_SOURCE}).status_code == 202
        assert client.post('/api/v1/scans', json={'source_type':'git','source':VALID_SOURCE}).status_code == 202
        rejected = client.post('/api/v1/scans', json={'source_type':'git','source':VALID_SOURCE})
        assert rejected.status_code == 503
        assert not guard.lock.locked()
    reopened = SQLiteScanRunRegistry(tmp_path / 'scans.db')
    again = _PersistentCapacity(tmp_path, reopened, limit_bytes=3*mib, reserve_bytes=mib, free_floor_bytes=1)
    with TestClient(create_app(reopened, persistent_capacity=again)) as client:
        assert client.post('/api/v1/scans', json={'source_type':'git','source':VALID_SOURCE}).status_code == 503
    reopened.close()


def test_capacity_inventory_counts_same_disk_workspace_unknown_files_and_fails_closed(harness, tmp_path, monkeypatch):
    from app.api.main import _PersistentCapacity
    from app.api.service import ApiError
    from types import SimpleNamespace
    mib = 1024**2
    guard = _PersistentCapacity(tmp_path, harness.registry, limit_bytes=4*mib, reserve_bytes=mib, free_floor_bytes=mib)
    workspace = tmp_path / 'workspaces'; workspace.mkdir()
    with (workspace / 'temporary').open('wb') as f: f.truncate(8*mib)
    with pytest.raises(ApiError): guard.check()
    (workspace / 'temporary').unlink()
    guard.check()
    unexpected = tmp_path / 'retained-old-report'
    with unexpected.open('wb') as f: f.truncate(4*mib)
    with pytest.raises(ApiError): guard.check()
    unexpected.unlink()  # This isolated test owns the dummy file, not user reports.
    (tmp_path / 'unsafe-link').symlink_to(workspace)
    with pytest.raises(OSError): guard.check()
    (tmp_path / 'unsafe-link').unlink()
    monkeypatch.setattr(os, 'statvfs', lambda _: SimpleNamespace(f_bavail=1, f_frsize=1))
    with pytest.raises(ApiError): guard.check()
    monkeypatch.setattr(os, 'statvfs', lambda _: (_ for _ in ()).throw(OSError('private path')))
    with TestClient(create_app(harness.registry, persistent_capacity=guard)) as client:
        response=client.post('/api/v1/scans',json={'source_type':'git','source':VALID_SOURCE})
        assert response.status_code == 503 and 'private path' not in response.text
    assert not guard.lock.locked()


def test_capacity_concurrent_request_busy_does_not_create_record(harness, tmp_path):
    from app.api.main import _PersistentCapacity
    guard=_PersistentCapacity(tmp_path,harness.registry)
    guard.lock.acquire()
    try:
        with TestClient(create_app(harness.registry,persistent_capacity=guard)) as client:
            r=client.post('/api/v1/scans',json={'source_type':'git','source':VALID_SOURCE})
            assert r.status_code==503 and r.json()['error']['details']['reason']=='persistent_capacity_busy'
        assert harness.registry.active_count()==0
    finally:
        guard.lock.release()
    with TestClient(create_app(harness.registry,persistent_capacity=guard)) as client:
        assert client.post('/api/v1/scans',json={'source_type':'git','source':VALID_SOURCE}).status_code==202
