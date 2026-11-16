"""Archive-member names are normalized before any filesystem operation."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .errors import IngestionSecurityError
from .limits import ZipSafetyLimits


_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")
_WINDOWS_DEVICES = {"con", "prn", "aux", "nul", *(f"com{number}" for number in range(1, 10)), *(f"lpt{number}" for number in range(1, 10))}


@dataclass(frozen=True)
class NormalizedArchivePath:
    parts: tuple[str, ...]
    relative_path: str
    collision_key: str
    is_directory: bool


def _reject(reason: str) -> None:
    raise IngestionSecurityError("invalid_archive", reason)


def _reject_limit(reason: str) -> None:
    raise IngestionSecurityError("archive_limit_exceeded", reason)


def normalize_member_path(
    raw_name: str,
    *,
    is_directory: bool,
    limits: ZipSafetyLimits,
) -> NormalizedArchivePath:
    """Return the sole filesystem representation accepted for a ZIP member."""

    if not isinstance(raw_name, str) or not raw_name:
        _reject("archive_path_unsafe")
    if "\\" in raw_name or raw_name.startswith("/") or _DRIVE_PREFIX.match(raw_name):
        _reject("archive_path_unsafe")
    if any(ord(character) < 32 or ord(character) == 127 for character in raw_name):
        _reject("archive_path_unsafe")

    name = raw_name[:-1] if is_directory and raw_name.endswith("/") else raw_name
    if not name:
        _reject("archive_path_unsafe")
    raw_parts = name.split("/")
    if any(not part or part in {".", ".."} for part in raw_parts):
        _reject("archive_path_unsafe")
    # ``~`` and ``~user`` are home-directory shorthand only when they occupy
    # the first segment.  Reject those representations before normalization;
    # a later ordinary filename such as ``docs/file~.txt`` remains valid.
    if raw_parts[0].startswith("~"):
        _reject("archive_path_unsafe")
    if len(raw_parts) > limits.path_depth_max:
        _reject_limit("archive_path_depth_limit")

    normalized_parts: list[str] = []
    for raw_part in raw_parts:
        part = unicodedata.normalize("NFC", raw_part)
        if not part or part in {".", ".."}:
            _reject("archive_path_unsafe")
        if len(part.encode("utf-8")) > 255:
            _reject_limit("archive_path_length_limit")
        device_stem = part.split(".", 1)[0].casefold()
        if device_stem in _WINDOWS_DEVICES:
            _reject("archive_path_unsafe")
        normalized_parts.append(part)

    relative_path = "/".join(normalized_parts)
    if len(relative_path.encode("utf-8")) > limits.path_utf8_bytes_max:
        _reject_limit("archive_path_length_limit")
    return NormalizedArchivePath(
        parts=tuple(normalized_parts),
        relative_path=relative_path,
        collision_key=relative_path.casefold(),
        is_directory=is_directory,
    )
