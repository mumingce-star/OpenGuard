"""Independent A3-2 verification for ZIP multipart background scanning.

The tests construct their own multipart payloads, ZIP bytes and assertions.
They do not import implementation-side test helpers or expected fixtures.
"""

from __future__ import annotations

import http.client
import json
import os
import socket
import stat
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

import app.api.main as api_main
from app.api import create_app, create_default_app
from app.api.zip_scan import ZipScanRuntime
from app.domain.models import ScanStage, ScanStatus
from app.persistence import SQLiteScanRunRegistry


@dataclass
class ApiHarness:
    client: TestClient
    registry: SQLiteScanRunRegistry
    upload_root: Path
    workspace_root: Path
    runtime: ZipScanRuntime


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[ApiHarness]:
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
        yield ApiHarness(client, registry, upload_root, workspace_root, runtime)
    registry.close()


def _zip_bytes(
    *,
    requirements: str = "requests==2.32.5\n",
    package_json: str = '{"name":"independent-demo","dependencies":{"react":"18.2.0"}}',
) -> bytes:
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if requirements is not None:
            archive.writestr("requirements.txt", requirements)
        if package_json is not None:
            archive.writestr("package.json", package_json)
    return stream.getvalue()


def _post_zip(
    harness: ApiHarness,
    content: bytes,
    *,
    key: str | None = None,
    filename: str = "independent-demo.zip",
    media_type: str = "application/zip",
):
    fields: dict[str, str] = {"source_type": "zip"}
    if key is not None:
        fields["idempotency_key"] = key
    return harness.client.post(
        "/api/v1/scans",
        data=fields,
        files={"file": (filename, content, media_type)},
    )


def _assert_clean(harness: ApiHarness) -> None:
    assert list(harness.upload_root.iterdir()) == []
    assert list(harness.workspace_root.iterdir()) == []


def test_pos_a3zip_001_real_multipart_reaches_terminal_partial_and_resources(harness: ApiHarness) -> None:
    response = _post_zip(harness, _zip_bytes())
    assert response.status_code == 202
    accepted = response.json()
    assert accepted["status"] == "queued"
    assert accepted["status_url"] == f"/api/v1/scans/{accepted['scan_id']}"

    status_response = harness.client.get(accepted["status_url"])
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert (status_payload["status"], status_payload["stage"], status_payload["progress"]) == (
        "partial",
        "rules",
        70,
    )
    assert status_payload["summary"] == {
        "component_count": 2,
        "ai_asset_count": 0,
        "evidence_count": 2,
        "finding_counts": {"pass": 0, "warning": 0, "review_required": 0, "unknown": 0},
    }
    assert [error["code"] for error in status_payload["errors"]] == ["rules_stage_not_connected"]

    resources = harness.client.get(f"/api/v1/scans/{accepted['scan_id']}/resources")
    assert resources.status_code == 200
    resource_payload = resources.json()
    assert {(item["resource"]["ecosystem"], item["resource"]["name"]) for item in resource_payload["items"]} == {
        ("npm", "react"),
        ("pypi", "requests"),
    }
    evidence_id = resource_payload["items"][0]["resource"]["evidence_ids"][0]
    evidence = harness.client.get(f"/api/v1/scans/{accepted['scan_id']}/evidence/{evidence_id}")
    assert evidence.status_code == 200
    assert evidence.json()["id"] == evidence_id
    _assert_clean(harness)


def test_pos_a3zip_002_same_key_and_bytes_return_one_persisted_scan(harness: ApiHarness) -> None:
    content = _zip_bytes()
    first = _post_zip(harness, content, key="independent-same-001")
    second = _post_zip(harness, content, key="independent-same-001")

    assert first.status_code == second.status_code == 202
    assert first.json()["scan_id"] == second.json()["scan_id"]
    assert second.json()["status"] == "partial"
    assert len(harness.registry.list_runs().items) == 1
    stored = harness.registry.get(first.json()["scan_id"])
    assert stored.run.status is ScanStatus.PARTIAL
    assert stored.run.stage is ScanStage.RULES
    _assert_clean(harness)


