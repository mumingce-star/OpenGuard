"""Luna-owned independent B1-1 verification over the real A2-2 session."""

from __future__ import annotations

import builtins
import hashlib
import io
import os
import socket
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import get_type_hints

import pytest

from app.ingestion import ScanReadLimits, ZipIngestionService
from app.ingestion.inventory import Inventory, InventoryEntry
from app.scanners.python_manifest import (
    DependencyScope,
    DependencySourceKind,
    ManifestEvidenceDraft,
    ParseStatus,
    ParserDiagnostic,
    parse_python_manifests,
)
from app.security.errors import IngestionSecurityError


FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "b1-python-manifest"
READ_LIMITS = ScanReadLimits(single_file_max_bytes=262_144, total_max_bytes=4_194_304)
FROZEN_POSITIVE_IDS = (
    "POS-B1-PY-001", "POS-B1-PY-002", "POS-B1-PY-003", "POS-B1-PY-004",
    "POS-B1-PY-005", "POS-B1-PY-006", "POS-B1-PY-007", "POS-B1-PY-008",
    "POS-B1-PY-009", "POS-B1-PY-010", "POS-B1-PY-011", "POS-B1-PY-012",
)
FROZEN_NEGATIVE_IDS = (
    "NEG-B1-PY-001", "NEG-B1-PY-002", "NEG-B1-PY-003", "NEG-B1-PY-004",
    "NEG-B1-PY-005", "NEG-B1-PY-006", "NEG-B1-PY-007", "NEG-B1-PY-008",
    "NEG-B1-PY-009", "NEG-B1-PY-010", "NEG-B1-PY-011", "NEG-B1-PY-012",
    "NEG-B1-PY-013", "NEG-B1-PY-014", "NEG-B1-PY-015", "NEG-B1-PY-016",
    "NEG-B1-PY-017", "NEG-B1-PY-018", "NEG-B1-PY-019", "NEG-B1-PY-020",
    "NEG-B1-PY-021", "NEG-B1-PY-022", "NEG-B1-PY-023", "NEG-B1-PY-024",
)
assert len(FROZEN_POSITIVE_IDS) == 12
assert len(FROZEN_NEGATIVE_IDS) == 24


def _zip_bytes(entries: dict[str, bytes | str]) -> io.BytesIO:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for path, value in entries.items():
            archive.writestr(path, value.encode("utf-8") if isinstance(value, str) else value)
    stream.seek(0)
    return stream


def _capability_only(real_session, calls: list[str], forbidden: list[str]):
    """Expose only the frozen two-member parser capability and record access."""

    class CapabilityOnly:
        __slots__ = ("inventory",)

        def __init__(self) -> None:
            object.__setattr__(self, "inventory", real_session.inventory)

        def __getattribute__(self, name: str):
            if name in {"path", "root", "fd", "workspace", "open", "write", "stream", "fileno", "_session", "__dict__"}:
                forbidden.append(name)
                raise AssertionError(f"forbidden parser capability requested: {name}")
            return object.__getattribute__(self, name)

        def read_bytes(self, path: str, *, max_bytes: int | None = None) -> bytes:
            calls.append(path)
            return real_session.read_bytes(path, max_bytes=max_bytes)

    return CapabilityOnly()


def _run_zip(
    tmp_path: Path,
    entries: dict[str, bytes | str],
    *,
    capture_session: bool = False,
    capture_parser_error: bool = False,
):
    """Run the parser inside a real A2 ZIP consumer and retain observable state."""

    workspace_root = tmp_path / "scan-root"
    workspace_root.mkdir(mode=0o700, parents=True)
    service = ZipIngestionService(workspace_root)
    calls: list[str] = []
    forbidden: list[str] = []
    captured: list[object] = []

    def consume(real_session):
        if capture_session:
            captured.append(real_session)
        capability = _capability_only(real_session, calls, forbidden)
        try:
            return parse_python_manifests(capability)
        except IngestionSecurityError as parser_error:
            if not capture_parser_error:
                raise
            captured.append(parser_error)
            return None

    result = None
    error: BaseException | None = None
    try:
        result = service.ingest_with_consumer(_zip_bytes(entries), consume, read_limits=READ_LIMITS)
    except BaseException as caught:
        error = caught
    finally:
        service.close()
    return result, error, calls, forbidden, captured, workspace_root


def _diagnostic_codes(result) -> set[str]:
    return {diagnostic.code for diagnostic in result.consumer_result.diagnostics}


