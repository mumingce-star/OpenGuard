import copy
import json
from pathlib import Path

import pytest

from app.ai.runtime_probe import main, run_probe
from app.domain.models import ProducerRef, ProducerType, ScanRun

ROOT = Path(__file__).resolve().parents[2]


class FakeProvider:
    mode = "local"
    producer = ProducerRef(type=ProducerType.AI, name="fake", version="1", provider="fake", model_id="fake@sha256:" + "a" * 64, prompt_schema_digest={"algorithm": "sha256", "value": "b" * 64})
    def generate(self, payload, timeout_seconds):
        finding = json.loads(payload)["finding"]
        return json.dumps(
            {
                "schema_version": "openguard.ai-remediation/v1",
                "finding_id": finding["id"],
                "summary": "Review evidence.",
                "steps": ["Verify evidence."],
                "evidence_ids": [finding["evidence_ids"][0]],
            }
        )


def _input(tmp_path: Path) -> Path:
    value = copy.deepcopy(
        json.loads((ROOT / "examples/sample-scan-result.json").read_text())
    )
    value["findings"][0]["remediation_id"] = None
    value["remediations"] = []
    path = tmp_path / "run.json"
    path.write_text(json.dumps(value))
    return path


def test_probe_rejects_invalid_arguments(tmp_path):
    with pytest.raises(ValueError):
        run_probe(tmp_path / "missing.json", 0, FakeProvider())

    with pytest.raises(ValueError):
        run_probe(_input(tmp_path), 1, FakeProvider(), timeout_seconds=float("nan"))


def test_probe_uses_stable_aggregate_output(tmp_path):
    outcome = run_probe(
        _input(tmp_path),
        2,
        FakeProvider(),
        clock=iter([0, 0.1, 1, 1.2]).__next__,
        timeout_seconds=12,
    )

    assert outcome["schema_version"] == "openguard.ai-runtime-probe/v1"
    assert outcome["runs"] == outcome["successes"] == 2
    assert outcome["success_rate"] == "2/2"
    assert outcome["eligible_findings"] == 1
    assert outcome["latency_ms"] == {
        "cold": 100.0,
        "hot": [200.0],
        "min": 100.0,
        "median": 150.0,
        "max": 200.0,
    }
    assert all(outcome["validations"].values())


def test_probe_handles_multiple_findings_without_single_id_assumption(tmp_path):
    path = _input(tmp_path)
    value = json.loads(path.read_text())
    second = copy.deepcopy(value["findings"][0])
    second["id"] = "rsk_223e4567-e89b-12d3-a456-426614174000"
    second["title"] = "Second review"
    value["findings"].append(second)
    value["summary"]["finding_counts"]["review_required"] = 2
    path.write_text(json.dumps(value))

    outcome = run_probe(
        path,
        2,
        FakeProvider(),
        clock=iter([0, 0.1, 1, 1.1]).__next__,
    )

    assert outcome["successes"] == 2
    assert outcome["eligible_findings"] == 2
    assert outcome["validations"]["stable_identity"] is True


class FailingProvider(FakeProvider):
    def generate(self, payload, timeout_seconds):
        raise RuntimeError("token=secret /private/path")


def test_provider_failure_is_aggregate_only(tmp_path):
    outcome = run_probe(
        _input(tmp_path),
        1,
        FailingProvider(),
        clock=iter([0, 0.1]).__next__,
    )

    assert outcome["success_rate"] == "0/1"
    assert not any(outcome["validations"].values())
    assert "secret" not in json.dumps(outcome)
    assert "/private" not in json.dumps(outcome)


def test_main_sanitizes_invalid_path(capsys):
    assert main(["/private/secret/not-found.json"]) == 2
    assert capsys.readouterr().out == '{"error":"ai_runtime_probe_failed"}\n'
