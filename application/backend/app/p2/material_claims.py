"""Exact-result material claims and the verified delta from a saved predecessor."""
from __future__ import annotations
import hashlib
from urllib.parse import quote
from app.p2b._resource_roles import assess_resource_roles
from app.p2b.candidates import EXACT_VERSION
from app.p2b.material_claims import parse_claim_material
from .contract import P2Error, digest, strict_json
from .material_claims_contract import MaterialClaims, RULE_VERSION, SCHEMA_VERSION
from .preliminary import load_sources, _project_sources, CONDITIONS, LIMITATIONS

USES = ('commercial', 'distributed', 'modified')
APACHE = 'Apache-2.0'
APACHE_MATCH = 'MATCHED_APACHE_2_0'
LICENSE_MATCHES = {'MIT': 'MATCHED_MIT', APACHE: APACHE_MATCH}
ROLE_CONFLICTS = frozenset({
    'dependency_declaration_conflict', 'lock_version_conflict', 'lock_root_mismatch',
    'contradictory_role_evidence',
})
NOTICE_MATCHED = 'NOTICE_MATCHED_REQUIRES_HUMAN_OBLIGATION_REVIEW'
NOTICE_REVIEW = '按 Apache-2.0 §4(d) 人工核对 NOTICE 的归属声明、适用范围及实际交付中的呈现方式。'
APACHE_CONDITIONS = (
    '再分发时按 Apache-2.0 §4(a) 随附一份完整许可副本。',
    '分发衍生作品源码时按 Apache-2.0 §4(c) 保留相关原有版权、专利、商标及归属声明。',
)
APACHE_MODIFIED = '再分发时按 Apache-2.0 §4(b) 在修改文件上保留显著的变更说明。'
LIMITS = LIMITATIONS + [
    '资源角色仅可由明确扫描来源推断，不证明安装、交付或许可证适用性已签认。',
    '相同许可字节可能出现在不同版本；MIT正文不能证明资源版本。',
    'NOTICE仅观察，不解释其法律效力；用户义务声明不自动证明具体条款已被违反。',
]


def _unknown_role():
    return {'role': 'unknown', 'state': 'unknown', 'evidence_ids': []}


def _dependency_role(resource, refs, diagnostics):
    """Use only the declaration finding over the resource's saved evidence closure."""
    token = resource.name.replace('~', '~0').replace('/', '~1')
    manifest_fields = {f'/{field}/{token}' for field in (
        'dependencies', 'devDependencies', 'optionalDependencies', 'peerDependencies',
    )}
    lock_token = ('node_modules/' + resource.name).replace('~', '~0').replace('/', '~1')
    lock_field = f'/packages/{lock_token}/version'

    def dependency_ref(entry):
        if entry.detected_by.value == 'syft':
            return entry.producer.type.value == 'tool'
        if entry.detected_by.value != 'manifest_parser' or entry.producer.type.value != 'parser':
            return False
        producer = entry.producer.name
        if producer == 'openguard.javascript-manifest' and entry.kind.value == 'manifest_field':
            path, _, field = entry.locator.partition(':')
            if path.rsplit('/', 1)[-1] == 'package-lock.json':
                return field in {lock_field, f'/packages/{lock_token}/resolved'}
            return path.rsplit('/', 1)[-1] == 'package.json' and field in manifest_fields
        return ((producer == 'openguard-python-manifest-parser' and entry.kind.value == 'manifest_field')
                or (producer in {'openguard.dependency-observations.lock', 'openguard.dependency-observations.sbom'}
                    and entry.kind.value in {'manifest_field', 'file'}))

    refs = tuple(entry for entry in refs if dependency_ref(entry))
    if not refs:
        return _unknown_role()
    component = resource.model_copy(update={'evidence_ids': [e.id for e in refs]})
    (observed,) = assess_resource_roles((component,), refs)
    declared = next(finding for finding in observed.roles if finding.role == 'declared')
    conflicts = {item.code for item in declared.conflicts}
    by_id = {e.id: e for e in refs}
    exact, selectors = {'manifest': set(), 'lock': set()}, set()
    for ref in declared.evidence:
        entry = by_id[ref.evidence_id]
        conflicts.update(diagnostics.get(entry.id, ()))
        # Persisted manifest fields can directly prove version disagreement.
        # Generic scan-partial errors cannot identify a conflicting resource.
        if (ref.source not in exact or entry.kind.value != 'manifest_field'
                or entry.producer.name != 'openguard.javascript-manifest'):
            continue
        if ref.source == 'lock' and entry.locator.partition(':')[2] != lock_field:
            continue
        try:
            value = strict_json(entry.excerpt or '')
        except ValueError:
            continue
        if isinstance(value, str):
            if ref.source == 'manifest':
                selectors.add(value)
            if EXACT_VERSION.fullmatch(value):
                exact[ref.source].add(value)
    if len(selectors) > 1:
        conflicts.add('dependency_declaration_conflict')
    if len(exact['lock']) > 1 or (exact['lock'] and len(exact['manifest'] | exact['lock']) > 1):
        conflicts.add('lock_version_conflict')
    if conflicts:
        return {**_unknown_role(), 'conflicts': sorted(conflicts)}
    if declared.status == 'unknown':
        return _unknown_role()
    return {'role': 'dependency', 'state': declared.status,
            'evidence_ids': sorted({e.evidence_id for e in declared.evidence if e.present})}


