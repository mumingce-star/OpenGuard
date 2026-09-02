"""Independent Luna checks for the A2-0/A2-1 local ZIP boundary.

All archives are generated in memory with the Python standard library or with
small, auditable ZIP headers in this file.  No third-party or opaque binary
fixture is committed.  Expected reasons follow the frozen A2 acceptance
document, not the implementation's current exception spelling.
"""

from __future__ import annotations

import io
import os
import struct
import stat
import warnings
import zipfile
from pathlib import Path
from zlib import crc32

import pytest

from app.ingestion.inventory import root_digest_v1
from app.ingestion.zip_stream import ZipIngestionService
from app.security.archive_path import normalize_member_path
from app.security.errors import IngestionSecurityError
from app.security.limits import MIB, ZipSafetyLimits
from app.security.secure_dir import SecureRoot


def _archive(entries: list[tuple[str | zipfile.ZipInfo, bytes]], *, compression: int = zipfile.ZIP_DEFLATED) -> bytes:
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


def _assert_rejected(
    service: ZipIngestionService,
    root: Path,
    payload: bytes,
    expected_code: str,
    expected_reason: str,
) -> None:
    with pytest.raises(IngestionSecurityError) as caught:
        service.ingest(io.BytesIO(payload))
    assert (caught.value.code, caught.value.reason) == (expected_code, expected_reason)
    _assert_clean(root)


@pytest.mark.parametrize(
    "name",
    [
        "/absolute.txt",
        "../parent.txt",
        "a/../parent.txt",
        "./dot.txt",
        "a//empty-segment.txt",
        "folder\\backslash.txt",
        "C:/drive.txt",
        "\\\\server\\share.txt",
        "bad\x01.txt",
        "bad\x7f.txt",
        "folder/CON.txt",
        "folder/NUL.",
    ],
)
def test_path_policy_rejects_escape_controls_and_windows_names(name: str) -> None:
    with pytest.raises(IngestionSecurityError) as caught:
        normalize_member_path(name, is_directory=False, limits=ZipSafetyLimits())
    assert (caught.value.code, caught.value.reason) == ("invalid_archive", "archive_path_unsafe")


def test_nfc_and_casefold_collisions_are_rejected_as_duplicate_paths(tmp_path: Path) -> None:
    payload = _archive(
        [
            ("caf\u00e9.txt", b"one"),
            ("cafe\u0301.txt", b"two"),
        ]
    )
    root = tmp_path / "root"
    service = _service(root)
    try:
        _assert_rejected(service, root, payload, "invalid_archive", "archive_duplicate_path")
    finally:
        service.close()


@pytest.mark.parametrize(
    "entries",
    [
        [("same.txt", b"one"), ("same.txt", b"two")],
        [("node", b"file"), ("node/child.txt", b"child")],
    ],
)
def test_original_duplicate_and_file_directory_collision_are_not_last_write_wins(
    tmp_path: Path, entries: list[tuple[str, bytes]]
) -> None:
    root = tmp_path / "root"
    service = _service(root)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            payload = _archive(entries)
        _assert_rejected(service, root, payload, "invalid_archive", "archive_duplicate_path")
    finally:
        service.close()


def test_depth_equal_is_allowed_and_just_over_is_rejected_with_stable_limit_reason(tmp_path: Path) -> None:
    exact_name = "/".join(["d"] * 31 + ["file.txt"])
    over_name = "/".join(["d"] * 32 + ["file.txt"])
    limits = ZipSafetyLimits(path_depth_max=32)

    exact_root = tmp_path / "exact"
    exact_service = _service(exact_root, limits)
    try:
        result = exact_service.ingest(io.BytesIO(_archive([(exact_name, b"ok")], compression=zipfile.ZIP_STORED)))
        assert result.entries[0].relative_path == exact_name
    finally:
        exact_service.close()
    _assert_clean(exact_root)

    over_root = tmp_path / "over"
    over_service = _service(over_root, limits)
    try:
        _assert_rejected(
            over_service,
            over_root,
            _archive([(over_name, b"over")], compression=zipfile.ZIP_STORED),
            "archive_limit_exceeded",
            "archive_path_depth_limit",
        )
    finally:
        over_service.close()


