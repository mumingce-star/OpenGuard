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
_PRODUCER = ProducerRef(type=ProducerType.PARSER, name="openguard-static-ai-detector", version="0.1.0")
_PATTERNS = (
    (AIAssetType.MODEL, "huggingface", re.compile(r"https?://huggingface\.co/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)")),
    (AIAssetType.MODEL, "modelscope", re.compile(r"https?://modelscope\.cn/models/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)")),
    (AIAssetType.DATASET, "huggingface", re.compile(r"https?://huggingface\.co/datasets/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)")),
    (AIAssetType.API, "openai", re.compile(r"\b(?:openai|OpenAI)\.(?:ChatCompletion|responses|chat\.completions)\b")),
    (AIAssetType.API, "anthropic", re.compile(r"\b(?:anthropic|Anthropic)\.(?:messages|Anthropic)\b")),
    (AIAssetType.API, "google", re.compile(r"\b(?:google\.generativeai|google\.genai|google\.generative_ai)\b")),
)


def _identifier(prefix: str, *parts: str) -> str:
    return f"{prefix}_{uuid.uuid5(_NAMESPACE, '|'.join(parts))}"


def _line_excerpt(line: str) -> str:
    # Do not turn credentials into evidence excerpts.
    return re.sub(r"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*[^\s,]+", r"\1=[REDACTED]", line.strip())[:1_000]


def detect_ai_assets(files: Mapping[str, str], *, observed_at: datetime | None = None) -> tuple[list[AIAsset], list[Evidence]]:
    """Find declared AI references in already-read, relative-path text files.

    This function never opens files, executes code, calls a remote API, or
    treats an observed reference as authorization or a license conclusion.
    """
    timestamp = observed_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    assets: dict[tuple[str, str, str], AIAsset] = {}
    evidence: list[Evidence] = []
    for locator, text in sorted(files.items()):
        if not locator or locator.startswith(("/", "\\")) or ".." in locator.split("/"):
            raise ValueError("files must use relative locators")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for asset_type, provider, pattern in _PATTERNS:
                for match in pattern.finditer(line):
                    name = match.group(1) if match.lastindex else provider
                    source_url = match.group(0) if match.group(0).startswith("http") else None
                    key = (asset_type.value, provider, name)
                    evidence_id = _identifier("evd", locator, str(line_number), provider, name)
                    evidence.append(Evidence(
                        id=evidence_id, kind=EvidenceKind.FILE, locator=locator, excerpt=_line_excerpt(line),
                        start_line=line_number, end_line=line_number,
                        content_hash={"algorithm": "sha256", "value": hashlib.sha256(line.encode()).hexdigest()},
                        detected_by=DetectionMethod.STATIC_PATTERN, producer=_PRODUCER,
                        observed_at=timestamp, verification_status=VerificationStatus.PENDING,
                    ))
                    existing = assets.get(key)
                    ids = sorted(set((existing.evidence_ids if existing else []) + [evidence_id]))
                    assets[key] = AIAsset(
                        id=_identifier("ast", *key), asset_type=asset_type, name=name, provider=provider,
                        source_url=source_url, authorization_status=VerificationStatus.PENDING,
                        evidence_ids=ids, detected_by=[DetectionMethod.STATIC_PATTERN], confidence=0.6,
                    )
    return list(sorted(assets.values(), key=lambda item: item.id)), list(sorted(evidence, key=lambda item: item.id))
