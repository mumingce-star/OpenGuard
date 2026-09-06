"""Exercise both fixed tools against generated, non-executed local inputs."""

import hashlib
import json
import subprocess
import resource
import sys
import tempfile
from pathlib import Path


def run(arguments):
    return subprocess.run(
        arguments, check=True, capture_output=True, timeout=180,
    ).stdout


def check_nofile():
    """Exercise inherited kernel limits in a disposable child, not the API."""
    assert resource.getrlimit(resource.RLIMIT_NOFILE) == (256, 256)
    probe = r"""
import errno, json, os, resource
assert resource.getrlimit(resource.RLIMIT_NOFILE) == (256, 256)
try:
    resource.setrlimit(resource.RLIMIT_NOFILE, (257, 257))
except (ValueError, OSError):
    pass
else:
    raise AssertionError('hard limit could be raised')
# /proc also exposes translation-runtime descriptors on Apple silicon.
# Exclude the already-closed descriptor used by listdir itself.
initial = sum(os.path.exists('/proc/self/fd/' + n) for n in os.listdir('/proc/self/fd'))
fds = []
try:
    for _ in range(257):
        fds.append(os.open('/dev/null', os.O_RDONLY))
except OSError as exc:
    assert exc.errno == errno.EMFILE, exc
    assert initial + len(fds) == 256, (initial, len(fds))
else:
    raise AssertionError('kernel did not enforce the descriptor limit')
finally:
    for fd in fds:
        os.close(fd)
fd = os.open('/dev/null', os.O_RDONLY)
os.close(fd)
print(json.dumps({'soft': 256, 'hard': 256, 'initial': initial, 'opened': len(fds),
                  'error': 'EMFILE', 'reopen_after_close': True}))
"""
    return json.loads(run([sys.executable, '-c', probe]))


def check_workspace_quota():
    """Destructive capacity probe ONLY for a disposable /quota tmpfs container.

    Never run against the live data volume. This function requires a separate
    /quota mount and refuses other paths or non-empty mounts.
    """
    import errno
    import io
    import os
    import zipfile
    from app.ingestion.zip_stream import ZipIngestionService
    from app.security.errors import IngestionSecurityError

    root = Path('/quota')
    assert root.is_mount() and not list(root.iterdir())
    mounts = Path('/proc/mounts').read_text().splitlines()
    assert any(row.split()[1:3] == ['/quota', 'tmpfs'] for row in mounts)
    capacity = os.statvfs(root).f_blocks * os.statvfs(root).f_frsize
    assert capacity == 1024 * 1024 * 1024, capacity
    workspace = root / 'workspaces'
    workspace.mkdir(mode=0o700)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_STORED) as zipped:
        zipped.writestr('payload.txt', b'x' * (2 * 1024 * 1024))
    service = ZipIngestionService(workspace)
    results = []
    try:
        # 1 MiB: receive fails. 3 MiB: receive fits, extraction fails.
        for remaining_mib in (1, 3):
            ballast = root / 'ballast'
            try:
                with ballast.open('wb') as handle:
                    os.posix_fallocate(handle.fileno(), 0, capacity - remaining_mib * 1024 * 1024)
                try:
                    service.ingest_with_consumer(io.BytesIO(archive.getvalue()), lambda session: None)
                except IngestionSecurityError as error:
                    assert (error.code, error.reason) == ('scanner_failed', 'workspace_write_failed'), error
                    cause = error
                    while cause.__cause__ is not None:
                        cause = cause.__cause__
                    assert isinstance(cause, OSError) and cause.errno == errno.ENOSPC, repr(cause)
                else:
                    raise AssertionError('over-capacity ZIP unexpectedly succeeded')
                assert not list(workspace.iterdir()), 'failed task left workspace bytes'
                results.append({'remaining_mib': remaining_mib, 'errno': 'ENOSPC', 'cleaned': True})
            finally:
                ballast.unlink(missing_ok=True)
        service.ingest_with_consumer(io.BytesIO(archive.getvalue()), lambda session: None)
        assert not list(workspace.iterdir()), 'successful task left workspace bytes'
    finally:
        service.close()
        workspace.rmdir()
    return {'capacity_bytes': capacity, 'failures': results, 'next_ingestion': 'passed'}


def main():
    nofile = check_nofile()
    scancode_version = run(["scancode", "--version"]).decode().strip()
    syft_version = run(["syft", "version", "-o", "json"])
    assert "32.5.0" in scancode_version, scancode_version
    assert json.loads(syft_version)["version"] == "1.51.0"
    with tempfile.TemporaryDirectory(prefix="openguard-tools-") as temporary:
        root = Path(temporary)
        (root / "LICENSE").write_text("""MIT License

Copyright (c) 2026 OpenGuard sample contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
""", encoding="utf-8")
        (root / "package.json").write_text(json.dumps({
            "name": "openguard-tool-smoke", "version": "1.0.0",
            "dependencies": {"is-number": "7.0.0"},
        }), encoding="utf-8")
        (root / "package-lock.json").write_text(json.dumps({
            "name": "openguard-tool-smoke", "version": "1.0.0", "lockfileVersion": 3,
            "packages": {
                "": {"name": "openguard-tool-smoke", "version": "1.0.0",
                     "dependencies": {"is-number": "7.0.0"}},
                "node_modules/is-number": {"version": "7.0.0", "license": "MIT"},
            },
        }), encoding="utf-8")
        license_output = run([
            "scancode", "--license", "--strip-root", "--processes", "1", "--json", "-", str(root),
        ])
        license_json = json.loads(license_output)
        license_file = next(item for item in license_json["files"] if item["path"] == "LICENSE")
        assert license_file["detected_license_expression"] == "mit"
        assert not license_file.get("scan_errors")
        sbom_output = run(["syft", "scan", f"dir:{root}", "-o", "syft-json"])
        package = next(item for item in json.loads(sbom_output)["artifacts"]
                       if item.get("purl") == "pkg:npm/is-number@7.0.0")
        assert any(item["path"].endswith("package-lock.json") for item in package["locations"])
        print(json.dumps({
            "nofile": nofile,
            "status": "passed", "scancode": "32.5.0", "syft": "1.51.0",
            "license": "mit", "license_path": "LICENSE", "component": package["purl"],
            "scancode_json_sha256": hashlib.sha256(license_output).hexdigest(),
            "syft_json_sha256": hashlib.sha256(sbom_output).hexdigest(),
            "scope": "tool runtime only; not an API pipeline integration",
        }, indent=2))


if __name__ == "__main__":
    main()
