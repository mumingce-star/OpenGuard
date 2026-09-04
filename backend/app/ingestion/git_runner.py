"""Locked Git subprocess invocation with no target checkout or shell."""

from __future__ import annotations

import json
import os
import re
import signal
import stat
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from app.security.errors import IngestionSecurityError
from app.security.limits import GitSafetyLimits


_VERSION = re.compile(r"^git version ([0-9A-Za-z.+() _-]{1,90})$")
_FIXED_CONFIG = (
    "protocol.allow=never",
    "protocol.https.allow=always",
    "http.followRedirects=false",
    "credential.helper=",
    "core.hooksPath=/dev/null",
    "core.fsmonitor=false",
    "filter.lfs.smudge=",
    "filter.lfs.required=false",
    "diff.external=",
    "http.extraHeader=",
)


@dataclass(frozen=True)
class GitRuntimeIdentity:
    version: str
    config_digest: str


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            process.kill()
        except OSError:
            pass


class GitProcessRunner:
    def __init__(self, executable: Path, limits: GitSafetyLimits) -> None:
        if not isinstance(executable, Path) or not executable.is_absolute() or type(limits) is not GitSafetyLimits:
            raise ValueError("invalid Git process configuration")
        try:
            resolved = executable.resolve(strict=True)
            info = resolved.stat()
        except OSError as error:
            raise ValueError("Git executable is unavailable") from error
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or not os.access(resolved, os.X_OK):
            raise ValueError("Git executable is not trusted")
        self.executable = resolved
        self.limits = limits
        version_output = self.capture(("--version",), cwd=resolved.parent, home=resolved.parent, deadline=time.monotonic() + 5, output_max=256)
        try:
            rendered = version_output.decode("ascii").strip()
        except UnicodeDecodeError as error:
            raise ValueError("Git version is invalid") from error
        match = _VERSION.fullmatch(rendered)
        if match is None:
            raise ValueError("Git version is invalid")
        version = match.group(1)
        payload = json.dumps(
            {
                "clone": ["no-checkout", "depth=1", "single-branch", "no-tags", "no-recurse-submodules"],
                "config": list(_FIXED_CONFIG),
                "environment": [
                    "GIT_CONFIG_NOSYSTEM=1",
                    "GIT_LFS_SKIP_SMUDGE=1",
                    "GIT_NO_REPLACE_OBJECTS=1",
                    "GIT_OPTIONAL_LOCKS=0",
                    "GIT_PROTOCOL_FROM_USER=0",
                    "GIT_TERMINAL_PROMPT=0",
                ],
                "limits": {
                    "redirects_max": limits.redirects_max,
                    "connect_timeout_s": limits.connect_timeout_s,
                    "total_timeout_s": limits.total_timeout_s,
                    "transfer_max_bytes": limits.transfer_max_bytes,
                    "materialized_max_bytes": limits.materialized_max_bytes,
                    "file_count_max": limits.file_count_max,
                    "single_file_max_bytes": limits.single_file_max_bytes,
                },
                "version": version,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        import hashlib

        self.identity = GitRuntimeIdentity(version=version, config_digest=hashlib.sha256(payload).hexdigest())

    @staticmethod
    def _environment(home: Path, proxy_url: str | None = None) -> dict[str, str]:
        environment = {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "/usr/bin/false",
            "SSH_ASKPASS": "/usr/bin/false",
            "GIT_LFS_SKIP_SMUDGE": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_PROTOCOL_FROM_USER": "0",
            "GIT_OPTIONAL_LOCKS": "0",
            "LC_ALL": "C",
            "LANG": "C",
            "PATH": "/usr/bin:/bin",
            "NO_PROXY": "",
            "no_proxy": "",
        }
        if proxy_url is not None:
            environment.update(
                HTTPS_PROXY=proxy_url,
                https_proxy=proxy_url,
                HTTP_PROXY="",
                http_proxy="",
                ALL_PROXY="",
                all_proxy="",
            )
        return environment

    def _argv(self, arguments: tuple[str, ...], *, proxy_url: str | None = None) -> list[str]:
        argv = [str(self.executable)]
        for setting in _FIXED_CONFIG:
            argv.extend(("-c", setting))
        if proxy_url is not None:
            argv.extend(("-c", f"http.proxy={proxy_url}"))
        argv.extend(arguments)
        return argv

    def clone_no_checkout(
        self,
        source: str,
        destination: Path,
        *,
        home: Path,
        proxy_url: str,
        deadline: float,
    ) -> None:
        arguments = (
            "clone",
            "--quiet",
            "--no-checkout",
            "--depth=1",
            "--single-branch",
            "--no-tags",
            "--no-recurse-submodules",
            "--template=",
            "--",
            source,
            str(destination),
        )
        process = self._spawn(
            self._argv(arguments, proxy_url=proxy_url),
            cwd=destination.parent,
            home=home,
            proxy_url=proxy_url,
            stdout=subprocess.DEVNULL,
        )
        try:
            process.wait(timeout=self._remaining(deadline))
        except subprocess.TimeoutExpired as error:
            _kill_process_group(process)
            process.wait()
            raise IngestionSecurityError("scanner_timeout", "git_fetch_timeout") from error
        if process.returncode != 0:
            raise IngestionSecurityError("invalid_source", "git_fetch_failed")

    def capture(
        self,
        arguments: tuple[str, ...],
        *,
        cwd: Path,
        home: Path,
        deadline: float,
        output_max: int,
    ) -> bytes:
        if output_max <= 0:
            raise ValueError("invalid Git output limit")
        process = self._spawn(self._argv(arguments), cwd=cwd, home=home, proxy_url=None, stdout=subprocess.PIPE)
        assert process.stdout is not None
        timed_out = threading.Event()

        def expire() -> None:
            timed_out.set()
            _kill_process_group(process)

        timer = threading.Timer(self._remaining(deadline), expire)
        timer.start()
        output = bytearray()
        try:
            while True:
                chunk = process.stdout.read(64 * 1024)
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) > output_max:
                    _kill_process_group(process)
                    raise IngestionSecurityError("scanner_failed", "git_object_limit_exceeded")
            process.wait()
        finally:
            timer.cancel()
        if timed_out.is_set():
            raise IngestionSecurityError("scanner_timeout", "git_process_timeout")
        if process.returncode != 0:
            raise IngestionSecurityError("invalid_source", "git_object_invalid")
        return bytes(output)

    def spawn_batch(self, *, cwd: Path, home: Path) -> subprocess.Popen[bytes]:
        return self._spawn(
            self._argv(("-C", str(cwd), "cat-file", "--batch")),
            cwd=cwd.parent,
            home=home,
            proxy_url=None,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
        )

    def _spawn(
        self,
        argv: list[str],
        *,
        cwd: Path,
        home: Path,
        proxy_url: str | None,
        stdout: int,
        stdin: int = subprocess.DEVNULL,
    ) -> subprocess.Popen[bytes]:
        try:
            return subprocess.Popen(
                argv,
                cwd=cwd,
                env=self._environment(home, proxy_url),
                stdin=stdin,
                stdout=stdout,
                stderr=subprocess.DEVNULL,
                shell=False,
                start_new_session=True,
                close_fds=True,
                umask=0o077,
            )
        except OSError as error:
            raise IngestionSecurityError("scanner_failed", "git_process_unavailable") from error

    @staticmethod
    def _remaining(deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise IngestionSecurityError("scanner_timeout", "git_process_timeout")
        return remaining


__all__ = ["GitProcessRunner", "GitRuntimeIdentity", "_kill_process_group"]
