"""Exact-result v3 graph. Source members are not uploaded Materials or scan Evidence."""
from __future__ import annotations
import hashlib
from urllib.parse import quote
from app.p2b.material_claims import parse_claim_material
from .contract import P2Error, digest, strict_json
from .material_claims_contract import MaterialClaims
from .preliminary import load_sources, _project_sources, CONDITIONS, LIMITATIONS

USES = ('commercial', 'distributed', 'modified')
LIMITS = LIMITATIONS + [
    '资源角色仅可由明确扫描来源推断，不证明安装、交付或许可证适用性已签认。',
    '相同许可字节可能出现在不同版本；MIT正文不能证明资源版本。',
    'NOTICE仅观察，不解释其法律效力；用户义务声明不自动证明具体条款已被违反。',
]


def evidence_context(run, resources, result):
    """Extract declaration provenance and narrowly supported role inference.

    LicenseExpression.evidence_ids is the declared provenance edge, never the
    union returned by service._evidence. Missing/hashless edges remain UNKNOWN.
    """
    evidence = {e.id: e for e in run.evidence}
    licenses = {l.id: l for l in run.licenses}
    declarations, roles = {}, {}
    for row in result['resources']:
        rid = row['subject']['resource_id']; resource = resources[rid]
        def valid(eid):
            e = evidence.get(eid)
            return (e is not None and eid in row['evidence_ids'] and e.content_hash is not None
                    and e.content_hash.algorithm == 'sha256'
                    and row['evidence_source_hashes'].get(eid) == e.content_hash.value)
        license_ = licenses.get(resource.license_expression_id)
        if license_ is not None:
            ids = sorted(eid for eid in license_.evidence_ids if valid(eid) and eid in resource.evidence_ids)
            declarations[rid] = {'expression': license_.expression, 'normalized_ids': list(license_.normalized_ids),
                                 'evidence_ids': ids, 'complete': bool(ids) and set(ids) == set(license_.evidence_ids)}
        roles[rid] = {'role': 'unknown', 'state': 'unknown', 'evidence_ids': []}
        kind = getattr(resource.component_type, 'value', resource.component_type) if hasattr(resource, 'component_type') else None
        if kind != 'application':
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


