"""Server-owned ZIP safety settings and stream accounting."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import IngestionSecurityError


MIB = 1024 * 1024


def _require_range(name: str, value: int, minimum: int, maximum: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")


@dataclass(frozen=True)
class GitSafetyLimits:
    """Validated administrator-owned limits for one public Git ingestion."""

    redirects_max: int = 0
    connect_timeout_s: int = 10
    total_timeout_s: int = 120
    transfer_max_bytes: int = 256 * MIB
    materialized_max_bytes: int = 512 * MIB
    file_count_max: int = 50_000
    single_file_max_bytes: int = 32 * MIB
    path_depth_max: int = 32
    path_utf8_bytes_max: int = 1_024
    cleanup_retry_max: int = 3
    scan_single_file_read_max_bytes: int = 2 * MIB
    scan_total_read_max_bytes: int = 16 * MIB

    def __post_init__(self) -> None:
        _require_range("redirects_max", self.redirects_max, 0, 5)
        if self.redirects_max != 0:
            raise ValueError("redirects_max must remain zero until redirect validation is implemented")
        _require_range("connect_timeout_s", self.connect_timeout_s, 3, 30)
        _require_range("total_timeout_s", self.total_timeout_s, 30, 600)
        _require_range("transfer_max_bytes", self.transfer_max_bytes, 16 * MIB, 1024 * MIB)
        _require_range("materialized_max_bytes", self.materialized_max_bytes, 64 * MIB, 2 * 1024 * MIB)
        _require_range("file_count_max", self.file_count_max, 1_000, 100_000)
        _require_range("single_file_max_bytes", self.single_file_max_bytes, 1 * MIB, 128 * MIB)
        _require_range("path_depth_max", self.path_depth_max, 8, 64)
        _require_range("path_utf8_bytes_max", self.path_utf8_bytes_max, 256, 4_096)
        _require_range("cleanup_retry_max", self.cleanup_retry_max, 1, 5)
        _require_range("scan_single_file_read_max_bytes", self.scan_single_file_read_max_bytes, 64 * 1024, 32 * MIB)
        _require_range("scan_total_read_max_bytes", self.scan_total_read_max_bytes, 1 * MIB, 256 * MIB)
        if self.single_file_max_bytes > self.materialized_max_bytes:
            raise ValueError("single_file_max_bytes must not exceed materialized_max_bytes")
        if not self.scan_single_file_read_max_bytes <= self.scan_total_read_max_bytes <= self.materialized_max_bytes:
            raise ValueError("scan read limits must fit within materialized limits")


@dataclass(frozen=True)
class ZipSafetyLimits:
    """Validated administrator configuration; request data cannot override it."""

    upload_max_bytes: int = 64 * MIB
    uncompressed_max_bytes: int = 256 * MIB
    entry_count_max: int = 20_000
    single_file_max_bytes: int = 32 * MIB
    expansion_ratio_max: int = 100
    path_depth_max: int = 32
    path_utf8_bytes_max: int = 1_024
    cleanup_retry_max: int = 3
    scan_single_file_read_max_bytes: int | None = None
    scan_total_read_max_bytes: int = 16 * MIB

    def __post_init__(self) -> None:
        _require_range("upload_max_bytes", self.upload_max_bytes, 8 * MIB, 256 * MIB)
        _require_range("uncompressed_max_bytes", self.uncompressed_max_bytes, 32 * MIB, 1024 * MIB)
        _require_range("entry_count_max", self.entry_count_max, 100, 100_000)
        _require_range("single_file_max_bytes", self.single_file_max_bytes, 1 * MIB, 128 * MIB)
        _require_range("expansion_ratio_max", self.expansion_ratio_max, 10, 200)
        _require_range("path_depth_max", self.path_depth_max, 8, 64)
        _require_range("path_utf8_bytes_max", self.path_utf8_bytes_max, 256, 4_096)
        _require_range("cleanup_retry_max", self.cleanup_retry_max, 1, 5)
        _require_range("scan_total_read_max_bytes", self.scan_total_read_max_bytes, 1 * MIB, 256 * MIB)
        if self.scan_single_file_read_max_bytes is not None:
            _require_range(
                "scan_single_file_read_max_bytes",
                self.scan_single_file_read_max_bytes,
                64 * 1024,
                32 * MIB,
            )
            if self.scan_single_file_read_max_bytes > self.single_file_max_bytes:
                raise ValueError("scan_single_file_read_max_bytes must not exceed single_file_max_bytes")
        if not self.effective_scan_single_file_read_max_bytes <= self.scan_total_read_max_bytes <= self.uncompressed_max_bytes:
            raise ValueError("scan read limits must fit within archive limits")

    @property
    def effective_scan_single_file_read_max_bytes(self) -> int:
        """Resolve the omitted A2-2 limit without widening an older ZIP cap."""

        configured = self.scan_single_file_read_max_bytes
        return min(2 * MIB, self.single_file_max_bytes) if configured is None else configured


@dataclass
class ZipExtractionBudget:
    """Counts actual stream output; central-directory values are only preflight hints."""

    limits: ZipSafetyLimits
    upload_size_bytes: int
    total_output_bytes: int = 0

    def begin_file(self, compressed_size_hint: int) -> "ZipFileBudget":
        return ZipFileBudget(self, compressed_size_hint)

    def add_file_bytes(self, amount: int) -> None:
        self.total_output_bytes += amount
        if self.total_output_bytes > self.limits.uncompressed_max_bytes:
            raise IngestionSecurityError("archive_limit_exceeded", "archive_total_size_limit")
        if self.total_output_bytes > self.upload_size_bytes * self.limits.expansion_ratio_max:
            raise IngestionSecurityError("archive_limit_exceeded", "archive_ratio_limit")


@dataclass
class ZipFileBudget:
    """Per-member view of a ``ZipExtractionBudget``."""

    parent: ZipExtractionBudget
    compressed_size_hint: int
    output_bytes: int = 0

    def add(self, amount: int) -> None:
        self.output_bytes += amount
        if self.output_bytes > self.parent.limits.single_file_max_bytes:
            raise IngestionSecurityError("archive_limit_exceeded", "archive_single_file_limit")
        if self.output_bytes and self.compressed_size_hint == 0:
            raise IngestionSecurityError("archive_limit_exceeded", "archive_ratio_limit")
        if self.output_bytes > self.compressed_size_hint * self.parent.limits.expansion_ratio_max:
            raise IngestionSecurityError("archive_limit_exceeded", "archive_ratio_limit")
        self.parent.add_file_bytes(amount)
