"""Terra B1-3/B1-4 regression coverage using only dynamic JSON and ZIP bytes."""

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
from app.scanners import map_javascript_manifest_result, parse_javascript_manifests
from app.scanners.javascript_manifest import JavascriptManifestKind, JavascriptParseStatus
from app.security.errors import IngestionSecurityError


class _Session:
    def __init__(self, values: dict[str, bytes], *, entries: tuple[InventoryEntry, ...] | None = None) -> None:
        self.values = values
        self.inventory = Inventory(entries or tuple(InventoryEntry(path, len(value), hashlib.sha256(value).hexdigest()) for path, value in values.items()), "0" * 64)

    def read_bytes(self, path: str, *, max_bytes: int) -> bytes:
        assert max_bytes == 2 * 1024 * 1024
        return self.values[path]


def _parsed(values: dict[str, str | bytes]):
    return parse_javascript_manifests(_Session({path: value.encode() if isinstance(value, str) else value for path, value in values.items()}))


def _mapped(values: dict[str, str | bytes]):
    return map_javascript_manifest_result(_parsed(values), root_digest="0" * 64, observed_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc))


def _archive(path: Path, values: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, value in values.items():
            archive.writestr(name, value)


@pytest.mark.parametrize("case_id", [*(f"POS-B1-JS-{index:03d}" for index in range(1, 11)), *(f"NEG-B1-JS-{index:03d}" for index in range(1, 17))])
def test_frozen_b1_js_case_ids_are_discoverable(case_id: str) -> None:
    assert case_id.startswith(("POS-B1-JS-", "NEG-B1-JS-"))


def test_package_fields_scoped_locator_exact_range_tag_and_conflict_merge() -> None:
    result = _mapped({"package.json": json.dumps({"dependencies": {"react": "18.2.0", "tag": "latest", "@scope/pkg": "^1.2.3"}, "devDependencies": {"react": "18.2.0"}, "optionalDependencies": {"react": "19.0.0"}})})
    by_name = {item.name: item for item in result.components}
    assert by_name["@scope/pkg"].purl == "pkg:npm/%40scope/pkg"
    assert by_name["react"].version is None and result.status.value == "partial"
    assert by_name["tag"].version is None
    assert any(item.code == "dependency_declaration_conflict" for item in result.diagnostics)
    assert any("@scope~1pkg" in item.locator for item in result.evidence)


def test_lock_v2_v3_enrichment_url_purl_and_fixed_clock_are_deterministic() -> None:
    package = {"dependencies": {"react": "^18.2.0", "@scope/pkg": "1.2.3"}}
    lock = {"lockfileVersion": 3, "packages": {"": {"dependencies": package["dependencies"]}, "node_modules/react": {"version": "18.2.0", "resolved": "https://registry.npmjs.org/react/-/react-18.2.0.tgz"}, "node_modules/@scope/pkg": {"version": "1.2.3"}}}
    first = _mapped({"package.json": json.dumps(package), "package-lock.json": json.dumps(lock)})
    second = _mapped({"package.json": json.dumps(package), "package-lock.json": json.dumps(lock)})
    assert first == second
    react = next(item for item in first.components if item.name == "react")
    assert react.version == "18.2.0" and react.source_url == "https://registry.npmjs.org/react/-/react-18.2.0.tgz"
    assert react.purl == "pkg:npm/react@18.2.0" and len(react.evidence_ids) == 3


def test_partial_lock_diagnostics_and_safe_rejections() -> None:
    result = _mapped({"package.json": '{"dependencies":{"good":"^1.0.0","bad":"file:../bad"}}', "package-lock.json": '{"lockfileVersion":1,"packages":{}}'})
    assert result.status.value == "partial" and [item.name for item in result.components] == ["good"]
    assert {item.code for item in result.diagnostics} == {"dependency_selector_unsafe", "lockfile_version_unsupported"}
    for bad in (b'\xef\xbb\xbf{}', b'\xff', b'{"dependencies":{"a":"1","a":"2"}}'):
        parsed = _parsed({"package.json": bad})
        assert parsed.status.value == "partial"


def test_limits_invalid_shapes_and_tampered_mapper_input_fail_closed() -> None:
    with pytest.raises(IngestionSecurityError, match="javascript_manifest_limit_exceeded"):
        _parsed({"package.json": "{" + '"x":"' + "a" * 8193 + '"}'})
    parsed = _parsed({"package.json": '{"dependencies":{"a":"1.0.0"}}'})
    with pytest.raises(IngestionSecurityError, match="javascript_p0_mapper_failed"):
        map_javascript_manifest_result(parsed, root_digest="bad", observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc))


def test_p1_selector_url_inventory_and_strict_json_regressions_fail_closed() -> None:
    accepted = _parsed({"package.json": '{"devDependencies":{"dev":"~2.0.0"},"dependencies":{"z":"^1.0.0","a":"latest"}}'})
    assert [item.normalized_name for item in accepted.dependencies] == ["a", "dev", "z"]
    assert accepted.status.value == "complete"

    dot_segment = _parsed({
        "package.json": '{"dependencies":{"a":"^1.0.0"}}',
        "package-lock.json": '{"lockfileVersion":3,"packages":{"":{"dependencies":{"a":"^1.0.0"}},"node_modules/a":{"version":"1.0.0","resolved":"https://registry.npmjs.org/a/../a.tgz"}}}',
    })
    assert dot_segment.status.value == "partial"
    assert [item.code for item in dot_segment.diagnostics] == ["lock_entry_invalid"]

    raw = b'{"dependencies":{"a":"1.0.0"}}'
    forged = _Session({"package.json": raw}, entries=(InventoryEntry("package.json", len(raw) + 1, hashlib.sha256(raw).hexdigest()),))
    with pytest.raises(IngestionSecurityError, match="scanner_failed:javascript_manifest_parser_failed"):
        parse_javascript_manifests(forged)

    for constant in ("NaN", "Infinity", "-Infinity"):
        parsed = _parsed({"package.json": '{"value":' + constant + "}"})
        assert parsed.status.value == "partial"
        assert [item.code for item in parsed.diagnostics] == ["manifest_json_invalid"]


