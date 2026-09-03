"""Implementation-side A3-2 ZIP HTTP to A4-1 background vertical-slice tests."""

from __future__ import annotations

import io
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

import app.api.main as api_main
from app.api import create_app, create_default_app
from app.api.zip_scan import ZipScanRuntime
from app.domain import ScanStatus
from app.persistence import SQLiteScanRunRegistry


@dataclass
class Harness:
    client: TestClient
    registry: SQLiteScanRunRegistry
    upload_root: Path
    workspace_root: Path
    runtime: ZipScanRuntime


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[Harness]:
    os.chmod(tmp_path, 0o700)
    upload_root = tmp_path / "uploads"
    workspace_root = tmp_path / "workspaces"
    upload_root.mkdir(mode=0o700)
    workspace_root.mkdir(mode=0o700)
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    runtime = ZipScanRuntime(
        registry,
        upload_root=upload_root,
        workspace_root=workspace_root,
    )
    app = create_app(registry, zip_runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield Harness(client, registry, upload_root, workspace_root, runtime)
    registry.close()


def _archive(*, python: str = "requests==2.32.0\n", javascript: str = '{"name":"demo","dependencies":{"react":"19.0.0"}}') -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("requirements.txt", python)
        archive.writestr("package.json", javascript)
    return stream.getvalue()


def _post(harness: Harness, content: bytes, *, key: str | None = None, filename: str = "demo.zip", media_type: str = "application/zip"):
    fields = {"source_type": "zip"}
    if key is not None:
        fields["idempotency_key"] = key
    return harness.client.post(
        "/api/v1/scans",
        data=fields,
        files={"file": (filename, content, media_type)},
    )


def _assert_clean(harness: Harness) -> None:
    assert list(harness.upload_root.iterdir()) == []
    assert list(harness.workspace_root.iterdir()) == []


def test_pos_a3zip_001_upload_runs_real_dependencies_to_visible_partial(harness: Harness) -> None:
    response = _post(harness, _archive())
    assert response.status_code == 202
    accepted = response.json()
    assert accepted["status"] == "queued"

    status = harness.client.get(accepted["status_url"])
    assert status.status_code == 200
    payload = status.json()
    assert payload["status"] == "partial"
    assert payload["stage"] == "rules"
    assert payload["progress"] == 70
    assert payload["summary"] == {
        "component_count": 2,
        "ai_asset_count": 0,
        "evidence_count": 2,
        "finding_counts": {"pass": 0, "warning": 0, "review_required": 0, "unknown": 0},
    }
    assert [error["code"] for error in payload["errors"]] == ["rules_stage_not_connected"]

    resources = harness.client.get(f"/api/v1/scans/{accepted['scan_id']}/resources")
    assert resources.status_code == 200
    assert {(item["resource"]["ecosystem"], item["resource"]["name"]) for item in resources.json()["items"]} == {
        ("npm", "react"),
        ("pypi", "requests"),
    }
    evidence_id = resources.json()["items"][0]["resource"]["evidence_ids"][0]
    assert harness.client.get(f"/api/v1/scans/{accepted['scan_id']}/evidence/{evidence_id}").status_code == 200
    _assert_clean(harness)


def test_pos_a3zip_002_same_key_and_bytes_are_idempotent_without_second_run(harness: Harness) -> None:
    content = _archive()
    first = _post(harness, content, key="zip-request-001")
    second = _post(harness, content, key="zip-request-001")
    assert first.status_code == second.status_code == 202
    assert first.json()["scan_id"] == second.json()["scan_id"]
    assert second.json()["status"] == "partial"
    assert len(harness.registry.list_runs().items) == 1
    _assert_clean(harness)


def test_neg_a3zip_004_same_key_different_bytes_conflicts_and_cleans(harness: Harness) -> None:
    assert _post(harness, _archive(), key="zip-request-002").status_code == 202
    conflict = _post(
        harness,
        _archive(python="httpx==0.28.0\n"),
        key="zip-request-002",
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["details"] == {"reason": "idempotency_conflict"}
    assert len(harness.registry.list_runs().items) == 1
    _assert_clean(harness)


@pytest.mark.parametrize(
    "data,files",
    [
        ({}, {"file": ("demo.zip", b"x", "application/zip")}),
        ({"source_type": "git"}, {"file": ("demo.zip", b"x", "application/zip")}),
        ({"source_type": "zip", "unexpected": "x"}, {"file": ("demo.zip", b"x", "application/zip")}),
        ({"source_type": "zip", "idempotency_key": ""}, {"file": ("demo.zip", b"x", "application/zip")}),
        ({"source_type": "zip"}, {"unexpected_file": ("demo.zip", b"x", "application/zip")}),
    ],
)
def test_neg_a3zip_001_invalid_fields_are_rejected_without_run(harness: Harness, data: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> None:
    response = harness.client.post("/api/v1/scans", data=data, files=files)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_archive"
    assert harness.registry.list_runs().items == ()
    _assert_clean(harness)


def test_neg_a3zip_001_duplicate_fields_are_rejected_without_run(harness: Harness) -> None:
    response = harness.client.post(
        "/api/v1/scans",
        files=[
            ("source_type", (None, "zip")),
            ("source_type", (None, "zip")),
            ("file", ("demo.zip", _archive(), "application/zip")),
        ],
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_archive"
    assert harness.registry.list_runs().items == ()
    _assert_clean(harness)


@pytest.mark.parametrize(
    "filename,media_type",
    [
        ("../demo.zip", "application/zip"),
        ("demo.txt", "application/zip"),
        ("demo.zip", "text/plain"),
        (" bad.zip", "application/zip"),
        ("bad\nname.zip", "application/zip"),
    ],
)
def test_neg_a3zip_002_invalid_filename_or_media_type_is_rejected_and_cleaned(harness: Harness, filename: str, media_type: str) -> None:
    response = _post(harness, _archive(), filename=filename, media_type=media_type)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_archive"
    assert harness.registry.list_runs().items == ()
    _assert_clean(harness)


def test_neg_a3zip_003_empty_and_just_over_limit_are_rejected_and_cleaned(harness: Harness) -> None:
    empty = _post(harness, b"")
    assert empty.status_code == 422
    assert empty.json()["error"]["details"] == {"reason": "archive_empty"}
    harness.runtime._upload_max_bytes = 8
    too_large = _post(harness, b"123456789")
    assert too_large.status_code == 413
    assert too_large.json()["error"]["code"] == "archive_limit_exceeded"
    assert harness.registry.list_runs().items == ()
    _assert_clean(harness)


def test_neg_a3zip_003_multipart_body_is_bounded_before_form_spooling(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_main, "MULTIPART_REQUEST_MAX_BYTES", 128)
    response = _post(harness, _archive())
    assert response.status_code == 413
    assert response.json()["error"] == {
        "code": "archive_limit_exceeded",
        "message": "ZIP upload exceeds the configured limit.",
        "request_id": response.headers["x-request-id"],
        "details": {"reason": "archive_upload_size_limit"},
    }
    assert harness.registry.list_runs().items == ()
    _assert_clean(harness)


def test_neg_a3zip_005_bad_zip_is_durable_failed_and_all_staging_is_removed(harness: Harness) -> None:
    response = _post(harness, b"not-a-zip")
    assert response.status_code == 202
    stored = harness.registry.get(response.json()["scan_id"])
    assert stored.run.status is ScanStatus.FAILED
    assert stored.run.stage.value == "ingestion"
    assert [(error.code, error.message) for error in stored.run.errors] == [
        ("zip_ingestion_failed", "Local ZIP ingestion failed."),
    ]
    assert "/" not in stored.run.errors[0].message
    _assert_clean(harness)


def test_neg_a3zip_006_unconfigured_runtime_rejects_zip_but_keeps_git_json(tmp_path: Path) -> None:
    os.chmod(tmp_path, 0o700)
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    try:
        with TestClient(create_app(registry), raise_server_exceptions=False) as client:
            unavailable = client.post(
                "/api/v1/scans",
                data={"source_type": "zip"},
                files={"file": ("demo.zip", _archive(), "application/zip")},
            )
            assert unavailable.status_code == 500
            assert unavailable.json()["error"]["details"] == {"reason": "zip_runtime_unavailable"}
            git = client.post(
                "/api/v1/scans",
                json={"source_type": "git", "source": "https://github.com/example/demo"},
            )
            assert git.status_code == 202
    finally:
        registry.close()


def test_pos_a3zip_003_openapi_keeps_exactly_six_paths_and_documents_one_post(harness: Harness) -> None:
    schema = harness.client.get("/openapi.json").json()
    assert len(schema["paths"]) == 6
    assert set(schema["paths"]["/api/v1/scans"]) == {"post"}
    content = schema["paths"]["/api/v1/scans"]["post"]["requestBody"]["content"]
    assert set(content) == {"application/json", "multipart/form-data"}
    assert content["application/json"]["schema"]["properties"]["source_type"]["const"] == "git"
    assert content["multipart/form-data"]["schema"]["properties"]["source_type"]["const"] == "zip"


def test_pos_a3zip_004_default_factory_creates_private_runtime_directories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENGUARD_DATA_DIR", raising=False)
    app = create_default_app()
    with TestClient(app) as client:
        assert client.get("/openapi.json").status_code == 200
    for path in (tmp_path / "data", tmp_path / "data" / "uploads", tmp_path / "data" / "workspaces"):
        assert path.stat().st_mode & 0o777 == 0o700
