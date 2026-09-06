"""Independent A4-1 verification for the local ZIP dependency pipeline.

This module builds its own ZIP archives, queued P0 runs, SQLite registries and
expected terminal states.  It deliberately does not import implementation-side
test helpers or expected fixtures.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import app.pipeline.local_zip as local_zip
from app.domain.models import (
    Component,
    DetectionMethod,
    Evidence,
    EvidenceKind,
    FindingOutcome,
    HashValue,
    ProducerRef,
    ProducerType,
    Project,
    RunEnvironment,
    RunProvenance,
    ScanRun,
    ScanStage,
    ScanStatus,
    ScanSummary,
    SourceType,
    VerificationStatus,
)
from app.persistence import SQLiteScanRunRegistry
from app.pipeline import (
    PipelinePlan,
    PipelineStep,
    ScanPipelineWorker,
    build_local_zip_dependency_plan,
)


BASE_TIME = datetime(2026, 9, 3, 7, 0, tzinfo=timezone.utc)
WORKER_TIME = BASE_TIME + timedelta(hours=1)
ZERO_DIGEST = "0" * 64


def _id(prefix: str, number: int) -> str:
    return f"{prefix}_00000000-0000-0000-0000-{number:012x}"


def _hash(value: str) -> HashValue:
    return HashValue(algorithm="sha256", value=value * 64)


def _empty_summary() -> ScanSummary:
    return ScanSummary(
        component_count=0,
        ai_asset_count=0,
        evidence_count=0,
        finding_counts={
            FindingOutcome.PASS: 0,
            FindingOutcome.WARNING: 0,
            FindingOutcome.REVIEW_REQUIRED: 0,
            FindingOutcome.UNKNOWN: 0,
        },
    )


def _write_zip(directory: Path, files: dict[str, str | bytes], name: str = "source.zip") -> Path:
    archive_path = directory / name
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for member, content in files.items():
            archive.writestr(member, content)
    return archive_path


def _queued(
    archive_path: Path,
    number: int,
    *,
    input_digest: str | None = None,
    project: Project | None = None,
    provenance: RunProvenance | None = None,
    components: list[Component] | None = None,
    evidence: list[Evidence] | None = None,
) -> ScanRun:
    created_at = BASE_TIME + timedelta(seconds=number)
    archive_digest = input_digest or hashlib.sha256(archive_path.read_bytes()).hexdigest()
    selected_project = project or Project(
        id=_id("prj", number),
        name=f"independent-local-zip-{number}",
        source_type=SourceType.ZIP,
        source=archive_path.name,
        created_at=created_at,
    )
    selected_provenance = provenance or RunProvenance(
        input_digest=HashValue(algorithm="sha256", value=archive_digest),
        inventory_digest=None,
        tool_versions=[],
        ruleset_version="independent-local-zip-rules",
        contract_version="0.1.1",
        ai_enabled=False,
        ai_model=None,
        run_environment=RunEnvironment(
            python_version="3.12-independent",
            platform="macos-independent",
            openguard_version="independent-a4-1",
        ),
    )
    selected_components = components or []
    selected_evidence = evidence or []
    return ScanRun(
        contract_version="0.1.1",
        id=_id("scn", number),
        idempotency_key=None,
        status=ScanStatus.QUEUED,
        stage=ScanStage.QUEUED,
        progress=0,
        project=selected_project,
        components=selected_components,
        evidence=selected_evidence,
        summary=ScanSummary(
            component_count=len(selected_components),
            ai_asset_count=0,
            evidence_count=len(selected_evidence),
            finding_counts={
                FindingOutcome.PASS: 0,
                FindingOutcome.WARNING: 0,
                FindingOutcome.REVIEW_REQUIRED: 0,
                FindingOutcome.UNKNOWN: 0,
            },
        ),
        provenance=selected_provenance,
        created_at=created_at,
    )


def _replace_run(run: ScanRun, **changes: object) -> ScanRun:
    payload = run.model_dump(mode="python")
    payload.update(changes)
    return ScanRun.model_validate(payload)


def _workspace(tmp_path: Path, number: int) -> Path:
    root = tmp_path / f"workspace-root-{number}"
    root.mkdir(mode=0o700, exist_ok=True)
    return root


def _execute(tmp_path: Path, archive_path: Path, queued: ScanRun, *, plan: PipelinePlan | None = None):
    database = tmp_path / f"run-{queued.id}.sqlite"
    registry = SQLiteScanRunRegistry(database)
    stored = registry.create(queued)
    workspace_root = _workspace(tmp_path, int(queued.id[-2:], 16))
    selected_plan = plan or build_local_zip_dependency_plan(
        archive_path,
        workspace_root,
        clock=lambda: WORKER_TIME,
    )
    result = ScanPipelineWorker(registry, clock=lambda: WORKER_TIME).run(stored.run.id, selected_plan)
    registry.close()
    return database, result, workspace_root


def _sample_aggregate(number: int) -> tuple[Component, Evidence]:
    producer = ProducerRef(type=ProducerType.PARSER, name="independent-fixture", version="1")
    evidence = Evidence(
        id=_id("evd", number),
        kind=EvidenceKind.MANIFEST_FIELD,
        locator="requirements.txt",
        excerpt="requests==2.32.5",
        start_line=1,
        end_line=1,
        content_hash=_hash("b"),
        detected_by=DetectionMethod.MANIFEST_PARSER,
        producer=producer,
        observed_at=BASE_TIME,
        verification_status=VerificationStatus.VERIFIED,
    )
    component = Component(
        id=_id("cmp", number),
        name="requests",
        version="2.32.5",
        ecosystem="pypi",
        purl="pkg:pypi/requests@2.32.5",
        evidence_ids=[evidence.id],
        detected_by=[DetectionMethod.MANIFEST_PARSER],
        confidence=1.0,
    )
    return component, evidence


def test_pos_a4zip_001_004_mixed_zip_persists_real_p0_and_reopens(tmp_path: Path) -> None:
    archive_path = _write_zip(
        tmp_path,
        {
            "requirements.txt": "requests==2.32.5\n",
            "package.json": json.dumps({"dependencies": {"react": "18.2.0"}}),
        },
    )
    queued = _queued(archive_path, 1)
    database, result, workspace_root = _execute(tmp_path, archive_path, queued)

    run = result.run
    assert (run.status, run.stage, run.progress) == (ScanStatus.PARTIAL, ScanStage.RULES, 70)
    assert {(item.ecosystem, item.name) for item in run.components} == {
        ("pypi", "requests"),
        ("npm", "react"),
    }
    assert len(run.evidence) >= 2
    assert run.summary.component_count == len(run.components)
    assert run.summary.evidence_count == len(run.evidence)
    assert run.project.root_digest is not None
    assert run.project.root_digest == run.provenance.inventory_digest
    assert run.provenance.input_digest.value == hashlib.sha256(archive_path.read_bytes()).hexdigest()
    assert {producer.name for producer in run.provenance.tool_versions} == {
        "openguard-python-manifest-parser",
        "openguard.javascript-manifest",
    }
    assert not run.licenses
    assert not run.findings
    assert not run.ai_assets
    assert not run.report_links
    assert [error.code for error in run.errors] == ["rules_stage_not_connected"]
    assert not list(workspace_root.iterdir())

    reopened = SQLiteScanRunRegistry(database)
    try:
        assert reopened.get(run.id).run == run
    finally:
        reopened.close()


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ({"requirements.txt": "httpx==0.28.1\n"}, {("pypi", "httpx")}),
        ({"package.json": json.dumps({"devDependencies": {"vite": "5.0.7"}})}, {("npm", "vite")}),
    ],
)
def test_pos_a4zip_002_single_language_is_persisted_without_fake_completion(
    tmp_path: Path,
    files: dict[str, str],
    expected: set[tuple[str, str]],
) -> None:
    archive_path = _write_zip(tmp_path, files)
    _, result, workspace_root = _execute(tmp_path, archive_path, _queued(archive_path, 2))

    assert {(item.ecosystem, item.name) for item in result.run.components} == expected
    assert (result.run.status, result.run.stage, result.run.progress) == (
        ScanStatus.PARTIAL,
        ScanStage.RULES,
        70,
    )
    assert [error.code for error in result.run.errors] == ["rules_stage_not_connected"]
    assert not list(workspace_root.iterdir())


def test_pos_a4zip_003_partial_lane_keeps_other_language(tmp_path: Path) -> None:
    archive_path = _write_zip(
        tmp_path,
        {
            "requirements.txt": "-r missing-requirements.txt\n",
            "package.json": json.dumps({"dependencies": {"react": "18.2.0"}}),
        },
    )
    _, result, workspace_root = _execute(tmp_path, archive_path, _queued(archive_path, 3))

    assert {(item.ecosystem, item.name) for item in result.run.components} == {("npm", "react")}
    assert (result.run.status, result.run.stage) == (ScanStatus.PARTIAL, ScanStage.RULES)
    assert [error.code for error in result.run.errors] == [
        "python_dependency_scan_partial",
        "rules_stage_not_connected",
    ]
    assert all(error.recoverable for error in result.run.errors)
    assert not list(workspace_root.iterdir())


def test_pos_a4zip_005_success_and_rejection_leave_no_task_workspace(tmp_path: Path) -> None:
    good_archive = _write_zip(tmp_path, {"requirements.txt": "requests==2.32.5\n"}, "good.zip")
    _, good_result, good_root = _execute(tmp_path, good_archive, _queued(good_archive, 4))
    assert good_result.run.status is ScanStatus.PARTIAL
    assert not list(good_root.iterdir())

    escape_target = tmp_path / "escaped.txt"
    rejected_archive = _write_zip(tmp_path, {"../escaped.txt": "must not materialize"}, "rejected.zip")
    _, rejected_result, rejected_root = _execute(tmp_path, rejected_archive, _queued(rejected_archive, 5))
    assert rejected_result.run.status is ScanStatus.FAILED
    assert [error.code for error in rejected_result.run.errors] == ["zip_ingestion_failed"]
    assert not escape_target.exists()
    assert not list(rejected_root.iterdir())


@pytest.mark.parametrize(
    "project_change",
    [
        {"source_type": SourceType.GIT, "source": "https://example.org/source.git"},
        {"source": "another.zip"},
    ],
)
def test_neg_a4zip_001_incompatible_source_fails_before_open(
    tmp_path: Path,
    project_change: dict[str, object],
) -> None:
    archive_path = _write_zip(tmp_path, {"requirements.txt": "requests==2.32.5\n"})
    base = _queued(archive_path, 10)
    project = base.project.model_copy(update=project_change)
    queued = _replace_run(base, project=project)

    _, result, workspace_root = _execute(tmp_path, archive_path, queued)
    assert (result.run.status, result.run.stage) == (ScanStatus.FAILED, ScanStage.INGESTION)
    assert [error.code for error in result.run.errors] == ["local_zip_plan_incompatible"]
    assert result.run.project.root_digest is None
    assert not list(workspace_root.iterdir())


@pytest.mark.parametrize("variant", ["root_digest", "aggregate", "ai_enabled"])
def test_neg_a4zip_001_non_pristine_queued_run_is_rejected(tmp_path: Path, variant: str) -> None:
    archive_path = _write_zip(tmp_path, {"requirements.txt": "requests==2.32.5\n"})
    base = _queued(archive_path, 11)
    if variant == "root_digest":
        queued = _replace_run(
            base,
            project=base.project.model_copy(update={"root_digest": _hash("c")}),
        )
    elif variant == "aggregate":
        component, evidence = _sample_aggregate(11)
        queued = _replace_run(
            base,
            components=[component],
            evidence=[evidence],
            summary=ScanSummary(
                component_count=1,
                ai_asset_count=0,
                evidence_count=1,
                finding_counts={
                    FindingOutcome.PASS: 0,
                    FindingOutcome.WARNING: 0,
                    FindingOutcome.REVIEW_REQUIRED: 0,
                    FindingOutcome.UNKNOWN: 0,
                },
            ),
        )
    else:
        ai_model = ProducerRef(
            type=ProducerType.AI,
            name="independent-ai",
            version="1",
            provider="local",
            model_id="model",
            prompt_schema_digest=_hash("d"),
        )
        provenance = RunProvenance.model_validate(
            {
                **base.provenance.model_dump(mode="python"),
                "ai_enabled": True,
                "ai_model": ai_model,
            }
        )
        queued = _replace_run(base, provenance=provenance)

    _, result, workspace_root = _execute(tmp_path, archive_path, queued)
    assert [error.code for error in result.run.errors] == ["local_zip_plan_incompatible"]
    assert result.run.stage is ScanStage.INGESTION
    assert not list(workspace_root.iterdir())


@pytest.mark.parametrize("variant", ["missing", "invalid"])
def test_neg_a4zip_002_unavailable_or_bad_zip_is_fixed_and_sanitized(tmp_path: Path, variant: str) -> None:
    archive_path = tmp_path / f"{variant}.zip"
    if variant == "invalid":
        archive_path.write_bytes(b"not a ZIP archive")
        queued = _queued(archive_path, 12)
    else:
        queued = _queued(archive_path, 13, input_digest=ZERO_DIGEST)

    _, result, workspace_root = _execute(tmp_path, archive_path, queued)
    expected = "local_zip_unavailable" if variant == "missing" else "zip_ingestion_failed"
    assert [error.code for error in result.run.errors] == [expected]
    assert result.run.status is ScanStatus.FAILED
    assert result.run.project.root_digest is None
    assert not list(workspace_root.iterdir())
    serialized = result.run.model_dump_json()
    assert str(tmp_path) not in serialized
    assert "not a ZIP" not in serialized


def test_neg_a4zip_003_digest_mismatch_publishes_no_aggregate(tmp_path: Path) -> None:
    archive_path = _write_zip(tmp_path, {"requirements.txt": "requests==2.32.5\n"})
    queued = _queued(archive_path, 14, input_digest=ZERO_DIGEST)
    _, result, workspace_root = _execute(tmp_path, archive_path, queued)

    assert [error.code for error in result.run.errors] == ["input_digest_mismatch"]
    assert result.run.stage is ScanStage.INGESTION
    assert not result.run.components
    assert not result.run.evidence
    assert result.run.project.root_digest is None
    assert result.run.provenance.inventory_digest is None
    assert not list(workspace_root.iterdir())


def test_neg_a4zip_005_both_dependency_lanes_fail_at_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = _write_zip(tmp_path, {"README.md": "inputs are intentionally unusable"})

    def fail(_session: object) -> object:
        raise RuntimeError("parser failed")

    monkeypatch.setattr(local_zip, "parse_python_manifests", fail)
    monkeypatch.setattr(local_zip, "parse_javascript_manifests", fail)
    _, result, workspace_root = _execute(tmp_path, archive_path, _queued(archive_path, 15))

    assert (result.run.status, result.run.stage, result.run.progress) == (
        ScanStatus.FAILED,
        ScanStage.SCAN,
        35,
    )
    assert [error.code for error in result.run.errors] == ["dependency_scan_failed"]
    assert not result.run.components
    assert not result.run.evidence
    assert not list(workspace_root.iterdir())


def test_neg_a4zip_006_unknown_lane_error_is_sanitized_but_other_lane_survives(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = _write_zip(
        tmp_path,
        {"package.json": json.dumps({"dependencies": {"react": "18.2.0"}})},
    )

    def unsafe_failure(_session: object) -> object:
        raise RuntimeError("/private/work token=secret https://internal.example.invalid")

    monkeypatch.setattr(local_zip, "parse_python_manifests", unsafe_failure)
    _, result, workspace_root = _execute(tmp_path, archive_path, _queued(archive_path, 16))

    assert {(item.ecosystem, item.name) for item in result.run.components} == {("npm", "react")}
    assert [error.code for error in result.run.errors] == [
        "python_dependency_scan_failed",
        "rules_stage_not_connected",
    ]
    serialized = result.run.model_dump_json()
    for forbidden in ("/private/work", "token=secret", "internal.example.invalid", "parser failed"):
        assert forbidden not in serialized
    assert not list(workspace_root.iterdir())


def test_neg_a4zip_007_manifest_absence_never_creates_fake_evidence(tmp_path: Path) -> None:
    archive_path = _write_zip(tmp_path, {"README.md": "no dependency declaration"})
    _, result, workspace_root = _execute(tmp_path, archive_path, _queued(archive_path, 17))

    assert (result.run.status, result.run.stage) == (ScanStatus.FAILED, ScanStage.SCAN)
    assert [error.code for error in result.run.errors] == ["dependency_manifest_not_found"]
    assert not result.run.components
    assert not result.run.evidence
    assert not result.run.report_links
    assert not list(workspace_root.iterdir())


def test_neg_a4zip_008_illegal_mapper_objects_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = _write_zip(
        tmp_path,
        {
            "requirements.txt": "requests==2.32.5\n",
            "package.json": json.dumps({"dependencies": {"react": "18.2.0"}}),
        },
    )

    def invalid_mapper(*_args: object, **_kwargs: object) -> object:
        return object()

    monkeypatch.setattr(local_zip, "map_python_manifest_result", invalid_mapper)
    monkeypatch.setattr(local_zip, "map_javascript_manifest_result", invalid_mapper)
    _, result, workspace_root = _execute(tmp_path, archive_path, _queued(archive_path, 18))

    assert (result.run.status, result.run.stage) == (ScanStatus.FAILED, ScanStage.SCAN)
    assert [error.code for error in result.run.errors] == ["dependency_scan_failed"]
    assert not result.run.components
    assert not result.run.evidence
    assert not list(workspace_root.iterdir())


def test_neg_a4zip_008_invalid_p0_reference_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = _write_zip(tmp_path, {"requirements.txt": "requests==2.32.5\n"})
    original_mapper = local_zip.map_python_manifest_result

    def invalid_reference(*args: object, **kwargs: object) -> object:
        mapping = original_mapper(*args, **kwargs)
        assert mapping.components
        broken = mapping.components[0].model_copy(update={"evidence_ids": [_id("evd", 999)]})
        return replace(mapping, components=(broken, *mapping.components[1:]))

    monkeypatch.setattr(local_zip, "map_python_manifest_result", invalid_reference)
    _, result, workspace_root = _execute(tmp_path, archive_path, _queued(archive_path, 19))

    assert (result.run.status, result.run.stage) == (ScanStatus.FAILED, ScanStage.SCAN)
    assert [error.code for error in result.run.errors] == ["pipeline_stage_failed"]
    assert not result.run.components
    assert not result.run.evidence
    assert not list(workspace_root.iterdir())


def test_neg_a4zip_009_plan_reuse_does_not_reopen_archive_or_parser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = _write_zip(tmp_path, {"requirements.txt": "requests==2.32.5\n"})
    first = _queued(archive_path, 20)
    second = _queued(archive_path, 21)
    database = tmp_path / "reuse.sqlite"
    registry = SQLiteScanRunRegistry(database)
    first_stored = registry.create(first)
    second_stored = registry.create(second)
    workspace_root = _workspace(tmp_path, 20)
    parser_calls = {"python": 0, "javascript": 0}
    original_python = local_zip.parse_python_manifests
    original_javascript = local_zip.parse_javascript_manifests

    def count_python(session: object):
        parser_calls["python"] += 1
        return original_python(session)

    def count_javascript(session: object):
        parser_calls["javascript"] += 1
        return original_javascript(session)

    monkeypatch.setattr(local_zip, "parse_python_manifests", count_python)
    monkeypatch.setattr(local_zip, "parse_javascript_manifests", count_javascript)
    plan = build_local_zip_dependency_plan(archive_path, workspace_root, clock=lambda: WORKER_TIME)
    worker = ScanPipelineWorker(registry, clock=lambda: WORKER_TIME)
    first_result = worker.run(first_stored.run.id, plan)
    assert first_result.run.status is ScanStatus.PARTIAL
    assert parser_calls == {"python": 1, "javascript": 1}

    archive_path.unlink()
    second_result = worker.run(second_stored.run.id, plan)
    registry.close()
    assert second_result.run.status is ScanStatus.FAILED
    assert second_result.run.stage is ScanStage.INGESTION
    assert [error.code for error in second_result.run.errors] == ["local_zip_plan_reused"]
    assert parser_calls == {"python": 1, "javascript": 1}
    assert not list(workspace_root.iterdir())


def test_neg_a4zip_010_rules_partial_does_not_execute_ai_or_report(
    tmp_path: Path,
) -> None:
    archive_path = _write_zip(tmp_path, {"requirements.txt": "requests==2.32.5\n"})
    workspace_root = _workspace(tmp_path, 22)
    base_plan = build_local_zip_dependency_plan(archive_path, workspace_root, clock=lambda: WORKER_TIME)
    calls: list[str] = []

    def ai_handler(run: ScanRun) -> ScanRun:
        calls.append("ai")
        return run

    def report_handler(run: ScanRun) -> ScanRun:
        calls.append("report")
        return run

    plan = PipelinePlan(
        steps=(
            *base_plan.steps[:5],
            PipelineStep(ScanStage.AI_ASSIST, ai_handler),
            PipelineStep(ScanStage.REPORT, report_handler),
        )
    )
    _, result, _ = _execute(
        tmp_path,
        archive_path,
        _queued(archive_path, 22),
        plan=plan,
    )

    assert (result.run.status, result.run.stage, result.run.progress) == (
        ScanStatus.PARTIAL,
        ScanStage.RULES,
        70,
    )
    assert calls == []
    assert not result.run.ai_assets
    assert not result.run.report_links
    assert [error.code for error in result.run.errors] == ["rules_stage_not_connected"]


@pytest.mark.parametrize("lock_version", [2, 3])
def test_real_zip_declared_licenses_reach_risks_and_durable_http_reports(tmp_path: Path, lock_version: int) -> None:
    """Real socket/production factory; expectations come from independently authored bytes."""
    import base64
    import http.client
    import io
    import os
    import socket
    import subprocess
    import sys
    import time

    root = Path(__file__).resolve().parents[2]
    manifest = json.dumps({"name": "demo-root", "license": "GPL-3.0-only", "dependencies": {"demo-mit": "1.0.0", "demo-unknown": "2.0.0"}})
    lock = json.dumps({
        "name": "demo-root", "lockfileVersion": lock_version,
        "packages": {
            "": {"name": "demo-root", "license": "GPL-3.0-only"},
            "node_modules/demo-mit": {"version": "1.0.0", "license": "MIT"},
            "node_modules/demo-unknown": {"version": "2.0.0"},
        },
    })
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("package.json", manifest)
        archive.writestr("package-lock.json", lock)
        archive.writestr("LICENSE", "Root license must not be inherited by dependencies.")
    boundary = "openguard-independent-license-boundary"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="source_type"\r\n\r\nzip\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="idempotency_key"\r\n\r\nlicense-{lock_version}\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="license-demo.zip"\r\n'
        'Content-Type: application/zip\r\n\r\n'
    ).encode() + data.getvalue() + f"\r\n--{boundary}--\r\n".encode()
    env = {**os.environ, "PYTHONPATH": str(root / "backend"), "PYTHONDONTWRITEBYTECODE": "1",
           "OPENGUARD_DATA_DIR": str(tmp_path / "data"), "OPENGUARD_ENABLE_DURABLE_ZIP": "1",
           "OPENGUARD_ENABLE_AI": "0", "OPENGUARD_ENABLE_PUBLIC_GIT": "0"}
    downloaded: dict[str, bytes] = {}
    scan_id = None
    for boot in range(2):
        with socket.socket() as listener, (tmp_path / f"server-{boot}.log").open("wb") as log:
            listener.bind(("127.0.0.1", 0))
            listener.listen(16)
            port = listener.getsockname()[1]
            process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app.api.main:create_default_app", "--factory", "--fd", str(listener.fileno()), "--log-level", "error"],
                cwd=root, env=env, pass_fds=(listener.fileno(),), stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            )
            def request(path: str, payload: bytes | None = None):
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                try:
                    connection.request("GET" if payload is None else "POST", path, body=payload,
                                       headers={} if payload is None else {"Content-Type": f"multipart/form-data; boundary={boundary}"})
                    response = connection.getresponse()
                    return response.status, dict(response.getheaders()), response.read()
                finally:
                    connection.close()
            try:
                deadline = time.monotonic() + 15
                while True:
                    assert process.poll() is None, (tmp_path / f"server-{boot}.log").read_text()
                    try:
                        if request("/openapi.json")[0] == 200:
                            break
                    except (OSError, http.client.HTTPException):
                        pass
                    assert time.monotonic() < deadline
                    time.sleep(0.05)
                if boot == 0:
                    status, _, accepted_bytes = request("/api/v1/scans", body)
                    assert status == 202
                    accepted = json.loads(accepted_bytes)
                    scan_id = accepted["scan_id"]
                    assert accepted["status"] == "queued"
                deadline = time.monotonic() + 20
                while True:
                    status, _, content = request(f"/api/v1/scans/{scan_id}")
                    assert status == 200
                    state = json.loads(content)
                    if state["status"] not in {"queued", "running"}:
                        break
                    assert time.monotonic() < deadline
                    time.sleep(0.05)
                assert state["status"] == "completed", state
                assert state["stage"] == "completed" and state["progress"] == 100
                assert state["summary"]["component_count"] == 2
                assert state["summary"]["finding_counts"]["review_required"] == 2
                status, _, content = request(f"/api/v1/scans/{scan_id}/resources")
                assert status == 200
                resources = {x["resource"]["name"]: x["resource"] for x in json.loads(content)["items"]}
                assert set(resources) == {"demo-mit", "demo-unknown"}
                status, _, content = request(f"/api/v1/scans/{scan_id}/risks")
                assert status == 200
                risks = json.loads(content)["items"]
                assert len(risks) == 2
                for risk in risks:
                    assert risk["outcome"] == "review_required" and risk["rule_id"] == "license-evidence-gate"
                    assert risk["evidence_ids"]
                    for evidence_id in risk["evidence_ids"]:
                        assert request(f"/api/v1/scans/{scan_id}/evidence/{evidence_id}")[0] == 200
                for fmt in ("json", "html", "csv", "resource_inventory"):
                    status, _, content = request(f"/api/v1/scans/{scan_id}/report?format={fmt}")
                    assert status == 200
                    link = json.loads(content)
                    status, headers, content = request(f"/api/v1/scans/{scan_id}/report?format={fmt}&download=true")
                    assert status == 200
                    digest = hashlib.sha256(content).hexdigest()
                    assert digest == link["content_hash"]["value"]
                    assert headers["etag"] == f'"sha256:{digest}"'
                    assert headers["content-digest"] == f'sha-256=:{base64.b64encode(bytes.fromhex(digest)).decode() }:'
                    if boot:
                        assert content == downloaded[fmt]
                    else:
                        downloaded[fmt] = content
                exported = json.loads(downloaded["json"])["scan_run"]
                assert exported["provenance"]["input_digest"]["value"] == hashlib.sha256(data.getvalue()).hexdigest()
                licenses = {x["id"]: x for x in exported["licenses"]}
                assert licenses[resources["demo-mit"]["license_expression_id"]]["expression"] == "MIT"
                assert licenses[resources["demo-unknown"]["license_expression_id"]]["expression"] == "NOASSERTION"
                assert all(x["verification_status"] == "pending" for x in licenses.values())
                assert not exported["obligations"] and not exported["remediations"]
                assert exported["provenance"]["ai_enabled"] is False
                evidence = {x["id"]: x for x in exported["evidence"]}
                mit = licenses[resources["demo-mit"]["license_expression_id"]]
                observations = [evidence[i] for i in mit["evidence_ids"]]
                assert any(x["locator"] == "package-lock.json:/packages/node_modules~1demo-mit/license"
                           and x["content_hash"]["value"] == hashlib.sha256(lock.encode()).hexdigest()
                           and x["verification_status"] == "pending" for x in observations)
                assert b"MIT" in downloaded["html"] and b"demo-unknown" in downloaded["csv"]
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                    pytest.fail("server did not shut down")


def test_large_valid_zip_does_not_lose_dependency_results_to_license_reread(tmp_path: Path) -> None:
    files = {}
    for index in range(4):
        name = f"dep-{index}"
        files[f"p{index}/package.json"] = json.dumps({"dependencies": {name: "1.0.0"}})
        files[f"p{index}/package-lock.json"] = json.dumps({
            "lockfileVersion": 3,
            "packages": {f"node_modules/{name}": {"version": "1.0.0"}},
            "padding": ["x" * 4000] * 410,
        })
    archive = tmp_path / "large-valid.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as zipped:
        for name, content in files.items():
            zipped.writestr(name, content)
    database, result, _ = _execute(tmp_path, archive, _queued(archive, 250))
    registry = SQLiteScanRunRegistry(database)
    try:
        final = registry.get(result.run.id).run
    finally:
        registry.close()
    assert final.status is ScanStatus.PARTIAL
    assert final.stage is ScanStage.RULES
    assert final.progress == 70
    assert len(final.components) == 4
    assert not final.licenses and not final.findings
    assert [x.code for x in final.errors] == ["rules_stage_not_connected"]
