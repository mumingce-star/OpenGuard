"""Offline subprocess contracts for the public openguard.py scan command."""

from base64 import b64encode
import builtins
from hashlib import sha256
from importlib.metadata import distribution
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import sysconfig
from types import SimpleNamespace
import venv
from zipfile import ZipFile

import pytest

from deployment import launcher


ROOT = Path(__file__).resolve().parents[3]
SAMPLE = "samples/is-number-7.0.0-derived.zip"
SCHEMA = "openguard-cli-scan/2"
ECOSYSTEMS = {"npm", "pypi", "golang", "cargo", "maven", "unknown"}
REPORT_FIELDS = {
    "schema_version", "input", "scan", "root_packages", "components", "conflicts",
    "root_license_checks", "copyleft_findings", "license_compatibility", "diagnostics", "policy",
}
PACKAGE = {
    "name": "cli-fixture", "version": "1.0.0", "license": "MIT",
    "dependencies": {"synthetic-dependency": "1.0.0"},
}
GO_MOD = b"module example.invalid/CliRoot\n\nrequire example.invalid/CliWatch v1.0.0\n"
GO_SUM = b"example.invalid/CliWatch v1.2.0 h1:" + b64encode(sha256(b"task56-test-only").digest()) + b"\n"


@pytest.fixture(scope="module")
def package(tmp_path_factory):
    """Keep the executable and actual product rules in a disposable package."""
    copy = tmp_path_factory.mktemp("task56-launcher")
    for relative in (
        "deployment", "application/backend/app", "application/examples",
        "application/rules", "application/schemas", "samples",
    ):
        shutil.copytree(ROOT / relative, copy / relative, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(ROOT / "openguard.py", copy / "openguard.py")
    assert not (copy / "runtime").exists()
    return copy


def _project(path, *, license_id="MIT"):
    path.mkdir()
    (path / "package.json").write_text(
        json.dumps({**PACKAGE, "license": license_id}), encoding="utf-8",
    )
    return path


def _run(package, scratch, *arguments, suppress_bytecode=True, python=sys.executable):
    isolated_tmp = scratch / "command-tmp"
    isolated_tmp.mkdir(exist_ok=True)
    runtime = package / "runtime"
    runtime_existed = runtime.exists()
    environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith("OPENGUARD_")
        and key not in {
            "_OPENGUARD_SCAN_REEXEC", "PYTHONHOME", "PYTHONPATH",
            "PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX",
        }
    }
    environment.update(
        TMPDIR=str(isolated_tmp), TMP=str(isolated_tmp), TEMP=str(isolated_tmp), PYTHONNOUSERSITE="1",
    )
    command = [str(python)]
    if suppress_bytecode:
        command.append("-B")
    result = subprocess.run(
        [*command, str(package / "openguard.py"), "scan", *map(str, arguments)],
        cwd=package, env=environment, capture_output=True, text=True, timeout=80,
    )
    assert runtime.exists() is runtime_existed
    assert not list(isolated_tmp.iterdir()), "Headless scanner left temporary files"
    for stream in (result.stdout, result.stderr):
        assert str(scratch) not in stream
        assert str(scratch.resolve()) not in stream
        assert str(package) not in stream
    return result


