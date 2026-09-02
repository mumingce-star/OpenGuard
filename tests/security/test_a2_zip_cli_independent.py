"""Independent security regression tests for the offline local-ZIP CLI."""

from __future__ import annotations

import io
import json
import os
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


def _module(arguments: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    return subprocess.run(
        [sys.executable, "-m", "app.cli", *arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )


def test_repeated_valid_zip_runs_emit_identical_sorted_json(tmp_path: Path) -> None:
    archive_path = tmp_path / "input.zip"
    _archive(
        archive_path,
        [("z.txt", b"z"), ("ordinary/file~.txt", b"tilde"), ("a.txt", b"a")],
    )

    first = _invoke([str(archive_path)])
    second = _invoke([str(archive_path)])

    assert first[0] == second[0] == 0
    assert first[2] == second[2] == ""
    assert first[1] == second[1]
    payload = json.loads(first[1])
    assert [entry["relative_path"] for entry in payload["entries"]] == [
        "a.txt",
        "ordinary/file~.txt",
        "z.txt",
    ]
    assert first[1] == json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    assert str(tmp_path) not in first[1]


def test_traversal_rejection_has_stable_stderr_empty_stdout_and_no_residual_workspace(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    _archive(archive_path, [("../escape.txt", b"blocked")])

    exit_code, stdout, stderr = _invoke([str(archive_path)])

    assert (exit_code, stdout, stderr) == (1, "", "invalid_archive:archive_path_unsafe\n")
    assert str(tmp_path) not in stderr
    assert "Traceback" not in stderr

    workspace_root = tmp_path / "workspace-root"
    workspace_root.mkdir(mode=0o700)
    with pytest.raises(IngestionSecurityError, match="invalid_archive:archive_path_unsafe"):
        cli.run_local_zip(archive_path, workspace_root)
    assert list(workspace_root.iterdir()) == []


def test_missing_directory_non_zip_and_wrong_arguments_are_sanitized(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.zip"
    directory_path = tmp_path / "directory-input"
    directory_path.mkdir()
    non_zip_path = tmp_path / "not-a-zip.bin"
    non_zip_path.write_bytes(b"plain bytes")

    cases = [
        ([str(missing_path)], 2, "invalid_request:input_file_unavailable\n"),
        ([str(directory_path)], 2, "invalid_request:input_file_unavailable\n"),
        ([str(non_zip_path)], 1, "invalid_archive:archive_not_zip\n"),
        ([], 2, "invalid_request:invalid_arguments\n"),
        ([str(missing_path), "extra"], 2, "invalid_request:invalid_arguments\n"),
    ]
    for arguments, expected_code, expected_stderr in cases:
        exit_code, stdout, stderr = _invoke(arguments)
        assert exit_code == expected_code
        assert stdout == ""
        assert stderr == expected_stderr
        assert str(tmp_path) not in stderr
        assert "Traceback" not in stderr


def test_module_subprocess_exposes_exit_codes_zero_one_two_without_path_leaks(tmp_path: Path) -> None:
    repo_root = Path(__file__).parents[2]
    valid_path = tmp_path / "valid.zip"
    unsafe_path = tmp_path / "unsafe.zip"
    missing_path = tmp_path / "missing.zip"
    _archive(valid_path, [("file.txt", b"ok")])
    _archive(unsafe_path, [("../escape.txt", b"blocked")])

    successful = _module([str(valid_path)], cwd=repo_root)
    rejected = _module([str(unsafe_path)], cwd=repo_root)
    usage_error = _module([], cwd=repo_root)

    assert (successful.returncode, successful.stderr) == (0, "")
    assert json.loads(successful.stdout)["entries"][0]["relative_path"] == "file.txt"
    assert (rejected.returncode, rejected.stdout, rejected.stderr) == (
        1,
        "",
        "invalid_archive:archive_path_unsafe\n",
    )
    assert (usage_error.returncode, usage_error.stdout, usage_error.stderr) == (
        2,
        "",
        "invalid_request:invalid_arguments\n",
    )
    for output in (successful.stdout, successful.stderr, rejected.stderr, usage_error.stderr):
        assert str(tmp_path) not in output
        assert "Traceback" not in output

    missing = _module([str(missing_path)], cwd=repo_root)
    assert (missing.returncode, missing.stdout, missing.stderr) == (
        2,
        "",
        "invalid_request:input_file_unavailable\n",
    )
    assert str(tmp_path) not in missing.stderr


def test_run_local_zip_cleans_explicit_workspace_after_success_and_rejection(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace-root"
    workspace_root.mkdir(mode=0o700)
    valid_path = tmp_path / "valid.zip"
    unsafe_path = tmp_path / "unsafe.zip"
    _archive(valid_path, [("file.txt", b"ok")])
    _archive(unsafe_path, [("../escape.txt", b"blocked")])

    result = cli.run_local_zip(valid_path, workspace_root)
    assert [entry.relative_path for entry in result.entries] == ["file.txt"]
    assert list(workspace_root.iterdir()) == []

    with pytest.raises(IngestionSecurityError, match="invalid_archive:archive_path_unsafe"):
        cli.run_local_zip(unsafe_path, workspace_root)
    assert list(workspace_root.iterdir()) == []
