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


def test_neg_a4zip_010_factory_validation_and_disabled_future_stages(tmp_path: Path) -> None:
    with pytest.raises(PipelineError) as raised:
        build_local_zip_dependency_plan("project.zip", tmp_path, clock=lambda: NOW)  # type: ignore[arg-type]
    assert raised.value.code == "pipeline_invalid_argument"

    archive = _archive(tmp_path, {"requirements.txt": "requests==2.32.5\n"})
    plan = build_local_zip_dependency_plan(archive, tmp_path / "workspace", clock=lambda: NOW)
    assert plan.steps[5].stage is ScanStage.AI_ASSIST
    assert plan.steps[6].stage is ScanStage.REPORT
    queued = _queued(archive)
    ai_disabled = plan.steps[5].handler(queued)
    assert ai_disabled.provenance.ai_enabled is False
    assert ai_disabled.provenance.ai_model is None
    assert plan.steps[6].handler(ai_disabled) == ai_disabled


def _licensed_files(license_value="MIT", **record_changes):
    record = {"version": "1.0.0", "license": license_value, **record_changes}
    return {
        "package.json": json.dumps({"dependencies": {"known": "1.0.0", "unknown": "2.0.0"}}),
        "package-lock.json": json.dumps({"lockfileVersion": 3, "packages": {
            "": {"license": "GPL-3.0-only"},
            "node_modules/known": record,
            "node_modules/unknown": {"version": "2.0.0"},
        }}),
        "requirements.txt": "requests==2.32.5\n",
    }


def test_zip_explicit_license_reaches_rules_and_report_without_verification(tmp_path):
    from app.domain.models import VerificationStatus, FindingOutcome
    archive = _archive(tmp_path, _licensed_files())
    registry, result = _run(tmp_path, archive, _queued(archive))
    run = result.run
    assert run.status is ScanStatus.COMPLETED
    assert run.stage is ScanStage.COMPLETED
    licenses = {item.id: item for item in run.licenses}
    components = {item.name: item for item in run.components}
    assert licenses[components["known"].license_expression_id].normalized_ids == ["MIT"]
    for name in ("unknown", "requests"):
        assert licenses[components[name].license_expression_id].expression == "NOASSERTION"
    assert all(item.verification_status is VerificationStatus.PENDING for item in run.licenses)
    license_evidence = [item for item in run.evidence if item.locator.endswith("/license")]
    assert len(license_evidence) == 1
    item = license_evidence[0]
    assert item.locator == "package-lock.json:/packages/node_modules~1known/license"
    assert item.verification_status is VerificationStatus.PENDING
    assert item.content_hash.value == hashlib.sha256(_licensed_files()["package-lock.json"].encode()).hexdigest()
    assert run.findings and all(item.outcome is FindingOutcome.REVIEW_REQUIRED for item in run.findings)
    assert run.summary.evidence_count == len(run.evidence)
    assert registry.get(run.id).run == run
    registry.close()


@pytest.mark.parametrize("license_value", [None, {}, ["MIT"], "", "MIT\n", "secret_token=abc", "Custom-Unknown", "MIT OR Unknown"])
def test_zip_invalid_or_unknown_license_preserves_legacy_partial(tmp_path, license_value):
    archive = _archive(tmp_path, _licensed_files(license_value))
    registry, result = _run(tmp_path, archive, _queued(archive))
    assert result.run.status is ScanStatus.PARTIAL
    assert [item.code for item in result.run.errors] == ["rules_stage_not_connected"]
    assert not result.run.licenses
    assert not any(item.locator.endswith("/license") for item in result.run.evidence)
    registry.close()


@pytest.mark.parametrize("changes", [{"name": "other"}, {"version": "9.0.0"}])
def test_zip_mismatched_lock_identity_never_inherits_license(tmp_path, changes):
    archive = _archive(tmp_path, _licensed_files(**changes))
    registry, result = _run(tmp_path, archive, _queued(archive))
    assert result.run.status is ScanStatus.PARTIAL
    assert not result.run.licenses
    registry.close()


@pytest.mark.parametrize("invalid", [
    '{"lockfileVersion":3,"packages":{"node_modules/known":{"version":"1.0.0","license":"MIT","license":"ISC"}}}',
    '{"lockfileVersion":3,"packages":{"node_modules/known":{"version":"1.0.0","license":"MIT"}},"extra":NaN}',
    '{"lockfileVersion":3,"packages":{"node_modules/known":{"version":"1.0.0","license":"MIT"}},"extra":1e999}',
])
def test_zip_ambiguous_json_cannot_supply_license(tmp_path, invalid):
    files = _licensed_files()
    files["package-lock.json"] = invalid
    archive = _archive(tmp_path, files)
    registry, result = _run(tmp_path, archive, _queued(archive))
    assert result.run.status is ScanStatus.PARTIAL
    assert not result.run.licenses
    registry.close()


@pytest.mark.parametrize("lock_version", [2, 3])
def test_zip_scoped_nested_package_lock_binding(tmp_path, lock_version):
    files = {
        "web/package.json": '{"dependencies":{"@scope/library":"1.0.0"}}',
        "web/package-lock.json": json.dumps({"lockfileVersion": lock_version, "packages": {
            "node_modules/@scope/library": {"version": "1.0.0", "name": "@scope/library", "license": "Apache-2.0"},
        }}),
    }
    registry, result = _run(tmp_path, (archive := _archive(tmp_path, files)), _queued(archive))
    assert result.run.status is ScanStatus.COMPLETED
    assert result.run.licenses[0].normalized_ids == ["Apache-2.0"]
    assert any(item.locator == "web/package-lock.json:/packages/node_modules~1@scope~1library/license" for item in result.run.evidence)
    registry.close()


