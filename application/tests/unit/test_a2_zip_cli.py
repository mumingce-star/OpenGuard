"""Implementation-owned tests for the offline A2 ZIP demonstration CLI."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from app import cli
from app.security.errors import IngestionSecurityError


def _archive(path: Path, entries: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in entries:
            archive.writestr(name, content)


def _invoke(arguments: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = cli.main(arguments, stdout=stdout, stderr=stderr)
    return exit_code, stdout.getvalue(), stderr.getvalue()


def test_cli_emits_stable_inventory_json_for_a_local_zip(tmp_path: Path) -> None:
    archive_path = tmp_path / "input.zip"
    _archive(archive_path, [("z.txt", b"z"), ("docs/readme.txt", b"alpha")])

    exit_code, stdout, stderr = _invoke([str(archive_path)])

    assert exit_code == 0
    assert stderr == ""
    assert json.loads(stdout) == {
        "schema": "openguard.zip-inventory",
        "version": "1",
        "root_digest": "58d969600536dc295f43c4d5d17cc904e0f313b0efb768ce197c7a190160f89e",
        "entries": [
            {
                "relative_path": "docs/readme.txt",
                "size_bytes": 5,
                "sha256": "8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8",
            },
            {
                "relative_path": "z.txt",
                "size_bytes": 1,
                "sha256": "594e519ae499312b29433b7dd8a97ff068defcba9755b6d5d00e84c524d67b06",
            },
        ],
    }


def test_cli_rejects_unsafe_archive_without_echoing_the_input_path(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    _archive(archive_path, [("../escape.txt", b"blocked")])

    exit_code, stdout, stderr = _invoke([str(archive_path)])

    assert exit_code == 1
    assert stdout == ""
    assert stderr == "invalid_archive:archive_path_unsafe\n"
    assert str(archive_path) not in stderr


def test_python_module_entrypoint_emits_the_same_json(tmp_path: Path) -> None:
    archive_path = tmp_path / "input.zip"
    _archive(archive_path, [("file.txt", b"module entrypoint")])

    completed = subprocess.run(
        [sys.executable, "-m", "app.cli", str(archive_path)],
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    assert json.loads(completed.stdout)["entries"] == [
        {
            "relative_path": "file.txt",
            "size_bytes": len(b"module entrypoint"),
            "sha256": "cdccd888b48591016a5b2bc785bf0dab3f9bb9b9f5a0f71d24e5ed5a5a921736",
        }
    ]


def test_cli_hides_missing_path_and_usage_details(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.zip"

    missing_code, missing_stdout, missing_stderr = _invoke([str(missing_path)])
    usage_code, usage_stdout, usage_stderr = _invoke([])

    assert (missing_code, missing_stdout, missing_stderr) == (2, "", "invalid_request:input_file_unavailable\n")
    assert str(missing_path) not in missing_stderr
    assert (usage_code, usage_stdout, usage_stderr) == (2, "", "invalid_request:invalid_arguments\n")


def test_cli_runner_leaves_no_task_workspace_after_success_or_rejection(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace-root"
    workspace_root.mkdir(mode=0o700)
    valid_archive = tmp_path / "valid.zip"
    unsafe_archive = tmp_path / "unsafe.zip"
    _archive(valid_archive, [("file.txt", b"ok")])
    _archive(unsafe_archive, [("../escape.txt", b"blocked")])

    cli.run_local_zip(valid_archive, workspace_root)
    assert list(workspace_root.iterdir()) == []

    with pytest.raises(IngestionSecurityError, match="invalid_archive:archive_path_unsafe"):
        cli.run_local_zip(unsafe_archive, workspace_root)
    assert list(workspace_root.iterdir()) == []
