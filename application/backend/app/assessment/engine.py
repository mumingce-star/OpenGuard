"""Conservative, offline project assessment. No scanner facts are edited.

Only exact MIT grants are currently promoted, with verified license evidence,
exact resource/version and an explicitly human-verified scope attestation.
GPL-3.0-only conveyance conflicts are conditional on an explicit source refusal.
No scope is inferred from package category, paths, root LICENSE or UI presets.
"""
from __future__ import annotations
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from app.domain.models import ScanRun, VerificationStatus, EvidenceKind, ProducerType
from app.domain.usage import UsageDeclaration
from app.rules.engine import load_ruleset
from .models import Assessment, AssessmentObligation, DimensionAssessment, ResourceEvaluation, DIMENSIONS, LABELS
from .project_facts import project_fact_view

RULE_VERSION = "assessment-1.0-facts2"
RULE_SOURCES = ["https://opensource.org/license/mit", "https://opensource.org/license/gpl-3.0"]
_SCOPE_VALUES = {"project_code", "runtime_dependency", "development_dependency", "example", "model", "dataset", "api", "other"}


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def facts_digest(run: ScanRun) -> str:
    return digest(run.model_dump(mode="json"))


def _scope(resource, evidence) -> tuple[str, list[str]]:
    matches = []
    for eid in resource.evidence_ids:
        item = evidence[eid]
        if item.kind != EvidenceKind.METADATA or item.producer.type != ProducerType.HUMAN or item.verification_status != VerificationStatus.VERIFIED:
            continue
        try:
            data = json.loads(item.excerpt or "")
        except (ValueError, TypeError):
            continue
        if (isinstance(data, dict) and set(data) == {"kind", "resource_id", "version", "scope", "license_expression_id"}
            and data["kind"] == "openguard.scope.v1" and data["resource_id"] == resource.id
            and data["license_expression_id"] == resource.license_expression_id and resource.license_expression_id is not None
            and resource.version and data["version"] == resource.version and isinstance(data["scope"], str) and data["scope"] in _SCOPE_VALUES):
            matches.append((data["scope"], eid))
    if not matches or len({item[0] for item in matches}) != 1:
        return "unknown", []
    return matches[0][0], sorted(item[1] for item in matches)