def evidence_context(run, resources, result):
    """Extract declaration provenance and narrowly supported role inference.

    LicenseExpression.evidence_ids is the declared provenance edge, never the
    union returned by service._evidence. Missing/hashless edges remain UNKNOWN.
    """
    evidence = {e.id: e for e in run.evidence}
    licenses = {l.id: l for l in run.licenses}
    diagnostics = {}
    for error in run.errors:
        if error.code in ROLE_CONFLICTS:
            for eid in error.evidence_ids:
                diagnostics.setdefault(eid, set()).add(error.code)
    declarations, roles = {}, {}
    for row in result['resources']:
        rid = row['subject']['resource_id']; resource = resources[rid]
        row_ids = set(row['evidence_ids'])
        def valid(eid):
            e = evidence.get(eid)
            return (e is not None and eid in row_ids and e.content_hash is not None
                    and e.content_hash.algorithm == 'sha256'
                    and row['evidence_source_hashes'].get(eid) == e.content_hash.value)
        license_ = licenses.get(resource.license_expression_id)
        if license_ is not None:
            ids = sorted(eid for eid in license_.evidence_ids if valid(eid) and eid in resource.evidence_ids)
            declarations[rid] = {'expression': license_.expression, 'normalized_ids': list(license_.normalized_ids),
                                 'evidence_ids': ids, 'complete': bool(ids) and set(ids) == set(license_.evidence_ids)}
        roles[rid] = _unknown_role()
        kind = getattr(resource.component_type, 'value', resource.component_type) if hasattr(resource, 'component_type') else None
        if kind is None:
            continue
        if kind != 'application':
            refs = tuple(evidence[eid] for eid in resource.evidence_ids if valid(eid))
            roles[rid] = _dependency_role(resource, refs, diagnostics)
            continue
        matches, hashes, bad = {}, set(), False
        for eid in resource.evidence_ids:
            e = evidence.get(eid)
            if (not valid(eid) or e.kind.value != 'manifest_field' or e.producer.type.value != 'parser'
                    or e.producer.name != 'openguard.root-package-manifest' or e.producer.version != '1'):
                continue
            field = {'package.json:/name': 'name', 'package.json:/version': 'version'}.get(e.locator)
            if field is None:
                continue
            try:
                if strict_json(e.excerpt or '') != getattr(resource, field):
                    bad = True; continue
            except ValueError:
                bad = True; continue
            matches.setdefault(field, []).append(eid); hashes.add(e.content_hash.value)
        if not bad and set(matches) == {'name', 'version'} and len(hashes) == 1:
            roles[rid] = {'role': 'root_package', 'state': 'inferred',
                          'evidence_ids': sorted(eid for ids in matches.values() for eid in ids)}
    return declarations, roles


def _source_for(resource, subject, sources):
    source = sources.get((resource.name, subject['version']))
    if source is None or getattr(resource, 'ecosystem', None) != 'npm':
        return None
    version = subject['version']; name = resource.name
    if getattr(resource, 'purl', None) not in {None, f'pkg:npm/{name}@{version}', f'pkg:npm/{quote(name, safe="/")}@{version}'}:
        return None
    if getattr(resource, 'source_url', None) not in {None, source['record'].tarball_url}:
        return None
    return source


