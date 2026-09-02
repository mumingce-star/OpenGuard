"""The A2-1 local ZIP ingestion vertical slice."""

from __future__ import annotations

import os
import zipfile
from pathlib import Path
from typing import BinaryIO

from app.ingestion.inventory import Inventory, build_inventory
from app.ingestion.workspace import WorkspaceManager
from app.ingestion.zip_preflight import VerifiedZipMember, preflight_zip
from app.security.errors import IngestionSecurityError
from app.security.limits import ZipExtractionBudget, ZipSafetyLimits
from app.security.secure_dir import SecureWorkspace


_CHUNK_SIZE = 64 * 1024
_ARCHIVE_PARTS = ("input.zip",)
_TREE_PARTS = ("tree",)


class ZipIngestionService:
    """A server-configured local ZIP boundary with no request-settable limits.

    This service intentionally returns only an in-memory inventory.  The
    workspace is deleted before the result is returned, so this initial vertical
    slice cannot accidentally publish a partially materialized tree.  A future
    task supervisor may retain the same descriptor-safe tree until its final
    read-only consumer completes.
    """

    def __init__(self, workspace_root: str | Path, limits: ZipSafetyLimits | None = None):
        self.limits = limits or ZipSafetyLimits()
        self._workspaces = WorkspaceManager(workspace_root, self.limits)

    def close(self) -> None:
        self._workspaces.close()

    def ingest(self, archive_stream: BinaryIO) -> Inventory:
        workspace = self._workspaces.create()
        result: Inventory | None = None
        try:
            upload_size = _receive_archive(workspace, archive_stream, self.limits)
            with workspace.open_existing_file(_ARCHIVE_PARTS) as archive_file:
                try:
                    archive = zipfile.ZipFile(archive_file, mode="r")
                except (OSError, EOFError, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
                    raise IngestionSecurityError("invalid_archive", "archive_not_zip") from error
                try:
                    with archive:
                        members = preflight_zip(archive, self.limits)
                        _stream_verified_members(archive, members, workspace, self.limits, upload_size)
                except IngestionSecurityError:
                    raise
                except (OSError, EOFError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
                    raise IngestionSecurityError("invalid_archive", "archive_integrity_failed") from error
            result = build_inventory(workspace, _TREE_PARTS)
        finally:
            # Cleanup errors intentionally replace an earlier archive error: a
            # worker with retained untrusted bytes must fail closed and must not
            # be reported as a successfully handled rejection.
            self._workspaces.cleanup(workspace)
        if result is None:
            raise IngestionSecurityError("scanner_failed", "workspace_integrity_failed")
        return result


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
