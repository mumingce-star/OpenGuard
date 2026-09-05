"""Bounded A2 text reads feeding the teammate's static AI reference detector."""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath

from app.detectors import detect_ai_assets
from app.domain.models import AIAsset, Evidence, ScanError, ScanRun
from app.ingestion import ReadOnlyScanSession
from app.licenses import normalize_license

_MAX_FILE = 512 * 1024
_MAX_TOTAL = 2 * 1024 * 1024
_MAX_FILES = 128
_SUFFIXES = {".md", ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yaml", ".yml", ".toml"}
_DEPENDENCY_FILES = {"package.json", "package-lock.json", "pyproject.toml"}


@dataclass(frozen=True)
class AIAssetScan:
    assets: tuple[AIAsset, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    errors: tuple[ScanError, ...] = ()


def collect_ai_assets(session: ReadOnlyScanSession, observed_at: datetime, *, total_read_budget: int) -> AIAssetScan:
    entries = {item.relative_path: item for item in session.inventory.entries}
    selected = [item for path, item in sorted(entries.items())
                if PurePosixPath(path).suffix.lower() in _SUFFIXES
                and PurePosixPath(path).name not in _DEPENDENCY_FILES]
    # B1 reads selected manifests once; license enrichment can reread locks.
    # Twice all inventory bytes conservatively reserves both existing passes.
    available = min(_MAX_TOTAL, max(0, total_read_budget - 2 * sum(item.size_bytes for item in entries.values())))
    files = {}
    incomplete = False
    for index, item in enumerate(selected):
        if index >= _MAX_FILES or item.size_bytes > min(_MAX_FILE, available):
            incomplete = True
            continue
        available -= item.size_bytes
        data = session.read_bytes(item.relative_path, max_bytes=_MAX_FILE)
        if len(data) != item.size_bytes or hashlib.sha256(data).hexdigest() != item.sha256:
            raise ValueError("AI reference source did not match inventory")
        try:
            files[item.relative_path] = data.decode("utf-8")
        except UnicodeDecodeError:
            incomplete = True
    try:
        assets, evidence = detect_ai_assets(files, observed_at=observed_at)
        for item in evidence:
            if item.locator not in files or item.content_hash is None or item.content_hash.value != entries[item.locator].sha256:
                raise ValueError("AI reference evidence did not match inventory")
    except Exception:
        assets, evidence = [], []
        incomplete = True
    errors = (ScanError(code="ai_asset_scan_incomplete", stage="scan",
                       message="AI reference scanning was incomplete.", recoverable=True),) if incomplete else ()
    return AIAssetScan(tuple(assets), tuple(evidence), errors)


def apply_ai_asset_licenses(run: ScanRun) -> ScanRun:
    """A reference proves neither permission nor ownership of a nearby LICENSE."""
    if not run.ai_assets:
        return run
    evidence = {item.id: item for item in run.evidence}
    licenses = {item.id: item for item in run.licenses}
    def bind(resource):
        if resource.license_expression_id is not None:
            return resource
        expression = normalize_license("NOASSERTION", [evidence[key] for key in resource.evidence_ids])
        licenses[expression.id] = expression
        return resource.model_copy(update={"license_expression_id": expression.id})
    components = [bind(item) for item in run.components]
    assets = [bind(item) for item in run.ai_assets]
    payload = run.model_dump(mode="python")
    payload.update(components=components, ai_assets=assets, licenses=sorted(licenses.values(), key=lambda item: item.id))
    return ScanRun.model_validate(payload)
