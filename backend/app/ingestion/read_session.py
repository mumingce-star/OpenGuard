"""Lifecycle-bound, descriptor-relative read capability for trusted parsers."""

from __future__ import annotations

import hashlib
import errno
import os
import stat
import threading
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from app.ingestion.inventory import (
    Inventory,
    _DirectorySeal,
    _FileSeal,
    _InventorySnapshot,
    build_inventory_snapshot,
)
from app.security.archive_path import normalize_member_path
from app.security.errors import IngestionSecurityError
from app.security.limits import ZipSafetyLimits
from app.security.secure_dir import SecureWorkspace


T = TypeVar("T")
_CHUNK_SIZE = 64 * 1024
_OPEN_DIRECTORY = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_OPEN_FILE = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)


@dataclass(frozen=True)
class ScanReadLimits:
    single_file_max_bytes: int | None = None
    total_max_bytes: int | None = None


@dataclass(frozen=True)
class ScanSessionResult(Generic[T]):
    inventory: Inventory
    consumer_result: T


def effective_limits(limits: ScanReadLimits | None, *, single: int, total: int) -> tuple[int, int]:
    """Resolve request-scoped limits without permitting a server limit increase."""

    requested = limits or ScanReadLimits()
    values = (requested.single_file_max_bytes, requested.total_max_bytes)
    if any(value is not None and (type(value) is not int or value <= 0) for value in values):
        raise IngestionSecurityError("scanner_failed", "scan_read_limit_invalid")
    resolved_single = single if values[0] is None else values[0]
    resolved_total = total if values[1] is None else values[1]
    if resolved_single > single or resolved_total > total or resolved_total < resolved_single:
        raise IngestionSecurityError("scanner_failed", "scan_read_limit_invalid")
    return resolved_single, resolved_total


def validate_inventory_snapshot(workspace: SecureWorkspace, expected: _InventorySnapshot) -> None:
    """Fail closed when any sealed directory, file identity, size, or byte changes."""

    try:
        current = build_inventory_snapshot(workspace)
    except IngestionSecurityError as error:
        raise IngestionSecurityError("scanner_failed", "scan_file_integrity_failed") from error
    if current != expected:
        raise IngestionSecurityError("scanner_failed", "scan_file_integrity_failed")


def _directory_matches(status: os.stat_result, seal: _DirectorySeal) -> bool:
    return (
        stat.S_ISDIR(status.st_mode)
        and stat.S_IFMT(status.st_mode) == seal.mode_type
        and status.st_dev == seal.dev
        and status.st_ino == seal.ino
    )


def _file_matches(status: os.stat_result, seal: _FileSeal) -> bool:
    return (
        stat.S_ISREG(status.st_mode)
        and stat.S_IFMT(status.st_mode) == seal.mode_type
        and status.st_dev == seal.dev
        and status.st_ino == seal.ino
        and status.st_size == seal.size
    )


def _integrity_error() -> IngestionSecurityError:
    return IngestionSecurityError("scanner_failed", "scan_file_integrity_failed")


@dataclass(frozen=True)
class _DeferredDescriptor:
    file_descriptor: int
    mode_type: int
    dev: int
    ino: int
    size: int | None


class _DeferredCloseError(IngestionSecurityError):
    """Retain ownership when close reports an ambiguous failure."""

    def __init__(self, descriptors: tuple[_DeferredDescriptor, ...]):
        super().__init__("scanner_failed", "scan_file_read_failed")
        self.descriptors = descriptors


def _deferred_file(file_descriptor: int, seal: _FileSeal) -> _DeferredDescriptor:
    return _DeferredDescriptor(file_descriptor, seal.mode_type, seal.dev, seal.ino, seal.size)


def _deferred_directory(file_descriptor: int, seal: _DirectorySeal) -> _DeferredDescriptor:
    return _DeferredDescriptor(file_descriptor, seal.mode_type, seal.dev, seal.ino, None)


def _deferred_matches(status: os.stat_result, descriptor: _DeferredDescriptor) -> bool:
    return (
        stat.S_IFMT(status.st_mode) == descriptor.mode_type
        and status.st_dev == descriptor.dev
        and status.st_ino == descriptor.ino
        and (descriptor.size is None or status.st_size == descriptor.size)
    )


