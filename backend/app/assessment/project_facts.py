"""从已有扫描中整理项目事实；不授予许可，不修改扫描或核验状态。"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from typing import Any

VIEW_VERSION = "project-facts/1"
GROUP_LABELS = {
    "direct": "直接依赖声明",
    "optional": "可选依赖声明",
    "development": "开发／测试／构建／文档线索",
    "workflow": "工作流引用",
    "unclassified": "尚未分类",
}
_ROOT_LICENSE = re.compile(r"(?:license|licence|copying)(?:\.(?:txt|md|rst))?", re.I)
_SUPPORT_GROUPS = {"dev", "development", "test", "tests", "lint", "typecheck", "typing", "docs", "doc"}


def _data(run: Any) -> dict:
    """同时支持ScanRun和其JSON快照；返回值只读使用。"""
    value = run.model_dump(mode="json") if hasattr(run, "model_dump") else run
    if not isinstance(value, Mapping):
        raise ValueError("project_facts_invalid_run")
    for key in ("components", "ai_assets", "evidence", "licenses"):
        if not isinstance(value.get(key), list):
            raise ValueError("project_facts_missing_" + key)
    if not isinstance(value.get("project"), Mapping):
        raise ValueError("project_facts_missing_project")
    return value


def _path(locator: str) -> str | None:
    """只接受相对路径；不下载、不解析URL、不跟随文件或符号链接。"""
    path = locator.split(":", 1)[0].replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    if not path or path.startswith("/") or "://" in locator or "\x00" in locator:
        return None
    if any(part in {"", ".", ".."} for part in path.split("/")):
        return None
    return path


def _declaration(item: dict) -> tuple[str, str] | None:
    """返回声明角色和依据类型；角色不等于用户最终的交付范围。"""
    locator = item["locator"]
    path = _path(locator)
    if path is None:
        return None
    kind = item["kind"]
    _, separator, field = locator.partition(":")

    if kind == "manifest_field" and path.rsplit("/", 1)[-1] == "pyproject.toml" and separator:
        if re.fullmatch(r"project\.dependencies\[\d+\]", field):
            return "direct", "manifest_field"
        if re.fullmatch(r"project\.optional-dependencies\..+\[\d+\]", field):
            return "optional", "manifest_field"
        if re.fullmatch(r"build-system\.requires\[\d+\]", field):
            return "development", "build_manifest_field"
        match = re.fullmatch(r"dependency-groups\.([^\[\]]+)\[\d+\]", field)
        if match and match.group(1).casefold() in _SUPPORT_GROUPS:
            return "development", "named_dependency_group"
        # 未知分组（例如production）不冒充开发依赖。
        return None

    if kind == "manifest_field":
        name = path.rsplit("/", 1)[-1].casefold()
        parts = path.casefold().split("/")
        if name in {"requirements-dev.txt", "requirements-test.txt", "requirements-tests.txt"}:
            return "development", "filename_hint"
        if name == "requirements.txt" and any(p in {"docs", "doc"} for p in parts[:-1]):
            return "development", "documentation_path_hint"

    if (
        kind == "tool_output"
        and item.get("producer", {}).get("name") == "syft"
        and re.fullmatch(r"\.github/workflows/[^/]+\.ya?ml", path)
    ):
        return "workflow", "scanner_location_observation"
    return None


def project_fact_view(run: Any) -> dict:
    """返回可复用的事实视图；全部来源都保留原资源／许可／证据ID。"""
    data = _data(run)
    evidence = {item["id"]: item for item in data["evidence"]}
    if len(evidence) != len(data["evidence"]):
        raise ValueError("project_facts_duplicate_evidence")
    licenses = {item["id"]: item for item in data["licenses"]}
    if len(licenses) != len(data["licenses"]):
        raise ValueError("project_facts_duplicate_license")

    observations = []
    for license_ in sorted(licenses.values(), key=lambda item: item["id"]):
        for evidence_id in sorted(set(license_["evidence_ids"])):
            if evidence_id not in evidence:
                raise ValueError("project_facts_missing_evidence")
            item = evidence[evidence_id]
            if item["kind"] != "license_text":
                continue
            path = _path(item["locator"])
            observations.append({
                "license_id": license_["id"],
                "evidence_id": evidence_id,
                "locator": item["locator"],
                "expression": license_["expression"],
                "normalized_ids": list(license_["normalized_ids"]),
                "license_verification": license_["verification_status"],
                "evidence_verification": item["verification_status"],
                "root_candidate": bool(path and _ROOT_LICENSE.fullmatch(path)),
            })
    roots = [item for item in observations if item["root_candidate"]]

    records = []
    counts = Counter({key: 0 for key in GROUP_LABELS})
    for resource in sorted(data["components"], key=lambda item: item["id"]):
        declarations = []
        for evidence_id in sorted(set(resource["evidence_ids"])):
            if evidence_id not in evidence:
                raise ValueError("project_facts_missing_evidence")
            item = evidence[evidence_id]
            role = _declaration(item)
            if role is not None:
                declarations.append({
                    "role": role[0], "basis": role[1],
                    "evidence_id": evidence_id, "locator": item["locator"],
                    "verification_status": item["verification_status"],
                })
        roles = sorted({item["role"] for item in declarations})
        # 主分组只为去重计数；所有角色及依据仍在declarations中。
        primary = next((key for key in GROUP_LABELS if key in roles), "unclassified")
        counts[primary] += 1
        license_id = resource.get("license_expression_id")
        if license_id is not None and license_id not in licenses:
            raise ValueError("project_facts_missing_license")
        license_ = licenses.get(license_id)
        records.append({
            "resource_id": resource["id"], "name": resource["name"],
            "version": resource.get("version"), "primary_group": primary,
            "roles": roles, "declarations": declarations,
            "license_expression_id": license_id,
            "license_expression": license_["expression"] if license_ else None,
            "scope_confirmed_by_this_view": False,
        })

    root_expressions = sorted({
        item["expression"] for item in roots
        if item["expression"] not in {"NOASSERTION", "NONE", ""}
    })
    if root_expressions:
        shown = "、".join(root_expressions[:3])
        if len(root_expressions) > 3:
            shown += f"等{len(root_expressions)}种记录（不是合并后的许可表达式）"
        root_text = f"根目录许可文件记录到：{shown}。这属于文件级许可观察，不表示条款原文与适用关系已核验，也不自动适用于依赖。"
    elif roots:
        root_text = "已有根目录许可文件观察，但记录未给出可识别的许可表达式；不据此推断授权。"
    else:
        root_text = "本次结果尚未建立根目录许可文件观察；不等于仓库没有许可证。"
    group_text = "，".join(f"{GROUP_LABELS[key]}{counts[key]}条" for key in GROUP_LABELS if counts[key])
    component_text = (
        f"组件共{len(records)}条：{group_text}。此分类依据声明字段或扫描位置，不代表最终交付范围。"
        if records else "本次未记录组件，不能据此断言没有第三方依赖。"
    )
    ai_count = len(data["ai_assets"])
    ai_text = (
        f"另有{ai_count}条AI资产记录，须独立检查授权条件。"
        if ai_count else "本次未识别到AI资产记录，不等于不存在AI资产。"
    )
    return {
        "view_version": VIEW_VERSION,
        "scan_id": data["id"], "revision": data["project"].get("revision"),
        "scan_status": data["status"],
        "component_count": len(records), "ai_asset_count": ai_count,
        "root_license_observations": roots,
        "file_license_observations": observations,
        "declaration_group_counts": dict(counts),
        "resource_declarations": records,
        "summary": root_text + "\n" + component_text + "\n" + ai_text,
    }
