"""Luna independent verification for B1-2 mapper and Python dependency CLI."""

from __future__ import annotations

import builtins
import io
import json
import socket
import subprocess
import zipfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, unquote

import pytest

from app import cli
from app.ingestion import ScanReadLimits, ZipIngestionService
from app.scanners import (
    DependencyScope,
    DependencySourceKind,
    ManifestKind,
    ParseStatus,
    PythonManifestParseResult,
    map_python_manifest_result,
    parse_python_manifests,
)
from app.scanners.python_manifest import (
    ManifestEvidenceDraft,
    ParsedManifest,
    ParserDiagnostic,
    PythonDependencyDeclaration,
)
from app.security.errors import IngestionSecurityError


ROOT_ZERO = "0" * 64
HASH_ONE = "1" * 64
FIXED = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
READ_LIMITS = ScanReadLimits(single_file_max_bytes=262_144, total_max_bytes=4_194_304)

POSITIVE_IDS = (
    "POS-B1-MAP-001", "POS-B1-MAP-002", "POS-B1-MAP-003", "POS-B1-MAP-004",
    "POS-B1-MAP-005", "POS-B1-MAP-006", "POS-B1-MAP-007", "POS-B1-MAP-008",
    "POS-B1-MAP-009", "POS-B1-MAP-010", "POS-B1-MAP-011", "POS-B1-MAP-012",
)
NEGATIVE_IDS = (
    "NEG-B1-MAP-001", "NEG-B1-MAP-002", "NEG-B1-MAP-003", "NEG-B1-MAP-004",
    "NEG-B1-MAP-005", "NEG-B1-MAP-006", "NEG-B1-MAP-007", "NEG-B1-MAP-008",
    "NEG-B1-MAP-009", "NEG-B1-MAP-010", "NEG-B1-MAP-011", "NEG-B1-MAP-012",
    "NEG-B1-MAP-013", "NEG-B1-MAP-014", "NEG-B1-MAP-015", "NEG-B1-MAP-016",
    "NEG-B1-MAP-017", "NEG-B1-MAP-018",
)
assert len(POSITIVE_IDS) == 12
assert len(NEGATIVE_IDS) == 18


def _zip_bytes(entries: dict[str, bytes | str]) -> io.BytesIO:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for path, value in entries.items():
            archive.writestr(path, value.encode("utf-8") if isinstance(value, str) else value)
    stream.seek(0)
    return stream


def _archive(path: Path, entries: dict[str, bytes | str]) -> None:
    path.write_bytes(_zip_bytes(entries).getvalue())


def _run_parser(
    tmp_path: Path,
    entries: dict[str, bytes | str],
    *,
    consumer,
):
    root = tmp_path / "workspace"
    root.mkdir(mode=0o700, parents=True)
    service = ZipIngestionService(root)
    outcome = None
    failure: BaseException | None = None
    try:
        outcome = service.ingest_with_consumer(_zip_bytes(entries), consumer, read_limits=READ_LIMITS)
    except BaseException as error:
        failure = error
    finally:
        service.close()
    return outcome, failure, root


def _parsed(tmp_path: Path, entries: dict[str, bytes | str]):
    outcome, failure, root = _run_parser(tmp_path, entries, consumer=parse_python_manifests)
    assert failure is None
    assert outcome is not None
    assert list(root.iterdir()) == []
    return outcome.consumer_result


def _mapped(tmp_path: Path, entries: dict[str, bytes | str], *, root_digest: str = ROOT_ZERO):
    def consume(session):
        parsed = parse_python_manifests(session)
        return map_python_manifest_result(parsed, root_digest=root_digest, observed_at=FIXED)

    outcome, failure, root = _run_parser(tmp_path, entries, consumer=consume)
    assert failure is None
    assert outcome is not None
    assert list(root.iterdir()) == []
    return outcome.consumer_result


def _invoke(arguments: list[str], *, clock=None) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    code = cli.main(arguments, stdout=stdout, stderr=stderr, clock=clock)
    return code, stdout.getvalue(), stderr.getvalue()


