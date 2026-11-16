"""Private, integrity-checked persistence for rendered report artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.domain.models import HashValue, ReportFormat, ReportLink, ScanRun
from app.reporting.render import ReportArtifact, render_report


REPORT_STORE_SCHEMA = "openguard.report-artifact"
REPORT_STORE_VERSION = 1
MAX_REPORT_BYTES = 16 * 1024 * 1024

_SCAN_ID = re.compile(
    r"^scn_(?:[0-9a-hjkmnp-tv-z]{26}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$"
)
_MEDIA_TYPES = {
    ReportFormat.HTML: "text/html; charset=utf-8",
    ReportFormat.JSON: "application/json; charset=utf-8",
    ReportFormat.CSV: "text/csv; charset=utf-8",
    ReportFormat.RESOURCE_INVENTORY: "text/csv; charset=utf-8",
}
_EXTENSIONS = {
    ReportFormat.HTML: "html",
    ReportFormat.JSON: "json",
    ReportFormat.CSV: "csv",
    ReportFormat.RESOURCE_INVENTORY: "resources.csv",
}
_METADATA_KEYS = {
    "schema",
    "version",
    "scan_id",
    "format",
    "media_type",
    "filename",
    "size_bytes",
    "link",
}


class ReportStoreError(RuntimeError):
    """Stable, non-sensitive storage failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class StoredReport:
    """Verified bytes and public metadata returned by the private store."""

    link: ReportLink
    media_type: str
    filename: str
    content: bytes


def _fail(code: str) -> None:
    raise ReportStoreError(code) from None


def _reject_constant(_: str) -> None:
    raise ValueError("non-finite number")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _validate_scan_id(value: object) -> str:
    if type(value) is not str or _SCAN_ID.fullmatch(value) is None:
        _fail("report_store_invalid_argument")
    return value


def _validate_format(value: object) -> ReportFormat:
    if type(value) is not ReportFormat:
        _fail("report_store_invalid_argument")
    return value