def test_home_shorthand_is_rejected_only_in_first_segment_and_tilde_filename_is_inventory_data(
    tmp_path: Path,
) -> None:
    for index, name in enumerate(("~/escape.txt", "~user/escape.txt")):
        root = tmp_path / f"unsafe-{index}"
        service = _service(root)
        try:
            _assert_rejected(
                service,
                root,
                _archive([(name, b"must not escape")], compression=zipfile.ZIP_STORED),
                "invalid_archive",
                "archive_path_unsafe",
            )
        finally:
            service.close()

    root = tmp_path / "safe"
    service = _service(root)
    try:
        result = service.ingest(
            io.BytesIO(_archive([("ordinary/file~.txt", b"ordinary")], compression=zipfile.ZIP_STORED))
        )
    finally:
        service.close()
    assert [(entry.relative_path, entry.size_bytes) for entry in result.entries] == [("ordinary/file~.txt", 8)]
    _assert_clean(root)


def test_path_utf8_length_equal_is_allowed_and_just_over_is_rejected(tmp_path: Path) -> None:
    exact_name = f"{'a' * 127}/{'b' * 128}"
    over_name = f"{'a' * 127}/{'b' * 129}"
    assert len(exact_name.encode("utf-8")) == 256
    limits = ZipSafetyLimits(path_utf8_bytes_max=256)

    exact_root = tmp_path / "exact"
    exact_service = _service(exact_root, limits)
    try:
        result = exact_service.ingest(io.BytesIO(_archive([(exact_name, b"ok")], compression=zipfile.ZIP_STORED)))
        assert result.entries[0].relative_path == exact_name
    finally:
        exact_service.close()
    _assert_clean(exact_root)

    over_root = tmp_path / "over"
    over_service = _service(over_root, limits)
    try:
        _assert_rejected(
            over_service,
            over_root,
            _archive([(over_name, b"over")], compression=zipfile.ZIP_STORED),
            "archive_limit_exceeded",
            "archive_path_length_limit",
        )
    finally:
        over_service.close()


@pytest.mark.parametrize("mode", [stat.S_IFIFO | 0o644, stat.S_IFCHR | 0o600, stat.S_IFSOCK | 0o600])
def test_unix_special_external_attributes_fail_closed_with_frozen_reason(tmp_path: Path, mode: int) -> None:
    member = zipfile.ZipInfo("special")
    member.create_system = 3
    member.external_attr = mode << 16
    root = tmp_path / "root"
    service = _service(root)
    try:
        _assert_rejected(service, root, _archive([(member, b"bytes")]), "invalid_archive", "archive_entry_type_unsafe")
    finally:
        service.close()


def test_zero_and_unknown_producer_attributes_create_only_regular_bytes(tmp_path: Path) -> None:
    payload = bytearray(_archive([("plain.bin", b"ordinary")], compression=zipfile.ZIP_STORED))
    central = payload.index(b"PK\x01\x02")
    struct.pack_into("<I", payload, central + 38, 0xDEADBEEF)
    struct.pack_into("<H", payload, central + 5, 0)  # unknown non-Unix producer
    root = tmp_path / "root"
    service = _service(root)
    try:
        result = service.ingest(io.BytesIO(payload))
    finally:
        service.close()
    assert [(entry.relative_path, entry.size_bytes) for entry in result.entries] == [("plain.bin", 8)]
    assert result.root_digest == root_digest_v1(result.entries)
    _assert_clean(root)


def test_nested_archive_is_ordinary_content_and_not_recursively_expanded(tmp_path: Path) -> None:
    nested = _archive([("inner.txt", b"must not appear")])
    outer = _archive([("nested/inner.zip", nested)])
    root = tmp_path / "root"
    service = _service(root)
    try:
        result = service.ingest(io.BytesIO(outer))
    finally:
        service.close()
    assert [entry.relative_path for entry in result.entries] == ["nested/inner.zip"]
    assert result.entries[0].size_bytes == len(nested)
    _assert_clean(root)


