"""A5-1c implementation tests for the B5 -> AI_ASSIST -> A6 vertical slice."""

from __future__ import annotations

import copy
import hashlib
import io
import zipfile
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import create_default_app
from app.ai import OllamaProvider
from app.domain.models import (
    ProducerRef,
    ProducerType,
    ReportFormat,
    ScanRun,
    ScanStage,
    ScanStatus,
    VerificationStatus,
)
from app.persistence import SQLiteScanRunRegistry
from app.pipeline import (
    PipelineError,
    PipelinePlan,
    ScanPipelineWorker,
    build_local_zip_dependency_plan,
    build_public_git_dependency_plan,
)
from app.pipeline.dependency_plan import DependencyPlanState, build_dependency_plan
from app.reporting import PipelineReportPublisher, ReportArtifactStore


ROOT = Path(__file__).resolve().parents[2]
SAMPLE = json.loads((ROOT / "examples" / "sample-scan-result.json").read_text())
NOW = datetime(2026, 9, 6, tzinfo=timezone.utc)


class RecordingProvider:
    mode = "local"

    def __init__(self, *, fail: bool = False) -> None:
        self.producer = ProducerRef(
            type=ProducerType.AI,
            name="a5-pipeline-test-provider",
            version="1.0.0",
            provider="local-test",
            model_id="test-model@sha256:" + "a" * 64,
            prompt_schema_digest={"algorithm": "sha256", "value": "b" * 64},
            config_digest={"algorithm": "sha256", "value": "c" * 64},
        )
        self.fail = fail
        self.calls: list[tuple[dict[str, object], float]] = []

    def generate(self, payload: str, timeout_seconds: float) -> str:
        request = json.loads(payload)
        self.calls.append((request, timeout_seconds))
        if self.fail:
            raise RuntimeError("provider-private-detail")
        finding = request["finding"]
        evidence_ids = finding["evidence_ids"]
        return json.dumps(
            {
                "schema_version": "openguard.ai-remediation/v1",
                "finding_id": finding["id"],
                "summary": "Review the pending license evidence before distribution.",
                "steps": ["Verify the cited license evidence with a human reviewer."],
                "evidence_ids": [evidence_ids[0]],
            }
        )


def _rules_input(*, verified: bool, queued: bool = False) -> ScanRun:
    value = copy.deepcopy(SAMPLE)
    value.update(
        status="queued" if queued else "running",
        stage="queued" if queued else "rules",
        progress=0 if queued else 70,
        started_at=None if queued else value["started_at"],
        finished_at=None,
    )
    value["ai_assets"] = []
    value["obligations"] = []
    value["findings"] = []
    value["remediations"] = []
    value["errors"] = []
    value["report_links"] = []
    status = "verified" if verified else "pending"
    value["licenses"][0]["verification_status"] = status
    value["evidence"][2]["verification_status"] = status
    value["summary"] = {
        "component_count": 1,
        "ai_asset_count": 0,
        "evidence_count": 3,
        "finding_counts": {
            "pass": 0,
            "warning": 0,
            "review_required": 0,
            "unknown": 0,
        },
    }
    return ScanRun.model_validate(value)


def _plan(provider: RecordingProvider | None, *, enabled: bool) -> PipelinePlan:
    return build_dependency_plan(
        lambda run: run,
        DependencyPlanState(),
        ingestion_error_code="ingestion_failed",
        ingestion_error_message="Ingestion failed.",
        ai_provider=provider,
        ai_enabled=enabled,
        ai_timeout_seconds=7.5,
    )


def _private(path: Path) -> Path:
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def test_ai_disabled_preserves_pending_b5_result_without_provider_call() -> None:
    provider = RecordingProvider()
    plan = _plan(provider, enabled=False)
    rules_result = plan.steps[4].handler(_rules_input(verified=False))

    result = plan.steps[5].handler(rules_result)

    assert result == rules_result
    assert result.provenance.ai_enabled is False
    assert result.provenance.ai_model is None
    assert provider.calls == []


