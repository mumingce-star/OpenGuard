"""Independent A2-2 regression tests using real temporary filesystems."""

from __future__ import annotations

import io
import errno
import os
import stat
import threading
import zipfile
from pathlib import Path

import pytest

from app.ingestion import ReadOnlyScanSession, ScanReadLimits, ZipIngestionService
from app.security.errors import IngestionSecurityError
from app.security.limits import MIB, ZipSafetyLimits
import app.ingestion.read_session as read_session_module
import app.ingestion.zip_stream as zip_stream_module


def _zip(entries: list[tuple[str, bytes]]) -> io.BytesIO:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    output.seek(0)
    return output


def _service(tmp_path: Path, limits: ZipSafetyLimits | None = None) -> tuple[ZipIngestionService, Path]:
    root = tmp_path / "workspace-root"
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(mode=0o700)
    return ZipIngestionService(root, limits=limits), root


def _tree_fd(session: object) -> int:
    return session._workspace.open_directory(("tree",))  # type: ignore[attr-defined]


def _replace_with_symlink(session: object, name: str, target: Path) -> None:
    directory_fd = _tree_fd(session)
    try:
        os.symlink(str(target), "replacement", dir_fd=directory_fd)
        os.rename("replacement", name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
    finally:
        os.close(directory_fd)


def _replace_with_directory(session: object, name: str) -> None:
    directory_fd = _tree_fd(session)
    try:
        os.mkdir("replacement", 0o700, dir_fd=directory_fd)
        os.rename("replacement", name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
    finally:
        os.close(directory_fd)


def _replace_with_fifo(session: object, name: str) -> None:
    directory_fd = _tree_fd(session)
    try:
        os.mkfifo("replacement", 0o600, dir_fd=directory_fd)
        os.rename("replacement", name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
    finally:
        os.close(directory_fd)


def _replace_with_file(session: object, name: str, content: bytes) -> None:
    directory_fd = _tree_fd(session)
    file_fd: int | None = None
    try:
        file_fd = os.open(
            "replacement",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=directory_fd,
        )
        os.write(file_fd, content)
        os.fsync(file_fd)
        os.rename("replacement", name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(directory_fd)


def _rewrite_same_inode(session: object, name: str, content: bytes) -> None:
    directory_fd = _tree_fd(session)
    file_fd: int | None = None
    try:
        file_fd = os.open(name, os.O_WRONLY, dir_fd=directory_fd)
        os.ftruncate(file_fd, len(content))
        os.write(file_fd, content)
        os.fsync(file_fd)
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(directory_fd)


def test_path_and_type_inputs_are_rejected_without_external_sentinel_access(tmp_path: Path) -> None:
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "sentinel.txt"
    sentinel.write_bytes(b"outside")
    decomposed = "cafe\u0301.txt"
    service, root = _service(tmp_path)
    invalid_inputs: list[object] = [
        "/a.txt",
        "../a.txt",
        "./a.txt",
        "a\\b.txt",
        "C:\\a.txt",
        "\\\\server\\share\\a.txt",
        decomposed,
        "CAFÉ.TXT",
        Path("a.txt"),
        b"a.txt",
        "missing.txt",
        "dir",
    ]
    try:
        for invalid in invalid_inputs:
            with pytest.raises(IngestionSecurityError) as captured:
                service.ingest_with_consumer(
                    _zip([("a.txt", b"alpha"), ("café.txt", b"accent"), ("dir/", b"")]),
                    lambda session, invalid=invalid: session.read_bytes(invalid),  # type: ignore[arg-type]
                )
            assert (captured.value.code, captured.value.reason) == (
                "scanner_failed",
                "scan_path_not_in_inventory",
            )
            assert str(captured.value) == "scanner_failed:scan_path_not_in_inventory"
    finally:
        service.close()
    assert list(root.iterdir()) == []
    assert sentinel.read_bytes() == b"outside"


def test_parent_directory_symlink_is_not_followed_and_external_sentinel_is_untouched(tmp_path: Path) -> None:
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "sentinel.txt"
    sentinel.write_bytes(b"outside")
    service, root = _service(tmp_path)

    def consumer(session: object) -> None:
        _replace_with_symlink(session, "nested", external)
        session.read_bytes("nested/value.txt")  # type: ignore[attr-defined]

    try:
        with pytest.raises(IngestionSecurityError, match="scan_file_integrity_failed"):
            service.ingest_with_consumer(_zip([("nested/value.txt", b"inside")]), consumer)
    finally:
        service.close()
    assert list(root.iterdir()) == []
    assert sentinel.read_bytes() == b"outside"


@pytest.mark.parametrize("replacement", ["symlink", "directory", "fifo"])
def test_file_symlink_directory_and_fifo_replacements_fail_without_blocking(
    tmp_path: Path, replacement: str
) -> None:
    external_file = tmp_path / "external.txt"
    external_file.write_bytes(b"outside")
    service, root = _service(tmp_path)
    replace = {
        "symlink": lambda session: _replace_with_symlink(session, "a.txt", external_file),
        "directory": lambda session: _replace_with_directory(session, "a.txt"),
        "fifo": lambda session: _replace_with_fifo(session, "a.txt"),
    }[replacement]

    def consumer(session: object) -> None:
        replace(session)
        session.read_bytes("a.txt")  # type: ignore[attr-defined]

    try:
        with pytest.raises(IngestionSecurityError) as captured:
            service.ingest_with_consumer(_zip([("a.txt", b"alpha")]), consumer)
    finally:
        service.close()
    assert (captured.value.code, captured.value.reason) == (
        "scanner_failed",
        "scan_file_integrity_failed",
    )
    assert list(root.iterdir()) == []
    assert external_file.read_bytes() == b"outside"


@pytest.mark.parametrize("replacement_kind", ["new_inode", "same_inode"])
def test_same_size_identity_or_content_replacement_fails_closed(
    tmp_path: Path, replacement_kind: str
) -> None:
    service, root = _service(tmp_path)

    def consumer(session: object) -> None:
        if replacement_kind == "new_inode":
            _replace_with_file(session, "a.txt", b"bravo")
        else:
            _rewrite_same_inode(session, "a.txt", b"bravo")
        session.read_bytes("a.txt")  # type: ignore[attr-defined]

    try:
        with pytest.raises(IngestionSecurityError, match="scan_file_integrity_failed"):
            service.ingest_with_consumer(_zip([("a.txt", b"alpha")]), consumer)
    finally:
        service.close()
    assert list(root.iterdir()) == []


def test_read_during_same_inode_rewrite_is_detected_by_before_after_seals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, root = _service(tmp_path)
    observed_reads = 0
    mutated = False
    original_read = read_session_module.os.read

    def hooked_read(file_descriptor: int, size: int) -> bytes:
        nonlocal observed_reads, mutated
        data = original_read(file_descriptor, size)
        if not mutated and data:
            try:
                if stat.S_ISREG(os.fstat(file_descriptor).st_mode):
                    observed_reads += 1
            except OSError:
                return data
            # First target read is the consumer pre-validation inventory pass;
            # mutate during the subsequent target read in read_snapshot_file.
            if observed_reads == 2:
                mutated = True
                _rewrite_same_inode(held_session[0], "a.txt", b"bravo")
        return data

    held_session: list[object] = []
    def consumer(session: object) -> None:
        held_session.append(session)
        monkeypatch.setattr(read_session_module.os, "read", hooked_read)
        session.read_bytes("a.txt")  # type: ignore[attr-defined]

    try:
        with pytest.raises(IngestionSecurityError, match="scan_file_integrity_failed"):
            service.ingest_with_consumer(_zip([("a.txt", b"alpha")]), consumer)
    finally:
        service.close()
    assert mutated
    assert list(root.iterdir()) == []


def test_single_file_limit_rejects_exactly_one_byte_over_before_open(tmp_path: Path) -> None:
    payload = b"x" * (64 * 1024 + 1)
    service, root = _service(tmp_path)
    try:
        with pytest.raises(IngestionSecurityError) as captured:
            service.ingest_with_consumer(
                _zip([("a.txt", payload)]),
                lambda session: session.read_bytes("a.txt"),
                read_limits=ScanReadLimits(single_file_max_bytes=64 * 1024),
            )
    finally:
        service.close()
    assert (captured.value.code, captured.value.reason) == (
        "scanner_failed",
        "scan_read_limit_exceeded",
    )
    assert list(root.iterdir()) == []


def test_total_limit_counts_repeated_reads_and_rejects_one_byte_over(tmp_path: Path) -> None:
    payload = b"x" * (64 * 1024)
    service, root = _service(tmp_path)
    reads: list[bytes] = []

    def consumer(session: object) -> None:
        reads.append(session.read_bytes("a.txt"))  # type: ignore[attr-defined]
        session.read_bytes("a.txt")  # type: ignore[attr-defined]

    try:
        with pytest.raises(IngestionSecurityError) as captured:
            service.ingest_with_consumer(
                _zip([("a.txt", payload)]),
                consumer,
                read_limits=ScanReadLimits(single_file_max_bytes=len(payload), total_max_bytes=len(payload) + 1),
            )
    finally:
        service.close()
    assert reads == [payload]
    assert captured.value.reason == "scan_read_limit_exceeded"
    assert list(root.iterdir()) == []


@pytest.mark.parametrize(
    "read_limits",
    [
        ScanReadLimits(single_file_max_bytes=0),
        ScanReadLimits(single_file_max_bytes=True),  # type: ignore[arg-type]
        ScanReadLimits(single_file_max_bytes=1.0),  # type: ignore[arg-type]
        ScanReadLimits(single_file_max_bytes=2 * MIB + 1),
        ScanReadLimits(single_file_max_bytes=64 * 1024, total_max_bytes=64 * 1024 - 1),
    ],
)
def test_invalid_call_limits_are_rejected_before_archive_stream_consumption(
    tmp_path: Path, read_limits: ScanReadLimits
) -> None:
    class TrackingStream(io.BytesIO):
        read_called = False

        def read(self, size: int = -1) -> bytes:
            self.read_called = True
            return super().read(size)

    stream = TrackingStream(_zip([("a.txt", b"alpha")]).read())
    service, root = _service(tmp_path)
    try:
        with pytest.raises(IngestionSecurityError) as captured:
            service.ingest_with_consumer(stream, lambda session: None, read_limits=read_limits)
    finally:
        service.close()
    assert captured.value.reason == "scan_read_limit_invalid"
    assert not stream.read_called
    assert list(root.iterdir()) == []


@pytest.mark.parametrize("max_bytes", [0, True, 1.0, 2 * MIB + 1])
def test_invalid_read_max_bytes_are_rejected_without_leaking_input(
    tmp_path: Path, max_bytes: object
) -> None:
    service, root = _service(tmp_path)
    try:
        with pytest.raises(IngestionSecurityError) as captured:
            service.ingest_with_consumer(
                _zip([("a.txt", b"alpha")]),
                lambda session: session.read_bytes("a.txt", max_bytes=max_bytes),  # type: ignore[arg-type]
            )
    finally:
        service.close()
    assert str(captured.value) == "scanner_failed:scan_read_limit_invalid"
    assert list(root.iterdir()) == []


def test_none_server_scan_limit_derives_from_older_one_mib_archive_limit(tmp_path: Path) -> None:
    limits = ZipSafetyLimits(single_file_max_bytes=MIB, scan_single_file_read_max_bytes=None)
    assert limits.effective_scan_single_file_read_max_bytes == MIB
    service, root = _service(tmp_path, limits)
    try:
        result = service.ingest_with_consumer(_zip([("a.txt", b"alpha")]), lambda session: session.read_bytes("a.txt"))
    finally:
        service.close()
    assert result.consumer_result == b"alpha"
    assert list(root.iterdir()) == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"scan_single_file_read_max_bytes": 0},
        {"scan_single_file_read_max_bytes": True},
        {"scan_single_file_read_max_bytes": 64 * 1024.0},
        {"scan_single_file_read_max_bytes": 33 * MIB},
        {"single_file_max_bytes": MIB, "scan_single_file_read_max_bytes": 2 * MIB},
        {"scan_total_read_max_bytes": 0},
        {"scan_total_read_max_bytes": True},
        {"scan_total_read_max_bytes": 1.0},
    ],
)
def test_invalid_server_scan_limits_fail_closed(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ZipSafetyLimits(**kwargs)  # type: ignore[arg-type]


def test_saved_session_reference_is_expired_after_consumer_and_cleanup(tmp_path: Path) -> None:
    service, root = _service(tmp_path)
    held: list[object] = []
    try:
        result = service.ingest_with_consumer(
            _zip([("a.txt", b"alpha")]),
            lambda session: (held.append(session), session.read_bytes("a.txt"))[1],
        )
    finally:
        service.close()
    assert result.consumer_result == b"alpha"
    for access in (lambda: held[0].inventory, lambda: held[0].read_bytes("a.txt")):  # type: ignore[attr-defined]
        with pytest.raises(IngestionSecurityError) as captured:
            access()
        assert str(captured.value) == "scanner_failed:scan_session_expired"
    assert list(root.iterdir()) == []


def test_real_cross_thread_read_poisoning_fails_the_outer_call(tmp_path: Path) -> None:
    service, root = _service(tmp_path)
    errors: list[BaseException] = []

    def consumer(session: object) -> None:
        def read_in_other_thread() -> None:
            try:
                session.read_bytes("a.txt")  # type: ignore[attr-defined]
            except BaseException as error:
                errors.append(error)

        thread = threading.Thread(target=read_in_other_thread)
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive()

    try:
        with pytest.raises(IngestionSecurityError) as captured:
            service.ingest_with_consumer(_zip([("a.txt", b"alpha")]), consumer)
    finally:
        service.close()
    assert errors and str(errors[0]) == "scanner_failed:scan_session_thread_violation"
    assert str(captured.value) == "scanner_failed:scan_session_thread_violation"
    assert list(root.iterdir()) == []


def test_same_session_read_reentry_is_latched(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    service, root = _service(tmp_path)
    held: list[object] = []
    original_read = read_session_module.read_snapshot_file

    def reenter(*args: object, **kwargs: object) -> bytes:
        held[0].read_bytes("a.txt")  # type: ignore[attr-defined]
        return original_read(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(read_session_module, "read_snapshot_file", reenter)
    try:
        with pytest.raises(IngestionSecurityError) as captured:
            service.ingest_with_consumer(
                _zip([("a.txt", b"alpha")]),
                lambda session: (held.append(session), session.read_bytes("a.txt"))[1],
            )
    finally:
        service.close()
    assert str(captured.value) == "scanner_failed:scan_session_reentrant"
    assert list(root.iterdir()) == []


def test_same_service_same_thread_reentry_remains_failed_if_consumer_catches_inner_error(tmp_path: Path) -> None:
    service, root = _service(tmp_path)

    def consumer(_: object) -> str:
        try:
            service.ingest_with_consumer(_zip([("inner.txt", b"inner")]), lambda session: None)
        except IngestionSecurityError:
            return "caught"
        raise AssertionError("service reentry was not rejected")

    try:
        with pytest.raises(IngestionSecurityError) as captured:
            service.ingest_with_consumer(_zip([("outer.txt", b"outer")]), consumer)
    finally:
        service.close()
    assert str(captured.value) == "scanner_failed:scan_session_reentrant"
    assert list(root.iterdir()) == []


def test_independent_sessions_on_two_threads_have_isolated_workspaces_and_budgets(tmp_path: Path) -> None:
    service, root = _service(tmp_path)
    barrier = threading.Barrier(2)
    results: list[bytes] = []
    errors: list[BaseException] = []

    def run(name: str, content: bytes) -> None:
        try:
            result = service.ingest_with_consumer(
                _zip([(name, content)]),
                lambda session: (barrier.wait(timeout=5), session.read_bytes(name))[1],
                read_limits=ScanReadLimits(single_file_max_bytes=len(content), total_max_bytes=len(content)),
            )
            results.append(result.consumer_result)
        except BaseException as error:
            errors.append(error)

    threads = [
        threading.Thread(target=run, args=("a.txt", b"a")),
        threading.Thread(target=run, args=("b.txt", b"b")),
    ]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
    finally:
        service.close()
    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert sorted(results) == [b"a", b"b"]
    assert list(root.iterdir()) == []


@pytest.mark.parametrize("consumer_error", [ValueError("fixture/path/marker"), IngestionSecurityError("forged", "body")])
def test_consumer_exceptions_and_forged_security_errors_are_sanitized(
    tmp_path: Path, consumer_error: BaseException
) -> None:
    service, root = _service(tmp_path)
    try:
        with pytest.raises(IngestionSecurityError) as captured:
            service.ingest_with_consumer(_zip([("a.txt", b"alpha")]), lambda _: (_ for _ in ()).throw(consumer_error))
    finally:
        service.close()
    assert str(captured.value) == "scanner_failed:scan_consumer_failed"
    assert "fixture/path/marker" not in str(captured.value)
    assert "body" not in str(captured.value)
    assert list(root.iterdir()) == []


def test_caught_session_error_still_fails_outer_call_without_partial_result(tmp_path: Path) -> None:
    service, root = _service(tmp_path)

    def consumer(session: object) -> str:
        try:
            session.read_bytes("missing.txt")  # type: ignore[attr-defined]
        except IngestionSecurityError:
            return "ignored"
        raise AssertionError("missing path unexpectedly succeeded")

    try:
        with pytest.raises(IngestionSecurityError) as captured:
            service.ingest_with_consumer(_zip([("a.txt", b"alpha")]), consumer)
    finally:
        service.close()
    assert str(captured.value) == "scanner_failed:scan_path_not_in_inventory"
    assert list(root.iterdir()) == []


def test_unread_file_modification_is_caught_by_final_full_tree_revalidation(tmp_path: Path) -> None:
    service, root = _service(tmp_path)

    def consumer(session: object) -> bytes:
        _rewrite_same_inode(session, "unread.txt", b"bravo")
        return session.read_bytes("read.txt")  # type: ignore[attr-defined]

    try:
        with pytest.raises(IngestionSecurityError, match="scan_file_integrity_failed"):
            service.ingest_with_consumer(
                _zip([("read.txt", b"alpha"), ("unread.txt", b"alpha")]),
                consumer,
            )
    finally:
        service.close()
    assert list(root.iterdir()) == []


def test_read_oserror_is_stable_and_does_not_leak_injected_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, root = _service(tmp_path)
    original_read = read_session_module.os.read

    target_reads = 0
    target_inode: int | None = None

    def failing_read(file_descriptor: int, size: int) -> bytes:
        nonlocal target_reads
        data = original_read(file_descriptor, size)
        if target_inode is not None and data and os.fstat(file_descriptor).st_ino == target_inode:
            target_reads += 1
            if target_reads == 2:
                raise OSError("fixture/path/marker body")
        return data

    # Install the fault immediately before the real consumer read, while the
    # inventory and pre-validation have already completed.
    def actual_consumer(session: object) -> bytes:
        nonlocal target_inode
        directory_fd = _tree_fd(session)
        try:
            target_inode = os.stat("a.txt", dir_fd=directory_fd, follow_symlinks=False).st_ino
        finally:
            os.close(directory_fd)
        monkeypatch.setattr(read_session_module.os, "read", failing_read)
        try:
            return session.read_bytes("a.txt")  # type: ignore[attr-defined]
        finally:
            monkeypatch.setattr(read_session_module.os, "read", original_read)

    try:
        with pytest.raises(IngestionSecurityError) as captured:
            service.ingest_with_consumer(_zip([("a.txt", b"alpha")]), actual_consumer)
    finally:
        service.close()
    assert str(captured.value) == "scanner_failed:scan_file_read_failed"
    assert "fixture/path/marker" not in str(captured.value)
    assert list(root.iterdir()) == []


def test_transient_root_descriptor_open_error_is_read_failure_and_is_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, root = _service(tmp_path)
    original_read_snapshot_file = read_session_module.read_snapshot_file

    def consumer(session: object) -> bytes:
        original_open = read_session_module.os.open

        def transient_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
            if path == "tree" and kwargs.get("dir_fd") is not None:
                raise OSError("fixture/sensitive-marker")
            return original_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

        def transient_root_open(*args: object, **kwargs: object) -> bytes:
            monkeypatch.setattr(read_session_module.os, "open", transient_open)
            try:
                return original_read_snapshot_file(*args, **kwargs)  # type: ignore[arg-type]
            finally:
                monkeypatch.setattr(read_session_module.os, "open", original_open)

        monkeypatch.setattr(read_session_module, "read_snapshot_file", transient_root_open)
        try:
            return session.read_bytes("a.txt")  # type: ignore[attr-defined]
        finally:
            monkeypatch.setattr(read_session_module, "read_snapshot_file", original_read_snapshot_file)

    try:
        with pytest.raises(IngestionSecurityError) as captured:
            service.ingest_with_consumer(_zip([("a.txt", b"alpha")]), consumer)
    finally:
        service.close()
    assert str(captured.value) == "scanner_failed:scan_file_read_failed"
    assert "fixture/sensitive-marker" not in str(captured.value)
    assert list(root.iterdir()) == []


def test_failed_target_close_is_recovered_and_fd_is_ebadf_after_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, root = _service(tmp_path)
    original_read_snapshot_file = read_session_module.read_snapshot_file
    original_close = read_session_module.os.close
    target_inode: int | None = None
    failed_fd: int | None = None

    def consumer(session: object) -> bytes:
        nonlocal target_inode, failed_fd
        directory_fd = _tree_fd(session)
        try:
            target_inode = os.stat("a.txt", dir_fd=directory_fd, follow_symlinks=False).st_ino
        finally:
            os.close(directory_fd)

        target_close_attempts = 0

        def failing_close(file_descriptor: int) -> None:
            nonlocal target_close_attempts, failed_fd
            if target_inode is not None:
                try:
                    is_target = os.fstat(file_descriptor).st_ino == target_inode
                except OSError:
                    is_target = False
                if is_target:
                    target_close_attempts += 1
                    if target_close_attempts == 1:
                        failed_fd = file_descriptor
                        raise OSError("fixture/sensitive-marker")
            original_close(file_descriptor)

        def target_close_probe(*args: object, **kwargs: object) -> bytes:
            monkeypatch.setattr(read_session_module.os, "close", failing_close)
            try:
                return original_read_snapshot_file(*args, **kwargs)  # type: ignore[arg-type]
            finally:
                # The session's deferred-close recovery uses the real close.
                monkeypatch.setattr(read_session_module.os, "close", original_close)

        monkeypatch.setattr(read_session_module, "read_snapshot_file", target_close_probe)
        try:
            return session.read_bytes("a.txt")  # type: ignore[attr-defined]
        finally:
            monkeypatch.setattr(read_session_module, "read_snapshot_file", original_read_snapshot_file)

    try:
        with pytest.raises(IngestionSecurityError) as captured:
            service.ingest_with_consumer(_zip([("a.txt", b"alpha")]), consumer)
    finally:
        service.close()
    assert str(captured.value) == "scanner_failed:scan_file_read_failed"
    assert failed_fd is not None
    with pytest.raises(OSError) as fd_error:
        os.fstat(failed_fd)
    assert fd_error.value.errno == errno.EBADF
    assert list(root.iterdir()) == []


def test_open_oserror_is_mapped_to_stable_read_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, root = _service(tmp_path)
    original_open = read_session_module.os.open
    target_opens = 0

    def failing_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        nonlocal target_opens
        if path == "a.txt" and kwargs.get("dir_fd") is not None:
            target_opens += 1
            if target_opens == 2:
                raise OSError("fixture/path/marker body")
        return original_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

    def consumer(session: object) -> bytes:
        monkeypatch.setattr(read_session_module.os, "open", failing_open)
        try:
            return session.read_bytes("a.txt")  # type: ignore[attr-defined]
        finally:
            monkeypatch.setattr(read_session_module.os, "open", original_open)

    try:
        with pytest.raises(IngestionSecurityError) as captured:
            service.ingest_with_consumer(_zip([("a.txt", b"alpha")]), consumer)
    finally:
        service.close()
    assert str(captured.value) == "scanner_failed:scan_file_read_failed"
    assert "fixture/path/marker" not in str(captured.value)
    assert list(root.iterdir()) == []


def test_close_oserror_is_not_silently_discarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, root = _service(tmp_path)
    original_close = read_session_module.os.close
    target_inode: int | None = None
    target_closes = 0

    def failing_close(file_descriptor: int) -> None:
        nonlocal target_closes
        if target_inode is not None:
            try:
                if os.fstat(file_descriptor).st_ino == target_inode:
                    target_closes += 1
                    if target_closes == 2:
                        raise OSError("fixture/path/marker body")
            except OSError:
                if target_closes == 2:
                    raise
        original_close(file_descriptor)

    def consumer(session: object) -> bytes:
        nonlocal target_inode
        directory_fd = _tree_fd(session)
        try:
            target_inode = os.stat("a.txt", dir_fd=directory_fd, follow_symlinks=False).st_ino
        finally:
            os.close(directory_fd)
        monkeypatch.setattr(read_session_module.os, "close", failing_close)
        try:
            return session.read_bytes("a.txt")  # type: ignore[attr-defined]
        finally:
            monkeypatch.setattr(read_session_module.os, "close", original_close)

    try:
        with pytest.raises(IngestionSecurityError) as captured:
            service.ingest_with_consumer(_zip([("a.txt", b"alpha")]), consumer)
    finally:
        service.close()
    assert str(captured.value) == "scanner_failed:scan_file_read_failed"
    assert "fixture/path/marker" not in str(captured.value)
    assert list(root.iterdir()) == []


def test_cleanup_failure_is_reported_after_successful_consumer_and_cleanup_wins_over_integrity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_cleanup = zip_stream_module.SecureWorkspace.cleanup

    def cleanup_then_fail(workspace: object, retries: int) -> None:
        original_cleanup(workspace, retries)  # type: ignore[arg-type]
        raise IngestionSecurityError("scanner_failed", "workspace_cleanup_failed")

    monkeypatch.setattr(zip_stream_module.SecureWorkspace, "cleanup", cleanup_then_fail)
    for index, mutate in enumerate([False, True]):
        service, root = _service(tmp_path / f"case-{index}")

        def consumer(session: object, mutate=mutate) -> bytes:
            if mutate:
                _rewrite_same_inode(session, "unread.txt", b"bravo")
            return session.read_bytes("read.txt")  # type: ignore[attr-defined]

        try:
            with pytest.raises(IngestionSecurityError) as captured:
                service.ingest_with_consumer(
                    _zip([("read.txt", b"alpha"), ("unread.txt", b"alpha")]),
                    consumer,
                )
        finally:
            service.close()
        assert str(captured.value) == "scanner_failed:workspace_cleanup_failed"
        assert list(root.iterdir()) == []


def test_bad_zip_mapping_matches_ingest_and_never_calls_consumer(tmp_path: Path) -> None:
    service, root = _service(tmp_path)
    calls = 0

    def consumer(_: object) -> None:
        nonlocal calls
        calls += 1

    try:
        with pytest.raises(IngestionSecurityError) as legacy_error:
            service.ingest(io.BytesIO(b"not a zip"))
        with pytest.raises(IngestionSecurityError) as session_error:
            service.ingest_with_consumer(io.BytesIO(b"not a zip"), consumer)
    finally:
        service.close()
    assert (legacy_error.value.code, legacy_error.value.reason) == (
        "invalid_archive",
        "archive_not_zip",
    )
    assert (session_error.value.code, session_error.value.reason) == (
        legacy_error.value.code,
        legacy_error.value.reason,
    )
    assert calls == 0
    assert list(root.iterdir()) == []


def test_base_exception_is_reraised_after_cleanup(tmp_path: Path) -> None:
    class FixtureBaseFailure(BaseException):
        pass

    failure = FixtureBaseFailure("fixture/path/marker")
    service, root = _service(tmp_path)
    try:
        with pytest.raises(FixtureBaseFailure) as captured:
            service.ingest_with_consumer(
                _zip([("a.txt", b"alpha")]),
                lambda _: (_ for _ in ()).throw(failure),
            )
    finally:
        service.close()
    assert captured.value is failure
    assert list(root.iterdir()) == []


def test_public_session_surface_is_read_only_and_has_no_path_or_descriptor_capability() -> None:
    public_names = {name for name in dir(ReadOnlyScanSession) if not name.startswith("_")}
    forbidden_fragments = ("path", "fd", "open", "write", "stream", "fileno")
    assert all(not any(fragment in name.lower() for fragment in forbidden_fragments) for name in public_names)
    assert public_names == {"inventory", "read_bytes"}
