"""Lifecycle owner for server-configured, per-ingestion workspaces."""

from __future__ import annotations

from pathlib import Path

from app.security.limits import ZipSafetyLimits
from app.security.secure_dir import SecureRoot, SecureWorkspace


class WorkspaceManager:
    """Runs the POSIX capability probe once and allocates isolated task roots."""

    def __init__(self, workspace_root: str | Path, limits: ZipSafetyLimits):
        self._limits = limits
        self._root = SecureRoot.open(workspace_root)

    def create(self) -> SecureWorkspace:
        return self._root.create_workspace()

    def cleanup(self, workspace: SecureWorkspace) -> None:
        workspace.cleanup(self._limits.cleanup_retry_max)

    def close(self) -> None:
        self._root.close()