def _result(result):
    assert result is not None
    return result.consumer_result


def _assert_clean(root: Path) -> None:
    assert root.exists()
    assert list(root.iterdir()) == []


class IndependentDirectSession:
    """Minimal independent capability for parser-only failure semantics."""

    def __init__(self, values: dict[str, bytes], entries: tuple[InventoryEntry, ...] | None = None) -> None:
        self.values = values
        self.calls: list[str] = []
        inventory_entries = entries or tuple(
            InventoryEntry(path, len(data), hashlib.sha256(data).hexdigest()) for path, data in values.items()
        )
        self.inventory = Inventory(inventory_entries, "independent-root")

    def read_bytes(self, path: str, *, max_bytes: int) -> bytes:
        self.calls.append(path)
        assert max_bytes == 262_144
        return self.values[path]


def test_pos_b1_py_001_discovers_supported_candidates_in_stable_order(tmp_path: Path) -> None:
    result, error, calls, forbidden, _, root = _run_zip(
        tmp_path,
        {
            "z/requirements.txt": "z==1\n",
            ".venv/requirements.txt": "ignored==1\n",
            "a/pyproject.toml": "[project]\ndependencies=['a==1']\n",
            "vendor/requirements-dev.txt": "vendor==1\n",
            "requirements.in": "not a candidate\n",
            "Requirements.txt": "not a candidate\n",
        },
    )
    parsed = _result(result)
    assert error is None
    assert [item.relative_path for item in parsed.manifests] == [
        "a/pyproject.toml",
        "vendor/requirements-dev.txt",
        "z/requirements.txt",
    ]
    assert calls == ["a/pyproject.toml", "vendor/requirements-dev.txt", "z/requirements.txt"]
    assert forbidden == []
    _assert_clean(root)


