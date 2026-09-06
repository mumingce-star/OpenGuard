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
from datetime import datetime
from pathlib import Path


def check_public_sample(args, get, create):
    """Verify the unmodified pinned public sample; this is not a benchmark score."""
    zipped = args.public_zip.read_bytes()
    digest = hashlib.sha256(zipped).hexdigest()
    assert digest == "c486d41688b937e208393b95e70fc7293c555b046f4284a8fca7a925fe6ef4a9", "unexpected sample ZIP"
    started = time.monotonic()
    if args.scan_id:
        scan_id = args.scan_id
        deadline = time.monotonic() + 1800
        while True:
            status = json.loads(get(f"/api/v1/scans/{scan_id}"))
            if status["status"] not in {"queued", "running"}:
                break
            assert time.monotonic() < deadline, "scan did not finish within 1800 seconds"
            time.sleep(1)
    else:
        scan_id, status, _ = create(zipped=zipped, wait_seconds=1800)
    (args.output / "status.json").write_text(json.dumps(status, indent=2))
    raw = get(f"/api/v1/scans/{scan_id}/report?format=json&download=true")
    (args.output / "report.json").write_bytes(raw)
    scan = json.loads(raw)["scan_run"]
    assert status["status"] == "completed" and not scan["errors"], status
    assert scan["provenance"]["input_digest"]["value"] == digest
    versions = {p["name"]: p["version"] for p in scan["provenance"]["tool_versions"]}
    assert versions["scancode"] == "32.5.0" and versions["syft"] == "1.51.0"
    with zipfile.ZipFile(io.BytesIO(zipped)) as archive:
        sources = {n: archive.read(n) for n in archive.namelist() if not n.endswith("/")}
    evidence = {e["id"]: e for e in scan["evidence"]}
    for item in evidence.values():
        # Manifest evidence locates a field as path:project.dependencies[index].
        source_path = item["locator"].split(":", 1)[0]
        assert source_path in sources, item["locator"]
        assert item["content_hash"]["value"] == hashlib.sha256(sources[source_path]).hexdigest()
    assert any(e["producer"]["name"] == "scancode" and e["locator"].endswith("/LICENSE") for e in evidence.values())
    expected = {
        ("model", "Qwen/Qwen2.5-Coder-32B-Instruct"): ("docs/source/en/examples/multiagents.md", 57),
        ("model", "black-forest-labs/FLUX.1-dev"): ("docs/source/en/tutorials/tools.md", 119),
        ("dataset", "m-ric/agents_medium_benchmark_2"): ("README.md", 76),
        ("dataset", "huggingface/documentation-images"): ("docs/README.md", 233),
    }
    licenses = {x["id"]: x for x in scan["licenses"]}
    assert {(a["asset_type"], a["name"]) for a in scan["ai_assets"]} == set(expected)
    for asset in scan["ai_assets"]:
        path, line = expected[asset["asset_type"], asset["name"]]
        assert any(evidence[k]["locator"].split("/", 1)[1] == path and evidence[k]["start_line"] == line for k in asset["evidence_ids"])
        assert asset["authorization_status"] == "pending"
        assert licenses[asset["license_expression_id"]]["expression"] == "NOASSERTION"
    assert {"torch", "transformers", "requests", "pytest"} <= {c["name"] for c in scan["components"]}
    # A root project license cannot be inherited by its declared dependencies.
    for component in scan["components"]:
        if component["name"] in {"torch", "transformers", "requests", "pytest"}:
            assert licenses[component["license_expression_id"]]["expression"] == "NOASSERTION"
    findings = {f["id"]: f for f in scan["findings"]}
    resources = {r["id"]: r for r in [*scan["components"], *scan["ai_assets"]]}
    ai = [r for r in scan["remediations"] if r["generated_by"]["type"] == "ai"]
    assert bool(ai) is args.expect_ai
    assert scan["provenance"]["ai_enabled"] is args.expect_ai
    for remediation in ai:
        producer = remediation["generated_by"]
        assert producer["model_id"] == "qwen3:4b-instruct-2507-q4_K_M@sha256:0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0"
        assert producer["version"] == "0.33.3"
        assert remediation["verification_status"] == "pending"
        finding = findings[remediation["finding_id"]]
        assert finding["remediation_id"] == remediation["id"]
        allowed = set(finding["evidence_ids"])
        expression_id = resources[finding["resource_id"]].get("license_expression_id")
        if expression_id:
            allowed.update(licenses[expression_id]["evidence_ids"])
        assert remediation["evidence_ids"] and set(remediation["evidence_ids"]) <= allowed
    if args.compare_to:
        baseline = json.loads(args.compare_to.read_text())["scan_run"]
        assert baseline["provenance"]["input_digest"] == scan["provenance"]["input_digest"]
        assert baseline["provenance"]["inventory_digest"] == scan["provenance"]["inventory_digest"]
        for field in ("components", "ai_assets", "licenses", "evidence", "obligations", "findings"):
            def facts(run):
                omitted = {"observed_at"} if field == "evidence" else {"remediation_id"} if field == "findings" else set()
                return sorted(({k: v for k, v in item.items() if k not in omitted} for item in run[field]), key=lambda item: item["id"])
            assert facts(baseline) == facts(scan), f"AI changed deterministic {field}"
    hashes = {}
    for format_name in ("html", "json", "csv", "resource_inventory"):
        link = json.loads(get(f"/api/v1/scans/{scan_id}/report?format={format_name}"))
        data = get(f"/api/v1/scans/{scan_id}/report?format={format_name}&download=true")
        hashes[format_name] = hashlib.sha256(data).hexdigest()
        assert hashes[format_name] == link["content_hash"]["value"]
        assert b"Qwen/Qwen2.5-Coder-32B-Instruct" in data
        (args.output / ("report." + format_name)).write_bytes(data)
    receipt = {"scan_id": scan_id, "input_sha256": digest, "reports": hashes,
               "components": len(scan["components"]), "assets": len(scan["ai_assets"]),
               "findings": len(findings), "ai_remediations": len(ai),
               "scan_elapsed_seconds": round((datetime.fromisoformat(scan["finished_at"].replace("Z", "+00:00")) - datetime.fromisoformat(scan["started_at"].replace("Z", "+00:00"))).total_seconds(), 2),
               "validation_elapsed_seconds": round(time.monotonic() - started, 2)}
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--external-scanners", action="store_true")
    parser.add_argument("--ai-assets", action="store_true")
    parser.add_argument("--public-zip", type=Path, help="Fixed smolagents a3df1a21 ZIP acceptance")
    parser.add_argument("--expect-ai", action="store_true")
    parser.add_argument("--scan-id", help="Validate an existing Chrome-created public sample scan")
    parser.add_argument("--compare-to", type=Path, help="AI-disabled report.json for deterministic fact comparison")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get(path):
        with opener.open(args.url + path, timeout=15) as response:
            return response.read()

    def create(files=None, *, zipped=None, wait_seconds=60):
        if zipped is None:
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
        deadline = time.monotonic() + wait_seconds
        print("Accepted:", scan_id, flush=True)
        (args.output / "accepted.json").write_text(json.dumps({"scan_id": scan_id}))
        while time.monotonic() < deadline:
            status = json.loads(get(f"/api/v1/scans/{scan_id}"))
            if status["status"] not in {"queued", "running"}:
                return scan_id, status, zipped
            time.sleep(0.25)
        raise AssertionError(f"scan did not finish within {wait_seconds} seconds")

    if args.verify:
        receipt = json.loads((args.output / "receipt.json").read_text())
        scan_id = receipt["scan_id"]
        assert json.loads(get(f"/api/v1/scans/{scan_id}"))["status"] == "completed"
        for format_name, digest in receipt["reports"].items():
            data = get(f"/api/v1/scans/{scan_id}/report?format={format_name}&download=true")
            assert hashlib.sha256(data).hexdigest() == digest, format_name
        print("PASS: persisted scan and four report byte hashes after restart/recreation")
        return

    if args.public_zip:
        check_public_sample(args, get, create)
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
    if args.ai_assets:
        files["README.md"] = ("# Model reference sample\n\n"
            "Model: https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507\n"
            "Local runtime tag: qwen3:4b-instruct-2507-q4_K_M\n"
            "This sample records a reference only; it does not contain weights or execute inference.\n")
    scan_id, status, zipped = create(files)
    assert status["status"] == "completed", status
    (args.output / "compose-demo.zip").write_bytes(zipped)
    resources = json.loads(get(f"/api/v1/scans/{scan_id}/resources"))
    assert resources["total"] == (3 if args.external_scanners else 2) + int(args.ai_assets)
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
    if args.ai_assets:
        assert scan["summary"]["ai_asset_count"] == 1
        asset = scan["ai_assets"][0]
        assert asset["asset_type"] == "model" and asset["name"] == "Qwen/Qwen3-4B-Instruct-2507"
        assert asset["authorization_status"] == "pending"
        assert asset["source_url"] == "https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507"
        license_map = {item["id"]: item for item in scan["licenses"]}
        assert license_map[asset["license_expression_id"]]["expression"] == "NOASSERTION"
        evidence_map = {item["id"]: item for item in scan["evidence"]}
        for key in asset["evidence_ids"]:
            item = evidence_map[key]
            assert item["locator"] == "README.md" and item["start_line"] == 3
            assert item["content_hash"]["value"] == hashlib.sha256(files["README.md"].encode()).hexdigest()
        assert scan["provenance"]["ai_enabled"] is False
        assert asset["id"] in json.dumps(risks)
    for evidence in scan["evidence"]:
        assert json.loads(get(f'/api/v1/scans/{scan_id}/evidence/{evidence["id"]}'))
    hashes = {}
    for format_name in ("html", "json", "csv", "resource_inventory"):
        link = json.loads(get(f'/api/v1/scans/{scan_id}/report?format={format_name}'))
        data = get(f'/api/v1/scans/{scan_id}/report?format={format_name}&download=true')
        digest = hashlib.sha256(data).hexdigest()
        assert digest == link["content_hash"]["value"]
        if args.ai_assets:
            assert b"Qwen/Qwen3-4B-Instruct-2507" in data
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
                      "external_scanners": args.external_scanners, "ai_assets": args.ai_assets,
                      "checks": ["SPA deep link", "ZIP completed", "resource count", "pending licenses",
                                 "risks and evidence", "four report hashes", "missing declarations", "unsafe ZIP failed", "404"]}, indent=2))


if __name__ == "__main__":
    main()