def build_assessment(run: ScanRun, usage: UsageDeclaration | None = None, *, version: int = 1,
                     generated_at: datetime | None = None, model_version: str = "none",
                     prompt_version: str = "assessment-1.0") -> Assessment:
    """Pure relative to supplied run/time. Caller explicitly persists the result."""
    usage = usage or UsageDeclaration()
    facts_hash = facts_digest(run)
    usage_hash = digest(usage.model_dump(mode="json", exclude={"declared_at"}))
    ruleset = load_ruleset()
    rule_version = f"{RULE_VERSION}:{ruleset.version}:{ruleset.source_digest}"
    key = digest([run.id, facts_hash, usage_hash, rule_version, model_version, prompt_version])
    evidence = {e.id: e for e in run.evidence}
    licenses = {item.id: item for item in run.licenses}
    findings = {item.id: item for item in run.findings}
    resources = sorted([*run.components, *run.ai_assets], key=lambda x: x.id)
    rows = []
    for resource in resources:
        license_ = licenses.get(resource.license_expression_id)
        scope, scope_ids = _scope(resource, evidence)
        resource_findings = [f for f in run.findings if f.resource_id == resource.id]
        eids = set(resource.evidence_ids)
        if license_:
            eids.update(license_.evidence_ids)
        for f in resource_findings:
            eids.update(f.evidence_ids)
        verified = bool(license_ and license_.verification_status == VerificationStatus.VERIFIED
                        and all(evidence[e].verification_status == VerificationStatus.VERIFIED for e in license_.evidence_ids)
                        and any(evidence[e].kind == EvidenceKind.LICENSE_TEXT for e in license_.evidence_ids))
        exact_version = bool(resource.version and not re.search(r"[<>=*~^,|\s]", resource.version)
                             and resource.version.lower() not in {"unknown", "latest", "main", "master"})
        gaps = []
        if not exact_version:
            gaps.append("版本未固定，版本范围或分支名不能证明实际使用版本")
        if scope == "unknown":
            gaps.append("项目自身／依赖／开发示例的适用范围尚无已核验证据")
        if not verified:
            gaps.append("许可原文及其与本对象版本的适用关系尚未核验")
        kind = "component" if resource.id.startswith("cmp_") else "ai_asset"
        supported = bool(verified and exact_version and scope != "unknown" and kind == "component"
                         and license_.expression == "MIT" and license_.normalized_ids == ["MIT"])
        if verified and not supported:
            gaps.append("当前有限决策表未覆盖该许可表达式、对象类型或范围，不推断其它授权")
        restrictions = {}
        if (verified and exact_version and scope in {"project_code", "runtime_dependency"}
            and license_.expression == "GPL-3.0-only" and license_.normalized_ids == ["GPL-3.0-only"]
            and usage.distributed is True and usage.source_disclosure is False):
            restrictions["closed_distribution"] = ["计划交付该 GPL-3.0-only 对象但明确不提供对应源码，存在交付条件限制；适用对象是否构成同一作品仍需复核，独立聚合不自动扩展到其它对象"]
        label = f"{resource.name}（{resource.version or '版本未确定'}）"
        locators = sorted({evidence[e].locator for e in eids})
        steps = []
        if not exact_version:
            steps.append(f"对照 {locators[0] if locators else '原始声明'} 为 {label} 确定安装锁定版本或发布摘要")
        if scope == "unknown":
            steps.append(f"核对 {label} 的引入位置 {locators[0] if locators else '原始声明'}，记录属于项目自身、运行交付还是开发／示例的范围依据")
        if not verified:
            steps.append(f"从 {resource.source_url or '该对象官方发布页／安装包'} 查找 {label} 对应版本的 LICENSE／NOTICE，保存原文及版本绑定依据供人工核验")
        if verified and not supported:
            steps.append(f"对 {label} 的 {license_.expression} 按完整表达式及独立条款复核，不能只按许可名称判断")
        rows.append(ResourceEvaluation(resource_id=resource.id, resource_kind=kind, name=resource.name, version=resource.version,
            scope=scope, scope_evidence_ids=scope_ids, license_expression=license_.expression if license_ else None,
            license_verified=verified, supported_permission=supported, finding_ids=[f.id for f in resource_findings],
            evidence_ids=sorted(eids), locators=locators, conditions=["保留版权声明及许可声明；义务是否实际履行仍待核实"] if supported else [],
            restrictions=restrictions, gaps=gaps, next_steps=steps))
    coverage = [f"{e.stage.value} / {e.code}: {e.message}" for e in run.errors]
    if run.status.value != "completed":
        coverage.insert(0, f"扫描真实状态为 {run.status.value}，没有足够范围信息排除其对整体结论的影响")
    if not any(row.scope == "project_code" for row in rows):
        coverage.append("项目自身代码的范围和许可绑定尚未独立核验，根许可证不继承给依赖")
    if not rows:
        coverage.append("没有可用于评估的资源记录")
    dimensions = []
    all_ids = [row.resource_id for row in rows]
    for dim, title in DIMENSIONS.items():
        relevant = [row for row in rows if row.resource_kind == "ai_asset"] if dim == "ai_assets" else rows
        unknowns = list(coverage)
        for row in relevant:
            unknowns.extend(f"{row.name}（{row.version or '版本未确定'}）：{gap}" for gap in row.gaps)
        restrictions = [f"{row.name}：{r}" for row in relevant for r in row.restrictions.get(dim, [])]
        conditions = sorted({c for row in relevant for c in row.conditions})
        intent = {"commercial": usage.commercial, "modification": usage.modified,
                  "closed_distribution": usage.distributed, "redistribution": usage.distributed,
                  "network_service": usage.network_service, "ai_assets": usage.redistributed_assets}[dim]
        if intent is None:
            unknowns.append("该用途细节未明确；预设名称不会自动补齐用途前提")
        if dim == "ai_assets":
            unknowns.append("模型、数据、素材和 API 需独立核验；未检出不等于不存在或不适用")
        status = "restricted" if restrictions else "unknown"
        if not restrictions and not coverage and relevant and all(row.supported_permission for row in relevant) and dim != "ai_assets":
            if intent is False or (dim == "closed_distribution" and usage.source_disclosure is True):
                status = "not_applicable"
                unknowns = []
                conditions = ["仅在用户明确声明不实施该用途的前提下不适用；用途改变需显式重新评估"]
            elif intent is True and not unknowns:
                status = "conditional"
        dimensions.append(DimensionAssessment(id=dim, title=title, status=status, conclusion=LABELS[status], conditions=conditions,
            restrictions=restrictions, unknowns=unknowns, resource_ids=[r.resource_id for r in relevant],
            finding_ids=sorted({f for r in relevant for f in r.finding_ids}), evidence_ids=sorted({e for r in relevant for e in r.evidence_ids}),
            strength="verified" if status in {"conditional", "not_applicable"} else "limited" if restrictions else "insufficient"))
    obligations = []
    for obl in run.obligations:
        obligations.append(AssessmentObligation(id=obl.id, action=obl.action, requirement=obl.description, trigger=obl.trigger,
            resource_ids=[r.id for r in resources if r.license_expression_id == obl.license_expression_id],
            evidence_ids=obl.source_evidence_ids, rule_id=obl.rule_id, rule_version=obl.rule_version))
    for row in rows:
        if row.supported_permission and not any(row.resource_id in o.resource_ids and o.action == "retain_license_notice" for o in obligations):
            obligations.append(AssessmentObligation(id=f"mit-notice:{row.resource_id}", action="retain_license_notice",
                requirement="保留版权声明及许可声明；未核实是否已履行", trigger="使用或复制对应 MIT 软件或其实质部分",
                resource_ids=[row.resource_id], evidence_ids=row.evidence_ids, rule_id="V4-MIT", rule_version=RULE_VERSION))
    restricted = any(d.status == "restricted" for d in dimensions)
    unknown = any(d.status == "unknown" for d in dimensions)
    summary = "当前用途存在明确前提下的限制，同时仍有未核验事项。" if restricted else "已有扫描事实，但关键授权或用途证据不足，暂不能确认整个项目可用于目标用途。" if unknown else "在已声明用途与已核验范围内，可按列明条件使用；义务履行仍须落实。"
    # PROJECT_FACTS_STEP1: observations do not change permission states.
    summary = project_fact_view(run)["summary"] + "\n\n" + summary
    return Assessment(id=f"asm_{uuid.uuid5(uuid.NAMESPACE_URL, key + ':' + str(version))}", version=version, scan_id=run.id,
        project_name=run.project.name, revision=run.project.revision, input_hash=run.provenance.input_digest.value,
        facts_hash=facts_hash, usage_hash=usage_hash, cache_key=key, generated_at=generated_at or datetime.now(timezone.utc), usage=usage,
        rule_version=rule_version, model_version=model_version, prompt_version=prompt_version, scan_status=run.status.value,
        summary=summary, dimensions=dimensions, resource_evaluations=rows, obligations=obligations, coverage_issues=coverage,
        resource_ids=all_ids, finding_ids=sorted(findings), evidence_ids=sorted(evidence), license_ids=sorted(licenses),
        remediation_ids=sorted(r.id for r in run.remediations), rule_sources=RULE_SOURCES)
