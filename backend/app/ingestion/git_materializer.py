"""Validate Git objects and materialize only ordinary blobs, never a checkout."""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path

from app.ingestion.git_runner import (GitProcessRunner, _kill_process_group,
    _SCANCODE_VCS_IGNORED_PARTS, _SCANCODE_VCS_SUPPLEMENT_MAX)
from app.security.archive_path import normalize_member_path
from app.security.errors import IngestionSecurityError
from app.security.limits import GitSafetyLimits, ZipSafetyLimits
from app.security.secure_dir import SecureWorkspace


_OBJECT_ID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_ALLOWED_MODES = frozenset({"100644", "100755"})


@dataclass(frozen=True)
class GitTreeEntry:
    mode: str
    object_id: str
    size: int
    parts: tuple[str, ...]
    relative_path: str
    collision_key: str


@dataclass(frozen=True)
class GitOmission:
    path: str
    reason: str
    object_id: str


@dataclass(frozen=True)
class MaterializedGitTree:
    revision: str
    file_count: int
    total_bytes: int
    omissions: tuple[GitOmission, ...] = ()
    discovered_entries: int = 0


def _reject(reason: str) -> None:
    raise IngestionSecurityError("invalid_source", reason)


def _path_limits(limits: GitSafetyLimits) -> ZipSafetyLimits:
    return ZipSafetyLimits(
        uncompressed_max_bytes=limits.materialized_max_bytes,
        entry_count_max=limits.file_count_max,
        single_file_max_bytes=limits.single_file_max_bytes,
        path_depth_max=limits.path_depth_max,
        path_utf8_bytes_max=limits.path_utf8_bytes_max,
        cleanup_retry_max=limits.cleanup_retry_max,
        scan_single_file_read_max_bytes=limits.scan_single_file_read_max_bytes,
        scan_total_read_max_bytes=limits.scan_total_read_max_bytes,
    )


def _parse_tree(data: bytes, limits: GitSafetyLimits) -> tuple[GitTreeEntry, ...]:
    path_limits = _path_limits(limits)
    records = data.split(b"\0")
    if records[-1] != b"":
        _reject("git_object_invalid")
    entries: list[GitTreeEntry] = []
    files: set[str] = set()
    directories: set[str] = set()
    total = 0
    for record in records[:-1]:
        if len(entries) >= limits.file_count_max:
            raise IngestionSecurityError("scanner_failed", "git_file_count_limit_exceeded")
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_type, raw_object_id, raw_size = metadata.split()
            rendered_mode = mode.decode("ascii")
            rendered_type = object_type.decode("ascii")
            object_id = raw_object_id.decode("ascii")
            size = int(raw_size.decode("ascii"))
            raw_name = raw_path.decode("utf-8")
        except (UnicodeDecodeError, ValueError) as error:
            raise IngestionSecurityError("invalid_source", "git_object_invalid") from error
        if rendered_mode not in _ALLOWED_MODES or rendered_type != "blob" or _OBJECT_ID.fullmatch(object_id) is None:
            _reject("git_entry_unsafe")
        if size < 0:
            _reject("git_object_invalid")
        if size > limits.single_file_max_bytes:
            raise IngestionSecurityError("scanner_failed", "git_single_file_limit_exceeded")
        total += size
        if total > limits.materialized_max_bytes:
            raise IngestionSecurityError("scanner_failed", "git_materialized_limit_exceeded")
        try:
            path = normalize_member_path(raw_name, is_directory=False, limits=path_limits)
        except IngestionSecurityError as error:
            if error.code == "archive_limit_exceeded":
                raise IngestionSecurityError("scanner_failed", error.reason.replace("archive_", "git_", 1)) from error
            raise IngestionSecurityError("invalid_source", "git_entry_unsafe") from error
        if any(part.casefold() == ".git" for part in path.parts):
            _reject("git_entry_unsafe")
        if path.collision_key in files or path.collision_key in directories:
            _reject("git_entry_unsafe")
        for index in range(1, len(path.parts)):
            parent = "/".join(path.parts[:index]).casefold()
            if parent in files:
                _reject("git_entry_unsafe")
            directories.add(parent)
        prefix = f"{path.collision_key}/"
        if any(candidate.startswith(prefix) for candidate in files | directories):
            _reject("git_entry_unsafe")
        files.add(path.collision_key)
        entries.append(
            GitTreeEntry(
                mode=rendered_mode,
                object_id=object_id,
                size=size,
                parts=path.parts,
                relative_path=path.relative_path,
                collision_key=path.collision_key,
            )
        )
    return tuple(entries)


