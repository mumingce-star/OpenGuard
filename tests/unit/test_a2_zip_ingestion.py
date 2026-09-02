"""Implementation-owned tests for the A2-0/A2-1 local ZIP vertical slice."""

from __future__ import annotations

import hashlib
import io
import os
import stat
import struct
import warnings
import zipfile
from pathlib import Path

import pytest

from app.ingestion.inventory import root_digest_v1
from app.ingestion.zip_stream import ZipIngestionService
from app.security.archive_path import normalize_member_path
from app.security.errors import IngestionSecurityError
from app.security.limits import MIB, ZipSafetyLimits


def _archive(entries: list[tuple[str | zipfile.ZipInfo, bytes]], compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=compression) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return output.getvalue()


def _service(root: Path, limits: ZipSafetyLimits | None = None) -> ZipIngestionService:
    root.mkdir()
    return ZipIngestionService(root, limits)


def _assert_clean(root: Path) -> None:
    assert list(root.iterdir()) == []


def _assert_rejected(service: ZipIngestionService, root: Path, payload: bytes, code: str, reason: str) -> None:
    with pytest.raises(IngestionSecurityError) as caught:
        service.ingest(io.BytesIO(payload))
    assert (caught.value.code, caught.value.reason) == (code, reason)
    _assert_clean(root)


def test_valid_zip_has_stable_inventory_digest_and_is_cleaned(tmp_path: Path) -> None:
    root = tmp_path / "secure-root"
    service = _service(root)
    try:
        result = service.ingest(
            io.BytesIO(
                _archive(
                    [
                        ("z.txt", b"z"),
                        ("nested/archive.zip", b"not recursively extracted"),
                        ("docs/readme.txt", b"alpha"),
                    ]
                )
            )
        )
    finally:
        service.close()

    assert [(entry.relative_path, entry.size_bytes) for entry in result.entries] == [
        ("docs/readme.txt", 5),
        ("nested/archive.zip", 25),
        ("z.txt", 1),
    ]
    assert result.root_digest == root_digest_v1(result.entries)
    expected = hashlib.sha256()
    expected.update(b"openguard-inventory-v1\n")
    for path, content in [
        ("docs/readme.txt", b"alpha"),
        ("nested/archive.zip", b"not recursively extracted"),
        ("z.txt", b"z"),
    ]:
        expected.update(path.encode("utf-8"))
        expected.update(b"\0")
        expected.update(str(len(content)).encode("ascii"))
        expected.update(b"\0")
        expected.update(hashlib.sha256(content).hexdigest().encode("ascii"))
        expected.update(b"\n")
    assert result.root_digest == expected.hexdigest()
    _assert_clean(root)


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("../outside.txt", "archive_path_unsafe"),
        ("folder\\outside.txt", "archive_path_unsafe"),
        ("C:/outside.txt", "archive_path_unsafe"),
        ("//server/share.txt", "archive_path_unsafe"),
        ("dir//empty.txt", "archive_path_unsafe"),
    ],
)
def test_unsafe_paths_are_rejected_before_publish(tmp_path: Path, name: str, reason: str) -> None:
    root = tmp_path / "secure-root"
    service = _service(root)
    try:
        _assert_rejected(service, root, _archive([(name, b"payload")]), "invalid_archive", reason)
    finally:
        service.close()


def test_control_character_and_windows_device_paths_are_rejected() -> None:
    limits = ZipSafetyLimits()
    for name in ("bad\x01.txt", "NUL.txt", "folder/CON"):
        with pytest.raises(IngestionSecurityError) as caught:
            normalize_member_path(name, is_directory=False, limits=limits)
        assert (caught.value.code, caught.value.reason) == ("invalid_archive", "archive_path_unsafe")


def test_home_shorthand_is_rejected_only_in_the_first_path_segment() -> None:
    limits = ZipSafetyLimits()
    for name in ("~/x", "~user/x"):
        with pytest.raises(IngestionSecurityError) as caught:
            normalize_member_path(name, is_directory=False, limits=limits)
        assert (caught.value.code, caught.value.reason) == ("invalid_archive", "archive_path_unsafe")

    accepted = normalize_member_path("ordinary/file~.txt", is_directory=False, limits=limits)
    assert accepted.relative_path == "ordinary/file~.txt"


def test_path_limit_reasons_use_the_frozen_limit_code() -> None:
    limits = ZipSafetyLimits()
    cases = [
        ("/".join(["deep"] * (limits.path_depth_max + 1)), "archive_path_depth_limit"),
        ("a" * 256, "archive_path_length_limit"),
    ]
    for name, reason in cases:
        with pytest.raises(IngestionSecurityError) as caught:
            normalize_member_path(name, is_directory=False, limits=limits)
        assert (caught.value.code, caught.value.reason) == ("archive_limit_exceeded", reason)


def test_duplicates_unicode_collisions_and_file_directory_conflicts_fail_whole_archive(tmp_path: Path) -> None:
    cases = [
        (
            [("same.txt", b"one"), ("same.txt", b"two")],
            "archive_duplicate_path",
        ),
        (
            [("caf\u00e9.txt", b"one"), ("cafe\u0301.txt", b"two")],
            "archive_duplicate_path",
        ),
        (
            [("NODE", b"file"), ("node/child.txt", b"child")],
            "archive_duplicate_path",
        ),
    ]
    for index, (entries, reason) in enumerate(cases):
        root = tmp_path / f"secure-root-{index}"
        service = _service(root)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                payload = _archive(entries)
            _assert_rejected(service, root, payload, "invalid_archive", reason)
        finally:
            service.close()


