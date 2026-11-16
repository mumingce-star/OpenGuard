"""Pure rendering tests; synthetic display fixtures, no server/DB/AI invocation."""
from __future__ import annotations

from copy import deepcopy
from html.parser import HTMLParser
import json

import pytest

from app.assessment.review_groups import GAP_CODES, review_view
from app.p1.report_v2_html import CONCLUSIONS, DIMENSIONS, render_report_html


class Page(HTMLParser):
    def __init__(self, content: bytes):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.details = []
        self.appendix = []
        self.in_appendix = False
        self.feed(content.decode("utf-8"))

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag == "details":
            self.details.append(dict(attrs))
        if tag == "pre" and dict(attrs).get("id") == "report-document":
            self.in_appendix = True

    def handle_endtag(self, tag):
        if tag == "pre":
            self.in_appendix = False

    def handle_data(self, data):
        if self.in_appendix:
            self.appendix.append(data)


def example():
    gap = next(text for text, code in GAP_CODES.items() if code == "license")
    reason = f"示例依赖（1.0）：{gap}"
    assessment = {
        "id": "asm_html_fixture", "formal": True, "schema_version": "1.0",
        "project_name": "示例项目（仅测试数据）", "summary": "已有扫描事实，许可对应关系仍待核验。",
        "usage": {"preset": "internal"}, "coverage_issues": [],
        "dimensions": [
            {"id": key, "title": title, "status": "unknown",
             "conclusion": CONCLUSIONS["unknown"], "unknowns": [reason, reason],
             "resource_ids": ["cmp_html_fixture"], "conditions": ["保留原许可声明"],
             "restrictions": []}
            for key, title in DIMENSIONS.items()
        ],
        "resource_evaluations": [
            {"name": "示例依赖", "version": "1.0", "resource_id": "cmp_html_fixture",
             "gaps": [gap], "next_steps": ["核对固定版本的许可依据", "核对固定版本的许可依据"]}
        ],
        "obligations": [{"requirement": "保留原许可声明", "id": "o1"},
                        {"requirement": "保留原许可声明", "id": "o2"}],
    }
    scan = {"status": "completed", "components": [{"id": "cmp_html_fixture"}],
            "ai_assets": [], "evidence": [{"id": "evd_html_fixture"}], "findings": []}
    workflow = {"task_refs": [{"task_id": "tsk_fixture", "version": 1}],
                "tasks": [{"task_id": "tsk_fixture", "version": 1, "status": "todo",
                           "title": "核对材料", "note": ""}]}
    return {
        "schema_version": "1.0", "snapshot_id": "rptv2_html_fixture",
        "created_at": "2026-09-15T00:00:00Z", "generator_version": "report-v2/1.0",
        "binding": {"assessment_ref": {"assessment_id": assessment["id"], "version": 1}},
        "sections": [{"authority": authority, "content": content}
                     for authority, content in [
                         ("scan_facts", scan), ("formal_assessment", assessment),
                         ("workflow", workflow),
                         ("ai_explanation", {"ai_status": "fallback", "ai_summary": "保留的历史说明。"}),
                     ]],
        "provenance": {"fixture": True},
    }


def content(doc, authority):
    return next(row["content"] for row in doc["sections"] if row["authority"] == authority)


def test_summary_is_first_and_all_details_are_closed():
    text = render_report_html(example())
    page = Page(text)
    assert page.details and all("open" not in attrs for attrs in page.details)
    value = text.decode()
    assert value.index("项目整体评价") < value.index("不同用途的已有结论") < value.index("按类核验清单")
    assert value.index("按类核验清单") < value.index("完整依据与版本信息")


def test_renderer_does_not_change_input_and_keeps_complete_appendix():
    doc = example()
    before = deepcopy(doc)
    first = render_report_html(doc)
    assert doc == before
    assert render_report_html(doc) == first
    assert json.loads("".join(Page(first).appendix)) == before


def test_uses_existing_shared_groups_and_preserves_occurrences():
    doc = example()
    view = review_view(content(doc, "formal_assessment"))
    page = Page(render_report_html(doc))
    groups = [attrs for tag, attrs in page.tags if tag == "details" and attrs.get("class") == "review-group"]
    assert len(view["groups"]) == len(groups) == 1
    assert view["groups"][0]["raw_count"] == 2
    assert len(view["groups"][0]["dimension_ids"]) == 6
    assert "2 条原始记录" in render_report_html(doc).decode()
    assert "不是违规数量" in render_report_html(doc).decode()


