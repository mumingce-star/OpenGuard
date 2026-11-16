"""Read-only grouping of saved assessment reasons. Never changes a conclusion."""
from __future__ import annotations

import hashlib
import html
import json
from collections import defaultdict
from collections.abc import Mapping

VIEW_VERSION = "review-groups/1"
# Exact matches prevent package names or new messages being silently reclassified.
GAP_CODES = {
    "版本未固定，版本范围或分支名不能证明实际使用版本": "version",
    "项目自身／依赖／开发示例的适用范围尚无已核验证据": "scope",
    "许可原文及其与本对象版本的适用关系尚未核验": "license",
    "当前有限决策表未覆盖该许可表达式、对象类型或范围，不推断其它授权": "rules",
}
USAGE_REASON = "该用途细节未明确；预设名称不会自动补齐用途前提"
AI_REASON = "模型、数据、素材和 API 需独立核验；未检出不等于不存在或不适用"
CATEGORIES = {
    "usage": ("用途尚未明确", "确认准备怎样使用或交付项目；未知不是默认同意。"),
    "license": ("许可与对象版本的对应关系待核验", "核对相关资源的许可依据；根许可证不自动适用于依赖。"),
    "version": ("实际版本待确定", "已有版本范围不等于实际安装或交付版本；不要求为核验而执行目标项目。"),
    "scope": ("实际使用或交付范围待确认", "声明位置可已知，但最终使用范围仍需依据；两者不要混为一谈。"),
    "coverage": ("覆盖限制及项目级说明", "这里含扫描诊断、汇总状态和项目级说明，不等于独立漏扫或违规数量。"),
    "rules": ("当前决策能力尚未覆盖", "这是系统能力边界，不应全部转嫁为用户补资料任务。"),
    "ai_review": ("AI资产需要独立核对", "没有资源记录不等于绝对不存在；提示数量不是资产数量。"),
    "other": ("其他待核验原因", "未识别的新原因保留原文，不静默删除或套用已知类别。"),
}


def _document(value):
    data = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    if not isinstance(data, Mapping):
        raise ValueError("review_group_invalid_assessment")
    return data


def _strings(value):
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("review_group_invalid_strings")
    return value


def review_view(assessment) -> dict:
    """Group all occurrences; every unknown index remains traceable, including duplicates."""
    data = _document(assessment)
    coverage = set(_strings(data["coverage_issues"]))
    lookup = defaultdict(list)
    for row in data["resource_evaluations"]:
        for gap in _strings(row["gaps"]):
            text = f'{row["name"]}（{row["version"] or "版本未确定"}）：{gap}'
            lookup[text].append((GAP_CODES.get(gap, "other"), row["resource_id"]))

    groups, dimensions = {}, []
    seen_dimensions = set()
    for dimension in data["dimensions"]:
        dim_id = dimension["id"]
        if dim_id in seen_dimensions:
            raise ValueError("review_group_duplicate_dimension")
        seen_dimensions.add(dim_id)
        relevant_ids = set(_strings(dimension["resource_ids"]))
        buckets = defaultdict(list)
        for index, text in enumerate(_strings(dimension["unknowns"])):
            hits = [(code, rid) for code, rid in lookup.get(text, []) if rid in relevant_ids]
            resources = sorted({resource for _, resource in hits})
            if hits:
                codes = {code for code, _ in hits}
                code = next(iter(codes)) if len(codes) == 1 else "other"
            elif text in coverage:
                code = "coverage"
            elif text == USAGE_REASON:
                code = "usage"
            elif text == AI_REASON:
                code = "ai_review"
            else:
                code = "other"
            buckets[code].append((index, {"text": text, "resource_ids": resources}))

        references = []
        for code in CATEGORIES:
            if code not in buckets:
                continue
            rows = buckets[code]
            # Preserve multiplicity. Sharing groups does not erase raw occurrences.
            members = [member for _, member in rows]
            fingerprint = json.dumps([code, members], ensure_ascii=False,
                                     sort_keys=True, separators=(",", ":"))
            gid = "rg_" + hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
            if gid not in groups:
                resources = sorted({rid for member in members for rid in member["resource_ids"]})
                groups[gid] = {
                    "id": gid, "code": code, "title": CATEGORIES[code][0],
                    "note": CATEGORIES[code][1], "items": members,
                    "raw_count": len(members), "resource_ids": resources,
                    "dimension_ids": [],
                }
            groups[gid]["dimension_ids"].append(dim_id)
            references.append({"group_id": gid, "unknown_indices": [index for index, _ in rows]})
        if sorted(index for ref in references for index in ref["unknown_indices"]) != list(range(len(dimension["unknowns"]))):
            raise ValueError("review_group_coverage_mismatch")
        dimensions.append({"id": dim_id, "raw_count": len(dimension["unknowns"]),
                           "group_count": len(references), "groups": references})

    return {"view_version": VIEW_VERSION, "assessment_id": data["id"],
            "formal": False, "groups": list(groups.values()), "dimensions": dimensions}


def present_assessment(assessment) -> dict:
    """Add presentation only to an API response; do not persist or change stored schema."""
    data = _document(assessment)
    return {**data, "review_view": review_view(data)}


def render_grouped_reviews(assessment) -> str:
    """One shared grouping policy for report and API. Escape all source-derived text."""
    data = _document(assessment)
    view = review_view(data)
    esc = lambda value: html.escape(str(value), quote=True)
    by_dimension = {item["id"]: item for item in view["dimensions"]}
    titles = {item["id"]: item["title"] for item in data["dimensions"]}
    result = []
    for dimension in data["dimensions"]:
        grouping = by_dimension[dimension["id"]]
        parts = [f'<section><h2>{esc(dimension["title"])}：{esc(dimension["conclusion"])}</h2>']
        for label, field in (("需要满足", "conditions"), ("限制", "restrictions")):
            parts.extend(f'<p>{label}：{esc(text)}</p>' for text in dimension[field])
        if grouping["raw_count"]:
            parts.append(f'<p>{grouping["group_count"]}类待核验原因，关联{grouping["raw_count"]}条原始记录；不是违规数量。</p>')
            parts.append('<a href="#review-groups">查看下方按类核验清单</a>')
        parts.append('</section>')
        result.extend(parts)

    result.append('<section id="review-groups"><h2>按类核验清单</h2><p>相同清单在多个用途间只展示一次；分类不改变任何正式结论。各组可能涉及相同资源，数量不能直接相加。</p>')
    for group in view["groups"]:
        names = "、".join(titles[key] for key in group["dimension_ids"])
        resource_note = f'，关联{len(group["resource_ids"])}条资源记录' if group["resource_ids"] else "，没有关联到具体资源记录"
        result.append(f'<details><summary>{esc(group["title"])}：{group["raw_count"]}条原始记录{resource_note}</summary>')
        result.append(f'<p>用于：{esc(names)}</p><p>{esc(group["note"])}</p><ol>')
        result.extend(f'<li>{esc(item["text"])}</li>' for item in group["items"])
        result.append('</ol></details>')
    if not view["groups"]:
        result.append('<p>当前评估没有列出待核验原因；本展示层不据此判断授权已确认。</p>')
    result.append('</section>')
    return "".join(result)