def test_non_zip_and_truncated_zip_fail_before_inventory(tmp_path: Path) -> None:
    for index, payload in enumerate([b"not a zip", _archive([("truncated.txt", b"bytes")])[:-1]]):
        root = tmp_path / f"root-{index}"
        service = _service(root)
        try:
            _assert_rejected(service, root, payload, "invalid_archive", "archive_not_zip")
        finally:
            service.close()


def test_encrypted_flag_is_rejected_before_member_materialization(tmp_path: Path) -> None:
    payload = bytearray(_archive([("encrypted.txt", b"secret-free test bytes")], compression=zipfile.ZIP_STORED))
    central = payload.index(b"PK\x01\x02")
    flags = struct.unpack_from("<H", payload, central + 8)[0]
    struct.pack_into("<H", payload, central + 8, flags | 0x1)
    root = tmp_path / "root"
    service = _service(root)
    try:
        _assert_rejected(service, root, bytes(payload), "invalid_archive", "archive_encrypted")
    finally:
        service.close()


def test_crc_corruption_is_rejected_and_does_not_leave_a_tree(tmp_path: Path) -> None:
    payload = bytearray(_archive([("crc.txt", b"CRC must be checked")], compression=zipfile.ZIP_STORED))
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        info = archive.infolist()[0]
    name_size, extra_size = struct.unpack_from("<HH", payload, info.header_offset + 26)
    data_offset = info.header_offset + 30 + name_size + extra_size
    payload[data_offset] ^= 0x01
    root = tmp_path / "root"
    service = _service(root)
    try:
        _assert_rejected(service, root, bytes(payload), "invalid_archive", "archive_integrity_failed")
    finally:
        service.close()


def test_inventory_order_and_digest_are_stable_for_safe_utf8_names(tmp_path: Path) -> None:
    payload = _archive(
        [("z space.txt", b"z"), ("中文/标点!.txt", b"utf8"), ("A.txt", b"a")],
        compression=zipfile.ZIP_STORED,
    )
    root = tmp_path / "root"
    service = _service(root)
    try:
        result = service.ingest(io.BytesIO(payload))
    finally:
        service.close()
    assert [entry.relative_path for entry in result.entries] == ["A.txt", "z space.txt", "中文/标点!.txt"]
    assert result.root_digest == root_digest_v1(result.entries)
    _assert_clean(root)


def test_zip64_small_member_with_zip64_headers_is_read_as_a_regular_file(tmp_path: Path) -> None:
    payload = _zip64_small_stored_member("zip64.txt", b"zip64 bytes")
    root = tmp_path / "root"
    service = _service(root)
    try:
        result = service.ingest(io.BytesIO(payload))
    finally:
        service.close()
    assert [(entry.relative_path, entry.size_bytes) for entry in result.entries] == [("zip64.txt", 11)]
    _assert_clean(root)


def test_data_descriptor_member_is_read_and_crc_verified(tmp_path: Path) -> None:
    payload = _with_data_descriptor(_archive([("descriptor.txt", b"descriptor bytes")], compression=zipfile.ZIP_STORED))
    root = tmp_path / "root"
    service = _service(root)
    try:
        result = service.ingest(io.BytesIO(payload))
    finally:
        service.close()
    assert [(entry.relative_path, entry.size_bytes) for entry in result.entries] == [("descriptor.txt", 16)]
    _assert_clean(root)


def test_local_and_central_header_size_mismatch_fails_closed(tmp_path: Path) -> None:
    payload = bytearray(_archive([("header.txt", b"header bytes")], compression=zipfile.ZIP_STORED))
    local = 0
    struct.pack_into("<I", payload, local + 18, 999)
    struct.pack_into("<I", payload, local + 22, 999)
    root = tmp_path / "root"
    service = _service(root)
    try:
        _assert_rejected(service, root, bytes(payload), "invalid_archive", "archive_integrity_failed")
    finally:
        service.close()


