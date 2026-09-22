"""Chinese presentation of already-bound Report V2 content.

No source reads, AI calls, new compliance conclusions, or changes to the input.
Grouping reuses the assessment presentation policy. The complete input document
is retained, escaped, in a closed appendix. Escaping is not secret redaction.
"""
from __future__ import annotations

from collections import Counter
import html
import json

from app.assessment.review_groups import review_view

HTML_RENDERER_VERSION = "report-v2-html/1.2"

DIMENSIONS = {
    "commercial": "商业使用",
    "modification": "修改与二次开发",
    "closed_distribution": "闭源发布／交付",
    "redistribution": "公开发布与再分发",
    "network_service": "对外在线服务部署",
    "ai_assets": "模型、数据、素材及 API 的独立条件",
}
CONCLUSIONS = {
    "conditional": "可按条件使用",
    "restricted": "当前用途存在限制",
    "unknown": "证据不足，暂无法判断",
    "not_applicable": "不适用",
}
USAGES = {
    "personal": "个人学习", "internal": "企业内部使用",
    "open_source": "修改后开源发布", "closed_source": "闭源产品交付",
    "service": "对外提供服务", "unknown": "用途未确定",
}
SCAN_STATES = {
    "completed": "扫描完成", "partial": "部分扫描完成",
    "failed": "扫描失败", "cancelled": "已取消",
    "queued": "等待扫描", "running": "正在扫描",
}
AI_STATES = {
    "succeeded": "已保存 AI 说明", "fallback": "AI 回退，保留原有记录",
    "failed": "AI 说明失败", "not_requested": "未请求 AI 说明",
}
TASK_STATES = {
    "todo": "待处理", "in_progress": "处理中",
    "done": "已完成", "dismissed": "已驳回",
}

STYLE = """
:root{color-scheme:light;font-family:system-ui,-apple-system,'PingFang SC',sans-serif;
color:#23313d;background:#f5f7f8;line-height:1.7}
*{box-sizing:border-box}body{max-width:1100px;margin:0 auto;padding:32px 20px}
h1{font-size:30px;line-height:1.3;margin:8px 0 16px}h2{font-size:21px;margin:0 0 12px}
h3{font-size:16px;margin:0 0 12px}p{margin:8px 0;overflow-wrap:anywhere}
header,.panel{background:#fff;border:1px solid #dfe6e9;border-radius:12px;
padding:24px;margin-bottom:20px}header{border-top:5px solid #678f95}
.eyebrow,.muted{color:#526674}.eyebrow{font-size:13px;letter-spacing:.1em}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.card{border:1px solid #e1e7eb;border-radius:8px;padding:16px;min-width:0}
.badge{display:inline-block;background:#edf2f5;border-radius:6px;padding:3px 9px;
font-size:14px;font-weight:600}.conditional{background:#edf4ee;color:#3c6147}
.restricted{background:#f9eeee;color:#843c3c}.unknown{background:#f9f3e7;color:#74572a}
.not_applicable{background:#f0f2f4;color:#52606b}
.notice{border-left:3px solid #ad9363;background:#faf7f0;padding:12px 16px}
summary{cursor:pointer;overflow-wrap:anywhere}summary:focus-visible{outline:2px solid #527c83}
details{margin:10px 0;border:1px solid #e1e7eb;border-radius:6px;padding:10px 12px}
details[open]>summary{margin-bottom:10px}pre{white-space:pre-wrap;overflow-wrap:anywhere;
background:#f5f7f8;padding:12px;font:12px/1.6 ui-monospace,monospace}
ol,ul{padding-left:24px;margin:8px 0}li{margin:7px 0;overflow-wrap:anywhere}
.stat{font-size:24px;font-weight:650}.label{font-size:13px;color:#526674}
.task-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
footer{font-size:13px;color:#526674;padding:4px 8px 24px}
@media(max-width:720px){body{padding:16px 12px}.grid{grid-template-columns:1fr}
header,.panel{padding:18px}.task-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media print{body{background:white;max-width:none;padding:0}.panel,header{border-radius:0}
.card{break-inside:avoid}details{break-inside:auto}}
"""


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _unique(values: list[str]) -> list[str]:
    # Exact, stable deduplication for presentation only; no fuzzy/AI merging.
    return list(dict.fromkeys(values))


