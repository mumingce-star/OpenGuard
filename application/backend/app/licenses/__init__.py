"""SPDX normalization and compatibility utilities used between scanners and the rule engine."""

from .compatibility import (
    PROPRIETARY,
    RULE_VERSION as COMPATIBILITY_RULE_VERSION,
    SCHEMA_VERSION as COMPATIBILITY_SCHEMA_VERSION,
    SUPPORTED_SPDX,
    SUPPORTED_TARGETS,
    evaluate_pairwise_atomic,
    evaluate_pairwise_expressions,
    evaluate_scan_compatibility,
    evaluate_target_expression,
    evaluate_target_pair,
    normalize_target_license,
    resolve_target_license,
)
from .spdx import ParsedLicenseExpression, normalize_license, parse_license_expression

__all__ = [
    "COMPATIBILITY_RULE_VERSION",
    "COMPATIBILITY_SCHEMA_VERSION",
    "PROPRIETARY",
    "ParsedLicenseExpression",
    "SUPPORTED_SPDX",
    "SUPPORTED_TARGETS",
    "evaluate_pairwise_atomic",
    "evaluate_pairwise_expressions",
    "evaluate_scan_compatibility",
    "evaluate_target_expression",
    "evaluate_target_pair",
    "normalize_license",
    "normalize_target_license",
    "parse_license_expression",
    "resolve_target_license",
]
