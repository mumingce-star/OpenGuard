"""The A2-1 local ZIP ingestion vertical slice."""

from __future__ import annotations

import os
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable, TypeVar

from app.ingestion.inventory import Inventory, build_inventory, build_inventory_snapshot
from app.ingestion.read_session import (
    ReadOnlyScanSession,
    ScanReadLimits,
    ScanSessionResult,
    effective_limits,
    validate_inventory_snapshot,
)
from app.ingestion.workspace import WorkspaceManager
from app.ingestion.zip_preflight import VerifiedZipMember, preflight_zip
from app.security.errors import IngestionSecurityError
from app.security.limits import ZipExtractionBudget, ZipSafetyLimits
from app.security.secure_dir import SecureWorkspace


_CHUNK_SIZE = 64 * 1024
_ARCHIVE_PARTS = ("input.zip",)
_TREE_PARTS = ("tree",)
T = TypeVar("T")


@dataclass
class TrustedTreeScan:
    """Short-lived descriptor target for a code-owned external scanner."""

    _directory_fd: int
    _active: bool = True

    def proc_target(self) -> str:
        if not self._active or os.name != "posix":
            raise IngestionSecurityError("scanner_failed", "external_scanner_unavailable")
        return f"/proc/self/fd/{self._directory_fd}"

    @property
    def inherited_fds(self) -> tuple[int, ...]:
        if not self._active:
            raise IngestionSecurityError("scanner_failed", "external_scanner_unavailable")
        return (self._directory_fd,)

    def close(self) -> None:
        if self._active:
            self._active = False
            try:
                os.close(self._directory_fd)
            except OSError as error:
                raise IngestionSecurityError("scanner_failed", "scan_file_read_failed") from error


class ZipIngestionService:
    """A server-configured local ZIP boundary with no request-settable limits.

    ``ingest`` returns only an in-memory inventory after cleanup.
    ``ingest_with_consumer`` grants one trusted synchronous parser a bounded,
    lifecycle-bound read capability, then expires it and removes the workspace
    before returning. Neither entry point publishes a materialized tree.
    """

    def __init__(self, workspace_root: str | Path, limits: ZipSafetyLimits | None = None):
        self.limits = limits or ZipSafetyLimits()
        self._workspaces = WorkspaceManager(workspace_root, self.limits)
        self._consumer_local = threading.local()
        self._state_lock = threading.Lock()
        self._poisoned = False

    def close(self) -> None:
        self._workspaces.close()

    def _ensure_usable(self) -> None:
        with self._state_lock:
            if self._poisoned:
                raise IngestionSecurityError("scanner_failed", "workspace_cleanup_failed")

    def _poison(self) -> None:
        with self._state_lock:
            self._poisoned = True

    def ingest(self, archive_stream: BinaryIO) -> Inventory:
        self._ensure_usable()
        workspace = self._workspaces.create()
        result: Inventory | None = None
        try:
            _materialize_archive(workspace, archive_stream, self.limits)
            result = build_inventory(workspace, _TREE_PARTS)
        finally:
            # Cleanup errors intentionally replace an earlier archive error: a
            # worker with retained untrusted bytes must fail closed and must not
            # be reported as a successfully handled rejection.
            self._workspaces.cleanup(workspace)
        if result is None:
            raise IngestionSecurityError("scanner_failed", "workspace_integrity_failed")
        return result

    def ingest_with_consumer(
        self,
        archive_stream: BinaryIO,
        consumer: Callable[[ReadOnlyScanSession], T],
        *,
        read_limits: ScanReadLimits | None = None,
    ) -> ScanSessionResult[T]:
        """Run one trusted synchronous consumer before the task tree is removed."""
        if getattr(self._consumer_local, "active", False):
            error = IngestionSecurityError("scanner_failed", "scan_session_reentrant")
            self._consumer_local.reentry_failure = error
            raise error
        self._ensure_usable()
        single, total = effective_limits(
            read_limits,
            single=self.limits.effective_scan_single_file_read_max_bytes,
            total=self.limits.scan_total_read_max_bytes,
        )
        workspace = self._workspaces.create()
        session: ReadOnlyScanSession | None = None
        result: T | None = None
        primary: BaseException | None = None
        final_integrity: IngestionSecurityError | None = None
        reentry_failure: IngestionSecurityError | None = None
        recovery_failure: IngestionSecurityError | None = None
        inventory: Inventory | None = None
        try:
            _materialize_archive(workspace, archive_stream, self.limits)
            snapshot = build_inventory_snapshot(workspace, _TREE_PARTS)
            inventory = snapshot.inventory

            def validate() -> None:
                validate_inventory_snapshot(workspace, snapshot)

            validate()
            session = ReadOnlyScanSession(snapshot, workspace, self.limits, single, total, validate)
            self._consumer_local.active = True
            try:
                result = consumer(session)
            except BaseException as error:
                primary = error
            finally:
                self._consumer_local.active = False
                reentry_failure = getattr(self._consumer_local, "reentry_failure", None)
                if hasattr(self._consumer_local, "reentry_failure"):
                    del self._consumer_local.reentry_failure
                session._expire()
            try:
                session._recover_deferred_closes()
            except IngestionSecurityError as error:
                self._poison()
                recovery_failure = error
            try:
                validate()
            except IngestionSecurityError as error:
                final_integrity = error
            if final_integrity is not None:
                raise final_integrity
            if recovery_failure is not None:
                raise recovery_failure
            if reentry_failure is not None:
                raise reentry_failure
            if session._get_internal_failure is not None:
                raise session._get_internal_failure
            if primary is not None:
                if isinstance(primary, Exception):
                    raise IngestionSecurityError("scanner_failed", "scan_consumer_failed")
                raise primary
            return ScanSessionResult(inventory=inventory, consumer_result=result)  # type: ignore[arg-type]
        finally:
            if session is not None:
                session._expire()
            self._workspaces.cleanup(workspace)


    def ingest_with_tree_consumer(
        self, archive_stream: BinaryIO, consumer: Callable[[TrustedTreeScan, Inventory], T]
    ) -> ScanSessionResult[T]:
        """Run one code-owned external scanner over the sealed tree.

        The callback receives a descriptor-backed `/proc/self/fd` target, never
        an attacker-controlled host path. Inventory seals are checked before
        and after the scanner; mutations fail closed before workspace cleanup.
        """
        if getattr(self._consumer_local, "active", False):
            raise IngestionSecurityError("scanner_failed", "scan_session_reentrant")
        self._ensure_usable()
        workspace = self._workspaces.create()
        tree: TrustedTreeScan | None = None
        try:
            _materialize_archive(workspace, archive_stream, self.limits)
            snapshot = build_inventory_snapshot(workspace, _TREE_PARTS)
            validate_inventory_snapshot(workspace, snapshot)
            tree = TrustedTreeScan(workspace.open_directory(_TREE_PARTS))
            self._consumer_local.active = True
            try:
                result = consumer(tree, snapshot.inventory)
            except IngestionSecurityError:
                raise
            except Exception as error:
                raise IngestionSecurityError("scanner_failed", "external_scanner_failed") from error
            finally:
                self._consumer_local.active = False
                tree.close()
                tree = None
            validate_inventory_snapshot(workspace, snapshot)
            return ScanSessionResult(inventory=snapshot.inventory, consumer_result=result)
        finally:
            if tree is not None:
                tree.close()
            self._workspaces.cleanup(workspace)


