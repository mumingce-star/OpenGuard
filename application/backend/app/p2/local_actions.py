"""Read-only verification actions from exact saved material, never license advice.

This TASK feature does not add a rule to the formal P2 candidate evaluator.  Its
output is a deterministic projection of an immutable Result, adopted Material
and the same Scan's recorded Git observation.  GET never adopts or generates.
"""
from __future__ import annotations

import hashlib

from .contract import Material, P2Error, digest

COMMIT = '0d3b7bb5b6e8a59fd450ae2dca65870009cfcd8b'
LICENSE_SHA = 'accfc4d5a588384b29c4817392854afb8f319b4568359ca8d063df8a9bc396b6'
GIT_URL = f'https://raw.githubusercontent.com/http-party/http-server/{COMMIT}/LICENSE'
USES = ('commercial', 'modified', 'distributed', 'network_service', 'training',
        'redistributed_assets', 'source_disclosure')
CONDITION = ('The above copyright notice and this permission notice shall be\n'
             'included in all copies or substantial portions of the Software.')
LIMITATIONS = [
    '以下是基于已保存材料的核验行动，不是允许商业使用、分发或正式许可适用性的结论。',
    '材料仍为user_supplied_unverified/pending；Git根LICENSE仅对应所记录提交的源码，不覆盖其他依赖或npm发行包。',
    '用途为演示用途假设，不证明实际安装、交付、使用或义务已履行；正式来源与适用范围仍待审核。',
    '行动是固定Result的只读派生；不改写已保存Advice、Result、Summary或许可证规则。',
]


def _frozen(value):
    return {**value, 'content_sha256': digest(value)}


