#!/usr/bin/env python3
"""Bounded real HTTP examples for a seeded synthetic P1 instance; no scans/AI.

--verify reads an existing receipt after restart, without POST or PATCH.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request
import urllib.error
import urllib.parse
import re

IDENTITY_HEADER = 'X-OpenGuard-Dev-Identity'


def instance_identity(value):
    identity = {key: value.get(key) for key in ('root_id', 'synthetic', 'seed_version')}
    if (identity['synthetic'] is not True or identity['seed_version'] != 'p1-dev-integration/2'
            or not isinstance(identity['root_id'], str)
            or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', identity['root_id'])):
        raise ValueError('invalid development identity')
    return identity


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('HTTP redirect refused; instance identity cannot be assumed')


def local_url(value):
    url = urllib.parse.urlsplit(value)
    if url.scheme != 'http' or url.hostname not in {'127.0.0.1', 'localhost'} or url.username or url.password or url.path or url.query or url.fragment or not url.port:
        raise ValueError('explicit loopback base URL required, without trailing slash/path')
    if url.port in {8000, 8011, 8080, 5174}:
        raise ValueError('existing service ports are forbidden')
    return value


class Client:
    def __init__(self, base, origin, manifest=None):
        self.base, self.origin = local_url(base), local_url(origin)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.events = []
        self.manifest_identity = instance_identity(manifest) if manifest is not None else None
        self.observed_identity = None

    def bind(self):
        if self.manifest_identity is None:
            raise ValueError('manifest identity required')
        self.call('GET', '/api/v1/scans?limit=1')

    def identity_receipt(self):
        return {'base': self.base, 'origin': self.origin,
                'manifest_identity': self.manifest_identity, 'observed_identity': self.observed_identity}

    def call(self, method, path, body=None, expected=200):
        parsed = urllib.parse.urlsplit(path)
        if (not path.startswith('/api/v1/') or parsed.netloc or parsed.scheme or parsed.fragment
                or '\\' in path or any(ord(c) < 32 for c in path)):
            raise ValueError('only relative API paths are accepted')
        if method not in {'GET', 'POST', 'PATCH'}:
            raise ValueError('unsupported method')
        if method != 'GET' and (self.manifest_identity is None or self.observed_identity != self.manifest_identity):
            raise ValueError('remote identity must be verified before writes')
        site = ('same-origin' if self.base == self.origin else
                'same-site' if urllib.parse.urlsplit(self.base).hostname == urllib.parse.urlsplit(self.origin).hostname
                else 'cross-site')
        headers = {'Origin': self.origin, 'Sec-Fetch-Site': site}
        if self.manifest_identity is not None:
            headers[IDENTITY_HEADER] = json.dumps(self.manifest_identity, sort_keys=True, separators=(',', ':'))
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        started = time.monotonic()
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        # Every new response must re-establish the binding. Failure must not
        # leave an earlier successful identity authorizing another write.
        self.observed_identity = None
        try:
            response = self.opener.open(req, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            if 300 <= response.status < 400:
                raise ValueError('HTTP redirect refused')
            if self.manifest_identity is not None:
                try:
                    observed = instance_identity(json.loads(response.headers.get(IDENTITY_HEADER, '')))
                except (ValueError, TypeError, AttributeError):
                    raise ValueError('remote identity missing/invalid') from None
                if observed != self.manifest_identity:
                    raise ValueError('remote identity mismatch')
                self.observed_identity = observed
            payload = response.read(20 * 1024 * 1024 + 1)
            status = response.status
        self.events.append({'method':method,'path':path,'status':status,'seconds':round(time.monotonic()-started,4)})
        if len(payload) > 20 * 1024 * 1024:
            raise ValueError('response exceeds bounded size')
        if status != expected:
            raise AssertionError(f'{method} {path}: {status}, expected {expected}: {payload[:1000]!r}')
        return payload

    def json(self, method, path, body=None, expected=200):
        return json.loads(self.call(method, path, body, expected))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', required=True, type=Path)
    p.add_argument('--base', type=local_url, default='http://127.0.0.1:18011')
    p.add_argument('--origin', type=local_url, default='http://127.0.0.1:15174')
    p.add_argument('--receipt', required=True, type=Path)
    p.add_argument('--key', default='dev-smoke-v1')
    p.add_argument('--verify', action='store_true')
    a = p.parse_args(argv)
    manifest = json.loads(a.manifest.read_text())
    if manifest.get('synthetic') is not True:
        raise ValueError('synthetic manifest required')
    client = Client(a.base, a.origin, manifest)
    client.bind()
    if a.verify:
        receipt = json.loads(a.receipt.read_text())
        assert receipt['root_id'] == manifest['root_id']
        for row in receipt['artifacts']:
            payload = client.call('GET', row['href'])
            assert hashlib.sha256(payload).hexdigest() == row['content_hash']
            assert len(payload) == row['size_bytes']
        tasks = client.json('GET', receipt['task_list_path'])['items']
        task = next(t for t in tasks if t['task_id'] == receipt['task_id'])
        assert task['version'] == receipt['final_task_version']
        assert task['status'] == 'done'
        print(json.dumps({'restart_verification':'PASS','events':client.events, **client.identity_receipt()}, indent=2))
        return
    if a.receipt.exists():
        raise ValueError('receipt exists; use --verify or choose a new receipt/key')
    sid = manifest['scans']['completed_target']
    fixed = manifest['assessments'][sid]
    prefix = f'/api/v1/scans/{sid}/assessments/{fixed["assessment_id"]}'
    task_base = prefix + '/remediation-tasks'
    report_path = prefix + '/report-v2'
    history = client.json('GET', '/api/v1/scans')
    assert {x['scan_id'] for x in history['items']} == set(manifest['scans'].values())
    client.json('GET', f'/api/v1/scans/{sid}/diff?base_scan_id={manifest["comparisons"]["base_scan_id"]}')
    graph = client.json('GET', f'/api/v1/scans/{sid}/graph')
    assert graph['nodes'] and graph['edges']
    client.json('GET', f'/api/v1/scans/{sid}/graph?resource_kinds=component')
    partial = client.json('GET', f'/api/v1/scans/{manifest["scans"]["partial"]}/graph')
    assert partial['coverage']['scan_gaps']
    asm = client.json('GET', prefix)
    assert asm['id'] == fixed['assessment_id'] and asm['facts_hash'] == fixed['facts_hash']
    payload = {'idempotency_key':a.key + '-derive','expected_facts_hash':fixed['facts_hash']}
    derived = client.json('POST', task_base + '/derive', payload)
    assert client.json('POST', task_base + '/derive', payload) == derived
    task = derived['items'][0]
    task_path = task_base + '/' + task['task_id']
    active = client.json('PATCH', task_path, {'expected_version':task['version'], 'status':'in_progress'})
    stale = client.json('PATCH', task_path, {'expected_version':task['version'], 'note':'stale'}, 409)
    assert stale['error']['code'] == 'conflict'
    done = client.json('PATCH', task_path, {'expected_version':active['version'], 'status':'done',
        'note':'Synthetic integration review; this does not verify compliance.'})
    reports, artifacts = [], []
    for label, refs in [('base', []), ('graph', [manifest['graph_refs'][sid]])]:
        body = {'idempotency_key':a.key + '-' + label,
                'task_refs':[] if label == 'base' else [{'task_id':done['task_id'], 'version':done['version']}],
                'notice_refs':[], 'algorithm_refs':refs}
        report = client.json('POST', report_path, body)
        assert client.json('POST', report_path, body) == report
        reports.append(report['snapshot_id'])
        for meta in report['artifacts']:
            data = client.call('GET', meta['href'])
            assert hashlib.sha256(data).hexdigest() == meta['content_hash']
            assert len(data) == meta['size_bytes']
            if meta['format'] == 'json':
                document = json.loads(data)
                assert all('content' in section for section in document['sections'])
                assert all('content' not in section for section in report['sections'])
                if label == 'graph':
                    assert report['binding']['algorithm_refs'] == refs
                    observation = [s for s in document['sections'] if s['authority'] == 'observation']
                    assert len(observation) == 1 and observation[0]['content']['nodes']
            artifacts.append(meta)
            a.receipt.parent.mkdir(parents=True, exist_ok=True)
            (a.receipt.parent / (a.receipt.stem + '-' + label + '.' + meta['format'])).write_bytes(data)
    final = client.json('PATCH', task_path, {'expected_version':done['version'], 'note':'Later synthetic note; saved reports remain immutable.'})
    for meta in artifacts:
        assert hashlib.sha256(client.call('GET', meta['href'])).hexdigest() == meta['content_hash']
    blocked = client.json('POST', '/api/v1/scans', {'source_type':'git','source':'https://github.com/example/synthetic'},503)
    assert blocked['error']['code'] == 'feature_disabled'
    receipt = {'synthetic':True,'root_id':client.observed_identity['root_id'], **client.identity_receipt(), 'task_id':task['task_id'],
               'task_list_path':task_base,'final_task_version':final['version'],
               'snapshot_ids':reports,'artifacts':artifacts,'events':client.events,
               'real_external_scan':False,'Qwen':False}
    a.receipt.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'result':'PASS','requests':len(client.events),'receipt':str(a.receipt)},indent=2))


if __name__ == '__main__':
    main()