def project_core(result, resources, materials, source_root, source_sha, declared_licenses,
                 *, declaration_facts=None, role_facts=None, source_snapshot=None):
    """Project one immutable result from a single checked source snapshot."""
    declarations, roles = declaration_facts or {}, role_facts or {}
    rows = {r['subject']['resource_id']: r for r in result['resources']}
    mids = [m['material_id'] for m, _ in materials]
    if (len(rows) != len(result['resources']) or len(set(mids)) != len(mids)
            or len(materials) != len(result['material_ids']) or set(mids) != set(result['material_ids'])):
        raise P2Error('p2_claim_integrity_error', 503)
    for m, raw in materials:
        row = rows.get(m['subject']['resource_id'])
        if (row is None or m['subject'] != row['subject'] or m['binding'] != result['binding']
                or m['data_scope'] != result['data_scope'] or m['material_id'] not in row['material_ids']
                or not m['evidence_ids'] or not set(m['evidence_ids']) <= set(row['evidence_ids'])
                or len(raw) != m['byte_count'] or hashlib.sha256(raw).hexdigest() != m['source_sha256']):
            raise P2Error('p2_claim_integrity_error', 503)
    if source_snapshot is None:
        source_snapshot = load_sources(source_root, source_sha, result['data_scope'],
                                       inspect_notices=True, allowed_licenses=('MIT', APACHE))
    sources, profile_sha = source_snapshot
    # One validated source snapshot supplies both old ceiling and new NOTICE gate.
    safe_declared = dict(declared_licenses)
    for rid, d in declarations.items():
        if d['expression'] == 'MIT' and d['normalized_ids'] != ['MIT']:
            safe_declared[rid] = 'CONFLICT_OR_UNSUPPORTED'
    preliminary = _project_sources(result, resources, materials, safe_declared, sources, profile_sha)
    ceilings = {(u['usage'], r['subject']['resource_id']): r for u in preliminary['advice'] for r in u['resources']}
    source_views, source_by_resource, releases = [], {}, {}
    for rid, row in rows.items():
        source = _source_for(resources[rid], row['subject'], sources)
        if source is None:
            continue
        releases[rid] = source
        inv = source['notice_inventory']
        view = {'subject': row['subject'], 'source_profile_sha256': profile_sha,
                'archive_sha256': source['record'].tarball_sha256, 'notice_status': inv['status'],
                'reason': inv['reason'], 'member_count': inv['member_count'],
                'enumeration_complete': inv['enumeration_complete'], 'notices': inv['members']}
        view = {'source_observation_id': 'p4source_' + digest(view), **view}
        source_views.append(view); source_by_resource[rid] = view
    declaration_views, declaration_by_resource = [], {}
    for rid, row in rows.items():
        d = declarations.get(rid, {})
        ids = d.get('evidence_ids', [])
        if (len(ids) != len(set(ids)) or not set(ids) <= set(row['evidence_ids'])
                or not set(ids) <= set(resources[rid].evidence_ids)):
            raise P2Error('p2_claim_integrity_error', 503)
        complete = bool(d.get('complete') and ids and all(row['evidence_source_hashes'].get(e) for e in ids))
        view = {'subject': row['subject'], 'expression': d.get('expression', declared_licenses.get(rid, 'UNOBSERVED')),
                'normalized_ids': list(d.get('normalized_ids', [])), 'declaration_evidence_ids': list(ids),
                'evidence': [{'evidence_id': e, 'source_sha256': row['evidence_source_hashes'].get(e)} for e in ids],
                'evidence_status': 'COMPLETE' if complete else 'UNKNOWN'}
        declaration_views.append(view); declaration_by_resource[rid] = view
    observations, observations_by_resource, apache_matches = [], {}, set()
    for m, raw in materials:
        rid = m['subject']['resource_id']; row = rows[rid]
        parsed = parse_claim_material(raw, m['filename']); clauses = []
        for span in parsed['spans']:
            quote_bytes = raw[span['byte_start']:span['byte_end']]
            if quote_bytes.decode('utf-8') != span['quote'] or hashlib.sha256(quote_bytes).hexdigest() != span['quote_sha256']:
                raise P2Error('p2_claim_integrity_error', 503)
            clause = {'material_id': m['material_id'], 'material_sha256': m['source_sha256'], **span}
            clauses.append({'clause_id': 'p4clause_' + digest(clause), **clause})
        role = roles.get(rid, _unknown_role())
        if not set(role['evidence_ids']) <= (set(row['evidence_ids']) & set(row['evidence_source_hashes'])):
            raise P2Error('p2_claim_integrity_error', 503)
        release = releases.get(rid)
        if (parsed['parse_state'] == APACHE_MATCH and release and release['complete_apache2']
                and m['completeness'] == 'FULL_TEXT_CLAIMED' and raw == release['bytes']
                and m['source_sha256'] == release['record'].license_sha256
                and all(row['evidence_source_hashes'].get(e) for e in m['evidence_ids'])):
            apache_matches.add(m['material_id'])
        supported = (parsed['parse_state'] == 'MATCHED_MIT'
            and bool(m['evidence_ids'])
            and all(row['evidence_source_hashes'].get(e) for e in m['evidence_ids'])
            and declaration_by_resource[rid]['evidence_status'] == 'COMPLETE'
            and declaration_by_resource[rid]['expression'] == 'MIT'
            and declaration_by_resource[rid]['normalized_ids'] == ['MIT']
            and source_by_resource.get(rid, {}).get('notice_status') == 'ABSENT_COMPLETE'
            and any(m['material_id'] in ceilings.get((u, rid), {}).get('material_ids', []) for u in USES))
        observation = {'material_id': m['material_id'], 'subject': m['subject'], 'source_sha256': m['source_sha256'],
            'byte_count': m['byte_count'], 'filename': m['filename'], 'parse_state': parsed['parse_state'],
            'parse_reason': parsed['reason'], 'binding_state': 'BOUND_TO_SAVED_RESULT',
            'adoption_state': 'CONDITIONAL_TEXT_BASIS' if supported else 'OBSERVATION_ONLY',
            'declared_spdx': declarations.get(rid, {}).get('expression', declared_licenses.get(rid, 'UNOBSERVED')),
            'text_license': parsed['text_license'], 'license_version': parsed['license_version'],
            'version_scope': parsed['version_scope'],
            'role': role['role'], 'role_state': role['state'], 'role_basis_evidence_ids': role['evidence_ids'],
            'role_conflicts': role.get('conflicts', []),
            'source_binding': 'PINNED_RELEASE_MATCH' if supported else 'NOT_ESTABLISHED', 'source_profile_sha256': profile_sha,
            'evidence': [{'evidence_id': e, 'source_sha256': row['evidence_source_hashes'].get(e)} for e in m['evidence_ids']],
            'clauses': clauses}
        observations.append(observation)
        observations_by_resource.setdefault(rid, []).append(observation)
    claims, advice = [], []
    for rid, row in rows.items():
        obs = observations_by_resource.get(rid, [])
        licenses = [m for m in obs if m['filename'].split('.')[0].upper() in {'LICENSE', 'LICENCE'}]
        notices = [m for m in obs if m['parse_state'] == 'NOTICE_OBSERVED']
        d = declarations.get(rid, {})
        declared = d.get('expression', declared_licenses.get(rid, 'UNOBSERVED'))
        declaration_ids = d.get('evidence_ids', [])
        if not set(declaration_ids) <= set(row['evidence_ids']):
            raise P2Error('p2_claim_integrity_error', 503)
        source_view = source_by_resource.get(rid)
        source_clear = source_view is not None and source_view['notice_status'] == 'ABSENT_COMPLETE'
        counters = []
        def counter(code, ms, *, extra_ids=(), source_refs=(), provenance=True):
            ids = sorted({e['evidence_id'] for m in ms for e in m['evidence']} | set(extra_ids))
            complete = provenance and bool(ids or source_refs) and all(row['evidence_source_hashes'].get(e) for e in ids)
            counters.append({'code': code, 'material_ids': [m['material_id'] for m in ms],
                'evidence_ids': ids, 'declaration_evidence_ids': list(extra_ids), 'source_observation_ids': list(source_refs),
                'evidence_status': 'COMPLETE' if complete else 'UNKNOWN'})
        multi = any(token in declared for token in (' AND ', ' OR ', ' WITH '))
        if d.get('expression') in LICENSE_MATCHES and d.get('normalized_ids') != [d['expression']]:
            counter('SPDX_NORMALIZATION_CONFLICT', [], extra_ids=declaration_ids, provenance=d.get('complete', False))
        conflicting = [m for m in licenses if m['text_license'] in LICENSE_MATCHES and m['text_license'] != declared]
        if conflicting and not multi and declared not in {'UNOBSERVED', 'CONFLICT_OR_UNSUPPORTED'}:
            counter('SPDX_TEXT_CONFLICT', conflicting, extra_ids=declaration_ids, provenance=d.get('complete', False))
        if len({m['source_sha256'] for m in licenses}) > 1:
            counter('BOUND_LICENSE_BYTES_CONFLICT', licenses)
        if notices:
            counter('NOTICE_REQUIRES_REVIEW', notices)
        if source_view and source_view['notice_status'] != 'ABSENT_COMPLETE':
            counter('NOTICE_REQUIRES_REVIEW', [], source_refs=[source_view['source_observation_id']],
                    provenance=source_view['notice_status'] == 'PRESENT_UNREVIEWED')
        notice_matched = False
        if declared == APACHE and notices and source_view and source_view['notice_status'] == 'PRESENT_UNREVIEWED':
            member_hashes = {m['sha256'] for m in source_view['notices'] if m['inspection_state'] == 'EXTRACTED_UNREVIEWED'}
            mismatched = [m for m in notices if m['source_sha256'] not in member_hashes]
            if mismatched:
                counter('BOUND_NOTICE_BYTES_CONFLICT', mismatched, source_refs=[source_view['source_observation_id']])
            else:
                notice_matched = True
        apache_basis = (
            declared == APACHE and d.get('normalized_ids') == [APACHE]
            and declaration_by_resource[rid]['evidence_status'] == 'COMPLETE'
            and source_clear and not counters and row['resource_kind'] == 'component'
            and not any('conflict' in gap for gap in row['gaps'])
            and bool(licenses) and all(m['source_sha256'] == releases[rid]['record'].license_sha256 for m in licenses)
            and any(m['material_id'] in apache_matches for m in licenses)
        )
        apache_uses = {u for u in USES if apache_basis and result['usage'][u] is True
                       and not (u == 'distributed' and row['user_assertions'].get('DELIVERY_SCOPE_FOR_RESOURCES') == 'NO_EXCLUDE')}
        if apache_uses:
            for material in licenses:
                if material['material_id'] in apache_matches:
                    material.update(adoption_state='CONDITIONAL_TEXT_BASIS', source_binding='PINNED_RELEASE_MATCH')
        expected_text = {LICENSE_MATCHES[declared]} if declared in LICENSE_MATCHES else set(LICENSE_MATCHES.values())
        for usage in USES:
            selected = result['usage'][usage]; ceiling = ceilings.get((usage, rid))
            basis = [m for m in obs if ceiling and m['material_id'] in ceiling['material_ids']]
            mit_basis = (declaration_by_resource[rid]['evidence_status'] == 'COMPLETE'
                and declared == 'MIT' and d.get('normalized_ids') == ['MIT']) and source_clear and bool(basis) and all(m['parse_state'] == 'MATCHED_MIT' and m['evidence']
                and all(e['source_sha256'] is not None for e in m['evidence']) for m in basis)
            valid_basis = mit_basis or usage in apache_uses
            if selected is False or row['resource_kind'] != 'component':
                state = 'NOT_COVERED'; reasons = ['USE_NOT_SELECTED' if selected is False else 'RESOURCE_KIND_NOT_COVERED']
            elif selected is None:
                state = 'UNKNOWN'; reasons = ['USAGE_UNDECLARED']
            elif any(c['code'] != 'NOTICE_REQUIRES_REVIEW' for c in counters):
                state = 'COUNTER_EVIDENCE'; reasons = sorted({c['code'] for c in counters})
            elif valid_basis and row['user_assertions'].get('OBLIGATION_FULFILLMENT_IN_DELIVERY') == 'NOT_FULFILLED':
                state = 'RESTRICTION'; reasons = ['USER_REPORTS_DELIVERY_OBLIGATION_UNFULFILLED']
            elif valid_basis:
                state = 'SUPPORT'
                reasons = ['PINNED_RELEASE_AND_COMPLETE_APACHE_2_0_CONDITIONAL_TEXT' if usage in apache_uses
                           else 'PINNED_RELEASE_AND_COMPLETE_MIT_CONDITIONAL_TEXT']
            else:
                state = 'UNKNOWN'
                reasons = (['MULTI_LICENSE_NOT_SUPPORTED'] if multi else
                           [NOTICE_MATCHED] if notice_matched else
                           ['NOTICE_REQUIRES_REVIEW'] if notices or (source_view and not source_clear) else
                           ['MISSING_LICENSE_MATERIAL'] if not licenses else
                           ['UNSUPPORTED_OR_FAILED_TEXT'] if any(m['parse_state'] not in expected_text for m in licenses) else
                           ['SOURCE_OR_EVIDENCE_BINDING_NOT_ESTABLISHED'])
            if any(c['evidence_status'] == 'UNKNOWN' for c in counters):
                reasons = [*reasons, 'COUNTER_EVIDENCE_SOURCE_UNKNOWN']
            conditions = []
            if state == 'SUPPORT':
                conditions = list(APACHE_CONDITIONS if usage in apache_uses else CONDITIONS)
                if usage in apache_uses and result['usage']['modified'] is True:
                    conditions.append(APACHE_MODIFIED)
            elif state == 'RESTRICTION':
                conditions = ['用户声明交付义务尚未履行；需明确义务对象与范围，不能据此认定某一具体条款被违反']
            elif NOTICE_MATCHED in reasons:
                conditions = [NOTICE_REVIEW]
            evidence_ids = sorted({e['evidence_id'] for m in obs for e in m['evidence']} | set(declaration_by_resource[rid]['declaration_evidence_ids']) | {e for c in counters for e in c['evidence_ids']})
            link = {'usage': usage, 'subject': row['subject'], 'material_ids': [m['material_id'] for m in obs],
                'evidence': [{'evidence_id': e, 'source_sha256': row['evidence_source_hashes'].get(e)} for e in evidence_ids],
                'clause_ids': [c['clause_id'] for m in obs for c in m['clauses']],
                'conditions': conditions, 'counter_evidence': counters, 'state': state, 'formal_effect': 'none'}
            link = {'claim_id': 'p4claim_' + digest([result['result_id'], result['result_sha256'], link]), **link}
            claims.append(link)
            advice.append({'usage': usage, 'subject': row['subject'], 'saved_value': selected, 'state': state,
                'reasons': reasons, 'claim_ids': [link['claim_id']], 'conditions': conditions, 'limitations': LIMITS})
    payload = dict(schema_version=SCHEMA_VERSION, rule_version=RULE_VERSION,
        result_id=result['result_id'], result_sha256=result['result_sha256'],
        revision=result['revision'], previous_result_id=result['previous_result_id'], binding=result['binding'],
        data_scope=result['data_scope'], source_status=preliminary['source_status'], source_profile_sha256=profile_sha,
        materials=observations, declaration_observations=declaration_views, source_observations=source_views,
        claims=claims, advice=advice, formal_effect='none', applicability_review='NOT_SIGNED', model_calls=0)
    # The core fingerprint includes the saved Result hash (and thus the affected
    # partition). Derived impact links are checked separately without a recursive
    # traversal of every ancestor merely to compute the immediate prior view ID.
    payload['view_id'] = 'p4view_' + digest(payload)
    return payload


