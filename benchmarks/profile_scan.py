"""Opt-in, serial production-Pipeline profiling; never a background service.

Run inside the existing locked scanner runtime. Uses its normal safety paths,
an independent registry/report directory and temporary workspace. No live scan
rows are changed. This is Pipeline timing, not HTTP/queue/browser latency.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import functools
import hashlib
import json
from pathlib import Path
import resource
import sqlite3
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("--revision", help="Required exact observed HEAD for Git; abort on drift")
    parser.add_argument("--zip-sha256")
    parser.add_argument("--ai", action="store_true")
    args = parser.parse_args()
    # Import only after argument validation; no app factory or dispatcher starts.
    from app.api.models import GitScanCreateRequest, ZipScanCreateFields
    from app.api.service import ScanApiService
    from app.persistence import SQLiteScanRunRegistry
    from app.pipeline import ScanPipelineWorker, build_local_zip_dependency_plan, build_public_git_dependency_plan
    from app.reporting import PipelineReportPublisher, ReportArtifactStore
    from app.pipeline import local_zip, dependency_plan, external_scans
    from app.ingestion import git_stream, zip_stream, git_materializer
    from app.ingestion.git_runner import GitProcessRunner
    from app.scanners import external_tools, scancode_pipeline, syft_pipeline

    live = sqlite3.connect("file:/var/lib/openguard/scans.db?mode=ro", uri=True)
    try:
        assert live.execute("select count(*) from scan_runs where status in ('running','queued')").fetchone()[0] == 0, "live scans active"
    finally:
        live.close()
    git = args.source.startswith("https://")
    assert (git and args.revision and len(args.revision) == 40) or (not git and args.zip_sha256)
    if not git:
        assert hashlib.sha256(Path(args.source).read_bytes()).hexdigest() == args.zip_sha256
    events, inventories = [], []
    origin = time.monotonic()

    def wrap(function, label):
        @functools.wraps(function)
        def measured(*a, **kw):
            event = {"name": label, "start": time.monotonic() - origin}
            if label == "tool":
                event.update(tool=Path(a[0]).name, arguments=list(a[1]))
                print("START_TOOL", json.dumps(event), flush=True)
            started = time.monotonic()
            try:
                result = function(*a, **kw)
                if label == "tool":
                    event.update(status=result.status, error=result.error_code, bytes=len(result.stdout or b""))
                    if result.stdout:
                        event["output_sha256"] = hashlib.sha256(result.stdout).hexdigest()
                        try:
                            payload = json.loads(result.stdout)
                            event["file_count"] = len(payload.get("files", []))
                            event["artifact_count"] = len(payload.get("artifacts", []))
                            event["headers"] = payload.get("headers")
                        except (ValueError, AttributeError):
                            pass
                if label == "inventory":
                    inventories.append(asdict(result.inventory))
                if label == "inspect_git":
                    event["revision"] = result[0]
                    if result[0] != args.revision:
                        raise ValueError("benchmark target revision drifted")
                if label == "merge":
                    event.update(existing=len(a[0]), incoming=len(a[1]), output=len(result))
                return result
            except BaseException as error:
                event["exception"] = type(error).__name__
                raise
            finally:
                event["seconds"] = time.monotonic() - started
                events.append(event)
                if label == "tool":
                    print("END_TOOL", json.dumps(event), flush=True)
        return measured

    # Replace already-imported aliases, preserving every argument/result/error.
    targets = [
        (external_tools.run_json_tool, "tool"),
        (external_tools.parse_json_output, "json_parse"),
        (external_tools.map_scancode_output, "scancode_map"),
        (external_tools.map_syft_output, "syft_map"),
        (external_scans.merge_external_components, "merge"),
        (local_zip.parse_python_manifests, "python_parse"),
        (local_zip.parse_javascript_manifests, "javascript_parse"),
        (local_zip.collect_ai_assets, "asset_detection"),
        (local_zip.collect_manifest_licenses, "manifest_licenses"),
        (git_stream.build_inventory_snapshot, "inventory"),
        (git_stream.validate_inventory_snapshot, "integrity_check"),
        (zip_stream._materialize_archive, "zip_materialize"),
        (git_stream.materialize_bounded_git_tree, "git_materialize"),
        (git_materializer.inspect_bounded_git_tree, "inspect_git"),
        (dependency_plan.apply_license_rules, "rules"),
        (dependency_plan.apply_external_licenses, "license_normalize"),
    ]
    for original, label in targets:
        replacement = wrap(original, label)
        for module in tuple(sys.modules.values()):
            if getattr(module, "__name__", "").startswith("app."):
                for name, value in tuple(vars(module).items()):
                    if value is original:
                        setattr(module, name, replacement)
    GitProcessRunner.clone_no_checkout = wrap(GitProcessRunner.clone_no_checkout, "git_fetch")
    clock = lambda: datetime.now(timezone.utc)
    provider = None
    if args.ai:
        from app.ai import OllamaProvider
        provider = OllamaProvider("http://host.docker.internal:11434", docker_host=True)
    with tempfile.TemporaryDirectory(prefix="openguard-v3-data-") as directory, tempfile.TemporaryDirectory(
        prefix="v3-", dir="/var/lib/openguard/workspaces"
    ) as workspace:
        root = Path(directory)
        reports = root / "reports"
        reports.mkdir(mode=0o700)
        registry = SQLiteScanRunRegistry(root / "scans.db")
        store = ReportArtifactStore(reports)
        service = ScanApiService(registry, report_store=store)
        options = dict(clock=clock, external_scanners=True, ai_enabled=args.ai,
                       ai_provider=provider, ai_timeout_seconds=30.0)
        started = time.monotonic()
        if git:
            accepted, _ = service.create_git_scan_record(GitScanCreateRequest(source_type="git", source=args.source))
            source = registry.get(accepted.scan_id).run.project.source
            plan = build_public_git_dependency_plan(source, Path(workspace), **options)
        else:
            archive = Path(args.source)
            accepted, _ = service.create_zip_scan(ZipScanCreateFields(source_type="zip"),
                staged_name=archive.name, project_name=archive.stem, input_digest=args.zip_sha256)
            plan = build_local_zip_dependency_plan(archive, Path(workspace), **options)
        plan = replace(plan, steps=tuple(replace(step, handler=wrap(step.handler, "stage:" + step.stage.value)) for step in plan.steps))
        publisher = PipelineReportPublisher(store)
        result = ScanPipelineWorker(registry, clock=clock,
            terminal_publisher=wrap(publisher.publish, "report_publish")).run(accepted.scan_id, plan)
        total = time.monotonic() - started
        run = result.run.model_dump(mode="json")
        artifacts = [{"path": str(p.relative_to(reports)), "bytes": p.stat().st_size,
                      "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                     for p in reports.rglob("*") if p.is_file()]
        receipt = dict(source=args.source, expected_revision=args.revision, zip_sha256=args.zip_sha256,
            ai=args.ai, scope="isolated production Pipeline, no HTTP queue/browser", total_seconds=total,
            cache="fresh Python process; no AI answer cache; OS/model warm state uncontrolled",
            events=events, inventories=inventories, scan_run=run, reports=artifacts,
            workspace_clean=not list(Path(workspace).iterdir()),
            cpu_self=resource.getrusage(resource.RUSAGE_SELF).ru_utime,
            cpu_children=resource.getrusage(resource.RUSAGE_CHILDREN).ru_utime,
            children_maxrss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
        print("RECEIPT", json.dumps(receipt, ensure_ascii=False), flush=True)
        registry.close()


if __name__ == "__main__":
    main()