def inspect_git_tree(
    runner: GitProcessRunner,
    repository: Path,
    *,
    home: Path,
    limits: GitSafetyLimits,
    deadline: float,
) -> tuple[str, tuple[GitTreeEntry, ...]]:
    revision = runner.capture(
        ("-C", str(repository), "rev-parse", "--verify", "HEAD^{commit}"),
        cwd=repository.parent,
        home=home,
        deadline=deadline,
        output_max=128,
    ).decode("ascii", "strict").strip()
    if _OBJECT_ID.fullmatch(revision) is None:
        _reject("git_object_invalid")
    maximum_listing = limits.file_count_max * (limits.path_utf8_bytes_max + 128)
    listing = runner.capture(
        ("-C", str(repository), "ls-tree", "-r", "-l", "-z", "--full-tree", "HEAD"),
        cwd=repository.parent,
        home=home,
        deadline=deadline,
        output_max=maximum_listing,
    )
    return revision, _parse_tree(listing, limits)



def _selection_priority(entry: GitTreeEntry) -> tuple[int, int, bytes]:
    name = entry.parts[-1].lower()
    if name.startswith(("license", "licence", "copying", "notice")):
        priority = 0
    elif name in {"pyproject.toml", "package.json", "setup.py", "setup.cfg", "cargo.toml", "go.mod", "pom.xml"} or name.startswith("requirements"):
        priority = 1
    elif name in {"uv.lock", "poetry.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "cargo.lock", "go.sum"}:
        priority = 2
    elif name.startswith("readme"):
        priority = 3
    elif name.endswith((".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml", ".toml")):
        priority = 4
    else:
        priority = 5
    # Shallow project metadata comes before hundreds of vendored package
    # LICENSE files. Within a directory keep license + manifest together.
    depth = len(entry.parts)
    tier = 0 if priority <= 3 and depth <= 3 else 1 if priority <= 1 else priority
    directory = "/".join(entry.parts[:-1]).encode("utf-8")
    return tier, depth, directory + b"\0" + bytes([priority]) + entry.parts[-1].encode("utf-8")


def inspect_bounded_git_tree(runner: GitProcessRunner, repository: Path, *, home: Path,
                             limits: GitSafetyLimits, deadline: float
                             ) -> tuple[str, tuple[GitTreeEntry, ...], tuple[GitOmission, ...], int]:
    revision = runner.capture(("-C", str(repository), "rev-parse", "--verify", "HEAD^{commit}"),
        cwd=repository.parent, home=home, deadline=deadline, output_max=128).decode("ascii").strip()
    if _OBJECT_ID.fullmatch(revision) is None:
        _reject("git_object_invalid")
    # Deliberately omit -l: looking up sizes would lazy-fetch all missing blobs.
    data = runner.capture(("-C", str(repository), "ls-tree", "-r", "-z", "--full-tree", "HEAD"),
        cwd=repository.parent, home=home, deadline=deadline,
        output_max=limits.file_count_max * (limits.path_utf8_bytes_max + 128))
    records = data.split(b"\0")
    if records[-1] or len(records) - 1 > limits.file_count_max:
        raise IngestionSecurityError("scanner_failed", "git_file_count_limit_exceeded")
    entries, omitted = [], []
    files, directories = set(), set()
    path_limits = _path_limits(limits)
    for record in records[:-1]:
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, kind, oid = metadata.decode("ascii").split()
            name = raw_path.decode("utf-8")
            path = normalize_member_path(name, is_directory=False, limits=path_limits)
        except (ValueError, UnicodeDecodeError, IngestionSecurityError):
            _reject("git_entry_unsafe")
        if _OBJECT_ID.fullmatch(oid) is None or any(p.casefold() == ".git" for p in path.parts):
            _reject("git_entry_unsafe")
        if path.collision_key in files or path.collision_key in directories:
            _reject("git_entry_unsafe")
        for i in range(1, len(path.parts)):
            parent = "/".join(path.parts[:i]).casefold()
            if parent in files:
                _reject("git_entry_unsafe")
            directories.add(parent)
        files.add(path.collision_key)
        if (mode, kind) in {("120000", "blob"), ("160000", "commit")}:
            omitted.append(GitOmission(path.relative_path, "symlink_not_followed" if mode == "120000" else "submodule_not_fetched", oid))
            continue
        if mode not in _ALLOWED_MODES or kind != "blob":
            _reject("git_entry_unsafe")
        entries.append(GitTreeEntry(mode, oid, 0, path.parts, path.relative_path, path.collision_key))
    entries.sort(key=_selection_priority)
    maximum = 4096 if len(entries) <= 4096 else 512
    for entry in entries[maximum:]:
        omitted.append(GitOmission(entry.relative_path, "bounded_file_selection", entry.object_id))
    return revision, tuple(entries[:maximum]), tuple(omitted), len(records) - 1


def materialize_bounded_git_tree(runner: GitProcessRunner, repository: Path, workspace: SecureWorkspace,
                                 *, home: Path, limits: GitSafetyLimits, deadline: float, proxy_url: str
                                 ) -> MaterializedGitTree:
    revision, candidates, initial_omissions, discovered = inspect_bounded_git_tree(
        runner, repository, home=home, limits=limits, deadline=deadline)
    omitted = list(initial_omissions)
    selected = []
    total = 0
    manifest_counts = {"python": 0, "javascript": 0}
    manifest_bytes = {"python": 0, "javascript": 0}
    # Match existing parser budgets; excluding an over-budget manifest is
    # explicit coverage loss, never an excuse to disable its safety checks.
    def lane_for(entry: GitTreeEntry) -> str | None:
        if any(p in {".git", ".hg", ".svn", ".venv", "venv", "__pycache__", "site-packages", "node_modules"} for p in entry.parts[:-1]):
            return None
        name = entry.parts[-1]
        if name == "pyproject.toml" or (name.startswith("requirements") and name.endswith(".txt")):
            return "python"
        return "javascript" if name in {"package.json", "package-lock.json"} else None
    admitted = []
    vcs_supplements = 0
    for candidate in candidates:
        lane = lane_for(candidate)
        if lane and manifest_counts[lane] >= 64:
            omitted.append(GitOmission(candidate.relative_path, f"bounded_{lane}_manifest_count", candidate.object_id))
            continue
        needs_supplement = any(part.lower() in _SCANCODE_VCS_IGNORED_PARTS for part in candidate.parts)
        if needs_supplement and vcs_supplements >= _SCANCODE_VCS_SUPPLEMENT_MAX:
            omitted.append(GitOmission(candidate.relative_path, "bounded_scancode_vcs_budget", candidate.object_id))
            continue
        if lane:
            manifest_counts[lane] += 1
        if needs_supplement:
            vcs_supplements += 1
        admitted.append(candidate)
    candidates = tuple(admitted)
    # Keep small SDKs complete when they fit the existing 16 MiB read budget.
    byte_limit = min(limits.materialized_max_bytes, limits.scan_total_read_max_bytes)
    fetched = set()
    for start in range(0, len(candidates), 256):
        batch = candidates[start:start + 256]
        if total >= byte_limit:
            omitted.extend(GitOmission(e.relative_path, "bounded_byte_budget", e.object_id) for e in candidates[start:])
            break
        ids = tuple(dict.fromkeys(e.object_id for e in batch if e.object_id not in fetched))
        if ids:
            runner.fetch_objects(repository, ids, home=home, proxy_url=proxy_url, deadline=deadline)
            fetched.update(ids)
        sizes = runner.object_sizes(repository, tuple(dict.fromkeys(e.object_id for e in batch)), home=home, deadline=deadline)
        for entry in batch:
            size = sizes[entry.object_id]
            lane = lane_for(entry)
            single_manifest_limit = 262144 if lane == "python" else 2 * 1024 * 1024
            total_manifest_limit = 4 * 1024 * 1024 if lane == "python" else 8 * 1024 * 1024
            if lane and (size > single_manifest_limit or manifest_bytes[lane] + size > total_manifest_limit):
                omitted.append(GitOmission(entry.relative_path, f"bounded_{lane}_manifest_bytes", entry.object_id))
            elif size > min(limits.single_file_max_bytes, limits.scan_single_file_read_max_bytes):
                omitted.append(GitOmission(entry.relative_path, "bounded_single_file_budget", entry.object_id))
            elif total + size > byte_limit:
                omitted.append(GitOmission(entry.relative_path, "bounded_byte_budget", entry.object_id))
            else:
                selected.append(replace(entry, size=size))
                total += size
                if lane:
                    manifest_bytes[lane] += size
    if not selected:
        workspace.make_directory(("tree",))
    else:
        materialize_git_blobs(runner, repository, workspace, tuple(selected), home=home, deadline=deadline)
    return MaterializedGitTree(revision, len(selected), total,
        tuple(sorted(omitted, key=lambda e: e.path.encode("utf-8"))), discovered)

def materialize_git_blobs(
    runner: GitProcessRunner,
    repository: Path,
    workspace: SecureWorkspace,
    entries: tuple[GitTreeEntry, ...],
    *,
    home: Path,
    deadline: float,
) -> int:
    process = runner.spawn_batch(cwd=repository, home=home)
    assert process.stdin is not None and process.stdout is not None
    timed_out = threading.Event()

    def expire() -> None:
        timed_out.set()
        _kill_process_group(process)

    remaining = deadline - time.monotonic()
    if remaining <= 0:
        _kill_process_group(process)
        process.wait()
        raise IngestionSecurityError("scanner_timeout", "git_process_timeout")
    timer = threading.Timer(remaining, expire)
    timer.start()
    materialized = 0
    try:
        for entry in entries:
            process.stdin.write(entry.object_id.encode("ascii") + b"\n")
            process.stdin.flush()
            header = process.stdout.readline(256)
            if not header.endswith(b"\n") or len(header) >= 256:
                _reject("git_object_invalid")
            try:
                object_id, object_type, rendered_size = header[:-1].decode("ascii").split(" ")
                size = int(rendered_size)
            except (UnicodeDecodeError, ValueError) as error:
                raise IngestionSecurityError("invalid_source", "git_object_invalid") from error
            if object_id != entry.object_id or object_type != "blob" or size != entry.size:
                _reject("git_object_invalid")

            def write(file_descriptor: int) -> None:
                remaining_bytes = entry.size
                while remaining_bytes:
                    chunk = process.stdout.read(min(64 * 1024, remaining_bytes))
                    if not chunk:
                        _reject("git_object_invalid")
                    view = memoryview(chunk)
                    while view:
                        written = os.write(file_descriptor, view)
                        if written <= 0:
                            raise OSError("short write")
                        view = view[written:]
                    remaining_bytes -= len(chunk)

            workspace.write_new_file(("tree", *entry.parts), write)
            if process.stdout.read(1) != b"\n":
                _reject("git_object_invalid")
            materialized += entry.size
        process.stdin.close()
        process.wait()
        if timed_out.is_set():
            raise IngestionSecurityError("scanner_timeout", "git_process_timeout")
        if process.returncode != 0:
            _reject("git_object_invalid")
        return materialized
    except (BrokenPipeError, OSError) as error:
        if timed_out.is_set():
            raise IngestionSecurityError("scanner_timeout", "git_process_timeout") from error
        raise IngestionSecurityError("invalid_source", "git_object_invalid") from error
    finally:
        timer.cancel()
        if process.poll() is None:
            _kill_process_group(process)
            process.wait()
        if not process.stdin.closed:
            process.stdin.close()
        process.stdout.close()


def materialize_git_tree(
    runner: GitProcessRunner,
    repository: Path,
    workspace: SecureWorkspace,
    *,
    home: Path,
    limits: GitSafetyLimits,
    deadline: float,
) -> MaterializedGitTree:
    revision, entries = inspect_git_tree(runner, repository, home=home, limits=limits, deadline=deadline)
    total = materialize_git_blobs(runner, repository, workspace, entries, home=home, deadline=deadline)
    return MaterializedGitTree(revision=revision, file_count=len(entries), total_bytes=total)


__all__ = [
    "GitTreeEntry",
    "MaterializedGitTree",
    "inspect_git_tree",
    "materialize_git_blobs",
    "materialize_git_tree",
]
