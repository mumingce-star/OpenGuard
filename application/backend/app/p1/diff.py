"""Read-only, deterministic comparison of two immutable ScanRun facts snapshots."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import quote, unquote
from collections import Counter
from packaging.utils import InvalidName, canonicalize_name

from app.api.service import ApiError
from app.assessment.engine import facts_digest
from app.assessment.store import AssessmentStoreError
from app.domain.models import ScanStatus
from app.persistence import ScanRegistryError
from .history import canonical, identity, public_source, utc

ALGORITHM = "scan-diff/1.0"
_PURL = re.compile(r"^pkg:([a-z0-9.+-]+)/((?:[^@/?#]+/)*[^@/?#]+)(?:@([^?#]+))?(?:\?([^#]+))?(?:#.*)?$", re.I)


def _fail(code: str, status: int, message: str) -> None:
    raise ApiError(status_code=status, code=code, message=message, reason=code)


def _scalar(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value)
    return None


def _token(value):
    """Unambiguous stable key, without placing locator/text in a public path."""
    return hashlib.sha256(canonical(value)).hexdigest()


def _evidence(available, ids):
    return [available[item] for item in sorted(set(ids)) if item in available]


def _package_name(ecosystem, name):
    if ecosystem == "pypi":
        # Same normalization used by the existing Python manifest parser.
        try:
            return str(canonicalize_name(name, validate=True))
        except InvalidName:
            return None
    if ecosystem == "npm":
        name = name.casefold()
        return name if re.fullmatch(r"(?:@[a-z0-9._-]+/)?[a-z0-9][a-z0-9._-]*", name) else None
    return name


def _purl_keys(value):
    if not isinstance(value, str) or re.search(r"%(?![0-9A-Fa-f]{2})", value):
        return None, None
    main, _, subpath = value.partition("#")
    matched = _PURL.fullmatch(main)
    if not matched:
        return None, None
    kind, raw_path, version, qualifiers = matched.groups()
    kind = kind.casefold()
    parts = [unquote(piece) for piece in raw_path.split("/")]
    if any(not part or "/" in part or part in {".", ".."} for part in parts):
        return None, None
    if kind == "pypi" and len(parts) != 1:
        return None, None
    parts[-1] = _package_name(kind, parts[-1])
    if parts[-1] is None:
        return None, None
    if kind == "npm":
        parts = [part.casefold() for part in parts]
    path = "/".join(quote(part, safe=".-_~") for part in parts)
    identity_key = f"pkg:{kind}/{path}"
    qualifier_suffix = ""
    if qualifiers:
        pairs = []
        for part in qualifiers.split("&"):
            key, separator, val = part.partition("=")
            key = unquote(key).casefold()
            if not separator or not re.fullmatch(r"[a-z][a-z0-9._-]*", key) or not val:
                return None, None
            pairs.append((key, quote(unquote(val), safe=".-_~")))
        if len({key for key, _ in pairs}) != len(pairs):
            return None, None
        qualifier_suffix = "?" + "&".join(f"{key}={val}" for key, val in sorted(pairs))
    instance = f"{identity_key}@{quote(unquote(version), safe='.-_~')}{qualifier_suffix}" if version else None
    if subpath and instance:
        parts = [unquote(part) for part in subpath.split("/")]
        if any(not part or part in {".", ".."} or "/" in part for part in parts):
            return None, None
        instance += "#" + "/".join(quote(part, safe=".-_~") for part in parts)
    return identity_key + qualifier_suffix, instance


def _resource(run, kind, item):
    if kind == "component":
        identity_key, instance_key = _purl_keys(item.purl)
        ecosystem = str(item.ecosystem)
        name = _package_name(ecosystem, item.name)
        if identity_key is None and ecosystem != "unknown" and name:
            identity_key = f"pkg:{ecosystem}/{quote(name, safe='/-_.~')}"
            instance_key = identity_key + "@" + quote(item.version, safe=".-_~") if item.version else None
        values = {"name": item.name, "version": item.version, "ecosystem": item.ecosystem,
                  "component_type": item.component_type, "purl": item.purl,
                  "source_url": item.source_url}
    else:
        # Only the resource's declared provider is authoritative here.
        identity_key = (f"ai:{item.asset_type.value}:{quote(item.provider, safe='')}:{quote(item.name, safe='')}"
                        if item.provider and item.name else None)
        instance_key = identity_key + "@" + quote(item.version, safe=".-_~") if identity_key and item.version else None
        values = {"name": item.name, "provider": item.provider, "version": item.version,
                  "asset_type": item.asset_type, "source_url": item.source_url}
    return {"ref": dict(scan_id=run.id, resource_kind=kind, resource_id=item.id,
                        resource_identity_key=identity_key, resource_instance_key=instance_key),
            "item": item, "values": values, "license_expression_id": item.license_expression_id,
            "evidence_ids": item.evidence_ids}


def _resources(run):
    return [_resource(run, "component", item) for item in run.components] + [_resource(run, "ai_asset", item) for item in run.ai_assets]


def _changes(before, after):
    result = []
    for key in sorted(set(before["values"]) | set(after["values"])):
        left, right = _scalar(before["values"].get(key)), _scalar(after["values"].get(key))
        if left != right:
            result.append(dict(path=f"/resources/{key}", before=left, after=right))
    return result


def _match(base, target):
    used_b, used_t, pairs = set(), set(), []
    def index(rows, key):
        result = {}
        for position, row in enumerate(rows):
            value = row["ref"][key]
            if value:
                result.setdefault(value, []).append(position)
        return result
    instance_base, instance_target = index(base, "resource_instance_key"), index(target, "resource_instance_key")
    for key in sorted(set(instance_base) & set(instance_target)):
        left, right = instance_base[key], instance_target[key]
        if len(left) == len(right) == 1 and base[left[0]]["ref"]["resource_identity_key"] == target[right[0]]["ref"]["resource_identity_key"]:
            used_b.add(left[0]); used_t.add(right[0]); pairs.append((left[0], right[0]))
    identity_base, identity_target = index(base, "resource_identity_key"), index(target, "resource_identity_key")
    for key in sorted(set(identity_base) & set(identity_target)):
        left = [i for i in identity_base[key] if i not in used_b]
        right = [i for i in identity_target[key] if i not in used_t]
        if len(left) == len(right) == 1:
            used_b.add(left[0]); used_t.add(right[0]); pairs.append((left[0], right[0]))
    return pairs, [row for i, row in enumerate(base) if i not in used_b], [row for i, row in enumerate(target) if i not in used_t]


def _fact_changes(base_rows, target_rows, *, category):
    """Pair only unique fact keys; duplicate keys remain separate observations.

    Each row holds match key, real source ID, scalar fields, evidence IDs and
    a prebuilt per-scan evidence index. Missing values retain their source ID.
    """
    counts = [Counter(row[0] for row in rows) for rows in (base_rows, target_rows)]
    ambiguous = {key for count in counts for key, n in count.items() if n > 1}
    def flattened(rows, side):
        output = {}
        for match_key, source_id, values, evidence_ids, evidence_index in rows:
            if match_key in ambiguous:
                match_key = f"{side}:{_token([match_key, source_id, values])}"
            for path, value in values.items():
                output[(match_key, path)] = (source_id, _scalar(value), evidence_ids, evidence_index)
        return output
    before, after = flattened(base_rows, "base"), flattened(target_rows, "target")
    changes = []
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        if (old[1] if old else None) == (new[1] if new else None):
            continue
        evidence = _evidence(old[3], old[2]) if old else []
        if new:
            evidence += _evidence(new[3], new[2])
        changes.append(dict(source_ids_before=[old[0]] if old else [], source_ids_after=[new[0]] if new else [],
                            path=f"/{category}/{quote(key[0], safe='')}/{key[1]}", before=old[1] if old else None,
                            after=new[1] if new else None,
                            evidence_refs=sorted({(x['scan_id'], x['evidence_id']): x for x in evidence}.values(), key=lambda x: (x['scan_id'], x['evidence_id']))))
    return changes


def _list_rows(prefix, value):
    # These Formal fields are sets of conditions, not procedural sequences.
    # Stable membership paths avoid shifting every row after an insertion.
    return {f"{prefix}/{_token(item)}": item for item in sorted(set(value))}


def _assessment_rows(assessment, evidence_index, resource_keys):
    """The Formal Assessment subset, deliberately excluding AI and summaries."""
    rows = []
    for dim in assessment.dimensions:
        values = {"status": dim.status, "strength": dim.strength}
        values.update(_list_rows("conditions", dim.conditions))
        values.update(_list_rows("restrictions", dim.restrictions))
        values.update(_list_rows("unknowns", dim.unknowns))
        rows.append((f"dimension:{dim.id}", assessment.id, values, dim.evidence_ids, evidence_index))
    for item in assessment.resource_evaluations:
        values = {"name": item.name, "version": item.version, "scope": item.scope, "license_expression": item.license_expression,
                  "license_verified": item.license_verified, "supported_permission": item.supported_permission}
        values.update(_list_rows("conditions", item.conditions))
        values.update(_list_rows("gaps", item.gaps))
        values.update(_list_rows("next_steps", item.next_steps))
        for restriction, items in sorted(item.restrictions.items()):
            values.update(_list_rows(f"restrictions/{quote(restriction, safe='')}", items))
        key = resource_keys.get(item.resource_id, item.resource_id)
        rows.append((f"resource:{item.resource_kind}:{key}", item.resource_id, values, sorted(set(item.evidence_ids) | set(item.scope_evidence_ids)), evidence_index))
    for item in assessment.obligations:
        values = {"action": item.action, "rule_id": item.rule_id, "rule_version": item.rule_version,
                  "fulfillment": item.fulfillment}
        # Requirement and trigger are formal fields.  Keep them scalar facts;
        # they are assessment-authored deterministic policy text, not AI text.
        values.update({"requirement": item.requirement, "trigger": item.trigger})
        resource_set = sorted(resource_keys.get(rid, rid) for rid in item.resource_ids)
        key = _token([item.rule_id, item.action, resource_set])
        rows.append((f"obligation:{key}", item.id, values, item.evidence_ids, evidence_index))
    coverage = _list_rows("coverage_issues", assessment.coverage_issues)
    rows.append(("coverage", assessment.id, coverage, assessment.evidence_ids, evidence_index))
    return rows


def _license_rows(run, resource_keys, resources, evidence_index, *, verification=False):
    """Keep explicit resource bindings and standalone observations separate."""
    licenses = {item.id: item for item in run.licenses}
    rows = []
    for row in resources:
        license_id = row["license_expression_id"]
        license_ = licenses.get(license_id)
        if license_ is None:
            continue
        resource_key = resource_keys.get(row["ref"]["resource_id"], row["ref"]["resource_id"])
        evidence_ids = sorted(set(row["evidence_ids"]) | set(license_.evidence_ids))
        if verification:
            values = {"verification_status": license_.verification_status}
        else:
            values = {"expression": license_.expression, "source_url": license_.source_url,
                      "confidence": license_.confidence}
            values.update(_list_rows("normalized_ids", license_.normalized_ids))
        rows.append((f"{resource_key}:license", license_.id, values, evidence_ids, evidence_index))
    bound = {row["license_expression_id"] for row in resources}
    evidence = {item.id: item for item in run.evidence}
    for item in run.licenses:
        if item.id in bound:
            continue
        # An unbound/root observation is never applied to a dependency or AI asset.
        locators = sorted({(evidence[eid].kind.value, evidence[eid].locator) for eid in item.evidence_ids})
        key = "standalone:" + _token(locators)
        if verification:
            values = {"verification_status": item.verification_status}
        else:
            values = {"expression": item.expression, "source_url": item.source_url,
                      "confidence": item.confidence}
            values.update(_list_rows("normalized_ids", item.normalized_ids))
        rows.append((key, item.id, values, item.evidence_ids, evidence_index))
    return rows


class DiffReader:
    def __init__(self, registry, assessment_store):
        self.registry, self.assessment_store = registry, assessment_store

    def _stored(self, scan_id):
        if self.registry is None:
            _fail("upstream_unavailable", 503, "扫描存储暂不可用。")
        try:
            return self.registry.get(scan_id)
        except ScanRegistryError as error:
            if error.code in {"registry_not_found", "registry_invalid_argument"}:
                _fail("not_found", 404, "扫描记录不存在。")
            _fail("upstream_unavailable", 503, "扫描存储暂不可用。")

    @staticmethod
    def _ref(stored):
        run = stored.run
        return dict(scan_id=run.id, revision=run.project.revision, facts_hash=facts_digest(run),
                    input_hash=run.provenance.input_digest.value,
                    inventory_hash=run.provenance.inventory_digest.value if run.provenance.inventory_digest else None,
                    status=run.status, registry_revision=stored.revision)

    def _assessment(self, scan_id, specified):
        if self.assessment_store is None:
            return None
        try:
            if not specified:
                return self.assessment_store.latest(scan_id)
            selected = self.assessment_store.get(scan_id, specified)
            if selected is None:
                lookup = getattr(self.assessment_store, "get_by_id", None)
                cross_scan = lookup(specified) if callable(lookup) else None
                if cross_scan is not None:
                    _fail("invalid_argument", 400, "评估与指定扫描不匹配。")
            return selected
        except AssessmentStoreError:
            _fail("upstream_unavailable", 503, "评估存储暂不可用。")

    @staticmethod
    def _assessment_ref(value):
        return dict(assessment_id=value.id, version=value.version, scan_id=value.scan_id, facts_hash=value.facts_hash,
                    usage_hash=value.usage_hash, rule_version=value.rule_version, formal=value.formal)

    def compare(self, target_scan_id, base_scan_id, base_assessment_id=None, target_assessment_id=None):
        if not isinstance(base_scan_id, str) or not isinstance(target_scan_id, str) or not base_scan_id or not target_scan_id or base_scan_id == target_scan_id:
            _fail("invalid_argument", 400, "比较参数无效。")
        if (base_assessment_id is None) != (target_assessment_id is None):
            _fail("invalid_argument", 400, "评估参数必须成对提供。")
        if base_assessment_id is not None and (not isinstance(base_assessment_id, str) or not base_assessment_id or not isinstance(target_assessment_id, str) or not target_assessment_id):
            _fail("invalid_argument", 400, "评估参数无效。")
        base_stored, target_stored = self._stored(base_scan_id), self._stored(target_scan_id)
        base, target = base_stored.run, target_stored.run
        if base.status in {ScanStatus.QUEUED, ScanStatus.RUNNING} or target.status in {ScanStatus.QUEUED, ScanStatus.RUNNING}:
            _fail("not_ready", 409, "扫描尚未完成，暂不能比较。")
        if base.status not in {ScanStatus.COMPLETED, ScanStatus.PARTIAL} or target.status not in {ScanStatus.COMPLETED, ScanStatus.PARTIAL}:
            _fail("not_comparable", 409, "扫描状态不可比较。")
        bsrc, bok = public_source(base); tsrc, tok = public_source(target)
        bid, tid = identity(base, bsrc, bok), identity(target, tsrc, tok)
        if bid["key"] != tid["key"]:
            _fail("not_comparable", 409, "扫描项目身份不一致，不能比较。")
        bref, tref = self._ref(base_stored), self._ref(target_stored)
        base_rows, target_rows = _resources(base), _resources(target)
        pairs, remaining_base, remaining_target = _match(base_rows, target_rows)
        remaining_identity_counts = []
        for rows in (remaining_base, remaining_target):
            remaining_identity_counts.append(Counter(
                row["ref"]["resource_identity_key"]
                for row in rows
                if row["ref"]["resource_identity_key"]
            ))
        base_resource_keys = {row["ref"]["resource_id"]: "base:" + row["ref"]["resource_id"] for row in base_rows}
        target_resource_keys = {row["ref"]["resource_id"]: "target:" + row["ref"]["resource_id"] for row in target_rows}
        for left, right in pairs:
            key = "pair:" + _token([base_rows[left]["ref"]["resource_id"], target_rows[right]["ref"]["resource_id"]])
            base_resource_keys[base_rows[left]["ref"]["resource_id"]] = key
            target_resource_keys[target_rows[right]["ref"]["resource_id"]] = key
        evidence_indexes = [{item.id: dict(namespace="scan", scan_id=run.id, evidence_id=item.id) for item in run.evidence} for run in (base, target)]
        base_evidence, target_evidence = evidence_indexes
        assessment_diff = self._assessment_diff(base, target, base_assessment_id, target_assessment_id, base_resource_keys, target_resource_keys, base_evidence, target_evidence)
        selected = {"base": assessment_diff["base"], "target": assessment_diff["target"], "requested": [base_assessment_id, target_assessment_id]}
        parameter_hash = hashlib.sha256(canonical({"algorithm": ALGORITHM, "base": bref, "target": tref, "selection": selected})).hexdigest()
        view_id = "diff_" + parameter_hash[:32]
        resources = []
        for left, right in pairs:
            changes = _changes(base_rows[left], target_rows[right])
            if changes:
                evidence = _evidence(base_evidence, base_rows[left]["evidence_ids"]) + _evidence(target_evidence, target_rows[right]["evidence_ids"])
                resources.append(dict(kind="changed", before=base_rows[left]["ref"], after=target_rows[right]["ref"], field_changes=changes,
                                      evidence_refs=sorted({(x['scan_id'], x['evidence_id']): x for x in evidence}.values(), key=lambda x: (x['scan_id'], x['evidence_id'])), removal_confirmed=None))
        for row in remaining_base:
            removal = True if base.status is ScanStatus.COMPLETED and target.status is ScanStatus.COMPLETED and not base.errors and not target.errors and row["ref"]["resource_identity_key"] else None
            identity_key = row["ref"]["resource_identity_key"]
            if not identity_key:
                kind = "unmatched"
            elif remaining_identity_counts[1][identity_key]:
                kind = "ambiguous"
            else:
                kind = "not_observed_in_target"
            resources.append(dict(kind=kind, before=row["ref"], after=None, field_changes=[], evidence_refs=_evidence(base_evidence, row["evidence_ids"]), removal_confirmed=removal if kind == "not_observed_in_target" else None))
        for row in remaining_target:
            identity_key = row["ref"]["resource_identity_key"]
            if not identity_key:
                kind = "unmatched"
            elif remaining_identity_counts[0][identity_key]:
                kind = "ambiguous"
            else:
                kind = "added"
            resources.append(dict(kind=kind, before=None, after=row["ref"], field_changes=[], evidence_refs=_evidence(target_evidence, row["evidence_ids"]), removal_confirmed=None))
        resources.sort(key=lambda x: (x["kind"], (x["before"] or x["after"])["resource_kind"], (x["before"] or x["after"])["resource_id"]))
        def verification(run, keys, index, license_rows):
            result = []
            for item in run.evidence:
                key = "evidence:" + _token([item.kind.value, item.locator, item.content_hash.model_dump(mode="json") if item.content_hash else None])
                result.append((key, item.id, {"verification_status": item.verification_status}, [item.id], index))
            result += [(keys[item.id], item.id, {"authorization_status": item.authorization_status}, item.evidence_ids, index) for item in run.ai_assets]
            result += license_rows
            return result
        def findings(run, keys, index):
            return [(_token([x.resource_kind, keys[x.resource_id], x.rule_id]), x.id,
                     {"severity": x.severity, "outcome": x.outcome, "rule_id": x.rule_id, "rule_version": x.rule_version},
                     x.evidence_ids, index) for x in run.findings]
        base_licenses = _license_rows(base, base_resource_keys, base_rows, base_evidence)
        target_licenses = _license_rows(target, target_resource_keys, target_rows, target_evidence)
        base_license_verification = _license_rows(base, base_resource_keys, base_rows, base_evidence, verification=True)
        target_license_verification = _license_rows(target, target_resource_keys, target_rows, target_evidence, verification=True)
        gaps = (["base scan partial"] if base.status is ScanStatus.PARTIAL else []) + (["target scan partial"] if target.status is ScanStatus.PARTIAL else [])
        gaps += [f"{side} scan reports coverage diagnostics" for side, run in (("base", base), ("target", target)) if run.status is ScanStatus.COMPLETED and run.errors]
        return dict(schema_version="1.0", view_id=view_id, base=bref, target=tref, project_identity_key=bid["key"], resources=resources,
                    license_observation_changes=_fact_changes(base_licenses, target_licenses, category="licenses"),
                    verification_changes=_fact_changes(verification(base, base_resource_keys, base_evidence, base_license_verification), verification(target, target_resource_keys, target_evidence, target_license_verification), category="verification"),
                    finding_changes=_fact_changes(findings(base, base_resource_keys, base_evidence), findings(target, target_resource_keys, target_evidence), category="findings"), assessment_diff=assessment_diff,
                    coverage=dict(gaps=gaps, base_complete=base.status is ScanStatus.COMPLETED, target_complete=target.status is ScanStatus.COMPLETED),
                    provenance=dict(producer={"name": "openguard-diff", "version": "1.0"}, source_refs=[bref, tref], assessment_refs=[x for x in (assessment_diff["base"], assessment_diff["target"]) if x], generated_at=utc(datetime.now(timezone.utc)), algorithm_version=ALGORITHM, parameters_hash=parameter_hash))

    def _assessment_diff(self, base_run, target_run, base_id, target_id, base_resource_keys, target_resource_keys, base_evidence, target_evidence):
        base, target = self._assessment(base_run.id, base_id), self._assessment(target_run.id, target_id)
        for assessment, run in ((base, base_run), (target, target_run)):
            if assessment is not None and (not assessment.formal or assessment.scan_id != run.id or assessment.facts_hash != facts_digest(run)):
                _fail("upstream_unavailable", 503, "评估绑定数据不完整。")
        if base is None or target is None:
            return dict(status="unavailable", base=self._assessment_ref(base) if base else None, target=self._assessment_ref(target) if target else None, reason="assessment unavailable", changes=[])
        bref, tref = self._assessment_ref(base), self._assessment_ref(target)
        if base.usage_hash != target.usage_hash:
            return dict(status="not_comparable", base=bref, target=tref, reason="usage context differs", changes=[])
        reason = "rule version differs" if base.rule_version != target.rule_version else None
        return dict(status="compared", base=bref, target=tref, reason=reason,
                    changes=_fact_changes(_assessment_rows(base, base_evidence, base_resource_keys), _assessment_rows(target, target_evidence, target_resource_keys), category="assessment"))
