"""Single-process I2 recovery and dispatch for durable local ZIP scans.

This module owns only the lifecycle lock and the dispatcher thread.  It
intentionally reuses the frozen registry, A4 worker, local-ZIP plan and report
publisher; it neither changes the registry schema nor retries a claimed
pipeline execution.
"""

from __future__ import annotations

import errno
import fcntl
import os
import stat
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from app.ai import Provider
from app.domain.models import ScanError, ScanRun, ScanStage, ScanStatus, SourceType
from app.persistence import (
    SQLiteScanRunRegistry,
    ScanRegistryError,
    StoredScanRun,
    ZipDispatchDescriptor,
    ZipDispatchError,
    ZipDispatchStore,
    ZipExecutionProfile,
    run_identity_sha256,
)
from app.pipeline.local_zip import build_local_zip_dependency_plan
from app.pipeline.worker import PipelineError, ScanPipelineWorker
from app.reporting import PipelineReportPublisher


_LOCK_NAME = ".openguard-zip-dispatch.lock"
_CYCLE_SECONDS = 1.0
_BUSY_DELAYS = (0.1, 0.5)
_TERMINAL = frozenset(
    {ScanStatus.COMPLETED, ScanStatus.PARTIAL, ScanStatus.FAILED, ScanStatus.CANCELLED}
)