def test_known_symlink_and_encrypted_members_are_rejected(tmp_path: Path) -> None:
    symlink = zipfile.ZipInfo("link")
    symlink.create_system = 3
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    root = tmp_path / "secure-root-link"
    service = _service(root)
    try:
        _assert_rejected(
            service,
            root,
            _archive([(symlink, b"target")]),
            "invalid_archive",
            "archive_entry_type_unsafe",
        )
    finally:
        service.close()

    encrypted = bytearray(_archive([("readme.txt", b"text")]))
    central_directory = encrypted.index(b"PK\x01\x02")
    flags = struct.unpack_from("<H", encrypted, central_directory + 8)[0]
    struct.pack_into("<H", encrypted, central_directory + 8, flags | 0x1)
    root = tmp_path / "secure-root-encrypted"
    service = _service(root)
    try:
        _assert_rejected(service, root, bytes(encrypted), "invalid_archive", "archive_encrypted")
    finally:
        service.close()


def test_zero_external_attributes_are_materialized_as_fresh_regular_bytes(tmp_path: Path) -> None:
    payload = bytearray(_archive([("unknown-attributes.txt", b"ordinary bytes")]))
    central_directory = payload.index(b"PK\x01\x02")
    struct.pack_into("<I", payload, central_directory + 38, 0)
    root = tmp_path / "secure-root"
    service = _service(root)
    try:
        result = service.ingest(io.BytesIO(payload))
    finally:
        service.close()
    assert [(entry.relative_path, entry.size_bytes) for entry in result.entries] == [
        ("unknown-attributes.txt", len(b"ordinary bytes")),
    ]
    _assert_clean(root)


def test_corrupt_member_crc_fails_and_leaves_no_workspace(tmp_path: Path) -> None:
    payload = bytearray(_archive([("file.txt", b"CRC sensitive content")], compression=zipfile.ZIP_STORED))
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        info = archive.infolist()[0]
    name_size, extra_size = struct.unpack_from("<HH", payload, info.header_offset + 26)
    data_offset = info.header_offset + 30 + name_size + extra_size
    payload[data_offset] ^= 0x01

    root = tmp_path / "secure-root"
    service = _service(root)
    try:
        _assert_rejected(service, root, bytes(payload), "invalid_archive", "archive_integrity_failed")
    finally:
        service.close()


def test_local_header_size_mismatch_is_rejected_before_materialization(tmp_path: Path) -> None:
    payload = bytearray(_archive([("file.txt", b"header-sensitive")], compression=zipfile.ZIP_STORED))
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        info = archive.infolist()[0]
    local_compressed_size_offset = info.header_offset + 18
    central_compressed_size = struct.unpack_from("<I", payload, local_compressed_size_offset)[0]
    struct.pack_into("<I", payload, local_compressed_size_offset, central_compressed_size + 1)

    root = tmp_path / "secure-root"
    service = _service(root)
    try:
        _assert_rejected(service, root, bytes(payload), "invalid_archive", "archive_integrity_failed")
    finally:
        service.close()


def test_server_configuration_is_validated_and_quota_limits_cannot_be_raised_by_input(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ZipSafetyLimits(upload_max_bytes=8 * MIB - 1)
    with pytest.raises(ValueError):
        ZipSafetyLimits(path_depth_max=7)

    root = tmp_path / "secure-root-entry-count"
    limits = ZipSafetyLimits(entry_count_max=100)
    service = _service(root, limits)
    try:
        payload = _archive([(f"files/{index}.txt", b"x") for index in range(101)])
        _assert_rejected(service, root, payload, "archive_limit_exceeded", "archive_entry_count_limit")
    finally:
        service.close()

    root = tmp_path / "secure-root-single"
    limits = ZipSafetyLimits(single_file_max_bytes=1 * MIB, scan_single_file_read_max_bytes=1 * MIB)
    service = _service(root, limits)
    try:
        payload = _archive([("large.bin", b"a" * (MIB + 1))], compression=zipfile.ZIP_STORED)
        _assert_rejected(service, root, payload, "archive_limit_exceeded", "archive_single_file_limit")
    finally:
        service.close()


def test_actual_upload_stream_limit_is_enforced_before_zip_parsing(tmp_path: Path) -> None:
    root = tmp_path / "secure-root"
    limits = ZipSafetyLimits(upload_max_bytes=8 * MIB)
    service = _service(root, limits)
    try:
        _assert_rejected(
            service,
            root,
            b"x" * (8 * MIB + 1),
            "archive_limit_exceeded",
            "archive_upload_size_limit",
        )
    finally:
        service.close()


def test_expansion_ratio_limit_uses_integer_boundary_and_cleanup(tmp_path: Path) -> None:
    root = tmp_path / "secure-root"
    limits = ZipSafetyLimits(expansion_ratio_max=10)
    service = _service(root, limits)
    try:
        payload = _archive([("compressible.txt", b"A" * MIB)])
        _assert_rejected(service, root, payload, "archive_limit_exceeded", "archive_ratio_limit")
    finally:
        service.close()


def test_non_posix_startup_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "secure-root"
    root.mkdir()
    monkeypatch.setattr("app.security.secure_dir.os.name", "nt")
    with pytest.raises(IngestionSecurityError) as caught:
        ZipIngestionService(root)
    assert (caught.value.code, caught.value.reason) == ("scanner_failed", "posix_security_capability_unavailable")


def test_group_or_other_writable_workspace_root_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "secure-root"
    root.mkdir()
    os.chmod(root, 0o777)
    with pytest.raises(IngestionSecurityError) as caught:
        ZipIngestionService(root)
    assert (caught.value.code, caught.value.reason) == ("scanner_failed", "posix_security_capability_unavailable")
