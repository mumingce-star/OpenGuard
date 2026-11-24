"""Capture a local input and run the existing ZIP pipeline in private scratch space."""

from __future__ import annotations

import hashlib
import os
import stat
import sys
import tempfile
import unicodedata
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from app.api.models import ZipScanCreateFields
from app.api.service import ScanApiService
from app.domain.models import ScanRun, ScanStatus
from app.domain.usage import UsageDeclaration
from app.ingestion.zip_preflight import preflight_zip
from app.persistence import SQLiteScanRunRegistry
from app.pipeline import ScanPipelineWorker, build_local_zip_dependency_plan
from app.security.archive_path import NormalizedArchivePath, normalize_member_path
from app.security.errors import IngestionSecurityError
from app.security.limits import ZipSafetyLimits

_EXCLUDED = frozenset({
    ".git", "node_modules", "__pycache__", ".venv", "venv", "target", "dist", "build", ".pytest_cache",
})
_LICENSE_FILES = frozenset({"license", "license.txt", "license.md", "copying", "copying.txt"})
_LICENSE_LIMIT = 65536
_CHUNK_SIZE = 65536
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


class HeadlessScanError(RuntimeError):
    """A fixed error code for the CLI, without host paths or source data."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ScanInput:
    run: ScanRun
    kind: str
    name: str
    sha256: str
    excluded_dirs: tuple[str, ...]
    license_files: dict[str, bytes]
    skipped_entries: int


@dataclass
class _TreeCapture:
    limits: ZipSafetyLimits
    source: Path
    protected_package: tuple[int, int]
    scratch: Path
    scratch_identity: tuple[int, int]
    visited: int = 0
    files: int = 0
    source_bytes: int = 0
    skipped: int = 0
    excluded: list[str] = field(default_factory=list)
    seen_paths: set[str] = field(default_factory=set)


def _absolute_path(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    # macOS exposes these two fixed system aliases. Rewrite only descendants
    # of the stock aliases and still open every component of the physical path
    # without following links. A symlink selected as the target stays invalid.
    if sys.platform == "darwin" and len(absolute.parts) > 2 and absolute.parts[1] in {"tmp", "var"}:
        alias = absolute.parts[1]
        try:
            destination = os.readlink(f"/{alias}")
        except OSError:
            destination = ""
        if destination in {f"private/{alias}", f"/private/{alias}"}:
            return Path("/private").joinpath(*absolute.parts[1:])
    return absolute


def _path_key(path: Path) -> tuple[str, ...]:
    return tuple(unicodedata.normalize("NFC", part).casefold() for part in path.parts)


def _at_or_below(path: Path, root: Path) -> bool:
    key = _path_key(root)
    return _path_key(path)[:len(key)] == key


def _signature(info: os.stat_result) -> tuple[int, ...]:
    return info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _directory_identity(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def _is_package_runtime(parent: int, name: str, package: tuple[int, int]) -> bool:
    # The parent descriptor provides the same identity through APFS firmlinks
    # and mount aliases. No lookup of the protected entry is needed.
    return name.casefold() == "runtime" and _directory_identity(os.fstat(parent)) == package


@contextmanager
def _open_directory(path: Path, *, protected_package: tuple[int, int] | None = None) -> Iterator[int]:
    """Pin every ancestor without following symlinks."""
    descriptor = os.open(path.anchor, _DIRECTORY_FLAGS)
    try:
        for part in path.parts[1:]:
            if protected_package is not None and _is_package_runtime(descriptor, part, protected_package):
                raise HeadlessScanError("invalid_input_path")
            child = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


@contextmanager
def _open_member(parent: int, name: str, info: os.stat_result, *, is_directory: bool) -> Iterator[int]:
    flags = _DIRECTORY_FLAGS if is_directory else _FILE_FLAGS
    descriptor = os.open(name, flags, dir_fd=parent)
    try:
        if _signature(os.fstat(descriptor)) != _signature(info):
            raise HeadlessScanError("input_changed")
        yield descriptor
        if _signature(os.fstat(descriptor)) != _signature(info):
            raise HeadlessScanError("input_changed")
    finally:
        os.close(descriptor)


def _member_path(
    parts: tuple[str, ...], *, directory: bool, limits: ZipSafetyLimits,
) -> NormalizedArchivePath:
    return normalize_member_path("/".join(parts), is_directory=directory, limits=limits)


def _copy_exact(source: int, destination: BinaryIO, size: int) -> None:
    remaining = size
    while remaining:
        block = os.read(source, min(remaining, _CHUNK_SIZE))
        if not block:
            raise HeadlessScanError("input_changed")
        destination.write(block)
        remaining -= len(block)
    if os.read(source, 1):
        raise HeadlessScanError("input_changed")


def _capture_directory(
    directory: int, relative: tuple[str, ...], archive: zipfile.ZipFile, capture: _TreeCapture,
) -> None:
    entries: list[tuple[str, str, os.stat_result]] = []
    with os.scandir(directory) as source:
        for entry in source:
            capture.visited += 1
            if capture.visited > capture.limits.entry_count_max:
                raise HeadlessScanError("archive_entry_count_limit")
            parts = (*relative, entry.name)
            physical = capture.source.joinpath(*parts)
            if _at_or_below(physical, capture.scratch):
                continue
            if _is_package_runtime(directory, entry.name, capture.protected_package):
                capture.excluded.append(_member_path(parts, directory=True, limits=capture.limits).relative_path)
                continue
            info = entry.stat(follow_symlinks=False)
            is_directory = stat.S_ISDIR(info.st_mode)
            if is_directory and _directory_identity(info) == capture.scratch_identity:
                continue
            if not (is_directory or stat.S_ISREG(info.st_mode)):
                capture.skipped += 1
                continue
            path = _member_path(parts, directory=is_directory, limits=capture.limits)
            if is_directory and entry.name.casefold() in _EXCLUDED:
                capture.excluded.append(path.relative_path)
                continue
            if path.collision_key in capture.seen_paths:
                raise HeadlessScanError("archive_duplicate_path")
            capture.seen_paths.add(path.collision_key)
            entries.append((path.relative_path, entry.name, info))

    def sort_key(entry: tuple[str, str, os.stat_result]) -> str:
        path, _, info = entry
        return path + "/" if stat.S_ISDIR(info.st_mode) else path

    for path, name, info in sorted(entries, key=sort_key):
        if stat.S_ISDIR(info.st_mode):
            with _open_member(directory, name, info, is_directory=True) as child:
                _capture_directory(child, (*relative, name), archive, capture)
            continue
        if info.st_size > capture.limits.single_file_max_bytes:
            raise HeadlessScanError("archive_single_file_limit")
        capture.source_bytes += info.st_size
        if capture.source_bytes > capture.limits.uncompressed_max_bytes:
            raise HeadlessScanError("archive_total_size_limit")
        if capture.source_bytes > capture.limits.upload_max_bytes:
            raise HeadlessScanError("archive_upload_size_limit")
        member = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
        # Stored entries preserve the production anti-expansion-ratio checks for
        # directories whose legitimate source happens to be highly repetitive.
        member.compress_type = zipfile.ZIP_STORED
        member.create_system = 3
        member.external_attr = 0o100644 << 16
        member.file_size = info.st_size
        with _open_member(directory, name, info, is_directory=False) as source_file:
            with archive.open(member, "w") as output:
                _copy_exact(source_file, output, info.st_size)
        capture.files += 1


def _stage_input(
    target: Path, private: Path, protected_package: tuple[int, int], limits: ZipSafetyLimits,
) -> tuple[Path, str, str, _TreeCapture]:
    archive = private / "input.zip"
    scratch_identity = _directory_identity(private.stat(follow_symlinks=False))
    capture = _TreeCapture(limits, target, protected_package, private, scratch_identity)
    with _open_directory(target.parent, protected_package=protected_package) as parent:
        if _is_package_runtime(parent, target.name, protected_package):
            raise HeadlessScanError("invalid_input_path")
        info = os.stat(target.name, dir_fd=parent, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            kind = "directory"
            with _open_member(parent, target.name, info, is_directory=True) as directory:
                with zipfile.ZipFile(archive, "x", allowZip64=False) as output:
                    _capture_directory(directory, (), output, capture)
            if not capture.files:
                raise HeadlessScanError("empty_directory")
        elif stat.S_ISREG(info.st_mode) and target.suffix.lower() == ".zip":
            kind = "zip"
            if not 0 < info.st_size <= limits.upload_max_bytes:
                raise HeadlessScanError("archive_upload_size_limit")
            with _open_member(parent, target.name, info, is_directory=False) as source:
                with archive.open("xb") as output:
                    _copy_exact(source, output, info.st_size)
        else:
            raise HeadlessScanError("invalid_input_type")
    if archive.stat().st_size > limits.upload_max_bytes:
        raise HeadlessScanError("archive_upload_size_limit")
    with archive.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return archive, kind, digest, capture


def _run_pipeline(archive: Path, scratch: Path, digest: str, usage: dict[str, bool]) -> ScanRun:
    def clock() -> datetime:
        return datetime.now(timezone.utc)

    workspace = scratch / "workspaces"
    workspace.mkdir(mode=0o700)
    with SQLiteScanRunRegistry(scratch / "scans.db") as registry:
        service = ScanApiService(registry, clock=clock)
        candidate = service.build_zip_scan_candidate(
            ZipScanCreateFields(source_type="zip", usage=UsageDeclaration(**usage)),
            staged_name=archive.name, project_name="local-scan", input_digest=digest,
        )
        accepted, _ = service.commit_zip_scan_candidate(candidate)
        plan = build_local_zip_dependency_plan(
            archive, workspace, clock=clock, ai_enabled=False, external_scanners=False,
        )
        run = ScanPipelineWorker(registry, clock=clock).run(accepted.scan_id, plan).run
    if run.status not in {ScanStatus.COMPLETED, ScanStatus.PARTIAL}:
        if any(error.code == "dependency_manifest_not_found" for error in run.errors):
            raise HeadlessScanError("dependency_manifest_not_found")
        if any(error.code == "zip_ingestion_failed" for error in run.errors):
            raise HeadlessScanError("zip_ingestion_failed")
        raise HeadlessScanError("scan_failed")
    return run


def _root_licenses(source: zipfile.ZipFile, limits: ZipSafetyLimits) -> dict[str, bytes]:
    """Read only root license members of the same accepted private archive."""
    files: dict[str, bytes] = {}
    for member in preflight_zip(source, limits):
        name = member.path.relative_path
        if (member.path.is_directory or len(member.path.parts) != 1
                or name.casefold() not in _LICENSE_FILES
                or not 0 < member.info.file_size <= _LICENSE_LIMIT):
            continue
        with source.open(member.info) as contents:
            data = contents.read(_LICENSE_LIMIT + 1)
        if len(data) != member.info.file_size:
            raise HeadlessScanError("archive_integrity_failed")
        files[name] = data
    return files


def _verified_root_licenses(archive: Path, digest: str, limits: ZipSafetyLimits) -> dict[str, bytes]:
    with _open_directory(archive.parent) as parent:
        info = os.stat(archive.name, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limits.upload_max_bytes:
            raise HeadlessScanError("input_changed")
        with _open_member(parent, archive.name, info, is_directory=False) as descriptor:
            with os.fdopen(descriptor, "rb", closefd=False) as packed:
                if hashlib.file_digest(packed, "sha256").hexdigest() != digest:
                    raise HeadlessScanError("input_changed")
                packed.seek(0)
                with zipfile.ZipFile(packed, "r") as source:
                    return _root_licenses(source, limits)


def scan_target(target: Path, *, usage: dict[str, bool], package_root: Path) -> ScanInput:
    """Run a single local scan, then destroy all staging and registry data."""
    absolute = _absolute_path(target)
    package = _absolute_path(package_root)
    protected = package / "runtime"
    if not absolute.name or _at_or_below(absolute, protected):
        raise HeadlessScanError("invalid_input_path")
    limits = ZipSafetyLimits()
    try:
        # Deliberately avoid TMPDIR: it may point into the package's protected
        # runtime. /tmp is the OS scratch location on the supported platforms.
        scratch_root = "/private/tmp" if sys.platform == "darwin" else "/tmp"
        with (_open_directory(package) as package_descriptor,
              tempfile.TemporaryDirectory(prefix="openguard-scan-", dir=scratch_root) as temp):
            scratch = Path(temp)
            protected_package = _directory_identity(os.fstat(package_descriptor))
            archive, kind, digest, capture = _stage_input(absolute, scratch, protected_package, limits)
            run = _run_pipeline(archive, scratch, digest, usage)
            licenses = _verified_root_licenses(archive, digest, limits)
    except IngestionSecurityError as error:
        raise HeadlessScanError(error.reason) from None
    except (OSError, UnicodeError):
        raise HeadlessScanError("input_unavailable") from None
    except (zipfile.BadZipFile, zipfile.LargeZipFile):
        raise HeadlessScanError("invalid_zip") from None
    return ScanInput(
        run=run, kind=kind, name=absolute.name, sha256=digest,
        excluded_dirs=tuple(sorted(capture.excluded)), license_files=licenses,
        skipped_entries=capture.skipped,
    )