def test_entry_count_equal_is_allowed_and_just_over_is_rejected_with_stable_reason(tmp_path: Path) -> None:
    limits = ZipSafetyLimits(entry_count_max=100)
    exact_root = tmp_path / "exact"
    exact_service = _service(exact_root, limits)
    try:
        result = exact_service.ingest(
            io.BytesIO(_archive([(f"f{index}.txt", b"x") for index in range(100)], compression=zipfile.ZIP_STORED))
        )
        assert len(result.entries) == 100
    finally:
        exact_service.close()
    _assert_clean(exact_root)

    over_root = tmp_path / "over"
    over_service = _service(over_root, limits)
    try:
        _assert_rejected(
            over_service,
            over_root,
            _archive([(f"f{index}.txt", b"x") for index in range(101)], compression=zipfile.ZIP_STORED),
            "archive_limit_exceeded",
            "archive_entry_count_limit",
        )
    finally:
        over_service.close()


def test_single_file_equal_is_allowed_and_just_over_is_rejected_with_stable_reason(tmp_path: Path) -> None:
    limit = MIB
    limits = ZipSafetyLimits(single_file_max_bytes=limit)
    exact_root = tmp_path / "exact"
    exact_service = _service(exact_root, limits)
    try:
        result = exact_service.ingest(io.BytesIO(_archive([("file.bin", b"x" * limit)], compression=zipfile.ZIP_STORED)))
        assert result.entries[0].size_bytes == limit
    finally:
        exact_service.close()
    _assert_clean(exact_root)

    over_root = tmp_path / "over"
    over_service = _service(over_root, limits)
    try:
        _assert_rejected(
            over_service,
            over_root,
            _archive([("file.bin", b"x" * (limit + 1))], compression=zipfile.ZIP_STORED),
            "archive_limit_exceeded",
            "archive_single_file_limit",
        )
    finally:
        over_service.close()


def test_total_uncompressed_equal_is_allowed_and_just_over_is_rejected(tmp_path: Path) -> None:
    limit = 32 * MIB
    limits = ZipSafetyLimits(uncompressed_max_bytes=limit)
    exact_payload = _archive(
        [("a.bin", b"a" * (16 * MIB)), ("b.bin", b"b" * (16 * MIB))], compression=zipfile.ZIP_STORED
    )
    exact_root = tmp_path / "exact"
    exact_service = _service(exact_root, limits)
    try:
        result = exact_service.ingest(io.BytesIO(exact_payload))
        assert sum(entry.size_bytes for entry in result.entries) == limit
    finally:
        exact_service.close()
    _assert_clean(exact_root)

    over_root = tmp_path / "over"
    over_service = _service(over_root, limits)
    try:
        over_payload = _archive(
            [("a.bin", b"a" * (16 * MIB)), ("b.bin", b"b" * (16 * MIB + 1))], compression=zipfile.ZIP_STORED
        )
        _assert_rejected(over_service, over_root, over_payload, "archive_limit_exceeded", "archive_total_size_limit")
    finally:
        over_service.close()


def test_upload_equal_is_allowed_and_one_byte_over_is_rejected_before_zip_parse(tmp_path: Path) -> None:
    payload = _archive([("small.bin", b"x" * (8 * MIB))], compression=zipfile.ZIP_STORED)
    limits = ZipSafetyLimits(upload_max_bytes=len(payload))
    exact_root = tmp_path / "exact"
    exact_service = _service(exact_root, limits)
    try:
        result = exact_service.ingest(io.BytesIO(payload))
        assert result.entries[0].relative_path == "small.bin"
    finally:
        exact_service.close()
    _assert_clean(exact_root)

    over_root = tmp_path / "over"
    over_service = _service(over_root, limits)
    try:
        _assert_rejected(
            over_service,
            over_root,
            payload + b"x",
            "archive_limit_exceeded",
            "archive_upload_size_limit",
        )
    finally:
        over_service.close()


