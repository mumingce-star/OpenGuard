from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

from app.domain.models import CONTRACT_VERSION, ReportFormat, ScanRun
from app.reporting import ReportExportError, render_report
from app.reporting.render import REPORT_DISCLAIMER, REPORT_SCHEMA, REPORT_VERSION, RESOURCE_INVENTORY_HEADERS


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PATH = REPOSITORY_ROOT / "examples" / "sample-scan-result.json"


def _sample() -> ScanRun:
    return ScanRun.model_validate_json(SAMPLE_PATH.read_bytes())


def _partial() -> ScanRun:
    run = _sample()
    components = [item.model_copy(update={"license_expression_id": None}) for item in run.components]
    payload = run.model_dump(mode="python")
    payload.update(
        status="partial",
        stage="rules",
        progress=70,
        components=components,
        licenses=[],
        obligations=[],
        findings=[],
        remediations=[],
        report_links=[],
        errors=[
            {
                "code": "rules_stage_not_connected",
                "stage": "rules",
                "message": "License rules are not connected.",
                "recoverable": True,
            }
        ],
        summary={
            "component_count": len(components),
            "ai_asset_count": len(run.ai_assets),
            "evidence_count": len(run.evidence),
            "finding_counts": {"pass": 0, "warning": 0, "review_required": 0, "unknown": 0},
        },
    )
    return ScanRun.model_validate(payload)


def test_json_export_is_stable_and_round_trips_the_frozen_scan() -> None:
    run = _sample()
    first = render_report(run, ReportFormat.JSON)
    second = render_report(run, ReportFormat.JSON)

    assert first == second
    assert first.media_type == "application/json; charset=utf-8"
    assert first.sha256 == hashlib.sha256(first.content).hexdigest()
    payload = json.loads(first.content)
    assert payload["schema"] == REPORT_SCHEMA
    assert payload["version"] == REPORT_VERSION
    assert payload["completeness"] == "complete"
    assert payload["disclaimer"] == REPORT_DISCLAIMER
    assert ScanRun.model_validate(payload["scan_run"]) == run
    assert payload["scan_run"]["contract_version"] == CONTRACT_VERSION


def test_equivalent_top_level_order_produces_identical_json() -> None:
    run = _sample()
    payload = run.model_dump(mode="python")
    for key in ("components", "ai_assets", "licenses", "evidence", "obligations", "findings", "remediations", "errors", "report_links"):
        payload[key] = list(reversed(payload[key]))
    reordered = ScanRun.model_validate(payload)

    assert render_report(run, ReportFormat.JSON).content == render_report(reordered, ReportFormat.JSON).content


@pytest.mark.parametrize("report_format", [ReportFormat.CSV, ReportFormat.RESOURCE_INVENTORY])
def test_csv_export_has_the_competition_seven_field_inventory(report_format: ReportFormat) -> None:
    artifact = render_report(_sample(), report_format)
    rows = list(csv.reader(io.StringIO(artifact.content.decode("utf-8-sig"))))

    assert tuple(rows[0]) == RESOURCE_INVENTORY_HEADERS
    assert len(rows) == 3
    assert all(len(row) == 7 for row in rows)
    assert rows[1][0] == "pydantic（软件组件）"
    assert rows[1][2] == "MIT（待核验）"
    assert rows[1][5] == "待团队人工补充"
    assert rows[1][6] == "待核验"
    assert rows[2][0] == "sample-model（AI model）"


def test_csv_neutralizes_spreadsheet_formula_prefixes_and_controls() -> None:
    run = _sample()
    payload = run.model_dump(mode="python")
    payload["components"][0]["name"] = "=WEBSERVICE(\"https://invalid.example\")\nname"
    changed = ScanRun.model_validate(payload)

    rows = list(csv.reader(io.StringIO(render_report(changed, ReportFormat.CSV).content.decode("utf-8-sig"))))

    assert rows[1][0].startswith("'=WEBSERVICE")
    assert "\n" not in rows[1][0]


def test_html_escapes_untrusted_values_and_has_no_active_script() -> None:
    run = _sample()
    payload = run.model_dump(mode="python")
    payload["project"]["name"] = "<script>alert(1)</script>"
    payload["components"][0]["name"] = "<img src=x onerror=alert(1)>"
    changed = ScanRun.model_validate(payload)

    html = render_report(changed, ReportFormat.HTML).content.decode("utf-8")

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "<script>" not in html
    assert "Content-Security-Policy" in html
    assert REPORT_DISCLAIMER in html


def test_partial_report_discloses_missing_rules_without_inventing_findings() -> None:
    run = _partial()
    json_payload = json.loads(render_report(run, ReportFormat.JSON).content)
    html = render_report(run, ReportFormat.HTML).content.decode("utf-8")
    csv_rows = list(csv.reader(io.StringIO(render_report(run, ReportFormat.CSV).content.decode("utf-8-sig"))))

    assert json_payload["completeness"] == "partial"
    assert json_payload["scan_run"]["findings"] == []
    assert json_payload["scan_run"]["errors"][0]["code"] == "rules_stage_not_connected"
    assert "阶段性报告" in html
    assert "不会在本报告中被推断或补写" in html
    assert "这不等于项目已通过许可证合规核验" in html
    assert all(row[6] == "待核验" for row in csv_rows[1:])


@pytest.mark.parametrize("status,stage,progress", [("queued", "queued", 0), ("running", "scan", 35)])
def test_non_terminal_run_is_not_exportable(status: str, stage: str, progress: int) -> None:
    run = _sample()
    payload = run.model_dump(mode="python")
    payload.update(status=status, stage=stage, progress=progress, finished_at=None)
    if status == "queued":
        payload["started_at"] = None
    candidate = ScanRun.model_validate(payload)

    with pytest.raises(ReportExportError, match="report_not_ready") as error:
        render_report(candidate, ReportFormat.JSON)
    assert error.value.code == "report_not_ready"


@pytest.mark.parametrize("run,report_format", [(object(), ReportFormat.JSON), (_sample(), "json")])
def test_invalid_arguments_fail_with_stable_code(run: object, report_format: object) -> None:
    with pytest.raises(ReportExportError, match="report_invalid_argument") as error:
        render_report(run, report_format)  # type: ignore[arg-type]
    assert error.value.code == "report_invalid_argument"


def test_rendering_does_not_mutate_the_input() -> None:
    run = _partial()
    before = run.model_dump_json()

    for report_format in ReportFormat:
        render_report(run, report_format)

    assert run.model_dump_json() == before
