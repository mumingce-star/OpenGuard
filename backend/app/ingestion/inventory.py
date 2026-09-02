"""Descriptor-safe inventory construction and the frozen v1 root digest."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass

from app.security.errors import IngestionSecurityError
from app.security.secure_dir import SecureWorkspace


_CHUNK_SIZE = 64 * 1024
_ROOT_DIGEST_HEADER = b"openguard-inventory-v1\n"


@dataclass(frozen=True)
class InventoryEntry:
    relative_path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class Inventory:
    entries: tuple[InventoryEntry, ...]
    root_digest: str


@dataclass(frozen=True)
class _DirectorySeal:
    parts: tuple[str, ...]
    mode_type: int
    dev: int
    ino: int


@dataclass(frozen=True)
class _FileSeal:
    parts: tuple[str, ...]
    mode_type: int
    dev: int
    ino: int
    size: int
    sha256: str


@dataclass(frozen=True)
class _InventorySnapshot:
    inventory: Inventory
    directory_seals: tuple[_DirectorySeal, ...]
    file_seals: tuple[_FileSeal, ...]


def root_digest_v1(entries: tuple[InventoryEntry, ...]) -> str:
    digest = hashlib.sha256()
    digest.update(_ROOT_DIGEST_HEADER)
    for entry in sorted(entries, key=lambda value: value.relative_path.encode("utf-8")):
        digest.update(entry.relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(entry.size_bytes).encode("ascii"))
        digest.update(b"\0")
        digest.update(entry.sha256.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def build_inventory(workspace: SecureWorkspace, root_parts: tuple[str, ...] = ("tree",)) -> Inventory:
    """Hash only regular files while holding each parent open by descriptor."""

    return build_inventory_snapshot(workspace, root_parts).inventory


def build_inventory_snapshot(
    workspace: SecureWorkspace,
    root_parts: tuple[str, ...] = ("tree",),
) -> _InventorySnapshot:
    """Seal descriptor-observed directory/file identities beside the v1 inventory."""

    root_fd = workspace.open_directory(root_parts)
    entries: list[InventoryEntry] = []
    directories: list[_DirectorySeal] = []
    files: list[_FileSeal] = []
    try:
        _walk_sealed(root_fd, (), entries, directories, files)
    finally:
        os.close(root_fd)

    stable_entries = tuple(sorted(entries, key=lambda value: value.relative_path.encode("utf-8")))
    return _InventorySnapshot(
        inventory=Inventory(stable_entries, root_digest_v1(stable_entries)),
        directory_seals=tuple(sorted(directories, key=lambda value: value.parts)),
        file_seals=tuple(sorted(files, key=lambda value: value.parts)),
    )


def _walk_sealed(
    directory_fd: int,
    prefix: tuple[str, ...],
    entries: list[InventoryEntry],
    directories: list[_DirectorySeal],
    files: list[_FileSeal],
) -> None:
    try:
        directory_status = os.fstat(directory_fd)
        if not stat.S_ISDIR(directory_status.st_mode):
            raise IngestionSecurityError("scanner_failed", "workspace_integrity_failed")
        directories.append(
            _DirectorySeal(
                parts=prefix,
                mode_type=stat.S_IFMT(directory_status.st_mode),
                dev=directory_status.st_dev,
                ino=directory_status.st_ino,
            )
        )

        for name in sorted(os.listdir(directory_fd), key=lambda value: value.encode("utf-8")):
            before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISDIR(before.st_mode):
                child_fd = os.open(
                    name,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_fd,
                )
                try:
                    opened = os.fstat(child_fd)
                    if not _same_identity(before, opened):
                        raise IngestionSecurityError("scanner_failed", "workspace_integrity_failed")
                    _walk_sealed(child_fd, (*prefix, name), entries, directories, files)
                finally:
                    os.close(child_fd)
                continue

            if not stat.S_ISREG(before.st_mode):
                raise IngestionSecurityError("scanner_failed", "workspace_integrity_failed")
            file_fd = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
                dir_fd=directory_fd,
            )
            try:
                opened = os.fstat(file_fd)
                if not stat.S_ISREG(opened.st_mode) or not _same_file(before, opened):
                    raise IngestionSecurityError("scanner_failed", "workspace_integrity_failed")
                digest = hashlib.sha256()
                size_bytes = 0
                while chunk := os.read(file_fd, _CHUNK_SIZE):
                    digest.update(chunk)
                    size_bytes += len(chunk)
                after = os.fstat(file_fd)
                if size_bytes != before.st_size or not _same_file(opened, after):
                    raise IngestionSecurityError("scanner_failed", "workspace_integrity_failed")
                parts = (*prefix, name)
                sha256 = digest.hexdigest()
                entries.append(InventoryEntry("/".join(parts), size_bytes, sha256))
                files.append(
                    _FileSeal(
                        parts=parts,
                        mode_type=stat.S_IFMT(after.st_mode),
                        dev=after.st_dev,
                        ino=after.st_ino,
                        size=size_bytes,
                        sha256=sha256,
                    )
                )
            finally:
                os.close(file_fd)
    except IngestionSecurityError:
        raise
    except OSError as error:
        raise IngestionSecurityError("scanner_failed", "workspace_integrity_failed") from error


def _walk(directory_fd: int, prefix: tuple[str, ...], entries: list[InventoryEntry]) -> None:
    try:
        names = sorted(os.listdir(directory_fd), key=lambda value: value.encode("utf-8"))
        for name in names:
            before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISDIR(before.st_mode):
                child_fd = os.open(
                    name,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_fd,
                )
                try:
                    _walk(child_fd, (*prefix, name), entries)
                finally:
                    os.close(child_fd)
                continue
            if not stat.S_ISREG(before.st_mode):
                raise IngestionSecurityError("scanner_failed", "workspace_integrity_failed")
            file_descriptor = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
            try:
                opened = os.fstat(file_descriptor)
                if not stat.S_ISREG(opened.st_mode) or not _same_file(before, opened):
                    raise IngestionSecurityError("scanner_failed", "workspace_integrity_failed")
                file_digest = hashlib.sha256()
                size_bytes = 0
                while chunk := os.read(file_descriptor, _CHUNK_SIZE):
                    file_digest.update(chunk)
                    size_bytes += len(chunk)
                after = os.fstat(file_descriptor)
                if size_bytes != before.st_size or not _same_file(opened, after):
                    raise IngestionSecurityError("scanner_failed", "workspace_integrity_failed")
                entries.append(
                    InventoryEntry(
                        relative_path="/".join((*prefix, name)),
                        size_bytes=size_bytes,
                        sha256=file_digest.hexdigest(),
                    )
                )
            finally:
                os.close(file_descriptor)
    except IngestionSecurityError:
        raise
    except OSError as error:
        raise IngestionSecurityError("scanner_failed", "workspace_integrity_failed") from error


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        stat.S_IFMT(left.st_mode) == stat.S_IFMT(right.st_mode)
        and left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_size == right.st_size
    )


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        stat.S_IFMT(left.st_mode) == stat.S_IFMT(right.st_mode)
        and left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
    )
