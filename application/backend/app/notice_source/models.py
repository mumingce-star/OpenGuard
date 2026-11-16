"""Strict, detached `openguard.notice-source/1` production DTO."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
_GAP = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
MAX_ITEMS = 1024
MAX_FULL_BYTES = 64 * 1024
MAX_EXCERPT_BYTES = 4 * 1024
MAX_ITEM_JSON_BYTES = 128 * 1024
MAX_PACKAGE_BYTES = 8 * 1024 * 1024


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class Producer(StrictModel):
    type: Literal["collector"]
    name: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=128)
    config_digest: str | None = None

    @field_validator("config_digest")
    @classmethod
    def sha_or_none(cls, value: str | None) -> str | None:
        if value is not None and not _SHA256.fullmatch(value):
            raise ValueError("sha256_invalid")
        return value


class Binding(StrictModel):
    scan_id: str = Field(min_length=1, max_length=256)
    registry_revision: str = Field(min_length=1, max_length=256)
    input_digest: str
    inventory_digest: str
    facts_hash: str

    @field_validator("input_digest", "inventory_digest", "facts_hash")
    @classmethod
    def sha(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("sha256_invalid")
        return value


class Relation(StrictModel):
    state: Literal["resolved", "unresolved"]
    subject: str | None = Field(default=None, min_length=1, max_length=512)
    basis: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def consistent(self) -> "Relation":
        if (self.state == "resolved") != (self.subject is not None):
            raise ValueError("relation_subject_invalid")
        return self


class Coverage(StrictModel):
    state: Literal["completed", "partial"]
    omissions: list[str] = Field(default_factory=list, max_length=MAX_ITEMS)
    gap_codes: list[str] = Field(default_factory=list, max_length=MAX_ITEMS)

    @field_validator("omissions")
    @classmethod
    def unique_omissions(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)) or any(not item or len(item) > 1024 for item in value):
            raise ValueError("coverage_omissions_invalid")
        return value

    @field_validator("gap_codes")
    @classmethod
    def unique_gaps(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)) or any(not _GAP.fullmatch(item) for item in value):
            raise ValueError("gap_codes_invalid")
        return value

    @model_validator(mode="after")
    def partial_has_reason(self) -> "Coverage":
        if self.state == "partial" and not (self.omissions or self.gap_codes):
            raise ValueError("partial_coverage_reason_missing")
        if self.state == "completed" and (self.omissions or self.gap_codes):
            raise ValueError("completed_coverage_has_gaps")
        return self


class Content(StrictModel):
    state: Literal["full", "excerpt", "not_observed", "not_scanned", "read_failed"]
    text: str | None = None
    encoding: Literal["utf-8"] | None = None
    byte_range: list[int] | None = None
    truncated: bool | None = None
    retained_bytes_sha256: str | None = None
    whole_bytes_sha256: str | None = None
    excerpt_bytes_sha256: str | None = None
    gap_codes: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("retained_bytes_sha256", "whole_bytes_sha256", "excerpt_bytes_sha256")
    @classmethod
    def hashes(cls, value: str | None) -> str | None:
        if value is not None and not _SHA256.fullmatch(value):
            raise ValueError("sha256_invalid")
        return value

    @field_validator("gap_codes")
    @classmethod
    def content_gaps(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)) or any(not _GAP.fullmatch(item) for item in value):
            raise ValueError("gap_codes_invalid")
        return value

    @model_validator(mode="after")
    def content_semantics(self) -> "Content":
        retained = (self.text, self.encoding, self.byte_range, self.truncated, self.retained_bytes_sha256)
        if self.state in {"full", "excerpt"}:
            if any(value is None for value in retained) or self.whole_bytes_sha256 is None:
                raise ValueError("retained_content_missing")
            if len(self.byte_range) != 2:  # type: ignore[arg-type]
                raise ValueError("byte_range_invalid")
            start, end = self.byte_range  # type: ignore[misc]
            if start < 0 or end < start:
                raise ValueError("byte_range_invalid")
            encoded = self.text.encode("utf-8")  # type: ignore[union-attr]
            if end - start != len(encoded) or hashlib.sha256(encoded).hexdigest() != self.retained_bytes_sha256:
                raise ValueError("retained_bytes_mismatch")
            if self.state == "full" and (self.truncated or start != 0 or self.whole_bytes_sha256 != self.retained_bytes_sha256
                                           or self.excerpt_bytes_sha256 is not None):
                raise ValueError("full_content_invalid")
            if self.state == "excerpt" and (not self.truncated or len(encoded) > MAX_EXCERPT_BYTES
                                              or self.excerpt_bytes_sha256 != self.retained_bytes_sha256):
                raise ValueError("excerpt_content_invalid")
        elif any(value is not None for value in (*retained, self.whole_bytes_sha256, self.excerpt_bytes_sha256)):
            raise ValueError("unobserved_content_present")
        if self.state == "not_observed" and self.gap_codes:
            raise ValueError("not_observed_has_gap")
        if self.state != "not_observed" and not self.gap_codes and self.state in {"not_scanned", "read_failed"}:
            raise ValueError("missing_observation_gap")
        return self


class NoticeObservation(StrictModel):
    observation_key: str = Field(min_length=1, max_length=256)
    locator: str = Field(min_length=1, max_length=1024)
    content: Content
    collector: Producer
    relation: Relation


class NoticeSourceCollection(StrictModel):
    """Detached snapshot returned while the read-only scan session is live.

    It intentionally cannot claim a terminal registry revision or facts hash.
    """

    schema_version: Literal["openguard.notice-source/1"]
    observed_at: str
    coverage: Coverage
    observations: list[NoticeObservation] = Field(min_length=1, max_length=MAX_ITEMS)

    @field_validator("observed_at")
    @classmethod
    def utc(cls, value: str) -> str:
        if not _UTC.fullmatch(value):
            raise ValueError("utc_invalid")
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        if parsed.tzinfo != timezone.utc:
            raise ValueError("utc_invalid")
        return value

    @model_validator(mode="after")
    def verify_collection(self) -> "NoticeSourceCollection":
        keys = [item.observation_key for item in self.observations]
        if len(keys) != len(set(keys)):
            raise ValueError("observation_key_duplicate")
        if any(len(canonical_json(item.model_dump(mode="json"))) > MAX_ITEM_JSON_BYTES for item in self.observations):
            raise ValueError("observation_too_large")
        return self


class NoticeSourcePackage(NoticeSourceCollection):
    """Terminally bound package, assembled by A only after final facts exist."""

    binding: Binding
    package_hash: str

    @field_validator("package_hash")
    @classmethod
    def package_sha(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("sha256_invalid")
        return value

    @model_validator(mode="after")
    def verify_package(self) -> "NoticeSourcePackage":
        payload = self.model_dump(mode="json", exclude={"package_hash"})
        if hashlib.sha256(canonical_json(payload)).hexdigest() != self.package_hash:
            raise ValueError("package_hash_mismatch")
        if len(canonical_json(self.model_dump(mode="json"))) > MAX_PACKAGE_BYTES:
            raise ValueError("package_too_large")
        return self


def bind_notice_source_collection(collection: NoticeSourceCollection | object, *, binding: Binding) -> NoticeSourcePackage:
    """Create the final package after A has obtained actual terminal binding facts."""
    source = collection if isinstance(collection, NoticeSourceCollection) else NoticeSourceCollection.model_validate(collection)
    payload = {**source.model_dump(mode="json"), "binding": binding.model_dump(mode="json")}
    return NoticeSourcePackage.model_validate({**payload, "package_hash": hashlib.sha256(canonical_json(payload)).hexdigest()})


def validate_notice_source_package(value: object) -> NoticeSourcePackage:
    """Validate a detached JSON-compatible package and its canonical package hash."""
    raw = canonical_json(value)
    if len(raw) > MAX_PACKAGE_BYTES:
        raise ValueError("package_too_large")
    return NoticeSourcePackage.model_validate(json.loads(raw))
