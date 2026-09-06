"""Descriptor-relative workspace creation, writing, and cleanup for POSIX."""

from __future__ import annotations

import errno
import os
import secrets
import stat
import re
from pathlib import Path
from typing import BinaryIO, Callable

from .errors import IngestionSecurityError


_OPEN_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
_OPEN_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_TRUSTED_PROCESS_PART = re.compile(r"^[A-Za-z0-9._-]+$")


def _capability_error() -> IngestionSecurityError:
    return IngestionSecurityError("scanner_failed", "posix_security_capability_unavailable")


def _close_quietly(file_descriptor: int | None) -> None:
    if file_descriptor is not None:
        try:
            os.close(file_descriptor)
        except OSError:
            pass


class SecureRoot:
    """A pre-existing server-controlled root held open by descriptor.

    The root is deliberately required to exist.  Creating arbitrary nested
    configuration paths with string APIs would weaken the startup boundary.
    """

    def __init__(self, path: Path, file_descriptor: int):
        self._path = path
        self._fd = file_descriptor

    @classmethod
    def open(cls, root_path: str | Path) -> "SecureRoot":
        path = Path(root_path)
        if os.name != "posix" or not path.is_absolute():
            raise _capability_error()
        required_dirfd_operations = {os.open, os.mkdir, os.stat, os.unlink, os.rmdir}
        if (
            not _OPEN_NOFOLLOW
            or not getattr(os, "O_DIRECTORY", 0)
            or not required_dirfd_operations.issubset(os.supports_dir_fd)
        ):
            raise _capability_error()
        try:
            file_descriptor = os.open(path, _OPEN_DIR_FLAGS | _OPEN_NOFOLLOW)
            root_stat = os.fstat(file_descriptor)
            if not stat.S_ISDIR(root_stat.st_mode) or root_stat.st_mode & 0o022:
                _close_quietly(file_descriptor)
                raise _capability_error()
            root = cls(path, file_descriptor)
            root._probe()
            return root
        except IngestionSecurityError:
            raise
        except OSError as error:
            _close_quietly(locals().get("file_descriptor"))
            raise _capability_error() from error

    def _probe(self) -> None:
        """Verify dirfd operations and ``O_NOFOLLOW`` semantics before accepting work."""

        probe_name = f".openguard-probe-{secrets.token_hex(8)}"
        link_name = f"{probe_name}-link"
        probe_fd: int | None = None
        try:
            os.mkdir(probe_name, 0o700, dir_fd=self._fd)
            probe_fd = os.open(probe_name, _OPEN_DIR_FLAGS | _OPEN_NOFOLLOW, dir_fd=self._fd)
            os.symlink(probe_name, link_name, dir_fd=self._fd)
            try:
                followed = os.open(link_name, _OPEN_DIR_FLAGS | _OPEN_NOFOLLOW, dir_fd=self._fd)
            except OSError as error:
                if error.errno not in {errno.ELOOP, errno.ENOTDIR}:
                    raise
            else:
                _close_quietly(followed)
                raise OSError(errno.EOPNOTSUPP, "O_NOFOLLOW did not reject a symlink")
        except OSError as error:
            raise _capability_error() from error
        finally:
            _close_quietly(probe_fd)
            try:
                os.unlink(link_name, dir_fd=self._fd)
            except OSError:
                pass
            try:
                os.rmdir(probe_name, dir_fd=self._fd)
            except OSError:
                pass

    def create_workspace(self) -> "SecureWorkspace":
        for _ in range(16):
            name = f"openguard-a2-{secrets.token_hex(16)}"
            try:
                os.mkdir(name, 0o700, dir_fd=self._fd)
                workspace_fd = os.open(name, _OPEN_DIR_FLAGS | _OPEN_NOFOLLOW, dir_fd=self._fd)
                return SecureWorkspace(self, name, workspace_fd)
            except FileExistsError:
                continue
            except OSError as error:
                raise IngestionSecurityError("scanner_failed", "workspace_create_failed") from error
        raise IngestionSecurityError("scanner_failed", "workspace_create_failed")

    def close(self) -> None:
        _close_quietly(self._fd)
        self._fd = -1


