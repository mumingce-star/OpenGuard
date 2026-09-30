"""Evidence-first static recognition of model, dataset and API references."""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from .structured_models import structured_asset_references

from app.domain.models import (
    AIAsset, AIAssetType, DetectionMethod, Evidence, EvidenceKind, ProducerRef,
    ProducerType, VerificationStatus,
)

_NAMESPACE = uuid.UUID("e6047e12-66d2-5ebb-b78a-756e0ee05601")
_PRODUCER = ProducerRef(type=ProducerType.PARSER, name="openguard-static-ai-detector", version="0.3.0")
_PATTERNS = (
    (AIAssetType.MODEL, "huggingface", re.compile(r"https://huggingface\.co/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)")),
    (AIAssetType.MODEL, "modelscope", re.compile(r"https://modelscope\.cn/models/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)")),
    (AIAssetType.DATASET, "huggingface", re.compile(r"https://huggingface\.co/datasets/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)")),
    (AIAssetType.DATASET, "modelscope", re.compile(r"https://modelscope\.cn/datasets/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)")),
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
_JS_SDK_CALLS = (
    ("openai", re.compile(r"\bimport\s+OpenAI\s+from\s+['\"]openai['\"]"), re.compile(r"\bnew\s+OpenAI\s*\(")),
    ("anthropic", re.compile(r"\bimport\s+Anthropic\s+from\s+['\"]@anthropic-ai/sdk['\"]"), re.compile(r"\bnew\s+Anthropic\s*\(")),
    ("google", re.compile(r"\bimport\s*\{\s*(?:GoogleGenerativeAI|GoogleGenAI)\s*\}\s*from\s*['\"]@google/(?:generative-ai|genai)['\"]"), re.compile(r"\bnew\s+(?:GoogleGenerativeAI|GoogleGenAI)\s*\(")),
)
_ENV_PROVIDER_KEYS = {
    "OPENAI_API_KEY": "openai",
    "ANTHROPIC_API_KEY": "anthropic",
    "GOOGLE_API_KEY": "google",
    "GEMINI_API_KEY": "google",
}
_ENV_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=.*$")


@dataclass(frozen=True)
class StaticAssetCandidate:
    """Detector 0.3's transport-neutral, evidence-first candidate view.

    The P0 aggregate remains ``AIAsset`` plus ``Evidence``.  This view makes
    the detector's review gate explicit for Bench and downstream adapters
    without promoting a static observation into a license or authorization
    conclusion.
    """

    resource_type: AIAssetType
    provider: str | None
    name: str
    source_url: str | None
    locator: str
    start_line: int | None
    end_line: int | None
    rule_version: str
    evidence_id: str
    evidence_sha256: str
    review_status: str = "review_required"
    authorization_status: VerificationStatus = VerificationStatus.PENDING


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
        for asset_type, provider, pattern in _PATTERNS[:4]:
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
    for asset_type, provider, pattern in _PATTERNS[4:]:
        for match in pattern.finditer(line):
            yield asset_type, provider, provider, None, match.group()


def _javascript_sdk_references(locator: str, text: str):
    """Yield only imported-and-constructed SDK clients from JS/TS source.

    A package name in prose, a lockfile, or an import by itself is not a
    service-use candidate. This intentionally declines aliases and dynamic
    imports until they have a parser with equivalent binding guarantees.
    """
    if not locator.endswith((".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")):
        return
    for provider, import_pattern, constructor_pattern in _JS_SDK_CALLS:
        if import_pattern.search(text) is None:
            continue
        for match in constructor_pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            yield AIAssetType.API, provider, provider, line, match.group()


def _environment_references(locator: str, text: str):
    """Recognize provider configuration keys without retaining their values."""
    filename = locator.rsplit("/", 1)[-1]
    if not (filename == ".env" or filename.startswith(".env.")):
        return
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = _ENV_ASSIGNMENT.fullmatch(line)
        if match is None:
            continue
        provider = _ENV_PROVIDER_KEYS.get(match.group(1))
        if provider is not None:
            yield AIAssetType.API, provider, provider, line_number


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
                    source_url=source_url or (existing.source_url if existing else None), authorization_status=VerificationStatus.PENDING,
                    evidence_ids=ids, detected_by=sorted(set((existing.detected_by if existing else []) + [DetectionMethod.STATIC_PATTERN]), key=lambda method: method.value), confidence=0.6,
                )
        for asset_type, provider, name, line_number, excerpt in _javascript_sdk_references(locator, text):
            key = (asset_type.value, provider, name)
            evidence_id = _identifier("evd", "js_sdk", locator, digest, str(line_number), *key)
            evidence[evidence_id] = Evidence(
                id=evidence_id, kind=EvidenceKind.FILE, locator=locator, excerpt=excerpt,
                start_line=line_number, end_line=line_number,
                content_hash={"algorithm": "sha256", "value": digest},
                detected_by=DetectionMethod.STATIC_PATTERN, producer=_PRODUCER,
                observed_at=timestamp, verification_status=VerificationStatus.PENDING,
            )
            existing = assets.get(key)
            assets[key] = AIAsset(
                id=_identifier("ast", *key), asset_type=asset_type, name=name, provider=provider,
                source_url=existing.source_url if existing else None,
                authorization_status=VerificationStatus.PENDING,
                evidence_ids=sorted(set((existing.evidence_ids if existing else []) + [evidence_id])),
                detected_by=sorted(set((existing.detected_by if existing else []) + [DetectionMethod.STATIC_PATTERN]), key=lambda method: method.value),
                confidence=0.6,
            )
        for asset_type, provider, name, line_number in _environment_references(locator, text):
            key = (asset_type.value, provider, name)
            evidence_id = _identifier("evd", "environment", locator, digest, str(line_number), *key)
            evidence[evidence_id] = Evidence(
                id=evidence_id, kind=EvidenceKind.MANIFEST_FIELD, locator=locator, excerpt=provider,
                start_line=line_number, end_line=line_number,
                content_hash={"algorithm": "sha256", "value": digest},
                detected_by=DetectionMethod.MANIFEST_PARSER, producer=_PRODUCER,
                observed_at=timestamp, verification_status=VerificationStatus.PENDING,
            )
            existing = assets.get(key)
            assets[key] = AIAsset(
                id=_identifier("ast", *key), asset_type=asset_type, name=name, provider=provider,
                source_url=existing.source_url if existing else None,
                authorization_status=VerificationStatus.PENDING,
                evidence_ids=sorted(set((existing.evidence_ids if existing else []) + [evidence_id])),
                detected_by=sorted(set((existing.detected_by if existing else []) + [DetectionMethod.MANIFEST_PARSER]), key=lambda method: method.value),
                confidence=0.6,
            )
        for asset_kind, provider, name, start_line, end_line, origin in structured_asset_references(locator, text):
            asset_type = AIAssetType(asset_kind)
            method = {
                "actual_call": DetectionMethod.AST,
                "example_reference": DetectionMethod.STATIC_PATTERN,
                "explicit_config_candidate": DetectionMethod.MANIFEST_PARSER,
            }[origin]
            key = (asset_type.value, provider, name)
            evidence_id = _identifier("evd", origin, locator, digest, str(start_line), str(end_line), *key, name)
            evidence[evidence_id] = Evidence(
                id=evidence_id,
                kind=EvidenceKind.MANIFEST_FIELD if origin == "explicit_config_candidate" else EvidenceKind.FILE,
                locator=locator, excerpt=name,
                start_line=start_line, end_line=end_line,
                content_hash={"algorithm": "sha256", "value": digest},
                detected_by=method, producer=_PRODUCER,
                observed_at=timestamp, verification_status=VerificationStatus.PENDING,
            )
            existing = assets.get(key)
            assets[key] = AIAsset(
                id=_identifier("ast", *key), asset_type=asset_type, name=name, provider=provider,
                source_url=existing.source_url if existing else None,
                authorization_status=VerificationStatus.PENDING,
                evidence_ids=sorted(set((existing.evidence_ids if existing else []) + [evidence_id])),
                detected_by=sorted(set((existing.detected_by if existing else []) + [method]), key=lambda method: method.value),
                confidence=0.6,
            )
    return list(sorted(assets.values(), key=lambda item: item.id)), list(sorted(evidence.values(), key=lambda item: item.id))


def detect_static_asset_candidates(
    files: Mapping[str, str], *, observed_at: datetime | None = None,
) -> list[StaticAssetCandidate]:
    """Return one pending human-review candidate for each bound observation."""
    assets, evidence = detect_ai_assets(files, observed_at=observed_at)
    evidence_by_id = {item.id: item for item in evidence}
    candidates: list[StaticAssetCandidate] = []
    for asset in assets:
        for evidence_id in asset.evidence_ids:
            item = evidence_by_id[evidence_id]
            if item.content_hash is None:  # Defensive: file/config observations always bind bytes.
                raise ValueError("static asset evidence requires content hash")
            candidates.append(StaticAssetCandidate(
                resource_type=asset.asset_type, provider=asset.provider, name=asset.name,
                source_url=asset.source_url, locator=item.locator,
                start_line=item.start_line, end_line=item.end_line,
                rule_version=_PRODUCER.version, evidence_id=item.id,
                evidence_sha256=item.content_hash.value,
            ))
    return sorted(candidates, key=lambda item: (item.evidence_id, item.resource_type.value, item.name))
