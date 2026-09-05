"""Real HTTP acceptance, using only Python's standard library.

Run against Compose, then rerun --verify after restarting/recreating API.
Keep --output outside the repository: it contains a test ZIP and scan IDs.
"""
import argparse
import hashlib
import io
import json
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--external-scanners", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get(path):
        with opener.open(args.url + path, timeout=15) as response:
            return response.read()

    def create(files):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, value in files.items():
                archive.writestr(name, value)
        zipped = buffer.getvalue()
        boundary = "openguard-" + uuid.uuid4().hex
        body = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="source_type"\r\n\r\nzip\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="idempotency_key"\r\n\r\n{uuid.uuid4()}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="demo.zip"\r\n'
            'Content-Type: application/zip\r\n\r\n'
        ).encode() + zipped + f"\r\n--{boundary}--\r\n".encode()
        request = urllib.request.Request(args.url + "/api/v1/scans", data=body,
                                        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with opener.open(request, timeout=15) as response:
            assert response.status == 202
            scan_id = json.load(response)["scan_id"]
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            status = json.loads(get(f"/api/v1/scans/{scan_id}"))
            if status["status"] not in {"queued", "running"}:
                return scan_id, status, zipped
            time.sleep(0.25)
        raise AssertionError("scan did not finish within 60 seconds")

    if args.verify:
        receipt = json.loads((args.output / "receipt.json").read_text())
        scan_id = receipt["scan_id"]
        assert json.loads(get(f"/api/v1/scans/{scan_id}"))["status"] == "completed"
        for format_name, digest in receipt["reports"].items():
            data = get(f"/api/v1/scans/{scan_id}/report?format={format_name}&download=true")
            assert hashlib.sha256(data).hexdigest() == digest, format_name
        print("PASS: persisted scan and four report byte hashes after restart/recreation")
        return

    assert b'<div id="root">' in get("/app/new-scan")
    files = {
        "package.json": json.dumps({"name": "compose-demo", "version": "1.0.0",
                                    "dependencies": {"is-number": "7.0.0", "unlicensed-demo": "1.0.0"}}),
        "package-lock.json": json.dumps({"name": "compose-demo", "version": "1.0.0", "lockfileVersion": 3,
            "packages": {"": {"name": "compose-demo", "version": "1.0.0", "dependencies": {
                "is-number": "7.0.0", "unlicensed-demo": "1.0.0"}},
                "node_modules/is-number": {"version": "7.0.0", "license": "MIT"},
                "node_modules/unlicensed-demo": {"version": "1.0.0"}}}),
    }
    if args.external_scanners:
        files["LICENSE"] = (Path(__file__).resolve().parents[1] / "LICENSE").read_text()
    scan_id, status, zipped = create(files)
    assert status["status"] == "completed", status
    (args.output / "compose-demo.zip").write_bytes(zipped)
    resources = json.loads(get(f"/api/v1/scans/{scan_id}/resources"))
    assert resources["total"] == (3 if args.external_scanners else 2)
    risks = json.loads(get(f"/api/v1/scans/{scan_id}/risks"))
    assert len(risks["items"]) == resources["total"]
    report = json.loads(get(f"/api/v1/scans/{scan_id}/report?format=json&download=true"))
    scan = report["scan_run"]
    assert {item["expression"] for item in scan["licenses"]} == ({"MIT", "NOASSERTION", "Apache-2.0"} if args.external_scanners else {"MIT", "NOASSERTION"})
    assert all(item["verification_status"] == "pending" for item in scan["licenses"])
    if args.external_scanners:
        versions = {item["name"]: item["version"] for item in scan["provenance"]["tool_versions"]}
        assert versions["scancode"] == "32.5.0" and versions["syft"] == "1.51.0"
        sources = {name: hashlib.sha256(data.encode()).hexdigest() for name, data in files.items()}
        tool_evidence = [item for item in scan["evidence"] if item["producer"]["name"] in {"scancode", "syft"}]
        assert {item["producer"]["name"] for item in tool_evidence} == {"scancode", "syft"}
        assert any(item["locator"] == "LICENSE" and item["producer"]["name"] == "scancode" for item in tool_evidence)
        for item in tool_evidence:
            assert item["content_hash"]["value"] == sources[item["locator"]]
        licenses = {item["id"]: item["expression"] for item in scan["licenses"]}
        components = {item["name"]: item for item in scan["components"]}
        assert licenses[components["is-number"]["license_expression_id"]] == "MIT"
        assert licenses[components["unlicensed-demo"]["license_expression_id"]] == "NOASSERTION"
        assert {"syft", "manifest_parser"} <= set(components["is-number"]["detected_by"])
    for evidence in scan["evidence"]:
        assert json.loads(get(f'/api/v1/scans/{scan_id}/evidence/{evidence["id"]}'))
    hashes = {}
    for format_name in ("html", "json", "csv", "resource_inventory"):
        link = json.loads(get(f'/api/v1/scans/{scan_id}/report?format={format_name}'))
        data = get(f'/api/v1/scans/{scan_id}/report?format={format_name}&download=true')
        digest = hashlib.sha256(data).hexdigest()
        assert digest == link["content_hash"]["value"]
        hashes[format_name] = digest
    assert set(hashes) == {"html", "json", "csv", "resource_inventory"}
    _, partial, _ = create({"package.json": files["package.json"]})
    assert partial["status"] == ("completed" if args.external_scanners else "partial"), partial
    _, failed, _ = create({"../escape.txt": "unsafe path"})
    assert failed["status"] == "failed", failed
    try:
        get("/api/v1/scans/scn_00000000-0000-4000-8000-000000000000")
    except urllib.error.HTTPError as error:
        assert error.code == 404
    else:
        raise AssertionError("unknown scan did not return 404")
    receipt = {"scan_id": scan_id, "reports": hashes}
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2))
    print(json.dumps({"status": "passed", "scan_id": scan_id,
                      "external_scanners": args.external_scanners,
                      "checks": ["SPA deep link", "ZIP completed", "resource count", "pending licenses",
                                 "risks and evidence", "four report hashes", "missing declarations", "unsafe ZIP failed", "404"]}, indent=2))


if __name__ == "__main__":
    main()
