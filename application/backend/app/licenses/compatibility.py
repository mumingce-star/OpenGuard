"""Deterministic project-level license compatibility matrix engine."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Literal
from urllib.parse import unquote
import re

from app.domain.models import (
    Component,
    ComponentType,
    ScanRun,
    _contains_absolute_path_fragment,
)
from app.licenses.spdx import _ALIASES, parse_license_expression

SCHEMA_VERSION = "openguard-license-compatibility/1"
RULE_VERSION = "license-compatibility-matrix/1"
PROPRIETARY = "PROPRIETARY"
SUPPORTED_SPDX: tuple[str, ...] = tuple(sorted(set(_ALIASES.values())))
SUPPORTED_TARGETS: tuple[str, ...] = (PROPRIETARY, *SUPPORTED_SPDX)

CompatibilityStatus = Literal["COMPATIBLE", "CONDITIONAL", "REVIEW_REQUIRED", "INCOMPATIBLE", "UNKNOWN"]

_STATUS_RANK: dict[str, int] = {
    "COMPATIBLE": 0,
    "CONDITIONAL": 1,
    "UNKNOWN": 2,
    "REVIEW_REQUIRED": 3,
    "INCOMPATIBLE": 4,
}
_PERMISSIVE = frozenset({"MIT", "ISC", "BSD-2-Clause", "BSD-3-Clause", "CC0-1.0", "Unlicense"})
_WEAK_COPYLEFT = frozenset({"MPL-2.0", "EPL-2.0", "CDDL-1.0", "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later"})
_LGPL_21 = frozenset({"LGPL-2.1-only", "LGPL-2.1-or-later"})
_LGPL_30 = frozenset({"LGPL-3.0-only", "LGPL-3.0-or-later"})
_GPL_20 = frozenset({"GPL-2.0-only", "GPL-2.0-or-later"})
_GPL_30 = frozenset({"GPL-3.0-only", "GPL-3.0-or-later"})
_AGPL_30 = frozenset({"AGPL-3.0-only", "AGPL-3.0-or-later"})
_GPL_ALL = _GPL_20 | _GPL_30
_GPL_FAMILY_ALL = _GPL_ALL | _AGPL_30
_RECIPROCAL_FILE = frozenset({"CDDL-1.0", "EPL-2.0"})
_CONTENT_LICENSES = frozenset({"CC-BY-4.0", "CC-BY-NC-4.0"})
_OSI_TARGETS = frozenset(SUPPORTED_SPDX) - _CONTENT_LICENSES
_SENSITIVE = re.compile(r"(?i)(?:(?:api[_-]?key|secret|token|password)\s*[=:]|bearer\s+\S+)")
_MAX_MATRIX_LICENSES = 30
_LIMITATIONS = (
    "仅基于扫描已声明且受收录的 SPDX 标识与当前用途开关做静态矩阵推演。",
    "条件兼容与人工复核结论须结合真实链接方式、修改范围、分发介质与网络交互边界核对。",
    "本引擎输出不构成正式法律签认，不替代人工或专业合规审查。",
)


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


def normalize_target_license(raw: str | None) -> str | None:
    """Validate and canonicalize an explicit outbound target license or PROPRIETARY."""
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    if stripped.upper() == PROPRIETARY:
        return PROPRIETARY
    parsed = parse_license_expression(stripped)
    if not parsed.supported or parsed.operators or len(parsed.normalized_ids) != 1:
        raise ValueError("invalid_target_license")
    return parsed.normalized_ids[0]


def _usage_flags(usage: Mapping[str, bool | None] | None) -> dict[str, bool]:
    source = usage or {}
    return {
        "commercial": bool(source.get("commercial")),
        "distributed": bool(source.get("distributed")),
        "modified": bool(source.get("modified")),
        "network_service": bool(source.get("network_service")),
    }


def _component_license_text(component: Component, licenses: Mapping[str, object]) -> str | None:
    if not component.license_expression_id:
        return None
    expr = licenses.get(component.license_expression_id)
    raw = getattr(expr, "expression", None)
    if not raw or raw in {"NONE", "NOASSERTION"}:
        return None
    return _safe_text(raw)


def resolve_target_license(
    run: ScanRun,
    *,
    target_license: str | None = None,
    root_license_checks: Iterable[Mapping[str, object]] = (),
) -> dict:
    """Resolve outbound target license: explicit > unique clean root > UNKNOWN."""
    normalized_explicit = normalize_target_license(target_license)
    if normalized_explicit is not None:
        return {
            "license": normalized_explicit,
            "source": "explicit",
            "status": "RESOLVED",
            "root_component_id": None,
            "gaps": [],
        }

    checks = list(root_license_checks)
    if any(bool(item.get("spdx_text_conflict")) for item in checks):
        return {
            "license": None,
            "source": "root_conflict",
            "status": "UNKNOWN",
            "root_component_id": None,
            "gaps": ["root_spdx_text_conflict"],
        }

    licenses = {item.id: item for item in run.licenses}
    roots = sorted(
        (item for item in run.components if item.component_type is ComponentType.APPLICATION),
        key=lambda item: (item.ecosystem, item.name, item.id),
    )
    if len(roots) == 1:
        root = roots[0]
        raw_expr = _component_license_text(root, licenses)
        if raw_expr:
            parsed = parse_license_expression(raw_expr)
            if parsed.supported and not parsed.operators and len(parsed.normalized_ids) == 1:
                return {
                    "license": parsed.normalized_ids[0],
                    "source": "root_package",
                    "status": "RESOLVED",
                    "root_component_id": root.id,
                    "gaps": [],
                }
            return {
                "license": None,
                "source": "undeclared",
                "status": "UNKNOWN",
                "root_component_id": root.id,
                "gaps": ["target_license_complex_or_unsupported"],
            }
        return {
            "license": None,
            "source": "undeclared",
            "status": "UNKNOWN",
            "root_component_id": root.id,
            "gaps": ["target_license_undeclared"],
        }

    if len(roots) > 1:
        return {
            "license": None,
            "source": "ambiguous_roots",
            "status": "UNKNOWN",
            "root_component_id": None,
            "gaps": ["multiple_root_licenses"],
        }

    return {
        "license": None,
        "source": "undeclared",
        "status": "UNKNOWN",
        "root_component_id": None,
        "gaps": ["target_license_undeclared"],
    }


def _verdict(
    status: CompatibilityStatus,
    rule_id: str,
    rationale: str,
    *,
    obligations: tuple[str, ...] = (),
    chosen_branch: str | None = None,
) -> dict:
    return {
        "status": status,
        "rule_id": rule_id,
        "rationale": rationale,
        "obligations": list(obligations),
        "chosen_branch": chosen_branch,
    }


def _dist_or_review(distributed: bool, *, network: bool = False) -> CompatibilityStatus:
    return "INCOMPATIBLE" if (distributed or network) else "REVIEW_REQUIRED"


def evaluate_target_pair(target: str, dep: str, usage: Mapping[str, bool | None] | None) -> dict:
    """Evaluate compatibility when incorporating atomic SPDX `dep` into outbound `target`."""
    flags = _usage_flags(usage)
    commercial = flags["commercial"]
    distributed = flags["distributed"]
    network_service = flags["network_service"]

    if dep == "CC-BY-NC-4.0":
        if commercial:
            return _verdict(
                "INCOMPATIBLE",
                "COMPAT-CC-BY-NC-COMMERCIAL",
                "CC-BY-NC-4.0 禁止商业用途，与当前声明的商业使用冲突。",
                obligations=("移除或替换为允许商业使用的组件",),
            )
        if distributed and target not in {PROPRIETARY, "CC-BY-NC-4.0", "CC-BY-4.0"}:
            return _verdict(
                "INCOMPATIBLE",
                "COMPAT-CC-BY-NC-OSI-OUTBOUND",
                f"CC-BY-NC-4.0 的非商业限制与开源目标许可证 {target} 对外再分发权限冲突。",
                obligations=("移除非商业限制素材或避免将其并入开源再分发包",),
            )
        return _verdict(
            "REVIEW_REQUIRED",
            "COMPAT-CC-BY-NC-SCOPE",
            "包含 CC-BY-NC-4.0 组件，须人工确认使用与后续分发不突破非商业限制并履行署名义务。",
            obligations=("保留创作者署名与许可链接", "复核非商业使用范围"),
        )

    if dep == "CC-BY-4.0":
        if target in _GPL_20 and distributed:
            return _verdict(
                "INCOMPATIBLE",
                "COMPAT-CC-BY-4-GPL2",
                f"CC-BY-4.0 与目标许可证 {target} 在对外分发组合中存在单向兼容与额外限制冲突。",
                obligations=("核查内容与代码的分离分发边界或替换素材许可",),
            )
        return _verdict(
            "REVIEW_REQUIRED",
            "COMPAT-CC-BY-4-ATTRIBUTION",
            "CC-BY-4.0 主要面向文档与媒体资产，须人工确认署名、变更说明与目标发行边界。",
            obligations=("保留原作者署名、许可链接及变更说明",),
        )

    if dep in _PERMISSIVE:
        return _verdict(
            "COMPATIBLE",
            "COMPAT-PERMISSIVE-INBOUND",
            f"宽松许可证 {dep} 可被目标许可证 {target} 引入组合。",
            obligations=(f"保留 {dep} 版权声明、许可全文与免责声明",),
        )

    if dep == "Apache-2.0":
        if target == "GPL-2.0-only":
            status = _dist_or_review(distributed)
            return _verdict(
                status,
                "COMPAT-APACHE2-GPL2-ONLY",
                ("Apache-2.0 的专利与赔偿条款与仅限 GPL-2.0-only 对外分发不兼容。"
                 if distributed else "Apache-2.0 与 GPL-2.0-only 存在公认冲突；当前未声明对外分发，若后续分发将升级为不兼容。"),
                obligations=("避免将 GPL-2.0-only 目标与 Apache-2.0 组件一并分发，或升级至 GPL-3.0+",),
            )
        if target in ({"GPL-2.0-or-later"} | _GPL_30 | _AGPL_30):
            return _verdict(
                "CONDITIONAL",
                "COMPAT-APACHE2-INTO-GPL3-FAMILY",
                f"Apache-2.0 可单向并入 {target}（GPL-2.0-or-later 须以 GPL-3.0+ 条款对外分发），并保留 NOTICE。",
                obligations=("以 GPLv3/AGPLv3 家族条款统一履行对应源码与专利授权要求", "保留 Apache-2.0 §4 版权与 NOTICE 归属声明"),
            )
        return _verdict(
            "COMPATIBLE",
            "COMPAT-APACHE2-INBOUND",
            f"Apache-2.0 与目标许可证 {target} 兼容，须随附 NOTICE 与变更说明。",
            obligations=("随附 Apache-2.0 全文与 APPLICABLE NOTICE 内容", "按 §4(b) 标注修改文件"),
        )

    if dep in _RECIPROCAL_FILE:
        if target in _GPL_FAMILY_ALL:
            status = _dist_or_review(distributed, network=(network_service and target in _AGPL_30))
            return _verdict(
                status,
                "COMPAT-RECIPROCAL-VS-GPL",
                (f"{dep} 的文件级互惠与选择法律/专利条款与 {target} 传染要求冲突。"
                 if status == "INCOMPATIBLE"
                 else f"{dep} 与 {target} 存在文件级互惠冲突；当前未声明外部发布，若分发或提供网络交互将升级为不兼容。"),
                obligations=("隔离进程/模块边界或替换为兼容许可依赖",),
            )
        return _verdict(
            "REVIEW_REQUIRED",
            "COMPAT-RECIPROCAL-BOUNDARY",
            f"{dep} 要求修改文件按原许可回馈源码与声明，须人工核对文件/模块组合边界。",
            obligations=(f"保留 {dep} 原始声明并对受覆盖修改提供源码",),
        )

    if dep == "MPL-2.0":
        if target == "GPL-2.0-only":
            return _verdict(
                "REVIEW_REQUIRED",
                "COMPAT-MPL2-GPL2-ONLY",
                "MPL-2.0 与 GPL-2.0-only 之间的次级许可兼容性取决于源码是否标注 Incompatible With Secondary Licenses，须人工复核。",
                obligations=("核查 MPL-2.0 文件头及与 GPL-2.0-only 的边界",),
            )
        if target in ({"GPL-2.0-or-later"} | _GPL_30 | _AGPL_30):
            return _verdict(
                "CONDITIONAL",
                "COMPAT-MPL2-SECONDARY",
                f"依据 MPL-2.0 §3.3，未声明排除次级许可的文件可按次级许可并入 {target}，且须保留 MPL 文件级源码可获性。",
                obligations=("确认上游未标注 Incompatible With Secondary Licenses", f"同步履行 MPL-2.0 与 {target} 源码披露义务"),
            )
        return _verdict(
            "REVIEW_REQUIRED",
            "COMPAT-MPL2-FILE-COPYLEFT",
            f"MPL-2.0 为弱 Copyleft 文件级互惠许可，并入 {target} 须人工核查修改文件披露与大型作品声明。",
            obligations=("告知收受方 MPL-2.0 受覆盖文件源码获取方式",),
        )

    if dep in (_LGPL_21 | _LGPL_30):
        if dep in _LGPL_30 and target == "GPL-2.0-only":
            status = _dist_or_review(distributed)
            return _verdict(
                status,
                "COMPAT-LGPL3-GPL2-ONLY",
                ("LGPL-3.0 不可降级并入仅限 GPL-2.0-only 的对外分发作品。"
                 if distributed else "LGPL-3.0 与 GPL-2.0-only 不兼容；当前未声明对外分发，若后续分发将升级为不兼容。"),
                obligations=("保持动态库独立边界或统一升级目标至 GPL-3.0+",),
            )
        if (dep in _LGPL_21 and target in _GPL_FAMILY_ALL) or (dep in _LGPL_30 and target in (_GPL_30 | _AGPL_30 | {"GPL-2.0-or-later"})):
            return _verdict(
                "CONDITIONAL",
                "COMPAT-LGPL-TO-GPL-CONVERSION",
                f"{dep} 可依转换条款并入 {target}（GPL-2.0-or-later 目标遇 LGPL-3.0 时须按 GPL-3.0+ 分发）。",
                obligations=(f"按 {target} 与 {dep} 条款保留声明并履行源码要求",),
            )
        return _verdict(
            "REVIEW_REQUIRED",
            "COMPAT-LGPL-LINKING",
            f"{dep} 引入 {target} 项目须人工核对动态链接、允许用户重链接及安装信息（如适用）等弱 Copyleft 义务。",
            obligations=("保留动态/可替换重链接边界与相应 LGPL 源码要约",),
        )

    if dep in _GPL_ALL:
        if target == dep:
            return _verdict(
                "COMPATIBLE",
                "COMPAT-GPL-EXACT-MATCH",
                f"依赖与目标同为 {target}，版本与传染家族一致。",
                obligations=(f"遵守 {target} 的对应源码、声明与版权保留要求",),
            )
        upgrade_ok = (
            (dep == "GPL-2.0-or-later" and target in ({"GPL-2.0-only"} | _GPL_30 | _AGPL_30))
            or (dep in _GPL_30 and target in (_GPL_30 | _AGPL_30))
        )
        if upgrade_ok:
            return _verdict(
                "CONDITIONAL",
                "COMPAT-GPL-VERSION-CONVERSION",
                f"{dep} 可在组合作品中按 {target} 条款授权对外分发。",
                obligations=(f"组合作品整体按 {target} 履行源码与声明义务",),
            )
        if target in _GPL_FAMILY_ALL:
            status = _dist_or_review(distributed, network=(network_service and target in _AGPL_30))
            return _verdict(
                status,
                "COMPAT-GPL-VERSION-CONFLICT",
                (f"{dep} 与目标许可证 {target} 的 GPL 版本条款互斥，对外分发无法同时满足双方许可。"
                 if status == "INCOMPATIBLE"
                 else f"{dep} 与目标许可证 {target} 存在 GPL 版本互斥；当前未声明外部发布，若分发将升级为不兼容。"),
                obligations=("对齐相同兼容的 GPL 主版本或更换依赖",),
            )
        status = _dist_or_review(distributed)
        return _verdict(
            status,
            "COMPAT-STRONG-COPYLEFT-PROPAGATION",
            (f"强传染许可证 {dep} 要求衍生/组合作品整体按相同 Copyleft 条款开源，与目标 {target} 对外分发冲突。"
             if distributed
             else f"引入强传染许可证 {dep}；当前未声明对外分发，但一旦分发将要求整包受 Copyleft 约束。"),
            obligations=("替换强 Copyleft 依赖，或调整项目目标许可证并公开对应源码",),
        )

    if dep in _AGPL_30:
        if target == dep:
            return _verdict(
                "COMPATIBLE",
                "COMPAT-AGPL-EXACT-MATCH",
                f"依赖与目标同为 {target}。",
                obligations=(f"遵守 {target} §13 网络交互源码提供与声明义务",),
            )
        if target in _AGPL_30:
            return _verdict(
                "CONDITIONAL",
                "COMPAT-AGPL-VERSION-CONVERSION",
                f"{dep} 可并入 {target} 组合。",
                obligations=(f"组合作品整体遵守 {target} §13 网络交互源码提供义务",),
            )
        status = _dist_or_review(distributed, network=network_service)
        return _verdict(
            status,
            "COMPAT-AGPL-NETWORK-COPYLEFT",
            (f"{dep} 要求向网络交互用户提供完整对应源码，与目标 {target} 在当前分发/网络服务声明下冲突。"
             if status == "INCOMPATIBLE"
             else f"包含网络传染许可证 {dep}；一旦对外分发或作为网络服务提供，将触发整包开源传染。"),
            obligations=("避免引入 AGPL-3.0 依赖，或改用 AGPL-3.0 发布项目并履行 §13 源码提供",),
        )

    return _verdict("UNKNOWN", "COMPAT-UNSUPPORTED-LICENSE", f"未收录或不支持推演的许可证 {dep}，保守降级为未知。")


def evaluate_target_expression(target: str | None, dep_expression: str | None, usage: Mapping[str, bool | None] | None) -> dict:
    """Evaluate a dependency's raw/normalized expression against outbound target license."""
    if target is None:
        return _verdict(
            "UNKNOWN",
            "COMPAT-TARGET-UNRESOLVED",
            "项目目标许可证尚未确立，无法判定目标与依赖的出向兼容性；下表仍会检查依赖间两两冲突。",
        )
    if not dep_expression or dep_expression in {"NONE", "NOASSERTION"}:
        return _verdict("UNKNOWN", "COMPAT-DEPENDENCY-UNDECLARED", "该依赖未声明有效许可证，保守保持 UNKNOWN。")

    parsed = parse_license_expression(dep_expression)
    if not parsed.supported:
        return _verdict("UNKNOWN", "COMPAT-UNSUPPORTED-EXPRESSION", "依赖许可证不在已收录 SPDX 规则集内，保守保持 UNKNOWN。")

    op_set = set(parsed.operators)
    if not op_set:
        return evaluate_target_pair(target, parsed.normalized_ids[0], usage)

    if len(op_set) > 1:
        return _verdict(
            "UNKNOWN",
            "COMPAT-COMPLEX-EXPRESSION",
            "无括号混用 AND/OR 的复合表达式优先级不明确，保守保持 UNKNOWN。",
        )

    terms = [evaluate_target_pair(target, term, usage) for term in parsed.normalized_ids]
    if op_set == {"OR"}:
        best_idx = min(range(len(terms)), key=lambda idx: _STATUS_RANK[terms[idx]["status"]])
        best = terms[best_idx]
        branch = parsed.normalized_ids[best_idx]
        all_compatible = all(item["status"] == "COMPATIBLE" for item in terms)
        if best["status"] == "COMPATIBLE" and not all_compatible:
            return _verdict(
                "CONDITIONAL",
                "COMPAT-OR-BRANCH-SELECTED",
                f"双许可表达式中存在与 {target} 兼容的分支 {branch}，须在项目集成与交付中明确择一适用。",
                obligations=(f"明确选定 {branch} 分支并履行对应声明义务", *best["obligations"]),
                chosen_branch=branch,
            )
        return _verdict(
            best["status"],
            best["rule_id"],
            f"双许可表达式优先按最优分支 {branch} 判定：{best['rationale']}",
            obligations=tuple(best["obligations"]),
            chosen_branch=branch,
        )

    # Pure AND: every conjunct must be satisfied simultaneously -> worst rank wins.
    worst_idx = max(range(len(terms)), key=lambda idx: _STATUS_RANK[terms[idx]["status"]])
    worst = terms[worst_idx]
    obligations = tuple(dict.fromkeys(item for term in terms for item in term["obligations"]))
    return _verdict(
        worst["status"],
        worst["rule_id"],
        f"合取许可证（AND）须同时满足全部子项，最严格结论来自 {parsed.normalized_ids[worst_idx]}：{worst['rationale']}",
        obligations=obligations,
    )


