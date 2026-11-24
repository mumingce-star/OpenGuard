"""Server-owned binding, deterministic candidates and synchronous atomic L2.

No transport, scanner, model, Formal engine or Report/NOTICE writer is imported.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
from datetime import datetime, timezone

from app.assessment.engine import facts_digest
from app.assessment.store import AssessmentStoreError
from app.domain.models import Component, ComponentType
from app.p2b.candidates import EXACT_VERSION, USAGE_FIELDS, evaluate_bound_candidate
from app.p2b.materials import is_exact_material_version, parse_local_material
from app.persistence.scan_registry import ScanRegistryError
from .contract import (ALGORITHM, VERSION, OPTIONS, Answer, Binding, Material, P2Error,
                       Receipt, Result, Summary, canonical, digest, strict_json)
from .material_claims_contract import MATERIAL_TEXT_LICENSES


# Public gap reasons are a closed vocabulary, never arbitrary scanner text.
_COVERAGE_ERROR_CODES = frozenset({
    'rules_stage_not_connected', 'git_scan_coverage_partial',
    'dependency_scan_failed', 'dependency_manifest_not_found',
    'python_dependency_scan_failed', 'python_dependency_scan_partial',
    'javascript_dependency_scan_failed', 'javascript_dependency_scan_partial', 'multi_ecosystem_scan_partial',
    'ai_asset_scan_incomplete', 'external_scan_incomplete', 'scan_incomplete',
    'scanner_timeout', 'scanner_failed', 'zip_ingestion_failed',
    'input_digest_mismatch', 'pipeline_stage_failed', 'report_publish_failed',
})


def _id(prefix, value):
    return prefix + digest(value)


def _is_python_root(resource, evidence):
    if (not isinstance(resource, Component) or resource.component_type is not ComponentType.APPLICATION
            or resource.ecosystem != "pypi"):
        return False
    from .material_claims import root_package_evidence_ids
    return bool(root_package_evidence_ids(resource, evidence))


def _manifest_bound_version(resource, evidence):
    if not isinstance(resource, Component) or resource.ecosystem not in {'cargo', 'maven'}:
        return None
    from .material_claims import root_package_evidence_ids
    return resource.version if root_package_evidence_ids(resource, evidence) else None


class P2Service:
    def __init__(self, registry, assessments, store, *, readonly=False, data_scope="OWNER",
                 public_source_root=None, public_source_profile_sha256=None,
                 automatic_source_root=None, automatic_source_profile_sha256=None):
        if data_scope not in {"OWNER", "TEST_ONLY"}:
            raise ValueError("invalid P2 data scope")
        self.registry, self.assessments, self.store = registry, assessments, store
        self.readonly, self.data_scope = readonly, data_scope
        self.public_source_root = public_source_root
        self.public_source_profile_sha256 = public_source_profile_sha256
        self.automatic_source_root = automatic_source_root
        self.automatic_source_profile_sha256 = automatic_source_profile_sha256

    def context(self, sid, aid):
        try:
            saved = self.registry.get(sid)
        except ScanRegistryError as exc:
            if exc.code == 'registry_invalid_argument':
                raise P2Error('p2_request_invalid', 422) from exc
            if exc.code == 'registry_not_found':
                raise P2Error("p2_scan_not_found", 404) from exc
            raise P2Error('p2_parent_storage_unavailable', 503) from exc
        try:
            assessment = self.assessments.get_by_id(aid)
        except AssessmentStoreError as exc:
            raise P2Error('p2_parent_storage_unavailable', 503) from exc
        if assessment is None:
            raise P2Error("p2_assessment_not_found", 404)
        run = saved.run
        if assessment.scan_id != sid or assessment.facts_hash != facts_digest(run):
            raise P2Error("p2_parent_binding_conflict")
        if assessment.usage_hash != digest(assessment.usage.model_dump(mode="json", exclude={"declared_at"})):
            raise P2Error("p2_parent_binding_conflict")
        resources = {r.id: r for r in [*run.components, *run.ai_assets]}
        if (set(assessment.resource_ids) != set(resources)
                or {r.resource_id for r in assessment.resource_evaluations} != set(resources)
                or len(assessment.resource_evaluations) != len(resources)):
            raise P2Error("p2_resource_closure_conflict")
        binding = Binding(scan_id=sid, assessment_id=aid, assessment_version=assessment.version,
                          registry_revision=saved.revision, project_revision=run.project.revision,
                          facts_hash=assessment.facts_hash, usage_hash=assessment.usage_hash,
                          rule_version=assessment.rule_version,
                          assessment_sha256=digest(assessment.model_dump(mode="json")))
        if len(resources) > 1000:
            raise P2Error("p2_resource_capacity", 413)
        return run, assessment, binding.model_dump(), resources

    @staticmethod
    def _evidence(run, resource):
        evidence = {e.id: e for e in run.evidence}
        license_ = next((l for l in run.licenses if l.id == resource.license_expression_id), None)
        ids = sorted(set(resource.evidence_ids + (license_.evidence_ids if license_ else [])))
        if any(e not in evidence for e in ids):
            raise P2Error("p2_evidence_not_found")
        return evidence, license_, ids

    def candidate(self, run, assessment, resource):
        evidence, license_, ids = self._evidence(run, resource)
        scope_rows = []
        for eid in resource.evidence_ids:
            e = evidence[eid]
            if e.kind.value != "metadata" or e.producer.type.value != "human" or e.verification_status.value != "verified":
                continue
            try:
                obj = strict_json(e.excerpt or "")
            except ValueError:
                continue
            if not isinstance(obj, dict) or obj.get("kind") != "openguard.scope.v1":
                continue
            if (set(obj) != {"kind", "resource_id", "version", "scope", "license_expression_id"}
                    or obj['resource_id'] != resource.id or obj['version'] != resource.version
                    or obj['license_expression_id'] != resource.license_expression_id):
                raise P2Error("p2_evidence_binding_conflict")
            if not isinstance(obj['scope'], str):
                raise P2Error("p2_evidence_binding_conflict")
            scope_rows.append((eid, obj['scope']))
        if len({s for _, s in scope_rows}) > 1:
            raise P2Error("p2_evidence_conflict", conflict_rule="object_scope_conflict")
        scope = scope_rows[0][1] if scope_rows else "unknown"
        hashes = {eid: evidence[eid].content_hash.value for eid in ids if evidence[eid].content_hash is not None}
        kind = "component" if resource.id.startswith("cmp_") else "ai_asset"
        # Historical verification is not an upstream-source/applicability receipt.
        # Keep these facts observable, but never manufacture P2B admission fields.
        reviewed_texts = [evidence[eid] for eid in ids if evidence[eid].kind.value == 'license_text'
                          and evidence[eid].verification_status.value == 'verified']
        if len({e.content_hash.value for e in reviewed_texts if e.content_hash}) > 1:
            raise P2Error('p2_evidence_conflict', conflict_rule='distinct_verified_license_materials')
        if (license_ and license_.expression in MATERIAL_TEXT_LICENSES
                and license_.normalized_ids != [license_.expression]):
            raise P2Error('p2_evidence_conflict', conflict_rule='license_normalization_conflict')
        bound = {}
        for eid in ids:
            e = evidence[eid]
            row = {"id": eid, "scan_id": run.id, "object_id": resource.id,
                   "version": resource.version, "source_sha256": hashes.get(eid),
                   "role": "observation", "verification_status": "pending"}
            if eid in {s[0] for s in scope_rows}:
                row.update(role="scope_attestation", producer="human", verification_status="verified", scope=scope)
            bound[eid] = row
        usage = {k: getattr(assessment.usage, k) for k in USAGE_FIELDS}
        gaps = ["upstream_source_attestation_missing"]
        if set(hashes) != set(ids):
            gaps.append("evidence_source_hash_missing")
        suggestions = []
        legacy_exact = bool(resource.version and EXACT_VERSION.fullmatch(resource.version))
        bound = _manifest_bound_version(resource, evidence)
        if not legacy_exact and bound is None and not (
            _is_python_root(resource, evidence) and is_exact_material_version(resource.version, allow_pep440=True)
        ):
            gaps.append("exact_version_missing")
        if scope not in {"runtime_dependency", "project_code"} or kind == "ai_asset":
            gaps.append("object_scope_unverified" if kind == "component" else "ai_asset_independent_license_required")
        # Recognition of an exact Python root version does not expand the
        # existing SemVer-only L1 candidate evaluator.
        if (legacy_exact and getattr(resource, 'ecosystem', None) not in {'cargo', 'maven', 'golang'}
                and gaps == ["upstream_source_attestation_missing"]):
            snapshot = {"scan_id": run.id, "status": run.status.value,
                        "coverage_gaps": sorted({e.code for e in run.errors}),
                        "objects": [{"id": resource.id, "scan_id": run.id, "kind": kind,
                                     "name": resource.name, "version": resource.version, "scope": scope,
                                     "evidence_ids": ids, "usage": {"version": assessment.usage_hash, "values": usage}}],
                        "evidence": bound}
            snapshot['snapshot_sha256'] = digest(snapshot)
            try:
                candidate = evaluate_bound_candidate(snapshot=snapshot, object_id=resource.id,
                                                     expected_scan_id=run.id, expected_usage_version=assessment.usage_hash)
            except ValueError as exc:
                raise P2Error("p2_candidate_binding_rejected") from exc
            if any("conflict" in g for g in candidate['gaps']):
                raise P2Error("p2_evidence_conflict", conflict_rule="candidate_evidence_conflict")
            gaps.extend(candidate['gaps'])
            suggestions = candidate['suggestions']
        else:
            gaps.append("license_text_and_applicability_unverified")
        # Source/version/scope admission and scan coverage are independent.
        # Even when admission cannot call P2B, keep the parent's incompleteness
        # on every affected resource/advice; do not reclassify Formal or state.
        if run.status.value != 'completed' or run.errors:
            gaps.append('scan_coverage_incomplete')
        for error in run.errors:
            gaps.append('scan_error_' + error.code if error.code in _COVERAGE_ERROR_CODES
                        else 'scan_error_unclassified')
        return scope, ids, hashes, sorted(set(gaps)), suggestions

    def resource_result(self, run, assessment, resource, answers, materials):
        scope, eids, hashes, gaps, suggestions = self.candidate(run, assessment, resource)
        relevant_answers = [a for a in answers if resource.id in {s['resource_id'] for s in a['subjects']}]
        relevant_materials = [m for m in materials if m['subject']['resource_id'] == resource.id]
        assertions = {a['question_code']: a['answer_code'] for a in relevant_answers}
        if relevant_materials:
            gaps.append("uploaded_material_applicability_pending")
            if any(m['completeness'] == 'EXCERPT' for m in relevant_materials):
                gaps.append("uploaded_material_incomplete")
        if relevant_answers:
            gaps.append("user_statement_not_independently_verified")
        advice = []
        by_use = {s['usage']: s for s in suggestions}
        for key in USAGE_FIELDS:
            value = getattr(assessment.usage, key)
            suggestion = by_use.get(key)
            advice.append({"usage": key, "saved_value": value,
                           "selection": "UNKNOWN" if value is None else "SELECTED" if value else "NOT_SELECTED",
                           "state": "conditional_candidate" if suggestion else "not_selected" if value is False else "unknown",
                           "conditions": suggestion['conditions'] if suggestion else [],
                           "gaps": sorted(set(gaps + ([f"usage_{key}_unknown"] if value is None else []))),
                           "basis_evidence_ids": suggestion['basis_evidence_ids'] if suggestion else [],
                           "rule_ids": [suggestion['rule_id']] if suggestion else []})
        parent_row = next(r for r in assessment.resource_evaluations if r.resource_id == resource.id)
        state = "partial" if suggestions and gaps else "candidate" if suggestions else "pending" if relevant_materials else "unknown"
        return {"subject": {"resource_id": resource.id, "version": resource.version}, "resource_kind": "component" if resource.id.startswith('cmp_') else "ai_asset",
                "state": state, "scope": scope, "evidence_ids": eids, "evidence_source_hashes": hashes,
                "material_ids": [m['material_id'] for m in relevant_materials], "answer_ids": [a['answer_id'] for a in relevant_answers],
                "gaps": sorted(set(gaps)), "advice": advice, "user_assertions": assertions,
                "inherited_local_support": parent_row.supported_permission}

    def _subject(self, subject, resources, evidence_ids, run):
        resource = resources.get(subject.resource_id)
        if resource is None:
            raise P2Error("p2_resource_not_found", 404)
        if subject.version != resource.version:
            raise P2Error("p2_resource_version_conflict")
        _, _, allowed = self._evidence(run, resource)
        if not set(evidence_ids) <= set(allowed):
            raise P2Error("p2_evidence_wrong_resource")
        return resource

    def _read_result(self, db, sid, aid, identity, version):
        value = self.store.get(db, "result", identity, sid, aid)
        result = Result.model_validate(value)
        if result.binding.assessment_version != version:
            raise P2Error("p2_assessment_version_conflict")
        content = result.model_dump(mode="json")
        expected = content.pop('result_sha256')
        if digest(content) != expected or result.data_scope != self.data_scope:
            raise P2Error("p2_integrity_error", 503)
        return result.model_dump(mode="json")

    def read(self, sid, aid, identity, version):
        with self.store.connection() as db:
            return self._read_result(db, sid, aid, identity, version)

    def preliminary_advice(self, sid, aid, identity, version):
        from .preliminary import project
        with self.store.connection() as db:
            result = self._read_result(db, sid, aid, identity, version)
            run, _, binding, resources = self.context(sid, aid)
            if binding != result['binding']:
                raise P2Error('p2_parent_binding_conflict')
            materials = []
            for mid in result['material_ids']:
                material = Material.model_validate(self.store.get(db, 'material', mid, sid, aid)).model_dump(mode='json')
                row = next((r for r in result['resources'] if r['subject'] == material['subject']), None)
                if (material['binding'] != binding or material['data_scope'] != result['data_scope']
                        or row is None or mid not in row['material_ids']
                        or not set(material['evidence_ids']) <= set(row['evidence_ids'])):
                    raise P2Error('p2_integrity_error', 503)
                materials.append((material, self.store.material_bytes(db, material)))
            licenses = {l.id: l for l in run.licenses}
            declared = {}
            for rid, resource in resources.items():
                license_ = licenses.get(resource.license_expression_id)
                if license_ is None or (license_.expression in {'NOASSERTION', 'NONE'} and not license_.normalized_ids):
                    declared[rid] = 'UNOBSERVED'
                elif license_.expression == 'MIT' and license_.normalized_ids == ['MIT']:
                    declared[rid] = 'MIT'
                else:
                    declared[rid] = 'CONFLICT_OR_UNSUPPORTED'
                # Do not let the new view bypass existing conflicting-Evidence gates.
                # Resolve this resource's closure once, not once per Evidence.
                # Preserve the empty-evidence branch of the original comprehension.
                bound_ids = set(self._evidence(run, resource)[2]) if run.evidence else set()
                texts = [e for e in run.evidence if e.id in bound_ids
                         and e.kind.value == 'license_text' and e.verification_status.value == 'verified']
                if len({e.content_hash.value for e in texts if e.content_hash}) > 1:
                    raise P2Error('p2_evidence_conflict', conflict_rule='distinct_verified_license_materials')
            return project(result, resources, materials, self.public_source_root, self.public_source_profile_sha256, declared)

    def material_claims(self, sid, aid, identity, version):
        from .material_claims import evidence_context, project
        with self.store.connection() as db:
            result = self._read_result(db, sid, aid, identity, version)
            run, _, binding, resources = self.context(sid, aid)
            if binding != result['binding']:
                raise P2Error('p2_parent_binding_conflict')
            current_subjects = {row['subject']['resource_id']: row['subject']['version'] for row in result['resources']}
            if current_subjects != {rid: resource.version for rid, resource in resources.items()}:
                raise P2Error('p2_claim_integrity_error', 503)
            checked_materials = {}

            def materials_for(saved):
                rows = {row['subject']['resource_id']: row for row in saved['resources']}
                materials = []
                for mid in saved['material_ids']:
                    if mid not in checked_materials:
                        record = self.store.get(db, 'material', mid, sid, aid)
                        material = Material.model_validate(record).model_dump(mode='json')
                        checked_materials[mid] = (material, self.store.material_bytes(db, material))
                    material, raw = checked_materials[mid]
                    row = rows.get(material['subject']['resource_id'])
                    if (material['binding'] != binding or material['data_scope'] != saved['data_scope']
                            or row is None or material['subject'] != row['subject'] or mid not in row['material_ids']
                            or not set(material['evidence_ids']) <= set(row['evidence_ids'])):
                        raise P2Error('p2_integrity_error', 503)
                    materials.append((material, raw))
                return materials

            materials = materials_for(result)
            licenses = {l.id: l for l in run.licenses}
            declared = {}
            for rid, resource in resources.items():
                license_ = licenses.get(resource.license_expression_id)
                if license_ is None or (license_.expression in {'NOASSERTION', 'NONE'} and not license_.normalized_ids):
                    declared[rid] = 'UNOBSERVED'
                elif license_.expression in MATERIAL_TEXT_LICENSES:
                    declared[rid] = (license_.expression if license_.normalized_ids == [license_.expression]
                                     else 'CONFLICT_OR_UNSUPPORTED')
                else:
                    declared[rid] = license_.expression
                # Do not let the new view bypass existing conflicting-Evidence gates.
                bound_ids = set(self._evidence(run, resource)[2]) if run.evidence else set()
                texts = [e for e in run.evidence if e.id in bound_ids
                         and e.kind.value == 'license_text' and e.verification_status.value == 'verified']
                if len({e.content_hash.value for e in texts if e.content_hash}) > 1:
                    raise P2Error('p2_evidence_conflict', conflict_rule='distinct_verified_license_materials')
            declarations, roles = evidence_context(run, resources, result)
            previous = None
            prior_materials, prior_declarations, prior_roles = [], {}, {}
            if result['revision'] > 1:
                previous_id = result['previous_result_id']
                if not previous_id:
                    raise P2Error('p2_claim_integrity_error', 503)
                try:
                    previous = self._read_result(db, sid, aid, previous_id, version)
                except P2Error as exc:
                    raise P2Error('p2_claim_integrity_error', 503) from exc
                if (previous['binding'] != binding or previous['revision'] != result['revision'] - 1
                        or {r['subject']['resource_id'] for r in previous['resources']} != set(resources)):
                    raise P2Error('p2_claim_integrity_error', 503)
                try:
                    prior_materials = materials_for(previous)
                    for answer_id in set(result['answer_ids']) - set(previous['answer_ids']):
                        answer = Answer.model_validate(self.store.get(db, 'answer', answer_id, sid, aid)).model_dump(mode='json')
                        rows = [row for row in result['resources'] if answer_id in row['answer_ids']]
                        attached = {row['subject']['resource_id']: row['subject'] for row in rows}
                        answered = {subject['resource_id']: subject for subject in answer['subjects']}
                        if (answer['binding'] != binding or answer['data_scope'] != result['data_scope']
                                or answer['revision'] != result['revision'] or not rows
                                or len(answered) != len(answer['subjects']) or attached != answered
                                or any(row['user_assertions'].get(answer['question_code']) != answer['answer_code'] for row in rows)):
                            raise P2Error('p2_claim_integrity_error', 503)
                except (P2Error, ValueError) as exc:
                    raise P2Error('p2_claim_integrity_error', 503) from exc
                prior_declarations, prior_roles = evidence_context(run, resources, previous)
            return project(result, resources, materials, self.public_source_root, self.public_source_profile_sha256, declared,
                           declaration_facts=declarations, role_facts=roles, previous_result=previous,
                           previous_materials=prior_materials, previous_declaration_facts=prior_declarations,
                           previous_role_facts=prior_roles)

    def automatic_review(self, sid, aid, identity, version):
        """Read pinned release materials without fetching or changing any saved result."""
        from .automatic_review import project
        with self.store.connection() as db:
            result = self._read_result(db, sid, aid, identity, version)
            run, _, binding, resources = self.context(sid, aid)
            if binding != result['binding']:
                raise P2Error('p2_parent_binding_conflict')
            materials = []
            for mid in result['material_ids']:
                material = Material.model_validate(self.store.get(db, 'material', mid, sid, aid)).model_dump(mode='json')
                row = next((r for r in result['resources'] if r['subject'] == material['subject']), None)
                if (material['binding'] != binding or material['data_scope'] != result['data_scope']
                        or row is None or mid not in row['material_ids']
                        or not set(material['evidence_ids']) <= set(row['evidence_ids'])):
                    raise P2Error('p2_integrity_error', 503)
                materials.append((material, self.store.material_bytes(db, material)))
            declared = {}
            for rid, resource in resources.items():
                _, license_, ids = self._evidence(run, resource)
                if license_ is None or (license_.expression in {'NOASSERTION', 'NONE'} and not license_.normalized_ids):
                    declared[rid] = 'UNOBSERVED'
                elif license_.expression in {'MIT', 'ISC'} and license_.normalized_ids == [license_.expression]:
                    declared[rid] = license_.expression
                else:
                    declared[rid] = 'CONFLICT_OR_UNSUPPORTED'
                texts = [e for e in run.evidence if e.id in ids and e.kind.value == 'license_text'
                         and e.verification_status.value == 'verified']
                if len({e.content_hash.value for e in texts if e.content_hash}) > 1:
                    raise P2Error('p2_evidence_conflict', conflict_rule='distinct_verified_license_materials')
            return project(result, resources, root=self.automatic_source_root,
                           profile_sha256=self.automatic_source_profile_sha256,
                           materials=materials, declared_licenses=declared)

    def index(self, sid, aid, version, offset=0):
        with self.store.connection() as db:
            head = self.store.head(db, sid, aid)
            if head:
                self._read_result(db, sid, aid, head[0], version)
            elif self.context(sid, aid)[2]['assessment_version'] != version:
                raise P2Error('p2_assessment_version_conflict')
            rows = db.execute("SELECT id FROM p2_objects WHERE kind='result' AND scan_id=? AND assessment_id=? ORDER BY rowid DESC LIMIT 21 OFFSET ?", (sid, aid, offset)).fetchall()
            return {"head_result_id": head[0] if head else None, "head_revision": head[1] if head else 0,
                    "result_ids": [r[0] for r in rows[:20]], "has_more": len(rows) > 20}

    def record(self, sid, aid, kind, identity, version):
        with self.store.connection() as db:
            value = self.store.get(db, kind, identity, sid, aid)
            value = {'answer': Answer, 'material': Material}[kind].model_validate(value).model_dump(mode='json')
            if value['binding']['assessment_version'] != version or value.get('data_scope', self.data_scope) != self.data_scope:
                raise P2Error("p2_binding_conflict")
            if kind == 'material':
                self.store.material_bytes(db, value)
            return value

    def summary(self, sid, aid, result_id, version):
        with self.store.connection() as db:
            result = self._read_result(db, sid, aid, result_id, version)
            summary = Summary.model_validate(self.store.get(db, 'summary', result['companion_summary_id'], sid, aid)).model_dump(mode='json')
            if (summary['result_sha256'] != result['result_sha256'] or summary['binding'] != result['binding']
                    or summary['material_ids'] != result['material_ids'] or summary['result_id'] != result_id
                    or summary['answer_ids'] != result['answer_ids'] or summary['result_revision'] != result['revision']
                    or summary['state'] != result['state']):
                raise P2Error('p2_integrity_error', 503)
            return summary

    def write(self, sid, aid, body, operation):
        if self.readonly:
            raise P2Error("p2_read_only", 503)
        request_data = body.model_dump(mode='json')
        fingerprint = digest([VERSION, ALGORITHM, self.data_scope, operation, request_data])
        with self.store.connection(write=True) as db:
            replay = self.store.replay(db, sid, aid, body.idempotency_key, fingerprint)
            if replay is not None:
                receipt = Receipt.model_validate(replay).model_dump(mode='json')
                saved = self._read_result(db, sid, aid, receipt['result']['result_id'], body.binding.assessment_version)
                if receipt['result'] != saved or saved['binding'] != body.binding.model_dump():
                    raise P2Error('p2_integrity_error', 503)
                for kind in ('answer', 'material'):
                    item = receipt[kind]
                    if item is not None:
                        if (item != self.store.get(db, kind, item[kind + '_id'], sid, aid)
                                or item[kind + '_id'] not in saved[kind + '_ids']):
                            raise P2Error('p2_integrity_error', 503)
                        if kind == 'material':
                            self.store.material_bytes(db, item)
                return receipt
            run, assessment, binding, resources = self.context(sid, aid)
            if body.binding.model_dump() != binding:
                raise P2Error("p2_parent_binding_conflict")
            head = self.store.head(db, sid, aid)
            current_id, revision = head if head else (None, 0)
            if (body.expected_revision, body.parent_result_id) != (revision, current_id):
                raise P2Error("p2_revision_conflict", current_result_id=current_id, current_revision=revision)
            if operation != 'create' and head is None:
                raise P2Error("p2_initial_result_required")
            if operation == 'create' and head:
                # New request keys cannot create duplicate initial versions.
                old = self._read_result(db, sid, aid, current_id, assessment.version)
                receipt = Receipt(result=old).model_dump(mode='json')
                self.store.request(db, sid, aid, body.idempotency_key, fingerprint, receipt)
                return receipt
            previous = self._read_result(db, sid, aid, current_id, assessment.version) if head else None
            answers = [self.store.get(db, 'answer', i, sid, aid) for i in previous['answer_ids']] if previous else []
            materials = [self.store.get(db, 'material', i, sid, aid) for i in previous['material_ids']] if previous else []
            for m in materials:
                self.store.material_bytes(db, m)
            answer = material = None
            affected = set(resources) if previous is None else set()
            if operation == 'answer':
                question = next((q for q in previous['questions'] if q['question_id'] == body.question_id and q['question_code'] == body.question_code), None)
                if question is None:
                    raise P2Error('p2_question_binding_conflict')
                allowed = {s['resource_id'] for s in question['subjects']}
                for subject in body.subjects:
                    self._subject(subject, resources, [], run)
                    if subject.resource_id not in allowed:
                        raise P2Error('p2_question_resource_conflict')
                closure = set().union(*(set(self._evidence(run, resources[s.resource_id])[2]) for s in body.subjects))
                if not set(body.evidence_ids) <= closure:
                    raise P2Error('p2_evidence_wrong_resource')
                affected = {s.resource_id for s in body.subjects}
                content = {"binding": binding, "question_id": body.question_id, "question_code": body.question_code,
                           "answer_code": body.answer_code, "subjects": sorted([s.model_dump() for s in body.subjects], key=lambda s: s['resource_id']),
                           "evidence_ids": sorted(body.evidence_ids), "data_scope": self.data_scope}
                latest = {s['resource_id']: a for a in answers if a['question_code'] == body.question_code for s in a['subjects']}
                if all(s in latest and all(latest[s][k] == v for k, v in content.items()) for s in affected):
                    receipt = Receipt(result=previous, answer=latest[next(iter(affected))]).model_dump(mode='json')
                    self.store.request(db, sid, aid, body.idempotency_key, fingerprint, receipt)
                    return receipt
                answer = Answer(**content, answer_id=_id('p2ans_', [content, revision + 1]), revision=revision + 1).model_dump(mode='json')
                answers.append(answer)
            elif operation == 'material':
                resource = self._subject(body.subject, resources, body.evidence_ids, run)
                try:
                    raw = base64.b64decode(body.content_base64, validate=True)
                except (binascii.Error, ValueError) as exc:
                    raise P2Error('p2_material_base64_invalid', 422) from exc
                history = {(sid, m['subject']['resource_id'], m['subject']['version'], m['filename'].upper()): m['source_sha256'] for m in materials}
                try:
                    evidence = {entry.id: entry for entry in run.evidence}
                    parse_local_material(raw, {"scan_id": sid, "object_id": resource.id, "version": resource.version,
                                               "filename": body.filename, "sha256": body.source_sha256, "source": body.source_description},
                                         known_objects={(sid, resource.id): resource.version}, known_materials=history,
                                         allow_pep440=_is_python_root(resource, evidence),
                                         manifest_bound_version=_manifest_bound_version(resource, evidence))
                except ValueError as exc:
                    code = str(exc)
                    raise P2Error('p2_' + code, 413 if code == 'material_size_limit' else 409 if code in {'duplicate_material', 'material_identity_conflict'} else 422) from exc
                if len(materials) >= 20:
                    raise P2Error('p2_material_count_limit', 413)
                material = Material(material_id=_id('p2mat_', [binding, body.subject.model_dump(), body.filename.upper(), body.source_sha256]),
                                    binding=binding, subject=body.subject, evidence_ids=sorted(body.evidence_ids), filename=body.filename.upper(),
                                    source_sha256=body.source_sha256, byte_count=len(raw), completeness=body.completeness, data_scope=self.data_scope).model_dump(mode='json')
                materials.append(material)
                affected = {resource.id}
                db.execute('INSERT INTO p2_material_content VALUES(?,?,?)', (material['material_id'], raw, body.source_sha256))
            rows = []
            old_rows = {r['subject']['resource_id']: r for r in previous['resources']} if previous else {}
            for resource in sorted(resources.values(), key=lambda r: r.id):
                rows.append(self.resource_result(run, assessment, resource, answers, materials) if resource.id in affected else old_rows[resource.id])
            states = {row['state'] for row in rows}
            state = next(iter(states)) if len(states) == 1 else 'partial' if states else 'unknown'
            subjects = [{"resource_id": r.id, "version": r.version} for r in sorted(resources.values(), key=lambda r: r.id)]
            questions = [{"question_id": _id('p2q_', [binding, code]), "question_code": code, "subjects": subjects, "options": options} for code, options in OPTIONS.items()]
            identity = _id('p2res_', [VERSION, ALGORITHM, binding, self.data_scope, revision + 1, current_id, rows,
                                    [a['answer_id'] for a in answers], [m['material_id'] for m in materials]])
            payload = Result(result_id=identity, revision=revision + 1, previous_result_id=current_id, result_sha256='0' * 64,
                             binding=binding, data_scope=self.data_scope, state=state, created_at=datetime.now(timezone.utc).isoformat(),
                             usage={k: getattr(assessment.usage, k) for k in USAGE_FIELDS}, resources=rows, questions=questions,
                             answer_ids=[a['answer_id'] for a in answers], material_ids=[m['material_id'] for m in materials],
                             recomputed_resource_ids=sorted(affected), reused_resource_ids=sorted(set(resources) - affected),
                             companion_summary_id=_id('p2sum_', identity)).model_dump(mode='json')
            unsigned = {k: v for k, v in payload.items() if k != 'result_sha256'}
            payload['result_sha256'] = digest(unsigned)
            # Recheck original bindings after calculation, before publication.
            if self.context(sid, aid)[2] != binding:
                raise P2Error('p2_parent_binding_conflict')
            summary = Summary(summary_id=payload['companion_summary_id'], result_id=identity, result_revision=revision + 1,
                              result_sha256=payload['result_sha256'], binding=binding, material_ids=payload['material_ids'],
                              answer_ids=payload['answer_ids'], state=state,
                              resource_states={r['subject']['resource_id']: r['state'] for r in rows}).model_dump(mode='json')
            if answer:
                self.store.put(db, 'answer', answer['answer_id'], binding, answer)
            if material:
                self.store.put(db, 'material', material['material_id'], binding, material)
            self.store.put(db, 'result', identity, binding, payload)
            self.store.put(db, 'summary', summary['summary_id'], binding, summary)
            db.execute('INSERT INTO p2_heads VALUES(?,?,?,?) ON CONFLICT(scan_id,assessment_id) DO UPDATE SET result_id=excluded.result_id,revision=excluded.revision', (sid, aid, identity, revision + 1))
            receipt = Receipt(result=payload, answer=answer, material=material).model_dump(mode='json')
            self.store.request(db, sid, aid, body.idempotency_key, fingerprint, receipt)
            return receipt
