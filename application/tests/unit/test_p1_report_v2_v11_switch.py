"""Explicit process configuration for new 1.1 writes in TEST_ONLY apps."""

import logging

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_default_app, report_v2_v11_writes_from_environment


WRITES_ENV = "OPENGUARD_ENABLE_REPORT_V2_1_1_WRITES"


@pytest.mark.parametrize("value, expected, warning", [
    (None, False, False),
    ("0", False, False),
    ("1", True, False),
    ("", False, True),
    (" 1", False, True),
    ("01", False, True),
    ("true", False, True),
    ("test-only-marker-must-not-be-logged", False, True),
])
def test_new_report_write_switch_uses_only_exact_values(value, expected, warning, monkeypatch, caplog):
    if value is None:
        monkeypatch.delenv(WRITES_ENV, raising=False)
    else:
        monkeypatch.setenv(WRITES_ENV, value)
    with caplog.at_level(logging.WARNING, logger="app.api.main"):
        assert report_v2_v11_writes_from_environment() is expected
    assert len(caplog.records) == int(warning)
    if warning:
        assert caplog.records[0].getMessage() == f"{WRITES_ENV} is invalid; new Report V2 1.1 writes are disabled"


def test_config_is_captured_at_app_composition(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENGUARD_ENABLE_ASSESSMENTS", "1")
    monkeypatch.setenv(WRITES_ENV, "1")
    frozen_setting = report_v2_v11_writes_from_environment()
    monkeypatch.setenv(WRITES_ENV, "0")
    with TestClient(create_default_app(data_dir=tmp_path / "tenant", report_v2_v11_writes=frozen_setting)) as tenant:
        assert tenant.app.state.report_v2_service.enable_v11_writes is True
    with TestClient(create_default_app(data_dir=tmp_path / "default")) as default:
        assert default.app.state.report_v2_service.enable_v11_writes is False


def test_write_setting_does_not_enable_disabled_assessments(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENGUARD_ENABLE_ASSESSMENTS", "0")
    monkeypatch.setenv(WRITES_ENV, "1")
    with TestClient(create_default_app(data_dir=tmp_path / "tenant")) as client:
        assert client.app.state.assessment_service is None
        assert client.app.state.report_v2_service is None
        response = client.post("/api/v1/scans/scan/assessments/assessment/report-v2", json={
            "idempotency_key": "new", "schema_version": "1.1",
        })
        assert response.status_code == 503
        assert response.json()["error"]["details"]["reason"] == "report_v2_not_configured"
    assert not (tmp_path / "tenant" / "report_v2.db").exists()