def _validate_generated_at(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        _fail("report_store_invalid_argument")
    return value.astimezone(timezone.utc)


def _expected_filename(scan_id: str, report_format: ReportFormat) -> str:
    return f"openguard-{scan_id}.{_EXTENSIONS[report_format]}"


def _expected_href(scan_id: str, report_format: ReportFormat) -> str:
    return f"api/v1/scans/{scan_id}/report?format={report_format.value}&download=true"


class ReportArtifactStore:
    """Persist reports below a private server-owned directory.

    Metadata is committed after the content file, so an interrupted publication
    is never visible as a valid report. Reads re-check type, ownership,
    permissions, size and SHA-256 before returning any bytes.
    """

    def __init__(
        self,
        root: Path,
        *,
        clock: Callable[[], datetime] | None = None,
        max_report_bytes: int = MAX_REPORT_BYTES,
    ) -> None:
        if (
            not isinstance(root, Path)
            or not root.is_absolute()
            or type(max_report_bytes) is not int
            or not 1 <= max_report_bytes <= MAX_REPORT_BYTES
        ):
            _fail("report_store_invalid_argument")
        self._root = root
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._max_report_bytes = max_report_bytes
        self._lock = threading.RLock()
        self._validate_private_directory(root, code="report_store_path_invalid")

    @staticmethod
    def _validate_private_directory(path: Path, *, code: str) -> os.stat_result:
        try:
            info = path.lstat()
        except (OSError, ValueError):
            _fail(code)
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            _fail(code)
        return info

    @staticmethod
    def _validate_existing_file(path: Path) -> os.stat_result | None:
        try:
            info = path.lstat()
        except FileNotFoundError:
            return None
        except OSError:
            _fail("report_store_io_failed")
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            _fail("report_store_corrupt")
        return info

    def _scan_directory(self, scan_id: str, *, create: bool) -> Path:
        self._validate_private_directory(self._root, code="report_store_path_invalid")
        directory = self._root / scan_id
        if create:
            try:
                directory.mkdir(mode=0o700, exist_ok=True)
            except OSError:
                _fail("report_store_io_failed")
        else:
            try:
                directory.lstat()
            except FileNotFoundError:
                _fail("report_store_not_found")
            except OSError:
                _fail("report_store_io_failed")
        self._validate_private_directory(directory, code="report_store_corrupt")
        return directory

    @staticmethod
    def _metadata_path(directory: Path, report_format: ReportFormat) -> Path:
        return directory / f"{report_format.value}.metadata.json"

    @staticmethod
    def _content_path(directory: Path, report_format: ReportFormat, digest: str) -> Path:
        return directory / f"{report_format.value}-{digest}.artifact"

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(directory, flags)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError:
            _fail("report_store_io_failed")

    @classmethod
    def _atomic_write(cls, path: Path, content: bytes) -> None:
        cls._validate_existing_file(path)
        temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
        descriptor: int | None = None
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            view = memoryview(content)
            offset = 0
            while offset < len(view):
                written = os.write(descriptor, view[offset:])
                if written <= 0:
                    raise OSError("short write")
                offset += written
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = None
            os.replace(temporary, path)
            cls._fsync_directory(path.parent)
        except ReportStoreError:
            raise
        except OSError:
            _fail("report_store_io_failed")
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def _read_file(self, path: Path, *, maximum: int) -> bytes:
        expected = self._validate_existing_file(path)
        if expected is None:
            _fail("report_store_not_found")
        if expected.st_size > maximum:
            _fail("report_store_corrupt")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
            try:
                actual = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(actual.st_mode)
                    or actual.st_uid != os.geteuid()
                    or stat.S_IMODE(actual.st_mode) != 0o600
                    or (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino)
                    or actual.st_size > maximum
                ):
                    _fail("report_store_corrupt")
                chunks: list[bytes] = []
                remaining = actual.st_size
                while remaining:
                    chunk = os.read(descriptor, min(65_536, remaining))
                    if not chunk:
                        _fail("report_store_corrupt")
                    chunks.append(chunk)
                    remaining -= len(chunk)
                if os.read(descriptor, 1):
                    _fail("report_store_corrupt")
                return b"".join(chunks)
            finally:
                os.close(descriptor)
        except ReportStoreError:
            raise
        except OSError:
            _fail("report_store_io_failed")
        raise AssertionError("unreachable")

    @staticmethod
    def _metadata_bytes(scan_id: str, artifact: ReportArtifact, link: ReportLink) -> bytes:
        payload = {
            "schema": REPORT_STORE_SCHEMA,
            "version": REPORT_STORE_VERSION,
            "scan_id": scan_id,
            "format": artifact.format.value,
            "media_type": artifact.media_type,
            "filename": artifact.filename,
            "size_bytes": len(artifact.content),
            "link": link.model_dump(mode="json"),
        }
        return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")

    def publish(
        self,
        run: ScanRun,
        report_format: ReportFormat,
        *,
        generated_at: datetime | None = None,
    ) -> ReportLink:
        """Render and atomically publish one format; equivalent repeats are idempotent."""

        if type(run) is not ScanRun:
            _fail("report_store_invalid_argument")
        valid_format = _validate_format(report_format)
        timestamp = _validate_generated_at(self._clock() if generated_at is None else generated_at)
        artifact = render_report(run, valid_format)
        if len(artifact.content) > self._max_report_bytes:
            _fail("report_store_size_exceeded")
        scan_id = _validate_scan_id(run.id)
        link = ReportLink(
            format=valid_format,
            href=_expected_href(scan_id, valid_format),
            content_hash=HashValue(algorithm="sha256", value=artifact.sha256),
            generated_at=timestamp,
        )

        with self._lock:
            directory = self._scan_directory(scan_id, create=True)
            metadata_path = self._metadata_path(directory, valid_format)
            try:
                existing = self.get(scan_id, valid_format)
            except ReportStoreError as error:
                if error.code not in {"report_store_not_found"}:
                    raise
            else:
                if existing.content == artifact.content:
                    return existing.link

            content_path = self._content_path(directory, valid_format, artifact.sha256)
            self._atomic_write(content_path, artifact.content)
            self._atomic_write(metadata_path, self._metadata_bytes(scan_id, artifact, link))
            published = self.get(scan_id, valid_format)
            if published.link != link or published.content != artifact.content:
                _fail("report_store_corrupt")
            return published.link

    def get(self, scan_id: str, report_format: ReportFormat) -> StoredReport:
        """Read and verify one published report without changing store state."""

        valid_scan_id = _validate_scan_id(scan_id)
        valid_format = _validate_format(report_format)
        with self._lock:
            directory = self._scan_directory(valid_scan_id, create=False)
            metadata_path = self._metadata_path(directory, valid_format)
            raw_metadata = self._read_file(metadata_path, maximum=32_768)
            try:
                payload = json.loads(
                    raw_metadata.decode("utf-8"),
                    object_pairs_hook=_pairs,
                    parse_constant=_reject_constant,
                )
                if type(payload) is not dict or set(payload) != _METADATA_KEYS:
                    raise ValueError("metadata shape")
                if (
                    payload["schema"] != REPORT_STORE_SCHEMA
                    or payload["version"] != REPORT_STORE_VERSION
                    or payload["scan_id"] != valid_scan_id
                    or payload["format"] != valid_format.value
                    or payload["media_type"] != _MEDIA_TYPES[valid_format]
                    or payload["filename"] != _expected_filename(valid_scan_id, valid_format)
                    or type(payload["size_bytes"]) is not int
                    or not 0 <= payload["size_bytes"] <= self._max_report_bytes
                ):
                    raise ValueError("metadata values")
                link = ReportLink.model_validate(payload["link"])
            except Exception:
                _fail("report_store_corrupt")
            if (
                link.format is not valid_format
                or link.href != _expected_href(valid_scan_id, valid_format)
            ):
                _fail("report_store_corrupt")
            content_path = self._content_path(directory, valid_format, link.content_hash.value)
            try:
                content = self._read_file(content_path, maximum=self._max_report_bytes)
            except ReportStoreError as error:
                if error.code == "report_store_not_found":
                    _fail("report_store_corrupt")
                raise
            if len(content) != payload["size_bytes"] or hashlib.sha256(content).hexdigest() != link.content_hash.value:
                _fail("report_store_corrupt")
            return StoredReport(
                link=link,
                media_type=payload["media_type"],
                filename=payload["filename"],
                content=content,
            )


__all__ = [
    "MAX_REPORT_BYTES",
    "REPORT_STORE_SCHEMA",
    "REPORT_STORE_VERSION",
    "ReportArtifactStore",
    "ReportStoreError",
    "StoredReport",
]