def _cli_venv(path, *, locked=False, startup_log=None):
    venv.EnvBuilder(with_pip=False, symlinks=True).create(path)
    path.chmod(0o700)
    (path / "bin").chmod(0o700)
    (path / "pyvenv.cfg").chmod(0o600)
    prefix = str(path)
    packages = Path(sysconfig.get_path("purelib", "venv", vars={"base": prefix, "platbase": prefix}))
    assert packages.is_dir()
    if locked:
        for name, version in launcher.pins().items():
            installed = distribution(name)
            assert installed.version == version and installed.files is not None
            for member in installed.files:
                # Copy importable wheel contents, not console scripts or caches.
                if not member.is_absolute() and not {"..", "__pycache__"}.intersection(member.parts):
                    destination = packages / member
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(installed.locate_file(member), destination)
    if startup_log is not None:
        # The interpreter may visit the venv site directory twice at startup.
        # Write one record per process image, disjoint from the runtime tree.
        observation = (
            "import json, os, sys\n"
            "if not getattr(sys, '_task56b_startup_recorded', False):\n"
            "    sys._task56b_startup_recorded = True\n"
            f"    with open({str(startup_log)!r}, 'a', encoding='utf-8') as log:\n"
            "        log.write(json.dumps([os.getpid(), sys.prefix, "
            "os.getenv('_OPENGUARD_SCAN_REEXEC'), sys.flags.dont_write_bytecode, "
            "os.getenv('PYTHONDONTWRITEBYTECODE'), sys.executable, sys.orig_argv]) + '\\n')\n"
        )
        (packages / "task56b-startup.pth").write_text(f"import sys; exec({observation!r})\n", encoding="utf-8")
    return path / "bin/python"


def _runtime_snapshot(runtime):
    snapshot = {}
    for path in [runtime, *runtime.rglob("*")]:
        status = path.lstat()
        if path.is_symlink():
            content = os.readlink(path)
        elif path.is_file():
            with path.open("rb") as stream:
                content = sha256(stream.read()).hexdigest()
        else:
            assert path.is_dir()
            content = None
        snapshot[path.relative_to(runtime)] = (status.st_mode, status.st_mtime_ns, status.st_ctime_ns, content)
    return snapshot


def _assert_locked_python_required(result):
    assert result.returncode == 2 and not result.stdout
    assert result.stderr.startswith("ERROR: scan_requires_locked_python.")
    assert "openguard.py setup" in result.stderr


def _assert_scan_reexec(startup_log, external, runtime, package, arguments):
    records = startup_log.read_text(encoding="utf-8").splitlines()
    assert len(records) == 2
    initial, resumed = map(json.loads, records)
    assert len(initial) == len(resumed) == 7
    pid = initial[0]
    command = [str(package / "openguard.py"), "scan", *arguments]
    assert initial[:6] == [pid, str(external.parent.parent), None, 0, None, str(external)]
    assert resumed[:6] == [pid, str(runtime.parent.parent), "1", 1, "1", str(runtime)]
    assert initial[6][1:] == command
    assert resumed[6][1:] == ["-B", *command]
    # Python.framework can rewrite argv[0] without changing the venv executable.
    assert initial[6][0] in {str(external), sys.orig_argv[0]}
    assert resumed[6][0] in {str(runtime), sys.orig_argv[0]}


def test_assert_scan_reexec_accepts_framework_argv0_and_rejects_mismatches(tmp_path, monkeypatch):
    package = tmp_path / "package"
    external = tmp_path / "external" / "bin" / "python"
    runtime = package / "runtime" / "venv" / "bin" / "python"
    arguments = [SAMPLE, "--format", "json"]
    command = [str(package / "openguard.py"), "scan", *arguments]
    framework = "/Library/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python"
    monkeypatch.setattr(sys, "orig_argv", [framework, *sys.orig_argv[1:]])
    pid = os.getpid()
    initial = [pid, str(external.parent.parent), None, 0, None, str(external), [framework, *command]]
    resumed = [pid, str(runtime.parent.parent), "1", 1, "1", str(runtime), [framework, "-B", *command]]
    startup_log = tmp_path / "interpreter-starts.jsonl"

    def check(initial_record, resumed_record):
        startup_log.write_text(f"{json.dumps(initial_record)}\n{json.dumps(resumed_record)}\n", encoding="utf-8")
        _assert_scan_reexec(startup_log, external, runtime, package, arguments)

    check(initial, resumed)
    with pytest.raises(AssertionError):
        check(initial, [*resumed[:5], str(external), resumed[6]])
    with pytest.raises(AssertionError):
        check(initial, [*resumed[:6], [framework, *command]])
    with pytest.raises(AssertionError):
        check(initial, [*resumed[:6], [str(external), "-B", *command]])


