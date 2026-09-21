"""Small, deterministic SPDX normalizer for the P0 supported license set.

It intentionally recognizes only explicit aliases.  Unknown text is retained
as pending evidence and never converted into a guessed SPDX identifier.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.models import Evidence, LicenseExpression, VerificationStatus

_NAMESPACE = uuid.UUID("c6bcaa52-7231-5a29-a4c0-3db3ec3f2d8d")
_ALIASES = {
    "agpl 3.0": "AGPL-3.0-only", "agpl-3.0-only": "AGPL-3.0-only",
    "apache 2.0": "Apache-2.0", "apache-2.0": "Apache-2.0", "apache license 2.0": "Apache-2.0",
    "bsd 2 clause": "BSD-2-Clause", "bsd-2-clause": "BSD-2-Clause",
    "bsd 3 clause": "BSD-3-Clause", "bsd-3-clause": "BSD-3-Clause",
    "cc0": "CC0-1.0", "cc0-1.0": "CC0-1.0",
    "cc by 4.0": "CC-BY-4.0", "cc-by-4.0": "CC-BY-4.0",
    "cc by nc 4.0": "CC-BY-NC-4.0", "cc-by-nc-4.0": "CC-BY-NC-4.0",
    "cddl 1.0": "CDDL-1.0", "cddl-1.0": "CDDL-1.0",
    "epl 2.0": "EPL-2.0", "epl-2.0": "EPL-2.0",
    "gpl 2.0": "GPL-2.0-only", "gpl-2.0-only": "GPL-2.0-only",
    "gpl 3.0": "GPL-3.0-only", "gpl-3.0-only": "GPL-3.0-only",
    "lgpl 2.1": "LGPL-2.1-only", "lgpl-2.1-only": "LGPL-2.1-only",
    "lgpl 3.0": "LGPL-3.0-only", "lgpl-3.0-only": "LGPL-3.0-only",
    "isc": "ISC", "mit": "MIT", "mpl 2.0": "MPL-2.0", "mpl-2.0": "MPL-2.0",
    "unlicense": "Unlicense",
}
_TOKEN = re.compile(r"\s+")


@dataclass(frozen=True)
class ParsedLicenseExpression:
    """The deliberately small expression subset supported by the P0 engine."""

    expression: str
    normalized_ids: tuple[str, ...]
    operators: tuple[str, ...]
    supported: bool


def _canonical_token(value: str) -> str:
    return _TOKEN.sub(" ", value.strip().lower().replace("/", " ").replace("_", " "))


def parse_license_expression(text: str) -> ParsedLicenseExpression:
    """Parse aliases and flat AND/OR expressions without guessing unsupported syntax."""

    parts = re.split(r"\s+(AND|OR)\s+", text.strip(), flags=re.IGNORECASE)
    normalized: list[str] = []
    expression: list[str] = []
    operators: list[str] = []
    for part in parts:
        if part.upper() in {"AND", "OR"}:
            operator = part.upper()
            expression.append(operator)
            operators.append(operator)
            continue
        candidate = _ALIASES.get(_canonical_token(part))
        if candidate is None:
            return ParsedLicenseExpression(text.strip(), (), (), False)
        normalized.append(candidate)
        expression.append(candidate)
    return ParsedLicenseExpression(
        " ".join(expression), tuple(sorted(set(normalized))), tuple(operators), True
    )


def _normalise_expression(text: str) -> tuple[str, list[str]]:
    parsed = parse_license_expression(text)
    return parsed.expression, list(parsed.normalized_ids)


def normalize_license(text: str, evidence: Sequence[Evidence]) -> LicenseExpression:
    """Return a P0 license object from explicit SPDX IDs/aliases and evidence.

    A compound expression is supported only when every term is recognized.
    Unrecognized text remains pending, with an empty normalized ID list.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("license text must be non-empty")
    evidence_ids = sorted({item.id for item in evidence})
    if not evidence_ids:
        raise ValueError("license normalization requires supporting evidence")
    expression, normalized = _normalise_expression(text)
    verified = normalized and all(item.verification_status is VerificationStatus.VERIFIED for item in evidence)
    identity = "|".join([expression, *evidence_ids])
    return LicenseExpression(
        id=f"lic_{uuid.uuid5(_NAMESPACE, identity)}",
        expression=expression,
        normalized_ids=normalized,
        evidence_ids=evidence_ids,
        confidence=1.0 if verified else 0.0,
        verification_status=VerificationStatus.VERIFIED if verified else VerificationStatus.PENDING,
    )
