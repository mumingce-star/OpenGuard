"""Stable, non-sensitive errors for the ingestion boundary."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(eq=False)
class IngestionSecurityError(Exception):
    """An error safe to map to a future ingestion response.

    ``reason`` deliberately comes from a small, code-owned vocabulary.  Callers
    must not put archive names, local paths, parser exceptions, or input bytes in
    either field.
    """

    code: str
    reason: str

    def __str__(self) -> str:
        return f"{self.code}:{self.reason}"