def _json_report(result, *, exit_code=0):
    assert result.returncode == exit_code, result.stderr
    assert not result.stderr
    report = json.loads(result.stdout)
    assert set(report) == REPORT_FIELDS and report["schema_version"] == SCHEMA
    assert set(report["scan"]["ecosystem_counts"]) == ECOSYSTEMS
    assert report["scan"]["component_count"] == len(report["components"])
    assert report["scan"]["root_package_count"] == len(report["root_packages"])
    assert report["scan"]["conflict_count"] == len(report["conflicts"])
    assert report["scan"]["copyleft_count"] == len(report["copyleft_findings"])
    assert report["policy"]["exit_code"] == exit_code
    assert len(report["input"]["sha256"]) == len(report["input"]["root_digest"]) == 64
    assert all(not row["file_path"].startswith("/") for item in report["components"]
               for row in item["evidence"] if row["file_path"])
    return report


@pytest.fixture
def mixed(tmp_path):
    tree = _project(tmp_path / "five-ecosystems")
    (tree / "requirements.txt").write_text("synthetic-py==1.0.0\n", encoding="utf-8")
    (tree / "go.mod").write_bytes(GO_MOD)
    (tree / "go.sum").write_bytes(GO_SUM)
    (tree / "Cargo.toml").write_text(
        '[package]\nname = "cli-rust"\nversion = "1.0.0"\nlicense = "MIT"\n'
        '[dependencies]\ncli-crate = "=1.2.3"\n',
        encoding="utf-8",
    )
    (tree / "pom.xml").write_text(
        '<project xmlns="http://maven.apache.org/POM/4.0.0">'
        '<modelVersion>4.0.0</modelVersion><groupId>org.cli</groupId>'
        '<artifactId>sample</artifactId><version>1.0.Final</version>'
        '<licenses><license><name>MIT</name></license></licenses>'
        '<dependencies><dependency><groupId>org.cli</groupId>'
        '<artifactId>fixture</artifactId><version>1.0.Final</version>'
        '</dependency></dependencies></project>',
        encoding="utf-8",
    )
    for i, directory in enumerate((".git", "node_modules", "target", "__pycache__")):
        ignored = tree / "nested" / directory
        ignored.mkdir(parents=True)
        (ignored / "requirements.txt").write_text(f"ignored-dependency-{i}==1.0.0\n", encoding="utf-8")
    return tree


def _assert_mixed(report):
    assert all(report["scan"]["ecosystem_counts"][name] > 0 for name in ECOSYSTEMS - {"unknown"})
    assert {"npm", "cargo", "maven"} == {root["ecosystem"] for root in report["root_packages"]}
    assert not any(row["name"].startswith("ignored-dependency-") for row in report["components"])
    (conflict,) = report["conflicts"]
    assert (conflict["ecosystem"], conflict["name"], conflict["status"]) == (
        "golang", "example.invalid/CliWatch", "confirmed",
    )
    for key, version, path, raw in (
        ("declaration", "v1.0.0", "go.mod", GO_MOD),
        ("lock", "v1.2.0", "go.sum", GO_SUM),
    ):
        assert conflict[key]["version"] == version
        assert any(item["file_path"] == path and item["source_sha256"] == sha256(raw).hexdigest()
                   and item["locator"] for item in conflict[key]["evidence"])


def test_directory_five_ecosystems_exclusions_and_determinism(package, tmp_path, mixed):
    first = _run(package, tmp_path, mixed, "--format", "json", "--usage", "modified,commercial")
    report = _json_report(first)
    assert report["input"]["kind"] == "directory" and report["input"]["name"] == mixed.name
    assert report["input"]["excluded_dirs"] == [
        "nested/.git", "nested/__pycache__", "nested/node_modules", "nested/target",
    ]
    assert report["scan"]["usage"] == {"commercial": True, "distributed": False, "modified": True, "network_service": False}
    _assert_mixed(report)
    repeated = _run(package, tmp_path, mixed, "--format", "json", "--usage", "commercial,modified")
    _json_report(repeated)
    assert repeated.stdout == first.stdout
    gated = _json_report(
        _run(package, tmp_path, mixed, "--format", "json", "--fail-on", "conflict"), exit_code=1,
    )
    assert gated["policy"] == {"fail_on": ["conflict"], "triggered": ["conflict"], "exit_code": 1}


