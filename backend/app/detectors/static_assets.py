"""Evidence-first static recognition of model, dataset and API references."""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone

from app.domain.models import (
    AIAsset, AIAssetType, DetectionMethod, Evidence, EvidenceKind, ProducerRef,
    ProducerType, VerificationStatus,
)

_NAMESPACE = uuid.UUID("e6047e12-66d2-5ebb-b78a-756e0ee05601")
_PRODUCER = ProducerRef(type=ProducerType.PARSER, name="openguard-static-ai-detector", version="0.1.2")
_PATTERNS = (
    (AIAssetType.MODEL, "huggingface", re.compile(r"https://huggingface\.co/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)")),
    (AIAssetType.MODEL, "modelscope", re.compile(r"https://modelscope\.cn/models/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)")),
    (AIAssetType.DATASET, "huggingface", re.compile(r"https://huggingface\.co/datasets/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)")),
    (AIAssetType.API, "openai", re.compile(r"\b(?:openai|OpenAI)\.(?:ChatCompletion|responses|chat\.completions)\b")),
    (AIAssetType.API, "anthropic", re.compile(r"\b(?:anthropic|Anthropic)\.(?:messages|Anthropic)\b")),
    (AIAssetType.API, "google", re.compile(r"\b(?:google\.generativeai|google\.genai|google\.generative_ai)\b")),
)
_URL = re.compile(r"(?<![\w:/@.%-])https?://[^\s<>\"'`()\[\]{}]+")
_HF_ROUTES = frozenset({
    "datasets", "spaces", "docs", "settings", "models", "api", "blog",
    "organizations", "collections", "join", "login", "logout", "pricing",
    "terms-of-service", "privacy", "tasks", "papers", "learn", "inference",
})


def _identifier(prefix: str, *parts: str) -> str:
    return f"{prefix}_{uuid.uuid5(_NAMESPACE, '|'.join(parts))}"


def _canonical_resource_url(url: str) -> str | None:
    """Accept only HF roots or explicit revision/file paths; never fetch a URL."""
    prefix = "https://huggingface.co/"
    if not url.startswith(prefix):
        return url
    parts = url[len(prefix):].split("/")
    root_size = 3 if parts[0] == "datasets" else 2
    if any(part in {"", ".", ".."} or re.fullmatch(r"[A-Za-z0-9_.-]+", part) is None for part in parts):
        return None
    suffix = parts[root_size:]
    if suffix and (len(suffix) < 3 or suffix[0] not in {"resolve", "blob"}):
        return None
    return prefix + "/".join(parts[:root_size])


def _references(line: str):
    # Preserve the complete observed URL as evidence. Only supported HF file
    # paths may canonicalize to a resource root; unknown routes stay excluded.
    for token in _URL.finditer(line):
        canonical = _canonical_resource_url(token.group())
        if canonical is None:
            continue
        for asset_type, provider, pattern in _PATTERNS[:3]:
            match = pattern.fullmatch(canonical)
            if match is None:
                continue
            name = match.group(1)
            parts = name.split("/")
            if len(name) > 200 or any(part in {".", ".."} for part in parts):
                continue
            if provider == "huggingface" and asset_type == AIAssetType.MODEL and parts[0].lower() in _HF_ROUTES:
                continue
            yield asset_type, provider, name, canonical, token.group()
    for asset_type, provider, pattern in _PATTERNS[3:]:
        for match in pattern.finditer(line):
            yield asset_type, provider, provider, None, match.group()


def detect_ai_assets(files: Mapping[str, str], *, observed_at: datetime | None = None) -> tuple[list[AIAsset], list[Evidence]]:
    """Find declared AI references in already-read, relative-path text files.

    This function never opens files, executes code, calls a remote API, or
    treats an observed reference as authorization or a license conclusion.
    """
    timestamp = observed_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() != timezone.utc.utcoffset(timestamp):
        raise ValueError("observed_at must use UTC with an explicit timezone")
    assets: dict[tuple[str, str, str], AIAsset] = {}
    evidence: dict[str, Evidence] = {}
    for locator, text in sorted(files.items()):
        if (not locator or len(locator) > 2048 or "\\" in locator or ":" in locator
                or any(ord(char) < 32 for char in locator)
                or any(part in {"", ".", ".."} for part in locator.split("/"))):
            raise ValueError("files must use relative locators")
        digest = hashlib.sha256(text.encode("utf-8", errors="strict")).hexdigest()
        for line_number, line in enumerate(text.splitlines(), start=1):
            for asset_type, provider, name, source_url, excerpt in _references(line):
                key = (asset_type.value, provider, name)
                evidence_id = _identifier("evd", locator, digest, str(line_number), *key, excerpt)
                evidence[evidence_id] = Evidence(
                    id=evidence_id, kind=EvidenceKind.FILE, locator=locator, excerpt=excerpt,
                    start_line=line_number, end_line=line_number,
                    content_hash={"algorithm": "sha256", "value": digest},
                    detected_by=DetectionMethod.STATIC_PATTERN, producer=_PRODUCER,
                    observed_at=timestamp, verification_status=VerificationStatus.PENDING,
                )
                existing = assets.get(key)
                ids = sorted(set((existing.evidence_ids if existing else []) + [evidence_id]))
                assets[key] = AIAsset(
                    id=_identifier("ast", *key), asset_type=asset_type, name=name, provider=provider,
                    source_url=source_url, authorization_status=VerificationStatus.PENDING,
                    evidence_ids=ids, detected_by=[DetectionMethod.STATIC_PATTERN], confidence=0.6,
                )
    return list(sorted(assets.values(), key=lambda item: item.id)), list(sorted(evidence.values(), key=lambda item: item.id))
