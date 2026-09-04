"""End-to-end public Git ingestion using TrustedEgress and Git objects."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from app.ingestion.git_materializer import MaterializedGitTree, materialize_git_tree
from app.ingestion.git_runner import GitProcessRunner, GitRuntimeIdentity
from app.ingestion.inventory import Inventory, build_inventory_snapshot
from app.ingestion.read_session import (
    ReadOnlyScanSession,
    ScanReadLimits,
    ScanSessionResult,
    effective_limits,
    validate_inventory_snapshot,
)
from app.ingestion.trusted_egress import Connector, EgressConnectionEvidence, TrustedEgressProxy
from app.ingestion.url_policy import parse_public_git_url
from app.ingestion.workspace import WorkspaceManager
from app.security.address_policy import Resolver
from app.security.errors import IngestionSecurityError
from app.security.limits import GitSafetyLimits, ZipSafetyLimits


T = TypeVar("T")


@dataclass(frozen=True)
class GitScanSessionResult(ScanSessionResult[T]):
    revision: str
    runtime_identity: GitRuntimeIdentity
    egress_evidence: tuple[EgressConnectionEvidence, ...]


class GitIngestionService:
    """Fetch one public repository and expose one lifecycle-bound read session."""

    def __init__(
        self,
        workspace_root: Path,
        *,
        limits: GitSafetyLimits | None = None,
        git_executable: Path = Path("/usr/bin/git"),
        resolver: Resolver | None = None,
        connector: Connector | None = None,
    ) -> None:
        self.limits = limits or GitSafetyLimits()
        self._workspaces = WorkspaceManager(workspace_root, _workspace_limits(self.limits))
        self._runner = GitProcessRunner(git_executable, self.limits)
        self._resolver = resolver
        self._connector = connector
        self._consumer_local = threading.local()
        self._poisoned = False
        self._state_lock = threading.Lock()

    def close(self) -> None:
        self._workspaces.close()

    def _ensure_usable(self) -> None:
        with self._state_lock:
            if self._poisoned:
                raise IngestionSecurityError("scanner_failed", "workspace_cleanup_failed")

    def ingest_with_consumer(
        self,
        source: str,
        consumer: Callable[[ReadOnlyScanSession], T],
        *,
        read_limits: ScanReadLimits | None = None,
    ) -> GitScanSessionResult[T]:
        if getattr(self._consumer_local, "active", False):
            raise IngestionSecurityError("scanner_failed", "scan_session_reentrant")
        parsed = parse_public_git_url(source)
        self._ensure_usable()
        single, total = effective_limits(
            read_limits,
            single=self.limits.scan_single_file_read_max_bytes,
            total=self.limits.scan_total_read_max_bytes,
        )
        workspace = self._workspaces.create()
        deadline = time.monotonic() + self.limits.total_timeout_s
        session: ReadOnlyScanSession | None = None
        inventory: Inventory | None = None
        result: T | None = None
        materialized: MaterializedGitTree | None = None
        egress_evidence: tuple[EgressConnectionEvidence, ...] = ()
        primary: BaseException | None = None
        try:
            workspace.make_directory(("home",))
            home = workspace.trusted_process_path(("home",))
            repository = workspace.trusted_process_path(("repository",))
            proxy = TrustedEgressProxy(
                parsed.host,
                transfer_max_bytes=self.limits.transfer_max_bytes,
                connect_timeout_s=self.limits.connect_timeout_s,
                resolver=self._resolver,
                connector=self._connector,
            )
            with proxy:
                try:
                    self._runner.clone_no_checkout(
                        parsed.canonical,
                        repository,
                        home=home,
                        proxy_url=proxy.proxy_url,
                        deadline=deadline,
                    )
                except IngestionSecurityError as error:
                    reason = proxy.failure_reason
                    if reason is not None:
                        code = "scanner_failed" if reason == "git_fetch_limit_exceeded" else "invalid_source"
                        raise IngestionSecurityError(code, reason) from error
                    raise
                egress_evidence = proxy.evidence
            if not egress_evidence:
                raise IngestionSecurityError("invalid_source", "source_connection_failed")
            materialized = materialize_git_tree(
                self._runner,
                repository,
                workspace,
                home=home,
                limits=self.limits,
                deadline=deadline,
            )
            snapshot = build_inventory_snapshot(workspace, ("tree",))
            inventory = snapshot.inventory

            def validate() -> None:
                validate_inventory_snapshot(workspace, snapshot)

            validate()
            session = ReadOnlyScanSession(snapshot, workspace, _workspace_limits(self.limits), single, total, validate)
            self._consumer_local.active = True
            try:
                result = consumer(session)
            except BaseException as error:
                primary = error
            finally:
                self._consumer_local.active = False
                session._expire()
            session._recover_deferred_closes()
            validate()
            if session._get_internal_failure is not None:
                raise session._get_internal_failure
            if primary is not None:
                if isinstance(primary, Exception):
                    raise IngestionSecurityError("scanner_failed", "scan_consumer_failed") from primary
                raise primary
            return GitScanSessionResult(
                inventory=inventory,
                consumer_result=result,  # type: ignore[arg-type]
                revision=materialized.revision,
                runtime_identity=self._runner.identity,
                egress_evidence=egress_evidence,
            )
        finally:
            if session is not None:
                session._expire()
            try:
                self._workspaces.cleanup(workspace)
            except IngestionSecurityError:
                with self._state_lock:
                    self._poisoned = True
                raise


def _workspace_limits(limits: GitSafetyLimits) -> ZipSafetyLimits:
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


__all__ = ["GitIngestionService", "GitScanSessionResult"]