def test_local_sample_zip_uses_pinned_interpreter_without_package_runtime(package, tmp_path):
    sample = package / SAMPLE
    report = _json_report(_run(package, tmp_path, sample, "--format", "json"))
    assert report["input"]["kind"] == "zip" and report["input"]["name"] == sample.name
    assert report["input"]["sha256"] == sha256(sample.read_bytes()).hexdigest()
    assert any(row["name"] == "is-number" for row in report["components"])
    assert report["scan"]["usage"] == {"commercial": False, "distributed": False, "modified": False, "network_service": False}


def test_scan_without_python_bytecode_flag_leaves_package_untouched(package, tmp_path):
    clean = shutil.copytree(package, tmp_path / "clean-package")
    assert not list(clean.rglob("__pycache__"))
    report = _json_report(_run(clean, tmp_path, SAMPLE, "--format", "json", suppress_bytecode=False))
    assert any(row["name"] == "is-number" for row in report["components"])
    assert not list(clean.rglob("__pycache__"))
    assert not list(clean.rglob("*.pyc"))


def test_multiecosystem_zip_and_combined_policy(package, tmp_path, mixed):
    archive = tmp_path / "polyglot.zip"
    with ZipFile(archive, "w") as target:
        for path in sorted(mixed.iterdir()):
            if path.is_file():
                target.write(path, path.name)
    report = _json_report(
        _run(package, tmp_path, archive, "--format", "json", "--fail-on", "copyleft,conflict,conflict"),
        exit_code=1,
    )
    assert report["input"]["kind"] == "zip"
    _assert_mixed(report)
    assert report["policy"] == {"fail_on": ["conflict", "copyleft"], "triggered": ["conflict"], "exit_code": 1}


def test_partial_policy_and_default_partial_exit(package, tmp_path):
    tree = _project(tmp_path / "partial")
    (tree / "Cargo.lock").write_text("version = 99\n", encoding="utf-8")
    report = _json_report(_run(package, tmp_path, tree, "--format", "json"))
    assert report["scan"]["status"] == "partial" and report["scan"]["gap_count"] > 0
    gated = _json_report(
        _run(package, tmp_path, tree, "--format", "json", "--fail-on", "partial"), exit_code=1,
    )
    assert gated["policy"]["triggered"] == ["partial"]
    assert not report["policy"]["triggered"]


@pytest.mark.parametrize("format", ["text", "markdown"])
def test_human_output_formats(package, tmp_path, format):
    result = _run(package, tmp_path, SAMPLE, "--format", format)
    assert result.returncode == 0 and not result.stderr
    assert "is-number" in result.stdout and not result.stdout.lstrip().startswith("{")
    if format == "markdown":
        assert "|" in result.stdout and "---" in result.stdout


def test_output_creates_a_file_even_when_a_completed_policy_is_triggered(package, tmp_path):
    tree = _project(tmp_path / "copyleft", license_id="GPL-3.0-only")
    report_file = tmp_path / "report.json"
    result = _run(package, tmp_path, tree, "--format", "json", "--output", report_file, "--fail-on", "copyleft")
    assert result.returncode == 1 and not result.stdout and not result.stderr
    report = json.loads(report_file.read_text(encoding="utf-8"))
    assert report["schema_version"] == SCHEMA and report["policy"]["triggered"] == ["copyleft"]


