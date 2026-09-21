"""Durable, internal persistence primitives for OpenGuard."""

from .scan_registry import (
    REGISTRY_STORAGE_SCHEMA,
    REGISTRY_STORAGE_VERSION,
    SQLiteScanRunRegistry,
    ScanRegistryError,
    ScanRunPage,
    StoredScanRun,
)
from .zip_dispatch import (
    ZIP_DISPATCH_MAX_BYTES,
    ZIP_DISPATCH_MAX_DESCRIPTOR_BYTES,
    ZIP_DISPATCH_MAX_INPUTS,
    ZIP_DISPATCH_PLAN_VERSION,
    ZIP_DISPATCH_RESERVATION_BYTES,
    ZIP_DISPATCH_SCHEMA,
    ZIP_DISPATCH_VERSION,
    ZipDispatchDescriptor,
    ZipDispatchError,
    ZipDispatchReservation,
    ZipDispatchStore,
    ZipExecutionProfile,
    run_identity_sha256,
)

__all__ = [
    "REGISTRY_STORAGE_SCHEMA",
    "REGISTRY_STORAGE_VERSION",
    "SQLiteScanRunRegistry",
    "ScanRegistryError",
    "ScanRunPage",
    "StoredScanRun",
    "ZIP_DISPATCH_MAX_BYTES",
    "ZIP_DISPATCH_MAX_DESCRIPTOR_BYTES",
    "ZIP_DISPATCH_MAX_INPUTS",
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
