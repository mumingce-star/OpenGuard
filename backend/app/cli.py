"""Offline command-line demonstration for the secure local ZIP intake slice."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Sequence, TextIO

from app.ingestion.inventory import Inventory
from app.ingestion.zip_stream import ZipIngestionService
from app.security.errors import IngestionSecurityError


_SCHEMA = "openguard.zip-inventory"
_VERSION = "1"
_USAGE_ERROR = IngestionSecurityError("invalid_request", "invalid_arguments")
_INPUT_ERROR = IngestionSecurityError("invalid_request", "input_file_unavailable")
_RUNTIME_ERROR = IngestionSecurityError("scanner_failed", "cli_runtime_failed")


def inventory_payload(inventory: Inventory) -> dict[str, object]:
    """Build the sole successful CLI representation from the stable inventory DTO."""

    return {
        "schema": _SCHEMA,
        "version": _VERSION,
        "root_digest": inventory.root_digest,
        "entries": [
            {
                "relative_path": entry.relative_path,
                "size_bytes": entry.size_bytes,
                "sha256": entry.sha256,
            }
            for entry in inventory.entries
        ],
    }


def run_local_zip(archive_path: Path, workspace_root: Path) -> Inventory:
    """Ingest one local archive without exposing workspace or parser details."""

    try:
        archive_stream = archive_path.open("rb")
    except OSError as error:
        raise _INPUT_ERROR from error

    service: ZipIngestionService | None = None
    try:
        service = ZipIngestionService(workspace_root)
        with archive_stream:
            return service.ingest(archive_stream)
    finally:
        if service is not None:
            service.close()


def _write_error(error: IngestionSecurityError, stream: TextIO) -> None:
    stream.write(f"{error.code}:{error.reason}\n")


def main(
    arguments: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the local-only demonstration and return a process-compatible status."""

    args = list(sys.argv[1:] if arguments is None else arguments)
    output = sys.stdout if stdout is None else stdout
    errors = sys.stderr if stderr is None else stderr
    if args == ["--help"]:
        output.write("usage: python -m app.cli LOCAL_ZIP\n")
        return 0
    if len(args) != 1:
        _write_error(_USAGE_ERROR, errors)
        return 2

    try:
        with tempfile.TemporaryDirectory(prefix="openguard-zip-cli-") as directory:
            inventory = run_local_zip(Path(args[0]), Path(directory))
    except IngestionSecurityError as error:
        _write_error(error, errors)
        return 1 if error.code != "invalid_request" else 2
    except (OSError, RuntimeError):
        _write_error(_RUNTIME_ERROR, errors)
        return 1

    json.dump(inventory_payload(inventory), output, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    output.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
