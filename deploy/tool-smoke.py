"""Exercise both fixed tools against generated, non-executed local inputs."""

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path


def run(arguments):
    return subprocess.run(
        arguments, check=True, capture_output=True, timeout=180,
    ).stdout


def main():
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
            "status": "passed", "scancode": "32.5.0", "syft": "1.51.0",
            "license": "mit", "license_path": "LICENSE", "component": package["purl"],
            "scancode_json_sha256": hashlib.sha256(license_output).hexdigest(),
            "syft_json_sha256": hashlib.sha256(sbom_output).hexdigest(),
            "scope": "tool runtime only; not an API pipeline integration",
        }, indent=2))


if __name__ == "__main__":
    main()
