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

    root_fd = workspace.open_directory(root_parts)
    entries: list[InventoryEntry] = []
    try:
        _walk(root_fd, (), entries)
    finally:
        os.close(root_fd)
    stable_entries = tuple(sorted(entries, key=lambda value: value.relative_path.encode("utf-8")))
    return Inventory(entries=stable_entries, root_digest=root_digest_v1(stable_entries))


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