def _dto_base() -> PythonManifestParseResult:
    draft = ManifestEvidenceDraft("requirements.txt", None, 1, 1, HASH_ONE, "requests==2.32.5")
    declaration = PythonDependencyDeclaration(
        "requests",
        "requests",
        "==2.32.5",
        None,
        (),
        None,
        DependencySourceKind.INDEX,
        DependencyScope.RUNTIME,
        None,
        (),
        "requests==2.32.5",
        "requirements.txt",
        (draft,),
    )
    manifest = ParsedManifest("requirements.txt", ManifestKind.REQUIREMENTS, 17, HASH_ONE, ParseStatus.COMPLETE)
    return PythonManifestParseResult(
        "b1-python-manifest/v1",
        ParseStatus.COMPLETE,
        (manifest,),
        (declaration,),
        (),
    )


def _map_direct(result: PythonManifestParseResult, *, root_digest: str = ROOT_ZERO, observed_at: datetime = FIXED):
    return map_python_manifest_result(result, root_digest=root_digest, observed_at=observed_at)


def test_pos_b1_map_001_full_p0_exact_pin_and_known_fields(tmp_path: Path) -> None:
    result = _map_direct(_dto_base())
    component, evidence = result.components[0], result.evidence[0]
    assert component.id == "cmp_d2c4370f-4dee-58e4-a924-5c0ca9589acf"
    assert evidence.id == "evd_62a3eee2-9135-53d4-95cb-bd48e7fcbdfe"
    assert component.model_dump(mode="json") == {
        "id": component.id, "name": "requests", "version": "2.32.5", "ecosystem": "pypi",
        "component_type": "library", "purl": None, "source_url": None, "license_expression_id": None,
        "evidence_ids": [evidence.id], "detected_by": ["manifest_parser"], "confidence": 1.0,
    }
    assert evidence.model_dump(mode="json") == {
        "id": evidence.id, "kind": "manifest_field", "locator": "requirements.txt",
        "excerpt": "requests==2.32.5", "start_line": 1, "end_line": 1,
        "content_hash": {"algorithm": "sha256", "value": HASH_ONE},
        "detected_by": "manifest_parser",
        "producer": {"type": "parser", "name": "openguard-python-manifest-parser", "version": "0.1.0",
                     "config_digest": None, "provider": None, "model_id": None, "prompt_schema_digest": None},
        "observed_at": "2026-01-02T03:04:05Z", "verification_status": "verified",
    }


def test_pos_b1_map_002_non_pins_are_unresolved_but_evidence_is_retained(tmp_path: Path) -> None:
    result = _mapped(
        tmp_path,
        {"requirements.txt": "a\nb>=1\nc~=2.0\nd==3.*\ne==4 ; python_version > '3'\nf[extra]\n"},
    )
    assert len(result.components) == 6
    assert all(item.version is None and item.purl is None and item.source_url is None and item.license_expression_id is None for item in result.components)
    assert all(item.detected_by == ["manifest_parser"] and item.confidence == 1.0 and item.evidence_ids for item in result.components)
    assert len(result.evidence) == 6


def test_pos_b1_map_003_direct_https_only_sets_source_url_without_fetch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args, **kwargs):
        raise AssertionError("network access is outside B1-2")
    monkeypatch.setattr(socket, "socket", blocked)
    result = _mapped(tmp_path, {"requirements.txt": "demo @ https://EXAMPLE.org/pkg.whl\n"})
    component = result.components[0]
    assert component.source_url == "https://example.org/pkg.whl"
    assert component.version is None and component.purl is None and component.license_expression_id is None


def test_pos_b1_map_004_vcs_is_evidence_only(tmp_path: Path) -> None:
    result = _mapped(tmp_path, {"requirements.txt": "demo @ git+https://example.org/demo.git@v1\n"})
    assert result.components[0].source_url is None and result.components[0].version is None
    assert "git+https://example.org/demo.git@v1" in result.evidence[0].excerpt


