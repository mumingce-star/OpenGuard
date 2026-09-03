"""Implementation-side tests for the frozen A4-1 local ZIP plan."""

from __future__ import annotations

import copy
import hashlib
import json
import zipfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

import app.pipeline.local_zip as local_zip
from app.domain.models import ScanRun, ScanStage, ScanStatus
from app.persistence import SQLiteScanRunRegistry
from app.pipeline import PipelineError, ScanPipelineWorker, build_local_zip_dependency_plan
from app.scanners import JavascriptP0MappingResult


ROOT = Path(__file__).resolve().parents[2]
SAMPLE = json.loads((ROOT / "examples" / "sample-scan-result.json").read_text())
NOW = datetime(2026, 9, 3, 1, 2, 3, tzinfo=timezone.utc)
CASE_IDS = tuple(
    [
        *(f"POS-A4ZIP-{value:03d}" for value in range(1, 6)),
        *(f"NEG-A4ZIP-{value:03d}" for value in range(1, 11)),
    ]
)


def _archive(tmp_path: Path, files: dict[str, str], name: str = "project.zip") -> Path:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, content in files.items():
            archive.writestr(filename, content)
    return path


def _queued(archive: Path, index: int = 0, **project_changes: object) -> ScanRun:
    value = copy.deepcopy(SAMPLE)
    suffix = f"{index:012x}"
    value["id"] = f"scn_123e4567-e89b-12d3-a456-{suffix}"
    value["idempotency_key"] = None
    value["status"] = "queued"
    value["stage"] = "queued"
    value["progress"] = 0
    value["project"] = {
        "id": f"prj_123e4567-e89b-12d3-a456-{suffix}",
        "name": "local-zip-test",
        "source_type": "zip",
        "source": archive.name,
        "revision": None,
        "root_digest": None,
        "created_at": "2026-09-01T12:00:00Z",
        **project_changes,
    }
    for field in (
        "components",
        "ai_assets",
        "licenses",
        "evidence",
        "obligations",
        "findings",
        "remediations",
        "errors",
        "report_links",
    ):
        value[field] = []
    value["summary"] = {
        "component_count": 0,
        "ai_asset_count": 0,
        "evidence_count": 0,
        "finding_counts": {"pass": 0, "warning": 0, "review_required": 0, "unknown": 0},
    }
    value["provenance"].update(
        input_digest={"algorithm": "sha256", "value": hashlib.sha256(archive.read_bytes()).hexdigest()},
        inventory_digest=None,
        tool_versions=[],
        ai_enabled=False,
        ai_model=None,
    )
    value["started_at"] = None
    value["finished_at"] = None
    return ScanRun.model_validate(value)


def _run(tmp_path: Path, archive: Path, queued: ScanRun, *, plan=None):
    registry = SQLiteScanRunRegistry(tmp_path / f"{queued.id}.sqlite")
    stored = registry.create(queued)
    workspace = tmp_path / f"workspace-{queued.id}"
    if plan is None:
        workspace.mkdir(mode=0o700)
    actual_plan = plan or build_local_zip_dependency_plan(archive, workspace, clock=lambda: NOW)
    result = ScanPipelineWorker(registry, clock=lambda: NOW).run(stored.run.id, actual_plan)
    return registry, result


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_frozen_case_ids_are_discoverable(case_id: str) -> None:
    assert case_id.startswith(("POS-A4ZIP-", "NEG-A4ZIP-"))


def test_pos_a4zip_001_004_real_python_and_javascript_persist_partial(tmp_path: Path) -> None:
    archive = _archive(
        tmp_path,
        {
            "requirements.txt": "requests==2.32.5\n",
            "package.json": '{"dependencies":{"react":"18.2.0"}}',
        },
    )
    queued = _queued(archive)
    workspace = tmp_path / f"workspace-{queued.id}"
    registry, result = _run(tmp_path, archive, queued)

    run = result.run
    assert (run.status, run.stage, run.progress) == (ScanStatus.PARTIAL, ScanStage.RULES, 70)
    assert {(item.ecosystem, item.name) for item in run.components} == {
        ("pypi", "requests"),
        ("npm", "react"),
    }
    assert run.summary.component_count == 2
    assert run.summary.evidence_count == len(run.evidence) >= 2
    assert [item.code for item in run.errors] == ["rules_stage_not_connected"]
    assert run.project.root_digest == run.provenance.inventory_digest
    assert run.project.root_digest is not None
    assert run.provenance.input_digest.value == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert {item.name for item in run.provenance.tool_versions} == {
        "openguard-python-manifest-parser",
        "openguard.javascript-manifest",
    }
    assert not any((run.licenses, run.findings, run.ai_assets, run.report_links))
    assert not list(workspace.iterdir())
    registry.close()
    reopened = SQLiteScanRunRegistry(tmp_path / f"{queued.id}.sqlite")
    assert reopened.get(queued.id).run == run


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ({"pyproject.toml": '[project]\ndependencies=["httpx==0.28.1"]\n'}, {("pypi", "httpx")}),
        ({"package.json": '{"devDependencies":{"vite":"5.0.7"}}'}, {("npm", "vite")}),
    ],
)
def test_pos_a4zip_002_single_language_is_still_useful(
    tmp_path: Path,
    files: dict[str, str],
    expected: set[tuple[str, str]],
) -> None:
    archive = _archive(tmp_path, files)
    _, result = _run(tmp_path, archive, _queued(archive))
    assert {(item.ecosystem, item.name) for item in result.run.components} == expected
    assert result.run.status is ScanStatus.PARTIAL
    assert [item.code for item in result.run.errors] == ["rules_stage_not_connected"]


