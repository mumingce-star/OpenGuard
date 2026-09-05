"""Independent dynamic ZIP verification for A4 static AI asset aggregation."""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

import app.pipeline.ai_assets as ai_assets_pipeline
from app.domain.models import (
    FindingOutcome,
    HashValue,
    Project,
    RunEnvironment,
    RunProvenance,
    ScanRun,
    ScanStage,
    ScanStatus,
    ScanSummary,
    SourceType,
)
from app.persistence import SQLiteScanRunRegistry
from app.pipeline import ScanPipelineWorker, build_local_zip_dependency_plan
from app.reporting import PipelineReportPublisher, ReportArtifactStore
from app.domain.models import ReportFormat


NOW = datetime(2026, 9, 5, 8, 0, tzinfo=timezone.utc)
MODEL = "https://huggingface.co/Qwen/Qwen3-0.6B"
DATASET = "https://huggingface.co/datasets/example/research"


def _zip(tmp_path: Path, files: dict[str, str | bytes]) -> Path:
    path = tmp_path / "independent-assets.zip"
    # Stored entries isolate AI read limits from A2 decompression-ratio limits.
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return path


def _queued(archive: Path, number: int = 1) -> ScanRun:
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    created = NOW
    return ScanRun(
        contract_version="0.1.1", id=f"scn_123e4567-e89b-12d3-a456-{number:012x}",
        status=ScanStatus.QUEUED, stage=ScanStage.QUEUED, progress=0,
        project=Project(id=f"prj_123e4567-e89b-12d3-a456-{number:012x}",
                        name="independent-ai-assets", source_type=SourceType.ZIP,
                        source=archive.name, created_at=created),
        summary=ScanSummary(component_count=0, ai_asset_count=0, evidence_count=0,
                            finding_counts={item: 0 for item in FindingOutcome}),
        provenance=RunProvenance(
            input_digest=HashValue(algorithm="sha256", value=digest),
            ruleset_version="independent-a4-ai-assets", contract_version="0.1.1",
            ai_enabled=False, run_environment=RunEnvironment(
                python_version="independent", platform="independent", openguard_version="independent")),
        created_at=created,
    )


def _run(tmp_path: Path, files: dict[str, str | bytes], number: int = 1, *, publisher: bool = False):
    archive = _zip(tmp_path, files)
    queued = _queued(archive, number)
    registry = SQLiteScanRunRegistry(tmp_path / "runs.sqlite")
    registry.create(queued)
    workspace = tmp_path / "materialized"
    workspace.mkdir(mode=0o700)
    if publisher:
        report_root = tmp_path / "reports"
        report_root.mkdir(mode=0o700)
        store = ReportArtifactStore(report_root, clock=lambda: NOW)
    else:
        store = None
    plan = build_local_zip_dependency_plan(archive, workspace, clock=lambda: NOW)
    if store:
        result = ScanPipelineWorker(registry, clock=lambda: NOW,
                                    terminal_publisher=PipelineReportPublisher(store).publish).run(queued.id, plan)
    else:
        result = ScanPipelineWorker(registry, clock=lambda: NOW).run(queued.id, plan)
    return archive, registry, result.run, workspace, store


def test_dynamic_zip_qwen_asset_is_pending_and_reported_with_full_file_hash(tmp_path: Path):
    text = f"README reference: {MODEL}\nsecret='nearby-private-value'\n"
    archive, registry, run, workspace, store = _run(tmp_path, {"README.md": text}, 1, publisher=True)
    try:
        assert run.status is ScanStatus.COMPLETED
        assert not run.components
        assert len(run.ai_assets) == 1
        asset = run.ai_assets[0]
        assert (asset.name, asset.source_url, asset.authorization_status.value) == (
            "Qwen/Qwen3-0.6B", MODEL, "pending")
        evidence = next(item for item in run.evidence if item.id in asset.evidence_ids)
        assert evidence.content_hash.value == hashlib.sha256(text.encode()).hexdigest()
        assert evidence.excerpt == MODEL
        assert "nearby-private-value" not in evidence.model_dump_json()
        assert run.licenses[0].expression == "NOASSERTION"
        assert [link.format for link in run.report_links] == list(ReportFormat)
        saved = {fmt: store.get(run.id, fmt).content for fmt in ReportFormat}
        assert all(hashlib.sha256(content).hexdigest() == link.content_hash.value
                   for fmt, link in ((link.format, link) for link in run.report_links)
                   for content in [saved[fmt]])
        report = json.loads(saved[ReportFormat.JSON])
        assert "Qwen/Qwen3-0.6B" in json.dumps(report, ensure_ascii=False)
        assert not list(workspace.iterdir())
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == run.provenance.input_digest.value
    finally:
        registry.close()


