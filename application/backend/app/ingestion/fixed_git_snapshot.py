"""Explicit operator-pinned Git source input; never a cached ScanRun/result.

The operator attests the capture receipt separately. Hash binding proves byte
consistency, not source authentication against a malicious local administrator.
No path or snapshot identity is accepted from the HTTP scan request.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.ingestion.url_policy import parse_public_git_url
from app.security.errors import IngestionSecurityError

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_REVISION = re.compile(r"[0-9a-f]{40}\Z")
_CHUNK = 64 * 1024


@dataclass(frozen=True)
class GitSourceSnapshotEvidence:
    source_url: str
    revision: str
    bundle_sha256: str
    bundle_size: int
    captured_at: str
    capture_receipt_sha256: str
    kind: str = "FIXED_GIT_SOURCE_SNAPSHOT"
    profile: str = "complete_git_objects_offline_materialization/v1"


@dataclass(frozen=True)
class FixedGitSnapshot:
    bundle_path: Path
    source_url: str
    revision: str
    bundle_sha256: str
    bundle_size: int
    captured_at: str
    capture_receipt_sha256: str

    def __post_init__(self):
        if (not isinstance(self.bundle_path, Path) or not self.bundle_path.is_absolute()
                or ".." in self.bundle_path.parts or "\0" in str(self.bundle_path)
                or type(self.source_url) is not str
                or parse_public_git_url(self.source_url).canonical != self.source_url
                or type(self.revision) is not str or not _REVISION.fullmatch(self.revision)
                or type(self.bundle_sha256) is not str or not _SHA256.fullmatch(self.bundle_sha256)
                or type(self.capture_receipt_sha256) is not str or not _SHA256.fullmatch(self.capture_receipt_sha256)
                or type(self.bundle_size) is not int or not 0 < self.bundle_size <= 256 * 1024 * 1024
                or type(self.captured_at) is not str or len(self.captured_at) > 40):
            raise ValueError("fixed_git_snapshot_config_invalid")
        try:
            stamp = datetime.fromisoformat(self.captured_at.replace("Z", "+00:00"))
            if stamp.utcoffset() is None:
                raise ValueError
        except ValueError:
            raise ValueError("fixed_git_snapshot_time_invalid") from None

    def evidence(self) -> GitSourceSnapshotEvidence:
        return GitSourceSnapshotEvidence(self.source_url, self.revision, self.bundle_sha256,
            self.bundle_size, self.captured_at, self.capture_receipt_sha256)


def _deadline(deadline):
    if time.monotonic() >= deadline:
        raise IngestionSecurityError("scanner_timeout", "fixed_git_snapshot_timeout")


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size,
        info.st_mtime_ns, info.st_ctime_ns)


def _open_no_links(path: Path) -> int:
    """Walk every directory through descriptors; reject intermediate symlinks."""
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in path.parts[1:-1]:
            following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=directory)
            os.close(directory)
            directory = following
        return os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
            dir_fd=directory)
    finally:
        os.close(directory)


def restore_fixed_snapshot(profile: FixedGitSnapshot, canonical_url: str, workspace,
        runner, *, home: Path, repository: Path, deadline: float, transfer_max_bytes: int):
    """Verify and copy the very same descriptor before any offline Git process."""
    if canonical_url != profile.source_url:
        raise IngestionSecurityError("invalid_source", "fixed_git_snapshot_source_mismatch")
    if profile.bundle_size > transfer_max_bytes:
        raise IngestionSecurityError("scanner_failed", "git_fetch_limit_exceeded")
    descriptor = None
    try:
        _deadline(deadline)
        descriptor = _open_no_links(profile.bundle_path)
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_mode & 0o222
                or before.st_nlink != 1 or before.st_size != profile.bundle_size):
            raise IngestionSecurityError("invalid_source", "fixed_git_snapshot_file_invalid")
        count, digest = 0, hashlib.sha256()
        def write(destination):
            nonlocal count
            while True:
                _deadline(deadline)
                data = os.read(descriptor, min(_CHUNK, max(1, profile.bundle_size - count + 1)))
                if not data:
                    break
                count += len(data)
                if count > profile.bundle_size:
                    raise IngestionSecurityError("invalid_source", "fixed_git_snapshot_size_mismatch")
                digest.update(data)
                pending = memoryview(data)
                while pending:
                    written = os.write(destination, pending)
                    if written <= 0:
                        raise OSError
                    pending = pending[written:]
            _deadline(deadline)
            if (count != profile.bundle_size or digest.hexdigest() != profile.bundle_sha256
                    or _identity(os.fstat(descriptor)) != _identity(before)):
                raise IngestionSecurityError("invalid_source", "fixed_git_snapshot_identity_mismatch")
        workspace.write_new_file(("source.bundle",), write)
    except OSError:
        raise IngestionSecurityError("invalid_source", "fixed_git_snapshot_read_failed") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    bundle = workspace.trusted_process_path(("source.bundle",))
    # All Git network protocols remain denied by the locked runner. File is
    # permitted only for this explicit private verified bundle clone command.
    runner.capture(("-c", "protocol.file.allow=always", "clone", "--quiet", "--no-checkout",
        "--no-tags", "--no-recurse-submodules", "--template=", "--", str(bundle), str(repository)),
        cwd=home, home=home, deadline=deadline, output_max=4096)
    revision = runner.capture(("rev-parse", "--verify", "HEAD^{commit}"), cwd=repository,
        home=home, deadline=deadline, output_max=128).decode("ascii", errors="strict").strip()
    if revision != profile.revision:
        raise IngestionSecurityError("invalid_source", "fixed_git_snapshot_revision_mismatch")
    return profile.evidence()
