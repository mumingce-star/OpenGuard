"""SPDX normalization utilities used between scanners and the rule engine."""

from .spdx import ParsedLicenseExpression, normalize_license, parse_license_expression

__all__ = ["ParsedLicenseExpression", "normalize_license", "parse_license_expression"]
