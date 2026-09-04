"""Render one validated terminal ``ScanRun`` without inventing missing facts."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from html import escape
from typing import Any

from app.domain.models import (
    AIAsset,
    Component,
    FindingOutcome,
    LicenseExpression,
    Obligation,
    ReportFormat,
    RiskFinding,
    ScanRun,
    ScanStatus,
    VerificationStatus,
)


REPORT_SCHEMA = "openguard.report"
REPORT_VERSION = 1
REPORT_DISCLAIMER = "本报告仅用于开源合规信息整理与风险提示，不构成法律意见；待核验内容须由项目负责人复核。"
RESOURCE_INVENTORY_HEADERS = (
    "资源名称及类型",
    "版本/来源",
    "许可证/授权类型",
    "使用/开放方式",
    "关键义务/限制",
    "团队自主修改或开发内容",
    "合规状态",
)
_READY_STATUSES = frozenset({ScanStatus.COMPLETED, ScanStatus.PARTIAL})


class ReportExportError(RuntimeError):
    """Stable internal error raised before an export is published."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ReportArtifact:
    """In-memory report ready for a later persistence or HTTP adapter."""

    format: ReportFormat
    media_type: str
    filename: str
    content: bytes
    sha256: str


def _fail(code: str) -> None:
    raise ReportExportError(code) from None


def _canonical_run(run: ScanRun) -> dict[str, Any]:
    payload = run.model_dump(mode="json")
    for key in ("components", "ai_assets", "licenses", "evidence", "obligations", "findings", "remediations"):
        payload[key] = sorted(payload[key], key=lambda item: item["id"])
    payload["errors"] = sorted(
        payload["errors"],
        key=lambda item: (item["stage"], item["code"], item["message"], item.get("tool") or ""),
    )
    payload["report_links"] = sorted(payload["report_links"], key=lambda item: (item["format"], item["href"]))
    payload["provenance"]["tool_versions"] = sorted(
        payload["provenance"]["tool_versions"],
        key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )
    return payload


def _report_payload(run: ScanRun) -> dict[str, Any]:
    return {
        "schema": REPORT_SCHEMA,
        "version": REPORT_VERSION,
        "completeness": "complete" if run.status is ScanStatus.COMPLETED else "partial",
        "disclaimer": REPORT_DISCLAIMER,
        "scan_run": _canonical_run(run),
    }


def _license_map(run: ScanRun) -> dict[str, LicenseExpression]:
    return {item.id: item for item in run.licenses}


def _resource_findings(run: ScanRun) -> dict[str, list[RiskFinding]]:
    result: dict[str, list[RiskFinding]] = {}
    for finding in sorted(run.findings, key=lambda item: item.id):
        result.setdefault(finding.resource_id, []).append(finding)
    return result


def _license_obligations(run: ScanRun) -> dict[str, list[Obligation]]:
    result: dict[str, list[Obligation]] = {}
    for obligation in sorted(run.obligations, key=lambda item: item.id):
        result.setdefault(obligation.license_expression_id, []).append(obligation)
    return result


def _license_label(resource: Component | AIAsset, licenses: dict[str, LicenseExpression]) -> str:
    if resource.license_expression_id is None:
        return "待核验"
    license_expression = licenses.get(resource.license_expression_id)
    if license_expression is None:
        return "待核验"
    suffix = "已核验" if license_expression.verification_status is VerificationStatus.VERIFIED else "待核验"
    return f"{license_expression.expression}（{suffix}）"


def _obligation_label(
    resource: Component | AIAsset,
    obligations: dict[str, list[Obligation]],
) -> str:
    if resource.license_expression_id is None:
        return "待规则引擎核验"
    values = obligations.get(resource.license_expression_id, [])
    if not values:
        return "待规则引擎核验"
    return "；".join(f"{item.action}：{item.description}" for item in values)


def _compliance_status(
    resource: Component | AIAsset,
    licenses: dict[str, LicenseExpression],
    findings: dict[str, list[RiskFinding]],
) -> str:
    license_expression = licenses.get(resource.license_expression_id or "")
    related = findings.get(resource.id, [])
    if license_expression is None or license_expression.verification_status is not VerificationStatus.VERIFIED:
        return "待核验"
    if not related or any(item.outcome is not FindingOutcome.PASS for item in related):
        return "待核验"
    return "已核验"


def _resource_rows(run: ScanRun) -> list[tuple[str, ...]]:
    licenses = _license_map(run)
    findings = _resource_findings(run)
    obligations = _license_obligations(run)
    rows: list[tuple[str, ...]] = []

    for component in sorted(run.components, key=lambda item: (item.name.casefold(), item.id)):
        source = component.source_url or component.purl or component.ecosystem
        rows.append(
            (
                f"{component.name}（软件组件）",
                f"{component.version or '未声明'} / {source}",
                _license_label(component, licenses),
                "项目依赖（具体使用与分发方式待人工确认）",
                _obligation_label(component, obligations),
                "待团队人工补充",
                _compliance_status(component, licenses, findings),
            )
        )

    for asset in sorted(run.ai_assets, key=lambda item: (item.name.casefold(), item.id)):
        source = asset.source_url or asset.provider or "未声明"
        rows.append(
            (
                f"{asset.name}（AI {asset.asset_type.value}）",
                f"{asset.version or '未声明'} / {source}",
                _license_label(asset, licenses),
                "AI 资源引用（具体使用与开放方式待人工确认）",
                _obligation_label(asset, obligations),
                "待团队人工补充",
                _compliance_status(asset, licenses, findings),
            )
        )
    return rows


