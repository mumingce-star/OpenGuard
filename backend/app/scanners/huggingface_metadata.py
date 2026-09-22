"""Bounded offline parser for Hugging Face model and dataset metadata."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any

from app.ingestion.metadata_types import (
    MetadataError,
    MetadataRequest,
    SourceDescriptor,
    TemporaryMetadata,
    build_target,
)
from app.p1.profile_models import ParsedMetadataObservation


PARSER_VERSION = "openguard-huggingface-metadata/1"
_REVISION = re.compile(r"[0-9a-f]{40}")
_IDENTITY = re.compile(
    r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9_][A-Za-z0-9_.-]{0,95}"
)


def _invalid() -> ValueError:
    return ValueError("metadata_invalid")


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise _invalid()
        result[key] = value
    return result


def _integer(value: str) -> int:
    if len(value.lstrip("-")) > 256:
        raise _invalid()
    return int(value)


def _reject_constant(_: str) -> None:
    raise _invalid()


def _load(body: bytes) -> dict[str, Any]:
    try:
        text = body.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
            parse_int=_integer,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, OverflowError):
        raise _invalid() from None
    if type(value) is not dict:
        raise _invalid()
    return value


def _bounded_text(value: object, *, maximum: int = 1_000) -> str | None:
    if type(value) is not str or not value or len(value) > maximum:
        return None
    value.encode("utf-8", errors="strict")
    return value


def _license(value: object) -> str | None:
    text = _bounded_text(value, maximum=200)
    if text is not None:
        return text
    if type(value) is not list or not 1 <= len(value) <= 16:
        return None
    if any(_bounded_text(item, maximum=200) is None for item in value):
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _field(name: str, value: str, locator: str, status: str = "verified") -> dict[str, str]:
    return {
        "name": name,
        "value": value,
        "locator": locator,
        "verification_status": status,
    }


def _valid_utc_timestamp(value: object) -> bool:
    if type(value) is not str or not 1 <= len(value) <= 64 or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.utcoffset() == timezone.utc.utcoffset(None)


def _expected_source_url(source: SourceDescriptor) -> str:
    try:
        return build_target(
            MetadataRequest(
                provider=source.provider,
                resource_kind=source.resource_kind,
                repository_id=source.repository_id,
                revision_mode=source.revision_mode,
                requested_revision=source.requested_revision,
            )
        )
    except MetadataError:
        raise _invalid() from None


class HuggingFaceMetadataParser:
    """Parse transport-owned HF JSON without network, filesystem, or persistence access."""

    parser_version = PARSER_VERSION

    def parse(
        self,
        *,
        provider: str,
        resource_kind: str,
        resource_identity: str,
        temporary_metadata: TemporaryMetadata,
        source_descriptor: SourceDescriptor,
    ) -> ParsedMetadataObservation:
        try:
            return self._parse(
                provider=provider,
                resource_kind=resource_kind,
                resource_identity=resource_identity,
                temporary_metadata=temporary_metadata,
                source_descriptor=source_descriptor,
            )
        except ValueError:
            raise _invalid() from None
        except Exception:
            raise _invalid() from None

    def _parse(
        self,
        *,
        provider: str,
        resource_kind: str,
        resource_identity: str,
        temporary_metadata: TemporaryMetadata,
        source_descriptor: SourceDescriptor,
    ) -> ParsedMetadataObservation:
        if (
            provider != "huggingface"
            or resource_kind not in {"model", "dataset"}
            or type(resource_identity) is not str
            or not _IDENTITY.fullmatch(resource_identity)
            or type(temporary_metadata) is not TemporaryMetadata
            or type(source_descriptor) is not SourceDescriptor
            or source_descriptor is not temporary_metadata.source
            or source_descriptor.provider != provider
            or source_descriptor.resource_kind != resource_kind
            or source_descriptor.repository_id != resource_identity
            or source_descriptor.content_type != "application/json"
            or source_descriptor.descriptor_version != "metadata-source/1"
            or source_descriptor.transport_version != "hf-metadata-transport/1"
            or source_descriptor.full_response_replay_available is not False
            or source_descriptor.source_url != _expected_source_url(source_descriptor)
            or not _valid_utc_timestamp(source_descriptor.fetched_at)
            or type(source_descriptor.body_size) is not int
            or source_descriptor.body_size < 1
            or type(source_descriptor.body_sha256) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", source_descriptor.body_sha256)
        ):
            raise _invalid()

        body = temporary_metadata.bounded_bytes()
        if (
            type(body) is not bytes
            or not body
            or len(body) > 1_048_576
            or source_descriptor.body_size != len(body)
            or source_descriptor.body_sha256 != hashlib.sha256(body).hexdigest()
        ):
            raise _invalid()
        payload = _load(body)
        if payload.get("id") != resource_identity:
            raise _invalid()

        revision = payload.get("sha")
        if revision is not None and (type(revision) is not str or not _REVISION.fullmatch(revision)):
            raise _invalid()
        if revision != source_descriptor.resolved_revision:
            raise _invalid()
        if revision is None:
            if (
                source_descriptor.revision_locator is not None
                or source_descriptor.version_status != "bounded_content_revision_unconfirmed"
            ):
                raise _invalid()
        elif (
            source_descriptor.revision_locator != "/sha"
            or source_descriptor.version_status != "revision_observed"
        ):
            raise _invalid()
        if (
            source_descriptor.revision_mode == "fixed"
            and revision != source_descriptor.requested_revision
        ):
            raise _invalid()

        fields: list[dict[str, str]] = [
            _field("canonical_id", resource_identity, "/id"),
        ]
        gaps: set[str] = set()
        if revision is None:
            gaps.add("metadata_revision_unavailable")
        else:
            fields.append(_field("revision", revision, "/sha"))

        self._boolean_observations(payload, fields, gaps)
        self._optional_text(payload, "lastModified", "last_modified", fields, gaps)
        if resource_kind == "model":
            self._optional_text(payload, "pipeline_tag", "pipeline_tag", fields, gaps)
            self._optional_text(payload, "library_name", "library_name", fields, gaps)
        self._declared_license(payload, fields, gaps)

        excerpt = f"Bounded Hugging Face {resource_kind} metadata observation."
        return ParsedMetadataObservation.model_validate(
            {
                "parser_version": PARSER_VERSION,
                "bounded_excerpt": excerpt,
                "fields": fields,
                "verification_status": "pending",
                "coverage_gaps": sorted(gaps),
            }
        )

    @staticmethod
    def _boolean_observations(
        payload: dict[str, Any],
        fields: list[dict[str, str]],
        gaps: set[str],
    ) -> None:
        private = payload.get("private")
        if type(private) is bool:
            fields.append(_field("visibility", "private" if private else "public", "/private"))
        else:
            gaps.add("private_value_unavailable" if "private" not in payload else "unsupported_private_value")

        gated = payload.get("gated")
        if type(gated) is bool:
            fields.append(_field("access_gate", "gated" if gated else "ungated", "/gated"))
        elif "gated" in payload:
            fields.append(_field("access_gate", "unknown", "/gated", "pending"))
            gaps.add("unsupported_gate_value")
        else:
            gaps.add("gate_value_unavailable")

        disabled = payload.get("disabled")
        if type(disabled) is bool:
            fields.append(_field("disabled", str(disabled).lower(), "/disabled"))
        else:
            gaps.add("disabled_value_unavailable" if "disabled" not in payload else "unsupported_disabled_value")

    @staticmethod
    def _optional_text(
        payload: dict[str, Any],
        source_name: str,
        field_name: str,
        fields: list[dict[str, str]],
        gaps: set[str],
    ) -> None:
        if source_name not in payload:
            return
        value = _bounded_text(payload[source_name], maximum=200)
        if value is None:
            gaps.add(f"unsupported_{field_name}_value")
            return
        if source_name == "lastModified":
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                gaps.add("unsupported_last_modified_value")
                return
            if not value.endswith("Z") or parsed.utcoffset() is None:
                gaps.add("unsupported_last_modified_value")
                return
        fields.append(_field(field_name, value, f"/{source_name}"))

    @staticmethod
    def _declared_license(
        payload: dict[str, Any],
        fields: list[dict[str, str]],
        gaps: set[str],
    ) -> None:
        top_present = "license" in payload
        top = _license(payload.get("license")) if top_present else None
        card = payload.get("cardData")
        card_present = type(card) is dict and "license" in card
        card_value = _license(card.get("license")) if type(card) is dict else None

        invalid = (top_present and top is None) or (card_present and card_value is None)
        if type(card) not in {dict, type(None)}:
            invalid = True
        if invalid:
            gaps.add("unsupported_declared_license_value")

        if top is not None and card_value is not None and top != card_value:
            fields.extend(
                [
                    _field("declared_license_top_level", top, "/license", "pending"),
                    _field("declared_license_card", card_value, "/cardData/license", "pending"),
                ]
            )
            gaps.add("conflicting_declared_license")
            return

        value = card_value if card_value is not None else top
        if value is None:
            gaps.add("declared_license_unavailable")
            return
        locator = "/cardData/license" if card_value is not None else "/license"
        fields.append(_field("declared_license_raw", value, locator, "pending"))


__all__ = ["HuggingFaceMetadataParser", "PARSER_VERSION"]