def _pair_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def evaluate_pairwise_atomic(lic_a: str, lic_b: str, usage: Mapping[str, bool | None] | None) -> dict:
    """Symmetric pairwise compatibility evaluation for two atomic supported SPDX IDs."""
    flags = _usage_flags(usage)
    commercial = flags["commercial"]
    distributed = flags["distributed"]
    network_service = flags["network_service"]
    first, second = _pair_key(lic_a, lic_b)
    pair = {first, second}

    if first == second:
        return _verdict("COMPATIBLE", "PAIR-SAME-LICENSE", f"双方均采用 {first}，许可条款一致。")

    if "CC-BY-NC-4.0" in pair and bool(pair - {"CC-BY-NC-4.0", "CC-BY-4.0"}):
        other = second if first == "CC-BY-NC-4.0" else first
        if other in _OSI_TARGETS:
            status: CompatibilityStatus = "INCOMPATIBLE" if (commercial or distributed) else "REVIEW_REQUIRED"
            return _verdict(
                status,
                "PAIR-OSI-NONCOMMERCIAL",
                ("CC-BY-NC-4.0 的非商业限制与 OSI 开源许可 " + other + " 允许商业使用的授权冲突。"
                 if status == "INCOMPATIBLE"
                 else "CC-BY-NC-4.0 与 OSI 开源组件共存须人工核实非商业使用且未对外分发。"),
            )

    if pair & _CONTENT_LICENSES:
        if pair & _GPL_20 and "CC-BY-4.0" in pair:
            status = _dist_or_review(distributed)
            return _verdict(
                status,
                "PAIR-GPL2-CCBY4",
                ("CC-BY-4.0 与 GPL-2.0 族在组合分发中存在单向兼容性冲突。"
                 if distributed else "CC-BY-4.0 与 GPL-2.0 共存；若后续对外分发代码与素材组合将升级为不兼容。"),
            )
        return _verdict("REVIEW_REQUIRED", "PAIR-CONTENT-BOUNDARY", f"{first} 与 {second} 含内容许可，须核对素材与代码分离边界。")

    if pair == {"Apache-2.0", "GPL-2.0-only"}:
        status = _dist_or_review(distributed)
        return _verdict(
            status,
            "PAIR-GPL2-ONLY-APACHE2",
            ("GPL-2.0-only 与 Apache-2.0 在对外分发作品中公认互斥（专利终止与额外条款冲突）。"
             if distributed else "GPL-2.0-only 与 Apache-2.0 存在互斥风险；当前未声明分发，若后续对外分发将升级为不兼容。"),
        )

    if "GPL-2.0-only" in pair and bool(pair & (_GPL_30 | _AGPL_30 | _LGPL_30)):
        has_agpl = bool(pair & _AGPL_30)
        status = _dist_or_review(distributed, network=(network_service and has_agpl))
        return _verdict(
            status,
            "PAIR-GPL2-ONLY-GPL3-FAMILY",
            ("仅限 GPL-2.0-only 与 GPLv3/AGPLv3/LGPLv3 家族版本条款互斥，不能在分发作品中合法合并。"
             if status == "INCOMPATIBLE"
             else "GPL-2.0-only 与 v3 家族共存存在版本互斥风险；若对外分发或提供网络交互将升级为不兼容。"),
        )

    if bool(pair & _GPL_FAMILY_ALL) and bool(pair & _RECIPROCAL_FILE):
        has_agpl = bool(pair & _AGPL_30)
        status = _dist_or_review(distributed, network=(network_service and has_agpl))
        return _verdict(
            status,
            "PAIR-GPL-RECIPROCAL",
            (f"{first} 与 {second} 属于公认的 GPL 与文件级互惠许可互斥组合。"
             if status == "INCOMPATIBLE"
             else f"{first} 与 {second} 存在强/弱互惠冲突；若对外分发或提供网络交互将升级为不兼容。"),
        )

    if "GPL-2.0-only" in pair and "MPL-2.0" in pair:
        return _verdict(
            "REVIEW_REQUIRED",
            "PAIR-MPL2-GPL2-ONLY",
            "MPL-2.0 与 GPL-2.0-only 共存须确认是否仅作为独立模块或触发次级许可限制。",
        )

    if "Apache-2.0" in pair and ("GPL-2.0-or-later" in pair or bool(pair & (_GPL_30 | _AGPL_30))):
        return _verdict(
            "CONDITIONAL",
            "PAIR-APACHE2-GPL3-COMBINATION",
            "Apache-2.0 与 GPL-2.0-or-later / GPLv3 家族合并时，组合作品须整体按 GPLv3/AGPLv3 履行并保留 NOTICE。",
        )

    if "MPL-2.0" in pair and ("GPL-2.0-or-later" in pair or bool(pair & (_GPL_30 | _AGPL_30))):
        return _verdict(
            "CONDITIONAL",
            "PAIR-MPL2-SECONDARY",
            "MPL-2.0 可依据 §3.3 次级许可条款与 GPL-2.0-or-later / GPLv3 家族组合，须保留原文件可获性。",
        )

    if bool(pair & _GPL_30) and bool(pair & _AGPL_30):
        return _verdict(
            "CONDITIONAL",
            "PAIR-GPL3-AGPL3-CONVERSION",
            "GPL-3.0 与 AGPL-3.0 可依 AGPL-3.0 §13 合并，合并后交互服务整体适用 AGPL-3.0 源码条款。",
        )

    if pair.issubset(_PERMISSIVE | {"Apache-2.0"}):
        return _verdict("COMPATIBLE", "PAIR-PERMISSIVE", f"{first} 与 {second} 均为宽松许可，可自由组合并保留声明。")

    if pair <= (_PERMISSIVE | {"Apache-2.0"} | _GPL_FAMILY_ALL):
        # Compatible GPL/AGPL upgrades or GPL + permissive downstream
        return _verdict(
            "CONDITIONAL",
            "PAIR-GPL-DOMINANT",
            f"{first} 与 {second} 共存时，组合分发整体受更严格的 Copyleft 一方条款约束。",
        )

    if pair & (_WEAK_COPYLEFT | _AGPL_30):
        return _verdict(
            "REVIEW_REQUIRED",
            "PAIR-COPYLEFT-BOUNDARY",
            f"{first} 与 {second} 涉及弱 Copyleft 或网络互惠条款，须人工确认链接与交付边界。",
        )

    return _verdict("COMPATIBLE", "PAIR-COMPATIBLE", f"{first} 与 {second} 未命中冲突规则。")