def _csv_cell(value: str) -> str:
    sanitized = value.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    if sanitized.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + sanitized
    return sanitized


def _render_json(run: ScanRun) -> bytes:
    text = json.dumps(
        _report_payload(run),
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    )
    return (text + "\n").encode("utf-8")


def _render_csv(run: ScanRun) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(RESOURCE_INVENTORY_HEADERS)
    for row in _resource_rows(run):
        writer.writerow([_csv_cell(value) for value in row])
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def _html_table(headers: tuple[str, ...], rows: list[tuple[str, ...]], *, empty: str) -> str:
    head = "".join(f"<th>{escape(value)}</th>" for value in headers)
    if rows:
        body = "".join(
            "<tr>" + "".join(f"<td>{escape(value)}</td>" for value in row) + "</tr>"
            for row in rows
        )
    else:
        body = f'<tr><td colspan="{len(headers)}">{escape(empty)}</td></tr>'
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _render_html(run: ScanRun) -> bytes:
    completeness = "完整报告" if run.status is ScanStatus.COMPLETED else "阶段性报告"
    state_note = (
        "扫描主链已完成。"
        if run.status is ScanStatus.COMPLETED
        else "当前扫描只完成部分阶段；未产生的许可证规则、风险或 AI 建议不会在本报告中被推断或补写。"
    )
    resource_rows = _resource_rows(run)
    finding_rows = [
        (
            item.id,
            item.outcome.value,
            item.severity.value,
            item.title,
            item.rule_id,
            "、".join(item.evidence_ids) or "无",
        )
        for item in sorted(run.findings, key=lambda item: item.id)
    ]
    error_rows = [
        (item.stage.value, item.code, item.message, "是" if item.recoverable else "否")
        for item in sorted(run.errors, key=lambda item: (item.stage.value, item.code, item.message))
    ]
    resources = _html_table(RESOURCE_INVENTORY_HEADERS, resource_rows, empty="未识别到资源。")
    findings = _html_table(
        ("风险ID", "结论", "严重度", "标题", "规则", "证据ID"),
        finding_rows,
        empty="当前结果没有可展示的规则风险；这不等于项目已通过许可证合规核验。",
    )
    errors = _html_table(("阶段", "错误码", "说明", "可恢复"), error_rows, empty="无结构化错误。")
    title = escape(f"OpenGuard 报告 - {run.project.name}")
    project_name = escape(run.project.name)
    source = escape(run.project.source)
    scan_id = escape(run.id)
    status = escape(run.status.value)
    stage = escape(run.stage.value)
    disclaimer = escape(REPORT_DISCLAIMER)
    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
  <title>{title}</title>
  <style>
    body {{ margin: 32px auto; max-width: 1120px; padding: 0 24px; color: #172033; font: 14px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    h1, h2 {{ color: #0d2145; }} .meta {{ color: #52627a; }} .state {{ padding: 12px 16px; background: #eef4ff; border-left: 4px solid #2f6fed; }}
    table {{ width: 100%; border-collapse: collapse; margin: 12px 0 28px; }} th, td {{ border: 1px solid #d7deea; padding: 8px; text-align: left; vertical-align: top; }} th {{ background: #edf2f9; }}
    footer {{ margin-top: 32px; color: #52627a; }}
  </style>
</head>
<body>
  <h1>OpenGuard AI 开源合规扫描报告</h1>
  <p class="meta">扫描：{scan_id}　项目：{project_name}　状态：{status}　阶段：{stage}</p>
  <p class="meta">输入：{source}</p>
  <p class="state"><strong>{completeness}</strong>：{escape(state_note)}</p>
  <h2>资源与第三方使用清单</h2>
  {resources}
  <h2>风险结果</h2>
  {findings}
  <h2>运行状态与未完成项</h2>
  {errors}
  <h2>复现信息</h2>
  <p>OpenGuard {escape(run.provenance.run_environment.openguard_version)}；契约 {escape(run.contract_version)}；规则集 {escape(run.provenance.ruleset_version)}；输入摘要 {escape(run.provenance.input_digest.value)}。</p>
  <footer>{disclaimer}</footer>
</body>
</html>
"""
    return document.encode("utf-8")


def render_report(run: ScanRun, report_format: ReportFormat) -> ReportArtifact:
    """Render a terminal result to memory; persistence and HTTP are separate adapters."""

    if type(run) is not ScanRun or type(report_format) is not ReportFormat:
        _fail("report_invalid_argument")
    if run.status not in _READY_STATUSES:
        _fail("report_not_ready")

    if report_format is ReportFormat.JSON:
        content = _render_json(run)
        media_type = "application/json; charset=utf-8"
        extension = "json"
    elif report_format in {ReportFormat.CSV, ReportFormat.RESOURCE_INVENTORY}:
        content = _render_csv(run)
        media_type = "text/csv; charset=utf-8"
        extension = "resources.csv" if report_format is ReportFormat.RESOURCE_INVENTORY else "csv"
    elif report_format is ReportFormat.HTML:
        content = _render_html(run)
        media_type = "text/html; charset=utf-8"
        extension = "html"
    else:
        _fail("report_invalid_argument")

    return ReportArtifact(
        format=report_format,
        media_type=media_type,
        filename=f"openguard-{run.id}.{extension}",
        content=content,
        sha256=hashlib.sha256(content).hexdigest(),
    )


__all__ = [
    "REPORT_DISCLAIMER",
    "REPORT_SCHEMA",
    "REPORT_VERSION",
    "RESOURCE_INVENTORY_HEADERS",
    "ReportArtifact",
    "ReportExportError",
    "render_report",
]