def _materialize_archive(
    workspace: SecureWorkspace,
    archive_stream: BinaryIO,
    limits: ZipSafetyLimits,
) -> None:
    """Receive and extract a ZIP with one stable error mapping for both APIs."""

    upload_size = _receive_archive(workspace, archive_stream, limits)
    with workspace.open_existing_file(_ARCHIVE_PARTS) as archive_file:
        try:
            archive = zipfile.ZipFile(archive_file, mode="r")
        except (OSError, EOFError, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
            raise IngestionSecurityError("invalid_archive", "archive_not_zip") from error
        try:
            with archive:
                members = preflight_zip(archive, limits)
                _stream_verified_members(archive, members, workspace, limits, upload_size)
        except IngestionSecurityError:
            raise
        except (OSError, EOFError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
            raise IngestionSecurityError("invalid_archive", "archive_integrity_failed") from error


def _receive_archive(workspace: SecureWorkspace, stream: BinaryIO, limits: ZipSafetyLimits) -> int:
    received = 0

    def write(file_descriptor: int) -> None:
        nonlocal received
        while True:
            chunk = stream.read(_CHUNK_SIZE)
            if not chunk:
                return
            if not isinstance(chunk, bytes):
                raise IngestionSecurityError("invalid_archive", "archive_stream_invalid")
            received += len(chunk)
            if received > limits.upload_max_bytes:
                raise IngestionSecurityError("archive_limit_exceeded", "archive_upload_size_limit")
            _write_all(file_descriptor, chunk)

    try:
        workspace.write_new_file(_ARCHIVE_PARTS, write)
    except IngestionSecurityError:
        raise
    except (AttributeError, OSError) as error:
        raise IngestionSecurityError("invalid_archive", "archive_stream_invalid") from error
    return received


def _stream_verified_members(
    archive: zipfile.ZipFile,
    members: tuple[VerifiedZipMember, ...],
    workspace: SecureWorkspace,
    limits: ZipSafetyLimits,
    upload_size: int,
) -> None:
    budget = ZipExtractionBudget(limits=limits, upload_size_bytes=upload_size)
    for member in members:
        destination = (*_TREE_PARTS, *member.path.parts)
        if member.path.is_directory:
            workspace.make_directory(destination)
            continue
        _stream_member(archive, member, workspace, destination, budget)


def _stream_member(
    archive: zipfile.ZipFile,
    member: VerifiedZipMember,
    workspace: SecureWorkspace,
    destination: tuple[str, ...],
    budget: ZipExtractionBudget,
) -> None:
    file_budget = budget.begin_file(member.info.compress_size)

    def write(file_descriptor: int) -> None:
        try:
            with archive.open(member.info, mode="r") as source:
                while True:
                    chunk = source.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    file_budget.add(len(chunk))
                    _write_all(file_descriptor, chunk)
        except IngestionSecurityError:
            raise
        except (EOFError, OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
            raise IngestionSecurityError("invalid_archive", "archive_integrity_failed") from error
        # ZipExtFile validates CRC at EOF; inventory hashes the staged tree via
        # independent descriptor-relative reads before any result is returned.

    workspace.write_new_file(destination, write)


def _write_all(file_descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(file_descriptor, view)
        if written <= 0:
            raise OSError("short write")
        view = view[written:]
