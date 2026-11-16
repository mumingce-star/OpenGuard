"""Private, I1-only durable ZIP dispatch preparation.

This module deliberately does not start a dispatcher, acquire a lifecycle
lock, recover runs, or execute a pipeline.  It only makes one already-staged
ZIP and its immutable execution descriptor durable enough for I2 to consume.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.ai.ollama import MANIFEST_DIGEST, MODEL_ID, OLLAMA_VERSION, OllamaProvider
from app.domain.models import ProducerRef, ProducerType, ScanRun, ScanStatus, SourceType


ZIP_DISPATCH_SCHEMA = "openguard.zip-dispatch"
ZIP_DISPATCH_VERSION = 1
ZIP_DISPATCH_PLAN_VERSION = "zip-dependency-v1"
ZIP_DISPATCH_MAX_DESCRIPTOR_BYTES = 8 * 1024
ZIP_DISPATCH_MAX_INPUTS = 8
ZIP_DISPATCH_MAX_BYTES = 512 * 1024 * 1024
ZIP_DISPATCH_RESERVATION_BYTES = 64 * 1024 * 1024

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SCAN_ID = re.compile(r"^scn_(?:[0-9a-hjkmnp-tv-z]{26}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")
_DESCRIPTOR_KEYS = frozenset(
    {
        "schema",
        "version",
        "scan_id",
        "source_type",
        "upload_name",
        "input_sha256",
        "run_identity_sha256",
        "execution_profile",
    }
)
_PROFILE_KEYS = frozenset({"plan_version", "ai_requested", "ai_identity", "ai_timeout_seconds"})
_AI_IDENTITY_KEYS = frozenset(
    {"provider", "model_id", "runtime_version", "manifest_digest", "prompt_schema_digest"}
)
_UPLOAD_NAME = re.compile(r"^openguard-upload-[A-Za-z0-9_]{1,128}\.zip$")


def _locked_prompt_schema_digest() -> str:
    """Reuse the A5 producer's fixed prompt digest without any transport call."""

    value = OllamaProvider().producer.prompt_schema_digest
    if value is None:
        _fail("dispatch_descriptor_invalid")
    return value.value


