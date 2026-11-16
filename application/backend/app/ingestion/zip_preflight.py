"""ZIP metadata preflight before any archive member is materialized."""

from __future__ import annotations

import stat
import struct
import zipfile
from dataclasses import dataclass

from app.security.archive_path import NormalizedArchivePath, normalize_member_path
from app.security.errors import IngestionSecurityError
from app.security.limits import ZipSafetyLimits


_ALLOWED_COMPRESSION = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
_LOCAL_FILE_HEADER = struct.Struct("<IHHHHHIIIHH")
_LOCAL_FILE_HEADER_SIGNATURE = 0x04034B50
_DATA_DESCRIPTOR_SIGNATURE = 0x08074B50
_ZIP64_EXTRA_FIELD = 0x0001
_ZIP64_SENTINEL = 0xFFFFFFFF


@dataclass(frozen=True)
class VerifiedZipMember:
    info: zipfile.ZipInfo
    path: NormalizedArchivePath


def _reject(reason: str) -> None:
    raise IngestionSecurityError("invalid_archive", reason)


def _reject_integrity() -> None:
    _reject("archive_integrity_failed")


def _read_exact(source: object, size: int) -> bytes:
    data = source.read(size)  # type: ignore[attr-defined]
    if not isinstance(data, bytes) or len(data) != size:
        _reject_integrity()
    return data


def _parse_extra_fields(extra: bytes) -> tuple[tuple[int, bytes], ...]:
    fields: list[tuple[int, bytes]] = []
    offset = 0
    while offset < len(extra):
        if len(extra) - offset < 4:
            _reject_integrity()
        field_id, field_size = struct.unpack_from("<HH", extra, offset)
        offset += 4
        if field_size > len(extra) - offset:
            _reject_integrity()
        fields.append((field_id, extra[offset : offset + field_size]))
        offset += field_size
    return tuple(fields)


def _zip64_sizes(
    uncompressed_size: int,
    compressed_size: int,
    extra: bytes,
) -> tuple[int, int]:
    """Resolve local-header sizes, requiring ZIP64 values when sentinels occur."""

    fields = _parse_extra_fields(extra)
    zip64_data = next((data for field_id, data in fields if field_id == _ZIP64_EXTRA_FIELD), None)
    offset = 0

    def resolve(value: int) -> int:
        nonlocal offset
        if value != _ZIP64_SENTINEL:
            return value
        if zip64_data is None or len(zip64_data) - offset < 8:
            _reject_integrity()
        resolved = struct.unpack_from("<Q", zip64_data, offset)[0]
        offset += 8
        return resolved

    return resolve(uncompressed_size), resolve(compressed_size)


def _encoded_filename(info: zipfile.ZipInfo) -> bytes:
    try:
        encoding = "utf-8" if info.flag_bits & 0x800 else "cp437"
        return info.filename.encode(encoding)
    except UnicodeEncodeError:
        _reject_integrity()


def _has_zip64_extra(extra: bytes) -> bool:
    return any(field_id == _ZIP64_EXTRA_FIELD for field_id, _ in _parse_extra_fields(extra))


def _verify_data_descriptor(
    source: object,
    *,
    data_offset: int,
    info: zipfile.ZipInfo,
    local_compressed_size: int,
    local_uncompressed_size: int,
) -> None:
    """Verify a data descriptor against the already parsed central directory."""

    source.seek(data_offset + info.compress_size)  # type: ignore[attr-defined]
    first_word = struct.unpack("<I", _read_exact(source, 4))[0]
    crc = struct.unpack("<I", _read_exact(source, 4))[0] if first_word == _DATA_DESCRIPTOR_SIGNATURE else first_word
    use_zip64 = (
        local_compressed_size == _ZIP64_SENTINEL
        or local_uncompressed_size == _ZIP64_SENTINEL
        or _has_zip64_extra(info.extra)
    )
    if use_zip64:
        compressed_size, uncompressed_size = struct.unpack("<QQ", _read_exact(source, 16))
    else:
        compressed_size, uncompressed_size = struct.unpack("<II", _read_exact(source, 8))
    if (crc, compressed_size, uncompressed_size) != (info.CRC, info.compress_size, info.file_size):
        _reject_integrity()


