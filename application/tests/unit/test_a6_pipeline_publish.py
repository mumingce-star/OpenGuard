"""A6-2 terminal publication and ZIP-to-report integration tests."""

from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from datetime import datetime, timedelta, timezone
from itertools import count
from pathlib import Path
from typing import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api import create_app, create_default_app
from app.api.models import ZipScanCreateFields
from app.api.service import ScanApiService
from app.api.zip_scan import ZipScanRuntime
from app.domain.models import ReportFormat, ScanRun, ScanStage, ScanStatus
from app.persistence import SQLiteScanRunRegistry
from app.pipeline import PipelineError, PipelinePlan, PipelineStep, ScanPipelineWorker, build_local_zip_dependency_plan
from app.reporting import PipelineReportPublisher, ReportArtifactStore, ReportPipelineError, render_report


ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PATH = ROOT / "examples" / "sample-scan-result.json"
FIXED_TIME = datetime(2030, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _private(path: Path) -> Path:
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def _zip_bytes() -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("requirements.txt", "requests==2.32.5\n")
        archive.writestr("package.json", '{"dependencies":{"react":"19.2.0"}}')
    return stream.getvalue()


def _archive(path: Path) -> Path:
    path.write_bytes(_zip_bytes())
    return path


def _queued(index: int = 1) -> ScanRun:
    payload = ScanRun.model_validate_json(SAMPLE_PATH.read_bytes()).model_dump(mode="python")
    suffix = f"{index:012x}"
    payload.update(
        id=f"scn_123e4567-e89b-12d3-a456-{suffix}",
        status=ScanStatus.QUEUED,
        stage=ScanStage.QUEUED,
        progress=0,
        report_links=[],
        errors=[],
        started_at=None,
        finished_at=None,
    )
    payload["project"] = {
        **payload["project"],
        "id": f"prj_123e4567-e89b-12d3-a456-{suffix}",
        "created_at": payload["created_at"],
    }
    return ScanRun.model_validate(payload)


def _noop_plan() -> PipelinePlan:
    return PipelinePlan(
        steps=tuple(
            PipelineStep(stage, lambda run: run)
            for stage in (
                ScanStage.INGESTION,
                ScanStage.INVENTORY,
                ScanStage.SCAN,
                ScanStage.NORMALIZE,
                ScanStage.RULES,
                ScanStage.AI_ASSIST,
                ScanStage.REPORT,
            )
        )
    )


def _local_partial(
    tmp_path: Path,
    *,
    publisher: PipelineReportPublisher | None = None,
) -> tuple[SQLiteScanRunRegistry, ScanRun, Path]:
    archive = _archive(tmp_path / "pipeline-demo.zip")
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    identifiers = count(1)
    service = ScanApiService(
        registry,
        clock=lambda: FIXED_TIME,
        id_factory=lambda: UUID(int=next(identifiers)),
    )
    accepted, created = service.create_zip_scan(
        ZipScanCreateFields(source_type="zip"),
        staged_name=archive.name,
        project_name="pipeline-demo",
        input_digest=hashlib.sha256(archive.read_bytes()).hexdigest(),
    )
    assert created
    workspace = _private(tmp_path / "workspaces")
    result = ScanPipelineWorker(
        registry,
        clock=lambda: FIXED_TIME,
        terminal_publisher=publisher.publish if publisher is not None else None,
    ).run(
        accepted.scan_id,
        build_local_zip_dependency_plan(archive, workspace, clock=lambda: FIXED_TIME),
    )
    return registry, result.run, workspace


def test_publisher_binds_all_formats_without_recursive_report_links(tmp_path: Path) -> None:
    registry, partial, _ = _local_partial(tmp_path)
    store = ReportArtifactStore(_private(tmp_path / "reports"), clock=lambda: FIXED_TIME)

    published = PipelineReportPublisher(store).publish(partial)

    assert partial.report_links == []
    assert [link.format for link in published.report_links] == list(ReportFormat)
    assert render_report(published, ReportFormat.JSON).content == render_report(partial, ReportFormat.JSON).content
    report_payload = json.loads(render_report(published, ReportFormat.JSON).content)
    assert report_payload["scan_run"]["report_links"] == []
    for link in published.report_links:
        stored = store.get(partial.id, link.format)
        assert stored.link == link
        assert hashlib.sha256(stored.content).hexdigest() == link.content_hash.value
    registry.close()


def test_worker_commits_partial_and_four_links_in_one_terminal_revision(tmp_path: Path) -> None:
    store = ReportArtifactStore(_private(tmp_path / "reports"), clock=lambda: FIXED_TIME)
    registry, run, _ = _local_partial(tmp_path, publisher=PipelineReportPublisher(store))

    assert (run.status, run.stage, run.progress) == (ScanStatus.PARTIAL, ScanStage.RULES, 70)
    assert [error.code for error in run.errors] == ["rules_stage_not_connected"]
    assert [link.format for link in run.report_links] == list(ReportFormat)
    assert registry.get(run.id).run == run
    registry.close()


def test_zip_http_reaches_truthful_partial_and_restartable_downloads(tmp_path: Path) -> None:
    os.chmod(tmp_path, 0o700)
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    store = ReportArtifactStore(_private(tmp_path / "reports"), clock=lambda: FIXED_TIME)
    runtime = ZipScanRuntime(
        registry,
        upload_root=_private(tmp_path / "uploads"),
        workspace_root=_private(tmp_path / "workspaces"),
        report_publisher=PipelineReportPublisher(store),
    )
    app = create_app(registry, zip_runtime=runtime, report_store=store)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/scans",
            data={"source_type": "zip"},
            files={"file": ("demo.zip", _zip_bytes(), "application/zip")},
        )
        assert response.status_code == 202
        scan_id = response.json()["scan_id"]
        run = registry.get(scan_id).run
        assert (run.status, run.stage, run.progress) == (ScanStatus.PARTIAL, ScanStage.RULES, 70)
        assert [error.code for error in run.errors] == ["rules_stage_not_connected"]
        assert [link.format for link in run.report_links] == list(ReportFormat)
        for link in run.report_links:
            metadata = client.get(f"/api/v1/scans/{scan_id}/report", params={"format": link.format.value})
            assert metadata.status_code == 200
            assert metadata.json() == link.model_dump(mode="json")
            download = client.get("/" + link.href)
            assert download.status_code == 200
            assert hashlib.sha256(download.content).hexdigest() == link.content_hash.value

        html = client.get(f"/api/v1/scans/{scan_id}/report", params={"format": "html", "download": True})
        assert "阶段性报告" in html.text
        assert "这不等于项目已通过许可证合规核验" in html.text
        payload = client.get(
            f"/api/v1/scans/{scan_id}/report",
            params={"format": "json", "download": True},
        ).json()
        assert payload["completeness"] == "partial"
        assert payload["scan_run"]["report_links"] == []
        assert payload["scan_run"]["errors"][0]["code"] == "rules_stage_not_connected"

    reopened_store = ReportArtifactStore(tmp_path / "reports")
    with TestClient(create_app(registry, report_store=reopened_store)) as client:
        assert client.get(
            f"/api/v1/scans/{scan_id}/report",
            params={"format": "resource_inventory", "download": True},
        ).status_code == 200
    registry.close()


