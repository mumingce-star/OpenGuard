"""Implementation tests for the lifecycle-bound A2 read-only session."""
from __future__ import annotations

import io
import os
import threading
import zipfile
from pathlib import Path

import pytest

from app.ingestion import ScanReadLimits, ZipIngestionService
from app.security.errors import IngestionSecurityError
from app.security.limits import MIB, ZipSafetyLimits


def _zip(entries: list[tuple[str, bytes]]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return output.getvalue()


def _service(tmp_path: Path) -> tuple[ZipIngestionService, Path]:
    root = tmp_path / "root"
    root.mkdir()
    return ZipIngestionService(root), root


def test_consumer_reads_inventory_bytes_and_session_expires(tmp_path: Path) -> None:
    service, root = _service(tmp_path)
    held = []
    try:
        result = service.ingest_with_consumer(
            io.BytesIO(_zip([("a.txt", b"alpha"), ("b.txt", b"beta")])),
            lambda session: (held.append(session), session.read_bytes("a.txt"))[1],
        )
    finally:
        service.close()
    assert result.consumer_result == b"alpha"
    assert [entry.relative_path for entry in result.inventory.entries] == ["a.txt", "b.txt"]
    with pytest.raises(IngestionSecurityError, match="scan_session_expired"):
        held[0].read_bytes("a.txt")
    assert list(root.iterdir()) == []


def test_read_limits_path_and_caught_session_errors_fail_closed(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    try:
        with pytest.raises(IngestionSecurityError, match="scan_read_limit_invalid"):
            service.ingest_with_consumer(io.BytesIO(_zip([("a.txt", b"a")])), lambda _: None, read_limits=ScanReadLimits(total_max_bytes=0))
        with pytest.raises(IngestionSecurityError, match="scan_path_not_in_inventory"):
            service.ingest_with_consumer(io.BytesIO(_zip([("a.txt", b"a")])), lambda session: session.read_bytes("../a.txt"))
        with pytest.raises(IngestionSecurityError, match="scan_read_limit_exceeded"):
            def catches_limit(session: object) -> str:
                try:
                    session.read_bytes("a.txt", max_bytes=1)  # type: ignore[attr-defined]
                except IngestionSecurityError:
                    pass
                return "ignored"
            service.ingest_with_consumer(
                io.BytesIO(_zip([("a.txt", b"abc")])),
                catches_limit,
            )
    finally:
        service.close()


def test_consumer_exception_and_cross_thread_read_are_sanitized(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    try:
        with pytest.raises(IngestionSecurityError, match="scan_consumer_failed"):
            service.ingest_with_consumer(io.BytesIO(_zip([("a.txt", b"a")])), lambda _: (_ for _ in ()).throw(ValueError("/secret/token")))

        def consumer(session: object) -> None:
            errors: list[Exception] = []
            thread = threading.Thread(target=lambda: _read_in_thread(session, errors))
            thread.start(); thread.join()
            assert errors
        with pytest.raises(IngestionSecurityError, match="scan_session_thread_violation"):
            service.ingest_with_consumer(io.BytesIO(_zip([("a.txt", b"a")])), consumer)
    finally:
        service.close()


def _read_in_thread(session: object, errors: list[Exception]) -> None:
    try:
        session.read_bytes("a.txt")  # type: ignore[attr-defined]
    except Exception as error:
        errors.append(error)


def test_consumer_can_use_tightened_limits_at_exact_total_boundary(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    try:
        result = service.ingest_with_consumer(
            io.BytesIO(_zip([("a.txt", b"a"), ("b.txt", b"b")])),
            lambda session: session.read_bytes("a.txt") + session.read_bytes("b.txt"),
            read_limits=ScanReadLimits(single_file_max_bytes=1, total_max_bytes=2),
        )
    finally:
        service.close()
    assert result.consumer_result == b"ab"


def test_consumer_can_return_inventory_only_dto_and_service_is_reusable(tmp_path: Path) -> None:
    service, root = _service(tmp_path)
    try:
        first = service.ingest_with_consumer(
            io.BytesIO(_zip([("one.txt", b"1")])),
            lambda session: session.inventory.root_digest,
        )
        second = service.ingest_with_consumer(
            io.BytesIO(_zip([("two.txt", b"2")])),
            lambda session: session.read_bytes("two.txt"),
        )
    finally:
        service.close()
    assert first.consumer_result == first.inventory.root_digest
    assert second.consumer_result == b"2"
    assert list(root.iterdir()) == []


def test_same_service_allows_independent_calls_from_different_threads(tmp_path: Path) -> None:
    service, root = _service(tmp_path)
    results: list[bytes] = []
    errors: list[BaseException] = []

    def run(name: str, content: bytes) -> None:
        try:
            result = service.ingest_with_consumer(
                io.BytesIO(_zip([(name, content)])),
                lambda session: session.read_bytes(name),
            )
            results.append(result.consumer_result)
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=run, args=("a.txt", b"a")), threading.Thread(target=run, args=("b.txt", b"b"))]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        service.close()
    assert not errors
    assert sorted(results) == [b"a", b"b"]
    assert list(root.iterdir()) == []


def test_same_thread_service_reentry_is_latched_even_if_consumer_catches_it(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)

    def consumer(_: object) -> str:
        try:
            service.ingest_with_consumer(io.BytesIO(_zip([("nested.txt", b"n")])), lambda session: None)
        except IngestionSecurityError:
            return "caught"
        raise AssertionError("reentry was not rejected")

    try:
        with pytest.raises(IngestionSecurityError) as captured:
            service.ingest_with_consumer(io.BytesIO(_zip([("outer.txt", b"o")])), consumer)
    finally:
        service.close()
    assert (captured.value.code, captured.value.reason) == ("scanner_failed", "scan_session_reentrant")


def test_not_zip_mapping_matches_existing_ingest_api(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    try:
        with pytest.raises(IngestionSecurityError) as captured:
            service.ingest_with_consumer(io.BytesIO(b"not a zip"), lambda session: None)
    finally:
        service.close()
    assert (captured.value.code, captured.value.reason) == ("invalid_archive", "archive_not_zip")


def test_invalid_read_limits_are_rejected_before_stream_consumption(tmp_path: Path) -> None:
    class TrackingStream(io.BytesIO):
        read_called = False

        def read(self, size: int = -1) -> bytes:
            self.read_called = True
            return super().read(size)

    stream = TrackingStream(_zip([("a.txt", b"a")]))
    service, _ = _service(tmp_path)
    try:
        with pytest.raises(IngestionSecurityError, match="scan_read_limit_invalid"):
            service.ingest_with_consumer(
                stream,
                lambda session: None,
                read_limits=ScanReadLimits(single_file_max_bytes=True),
            )
    finally:
        service.close()
    assert not stream.read_called


def test_explicit_server_read_limit_cannot_exceed_archive_limit() -> None:
    with pytest.raises(ValueError, match="must not exceed"):
        ZipSafetyLimits(single_file_max_bytes=1 * MIB, scan_single_file_read_max_bytes=2 * MIB)


def _replace_sealed_file(session: object, replacement: bytes, *, keep_inode: bool) -> None:
    workspace = session._workspace  # type: ignore[attr-defined]
    directory_fd = workspace.open_directory(("tree",))
    try:
        if keep_inode:
            file_fd = os.open("a.txt", os.O_WRONLY, dir_fd=directory_fd)
            try:
                os.write(file_fd, replacement)
                os.fsync(file_fd)
            finally:
                os.close(file_fd)
        else:
            replacement_fd = os.open("replacement", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory_fd)
            try:
                os.write(replacement_fd, replacement)
                os.fsync(replacement_fd)
            finally:
                os.close(replacement_fd)
            os.rename("replacement", "a.txt", src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
    finally:
        os.close(directory_fd)


@pytest.mark.parametrize("keep_inode", [False, True])
def test_identity_or_same_size_content_replacement_fails_closed(tmp_path: Path, keep_inode: bool) -> None:
    service, _ = _service(tmp_path)

    def consumer(session: object) -> bytes:
        _replace_sealed_file(session, b"bravo", keep_inode=keep_inode)
        return session.read_bytes("a.txt")  # type: ignore[attr-defined]

    try:
        with pytest.raises(IngestionSecurityError) as captured:
            service.ingest_with_consumer(io.BytesIO(_zip([("a.txt", b"alpha")])), consumer)
    finally:
        service.close()
    assert captured.value.reason == "scan_file_integrity_failed"


@pytest.mark.parametrize("path", ["/a.txt", "../a.txt", "./a.txt", "a\\.txt", "A.txt", Path("a.txt")])
def test_noncanonical_or_noninventory_paths_are_rejected(tmp_path: Path, path: object) -> None:
    service, _ = _service(tmp_path)
    try:
        with pytest.raises(IngestionSecurityError) as captured:
            service.ingest_with_consumer(
                io.BytesIO(_zip([("a.txt", b"alpha")])),
                lambda session: session.read_bytes(path),  # type: ignore[arg-type]
            )
    finally:
        service.close()
    assert captured.value.reason == "scan_path_not_in_inventory"
