from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from itertools import count
from pathlib import Path
from typing import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api import create_app, create_default_app
from app.api.models import GitScanCreateRequest
from app.api.service import ScanApiService
from app.domain.models import ReportFormat, ScanRun
from app.persistence import SQLiteScanRunRegistry
from app.reporting import ReportArtifactStore, ReportStoreError, render_report


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PATH = REPOSITORY_ROOT / "examples" / "sample-scan-result.json"
FIXED_TIME = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)


def _private_directory(path: Path) -> Path:
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def _sample() -> ScanRun:
    return ScanRun.model_validate_json(SAMPLE_PATH.read_bytes())


def _partial() -> ScanRun:
    run = _sample()
    components = [item.model_copy(update={"license_expression_id": None}) for item in run.components]
    payload = run.model_dump(mode="python")
    payload.update(
        status="partial",
        stage="rules",
        progress=70,
        components=components,
        licenses=[],
        obligations=[],
        findings=[],
        remediations=[],
        report_links=[],
        errors=[
            {
                "code": "rules_stage_not_connected",
                "stage": "rules",
                "message": "License rules are not connected.",
                "recoverable": True,
            }
        ],
        summary={
            "component_count": len(components),
            "ai_asset_count": len(run.ai_assets),
            "evidence_count": len(run.evidence),
            "finding_counts": {"pass": 0, "warning": 0, "review_required": 0, "unknown": 0},
        },
    )
    return ScanRun.model_validate(payload)


def _persisted_terminal(
    registry: SQLiteScanRunRegistry,
    *,
    partial: bool = False,
) -> ScanRun:
    ids = count(1)
    service = ScanApiService(
        registry,
        clock=lambda: FIXED_TIME,
        id_factory=lambda: UUID(int=next(ids)),
    )
    accepted = service.create_git_scan(
        GitScanCreateRequest(source_type="git", source="https://github.com/example/OpenGuard")
    )
    queued = registry.get(accepted.scan_id)
    started_at = FIXED_TIME + timedelta(seconds=1)
    running = ScanRun.model_validate(
        {
            **queued.run.model_dump(mode="python"),
            "status": "running",
            "stage": "ingestion",
            "progress": 10,
            "started_at": started_at,
        }
    )
    running_stored = registry.replace(running, expected_revision=queued.revision)
    source = _partial() if partial else _sample()
    terminal = ScanRun.model_validate(
        {
            **source.model_dump(mode="python"),
            "id": queued.run.id,
            "idempotency_key": queued.run.idempotency_key,
            "project": queued.run.project,
            "provenance": queued.run.provenance,
            "created_at": queued.run.created_at,
            "started_at": started_at,
            "finished_at": FIXED_TIME + timedelta(seconds=2),
            "report_links": [],
        }
    )
    return registry.replace(terminal, expected_revision=running_stored.revision).run


def test_publish_is_private_integrity_checked_restartable_and_idempotent(tmp_path: Path) -> None:
    root = _private_directory(tmp_path / "reports")
    run = _partial()
    store = ReportArtifactStore(root, clock=lambda: FIXED_TIME)

    first = store.publish(run, ReportFormat.HTML)
    second = store.publish(run, ReportFormat.HTML, generated_at=FIXED_TIME + timedelta(hours=1))
    reopened = ReportArtifactStore(root).get(run.id, ReportFormat.HTML)

    assert second == first == reopened.link
    assert first.href == f"api/v1/scans/{run.id}/report?format=html&download=true"
    assert first.generated_at == FIXED_TIME
    assert reopened.content == render_report(run, ReportFormat.HTML).content
    assert first.content_hash.value == hashlib.sha256(reopened.content).hexdigest()
    scan_directory = root / run.id
    assert scan_directory.stat().st_mode & 0o777 == 0o700
    assert {item.stat().st_mode & 0o777 for item in scan_directory.iterdir()} == {0o600}
    assert not any(item.name.endswith(".tmp") for item in scan_directory.iterdir())

    content_path = next(scan_directory.glob("html-*.artifact"))
    os.chmod(content_path, 0o700)
    with pytest.raises(ReportStoreError, match="report_store_corrupt"):
        store.get(run.id, ReportFormat.HTML)