def evaluate_pairwise_expressions(
    expr_a: str,
    expr_b: str,
    usage: Mapping[str, bool | None] | None,
) -> dict:
    """Evaluate compatibility between two normalized/raw dependency license expressions."""
    parsed_a = parse_license_expression(expr_a)
    parsed_b = parse_license_expression(expr_b)
    if not parsed_a.supported or not parsed_b.supported:
        return _verdict("UNKNOWN", "PAIR-UNSUPPORTED-EXPRESSION", "存在未收录 SPDX 标识，无法判定依赖间兼容性。")
    ops_a = set(parsed_a.operators)
    ops_b = set(parsed_b.operators)
    if len(ops_a) > 1 or len(ops_b) > 1:
        return _verdict("UNKNOWN", "PAIR-COMPLEX-EXPRESSION", "存在未括起的混合 AND/OR 表达式，保守保持 UNKNOWN。")

    def combine(verdicts: list[dict], op: str | None) -> dict:
        if op == "OR":
            idx = min(range(len(verdicts)), key=lambda i: _STATUS_RANK[verdicts[i]["status"]])
            return verdicts[idx]
        if op == "AND":
            idx = max(range(len(verdicts)), key=lambda i: _STATUS_RANK[verdicts[i]["status"]])
            return verdicts[idx]
        return verdicts[0]

    op_a = next(iter(ops_a), None)
    op_b = next(iter(ops_b), None)
    outer_verdicts = []
    for term_a in parsed_a.normalized_ids:
        inner = [evaluate_pairwise_atomic(term_a, term_b, usage) for term_b in parsed_b.normalized_ids]
        outer_verdicts.append(combine(inner, op_b))
    chosen = combine(outer_verdicts, op_a)
    if (op_a == "OR" or op_b == "OR") and chosen["status"] == "COMPATIBLE":
        # Both expressions had at least one compatible OR branch; keep COMPATIBLE if strictly clean,
        # or CONDITIONAL when one branch conflicted.
        all_statuses = {
            evaluate_pairwise_atomic(term_a, term_b, usage)["status"]
            for term_a in parsed_a.normalized_ids
            for term_b in parsed_b.normalized_ids
        }
        if len(all_statuses) > 1:
            return _verdict(
                "CONDITIONAL",
                "PAIR-OR-BRANCH-SELECTION",
                f"双方含双许可选项，可选择兼容分支完成组合：{chosen['rationale']}",
            )
    return chosen