def test_pos_b1_map_005_merges_duplicate_and_cross_scope_evidence(tmp_path: Path) -> None:
    result = _mapped(
        tmp_path,
        {
            "requirements.txt": "requests==2.32.5\n",
            "pyproject.toml": "[project.optional-dependencies]\nextra=['requests==2.32.5']\n",
        },
    )
    assert len(result.components) == 1
    assert len(result.components[0].evidence_ids) == 2
    assert result.components[0].evidence_ids == sorted(set(result.components[0].evidence_ids))


def test_pos_b1_map_006_conflict_keeps_diagnostics_and_does_not_choose_first(tmp_path: Path) -> None:
    result = _mapped(tmp_path, {"requirements.txt": "demo==1\ndemo==2\n"})
    assert result.status is ParseStatus.PARTIAL
    assert result.components[0].version is None
    assert {item.code for item in result.diagnostics} == {"dependency_declaration_conflict"}
    assert len(result.evidence) == 2


def test_pos_b1_map_007_locator_percent_encoding_round_trips_paths(tmp_path: Path) -> None:
    path = "dir/a:b% c/pyproject.toml"
    result = _mapped(tmp_path, {path: "[project]\ndependencies=['requests==1']\n"})
    locator = result.evidence[0].locator
    assert locator == "dir/a%3Ab%25%20c/pyproject.toml:project.dependencies[0]"
    assert unquote(locator.split(":", 1)[0]) == path.rsplit("/", 1)[0] + "/pyproject.toml"
    assert quote(unquote(locator.split(":", 1)[0]), safe="/-._~") == locator.split(":", 1)[0]


def test_pos_b1_map_008_known_answers_time_root_and_sort_are_deterministic() -> None:
    first = _map_direct(_dto_base(), observed_at=FIXED)
    second = _map_direct(_dto_base(), observed_at=FIXED)
    later = _map_direct(_dto_base(), observed_at=FIXED + timedelta(hours=1))
    other_root = _map_direct(_dto_base(), root_digest="2" * 64)
    assert first == second
    assert first.evidence[0].id == "evd_62a3eee2-9135-53d4-95cb-bd48e7fcbdfe"
    assert first.components[0].id == "cmp_d2c4370f-4dee-58e4-a924-5c0ca9589acf"
    assert first.evidence[0].observed_at != later.evidence[0].observed_at
    assert first.evidence[0].id == later.evidence[0].id
    assert first.evidence[0].id != other_root.evidence[0].id


def test_pos_b1_map_009_partial_diagnostics_keep_all_seven_fields(tmp_path: Path) -> None:
    parsed = _parsed(tmp_path, {"requirements.txt": "requests==1\n", "pyproject.toml": "[project\n"})
    result = _map_direct(parsed)
    assert result.status is ParseStatus.PARTIAL
    diagnostic = result.diagnostics[0]
    assert set(diagnostic.__dict__) == {"code", "severity", "manifest_path", "field_locator", "start_line", "end_line", "message"}
    assert diagnostic.code == "manifest_toml_invalid"
    assert result.components[0].name == "requests"


def test_pos_b1_map_010_legacy_cli_bytes_and_no_new_stage_clock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "legacy.zip"
    _archive(archive, {"file.txt": b"module entrypoint"})
    forbidden = []
    original_import = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        if name.startswith("app.scanners"):
            forbidden.append(name)
            raise AssertionError("legacy mode imported B1 stage")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    code, stdout, stderr = _invoke([str(archive)], clock=lambda: (_ for _ in ()).throw(AssertionError("clock called")))
    assert (code, stderr) == (0, "")
    assert stdout == '{"entries":[{"relative_path":"file.txt","sha256":"cdccd888b48591016a5b2bc785bf0dab3f9bb9b9f5a0f71d24e5ed5a5a921736","size_bytes":17}],"root_digest":"36bb7749c4bb61b59d4471be2dfd75e3c64d34fe3f7ebc7576e3d4906b7dd21e","schema":"openguard.zip-inventory","version":"1"}\n'
    assert forbidden == []


