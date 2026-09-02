"""Terra-owned regression coverage for B1 Python manifest parsing."""
from __future__ import annotations

import hashlib
from typing import get_type_hints

import pytest

from app.ingestion.inventory import Inventory, InventoryEntry
from app.scanners.python_manifest import (
    DependencyScope,
    DependencySourceKind,
    ManifestEvidenceDraft,
    ParserDiagnostic,
    ParseStatus,
    parse_python_manifests,
)
from app.security.errors import IngestionSecurityError


class MemorySession:
    """Capability-shaped test double; it exposes no path or workspace."""
    def __init__(self, values: dict[str, bytes]) -> None:
        self.values = values
        self.calls: list[str] = []
        entries = tuple(InventoryEntry(path, len(data), hashlib.sha256(data).hexdigest()) for path, data in values.items())
        self.inventory = Inventory(entries, "test-root")

    def read_bytes(self, path: str, *, max_bytes: int) -> bytes:
        self.calls.append(path)
        assert max_bytes == 262_144
        return self.values[path]


def _parse(values: dict[str, str | bytes]):
    return parse_python_manifests(MemorySession({key: value if isinstance(value, bytes) else value.encode() for key, value in values.items()}))


@pytest.mark.parametrize(
    ("case_id", "values", "check"),
    [
        ("POS-B1-PY-001", {"z/requirements.txt": "z==1", ".venv/requirements.txt": "ignored", "a/pyproject.toml": "[project]\ndependencies=['a==1']"}, lambda result: [m.relative_path for m in result.manifests] == ["a/pyproject.toml", "z/requirements.txt"]),
        ("POS-B1-PY-002", {"requirements.txt": 'Requests[socks]>=2 ; python_version < "3.14"'}, lambda result: result.dependencies[0].normalized_name == "requests" and result.dependencies[0].marker is not None),
        ("POS-B1-PY-003", {"requirements.txt": "a==1 \\\n  ; python_version > '3' # note"}, lambda result: result.dependencies[0].evidence[0].start_line == 1 and result.dependencies[0].evidence[0].end_line == 2),
        ("POS-B1-PY-004", {"requirements.txt": "a @ https://example.org/pkg#sha256=" + "a" * 64}, lambda result: result.dependencies[0].source_kind is DependencySourceKind.DIRECT_URL),
        ("POS-B1-PY-005", {"requirements.txt": "a @ git+https://example.org/pkg#subdirectory=src"}, lambda result: result.dependencies[0].source_kind is DependencySourceKind.VCS),
        ("POS-B1-PY-006", {"requirements.txt": "a==1 --hash=sha256:" + "A" * 64 + " --hash=sha256:" + "a" * 64}, lambda result: result.dependencies[0].hashes == ("a" * 64,)),
        ("POS-B1-PY-007", {"pyproject.toml": "[project]\ndependencies=['a==1']"}, lambda result: result.dependencies[0].scope is DependencyScope.RUNTIME and result.dependencies[0].evidence[0].field_locator == "project.dependencies[0]"),
        ("POS-B1-PY-008", {"pyproject.toml": "[project.optional-dependencies]\nDev_Test=['a==1']"}, lambda result: result.dependencies[0].scope is DependencyScope.OPTIONAL and result.dependencies[0].group == "dev-test"),
        ("POS-B1-PY-009", {"pyproject.toml": "[build-system]\nrequires=['setuptools>=1']"}, lambda result: result.dependencies[0].scope is DependencyScope.BUILD),
        ("POS-B1-PY-010", {"requirements.txt": "a==1", "sub/requirements.txt": "a==1"}, lambda result: len(result.dependencies) == 1 and len(result.dependencies[0].evidence) == 2),
        ("POS-B1-PY-011", {"requirements.txt": "a==1", "pyproject.toml": "[project\n"}, lambda result: result.status is ParseStatus.PARTIAL and len(result.dependencies) == 1),
        ("POS-B1-PY-012", {"requirements.txt": "a==1"}, lambda result: result.schema_version == "b1-python-manifest/v1"),
    ],
)
def test_positive_matrix(case_id: str, values: dict[str, str], check) -> None:
    assert check(_parse(values)), case_id


