"""Render one validated terminal ``ScanRun`` without inventing missing facts."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from html import escape
from typing import Any

from app.domain.grouping import build_grouping
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
    # Delivery links contain the digest of this report.  Embedding them would
    # create a recursive hash, so reports always carry the analytical snapshot
    # with delivery metadata projected out.  The canonical ScanRun/API remains
    # authoritative for ReportLink values.
    payload["report_links"] = []
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
        "grouping": build_grouping(run),
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


def _html_raw_table(headers: tuple[str, ...], rows: list[tuple[str, ...]], *, empty: str) -> str:
    """Render cells already assembled from escaped values and fixed markup."""
    head = "".join(f"<th>{escape(value)}</th>" for value in headers)
    if rows:
        body = "".join("<tr>" + "".join(f"<td>{value}</td>" for value in row) + "</tr>" for row in rows)
    else:
        body = f'<tr><td colspan="{len(headers)}">{escape(empty)}</td></tr>'
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _html_list(values: list[str], *, empty: str = "无") -> str:
    if not values:
        return f"<p>{escape(empty)}</p>"
    return "<ul>" + "".join(f"<li>{escape(value)}</li>" for value in values) + "</ul>"


def _resource_maps(run: ScanRun) -> tuple[dict[str, Component | AIAsset], dict[str, str]]:
    resources: dict[str, Component | AIAsset] = {}
    kinds: dict[str, str] = {}
    for item in run.components:
        resources[item.id] = item
        kinds[item.id] = "软件组件"
    for item in run.ai_assets:
        resources[item.id] = item
        kinds[item.id] = {
            "model": "模型", "dataset": "数据集", "api": "API", "service": "服务", "asset": "素材",
        }.get(item.asset_type.value, "AI 资源")
    return resources, kinds


def _resource_source(resource: Component | AIAsset) -> str:
    if isinstance(resource, Component):
        return resource.source_url or resource.purl or resource.ecosystem
    return resource.source_url or resource.provider or "未声明"


def _render_html(run: ScanRun) -> bytes:
    grouping = build_grouping(run)
    groups = grouping["groups"]
    resources_by_id, resource_kinds = _resource_maps(run)
    findings_by_id = {item.id: item for item in run.findings}
    evidence_by_id = {item.id: item for item in run.evidence}
    licenses = _license_map(run)
    remediations_by_finding = {item.finding_id: item for item in run.remediations}
    completeness = "完整报告" if run.status is ScanStatus.COMPLETED else "阶段性报告（部分结果）"
    state_note = (
        "扫描主链已完成。"
        if run.status is ScanStatus.COMPLETED
        else "当前扫描只完成部分阶段；未产生的许可证规则、风险或 AI 建议不会在本报告中被推断或补写。"
    )
    severity_counts = {level: 0 for level in ("high", "medium", "low", "info")}
    for finding in run.findings:
        severity_counts[finding.severity.value] += 1
    severity_text = "、".join(f"{key} {value}" for key, value in severity_counts.items())
    coverage_ids = {
        evidence_id for error in run.errors if error.code == "git_scan_coverage_partial"
        for evidence_id in error.evidence_ids
    }
    coverage_note = (
        f"发现 {len(coverage_ids)} 条未覆盖证据；本报告不能证明整个仓库均已核验。"
        if coverage_ids else "未报告单独的扫描覆盖缺口；仍应结合任务终态和错误记录理解范围。"
    )
    coverage_rows = [
        (item.locator, item.excerpt or "")
        for item in sorted(run.evidence, key=lambda value: value.locator)
        if item.id in coverage_ids
    ]
    coverage_details = (
        '<h3>扫描覆盖范围：未扫描条目</h3><p>以下条目未纳入本次扫描；本报告不能用于证明整个仓库均已完成核验。</p>'
        + _html_table(("仓库路径", "未覆盖原因与 Git 对象"), coverage_rows, empty="无未覆盖记录。")
        if coverage_rows else ""
    )

    category_blocks: list[str] = []
    advice_blocks: list[str] = []
    for category_name in dict.fromkeys(str(group["category_name"]) for group in groups):
        category_groups = [group for group in groups if group["category_name"] == category_name]
        rendered_groups: list[str] = []
        for group in category_groups:
            member_rows: list[tuple[str, ...]] = []
            for finding_id in group["finding_ids"]:
                finding = findings_by_id[finding_id]
                resource = resources_by_id[finding.resource_id]
                license_label = _license_label(resource, licenses)
                evidence_links = "、".join(
                    f'<a href="#evidence-{escape(item)}">{escape(item)}</a>' for item in finding.evidence_ids
                ) or "无"
                remediation = remediations_by_finding.get(finding.id)
                historical_advice = (
                    f'<details><summary>历史成员建议</summary><p>{escape(remediation.summary)}</p>'
                    + _html_list([str(step) for step in remediation.steps]) + "</details>"
                    if group["advice"]["kind"] == "historical" and remediation is not None
                    else ""
                )
                identity = (
                    f'<strong>{escape(resource.name)}</strong><br>版本：{escape(resource.version or "未知")}'
                    f'<details><summary>技术标识</summary><p>资源：{escape(resource.id)}<br>发现：{escape(finding.id)}'
                    f'<br>规则：{escape(finding.rule_id)}@{escape(finding.rule_version)}</p>{historical_advice}</details>'
                )
                difference = (
                    f'{escape(_resource_source(resource))}<br>证据位置：{escape("；".join(evidence_by_id[i].locator for i in finding.evidence_ids))}<br><strong>个体触发：</strong>{escape(finding.trigger)}'
                    f'<details><summary>完整扫描结论</summary><p>{escape(finding.description)}</p></details>'
                )
                member_rows.append((
                    identity, f'{escape(license_label)}<br>等级：{escape(finding.severity.value)}',
                    difference, evidence_links,
                    f'<a href="#advice-{escape(group["id"])}">{escape(group["id"])} 组建议</a>',
                ))
            context = group.get("context", {})
            context_text = "；".join(f"{key}={value}" for key, value in context.items() if value not in (None, "", [], {}))
            advice = group["advice"]
            advice_kind = {
                "group_ai": "组级 AI 共用建议", "rule": "规则共用建议",
                "historical": "历史逐成员 AI 建议（保留可查，未声明为本组共享生成）",
                "unavailable": "建议不可用",
            }.get(advice["kind"], advice["kind"])
            rendered_groups.append(
                f'<details class="group" id="group-{escape(group["id"])}"><summary><strong>{escape(group["title"])}</strong>'
                f'　{len(group["finding_ids"])} 条发现 / {len(group["resource_ids"])} 项资源</summary>'
                f'<p>{escape(group["summary"])}</p><details class="context"><summary>分组技术依据</summary>'
                f'<p>{escape(context_text or "接口未提供")}</p></details>'
                f'<p><a href="#advice-{escape(group["id"])}">查看本组建议</a></p>'
                + _html_raw_table(("资源名称 / 版本", "许可 / 真实等级", "来源 / 个体触发差异", "证据", "建议"), member_rows, empty="无成员。")
                + "</details>"
            )
            advice_blocks.append(
                f'<article id="advice-{escape(group["id"])}"><h3>{escape(group["title"])}</h3>'
                f'<p><strong>{escape(advice_kind)}</strong>：{escape(advice.get("summary") or "未提供建议摘要")}</p>'
                + _html_list([str(step) for step in advice.get("steps", [])], empty="未提供可执行步骤。")
                + f'<p>适用范围：<a href="#group-{escape(group["id"])}">{escape(group["id"])} 分组</a>，'
                f'共 {len(group["finding_ids"])} 条成员发现。每条发现 ID 可在该组的成员技术详情中查看。</p></article>'
            )
        category_blocks.append(f'<section class="category"><h3>{escape(category_name)}</h3>{"".join(rendered_groups)}</section>')

    resource_rows = []
    for resource_id, resource in sorted(resources_by_id.items(), key=lambda pair: (pair[1].name.casefold(), pair[0])):
        related = [item for item in run.findings if item.resource_id == resource_id]
        identity = (
            f'<span id="resource-{escape(resource.id)}"><strong>{escape(resource.name)}</strong></span>'
            f'<br>版本：{escape(resource.version or "未知")}<details><summary>资源标识</summary>'
            f'<p>{escape(resource.id)}</p></details>'
        )
        resource_evidence = "、".join(
            f'<a href="#evidence-{escape(evidence_id)}">{escape(evidence_id)}</a>'
            for evidence_id in resource.evidence_ids
        ) or "无"
        resource_rows.append((identity, f'{escape(resource_kinds[resource_id])}<br>{escape(_license_label(resource, licenses))}',
                              escape(_resource_source(resource)), str(len(related)), resource_evidence))
    model_asset_links = [
        f'<li><a href="#resource-{escape(resource_id)}">{escape(resource.name)}</a>：'
        f'{escape(resource_kinds[resource_id])}，版本 {escape(resource.version or "未知")}</li>'
        for resource_id, resource in sorted(resources_by_id.items(), key=lambda pair: (pair[1].name.casefold(), pair[0]))
        if resource_kinds[resource_id] in {"模型", "数据集"}
    ]
    model_asset_index = (
        '<p>以下条目复用第三方资源清单，不重复整段资源表：</p><ul>' + "".join(model_asset_links) + "</ul>"
        if model_asset_links else "<p>本次未识别到模型或数据集。</p>"
    )
    evidence_rows = [
        (f'<span id="evidence-{escape(item.id)}"><strong>{escape(item.id)}</strong></span>', escape(item.kind.value),
         escape(item.locator), escape(item.excerpt or ""), escape(item.verification_status.value),
         escape("、".join(finding.id for finding in run.findings if item.id in finding.evidence_ids) or "无"))
        for item in sorted(run.evidence, key=lambda value: value.id)
    ]
    error_rows = [(item.stage.value, item.code, item.message, "是" if item.recoverable else "否")
                  for item in sorted(run.errors, key=lambda value: (value.stage.value, value.code, value.message))]
    title = escape(f"OpenGuard 报告 - {run.project.name}")
    document = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>{title}</title><style>
body {{ margin:32px auto; max-width:1180px; padding:0 24px; color:#172033; font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif }}
h1,h2,h3 {{ color:#0d2145 }} nav a {{ margin-right:16px }} .meta,.context,footer {{ color:#52627a }}
.state,.print-note {{ padding:12px 16px; background:#eef4ff; border-left:4px solid #2f6fed }}
.partial {{ background:#fff4df; border-color:#c97800 }} table {{ width:100%; border-collapse:collapse; margin:12px 0 24px }}
th,td {{ border:1px solid #d7deea; padding:7px; text-align:left; vertical-align:top; overflow-wrap:anywhere }} th {{ background:#edf2f9 }}
details {{ margin:10px 0 }} summary {{ cursor:pointer; padding:8px; background:#f6f8fb }} footer {{ margin-top:32px }}
@media print {{ nav {{ display:none }} details > * {{ display:block !important }} details::details-content {{ content-visibility:visible !important; display:block !important }} details > summary {{ display:list-item !important }} body {{ margin:0; max-width:none }} }}
</style></head><body>
<header><h1>OpenGuard AI 开源合规扫描报告</h1><p class="meta">扫描：{escape(run.id)}　项目：{escape(run.project.name)}　revision：{escape(run.project.revision or "未声明")}</p>
<p class="meta">输入：{escape(run.project.source)}　OpenGuard：{escape(run.provenance.run_environment.openguard_version)}　规则集：{escape(run.provenance.ruleset_version)}</p>
<p class="state{' partial' if run.status is ScanStatus.PARTIAL else ''}"><strong>{completeness}</strong>：{escape(state_note)} {escape(coverage_note)}</p>
<p>{escape(REPORT_DISCLAIMER)}</p></header>
<nav aria-label="报告目录"><a href="#report-0">01 执行摘要</a><a href="#report-1">02 风险清单</a><a href="#report-2">03 第三方资源</a><a href="#report-3">04 模型与数据集</a><a href="#report-4">05 整改建议</a><a href="#report-5">06 证据附录</a></nav>
<main><section id="report-0"><h2>01 / 执行摘要</h2><p>终态：{escape(run.status.value)}；阶段：{escape(run.stage.value)}；发现 {grouping['finding_count']} 条，涉及 {grouping['resource_count']} 项唯一资源；问题大类 {len(set(group['category_id'] for group in groups))} 个，等价情境组 {len(groups)} 个；严重度：{escape(severity_text)}。</p>
<p>优先核验较高等级条目、证据不足与扫描未覆盖项。进度 {run.progress}% 表示处理流程进度，不表示许可证正确率或仓库覆盖率。</p></section>
<section id="report-1"><h2>02 / 风险清单</h2><p class="print-note">完整离线明细：屏幕上可逐组展开；打印或保存 PDF 时将显示全部成员明细。</p>{''.join(category_blocks) or '<p>当前结果没有可展示的规则风险；这不等于项目已通过许可证合规核验。</p>'}</section>
<section id="report-2"><h2>03 / 第三方资源</h2><details><summary>展开 {len(resource_rows)} 项资源完整清单</summary>{_html_raw_table(("资源名称 / 版本","类型 / 许可","来源","关联发现数","源证据"), resource_rows, empty="未识别到资源。")}</details></section>
<section id="report-3"><h2>04 / 模型与数据集</h2>{model_asset_index}</section>
<section id="report-4"><h2>05 / 整改建议</h2><p>每组建议仅在此处完整列出；风险明细通过组 ID 引用。建议不改变扫描事实、等级、许可或证据。</p>{''.join(advice_blocks) or '<p>暂无整改建议。</p>'}</section>
<section id="report-5"><h2>06 / 证据附录</h2><details><summary>展开 {len(evidence_rows)} 条证据完整附录</summary>{_html_raw_table(("证据ID","类型","位置","原文摘录","核验状态","关联发现ID"), evidence_rows, empty="暂无可展示的证据。")}</details>
{coverage_details}<h3>运行状态、覆盖范围与未完成项</h3><p>{escape(coverage_note)}</p>{_html_table(("阶段","错误码","说明","可恢复"), error_rows, empty="无结构化错误。")}
<h3>复现信息</h3><p>契约 {escape(run.contract_version)}；输入摘要 {escape(run.provenance.input_digest.value)}；分组契约 {escape(grouping['version'])}。</p></section></main>
<footer>报告生成自任务快照；原始发现、资源和证据均保留在本离线文件中。</footer></body></html>"""
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
