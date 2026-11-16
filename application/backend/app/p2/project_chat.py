"""Read-only project explanations, with writes confined to a private chat sidecar."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import stat
import fcntl
from contextlib import contextmanager

from pydantic import Field

from app.ai.project import context as formal_context, validate as validate_formal_answer
from app.ai.p2_analysis import material_quote_candidates
from app.ai.project_chat import BoundProjectQwen, ChatBudget, PROMPT_VERSION, PROMPT, output_schema
from app.ai.ollama import MODEL_NAME, MANIFEST_DIGEST, OLLAMA_VERSION
from .ai_analysis import validate_action_semantics
from .contract import Binding, DTO, ID, SHA, Material, P2Error, canonical, digest, strict_json
from .store import P2Store

VERSION = 'openguard-p2-project-chat/1'
USAGE_LABELS = (
    ('commercial', '涉及商业使用'), ('modified', '修改项目代码'),
    ('distributed', '向他人分发／交付'), ('network_service', '对外提供在线服务'),
    ('training', '用于模型训练'), ('redistributed_assets', '再分发模型／数据等资源'),
    ('source_disclosure', '计划公开源代码'),
)


def usage_fact(result):
    values = {True: '是', False: '否', None: '未知'}
    quote = '\n'.join(label + '：' + values[result['usage'][key]] for key, label in USAGE_LABELS)
    quote += '\n以上为本版保存的演示用途声明，不证明实际行为已经发生或完成。'
    return {'basis_id': 'result:' + result['result_sha256'] + ':usage', 'kind': 'result_fact',
            'label': f"保存用途 · 评估 v{result['binding']['assessment_version']} / 结果 r{result['revision']}",
            'resource_ids': [], 'quote': quote, 'verification_state': 'saved_declaration'}


class ChatRequest(DTO):
    binding: Binding
    result_id: ID
    result_sha256: SHA
    question: str = Field(min_length=1, max_length=2000)
    request_id: str = Field(min_length=8, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')


class ProjectChatStore(P2Store):
    def guard(self):
        if self.path.name != 'p2-project-chat.db':
            raise P2Error('p2_chat_storage_invalid', 503)
        for path in (self.path.parent, self.path):
            info = path.lstat()
            if (stat.S_ISLNK(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077
                    or path == self.path and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1)):
                raise P2Error('p2_chat_storage_invalid', 503)

    def initialize(self):
        # Factory only. GET never calls initialization or recovery writes.
        if not self.path.exists():
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        with self.connection(write=True) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS project_chat_turns(
                request_id TEXT PRIMARY KEY,scope_key TEXT NOT NULL,fingerprint TEXT NOT NULL,
                payload BLOB NOT NULL,sha256 TEXT NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS project_chat_audit(
                request_id TEXT PRIMARY KEY,scope_key TEXT NOT NULL,payload BLOB NOT NULL,sha256 TEXT NOT NULL)''')
        operations = self.path.parent / 'p2-chat-operations'
        operations.mkdir(mode=0o700, exist_ok=True)
        with self.connection() as db:
            rows = db.execute('SELECT payload,sha256 FROM project_chat_turns').fetchall()
        for row in rows:
            value = self.decode(row)
            if value['turn']['status'] != 'pending': continue
            try:
                with self.operation(value['turn']['request_id']):
                    with self.connection() as db:
                        latest = db.execute('SELECT payload,sha256 FROM project_chat_turns WHERE request_id=?',
                                            (value['turn']['request_id'],)).fetchone()
                    current = self.decode(latest)
                    if current is None or current['turn']['status'] != 'pending':
                        continue  # A live operation may have completed before the lock was obtained.
                    self.finish(value['scope'], value['turn']['request_id'], error='p2_chat_interrupted_outcome_unknown')
                    with self.connection() as db:
                        audit_row = db.execute('SELECT payload,sha256 FROM project_chat_audit WHERE request_id=?',
                                               (value['turn']['request_id'],)).fetchone()
                    if audit_row:
                        audit = self.decode(audit_row)
                        audit.update(outcome='INTERRUPTED_OUTCOME_UNKNOWN_NO_RETRY', validation_error='process_interrupted')
                        self.audit(value['scope'], value['turn']['request_id'], audit)
            except P2Error as exc:
                if exc.code != 'p2_chat_busy': raise

    @contextmanager
    def operation(self, request_id):
        directory = self.path.parent / 'p2-chat-operations'
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise P2Error('p2_chat_storage_invalid', 503)
        name = hashlib.sha256(request_id.encode()).hexdigest() + '.lock'
        fd = os.open(directory / name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            ChatBudget._fd(fd)
            try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: raise P2Error('p2_chat_busy', 503) from None
            yield
        finally: os.close(fd)

    def audit(self, scope, request_id, value):
        raw = canonical(value)
        with self.connection(write=True) as db:
            db.execute('INSERT OR REPLACE INTO project_chat_audit VALUES(?,?,?,?)',
                       (request_id, digest(scope), raw, hashlib.sha256(raw).hexdigest()))

    def history(self, scope):
        with self.connection() as db:
            rows = db.execute('SELECT payload,sha256 FROM project_chat_turns WHERE scope_key=? ORDER BY rowid',
                              (digest(scope),)).fetchall()
        values = [self.decode(row) for row in rows]
        if any(value['scope'] != scope for value in values):
            raise P2Error('p2_chat_integrity_error', 503)
        return [value['turn'] for value in values]

    def reserve(self, scope, body):
        fingerprint = digest(body.model_dump())
        with self.connection(write=True) as db:
            old = db.execute('SELECT fingerprint,payload,sha256 FROM project_chat_turns WHERE request_id=?',
                             (body.request_id,)).fetchone()
            if old:
                if old[0] != fingerprint:
                    raise P2Error('p2_chat_idempotency_conflict', 409)
                self.decode(old[1:])
                return False
            rows = db.execute('SELECT payload,sha256 FROM project_chat_turns WHERE scope_key=?',
                              (digest(scope),)).fetchall()
            if len(rows) >= 50 or db.execute('SELECT count(*) FROM project_chat_turns').fetchone()[0] >= 1000:
                raise P2Error('p2_chat_capacity_exceeded', 413)
            if any(self.decode(row)['turn']['status'] == 'pending' for row in rows):
                raise P2Error('p2_chat_pending_confirmation', 409)
            turn = {'request_id': body.request_id, 'question': body.question,
                    'status': 'pending', 'answer': None, 'citations': [], 'error_code': None,
                    'created_at': datetime.now(timezone.utc).isoformat()}
            raw = canonical({'scope': scope, 'turn': turn})
            db.execute('INSERT INTO project_chat_turns VALUES(?,?,?,?,?)',
                       (body.request_id, digest(scope), fingerprint, raw, hashlib.sha256(raw).hexdigest()))
        return True

    def finish(self, scope, request_id, *, result=None, error=None):
        with self.connection(write=True) as db:
            row = db.execute('SELECT payload,sha256 FROM project_chat_turns WHERE request_id=? AND scope_key=?',
                             (request_id, digest(scope))).fetchone()
            value = self.decode(row)
            if value is None or value['scope'] != scope or value['turn']['status'] != 'pending':
                raise P2Error('p2_chat_binding_conflict', 409)
            value['turn'].update(status='failed' if error else 'succeeded',
                answer=None if error else result['answer'], citations=[] if error else result['citations'], error_code=error)
            raw = canonical(value)
            db.execute('UPDATE project_chat_turns SET payload=?,sha256=? WHERE request_id=?',
                       (raw, hashlib.sha256(raw).hexdigest(), request_id))


def validate_usage_prose(answer, usage):
    """Known false usage/completion claims fail closed; no claim of full NLP proof."""
    targets = {
        'commercial': r'商业使用|商业用途|商用|非商业',
        'modified': r'修改(?:项目)?代码|修改源码|代码修改|二次开发',
        'distributed': r'对外交付|向他人分发|分发|交付',
        'network_service': r'在线服务|网络服务|对外服务|SaaS',
        'training': r'模型训练|训练模型|训练用途',
        'redistributed_assets': r'资源再分发|再分发(?:模型|数据|资源)',
        'source_disclosure': r'公开源码|公开源代码|开源发布',
    }
    for sentence in re.split(r'[，,。；;！!？?\n]', answer):
        if not sentence.strip(): continue
        # A saved intention alone never establishes completed real-world acts.
        for completed in re.finditer(r'(?:已经|已)(?:对外|向客户|向他人)?(?:交付|分发|发布|上线|公开|完成训练|训练完成|履行义务|保留声明)', sentence):
            prefix = sentence[:completed.start()]
            # Negation must immediately govern this completion claim. It cannot
            # license a later affirmative claim or a double-negative assertion.
            unproven = re.search(r'未被证实\s*$', prefix)
            if unproven and re.search(r'(?:并非|不是|并不是|不能说|不代表)\s*$', prefix[:unproven.start()]):
                raise ValueError('p2_chat_unverified_completion')
            if not unproven and not re.search(r'不代表|不等(?:同)?于|并非|不能(?:认定|确认|说明|证明)|未确认', prefix):
                raise ValueError('p2_chat_unverified_completion')
        if re.match(r'\s*(?:如果|假设|若(?:后续|将来|计划|要|你|您)|需要确认|需确认)', sentence):
            continue
        for field, target in targets.items():
            if not re.search(target, sentence): continue
            negative = re.search(r'(?:未(?:选择|声明|计划|涉及)|没有(?:选择|声明|计划)|不(?:涉及|计划|选择|进行)|暂不).{0,12}(?:' + target + ')', sentence)
            if field == 'commercial' and re.search(r'(?:选择|声明|用途|用于).{0,8}非商业|当前.{0,8}非商业', sentence):
                negative = True
            if negative and usage[field] is True:
                raise ValueError('p2_chat_usage_contradiction')
            positive = re.search(r'(?:当前|目前|本次|你|您|用户).{0,15}(?:已(?:经)?选择|已声明|选择了|声明了|计划|用途为|用于|涉及).{0,12}(?:' + target + ')', sentence)
            if positive and not negative and usage[field] is not True:
                raise ValueError('p2_chat_usage_contradiction')


def validate_answer(raw, payload, guard):
    if not isinstance(raw, str) or len(raw.encode()) > 65536:
        raise ValueError('p2_chat_output_rejected')
    value = strict_json(raw)
    if (not isinstance(value, dict) or set(value) != {'result_id', 'result_sha256', 'usage_echo', 'answer', 'citations'}
            or value['result_id'] != payload['scope']['result_id']
            or value['result_sha256'] != payload['scope']['result_sha256']
            or not isinstance(value['usage_echo'], dict) or set(value['usage_echo']) != set(payload['usage'])
            or any(type(v) not in (bool, type(None)) for v in value['usage_echo'].values())
            or value['usage_echo'] != payload['usage']
            or not isinstance(value['citations'], list) or len(value['citations']) > 4):
        raise ValueError('p2_chat_output_rejected')
    sources = {item['basis_id']: item for item in payload['evidence']}
    if sources and not value['citations']:
        raise ValueError('p2_chat_citation_required')
    seen = set()
    for citation in value['citations']:
        if (not isinstance(citation, dict) or set(citation) != {'basis_id', 'quote'}
                or not isinstance(citation['basis_id'], str) or citation['basis_id'] not in sources
                or citation['basis_id'] in seen or citation['quote'] != sources[citation['basis_id']]['quote']):
            raise ValueError('p2_chat_citation_rejected')
        seen.add(citation['basis_id'])
    # Reuse existing output/unknown-is-not-prohibition guards without granting
    # model text the ability to change Formal Assessment or any P2 state.
    guard = dict(guard)
    guard['evidence'] = [{'id': item['basis_id'], 'kind': 'license_text' if item['kind'] == 'material' else 'metadata'}
                         for item in payload['evidence']]
    validate_formal_answer(json.dumps({'assessment_id': guard['assessment_id'], 'state_digest': guard['state_digest'],
        'answer': value['answer'], 'evidence_ids': list(seen)}, ensure_ascii=False), json.dumps(guard, ensure_ascii=False))
    validate_action_semantics(value['answer'], payload['usage'], [])
    validate_usage_prose(value['answer'], payload['usage'])
    for sentence in re.split(r'[。；;\n]', value['answer']):
        every_file = re.search(r'(?:所有|每(?:一)?(?:个|份)?).{0,18}(?:代码文件|源码文件|源文件|修改后代码|文件)'
                               r'.{0,18}(?:包含|保留|附带|添加|加入|放置|标注|注明).{0,15}(?:版权|许可|声明)', sentence)
        if (every_file and not re.search(r'哪些|是否', every_file.group())
                and not re.search(r'不代表|不等于|不能要求|并非|未规定|未指定', sentence[max(0, every_file.start()-16):every_file.start()])):
            raise ValueError('p2_chat_each_file_obligation_unsupported')
        identical_location = re.search(
            r'(?:位置|文件头|页首).{0,12}(?:需|必须|应|要).{0,25}(?:LICENSE(?:\.TXT)?|原文|许可(?:证)?材料).{0,20}(?:一致|相同)'
            r'|(?:需|必须|应).{0,20}(?:原文|LICENSE(?:\.TXT)?).{0,15}(?:相同|同一).{0,8}(?:位置|文件头)', sentence, re.I)
        if (identical_location and not re.search(r'不代表|不等于|不能要求|并非|未规定|未指定',
                sentence[max(0, identical_location.start()-16):identical_location.start()])):
            raise ValueError('p2_chat_statement_location_unsupported')
    has_license_body = any(
        (source['kind'] == 'material' or source['kind'] == 'scan_evidence' and source.get('label') == 'license_text')
        and len(source['quote'].strip()) >= 40
        and (len(re.findall(r'[A-Za-z]{2,}', source['quote'])) >= 6 or len(re.findall(r'[\u4e00-\u9fff]', source['quote'])) >= 12)
        for source in payload['evidence'])
    if not has_license_body:
        for sentence in re.split(r'[，,。；;\n]', value['answer']):
            claim = re.search(r'(?:许可(?:证|条款)?|条款|MIT|Apache|GPL|BSD|MPL).{0,30}(?:要求|允许|豁免|免除|义务|限制|无需|不必|必须)'
                              r'|(?:无需|不必|免于).{0,10}(?:交付源码|公开源码|公开源代码|保留声明|履行义务)', sentence, re.I)
            if claim and not re.search(r'无法判断|不能判断|不能确认|无法确认|不足以判断|不能据此|不代表|不等于|尚不清楚', sentence[:claim.end()]):
                raise ValueError('p2_chat_license_body_required')
    for source in payload['evidence']:
        filename = source.get('uploaded_filename')
        if source['kind'] != 'material' or not filename or source.get('upstream_path') is not None:
            continue
        for sentence in re.split(r'[，,。；;\n]', value['answer']):
            claim = re.search(r'(?:项目根|仓库根|根目录|上游路径).{0,40}' + re.escape(filename)
                              + '|' + re.escape(filename) + r'.{0,20}(?:位于|就是|是|来自).{0,10}(?:项目根|仓库根|根目录|上游路径)', sentence, re.I)
            if claim and not re.search(r'不能证明|不能确认|不代表|不等于|并非|无法确认|尚未确认|不能据此', sentence[max(0, claim.start()-16):claim.start()]):
                raise ValueError('p2_chat_upload_name_is_not_source_path')
    if re.search(r'(?:允许|可直接|可以直接)(?:商业使用|分发)|(?:来源可信|义务已履行|许可有效|授权有效)', value['answer']):
        raise ValueError('p2_chat_semantic_rejected')
    return value


def select_scan_evidence(items, result_resources, resources, project_name, material_resources):
    """Project/material binding ranks candidates; identifiers never rank meaning.

    This only selects existing literal excerpts. It does not modify source
    records, verification states, or the saved Result's evidence relationships.
    """
    root_resources = {identity for identity, resource in resources.items()
                      if resource.name.strip().casefold() == project_name.strip().casefold()}
    selected = []
    for order, item in enumerate(items):
        quote = (item.excerpt or '')[:500]
        if (not quote.strip() or re.fullmatch(r'[\s\"\x27`~^<>=vV0-9.*xX|+\-]+', quote)
                or re.fullmatch(r'[\"\x27]?https?://\S+[\"\x27]?', quote.strip(), re.I)):
            continue  # Bare versions and download URLs do not explain an action.
        linked = sorted(row['subject']['resource_id'] for row in result_resources if item.id in row['evidence_ids'])
        if not linked: continue
        priority = 0 if material_resources.intersection(linked) else 1 if root_resources.intersection(linked) else 2
        if priority == 2 and (len(quote.strip()) < 40 or len(re.findall(r'[A-Za-z\u4e00-\u9fff]{2,}', quote)) < 3):
            continue
        selected.append(((priority, item.kind.value != 'license_text', order), item, linked))
    return [(item, linked) for _, item, linked in sorted(selected, key=lambda row: row[0])[:8]]


def revalidated_history(history, payload, guard, run, result):
    """Project old successful answers through current guards without rewriting them.

    Previous exact citations may be absent from the improved model selection.
    Reconstruct those only for validation; they never expand new model evidence.
    """
    excerpts = []
    scan_evidence = {item.id: item for item in run.evidence}
    for turn in [row for row in history if row['status'] == 'succeeded'][-2:]:
        excerpt = {'question_excerpt': turn['question'][:160]}
        try:
            basis = {item['basis_id']: item for item in payload['evidence']}
            for citation in turn['citations']:
                identity = citation['basis_id']
                if identity in basis: continue
                source = scan_evidence.get(identity)
                linked = sorted(row['subject']['resource_id'] for row in result['resources'] if identity in row['evidence_ids'])
                if source is None or not linked or citation['quote'] != (source.excerpt or '')[:500]:
                    raise ValueError('historical_basis_not_bound')
                basis[identity] = {'basis_id': identity, 'kind': 'scan_evidence', 'label': source.kind.value,
                    'resource_ids': linked, 'quote': citation['quote'], 'verification_state': source.verification_status.value}
            candidate = {'result_id': payload['scope']['result_id'], 'result_sha256': payload['scope']['result_sha256'],
                         'usage_echo': payload['usage'], 'answer': turn['answer'], 'citations': turn['citations']}
            validate_answer(canonical(candidate).decode(), {**payload, 'evidence': list(basis.values())}, guard)
            excerpt['answer_excerpt'] = turn['answer'][:300]
        except (ValueError, TypeError, KeyError):
            excerpt.update(answer_omitted=True,
                history_note='此前答复未通过当前依据和用途校验，不能作为事实。仅承接这个问题，依据本轮固定材料重新回答。')
        excerpts.append(excerpt)
    return excerpts


class ProjectChatService:
    def __init__(self, p2, store, provider=None, budget=None):
        self.p2, self.store, self.provider, self.budget = p2, store, provider, budget

    def _context(self, sid, aid, rid, version):
        result = self.p2.read(sid, aid, rid, version)
        run, assessment, binding, resources = self.p2.context(sid, aid)
        if result['binding'] != binding:
            raise P2Error('p2_chat_binding_conflict', 409)
        scope = {'binding': binding, 'result_id': rid, 'result_revision': result['revision'],
                 'result_sha256': result['result_sha256']}
        evidence = [usage_fact(result)]
        material_resources = set()
        with self.p2.store.connection() as db:
            for mid in result['material_ids'][:4]:
                material = Material.model_validate(self.p2.store.get(db, 'material', mid, sid, aid)).model_dump(mode='json')
                row = next((r for r in result['resources'] if r['subject'] == material['subject']), None)
                if (material['binding'] != binding or material['data_scope'] != result['data_scope']
                        or row is None or mid not in row['material_ids']
                        or not set(material['evidence_ids']) <= set(row['evidence_ids'])):
                    raise P2Error('p2_chat_material_binding_conflict', 409)
                raw = self.p2.store.material_bytes(db, material)
                try: text = raw.decode('utf-8-sig')
                except UnicodeError: raise P2Error('p2_chat_material_text_invalid', 422) from None
                resource = resources.get(material['subject']['resource_id'])
                material_resources.add(material['subject']['resource_id'])
                for number, quote in enumerate(material_quote_candidates(text)[:3]):
                    evidence.append({'basis_id': mid + ':quote:' + str(number), 'kind': 'material',
                        'label': (resource.name if resource else material['subject']['resource_id']) + ' · 本版保存的 LICENSE / NOTICE 材料（上传名：' + material['filename'] + '）',
                        'resource_ids': [material['subject']['resource_id']], 'quote': quote, 'verification_state': 'pending',
                        'subject': material['subject'], 'source_level': material['source_level'],
                        'source_sha256': material['source_sha256'], 'completeness': material['completeness'],
                        'uploaded_filename': material['filename'], 'upstream_path': None})
        for item, resource_ids in select_scan_evidence(run.evidence, result['resources'], resources,
                                                      assessment.project_name, material_resources):
            quote = (item.excerpt or '')[:500]
            evidence.append({'basis_id': item.id, 'kind': 'scan_evidence', 'label': item.kind.value,
                'resource_ids': resource_ids,
                'quote': quote, 'verification_state': item.verification_status.value})
        context = {'project_name': assessment.project_name, 'usage': result['usage'],
                   'resource_count': len(result['resources']), 'material_count': len(result['material_ids']), 'evidence': evidence}
        return scope, context, run, assessment, result, resources

    def snapshot(self, sid, aid, version, rid):
        scope, context, run, _, result, _ = self._context(sid, aid, rid, version)
        history = self.store.history(scope)
        shown = {row['basis_id'] for row in context['evidence']}
        sources = {item.id: item for item in run.evidence}
        # A better model selection must not hide or rewrite earlier citations.
        # Restore only exact historical excerpts still bound to this Result;
        # send() continues to consume the narrower _context() selection.
        for turn in history:
            for citation in turn['citations']:
                identity = citation['basis_id']
                if identity in shown: continue
                item = sources.get(identity)
                linked = sorted(row['subject']['resource_id'] for row in result['resources'] if identity in row['evidence_ids'])
                if item is None or not linked or citation['quote'] != (item.excerpt or '')[:500]:
                    raise P2Error('p2_chat_history_evidence_conflict', 409)
                context['evidence'].append({'basis_id': identity, 'kind': 'scan_evidence', 'label': item.kind.value,
                    'resource_ids': linked, 'quote': citation['quote'], 'verification_state': item.verification_status.value})
                shown.add(identity)
        used = self.budget.usage() if self.budget else 0
        maximum = self.budget.maximum if self.budget else 8
        return {'schema_version': VERSION, 'scope': scope, 'context': context, 'items': history,
                'limits': {'max_question_chars': 2000, 'max_turns': 50, 'max_model_calls': maximum,
                           'used_model_calls': used, 'remaining_model_calls': max(0, maximum-used)}, 'formal_effect': 'none'}

    def send(self, sid, aid, body):
        if not body.question.strip(): raise P2Error('p2_chat_question_invalid', 422)
        scope, context, run, assessment, result, resources = self._context(sid, aid, body.result_id, body.binding.assessment_version)
        if body.binding.model_dump() != scope['binding'] or body.result_sha256 != scope['result_sha256']:
            raise P2Error('p2_chat_binding_conflict', 409)
        # Idempotent recovery is valid even if model configuration later changes.
        with self.store.connection() as db:
            old = db.execute('SELECT fingerprint FROM project_chat_turns WHERE request_id=?', (body.request_id,)).fetchone()
        if old:
            if old[0] != digest(body.model_dump()): raise P2Error('p2_chat_idempotency_conflict', 409)
            return self.snapshot(sid, aid, body.binding.assessment_version, body.result_id)
        if self.provider is None: raise P2Error('p2_chat_disabled', 503)
        history = self.store.history(scope)
        # This object is used only by the existing answer validator. The full
        # free-form question belongs to the new bounded payload below, not to a
        # second, unused legacy model prompt with its separate 12 KiB budget.
        try: guard = json.loads(formal_context(run, assessment, '', []))
        except ValueError: raise P2Error('p2_chat_input_too_large', 413) from None
        guard['selected_resources'] = [{'scope': row['scope']} for row in result['resources']]
        advice_catalog, advice_sha256, advice_keys = {}, {}, {}
        def advice_refs(row):
            refs = []
            for advice in row['advice']:
                content_sha256 = digest(advice)
                identity = advice_keys.setdefault(content_sha256, 'saved_advice_' + str(len(advice_keys) + 1))
                advice_catalog[identity] = advice
                advice_sha256[identity] = content_sha256
                refs.append(identity)
            return refs
        payload = {'schema_version': PROMPT_VERSION, 'request_id': body.request_id, 'scope': scope, 'project_name': context['project_name'],
            'usage': result['usage'], 'usage_assumption': 'DEMO_USAGE_ASSUMPTION', 'formal_state': guard['formal_state'],
            'state_counts': dict(Counter(row['state'] for row in result['resources'])),
            'resources': [{'subject': row['subject'], 'name': resources[row['subject']['resource_id']].name,
                'scope': row['scope'], 'state': row['state'], 'gaps': row['gaps'], 'user_assertions': row['user_assertions'],
                'saved_advice_refs': advice_refs(row)}
                for row in result['resources']],
            'evidence': context['evidence'], 'evidence_total': len(run.evidence), 'material_total': len(result['material_ids']),
            'saved_advice_catalog': advice_catalog,
            'saved_advice_content_sha256': advice_sha256,
            'history': [], 'question': body.question}
        payload['history'] = revalidated_history(history, payload, guard, run, result)
        if len(canonical(payload)) > 32000: raise P2Error('p2_chat_input_too_large', 413)
        with self.store.operation(body.request_id):
            if not self.store.reserve(scope, body): return self.snapshot(sid, aid, body.binding.assessment_version, body.result_id)
            self._generate(scope, body, payload, guard)
        return self.snapshot(sid, aid, body.binding.assessment_version, body.result_id)

    def _generate(self, scope, body, payload, guard):
        audit = {'input': payload, 'input_sha256': digest(payload), 'system': PROMPT, 'schema': output_schema(payload),
                 'system_sha256': hashlib.sha256(PROMPT.encode()).hexdigest(), 'schema_sha256': digest(output_schema(payload)),
                 'model': {'name': MODEL_NAME, 'digest': MANIFEST_DIGEST, 'runtime': 'ollama/' + OLLAMA_VERSION},
                 'raw_response': None, 'raw_response_sha256': None, 'metrics': {}, 'validation_error': None,
                 'outcome': 'PENDING_NO_COMPLETION_CLAIM'}
        self.store.audit(scope, body.request_id, audit)
        try:
            raw = self.provider.generate(payload)
            audit.update(raw_response=raw, raw_response_sha256=hashlib.sha256(raw.encode()).hexdigest(),
                         metrics=getattr(self.provider, 'last_metrics', {}), outcome='RAW_SAVED_NOT_YET_VALIDATED')
            self.store.audit(scope, body.request_id, audit)
            value = validate_answer(raw, payload, guard)
            audit['outcome'] = 'VALIDATED'; self.store.audit(scope, body.request_id, audit)
            self.store.finish(scope, body.request_id, result=value)
        except Exception as exc:
            code = exc.code if isinstance(exc, P2Error) else 'p2_chat_output_rejected' if isinstance(exc, (ValueError, TypeError, KeyError)) else 'p2_chat_model_unavailable'
            audit.update(outcome='FAILED_NO_RETRY', validation_error=str(exc) if isinstance(exc, (ValueError, P2Error)) else type(exc).__name__,
                         metrics=getattr(self.provider, 'last_metrics', {}))
            self.store.audit(scope, body.request_id, audit)
            self.store.finish(scope, body.request_id, error=code)


def configured_service(p2, data_dir):
    enabled = os.environ.get('OPENGUARD_ENABLE_P2_CHAT', '0')
    if enabled not in {'0', '1'}: raise RuntimeError('invalid project chat configuration')
    store = ProjectChatStore(data_dir / 'p2-project-chat.db'); store.initialize()
    provider = budget = None
    if enabled == '1':
        path = os.environ.get('OPENGUARD_P2_CHAT_BUDGET_PATH')
        if not path or p2.data_scope != 'TEST_ONLY':
            raise RuntimeError('Project chat requires explicit independent TEST_ONLY budget')
        budget = ChatBudget(path, int(os.environ.get('OPENGUARD_P2_CHAT_MAX_GENERATIONS', '8')))
        provider = BoundProjectQwen(budget, os.environ.get('OPENGUARD_P2_CHAT_ORIGIN', 'http://127.0.0.1:11434'), data_dir / 'p2-chat-model-audit')
    return ProjectChatService(p2, store, provider, budget)