@pytest.mark.parametrize(("filename", "declared", "conflict"), [
    ("LICENSE", "MIT", True), ("COPYING.txt", "MIT", True),
    ("LICENSE.md", "GPL-3.0-only", False), ("COPYING", "GPL-3.0-or-later", False),
])
def test_root_license_original_bytes_and_conservative_policy(package, tmp_path, filename, declared, conflict):
    tree = _project(tmp_path / "license-profile", license_id=declared)
    profile = json.loads(
        (ROOT / "application/tests/fixtures/task49-copyleft-licenses.json").read_text(encoding="utf-8"),
    )["licenses"]["GPL-3.0"]
    raw = profile["text"].encode("utf-8")
    assert sha256(raw).hexdigest() == profile["sha256"]
    (tree / filename).write_bytes(raw)
    report = _json_report(
        _run(package, tmp_path, tree, "--format", "json", "--fail-on", "copyleft"), exit_code=1,
    )
    (check,) = report["root_license_checks"]
    assert check["file_path"] == filename and check["sha256"] == profile["sha256"]
    assert check["text_license"] == check["copyleft_family"] == "GPL-3.0"
    assert check["declared_license"] == declared and check["spdx_text_conflict"] is conflict
    assert check["root_package_id"] == report["root_packages"][0]["id"]
    assert check["support_state"] == "UNKNOWN"
    assert any(finding["severity"] == "strong" for finding in report["copyleft_findings"])


@pytest.mark.parametrize("arguments", [
    ("--fail-on", "unsupported"),
    ("--usage", "unsupported"),
    ("--format", "unsupported"),
])
def test_invalid_cli_flags_leave_no_output(package, tmp_path, arguments):
    output = tmp_path / "report.json"
    result = _run(package, tmp_path, SAMPLE, "--output", output, *arguments)
    assert result.returncode == 2 and result.stderr and not result.stdout and not output.exists()


@pytest.mark.parametrize("kind", ["missing", "empty", "unsupported", "non_zip", "oversize_file", "oversize_zip"])
def test_invalid_targets_are_fail_closed(package, tmp_path, kind):
    target = tmp_path / "input"
    if kind == "empty":
        target.mkdir()
    elif kind == "unsupported":
        target.mkdir()
        (target / "plain.txt").write_text("TEST_ONLY non-manifest", encoding="utf-8")
    elif kind == "non_zip":
        target.write_text("TEST_ONLY plain file", encoding="utf-8")
    elif kind == "oversize_file":
        _project(target)
        with (target / "oversize.bin").open("wb") as file:
            file.truncate(32 * 1024 * 1024 + 1)
    elif kind == "oversize_zip":
        target = target.with_suffix(".zip")
        with target.open("wb") as file:
            file.truncate(64 * 1024 * 1024 + 1)
    output = tmp_path / "report.json"
    result = _run(package, tmp_path, target, "--output", output)
    assert result.returncode == 2 and result.stderr and not result.stdout and not output.exists()


def test_nested_symlink_is_skipped_and_root_symlink_is_rejected(package, tmp_path):
    tree = _project(tmp_path / "project")
    outside = tmp_path / "outside-requirements.txt"
    outside.write_text("must-not-escape==1.0.0\n", encoding="utf-8")
    (tree / "requirements.txt").symlink_to(outside)
    report = _json_report(_run(package, tmp_path, tree, "--format", "json"))
    assert report["scan"]["status"] == "partial"
    assert not any(row["name"] == "must-not-escape" for row in report["components"])
    root_link = tmp_path / "root-link"
    root_link.symlink_to(tree, target_is_directory=True)
    refused = _run(package, tmp_path, root_link, "--format", "json")
    assert refused.returncode == 2 and refused.stderr and not refused.stdout


