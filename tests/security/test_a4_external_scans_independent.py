"""Independent ZIP/FD observations; tool JSON and expected hashes are authored here."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from types import SimpleNamespace
import zipfile

import pytest

from app.ingestion import ZipIngestionService
from app.pipeline import external_scans
from app.scanners import scancode_pipeline, syft_pipeline
from app.scanners.external_tools import ToolExecution
from app.security.errors import IngestionSecurityError

REAL_SCANCODE_VERSION = b"ScanCode version: 32.5.0\nScanCode Output Format version: 4.1.0\nSPDX License list version: 3.27\n"

NOW = datetime(2026, 9, 5, tzinfo=timezone.utc)
FILES = {"LICENSE": b"Independent license observation\n", "package-lock.json": b'{"name":"independent","lockfileVersion":3}\n'}


def archive():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as output:
        for path, body in FILES.items():
            output.writestr(path, body)
    stream.seek(0)
    return stream


@pytest.fixture
def service(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir(mode=0o700)
    instance = ZipIngestionService(root)
    yield instance, root
    instance.close()


def execute(service, callback):
    return service.ingest_with_consumer(archive(), lambda session: "parser-result", tree_consumer=callback)


@pytest.mark.parametrize("mode", ["success", "raise", "mutate_raise", "reentry"])
def test_tree_lifecycle_cleanup_and_expiration(service, mode):
    instance, root = service
    captured = []

    def callback(tree, inventory):
        captured.append(tree)
        fd = os.open("LICENSE", os.O_RDONLY, dir_fd=tree._directory_fd)
        try:
            assert os.read(fd, 4096) == FILES["LICENSE"]
        finally:
            os.close(fd)
        assert {entry.relative_path: entry.sha256 for entry in inventory.entries} == {
            path: hashlib.sha256(body).hexdigest() for path, body in FILES.items()
        }
        if mode == "mutate_raise":
            fd = os.open("LICENSE", os.O_WRONLY | os.O_TRUNC, dir_fd=tree._directory_fd)
            try:
                os.write(fd, b"changed")
            finally:
                os.close(fd)
        if mode in {"raise", "mutate_raise"}:
            raise RuntimeError("SECRET /outside/private")
        if mode == "reentry":
            with pytest.raises(IngestionSecurityError):
                execute(instance, lambda *_: None)

    reasons = {"raise": "scan_consumer_failed", "mutate_raise": "scan_file_integrity_failed", "reentry": "scan_session_reentrant"}
    if mode == "success":
        assert execute(instance, callback).consumer_result == "parser-result"
    else:
        with pytest.raises(IngestionSecurityError) as failure:
            execute(instance, callback)
        assert failure.value.reason == reasons[mode]
        assert "SECRET" not in str(failure.value)
    assert list(root.iterdir()) == []
    assert len(captured) == 1
    with pytest.raises(IngestionSecurityError):
        captured[0].proc_target()
    with pytest.raises(IngestionSecurityError):
        _ = captured[0].inherited_fds
    with pytest.raises(OSError):
        os.fstat(captured[0]._directory_fd)


def test_cleanup_failure_overrides_callback_failure(service, monkeypatch):
    instance, root = service
    original = instance._workspaces.cleanup
    def cleanup(workspace):
        original(workspace)
        raise IngestionSecurityError("scanner_failed", "workspace_cleanup_failed")
    monkeypatch.setattr(instance._workspaces, "cleanup", cleanup)
    def callback(*_):
        raise RuntimeError("PRIVATE")
    with pytest.raises(IngestionSecurityError) as failure:
        execute(instance, callback)
    assert failure.value.reason == "workspace_cleanup_failed"
    assert list(root.iterdir()) == []


class DescriptorTarget:
    """Only the fixed subprocess target protocol, no mapper implementation helpers."""
    def proc_target(self):
        return "/proc/self/fd/777"
    inherited_fds = (777,)


def tool_json(name, payload):
    return ToolExecution(name, "complete", json.dumps(payload).encode())


@pytest.mark.parametrize("bad", [None, "unknown", "hash", "scan_errors"])
def test_scancode_inventory_binding(service, monkeypatch, bad):
    instance, root = service
    record = {"path": "LICENSE", "type": "file", "detected_license_expression": "mit"}
    if bad == "unknown":
        record["path"] = "absent-LICENSE"
    elif bad == "hash":
        record["sha256"] = "0" * 64
    elif bad == "scan_errors":
        record["scan_errors"] = ["SECRET /outside/private"]
    monkeypatch.setattr(scancode_pipeline, "run_scancode_license_scan", lambda *_args, **_kwargs: tool_json("scancode", {"files": [record, {"path": "package-lock.json", "type": "file"}]}))
    observed = []
    def callback(_tree, inventory):
        result = scancode_pipeline.scan_sealed_tree(DescriptorTarget(), inventory, executable="fixed", tool_version="32.5.0", observed_at=NOW)
        observed.extend(result.mapping.evidence)
    if bad is None:
        execute(instance, callback)
        assert len(observed) == 1
        assert observed[0].locator == "LICENSE"
        assert observed[0].content_hash.value == hashlib.sha256(FILES["LICENSE"]).hexdigest()
    else:
        # Inspect the adapter directly inside A2, before A2 sanitizes callback failures.
        def rejected(tree, inventory):
            with pytest.raises(IngestionSecurityError) as failure:
                callback(tree, inventory)
            assert failure.value.reason == "external_scanner_invalid_output"
        execute(instance, rejected)
        assert observed == []
    assert list(root.iterdir()) == []


@pytest.mark.parametrize("location", ["package-lock.json", "/proc/self/fd/777/package-lock.json", "missing.json", "../package-lock.json", "/proc/self/fd/777/../package-lock.json", "/private/package-lock.json"])
def test_syft_inventory_binding(service, monkeypatch, location):
    instance, root = service
    payload = {"artifacts": [{"name": "independent", "version": "1.2.3", "purl": "pkg:npm/independent@1.2.3", "locations": [{"path": location}]}]}
    monkeypatch.setattr(syft_pipeline, "run_syft_sbom_scan", lambda *_args, **_kwargs: tool_json("syft", payload))
    valid = location in {"package-lock.json", "/proc/self/fd/777/package-lock.json"}
    def callback(_tree, inventory):
        def scan():
            return syft_pipeline.scan_sealed_tree(DescriptorTarget(), inventory, executable="fixed", tool_version="1.51.0", observed_at=NOW)
        if valid:
            result = scan()
            assert len(result.mapping.evidence) == 1
            evidence = result.mapping.evidence[0]
            assert evidence.locator == "package-lock.json"
            assert evidence.content_hash.value == hashlib.sha256(FILES["package-lock.json"]).hexdigest()
            assert result.mapping.components[0].evidence_ids == [evidence.id]
        else:
            with pytest.raises(IngestionSecurityError) as failure:
                scan()
            assert failure.value.reason == "external_scanner_invalid_output"
    execute(instance, callback)
    assert list(root.iterdir()) == []


@pytest.mark.parametrize("failed_lane", ["scancode", "syft"])
@pytest.mark.parametrize("failure_mode", ["missing", "wrong_version"])
def test_collect_retains_other_lane_and_sanitizes(service, monkeypatch, failed_lane, failure_mode):
    instance, _ = service
    sentinel = object()
    called = []
    def version(executable, *_args, **_kwargs):
        name = "scancode" if "scancode" in executable else "syft"
        if name == failed_lane:
            if failure_mode == "missing":
                return ToolExecution(name, "unavailable", None, "SECRET /private/tool")
            return ToolExecution(name, "complete", b'ScanCode version SECRET' if name == "scancode" else b'{"version":"SECRET"}')
        return ToolExecution(name, "complete", REAL_SCANCODE_VERSION if name == "scancode" else b'{"version":"1.51.0"}')
    def scan(name):
        def run(*_args, **_kwargs):
            called.append(name)
            return SimpleNamespace(mapping=SimpleNamespace(evidence=[sentinel], components=[]))
        return run
    monkeypatch.setattr(external_scans, "run_json_tool", version)
    monkeypatch.setattr(external_scans, "scan_licenses", scan("scancode"))
    monkeypatch.setattr(external_scans, "scan_components", scan("syft"))
    def callback(tree, inventory):
        facts = external_scans.collect_external_scans(tree, inventory, lambda: NOW)
        other = "syft" if failed_lane == "scancode" else "scancode"
        assert called == [other]
        assert facts.evidence == [sentinel]
        assert len(facts.errors) == 1
        assert facts.errors[0].code == failed_lane + "_scan_incomplete"
        assert facts.errors[0].message == failed_lane + " scan could not be completed."
        assert "SECRET" not in facts.errors[0].model_dump_json()
        assert [item.name for item in facts.producers] == [other]
    execute(instance, callback)


@pytest.mark.parametrize("version_bytes, accepted", [
    (REAL_SCANCODE_VERSION, True),
    (b"ScanCode version 32.5.0\n", False),
    (b"PREFIX ScanCode version: 32.5.0\n", False),
    (b"ScanCode version: 32.5.0-malicious\n", False),
    (b"ScanCode version: 32.5.00\n", False),
    (b"ScanCode version: 32.4.0\nScanCode version: 32.5.0\n", False),
])
def test_real_scancode_version_first_line_is_exact(service, monkeypatch, version_bytes, accepted):
    instance, _ = service
    called = []
    def version(executable, *_args, **_kwargs):
        if "scancode" in executable:
            return ToolExecution("scancode", "complete", version_bytes)
        return ToolExecution("syft", "complete", b'{"version":"1.51.0"}')
    def scan(name):
        def run(*_args, **_kwargs):
            called.append(name)
            return SimpleNamespace(mapping=SimpleNamespace(evidence=[], components=[]))
        return run
    monkeypatch.setattr(external_scans, "run_json_tool", version)
    monkeypatch.setattr(external_scans, "scan_licenses", scan("scancode"))
    monkeypatch.setattr(external_scans, "scan_components", scan("syft"))
    def callback(tree, inventory):
        facts = external_scans.collect_external_scans(tree, inventory, lambda: NOW)
        assert called == (["scancode", "syft"] if accepted else ["syft"])
        assert [item.name for item in facts.producers] == called
        assert [item.code for item in facts.errors] == ([] if accepted else ["scancode_scan_incomplete"])
        if not accepted:
            assert facts.errors[0].message == "scancode scan could not be completed."
    execute(instance, callback)


@pytest.mark.parametrize("records", [
    [{"path": "", "type": "directory"}],
    [{"path": "LICENSE", "type": "file", "detected_license_expression": "mit"}],
    [],
])
def test_scancode_incomplete_inventory_is_rejected(service, monkeypatch, records):
    instance, _ = service
    monkeypatch.setattr(scancode_pipeline, "run_scancode_license_scan", lambda *_args, **_kwargs: tool_json("scancode", {"files": records}))
    def callback(_tree, inventory):
        with pytest.raises(IngestionSecurityError) as failure:
            scancode_pipeline.scan_sealed_tree(DescriptorTarget(), inventory, executable="fixed", tool_version="32.5.0", observed_at=NOW)
        assert failure.value.reason == "external_scanner_invalid_output"
    execute(instance, callback)


@pytest.mark.parametrize("source, location, accepted", [
    ({"type": "directory", "metadata": {"path": "/proc/self/fd/777"}}, "/package-lock.json", True),
    (None, "/package-lock.json", False),
    ({"type": "directory", "metadata": {"path": "/proc/self/fd/778"}}, "/package-lock.json", False),
    ({"type": "image", "metadata": {"path": "/proc/self/fd/777"}}, "/package-lock.json", False),
    ({"type": "directory", "metadata": {"path": "/proc/self/fd/777"}}, "/../package-lock.json", False),
    ({"type": "directory", "metadata": {"path": "/proc/self/fd/777"}}, "//package-lock.json", False),
    ({"type": "directory", "metadata": {"path": "/proc/self/fd/777"}}, "/package\\lock.json", False),
    ({"type": "directory", "metadata": {"path": "/proc/self/fd/777"}}, "/absent.json", False),
])
def test_syft_rooted_location_requires_exact_source(service, monkeypatch, source, location, accepted):
    instance, _ = service
    payload = {"artifacts": [{"name": "independent", "version": "1.2.3", "purl": "pkg:npm/independent@1.2.3", "locations": [{"path": location}]}]}
    if source is not None:
        payload["source"] = source
    monkeypatch.setattr(syft_pipeline, "run_syft_sbom_scan", lambda *_args, **_kwargs: tool_json("syft", payload))
    def callback(_tree, inventory):
        def scan():
            return syft_pipeline.scan_sealed_tree(DescriptorTarget(), inventory, executable="fixed", tool_version="1.51.0", observed_at=NOW)
        if accepted:
            result = scan()
            assert len(result.mapping.evidence) == 1
            evidence = result.mapping.evidence[0]
            assert evidence.locator == "package-lock.json"
            assert evidence.content_hash.value == hashlib.sha256(FILES["package-lock.json"]).hexdigest()
            assert result.mapping.components[0].evidence_ids == [evidence.id]
        else:
            with pytest.raises(IngestionSecurityError) as failure:
                scan()
            assert failure.value.reason == "external_scanner_invalid_output"
    execute(instance, callback)