def _component_ref(component: Component) -> dict:
    return {
        "resource_id": component.id,
        "name": _safe_text(component.name, "[redacted]"),
        "version": _safe_text(component.version),
        "ecosystem": component.ecosystem,
        "evidence_ids": list(component.evidence_ids),
    }


def evaluate_scan_compatibility(
    run: ScanRun,
    *,
    usage: Mapping[str, bool | None] | None = None,
    target_license: str | None = None,
    root_license_checks: Iterable[Mapping[str, object]] = (),
) -> dict:
    """Evaluate target<-dependency and dependency<->dependency compatibility over a ScanRun."""
    flags = _usage_flags(usage)
    target = resolve_target_license(run, target_license=target_license, root_license_checks=root_license_checks)
    resolved_target = target["license"]

    licenses = {item.id: item for item in run.licenses}
    dependencies = sorted(
        (item for item in run.components if item.component_type is not ComponentType.APPLICATION),
        key=lambda item: (item.ecosystem, item.name, item.version or "", item.id),
    )

    target_assessments: list[dict] = []
    target_counts = dict.fromkeys(_STATUS_RANK, 0)
    by_canonical_expr: dict[str, list[dict]] = defaultdict(list)

    for component in dependencies:
        raw_expr = _component_license_text(component, licenses)
        canonical_expr: str | None = None
        if raw_expr:
            parsed = parse_license_expression(raw_expr)
            canonical_expr = parsed.expression if parsed.supported else raw_expr
            if parsed.supported and len(set(parsed.operators)) <= 1:
                by_canonical_expr[canonical_expr].append(_component_ref(component))
        verdict = evaluate_target_expression(resolved_target, canonical_expr, flags)
        target_counts[verdict["status"]] += 1
        target_assessments.append({
            **_component_ref(component),
            "declared_license": canonical_expr,
            **verdict,
        })

    target_assessments.sort(key=lambda item: (-_STATUS_RANK[item["status"]], item["ecosystem"], item["name"], item["resource_id"]))

    unique_exprs = sorted(by_canonical_expr)
    pairwise_conflicts: list[dict] = []
    pairwise_counts = dict.fromkeys(_STATUS_RANK, 0)
    pair_cache: dict[tuple[str, str], dict] = {}

    for i, expr_a in enumerate(unique_exprs):
        for expr_b in unique_exprs[i + 1:]:
            verdict = evaluate_pairwise_expressions(expr_a, expr_b, flags)
            pair_cache[(expr_a, expr_b)] = verdict
            pairwise_counts[verdict["status"]] += 1
            if verdict["status"] in {"INCOMPATIBLE", "REVIEW_REQUIRED", "CONDITIONAL"}:
                pairwise_conflicts.append({
                    "license_a": expr_a,
                    "license_b": expr_b,
                    "status": verdict["status"],
                    "rule_id": verdict["rule_id"],
                    "rationale": verdict["rationale"],
                    "components_a": by_canonical_expr[expr_a],
                    "components_b": by_canonical_expr[expr_b],
                })

    pairwise_conflicts.sort(key=lambda item: (-_STATUS_RANK[item["status"]], item["license_a"], item["license_b"]))

    matrix_licenses = unique_exprs[:_MAX_MATRIX_LICENSES]
    matrix_cells: list[dict] = []
    for r, row_lic in enumerate(matrix_licenses):
        for c, col_lic in enumerate(matrix_licenses):
            if r == c:
                cell = _verdict("COMPATIBLE", "PAIR-SAME-LICENSE", "")
            else:
                a, b = (row_lic, col_lic) if row_lic <= col_lic else (col_lic, row_lic)
                cell = pair_cache[(a, b)]
            matrix_cells.append({
                "row": r,
                "col": c,
                "status": cell["status"],
                "rule_id": cell["rule_id"],
            })

    combined_statuses = [item["status"] for item in target_assessments] + [item["status"] for item in pairwise_conflicts]
    if not dependencies and resolved_target is not None:
        overall_status: CompatibilityStatus = "COMPATIBLE"
    elif resolved_target is None and not any(item["status"] in {"INCOMPATIBLE", "REVIEW_REQUIRED"} for item in pairwise_conflicts):
        overall_status = "UNKNOWN"
    elif combined_statuses:
        overall_status = max(combined_statuses, key=lambda s: _STATUS_RANK[s])
    else:
        overall_status = "UNKNOWN"

    incompatible_count = target_counts["INCOMPATIBLE"] + pairwise_counts["INCOMPATIBLE"]
    review_required_count = target_counts["REVIEW_REQUIRED"] + pairwise_counts["REVIEW_REQUIRED"]
    conditional_count = target_counts["CONDITIONAL"] + pairwise_counts["CONDITIONAL"]
    unknown_count = target_counts["UNKNOWN"] + pairwise_counts["UNKNOWN"]
    compatible_count = target_counts["COMPATIBLE"] + pairwise_counts["COMPATIBLE"]

    return {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "supported_targets": list(SUPPORTED_TARGETS),
        "target": target,
        "usage": flags,
        "summary": {
            "overall_status": overall_status,
            "dependency_count": len(dependencies),
            "unique_license_count": len(unique_exprs),
            "target_counts": target_counts,
            "pairwise_counts": pairwise_counts,
            "compatible_count": compatible_count,
            "conditional_count": conditional_count,
            "review_required_count": review_required_count,
            "incompatible_count": incompatible_count,
            "unknown_count": unknown_count,
        },
        "target_assessments": target_assessments,
        "pairwise_conflicts": pairwise_conflicts,
        "matrix": {
            "licenses": matrix_licenses,
            "truncated": len(unique_exprs) > _MAX_MATRIX_LICENSES,
            "cells": matrix_cells,
        },
        "formal_effect": "none",
        "model_calls": 0,
        "limitations": list(_LIMITATIONS),
    }
