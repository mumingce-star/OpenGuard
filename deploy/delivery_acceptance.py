"""F01/F04/F06 isolated real HTTP acceptance. No server lifecycle or database access.

prepare only writes self-authored ZIP inputs; run requires explicit --allow-test-writes.
verify only re-downloads recorded immutable artifact URLs, including after an approved restart.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

ORIGIN = 'http://127.0.0.1:8086'
PREFIX = '/api/v1/scans'
QUESTIONS = ['当前结论的依据是什么？请引用本次扫描证据。', '还缺什么材料，哪些事实尚未确认？', '下一步优先处理哪三项核验，为什么？']

def sha(data):
    return hashlib.sha256(data).hexdigest()

def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

class Acceptance:
    def __init__(self, output):
        self.output = output
        self.record = json.loads((output / 'receipt.json').read_text(encoding='utf-8'))

    def checkpoint(self):
        save(self.output / 'receipt.json', self.record)

    def request(self, path, method='GET', value=None, raw=None, content_type=None, expected=200):
        if not path.startswith('/api/v1/'):
            raise ValueError('Unexpected API path')
        body = json.dumps(value, ensure_ascii=False).encode() if value is not None else raw
        event = dict(path=path, method=method, status='pending', request_sha256=sha(body) if body else None)
        self.record['http'].append(event)
        self.checkpoint()  # A lost write response remains pending; never silently repeat.
        headers = {'Content-Type': content_type or 'application/json'} if body is not None else {}
        request = urllib.request.Request(ORIGIN + path, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data, status = response.read(), response.status
        except urllib.error.HTTPError as error:
            data, status = error.read(), error.code
        event.update(status=status, response_sha256=sha(data))
        self.checkpoint()
        if status != expected:
            raise RuntimeError(f'{method} {path}: HTTP {status}, expected {expected}; preserve receipt, do not blindly resubmit')
        return data

    def json(self, path, **kwargs):
        return json.loads(self.request(path, **kwargs))

    def artifact(self, path, name):
        data = self.request(path)
        (self.output / name).write_bytes(data)
        self.record['artifacts'].append(dict(path=path, file=name, sha256=sha(data), bytes=len(data)))
        self.checkpoint()
        return data

    def scan(self, stage):
        raw = (self.output / (stage + '.zip')).read_bytes()
        assert sha(raw) == self.record['inputs'][stage]['sha256']
        boundary = 'openguard-' + uuid.uuid4().hex
        parts = []
        for key, value in [('source_type', 'zip'), ('idempotency_key', self.record['run_id'] + '-' + stage), ('usage', '{"preset":"internal"}')]:
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        parts.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="delivery-{stage}.zip"\r\nContent-Type: application/zip\r\n\r\n'.encode(), raw, f'\r\n--{boundary}--\r\n'.encode()])
        accepted = self.json(PREFIX, method='POST', raw=b''.join(parts), content_type='multipart/form-data; boundary=' + boundary, expected=202)
        sid = accepted['scan_id']
        self.record[stage] = dict(scan_id=sid)
        self.checkpoint()
        start = time.monotonic()
        while True:
            state = self.json(PREFIX + '/' + sid)
            self.record[stage]['terminal'] = state
            self.checkpoint()
            if state['status'] not in ('queued', 'running'):
                break
            if time.monotonic() - start > 600:
                raise TimeoutError('Scan observation exceeded 600 seconds; task retained, no replay')
            time.sleep(1)
        assert state['status'] in ('completed', 'partial'), state
        base = PREFIX + '/' + sid
        self.json(base + '/resources'); self.json(base + '/risks')
        report = json.loads(self.artifact(base + '/report?format=json&download=true', stage + '-p0.json'))
        run = report['scan_run']
        assert run['provenance']['input_digest']['value'] == sha(raw)
        for evidence in run['evidence']:
            self.json(base + '/evidence/' + evidence['id'])
        for format in ('html', 'csv', 'resource_inventory'):
            self.artifact(base + '/report?format=' + format + '&download=true', stage + '-p0-' + format + ('.html' if format == 'html' else '.csv'))
        assessment_start = time.monotonic()
        while True:
            listing = self.json(base + '/assessments')
            if listing['items']:
                assessment = listing['items'][0]
                break
            if time.monotonic() - assessment_start > 120:
                raise TimeoutError('Expected terminal-observer assessment missing; no GET-generated substitute')
            time.sleep(1)
        self.record[stage]['assessment_id'] = assessment['id']
        self.record[stage]['assessment_version'] = assessment['version']
        self.checkpoint()
        return run, assessment

    def snapshot(self, stage, assessment, tasks, label):
        base = PREFIX + '/' + self.record[stage]['scan_id'] + '/assessments/' + assessment['id']
        body = dict(idempotency_key=self.record['run_id'] + '-' + label, task_refs=[dict(task_id=t['task_id'], version=t['version']) for t in tasks], notice_refs=[], algorithm_refs=[])
        snapshot = self.json(base + '/report-v2', method='POST', value=body)
        replay = self.json(base + '/report-v2', method='POST', value=body)
        assert replay == snapshot
        self.record[label] = snapshot
        for format in ('json', 'html'):
            self.artifact(base + '/report-v2/' + snapshot['snapshot_id'] + '?format=' + format, label + '.' + format)

    def run(self, p2=False, ai=False):
        if self.record['http']:
            raise ValueError('This prepared receipt already has requests. Review pending writes; do not rerun blindly.')
        self.record['status'] = 'RUNNING'
        before, a = self.scan('before')
        base = PREFIX + '/' + before['id'] + '/assessments/' + a['id'] + '/remediation-tasks'
        derived = self.json(base + '/derive', method='POST', value=dict(idempotency_key=self.record['run_id'], expected_facts_hash=a['facts_hash']))
        tasks = derived['items']
        requests = [c for c in before['components'] if c['name'].lower() == 'requests']
        assert requests
        task = next((t for t in tasks if requests[0]['id'] in t['resource_ids'] and t['origin']['kind'] in ('gap', 'next_step') and '版本' in t['title']), None)
        assert task is not None, 'No actual version-related task; do not fabricate a task or mark F04 passed'
        self.record['task_before'] = task
        self.snapshot('before', a, tasks, 'before-fixed-report')
        patch = dict(expected_version=task['version'], status='in_progress', note='准备手动明确 requests 版本；第三方许可及适用性仍待核验。')
        updated = self.json(base + '/' + task['task_id'], method='PATCH', value=patch)
        self.json(base + '/' + task['task_id'], method='PATCH', value=patch, expected=409)
        after, b = self.scan('after')
        target = PREFIX + '/' + after['id']
        diff = self.json(target + '/diff?base_scan_id=' + before['id'] + '&base_assessment_id=' + a['id'] + '&target_assessment_id=' + b['id'] + '&confirm_zip_pair=true')
        save(self.output / 'diff.json', diff)
        assert any(field['path'] == '/resources/version' and field['after'] == '2.32.3' for item in diff['resources'] for field in item['field_changes']), 'Expected observed exact-version improvement missing'
        note = '已手动将 requests>=2.32.3 改为 requests==2.32.3 并真实复扫：' + after['id'] + '。仅版本声明明确，许可证及适用性仍待核验，任务保留处理中。'
        self.record['task_after'] = self.json(base + '/' + task['task_id'], method='PATCH', value=dict(expected_version=updated['version'], status='in_progress', note=note))
        new_tasks = self.json(target + '/assessments/' + b['id'] + '/remediation-tasks/derive', method='POST', value=dict(idempotency_key=self.record['run_id'] + '-after', expected_facts_hash=b['facts_hash']))['items']
        self.snapshot('after', b, new_tasks, 'after-fixed-report')
        fixed = self.json(PREFIX + '/' + before['id'] + '/assessments/' + a['id'])
        assert fixed == a, 'Task updates changed original Formal Assessment'
        if p2:
            pbase = target + '/assessments/' + b['id'] + '/p2'
            binding = self.json(pbase + '/binding?assessment_version=' + str(b['version']))
            body = dict(binding=binding, expected_revision=0, parent_result_id=None, idempotency_key=self.record['run_id'])
            saved = self.json(pbase + '/results', method='POST', value=body, expected=201)
            assert self.json(pbase + '/results', method='POST', value=body, expected=201) == saved
            self.json(pbase + '/results', method='POST', value={**body, 'expected_revision':1}, expected=409)
            result = saved['result']
            assert result['data_scope'] == 'TEST_ONLY' and result['model_calls'] == 0
            summary = self.json(pbase + '/results/' + result['result_id'] + '/summary?assessment_version=' + str(b['version']))
            assert summary['resource_states'] == {r['subject']['resource_id']:r['state'] for r in result['resources']}
            self.record['p2'] = saved
        if ai:
            self.record['ai_questions'] = QUESTIONS
            chat = self.json(target + '/chat')
            for i, question in enumerate(QUESTIONS):
                request_id = self.record['run_id'] + '-qa-' + str(i)
                self.json(target + '/chat', method='POST', value=dict(assessment_id=b['id'], request_id=request_id, message=question, generation=chat['generation']), expected=202)
                start = time.monotonic()
                while True:
                    chat = self.json(target + '/chat')
                    turn = next(t for t in chat['items'] if t['request_id'] == request_id)
                    if turn['status'] != 'pending': break
                    if time.monotonic()-start > 90: raise TimeoutError('Chat remained pending; no automatic resend')
                    time.sleep(1)
                assert turn['status']=='succeeded', turn
                for eid in turn['evidence_ids']: self.json(target + '/evidence/' + eid)
            save(self.output / 'chat.json', chat)
        self.verify()
        self.record['status'] = 'HTTP_PASSED_BROWSER_AND_RESTART_PENDING'
        self.checkpoint()

    def verify(self):
        for item in self.record['artifacts']:
            assert sha(self.request(item['path'])) == item['sha256'], item['path']
        self.record['last_readback'] = dict(at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), artifacts=len(self.record['artifacts']), byte_equal=True)
        self.checkpoint()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare','run','verify'])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-test-writes', action='store_true')
    parser.add_argument('--p2', action='store_true')
    parser.add_argument('--ai', action='store_true')
    args=parser.parse_args()
    if args.action=='prepare':
        args.output.mkdir(parents=True, exist_ok=False)
        sample=Path(__file__).resolve().parents[1]/'examples'/'delivery-remediation'
        inputs={}
        for stage in ('before','after'):
            buffer=io.BytesIO()
            with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as archive:
                for file in sorted((sample/stage).iterdir()):
                    info=zipfile.ZipInfo(file.name, date_time=(2026,10,22,0,0,0))
                    archive.writestr(info,file.read_bytes())
            raw=buffer.getvalue();(args.output/(stage+'.zip')).write_bytes(raw)
            inputs[stage]=dict(sha256=sha(raw),bytes=len(raw))
        save(args.output/'receipt.json',dict(status='PREPARED_NOT_RUN',origin=ORIGIN,run_id='delivery-'+uuid.uuid4().hex,inputs=inputs,http=[],artifacts=[]))
    elif args.action=='run':
        if not args.allow_test_writes: parser.error('run requires --allow-test-writes and external operator authorization for the isolated deployment')
        Acceptance(args.output).run(args.p2,args.ai)
    else:
        run=Acceptance(args.output)
        if not run.record['artifacts']: parser.error('No saved artifact exists to verify')
        run.verify()
    print(args.action+' complete; receipt: '+str(args.output/'receipt.json'))

if __name__=='__main__':
    main()