class SecureWorkspace:
    """A single task root which never resolves archive paths through string joins."""

    def __init__(self, root: SecureRoot, name: str, file_descriptor: int):
        self._root = root
        self._name = name
        self._fd = file_descriptor
        self._cleaned = False

    def _open_directory(self, parts: tuple[str, ...], *, create: bool) -> int:
        current_fd = os.dup(self._fd)
        try:
            for part in parts:
                if create:
                    try:
                        os.mkdir(part, 0o700, dir_fd=current_fd)
                    except FileExistsError:
                        pass
                child_fd = os.open(part, _OPEN_DIR_FLAGS | _OPEN_NOFOLLOW, dir_fd=current_fd)
                if not stat.S_ISDIR(os.fstat(child_fd).st_mode):
                    _close_quietly(child_fd)
                    raise IngestionSecurityError("scanner_failed", "workspace_integrity_failed")
                os.close(current_fd)
                current_fd = child_fd
            return current_fd
        except IngestionSecurityError:
            _close_quietly(current_fd)
            raise
        except OSError as error:
            _close_quietly(current_fd)
            raise IngestionSecurityError("scanner_failed", "workspace_integrity_failed") from error

    def make_directory(self, parts: tuple[str, ...]) -> None:
        directory_fd = self._open_directory(parts, create=True)
        _close_quietly(directory_fd)

    def write_new_file(self, parts: tuple[str, ...], write: Callable[[int], object]) -> object:
        if not parts:
            raise IngestionSecurityError("scanner_failed", "workspace_integrity_failed")
        parent_fd = self._open_directory(parts[:-1], create=True)
        file_fd: int | None = None
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _OPEN_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
            file_fd = os.open(parts[-1], flags, 0o600, dir_fd=parent_fd)
            return write(file_fd)
        except IngestionSecurityError:
            raise
        except OSError as error:
            raise IngestionSecurityError("scanner_failed", "workspace_write_failed") from error
        finally:
            _close_quietly(file_fd)
            _close_quietly(parent_fd)

    def open_existing_file(self, parts: tuple[str, ...]) -> BinaryIO:
        parent_fd = self._open_directory(parts[:-1], create=False)
        try:
            file_descriptor = os.open(
                parts[-1],
                os.O_RDONLY | _OPEN_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
                dir_fd=parent_fd,
            )
            if not stat.S_ISREG(os.fstat(file_descriptor).st_mode):
                _close_quietly(file_descriptor)
                raise IngestionSecurityError("scanner_failed", "workspace_integrity_failed")
            return os.fdopen(file_descriptor, "rb")
        except IngestionSecurityError:
            raise
        except OSError as error:
            raise IngestionSecurityError("scanner_failed", "workspace_integrity_failed") from error
        finally:
            _close_quietly(parent_fd)

    def open_directory(self, parts: tuple[str, ...]) -> int:
        return self._open_directory(parts, create=False)

    def trusted_process_path(self, parts: tuple[str, ...]) -> Path:
        """Render a path made solely from code-owned components for a fixed tool.

        Untrusted archive or Git paths must continue to use descriptor-relative
        methods. This narrow escape hatch exists only because Git requires a
        filesystem path for its own private object database.
        """

        if not parts or any(part in {".", ".."} or _TRUSTED_PROCESS_PART.fullmatch(part) is None for part in parts):
            raise IngestionSecurityError("scanner_failed", "workspace_integrity_failed")
        return self._root._path.joinpath(self._name, *parts)

    def cleanup(self, retries: int) -> None:
        if self._cleaned:
            return
        last_error: OSError | None = None
        for _ in range(retries):
            try:
                self._remove_tree(self._fd)
                os.rmdir(self._name, dir_fd=self._root._fd)
                self._cleaned = True
                _close_quietly(self._fd)
                self._fd = -1
                return
            except OSError as error:
                last_error = error
        _close_quietly(self._fd)
        self._fd = -1
        raise IngestionSecurityError("scanner_failed", "workspace_cleanup_failed") from last_error

    def _remove_tree(self, directory_fd: int) -> None:
        for name in os.listdir(directory_fd):
            entry_stat = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISDIR(entry_stat.st_mode):
                child_fd = os.open(name, _OPEN_DIR_FLAGS | _OPEN_NOFOLLOW, dir_fd=directory_fd)
                try:
                    self._remove_tree(child_fd)
                finally:
                    _close_quietly(child_fd)
                os.rmdir(name, dir_fd=directory_fd)
            else:
                os.unlink(name, dir_fd=directory_fd)