def test_large_valid_locks_preserve_shared_read_budget_and_legacy_partial(tmp_path):
    # B1 reads below its 8 MiB limit, but rereading all locks would exceed A2's
    # 12 MiB budget and irreversibly invalidate the session.
    files = {}
    for index in range(4):
        name = f"dependency-{index}"
        files[f"project-{index}/package.json"] = json.dumps({"dependencies": {name: "1.0.0"}})
        files[f"project-{index}/package-lock.json"] = json.dumps({
            "lockfileVersion": 3,
            "packages": {f"node_modules/{name}": {"version": "1.0.0"}},
            "padding": ["a" * 4000 for _ in range(410)],
        })
    archive = tmp_path / "large-manifests.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as output:
        for path, content in files.items():
            output.writestr(path, content)
    registry, result = _run(tmp_path, archive, _queued(archive))
    assert result.run.status is ScanStatus.PARTIAL
    assert result.run.stage is ScanStage.RULES
    assert result.run.progress == 70
    assert len(result.run.components) == 4
    assert not result.run.licenses
    assert [item.code for item in result.run.errors] == ["rules_stage_not_connected"]
    registry.close()


def test_external_facts_keep_manifest_identity_and_do_not_inherit_root_license(tmp_path, monkeypatch):
    from app.domain.models import Evidence, ProducerRef, HashValue
    from app.pipeline.external_scans import ExternalScanFacts
    from app.scanners.external_tools import map_syft_output
    files = {"LICENSE": "MIT License", "package.json": json.dumps({"name": "fixture", "version": "1.0.0", "dependencies": {"declared": "1.0.0", "unknown": "2.0.0"}}), "package-lock.json": json.dumps({
        "lockfileVersion": 3, "packages": {"": {"name": "fixture", "version": "1.0.0"},
        "node_modules/declared": {"version": "1.0.0", "license": "MIT"},
        "node_modules/unknown": {"version": "2.0.0"}}})}
    archive = _archive(tmp_path, files)
    seen = []
    def collect(tree, inventory, clock):
        seen.append(tree)
        producer = ProducerRef(type="scanner", name="scancode", version="32.5.0")
        license_evidence = Evidence(id="evd_123e4567-e89b-12d3-a456-000000000099",
            kind="license_text", locator="LICENSE", excerpt="mit", detected_by="scancode",
            content_hash=HashValue(algorithm="sha256", value=hashlib.sha256(files["LICENSE"].encode()).hexdigest()),
            producer=producer, observed_at=clock(), verification_status="pending")
        syft = map_syft_output({"artifacts": [{"name": "declared", "version": "1.0.0",
            "purl": "pkg:npm/declared@1.0.0", "locations": [{"path": "package-lock.json"}]}]},
            root_digest=inventory.root_digest, observed_at=clock(), tool_version="1.51.0")
        return ExternalScanFacts(list(syft.components), [license_evidence, *syft.evidence], [producer])
    monkeypatch.setattr(local_zip, "collect_external_scans", collect)
    workspace = tmp_path / "external-work"; workspace.mkdir(mode=0o700)
    plan = build_local_zip_dependency_plan(archive, workspace, clock=lambda: NOW, external_scanners=True)
    registry, result = _run(tmp_path, archive, _queued(archive, 500), plan=plan)
    run = registry.get(result.run.id).run if hasattr(result, "run") else registry.get(_queued(archive, 500).id).run
    assert run.status == ScanStatus.COMPLETED
    licenses = {item.id: item.expression for item in run.licenses}
    by_name = {item.name: item for item in run.components}
    assert len(run.components) == 2
    assert licenses[by_name["declared"].license_expression_id] == "MIT"
    assert licenses[by_name["unknown"].license_expression_id] == "NOASSERTION"
    assert "syft" in by_name["declared"].detected_by
    assert any(item.locator == "LICENSE" for item in run.evidence)
    assert not seen[0]._active
    assert not list(workspace.iterdir())


def test_external_failure_is_partial_with_existing_facts(tmp_path, monkeypatch):
    from app.domain.models import ScanError
    from app.pipeline.external_scans import ExternalScanFacts
    archive = _archive(tmp_path, {"requirements.txt": "requests==2.32.3\n"})
    monkeypatch.setattr(local_zip, "collect_external_scans", lambda *args: ExternalScanFacts(errors=[
        ScanError(code="scancode_scan_incomplete", stage="scan", message="Scan incomplete.", recoverable=True)]))
    workspace = tmp_path / "external-failure"; workspace.mkdir(mode=0o700)
    queued = _queued(archive, 501)
    registry, result = _run(tmp_path, archive, queued, plan=build_local_zip_dependency_plan(
        archive, workspace, clock=lambda: NOW, external_scanners=True))
    run = registry.get(queued.id).run
    assert run.status == ScanStatus.PARTIAL
    assert run.components and run.findings
    assert {error.code for error in run.errors} >= {"scancode_scan_incomplete", "external_scan_incomplete"}
    assert all(item.expression == "NOASSERTION" for item in run.licenses)