@pytest.mark.parametrize("existing", ["file", "symlink"])
def test_output_never_overwrites_or_follows_symlinks(package, tmp_path, existing):
    sentinel = tmp_path / "sentinel"
    sentinel.write_text("TEST_ONLY original bytes", encoding="utf-8")
    if existing == "file":
        output = sentinel
    else:
        output = tmp_path / "output"
        output.symlink_to(sentinel)
    refused = _run(package, tmp_path, SAMPLE, "--format", "json", "--output", output)
    assert refused.returncode == 2 and refused.stderr and not refused.stdout
    assert sentinel.read_text(encoding="utf-8") == "TEST_ONLY original bytes"
    if existing == "symlink":
        assert output.is_symlink()


def test_package_venv_runs_directly_without_writing_runtime(package, tmp_path):
    isolated = shutil.copytree(package, tmp_path / "installed-package")
    runtime = isolated / "runtime"
    runtime.mkdir(mode=0o700)
    python = _cli_venv(runtime / "venv", locked=True)
    before = _runtime_snapshot(runtime)
    report = _json_report(_run(isolated, tmp_path, SAMPLE, "--format", "json",
                               suppress_bytecode=False, python=python))
    assert any(component["name"] == "is-number" for component in report["components"])
    assert _runtime_snapshot(runtime) == before
    assert not list(runtime.rglob("*.pyc"))


def test_package_venv_reexec_forwards_original_arguments_without_writing_runtime(package, tmp_path):
    isolated = shutil.copytree(package, tmp_path / "installed-package")
    runtime = isolated / "runtime"
    runtime.mkdir(mode=0o700)
    startup_log = tmp_path / "interpreter-starts.jsonl"
    external = _cli_venv(tmp_path / "empty", startup_log=startup_log)
    python = _cli_venv(runtime / "venv", locked=True, startup_log=startup_log)
    arguments = [SAMPLE, "--format", "json", "--usage=commercial", "--fail-on", "partial"]
    before = _runtime_snapshot(runtime)
    report = _json_report(_run(isolated, tmp_path, *arguments, suppress_bytecode=False, python=external))
    assert any(component["name"] == "is-number" for component in report["components"])
    assert report["scan"]["usage"] == {"commercial": True, "distributed": False, "modified": False, "network_service": False}
    assert report["policy"] == {"fail_on": ["partial"], "triggered": [], "exit_code": 0}
    _assert_scan_reexec(startup_log, external, python, isolated, arguments)
    assert _runtime_snapshot(runtime) == before
    assert not list(runtime.rglob("*.pyc"))


def test_package_venv_absent_does_not_create_runtime(package, tmp_path):
    external = _cli_venv(tmp_path / "empty")
    result = _run(package, tmp_path, SAMPLE, "--format", "json", suppress_bytecode=False, python=external)
    _assert_locked_python_required(result)
    assert not (package / "runtime").exists()


def test_package_venv_missing_locks_fails_after_one_reexec(package, tmp_path):
    isolated = shutil.copytree(package, tmp_path / "installed-package")
    runtime = isolated / "runtime"
    runtime.mkdir(mode=0o700)
    startup_log = tmp_path / "interpreter-starts.jsonl"
    external = _cli_venv(tmp_path / "empty", startup_log=startup_log)
    python = _cli_venv(runtime / "venv", startup_log=startup_log)
    arguments = [SAMPLE, "--format", "json"]
    before = _runtime_snapshot(runtime)
    result = _run(isolated, tmp_path, *arguments, suppress_bytecode=False, python=external)
    _assert_locked_python_required(result)
    _assert_scan_reexec(startup_log, external, python, isolated, arguments)

    startup_log.unlink()
    direct = _run(isolated, tmp_path, *arguments, suppress_bytecode=False, python=python)
    _assert_locked_python_required(direct)
    (one_start,) = startup_log.read_text(encoding="utf-8").splitlines()
    assert json.loads(one_start)[1:5] == [str(runtime / "venv"), None, 0, None]
    assert _runtime_snapshot(runtime) == before
    assert not list(runtime.rglob("*.pyc"))