def _impact_rows(result):
    rows = {row['subject']['resource_id']: row for row in result['resources']}
    recomputed, reused = result['recomputed_resource_ids'], result['reused_resource_ids']
    assigned = recomputed + reused
    if (len(rows) != len(result['resources']) or len(assigned) != len(set(assigned))
            or set(assigned) != set(rows)):
        raise P2Error('p2_claim_integrity_error', 503)
    for key in ('material_ids', 'answer_ids'):
        items = result[key]
        referenced = [item for row in rows.values() for item in row[key]]
        if (len(items) != len(set(items)) or set(items) != set(referenced)
                or (key == 'material_ids' and len(items) != len(referenced))
                or any(len(row[key]) != len(set(row[key])) for row in rows.values())):
            raise P2Error('p2_claim_integrity_error', 503)
    return rows


def _impact(result, core, previous, prior_core):
    rows = _impact_rows(result)
    recomputed, reused = result['recomputed_resource_ids'], result['reused_resource_ids']
    affected, unchanged = set(recomputed), set(reused)
    impact = {
        'mode': 'INITIAL_RESULT' if previous is None else 'INCREMENTAL_DERIVED',
        'previous_result_id': result['previous_result_id'],
        'previous_revision': None if previous is None else previous['revision'],
        'previous_view_id': None if prior_core is None else prior_core['view_id'],
        'affected_resource_ids': recomputed,
        'unchanged_resource_ids': reused,
        'recomputed_claim_ids': [c['claim_id'] for c in core['claims'] if c['subject']['resource_id'] in affected],
        'reused_claim_ids': [c['claim_id'] for c in core['claims'] if c['subject']['resource_id'] in unchanged],
        'added_material_ids': sorted(set(result['material_ids']) - (set(previous['material_ids']) if previous else set())),
        'added_answer_ids': sorted(set(result['answer_ids']) - (set(previous['answer_ids']) if previous else set())),
        'changed_claims': [],
        'unchanged_claims_verified': True,
    }
    if previous is None:
        if (result['revision'] != 1 or result['previous_result_id'] is not None or reused
                or result['material_ids'] or result['answer_ids']):
            raise P2Error('p2_claim_integrity_error', 503)
        return impact

    prior_rows = _impact_rows(previous)
    if (not affected or set(rows) != set(prior_rows)
            or any(rows[rid]['subject'] != prior_rows[rid]['subject'] for rid in rows)
            or any(rows[rid] != prior_rows[rid] for rid in unchanged)):
        raise P2Error('p2_claim_integrity_error', 503)
    triggered = set()
    for rid in rows:
        for key in ('material_ids', 'answer_ids'):
            old_ids, new_ids = set(prior_rows[rid][key]), set(rows[rid][key])
            if not old_ids <= new_ids:
                raise P2Error('p2_claim_integrity_error', 503)
            if (new_ids - old_ids) - set(impact['added_' + key]):
                raise P2Error('p2_claim_integrity_error', 503)
            if new_ids != old_ids:
                triggered.add(rid)
    if triggered != affected:
        raise P2Error('p2_claim_integrity_error', 503)

    def by_subject_usage(items):
        return {(entry['subject']['resource_id'], entry['usage']): entry for entry in items}

    old_claims = by_subject_usage(prior_core['claims'])
    old_advice = by_subject_usage(prior_core['advice'])
    new_advice = by_subject_usage(core['advice'])
    for claim in core['claims']:
        rid = claim['subject']['resource_id']
        key = (rid, claim['usage'])
        old_claim, old, current = old_claims[key], old_advice[key], new_advice[key]
        if rid in unchanged:
            if (any(claim[k] != old_claim[k] for k in claim if k != 'claim_id')
                    or any(current[k] != old[k] for k in current if k != 'claim_ids')):
                raise P2Error('p2_claim_integrity_error', 503)
        elif (old['state'], old['reasons']) != (current['state'], current['reasons']):
            impact['changed_claims'].append({
                'usage': claim['usage'], 'subject': claim['subject'],
                'previous_claim_id': old_claim['claim_id'], 'current_claim_id': claim['claim_id'],
                'previous_state': old['state'], 'current_state': current['state'],
                'previous_reasons': old['reasons'], 'current_reasons': current['reasons'],
                'trigger_material_ids': sorted(set(impact['added_material_ids']) & set(rows[rid]['material_ids'])),
                'trigger_answer_ids': sorted(set(impact['added_answer_ids']) & set(rows[rid]['answer_ids'])),
            })
    return impact