def test_pos_a3zip_003_git_json_create_and_readiness_behavior_remain_compatible(harness: ApiHarness) -> None:
    payload = {
        "source_type": "git",
        "source": "https://github.com/example/openguard-a3-2",
        "idempotency_key": "independent-git-001",
    }
    first = harness.client.post("/api/v1/scans", json=payload)
    second = harness.client.post("/api/v1/scans", json=payload)
    assert first.status_code == second.status_code == 202
    scan_id = first.json()["scan_id"]
    assert second.json()["scan_id"] == scan_id
    assert first.json()["status"] == second.json()["status"] == "queued"

    status_response = harness.client.get(f"/api/v1/scans/{scan_id}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "queued"
    resources = harness.client.get(f"/api/v1/scans/{scan_id}/resources")
    assert resources.status_code == 409
    assert resources.json()["error"]["code"] == "scan_not_ready"
    risks = harness.client.get(f"/api/v1/scans/{scan_id}/risks")
    assert risks.status_code == 409
    assert risks.json()["error"]["code"] == "scan_not_ready"
    assert len(harness.registry.list_runs().items) == 1


def test_pos_a3zip_004_openapi_has_six_paths_and_default_runtime_is_private(harness: ApiHarness) -> None:
    schema = harness.client.get("/openapi.json").json()
    assert set(schema["paths"]) == {
        "/api/v1/scans",
        "/api/v1/scans/{scan_id}",
        "/api/v1/scans/{scan_id}/resources",
        "/api/v1/scans/{scan_id}/risks",
        "/api/v1/scans/{scan_id}/evidence/{evidence_id}",
        "/api/v1/scans/{scan_id}/report",
    }
    assert len(schema["paths"]) == 6
    request_content = schema["paths"]["/api/v1/scans"]["post"]["requestBody"]["content"]
    assert set(request_content) == {"application/json", "multipart/form-data"}
    assert request_content["application/json"]["schema"]["properties"]["source_type"]["const"] == "git"
    assert request_content["multipart/form-data"]["schema"]["properties"]["source_type"]["const"] == "zip"


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
def test_neg_a3zip_001_missing_unknown_wrong_or_empty_fields_are_rejected(
    harness: ApiHarness,
    data: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
) -> None:
    response = harness.client.post("/api/v1/scans", data=data, files=files)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_archive"
    assert harness.registry.list_runs().items == ()
    _assert_clean(harness)


def test_neg_a3zip_001_duplicate_fields_are_rejected_without_creating_a_run(harness: ApiHarness) -> None:
    response = harness.client.post(
        "/api/v1/scans",
        files=[
            ("source_type", (None, "zip")),
            ("source_type", (None, "zip")),
            ("file", ("demo.zip", _zip_bytes(), "application/zip")),
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
        ("demo%2Fescape.zip", "application/zip"),
        ("demo.txt", "application/zip"),
        ("demo.zip", "text/plain"),
        ("bad\nname.zip", "application/zip"),
        (" demo.zip", "application/zip"),
    ],
)
def test_neg_a3zip_002_percent_encoded_path_control_and_media_boundaries_are_clean(
    harness: ApiHarness,
    filename: str,
    media_type: str,
) -> None:
    response = _post_zip(harness, _zip_bytes(), filename=filename, media_type=media_type)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_archive"
    assert str(harness.upload_root) not in response.text
    assert harness.registry.list_runs().items == ()
    _assert_clean(harness)


def test_neg_a3zip_003_empty_stream_upload_limit_and_request_limit_are_stable(
    harness: ApiHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty = _post_zip(harness, b"")
    assert empty.status_code == 422
    assert empty.json()["error"]["details"] == {"reason": "archive_empty"}
    assert harness.registry.list_runs().items == ()
    _assert_clean(harness)

    harness.runtime._upload_max_bytes = 8
    too_large = _post_zip(harness, b"123456789")
    assert too_large.status_code == 413
    assert too_large.json()["error"] == {
        "code": "archive_limit_exceeded",
        "message": "ZIP upload exceeds the configured limit.",
        "request_id": too_large.headers["x-request-id"],
        "details": {"reason": "archive_upload_size_limit"},
    }
    assert harness.registry.list_runs().items == ()
    _assert_clean(harness)

    monkeypatch.setattr(api_main, "MULTIPART_REQUEST_MAX_BYTES", 128)
    body_limit = _post_zip(harness, _zip_bytes())
    assert body_limit.status_code == 413
    assert body_limit.json()["error"]["details"] == {"reason": "archive_upload_size_limit"}
    assert harness.registry.list_runs().items == ()
    _assert_clean(harness)


def test_neg_a3zip_004_same_key_different_bytes_is_a_sanitized_conflict(harness: ApiHarness) -> None:
    first = _post_zip(harness, _zip_bytes(), key="independent-conflict-001")
    conflict = _post_zip(
        harness,
        _zip_bytes(requirements="httpx==0.28.1\n"),
        key="independent-conflict-001",
    )
    assert first.status_code == 202
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "invalid_source"
    assert conflict.json()["error"]["details"] == {"reason": "idempotency_conflict"}
    assert len(harness.registry.list_runs().items) == 1
    assert str(harness.upload_root) not in conflict.text
    _assert_clean(harness)


def test_neg_a3zip_005_bad_zip_becomes_durable_failed_without_raw_details(harness: ApiHarness) -> None:
    response = _post_zip(harness, b"not a zip archive")
    assert response.status_code == 202
    accepted = response.json()
    stored = harness.registry.get(accepted["scan_id"])
    assert stored.run.status is ScanStatus.FAILED
    assert stored.run.stage is ScanStage.INGESTION
    assert [(error.code, error.message) for error in stored.run.errors] == [
        ("zip_ingestion_failed", "Local ZIP ingestion failed."),
    ]
    serialized = stored.run.model_dump_json()
    assert str(harness.upload_root) not in serialized
    assert "not a zip archive" not in serialized
    assert "/" not in stored.run.errors[0].message
    _assert_clean(harness)


def test_neg_a3zip_006_unconfigured_zip_runtime_rejects_zip_but_preserves_git_json(tmp_path: Path) -> None:
    os.chmod(tmp_path, 0o700)
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    try:
        with TestClient(create_app(registry), raise_server_exceptions=False) as client:
            unavailable = client.post(
                "/api/v1/scans",
                data={"source_type": "zip"},
                files={"file": ("demo.zip", _zip_bytes(), "application/zip")},
            )
            assert unavailable.status_code == 500
            assert unavailable.json()["error"]["code"] == "internal_error"
            assert unavailable.json()["error"]["details"] == {"reason": "zip_runtime_unavailable"}

            git = client.post(
                "/api/v1/scans",
                json={"source_type": "git", "source": "https://github.com/example/openguard-a3-2"},
            )
            assert git.status_code == 202
            assert git.json()["status"] == "queued"
    finally:
        registry.close()


def _multipart_body(content: bytes, *, filename: str = "uvicorn-demo.zip") -> tuple[bytes, str]:
    boundary = "----OpenGuardIndependentA3ZipBoundary"
    marker = boundary.encode("ascii")
    body = bytearray()
    for name, value in (("source_type", "zip"), ("idempotency_key", "uvicorn-independent-001")):
        body.extend(b"--" + marker + b"\r\n")
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii"))
        body.extend(value.encode("ascii") + b"\r\n")
    body.extend(b"--" + marker + b"\r\n")
    body.extend(
        (
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: application/zip\r\n\r\n"
        ).encode("ascii")
    )
    body.extend(content + b"\r\n")
    body.extend(b"--" + marker + b"--\r\n")
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_for_server(process: subprocess.Popen[bytes], port: int) -> None:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"uvicorn exited before listening: {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise AssertionError("uvicorn did not listen on loopback")


def _http_json(port: int, method: str, path: str, *, body: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[int, dict[str, object]]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=4)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        return response.status, payload
    finally:
        connection.close()


def test_pos_a3zip_004_real_uvicorn_zip_reaches_terminal_resources_and_restart_persistence(tmp_path: Path) -> None:
    os.chmod(tmp_path, 0o700)
    data_dir = tmp_path / "uvicorn-data"
    port = _free_loopback_port()
    project_root = Path(__file__).resolve().parents[2]
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
    scan_id: str | None = None
    try:
        _wait_for_server(process, port)
        content, content_type = _multipart_body(_zip_bytes())
        status_code, accepted = _http_json(
            port,
            "POST",
            "/api/v1/scans",
            body=content,
            headers={
                "Accept": "application/json",
                "Content-Type": content_type,
                "Content-Length": str(len(content)),
            },
        )
        assert status_code == 202
        assert accepted["status"] == "queued"
        scan_id = str(accepted["scan_id"])
        assert accepted["status_url"] == f"/api/v1/scans/{scan_id}"

        terminal: dict[str, object] | None = None
        for _ in range(160):
            status_code, payload = _http_json(port, "GET", str(accepted["status_url"]))
            assert status_code == 200
            if payload["status"] in {"partial", "failed", "completed"}:
                terminal = payload
                break
            time.sleep(0.05)
        assert terminal is not None
        assert (terminal["status"], terminal["stage"], terminal["progress"]) == ("partial", "rules", 70)

        resource_status, resources = _http_json(port, "GET", f"/api/v1/scans/{scan_id}/resources")
        assert resource_status == 200
        assert {(item["resource"]["ecosystem"], item["resource"]["name"]) for item in resources["items"]} == {
            ("npm", "react"),
            ("pypi", "requests"),
        }
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    assert scan_id is not None
    database = data_dir / "scans.db"
    assert stat.S_IMODE(data_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(database.stat().st_mode) == 0o600
    registry = SQLiteScanRunRegistry(database)
    try:
        persisted = registry.get(scan_id)
        assert persisted.run.status is ScanStatus.PARTIAL
        assert persisted.run.stage is ScanStage.RULES
        assert {(item.ecosystem, item.name) for item in persisted.run.components} == {
            ("npm", "react"),
            ("pypi", "requests"),
        }
    finally:
        registry.close()
    assert list((data_dir / "uploads").iterdir()) == []
    assert list((data_dir / "workspaces").iterdir()) == []


def test_pos_a3zip_004_default_factory_creates_private_runtime_directories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENGUARD_DATA_DIR", raising=False)
    app = create_default_app()
    with TestClient(app) as client:
        assert client.get("/openapi.json").status_code == 200
    for path in (
        tmp_path / "data",
        tmp_path / "data" / "uploads",
        tmp_path / "data" / "workspaces",
    ):
        assert stat.S_IMODE(path.stat().st_mode) == 0o700
    assert stat.S_IMODE((tmp_path / "data" / "scans.db").stat().st_mode) == 0o600
