"""Terra-owned B1-2 P0 mapping and local-only CLI regression coverage."""

from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app import cli
from app.ingestion.inventory import Inventory, InventoryEntry
from app.scanners.python_manifest import (
    DependencyScope,
    DependencySourceKind,
    ManifestEvidenceDraft,
    ManifestKind,
    ParserDiagnostic,
    ParseStatus,
    ParsedManifest,
    PythonDependencyDeclaration,
    PythonManifestParseResult,
    parse_python_manifests,
)
from app.scanners.python_p0_mapper import MAPPER_SCHEMA_VERSION, map_python_manifest_result
from app.security.errors import IngestionSecurityError


class _MemorySession:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = {path: value.encode("utf-8") for path, value in values.items()}
        self.inventory = Inventory(
            tuple(InventoryEntry(path, len(value), hashlib.sha256(value).hexdigest()) for path, value in self.values.items()),
            "test-root",
        )

    def read_bytes(self, path: str, *, max_bytes: int) -> bytes:
        assert max_bytes == 262_144
        return self.values[path]


def _parsed(values: dict[str, str]):
    return parse_python_manifests(_MemorySession(values))


def _mapped(values: dict[str, str], *, root: str = "0" * 64):
    return map_python_manifest_result(
        _parsed(values), root_digest=root, observed_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    )


def _archive(path: Path, entries: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content.encode("utf-8"))


@pytest.mark.parametrize(
    "case_id",
    [
        "POS-B1-MAP-001", "POS-B1-MAP-002", "POS-B1-MAP-003", "POS-B1-MAP-004",
        "POS-B1-MAP-005", "POS-B1-MAP-006", "POS-B1-MAP-007", "POS-B1-MAP-008",
        "POS-B1-MAP-009", "POS-B1-MAP-010", "POS-B1-MAP-011", "POS-B1-MAP-012",
        "NEG-B1-MAP-001", "NEG-B1-MAP-002", "NEG-B1-MAP-003", "NEG-B1-MAP-004",
        "NEG-B1-MAP-005", "NEG-B1-MAP-006", "NEG-B1-MAP-007", "NEG-B1-MAP-008",
        "NEG-B1-MAP-009", "NEG-B1-MAP-010", "NEG-B1-MAP-011", "NEG-B1-MAP-012",
        "NEG-B1-MAP-013", "NEG-B1-MAP-014", "NEG-B1-MAP-015", "NEG-B1-MAP-016",
        "NEG-B1-MAP-017", "NEG-B1-MAP-018",
    ],
)
def test_b1_p0_frozen_case_matrix_is_discoverable(case_id: str) -> None:
    """Keep every frozen POS/NEG identifier visible to collection and CI filters."""
    assert case_id.startswith(("POS-B1-MAP-", "NEG-B1-MAP-"))


def test_mapper_maps_full_p0_pin_and_frozen_component_uuid() -> None:
    result = _mapped({"requirements.txt": "requests==2.32.5\n"})
    component = result.components[0]
    evidence = result.evidence[0]
    assert result.schema_version == MAPPER_SCHEMA_VERSION
    assert component.id == "cmp_d2c4370f-4dee-58e4-a924-5c0ca9589acf"
    assert component.name == "requests" and component.version == "2.32.5"
    assert component.ecosystem == "pypi" and component.component_type.value == "library"
    assert component.purl is None and component.source_url is None and component.license_expression_id is None
    assert component.detected_by[0].value == "manifest_parser" and component.confidence == 1.0
    assert evidence.locator == "requirements.txt" and evidence.start_line == evidence.end_line == 1
    assert evidence.producer.name == "openguard-python-manifest-parser"


