"""Regression coverage for the non-executing ScanCode/Syft adapter boundary."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import pytest

from datetime import datetime, timezone

from app.domain.models import Component, ComponentType, DetectionMethod
from app.scanners import external_tools
from app.scanners.external_tools import (
    ToolExecution,
    map_scancode_output,
    map_syft_output,
    merge_components,
    parse_json_output,
    run_json_tool,
)


_DIGEST = "0" * 64
_NOW = datetime(2026, 9, 2, tzinfo=timezone.utc)


def test_scancode_maps_only_locatable_license_evidence_and_candidates() -> None:
    result = map_scancode_output(
        {"files": [
            {"path": "LICENSE", "sha256": "a" * 64, "detected_license_expression": "MIT"},
            {"path": "src/main.py", "license_detections": [{"license_expression": "Apache-2.0"}]},
            {"path": "../outside", "detected_license_expression": "GPL-3.0-only"},
        ]},
        root_digest=_DIGEST,
        observed_at=_NOW,
        tool_version="32.3.0",
    )
    assert result.license_candidates == ("Apache-2.0", "MIT")
    assert [item.locator for item in result.evidence] == ["LICENSE", "src/main.py"]
    assert all(item.detected_by is DetectionMethod.SCANCODE for item in result.evidence)
    assert all(item.verification_status.value == "pending" for item in result.evidence)


def test_syft_maps_artifact_locations_without_guessing_license_or_version() -> None:
    result = map_syft_output(
        {"artifacts": [
            {"name": "requests", "version": "2.32.0", "purl": "pkg:pypi/requests@2.32.0", "locations": [{"path": "requirements.txt"}]},
            {"name": "bad", "locations": [{"path": "../outside"}]},
        ]},
        root_digest=_DIGEST,
        observed_at=_NOW,
        tool_version="1.20.0",
    )
    assert len(result.components) == len(result.evidence) == 1
    component = result.components[0]
    assert component.ecosystem == "pypi" and component.license_expression_id is None
    assert component.detected_by == [DetectionMethod.SYFT]
    assert result.evidence[0].locator == "requirements.txt"


def test_component_merge_keeps_evidence_and_marks_metadata_conflict() -> None:
    first = Component(
        id="cmp_123e4567-e89b-12d3-a456-426614174000", name="requests", version="2.32.0", ecosystem="pypi",
        component_type=ComponentType.LIBRARY, purl="pkg:pypi/requests@2.32.0", source_url=None,
        license_expression_id=None, evidence_ids=["evd_123e4567-e89b-12d3-a456-426614174000"],
        detected_by=[DetectionMethod.MANIFEST_PARSER], confidence=1.0,
    )
    second = first.model_copy(update={
        "id": "cmp_123e4567-e89b-12d3-a456-426614174001",
        "source_url": "https://example.com/requests",
        "evidence_ids": ["evd_123e4567-e89b-12d3-a456-426614174001"],
        "detected_by": [DetectionMethod.SYFT],
        "confidence": 0.8,
    })
    merged = merge_components([first], [second])
    assert len(merged.components) == 1 and merged.components[0].source_url is None
    assert len(merged.components[0].evidence_ids) == 2
    assert merged.components[0].confidence == 0.8
    assert merged.diagnostics[0].code == "component_metadata_conflict"


def test_tool_output_is_bounded_and_invalid_json_is_not_promoted() -> None:
    assert parse_json_output(ToolExecution("syft", "complete", json.dumps({"artifacts": []}).encode())) == {"artifacts": []}
    assert parse_json_output(ToolExecution("syft", "complete", b"not-json")) is None
    unavailable = run_json_tool("openguard-tool-that-does-not-exist", ["--version"])
    assert unavailable.status == "unavailable" and unavailable.error_code == "tool_unavailable"


# Exercise the actual POSIX pipe/process-group boundary with controlled local
# programs, independent of installed ScanCode/Syft versions.
@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group contract")
def test_incremental_capture_stops_at_default_eight_mib(monkeypatch) -> None:
    reads = []
    actual_read = os.read

    def recorded_read(fd, size):
        chunk = actual_read(fd, size)
        reads.append((size, len(chunk)))
        return chunk

    monkeypatch.setattr(external_tools.os, "read", recorded_read)
    started = time.monotonic()
    execution = run_json_tool(
        sys.executable,
        ["-c", "import os,time; chunk=b'x'*65536\nwhile True: os.write(1,chunk)"],
        timeout_seconds=5,
    )
    assert execution.status == "failed"
    assert execution.error_code == "tool_output_limit_exceeded"
    assert execution.stdout is None
    assert time.monotonic() - started < 5
    # Popen also reads its startup-error pipe (zero bytes on success).
    assert sum(count for _, count in reads) == 8 * 1024 * 1024 + 1
    assert max(size for size, _ in reads) <= 65536


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group contract")
@pytest.mark.parametrize("size,status", [(4096, "complete"), (4097, "failed")])
def test_exact_capture_limit(size, status) -> None:
    execution = run_json_tool(
        sys.executable, ["-c", f"import os; os.write(1,b'x'*{size})"],
        max_output_bytes=4096,
    )
    assert execution.status == status
    if status == "complete":
        assert execution.stdout == b"x" * size
    else:
        assert execution.error_code == "tool_output_limit_exceeded"
        assert execution.stdout is None


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group contract")
def test_timeout_terminates_and_reaps_leader_and_descendant(tmp_path, monkeypatch) -> None:
    pid_file = tmp_path / "child.pid"
    code = '''import os,signal,time,sys
child = os.fork()
if child == 0:
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    open(sys.argv[1], 'w').write(str(os.getpid()))
    while True: time.sleep(.02)
def finish(*_):
    os.waitpid(child, 0)
    sys.exit(0)
signal.signal(signal.SIGTERM, finish)
while True: time.sleep(.02)
'''
    spawned = []
    actual_popen = subprocess.Popen

    def tracked_popen(*args, **kwargs):
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert kwargs["stderr"] == subprocess.DEVNULL
        assert kwargs["shell"] is False
        assert kwargs["close_fds"] is True
        assert kwargs["start_new_session"] is True
        process = actual_popen(*args, **kwargs)
        spawned.append(process)
        return process

    monkeypatch.setattr(external_tools.subprocess, "Popen", tracked_popen)
    started = time.monotonic()
    execution = run_json_tool(sys.executable, ["-c", code, str(pid_file)], timeout_seconds=1)
    assert execution == ToolExecution(sys.executable, "timeout", None, "scanner_timeout")
    assert time.monotonic() - started < 3
    assert spawned[0].poll() is not None
    assert spawned[0].stdout.closed
    child_pid = int(pid_file.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)
    with pytest.raises(ChildProcessError):
        os.waitpid(spawned[0].pid, os.WNOHANG)


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group contract")
def test_timeout_applies_after_stdout_closed() -> None:
    execution = run_json_tool(
        sys.executable, ["-c", "import os,time; os.close(1); time.sleep(30)"], timeout_seconds=1,
    )
    assert execution.status == "timeout" and execution.error_code == "scanner_timeout"


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group contract")
def test_runtime_environment_and_diagnostics_are_sanitized(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "never-forward-this-secret")
    monkeypatch.setenv("SCANCODE_CACHE", "/caller-chosen-cache")
    monkeypatch.setenv("SCANCODE_TEMP", "/caller-chosen-temp")
    monkeypatch.setenv("SYFT_CHECK_FOR_APP_UPDATE", "true")
    execution = run_json_tool(
        sys.executable, ["-c", "import os,json; print(json.dumps(dict(os.environ)))"],
        disable_update_check=True, scancode_runtime=True,
    )
    environment = parse_json_output(execution)
    assert environment is not None
    assert "OPENAI_API_KEY" not in environment
    assert environment["SYFT_CHECK_FOR_APP_UPDATE"] == "false"
    assert environment["SCANCODE_CACHE"] == "/tmp/scancode-cache"
    assert environment["SCANCODE_TEMP"] == "/tmp"
    failed = run_json_tool(sys.executable, ["-c", "import sys; print('secret',file=sys.stderr); sys.exit(9)"])
    assert failed == ToolExecution(sys.executable, "failed", None, "scanner_failed")


def test_fixed_scanner_invocations(monkeypatch) -> None:
    calls = []

    def capture(tool, arguments, **kwargs):
        calls.append((tool, arguments, kwargs))
        return ToolExecution(tool, "complete", b"{}")

    monkeypatch.setattr(external_tools, "run_json_tool", capture)
    external_tools.run_scancode_license_scan("scancode", "/proc/self/fd/9", pass_fds=(9,))
    external_tools.run_syft_sbom_scan("syft", "/proc/self/fd/9", pass_fds=(9,))
    assert calls[0] == (
        "scancode", ("--processes", "1", "--license", "--strip-root", "--json", "-", "."),
        {"timeout_seconds": 120, "max_output_bytes": 8 * 1024 * 1024, "pass_fds": (9,), "scancode_runtime": True, "working_directory": "/proc/self/fd/9"},
    )
    assert calls[1] == (
        "syft", ("scan", "dir:/proc/self/fd/9", "-o", "syft-json"),
        {"timeout_seconds": 120, "max_output_bytes": 8 * 1024 * 1024, "pass_fds": (9,), "disable_update_check": True},
    )


@pytest.mark.parametrize("target,fds", [
    ("/proc/self/fd/9/../../etc", (9,)), ("/proc/self/fd/9suffix", (9,)),
    ("/proc/self/fd/９", (9,)), ("/proc/self/fd/09", (9,)),
    ("/proc/self/fd/9", (8,)), ("/proc/self/fd/9", (9, 10)),
    ("/proc/self/fd/9", ()), ("/tmp/root", (9,)),
])
@pytest.mark.parametrize("wrapper", [external_tools.run_scancode_license_scan, external_tools.run_syft_sbom_scan])
def test_fixed_scanner_rejects_non_exact_or_mismatched_fd(target, fds, wrapper) -> None:
    with pytest.raises(ValueError):
        wrapper("tool", target, pass_fds=fds)


@pytest.mark.skipif(os.name != "posix", reason="POSIX cwd contract")
def test_real_subprocess_reads_contents_from_trusted_working_directory(tmp_path) -> None:
    (tmp_path / "LICENSE").write_text("controlled-license")
    descriptor = os.open(tmp_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        # Linux exercises the actual proc-FD target. macOS lacks procfs, so
        # exercise the same Popen cwd/read behavior using the controlled path.
        directory = f"/proc/self/fd/{descriptor}" if sys.platform == "linux" else str(tmp_path)
        execution = run_json_tool(
            sys.executable,
            ["-c", "import json,pathlib; print(json.dumps({'license':pathlib.Path('LICENSE').read_text()}))"],
            working_directory=directory, pass_fds=(descriptor,),
        )
        assert execution.status == "complete"
        assert parse_json_output(execution) == {"license": "controlled-license"}
    finally:
        os.close(descriptor)
