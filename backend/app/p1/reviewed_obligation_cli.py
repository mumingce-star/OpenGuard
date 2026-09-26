"""Private operator entrypoint for one fixed, reviewed pydantic 2.13.4 sample."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import uuid
from pathlib import Path

from app.assessment.engine import canonical_bytes
from app.persistence.scan_registry import SQLiteScanRunRegistry
from .reviewed_obligation import ReviewAdmissionError, _private_json_exclusive, apply, prepare


def _pairs(rows: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in rows:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _read_json(path: Path) -> dict:
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or info.st_uid != os.geteuid() or info.st_nlink != 1
            or info.st_mode & 0o077 or info.st_size > 32 * 1024
            or any(parent.is_symlink() for parent in path.parents)):
        raise ReviewAdmissionError("review_input_unsafe")
    value = json.loads(path.read_bytes(), object_pairs_hook=_pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    if type(value) is not dict:
        raise ReviewAdmissionError("review_input_invalid")
    return value


def _reserve_result(path: Path, confirmation_sha256: str) -> tuple[int, int]:
    """Reserve a private result file before any admission side effect."""
    try:
        SQLiteScanRunRegistry._private_stat(path.parent, directory=True)
        if any(parent.is_symlink() for parent in path.parents):
            raise ReviewAdmissionError("result_path_unsafe")
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError:
        raise ReviewAdmissionError("result_exists") from None
    except ReviewAdmissionError:
        raise
    except Exception:
        raise ReviewAdmissionError("result_path_unsafe") from None
    try:
        with os.fdopen(descriptor, "wb") as sink:
            sink.write(canonical_bytes({"state": "pending", "confirmation_sha256": confirmation_sha256}))
            sink.flush()
            os.fsync(sink.fileno())
            info = os.fstat(sink.fileno())
        return info.st_dev, info.st_ino
    except Exception:
        # An incomplete reservation remains; no admission was attempted.
        raise ReviewAdmissionError("result_reservation_failed") from None


def _finalize_result(path: Path, reserved_identity: tuple[int, int], value: dict) -> None:
    """Publish one complete state atomically over this invocation's reservation."""
    temporary = path.with_name(path.name + ".final-" + uuid.uuid4().hex)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "wb") as sink:
        sink.write(canonical_bytes(value))
        sink.flush()
        os.fsync(sink.fileno())
    current = path.lstat()
    if (current.st_dev, current.st_ino) != reserved_identity or not stat.S_ISREG(current.st_mode):
        raise ReviewAdmissionError("result_reservation_lost")
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _apply_with_result(arguments: argparse.Namespace) -> dict:
    card = _read_json(arguments.card)
    confirmation = _read_json(arguments.confirmation)
    reserved = _reserve_result(arguments.result, arguments.confirmation_sha256)
    try:
        value = apply(arguments.data_dir, arguments.source_archive, arguments.artifact,
                      card, confirmation, expected_confirmation_sha256=arguments.confirmation_sha256)
    except Exception as error:
        code = getattr(error, "code", "review_apply_failed")
        try:
            _finalize_result(arguments.result, reserved,
                             {"state": "failure", "error": code, "retry_apply": False})
        except Exception:
            raise ReviewAdmissionError("apply_failed_result_unavailable") from error
        raise
    try:
        _finalize_result(arguments.result, reserved, {"state": "success", "result": value})
    except Exception as error:
        raise ReviewAdmissionError("apply_completed_result_unavailable") from error
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    initial = commands.add_parser("prepare", help="read-only DB/material validation; write a pending card")
    initial.add_argument("--data-dir", type=Path, required=True)
    initial.add_argument("--source-scan-id", required=True)
    initial.add_argument("--source-archive", type=Path, required=True)
    initial.add_argument("--artifact", type=Path, required=True)
    initial.add_argument("--card", type=Path, required=True)
    digest = commands.add_parser("hash-confirmation", help="read-only canonical hash of operator-authored JSON")
    digest.add_argument("--confirmation", type=Path, required=True)
    final = commands.add_parser("apply", help="create a new real scan only after explicit human confirmation")
    final.add_argument("--data-dir", type=Path, required=True)
    final.add_argument("--source-archive", type=Path, required=True)
    final.add_argument("--artifact", type=Path, required=True)
    final.add_argument("--card", type=Path, required=True)
    final.add_argument("--confirmation", type=Path, required=True)
    final.add_argument("--confirmation-sha256", required=True,
                       help="SHA-256 of the exact canonical confirmation JSON, fixed before apply")
    final.add_argument("--result", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "prepare":
            value = prepare(arguments.data_dir / "scans.db", arguments.source_scan_id,
                            arguments.source_archive, arguments.artifact)
            _private_json_exclusive(arguments.card, value)
            print(json.dumps({"state": "pending", "card_sha256": value["card_sha256"],
                              "card": str(arguments.card)}, sort_keys=True))
        elif arguments.command == "hash-confirmation":
            print(hashlib.sha256(canonical_bytes(_read_json(arguments.confirmation))).hexdigest())
        else:
            value = _apply_with_result(arguments)
            print(canonical_bytes(value).decode("utf-8"))
        return 0
    except (ReviewAdmissionError, OSError, ValueError, json.JSONDecodeError) as error:
        code = getattr(error, "code", "review_input_invalid")
        payload = {"error": code}
        if code == "apply_completed_result_unavailable":
            payload.update({"apply_completed": True, "retry_apply": False})
        elif code == "apply_failed_result_unavailable":
            payload.update({"apply_may_have_persisted": True, "retry_apply": False})
        print(json.dumps(payload), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