@pytest.mark.parametrize("report_format", list(ReportFormat))
def test_each_format_has_verified_public_metadata(tmp_path: Path, report_format: ReportFormat) -> None:
    root = _private_directory(tmp_path / "reports")
    run = _sample()
    store = ReportArtifactStore(root, clock=lambda: FIXED_TIME)

    link = store.publish(run, report_format)
    stored = store.get(run.id, report_format)

    assert stored.link == link
    assert stored.filename == render_report(run, report_format).filename
    assert stored.media_type == render_report(run, report_format).media_type
    assert stored.content == render_report(run, report_format).content
    assert Path(link.href.split("?", 1)[0]).is_absolute() is False


def test_store_rejects_non_private_root_and_symlink_root(tmp_path: Path) -> None:
    with pytest.raises(ReportStoreError, match="report_store_invalid_argument"):
        ReportArtifactStore(Path("relative-reports"))

    public = _private_directory(tmp_path / "public")
    os.chmod(public, 0o755)
    with pytest.raises(ReportStoreError, match="report_store_path_invalid"):
        ReportArtifactStore(public)

    private = _private_directory(tmp_path / "private")
    link = tmp_path / "link"
    link.symlink_to(private, target_is_directory=True)
    with pytest.raises(ReportStoreError, match="report_store_path_invalid"):
        ReportArtifactStore(link)


def test_default_factory_creates_a_private_report_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENGUARD_DATA_DIR", raising=False)

    app = create_default_app()
    with TestClient(app) as client:
        assert client.get("/openapi.json").status_code == 200

    assert (tmp_path / "data" / "reports").stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize("target", ["artifact", "metadata"])
def test_tampering_or_missing_committed_content_fails_closed(tmp_path: Path, target: str) -> None:
    root = _private_directory(tmp_path / "reports")
    run = _sample()
    store = ReportArtifactStore(root, clock=lambda: FIXED_TIME)
    store.publish(run, ReportFormat.JSON)
    scan_directory = root / run.id
    path = (
        next(scan_directory.glob("json-*.artifact"))
        if target == "artifact"
        else scan_directory / "json.metadata.json"
    )
    if target == "artifact":
        path.write_bytes(b"tampered")
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["link"]["href"] = "reports/wrong.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
    os.chmod(path, 0o600)

    with pytest.raises(ReportStoreError, match="report_store_corrupt"):
        store.get(run.id, ReportFormat.JSON)


def test_committed_symlink_and_missing_content_fail_closed(tmp_path: Path) -> None:
    root = _private_directory(tmp_path / "reports")
    run = _sample()
    store = ReportArtifactStore(root, clock=lambda: FIXED_TIME)
    store.publish(run, ReportFormat.CSV)
    content = next((root / run.id).glob("csv-*.artifact"))
    content.unlink()
    with pytest.raises(ReportStoreError, match="report_store_corrupt"):
        store.get(run.id, ReportFormat.CSV)

    sentinel = tmp_path / "sentinel"
    sentinel.write_bytes(b"outside")
    content.symlink_to(sentinel)
    with pytest.raises(ReportStoreError, match="report_store_corrupt"):
        store.get(run.id, ReportFormat.CSV)
    assert sentinel.read_bytes() == b"outside"


