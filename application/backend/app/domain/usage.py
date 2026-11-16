"""Optional user-declared use; presets never imply missing details."""
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class UsageDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    preset: Literal["personal", "internal", "open_source", "closed_source", "service", "unknown"] = "unknown"
    commercial: bool | None = None
    modified: bool | None = None
    distributed: bool | None = None
    network_service: bool | None = None
    training: bool | None = None
    redistributed_assets: bool | None = None
    source_disclosure: bool | None = None
    declared_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("declared_at")
    @classmethod
    def utc_only(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError("declared_at must be explicit UTC")
        return value