def test_pos_a4zip_003_partial_lane_keeps_other_lane_result(tmp_path: Path) -> None:
    archive = _archive(
        tmp_path,
        {
            "requirements.txt": "-r other.txt\n",
            "package.json": '{"dependencies":{"react":"18.2.0"}}',
        },
    )
    _, result = _run(tmp_path, archive, _queued(archive))
    assert {(item.ecosystem, item.name) for item in result.run.components} == {("npm", "react")}
    assert [item.code for item in result.run.errors] == [
        "python_dependency_scan_partial",
        "rules_stage_not_connected",
    ]
    assert all(item.recoverable for item in result.run.errors)


def test_pos_a4zip_005_unknown_lane_failure_is_sanitized_and_cleanup_holds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = _archive(tmp_path, {"package.json": '{"dependencies":{"react":"18.2.0"}}'})
    workspace = tmp_path / "workspace"

    def unsafe_failure(session: object) -> object:
        raise RuntimeError("/Users/private token=secret https://internal.invalid")

    monkeypatch.setattr(local_zip, "parse_python_manifests", unsafe_failure)
    registry = SQLiteScanRunRegistry(tmp_path / "runs.sqlite")
    queued = registry.create(_queued(archive))
    workspace.mkdir(mode=0o700)
    plan = build_local_zip_dependency_plan(archive, workspace, clock=lambda: NOW)
    result = ScanPipelineWorker(registry, clock=lambda: NOW).run(queued.run.id, plan)
    serialized = result.run.model_dump_json()
    assert [item.code for item in result.run.errors] == [
        "python_dependency_scan_failed",
        "rules_stage_not_connected",
    ]
    assert "/Users/private" not in serialized
    assert "internal.invalid" not in serialized
    assert "token=secret" not in serialized
    assert not list(workspace.iterdir())


def test_neg_a4zip_001_incompatible_queued_run_fails_before_open(tmp_path: Path) -> None:
    archive = _archive(tmp_path, {"requirements.txt": "requests==2.32.5\n"})
    queued = _queued(
        archive,
        source_type="git",
        source="https://example.org/repository.git",
    )
    _, result = _run(tmp_path, archive, queued)
    assert (result.run.status, result.run.stage) == (ScanStatus.FAILED, ScanStage.INGESTION)
    assert [item.code for item in result.run.errors] == ["local_zip_plan_incompatible"]
    assert result.run.project.root_digest is None


@pytest.mark.parametrize(
    ("kind", "expected_code"),
    [("missing", "local_zip_unavailable"), ("invalid", "zip_ingestion_failed")],
)
def test_neg_a4zip_002_004_unavailable_or_invalid_is_fixed_and_clean(
    tmp_path: Path,
    kind: str,
    expected_code: str,
) -> None:
    archive = tmp_path / "project.zip"
    if kind == "invalid":
        archive.write_bytes(b"not-a-zip")
    digest_source = archive if archive.exists() else _archive(tmp_path, {}, "digest.zip")
    queued = _queued(digest_source).model_copy(
        update={"project": _queued(digest_source).project.model_copy(update={"source": archive.name})}
    )
    registry = SQLiteScanRunRegistry(tmp_path / "runs.sqlite")
    stored = registry.create(queued)
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700)
    result = ScanPipelineWorker(registry, clock=lambda: NOW).run(
        stored.run.id,
        build_local_zip_dependency_plan(archive, workspace, clock=lambda: NOW),
    )
    assert [item.code for item in result.run.errors] == [expected_code]
    assert result.run.status is ScanStatus.FAILED
    assert result.run.project.root_digest is None
    assert not workspace.exists() or not list(workspace.iterdir())
    assert str(tmp_path) not in result.run.model_dump_json()


