"""Deterministic views over the evidence of one completed local scan."""

from __future__ import annotations

from collections.abc import Mapping
from html import escape
import json
import re
from urllib.parse import quote, unquote

from app.domain.models import (
    ComponentType, EvidenceKind, ScanRun, ScanStatus, _contains_absolute_path_fragment,
)
from app.licenses.compatibility import (
    ROOT_LICENSE_LIMIT,
    ROOT_LICENSE_NAMES,
    build_root_license_checks,
    evaluate_scan_compatibility,
)
from app.p1.dependency_evidence import project_dependency_evidence
from app.p2.material_claims import COPYLEFT, WEAK_COPYLEFT, _COPYLEFT_DECLARATION_FAMILIES
from app.security.archive_path import normalize_member_path
from app.security.errors import IngestionSecurityError
from app.security.limits import ZipSafetyLimits

SCHEMA_VERSION = "openguard-cli-scan/2"
_ECOSYSTEMS = ("npm", "pypi", "golang", "cargo", "maven", "unknown")
_LIMITS = ZipSafetyLimits()
_SENSITIVE = re.compile(r"(?i)(?:(?:api[_-]?key|secret|token|password)\s*[=:]|bearer\s+\S+)")
_FAMILIES = _COPYLEFT_DECLARATION_FAMILIES
_SEVERITIES = {
    **{_FAMILIES[identifier]: "strong" for identifier in COPYLEFT},
    **{_FAMILIES[identifier]: "weak" for identifier in WEAK_COPYLEFT},
}


def _safe_text(value: str | None, fallback: str | None = None) -> str | None:
    if not isinstance(value, str) or not value:
        return fallback
    decoded = unquote(value)
    for actual in (value, decoded):
        if (not actual.isprintable() or "\\" in actual or "://" in actual or "//" in actual
                or actual.startswith("~") or _contains_absolute_path_fragment(actual)
                or _SENSITIVE.search(actual)):
            return fallback
    return value


def _safe_path(path: str | None) -> str | None:
    if _safe_text(path) is None:
        return None
    try:
        result = normalize_member_path(path, is_directory=False, limits=_LIMITS)
    except (IngestionSecurityError, ValueError):
        return None
    return path if result.relative_path == path else None


def _safe_locator(path: str | None, locator: str | None) -> str | None:
    if path is None or locator is None:
        return None
    for prefix in (path, quote(path, safe="/-._~")):
        if locator == prefix:
            return locator
        if locator.startswith(prefix + ":") and _safe_text(locator[len(prefix) + 1:].removeprefix("/")):
            return locator
    return None


def _evidence(evidence_id: str, path: str | None, locator: str | None, digest: str | None) -> dict:
    safe_path = _safe_path(path)
    return {
        "evidence_id": evidence_id,
        "file_path": safe_path,
        "locator": _safe_locator(safe_path, locator),
        "source_sha256": digest if safe_path is not None else None,
    }


def _projected_evidence(ref) -> dict:
    return _evidence(ref.evidence_id, ref.file_path, ref.locator, ref.source_sha256)


def _side(side) -> dict | None:
    if side is None:
        return None
    return {
        "resource_id": side.resource_id,
        "version": _safe_text(side.version),
        "evidence": [_projected_evidence(ref) for ref in side.evidence],
    }


def _json_key(value: dict) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _declaration(license_) -> str | None:
    if license_ is None or license_.expression in {"NONE", "NOASSERTION"}:
        return None
    return _safe_text(license_.expression)


def _copyleft(identifier: str | None) -> str | None:
    return _SEVERITIES.get(_FAMILIES.get(identifier, identifier))


def _root_license_observations(license_files, roots, licenses):
    return build_root_license_checks(license_files, roots, licenses)