def test_unregistered_store_artifact_is_not_api_visible(tmp_path: Path) -> None:
    registry, run, _ = _local_partial(tmp_path)
    store = ReportArtifactStore(_private(tmp_path / "reports"), clock=lambda: FIXED_TIME)
    store.publish(run, ReportFormat.HTML)

    with TestClient(create_app(registry, report_store=store)) as client:
        response = client.get(f"/api/v1/scans/{run.id}/report", params={"format": "html"})
        assert response.status_code == 409
        assert response.json()["error"]["details"] == {"reason": "not_generated"}
    registry.close()


def test_publication_failure_keeps_partial_results_and_hides_orphans(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ReportArtifactStore(_private(tmp_path / "reports"), clock=lambda: FIXED_TIME)
    original = store.publish
    calls = 0

    def fail_second(run: ScanRun, report_format: ReportFormat, **kwargs: object):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("/Users/private token=do-not-leak")
        return original(run, report_format, **kwargs)

    monkeypatch.setattr(store, "publish", fail_second)
    registry, run, _ = _local_partial(tmp_path, publisher=PipelineReportPublisher(store))

    assert (run.status, run.stage, run.progress) == (ScanStatus.PARTIAL, ScanStage.RULES, 70)
    assert run.report_links == []
    assert [error.code for error in run.errors] == ["rules_stage_not_connected", "report_publish_failed"]
    assert "/Users/" not in run.model_dump_json()
    assert "do-not-leak" not in run.model_dump_json()
    with TestClient(create_app(registry, report_store=store)) as client:
        assert client.get(f"/api/v1/scans/{run.id}/report", params={"format": "html"}).status_code == 409
    registry.close()


def test_terminal_cas_conflict_keeps_published_orphans_hidden(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = _archive(tmp_path / "pipeline-demo.zip")
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    identifiers = count(1)
    service = ScanApiService(
        registry,
        clock=lambda: FIXED_TIME,
        id_factory=lambda: UUID(int=next(identifiers)),
    )
    accepted, created = service.create_zip_scan(
        ZipScanCreateFields(source_type="zip"),
        staged_name=archive.name,
        project_name="pipeline-demo",
        input_digest=hashlib.sha256(archive.read_bytes()).hexdigest(),
    )
    assert created
    store = ReportArtifactStore(_private(tmp_path / "reports"), clock=lambda: FIXED_TIME)
    publisher = PipelineReportPublisher(store)
    original = publisher.publish

    def publish_then_race(terminal: ScanRun) -> ScanRun:
        linked = original(terminal)
        current = registry.get(terminal.id)
        raced = current.run.model_copy(update={"progress": current.run.progress + 1})
        registry.replace(raced, expected_revision=current.revision)
        return linked

    monkeypatch.setattr(publisher, "publish", publish_then_race)
    with pytest.raises(PipelineError, match="pipeline_state_conflict"):
        ScanPipelineWorker(
            registry,
            clock=lambda: FIXED_TIME,
            terminal_publisher=publisher.publish,
        ).run(
            accepted.scan_id,
            build_local_zip_dependency_plan(
                archive,
                _private(tmp_path / "workspaces"),
                clock=lambda: FIXED_TIME,
            ),
        )

    latest = registry.get(accepted.scan_id).run
    assert (latest.status, latest.stage, latest.progress) == (ScanStatus.RUNNING, ScanStage.RULES, 71)
    assert latest.report_links == []
    for report_format in ReportFormat:
        assert store.get(latest.id, report_format).link.format is report_format
    with TestClient(create_app(registry, report_store=store)) as client:
        response = client.get(f"/api/v1/scans/{latest.id}/report", params={"format": "html"})
        assert response.status_code == 409
        assert response.json()["error"]["details"] == {"reason": "status_not_ready"}
    registry.close()


def test_invalid_terminal_publisher_cannot_change_pipeline_facts(tmp_path: Path) -> None:
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    queued = registry.create(_queued())

    result = ScanPipelineWorker(
        registry,
        clock=lambda: FIXED_TIME,
        terminal_publisher=lambda terminal: terminal.model_copy(
            update={"project": terminal.project.model_copy(update={"name": "tampered"})}
        ),
    ).run(queued.run.id, _noop_plan())

    assert (result.run.status, result.run.stage, result.run.progress) == (
        ScanStatus.PARTIAL,
        ScanStage.REPORT,
        95,
    )
    assert result.run.project.name != "tampered"
    assert result.run.errors[-1].code == "report_publish_failed"
    registry.close()


def test_registry_link_and_store_metadata_must_match(tmp_path: Path) -> None:
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    queued = registry.create(_queued())
    store = ReportArtifactStore(_private(tmp_path / "reports"), clock=lambda: FIXED_TIME)
    publisher = PipelineReportPublisher(store)

    def mismatched(terminal: ScanRun) -> ScanRun:
        published = publisher.publish(terminal)
        links = list(published.report_links)
        links[0] = links[0].model_copy(update={"generated_at": FIXED_TIME + timedelta(seconds=1)})
        return ScanRun.model_validate({**published.model_dump(mode="python"), "report_links": links})

    result = ScanPipelineWorker(
        registry,
        clock=lambda: FIXED_TIME,
        terminal_publisher=mismatched,
    ).run(queued.run.id, _noop_plan())
    assert result.run.status is ScanStatus.COMPLETED

    with TestClient(create_app(registry, report_store=store), raise_server_exceptions=False) as client:
        response = client.get(f"/api/v1/scans/{result.run.id}/report", params={"format": "html"})
        assert response.status_code == 500
        assert response.json()["error"]["details"] == {"reason": "report_storage_failure"}
    registry.close()


def test_publisher_rejects_nonterminal_and_prelinked_runs(tmp_path: Path) -> None:
    publisher = PipelineReportPublisher(
        ReportArtifactStore(_private(tmp_path / "reports"), clock=lambda: FIXED_TIME)
    )
    with pytest.raises(ReportPipelineError, match="report_pipeline_invalid_argument"):
        publisher.publish(_queued())

    registry, partial, _ = _local_partial(_private(tmp_path / "prelinked"))
    linked = publisher.publish(partial)
    with pytest.raises(ReportPipelineError, match="report_pipeline_invalid_argument"):
        publisher.publish(linked)
    registry.close()


def test_default_factory_wires_zip_pipeline_reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENGUARD_DATA_DIR", raising=False)
    with TestClient(create_default_app(), raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/scans",
            data={"source_type": "zip"},
            files={"file": ("default.zip", _zip_bytes(), "application/zip")},
        )
        assert response.status_code == 202
        scan_id = response.json()["scan_id"]
        report = client.get(f"/api/v1/scans/{scan_id}/report", params={"format": "html"})
        assert report.status_code == 200
        assert client.get("/" + report.json()["href"]).status_code == 200
    assert (tmp_path / "data" / "reports").stat().st_mode & 0o777 == 0o700
