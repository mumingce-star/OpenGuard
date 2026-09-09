"""Strict, deterministic boundary for injected AI remediation providers."""

from __future__ import annotations

import json
import hashlib
import itertools
import math
import re
import uuid
import time
import logging
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from app.domain.models import (
    Evidence,
    FindingOutcome,
    ProducerRef,
    ProducerType,
    Remediation,
    RiskFinding,
    ScanError,
    ScanRun,
    ScanStage,
    VerificationStatus,
)


_INPUT_SCHEMA = "openguard.ai-remediation-input/v1"
_OUTPUT_SCHEMA = "openguard.ai-remediation/v1"
REVIEW_PLAN_SUMMARY = "现有证据尚未完成许可核验，不能据此判定授权有效或无效。"
_MAX_RESPONSE_BYTES = 64 * 1024
_NAMESPACE = uuid.UUID("92e3059e-f59c-4b2b-960d-44d9e91c0b51")
_SENSITIVE_FRAGMENT = re.compile(
    r"(?i)(?:api[_-]?key|secret|token|password|authorization|bearer)\s*[=:]"
)
_ABSOLUTE_PATH_FRAGMENT = re.compile(
    r"(?:(?<![A-Za-z0-9_./])/(?!/)|(?<![A-Za-z0-9_])[A-Za-z]:[\\/]|(?<![A-Za-z0-9_])\\\\)"
)
_ELIGIBLE_OUTCOMES = frozenset(
    {FindingOutcome.WARNING, FindingOutcome.REVIEW_REQUIRED, FindingOutcome.UNKNOWN}
)


class Provider(Protocol):
    """Transport-neutral provider implemented by a later local or remote adapter."""

    mode: Literal["local", "remote"]
    producer: ProducerRef

    def generate(self, payload: str, timeout_seconds: float) -> str: ...