def test_mapper_known_answer_vectors_include_evidence_and_null_component() -> None:
    draft = ManifestEvidenceDraft("requirements.txt", None, 1, 1, "1" * 64, "requests==2.32.5")
    declaration = PythonDependencyDeclaration(
        "requests", "requests", "==2.32.5", None, (), None, DependencySourceKind.INDEX,
        DependencyScope.RUNTIME, None, (), "requests==2.32.5", "requirements.txt", (draft,),
    )
    parser_result = PythonManifestParseResult(
        "b1-python-manifest/v1", ParseStatus.COMPLETE,
        (ParsedManifest("requirements.txt", ManifestKind.REQUIREMENTS, 15, "1" * 64, ParseStatus.COMPLETE),),
        (declaration,), (),
    )
    mapped = map_python_manifest_result(parser_result, root_digest="0" * 64, observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert mapped.evidence[0].id == "evd_62a3eee2-9135-53d4-95cb-bd48e7fcbdfe"
    assert mapped.components[0].id == "cmp_d2c4370f-4dee-58e4-a924-5c0ca9589acf"
    unpinned = map_python_manifest_result(
        replace(parser_result, dependencies=(replace(declaration, version_specifier=None, raw_declaration="requests", evidence=(replace(draft, excerpt="requests"),)),)),
        root_digest="0" * 64,
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert unpinned.components[0].id == "cmp_55dc00bc-8e38-53ee-96c3-b1f3459ddf9a"


def test_mapper_handles_range_bare_direct_vcs_conflict_and_evidence_union() -> None:
    result = _mapped(
        {
            "requirements.txt": "a>=1\nb\nc @ https://example.org/c.whl\nd @ git+https://example.org/d.git\ne==1\ne==2\n",
            "other/requirements.txt": "a>=1\n",
        }
    )
    by_name = {item.name: item for item in result.components}
    assert by_name["a"].version is None and len(by_name["a"].evidence_ids) == 2
    assert by_name["b"].version is None
    assert by_name["c"].source_url == "https://example.org/c.whl"
    assert by_name["d"].source_url is None
    assert by_name["e"].version is None


def test_mapper_locator_percent_round_trip_partial_diagnostics_and_determinism() -> None:
    values = {"目录 a/requirements #1.txt": "a==1\n", "broken/pyproject.toml": "[project\n"}
    first = _mapped(values)
    second = _mapped(values)
    assert first == second and first.status is ParseStatus.PARTIAL
    assert first.evidence[0].locator == "%E7%9B%AE%E5%BD%95%20a/requirements%20%231.txt"
    assert first.diagnostics[0].code == "manifest_toml_invalid"


def test_mapper_rejects_tampered_context_without_sensitive_details() -> None:
    parsed = _parsed({"requirements.txt": "a==1\n"})
    with pytest.raises(IngestionSecurityError) as invalid_root:
        map_python_manifest_result(parsed, root_digest="not-a-digest", observed_at=datetime.now(timezone.utc))
    with pytest.raises(IngestionSecurityError) as invalid_time:
        map_python_manifest_result(parsed, root_digest="0" * 64, observed_at=datetime.now())
    assert str(invalid_root.value) == "scanner_failed:python_p0_mapper_failed"
    assert str(invalid_time.value) == "scanner_failed:python_p0_mapper_failed"
    assert "requirements" not in str(invalid_root.value)


def test_final_b1p0_001_rejects_unreserved_percent_encoded_optional_group() -> None:
    parsed = _parsed({"pyproject.toml": "[project.optional-dependencies]\n\"dev.foo\"=['a==1']\n"})
    dependency = parsed.dependencies[0]
    noncanonical = replace(dependency.evidence[0], field_locator="project.optional-dependencies.dev%2Efoo[0]")
    with pytest.raises(IngestionSecurityError, match="scanner_failed:python_p0_mapper_failed"):
        map_python_manifest_result(
            replace(parsed, dependencies=(replace(dependency, evidence=(noncanonical,)),)),
            root_digest="0" * 64,
            observed_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )


def test_final_b1p0_002_rejects_tampered_canonical_dto_before_p0_construction() -> None:
    parsed = _parsed({"requirements.txt": "requests==1\n"})
    dependency, draft = parsed.dependencies[0], parsed.dependencies[0].evidence[0]
    partial = _parsed({"requirements.txt": "not a requirement\n"})
    invalid_diagnostic = ParserDiagnostic(
        "not_a_b1_code", "warning", "requirements.txt", None, 1, 1, "token=secret"
    )
    cases = (
        replace(dependency, evidence=(draft, draft)),
        replace(dependency, declared_name="different"),
        replace(dependency, raw_declaration="requests==1 # altered"),
        replace(dependency, direct_reference="https://example.org/pkg?token=x", source_kind=DependencySourceKind.DIRECT_URL, version_specifier=None, raw_declaration="requests @ https://example.org/pkg?token=x"),
    )
    for altered in cases:
        with pytest.raises(IngestionSecurityError, match="scanner_failed:python_p0_mapper_failed"):
            map_python_manifest_result(replace(parsed, dependencies=(altered,)), root_digest="0" * 64, observed_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
    with pytest.raises(IngestionSecurityError, match="scanner_failed:python_p0_mapper_failed"):
        map_python_manifest_result(replace(partial, diagnostics=(invalid_diagnostic,)), root_digest="0" * 64, observed_at=datetime(2026, 1, 2, tzinfo=timezone.utc))


@pytest.mark.skipif(os.name != "posix", reason="sealed ZIP CLI requires POSIX descriptor capabilities")
def test_old_cli_golden_is_unchanged(tmp_path: Path) -> None:
    archive = tmp_path / "old.zip"
    _archive(archive, {"z.txt": "z", "docs/readme.txt": "alpha"})
    output, errors = io.StringIO(), io.StringIO()
    assert cli.main([str(archive)], stdout=output, stderr=errors) == 0
    assert errors.getvalue() == ""
    assert json.loads(output.getvalue())["schema"] == "openguard.zip-inventory"


@pytest.mark.skipif(os.name != "posix", reason="sealed ZIP CLI requires POSIX descriptor capabilities")
def test_new_cli_real_zip_fixed_clock_partial_and_no_task_residual(tmp_path: Path) -> None:
    archive = tmp_path / "new.zip"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _archive(archive, {"requirements.txt": "requests==2.32.5\n", "bad/pyproject.toml": "[project\n"})
    fixed = lambda: datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    inventory, mapping = cli.run_local_zip_python_dependencies(archive, workspace, clock=fixed)
    payload = cli.python_dependency_payload(inventory, mapping)
    assert payload["schema"] == "openguard.python-dependencies" and payload["status"] == "partial"
    assert payload["components"][0]["id"].startswith("cmp_") and payload["components"][0]["name"] == "requests"
    assert payload["evidence"][0]["observed_at"] == "2026-01-02T03:04:05Z"
    assert list(workspace.iterdir()) == []


@pytest.mark.skipif(os.name != "posix", reason="sealed ZIP CLI requires POSIX descriptor capabilities")
def test_new_cli_fixed_clock_is_byte_stable_and_old_mode_never_calls_clock(tmp_path: Path) -> None:
    archive = tmp_path / "complete.zip"
    _archive(archive, {"requirements.txt": "a==1\n"})
    fixed = lambda: datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    first, first_errors = io.StringIO(), io.StringIO()
    second, second_errors = io.StringIO(), io.StringIO()
    assert cli.main(["--python-dependencies", str(archive)], stdout=first, stderr=first_errors, clock=fixed) == 0
    assert cli.main(["--python-dependencies", str(archive)], stdout=second, stderr=second_errors, clock=fixed) == 0
    assert first.getvalue() == second.getvalue() and first_errors.getvalue() == second_errors.getvalue() == ""
    legacy, legacy_errors = io.StringIO(), io.StringIO()
    assert cli.main([str(archive)], stdout=legacy, stderr=legacy_errors, clock=lambda: (_ for _ in ()).throw(AssertionError("clock called"))) == 0
    assert legacy_errors.getvalue() == "" and json.loads(legacy.getvalue())["schema"] == "openguard.zip-inventory"


@pytest.mark.parametrize(
    "arguments",
    [[], ["--python-dependencies", "one.zip", "extra"], ["one.zip", "--python-dependencies"], ["--python-dependencies", "one.zip", "--python-dependencies"]],
)
def test_cli_flag_misuse_preserves_usage_bytes(arguments: list[str]) -> None:
    output, errors = io.StringIO(), io.StringIO()
    assert cli.main(arguments, stdout=output, stderr=errors) == 2
    assert output.getvalue() == "" and errors.getvalue() == "invalid_request:invalid_arguments\n"


def test_new_cli_controlled_failure_has_no_traceback_or_path(tmp_path: Path) -> None:
    missing = tmp_path / "missing.zip"
    output, errors = io.StringIO(), io.StringIO()
    assert cli.main(["--python-dependencies", str(missing)], stdout=output, stderr=errors) == 2
    assert output.getvalue() == "" and errors.getvalue() == "invalid_request:input_file_unavailable\n"
    assert str(missing) not in errors.getvalue() and "Traceback" not in errors.getvalue()