def build_report(
    run: ScanRun,
    *,
    input_kind: str,
    input_name: str,
    input_sha256: str,
    excluded_dirs: list[str],
    usage: Mapping[str, bool],
    license_files: Mapping[str, bytes],
    fail_on: tuple[str, ...],
    skipped_entries: int = 0,
    target_license: str | None = None,
) -> dict:
    """Project the saved dependency facts and apply the caller's exit policy."""
    if run.status not in {ScanStatus.COMPLETED, ScanStatus.PARTIAL} or run.project.root_digest is None:
        raise ValueError("scan_report_unavailable")
    dependencies, _, _ = project_dependency_evidence(run, source=None, after=None, limit=len(run.components))
    by_component = {item.resource_id: item for item in dependencies}
    by_evidence = {item.id: item for item in run.evidence}
    licenses = {item.id: item for item in run.licenses}
    components, root_packages, roots, findings = [], [], [], []
    counts = dict.fromkeys(_ECOSYSTEMS, 0)
    for component in sorted(run.components, key=lambda item: (item.ecosystem, item.name, item.version or "", item.id)):
        counts[component.ecosystem] += 1
        license_ = licenses.get(component.license_expression_id)
        row = {
            "id": component.id,
            "name": _safe_text(component.name, "[redacted]"),
            "version": _safe_text(component.version),
            "ecosystem": component.ecosystem,
            "purl": _safe_text(component.purl),
            "declared_license": _declaration(license_),
        }
        if component.component_type is ComponentType.APPLICATION:
            roots.append(component)
            root_packages.append({**row, "evidence_ids": list(component.evidence_ids)})
            evidence = []
            for identifier in component.evidence_ids:
                item = by_evidence[identifier]
                path = (item.locator.split(":", 1)[0]
                        if item.kind in {EvidenceKind.FILE, EvidenceKind.MANIFEST_FIELD} else None)
                digest = item.content_hash.value if item.content_hash and item.content_hash.algorithm == "sha256" else None
                evidence.append(_evidence(identifier, path, item.locator, digest))
            sources = ["manifest"]
        else:
            dependency = by_component[component.id]
            evidence = [_projected_evidence(ref) for ref in dependency.evidence]
            sources = dependency.sources
        components.append({**row, "component_type": component.component_type.value,
                           "sources": sources, "evidence": evidence})
        if license_ is not None:
            for identifier in sorted(set(license_.normalized_ids)):
                severity = _copyleft(identifier)
                if severity is not None:
                    findings.append({"source": "declared_license", "resource_id": component.id,
                                     "license_id": identifier, "severity": severity})

    projected_conflicts = {}
    for item in dependencies:
        for conflict in item.conflicts:
            record = {"ecosystem": item.ecosystem, "name": _safe_text(item.name, "[redacted]"),
                      "status": conflict.status, "declaration": _side(conflict.declaration), "lock": _side(conflict.lock)}
            projected_conflicts[_json_key(record)] = record
    conflicts = [projected_conflicts[key] for key in sorted(projected_conflicts)]
    root_checks, root_findings = _root_license_observations(license_files, roots, licenses)
    findings.extend(root_findings)
    compatibility = evaluate_scan_compatibility(
        run, usage=usage, target_license=target_license, root_license_checks=root_checks,
    )
    diagnostics = [
        {"code": _safe_text(error.code, "scan_diagnostic"), "stage": error.stage.value,
         "message": _safe_text(error.message, "Diagnostic text withheld."), "evidence_ids": list(error.evidence_ids)}
        for error in run.errors
    ]
    if skipped_entries:
        diagnostics.append({"code": "directory_entries_skipped", "stage": "ingestion",
                            "message": f"Skipped {skipped_entries} unsafe directory entries.", "evidence_ids": []})
    conflict_count = sum(item["status"] == "confirmed" for item in conflicts)
    incompatible_count = compatibility["summary"]["incompatible_count"]
    review_required_count = compatibility["summary"]["review_required_count"]
    partial = run.status == ScanStatus.PARTIAL or bool(skipped_entries)
    matches = {
        "conflict": conflict_count > 0,
        "copyleft": bool(findings),
        "partial": partial,
        "incompatible": incompatible_count > 0,
    }
    triggered = [rule for rule in sorted(set(fail_on)) if matches[rule]]
    return {
        "schema_version": SCHEMA_VERSION,
        "input": {"kind": input_kind, "name": _safe_text(input_name, "[redacted]"), "sha256": input_sha256,
                  "root_digest": run.project.root_digest.value,
                  "excluded_dirs": sorted({name for name in excluded_dirs if _safe_path(name) is not None})},
        "scan": {"status": "partial" if partial else "completed",
                 "usage": {k: bool(usage.get(k)) for k in ("commercial", "distributed", "modified", "network_service")},
                 "component_count": len(components), "root_package_count": len(root_packages),
                 "ecosystem_counts": counts, "conflict_count": conflict_count,
                 "copyleft_count": len(findings), "incompatible_count": incompatible_count,
                 "review_required_count": review_required_count, "gap_count": len(diagnostics)},
        "root_packages": root_packages,
        "components": components,
        "conflicts": conflicts,
        "root_license_checks": root_checks,
        "copyleft_findings": sorted(findings, key=_json_key),
        "license_compatibility": compatibility,
        "diagnostics": sorted(diagnostics, key=_json_key),
        "policy": {"fail_on": sorted(set(fail_on)), "triggered": triggered, "exit_code": int(bool(triggered))},
    }