class AIProviderError(RuntimeError):
    """Stable caller/configuration failure at the A5 boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class AIProviderResult:
    status: Literal["generated", "skipped", "disabled", "degraded"]
    run: ScanRun


@dataclass(frozen=True)
class _ProviderSnapshot:
    mode: Literal["local", "remote"]
    producer: ProducerRef
    generate: Any
    review_plan_mode: bool = False
    resource_batch_mode: bool = False


def _fail(code: str) -> None:
    raise AIProviderError(code) from None


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _snapshot_provider(provider: object) -> _ProviderSnapshot:
    try:
        mode = provider.mode  # type: ignore[attr-defined]
        producer = provider.producer  # type: ignore[attr-defined]
        generate = provider.generate  # type: ignore[attr-defined]
        if type(mode) is not str or mode not in {"local", "remote"}:
            raise ValueError
        if type(producer) is not ProducerRef or producer.type is not ProducerType.AI:
            raise ValueError
        if not callable(generate):
            raise ValueError
        producer_snapshot = ProducerRef.model_validate(producer.model_dump(mode="python"))
        review_plan_mode = getattr(provider, "review_plan_mode", False) is True
    except Exception:
        _fail("ai_invalid_argument")
    return _ProviderSnapshot(mode=mode, producer=producer_snapshot, generate=generate,
                             review_plan_mode=review_plan_mode,
                             resource_batch_mode=getattr(provider, "resource_batch_mode", False) is True)


def _review_context(run: ScanRun, finding: RiskFinding) -> dict[str, Any] | None:
    """Share a workflow, never a resource-specific factual assessment."""
    if finding.rule_id != "license-evidence-gate" or finding.obligation_ids:
        return None
    resource = next(r for r in [*run.components, *run.ai_assets] if r.id == finding.resource_id)
    license_ = next((l for l in run.licenses if l.id == resource.license_expression_id), None)
    if license_ is None or not finding.evidence_ids:
        return None
    evidence = {e.id: e for e in run.evidence}
    return {
        "rule_id": finding.rule_id, "rule_version": finding.rule_version,
        "outcome": finding.outcome.value, "severity": finding.severity.value,
        "resource_kind": finding.resource_kind,
        "resource_type": getattr(resource, "asset_type", getattr(resource, "ecosystem", "unknown")),
        "license_expression": license_.expression,
        "license_status": license_.verification_status.value,
        "evidence_kinds": sorted({evidence[i].kind.value for i in finding.evidence_ids}),
        "evidence_statuses": sorted({evidence[i].verification_status.value for i in finding.evidence_ids}),
    }


def _decode_review_plan(raw: str, plan_id: str) -> dict[str, Any]:
    if type(raw) is not str or len(raw.encode("utf-8")) > _MAX_RESPONSE_BYTES:
        raise ValueError("invalid plan")
    value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    if type(value) is not dict or set(value) != {"schema_version", "plan_id", "summary", "steps"}:
        raise ValueError("invalid plan shape")
    if value["schema_version"] != "openguard.ai-review-plan/v1" or value["plan_id"] != plan_id:
        raise ValueError("invalid plan identity")
    if value["summary"] != REVIEW_PLAN_SUMMARY:
        raise ValueError("plan must preserve uncertainty")
    if type(value["steps"]) is not list or len(value["steps"]) != 3:
        raise ValueError("invalid plan steps")
    texts = [value["summary"], *value["steps"]]
    if any(_unsafe_text(t) or not 5 <= len(t) <= 200 or not re.search(r"[\u4e00-\u9fff]", t) for t in texts):
        raise ValueError("invalid Chinese plan text")
    if len(set(value["steps"])) != len(value["steps"]):
        raise ValueError("duplicate plan steps")
    if any(len(re.findall(r"[\u4e00-\u9fff]", t)) < len(re.findall(r"[A-Za-z]", t)) for t in texts):
        raise ValueError("plan must be primarily Chinese")
    if any(re.search(r"NOASSERTION|pending|license_expression|已获授权|已经合规|保证合规|可(?:以)?商用|必须删除|(?:无需|不用|不必).{0,12}(?:核验|复核|确认)", t, re.I) for t in value["steps"]):
        raise ValueError("plan confuses status with license evidence")
    return value


def _unsafe_text(value: object) -> bool:
    return (
        type(value) is not str
        or _SENSITIVE_FRAGMENT.search(value) is not None
        or _ABSOLUTE_PATH_FRAGMENT.search(value) is not None
    )


def _request_payload(run: ScanRun, finding: RiskFinding) -> tuple[str, set[str]]:
    evidence_by_id = {item.id: item for item in run.evidence}
    resource_by_id = {item.id: item for item in [*run.components, *run.ai_assets]}
    license_by_id = {item.id: item for item in run.licenses}

    resource = resource_by_id[finding.resource_id]
    licenses = []
    if resource.license_expression_id is not None:
        licenses.append(license_by_id[resource.license_expression_id])

    finding_evidence = [evidence_by_id[item_id] for item_id in finding.evidence_ids]
    license_evidence_ids = sorted(
        {item_id for license_ in licenses for item_id in license_.evidence_ids}
    )
    license_evidence = [evidence_by_id[item_id] for item_id in license_evidence_ids]
    allowed_evidence_ids = {item.id for item in [*finding_evidence, *license_evidence]}
    # Shared license/finding references point to the same immutable evidence.
    # Send each object once; all original reference IDs remain in the payload.
    finding_ids = {item.id for item in finding_evidence}
    license_evidence = [item for item in license_evidence if item.id not in finding_ids]

    def dump_evidence(items: list[Evidence]) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in sorted(items, key=lambda item: item.id)]

    payload = {
        "schema_version": _INPUT_SCHEMA,
        "language": "en",
        "finding": finding.model_dump(mode="json"),
        "evidence": dump_evidence(finding_evidence),
        "licenses": [
            item.model_dump(mode="json") for item in sorted(licenses, key=lambda item: item.id)
        ],
        "license_evidence": dump_evidence(license_evidence),
        "forbidden": "Do not add or modify resource, license, obligation, rule, outcome, or severity facts.",
    }
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        allowed_evidence_ids,
    )


def _decode_response(
    raw: object, *, finding_id: str, allowed_evidence_ids: set[str]
) -> dict[str, Any]:
    if type(raw) is not str:
        raise ValueError("response must be text")
    try:
        if len(raw.encode("utf-8")) > _MAX_RESPONSE_BYTES:
            raise ValueError("response too large")
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non-finite number")),
        )
    except (TypeError, UnicodeError, ValueError):
        raise ValueError("invalid JSON response") from None

    required = {"schema_version", "finding_id", "summary", "steps", "evidence_ids"}
    if type(value) is not dict or set(value) != required:
        raise ValueError("invalid response shape")
    if value["schema_version"] != _OUTPUT_SCHEMA or value["finding_id"] != finding_id:
        raise ValueError("response identity mismatch")

    summary = value["summary"]
    steps = value["steps"]
    evidence_ids = value["evidence_ids"]
    if _unsafe_text(summary) or not summary.strip() or len(summary) > 1000:
        raise ValueError("invalid summary")
    if (
        type(steps) is not list
        or not 1 <= len(steps) <= 8
        or any(_unsafe_text(item) or not item.strip() or len(item) > 1000 for item in steps)
    ):
        raise ValueError("invalid steps")
    if (
        type(evidence_ids) is not list
        or not 1 <= len(evidence_ids) <= 32
        or any(type(item) is not str for item in evidence_ids)
        or len(set(evidence_ids)) != len(evidence_ids)
        or not set(evidence_ids).issubset(allowed_evidence_ids)
    ):
        raise ValueError("invalid evidence references")

    return {
        "schema_version": _OUTPUT_SCHEMA,
        "finding_id": finding_id,
        "summary": summary,
        "steps": sorted(set(steps)),
        "evidence_ids": sorted(evidence_ids),
    }


def _with_ai_provenance(run: ScanRun, producer: ProducerRef) -> dict[str, Any]:
    payload = run.model_dump(mode="python")
    payload["provenance"] = run.provenance.model_copy(
        update={"ai_enabled": True, "ai_model": producer}
    )
    return payload


def _degraded(run: ScanRun, provider: _ProviderSnapshot, code: str) -> AIProviderResult:
    messages = {
        "ai_provider_unavailable": "AI remediation provider was unavailable.",
        "ai_response_invalid": "AI remediation response was rejected.",
    }
    payload = _with_ai_provenance(run, provider.producer)
    already_recorded = any(
        item.code == code and item.stage is ScanStage.AI_ASSIST for item in run.errors
    )
    if not already_recorded:
        payload["errors"] = [
            *run.errors,
            ScanError(
                code=code,
                stage=ScanStage.AI_ASSIST,
                message=messages[code],
                recoverable=True,
            ),
        ]
    return AIProviderResult(status="degraded", run=ScanRun.model_validate(payload))


def _resource_batches(run: ScanRun, eligible: list[RiskFinding], provider: _ProviderSnapshot,
                      timeout: float) -> tuple[list[Remediation], set[str]]:
    """Read each resource's evidence in bounded batches; no cross-resource answer cache."""
    resources = {r.id: r for r in [*run.components, *run.ai_assets]}
    licenses = {r.id: r for r in run.licenses}
    evidence = {r.id: r for r in run.evidence}
    records = []
    for finding in eligible:
        resource = resources[finding.resource_id]
        license_ = licenses.get(resource.license_expression_id)
        refs = [evidence[e] for e in finding.evidence_ids[:3]]
        if not refs:
            continue
        locators = " ".join(e.locator for e in refs)
        if "examples/" in locators:
            scope = "示例"
        elif any(name in locators for name in ("uv.lock", "poetry.lock", "package-lock", "yarn.lock")):
            scope = "锁文件"
        elif "build-system" in locators:
            scope = "构建"
        elif "dependency-groups" in locators or "optional-dependencies" in locators:
            scope = "依赖组"
        elif any(e.kind.value == "tool_output" for e in refs):
            scope = "工具"
        else:
            scope = "声明"
        records.append((finding, resource, refs, {
            "name": resource.name, "version": resource.version,
            "kind": getattr(resource, "asset_type", getattr(resource, "ecosystem", "unknown")),
            "license": license_.expression if license_ else None,
            "license_status": license_.verification_status.value if license_ else "unknown",
            "scope": scope,
            "focus": (f"这是{scope}证据。" + ("记录有版本，核对该发行版本与许可原文的关联。" if resource.version
                      else "未提供固定版本，先核对约束对应的实际版本及其许可。")
                      + ("已有许可表达式，核对声明适用范围，不当作授权通过。" if license_ and license_.expression not in {"NOASSERTION", "NONE"}
                         else "未确认许可表达式，不能声称整个仓库没有许可。")),
            "license_source": license_.source_url if license_ else None,
            "license_evidence": [{"locator": evidence[e].locator,
                                  "excerpt": (evidence[e].excerpt or "")[:180]}
                                 for e in (license_.evidence_ids[:3] if license_ else [])
                                 if e not in {ref.id for ref in refs}],
            "rule": finding.rule_id, "rule_version": finding.rule_version,
            "trigger": finding.trigger, "outcome": finding.outcome.value,
            "severity": finding.severity.value,
            "obligations": [o.model_dump(mode="json") for o in run.obligations if o.id in finding.obligation_ids],
            "usage": "unknown; infer only the context visible in the quoted evidence",
            "coverage": [{"stage": stage, "code": code} for stage, code in
                         sorted({(e.stage.value, e.code) for e in run.errors})],
            "evidence_total": len(finding.evidence_ids),
            "evidence": [{"locator": e.locator, "line": e.start_line,
                          "hash": e.content_hash.value if e.content_hash else None, "kind": e.kind.value,
                          "excerpt": (e.excerpt or "")[:180],
                          "excerpt_truncated": len(e.excerpt or "") > 180} for e in refs],
        }))
    remediations: list[Remediation] = []
    errors: set[str] = set()
    started = time.monotonic()
    calls = 0
    # Keep materially different evidence situations out of a shared inference batch.
    # Every member still supplies its own identity, version and original excerpts.
    def group_key(row):
        ctx = row[3]
        return (ctx["scope"], bool(ctx["version"]), ctx["license"] or "", ctx["license_status"],
                ctx["rule"], ctx["outcome"])
    batches = []
    for _, members in itertools.groupby(sorted(records, key=group_key), key=group_key):
        cohort = list(members)
        batches.extend(cohort[offset:offset + 16] for offset in range(0, len(cohort), 16))
    for batch in batches:
        items = [{"i": i, **row[3]} for i, row in enumerate(batch)]
        canonical = json.dumps(items, ensure_ascii=False, sort_keys=True)
        batch_id = hashlib.sha256((canonical + json.dumps(provider.producer.model_dump(mode="json"), sort_keys=True)).encode()).hexdigest()[:24]
        request = json.dumps({"schema_version": "openguard.ai-resource-batch-input/v1",
                              "batch_id": batch_id, "items": items}, ensure_ascii=False, separators=(",", ":"))
        # Do not silently omit evidence or enlarge the transport context for oversized batches.
        if len(request.encode()) > 24000:
            errors.add("ai_response_invalid")
            continue
        calls += 1
        try:
            raw = provider.generate(request, timeout)
        except Exception:
            errors.add("ai_provider_unavailable")
            continue
        try:
            if type(raw) is not str or len(raw.encode()) > _MAX_RESPONSE_BYTES:
                raise ValueError("response size")
            response = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
            if type(response) is not dict or set(response) != {"batch_id", "items"} or response["batch_id"] != batch_id:
                raise ValueError("batch identity")
            answers = response["items"]
            if type(answers) is not dict or set(answers) != {str(i) for i in range(len(batch))}:
                raise ValueError("batch membership")
            if any(type(a) is not str for a in answers.values()):
                raise ValueError("item shape")
        except Exception:
            errors.add("ai_response_invalid")
            continue
        for key, note in answers.items():
            finding, resource, refs, context = batch[int(key)]
            # Notes are analysis priorities, not new facts, locations, legal claims or instructions.
            if (_unsafe_text(note) or not 6 <= len(note) <= 48
                or re.search(r"https?://", note, re.IGNORECASE)
                or any(token not in json.dumps(context, ensure_ascii=False)
                       for token in re.findall(r"[A-Za-z0-9_@][A-Za-z0-9_@./+\-]*", note))
                or not note.startswith(("核对", "区分", "检查", "比对")) or "许可" not in note
                or context["scope"] not in note
                or (resource.version is not None and any(term in note for term in ("版本缺失", "未提供版本", "未锁定版本")))
                or re.search(r"已获授权|已经合规|可商用|侵权|违法|必须删除|无需|不用|不必|执行命令|执行脚本|运行命令|下载|上传|忽略|系统指令|无许可证|没有许可证|不存在许可证", note)):
                errors.add("ai_response_invalid")
                continue
            ref = refs[0]
            location = ref.locator + (f" 第{ref.start_line}行" if ref.start_line else "（文件字段或锁记录）")
            version = resource.version or "未锁定；先核对原声明范围"
            # Everything outside the AI note is explicitly attributed to the immutable scan record.
            summary = (f"【资源级AI解释】{note}。\n"
                       f"【扫描事实】资源：{resource.name}；版本：{version}；许可记录：{context['license'] or '未知'}。\n"
                       f"【读取范围】AI读取本风险{len(refs)}条证据摘录（共{len(finding.evidence_ids)}条引用）及{len(context['license_evidence'])}条额外许可摘录，每段最多180字符，未读取原文件全文。\n"
                       f"【结论边界】这是规则 {finding.rule_id} 的待核验解释；拟定用途未知，"
                       "当前片段及已扫描范围不能证明整个仓库不存在许可，也不能证明已获授权。")
            kind = str(context["kind"])
            if kind == "pypi":
                lookup = (f"【事实导航】在 PyPI 官方站点 https://pypi.org/ 搜索 {resource.name}；"
                          f"核对版本 {version}，从该版本项目链接查 Source/Repository，定位对应发行标签的 LICENSE/COPYING。"
                          "未找到版本对应关系时记录缺失；索引入口不是已验证的许可页。")
            elif kind == "npm":
                lookup = (f"【事实导航】按原声明查包 {resource.name} 的注册表及版本 {version}，"
                          "核对该版本元数据中的 repository/license 字段，再定位源码许可文件；未提供可靠入口时明确记录缺失。")
            elif kind == "api":
                lookup = (f"【事实导航】先在 {location} 区分 {resource.name} 的示例、兼容接口和实际调用；"
                          "查已确认服务提供方的使用条款，另查 SDK 许可证，不能互相代替；提供方入口未核验时记录缺失。")
            else:
                lookup = (f"【事实导航】从 {location} 中 {resource.name} 的原始引用定位资源卡，"
                          f"核对版本 {version} 和卡片许可字段及原文；引用可能只是示例，未找到可靠入口时记录缺失。")
            if kind == "unknown":
                lookup = (f"【事实导航】回到 {location} 核对 {resource.name} 的原始引用；"
                          f"若为工作流 uses 声明，确认 owner/repository 和版本 {version}，再查看该引用版本仓库内的 LICENSE 或 COPYING。"
                          "不是工作流时按原始工具证据确认资源类型和来源；未确认入口时记录缺失，不把它当成模型或数据集。")
            if context["license"] and context["license"] not in {"NOASSERTION", "NONE"}:
                lookup = (f"【事实导航】已有许可记录 {context['license']}，先核对原声明是否适用于 {resource.name} 的版本 {version}，"
                          "保留对应许可原文和版本来源，再核对声明要求及适用范围；已有表达式不代表义务已经满足。")
            steps = [f"【证据定位】打开本条证据 {location}，核对包或资源名称、版本及其所属依赖组或示例上下文。",
                     lookup,
                     "【核验动作】对照实际用途与是否分发，逐项记录对应条款、适用条件和未确认项；保留原文与版本来源，再决定是否需要补充声明。"]
            # The frozen model canonicalizes steps as a sorted set. Preserve sequence without changing it.
            steps = [f"{i}. {step}" for i, step in enumerate(steps, 1)]
            if len(summary) > 1000 or _unsafe_text(summary) or any(len(s) > 1000 or _unsafe_text(s) for s in steps):
                errors.add("ai_response_invalid")
                continue
            identity = json.dumps([finding.id, batch_id, note, summary, steps], ensure_ascii=False, sort_keys=True)
            remediations.append(Remediation(id=f"rem_{uuid.uuid5(_NAMESPACE, identity)}", finding_id=finding.id,
                summary=summary, steps=steps, evidence_ids=[e.id for e in refs], generated_by=provider.producer,
                verification_status=VerificationStatus.PENDING))
    if len(remediations) != len(eligible) and not errors:
        errors.add("ai_response_invalid")
    logging.getLogger(__name__).info("resource_ai batches=%s cache_hits=0 resources=%s generated=%s elapsed=%.3f",
                                    calls, len(eligible), len(remediations), time.monotonic() - started)
    return remediations, errors