class ZipDispatcherError(RuntimeError):
    """Internal lifecycle failures which are never exposed by the HTTP API."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _PreClaimBusy(BaseException):
    """Escape worker error mapping only for a known, pre-claim SQLite busy."""


class _PreClaimRegistry(SQLiteScanRunRegistry):
    """A minimal type-compatible view which observes only worker's first CAS.

    ``ScanPipelineWorker`` deliberately accepts only ``SQLiteScanRunRegistry``.
    The subclass forwards to the one real registry and never creates a second
    connection.  It changes only an explicit ``registry_busy`` before the
    queued->running claim into a private control signal.  Once that claim was
    attempted, every registry condition keeps the worker's existing behavior.
    """

    def __init__(
        self,
        registry: SQLiteScanRunRegistry,
        queued: StoredScanRun,
        *,
        wait_busy: Callable[[float], bool],
    ) -> None:
        self._delegate = registry
        self._scan_id = queued.run.id
        self._revision = queued.revision
        self._pre_claim = True
        self._wait_busy = wait_busy
        self._busy_events = 0

    def _call_while_preclaim(self, operation: Callable[[], StoredScanRun]) -> StoredScanRun:
        while True:
            try:
                return operation()
            except ScanRegistryError as error:
                if error.code != "registry_busy":
                    raise
                if self._busy_events >= 2:
                    raise _PreClaimBusy from None
                delay = _BUSY_DELAYS[self._busy_events]
                self._busy_events += 1
                if not self._wait_busy(delay):
                    raise _PreClaimBusy from None

    def get(self, scan_id: str) -> StoredScanRun:
        if self._pre_claim:
            return self._call_while_preclaim(lambda: self._delegate.get(scan_id))
        return self._delegate.get(scan_id)

    def replace(self, run: ScanRun, *, expected_revision: int) -> StoredScanRun:
        is_claim = (
            self._pre_claim
            and run.id == self._scan_id
            and expected_revision == self._revision
            and run.status is ScanStatus.RUNNING
            and run.stage is ScanStage.INGESTION
            and run.progress == 5
        )
        if not is_claim:
            return self._delegate.replace(run, expected_revision=expected_revision)
        try:
            return self._call_while_preclaim(
                lambda: self._delegate.replace(run, expected_revision=expected_revision)
            )
        finally:
            self._pre_claim = False


def _descriptor_matches(descriptor: ZipDispatchDescriptor, run: ScanRun) -> bool:
    return (
        descriptor.scan_id == run.id
        and run.project.source_type is SourceType.ZIP
        and descriptor.upload_name == run.project.source
        and descriptor.input_sha256 == run.provenance.input_digest.value
        and descriptor.run_identity_sha256 == run_identity_sha256(run)
    )


class ZipDispatcher:
    """Hold one local lifecycle lock and consume one ZIP at a time."""

    def __init__(
        self,
        registry: SQLiteScanRunRegistry,
        store: ZipDispatchStore,
        *,
        data_dir: Path,
        workspace_root: Path,
        clock: Callable[[], datetime] | None = None,
        report_publisher: PipelineReportPublisher | None = None,
        ai_provider: Provider | None = None,
        ai_enabled: bool = False,
        ai_timeout_seconds: float = 10.0,
    ) -> None:
        if (
            not isinstance(registry, SQLiteScanRunRegistry)
            or type(store) is not ZipDispatchStore
            or not isinstance(data_dir, Path)
            or not isinstance(workspace_root, Path)
            or (clock is not None and not callable(clock))
            or (report_publisher is not None and type(report_publisher) is not PipelineReportPublisher)
            or type(ai_enabled) is not bool
            or (ai_enabled and ai_provider is None)
            or type(ai_timeout_seconds) not in {int, float}
            or isinstance(ai_timeout_seconds, bool)
            or ai_timeout_seconds <= 0
        ):
            raise ZipDispatcherError("dispatch_invalid_argument")
        self._registry = registry
        self._store = store
        self._data_dir = data_dir
        self._workspace_root = workspace_root
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._report_publisher = report_publisher
        self._ai_provider = ai_provider
        self._ai_enabled = ai_enabled
        self._ai_timeout_seconds = float(ai_timeout_seconds)
        self._state_lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock_fd: int | None = None
        self._recovery_pending: set[str] = set()
        self._recovery_blocked: set[str] = set()
        self._uncertain_running: set[str] = set()
        self._fatal_diagnostic: str | None = None
        self._diagnostics: dict[str, str] = {}
        self._busy_cooldown_until = 0.0
        self._forked_child_pid: int | None = None
        if hasattr(os, "register_at_fork"):
            os.register_at_fork(after_in_child=self._after_fork_child)

    def start(self) -> None:
        """Acquire the lifecycle lock, reconcile durable state, then accept work."""

        with self._state_lock:
            if self._forked_child_pid == os.getpid():
                raise ZipDispatcherError("dispatch_forked_child")
            if self._thread is not None or self._lock_fd is not None:
                raise ZipDispatcherError("dispatch_already_started")
            self._acquire_lifecycle_lock()
        try:
            self._reconcile_startup()
            if self._stop.is_set():
                raise ZipDispatcherError(self._fatal_diagnostic or "dispatch_startup_stopped")
            thread = threading.Thread(target=self._run, name="openguard-zip-dispatcher", daemon=False)
            with self._state_lock:
                self._thread = thread
            thread.start()
        except Exception:
            with self._state_lock:
                self._thread = None
            raise

    def stop_and_join(self) -> None:
        """Stop accepting dispatcher cycles and wait for the active worker.

        The lock intentionally remains held.  The caller must close the
        registry first and then invoke :meth:`release_lifecycle_lock`.
        """

        self._stop.set()
        self._wake.set()
        with self._state_lock:
            thread = self._thread
        if thread is not None:
            if thread is threading.current_thread():
                raise ZipDispatcherError("dispatch_shutdown_invalid")
            thread.join()
            with self._state_lock:
                self._thread = None

    def release_lifecycle_lock(self) -> None:
        """Release only after the worker stopped and the registry was closed."""

        with self._state_lock:
            if self._thread is not None:
                raise ZipDispatcherError("dispatch_worker_active")
            descriptor = self._lock_fd
            self._lock_fd = None
        if descriptor is None:
            return
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        except OSError as error:
            raise ZipDispatcherError("dispatch_lock_release_failed") from error
        finally:
            try:
                os.close(descriptor)
            except OSError:
                pass

    def notify(self) -> None:
        """Best-effort wakeup; correctness remains the durable periodic scan."""

        self._wake.set()

    @property
    def fatal_diagnostic(self) -> str | None:
        """A fixed internal state for a stopped dispatcher, never HTTP output."""

        return self._fatal_diagnostic

    @property
    def has_lifecycle_lock(self) -> bool:
        return self._lock_fd is not None

    @property
    def is_accepting(self) -> bool:
        thread = self._thread
        return (
            self._lock_fd is not None
            and thread is not None
            and thread.is_alive()
            and not self._stop.is_set()
            and self._fatal_diagnostic is None
            and self._forked_child_pid != os.getpid()
        )

    def diagnostic_for(self, scan_id: str) -> str | None:
        """Return a fixed per-descriptor diagnostic for internal observability."""

        return self._diagnostics.get(scan_id)

    def is_bound_to(
        self,
        registry: SQLiteScanRunRegistry,
        store: ZipDispatchStore,
        *,
        ai_provider: Provider | None,
        ai_enabled: bool,
        ai_timeout_seconds: float,
    ) -> bool:
        """Expose only the object/root identity check needed by ``create_app``."""

        return (
            self._registry is registry
            and self._store is store
            and store.upload_root == self._data_dir / "uploads"
            and store.dispatch_root == self._data_dir / "dispatch"
            and self._ai_provider is ai_provider
            and self._ai_enabled is ai_enabled
            and self._ai_timeout_seconds == float(ai_timeout_seconds)
        )

    def _acquire_lifecycle_lock(self) -> None:
        try:
            parent = self._data_dir.lstat()
        except OSError as error:
            raise ZipDispatcherError("dispatch_lock_path_invalid") from error
        if (
            not stat.S_ISDIR(parent.st_mode)
            or stat.S_ISLNK(parent.st_mode)
            or parent.st_uid != os.geteuid()
            or stat.S_IMODE(parent.st_mode) != 0o700
        ):
            raise ZipDispatcherError("dispatch_lock_path_invalid")
        path = self._data_dir / _LOCK_NAME
        existed = True
        try:
            before = path.lstat()
        except FileNotFoundError:
            existed = False
            before = None
        except OSError as error:
            raise ZipDispatcherError("dispatch_lock_path_invalid") from error
        if existed and (
            before is None
            or stat.S_ISLNK(before.st_mode)
            or not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) != 0o600
        ):
            raise ZipDispatcherError("dispatch_lock_path_invalid")
        descriptor: int | None = None
        try:
            flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
            if not existed:
                flags |= os.O_CREAT | os.O_EXCL
            descriptor = os.open(path, flags, 0o600)
            if not existed:
                os.fchmod(descriptor, 0o600)
            current = os.fstat(descriptor)
            named = path.lstat()
            if (
                not stat.S_ISREG(current.st_mode)
                or current.st_uid != os.geteuid()
                or stat.S_IMODE(current.st_mode) != 0o600
                or (current.st_dev, current.st_ino) != (named.st_dev, named.st_ino)
            ):
                raise OSError("unsafe lifecycle lock")
            os.set_inheritable(descriptor, False)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno in {errno.EACCES, errno.EAGAIN}:
                    raise ZipDispatcherError("dispatch_lock_unavailable") from None
                raise
            final = path.lstat()
            if (current.st_dev, current.st_ino) != (final.st_dev, final.st_ino):
                raise OSError("lifecycle lock was replaced")
            self._lock_fd = descriptor
            descriptor = None
        except ZipDispatcherError:
            raise
        except FileExistsError:
            # Another compliant process created the fixed name after the
            # initial lstat.  Re-evaluate its inode and permissions instead
            # of ever chmod'ing an object we did not create.
            self._acquire_lifecycle_lock()
        except OSError as error:
            raise ZipDispatcherError("dispatch_lock_path_invalid") from error
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass

    def _after_fork_child(self) -> None:
        """Child processes drop the inherited descriptor without ``LOCK_UN``."""

        descriptor = self._lock_fd
        self._lock_fd = None
        self._thread = None
        self._forked_child_pid = os.getpid()
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass

    def _run(self) -> None:
        while not self._stop.is_set():
            # Startup reconciliation can exhaust a bounded busy budget before
            # this thread exists.  Honor that exact same cooldown here so the
            # first normal cycle (or a notify) cannot turn it into an early
            # fourth recovery CAS.
            if not self._honor_busy_cooldown():
                return
            try:
                if self._reconcile_pending():
                    self._process_ready()
            except (ScanRegistryError, ZipDispatchError, ZipDispatcherError):
                # A directory/registry-wide failure is not a business retry.
                # Per-descriptor malformed files are handled at their own
                # branch and never reach this boundary.
                self._fatal_diagnostic = "dispatch_cycle_stopped"
                self._stop.set()
                break
            delay = max(_CYCLE_SECONDS, self._busy_cooldown_until - time.monotonic())
            self._wake.wait(delay)
            self._wake.clear()
            remaining = self._busy_cooldown_until - time.monotonic()
            if remaining > 0:
                self._stop.wait(remaining)

    def _all_runs(self) -> tuple[StoredScanRun, ...]:
        items: list[StoredScanRun] = []
        after: str | None = None
        while True:
            page = self._registry.list_runs(after_scan_id=after)
            items.extend(page.items)
            if page.next_after_scan_id is None:
                return tuple(items)
            after = page.next_after_scan_id

    def _reconcile_startup(self) -> None:
        runs = self._all_runs()
        for stored in runs:
            if stored.run.status is ScanStatus.RUNNING and stored.run.project.source_type is SourceType.ZIP:
                self._recovery_pending.add(stored.run.id)
        if not self._reconcile_pending(include_prepared=False):
            return
        self._reconcile_prepared()

    def _reconcile_pending(self, *, include_prepared: bool = True) -> bool:
        deferred = False
        for scan_id in tuple(sorted(self._recovery_pending)):
            if self._stop.is_set() or scan_id in self._uncertain_running or scan_id in self._recovery_blocked:
                continue
            try:
                stored = self._registry.get(scan_id)
            except ScanRegistryError as error:
                if error.code == "registry_busy":
                    self._mark_busy_cooldown()
                    deferred = True
                    continue
                raise
            if stored.run.status in _TERMINAL:
                self._recovery_pending.discard(scan_id)
                self._cleanup_terminal(stored.run)
                continue
            if stored.run.status is not ScanStatus.RUNNING:
                self._recovery_pending.discard(scan_id)
                continue
            self._recover_running(stored)
            if scan_id in self._recovery_pending and scan_id not in self._recovery_blocked and scan_id not in self._uncertain_running:
                deferred = True
        if include_prepared and not deferred and not self._stop.is_set():
            self._reconcile_prepared()
        return not deferred

    def _reconcile_prepared(self) -> None:
        for scan_id in self._store.scan_ids(state="prepared"):
            if self._stop.is_set():
                return
            with self._store.operation():
                try:
                    descriptor = self._store.read(scan_id, state="prepared")
                except ZipDispatchError as error:
                    self._handle_descriptor_error(scan_id, error)
                    continue
                if descriptor is None:
                    continue
                try:
                    stored = self._registry.get(scan_id)
                except ScanRegistryError as error:
                    if error.code == "registry_not_found":
                        try:
                            self._store.cleanup_prepared_without_run(
                                scan_id,
                                run_exists=lambda candidate: self._registry_exists(candidate),
                            )
                        except ZipDispatchError:
                            pass
                        continue
                    if error.code == "registry_busy":
                        self._mark_busy_cooldown()
                        continue
                    raise
                if stored.run.status is ScanStatus.QUEUED and _descriptor_matches(descriptor, stored.run):
                    try:
                        self._store.input_path_for_dispatch(descriptor)
                    except ZipDispatchError as error:
                        if error.code in {"dispatch_input_unavailable", "dispatch_input_invalid"}:
                            self._converge_queued(descriptor, state="prepared", code=error.code)
                        else:
                            self._diagnose(scan_id, "dispatch_input_storage_failure")
                            self._stop_fatal("dispatch_storage_failure")
                        continue
                    outcome = self._profile_failure(descriptor)
                    if outcome is not None:
                        self._converge_queued(descriptor, state="prepared", code=outcome)
                        continue
                    try:
                        self._store.promote(descriptor)
                    except ZipDispatchError:
                        continue
                elif stored.run.status in _TERMINAL and _descriptor_matches(descriptor, stored.run):
                    self._cleanup_terminal(stored.run)
                elif not _descriptor_matches(descriptor, stored.run):
                    self._diagnose(scan_id, "dispatch_descriptor_mismatch")

    def _registry_exists(self, scan_id: str) -> bool:
        try:
            self._registry.get(scan_id)
        except ScanRegistryError as error:
            if error.code == "registry_not_found":
                return False
            raise
        return True

    def _process_ready(self) -> None:
        for scan_id in self._store.scan_ids(state="ready"):
            if self._stop.is_set():
                return
            with self._store.operation():
                try:
                    descriptor = self._store.read(scan_id, state="ready")
                except ZipDispatchError as error:
                    self._handle_descriptor_error(scan_id, error)
                    continue
                if descriptor is None:
                    continue
                stored = self._read_ready_run(scan_id)
                if stored is None:
                    continue
                if not _descriptor_matches(descriptor, stored.run):
                    self._diagnose(scan_id, "dispatch_descriptor_mismatch")
                    continue
                if stored.run.status in _TERMINAL:
                    self._cleanup_terminal(stored.run)
                    continue
                if stored.run.status is not ScanStatus.QUEUED or scan_id in self._uncertain_running:
                    continue
            self._dispatch_queued(descriptor, stored)

    def _read_ready_run(self, scan_id: str) -> StoredScanRun | None:
        for attempt in range(3):
            try:
                return self._registry.get(scan_id)
            except ScanRegistryError as error:
                if error.code == "registry_not_found":
                    return None
                if error.code == "registry_busy" and self._wait_busy(attempt):
                    continue
                if error.code == "registry_busy":
                    return None
                raise
        return None

    @staticmethod
    def _message(code: str) -> str:
        messages = {
            "dispatch_input_unavailable": "ZIP input is unavailable.",
            "dispatch_input_invalid": "ZIP input is invalid.",
            "dispatch_profile_disabled": "ZIP execution profile is disabled.",
            "dispatch_profile_mismatch": "ZIP execution profile does not match.",
        }
        return messages[code]

    def _profile_failure(self, descriptor: ZipDispatchDescriptor) -> str | None:
        profile = descriptor.execution_profile
        if not profile.ai_requested:
            return None
        if not self._ai_enabled:
            return "dispatch_profile_disabled"
        try:
            current = ZipExecutionProfile.from_provider(
                ai_requested=True,
                provider=self._ai_provider,
                ai_timeout_seconds=self._ai_timeout_seconds,
            )
        except ZipDispatchError:
            return "dispatch_profile_mismatch"
        if current.plan_version != profile.plan_version or current.ai_identity != profile.ai_identity:
            return "dispatch_profile_mismatch"
        # Timeout belongs to the acceptance-time profile.  It is intentionally
        # passed to the reconstructed plan below rather than compared to a
        # later administrator default.
        return None

    def _dispatch_queued(self, descriptor: ZipDispatchDescriptor, stored: StoredScanRun) -> None:
        with self._store.operation():
            try:
                latest = self._store.read(descriptor.scan_id, state="ready")
            except ZipDispatchError as error:
                self._handle_descriptor_error(descriptor.scan_id, error)
                return
            if latest != descriptor:
                return
            try:
                current = self._registry.get(descriptor.scan_id)
            except ScanRegistryError as error:
                if error.code == "registry_busy":
                    self._mark_busy_cooldown()
                    return
                self._stop_fatal("dispatch_registry_failure")
                return
            if current.run.status is not ScanStatus.QUEUED or not _descriptor_matches(descriptor, current.run):
                return
            try:
                archive = self._store.input_path_for_dispatch(descriptor)
            except ZipDispatchError as error:
                if error.code in {"dispatch_input_unavailable", "dispatch_input_invalid"}:
                    self._converge_queued(descriptor, state="ready", code=error.code)
                else:
                    self._diagnose(descriptor.scan_id, "dispatch_input_storage_failure")
                    self._stop_fatal("dispatch_storage_failure")
                return
            profile_failure = self._profile_failure(descriptor)
            if profile_failure is not None:
                self._converge_queued(descriptor, state="ready", code=profile_failure)
                return
        if self._stop.is_set():
            return
        try:
            plan = build_local_zip_dependency_plan(
                archive,
                self._workspace_root,
                clock=self._clock,
                ai_provider=self._ai_provider if descriptor.execution_profile.ai_requested else None,
                ai_enabled=descriptor.execution_profile.ai_requested,
                ai_timeout_seconds=descriptor.execution_profile.ai_timeout_seconds,
            )
        except Exception:
            self._stop_fatal("dispatch_plan_build_failed")
            return
        publisher = self._report_publisher
        worker = ScanPipelineWorker(
            _PreClaimRegistry(self._registry, current, wait_busy=self._wait_preclaim_busy),
            clock=self._clock,
            terminal_publisher=publisher.publish if publisher is not None else None,
        )
        try:
            terminal = worker.run(descriptor.scan_id, plan)
        except _PreClaimBusy:
            self._mark_busy_cooldown()
            return
        except PipelineError:
            self._mark_uncertain(descriptor.scan_id)
            return
        if terminal.run.status in _TERMINAL:
            self._cleanup_terminal(terminal.run)

    def _converge_queued(self, descriptor: ZipDispatchDescriptor, *, state: str, code: str) -> None:
        """Fail a known bad queued descriptor without constructing a plan."""

        for attempt in range(3):
            with self._store.operation():
                try:
                    latest = self._store.read(descriptor.scan_id, state=state)
                    current = self._registry.get(descriptor.scan_id)
                except ScanRegistryError as error:
                    if error.code == "registry_busy" and self._wait_busy(attempt):
                        continue
                    if error.code == "registry_revision_conflict":
                        self._mark_uncertain(descriptor.scan_id)
                    elif error.code != "registry_busy":
                        self._mark_uncertain(descriptor.scan_id)
                        self._stop_fatal("dispatch_registry_failure")
                    return
                except ZipDispatchError:
                    return
                if latest != descriptor or current.run.status is not ScanStatus.QUEUED or not _descriptor_matches(descriptor, current.run):
                    return
                started_at = self._now(minimum=current.run.created_at)
                claimed = self._controlled(
                    current.run,
                    status=ScanStatus.RUNNING,
                    stage=ScanStage.INGESTION,
                    progress=5,
                    started_at=started_at,
                    finished_at=None,
                )
                try:
                    running = self._registry.replace(claimed, expected_revision=current.revision)
                except ScanRegistryError as error:
                    if error.code == "registry_busy" and self._wait_busy(attempt):
                        continue
                    if error.code == "registry_revision_conflict":
                        self._mark_uncertain(descriptor.scan_id)
                    elif error.code != "registry_busy":
                        self._mark_uncertain(descriptor.scan_id)
                        self._stop_fatal("dispatch_registry_failure")
                    return
                error = ScanError(
                    code=code,
                    stage=ScanStage.INGESTION,
                    message=self._message(code),
                    recoverable=False,
                )
                failed = self._controlled(
                    running.run,
                    status=ScanStatus.FAILED,
                    stage=ScanStage.INGESTION,
                    progress=5,
                    started_at=started_at,
                    finished_at=self._now(minimum=started_at),
                    errors=[*running.run.errors, error],
                )
                try:
                    terminal = self._registry.replace(failed, expected_revision=running.revision)
                except ScanRegistryError as error:
                    self._mark_uncertain(descriptor.scan_id)
                    if error.code not in {"registry_revision_conflict", "registry_busy"}:
                        self._stop_fatal("dispatch_registry_failure")
                    return
            self._cleanup_terminal(terminal.run)
            return

    def _recover_running(self, stored: StoredScanRun) -> None:
        run = stored.run
        with self._store.operation():
            try:
                descriptor = self._store.read(run.id, state="ready") or self._store.read(run.id, state="prepared")
            except ZipDispatchError as error:
                self._handle_descriptor_error(run.id, error)
                self._recovery_blocked.add(run.id)
                return
        if descriptor is None or not _descriptor_matches(descriptor, run) or run.report_links:
            self._diagnose(
                run.id,
                "dispatch_recovery_report_links_blocked" if run.report_links else "dispatch_descriptor_mismatch",
            )
            self._recovery_blocked.add(run.id)
            return
        is_partial = bool(run.components or run.ai_assets or run.evidence or run.findings)
        minimum = run.started_at or run.created_at
        error = ScanError(
            code="worker_interrupted",
            stage=run.stage,
            message="Worker execution was interrupted.",
            recoverable=is_partial,
        )
        recovered = self._controlled(
            run,
            status=ScanStatus.PARTIAL if is_partial else ScanStatus.FAILED,
            stage=run.stage,
            progress=run.progress,
            started_at=run.started_at,
            finished_at=self._now(minimum=minimum),
            errors=[*run.errors, error],
        )
        for attempt in range(3):
            with self._store.operation():
                try:
                    terminal = self._registry.replace(recovered, expected_revision=stored.revision)
                except ScanRegistryError as error:
                    if error.code == "registry_busy" and self._wait_busy(attempt):
                        continue
                    if error.code == "registry_revision_conflict":
                        self._mark_uncertain(run.id)
                    elif error.code != "registry_busy":
                        self._mark_uncertain(run.id)
                        self._stop_fatal("dispatch_registry_failure")
                    return
            self._recovery_pending.discard(run.id)
            self._cleanup_terminal(terminal.run)
            return

    def _cleanup_terminal(self, run: ScanRun) -> None:
        with self._store.operation():
            try:
                self._store.cleanup_terminal(run, read_registry=lambda scan_id: self._registry.get(scan_id).run)
            except ZipDispatchError:
                self._diagnose(run.id, "dispatch_cleanup_deferred")

    def _handle_descriptor_error(self, scan_id: str, error: ZipDispatchError) -> None:
        if error.code in {"dispatch_descriptor_invalid", "dispatch_store_conflict", "dispatch_store_corrupt"}:
            self._diagnose(scan_id, "dispatch_descriptor_blocked")
            return
        self._stop_fatal("dispatch_storage_failure")

    def _diagnose(self, scan_id: str, code: str) -> None:
        self._diagnostics.setdefault(scan_id, code)

    def _stop_fatal(self, code: str) -> None:
        self._fatal_diagnostic = code
        self._stop.set()

    def _wait_busy(self, attempt: int) -> bool:
        if attempt >= len(_BUSY_DELAYS):
            self._mark_busy_cooldown()
            return False
        self._stop.wait(_BUSY_DELAYS[attempt])
        return not self._stop.is_set()

    def _wait_preclaim_busy(self, delay: float) -> bool:
        self._stop.wait(delay)
        return not self._stop.is_set()

    def _mark_busy_cooldown(self) -> None:
        self._busy_cooldown_until = max(self._busy_cooldown_until, time.monotonic() + _CYCLE_SECONDS)

    def _honor_busy_cooldown(self) -> bool:
        while not self._stop.is_set():
            remaining = self._busy_cooldown_until - time.monotonic()
            if remaining <= 0:
                return True
            self._wake.wait(remaining)
            self._wake.clear()
        return False

    def _mark_uncertain(self, scan_id: str) -> None:
        """Never reinterpret a potentially claimed run inside this process."""

        self._uncertain_running.add(scan_id)
        try:
            latest = self._registry.get(scan_id)
        except ScanRegistryError as error:
            self._uncertain_running.add(scan_id)
            if error.code != "registry_not_found":
                self._stop_fatal("dispatch_registry_failure")
            return
        if latest.run.status in _TERMINAL:
            self._cleanup_terminal(latest.run)

    def _now(self, *, minimum: datetime) -> datetime:
        value = self._clock()
        if type(value) is not datetime or value.tzinfo is None:
            raise ZipDispatcherError("dispatch_clock_invalid")
        value = value.astimezone(timezone.utc)
        return max(value, minimum)

    @staticmethod
    def _controlled(
        run: ScanRun,
        *,
        status: ScanStatus,
        stage: ScanStage,
        progress: int,
        started_at: datetime | None,
        finished_at: datetime | None,
        errors: list[ScanError] | None = None,
    ) -> ScanRun:
        payload = run.model_dump(mode="python")
        payload.update(
            status=status,
            stage=stage,
            progress=progress,
            started_at=started_at,
            finished_at=finished_at,
        )
        if errors is not None:
            payload["errors"] = errors
        return ScanRun.model_validate(payload)


__all__ = ["ZipDispatcher", "ZipDispatcherError"]
