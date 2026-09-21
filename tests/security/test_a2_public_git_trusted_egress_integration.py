"""Opt-in real HTTPS/TLS evidence for the A2-3a public Git vertical slice."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import create_default_app


PUBLIC_GIT_URL = os.environ.get("OPENGUARD_PUBLIC_GIT_TEST_URL")


@pytest.mark.skipif(
    not PUBLIC_GIT_URL or os.environ.get("OPENGUARD_RUN_LOOPBACK_TESTS") != "1",
    reason="requires an explicitly approved public repository and controlled loopback/network access",
)
def test_real_public_git_flows_through_trusted_egress_to_partial_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    os.chmod(tmp_path, 0o700)
    data = tmp_path / "runtime"
    data.mkdir(mode=0o700)
    monkeypatch.setenv("OPENGUARD_DATA_DIR", str(data))
    monkeypatch.setenv("OPENGUARD_ENABLE_PUBLIC_GIT", "1")
    app = create_default_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/scans",
            json={"source_type": "git", "source": PUBLIC_GIT_URL, "idempotency_key": "real-public-git-a2-3a"},
        )
        assert response.status_code == 202
        scan_id = response.json()["scan_id"]
        status = client.get(f"/api/v1/scans/{scan_id}")
        assert status.status_code == 200
        payload = status.json()
        assert (payload["status"], payload["stage"], payload["progress"]) == ("partial", "rules", 70)
        assert payload["summary"]["component_count"] > 0
        assert payload["summary"]["evidence_count"] > 0
        assert [error["code"] for error in payload["errors"]][-1] == "rules_stage_not_connected"
        stored = app.state.scan_api_service._registry.get(scan_id).run
        assert stored.project.revision is not None and len(stored.project.revision) in {40, 64}
        assert stored.project.root_digest == stored.provenance.inventory_digest
        assert {producer.name for producer in stored.provenance.tool_versions} >= {"git-client"}
        report = client.get(
            f"/api/v1/scans/{scan_id}/report",
            params={"format": "json", "download": "true"},
        )
        assert report.status_code == 200
        assert b'rules_stage_not_connected' in report.content
        assert list((data / "workspaces").iterdir()) == []
