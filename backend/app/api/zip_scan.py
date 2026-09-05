"""Bounded multipart staging and in-process A4-1 execution for ZIP scans."""

from __future__ import annotations

import hashlib
import math
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

from app.ai import Provider
from app.api.models import ScanCreateAccepted, ZipScanCreateFields
from app.api.service import ApiError, ScanApiService
from app.persistence import (
    SQLiteScanRunRegistry,
    ZipDispatchDescriptor,
    ZipDispatchError,
    ZipDispatchReservation,
    ZipDispatchStore,
    ZipExecutionProfile,
)
from app.pipeline import ScanPipelineWorker, build_local_zip_dependency_plan
from app.reporting import PipelineReportPublisher
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
        report_publisher: PipelineReportPublisher | None = None,
        ai_provider: Provider | None = None,
        ai_enabled: bool = False,
        ai_timeout_seconds: float = 10.0,
        dispatch_store: ZipDispatchStore | None = None,
    ) -> None:
        if (
            not isinstance(registry, SQLiteScanRunRegistry)
            or (clock is not None and not callable(clock))
            or (report_publisher is not None and type(report_publisher) is not PipelineReportPublisher)
            or type(ai_enabled) is not bool
            or type(ai_timeout_seconds) not in {int, float}
            or isinstance(ai_timeout_seconds, bool)
            or not math.isfinite(ai_timeout_seconds)
            or ai_timeout_seconds <= 0
            or (ai_enabled and ai_provider is None)
            or (dispatch_store is not None and type(dispatch_store) is not ZipDispatchStore)
        ):
            raise ValueError("invalid zip runtime")
        self._registry = registry
        self._upload_root = _validate_private_root(upload_root)
        self._workspace_root = _validate_private_root(workspace_root)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._upload_max_bytes = ZipSafetyLimits().upload_max_bytes
        self._report_publisher = report_publisher
        self._ai_provider = ai_provider
        self._ai_enabled = ai_enabled
        self._ai_timeout_seconds = float(ai_timeout_seconds)
        self._dispatch_store = dispatch_store
        if dispatch_store is not None and dispatch_store.upload_root != self._upload_root:
            raise ValueError("dispatch store upload root must match ZIP runtime")

    def reserve_upload_capacity(self) -> ZipDispatchReservation | None:
        """Reserve before ``request.form()`` is allowed to consume one body byte."""

        store = self._dispatch_store
        if store is None:
            return None
        try:
            return store.reserve_upload()
        except ZipDispatchError as error:
            if error.code == "dispatch_capacity_exceeded":
                raise _api_error(
                    status_code=500,
                    code="internal_error",
                    message="ZIP upload capacity is unavailable.",
                    reason="dispatch_capacity_exceeded",
                ) from None
            raise _api_error(
                status_code=500,
                code="internal_error",
                message="ZIP upload capacity is unavailable.",
                reason="dispatch_storage_failure",
            ) from None

    @staticmethod
    def release_upload_capacity(reservation: ZipDispatchReservation | None) -> None:
        if reservation is not None:
            reservation.release()

    async def submit(
        self,
        upload: UploadFile,
        fields: ZipScanCreateFields,
        service: ScanApiService,
        background_tasks: BackgroundTasks,
        reservation: ZipDispatchReservation | None = None,
    ) -> ScanCreateAccepted:
        if not isinstance(upload, UploadFile) or type(fields) is not ZipScanCreateFields:
            raise _api_error(status_code=422, code="invalid_archive", message="ZIP upload is invalid.", reason="request_invalid")
        if upload.content_type not in _CONTENT_TYPES:
            raise _api_error(status_code=422, code="invalid_archive", message="ZIP upload is invalid.", reason="content_type_invalid")
        project_name = _project_name(upload.filename)
        store = self._dispatch_store
        if store is not None and reservation is None:
            raise _api_error(
                status_code=500,
                code="internal_error",
                message="ZIP upload could not be prepared.",
                reason="dispatch_reservation_required",
            )
        archive_path, digest = await self._stage(upload, reservation=reservation)
        if store is None:
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
        try:
            candidate = service.build_zip_scan_candidate(
                fields,
                staged_name=archive_path.name,
                project_name=project_name,
                input_digest=digest,
            )
        except Exception:
            self._remove(archive_path)
            raise

        try:
            profile = ZipExecutionProfile.from_provider(
                ai_requested=self._ai_enabled,
                provider=self._ai_provider,
                ai_timeout_seconds=self._ai_timeout_seconds,
            )
        except ZipDispatchError:
            # No descriptor exists at this point, so this owned staging file is
            # still safe to remove before the request's finally releases it.
            self._remove(archive_path)
            raise _api_error(
                status_code=500,
                code="internal_error",
                message="ZIP upload could not be prepared.",
                reason="dispatch_storage_failure",
            ) from None
        descriptor: ZipDispatchDescriptor
        try:
            with store.operation():
                descriptor = store.prepare(archive_path, candidate.run, profile, reservation)
                store.checkpoint("after_prepared_before_registry")
                accepted, created = service.commit_zip_scan_candidate(candidate)
                if created:
                    try:
                        durable = self._registry.get(accepted.scan_id).run
                    except Exception:
                        raise _api_error(
                            status_code=500,
                            code="internal_error",
                            message="ZIP upload could not be prepared.",
                            reason="dispatch_storage_failure",
                        ) from None
                    if durable != candidate.run:
                        raise _api_error(
                            status_code=500,
                            code="internal_error",
                            message="ZIP upload could not be prepared.",
                            reason="dispatch_storage_failure",
                        )
                    store.checkpoint("after_registry_before_ready")
                    store.promote(descriptor)
                    return accepted
                try:
                    store.discard_prepared(descriptor, archive_path, reservation)
                except ZipDispatchError:
                    # The registry has already committed the idempotent answer.
                    # Preserve that original ID/profile and retain the loser for
                    # bounded capacity accounting rather than turn it into 500.
                    pass
                return accepted
        except ApiError as error:
            if error.reason == "idempotency_conflict":
                try:
                    # The live reservation token proves this is exactly this
                    # request's prepared loser; do not leave its ZIP behind.
                    store.discard_prepared(descriptor, archive_path, reservation)
                except ZipDispatchError:
                    # The registry has already determined the public result.
                    # Preserve its 409 and leave this proven input/descriptor
                    # pair for bounded future cleanup and capacity accounting.
                    pass
                raise
            raise
        except ZipDispatchError:
            # After an attempted prepared write, leave the descriptor and input
            # for I2 rather than risk a dangling/partially deleted pair.
            raise _api_error(
                status_code=500,
                code="internal_error",
                message="ZIP upload could not be prepared.",
                reason="dispatch_storage_failure",
            ) from None
        raise AssertionError("unreachable")

    async def _stage(
        self,
        upload: UploadFile,
        *,
        reservation: ZipDispatchReservation | None = None,
    ) -> tuple[Path, str]:
        file_descriptor: int | None = None
        archive_path: Path | None = None
        digest = hashlib.sha256()
        received = 0
        completed = False
        try:
            store = self._dispatch_store
            if store is not None:
                if reservation is None:
                    raise OSError("missing reservation")
                # ``reserve_upload`` rescans the private directory under the
                # same store lock.  Binding the generated name before that
                # lock is released prevents another request from mistaking
                # this in-flight file for a persistent input.
                with store.operation():
                    file_descriptor, rendered = tempfile.mkstemp(
                        prefix="openguard-upload-",
                        suffix=".zip",
                        dir=self._upload_root,
                    )
                    archive_path = Path(rendered)
                    info = os.fstat(file_descriptor)
                    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                        raise OSError("unsafe staged file")
                    store.bind_upload(reservation, archive_path)
            else:
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
            self._fsync_directory(self._upload_root)
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
                ai_provider=self._ai_provider,
                ai_enabled=self._ai_enabled,
                ai_timeout_seconds=self._ai_timeout_seconds,
            )
            publisher = self._report_publisher
            ScanPipelineWorker(
                self._registry,
                clock=self._clock,
                terminal_publisher=publisher.publish if publisher is not None else None,
            ).run(scan_id, plan)
        finally:
            self._remove(archive_path)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor: int | None = None
        try:
            descriptor = os.open(
                path,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            )
            os.fsync(descriptor)
        except OSError:
            raise _api_error(
                status_code=500,
                code="internal_error",
                message="ZIP upload could not be staged.",
                reason="upload_staging_failed",
            ) from None
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass

    @staticmethod
    def _remove(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


__all__ = ["MULTIPART_REQUEST_MAX_BYTES", "RequestBodyTooLarge", "ZipScanRuntime"]