def project(result, resources, materials, source_root, source_sha, declared_licenses,
            *, declaration_facts=None, role_facts=None):
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
    sources, profile_sha = load_sources(source_root, source_sha, result['data_scope'], inspect_notices=True)
    # One validated source snapshot supplies both old ceiling and new NOTICE gate.
    safe_declared = dict(declared_licenses)
    for rid, d in declarations.items():
        if d['expression'] == 'MIT' and d['normalized_ids'] != ['MIT']:
            safe_declared[rid] = 'CONFLICT_OR_UNSUPPORTED'
    preliminary = _project_sources(result, resources, materials, safe_declared, sources, profile_sha)
    ceilings = {(u['usage'], r['subject']['resource_id']): r for u in preliminary['advice'] for r in u['resources']}
    source_views, source_by_resource = [], {}
    for rid, row in rows.items():
        source = _source_for(resources[rid], row['subject'], sources)
        if source is None:
            continue
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
    observations = []
    for m, raw in materials:
        rid = m['subject']['resource_id']; row = rows[rid]
        parsed = parse_claim_material(raw, m['filename']); clauses = []
        for span in parsed['spans']:
            quote_bytes = raw[span['byte_start']:span['byte_end']]
            if quote_bytes.decode('utf-8') != span['quote'] or hashlib.sha256(quote_bytes).hexdigest() != span['quote_sha256']:
                raise P2Error('p2_claim_integrity_error', 503)
            clause = {'material_id': m['material_id'], 'material_sha256': m['source_sha256'], **span}
            clauses.append({'clause_id': 'p4clause_' + digest(clause), **clause})
        role = roles.get(rid, {'role': 'unknown', 'state': 'unknown', 'evidence_ids': []})
        if not set(role['evidence_ids']) <= set(row['evidence_ids']):
            raise P2Error('p2_claim_integrity_error', 503)
        supported = (parsed['parse_state'] == 'MATCHED_MIT'
            and bool(m['evidence_ids'])
            and all(row['evidence_source_hashes'].get(e) for e in m['evidence_ids'])
            and declaration_by_resource[rid]['evidence_status'] == 'COMPLETE'
            and declaration_by_resource[rid]['expression'] == 'MIT'
            and declaration_by_resource[rid]['normalized_ids'] == ['MIT']
            and source_by_resource.get(rid, {}).get('notice_status') == 'ABSENT_COMPLETE'
            and any(m['material_id'] in ceilings.get((u, rid), {}).get('material_ids', []) for u in USES))
        observations.append({'material_id': m['material_id'], 'subject': m['subject'], 'source_sha256': m['source_sha256'],
            'byte_count': m['byte_count'], 'filename': m['filename'], 'parse_state': parsed['parse_state'],
            'parse_reason': parsed['reason'], 'binding_state': 'BOUND_TO_SAVED_RESULT',
            'adoption_state': 'CONDITIONAL_TEXT_BASIS' if supported else 'OBSERVATION_ONLY',
            'declared_spdx': declarations.get(rid, {}).get('expression', declared_licenses.get(rid, 'UNOBSERVED')),
            'text_license': parsed['text_license'], 'license_version': None, 'version_scope': 'RESOURCE_VERSION_NOT_LICENSE_VERSION',
            'role': role['role'], 'role_state': role['state'], 'role_basis_evidence_ids': role['evidence_ids'],
            'source_binding': 'PINNED_RELEASE_MATCH' if supported else 'NOT_ESTABLISHED', 'source_profile_sha256': profile_sha,
            'evidence': [{'evidence_id': e, 'source_sha256': row['evidence_source_hashes'].get(e)} for e in m['evidence_ids']],
            'clauses': clauses})
    claims, advice = [], []
    for rid, row in rows.items():
        obs = [m for m in observations if m['subject'] == row['subject']]
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
        if d.get('expression') == 'MIT' and d.get('normalized_ids') != ['MIT']:
            counter('SPDX_NORMALIZATION_CONFLICT', [], extra_ids=declaration_ids, provenance=d.get('complete', False))
        mit_materials = [m for m in licenses if m['text_license'] == 'MIT']
        if declared not in {'MIT', 'UNOBSERVED', 'CONFLICT_OR_UNSUPPORTED'} and not multi and mit_materials:
            counter('SPDX_TEXT_CONFLICT', mit_materials, extra_ids=declaration_ids, provenance=d.get('complete', False))
        if len({m['source_sha256'] for m in licenses}) > 1:
            counter('BOUND_LICENSE_BYTES_CONFLICT', licenses)
        if notices:
            counter('NOTICE_REQUIRES_REVIEW', notices)
        if source_view and source_view['notice_status'] != 'ABSENT_COMPLETE':
            counter('NOTICE_REQUIRES_REVIEW', [], source_refs=[source_view['source_observation_id']],
                    provenance=source_view['notice_status'] == 'PRESENT_UNREVIEWED')
        for usage in USES:
            selected = result['usage'][usage]; ceiling = ceilings.get((usage, rid))
            basis = [m for m in obs if ceiling and m['material_id'] in ceiling['material_ids']]
            valid_basis = (declaration_by_resource[rid]['evidence_status'] == 'COMPLETE'
                and declared == 'MIT' and d.get('normalized_ids') == ['MIT']) and source_clear and bool(basis) and all(m['parse_state'] == 'MATCHED_MIT' and m['evidence']
                and all(e['source_sha256'] is not None for e in m['evidence']) for m in basis)
            if selected is False or row['resource_kind'] != 'component':
                state = 'NOT_COVERED'; reasons = ['USE_NOT_SELECTED' if selected is False else 'RESOURCE_KIND_NOT_COVERED']
            elif selected is None:
                state = 'UNKNOWN'; reasons = ['USAGE_UNDECLARED']
            elif any(c['code'] != 'NOTICE_REQUIRES_REVIEW' for c in counters):
                state = 'COUNTER_EVIDENCE'; reasons = sorted({c['code'] for c in counters})
            elif valid_basis and row['user_assertions'].get('OBLIGATION_FULFILLMENT_IN_DELIVERY') == 'NOT_FULFILLED':
                state = 'RESTRICTION'; reasons = ['USER_REPORTS_DELIVERY_OBLIGATION_UNFULFILLED']
            elif valid_basis:
                state = 'SUPPORT'; reasons = ['PINNED_RELEASE_AND_COMPLETE_MIT_CONDITIONAL_TEXT']
            else:
                state = 'UNKNOWN'
                reasons = (['MULTI_LICENSE_NOT_SUPPORTED'] if multi else
                           ['NOTICE_REQUIRES_REVIEW'] if notices or (source_view and not source_clear) else
                           ['MISSING_LICENSE_MATERIAL'] if not licenses else
                           ['UNSUPPORTED_OR_FAILED_TEXT'] if any(m['parse_state'] != 'MATCHED_MIT' for m in licenses) else
                           ['SOURCE_OR_EVIDENCE_BINDING_NOT_ESTABLISHED'])
            if any(c['evidence_status'] == 'UNKNOWN' for c in counters):
                reasons = [*reasons, 'COUNTER_EVIDENCE_SOURCE_UNKNOWN']
            conditions = list(CONDITIONS) if state == 'SUPPORT' else ['用户声明交付义务尚未履行；需明确义务对象与范围，不能据此认定某一具体条款被违反'] if state == 'RESTRICTION' else []
            evidence_ids = sorted({e['evidence_id'] for m in obs for e in m['evidence']} | set(declaration_by_resource[rid]['declaration_evidence_ids']) | {e for c in counters for e in c['evidence_ids']})
            link = {'usage': usage, 'subject': row['subject'], 'material_ids': [m['material_id'] for m in obs],
                'evidence': [{'evidence_id': e, 'source_sha256': row['evidence_source_hashes'].get(e)} for e in evidence_ids],
                'clause_ids': [c['clause_id'] for m in obs for c in m['clauses']],
                'conditions': conditions, 'counter_evidence': counters, 'state': state, 'formal_effect': 'none'}
            link = {'claim_id': 'p4claim_' + digest([result['result_id'], result['result_sha256'], link]), **link}
            claims.append(link)
            advice.append({'usage': usage, 'subject': row['subject'], 'saved_value': selected, 'state': state,
                'reasons': reasons, 'claim_ids': [link['claim_id']], 'conditions': conditions, 'limitations': LIMITS})
    payload = MaterialClaims(view_id='p4view_pending', result_id=result['result_id'], result_sha256=result['result_sha256'],
        revision=result['revision'], previous_result_id=result['previous_result_id'], binding=result['binding'],
        data_scope=result['data_scope'], source_status=preliminary['source_status'], source_profile_sha256=profile_sha,
        materials=observations, declaration_observations=declaration_views, source_observations=source_views, claims=claims, advice=advice).model_dump(mode='json')
    payload['view_id'] = 'p4view_' + digest({k: v for k, v in payload.items() if k != 'view_id'})
    return payload