def test_expansion_ratio_boundary_is_measured_from_actual_member_bytes(tmp_path: Path) -> None:
    content = b"A" * 1_024
    payload = _archive([("ratio.txt", content)])
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        compressed_size = archive.infolist()[0].compress_size
    ratio_ceiling = (len(content) + compressed_size - 1) // compressed_size
    assert 10 <= ratio_ceiling <= 200

    exact_root = tmp_path / "exact"
    exact_service = _service(exact_root, ZipSafetyLimits(expansion_ratio_max=ratio_ceiling))
    try:
        result = exact_service.ingest(io.BytesIO(payload))
        assert result.entries[0].size_bytes == len(content)
    finally:
        exact_service.close()
    _assert_clean(exact_root)

    over_root = tmp_path / "over"
    over_service = _service(over_root, ZipSafetyLimits(expansion_ratio_max=ratio_ceiling - 1))
    try:
        _assert_rejected(over_service, over_root, payload, "archive_limit_exceeded", "archive_ratio_limit")
    finally:
        over_service.close()


def test_preexisting_symlink_parent_cannot_redirect_descriptor_relative_write(tmp_path: Path) -> None:
    root_path = tmp_path / "root"
    root_path.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_bytes(b"unchanged")
    secure_root = SecureRoot.open(root_path)
    workspace = secure_root.create_workspace()
    try:
        os.symlink(outside, root_path / workspace._name / "link")
        with pytest.raises(IngestionSecurityError) as caught:
            workspace.write_new_file(("link", "escape.txt"), lambda fd: os.write(fd, b"must not write"))
        assert (caught.value.code, caught.value.reason) == ("scanner_failed", "workspace_integrity_failed")
        assert not (outside / "escape.txt").exists()
        assert sentinel.read_bytes() == b"unchanged"
    finally:
        workspace.cleanup(3)
        secure_root.close()


def _with_data_descriptor(original: bytes) -> bytes:
    """Turn a simple one-member ZIP into a valid stored data-descriptor ZIP."""

    eocd = original.rfind(b"PK\x05\x06")
    central_offset = struct.unpack_from("<I", original, eocd + 16)[0]
    central = bytearray(original[central_offset:eocd])
    local = bytearray(original[:central_offset])
    name_size, extra_size = struct.unpack_from("<HH", local, 26)
    data_offset = 30 + name_size + extra_size
    data = bytes(local[data_offset:])
    local = local[:data_offset]
    flags = struct.unpack_from("<H", local, 6)[0] | 0x08
    struct.pack_into("<HIII", local, 6, flags, 0, 0, 0)
    central_flags = struct.unpack_from("<H", central, 8)[0] | 0x08
    struct.pack_into("<H", central, 8, central_flags)
    crc = crc32(data) & 0xFFFFFFFF
    descriptor = struct.pack("<IIII", 0x08074B50, crc, len(data), len(data))
    new_central_offset = len(local) + len(data) + len(descriptor)
    new_eocd = bytearray(original[eocd:])
    struct.pack_into("<I", new_eocd, 16, new_central_offset)
    return bytes(local) + data + descriptor + bytes(central) + bytes(new_eocd)


def _zip64_small_stored_member(name: str, data: bytes) -> bytes:
    name_bytes = name.encode("utf-8")
    crc = crc32(data) & 0xFFFFFFFF
    zip64_extra = struct.pack("<HHQQ", 0x0001, 16, len(data), len(data))
    local = struct.pack(
        "<IHHHHHIIIHH",
        0x04034B50,
        45,
        0,
        zipfile.ZIP_STORED,
        0,
        0,
        crc,
        0xFFFFFFFF,
        0xFFFFFFFF,
        len(name_bytes),
        len(zip64_extra),
    ) + name_bytes + zip64_extra + data
    central = struct.pack(
        "<IHHHHHHIIIHHHHHII",
        0x02014B50,
        45,
        45,
        0,
        zipfile.ZIP_STORED,
        0,
        0,
        crc,
        0xFFFFFFFF,
        0xFFFFFFFF,
        len(name_bytes),
        len(zip64_extra),
        0,
        0,
        0,
        0,
        0,
    ) + name_bytes + zip64_extra
    central_offset = len(local)
    zip64_eocd_offset = central_offset + len(central)
    zip64_eocd = struct.pack("<IQHHIIQQQQ", 0x06064B50, 44, 45, 45, 0, 0, 1, 1, len(central), central_offset)
    locator = struct.pack("<IIQI", 0x07064B50, 0, zip64_eocd_offset, 1)
    eocd = struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, 0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0)
    return local + central + zip64_eocd + locator + eocd