def test_mixed_npm_license_and_root_license_do_not_attach_to_ai_asset(tmp_path: Path):
    files = {
        "README.md": MODEL,
        "package.json": json.dumps({"dependencies": {"is-number": "7.0.0"}}),
        "package-lock.json": json.dumps({"lockfileVersion": 3, "packages": {
            "": {"license": "GPL-3.0-only", "dependencies": {"is-number": "7.0.0"}},
            "node_modules/is-number": {"version": "7.0.0", "license": "MIT"},
        }}),
    }
    _, registry, run, workspace, _ = _run(tmp_path, files, 2)
    try:
        assert run.status is ScanStatus.COMPLETED
        component = next(item for item in run.components if item.name == "is-number")
        asset = run.ai_assets[0]
        licenses = {item.id: item.expression for item in run.licenses}
        assert licenses[component.license_expression_id] == "MIT"
        assert licenses[asset.license_expression_id] == "NOASSERTION"
        assert not list(workspace.iterdir())
    finally:
        registry.close()


def test_dataset_is_dataset_only_and_duplicate_same_line_evidence_is_deduplicated(tmp_path: Path):
    text = f"{DATASET} {DATASET}\n{DATASET}\n"
    _, registry, run, _, _ = _run(tmp_path, {"README.md": text}, 3)
    try:
        assert run.status is ScanStatus.COMPLETED
        assert len(run.ai_assets) == 1
        assert run.ai_assets[0].asset_type.value == "dataset"
        assert len(run.ai_assets[0].evidence_ids) == 2
        assert {item.start_line for item in run.evidence} == {1, 2}
    finally:
        registry.close()


def test_invalid_utf8_keeps_existing_facts_partial_and_cleanup(tmp_path: Path):
    files = {"requirements.txt": "requests==2.32.5\n", "model.py": b"# invalid utf8 \xff"}
    _, registry, run, workspace, _ = _run(tmp_path, files, 10)
    try:
        assert run.status is ScanStatus.PARTIAL
        assert run.components
        assert "ai_asset_scan_incomplete" in {item.code for item in run.errors}
        assert not list(workspace.iterdir())
    finally:
        registry.close()


def test_single_ai_file_over_512k_keeps_existing_facts_partial(tmp_path: Path):
    files = {"requirements.txt": "requests==2.32.5\n", "model.md": "x" * (512 * 1024 + 1)}
    _, registry, run, workspace, _ = _run(tmp_path, files, 11)
    try:
        assert run.status is ScanStatus.PARTIAL
        assert run.components
        assert "ai_asset_scan_incomplete" in {item.code for item in run.errors}
        assert not list(workspace.iterdir())
    finally:
        registry.close()


def test_ai_file_count_limit_is_independent_of_total_byte_limit(tmp_path: Path):
    files = {"requirements.txt": "requests==2.32.5\n", **{f"f{i}.md": "x" for i in range(129)}}
    _, registry, run, workspace, _ = _run(tmp_path, files, 12)
    try:
        assert run.status is ScanStatus.PARTIAL
        assert run.components
        assert "ai_asset_scan_incomplete" in {item.code for item in run.errors}
        assert not list(workspace.iterdir())
    finally:
        registry.close()


def test_ai_total_two_megabyte_limit_is_independent_of_file_count(tmp_path: Path):
    files = {"requirements.txt": "requests==2.32.5\n", **{f"f{i}.md": "x" * 500_000 for i in range(5)}}
    _, registry, run, workspace, _ = _run(tmp_path, files, 13)
    try:
        assert run.status is ScanStatus.PARTIAL
        assert run.components
        assert "ai_asset_scan_incomplete" in {item.code for item in run.errors}
        assert not list(workspace.iterdir())
    finally:
        registry.close()


def test_python_marker_source_is_never_executed(tmp_path: Path):
    marker = "marker-created-by-scan"
    source = f"from pathlib import Path\nPath({str(tmp_path / marker)!r}).write_text('executed')\n{MODEL}\n"
    _, registry, run, workspace, _ = _run(tmp_path, {"requirements.txt": "requests==2.32.5\n", "scan.py": source}, 14)
    try:
        assert run.status is ScanStatus.COMPLETED
        assert len(run.ai_assets) == 1
        assert not (tmp_path / marker).exists()
        assert not list(workspace.iterdir())
    finally:
        registry.close()


def test_evidence_hash_mismatch_fails_closed_without_fake_assets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    original = ai_assets_pipeline.detect_ai_assets

    def forged(files, *, observed_at):
        assets, evidence = original(files, observed_at=observed_at)
        bad = evidence[0].model_copy(update={"content_hash": HashValue(algorithm="sha256", value="0" * 64)})
        return assets, [bad]

    monkeypatch.setattr(ai_assets_pipeline, "detect_ai_assets", forged)
    _, registry, run, workspace, _ = _run(tmp_path, {"requirements.txt": "requests==2.32.5\n", "README.md": MODEL}, 20)
    try:
        assert run.status is ScanStatus.PARTIAL
        assert not run.ai_assets
        assert "ai_asset_scan_incomplete" in {item.code for item in run.errors}
        assert not list(workspace.iterdir())
    finally:
        registry.close()
