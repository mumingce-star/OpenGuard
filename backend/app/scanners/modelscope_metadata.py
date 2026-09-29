"""Bounded offline parser for a captured ModelScope repository metadata envelope.

This adapter deliberately consumes only a transport-owned, in-memory JSON body.
It neither fetches ModelScope nor derives authorization, rights, compliance, or
an SPDX conclusion from provider metadata.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any

from app.ingestion.metadata_types import SourceDescriptor, TemporaryMetadata
from app.p1.profile_models import ParsedMetadataObservation


PARSER_VERSION = "openguard-modelscope-metadata/1"
_PART = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,95}")
_IDENTITY = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9_][A-Za-z0-9_.-]{0,95}")


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


def _load(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(
            body.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(_invalid()),
            parse_int=_integer,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, OverflowError):
        raise _invalid() from None
    if type(value) is not dict:
        raise _invalid()
    return value


def _text(value: object, *, maximum: int = 200) -> str | None:
    if type(value) is not str or not value or len(value) > maximum:
        return None
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return None
    return value


def _field(name: str, value: str, locator: str, status: str = "verified") -> dict[str, str]:
    return {"name": name, "value": value, "locator": locator, "verification_status": status}


def _valid_utc_timestamp(value: object) -> bool:
    if type(value) is not str or not 1 <= len(value) <= 64 or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.utcoffset() == timezone.utc.utcoffset(None)


def _target(kind: str, identity: str) -> str:
    return f"https://modelscope.cn/api/v1/{kind}s/{identity}"


class ModelScopeMetadataParser:
    """Parse a strict ModelScope API envelope without side effects.

    Accepted provider fields are deliberately narrow: ``Data.Namespace`` and
    ``Data.Name`` identify the repository; ``License``, ``Visibility``,
    ``Gated``, ``Revision`` and ``LastUpdatedTime`` remain provider-declared
    observations. Unknown or malformed optional values become coverage gaps.
    """

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

    def _parse(self, *, provider: str, resource_kind: str, resource_identity: str,
               temporary_metadata: TemporaryMetadata, source_descriptor: SourceDescriptor) -> ParsedMetadataObservation:
        if (
            provider != "modelscope"
            or resource_kind not in {"model", "dataset"}
            or type(resource_identity) is not str
            or not _IDENTITY.fullmatch(resource_identity)
            or type(temporary_metadata) is not TemporaryMetadata
            or type(source_descriptor) is not SourceDescriptor
            or source_descriptor is not temporary_metadata.source
            or source_descriptor.provider != provider
            or source_descriptor.resource_kind != resource_kind
            or source_descriptor.repository_id != resource_identity
            or source_descriptor.requested_revision is not None
            or source_descriptor.revision_mode != "default_observation"
            or source_descriptor.resolved_revision is not None
            or source_descriptor.revision_locator is not None
            or source_descriptor.version_status != "bounded_content_revision_unconfirmed"
            or source_descriptor.source_url != _target(resource_kind, resource_identity)
            or source_descriptor.content_type != "application/json"
            or source_descriptor.descriptor_version != "metadata-source/1"
            or source_descriptor.transport_version != "modelscope-metadata-transport/1"
            or source_descriptor.full_response_replay_available is not False
            or not _valid_utc_timestamp(source_descriptor.fetched_at)
            or type(source_descriptor.body_size) is not int
            or source_descriptor.body_size < 1
            or type(source_descriptor.body_sha256) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", source_descriptor.body_sha256)
        ):
            raise _invalid()

        body = temporary_metadata.bounded_bytes()
        if (
            type(body) is not bytes or not body or len(body) > 1_048_576
            or len(body) != source_descriptor.body_size
            or hashlib.sha256(body).hexdigest() != source_descriptor.body_sha256
        ):
            raise _invalid()
        payload = _load(body)
        if payload.get("Code") != 200 or payload.get("Success") is not True or type(payload.get("Data")) is not dict:
            raise _invalid()
        data = payload["Data"]
        namespace, name = _text(data.get("Namespace"), maximum=96), _text(data.get("Name"), maximum=96)
        if namespace is None or name is None or not _PART.fullmatch(namespace) or not _PART.fullmatch(name):
            raise _invalid()
        if f"{namespace}/{name}" != resource_identity:
            raise _invalid()

        # Even the identity is only a provider-declared, bounded observation.
        fields = [_field("canonical_id", resource_identity, "/Data/Namespace+/Data/Name", "pending")]
        gaps: set[str] = {"metadata_revision_unavailable"}
        self._observed_text(data, "Revision", "revision_hint", fields, gaps)
        self._observed_text(data, "LastUpdatedTime", "last_modified", fields, gaps)
        self._visibility(data, fields, gaps)
        self._gate(data, fields, gaps)
        self._license(data, fields, gaps)
        return ParsedMetadataObservation.model_validate({
            "parser_version": PARSER_VERSION,
            "bounded_excerpt": f"Bounded ModelScope {resource_kind} metadata observation.",
            "fields": fields,
            "verification_status": "pending",
            "coverage_gaps": sorted(gaps),
        })

    @staticmethod
    def _observed_text(data: dict[str, Any], source: str, name: str,
                       fields: list[dict[str, str]], gaps: set[str]) -> None:
        if source not in data:
            return
        value = _text(data[source])
        if value is None:
            gaps.add(f"unsupported_{name}_value")
            return
        fields.append(_field(name, value, f"/Data/{source}", "pending"))

    @staticmethod
    def _visibility(data: dict[str, Any], fields: list[dict[str, str]], gaps: set[str]) -> None:
        if "Visibility" not in data:
            gaps.add("visibility_value_unavailable")
            return
        value = _text(data["Visibility"], maximum=32)
        if value not in {"public", "private"}:
            gaps.add("unsupported_visibility_value")
            return
        fields.append(_field("visibility", value, "/Data/Visibility", "pending"))

    @staticmethod
    def _gate(data: dict[str, Any], fields: list[dict[str, str]], gaps: set[str]) -> None:
        if "Gated" not in data:
            gaps.add("gate_value_unavailable")
            return
        if type(data["Gated"]) is not bool:
            gaps.add("unsupported_gate_value")
            return
        fields.append(_field("access_gate", "gated" if data["Gated"] else "ungated", "/Data/Gated", "pending"))

    @staticmethod
    def _license(data: dict[str, Any], fields: list[dict[str, str]], gaps: set[str]) -> None:
        if "License" not in data:
            gaps.add("declared_license_unavailable")
            return
        value = _text(data["License"])
        if value is None:
            gaps.add("unsupported_declared_license_value")
            return
        fields.append(_field("declared_license_raw", value, "/Data/License", "pending"))


__all__ = ["ModelScopeMetadataParser", "PARSER_VERSION"]
