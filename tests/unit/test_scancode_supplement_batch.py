"""Task-private initialization reuse must preserve all supplement gates."""
import json
import sys
from types import ModuleType
from datetime import datetime, timezone

import pytest

from app.ingestion.inventory import Inventory, InventoryEntry
from app.scanners import external_tools as tools, scancode_pipeline as pipeline
from app.security.errors import IngestionSecurityError


PATHS = ["a/.gitignore", "b/.gitignore", "c/.gitignore"]


class Tree:
    inherited_fds = (9,)

    def proc_target(self):
        return "/proc/self/fd/9"


def documents():
    return [{"files": [{"path": ".gitignore", "type": "file", "sha256": character * 64,
                        "detected_license_expression": "mit", "scan_errors": []}]}
            for character in "abc"]


def scan(monkeypatch, raw=None, status="complete", error=None, calls=None):
    clock = [0.0]
    calls = calls if calls is not None else []

    def tree_scan(*a, **kw):
        clock[0] += 4
        return tools.ToolExecution("scancode", "complete", b'{"files":[]}')

    def batch(*a, **kw):
        calls.append((a, kw))
        clock[0] += 5
        data = raw if raw is not None else b"\n".join(json.dumps(d).encode() for d in documents())
        return tools.ToolExecution("python", status, data, error)

    monkeypatch.setattr(pipeline, "run_scancode_license_scan", tree_scan)
    monkeypatch.setattr(pipeline, "_run_scancode_supplements", batch)
    monkeypatch.setattr(pipeline.time, "monotonic", lambda: clock[0])
    inventory = Inventory(tuple(InventoryEntry(path, 1, character * 64) for path, character in zip(PATHS, "abc")), "0" * 64)
    return pipeline.scan_sealed_tree(Tree(), inventory, executable=tools._PINNED_SCANCODE,
        tool_version="32.5.0", observed_at=datetime(2026, 9, 10, tzinfo=timezone.utc))


def test_same_basename_files_keep_distinct_paths_hashes_and_shared_budget(monkeypatch):
    calls = []
    result = scan(monkeypatch, calls=calls)
    assert [e.locator for e in result.mapping.evidence] == PATHS
    assert [e.content_hash.value for e in result.mapping.evidence] == [c * 64 for c in "abc"]
    assert len({e.id for e in result.mapping.evidence}) == 3
    assert calls == [(("/proc/self/fd/9", PATHS), {
        "pass_fds": (9,), "timeout_seconds": 356,
        "max_output_bytes": 8 * 1024 * 1024 - len(b'{"files":[]}'),
    })]


@pytest.mark.parametrize("raw", [b"", b"{}", b"{} {} {} {}", b"{} {} {} trailing", b"{} {} []", b"\xff", b"{} {} {", b'{"files":[]}\n{}\n{}'])
def test_missing_extra_invalid_or_truncated_documents_are_rejected(monkeypatch, raw):
    with pytest.raises(IngestionSecurityError):
        scan(monkeypatch, raw)


@pytest.mark.parametrize("bad", [{"path": "b/.gitignore"}, {"path": "../.gitignore"},
    {"sha256": "a" * 64}, {"sha256": None}, {"type": "directory"}, {"scan_errors": ["bad"]}])
def test_second_file_still_requires_exact_inventory_binding(monkeypatch, bad):
    parts = documents()
    parts[1]["files"][0].update(bad)
    with pytest.raises(IngestionSecurityError):
        scan(monkeypatch, b"\n".join(json.dumps(d).encode() for d in parts))


@pytest.mark.parametrize("status,error", [("timeout", "scanner_timeout"), ("failed", "scanner_failed"),
    ("failed", "tool_output_limit_exceeded"), ("unavailable", "tool_unavailable")])
def test_failed_batch_never_promotes_successful_prefix(monkeypatch, status, error):
    with pytest.raises(IngestionSecurityError) as caught:
        scan(monkeypatch, status=status, error=error)
    assert caught.value.reason == error


@pytest.mark.parametrize("paths", [[], ["a"], ["a"] * 3, [str(i) for i in range(9)],
    ["a", "../b"], ["a", "/b"], ["a", "x\\b"], ["a", "./b"], ["a", None]])
def test_batch_paths_are_bounded_relative_and_unique(paths):
    with pytest.raises(ValueError):
        tools._run_scancode_supplements("/proc/self/fd/9", paths, pass_fds=(9,), timeout_seconds=20, max_output_bytes=1000)


def test_batch_runner_keeps_fixed_interpreter_sandbox_arguments_and_limits(monkeypatch):
    calls = []
    monkeypatch.setattr(tools, "run_json_tool", lambda *a, **kw: calls.append((a, kw)))
    tools._run_scancode_supplements("/proc/self/fd/9", ["--help", "a/'quoted'"],
        pass_fds=(9,), timeout_seconds=35, max_output_bytes=1024)
    assert calls == [(("/opt/scancode/venv/bin/python",
        ("-I", "-c", tools._SCANCODE_SUPPLEMENT_PROGRAM, "--help", "a/'quoted'")),
        {"timeout_seconds": 35, "max_output_bytes": 1024, "pass_fds": (9,),
         "scancode_runtime": True, "working_directory": "/proc/self/fd/9"})]


def test_isolated_interpreter_does_not_import_target_modules(tmp_path, monkeypatch):
    marker = tmp_path / "executed"
    (tmp_path / "json.py").write_text("from pathlib import Path\nPath('executed').touch()\nraise RuntimeError('target executed')\n")
    (tmp_path / "scancode.py").write_text("from pathlib import Path\nPath('executed').touch()\n")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    result = tools.run_json_tool(sys.executable, ("-I", "-c",
        "import json,importlib.util; print(json.dumps({'json':json.__file__, 'scancode':str(importlib.util.find_spec('scancode'))}))"),
        working_directory=str(tmp_path))
    assert result.status == "complete"
    assert str(tmp_path).encode() not in result.stdout
    assert not marker.exists()


@pytest.mark.parametrize("exit_code", [1, 2, None, False, "0"])
def test_cli_failure_stops_before_next_file(monkeypatch, exit_code):
    calls = []
    module = ModuleType("scancode.cli")

    class Command:
        def main(self, *, args, standalone_mode):
            calls.append(args)
            assert standalone_mode is False
            return 0 if len(calls) == 1 else exit_code

    module.scancode = Command()
    monkeypatch.setitem(sys.modules, "scancode.cli", module)
    monkeypatch.setattr(sys, "argv", ["helper", *PATHS])
    with pytest.raises(SystemExit) as caught:
        exec(tools._SCANCODE_SUPPLEMENT_PROGRAM, {})
    assert caught.value.code == 1
    assert len(calls) == 2
    assert calls[0] == ['--processes', '0', '--license', '--info', '--strip-root', '--json', '-', './a/.gitignore']


def test_cli_exception_stops_before_next_file(monkeypatch):
    calls = []
    module = ModuleType("scancode.cli")

    class Command:
        def main(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 2:
                raise RuntimeError("scanner failed")
            return 0

    module.scancode = Command()
    monkeypatch.setitem(sys.modules, "scancode.cli", module)
    monkeypatch.setattr(sys, "argv", ["helper", *PATHS])
    with pytest.raises(RuntimeError, match="scanner failed"):
        exec(tools._SCANCODE_SUPPLEMENT_PROGRAM, {})
    assert len(calls) == 2
