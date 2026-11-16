"""Independent immutable AI explanations of exact saved P2 objects.

No promotion of Material, source admission, Advice, or public P2 Result fields.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
import time

from pydantic import Field, model_validator
from .contract import Binding, DTO, ID, SHA, Material, P2Error, canonical, digest, strict_json
from .store import P2Store
from app.ai.p2_analysis import BoundQwen, BudgetError, material_quote_candidates


class AnalysisRequest(DTO):
    binding: Binding
    result_id: ID
    result_sha256: SHA
    material_ids: list[ID] = Field(min_length=1, max_length=4)
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r'^[A-Za-z0-9_.:-]+$')
    previous_result_id: ID | None = None

    @model_validator(mode='after')
    def unique(self):
        if len(self.material_ids) != len(set(self.material_ids)):
            raise ValueError('duplicate material')
        return self


class AnalysisStore(P2Store):
    def guard(self):
        if self.path.name != 'p2-ai.db':
            raise P2Error('p2_ai_storage_invalid', 503)
        for path in (self.path.parent, self.path):
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077 or (path == self.path and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1)):
                raise P2Error('p2_ai_storage_invalid', 503)

    def initialize(self):
        if not self.path.exists():
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600); os.close(fd)
        with self.connection(write=True) as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS ai_requests(
                scan_id TEXT, assessment_id TEXT, key TEXT, fingerprint TEXT NOT NULL,
                analysis_id TEXT, PRIMARY KEY(scan_id,assessment_id,key));
                CREATE TABLE IF NOT EXISTS ai_objects(
                id TEXT PRIMARY KEY, scan_id TEXT, assessment_id TEXT, result_id TEXT,
                payload BLOB NOT NULL, sha256 TEXT NOT NULL);''')


_BANNED = re.compile(r'可商用|可以商用|允许商业|允许分发|允许商用|已获授权|已获得授权|已授权|已批准|已经合规|已合规|已核验|来源可信|义务已履行|无需核验|无需审核|无需审查|保证合法|确认合法|可自由|可以自由|没有风险|不存在风险|无需保留|无需遵守|可合法|许可有效|授权有效|https?://|file://|\b(?:sudo|curl|wget|approved|authorized|compliant|permitted)\b', re.I)
_START = re.compile(r'^(核对|检查|确认|保留|记录|补充|对照|明确|请)')
# Targeted rejection of the observed generation-02 mistakes, not a complete
# semantic verifier or an additional license applicability rule.
_KNOWN_ACTION_ERROR = re.compile(
    r'(?:许可|版权|免责)(?:条款|文本|声明)?.{0,65}(?:是否(?:包含|存在|明确(?:列出|排除)?|列出|排除)|有无)'
    r'|是否允许.{0,24}保留'
    r'|(?:服务运行中|服务运行时|运行服务时|在线服务运行中).{0,12}(?:均|都|必须|应当|需要|需|要).{0,12}(?:保留|包含|附带|展示)'
)


def known_action_error(text):
    # In this narrow construction the license is the comparison basis, while
    # the question concerns delivery/source files. Do not let the broad span
    # matcher treat that basis as the question's subject. Check the remaining
    # sentence normally, and retain the original text for every other guard.
    subject_text = re.sub(
        r'^对照(?:已引用的)?许可条款'
        r'(?=(?:确认|核对|检查)(?:实际|拟)?'
        r'(?:交付文件|修改后源码文件|修改后代码文件)(?:中)?(?:是否|有无))',
        '', text, count=1,
    )
    return _KNOWN_ACTION_ERROR.search(subject_text)


LIMITATIONS = [
    'AI只提出待核验行动，不能签发来源、确认许可适用性或义务履行。',
    '材料保持user_supplied_unverified/pending；逐字引用正确不等于来源可信或语义审核通过。',
    '用途为演示用途假设；Git根LICENSE不自动覆盖npm发行包、其他依赖或实际交付范围。',
    '结果变更由程序计算；Qwen解释不改变已有P2 Result、Advice、Summary或正式规则。',
    '结构与已知错误模式检查不保证行动完整或语义正确，内容仍需人工复核。',
]

_USAGE_FIELDS = ('commercial', 'modified', 'distributed', 'network_service',
                 'training', 'redistributed_assets', 'source_disclosure')
_USAGE_NAME = r'(?<![A-Za-z0-9_])(?:usage\.)?(' + '|'.join(_USAGE_FIELDS) + r')'
_QUOTING = r'[\s\x22\x27`‘’“”]*'
_VALUE = r'(true|false|null)(?![A-Za-z0-9_])'
_USAGE_ASSIGNMENT = re.compile(_USAGE_NAME + _QUOTING + r'(?:=|:|：|为|是)' + _QUOTING + _VALUE, re.I)
_USAGE_TRANSITION = re.compile(_USAGE_NAME + _QUOTING + r'(?:字段)?(?:由|从)' + _QUOTING + _VALUE
                             + _QUOTING + r'(?:变为|变成|变|改为|调整为|到|→|->)' + _QUOTING + _VALUE, re.I)
_JSON_USAGE_VALUE = {'true': True, 'false': False, 'null': None}
_DISCLAIMER = re.compile(r'免责|WITHOUT\s+WARRANTY|AS\s+IS|THE\s+SOFTWARE\s+IS\s+PROVIDED', re.I)
_SCOPE_WORDS = re.compile(r'交付|分发|副本|源码|下载件|服务运行|在线服务')
_SCOPE_INFERENCE = re.compile(r'依据|根据|基于|推导|推断|得出|说明|表明|证明')


def validate_action_semantics(text, usage, changes):
    """Reject observed semantic errors; this is not a general legal verifier.

    Assignment literals describe the current exact usage. Historical transition
    wording is accepted only with matching program-computed before/after facts.
    No model sentence can create a new usage fact or a clause applicability rule.
    """
    if not isinstance(text, str):
        raise ValueError('action text')
    # The observed generation-06 action hit its 300-character schema boundary
    # inside a long English quotation. Keep the raw model object immutable, but
    # do not present that incomplete copy as a usable verification action. This
    # only checks delimiter integrity, not truth or license applicability.
    for opening, closing in (("'", "'"), ('"', '"'), ('“', '”'), ('‘', '’')):
        start = None
        for index, character in enumerate(text):
            if (character == "'" and 0 < index < len(text) - 1
                    and text[index - 1].isascii() and text[index - 1].isalpha()
                    and text[index + 1].isascii() and text[index + 1].isalpha()):
                continue  # Apostrophes inside words are not quote delimiters.
            if start is None and character == opening:
                start = index + 1
            elif start is not None and character == closing:
                start = None
        if start is not None:
            tail = text[start:]
            if len(re.findall(r'[A-Za-z]', tail)) >= 40 and len(re.findall(r'[A-Za-z]+', tail)) >= 5:
                raise ValueError('incomplete embedded quote')
    usage = usage if isinstance(usage, dict) else {}
    for match in _USAGE_TRANSITION.finditer(text):
        field, before, after = match.groups()
        field = field.lower(); before = _JSON_USAGE_VALUE[before.lower()]; after = _JSON_USAGE_VALUE[after.lower()]
        if (field not in usage or usage[field] is not after
                or not any(row.get('field') == 'usage.' + field and row.get('before') is before
                           and row.get('after') is after for row in changes)):
            raise ValueError('usage transition conflict')
    for match in _USAGE_ASSIGNMENT.finditer(text):
        field, value = match.groups(); field = field.lower()
        if field not in usage or usage[field] is not _JSON_USAGE_VALUE[value.lower()]:
            raise ValueError('usage value conflict')
    if _DISCLAIMER.search(text) and _SCOPE_WORDS.search(text) and _SCOPE_INFERENCE.search(text):
        raise ValueError('disclaimer scope inference')


def validate_saved_semantics(value, usage):
    """Read-time guard only: never rewrite a previously saved model object."""
    if value.get('status') != 'succeeded':
        return
    if 'usage' in value and value['usage'] != usage:
        raise ValueError('usage value conflict')
    changes = value.get('changes', [])
    for action in value.get('actions', []):
        validate_action_semantics(action['text'], usage, changes)
    for change in changes:
        validate_action_semantics(change['explanation'], usage, changes)


def validate_output(raw, payload):
    obj = strict_json(raw)
    if not isinstance(obj, dict) or set(obj) != {'clauses', 'actions', 'change_explanations'}:
        raise ValueError('shape')
    materials = {m['material_id']: m for m in payload['materials']}
    clauses, actions, changes = obj['clauses'], obj['actions'], obj['change_explanations']
    if not isinstance(clauses, list) or not 1 <= len(clauses) <= 6 or not isinstance(actions, list) or not 1 <= len(actions) <= 4 or not isinstance(changes, list) or len(changes) != len(payload['changes']):
        raise ValueError('shape')
    frozen_clauses = []
    for clause in clauses:
        if not isinstance(clause, dict) or set(clause) != {'material_id', 'quote', 'category'} or clause['material_id'] not in materials or clause['category'] not in {'permission', 'condition', 'disclaimer', 'other'}:
            raise ValueError('clause identity')
        quote = clause['quote']; text = materials[clause['material_id']]['text']
        if (not isinstance(quote, str) or not 20 <= len(quote) <= 500 or quote not in text
                or quote not in materials[clause['material_id']]['quote_candidates']):
            raise ValueError('quote mismatch')
        start = text.index(quote)
        frozen_clauses.append({**clause, 'start': start, 'end': start + len(quote)})
    frozen_actions = []
    cited = {c['material_id'] for c in clauses}
    for action in actions:
        if not isinstance(action, dict) or set(action) != {'text', 'source_material_ids'}:
            raise ValueError('action shape')
        text, refs = action['text'], action['source_material_ids']
        if not isinstance(text, str) or not 8 <= len(text) <= 300 or not _START.search(text) or _BANNED.search(text) or not isinstance(refs, list) or not refs or len(refs) > 4 or any(not isinstance(r, str) or r not in cited for r in refs) or len(refs) != len(set(refs)):
            raise ValueError('unbound action')
        if known_action_error(text):
            raise ValueError('known action semantic error')
        validate_action_semantics(text, payload.get('usage'), payload['changes'])
        frozen_actions.append({**action, 'claim_level': 'verification_action_only'})
    by_index = {}
    for row in changes:
        if not isinstance(row, dict) or set(row) != {'index', 'text'} or type(row['index']) is not int or row['index'] in by_index or not 0 <= row['index'] < len(payload['changes']) or not isinstance(row['text'], str) or not 5 <= len(row['text']) <= 300 or _BANNED.search(row['text']):
            raise ValueError('change explanation')
        if re.search(r'(?:(?:字段|内容|状态|材料|缺口|gaps).{0,8}(?:未变|没变|不变|无变化|没有变化)|(?:没有|未发生|不存在).{0,6}(?:变化|变更|新增))', row['text'], re.I):
            raise ValueError('change denial')
        validate_action_semantics(row['text'], payload.get('usage'), payload['changes'])
        by_index[row['index']] = row['text']
    return frozen_clauses, frozen_actions, [{**row, 'explanation': by_index[i]} for i, row in enumerate(payload['changes'])]


class P2AnalysisService:
    def __init__(self, p2, store, provider, *, public_sample_only=True):
        self.p2, self.store, self.provider = p2, store, provider
        # Only explicit synthetic test dependency injection may opt out; not an HTTP field.
        self.public_sample_only = public_sample_only

    def _result(self, sid, aid, rid, version):
        result = self.p2.read(sid, aid, rid, version)
        if result['data_scope'] != 'TEST_ONLY':
            raise P2Error('p2_ai_test_only_required', 403)
        return result

    def index(self, sid, aid, rid, version):
        self._result(sid, aid, rid, version)
        with self.store.connection() as db:
            rows = db.execute('SELECT id FROM ai_objects WHERE scan_id=? AND assessment_id=? AND result_id=? ORDER BY rowid', (sid, aid, rid)).fetchall()
        return {'result_id': rid, 'analysis_ids': [r[0] for r in rows]}

    def read(self, sid, aid, identity, rid, version):
        result = self._result(sid, aid, rid, version)
        with self.store.connection() as db:
            row = db.execute('SELECT scan_id,assessment_id,result_id,payload,sha256 FROM ai_objects WHERE id=?', (identity,)).fetchone()
        if row is None:
            raise P2Error('p2_ai_not_found', 404)
        if tuple(row[:3]) != (sid, aid, rid):
            raise P2Error('p2_ai_binding_conflict', 409)
        value = self.store.decode(row[3:])
        check = dict(value); expected = check.pop('analysis_sha256'); stored_id = check.pop('analysis_id')
        if digest(check) != expected or stored_id != 'p2ai_' + expected or value['binding'] != result['binding'] or value['result_sha256'] != result['result_sha256']:
            raise P2Error('p2_ai_integrity_error', 503)
        try:
            if value.get('analysis_protocol') == 'openguard-qwen-action-plan/2':
                from .action_plan_runner import validate_saved_plan
                body = AnalysisRequest(binding=value['binding'], result_id=rid, result_sha256=value['result_sha256'],
                    material_ids=[m['material_id'] for m in value['source_refs']],
                    idempotency_key=value['idempotency_key'], previous_result_id=value['previous_result_id'])
                _, _, payload = self._input(sid, aid, body)
                if 'retrieval_source_context' in value:
                    payload['retrieval_source_context'] = value['retrieval_source_context']
                validate_saved_plan(value, payload)
            else:
                validate_saved_semantics(value, result['usage'])
        except (ValueError, TypeError, KeyError):
            raise P2Error('p2_ai_saved_output_rejected', 409) from None
        return value

    def _input(self, sid, aid, body):
        result = self._result(sid, aid, body.result_id, body.binding.assessment_version)
        if result['binding'] != body.binding.model_dump() or result['result_sha256'] != body.result_sha256:
            raise P2Error('p2_ai_binding_conflict', 409)
        materials = []
        with self.p2.store.connection() as db:
            for mid in body.material_ids:
                if mid not in result['material_ids']:
                    raise P2Error('p2_ai_material_not_in_result', 409)
                material = Material.model_validate(self.p2.store.get(db, 'material', mid, sid, aid)).model_dump(mode='json')
                row = next((r for r in result['resources'] if r['subject'] == material['subject']), None)
                if material['binding'] != result['binding'] or row is None or mid not in row['material_ids'] or not set(material['evidence_ids']) <= set(row['evidence_ids']) or material['data_scope'] != 'TEST_ONLY':
                    raise P2Error('p2_ai_material_binding_conflict', 409)
                raw = self.p2.store.material_bytes(db, material)
                if len(raw) > 8192 or len(raw) != material['byte_count'] or hashlib.sha256(raw).hexdigest() != material['source_sha256']:
                    raise P2Error('p2_ai_material_hash_invalid', 409)
                try:
                    text = raw.decode('utf-8-sig')
                except UnicodeError:
                    raise P2Error('p2_ai_material_text_invalid', 422) from None
                quotes = material_quote_candidates(text)
                if not quotes:
                    raise P2Error('p2_ai_material_text_invalid', 422)
                materials.append({k: material[k] for k in ('material_id', 'subject', 'source_sha256', 'byte_count', 'source_level', 'verification_state')} | {'text': text, 'quote_candidates': quotes})
        if len({m['subject']['resource_id'] for m in materials}) != 1:
            raise P2Error('p2_ai_one_resource_required', 422)
        subject = materials[0]['subject']
        resource = next(r for r in result['resources'] if r['subject'] == subject)
        if self.public_sample_only:
            run, _, binding, resources = self.p2.context(sid, aid)
            actual = resources.get(subject['resource_id'])
            if (binding != result['binding'] or actual is None or actual.name != 'http-server'
                    or actual.version != '14.1.2'
                    or run.project.revision != '0d3b7bb5b6e8a59fd450ae2dca65870009cfcd8b'
                    or any(m['source_sha256'] != 'accfc4d5a588384b29c4817392854afb8f319b4568359ca8d063df8a9bc396b6' for m in materials)):
                raise P2Error('p2_ai_public_sample_required', 403)
        changes = []; previous = None
        if body.previous_result_id is not None:
            previous = self._result(sid, aid, body.previous_result_id, body.binding.assessment_version)
            if previous['binding'] != result['binding'] or previous['revision'] >= result['revision'] or previous['result_id'] != result['previous_result_id']:
                raise P2Error('p2_ai_previous_result_conflict', 409)
            old = next((r for r in previous['resources'] if r['subject'] == subject), None)
            if old is None:
                raise P2Error('p2_ai_previous_resource_conflict', 409)
            for field in ('state', 'material_ids', 'answer_ids', 'gaps'):
                if old[field] != resource[field]:
                    changes.append({'field': field, 'before': old[field], 'after': resource[field]})
        payload = {'schema_version': 'openguard-p2-ai-input/1', 'result_id': result['result_id'],
                   'result_sha256': result['result_sha256'], 'binding': result['binding'], 'subject': subject,
                   'usage': result['usage'], 'usage_assumption': 'DEMO_USAGE_ASSUMPTION',
                   'resource_state': resource['state'], 'gaps': resource['gaps'], 'saved_advice': resource['advice'],
                   'materials': materials, 'changes': changes,
                   'change_facts': [{'index': i, 'field': row['field'],
                       'change_kind': 'list_changed' if isinstance(row['before'], list) else 'value_changed',
                       'added': [v for v in row['after'] if v not in row['before']] if isinstance(row['before'], list) else None,
                       'removed': [v for v in row['before'] if v not in row['after']] if isinstance(row['before'], list) else None}
                       for i, row in enumerate(changes)]}
        if len(canonical(payload)) > 24000:
            raise P2Error('p2_ai_input_too_large', 413)
        return result, previous, payload

    @staticmethod
    def _source_context(value, result, payload):
        # Internal trusted-caller extension only; not a public request DTO field.
        # Verify the immutable candidate and its exact saved material subject/hash.
        if not isinstance(value, dict):
            raise P2Error('p2_ai_source_context_invalid', 409)
        check = dict(value)
        identity, sha = check.pop('candidate_id', None), check.pop('candidate_sha256', None)
        if (not isinstance(sha, str) or digest(check) != sha or identity != 'p2src_' + sha
                or value.get('scan_id') != result['binding']['scan_id'] or value.get('subject') != payload['subject']
                or value.get('commit') != result['binding']['project_revision']
                or not isinstance(value.get('license_text'), str)
                or any(m['source_sha256'] != hashlib.sha256(value['license_text'].encode('utf-8')).hexdigest() for m in payload['materials'])
                or value.get('coverage') not in {'complete_fixed_sources', 'partial_git_license_only'}
                or value.get('npm_metadata_status') != ('missing_404' if value.get('coverage') == 'partial_git_license_only' else 'observed')
                or not isinstance(value.get('sources'), list) or not isinstance(value.get('source_failures'), list)
                or not isinstance(value.get('limitations'), list) or not all(isinstance(x, str) for x in value['limitations'])):
            raise P2Error('p2_ai_source_context_invalid', 409)
        return {k: v for k, v in value.items() if k != 'license_text'}

    def create(self, sid, aid, body, *, source_context=None):
        if self.p2.readonly:
            raise P2Error('p2_read_only', 403)
        if sid != body.binding.scan_id or aid != body.binding.assessment_id:
            raise P2Error('p2_ai_binding_conflict', 409)
        fingerprint = digest(body.model_dump(mode='json') if source_context is None else {'request': body.model_dump(mode='json'), 'source_context': source_context})
        # Check completed/ambiguous reservations first; never regenerate the same request.
        with self.store.connection() as db:
            old = db.execute('SELECT fingerprint,analysis_id FROM ai_requests WHERE scan_id=? AND assessment_id=? AND key=?', (sid, aid, body.idempotency_key)).fetchone()
        if old:
            if old[0] != fingerprint:
                raise P2Error('p2_ai_idempotency_conflict', 409)
            if old[1] is None:
                raise P2Error('p2_ai_outcome_unknown', 409)
            return self.read(sid, aid, old[1], body.result_id, body.binding.assessment_version)
        result, previous, payload = self._input(sid, aid, body)
        context = self._source_context(source_context, result, payload) if source_context is not None else None
        if context is not None:
            payload['retrieval_source_context'] = context
            if len(canonical(payload)) > 24000:
                raise P2Error('p2_ai_input_too_large', 413)
        with self.store.connection(write=True) as db:
            try:
                db.execute('INSERT INTO ai_requests VALUES(?,?,?,?,NULL)', (sid, aid, body.idempotency_key, fingerprint))
            except sqlite3.IntegrityError:
                raise P2Error('p2_ai_request_in_progress', 409) from None
        started = time.monotonic(); status = 'failed'; error = None
        clauses, actions, changes = [], [], []
        protocol_fields = {}
        model_calls = None
        try:
            from .action_plan_runner import enabled, run_plan
            if enabled():
                planned = run_plan(self.provider, payload, audit_root=self.store.path.parent/'action-plan-attempts')
                status, error = planned['status'], planned['error_code']
                clauses, actions, changes = planned['clauses'], planned['actions'], planned['changes']
                model_calls = planned['model_calls']
                protocol_fields = {k: v for k, v in planned.items() if k not in {'status', 'error_code', 'clauses', 'actions', 'changes', 'model_calls'}}
            else:
                raw = self.provider.generate(payload)
                clauses, actions, changes = validate_output(raw, payload)
                status = 'succeeded'
        except BudgetError as exc:
            error = str(exc) if str(exc) in {'p2_ai_busy', 'p2_ai_budget_invalid', 'p2_ai_budget_exhausted', 'p2_ai_rate_limited', 'p2_ai_input_too_large'} else 'p2_ai_unavailable'
        except (ValueError, TypeError, KeyError):
            error = 'p2_ai_output_rejected'
        except Exception:
            error = 'p2_ai_model_unavailable'
        metrics = getattr(self.provider, 'last_metrics', {})
        metrics = {k: (metrics.get(k) if type(metrics.get(k)) is int and metrics[k] >= 0 else None)
                   for k in ('prompt_eval_count', 'eval_count', 'total_duration')}
        value = {'schema_version': 'openguard-p2-ai-analysis/1', 'status': status, 'error_code': error,
                 'result_id': result['result_id'], 'result_revision': result['revision'], 'result_sha256': result['result_sha256'],
                 'binding': result['binding'], 'data_scope': 'TEST_ONLY', 'model': dict(self.provider.model),
                 'input_sha256': digest(payload), 'created_at': datetime.now(timezone.utc).isoformat(),
                 'idempotency_key': body.idempotency_key,
                 'previous_result_id': previous['result_id'] if previous else None,
                 'previous_result_sha256': previous['result_sha256'] if previous else None,
                 'model_calls': model_calls if model_calls is not None else getattr(self.provider, 'model_calls', 0),
                 'metrics': {'elapsed_ms': round((time.monotonic()-started)*1000), **{k: metrics.get(k) for k in ('prompt_eval_count', 'eval_count', 'total_duration')}},
                 'quote_index_unit': 'unicode_code_point', 'source_refs': [{k: v for k, v in m.items() if k not in {'text', 'quote_candidates'}} for m in payload['materials']],
                 'clauses': clauses, 'actions': actions, 'changes': changes, 'limitations': list(LIMITATIONS),
                 'formal_effect': 'none', 'usage_assumption': 'DEMO_USAGE_ASSUMPTION'}
        if context is not None:
            value['retrieval_source_context'] = context
            value['limitations'].extend(context['limitations'])
        value.update(protocol_fields)
        sha = digest(value); value.update(analysis_id='p2ai_' + sha, analysis_sha256=sha)
        raw = canonical(value)
        with self.store.connection(write=True) as db:
            db.execute('INSERT INTO ai_objects VALUES(?,?,?,?,?,?)', (value['analysis_id'], sid, aid, result['result_id'], raw, hashlib.sha256(raw).hexdigest()))
            db.execute('UPDATE ai_requests SET analysis_id=? WHERE scan_id=? AND assessment_id=? AND key=? AND fingerprint=?', (value['analysis_id'], sid, aid, body.idempotency_key, fingerprint))
        return value


def configured_service(p2, budget_path, *, max_generations=20, intent_ceiling=None, continuous=False, public_sample_only=True):
    if p2.data_scope != 'TEST_ONLY' or not budget_path:
        raise RuntimeError('P2 AI requires isolated TEST_ONLY storage and a task budget path')
    store = AnalysisStore(p2.store.path.with_name('p2-ai.db')); store.initialize()
    options = {'continuous': True} if continuous else {}
    return P2AnalysisService(p2, store, BoundQwen(budget_path, max_generations=max_generations, intent_ceiling=intent_ceiling, **options), public_sample_only=public_sample_only)