def test_pos_b1_map_011_new_cli_fixed_clock_is_byte_stable_and_cleans(tmp_path: Path) -> None:
    archive = tmp_path / "complete.zip"
    _archive(archive, {"requirements.txt": "requests==2.32.5\n"})
    code1, out1, err1 = _invoke(["--python-dependencies", str(archive)], clock=lambda: FIXED)
    code2, out2, err2 = _invoke(["--python-dependencies", str(archive)], clock=lambda: FIXED)
    payload = json.loads(out1)
    assert (code1, code2, err1, err2) == (0, 0, "", "")
    assert out1 == out2 and payload["schema"] == "openguard.python-dependencies"
    assert payload["status"] == "complete" and payload["root_digest"]
    assert payload["components"][0]["id"].startswith("cmp_")
    assert payload["components"][0]["name"] == "requests"


def test_pos_b1_map_012_new_cli_partial_is_complete_json_without_side_effects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "partial.zip"
    _archive(archive, {"requirements.txt": "requests==1\nnot a requirement\n", "target.py": "raise RuntimeError('must not run')"})
    monkeypatch.setattr(socket, "socket", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("process")))
    code, stdout, stderr = _invoke(["--python-dependencies", str(archive)], clock=lambda: FIXED)
    payload = json.loads(stdout)
    assert code == 0 and stderr == "" and payload["status"] == "partial"
    assert payload["components"] and payload["diagnostics"]
    assert "target.py" not in stdout and "RuntimeError" not in stdout


def test_neg_b1_map_001_rejects_wrong_schema_status_and_diagnostic_invariant() -> None:
    base = _dto_base()
    cases = (
        replace(base, schema_version="wrong"),
        replace(base, status=ParseStatus.PARTIAL),
        replace(base, diagnostics=(ParserDiagnostic("x", "error", None, None, None, None, "x"),)),
        replace(base, manifests=(replace(base.manifests[0], status=ParseStatus.PARTIAL),)),
    )
    for case in cases:
        with pytest.raises(IngestionSecurityError, match="scanner_failed:python_p0_mapper_failed"):
            _map_direct(case)


def test_neg_b1_map_002_rejects_noncanonical_root_digest() -> None:
    for digest in ("A" * 64, "f" * 63, "g" * 64):
        with pytest.raises(IngestionSecurityError, match="scanner_failed:python_p0_mapper_failed"):
            _map_direct(_dto_base(), root_digest=digest)


def test_neg_b1_map_003_rejects_naive_non_utc_and_clock_failures(tmp_path: Path) -> None:
    for when in (datetime(2026, 1, 1), datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=8)))):
        with pytest.raises(IngestionSecurityError, match="scanner_failed:python_p0_mapper_failed"):
            _map_direct(_dto_base(), observed_at=when)
    archive = tmp_path / "clock.zip"
    _archive(archive, {"requirements.txt": "a==1\n"})
    code, stdout, stderr = _invoke(["--python-dependencies", str(archive)], clock=lambda: (_ for _ in ()).throw(ValueError("secret path")))
    assert (code, stdout, stderr) == (1, "", "scanner_failed:cli_runtime_failed\n")


def test_neg_b1_map_004_rejects_missing_manifest_hash_and_empty_evidence() -> None:
    base = _dto_base()
    missing = replace(base.dependencies[0].evidence[0], manifest_path="missing.txt")
    mismatched = replace(base.dependencies[0].evidence[0], content_sha256="2" * 64)
    empty_dependency = replace(base.dependencies[0], evidence=())
    for draft, dependency in ((missing, replace(base.dependencies[0], evidence=(missing,))), (mismatched, replace(base.dependencies[0], evidence=(mismatched,)))):
        with pytest.raises(IngestionSecurityError, match="scanner_failed:python_p0_mapper_failed"):
            _map_direct(replace(base, dependencies=(dependency,)))
    with pytest.raises(IngestionSecurityError, match="scanner_failed:python_p0_mapper_failed"):
        _map_direct(replace(base, dependencies=(empty_dependency,)))


