"""Reproduce B01 fixture and optional public metadata observations.

Prints a small receipt to stdout. Raw upstream responses never leave memory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys

from app.ingestion.metadata_egress import MetadataTransport
from app.ingestion.metadata_types import MetadataError, MetadataRequest
from app.scanners.metadata_parser_router import ProviderMetadataParser


_CASES = (
    ("model", "Qwen/Qwen3.5-27B"),
    ("dataset", "AI-ModelScope/train_1M_CN"),
)


def _fixture_receipt(root: Path, version: str) -> dict:
    fixture_root = root / "tests" / "fixtures" / "huggingface" / f"resource-profile-{version}"
    manifest_path = fixture_root / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest["provider"] != "huggingface":
        raise ValueError("fixture provider mismatch")
    records = manifest["records"]
    if len(records) != 10 or sum(r["resource_kind"] == "model" for r in records) != 5 or sum(
        r["resource_kind"] == "dataset" for r in records
    ) != 5:
        raise ValueError("fixture inventory mismatch")
    verified = []
    for record in records:
        relative = Path(record["fixture"])
        if relative.is_absolute() or ".." in relative.parts or relative.parts[0] != "snapshots":
            raise ValueError("invalid fixture path")
        digest = hashlib.sha256((fixture_root / relative).read_bytes()).hexdigest()
        if digest != record["source_file_sha256"]:
            raise ValueError("fixture hash mismatch")
        if "source_observation_sha256" in record and digest != record["source_observation_sha256"]:
            raise ValueError("observation hash mismatch")
        verified.append({"case_id": record["case_id"], "sha256": digest})
    return {
        "version": version,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "models": 5,
        "datasets": 5,
        "records": verified,
    }


def _live_receipts() -> list[dict]:
    transport = MetadataTransport(enabled=True)
    parser = ProviderMetadataParser()
    observations = []
    for kind, identity in _CASES:
        request = MetadataRequest("modelscope", kind, identity, "default_observation", None)
        temporary = transport.fetch(request)
        source = temporary.source
        parsed = parser.parse(
            provider=source.provider,
            resource_kind=source.resource_kind,
            resource_identity=source.repository_id,
            temporary_metadata=temporary,
            source_descriptor=source,
        )
        if parsed.verification_status != "pending" or source.resolved_revision is not None:
            raise ValueError("unexpected metadata conclusion")
        observations.append({
            "provider": source.provider,
            "resource_kind": kind,
            "repository_id": identity,
            "source_url": source.source_url,
            "fetched_at": source.fetched_at,
            "body_sha256": source.body_sha256,
            "body_size": source.body_size,
            "descriptor_version": source.descriptor_version,
            "transport_version": source.transport_version,
            "parser_version": parsed.parser_version,
            "version_status": source.version_status,
            "resolved_revision": source.resolved_revision,
            "verification_status": parsed.verification_status,
            "field_locators": sorted({field.locator for field in parsed.fields}),
            "coverage_gaps": sorted(parsed.coverage_gaps),
        })
    return observations


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description="B01 offline verification and optional public metadata probe")
    cli.add_argument("--live", action="store_true", help="fetch two fixed public ModelScope metadata endpoints")
    cli.add_argument("--root", type=Path, default=Path.cwd(), help="OpenGuard checkout root")
    args = cli.parse_args(argv)
    result = {
        "schema": "openguard.b01-reproduction-receipt/1",
        "environment": {"platform": sys.platform, "python": platform.python_version()},
        "fixtures": [_fixture_receipt(args.root, version) for version in ("v1", "v2")],
        "live_requested": args.live,
        "live_observations": [],
    }
    try:
        if args.live:
            result["live_observations"] = _live_receipts()
    except (MetadataError, ValueError) as error:
        # The provider body and exception internals are deliberately omitted.
        result["probe_error"] = error.code.value if isinstance(error, MetadataError) else "metadata_invalid"
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