def test_neg_a4zip_003_digest_mismatch_publishes_no_aggregate(tmp_path: Path) -> None:
    archive = _archive(tmp_path, {"requirements.txt": "requests==2.32.5\n"})
    value = _queued(archive).model_dump(mode="python")
    value["provenance"]["input_digest"] = {"algorithm": "sha256", "value": "0" * 64}
    _, result = _run(tmp_path, archive, ScanRun.model_validate(value))
    assert [item.code for item in result.run.errors] == ["input_digest_mismatch"]
    assert not any((result.run.components, result.run.evidence))
    assert result.run.project.root_digest is None
    assert result.run.provenance.inventory_digest is None


def test_neg_a4zip_005_both_lanes_fail_at_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = _archive(tmp_path, {"requirements.txt": "requests==2.32.5\n"})

    def fail(session: object) -> object:
        raise RuntimeError("hidden")

    monkeypatch.setattr(local_zip, "parse_python_manifests", fail)
    monkeypatch.setattr(local_zip, "parse_javascript_manifests", fail)
    _, result = _run(tmp_path, archive, _queued(archive))
    assert (result.run.status, result.run.stage, result.run.progress) == (
        ScanStatus.FAILED,
        ScanStage.SCAN,
        35,
    )
    assert [item.code for item in result.run.errors] == ["dependency_scan_failed"]


def test_neg_a4zip_007_empty_archive_never_claims_completion(tmp_path: Path) -> None:
    archive = _archive(tmp_path, {"README.md": "no dependency declarations"})
    _, result = _run(tmp_path, archive, _queued(archive))
    assert result.run.status is ScanStatus.FAILED
    assert result.run.stage is ScanStage.SCAN
    assert [item.code for item in result.run.errors] == ["dependency_manifest_not_found"]
    assert not any((result.run.components, result.run.evidence, result.run.report_links))


def test_neg_a4zip_008_conflicting_evidence_id_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = _archive(
        tmp_path,
        {
            "requirements.txt": "requests==2.32.5\n",
            "package.json": '{"dependencies":{"react":"18.2.0"}}',
        },
    )
    captured: dict[str, object] = {}
    original_python = local_zip.map_python_manifest_result
    original_javascript = local_zip.map_javascript_manifest_result

    def capture_python(*args: object, **kwargs: object):
        result = original_python(*args, **kwargs)
        captured["evidence"] = result.evidence[0]
        return result

    def collide_javascript(*args: object, **kwargs: object):
        result = original_javascript(*args, **kwargs)
        evidence = captured["evidence"].model_copy(update={"excerpt": "different"})
        return JavascriptP0MappingResult(
            result.schema_version,
            result.status,
            result.components,
            (evidence,),
            result.diagnostics,
        )

    monkeypatch.setattr(local_zip, "map_python_manifest_result", capture_python)
    monkeypatch.setattr(local_zip, "map_javascript_manifest_result", collide_javascript)
    _, result = _run(tmp_path, archive, _queued(archive))
    assert result.run.status is ScanStatus.FAILED
    assert [item.code for item in result.run.errors] == ["dependency_scan_failed"]


def test_neg_a4zip_009_plan_is_one_shot(tmp_path: Path) -> None:
    archive = _archive(tmp_path, {"requirements.txt": "requests==2.32.5\n"})
    registry = SQLiteScanRunRegistry(tmp_path / "runs.sqlite")
    first = registry.create(_queued(archive, 1))
    second = registry.create(_queued(archive, 2))
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700)
    plan = build_local_zip_dependency_plan(archive, workspace, clock=lambda: NOW)
    first_result = ScanPipelineWorker(registry, clock=lambda: NOW).run(first.run.id, plan)
    archive.unlink()
    second_result = ScanPipelineWorker(registry, clock=lambda: NOW).run(second.run.id, plan)
    assert first_result.run.status is ScanStatus.PARTIAL
    assert [item.code for item in second_result.run.errors] == ["local_zip_plan_reused"]
    assert second_result.run.stage is ScanStage.INGESTION


def test_neg_a4zip_010_factory_validation_and_unreachable_stages(tmp_path: Path) -> None:
    with pytest.raises(PipelineError) as raised:
        build_local_zip_dependency_plan("project.zip", tmp_path, clock=lambda: NOW)  # type: ignore[arg-type]
    assert raised.value.code == "pipeline_invalid_argument"

    archive = _archive(tmp_path, {"requirements.txt": "requests==2.32.5\n"})
    plan = build_local_zip_dependency_plan(archive, tmp_path / "workspace", clock=lambda: NOW)
    assert plan.steps[5].stage is ScanStage.AI_ASSIST
    assert plan.steps[6].stage is ScanStage.REPORT
    with pytest.raises(Exception):
        plan.steps[5].handler(_queued(archive))
    with pytest.raises(Exception):
        plan.steps[6].handler(_queued(archive))