def test_neg_b1_map_005_rejects_illegal_line_field_and_noncanonical_percent_locator() -> None:
    base = _dto_base()
    drafts = (
        replace(base.dependencies[0].evidence[0], field_locator="project.dependencies[0]", start_line=1, end_line=1),
        replace(base.dependencies[0].evidence[0], field_locator="project.dependencies[-1]", start_line=None, end_line=None),
        replace(base.dependencies[0].evidence[0], field_locator="project.optional-dependencies.dev%2ftest[0]", start_line=None, end_line=None),
    )
    for draft in drafts:
        with pytest.raises(IngestionSecurityError, match="scanner_failed:python_p0_mapper_failed"):
            _map_direct(replace(base, dependencies=(replace(base.dependencies[0], evidence=(draft,)),)))


def test_neg_b1_map_006_rejects_empty_oversize_and_sensitive_evidence() -> None:
    base = _dto_base()
    drafts = (
        replace(base.dependencies[0].evidence[0], excerpt=""),
        replace(base.dependencies[0].evidence[0], excerpt="x" * 1001),
        replace(base.dependencies[0].evidence[0], excerpt="api_key=secret"),
        replace(base.dependencies[0].evidence[0], manifest_path="x" * 2049),
    )
    for draft in drafts:
        with pytest.raises(IngestionSecurityError, match="scanner_failed:python_p0_mapper_failed"):
            _map_direct(replace(base, dependencies=(replace(base.dependencies[0], evidence=(draft,)),)))


def test_neg_b1_map_007_rejects_duplicate_manifest_and_conflicting_evidence_identity() -> None:
    base = _dto_base()
    duplicate_manifest = replace(base, manifests=(base.manifests[0], base.manifests[0]))
    with pytest.raises(IngestionSecurityError, match="scanner_failed:python_p0_mapper_failed"):
        _map_direct(duplicate_manifest)
    second = replace(base.dependencies[0], evidence=(base.dependencies[0].evidence[0], replace(base.dependencies[0].evidence[0], excerpt="requests==2.32.6")))
    with pytest.raises(IngestionSecurityError, match="scanner_failed:python_p0_mapper_failed"):
        _map_direct(replace(base, dependencies=(second,)))


def test_neg_b1_map_008_rejects_malformed_name_scope_source_and_direct_reference() -> None:
    base = _dto_base()
    cases = (
        replace(base.dependencies[0], normalized_name="Requests"),
        replace(base.dependencies[0], scope=DependencyScope.OPTIONAL),
        replace(base.dependencies[0], source_kind=DependencySourceKind.INDEX, direct_reference="https://example.org/a"),
        replace(base.dependencies[0], source_kind=DependencySourceKind.VCS, direct_reference="https://example.org/a"),
    )
    for dependency in cases:
        with pytest.raises(IngestionSecurityError, match="scanner_failed:python_p0_mapper_failed"):
            _map_direct(replace(base, dependencies=(dependency,)))


def test_neg_b1_map_009_wildcard_arbitrary_equality_marker_and_conflict_are_unversioned(tmp_path: Path) -> None:
    parsed = _parsed(tmp_path, {"requirements.txt": "a==1.*\nb===2\nc>=1,<2\nd==3 ; python_version > '3'\ne==4\ne==5\n"})
    result = _map_direct(parsed)
    assert all(component.version is None for component in result.components)


def test_neg_b1_map_010_mixed_sources_do_not_choose_a_source_url(tmp_path: Path) -> None:
    parsed = _parsed(tmp_path, {"requirements.txt": "demo @ https://example.org/a\ndemo @ https://example.org/b\nother @ git+https://example.org/o.git\n"})
    result = _map_direct(parsed)
    assert all(component.source_url is None for component in result.components)
    assert len(result.evidence) == 3


def test_neg_b1_map_011_p0_constructor_failure_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.scanners.python_p0_mapper as mapper_module
    monkeypatch.setattr(mapper_module, "Component", lambda **kwargs: (_ for _ in ()).throw(ValueError("Pydantic path leak")))
    with pytest.raises(IngestionSecurityError) as error:
        _map_direct(_dto_base())
    assert str(error.value) == "scanner_failed:python_p0_mapper_failed"
    assert "Pydantic" not in str(error.value)