def project(result, resources, materials, source_root, source_sha, declared_licenses,
            *, declaration_facts=None, role_facts=None, previous_result=None,
            previous_materials=(), previous_declaration_facts=None, previous_role_facts=None):
    """Read both immutable revisions against the same checked release bytes."""
    if previous_result is not None:
        if (previous_result['result_id'] != result['previous_result_id']
                or previous_result['revision'] + 1 != result['revision']
                or any(previous_result[key] != result[key] for key in ('data_scope', 'binding', 'usage'))):
            raise P2Error('p2_claim_integrity_error', 503)
        _impact_rows(previous_result)
    elif result['revision'] != 1 or result['previous_result_id'] is not None:
        raise P2Error('p2_claim_integrity_error', 503)
    source_snapshot = load_sources(source_root, source_sha, result['data_scope'],
                                   inspect_notices=True, allowed_licenses=('MIT', APACHE))
    core = project_core(result, resources, materials, source_root, source_sha, declared_licenses,
                        declaration_facts=declaration_facts, role_facts=role_facts, source_snapshot=source_snapshot)
    prior = None if previous_result is None else project_core(
        previous_result, resources, previous_materials, source_root, source_sha, declared_licenses,
        declaration_facts=previous_declaration_facts, role_facts=previous_role_facts, source_snapshot=source_snapshot)
    return MaterialClaims(**core, incremental_impact=_impact(result, core, previous_result, prior)).model_dump(mode='json')