class ZipDispatchError(RuntimeError):
    """A stable internal storage failure with no path or exception disclosure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise ZipDispatchError(code) from None


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _reject_constant(_: str) -> None:
    raise ValueError("non-finite number")


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except Exception:
        _fail("dispatch_descriptor_invalid")
    raise AssertionError("unreachable")


def _validate_private_directory(path: object, *, code: str) -> Path:
    if not isinstance(path, Path) or not path.is_absolute():
        _fail(code)
    try:
        info = path.lstat()
    except OSError:
        _fail(code)
    if (
        os.name != "posix"
        or stat.S_ISLNK(info.st_mode)
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        _fail(code)
    return path


def _validate_scan_id(value: object) -> str:
    if type(value) is not str or _SCAN_ID.fullmatch(value) is None:
        _fail("dispatch_descriptor_invalid")
    return value


def _validate_basename(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or "\x00" in value
        or _UPLOAD_NAME.fullmatch(value) is None
    ):
        _fail("dispatch_descriptor_invalid")
    try:
        if len(value.encode("utf-8")) > 255:
            raise ValueError
    except (UnicodeError, ValueError):
        _fail("dispatch_descriptor_invalid")
    return value


def _validate_sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        _fail("dispatch_descriptor_invalid")
    return value


def _utc_text(value: object) -> str:
    try:
        rendered = value.isoformat().replace("+00:00", "Z")
    except Exception:
        _fail("dispatch_descriptor_invalid")
    if type(rendered) is not str:
        _fail("dispatch_descriptor_invalid")
    return rendered


def run_identity_sha256(run: ScanRun) -> str:
    """Hash exactly the immutable queued fields I2 is allowed to rely on."""

    if type(run) is not ScanRun:
        _fail("dispatch_descriptor_invalid")
    try:
        payload = {
            "contract_version": run.contract_version,
            "id": run.id,
            "idempotency_key": run.idempotency_key,
            "created_at": _utc_text(run.created_at),
            "project": {
                "id": run.project.id,
                "name": run.project.name,
                "source_type": run.project.source_type.value,
                "source": run.project.source,
                "created_at": _utc_text(run.project.created_at),
            },
            "provenance": {
                "input_digest": run.provenance.input_digest.model_dump(mode="json"),
            },
        }
    except Exception:
        _fail("dispatch_descriptor_invalid")
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


@dataclass(frozen=True)
class ZipExecutionProfile:
    """The acceptance-time plan and AI configuration; I2 must not rewrite it."""

    ai_requested: bool
    ai_identity: dict[str, object] | None
    ai_timeout_seconds: float
    plan_version: str = ZIP_DISPATCH_PLAN_VERSION
    external_scanners: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.ai_requested) is not bool
            or type(self.external_scanners) is not bool
            or type(self.plan_version) is not str
            or self.plan_version != ZIP_DISPATCH_PLAN_VERSION
            or type(self.ai_timeout_seconds) not in {int, float}
            or isinstance(self.ai_timeout_seconds, bool)
            or not math.isfinite(self.ai_timeout_seconds)
            or self.ai_timeout_seconds <= 0
        ):
            _fail("dispatch_descriptor_invalid")
        object.__setattr__(self, "ai_timeout_seconds", float(self.ai_timeout_seconds))
        if not self.ai_requested:
            if self.ai_identity is not None:
                _fail("dispatch_descriptor_invalid")
            return
        if type(self.ai_identity) is not dict:
            _fail("dispatch_descriptor_invalid")
        identity = self.ai_identity
        if set(identity) != _AI_IDENTITY_KEYS:
            _fail("dispatch_descriptor_invalid")
        if (
            type(identity["provider"]) is not str
            or identity["provider"] != "ollama-local"
            or identity["model_id"] != MODEL_ID
            or identity["runtime_version"] != OLLAMA_VERSION
            or identity["manifest_digest"] != MANIFEST_DIGEST
            or type(identity["prompt_schema_digest"]) is not str
            or identity["prompt_schema_digest"] != _locked_prompt_schema_digest()
        ):
            _fail("dispatch_descriptor_invalid")
        object.__setattr__(self, "ai_identity", dict(identity))

    @classmethod
    def from_provider(
        cls,
        *,
        ai_requested: bool,
        provider: object | None,
        ai_timeout_seconds: float,
        external_scanners: bool = False,
    ) -> "ZipExecutionProfile":
        if type(ai_requested) is not bool:
            _fail("dispatch_descriptor_invalid")
        if not ai_requested:
            return cls(False, None, ai_timeout_seconds, external_scanners=external_scanners)
        try:
            producer = ProducerRef.model_validate(provider.producer.model_dump(mode="python"))  # type: ignore[union-attr]
        except Exception:
            _fail("dispatch_descriptor_invalid")
        if (
            producer.type is not ProducerType.AI
            or producer.provider != "ollama-local"
            or producer.model_id != MODEL_ID
            or producer.version != OLLAMA_VERSION
            or producer.prompt_schema_digest is None
        ):
            _fail("dispatch_descriptor_invalid")
        return cls(
            True,
            {
                "provider": producer.provider,
                "model_id": producer.model_id,
                "runtime_version": producer.version,
                "manifest_digest": MANIFEST_DIGEST,
                "prompt_schema_digest": producer.prompt_schema_digest.value,
            },
            ai_timeout_seconds,
            external_scanners=external_scanners,
        )

    def as_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "plan_version": self.plan_version,
            "ai_requested": self.ai_requested,
            "ai_identity": self.ai_identity,
            "ai_timeout_seconds": self.ai_timeout_seconds,
        }
        if self.external_scanners:
            payload["external_scanners"] = True
        return payload

    @classmethod
    def from_payload(cls, value: object) -> "ZipExecutionProfile":
        if type(value) is not dict or set(value) not in (_PROFILE_KEYS, _PROFILE_KEYS | {"external_scanners"}):
            _fail("dispatch_descriptor_invalid")
        return cls(
            ai_requested=value["ai_requested"],
            ai_identity=value["ai_identity"],
            ai_timeout_seconds=value["ai_timeout_seconds"],
            plan_version=value["plan_version"],
            external_scanners=value.get("external_scanners", False),
        )


@dataclass(frozen=True)
class ZipDispatchDescriptor:
    scan_id: str
    upload_name: str
    input_sha256: str
    run_identity_sha256: str
    execution_profile: ZipExecutionProfile

    @classmethod
    def from_run(cls, run: ScanRun, profile: ZipExecutionProfile) -> "ZipDispatchDescriptor":
        if type(run) is not ScanRun or type(profile) is not ZipExecutionProfile:
            _fail("dispatch_descriptor_invalid")
        if run.project.source_type is not SourceType.ZIP:
            _fail("dispatch_descriptor_invalid")
        scan_id = _validate_scan_id(run.id)
        upload_name = _validate_basename(run.project.source)
        return cls(
            scan_id=scan_id,
            upload_name=upload_name,
            input_sha256=_validate_sha256(run.provenance.input_digest.value),
            run_identity_sha256=run_identity_sha256(run),
            execution_profile=profile,
        )

    def as_payload(self) -> dict[str, object]:
        return {
            "schema": ZIP_DISPATCH_SCHEMA,
            "version": ZIP_DISPATCH_VERSION,
            "scan_id": self.scan_id,
            "source_type": "zip",
            "upload_name": self.upload_name,
            "input_sha256": self.input_sha256,
            "run_identity_sha256": self.run_identity_sha256,
            "execution_profile": self.execution_profile.as_payload(),
        }

    def to_bytes(self) -> bytes:
        data = _canonical_json(self.as_payload())
        if len(data) > ZIP_DISPATCH_MAX_DESCRIPTOR_BYTES:
            _fail("dispatch_descriptor_invalid")
        return data

    @classmethod
    def from_bytes(cls, raw: object) -> "ZipDispatchDescriptor":
        if type(raw) is not bytes or not raw or len(raw) > ZIP_DISPATCH_MAX_DESCRIPTOR_BYTES:
            _fail("dispatch_descriptor_invalid")
        try:
            payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_reject_constant)
        except Exception:
            _fail("dispatch_descriptor_invalid")
        if type(payload) is not dict or set(payload) != _DESCRIPTOR_KEYS:
            _fail("dispatch_descriptor_invalid")
        if (
            payload["schema"] != ZIP_DISPATCH_SCHEMA
            or type(payload["version"]) is not int
            or isinstance(payload["version"], bool)
            or payload["version"] != ZIP_DISPATCH_VERSION
            or payload["source_type"] != "zip"
        ):
            _fail("dispatch_descriptor_invalid")
        descriptor = cls(
            scan_id=_validate_scan_id(payload["scan_id"]),
            upload_name=_validate_basename(payload["upload_name"]),
            input_sha256=_validate_sha256(payload["input_sha256"]),
            run_identity_sha256=_validate_sha256(payload["run_identity_sha256"]),
            execution_profile=ZipExecutionProfile.from_payload(payload["execution_profile"]),
        )
        if descriptor.to_bytes() != raw:
            _fail("dispatch_descriptor_invalid")
        return descriptor


@dataclass(frozen=True)
class _PersistentInput:
    name: str
    size_bytes: int


class ZipDispatchReservation:
    """A one-request pre-body reservation, owned by one ``ZipDispatchStore``."""

    def __init__(self, store: "ZipDispatchStore", token: str) -> None:
        self._store = store
        self._token = token

    def release(self) -> None:
        self._store._release(self._token)


class ZipDispatchStore:
    """Private descriptor and input lifecycle storage for I1 preparation only."""

    def __init__(
        self,
        dispatch_root: Path,
        upload_root: Path,
        *,
        event_hook: Callable[[str], None] | None = None,
        recovery_mode: bool = False,
    ) -> None:
        if event_hook is not None and not callable(event_hook) or type(recovery_mode) is not bool:
            _fail("dispatch_store_invalid_argument")
        self._dispatch_root = _validate_private_directory(dispatch_root, code="dispatch_store_path_invalid")
        self._upload_root = _validate_private_directory(upload_root, code="dispatch_store_path_invalid")
        self._event_hook = event_hook
        self._lock = threading.RLock()
        self._reservations: set[str] = set()
        self._reservation_inputs: dict[str, str] = {}
        self._prepared_owners: dict[str, str] = {}
        self._recovery_mode = recovery_mode
        self._persistent: dict[str, _PersistentInput] = {}
        # I1's default construction remains fail-closed.  I2 can instead
        # start in a deliberately restricted recovery mode: an unrelated
        # suspicious upload still blocks new accepts, but it cannot prevent a
        # separately, cryptographically bound descriptor from reaching its
        # required queued-failure convergence.
        try:
            self._persistent = self._discover_persistent_inputs()
        except ZipDispatchError as error:
            if not recovery_mode or error.code not in {
                "dispatch_store_corrupt",
                "dispatch_capacity_exceeded",
            }:
                raise

    @property
    def upload_root(self) -> Path:
        return self._upload_root

    @property
    def dispatch_root(self) -> Path:
        return self._dispatch_root

    @contextmanager
    def operation(self):
        """Serialize the no-await I1 prepare→registry→ready critical section."""

        with self._lock:
            yield

    @staticmethod
    def _open_directory(path: Path) -> int:
        descriptor: int | None = None
        try:
            descriptor = os.open(
                path,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            )
            info = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700
            ):
                raise OSError("unsafe directory")
            return descriptor
        except OSError:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            _fail("dispatch_store_io_failed")
        raise AssertionError("unreachable")

    @classmethod
    def _fsync_directory(cls, path: Path) -> None:
        descriptor = cls._open_directory(path)
        try:
            os.fsync(descriptor)
        except OSError:
            _fail("dispatch_store_io_failed")
        finally:
            os.close(descriptor)

    def _emit(self, name: str) -> None:
        hook = self._event_hook
        if hook is not None:
            hook(name)

    def checkpoint(self, name: str) -> None:
        """Explicit no-op seam unless a test-only event hook was injected."""

        if type(name) is not str or not name:
            _fail("dispatch_store_invalid_argument")
        self._emit(name)

    @staticmethod
    def _validated_private_file(info: os.stat_result) -> bool:
        return (
            stat.S_ISREG(info.st_mode)
            and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o600
        )

    def _discover_persistent_inputs(self) -> dict[str, _PersistentInput]:
        _validate_private_directory(self._upload_root, code="dispatch_store_path_invalid")
        discovered: dict[str, _PersistentInput] = {}
        try:
            entries = list(self._upload_root.iterdir())
        except OSError:
            _fail("dispatch_store_io_failed")
        active_names = set(self._reservation_inputs.values())
        for path in entries:
            try:
                info = path.lstat()
            except OSError:
                # An entry we cannot inspect is itself suspicious capacity
                # state, not authority to erase or ignore it.  Recovery mode
                # may still service separately bound descriptors while new
                # accepts remain fail-closed on the next capacity rescan.
                _fail("dispatch_store_corrupt")
            if path.name in active_names:
                continue
            if not self._validated_private_file(info) or _UPLOAD_NAME.fullmatch(path.name) is None:
                _fail("dispatch_store_corrupt")
            if info.st_size < 0 or path.name in discovered:
                _fail("dispatch_store_corrupt")
            discovered[path.name] = _PersistentInput(path.name, info.st_size)
        if len(discovered) > ZIP_DISPATCH_MAX_INPUTS or sum(item.size_bytes for item in discovered.values()) > ZIP_DISPATCH_MAX_BYTES:
            _fail("dispatch_capacity_exceeded")
        return discovered

    def reserve_upload(self) -> ZipDispatchReservation:
        """Reserve one maximum upload slot before any multipart body is consumed."""

        with self._lock:
            self._persistent = self._discover_persistent_inputs()
            reserved_count = len(self._reservations)
            persistent_bytes = sum(item.size_bytes for item in self._persistent.values())
            if (
                len(self._persistent) + reserved_count + 1 > ZIP_DISPATCH_MAX_INPUTS
                or persistent_bytes + (reserved_count + 1) * ZIP_DISPATCH_RESERVATION_BYTES > ZIP_DISPATCH_MAX_BYTES
            ):
                _fail("dispatch_capacity_exceeded")
            token = uuid.uuid4().hex
            self._reservations.add(token)
            return ZipDispatchReservation(self, token)

    def _release(self, token: str) -> None:
        with self._lock:
            self._reservations.discard(token)
            self._reservation_inputs.pop(token, None)

    def bind_upload(self, reservation: ZipDispatchReservation, archive_path: Path) -> None:
        """Associate the staged temporary name with its pre-body reservation."""

        if reservation._store is not self or not isinstance(archive_path, Path) or archive_path.parent != self._upload_root:
            _fail("dispatch_store_invalid_argument")
        name = _validate_basename(archive_path.name)
        with self._lock:
            if reservation._token not in self._reservations or reservation._token in self._reservation_inputs:
                _fail("dispatch_store_invalid_argument")
            if name in self._reservation_inputs.values() or name in self._persistent:
                _fail("dispatch_store_corrupt")
            self._reservation_inputs[reservation._token] = name

    def _persist_reservation(self, reservation: ZipDispatchReservation, name: str, size_bytes: int) -> None:
        if reservation._store is not self or type(size_bytes) is not int or size_bytes < 1:
            _fail("dispatch_store_invalid_argument")
        with self._lock:
            if reservation._token not in self._reservations:
                _fail("dispatch_store_invalid_argument")
            if self._reservation_inputs.get(reservation._token) != name:
                _fail("dispatch_store_invalid_argument")
            if name in self._persistent:
                _fail("dispatch_store_corrupt")
            self._reservations.remove(reservation._token)
            self._reservation_inputs.pop(reservation._token, None)
            self._persistent[name] = _PersistentInput(name, size_bytes)

    def _require_active_reservation(self, reservation: ZipDispatchReservation, name: str) -> None:
        if (
            reservation._store is not self
            or reservation._token not in self._reservations
            or self._reservation_inputs.get(reservation._token) != name
        ):
            _fail("dispatch_store_invalid_argument")

    def _descriptor_name(self, scan_id: str, state: str) -> str:
        if state not in {"prepared", "ready"}:
            _fail("dispatch_store_invalid_argument")
        return f"{_validate_scan_id(scan_id)}.{state}.json"

    def _read_relative(self, root: Path, name: str, *, maximum: int) -> bytes | None:
        directory = self._open_directory(root)
        descriptor: int | None = None
        try:
            try:
                expected = os.stat(name, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                return None
            if not self._validated_private_file(expected) or expected.st_size > maximum:
                _fail("dispatch_store_corrupt")
            descriptor = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory)
            actual = os.fstat(descriptor)
            if (
                not self._validated_private_file(actual)
                or (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino)
                or actual.st_size != expected.st_size
            ):
                _fail("dispatch_store_corrupt")
            chunks: list[bytes] = []
            remaining = actual.st_size
            while remaining:
                chunk = os.read(descriptor, min(64 * 1024, remaining))
                if not chunk:
                    _fail("dispatch_store_corrupt")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                _fail("dispatch_store_corrupt")
            return b"".join(chunks)
        except ZipDispatchError:
            raise
        except OSError:
            _fail("dispatch_store_io_failed")
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            os.close(directory)
        raise AssertionError("unreachable")

    def _write_new_descriptor(self, name: str, content: bytes) -> None:
        if len(content) > ZIP_DISPATCH_MAX_DESCRIPTOR_BYTES:
            _fail("dispatch_descriptor_invalid")
        directory = self._open_directory(self._dispatch_root)
        temporary = f".{name}.{uuid.uuid4().hex}.tmp"
        descriptor: int | None = None
        try:
            try:
                os.stat(name, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                _fail("dispatch_store_conflict")
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=directory,
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
            os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
            os.unlink(temporary, dir_fd=directory)
            self._fsync_directory(self._dispatch_root)
        except ZipDispatchError:
            raise
        except OSError:
            _fail("dispatch_store_io_failed")
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            try:
                os.unlink(temporary, dir_fd=directory)
            except OSError:
                pass
            os.close(directory)

    def _archive_facts(self, archive_path: Path, upload_name: str) -> tuple[int, str]:
        if not isinstance(archive_path, Path) or archive_path.parent != self._upload_root or archive_path.name != upload_name:
            _fail("dispatch_store_invalid_argument")
        directory = self._open_directory(self._upload_root)
        descriptor: int | None = None
        try:
            expected = os.stat(upload_name, dir_fd=directory, follow_symlinks=False)
            if not self._validated_private_file(expected) or expected.st_size < 1 or expected.st_size > ZIP_DISPATCH_RESERVATION_BYTES:
                _fail("dispatch_store_corrupt")
            descriptor = os.open(upload_name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory)
            actual = os.fstat(descriptor)
            if (
                not self._validated_private_file(actual)
                or (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino)
                or actual.st_size != expected.st_size
            ):
                _fail("dispatch_store_corrupt")
            os.fsync(descriptor)
            digest = hashlib.sha256()
            remaining = actual.st_size
            while remaining:
                chunk = os.read(descriptor, min(64 * 1024, remaining))
                if not chunk:
                    _fail("dispatch_store_corrupt")
                digest.update(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                _fail("dispatch_store_corrupt")
            current = os.fstat(descriptor)
            if (current.st_dev, current.st_ino, current.st_size) != (actual.st_dev, actual.st_ino, actual.st_size):
                _fail("dispatch_store_corrupt")
            return actual.st_size, digest.hexdigest()
        except ZipDispatchError:
            raise
        except OSError:
            _fail("dispatch_store_io_failed")
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            os.close(directory)
        raise AssertionError("unreachable")

    def prepare(
        self,
        archive_path: Path,
        run: ScanRun,
        profile: ZipExecutionProfile,
        reservation: ZipDispatchReservation,
    ) -> ZipDispatchDescriptor:
        """Persist ``prepared`` only after the ZIP parent directory has been fsynced."""

        descriptor = ZipDispatchDescriptor.from_run(run, profile)
        if reservation._store is not self:
            _fail("dispatch_store_invalid_argument")
        with self._lock:
            self._require_active_reservation(reservation, descriptor.upload_name)
            size_bytes, actual_digest = self._archive_facts(archive_path, descriptor.upload_name)
            if actual_digest != descriptor.input_sha256:
                _fail("dispatch_store_corrupt")
            self._fsync_directory(self._upload_root)
            self._emit("input_fsynced")
            self._write_new_descriptor(self._descriptor_name(descriptor.scan_id, "prepared"), descriptor.to_bytes())
            self._emit("prepared_fsynced")
            self._persist_reservation(reservation, descriptor.upload_name, size_bytes)
            self._prepared_owners[descriptor.scan_id] = reservation._token
            return descriptor

    def read(self, scan_id: str, *, state: str) -> ZipDispatchDescriptor | None:
        with self._lock:
            valid_id = _validate_scan_id(scan_id)
            opposite = "ready" if state == "prepared" else "prepared" if state == "ready" else None
            if opposite is None:
                _fail("dispatch_store_invalid_argument")
            raw = self._read_relative(
                self._dispatch_root,
                self._descriptor_name(valid_id, state),
                maximum=ZIP_DISPATCH_MAX_DESCRIPTOR_BYTES,
            )
            other = self._read_relative(
                self._dispatch_root,
                self._descriptor_name(valid_id, opposite),
                maximum=ZIP_DISPATCH_MAX_DESCRIPTOR_BYTES,
            )
            if raw is not None and other is not None:
                _fail("dispatch_store_conflict")
            if raw is None:
                return None
            descriptor = ZipDispatchDescriptor.from_bytes(raw)
            if descriptor.scan_id != valid_id:
                _fail("dispatch_store_corrupt")
            return descriptor

    def scan_ids(self, *, state: str) -> tuple[str, ...]:
        """Return only syntactically addressable descriptors without cleanup.

        Invalid or unfamiliar directory entries are intentionally not guessed
        at, deleted, or made dispatchable.  The caller still has to use
        :meth:`read` for the private-file and canonical-JSON validation.
        """

        if state not in {"prepared", "ready"}:
            _fail("dispatch_store_invalid_argument")
        suffix = f".{state}.json"
        with self._lock:
            _validate_private_directory(self._dispatch_root, code="dispatch_store_path_invalid")
            try:
                names = [path.name for path in self._dispatch_root.iterdir()]
            except OSError:
                _fail("dispatch_store_io_failed")
            identifiers: list[str] = []
            for name in names:
                if not name.endswith(suffix):
                    continue
                candidate = name[: -len(suffix)]
                try:
                    identifiers.append(_validate_scan_id(candidate))
                except ZipDispatchError:
                    # Unknown files are not this task's cleanup authority.
                    continue
            return tuple(sorted(set(identifiers)))

    def input_path_for_dispatch(self, descriptor: ZipDispatchDescriptor) -> Path:
        """Revalidate the exact descriptor-owned ZIP immediately before use."""

        if type(descriptor) is not ZipDispatchDescriptor:
            _fail("dispatch_store_invalid_argument")
        with self._lock:
            path = self._upload_root / descriptor.upload_name
            try:
                info = path.lstat()
            except FileNotFoundError:
                _fail("dispatch_input_unavailable")
            except OSError:
                _fail("dispatch_store_io_failed")
            if not self._validated_private_file(info) or info.st_size < 1:
                _fail("dispatch_input_invalid")
            try:
                size_bytes, actual_digest = self._archive_facts(path, descriptor.upload_name)
            except ZipDispatchError as error:
                if error.code == "dispatch_store_corrupt":
                    _fail("dispatch_input_invalid")
                raise
            if size_bytes < 1 or actual_digest != descriptor.input_sha256:
                _fail("dispatch_input_invalid")
            return path

    def promote(self, descriptor: ZipDispatchDescriptor) -> None:
        """Atomically move the exact prepared descriptor into I2-visible ``ready``."""

        if type(descriptor) is not ZipDispatchDescriptor:
            _fail("dispatch_store_invalid_argument")
        prepared_name = self._descriptor_name(descriptor.scan_id, "prepared")
        ready_name = self._descriptor_name(descriptor.scan_id, "ready")
        with self._lock:
            prepared = self.read(descriptor.scan_id, state="prepared")
            ready = self.read(descriptor.scan_id, state="ready")
            if prepared != descriptor or ready is not None:
                _fail("dispatch_store_conflict")
            directory = self._open_directory(self._dispatch_root)
            try:
                os.rename(prepared_name, ready_name, src_dir_fd=directory, dst_dir_fd=directory)
                self._fsync_directory(self._dispatch_root)
            except OSError:
                _fail("dispatch_store_io_failed")
            finally:
                os.close(directory)
            self._prepared_owners.pop(descriptor.scan_id, None)
            self._emit("ready_fsynced")

    def discard_prepared(
        self,
        descriptor: ZipDispatchDescriptor,
        archive_path: Path,
        reservation: ZipDispatchReservation,
    ) -> None:
        """Delete only a proven current-request loser, ZIP first and descriptor second."""

        if type(descriptor) is not ZipDispatchDescriptor or reservation._store is not self:
            _fail("dispatch_store_invalid_argument")
        with self._lock:
            if self._prepared_owners.get(descriptor.scan_id) != reservation._token:
                _fail("dispatch_store_conflict")
            if self.read(descriptor.scan_id, state="prepared") != descriptor or self.read(descriptor.scan_id, state="ready") is not None:
                _fail("dispatch_store_conflict")
            if archive_path.parent != self._upload_root or archive_path.name != descriptor.upload_name:
                _fail("dispatch_store_invalid_argument")
            upload_directory = self._open_directory(self._upload_root)
            dispatch_directory: int | None = None
            try:
                dispatch_directory = self._open_directory(self._dispatch_root)
                size_bytes, actual_digest = self._archive_facts(archive_path, descriptor.upload_name)
                if size_bytes < 1 or actual_digest != descriptor.input_sha256:
                    _fail("dispatch_store_corrupt")
                os.unlink(descriptor.upload_name, dir_fd=upload_directory)
                self._fsync_directory(self._upload_root)
                os.unlink(self._descriptor_name(descriptor.scan_id, "prepared"), dir_fd=dispatch_directory)
                self._fsync_directory(self._dispatch_root)
            except ZipDispatchError:
                raise
            except OSError:
                _fail("dispatch_store_io_failed")
            finally:
                os.close(upload_directory)
                if dispatch_directory is not None:
                    os.close(dispatch_directory)
            self._persistent.pop(descriptor.upload_name, None)
            self._prepared_owners.pop(descriptor.scan_id, None)

    @staticmethod
    def _matches_run(descriptor: ZipDispatchDescriptor, run: ScanRun) -> bool:
        return (
            type(run) is ScanRun
            and descriptor.scan_id == run.id
            and run.project.source_type is SourceType.ZIP
            and descriptor.upload_name == run.project.source
            and descriptor.input_sha256 == run.provenance.input_digest.value
            and descriptor.run_identity_sha256 == run_identity_sha256(run)
        )

    def _delete_verified_pair(self, descriptor: ZipDispatchDescriptor, *, state: str) -> None:
        """Remove ZIP then descriptor, tolerating only a previously removed ZIP."""

        if self.read(descriptor.scan_id, state=state) != descriptor:
            _fail("dispatch_store_conflict")
        upload_directory = self._open_directory(self._upload_root)
        dispatch_directory: int | None = None
        try:
            dispatch_directory = self._open_directory(self._dispatch_root)
            try:
                size_bytes, actual_digest = self._archive_facts(
                    self._upload_root / descriptor.upload_name,
                    descriptor.upload_name,
                )
            except ZipDispatchError as error:
                if error.code != "dispatch_store_io_failed":
                    raise
                # A missing input is permitted only for cleanup of an already
                # healthy descriptor; every suspicious existing object fails.
                try:
                    os.stat(descriptor.upload_name, dir_fd=upload_directory, follow_symlinks=False)
                except FileNotFoundError:
                    size_bytes, actual_digest = 0, descriptor.input_sha256
                except OSError:
                    _fail("dispatch_store_io_failed")
                else:
                    raise
            if size_bytes:
                if actual_digest != descriptor.input_sha256:
                    _fail("dispatch_store_corrupt")
                os.unlink(descriptor.upload_name, dir_fd=upload_directory)
            # Persist removal even when the ZIP was already removed during a
            # prior interrupted cleanup before this descriptor is deleted.
            self._fsync_directory(self._upload_root)
            os.unlink(self._descriptor_name(descriptor.scan_id, state), dir_fd=dispatch_directory)
            self._fsync_directory(self._dispatch_root)
        except ZipDispatchError:
            raise
        except OSError:
            _fail("dispatch_store_io_failed")
        finally:
            os.close(upload_directory)
            if dispatch_directory is not None:
                os.close(dispatch_directory)
        self._persistent.pop(descriptor.upload_name, None)
        self._prepared_owners.pop(descriptor.scan_id, None)

    def cleanup_prepared_without_run(
        self,
        scan_id: str,
        *,
        run_exists: Callable[[str], bool],
    ) -> None:
        """Restricted I1 cleanup for a healthy prepared descriptor with no row.

        I2 owns recovery and calls this only after its own lifecycle lock has
        established that no registry row exists.  This helper never starts work.
        """

        if not callable(run_exists):
            _fail("dispatch_store_invalid_argument")
        with self._lock:
            descriptor = self.read(scan_id, state="prepared")
            if descriptor is None:
                _fail("dispatch_store_not_found")
            try:
                exists = run_exists(descriptor.scan_id)
            except Exception:
                _fail("dispatch_store_io_failed")
            if type(exists) is not bool:
                _fail("dispatch_store_invalid_argument")
            if exists:
                _fail("dispatch_store_conflict")
            self._delete_verified_pair(descriptor, state="prepared")

    def cleanup_terminal(
        self,
        run: ScanRun,
        *,
        read_registry: Callable[[str], ScanRun],
    ) -> None:
        """Restricted I1 cleanup for a healthy terminal registry snapshot."""

        if not callable(read_registry) or type(run) is not ScanRun or run.status not in {
            ScanStatus.COMPLETED,
            ScanStatus.PARTIAL,
            ScanStatus.FAILED,
            ScanStatus.CANCELLED,
        }:
            _fail("dispatch_store_invalid_argument")
        with self._lock:
            try:
                healthy = read_registry(run.id)
            except Exception:
                _fail("dispatch_store_io_failed")
            if type(healthy) is not ScanRun or healthy != run:
                _fail("dispatch_store_conflict")
            descriptor = self.read(run.id, state="ready")
            state = "ready"
            if descriptor is None:
                descriptor = self.read(run.id, state="prepared")
                state = "prepared"
            if descriptor is None or not self._matches_run(descriptor, run):
                _fail("dispatch_store_conflict")
            self._delete_verified_pair(descriptor, state=state)


__all__ = [
    "ZIP_DISPATCH_MAX_BYTES",
    "ZIP_DISPATCH_MAX_INPUTS",
    "ZIP_DISPATCH_MAX_DESCRIPTOR_BYTES",
    "ZIP_DISPATCH_PLAN_VERSION",
    "ZIP_DISPATCH_RESERVATION_BYTES",
    "ZIP_DISPATCH_SCHEMA",
    "ZIP_DISPATCH_VERSION",
    "ZipDispatchDescriptor",
    "ZipDispatchError",
    "ZipDispatchReservation",
    "ZipDispatchStore",
    "ZipExecutionProfile",
    "run_identity_sha256",
]