def _summary(document: dict) -> list[tuple[str, object]]:
    scan, policy, source = document["scan"], document["policy"], document["input"]
    compat = document["license_compatibility"]
    return [
        ("Input", f"{source['name']} ({source['kind']})"),
        ("Status", scan["status"]),
        ("Components", scan["component_count"]),
        ("Root packages", scan["root_package_count"]),
        ("Target license", f"{compat['target']['license'] or 'UNKNOWN'} ({compat['target']['source']})"),
        ("Ecosystems", ", ".join(f"{name}={count}" for name, count in scan["ecosystem_counts"].items())),
        ("Usage", ", ".join(name for name, active in scan["usage"].items() if active) or "none"),
        ("Confirmed version conflicts", scan["conflict_count"]),
        ("Copyleft findings", scan["copyleft_count"]),
        ("Incompatible license verdicts", scan["incompatible_count"]),
        ("Review-required license verdicts", scan["review_required_count"]),
        ("Diagnostics", scan["gap_count"]),
        ("Fail-on policies", ", ".join(policy["fail_on"]) or "none"),
        ("Triggered policies", ", ".join(policy["triggered"]) or "none"),
        ("Exit code", policy["exit_code"]),
    ]


def _sections(document: dict) -> list[tuple[str, tuple[str, ...], list[tuple]]]:
    compat = document["license_compatibility"]
    return [
        ("Root packages", ("Name", "Version", "Ecosystem", "SPDX"), [
            (row["name"], row["version"], row["ecosystem"], row["declared_license"])
            for row in document["root_packages"]
        ]),
        ("Root license evidence", ("File", "SHA-256", "Text profile", "Declared SPDX", "Conflict", "Support"), [
            (row["file_path"], row["sha256"], row["text_license"], row["declared_license"],
             "SPDX_TEXT_CONFLICT" if row["spdx_text_conflict"] else "—", row["support_state"])
            for row in document["root_license_checks"]
        ]),
        ("License compatibility (target <- dependency)", ("Component", "Version", "Ecosystem", "Declared SPDX", "Status", "Rule"), [
            (row["name"], row["version"], row["ecosystem"], row["declared_license"], row["status"], row["rule_id"])
            for row in compat["target_assessments"]
        ]),
        ("Pairwise license conflicts", ("License A", "License B", "Status", "Rule"), [
            (row["license_a"], row["license_b"], row["status"], row["rule_id"])
            for row in compat["pairwise_conflicts"]
        ]),
        ("Version conflicts", ("Ecosystem", "Name", "Status", "Declaration", "Lock"), [
            (row["ecosystem"], row["name"], row["status"], (row["declaration"] or {}).get("version"),
             (row["lock"] or {}).get("version"))
            for row in document["conflicts"]
        ]),
        ("Copyleft findings", ("Source", "SPDX", "Severity"), [
            (row["source"], row["license_id"], row["severity"]) for row in document["copyleft_findings"]
        ]),
        ("Diagnostics", ("Code", "Stage", "Message"), [
            (row["code"], row["stage"], row["message"]) for row in document["diagnostics"]
        ]),
    ]


def _display(value) -> str:
    return "—" if value is None else str(value)


_MD_PUNCTUATION = str.maketrans({value: f"&#{ord(value)};" for value in "\\|`[]*_~!@"})


def _table(headings, rows) -> list[str]:
    result = [
        "| " + " | ".join(headings) + " |",
        "| " + " | ".join("---" for _ in headings) + " |",
    ]
    result.extend("| " + " | ".join(escape(_display(cell)).translate(_MD_PUNCTUATION) for cell in row) + " |" for row in rows)
    return result


def render_report(document: dict, format: str) -> str:
    if format == "json":
        return json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    summary = _summary(document)
    sections = _sections(document)
    if format == "markdown":
        lines = ["# OpenGuard scan", "", *_table(("Field", "Value"), summary)]
        for title, headings, rows in sections:
            lines.extend(("", f"## {title}", "", *(_table(headings, rows) if rows else ["None observed."])))
    elif format == "text":
        lines = ["OpenGuard scan", *(f"{label}: {value}" for label, value in summary)]
        for title, headings, rows in sections:
            lines.extend(("", title))
            lines.extend("  " + " | ".join(f"{label}: {_display(value)}" for label, value in zip(headings, row))
                         for row in rows)
            if not rows:
                lines.append("  None observed.")
    else:
        raise ValueError("scan_report_format_invalid")
    return "\n".join(lines) + "\n"