def _verify_local_headers(archive: zipfile.ZipFile, infos: tuple[zipfile.ZipInfo, ...]) -> None:
    """Cross-check each local record with central metadata before extraction.

    ``zipfile`` parses the central directory.  This check makes local header
    disagreements (including ZIP64 and data-descriptor records) an explicit
    fail-closed preflight decision rather than trusting whichever record a
    downstream reader happens to use.
    """

    source = archive.fp
    if source is None:
        _reject_integrity()
    try:
        for info in infos:
            source.seek(info.header_offset)
            (
                signature,
                _version_needed,
                flag_bits,
                compression,
                _modified_time,
                _modified_date,
                crc,
                local_compressed_size,
                local_uncompressed_size,
                filename_size,
                extra_size,
            ) = _LOCAL_FILE_HEADER.unpack(_read_exact(source, _LOCAL_FILE_HEADER.size))
            if signature != _LOCAL_FILE_HEADER_SIGNATURE:
                _reject_integrity()
            if flag_bits != info.flag_bits or compression != info.compress_type:
                _reject_integrity()
            if _read_exact(source, filename_size) != _encoded_filename(info):
                _reject_integrity()
            local_extra = _read_exact(source, extra_size)
            local_uncompressed, local_compressed = _zip64_sizes(
                local_uncompressed_size,
                local_compressed_size,
                local_extra,
            )
            data_offset = info.header_offset + _LOCAL_FILE_HEADER.size + filename_size + extra_size
            if flag_bits & 0x8:
                _verify_data_descriptor(
                    source,
                    data_offset=data_offset,
                    info=info,
                    local_compressed_size=local_compressed_size,
                    local_uncompressed_size=local_uncompressed_size,
                )
            elif (crc, local_compressed, local_uncompressed) != (info.CRC, info.compress_size, info.file_size):
                _reject_integrity()
    except IngestionSecurityError:
        raise
    except (AttributeError, EOFError, OSError, struct.error, ValueError) as error:
        raise IngestionSecurityError("invalid_archive", "archive_integrity_failed") from error


def _is_known_special_member(info: zipfile.ZipInfo, is_directory: bool) -> bool:
    """Reject explicit Unix special types but accept zero/unknown attributes as bytes.

    ZIP has no portable type field.  When the upper Unix mode carries a known
    type, it is authoritative enough to reject links/devices/FIFOs.  A zero or
    type-less attribute is intentionally treated as a fresh ordinary file (or a
    directory when its name says so); no archive permissions or metadata are
    restored later.
    """

    if info.create_system != 3:  # Unix; all other producer attributes are unknown.
        return False
    unix_mode = (info.external_attr >> 16) & 0xFFFF
    type_bits = stat.S_IFMT(unix_mode)
    if not type_bits:
        return False
    if is_directory:
        return type_bits not in {stat.S_IFDIR}
    return type_bits not in {stat.S_IFREG}


def preflight_zip(archive: zipfile.ZipFile, limits: ZipSafetyLimits) -> tuple[VerifiedZipMember, ...]:
    """Validate all names and metadata before any target file is created."""

    try:
        infos = archive.infolist()
    except (OSError, zipfile.BadZipFile) as error:
        raise IngestionSecurityError("invalid_archive", "archive_not_zip") from error
    if len(infos) > limits.entry_count_max:
        raise IngestionSecurityError("archive_limit_exceeded", "archive_entry_count_limit")
    # Semantic policy rejections are intentionally selected from central
    # metadata before consistency checks.  An archive advertising encryption is
    # rejected as encrypted even if its local flag is inconsistent too.
    for info in infos:
        if info.flag_bits & 0x1:
            _reject("archive_encrypted")
        if info.compress_type not in _ALLOWED_COMPRESSION:
            _reject("archive_unsupported_compression")
    _verify_local_headers(archive, infos)

    seen_original_names: set[str] = set()
    seen_collision_keys: set[str] = set()
    kinds_by_collision_key: dict[str, bool] = {}
    verified: list[VerifiedZipMember] = []
    declared_total = 0

    for info in infos:
        if info.filename in seen_original_names:
            _reject("archive_duplicate_path")
        seen_original_names.add(info.filename)

        is_directory = info.is_dir() or info.filename.endswith("/")
        path = normalize_member_path(info.filename, is_directory=is_directory, limits=limits)
        if path.collision_key in seen_collision_keys:
            _reject("archive_duplicate_path")
        seen_collision_keys.add(path.collision_key)
        if _is_known_special_member(info, is_directory):
            _reject("archive_entry_type_unsafe")
        if not is_directory:
            if info.file_size < 0 or info.compress_size < 0:
                _reject("archive_integrity_failed")
            if info.file_size > limits.single_file_max_bytes:
                raise IngestionSecurityError("archive_limit_exceeded", "archive_single_file_limit")
            declared_total += info.file_size
            if declared_total > limits.uncompressed_max_bytes:
                raise IngestionSecurityError("archive_limit_exceeded", "archive_total_size_limit")
            if info.file_size and info.compress_size == 0:
                raise IngestionSecurityError("archive_limit_exceeded", "archive_ratio_limit")
            if info.file_size > info.compress_size * limits.expansion_ratio_max:
                raise IngestionSecurityError("archive_limit_exceeded", "archive_ratio_limit")

        kinds_by_collision_key[path.collision_key] = is_directory
        verified.append(VerifiedZipMember(info=info, path=path))

    for member in verified:
        parts = member.path.parts
        for index in range(1, len(parts)):
            ancestor_key = "/".join(parts[:index]).casefold()
            if kinds_by_collision_key.get(ancestor_key) is False:
                _reject("archive_duplicate_path")
        if not member.path.is_directory:
            prefix = f"{member.path.collision_key}/"
            if any(candidate.startswith(prefix) for candidate in kinds_by_collision_key):
                _reject("archive_duplicate_path")
    return tuple(verified)