@pytest.mark.parametrize("relative", ["runtime", "runtime/venv", "runtime/venv/bin", "runtime/venv/pyvenv.cfg"])
@pytest.mark.parametrize("defect", ["symlink", "group-writable"])
def test_package_venv_reexec_refuses_unsafe_structure(package, tmp_path, relative, defect):
    isolated = shutil.copytree(package, tmp_path / "installed-package")
    (isolated / "runtime").mkdir(mode=0o700)
    external = _cli_venv(tmp_path / "empty")
    startup_log = tmp_path / "candidate-starts.jsonl"
    _cli_venv(isolated / "runtime/venv", startup_log=startup_log)
    member = isolated / relative
    if defect == "symlink":
        backing = tmp_path / "alias-target"
        member.rename(backing)
        member.symlink_to(backing, target_is_directory=backing.is_dir())
    else:
        member.chmod(member.stat().st_mode | stat.S_IWGRP)
    result = _run(isolated, tmp_path, SAMPLE, "--format", "json", suppress_bytecode=False, python=external)
    _assert_locked_python_required(result)
    assert not startup_log.exists(), "An unsafe interpreter was started"


@pytest.mark.parametrize(("mode", "same_base", "candidate_is_link", "accepted"), [
    pytest.param(0o775, True, True, True, id="same-base-group-writable"),
    pytest.param(0o777, True, True, True, id="same-base-world-writable"),
    pytest.param(0o775, False, True, False, id="different-base-group-writable"),
    pytest.param(0o777, False, True, False, id="different-base-world-writable"),
    pytest.param(0o775, True, False, False, id="regular-candidate-group-writable"),
    pytest.param(0o777, True, False, False, id="regular-candidate-world-writable"),
])
def test_package_venv_reexec_binary_permission_boundaries(
    tmp_path, monkeypatch, capsys, mode, same_base, candidate_is_link, accepted,
):
    root = tmp_path / "package"
    runtime = root / "runtime"
    venv_dir = runtime / "venv"
    bin_dir = venv_dir / "bin"
    external = tmp_path / "external"
    for directory in (root, runtime, venv_dir, bin_dir, external):
        directory.mkdir(mode=0o700)
    (venv_dir / "pyvenv.cfg").touch(mode=0o600)

    candidate = bin_dir / "python"
    current = external / "python"
    if candidate_is_link:
        current.touch(mode=0o755)
        target = current if same_base else external / "other-python"
        if not same_base:
            target.touch()
        candidate.symlink_to(target)
    else:
        target = candidate
        target.touch()
        current.hardlink_to(target)
    target.chmod(mode)
    assert stat.S_IMODE(candidate.stat().st_mode) == mode
    assert os.path.samestat(candidate.stat(), current.stat()) is same_base

    class ReexecRequested(Exception):
        pass

    calls = []

    def record_exec(executable, argv, env):
        calls.append((executable, argv, env.get("_OPENGUARD_SCAN_REEXEC"), env.get("PYTHONDONTWRITEBYTECODE")))
        raise ReexecRequested

    monkeypatch.setattr(launcher, "ROOT", root)
    monkeypatch.setattr(launcher, "RUNTIME", runtime)
    monkeypatch.setattr(launcher, "_scan_python_ready", lambda: False)
    monkeypatch.setattr(sys, "executable", str(current))
    monkeypatch.setattr(sys, "prefix", str(external))
    monkeypatch.setattr(os, "execve", record_exec)
    monkeypatch.delenv("_OPENGUARD_SCAN_REEXEC", raising=False)

    arguments = ["scan", SAMPLE, "--format=json", "--usage", "commercial"]
    before = _runtime_snapshot(runtime)
    if accepted:
        with pytest.raises(ReexecRequested):
            launcher.main(arguments)
        assert calls == [(str(candidate), [str(candidate), "-B", str(root / "openguard.py"), *arguments], "1", "1")]
        assert capsys.readouterr() == ("", "")
    else:
        code = launcher.main(arguments)
        output = capsys.readouterr()
        _assert_locked_python_required(SimpleNamespace(returncode=code, stdout=output.out, stderr=output.err))
        assert str(tmp_path) not in output.err
        assert not calls
    assert _runtime_snapshot(runtime) == before