def test_neg_b1_map_012_bad_zip_and_unsafe_path_are_empty_and_sanitized(tmp_path: Path) -> None:
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not zip")
    unsafe = tmp_path / "unsafe.zip"
    _archive(unsafe, {"../escape.txt": "blocked"})
    for archive in (bad, unsafe):
        code, stdout, stderr = _invoke(["--python-dependencies", str(archive)], clock=lambda: FIXED)
        assert code == 1 and stdout == "" and "/" not in stderr and "Traceback" not in stderr


def test_neg_b1_map_013_parser_sentinel_reason_survives_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "parser.zip"
    _archive(archive, {"requirements.txt": "a==1\n"})
    def unavailable(session):
        raise IngestionSecurityError("scanner_failed", "python_manifest_parser_unavailable")
    monkeypatch.setattr("app.scanners.parse_python_manifests", unavailable)
    code, stdout, stderr = _invoke(["--python-dependencies", str(archive)], clock=lambda: FIXED)
    assert (code, stdout, stderr) == (1, "", "scanner_failed:python_manifest_parser_unavailable\n")


def test_neg_b1_map_014_mapper_sentinel_reason_survives_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "mapper.zip"
    _archive(archive, {"requirements.txt": "a==1\n"})
    def failed(*args, **kwargs):
        raise IngestionSecurityError("scanner_failed", "python_p0_mapper_failed")
    monkeypatch.setattr("app.scanners.map_python_manifest_result", failed)
    code, stdout, stderr = _invoke(["--python-dependencies", str(archive)], clock=lambda: FIXED)
    assert (code, stdout, stderr) == (1, "", "scanner_failed:python_p0_mapper_failed\n")


def test_neg_b1_map_015_unclassified_cli_errors_are_one_line_runtime_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "runtime.zip"
    _archive(archive, {"requirements.txt": "a==1\n"})
    monkeypatch.setattr("app.scanners.parse_python_manifests", lambda session: (_ for _ in ()).throw(RuntimeError("secret")))
    code, stdout, stderr = _invoke(["--python-dependencies", str(archive)], clock=lambda: FIXED)
    assert (code, stdout, stderr) == (1, "", "scanner_failed:cli_runtime_failed\n")


def test_neg_b1_map_016_flag_misuse_and_single_unknown_flag_keep_legacy_bytes(tmp_path: Path) -> None:
    for args in ([], ["--python-dependencies", "a.zip", "extra"], ["a.zip", "--python-dependencies"], ["--python-dependencies", "a.zip", "--python-dependencies"]):
        assert _invoke(args) == (2, "", "invalid_request:invalid_arguments\n")
    assert _invoke(["--unknown-flag"]) == (2, "", "invalid_request:input_file_unavailable\n")


def test_neg_b1_map_017_no_network_process_target_import_or_bypass_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "side-effects.zip"
    _archive(archive, {"requirements.txt": "a==1\n", "target.py": "import socket; subprocess.run(['danger'])"})
    monkeypatch.setattr(socket, "socket", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("process")))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("process")))
    original_open = builtins.open
    def deny_absolute(file, *args, **kwargs):
        if isinstance(file, (str, Path)) and str(file).startswith("/"):
            raise AssertionError("bypass open")
        return original_open(file, *args, **kwargs)
    monkeypatch.setattr(builtins, "open", deny_absolute)
    code, stdout, stderr = _invoke(["--python-dependencies", str(archive)], clock=lambda: FIXED)
    assert code == 0 and stderr == "" and json.loads(stdout)["components"]