@pytest.mark.parametrize(
    ("case_id", "values", "code"),
    [
        ("NEG-B1-PY-001", {"requirements.txt": b"\xff"}, "manifest_encoding_invalid"),
        ("NEG-B1-PY-002", {"pyproject.toml": "[project\n"}, "manifest_toml_invalid"),
        ("NEG-B1-PY-003", {"pyproject.toml": "[project]\ndependencies='a==1'"}, "manifest_field_invalid"),
        ("NEG-B1-PY-004", {"requirements.txt": "not a requirement @@@"}, "requirement_invalid"),
        ("NEG-B1-PY-005", {"requirements.txt": "-r hidden.txt"}, "requirement_include_unsupported"),
        ("NEG-B1-PY-006", {"requirements.txt": "-c constraints.txt\na==1"}, "requirement_constraint_unsupported"),
        ("NEG-B1-PY-007", {"requirements.txt": "-e ./local"}, "requirement_editable_unsupported"),
        ("NEG-B1-PY-008", {"requirements.txt": "--index-url https://token@example.org/simple"}, "requirement_option_unsupported"),
        ("NEG-B1-PY-009", {"requirements.txt": "https://example.org/a.whl"}, "requirement_unnamed_reference_unsupported"),
        ("NEG-B1-PY-010", {"requirements.txt": "a @ file:///tmp/a"}, "requirement_reference_unsafe"),
        ("NEG-B1-PY-011", {"requirements.txt": "a @ https://user:secret@example.org/a?q=x"}, "requirement_reference_unsafe"),
        ("NEG-B1-PY-012", {"requirements.txt": "a==1 --hash=md5:bad"}, "requirement_hash_invalid"),
        ("NEG-B1-PY-013", {"requirements.txt": 'a==1 ; sys_platform == "never-evaluate"'}, None),
        ("NEG-B1-PY-017", {"requirements.txt": "a==1 " + "x" * 8193}, "manifest_logical_line_too_long"),
        ("NEG-B1-PY-019", {"requirements.txt": "a==1\na==2"}, "dependency_declaration_conflict"),
        ("NEG-B1-PY-020", {"pyproject.toml": "[project]\ndynamic=['dependencies']\n[tool.poetry]\nname='x'"}, "pyproject_dynamic_dependencies_unsupported"),
        ("NEG-B1-PY-021", {"requirements.txt": "a==1"}, None),
        ("NEG-B1-PY-022", {"requirements.txt": "--index-url https://secret@example.org"}, "requirement_option_unsupported"),
        ("NEG-B1-PY-023", {"requirements.txt": "a==1"}, None),
    ],
)
def test_negative_matrix(case_id: str, values: dict[str, str | bytes], code: str | None) -> None:
    result = _parse(values)
    if code is None:
        assert result.status in {ParseStatus.COMPLETE, ParseStatus.PARTIAL}
    else:
        assert code in {item.code for item in result.diagnostics}, case_id
    assert "secret" not in " ".join(item.message for item in result.diagnostics)


@pytest.mark.parametrize(
    ("case_id", "values"),
    [
        ("NEG-B1-PY-014", {f"d{i}/requirements.txt": b"a==1" for i in range(65)}),
        ("NEG-B1-PY-015", {"requirements.txt": b"a" * 262_145}),
        ("NEG-B1-PY-016", {f"d{i}/requirements.txt": b"a" * 65_537 for i in range(64)}),
        ("NEG-B1-PY-018", {"requirements.txt": ("\n".join(f"a{i}==1" for i in range(4097))).encode()}),
    ],
)
def test_limit_matrix(case_id: str, values: dict[str, bytes]) -> None:
    with pytest.raises(IngestionSecurityError, match="python_manifest_limit_exceeded"):
        parse_python_manifests(MemorySession(values))


def test_neg_b1_py_024_packaging_version_and_expired_session(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.scanners.python_manifest as module
    monkeypatch.setattr(module, "_packaging_version", "0")
    with pytest.raises(IngestionSecurityError, match="python_manifest_parser_unavailable"):
        _parse({"requirements.txt": "a==1"})


def test_amendment_nullable_dto_and_canonical_declaration_regressions() -> None:
    assert get_type_hints(ManifestEvidenceDraft)["start_line"] == (int | None)
    assert get_type_hints(ParserDiagnostic)["manifest_path"] == (str | None)
    result = _parse({"a/requirements.txt": " a == 1 # spelling\n", "z/requirements.txt": "a==1\n", "pyproject.toml": "[project]\ndependencies=['bare']\n"})
    assert result.dependencies[0].raw_declaration == "a==1"
    assert result.dependencies[1].version_specifier is None
    assert result.dependencies[1].evidence[0].start_line is None


def test_amendment_eof_reference_and_duplicate_inventory_fail_closed() -> None:
    dangling = _parse({"requirements.txt": "a==1 \\"})
    assert dangling.dependencies == ()
    assert {item.code for item in dangling.diagnostics} == {"requirement_invalid"}
    unsafe = _parse({"requirements.txt": "a @ https://example.org/pkg#subdirectory=a/./b"})
    assert unsafe.dependencies == ()
    assert {item.code for item in unsafe.diagnostics} == {"requirement_reference_unsafe"}

    data = b"a==1\n"
    entry = InventoryEntry("requirements.txt", len(data), hashlib.sha256(data).hexdigest())
    session = MemorySession({"requirements.txt": data})
    session.inventory = Inventory((entry, entry), "duplicate")
    with pytest.raises(IngestionSecurityError, match="python_manifest_parser_failed"):
        parse_python_manifests(session)


def test_final_audit_p1_physical_lines_and_output_bounds() -> None:
    for declaration in ("a==1\u2028b==2", "\u2028a==1", "a==1\u2028"):
        unicode_separator = _parse({"requirements.txt": declaration})
        assert unicode_separator.dependencies == ()
        assert unicode_separator.diagnostics[0].code == "requirement_invalid"
        assert unicode_separator.diagnostics[0].start_line == 1
    long_name = _parse({"requirements.txt": "a" * 1001})
    assert long_name.dependencies == ()
    assert all(len(item.message) <= 1000 for item in long_name.diagnostics)


def test_final_audit_p1_extras_order_identity_order_and_ipv6() -> None:
    parsed = _parse({"requirements.txt": "a[x_y,x-y]\na>=1\na\nv @ https://[::1]/pkg"})
    assert parsed.dependencies[0].normalized_name == "a"
    assert parsed.dependencies[0].version_specifier is None
    assert parsed.dependencies[1].version_specifier == ">=1"
    assert next(item for item in parsed.dependencies if item.extras).extras == ("x-y",)
    ipv6 = parsed.dependencies[-1]
    assert ipv6.direct_reference == "https://[::1]/pkg"