def test_pos_b1_py_002_normalizes_requirement_name_extras_and_marker(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(
        tmp_path,
        {"requirements.txt": 'Requests[socks,TEST]>=2,<3 ; python_version < "3.14"\n'},
    )
    parsed = _result(result)
    assert error is None
    declaration = parsed.dependencies[0]
    assert declaration.normalized_name == "requests"
    assert declaration.extras == ("socks", "test")
    assert declaration.version_specifier == "<3,>=2"
    assert declaration.marker == 'python_version < "3.14"'
    assert parsed.status is ParseStatus.COMPLETE
    _assert_clean(root)


def test_pos_b1_py_003_preserves_continuation_line_evidence(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(
        tmp_path,
        {"requirements.txt": "a==1 \\\n  ; python_version > '3' # note\n"},
    )
    parsed = _result(result)
    assert error is None
    evidence = parsed.dependencies[0].evidence[0]
    assert evidence.start_line == 1
    assert evidence.end_line == 2
    assert parsed.dependencies[0].raw_declaration == 'a==1 ; python_version > "3"'
    _assert_clean(root)


def test_pos_b1_py_004_accepts_safe_https_direct_reference_without_fetching(tmp_path: Path) -> None:
    digest = "a" * 64
    result, error, _, _, _, root = _run_zip(
        tmp_path,
        {"requirements.txt": f"a @ https://EXAMPLE.org/pkg#sha256={digest}\n"},
    )
    parsed = _result(result)
    assert error is None
    declaration = parsed.dependencies[0]
    assert declaration.source_kind is DependencySourceKind.DIRECT_URL
    assert declaration.direct_reference == f"https://example.org/pkg#sha256={digest}"
    assert parsed.status is ParseStatus.COMPLETE
    _assert_clean(root)


def test_pos_b1_py_005_accepts_safe_git_https_reference_as_data(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(
        tmp_path,
        {"requirements.txt": "a @ git+https://example.org/pkg#subdirectory=src\n"},
    )
    parsed = _result(result)
    assert error is None
    assert parsed.dependencies[0].source_kind is DependencySourceKind.VCS
    assert parsed.dependencies[0].direct_reference == "git+https://example.org/pkg#subdirectory=src"
    _assert_clean(root)


def test_pos_b1_py_006_normalizes_duplicate_sha256_hashes(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(
        tmp_path,
        {"requirements.txt": "a==1 --hash=sha256:" + "A" * 64 + " --hash=sha256:" + "a" * 64 + "\n"},
    )
    parsed = _result(result)
    assert error is None
    assert parsed.dependencies[0].hashes == ("a" * 64,)
    assert parsed.dependencies[0].source_kind is DependencySourceKind.INDEX
    _assert_clean(root)


def test_pos_b1_py_007_maps_project_dependencies_with_field_locator(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(
        tmp_path,
        {"pyproject.toml": "[project]\ndependencies=['a==1']\n"},
    )
    parsed = _result(result)
    assert error is None
    declaration = parsed.dependencies[0]
    assert declaration.scope is DependencyScope.RUNTIME
    assert declaration.group is None
    assert declaration.evidence[0].field_locator == "project.dependencies[0]"
    _assert_clean(root)


def test_pos_b1_py_008_maps_optional_dependency_group_deterministically(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(
        tmp_path,
        {"pyproject.toml": "[project.optional-dependencies]\nDev_Test=['a==1']\n"},
    )
    parsed = _result(result)
    assert error is None
    declaration = parsed.dependencies[0]
    assert declaration.scope is DependencyScope.OPTIONAL
    assert declaration.group == "dev-test"
    assert declaration.evidence[0].field_locator == "project.optional-dependencies.Dev_Test[0]"
    _assert_clean(root)


def test_pos_b1_py_009_maps_build_system_requires_without_backend_execution(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(
        tmp_path,
        {"pyproject.toml": "[build-system]\nrequires=['setuptools>=1']\nbuild-backend='target:build'\n"},
    )
    parsed = _result(result)
    assert error is None
    declaration = parsed.dependencies[0]
    assert declaration.scope is DependencyScope.BUILD
    assert declaration.evidence[0].field_locator == "build-system.requires[0]"
    assert parsed.status is ParseStatus.COMPLETE
    _assert_clean(root)


def test_pos_b1_py_010_merges_duplicate_identity_and_keeps_both_evidence(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(
        tmp_path,
        {"requirements.txt": "a==1\n", "sub/requirements.txt": "a==1\n"},
    )
    parsed = _result(result)
    assert error is None
    assert len(parsed.dependencies) == 1
    assert len(parsed.dependencies[0].evidence) == 2
    assert _diagnostic_codes(result) == {"dependency_duplicate"}
    _assert_clean(root)


def test_pos_b1_py_011_returns_partial_with_valid_sibling_and_invalid_toml(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(
        tmp_path,
        {"requirements.txt": "a==1\n", "pyproject.toml": "[project\n"},
    )
    parsed = _result(result)
    assert error is None
    assert parsed.status is ParseStatus.PARTIAL
    assert [item.normalized_name for item in parsed.dependencies] == ["a"]
    assert "manifest_toml_invalid" in _diagnostic_codes(result)
    _assert_clean(root)


def test_pos_b1_py_012_returns_immutable_versioned_deterministic_result(tmp_path: Path) -> None:
    entries = {
        "requirements.txt": FIXTURE_DIR.joinpath("requirements-basic.txt").read_bytes(),
        "pyproject.toml": FIXTURE_DIR.joinpath("pyproject-basic.toml").read_bytes(),
    }
    first, first_error, _, _, _, first_root = _run_zip(tmp_path / "first", entries)
    second, second_error, _, _, _, second_root = _run_zip(tmp_path / "second", entries)
    first_parsed = _result(first)
    second_parsed = _result(second)
    assert first_error is None and second_error is None
    assert first_parsed == second_parsed
    assert first_parsed.schema_version == "b1-python-manifest/v1"
    assert isinstance(first_parsed.dependencies, tuple)
    _assert_clean(first_root)
    _assert_clean(second_root)


def test_neg_b1_py_001_rejects_invalid_utf8_without_partial_dependency(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(tmp_path, {"requirements.txt": b"\xff"})
    parsed = _result(result)
    assert error is None
    assert parsed.status is ParseStatus.PARTIAL
    assert parsed.dependencies == ()
    assert "manifest_encoding_invalid" in _diagnostic_codes(result)
    _assert_clean(root)


def test_neg_b1_py_002_rejects_invalid_toml(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(tmp_path, {"pyproject.toml": "[project\n"})
    parsed = _result(result)
    assert error is None
    assert parsed.status is ParseStatus.PARTIAL
    assert "manifest_toml_invalid" in _diagnostic_codes(result)
    _assert_clean(root)


def test_neg_b1_py_003_rejects_wrong_pyproject_dependency_field_type(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(tmp_path, {"pyproject.toml": "[project]\ndependencies='a==1'\n"})
    parsed = _result(result)
    assert error is None
    assert parsed.dependencies == ()
    assert "manifest_field_invalid" in _diagnostic_codes(result)
    _assert_clean(root)


def test_neg_b1_py_004_rejects_invalid_requirement(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(tmp_path, {"requirements.txt": "!!!\n"})
    parsed = _result(result)
    assert error is None
    assert parsed.dependencies == ()
    assert "requirement_invalid" in _diagnostic_codes(result)
    _assert_clean(root)


def test_neg_b1_py_005_rejects_requirement_include_directive(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(tmp_path, {"requirements.txt": "-r hidden.txt\n"})
    parsed = _result(result)
    assert error is None
    assert parsed.dependencies == ()
    assert "requirement_include_unsupported" in _diagnostic_codes(result)
    _assert_clean(root)


def test_neg_b1_py_006_rejects_constraint_directive(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(tmp_path, {"requirements.txt": "-c constraints.txt\na==1\n"})
    parsed = _result(result)
    assert error is None
    assert [item.normalized_name for item in parsed.dependencies] == ["a"]
    assert "requirement_constraint_unsupported" in _diagnostic_codes(result)
    _assert_clean(root)


def test_neg_b1_py_007_rejects_editable_directive(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(tmp_path, {"requirements.txt": "-e ./local\n"})
    parsed = _result(result)
    assert error is None
    assert parsed.dependencies == ()
    assert "requirement_editable_unsupported" in _diagnostic_codes(result)
    _assert_clean(root)


def test_neg_b1_py_008_rejects_option_without_echoing_option_value(tmp_path: Path) -> None:
    marker = "credential-marker"
    result, error, _, _, _, root = _run_zip(tmp_path, {"requirements.txt": f"--index-url https://token:{marker}@example.org/simple\n"})
    parsed = _result(result)
    assert error is None
    assert "requirement_option_unsupported" in _diagnostic_codes(result)
    assert marker not in repr(parsed.diagnostics)
    _assert_clean(root)


def test_neg_b1_py_009_rejects_unnamed_url_reference(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(tmp_path, {"requirements.txt": "https://example.org/a.whl\n"})
    parsed = _result(result)
    assert error is None
    assert parsed.dependencies == ()
    assert "requirement_unnamed_reference_unsupported" in _diagnostic_codes(result)
    _assert_clean(root)


def test_neg_b1_py_010_rejects_file_url_reference(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(tmp_path, {"requirements.txt": "a @ file:///tmp/target.whl\n"})
    parsed = _result(result)
    assert error is None
    assert parsed.dependencies == ()
    assert "requirement_reference_unsafe" in _diagnostic_codes(result)
    _assert_clean(root)


def test_neg_b1_py_011_rejects_url_credentials_and_query_without_leak(tmp_path: Path) -> None:
    marker = "credential-marker"
    result, error, _, _, _, root = _run_zip(tmp_path, {"requirements.txt": f"a @ https://user:{marker}@example.org/a?q=x\n"})
    parsed = _result(result)
    assert error is None
    assert parsed.dependencies == ()
    assert "requirement_reference_unsafe" in _diagnostic_codes(result)
    assert marker not in repr(parsed.diagnostics)
    _assert_clean(root)


def test_neg_b1_py_012_rejects_non_sha256_hash(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(tmp_path, {"requirements.txt": "a==1 --hash=md5:bad\n"})
    parsed = _result(result)
    assert error is None
    assert parsed.dependencies == ()
    assert "requirement_hash_invalid" in _diagnostic_codes(result)
    _assert_clean(root)


def test_neg_b1_py_013_retains_marker_without_evaluating_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    entries = {"requirements.txt": 'a==1 ; sys_platform == "never-evaluate"\n'}
    monkeypatch.setattr(sys, "platform", "win32")
    windows, windows_error, _, _, _, windows_root = _run_zip(tmp_path / "windows", entries)
    monkeypatch.setattr(sys, "platform", "linux")
    linux, linux_error, _, _, _, linux_root = _run_zip(tmp_path / "linux", entries)
    windows_parsed = _result(windows)
    linux_parsed = _result(linux)
    assert windows_error is None and linux_error is None
    assert windows_parsed == linux_parsed
    assert windows_parsed.dependencies[0].marker == 'sys_platform == "never-evaluate"'
    assert windows_parsed.status is ParseStatus.COMPLETE
    _assert_clean(windows_root)
    _assert_clean(linux_root)


def test_neg_b1_py_014_rejects_more_than_64_candidates_before_first_read(tmp_path: Path) -> None:
    entries = {f"d{i:02d}/requirements.txt": b"a==1\n" for i in range(65)}
    result, error, calls, _, captured, root = _run_zip(tmp_path, entries, capture_parser_error=True)
    assert error is None
    assert result is not None
    assert isinstance(captured[0], IngestionSecurityError)
    assert str(captured[0]) == "scanner_failed:python_manifest_limit_exceeded"
    assert calls == []
    _assert_clean(root)


def test_neg_b1_py_015_rejects_oversized_candidate_before_first_read(tmp_path: Path) -> None:
    result, error, calls, _, captured, root = _run_zip(tmp_path, {"requirements.txt": b"a" * 262_145}, capture_parser_error=True)
    assert error is None
    assert result is not None
    assert isinstance(captured[0], IngestionSecurityError)
    assert str(captured[0]) == "scanner_failed:python_manifest_limit_exceeded"
    assert calls == []
    _assert_clean(root)


def test_neg_b1_py_016_rejects_total_candidate_quota_before_first_read(tmp_path: Path) -> None:
    entries = {f"d{i:02d}/requirements.txt": b"a" * 250_000 for i in range(17)}
    result, error, calls, _, captured, root = _run_zip(tmp_path, entries, capture_parser_error=True)
    assert error is None
    assert result is not None
    assert isinstance(captured[0], IngestionSecurityError)
    assert str(captured[0]) == "scanner_failed:python_manifest_limit_exceeded"
    assert calls == []
    _assert_clean(root)


def test_neg_b1_py_017_rejects_logical_line_over_8192_bytes(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(tmp_path, {"requirements.txt": "a==1 # " + "x" * 8200 + "\n"})
    parsed = _result(result)
    assert error is None
    assert parsed.dependencies == ()
    assert "manifest_logical_line_too_long" in _diagnostic_codes(result)
    _assert_clean(root)


def test_neg_b1_py_018_rejects_more_than_4096_declarations(tmp_path: Path) -> None:
    entries = {"requirements.txt": "\n".join(f"a{i}==1" for i in range(4097)) + "\n"}
    result, error, calls, _, captured, root = _run_zip(tmp_path, entries, capture_parser_error=True)
    assert error is None
    assert result is not None
    assert isinstance(captured[0], IngestionSecurityError)
    assert str(captured[0]) == "scanner_failed:python_manifest_limit_exceeded"
    assert calls == ["requirements.txt"]
    _assert_clean(root)


def test_neg_b1_py_019_reports_conflicting_pins_and_keeps_declarations(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(tmp_path, {"requirements.txt": "a==1\na==2\n"})
    parsed = _result(result)
    assert error is None
    assert parsed.status is ParseStatus.PARTIAL
    assert {item.version_specifier for item in parsed.dependencies} == {"==1", "==2"}
    assert "dependency_declaration_conflict" in _diagnostic_codes(result)
    _assert_clean(root)


def test_neg_b1_py_020_rejects_dynamic_dependencies(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(
        tmp_path,
        {"pyproject.toml": "[project]\ndynamic=['dependencies']\n"},
    )
    parsed = _result(result)
    assert error is None
    assert parsed.dependencies == ()
    assert "pyproject_dynamic_dependencies_unsupported" in _diagnostic_codes(result)
    _assert_clean(root)


def test_neg_b1_py_021_uses_no_path_fd_or_workspace_capability(tmp_path: Path) -> None:
    result, error, calls, forbidden, _, root = _run_zip(tmp_path, {"requirements.txt": "a==1\n"})
    parsed = _result(result)
    assert error is None
    assert parsed.status is ParseStatus.COMPLETE
    assert calls == ["requirements.txt"]
    assert forbidden == []
    _assert_clean(root)


def test_neg_b1_py_022_rejects_tool_dependency_table_without_parsing_it(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(tmp_path, {"pyproject.toml": "[tool.poetry]\nname='target-project'\n"})
    parsed = _result(result)
    assert error is None
    assert parsed.dependencies == ()
    assert "pyproject_tool_table_unsupported" in _diagnostic_codes(result)
    assert "target-project" not in repr(parsed.diagnostics)
    _assert_clean(root)


def test_neg_b1_py_023_blocks_process_socket_open_and_target_import_side_effects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = tmp_path / "target-imported"
    target_code = f"open({str(sentinel)!r}, 'w').write('executed')\n"

    def forbidden_call(*args, **kwargs):
        raise AssertionError("unexpected target capability call")

    original_open = builtins.open

    result_holder = {}
    workspace_root = tmp_path / "scan-root"
    workspace_root.mkdir(mode=0o700)
    service = ZipIngestionService(workspace_root)

    def consume(real_session):
        monkeypatch.setattr(subprocess, "run", forbidden_call)
        monkeypatch.setattr(subprocess, "Popen", forbidden_call)
        monkeypatch.setattr(socket, "socket", forbidden_call)
        monkeypatch.setattr(builtins, "open", forbidden_call)
        capability = _capability_only(real_session, result_holder.setdefault("calls", []), result_holder.setdefault("forbidden", []))
        try:
            result_holder["parsed"] = parse_python_manifests(capability)
        finally:
            monkeypatch.setattr(builtins, "open", original_open)
        return result_holder["parsed"]

    try:
        service.ingest_with_consumer(
            _zip_bytes({"requirements.txt": "a==1\n", "target_side_effect.py": target_code}),
            consume,
            read_limits=READ_LIMITS,
        )
    finally:
        service.close()
    parsed = result_holder["parsed"]
    assert parsed.status is ParseStatus.COMPLETE
    assert result_holder["calls"] == ["requirements.txt"]
    assert result_holder["forbidden"] == []
    assert not sentinel.exists()
    _assert_clean(workspace_root)


def test_neg_b1_py_024_separates_packaging_failure_from_expired_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.scanners.python_manifest as module

    monkeypatch.setattr(module, "_packaging_version", "0")
    unavailable, unavailable_error, unavailable_calls, _, unavailable_captured, unavailable_root = _run_zip(
        tmp_path / "wrong-version", {"requirements.txt": "a==1\n"}, capture_parser_error=True
    )
    assert unavailable_error is None
    assert unavailable is not None
    assert isinstance(unavailable_captured[0], IngestionSecurityError)
    assert str(unavailable_captured[0]) == "scanner_failed:python_manifest_parser_unavailable"
    assert unavailable_calls == []
    _assert_clean(unavailable_root)

    monkeypatch.setattr(module, "_packaging_version", "26.3")
    result, error, _, _, captured, root = _run_zip(tmp_path / "expired", {"requirements.txt": "a==1\n"}, capture_session=True)
    assert error is None
    assert _result(result).status is ParseStatus.COMPLETE
    assert len(captured) == 1
    with pytest.raises(IngestionSecurityError) as expired:
        captured[0].inventory
    assert str(expired.value) == "scanner_failed:scan_session_expired"
    _assert_clean(root)


def test_amendment_dto_evidence_line_annotations_allow_none() -> None:
    assert get_type_hints(ManifestEvidenceDraft)["start_line"] == (int | None)
    assert get_type_hints(ManifestEvidenceDraft)["end_line"] == (int | None)


def test_amendment_pyproject_evidence_lines_are_none(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(tmp_path, {"pyproject.toml": "[project]\ndependencies=['a']\n"})
    parsed = _result(result)
    assert error is None
    evidence = parsed.dependencies[0].evidence[0]
    assert evidence.start_line is None
    assert evidence.end_line is None
    _assert_clean(root)


def test_amendment_bare_name_version_specifier_is_none(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(tmp_path, {"requirements.txt": "a\n"})
    parsed = _result(result)
    assert error is None
    assert parsed.dependencies[0].version_specifier is None
    _assert_clean(root)


def test_amendment_parser_diagnostic_manifest_path_is_optional_and_constructible() -> None:
    assert get_type_hints(ParserDiagnostic)["manifest_path"] == (str | None)
    diagnostic = ParserDiagnostic("code", "warning", None, None, None, None, "fixed")
    assert diagnostic.manifest_path is None


@pytest.mark.parametrize(
    "reference",
    [
        "a @ https://example.org/pkg#subdirectory=./a",
        "a @ https://example.org/pkg#subdirectory=a/./b",
        "a @ https://example.org/pkg#subdirectory=a/.",
        "a @ https://example.org/pkg#subdirectory=a/..",
    ],
)
def test_amendment_url_subdirectory_dot_segments_are_rejected(tmp_path: Path, reference: str) -> None:
    result, error, _, _, _, root = _run_zip(tmp_path, {"requirements.txt": reference + "\n"})
    parsed = _result(result)
    assert error is None
    assert parsed.dependencies == ()
    assert "requirement_reference_unsafe" in _diagnostic_codes(result)
    _assert_clean(root)


def test_amendment_url_duplicate_subdirectory_key_is_rejected(tmp_path: Path) -> None:
    reference = "a @ https://example.org/pkg#subdirectory=src&subdirectory=tests"
    result, error, _, _, _, root = _run_zip(tmp_path, {"requirements.txt": reference + "\n"})
    parsed = _result(result)
    assert error is None
    assert parsed.dependencies == ()
    assert "requirement_reference_unsafe" in _diagnostic_codes(result)
    _assert_clean(root)


def test_amendment_eof_dangling_backslash_is_invalid_and_produces_no_dependency(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(tmp_path, {"requirements.txt": "a==1 " + "\\"})
    parsed = _result(result)
    assert error is None
    assert parsed.dependencies == ()
    assert "requirement_invalid" in _diagnostic_codes(result)
    _assert_clean(root)


def test_amendment_top_level_dependency_groups_is_unsupported(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(
        tmp_path,
        {"pyproject.toml": "[dependency-groups]\ndev=['a==1']\n"},
    )
    parsed = _result(result)
    assert error is None
    assert parsed.dependencies == ()
    assert "pyproject_tool_table_unsupported" in _diagnostic_codes(result)
    _assert_clean(root)


def test_amendment_unexpected_toml_error_is_stable_and_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.scanners.python_manifest as module

    marker = "amendment-toml-marker"

    def explode(_text: str):
        raise RuntimeError(f"{marker} traceback")

    monkeypatch.setattr(module.tomllib, "loads", explode)
    session = IndependentDirectSession({"pyproject.toml": b"[project]\ndependencies=['a==1']\n"})
    with pytest.raises(IngestionSecurityError) as caught:
        parse_python_manifests(session)
    assert str(caught.value) == "scanner_failed:python_manifest_parser_failed"
    assert marker not in str(caught.value)


def test_amendment_unexpected_internal_parser_error_is_stable_and_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.scanners.python_manifest as module

    marker = "amendment-parser-marker"

    def explode(_text: str, _path: str, _sha256: str):
        raise RuntimeError(f"{marker} traceback")

    monkeypatch.setattr(module, "_requirements", explode)
    session = IndependentDirectSession({"requirements.txt": b"a==1\n"})
    with pytest.raises(IngestionSecurityError) as caught:
        parse_python_manifests(session)
    assert str(caught.value) == "scanner_failed:python_manifest_parser_failed"
    assert marker not in str(caught.value)


def test_amendment_duplicate_inventory_path_fails_before_duplicate_reads() -> None:
    data = b"a==1\n"
    entry = InventoryEntry("requirements.txt", len(data), hashlib.sha256(data).hexdigest())
    session = IndependentDirectSession({"requirements.txt": data}, (entry, entry))
    with pytest.raises(IngestionSecurityError) as caught:
        parse_python_manifests(session)
    assert str(caught.value) == "scanner_failed:python_manifest_parser_failed"
    assert session.calls == []


def test_amendment_canonical_raw_declaration_does_not_depend_on_input_whitespace(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(
        tmp_path,
        {"a/requirements.txt": "  a == 1  # alternate spelling\n", "z/requirements.txt": "a==1\n"},
    )
    parsed = _result(result)
    assert error is None
    assert len(parsed.dependencies) == 1
    assert parsed.dependencies[0].raw_declaration == "a==1"
    assert len(parsed.dependencies[0].evidence) == 2
    _assert_clean(root)


def test_amendment_canonical_raw_uses_normalized_name_and_packaging_marker(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(
        tmp_path,
        {
            "a/requirements.txt": 'Requests [ SOCKS ] >= 2 ; python_version<"3.14"\n',
            "z/requirements.txt": 'requests[socks]>=2; python_version < "3.14"\n',
        },
    )
    parsed = _result(result)
    assert error is None
    assert len(parsed.dependencies) == 1
    declaration = parsed.dependencies[0]
    assert declaration.normalized_name == "requests"
    assert declaration.marker == 'python_version < "3.14"'
    assert declaration.raw_declaration == 'requests[socks]>=2 ; python_version < "3.14"'
    assert len(declaration.evidence) == 2
    _assert_clean(root)


@pytest.mark.parametrize(
    "reference",
    [
        "a @ https://example.org/pkg#subdirectory=a//b",
        "a @ https://example.org/pkg#subdirectory=a/",
        "a @ https://example.org/pkg#subdirectory=a/%2F/b",
    ],
)
def test_amendment_url_subdirectory_empty_segments_are_rejected(tmp_path: Path, reference: str) -> None:
    result, error, _, _, _, root = _run_zip(tmp_path, {"requirements.txt": reference + "\n"})
    parsed = _result(result)
    assert error is None
    assert parsed.dependencies == ()
    assert "requirement_reference_unsafe" in _diagnostic_codes(result)
    _assert_clean(root)


def test_amendment_non_list_project_dynamic_is_invalid_field(tmp_path: Path) -> None:
    result, error, _, _, _, root = _run_zip(
        tmp_path,
        {"pyproject.toml": "[project]\ndynamic='dependencies'\n"},
    )
    parsed = _result(result)
    assert error is None
    assert parsed.status is ParseStatus.PARTIAL
    assert "manifest_field_invalid" in _diagnostic_codes(result)
    _assert_clean(root)


@pytest.mark.parametrize("value", ["a==1\u2028b==2\n", "\u2028a==1\n", "a==1\u2028\n"])
def test_p1_b1_final_001_unicode_line_separator_is_not_a_physical_line_break(tmp_path: Path, value: str) -> None:
    """P1-B1-FINAL-001: only CRLF/LF/CR delimit physical requirement lines."""
    result, error, _, _, _, root = _run_zip(tmp_path, {"requirements.txt": value})
    parsed = _result(result)
    assert error is None
    assert parsed.dependencies == ()
    assert "requirement_invalid" in _diagnostic_codes(result)
    assert parsed.manifests[0].status is ParseStatus.PARTIAL
    _assert_clean(root)


def test_p1_b1_final_002_1001_character_canonical_raw_is_rejected_and_bounded(tmp_path: Path) -> None:
    """P1-B1-FINAL-002: canonical raw output may not exceed 1000 code points."""
    reference = "https://example.org/" + "a" * 978
    assert len(reference) == 998
    result, error, _, _, _, root = _run_zip(tmp_path, {"requirements.txt": "a @ " + reference + "\n"})
    parsed = _result(result)
    assert error is None
    assert parsed.dependencies == ()
    assert "requirement_invalid" in _diagnostic_codes(result)
    assert all(len(item.message) <= 1000 for item in parsed.diagnostics)
    _assert_clean(root)


def test_p1_b1_final_003_extras_canonical_collision_is_deduplicated(tmp_path: Path) -> None:
    """P1-B1-FINAL-003: canonical extras x_y and x-y identify one extra."""
    result, error, _, _, _, root = _run_zip(tmp_path, {"requirements.txt": "a[x_y,x-y]\n"})
    parsed = _result(result)
    assert error is None
    declaration = parsed.dependencies[0]
    assert declaration.extras == ("x-y",)
    assert declaration.raw_declaration == "a[x-y]"
    assert parsed.status is ParseStatus.COMPLETE
    _assert_clean(root)


def test_p1_b1_final_004_none_version_sorts_before_nonempty_specifier(tmp_path: Path) -> None:
    """P1-B1-FINAL-004: None is the empty-bytes field in identity ordering."""
    result, error, _, _, _, root = _run_zip(tmp_path, {"requirements.txt": "a>=1\na\n"})
    parsed = _result(result)
    assert error is None
    assert [(item.normalized_name, item.version_specifier) for item in parsed.dependencies] == [("a", None), ("a", ">=1")]
    assert parsed.status is ParseStatus.PARTIAL
    assert "dependency_multiple_constraints" in _diagnostic_codes(result)
    _assert_clean(root)


def test_p1_b1_final_005_ipv6_https_reference_retains_brackets(tmp_path: Path) -> None:
    """P1-B1-FINAL-005: canonical HTTPS IPv6 hosts retain required brackets."""
    result, error, _, _, _, root = _run_zip(tmp_path, {"requirements.txt": "a @ https://[::1]/pkg\n"})
    parsed = _result(result)
    assert error is None
    declaration = parsed.dependencies[0]
    assert declaration.source_kind is DependencySourceKind.DIRECT_URL
    assert declaration.direct_reference == "https://[::1]/pkg"
    assert parsed.status is ParseStatus.COMPLETE
    _assert_clean(root)