def test_pending_b5_finding_is_enriched_without_rewriting_facts() -> None:
    provider = RecordingProvider()
    plan = _plan(provider, enabled=True)
    rules_result = plan.steps[4].handler(_rules_input(verified=False))
    immutable_fields = {
        name: getattr(rules_result, name)
        for name in ("components", "ai_assets", "licenses", "evidence", "obligations", "summary")
    }

    result = plan.steps[5].handler(rules_result)

    assert len(provider.calls) == 1
    assert provider.calls[0][1] == 7.5
    assert provider.calls[0][0]["finding"]["rule_id"] == "license-evidence-gate"
    assert result.provenance.ai_enabled is True
    assert result.provenance.ai_model == provider.producer
    assert len(result.remediations) == 1
    assert result.remediations[0].verification_status is VerificationStatus.PENDING
    assert result.findings[0].remediation_id == result.remediations[0].id
    assert result.remediations[0].evidence_ids == result.findings[0].evidence_ids
    for name, expected in immutable_fields.items():
        assert getattr(result, name) == expected


def test_verified_b5_remediation_is_not_duplicated_by_ai() -> None:
    provider = RecordingProvider()
    plan = _plan(provider, enabled=True)
    rules_result = plan.steps[4].handler(_rules_input(verified=True))

    result = plan.steps[5].handler(rules_result)

    assert result == rules_result
    assert len(result.remediations) == 1
    assert result.remediations[0].generated_by.type is ProducerType.RULE_ENGINE
    assert provider.calls == []


@pytest.mark.parametrize("source_type", ["zip", "git"])
def test_source_specific_plans_forward_ai_configuration(tmp_path: Path, source_type: str) -> None:
    provider = RecordingProvider()
    if source_type == "zip":
        plan = build_local_zip_dependency_plan(
            tmp_path / "project.zip",
            tmp_path / "workspace",
            clock=lambda: NOW,
            ai_provider=provider,
            ai_enabled=True,
            ai_timeout_seconds=4.0,
        )
    else:
        plan = build_public_git_dependency_plan(
            "https://github.com/example/project.git",
            tmp_path / "workspace",
            clock=lambda: NOW,
            ai_provider=provider,
            ai_enabled=True,
            ai_timeout_seconds=4.0,
        )
    rules_result = plan.steps[4].handler(_rules_input(verified=False))

    result = plan.steps[5].handler(rules_result)

    assert result.provenance.ai_model == provider.producer
    assert len(result.remediations) == 1
    assert provider.calls[0][1] == 4.0


@pytest.mark.parametrize("source_type", ["zip", "git"])
def test_production_plans_preserve_facts_and_publish_partial_reports_on_ai_failure(
    tmp_path: Path, source_type: str,
) -> None:
    """Exercise every production stage; only the Git transport and model are fixtures."""
    from app.ingestion import ZipIngestionService
    from app.ingestion.git_runner import GitRuntimeIdentity

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("package.json", '{"dependencies":{"react":"19.2.0"}}')
        archive.writestr("package-lock.json", json.dumps({"lockfileVersion": 3, "packages": {
            "": {"dependencies": {"react": "19.2.0"}},
            "node_modules/react": {"version": "19.2.0", "license": "MIT"},
        }}))
    archive_bytes = stream.getvalue()
    archive_path = tmp_path / "project.zip"
    archive_path.write_bytes(archive_bytes)
    source = archive_path.name if source_type == "zip" else "https://github.com/example/project.git"

    class GitFixture:
        def __init__(self, root: Path) -> None:
            self.service = ZipIngestionService(root)

        def ingest_with_consumer(self, actual_source, consumer, *, read_limits):
            assert actual_source == source
            result = self.service.ingest_with_consumer(
                io.BytesIO(archive_bytes), consumer, read_limits=read_limits,
            )
            return SimpleNamespace(inventory=result.inventory, consumer_result=result.consumer_result,
                revision="a" * 40, runtime_identity=GitRuntimeIdentity("2.50.1", "b" * 64),
                egress_evidence=(object(),))

        def close(self) -> None:
            self.service.close()

    value = _rules_input(verified=False, queued=True).model_dump(mode="json")
    for field in ("components", "ai_assets", "licenses", "evidence", "obligations", "findings",
                  "remediations", "errors", "report_links"):
        value[field] = []
    value["summary"].update(component_count=0, ai_asset_count=0, evidence_count=0)
    value["project"].update(source_type=source_type, source=source, root_digest=None, revision=None)
    value["provenance"].update(inventory_digest=None, tool_versions=[], ai_enabled=False, ai_model=None,
        input_digest={"algorithm": "sha256", "value": hashlib.sha256(
            archive_bytes if source_type == "zip" else source.encode()).hexdigest()})
    queued = ScanRun.model_validate(value)
    results = []
    for failing in (False, True):
        root = _private(tmp_path / ("failure" if failing else "baseline"))
        registry = SQLiteScanRunRegistry(root / "runs.sqlite")
        try:
            registry.create(queued)
            provider = RecordingProvider(fail=failing)
            store = ReportArtifactStore(_private(root / "reports"), clock=lambda: NOW)
            options = dict(clock=lambda: NOW, ai_enabled=True, ai_provider=provider)
            if source_type == "zip":
                plan = build_local_zip_dependency_plan(archive_path, _private(root / "workspace"), **options)
            else:
                plan = build_public_git_dependency_plan(source, _private(root / "workspace"),
                    ingestion_factory=GitFixture, **options)
            run = ScanPipelineWorker(registry, clock=lambda: NOW,
                terminal_publisher=PipelineReportPublisher(store).publish).run(queued.id, plan).run
            results.append(run)
            assert provider.calls and run.findings
            assert len(run.report_links) == 4
            for format_ in ReportFormat:
                artifact = store.get(run.id, format_)
                assert artifact.content
            report = json.loads(store.get(run.id, ReportFormat.JSON).content)["scan_run"]
            if failing:
                assert (run.status, run.stage, run.progress) == (ScanStatus.PARTIAL, ScanStage.REPORT, 95)
                assert {error.code for error in run.errors} == {"ai_provider_unavailable", "scan_incomplete"}
                assert not run.remediations and all(f.remediation_id is None for f in run.findings)
                assert report["status"] == "partial"
                assert {e["code"] for e in report["errors"]} == {"ai_provider_unavailable", "scan_incomplete"}
                assert "provider-private-detail" not in json.dumps(report)
            else:
                assert run.status is ScanStatus.COMPLETED and not run.errors
                assert run.remediations
        finally:
            registry.close()
    baseline, failed = results
    for field in ("project", "components", "ai_assets", "licenses", "evidence", "obligations", "summary"):
        assert getattr(failed, field) == getattr(baseline, field)
    assert [f.model_dump(exclude={"remediation_id"}) for f in failed.findings] == [
        f.model_dump(exclude={"remediation_id"}) for f in baseline.findings]