def _resolve_file_seal(
    snapshot: _InventorySnapshot,
    relative_path: str,
    limits: ZipSafetyLimits,
) -> _FileSeal:
    if type(relative_path) is not str:
        raise IngestionSecurityError("scanner_failed", "scan_path_not_in_inventory")
    try:
        normalized = normalize_member_path(relative_path, is_directory=False, limits=limits)
    except IngestionSecurityError as error:
        raise IngestionSecurityError("scanner_failed", "scan_path_not_in_inventory") from error
    if normalized.relative_path != relative_path:
        raise IngestionSecurityError("scanner_failed", "scan_path_not_in_inventory")
    for seal in snapshot.file_seals:
        if seal.parts == normalized.parts:
            return seal
    raise IngestionSecurityError("scanner_failed", "scan_path_not_in_inventory")


def read_snapshot_file(
    workspace: SecureWorkspace,
    snapshot: _InventorySnapshot,
    relative_path: str,
    limits: ZipSafetyLimits,
) -> bytes:
    """Read one sealed file without resolving an attacker-controlled host path."""

    file_seal = _resolve_file_seal(snapshot, relative_path, limits)
    directory_index = {seal.parts: seal for seal in snapshot.directory_seals}
    root_seal = directory_index.get(())
    if root_seal is None:
        raise _integrity_error()

    directory_fd: int | None = None
    directory_fds: list[tuple[int, _DirectorySeal]] = []
    file_fd: int | None = None
    try:
        try:
            try:
                directory_fd = workspace.open_directory(("tree",))
            except IngestionSecurityError as error:
                # Session pre-validation already observed the sealed tree. A
                # transient descriptor-open failure is an I/O failure; a real
                # replacement remains caught by final full-tree validation.
                raise IngestionSecurityError("scanner_failed", "scan_file_read_failed") from error
            if not _directory_matches(os.fstat(directory_fd), root_seal):
                raise _integrity_error()
            directory_fds.append((directory_fd, root_seal))
            prefix: tuple[str, ...] = ()
            for part in file_seal.parts[:-1]:
                prefix = (*prefix, part)
                expected_directory = directory_index.get(prefix)
                if expected_directory is None:
                    raise _integrity_error()
                before = os.stat(part, dir_fd=directory_fd, follow_symlinks=False)
                if not _directory_matches(before, expected_directory):
                    raise _integrity_error()
                child_fd = os.open(part, _OPEN_DIRECTORY, dir_fd=directory_fd)
                directory_fds.append((child_fd, expected_directory))
                opened = os.fstat(child_fd)
                if not _directory_matches(opened, expected_directory):
                    raise _integrity_error()
                directory_fd = child_fd

            filename = file_seal.parts[-1]
            before_file = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
            if not _file_matches(before_file, file_seal):
                raise _integrity_error()
            file_fd = os.open(filename, _OPEN_FILE, dir_fd=directory_fd)
            opened_file = os.fstat(file_fd)
            if not _file_matches(opened_file, file_seal):
                raise _integrity_error()
        except IngestionSecurityError:
            raise
        except OSError as error:
            raise IngestionSecurityError("scanner_failed", "scan_file_read_failed") from error

        digest = hashlib.sha256()
        data = bytearray()
        try:
            while len(data) <= file_seal.size:
                chunk = os.read(file_fd, min(_CHUNK_SIZE, file_seal.size + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                digest.update(chunk)
            after_file = os.fstat(file_fd)
        except OSError as error:
            raise IngestionSecurityError("scanner_failed", "scan_file_read_failed") from error

        if (
            not _file_matches(after_file, file_seal)
            or len(data) != file_seal.size
            or digest.hexdigest() != file_seal.sha256
        ):
            raise _integrity_error()
        return bytes(data)
    finally:
        deferred: list[_DeferredDescriptor] = []
        if file_fd is not None:
            try:
                os.close(file_fd)
            except OSError:
                # Do not blindly retry close: POSIX may have closed and reused
                # the number. Transfer the uncertain ownership to the session,
                # which re-checks identity after the callback before cleanup.
                deferred.append(_deferred_file(file_fd, file_seal))
        for opened_directory_fd, directory_seal in reversed(directory_fds):
            try:
                os.close(opened_directory_fd)
            except OSError:
                deferred.append(_deferred_directory(opened_directory_fd, directory_seal))
        if deferred:
            raise _DeferredCloseError(tuple(deferred))


class ReadOnlyScanSession:
    """Narrow capability; this is not a sandbox for untrusted Python callbacks."""

    __slots__ = (
        "_active",
        "_failure",
        "_failure_lock",
        "_deferred_closes",
        "_inventory",
        "_limits",
        "_owner",
        "_reading",
        "_single",
        "_snapshot",
        "_total",
        "_used",
        "_validate",
        "_workspace",
    )

    def __init__(
        self,
        snapshot: _InventorySnapshot,
        workspace: SecureWorkspace,
        limits: ZipSafetyLimits,
        single: int,
        total: int,
        validate: Callable[[], None],
    ):
        self._inventory = snapshot.inventory
        self._snapshot = snapshot
        self._workspace = workspace
        self._limits = limits
        self._single = single
        self._total = total
        self._used = 0
        self._owner = threading.get_ident()
        self._active = True
        self._reading = False
        self._failure: IngestionSecurityError | None = None
        self._failure_lock = threading.Lock()
        self._deferred_closes: list[_DeferredDescriptor] = []
        self._validate = validate

    @property
    def inventory(self) -> Inventory:
        if not self._active:
            raise IngestionSecurityError("scanner_failed", "scan_session_expired")
        return self._inventory

    @property
    def _get_internal_failure(self) -> IngestionSecurityError | None:
        return self._failure

    def _expire(self) -> None:
        self._active = False

    def _recover_deferred_closes(self) -> None:
        """Close only descriptors that still match the ownership seal."""

        pending, self._deferred_closes = self._deferred_closes, []
        for deferred in pending:
            try:
                status = os.fstat(deferred.file_descriptor)
            except OSError as error:
                if error.errno == errno.EBADF:
                    continue
                raise IngestionSecurityError("scanner_failed", "scan_file_read_failed") from error
            if not _deferred_matches(status, deferred):
                raise IngestionSecurityError("scanner_failed", "scan_file_read_failed")
            try:
                os.close(deferred.file_descriptor)
            except OSError as error:
                raise IngestionSecurityError("scanner_failed", "scan_file_read_failed") from error

    def _fail(self, reason: str) -> None:
        with self._failure_lock:
            if self._failure is None:
                self._failure = IngestionSecurityError("scanner_failed", reason)
            error = self._failure
        raise error

    def _run_validation(self) -> None:
        try:
            self._validate()
        except IngestionSecurityError as error:
            self._fail(error.reason)

    def read_bytes(self, relative_path: str, *, max_bytes: int | None = None) -> bytes:
        if not self._active:
            raise IngestionSecurityError("scanner_failed", "scan_session_expired")
        if threading.get_ident() != self._owner:
            self._fail("scan_session_thread_violation")
        if self._reading:
            self._fail("scan_session_reentrant")
        if max_bytes is not None and (type(max_bytes) is not int or max_bytes <= 0 or max_bytes > self._single):
            self._fail("scan_read_limit_invalid")

        try:
            file_seal = _resolve_file_seal(self._snapshot, relative_path, self._limits)
        except IngestionSecurityError:
            self._fail("scan_path_not_in_inventory")
        allowed = self._single if max_bytes is None else max_bytes
        if file_seal.size > allowed or self._used + file_seal.size > self._total:
            self._fail("scan_read_limit_exceeded")

        # Reserve before opening; a failed retry never restores quota.
        self._used += file_seal.size
        self._reading = True
        try:
            self._run_validation()
            try:
                data = read_snapshot_file(self._workspace, self._snapshot, relative_path, self._limits)
            except _DeferredCloseError as error:
                self._deferred_closes.extend(error.descriptors)
                self._fail(error.reason)
            except IngestionSecurityError as error:
                self._fail(error.reason)
            self._run_validation()
            return data
        finally:
            self._reading = False