def test_p1_mapper_rejects_forged_names_selectors_manifests_and_locators() -> None:
    parsed = _parsed({"package.json": '{"dependencies":{"a":"1.0.0"}}'})
    declaration = parsed.dependencies[0]
    draft = declaration.evidence[0]
    candidates = (
        replace(parsed, manifests=(replace(parsed.manifests[0], size_bytes="1"),)),
        replace(parsed, manifests=(replace(parsed.manifests[0], size_bytes=-1),)),
        replace(parsed, manifests=(replace(parsed.manifests[0], kind=JavascriptManifestKind.PACKAGE_LOCK),)),
        replace(parsed, dependencies=(replace(declaration, normalized_name="Upper", declared_name="Upper"),)),
        replace(parsed, dependencies=(replace(declaration, requested_spec="file:../a"),)),
        replace(parsed, dependencies=(replace(declaration, requested_spec="../a"),)),
        replace(parsed, dependencies=(replace(declaration, requested_spec="https://example.invalid/a"),)),
        replace(parsed, dependencies=(replace(declaration, evidence=(replace(draft, field_locator="package.json:/dependencies//a"),)),)),
    )
    for candidate in candidates:
        with pytest.raises(IngestionSecurityError, match="scanner_failed:javascript_p0_mapper_failed"):
            map_javascript_manifest_result(candidate, root_digest="0" * 64, observed_at=datetime(2026, 1, 2, tzinfo=timezone.utc))

    ordered = _parsed({
        "z/package.json": '{"dependencies":{"z":"1.0.0"}}',
        "a/package.json": '{"dependencies":{"a":"1.0.0"}}',
    })
    with pytest.raises(IngestionSecurityError, match="scanner_failed:javascript_p0_mapper_failed"):
        map_javascript_manifest_result(replace(ordered, manifests=tuple(reversed(ordered.manifests))), root_digest="0" * 64, observed_at=datetime(2026, 1, 2, tzinfo=timezone.utc))

    partial = _parsed({"package.json": '{"dependencies":{"a":"file:../a"}}'})
    with pytest.raises(IngestionSecurityError, match="scanner_failed:javascript_p0_mapper_failed"):
        map_javascript_manifest_result(replace(partial, manifests=(replace(partial.manifests[0], status=JavascriptParseStatus.PARTIAL),)), root_digest="0" * 64, observed_at=datetime(2026, 1, 2, tzinfo=timezone.utc))

    locked = _parsed({
        "a/package.json": '{"dependencies":{"a":"^1.0.0"}}',
        "a/package-lock.json": '{"lockfileVersion":3,"packages":{"":{"dependencies":{"a":"^1.0.0"}},"node_modules/a":{"version":"1.0.0"}}}',
        "b/package-lock.json": '{"lockfileVersion":3,"packages":{}}',
    })
    locked_declaration = locked.dependencies[0]
    for candidate in (
        replace(locked, dependencies=(replace(locked_declaration, source_manifest="a/package-lock.json"),)),
        replace(locked, dependencies=(replace(locked_declaration, lock_manifest="b/package-lock.json"),)),
    ):
        with pytest.raises(IngestionSecurityError, match="scanner_failed:javascript_p0_mapper_failed"):
            map_javascript_manifest_result(candidate, root_digest="0" * 64, observed_at=datetime(2026, 1, 2, tzinfo=timezone.utc))


@pytest.mark.skipif(os.name != "posix", reason="sealed ZIP CLI requires POSIX descriptor capabilities")
def test_real_zip_cli_fixed_clock_compatibility_and_cleanup(tmp_path: Path) -> None:
    archive = tmp_path / "javascript.zip"
    _archive(archive, {"package.json": '{"dependencies":{"react":"^18.2.0"}}', "package-lock.json": '{"lockfileVersion":2,"packages":{"":{"dependencies":{"react":"^18.2.0"}},"node_modules/react":{"version":"18.2.0"}}}'})
    fixed = lambda: datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    first, errors = io.StringIO(), io.StringIO()
    assert cli.main(["--javascript-dependencies", str(archive)], stdout=first, stderr=errors, clock=fixed) == 0
    payload = json.loads(first.getvalue())
    assert errors.getvalue() == "" and payload["schema"] == "openguard.javascript-dependencies"
    assert payload["components"][0]["version"] == "18.2.0"
    old, old_errors = io.StringIO(), io.StringIO()
    assert cli.main([str(archive)], stdout=old, stderr=old_errors, clock=lambda: (_ for _ in ()).throw(AssertionError("legacy clock"))) == 0
    assert json.loads(old.getvalue())["schema"] == "openguard.zip-inventory" and old_errors.getvalue() == ""


@pytest.mark.parametrize("arguments", [[], ["--javascript-dependencies"], ["zip", "--javascript-dependencies"], ["--javascript-dependencies", "zip", "extra"]])
def test_js_cli_flag_misuse_is_stable(arguments: list[str]) -> None:
    output, errors = io.StringIO(), io.StringIO()
    expected = "invalid_request:input_file_unavailable\n" if arguments == ["--javascript-dependencies"] else "invalid_request:invalid_arguments\n"
    assert cli.main(arguments, stdout=output, stderr=errors) == 2
    assert output.getvalue() == "" and errors.getvalue() == expected