def test_package_runtime_is_blocked_for_input_and_output(package, tmp_path):
    isolated = shutil.copytree(package, tmp_path / "isolated-package").resolve()
    runtime = isolated / "runtime"
    runtime.mkdir()
    protected = runtime / "protected.zip"
    original = (isolated / SAMPLE).read_bytes()
    protected.write_bytes(original)

    runtime_paths = [runtime]
    if sys.platform == "darwin":
        data_alias = Path("/System/Volumes/Data") / isolated.relative_to("/")
        if data_alias.is_dir() and data_alias.samefile(isolated):
            runtime_paths.append(data_alias / "runtime")

    for runtime_path in runtime_paths:
        refused_input = _run(isolated, tmp_path, runtime_path / protected.name, "--format", "json")
        assert refused_input.returncode == 2 and refused_input.stderr and not refused_input.stdout
        refused_output = _run(
            isolated, tmp_path, SAMPLE, "--format", "json", "--output", runtime_path / "forbidden.json",
        )
        assert refused_output.returncode == 2 and refused_output.stderr and not refused_output.stdout
        assert list(runtime.iterdir()) == [protected]
        assert protected.read_bytes() == original


def test_headless_guard_rejects_synthetic_connect_and_dns_events(monkeypatch):
    hooks = []
    monkeypatch.setattr(sys, "addaudithook", hooks.append)
    launcher._install_headless_scan_guard()
    (guard,) = hooks
    sock = SimpleNamespace(family=socket.AF_INET)
    for event, data in (
        ("socket.connect", (sock, ("127.0.0.1", 11434))),
        ("socket.connect", (sock, ("192.0.2.1", 443))),
        ("socket.getaddrinfo", ("example.invalid", 443, 0, 0, 0)),
    ):
        with pytest.raises(PermissionError):
            guard(event, data)


def test_check_and_offline_setup_dispatch_without_backend_imports(monkeypatch, tmp_path, capsys):
    original_import = builtins.__import__

    def forbid_backend(name, *args, **kwargs):
        assert name != "app" and not name.startswith("app."), name
        return original_import(name, *args, **kwargs)

    def fake_run(arguments, **kwargs):
        if arguments[1] == "-c":
            return SimpleNamespace(stdout="3.12\n")
        assert arguments[1:3] == ["-m", "pip"] and "--no-index" in arguments
        assert "--index-url" not in arguments
        return SimpleNamespace()

    runtime = tmp_path / "runtime"
    (runtime / "venv").mkdir(parents=True, mode=0o700)
    runtime.chmod(0o700)
    (runtime / "venv/pyvenv.cfg").touch()
    (tmp_path / "samples").mkdir()
    (tmp_path / "samples/http-server.bundle").touch()
    (tmp_path / "web").mkdir()
    (tmp_path / "web/index.html").touch()
    wheels = tmp_path / "offline-wheels"
    wheels.mkdir()
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    monkeypatch.setattr(launcher, "RUNTIME", runtime)
    monkeypatch.setattr(launcher, "_runtime_python_selection", lambda: (Path(sys.executable), False))
    monkeypatch.setattr(launcher, "dependency_report", lambda _path: {"ready": True})
    monkeypatch.setattr(launcher, "sample_report", lambda: [{"match": True}])
    monkeypatch.setattr(launcher, "git_path", lambda: Path("/usr/bin/git"))
    monkeypatch.setattr(launcher.platform, "platform", lambda: "TEST_ONLY")
    monkeypatch.setattr(launcher.subprocess, "run", fake_run)
    with monkeypatch.context() as patch:
        patch.setattr(builtins, "__import__", forbid_backend)
        assert launcher.main(["check"]) == 0
        assert launcher.main(["setup", "--offline-wheelhouse", str(wheels)]) == 0
    output = capsys.readouterr()
    assert output.out.count('"ready": true') == 4 and not output.err