def build_local_actions(p2, result, row, candidate):
    """Return hash-bound actions; all inputs must refer to the same saved Result.

    The existing official-sources status calls this after its own bound-result
    checks.  Rechecking here keeps direct internal/export callers fail closed.
    Missing observations yield an explicit empty projection; conflicting input
    is rejected instead of being presented as a license restriction.
    """
    binding = result['binding']
    sid, aid, version = binding['scan_id'], binding['assessment_id'], binding['assessment_version']
    saved = p2.read(sid, aid, result['result_id'], version)
    run, assessment, current_binding, resources = p2.context(sid, aid)
    subject = row['subject']
    actual = resources.get(subject['resource_id'])
    if (saved != result or current_binding != binding or result['data_scope'] != 'TEST_ONLY'
            or row not in result['resources'] or actual is None
            or actual.name != 'http-server' or actual.version != '14.1.2'
            or subject['version'] != actual.version or run.project.revision != COMMIT
            or str(run.project.source or '').rstrip('/').removesuffix('.git') != 'https://github.com/http-party/http-server'
            or run.status.value != 'completed'
            or result['usage'] != {key: getattr(assessment.usage, key) for key in USES}):
        raise P2Error('p2_local_action_binding_conflict', 409)
    _, _, allowed = p2._evidence(run, actual)
    if not allowed or sorted(row['evidence_ids']) != sorted(allowed):
        raise P2Error('p2_local_action_evidence_conflict', 409)
    value = {
        'schema_version': 'openguard-p2-local-actions/1',
        'result_id': result['result_id'], 'result_revision': result['revision'],
        'result_sha256': result['result_sha256'], 'binding': binding,
        'subject': subject, 'usage': result['usage'],
        'usage_assumption': 'DEMO_USAGE_ASSUMPTION',
        'state': 'source_unavailable', 'source_refs': [], 'clauses': [], 'actions': [],
        'gaps': sorted(set(row['gaps'])), 'limitations': list(LIMITATIONS),
        'quote_index_unit': 'unicode_code_point', 'formal_effect': 'none', 'model_calls': 0,
        'source_admission': 'NOT_SIGNED', 'applicability': 'NOT_SIGNED',
        'obligations': 'NOT_ESTABLISHED',
    }
    if candidate is None:
        value['gaps'] = sorted(set(value['gaps'] + ['same_scan_git_source_missing']))
        return _frozen(value)
    check = dict(candidate)
    candidate_id, candidate_sha = check.pop('candidate_id', None), check.pop('candidate_sha256', None)
    text = candidate.get('license_text')
    git_sources = [s for s in candidate.get('sources', []) if s.get('kind') == 'git_license']
    if (digest(check) != candidate_sha or candidate_id != 'p2src_' + str(candidate_sha)
            or candidate.get('scan_id') != sid or candidate.get('subject') != subject
            or candidate.get('commit') != COMMIT or not isinstance(text, str)
            or len(text.encode('utf-8')) != 1124
            or hashlib.sha256(text.encode('utf-8')).hexdigest() != LICENSE_SHA
            or candidate.get('verification_state') != 'pending' or candidate.get('formal_effect') != 'none'
            or len(git_sources) != 1):
        raise P2Error('p2_local_action_source_conflict', 409)
    source = git_sources[0]
    if any(source.get(key) != expected for key, expected in {
            'url': GIT_URL, 'sha256': LICENSE_SHA, 'byte_count': 1124,
            'source_level': 'official_repository_bytes_observed', 'verification_state': 'pending',
            'name': 'http-server', 'version': '14.1.2', 'commit': COMMIT}.items()):
        raise P2Error('p2_local_action_source_conflict', 409)
    if candidate.get('npm_metadata_status') == 'missing_404':
        value['gaps'] = sorted(set(value['gaps'] + ['npm_exact_version_metadata_missing_404']))
    materials = []
    with p2.store.connection() as db:
        for mid in row['material_ids']:
            if mid not in result['material_ids']:
                raise P2Error('p2_local_action_material_conflict', 409)
            material = Material.model_validate(p2.store.get(db, 'material', mid, sid, aid)).model_dump(mode='json')
            if (material['binding'] != binding or material['subject'] != subject
                    or material['data_scope'] != 'TEST_ONLY'
                    or not set(material['evidence_ids']) <= set(row['evidence_ids'])):
                raise P2Error('p2_local_action_material_conflict', 409)
            raw = p2.store.material_bytes(db, material)
            if (material['filename'].split('.')[0] not in {'LICENSE', 'LICENCE'}
                    or material['completeness'] != 'FULL_TEXT_CLAIMED'):
                continue
            # A different bound LICENSE is a genuine unresolved conflict, not a
            # document to skip in favor of the expected sample.
            if raw != text.encode('utf-8') or material['source_sha256'] != LICENSE_SHA:
                raise P2Error('p2_local_action_material_source_conflict', 409)
            materials.append(material)
    if not materials:
        value['state'] = 'awaiting_material'
        value['gaps'] = sorted(set(value['gaps'] + ['saved_material_missing_for_this_result']))
        return _frozen(value)
    start = text.find(CONDITION)
    if start < 0 or text.find(CONDITION, start + 1) >= 0:
        raise P2Error('p2_local_action_clause_conflict', 409)
    end = start + len(CONDITION)
    mids = sorted(m['material_id'] for m in materials)
    value['state'] = 'supported_verification_actions'
    value['source_refs'] = [{
        'material_id': m['material_id'], 'subject': m['subject'], 'source_sha256': m['source_sha256'],
        'source_level': m['source_level'], 'verification_state': m['verification_state'],
        'evidence_ids': m['evidence_ids'], 'candidate_id': candidate_id, 'git_commit': COMMIT,
        'source_url': GIT_URL,
    } for m in sorted(materials, key=lambda m: m['material_id'])]
    value['clauses'] = [{
        'material_id': mid, 'quote': CONDITION, 'start': start, 'end': end,
        'line_start': text[:start].count('\n') + 1, 'line_end': text[:end].count('\n') + 1,
        'category': 'quoted_condition_not_applicability_decision',
    } for mid in mids]

    def action(code, text, fields):
        value['actions'].append({
            'code': code, 'text': text, 'usage_fields': fields,
            'source_material_ids': mids, 'clause_indices': list(range(len(mids))),
            'claim_level': 'verification_action_only',
        })

    usage = result['usage']
    action('CHECK_EXACT_SOURCE_SCOPE',
           '核对http-server@14.1.2中实际使用的文件是否来自本次记录的Git提交，保留文件清单及对应Hash；本条原文不能证明npm发行包或其他依赖的许可范围。', [])
    if usage['modified'] is True:
        action('CHECK_MODIFIED_FILES',
               '核对修改后的http-server源码清单，对照原文中的副本或实质部分条件，记录版权与许可声明的保留位置和待补项；当前材料不证明义务已经履行。', ['modified'])
    if usage['distributed'] is True or usage['source_disclosure'] is True:
        fields = [key for key in ('distributed', 'source_disclosure') if usage[key] is True]
        action('CHECK_PLANNED_DELIVERY',
               '核对拟交付或公开的文件集合，确认哪些属于该提交源码的副本或实质部分，再逐项核对版权和许可声明的保留位置；保留清单，不把用途声明当成实际交付证据。', fields)
    if usage['network_service'] is True:
        action('CHECK_SERVICE_DELIVERY_BOUNDARY',
               '核对在线服务是否另外提供源码、下载件或文件副本，记录具体交付边界后再对照所引用条件；仅运行服务不等于已经分发，也不能证明声明义务已履行。', ['network_service'])
    unknown = [key for key in USES if usage[key] is None]
    if unknown:
        value['gaps'] = sorted(set(value['gaps'] + ['usage_' + key + '_unknown' for key in unknown]))
    return _frozen(value)