def apply_ai_remediations(
    run: ScanRun,
    provider: Provider | None,
    *,
    enabled: bool = True,
    timeout_seconds: float = 10.0,
) -> AIProviderResult:
    """Generate pending remediations without promoting model output to facts."""

    if (
        type(run) is not ScanRun
        or type(enabled) is not bool
        or type(timeout_seconds) not in {int, float}
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        _fail("ai_invalid_argument")
    try:
        ScanRun.model_validate(run.model_dump(mode="python"))
    except Exception:
        _fail("ai_invalid_argument")

    if not enabled:
        payload = run.model_dump(mode="python")
        payload["provenance"] = run.provenance.model_copy(
            update={"ai_enabled": False, "ai_model": None}
        )
        return AIProviderResult(status="disabled", run=ScanRun.model_validate(payload))

    provider_snapshot = _snapshot_provider(provider)
    eligible = [
        item
        for item in run.findings
        if item.outcome in _ELIGIBLE_OUTCOMES and item.remediation_id is None
    ]
    if not eligible:
        return AIProviderResult(status="skipped", run=run)

    remediations: list[Remediation] = []
    plans: dict[str, dict[str, Any] | None] = {}
    plan_errors: set[str] = set()
    if provider_snapshot.resource_batch_mode:
        remediations, plan_errors = _resource_batches(run, eligible, provider_snapshot, float(timeout_seconds))
    for finding in ([] if provider_snapshot.resource_batch_mode else eligible):
        context = _review_context(run, finding) if provider_snapshot.review_plan_mode else None
        if context is not None:
            canonical = json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            plan_id = "plan_" + hashlib.sha256(canonical.encode()).hexdigest()[:24]
            if plan_id not in plans:
                request = json.dumps({"schema_version": "openguard.ai-review-plan-input/v1",
                                      "plan_id": plan_id, "context": context}, ensure_ascii=False)
                try:
                    raw = provider_snapshot.generate(request, float(timeout_seconds))
                except Exception:
                    plan_errors.add("ai_provider_unavailable")
                    plans[plan_id] = None
                    continue
                try:
                    plans[plan_id] = _decode_review_plan(raw, plan_id)
                except Exception:
                    plan_errors.add("ai_response_invalid")
                    plans[plan_id] = None
                    continue
            plan = plans[plan_id]
            if plan is None:
                continue
            # The model supplies a shared workflow. Bind only this finding's
            # actual references, never copy another resource's evidence IDs.
            response = {"summary": "【同类风险AI核验建议，未逐项确认许可】" + plan["summary"],
                        "steps": plan["steps"], "evidence_ids": sorted(finding.evidence_ids)[:3]}
            identity = json.dumps([finding.id, provider_snapshot.producer.model_dump(mode="json"),
                                   plan_id, response], ensure_ascii=False, sort_keys=True)
            remediations.append(Remediation(
                id=f"rem_{uuid.uuid5(_NAMESPACE, identity)}", finding_id=finding.id,
                summary=response["summary"], steps=response["steps"], evidence_ids=response["evidence_ids"],
                generated_by=provider_snapshot.producer, verification_status=VerificationStatus.PENDING))
            continue
        request, allowed_evidence_ids = _request_payload(run, finding)
        try:
            raw_response = provider_snapshot.generate(request, float(timeout_seconds))
        except Exception:
            if provider_snapshot.review_plan_mode:
                plan_errors.add("ai_provider_unavailable")
                continue
            return _degraded(run, provider_snapshot, "ai_provider_unavailable")
        try:
            response = _decode_response(
                raw_response,
                finding_id=finding.id,
                allowed_evidence_ids=allowed_evidence_ids,
            )
            identity = json.dumps(
                [finding.id, provider_snapshot.producer.model_dump(mode="json"), response],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            remediations.append(
                Remediation(
                    id=f"rem_{uuid.uuid5(_NAMESPACE, identity)}",
                    finding_id=finding.id,
                    summary=response["summary"],
                    steps=response["steps"],
                    evidence_ids=response["evidence_ids"],
                    generated_by=provider_snapshot.producer,
                    verification_status=VerificationStatus.PENDING,
                )
            )
        except Exception:
            if provider_snapshot.review_plan_mode:
                plan_errors.add("ai_response_invalid")
                continue
            return _degraded(run, provider_snapshot, "ai_response_invalid")

    payload = _with_ai_provenance(run, provider_snapshot.producer)
    payload["remediations"] = [*run.remediations, *remediations]
    remediation_ids = {item.finding_id: item.id for item in remediations}
    payload["findings"] = [
        item.model_copy(update={"remediation_id": remediation_ids.get(item.id, item.remediation_id)})
        for item in run.findings
    ]
    if provider_snapshot.producer not in run.provenance.tool_versions:
        payload["provenance"] = payload["provenance"].model_copy(
            update={"tool_versions": [*run.provenance.tool_versions, provider_snapshot.producer]}
        )
    try:
        generated = ScanRun.model_validate(payload)
    except Exception:
        return _degraded(run, provider_snapshot, "ai_response_invalid")
    for code in sorted(plan_errors):
        generated = _degraded(generated, provider_snapshot, code).run
    return AIProviderResult(status="degraded" if plan_errors else "generated", run=generated)