@pytest.mark.parametrize("status", list(CONCLUSIONS))
def test_exact_status_translation_without_new_conclusion(status):
    doc = example()
    for row in content(doc, "formal_assessment")["dimensions"]:
        row.update(status=status, conclusion=CONCLUSIONS[status])
    text = render_report_html(doc).decode()
    assert text.count(f'class="badge {status}"') == 6
    assert CONCLUSIONS[status] in text
    assert "证据不足不等于禁止使用，也不等于可以放心使用" in text


def test_partial_scan_is_never_shown_as_complete_success():
    doc = example()
    content(doc, "scan_facts")["status"] = "partial"
    text = render_report_html(doc).decode()
    assert "部分扫描完成" in text
    assert "本次不是完整成功扫描" in text


def test_untrusted_text_is_escaped_and_cannot_add_active_tags():
    doc = example()
    attack = '<script>alert(1)</script><img src="https://untrusted.example/x" onerror="alert(2)">'
    assessment = content(doc, "formal_assessment")
    assessment["project_name"] = attack
    assessment["summary"] = attack
    assessment["resource_evaluations"][0]["next_steps"] = [attack]
    content(doc, "workflow")["tasks"][0]["note"] = attack
    content(doc, "ai_explanation")["ai_summary"] = attack
    page = Page(render_report_html(doc))
    assert not {"script", "img", "iframe", "object", "embed", "link", "form"} & {tag for tag, _ in page.tags}
    assert all(not key.lower().startswith("on") for _, attrs in page.tags for key in attrs)
    assert json.loads("".join(page.appendix)) == doc


def test_done_is_only_workflow_status_not_compliance():
    doc = example()
    content(doc, "workflow")["tasks"][0].update(status="done", note="已核对提交材料")
    text = render_report_html(doc).decode()
    assert "任务完成也不表示相关义务已经履行" in text
    assert "仅统计本报告包含的 1 项固定版本任务" in text
    assert "已核对提交材料" in text
    assert "合规率" not in text


def test_empty_tasks_not_equated_with_no_problems():
    doc = example()
    content(doc, "workflow").update(tasks=[], task_refs=[])
    assert "本报告未包含整改任务；不代表项目没有任务" in render_report_html(doc).decode()


def test_historical_ai_status_and_text_are_not_promoted():
    doc = example()
    text = render_report_html(doc).decode()
    assert "AI 回退，保留原有记录" in text
    assert "保留的历史说明。" in text
    assert "本次不重新调用模型" in text
    content(doc, "ai_explanation").update(ai_status="not_requested", ai_summary=None)
    text = render_report_html(doc).decode()
    assert "未请求 AI 说明" in text and "当前快照未保存 AI 正文" in text


def test_all_actions_remain_available_after_display_limit():
    doc = example()
    content(doc, "formal_assessment")["resource_evaluations"][0]["next_steps"] = [f"核验步骤 {i}" for i in range(10)]
    text = render_report_html(doc).decode()
    assert "展开其余 4 项核验步骤" in text
    assert all(f"核验步骤 {i}" in text for i in range(10))


def test_no_sources_opened_no_network_or_model_calls(monkeypatch):
    doc = example()
    def forbidden(*args, **kwargs):
        raise AssertionError("renderer must not open sources or invoke external work")
    monkeypatch.setattr("builtins.open", forbidden)
    monkeypatch.setattr("socket.socket.connect", forbidden)
    monkeypatch.setattr("subprocess.Popen", forbidden)
    assert render_report_html(doc).startswith(b"<!doctype html>")


@pytest.mark.parametrize("problem", ["nonformal", "missing", "duplicate", "invalid_status"])
def test_unsupported_inputs_are_not_silently_converted_to_success(problem):
    doc = example()
    if problem == "nonformal":
        content(doc, "formal_assessment")["formal"] = False
    elif problem == "missing":
        doc["sections"] = [row for row in doc["sections"] if row["authority"] != "formal_assessment"]
    elif problem == "duplicate":
        doc["sections"].append(deepcopy(doc["sections"][1]))
    else:
        content(doc, "formal_assessment")["dimensions"][0]["status"] = "approved"
    with pytest.raises(ValueError):
        render_report_html(doc)
