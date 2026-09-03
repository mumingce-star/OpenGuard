"""Bounded multipart staging and in-process A4-1 execution for ZIP scans."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import unicodedata
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

from fastapi import BackgroundTasks
from starlette.datastructures import UploadFile

from app.api.models import ScanCreateAccepted, ZipScanCreateFields
from app.api.service import ApiError, ScanApiService
from app.persistence import SQLiteScanRunRegistry
from app.pipeline import ScanPipelineWorker, build_local_zip_dependency_plan
from app.security.limits import ZipSafetyLimits


_CHUNK_SIZE = 64 * 1024
_CONTENT_TYPES = frozenset({"application/octet-stream", "application/x-zip-compressed", "application/zip"})
MULTIPART_REQUEST_MAX_BYTES = ZipSafetyLimits().upload_max_bytes + 64 * 1024


class RequestBodyTooLarge(RuntimeError):
    pass


def _api_error(*, status_code: int, code: str, message: str, reason: str) -> ApiError:
    return ApiError(status_code=status_code, code=code, message=message, reason=reason)


def _validate_private_root(path: Path) -> Path:
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError("zip runtime root must be absolute")
    try:
        info = path.lstat()
    except OSError as error:
        raise ValueError("zip runtime root is unavailable") from error
    if (
        os.name != "posix"
        or stat.S_ISLNK(info.st_mode)
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("zip runtime root must be a private POSIX directory")
    return path


def _project_name(filename: object) -> str:
    if type(filename) is not str or not filename or filename != filename.strip():
        raise _api_error(status_code=422, code="invalid_archive", message="ZIP upload is invalid.", reason="filename_invalid")
    decoded = unquote(filename)
    if "/" in decoded or "\\" in decoded or decoded in {".", ".."}:
        raise _api_error(status_code=422, code="invalid_archive", message="ZIP upload is invalid.", reason="filename_invalid")
    if any(unicodedata.category(character) == "Cc" for character in decoded):
        raise _api_error(status_code=422, code="invalid_archive", message="ZIP upload is invalid.", reason="filename_invalid")
    try:
        encoded = filename.encode("utf-8")
    except UnicodeEncodeError:
        raise _api_error(status_code=422, code="invalid_archive", message="ZIP upload is invalid.", reason="filename_invalid")
    if len(encoded) > 255 or not filename.lower().endswith(".zip"):
        raise _api_error(status_code=422, code="invalid_archive", message="ZIP upload is invalid.", reason="filename_invalid")
    name = decoded[:-4]
    if not name:
        raise _api_error(status_code=422, code="invalid_archive", message="ZIP upload is invalid.", reason="filename_invalid")
    return name[:200]


class ZipScanRuntime:
    """Stage one upload, create one durable run, then execute A4-1 after response."""

    def __init__(
        self,
        registry: SQLiteScanRunRegistry,
        *,
        upload_root: Path,
        workspace_root: Path,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(registry, SQLiteScanRunRegistry) or (clock is not None and not callable(clock)):
            raise ValueError("invalid zip runtime")
        self._registry = registry
        self._upload_root = _validate_private_root(upload_root)
        self._workspace_root = _validate_private_root(workspace_root)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._upload_max_bytes = ZipSafetyLimits().upload_max_bytes

    async def submit(
        self,
        upload: UploadFile,
        fields: ZipScanCreateFields,
        service: ScanApiService,
        background_tasks: BackgroundTasks,
    ) -> ScanCreateAccepted:
        if not isinstance(upload, UploadFile) or type(fields) is not ZipScanCreateFields:
            raise _api_error(status_code=422, code="invalid_archive", message="ZIP upload is invalid.", reason="request_invalid")
        if upload.content_type not in _CONTENT_TYPES:
            raise _api_error(status_code=422, code="invalid_archive", message="ZIP upload is invalid.", reason="content_type_invalid")
        project_name = _project_name(upload.filename)
        archive_path, digest = await self._stage(upload)
        try:
            accepted, created = service.create_zip_scan(
                fields,
                staged_name=archive_path.name,
                project_name=project_name,
                input_digest=digest,
            )
        except Exception:
            self._remove(archive_path)
            raise
        if not created:
            self._remove(archive_path)
            return accepted
        background_tasks.add_task(self._execute, accepted.scan_id, archive_path)
        return accepted

    async def _stage(self, upload: UploadFile) -> tuple[Path, str]:
        file_descriptor: int | None = None
        archive_path: Path | None = None
        digest = hashlib.sha256()
        received = 0
        completed = False
        try:
            file_descriptor, rendered = tempfile.mkstemp(
                prefix="openguard-upload-",
                suffix=".zip",
                dir=self._upload_root,
            )
            archive_path = Path(rendered)
            info = os.fstat(file_descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise OSError("unsafe staged file")
            while True:
                chunk = await upload.read(_CHUNK_SIZE)
                if not chunk:
                    break
                if type(chunk) is not bytes:
                    raise OSError("invalid upload stream")
                received += len(chunk)
                if received > self._upload_max_bytes:
                    raise _api_error(
                        status_code=413,
                        code="archive_limit_exceeded",
                        message="ZIP upload exceeds the configured limit.",
                        reason="archive_upload_size_limit",
                    )
                digest.update(chunk)
                view = memoryview(chunk)
                while view:
                    written = os.write(file_descriptor, view)
                    if written <= 0:
                        raise OSError("short write")
                    view = view[written:]
            if received == 0:
                raise _api_error(status_code=422, code="invalid_archive", message="ZIP upload is invalid.", reason="archive_empty")
            os.fsync(file_descriptor)
            os.close(file_descriptor)
            file_descriptor = None
            completed = True
            return archive_path, digest.hexdigest()
        except ApiError:
            raise
        except Exception:
            raise _api_error(status_code=500, code="internal_error", message="ZIP upload could not be staged.", reason="upload_staging_failed")
        finally:
            if file_descriptor is not None:
                try:
                    os.close(file_descriptor)
                except OSError:
                    pass
            if archive_path is not None and not completed:
                self._remove(archive_path)

    def _execute(self, scan_id: str, archive_path: Path) -> None:
        try:
            plan = build_local_zip_dependency_plan(
                archive_path,
                self._workspace_root,
                clock=self._clock,
            )
            ScanPipelineWorker(self._registry, clock=self._clock).run(scan_id, plan)
        finally:
            self._remove(archive_path)

    @staticmethod
    def _remove(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


__all__ = ["MULTIPART_REQUEST_MAX_BYTES", "RequestBodyTooLarge", "ZipScanRuntime"]
