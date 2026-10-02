"""Internal completion authority for one genuine controlled ingestion.

Not an authentication boundary against malicious in-process Python. A completion
is correlated with this invocation's actual callback result and sealed detached
content, not a caller's success flag/digest or a reconstructed ScanSessionResult.
No live session, input descriptor, workspace or service escapes the wrappers.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import os
from pathlib import Path
import re
import stat
from typing import Callable, Generic, TypeVar

from app.ingestion import (ZipIngestionService, GitIngestionService,
    ScanSessionResult, GitScanSessionResult, ReadOnlyScanSession, ScanReadLimits)
from app.ingestion.read_session import effective_limits
from app.notice_source.models import NoticeSourceCollection, Producer, canonical_json
from app.notice_source.selector import SelectorResult

T = TypeVar("T")
_CHUNK = 64 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")


class NoticeIngestionError(ValueError):
    """Context-free internal rejection; never discloses input paths or content."""


@dataclass(frozen=True)
class CollectedNotice:
    collection: NoticeSourceCollection | None
    producer: Producer
    selection: SelectorResult


@dataclass(frozen=True)
class NoticeDependencyResult(Generic[T]):
    dependencies: T
    notice: CollectedNotice | None

    @property
    def collection(self) -> NoticeSourceCollection | None:
        return self.notice.collection if self.notice is not None else None


class CompletedNoticeIngestion:
    __slots__ = ("scan_id", "source", "source_type", "input_digest", "result", "_verify")

    def __init__(self, *args, **kwargs):
        raise NoticeIngestionError("completion_not_constructible")

    def __setattr__(self, name, value):
        raise NoticeIngestionError("completion_immutable")


def _snapshot(result):
    envelope = result.consumer_result
    if type(envelope) is not NoticeDependencyResult:
        raise NoticeIngestionError("completion_result_invalid")
    notice = envelope.notice
    collection = envelope.collection
    if collection is not None:
        # Validate mutable typed DTOs too; validation alone is not the content seal.
        collection = NoticeSourceCollection.model_validate(collection.model_dump(mode="json"))
        if notice is None or any(o.collector != notice.producer for o in collection.observations):
            raise NoticeIngestionError("producer_mismatch")
    inventory = result.inventory
    selection = asdict(notice.selection) if notice is not None else None
    return canonical_json({"inventory": asdict(inventory),
        "collection": collection.model_dump(mode="json") if collection is not None else None,
        "producer": notice.producer.model_dump(mode="json") if notice is not None else None,
        "selection": selection,
        "git_revision": result.revision if isinstance(result, GitScanSessionResult) else None,
        "git_runtime": asdict(result.runtime_identity) if isinstance(result, GitScanSessionResult) else None,
        "git_omissions": [asdict(o) for o in result.omissions] if isinstance(result, GitScanSessionResult) else None,
        "git_discovered_entries": result.discovered_entries if isinstance(result, GitScanSessionResult) else None})


def validate_completed_ingestion(value: CompletedNoticeIngestion) -> ScanSessionResult:
    if type(value) is not CompletedNoticeIngestion:
        raise NoticeIngestionError("completion_invalid")
    try:
        return value._verify(value)
    except (TypeError, AttributeError, ValueError, RecursionError) as error:
        raise NoticeIngestionError("completion_invalid") from error


class _BoundedDigestReader:
    """Same-fd sequential stream; empty short reads are EOF, not read(0)."""
    def __init__(self, raw, *, expected_size: int, max_bytes: int):
        if type(expected_size) is not int or expected_size <= 0 or type(max_bytes) is not int or max_bytes <= 0:
            raise NoticeIngestionError("input_limit_invalid")
        self.raw, self.expected_size, self.max_bytes = raw, expected_size, max_bytes
        self.count = 0; self.eof = False; self._digest = hashlib.sha256()

    def read(self, size=-1):
        if type(size) is not int or size < 0:
            raise NoticeIngestionError("unbounded_input_read")
        if size == 0:
            return b""
        # A one-byte probe distinguishes true EOF from an over-budget stream.
        amount = min(size, _CHUNK, max(1, self.max_bytes - self.count + 1))
        data = self.raw.read(amount)
        if type(data) is not bytes or len(data) > amount:
            raise NoticeIngestionError("input_read_invalid")
        if not data:
            self.eof = True
            if self.count != self.expected_size:
                raise NoticeIngestionError("input_early_eof")
            return data
        if self.eof:
            raise NoticeIngestionError("input_after_eof")
        self.count += len(data)
        if self.count > self.max_bytes or self.count > self.expected_size:
            raise NoticeIngestionError("input_limit_exceeded")
        self._digest.update(data)
        return data

    def verify(self, expected_digest):
        if (not self.eof or self.count != self.expected_size or self.count > self.max_bytes
                or self._digest.hexdigest() != expected_digest):
            raise NoticeIngestionError("input_digest_mismatch")


def _file_identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_uid, info.st_mode, info.st_nlink)


def _open_input(archive_path: Path, upload_root: Path, max_bytes: int):
    if (not isinstance(archive_path, Path) or not isinstance(upload_root, Path)
            or not archive_path.is_absolute() or not upload_root.is_absolute()
            or archive_path.parent != upload_root or archive_path.name in {"", ".", ".."}):
        raise NoticeIngestionError("input_path_invalid")
    if ".." in upload_root.parts:
        raise NoticeIngestionError("input_root_invalid")
    # Walk each component by held directory descriptor, including ancestors.
    # Checking Path.is_symlink then opening an absolute path would leave a race.
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    directory = os.open("/", flags)
    fd = None
    try:
        for component in upload_root.parts[1:]:
            child = os.open(component, flags, dir_fd=directory)
            try:
                os.close(directory)
            except BaseException:
                os.close(child)
                raise
            directory = child
        root = os.fstat(directory)
        if not stat.S_ISDIR(root.st_mode) or root.st_uid != os.geteuid() or root.st_mode & 0o077:
            raise NoticeIngestionError("input_root_invalid")
        named = os.stat(archive_path.name, dir_fd=directory, follow_symlinks=False)
        fd = os.open(archive_path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077
                or info.st_nlink != 1 or not 0 < info.st_size <= max_bytes
                or _file_identity(named) != _file_identity(info)):
            raise NoticeIngestionError("input_file_invalid")
        os.close(directory); directory = None
        raw = os.fdopen(fd, "rb", buffering=0); fd = None
        return raw, info
    finally:
        if fd is not None: os.close(fd)
        if directory is not None: os.close(directory)


def _close_input(raw):
    raw.close()


def _consumer(dependencies, notice_consumer, limits, identity):
    produced = []
    def consume(session):
        if produced or not isinstance(session, ReadOnlyScanSession):
            raise NoticeIngestionError("consumer_identity_invalid")
        session.inventory; session.remaining_read_bytes  # live, current-thread capability
        original = dependencies(session)
        notice = None
        try:
            notice = notice_consumer(session, limits)
            if notice is not None and type(notice) is not CollectedNotice:
                raise NoticeIngestionError("notice_result_invalid")
            if notice is not None and notice.collection is not None:
                validated = NoticeSourceCollection.model_validate(notice.collection.model_dump(mode="json"))
                if any(o.collector != notice.producer for o in validated.observations):
                    raise NoticeIngestionError("producer_mismatch")
        except Exception:
            # Original ingestion still checks its sticky session safety failure.
            notice = None
        envelope = NoticeDependencyResult(original, notice)
        produced.append(envelope)
        return envelope
    def finish(result):
        # This invocation's private callback channel cannot be replaced by a
        # caller-owned result list/hash. Only the wrapper calls this closure,
        # after all genuine ingestion/input/service finalizers have returned.
        if len(produced) != 1 or result.consumer_result is not produced[0]:
            raise NoticeIngestionError("completion_callback_mismatch")
        envelope = produced[0]
        seal = hashlib.sha256(_snapshot(result)).digest()
        proof = object.__new__(CompletedNoticeIngestion)
        def verify(candidate):
            if (candidate is not proof or candidate.result is not result
                    or result.consumer_result is not envelope
                    or (candidate.scan_id, candidate.source, candidate.source_type, candidate.input_digest) != identity
                    or hashlib.sha256(_snapshot(result)).digest() != seal):
                raise NoticeIngestionError("completion_seal_mismatch")
            return result
        for key, value in zip(CompletedNoticeIngestion.__slots__, (*identity, result, verify), strict=True):
            object.__setattr__(proof, key, value)
        return proof
    return consume, finish


def _limits(service, requested):
    if isinstance(service, ZipIngestionService):
        single = service.limits.effective_scan_single_file_read_max_bytes
    else:
        single = service.limits.scan_single_file_read_max_bytes
    single, total = effective_limits(requested, single=single, total=service.limits.scan_total_read_max_bytes)
    return ScanReadLimits(single_file_max_bytes=single, total_max_bytes=total)


def _arguments(scan_id, expected_input_digest, dependency_consumer, notice_consumer):
    if (type(scan_id) is not str or not scan_id or type(expected_input_digest) is not str
            or not _SHA.fullmatch(expected_input_digest) or not callable(dependency_consumer)
            or not callable(notice_consumer)):
        raise NoticeIngestionError("completion_arguments_invalid")


def complete_zip_ingestion(service: ZipIngestionService, *, archive_path: Path,
        upload_root: Path, scan_id: str, expected_input_digest: str,
        dependency_consumer: Callable, notice_consumer: Callable,
        read_limits: ScanReadLimits, tree_consumer=None) -> CompletedNoticeIngestion:
    raw = None
    try:
        _arguments(scan_id, expected_input_digest, dependency_consumer, notice_consumer)
        if not isinstance(service, ZipIngestionService):
            raise NoticeIngestionError("ingestion_service_invalid")
        limits = _limits(service, read_limits)
        consume, finish = _consumer(dependency_consumer, notice_consumer, limits,
            (scan_id, archive_path.name, "zip", expected_input_digest))
        raw, before = _open_input(archive_path, upload_root, service.limits.upload_max_bytes)
        reader = _BoundedDigestReader(raw, expected_size=before.st_size, max_bytes=service.limits.upload_max_bytes)
        options = {"tree_consumer": tree_consumer} if tree_consumer is not None else {}
        result = service.ingest_with_consumer(reader, consume, read_limits=read_limits, **options)
        reader.verify(expected_input_digest)
        if _file_identity(os.fstat(raw.fileno())) != _file_identity(before):
            raise NoticeIngestionError("input_identity_changed")
        if type(result) is not ScanSessionResult:
            raise NoticeIngestionError("completion_callback_mismatch")
    finally:
        try:
            if raw is not None: _close_input(raw)
        finally:
            service.close()
    # Neither a potentially failing close nor cleanup remains after issuance.
    return finish(result)


def complete_git_ingestion(service: GitIngestionService, *, source: str,
        scan_id: str, expected_input_digest: str, dependency_consumer: Callable,
        notice_consumer: Callable, read_limits: ScanReadLimits, tree_consumer=None) -> CompletedNoticeIngestion:
    try:
        _arguments(scan_id, expected_input_digest, dependency_consumer, notice_consumer)
        if not isinstance(service, GitIngestionService) or type(source) is not str:
            raise NoticeIngestionError("ingestion_service_invalid")
        if hashlib.sha256(source.encode("utf-8")).hexdigest() != expected_input_digest:
            raise NoticeIngestionError("input_digest_mismatch")
        consume, finish = _consumer(dependency_consumer, notice_consumer, _limits(service, read_limits),
            (scan_id, source, "git", expected_input_digest))
        options = {"tree_consumer": tree_consumer} if tree_consumer is not None else {}
        result = service.ingest_with_consumer(source, consume, read_limits=read_limits, **options)
        if type(result) is not GitScanSessionResult:
            raise NoticeIngestionError("completion_callback_mismatch")
    finally:
        service.close()
    return finish(result)


__all__ = ["CollectedNotice", "NoticeDependencyResult", "CompletedNoticeIngestion",
           "complete_zip_ingestion", "complete_git_ingestion", "validate_completed_ingestion"]