def _items(values: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{_esc(value)}</li>" for value in values) + "</ul>"


def _one_content(document: dict, authority: str) -> dict:
    matches = [section["content"] for section in document["sections"]
               if section["authority"] == authority]
    if len(matches) != 1 or not isinstance(matches[0], dict):
        raise ValueError("report_html_section_invalid")
    return matches[0]


def _dimension_cards(assessment: dict, view: dict) -> str:
    grouping = {row["id"]: row for row in view["dimensions"]}
    cards = []
    for dimension in assessment["dimensions"]:
        status = dimension["status"]
        if status not in CONCLUSIONS:
            raise ValueError("report_html_conclusion_invalid")
        title = DIMENSIONS.get(dimension["id"], dimension["title"])
        original = dimension["conclusion"]
        parts = [f'<article class="card"><h3>{_esc(title)}</h3>',
                 f'<span class="badge {status}">{_esc(CONCLUSIONS[status])}</span>']
        if original and original != CONCLUSIONS[status]:
            parts.append(f"<p>{_esc(original)}</p>")
        groups = grouping[dimension["id"]]
        if groups["raw_count"]:
            parts.append(f'<p class="muted">{groups["group_count"]} 类待核验原因，'
                         f'对应 {groups["raw_count"]} 条原始记录；不是违规数量。</p>')
        conditions = _unique(dimension["conditions"])
        restrictions = _unique(dimension["restrictions"])
        if conditions or restrictions:
            parts.append('<details><summary>查看该用途的条件与限制</summary>')
            for label, values in (("需要满足的条件", conditions), ("当前限制", restrictions)):
                if values:
                    parts.append(f"<h3>{label}</h3>{_items(values)}")
            parts.append("</details>")
        parts.append("</article>")
        cards.append("".join(parts))
    if not cards:
        return '<p class="notice">当前快照没有评估维度记录；不据此判断可以使用。</p>'
    return '<div class="grid">' + "".join(cards) + "</div>"


def _review_groups(assessment: dict, view: dict) -> str:
    titles = {row["id"]: DIMENSIONS.get(row["id"], row["title"])
              for row in assessment["dimensions"]}
    parts = ['<p class="muted">相同核验清单在多个用途间只展示一次。'
             '各组可能涉及相同资源，数量不能直接相加；分类不改变正式结论。</p>']
    for group in view["groups"]:
        count = len(group["resource_ids"])
        scope = f"关联 {count} 条资源记录" if count else "未定位到具体资源记录"
        parts.append(f'<details class="review-group"><summary>{_esc(group["title"])}'
                     f' · {group["raw_count"]} 条原始记录 · {scope}</summary>')
        parts.append(f'<p>{_esc(group["note"])}</p><p class="muted">适用维度：'
                     f'{_esc("、".join(titles[key] for key in group["dimension_ids"]))}</p>')
        parts.append(_items([item["text"] for item in group["items"]]))
        parts.append("</details>")
    if not view["groups"]:
        parts.append("<p>当前评估没有列出待核验原因；不代表授权已经确认。</p>")
    return "".join(parts)


def _actions(assessment: dict) -> str:
    # Keep exact next_steps, including package names and licensing terminology.
    sources: dict[str, set[str]] = {}
    for row in assessment["resource_evaluations"]:
        for text in row["next_steps"]:
            sources.setdefault(text, set()).add(row["resource_id"])
    if not sources:
        return "<p>当前评估未记录具体核验步骤；不自动补造整改建议。</p>"
    rows = [f'<li>{_esc(text)}<span class="muted">（关联 {len(resources)} 条资源记录）</span></li>'
            for text, resources in sources.items()]
    body = "<ol>" + "".join(rows[:6]) + "</ol>"
    if len(rows) > 6:
        body += (f"<details><summary>展开其余 {len(rows) - 6} 项核验步骤</summary>"
                 '<ol start="7">' + "".join(rows[6:]) + "</ol></details>")
    return '<p class="muted">沿用原评估顺序；相同文本合并展示，不重新生成建议。</p>' + body


def _workflow(workflow: dict) -> str:
    tasks = workflow["tasks"]
    if not tasks:
        return "<p>本报告未包含整改任务；不代表项目没有任务或没有需要处理的问题。</p>"
    counts = Counter(task["status"] for task in tasks)
    if set(counts) - set(TASK_STATES):
        raise ValueError("report_html_task_status_invalid")
    cards = "".join(f'<div class="card"><div class="stat">{counts[status]}</div>'
                    f'<div class="label">{label}</div></div>'
                    for status, label in TASK_STATES.items())
    rows = "".join(f'<li>{_esc(task["title"])} — {TASK_STATES[task["status"]]}'
                   f'，版本 {task["version"]}<p>处理说明：{_esc(task["note"] or "未填写")}</p></li>'
                   for task in tasks)
    return (f'<p>以下仅统计本报告包含的 {len(tasks)} 项固定版本任务，不是当前全项目任务总数。</p>'
            f'<div class="task-grid">{cards}</div>'
            '<details><summary>展开本报告的任务明细</summary><ol>' + rows + '</ol></details>')


def _graph_summary(document: dict) -> str:
    graphs = [section["content"] for section in document["sections"]
              if section["authority"] == "observation"
              and isinstance(section.get("content"), dict)
              and "nodes" in section["content"] and "edges" in section["content"]]
    if not graphs:
        return ""
    if len(graphs) != 1 or graphs[0].get("formal") is not False:
        raise ValueError("report_html_graph_invalid")
    graph = graphs[0]
    coverage = graph["coverage"]
    parts = ['<section class="panel"><h2>本报告的资源关系</h2>',
             f'<p>固定资源图包含 {len(graph["nodes"])} 个节点、{len(graph["edges"])} 条事实关系。</p>',
             '<p class="muted">资源图只展示已有事实关系，不代表授权已确认。',
             '节点、边及证据指针保留在本报告的完整固定快照中。</p>']
    if graph["scan_ref"]["status"] != "completed" or coverage["scan_gaps"]:
        parts.append('<p class="notice">图中已有事实完整展示，不代表扫描覆盖完整。</p>')
    parts.append('</section>')
    return "".join(parts)


def _notice_summary(document: dict) -> str:
    drafts = [row['content'] for row in document['sections']
              if row['authority'] == 'observation' and 'draft_id' in row['content']]
    if not drafts:
        return ''
    parts = ['<section class="panel"><h2>NOTICE 草稿／待人工核验</h2>',
             '<p class="notice">摘录不等于完整原文，草稿不代表义务已履行。缺口不是违规，生成成功不是合规通过。</p>']
    for draft in drafts:
        parts.append(f'<h3>固定草稿 {_esc(draft["draft_id"])}</h3>'
                     f'<p>内容 Hash：{_esc(draft["content_hash"])}</p>')
        for entry in draft['entries']:
            text = entry['text'] if entry['text'] is not None else '材料缺失：未保存原文，不补写法律文本。'
            parts.append(f'<details open><summary>{_esc(entry["entry_id"])}</summary><pre>{_esc(text)}</pre>'
                         '<p>缺失材料（missing）：</p>' + _items(entry['missing']) + '</details>')
        parts.append('<p>覆盖缺口（coverage_gaps）：</p>' + _items(draft['coverage_gaps']))
    parts.append('<p>完整草稿保留在下方固定快照附录中。</p></section>')
    return ''.join(parts)


def render_report_html(document: dict) -> bytes:
    """Render a saved-content document without modifying it or opening sources."""
    assessment = _one_content(document, "formal_assessment")
    scan = _one_content(document, "scan_facts")
    workflow = _one_content(document, "workflow")
    ai = _one_content(document, "ai_explanation")
    if assessment.get("formal") is not True:
        raise ValueError("report_html_assessment_not_formal")
    # Validate that the complete appendix is serializable before rendering.
    raw = json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    view = review_view(assessment)
    binding = document["binding"]
    usage = assessment.get("usage", {}).get("preset", "unknown")
    status = scan["status"]
    title = assessment["project_name"]
    counts = [("组件记录", len(scan["components"])), ("AI 资产记录", len(scan["ai_assets"])),
              ("证据记录", len(scan["evidence"])), ("规则发现记录", len(scan["findings"]))]
    stats = "".join(f'<div class="card"><div class="stat">{count}</div>'
                    f'<div class="label">{label}</div></div>' for label, count in counts)
    parts = ['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             f'<meta name="openguard-html-renderer" content="{HTML_RENDERER_VERSION}">',
             f'<title>{_esc(title)} · OpenGuard 合规报告</title><style>{STYLE}</style></head><body>',
             '<header><div class="eyebrow">OPENGUARD · 固定版本报告</div>',
             f'<h1>{_esc(title)} · 项目合规报告</h1>',
             f'<p>用途：{_esc(USAGES.get(usage, "用途状态未识别"))} · '
             f'扫描：{_esc(SCAN_STATES.get(status, "扫描状态未识别"))} · '
             f'评估版本：{_esc(binding["assessment_ref"]["version"])}</p>',
             '<h2>项目整体评价</h2>',
             f'<p>{_esc(assessment["summary"])}</p>',
             '<p class="muted">以上原文来自这份报告绑定的正式评估，不是本页面重新判断。</p>',
             '<p class="notice">证据不足不等于禁止使用，也不等于可以放心使用。'
             '报告生成成功不表示合规已经验证；任务完成也不表示相关义务已经履行。</p>',
             '</header>']
    if status != "completed":
        parts.append('<section class="panel"><p class="notice">本次不是完整成功扫描。'
                     '缺失记录不等于不存在风险，覆盖限制保留在完整依据中。</p></section>')
    panels = [
        ("不同用途的已有结论", _dimension_cards(assessment, view)),
        ("按类核验清单", _review_groups(assessment, view)),
        ("接下来需要核对什么", _actions(assessment)),
    ]
    for heading, body in panels:
        parts.append(f'<section class="panel"><h2>{heading}</h2>{body}</section>')
    obligations = assessment["obligations"]
    obligation_texts = _unique([item["requirement"] for item in obligations])
    if obligation_texts:
        parts.append('<section class="panel"><h2>已记录的义务要求</h2>'
                     f'<p>{len(obligation_texts)} 种不同文本，来自 {len(obligations)} 条义务记录。'
                     '这里仅合并完全相同的要求文字，履行状态与资源关联仍以完整记录为准。</p>'
                     '<details><summary>展开全部义务要求</summary>' + _items(obligation_texts)
                     + '</details></section>')
    else:
        parts.append('<section class="panel"><h2>已记录的义务要求</h2>'
                     '<p>当前快照没有义务记录；不代表没有义务。</p></section>')
    parts.append('<section class="panel"><h2>整改处理进度</h2>' + _workflow(workflow) + '</section>')
    parts.append(_graph_summary(document))
    parts.append(_notice_summary(document))
    ai_state = AI_STATES.get(ai["ai_status"], "AI 状态未识别，保留原始记录")
    ai_text = ai["ai_summary"] if ai["ai_summary"] is not None else "当前快照未保存 AI 正文。"
    parts.append('<section class="panel"><h2>已有 AI 说明</h2>'
                 f'<p>{_esc(ai_state)}；仅解释已有证据，不替代正式评估。</p>'
                 '<details><summary>展开历史 AI 正文（本次不重新调用模型）</summary>'
                 f'<p>{_esc(ai_text)}</p></details></section>')
    parts.append('<section class="panel"><h2>本次扫描记录概览</h2>'
                 f'<div class="task-grid">{stats}</div><p class="muted">'
                 '规则发现记录不全是违规；AI 资产零记录也不证明不存在 AI 资产。</p></section>')
    parts.append('<section class="panel"><h2>完整依据与版本信息</h2>'
                 '<p>资源明细、证据、原始字段、链接和哈希在下方保留；默认折叠，不删除。'
                 '折叠不是脱敏，分享报告前仍需检查原始证据。</p>'
                 '<details id="report-full-document"><summary>展开完整固定快照与技术依据</summary>'
                 f'<pre id="report-document">{_esc(raw)}</pre></details></section>')
    parts.append('<footer>这是一份历史固定版本报告，不是实时页面。'
                 '后续任务或评估变化不会修改本报告；需要新内容时请显式生成新报告。</footer></body></html>')
    return "".join(parts).encode("utf-8")