def test_enabled_ai_requires_a_provider_and_valid_timeout() -> None:
    with pytest.raises(PipelineError, match="pipeline_invalid_argument"):
        _plan(None, enabled=True)
    with pytest.raises(PipelineError, match="pipeline_invalid_argument"):
        build_dependency_plan(
            lambda run: run,
            DependencyPlanState(),
            ingestion_error_code="ingestion_failed",
            ingestion_error_message="Ingestion failed.",
            ai_timeout_seconds=float("nan"),
        )


def test_default_app_uses_explicit_ai_toggle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = _private(tmp_path / "runtime")
    monkeypatch.setenv("OPENGUARD_DATA_DIR", str(data))
    monkeypatch.setenv("OPENGUARD_ENABLE_AI", "1")
    with TestClient(create_default_app()) as client:
        assert client.app.state.zip_scan_runtime._ai_enabled is True
        assert client.app.state.zip_scan_runtime._ai_provider.producer.name == "ollama"


def test_default_app_rejects_ambiguous_ai_toggle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = _private(tmp_path / "runtime")
    monkeypatch.setenv("OPENGUARD_DATA_DIR", str(data))
    monkeypatch.setenv("OPENGUARD_ENABLE_AI", "true")
    with pytest.raises(RuntimeError, match="invalid OPENGUARD_ENABLE_AI"):
        create_default_app()


def test_default_app_selects_fixed_docker_ollama(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENGUARD_DATA_DIR", str(_private(tmp_path / "runtime")))
    monkeypatch.setenv("OPENGUARD_ENABLE_AI", "1")
    monkeypatch.setenv("OPENGUARD_OLLAMA_DOCKER_HOST", "1")
    with TestClient(create_default_app()) as client:
        provider = client.app.state.zip_scan_runtime._ai_provider
        assert provider._origin == "http://host.docker.internal:11434"
        assert provider.producer.model_id == OllamaProvider().producer.model_id


def test_default_app_rejects_ambiguous_docker_ollama(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENGUARD_DATA_DIR", str(_private(tmp_path / "runtime")))
    monkeypatch.setenv("OPENGUARD_OLLAMA_DOCKER_HOST", "true")
    with pytest.raises(RuntimeError, match="invalid OPENGUARD_OLLAMA_DOCKER_HOST"):
        create_default_app()