def test_metadata_is_commit_marker_when_atomic_publication_stops_early(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _private_directory(tmp_path / "reports")
    run = _sample()
    store = ReportArtifactStore(root, clock=lambda: FIXED_TIME)
    real_replace = os.replace
    calls = 0

    def fail_second_replace(source: object, destination: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated metadata commit failure")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_second_replace)
    with pytest.raises(ReportStoreError, match="report_store_io_failed"):
        store.publish(run, ReportFormat.HTML)
    with pytest.raises(ReportStoreError, match="report_store_not_found"):
        store.get(run.id, ReportFormat.HTML)
    assert not any(item.name.endswith(".tmp") for item in (root / run.id).iterdir())


def test_failed_republication_keeps_the_previous_committed_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _private_directory(tmp_path / "reports")
    original = _sample()
    store = ReportArtifactStore(root, clock=lambda: FIXED_TIME)
    original_link = store.publish(original, ReportFormat.HTML)
    changed = original.model_copy(
        update={"project": original.project.model_copy(update={"name": "changed-project"})}
    )
    real_replace = os.replace
    calls = 0

    def fail_metadata_replace(source: object, destination: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated metadata commit failure")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_metadata_replace)
    with pytest.raises(ReportStoreError, match="report_store_io_failed"):
        store.publish(changed, ReportFormat.HTML)

    committed = store.get(original.id, ReportFormat.HTML)
    assert committed.link == original_link
    assert committed.content == render_report(original, ReportFormat.HTML).content


@pytest.fixture
def api_harness(tmp_path: Path) -> Iterator[tuple[TestClient, SQLiteScanRunRegistry, ReportArtifactStore, ScanRun]]:
    os.chmod(tmp_path, 0o700)
    registry = SQLiteScanRunRegistry(tmp_path / "scans.db")
    report_store = ReportArtifactStore(_private_directory(tmp_path / "reports"), clock=lambda: FIXED_TIME)
    run = _persisted_terminal(registry, partial=True)
    report_store.publish(run, ReportFormat.HTML)
    app = create_app(registry, report_store=report_store)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, registry, report_store, run
    registry.close()


def test_api_returns_report_link_then_downloads_verified_partial_bytes_read_only(
    api_harness: tuple[TestClient, SQLiteScanRunRegistry, ReportArtifactStore, ScanRun],
) -> None:
    client, _, store, run = api_harness
    content_path = next((store._root / run.id).glob("html-*.artifact"))  # test-only read-only observation
    metadata_path = store._root / run.id / "html.metadata.json"
    before = (content_path.stat().st_mtime_ns, metadata_path.stat().st_mtime_ns)

    metadata = client.get(f"/api/v1/scans/{run.id}/report", params={"format": "html"})
    assert metadata.status_code == 200
    link = metadata.json()
    assert link["href"] == f"api/v1/scans/{run.id}/report?format=html&download=true"
    response = client.get("/" + link["href"])

    expected = render_report(run, ReportFormat.HTML)
    assert response.status_code == 200
    assert response.content == expected.content
    assert response.headers["content-type"] == expected.media_type
    assert response.headers["content-disposition"] == f'attachment; filename="{expected.filename}"'
    assert response.headers["etag"] == f'"sha256:{expected.sha256}"'
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"
    assert "sandbox" in response.headers["content-security-policy"]
    assert "阶段性报告" in response.text
    assert "这不等于项目已通过许可证合规核验" in response.text
    assert before == (content_path.stat().st_mtime_ns, metadata_path.stat().st_mtime_ns)


def test_api_missing_and_corrupt_reports_use_stable_redacted_errors(
    api_harness: tuple[TestClient, SQLiteScanRunRegistry, ReportArtifactStore, ScanRun],
) -> None:
    client, _, store, run = api_harness
    missing = client.get(f"/api/v1/scans/{run.id}/report", params={"format": "json"})
    assert missing.status_code == 409
    assert missing.json()["error"]["details"] == {"reason": "not_generated"}

    content = next((store._root / run.id).glob("html-*.artifact"))
    content.write_bytes(b"/Users/private token=do-not-leak")
    os.chmod(content, 0o600)
    corrupt = client.get(
        f"/api/v1/scans/{run.id}/report",
        params={"format": "html", "download": "true"},
    )
    assert corrupt.status_code == 500
    assert corrupt.json()["error"]["details"] == {"reason": "report_storage_failure"}
    assert "/Users/" not in corrupt.text
    assert "do-not-leak" not in corrupt.text


@pytest.mark.parametrize("method", ["post", "head"])
def test_report_download_does_not_open_a_write_method(
    api_harness: tuple[TestClient, SQLiteScanRunRegistry, ReportArtifactStore, ScanRun],
    method: str,
) -> None:
    client, _, _, run = api_harness
    response = getattr(client, method)(
        f"/api/v1/scans/{run.id}/report",
        params={"format": "html", "download": "true"},
    )
    assert response.status_code == 405
    assert response.headers["x-request-id"].startswith("req_")
    if method == "post":
        assert response.json()["error"]["details"] == {"reason": "method_not_allowed"}
    else:
        assert response.content == b""