def test_neg_b1_map_018_success_partial_and_failure_paths_leave_workspace_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "workspace-root"
    root.mkdir(mode=0o700)
    good = tmp_path / "good.zip"
    partial = tmp_path / "partial.zip"
    bad = tmp_path / "bad.zip"
    _archive(good, {"requirements.txt": "a==1\n"})
    _archive(partial, {"requirements.txt": "a==1\n", "pyproject.toml": "[project\n"})
    bad.write_bytes(b"bad")
    for archive in (good, partial):
        result = cli.run_local_zip_python_dependencies(archive, root, clock=lambda: FIXED)
        assert result[1].status in {ParseStatus.COMPLETE, ParseStatus.PARTIAL}
        assert list(root.iterdir()) == []
    with pytest.raises(IngestionSecurityError):
        cli.run_local_zip_python_dependencies(bad, root, clock=lambda: FIXED)
    assert list(root.iterdir()) == []


def test_final_b1p0_001_rejects_noncanonical_complete_optional_group_and_accepts_legal_group(tmp_path: Path) -> None:
    """FINAL-B1P0-001: the complete encoded optional group must round-trip canonically."""
    base = _dto_base()
    manifest = replace(base.manifests[0], relative_path="pyproject.toml", kind=ManifestKind.PYPROJECT)
    draft = replace(
        base.dependencies[0].evidence[0],
        manifest_path="pyproject.toml",
        field_locator="project.optional-dependencies.dev%2Efoo[0]",
        start_line=None,
        end_line=None,
    )
    dependency = replace(base.dependencies[0], source_manifest="pyproject.toml", evidence=(draft,))
    tampered = replace(base, manifests=(manifest,), dependencies=(dependency,))
    with pytest.raises(IngestionSecurityError) as error:
        _map_direct(tampered)
    assert str(error.value) == "scanner_failed:python_p0_mapper_failed"

    legal = _mapped(
        tmp_path,
        {"pyproject.toml": "[project.optional-dependencies]\n\"dev.foo\"=['requests==2.32.5']\n"},
    )
    assert legal.components[0].version == "2.32.5"
    assert legal.evidence[0].locator.endswith(":project.optional-dependencies.dev.foo[0]")


def test_final_b1p0_002_rejects_tampered_dto_and_preserves_real_parser_paths(tmp_path: Path) -> None:
    """FINAL-B1P0-002: frozen DTO tampering is uniformly sanitized before P0 construction."""
    base = _dto_base()
    draft = base.dependencies[0].evidence[0]
    tampered_drafts = (
        replace(base.dependencies[0], evidence=(draft, draft)),
        replace(base.dependencies[0], declared_name="not-requests"),
        replace(base.dependencies[0], raw_declaration="requests == 2.32.5"),
        replace(base.dependencies[0], direct_reference="https://example.org/pkg.whl?api_key=secret", source_kind=DependencySourceKind.DIRECT_URL),
    )
    for dependency in tampered_drafts:
        with pytest.raises(IngestionSecurityError) as error:
            _map_direct(replace(base, dependencies=(dependency,)))
        assert str(error.value) == "scanner_failed:python_p0_mapper_failed"

    diagnostics = (
        ParserDiagnostic("unexpected", "warning", "requirements.txt", None, 1, 1, "arbitrary"),
        ParserDiagnostic("unexpected", "error", "requirements.txt", None, 1, 1, "api_key=secret"),
    )
    for diagnostic in diagnostics:
        with pytest.raises(IngestionSecurityError) as error:
            _map_direct(replace(base, status=ParseStatus.PARTIAL, diagnostics=(diagnostic,)))
        assert str(error.value) == "scanner_failed:python_p0_mapper_failed"

    optional = _mapped(
        tmp_path / "optional",
        {"pyproject.toml": "[project.optional-dependencies]\ndev=['requests==2.32.5']\n"},
    )
    direct = _mapped(tmp_path / "direct", {"requirements.txt": "demo @ https://example.org/pkg.whl\n"})
    vcs = _mapped(tmp_path / "vcs", {"requirements.txt": "demo @ git+https://example.org/demo.git@v1\n"})
    diagnostic_result = _mapped(tmp_path / "diagnostic", {"requirements.txt": "a==1\n", "pyproject.toml": "[project\n"})
    assert optional.components[0].version == "2.32.5"
    assert direct.components[0].source_url == "https://example.org/pkg.whl"
    assert vcs.components[0].source_url is None
    assert diagnostic_result.status is ParseStatus.PARTIAL
