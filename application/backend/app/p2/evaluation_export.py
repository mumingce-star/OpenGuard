"""Bound, read-only, in-memory evaluation packages; no fetch or generation.

The package is a reproducible export snapshot, not another P2 publication.
Original report bytes and saved P2 objects retain their own identities.
"""
from __future__ import annotations

import hashlib
import html
import io
import re
import zipfile

from .contract import P2Error, canonical, digest, strict_json

MAX_PACKAGE_BYTES = 32 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_REFERENCES = 64
_ID = re.compile(r'^[A-Za-z0-9_.:-]{1,200}$')
_SENSITIVE = re.compile(
    r'/Users/|/private/(?:var|tmp)/|/home/[^/\s<>"\\]+/|[A-Za-z]:\\\\'
    r'|-----BEGIN [^-]*PRIVATE KEY-----'
    r'|https?://[^/\s"<>]*@'
    r'|(?i:\b(?:password|authorization|cookie|access_token|api_key|secret_key)'
    r'["\s]*[:=]["\s]*(?!null\b|false\b|none\b)[^\s"<,}]{8,})'
)


def _bad(code='evaluation_package_binding_conflict', status=409):
    raise P2Error(code, status)


def _identity(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        _bad('evaluation_package_selection_invalid', 422)


def _json(value):
    return canonical(value)


def _safe(raw):
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_FILE_BYTES:
        _bad('evaluation_package_size_invalid', 413)
    try:
        text = raw.decode('utf-8')
    except UnicodeError:
        _bad('evaluation_package_text_invalid', 503)
    if '\x00' in text or _SENSITIVE.search(text):
        _bad('evaluation_package_sensitive_content_blocked', 409)
    return raw


def _linked_record(p2, result, kind, identity):
    _identity(identity)
    b = result['binding']
    value = p2.record(b['scan_id'], b['assessment_id'], kind, identity, b['assessment_version'])
    if value['binding'] != b or value['data_scope'] != result['data_scope']:
        _bad()
    if kind == 'material':
        rows = [r for r in result['resources'] if identity in r['material_ids']]
        if (len(rows) != 1 or rows[0]['subject'] != value['subject']
                or not set(value['evidence_ids']) <= set(rows[0]['evidence_ids'])):
            _bad()
    else:
        subjects = [r['subject'] for r in result['resources'] if identity in r['answer_ids']]
        if (sorted(subjects, key=lambda x: x['resource_id'])
                != sorted(value['subjects'], key=lambda x: x['resource_id'])
                or not set(value['evidence_ids']) <= set().union(*[
                    set(r['evidence_ids']) for r in result['resources'] if identity in r['answer_ids']])):
            _bad()
    return value


def _analysis_matches(value, result, id_key, hash_key, expected_id):
    check = dict(value)
    identity, sha = check.pop(id_key, None), check.pop(hash_key, None)
    if (identity != expected_id or digest(check) != sha
            or value.get('binding') != result['binding']
            or value.get('result_id') != result['result_id']
            or value.get('result_sha256') != result['result_sha256']
            or value.get('result_revision') != result['revision']):
        _bad('evaluation_package_analysis_binding_conflict')


def _quote_closure(value, texts, *, preview=False):
    """Recheck export-visible references and Unicode offsets against saved bytes."""
    key, many = ('source_candidate_id', 'source_candidate_ids') if preview else ('material_id', 'source_material_ids')
    clauses, actions = value.get('clauses'), value.get('actions')
    if not isinstance(clauses, list) or not isinstance(actions, list):
        _bad('evaluation_package_analysis_reference_conflict')
    if value.get('status') != 'succeeded':
        if clauses or actions:
            _bad('evaluation_package_analysis_reference_conflict')
        return
    if not clauses or not actions or value.get('quote_index_unit') != 'unicode_code_point':
        _bad('evaluation_package_analysis_reference_conflict')
    for clause in clauses:
        identity, start, end = clause.get(key), clause.get('start'), clause.get('end')
        if (identity not in texts or type(start) is not int or type(end) is not int
                or not 0 <= start < end <= len(texts[identity])
                or texts[identity][start:end] != clause.get('quote')):
            _bad('evaluation_package_analysis_quote_conflict')
    cited = {clause[key] for clause in clauses}
    for action in actions:
        refs = action.get(many)
        if (not isinstance(refs, list) or not refs or len(refs) != len(set(refs))
                or not set(refs) <= cited or action.get('claim_level') != 'verification_action_only'):
            _bad('evaluation_package_analysis_reference_conflict')


def build_package(p2, assessment_service, report_service, sid, aid, result_id, version,
                  *, report_snapshot_id=None, analysis_id=None, preview_id=None):
    """Return deterministic ZIP bytes using only exact saved read methods.

    No latest/head lookup, initialization, store repair, model, or network call.
    A caller selects model bodies by immutable ID; failed/rejected analysis is
    represented accurately instead of exposing an invalid action as usable.
    """
    for identity in (sid, aid, result_id):
        _identity(identity)
    if type(version) is not int or version < 1 or (analysis_id and preview_id):
        _bad('evaluation_package_selection_invalid', 422)
    for identity in (report_snapshot_id, analysis_id, preview_id):
        if identity is not None:
            _identity(identity)
    result = p2.read(sid, aid, result_id, version)
    run, assessment, binding, _ = p2.context(sid, aid)
    if result['binding'] != binding or binding['assessment_version'] != version:
        _bad()
    summary = p2.summary(sid, aid, result_id, version)
    if (summary.get('summary_id') != result['companion_summary_id']
            or summary.get('resource_states') != {r['subject']['resource_id']: r['state'] for r in result['resources']}):
        _bad('evaluation_package_summary_binding_conflict')
    files = {}
    entries = {}

    def add(path, raw, *, kind, identity=None, representation='saved_object_canonical_json'):
        raw = _safe(raw)
        if path in files or path.startswith('/') or '..' in path.split('/'):
            _bad('evaluation_package_entry_invalid', 503)
        if sum(map(len, files.values())) + len(raw) > MAX_PACKAGE_BYTES - 256 * 1024:
            _bad('evaluation_package_size_invalid', 413)
        files[path] = raw
        entries[path] = {'byte_count': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                         'kind': kind, 'identity': identity, 'representation': representation}

    add('02_P2/Result.json', _json(result), kind='P2_RESULT', identity=result_id)
    add('02_P2/Summary.json', _json(summary), kind='P2_COMPANION_NOT_FORMAL_REPORT',
        identity=summary['summary_id'])
    if assessment_service is None:
        _bad('evaluation_package_assessment_report_unavailable', 503)
    for fmt in ('json', 'html'):
        raw = assessment_service.store.report(sid, aid, fmt)
        if raw is None:
            _bad('evaluation_package_assessment_report_missing', 404)
        if fmt == 'json':
            document = strict_json(raw)
            saved = document.get('assessment') if isinstance(document, dict) else None
            if (not isinstance(saved, dict) or saved.get('id') != aid
                    or saved.get('scan_id') != sid or saved.get('version') != version
                    or saved.get('facts_hash') != binding['facts_hash']
                    or saved.get('usage_hash') != binding['usage_hash']):
                _bad('evaluation_package_report_binding_conflict')
        add('01_REPORT/Assessment.' + fmt, raw, kind='SAVED_ASSESSMENT_REPORT', identity=aid,
            representation='exact_saved_artifact_bytes')

    if report_snapshot_id is not None:
        if report_service is None:
            _bad('evaluation_package_archive_unavailable', 503)
        snapshot = report_service.get(sid, aid, report_snapshot_id)
        if snapshot is None:
            _bad('evaluation_package_archive_missing', 404)
        saved = snapshot.model_dump(mode='json')
        sb = saved['binding']
        if (sb['scan_ref']['scan_id'] != sid or sb['assessment_ref']['assessment_id'] != aid
                or sb['assessment_ref']['version'] != version):
            _bad('evaluation_package_archive_binding_conflict')
        add('01_REPORT/ArchiveMetadata.json', _json(saved), kind='FIXED_REPORT_V2_METADATA',
            identity=report_snapshot_id)
        for fmt in ('json', 'html'):
            raw = report_service.artifact(sid, aid, report_snapshot_id, fmt)
            metadata = [x for x in saved['artifacts'] if x['format'] == fmt]
            if (not isinstance(raw, bytes) or len(metadata) != 1
                    or len(raw) != metadata[0]['size_bytes']
                    or hashlib.sha256(raw).hexdigest() != metadata[0]['content_hash']):
                _bad('evaluation_package_archive_integrity_error', 503)
            if fmt == 'json':
                value = strict_json(raw)
                if value.get('snapshot_id') != report_snapshot_id or value.get('binding', {}).get('assessment_ref') != sb['assessment_ref']:
                    _bad('evaluation_package_archive_binding_conflict')
            add('01_REPORT/Archive.' + fmt, raw, kind='FIXED_REPORT_V2_ARTIFACT',
                identity=report_snapshot_id, representation='exact_saved_artifact_bytes')

    if len(result['material_ids']) + len(result['answer_ids']) > MAX_REFERENCES:
        _bad('evaluation_package_reference_limit', 413)
    materials, material_texts = {}, {}
    for identity in sorted(result['material_ids']):
        material = _linked_record(p2, result, 'material', identity)
        materials[identity] = material
        add(f'03_MATERIALS/{identity}/Material.json', _json(material), kind='PENDING_MATERIAL', identity=identity)
        with p2.store.connection() as db:
            raw = p2.store.material_bytes(db, material)
        if (not re.fullmatch(r'(?i)(LICENSE|LICENCE|NOTICE)(\.(txt|md|rst))?', material['filename'])
                or hashlib.sha256(raw).hexdigest() != material['source_sha256']):
            _bad('evaluation_package_material_integrity_error', 503)
        add(f'03_MATERIALS/{identity}/{material["filename"]}', raw, kind='MATERIAL_ORIGINAL_BYTES',
            identity=identity, representation='exact_saved_material_bytes')
        material_texts[identity] = raw.decode('utf-8-sig')
    for identity in sorted(result['answer_ids']):
        value = _linked_record(p2, result, 'answer', identity)
        add(f'04_ANSWERS/{identity}.json', _json(value), kind='USER_ASSERTED_ANSWER', identity=identity)

    official = getattr(p2, 'official_sources', None)
    local_actions, selected_ai = None, None
    model_status = {'state': 'NOT_CONFIGURED', 'analysis_id': analysis_id, 'preview_id': preview_id}
    source_status = {'state': 'NOT_CONFIGURED'}
    if official is not None:
        status = official.status(sid, aid, version, result_id)
        if (status.get('binding') != binding or status.get('result_id') != result_id
                or status.get('result_sha256') != result['result_sha256']):
            _bad()
        job = dict(status['analysis']); preview = job.pop('preview', None)
        if job['state'] in {'queued', 'running', 'waiting_source'} or status['fetch']['state'] in {'queued', 'running'}:
            _bad('evaluation_package_analysis_in_progress', 409)
        model_status = job
        source_status = status['fetch']
        if status.get('candidate') is not None:
            add('05_AI_AND_SOURCES/SourceCandidate.json', _json(status['candidate']),
                kind='RETRIEVED_UNADOPTED_SOURCE_CANDIDATE', identity=status['candidate']['candidate_id'])
        actions = status.get('local_actions')
        if actions is not None:
            content = dict(actions); expected = content.pop('content_sha256', None)
            if (digest(content) != expected or actions.get('binding') != binding
                    or actions.get('result_id') != result_id
                    or actions.get('result_sha256') != result['result_sha256']):
                _bad('evaluation_package_actions_binding_conflict')
            add('06_ACTIONS/SourceBoundActions.json', _json(actions), kind='SOURCE_BOUND_VERIFICATION_ACTIONS')
            local_actions = actions
        if preview_id is not None:
            if preview is None or job.get('preview_id') != preview_id:
                _bad('evaluation_package_preview_unavailable', 409)
            _analysis_matches(preview, result, 'preview_id', 'preview_sha256', preview_id)
            candidate = status.get('candidate')
            refs = preview.get('source_refs')
            if (candidate is None or preview.get('candidate_id') != candidate['candidate_id']
                    or not isinstance(refs, list) or len(refs) != 1
                    or refs[0].get('candidate_id') != candidate['candidate_id']
                    or refs[0].get('subject') != candidate['subject']
                    or refs[0].get('source_sha256') != hashlib.sha256(candidate['license_text'].encode('utf-8')).hexdigest()
                    or refs[0].get('source_level') != 'retrieved_unadopted_candidate'
                    or refs[0].get('verification_state') != 'pending'):
                _bad('evaluation_package_analysis_source_conflict')
            _quote_closure(preview, {candidate['candidate_id']: candidate['license_text']}, preview=True)
            add('05_AI_AND_SOURCES/Preview.json', _json(preview), kind='UNADOPTED_AI_PREVIEW', identity=preview_id)
            selected_ai = preview
        elif preview is not None:
            _bad('evaluation_package_analysis_selection_required', 409)
        if analysis_id is not None and job.get('analysis_id') != analysis_id:
            _bad('evaluation_package_analysis_binding_conflict')

    ai = getattr(p2, 'ai_analysis', None)
    if analysis_id is not None:
        if ai is None:
            _bad('evaluation_package_analysis_unavailable', 503)
        try:
            value = ai.read(sid, aid, analysis_id, result_id, version)
        except P2Error as exc:
            if exc.code != 'p2_ai_saved_output_rejected':
                raise
            model_status = {**model_status, 'state': 'REJECTED_SAVED_OUTPUT', 'error_code': exc.code,
                            'analysis_id': analysis_id, 'body': 'NOT_INCLUDED_SEMANTIC_VALIDATION_REJECTED'}
        else:
            _analysis_matches(value, result, 'analysis_id', 'analysis_sha256', analysis_id)
            referenced = set()
            for ref in value['source_refs']:
                material = materials.get(ref['material_id'])
                if (material is None or ref['source_sha256'] != material['source_sha256']
                        or ref['subject'] != material['subject']
                        or ref.get('source_level') != material['source_level']
                        or ref.get('verification_state') != material['verification_state']
                        or ref.get('byte_count') != material['byte_count']
                        or ref['material_id'] in referenced):
                    _bad('evaluation_package_analysis_material_conflict')
                referenced.add(ref['material_id'])
            _quote_closure(value, {identity: material_texts[identity] for identity in referenced})
            add('05_AI_AND_SOURCES/Analysis.json', _json(value), kind='INDEPENDENT_AI_ANALYSIS', identity=analysis_id)
            selected_ai = value
            model_status = {**model_status, 'state': value['status'], 'analysis_id': analysis_id,
                            'analysis_sha256': value['analysis_sha256']}
    elif model_status.get('analysis_id') is not None:
        _bad('evaluation_package_analysis_selection_required', 409)
    if preview_id is not None and official is None:
        _bad('evaluation_package_preview_unavailable', 503)
    add('05_AI_AND_SOURCES/Status.json', _json({'sources': source_status, 'analysis': model_status}),
        kind='EXACT_RESULT_SOURCE_AND_AI_STATUS')

    manifest = {'schema_version': 'openguard-evaluation-package/1', 'binding': binding,
                'result_id': result_id, 'result_revision': result['revision'], 'result_sha256': result['result_sha256'],
                'companion_summary_id': summary['summary_id'], 'report_snapshot_id': report_snapshot_id,
                'analysis_id': analysis_id, 'preview_id': preview_id,
                'selected_result_created_at': result['created_at'], 'data_scope': result['data_scope'],
                'formal_effect': 'none', 'export_only': True, 'generation_model_calls': 0,
                'outbound_http_requests': 0, 'business_writes': 0,
                'report_boundary': 'Saved Assessment report predates P2 material updates; P2 Result and Summary are separate fixed files.',
                'ai_boundary': 'Independent saved AI analysis/preview is not formal Advice or license acceptance.',
                'source_boundary': 'Material pending and Git source scope do not prove npm distribution, actual delivery, applicability, or fulfillment.',
                'entries': entries.copy()}
    add('VERSION_BINDING.json', _json(manifest), kind='EXPORT_SNAPSHOT_MANIFEST')
    heading = f'OpenGuard 完整评估包 · Assessment v{version} / Result r{result["revision"]}'
    esc = lambda value: html.escape(str(value), quote=True)
    uses = {'commercial': '商业使用', 'modified': '修改代码', 'distributed': '分发或交付',
            'network_service': '提供在线服务', 'training': '用于模型训练',
            'redistributed_assets': '再分发资源', 'source_disclosure': '公开源代码'}
    usage_html = ''.join(f'<li>{esc(label)}：{esc({True:"是",False:"否",None:"暂不确定"}[result["usage"][key]])}</li>'
                         for key, label in uses.items())
    saved_conditions = [(row['subject'], advice) for row in result['resources'] for advice in row['advice']
                        if advice['state'] == 'conditional_candidate' and advice['conditions']]
    condition_html = ''.join('<li>' + esc(subject['resource_id']) + ' / ' + esc(subject['version']) + '：'
        + '；'.join(esc(x) for x in advice['conditions']) + '</li>' for subject, advice in saved_conditions)
    actions_html = ''.join('<li>' + esc(action.get('text', action.get('action', ''))) + '</li>'
                           for action in (local_actions or {}).get('actions', []))
    ai_html = ''.join('<li>' + esc(action['text']) + '</li>' for action in (selected_ai or {}).get('actions', []))
    material_html = ''.join('<li>' + esc(m['filename']) + ' · ' + esc(m['subject']['resource_id'])
                           + ' / ' + esc(m['subject']['version']) + ' · user_supplied_unverified / pending</li>'
                           for m in materials.values())
    reading = ('<h2>当前用途</h2><p>用途声明与真实使用、实际交付和义务履行分别核验。'
               + ('本例用途为演示假设。' if result['data_scope'] == 'TEST_ONLY' else '') + '</p><ul>' + usage_html + '</ul>'
               + '<h2>材料与结果变化</h2><p>本Result关联 ' + str(len(materials)) + ' 份材料；重新计算 '
               + str(len(result['recomputed_resource_ids'])) + ' 个资源，复用 ' + str(len(result['reused_resource_ids']))
               + ' 个资源。此处统计属于固定Result，不代表所有资源已获许可。</p><ul>'
               + (material_html or '<li>本Result没有关联材料；不从其他Assessment自动补入。</li>') + '</ul>'
               + '<h2>已保存的条件建议</h2><ul>' + (condition_html or '<li>本Result尚无具有完整条件依据的保存建议；不能据此宣称禁止或许可使用。</li>') + '</ul>'
               + '<h2>原文支持的具体核验行动</h2><ul>' + (actions_html or '<li>当前固定版本尚无独立原文支持行动；可查看具体缺口和来源记录。</li>') + '</ul>'
               + '<h2>独立Qwen辅助分析</h2><p>固定状态：' + esc(model_status.get('state'))
               + '。辅助分析不改变正式Assessment、P2 Result或许可状态。</p><ul>'
               + (ai_html or '<li>本包没有可展示的有效辅助行动；准确错误/未配置状态保留在Status.json。</li>') + '</ul>')
    start = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
             '<title>' + html.escape(heading) + '</title><style>body{max-width:960px;margin:3rem auto;padding:1rem;font:17px/1.7 system-ui}code{overflow-wrap:anywhere}li{margin:.5rem 0}</style>'
             '<h1>' + html.escape(heading) + '</h1><p>这是一份固定对象的导出快照；下载不会重算结果、联网或调用模型。</p>'
             + reading +
             '<ol><li><a href="01_REPORT/Assessment.html">查看本版原正式评估报告</a>。报告保留原字节；材料更新单独保存在P2结果中。</li>'
             '<li><a href="02_P2/Result.json">查看固定P2 Result及保存建议</a>，<a href="02_P2/Summary.json">查看同版材料核对摘要</a>。摘要不是正式报告，也不保存行动文字。</li>'
             '<li>03_MATERIALS保留本Result引用的材料原文及pending来源等级；未引用的历史材料不会跨版补入。</li>'
             '<li>05_AI_AND_SOURCES记录独立AI分析、预览或准确失败/未配置状态；AI不签发来源或许可结论。</li>'
             '<li>06_ACTIONS（若存在）提供原文支持的核验行动，不等于已批准商业使用或义务履行。</li></ol>'
             '<p>Assessment.version与Result.revision分别计数。版本、引用及文件SHA256见VERSION_BINDING.json与FILE_HASHES.json。</p>'
             '<p>来源观察、材料采用、许可适用和义务履行是不同事实。请保留未核实事项。</p></html>').encode()
    add('START_HERE.html', start, kind='EXPORT_READER')
    files['FILE_HASHES.json'] = _json({k: {'byte_count': len(v), 'sha256': hashlib.sha256(v).hexdigest()}
                                      for k, v in sorted(files.items())})
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED, strict_timestamps=True) as archive:
        for path, raw in sorted(files.items()):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw)
    raw = output.getvalue()
    if len(raw) > MAX_PACKAGE_BYTES:
        _bad('evaluation_package_size_invalid', 413)
    return raw, result
