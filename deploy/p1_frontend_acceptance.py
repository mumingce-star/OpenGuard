#!/usr/bin/env python3
"""Synthetic acceptance lifecycle and bounded real-HTTP acceptance (stdlib only).

All lifecycle security remains in p1_dev. prepare replays explicit writes;
verify only GETs; smoke additionally exercises Task CAS. No frontend/mock API.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import socket
import sys
import urllib.parse
from copy import deepcopy
from datetime import datetime,timezone

import p1_dev as launcher
from p1_dev_smoke import Client, local_url


def profile_get(client,href):
    start=datetime.now(timezone.utc)
    value=client.json('GET',href)
    at=value['provenance']['generated_at']
    assert at.endswith('Z')
    assert start<=datetime.fromisoformat(at.replace('Z','+00:00'))<=datetime.now(timezone.utc)
    return value


def profile_semantic(value):
    value=deepcopy(value);value['provenance'].pop('generated_at');return value


def network_guard():
    """Harness-only guard; not an OS firewall, not installed in product code."""
    original = socket.socket.connect
    original_ex = socket.socket.connect_ex
    resolver = socket.getaddrinfo
    attempts = []
    def connect(sock, address):
        if sock.family in {socket.AF_INET, socket.AF_INET6} and address[0] not in {'127.0.0.1', '::1'}:
            attempts.append('non-loopback connect refused')
            raise ValueError('external network forbidden')
        return original(sock, address)
    def resolve(host, *args, **kwargs):
        if host not in {'localhost', '127.0.0.1', '::1'}:
            attempts.append('non-loopback resolution refused')
            raise ValueError('external resolution forbidden')
        return resolver(host, *args, **kwargs)
    def connect_ex(sock, address):
        if sock.family in {socket.AF_INET, socket.AF_INET6} and address[0] not in {'127.0.0.1', '::1'}:
            attempts.append('non-loopback connect_ex refused')
            raise ValueError('external network forbidden')
        return original_ex(sock, address)
    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.getaddrinfo = resolve
    return attempts


def audit(root, manifest):
    name, labels = launcher.identity(root, manifest)
    info = launcher.inspect_owned(name)
    if not info or not info['State']['Running']:
        raise ValueError('owned acceptance instance must be running for audit')
    launcher.check_acceptance_configuration(info, root, manifest)
    result = launcher.docker('exec', info['Id'], launcher.PYTHON, '-B', '-m',
        'app.frontend_acceptance_server', 'audit', '--root',
        '/workspace/output/manual-fixes/' + root.name)
    return json.loads(result)


def prepare_http(client, manifest):
    for task in manifest['tasks'].values():
        response = client.json('POST', task['href'] + '/derive',
            {'idempotency_key':task['idempotency_key'], 'expected_facts_hash':task['facts_hash']})
        assert {t['task_id'] for t in response['items']} == {t['task_id'] for t in task['initial_tasks']}
    for report in manifest['reports'].values():
        response = client.json('POST', report['href'], dict(idempotency_key=report['idempotency_key'],
            task_refs=report['task_refs'], notice_refs=[], algorithm_refs=report['graph_refs']))
        assert response['snapshot_id'] == report['snapshot_id']
        assert response['artifacts'] == report['artifacts']
        assert all('content' not in section for section in response['sections'])


def verify_http(client, manifest):
    first = client.json('GET', '/api/v1/scans?limit=20')
    assert len(first['items']) == 20 and first['next_cursor']
    rows, pages, cursor = [], [], None
    while True:
        path = '/api/v1/scans?limit=100'
        if cursor:
            path += '&cursor=' + urllib.parse.quote(cursor)
        page = client.json('GET', path)
        rows.extend(page['items'])
        pages.append(len(page['items']))
        cursor = page['next_cursor']
        if not cursor:
            break
    assert len(rows) == len({r['scan_id'] for r in rows}) == 205
    for key, expected in [('status','partial'), ('source_type','zip'), ('q','synthetic 001'),
                          ('project_key', manifest['history']['project_key'])]:
        result = client.json('GET', '/api/v1/scans?' + urllib.parse.urlencode({key:expected, 'limit':100}))
        assert result['items']
        if key in {'status','source_type'}:
            assert all(r[key] == expected for r in result['items'])
        if key == 'project_key':
            assert all(r['project_identity']['key'] == expected for r in result['items'])
    diffs = {}
    for name, row in manifest['diff'].items():
        value = client.json('GET', row['href'])
        diffs[name] = {'assessment_status':value['assessment_diff']['status'],
                      'resource_kinds':sorted({r['kind'] for r in value['resources']})}
        if name == 'D1':
            assert {'changed','added','not_observed_in_target'} <= set(diffs[name]['resource_kinds'])
            assert any(r['removal_confirmed'] is True for r in value['resources'])
        if name == 'D2':
            assert all(r['removal_confirmed'] is not True for r in value['resources'])
        if name == 'D3':
            assert value['assessment_diff']['status'] == 'unavailable'
        if name == 'D4':
            assert value['assessment_diff']['status'] == 'compared'
    graphs = {}
    for tier, row in manifest['graphs'].items():
        value = client.json('GET', row['href'])
        ids = {n['id'] for n in value['nodes']}
        assert len(ids) == len(value['nodes']) == int(tier)
        assert len({e['id'] for e in value['edges']}) == len(value['edges'])
        assert all(e['source'] in ids and e['target'] in ids for e in value['edges'])
        graphs[tier] = dict(nodes=len(ids), edges=len(value['edges']))
        for query in ('resource_kinds=component', 'resource_ids=' + row['resource_id']):
            filtered = client.json('GET', row['href'] + '?' + query)
            selected = {n['id'] for n in filtered['nodes']}
            assert filtered['coverage']['scope'] == 'filtered'
            assert all(e['source'] in selected and e['target'] in selected for e in filtered['edges'])
    partial = client.json('GET', '/api/v1/scans/' + manifest['diff']['D2']['target_scan_id'] + '/graph')
    assert partial['coverage']['scan_gaps'] and partial['coverage']['view_complete']
    for row in manifest['assessments'].values():
        fixed = client.json('GET', row['href'])
        assert fixed['id'] == row['assessment_id'] and fixed['facts_hash'] == row['facts_hash']
    task_audit = {}
    for label, row in manifest['tasks'].items():
        items = client.json('GET', row['href'] + '?limit=100')['items']
        if label == 'empty':
            assert items == []
        else:
            kinds = {t['origin']['kind'] for t in items}
            assert 'obligation' in kinds and len(kinds) > 1
            assert any(t['resource_ids'] and t['evidence_refs'] for t in items)
        task_audit[label] = {'count':len(items), 'origins':sorted({t['origin']['kind'] for t in items})}
    for report in manifest['reports'].values():
        for artifact in report['artifacts']:
            payload = client.call('GET', artifact['href'])
            assert hashlib.sha256(payload).hexdigest() == artifact['content_hash']
            assert len(payload) == artifact['size_bytes']
            if artifact['format'] == 'json':
                document = json.loads(payload)
                assert all('content' in s for s in document['sections'])
    for fmt in ('html','json'):
        sizes = {label:next(a['size_bytes'] for a in report['artifacts'] if a['format']==fmt)
                 for label,report in manifest['reports'].items()}
        assert sizes['long'] > sizes['basic']
    for unsupported in manifest['unsupported'].values():
        client.call('GET', unsupported['href'], expected=404)
    result=dict(history={'count':len(rows), 'pages':pages}, diff=diffs, graphs=graphs, tasks=task_audit)
    if 'profiles' in manifest:
        profiles={}
        for label,row in manifest['profiles'].items():
            profile=profile_get(client,row['href'])
            assert len(profile['metadata_observations'])==row['expected_metadata_count']
            assert profile['coverage_gaps']==row['expected_gaps']
            assert profile_semantic(profile)==profile_semantic(profile_get(client,row['href']))
            profiles[label]=dict(profile_id=profile['profile_id'],resource_ref=profile['resource_ref'],
                metadata_count=len(profile['metadata_observations']),coverage_gaps=profile['coverage_gaps'])
        result['profiles']=profiles
        sid=manifest['profiles']['P2']['scan_id']
        resources=client.json('GET',f'/api/v1/scans/{sid}/resources?kind=ai_asset')['items']
        for row in resources:
            if row['resource']['name']=='synthetic/empty-provider':
                assert row['resource']['provider']==''
                value=profile_get(client,f'/api/v1/scans/{sid}/resources/{row["resource"]["id"]}/profile')
                assert value['identity']['provider'] is None
                assert 'identity_provider_empty_normalized_to_unknown' in value['coverage_gaps']
                result['empty_provider']=dict(resource_id=row['resource']['id'],provider=None,coverage_gaps=value['coverage_gaps'])
    return result


def profile_refresh_http(client,manifest):
    row=manifest['profiles']['P2']
    before=profile_get(client,row['href'])
    path=f'/api/v1/scans/{row["scan_id"]}/resource-profiles'
    body=dict(resource_ids=[row['resource_id']],expected_facts_hash=before['scan_ref']['facts_hash'],
              idempotency_key='acceptance-profile-http-v2')
    job=client.json('POST',path+'/refresh',body)
    assert job['status']=='succeeded'
    assert client.json('POST',path+'/refresh',body)==job
    client.json('POST',path+'/refresh',dict(body,resource_ids=[manifest['profiles']['P3']['resource_id']]),409)
    assert client.json('GET',path+'/jobs/'+job['job_id'])==job
    after=profile_get(client,row['href'])
    assert profile_semantic(after)==profile_semantic(before)
    return job


def profile_new_observation_http(client,manifest):
    sid=manifest['profiles']['P2']['scan_id']
    base=f'/api/v1/scans/{sid}'
    rows=client.json('GET',base+'/resources?kind=ai_asset')['items']
    resource=next(row['resource'] for row in rows if row['resource']['name']=='synthetic/unfetched')
    href=base+'/resources/'+resource['id']+'/profile'
    before=profile_get(client,href)
    body=dict(resource_ids=[resource['id']],expected_facts_hash=before['scan_ref']['facts_hash'],
        idempotency_key='acceptance-new-observation-v2')
    job=client.json('POST',base+'/resource-profiles/refresh',body)
    assert job['status']=='succeeded'
    assert client.json('GET',base+'/resource-profiles/jobs/'+job['job_id'])==job
    after=profile_get(client,href)
    assert len(after['metadata_observations'])==1
    assert profile_semantic(profile_get(client,href))==profile_semantic(after)
    assert client.json('POST',base+'/resource-profiles/refresh',body)==job
    return dict(resource_id=resource['id'],href=href,job_id=job['job_id'],
        before_count=len(before['metadata_observations']),after_count=1,profile_id=after['profile_id'])


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['init','init-v2','start','stop','status','prepare','smoke','verify','print-manifest'])
    p.add_argument('--root', required=True)
    p.add_argument('--image')
    p.add_argument('--base', type=local_url, default='http://127.0.0.1:18011')
    p.add_argument('--origin', type=local_url, default='http://127.0.0.1:15174')
    p.add_argument('--receipt', default='acceptance-http.json')
    p.add_argument('--profile-job-id')
    args = p.parse_args(argv)
    root = launcher.safe_root(args.root)
    if not root.name.startswith(launcher.ACCEPTANCE_PREFIX):
        p.error('only a dedicated frontend-acceptance root is allowed')
    if args.action in {'init','init-v2','start','stop','status'}:
        values = ['init' if args.action=='init-v2' else args.action, '--root', str(root)]
        if args.action=='init-v2': values += ['--acceptance-version','2']
        if args.image:
            values += ['--image', args.image]
        return launcher.main(values)
    manifest = launcher.marker(root)
    # print/HTTP paths must use the same backend validator as serve. Stop/status
    # returned above intentionally retain ownership-only recovery semantics.
    image = args.image
    if image is None:
        name, _ = launcher.identity(root, manifest)
        info = launcher.inspect_owned(name)
        if info is None:
            raise launcher.LaunchError('--image required until an owned instance exists')
        image = launcher.check_acceptance_configuration(info, root, manifest)
    image_id, platform = launcher.local_image(image)
    validated = launcher.validate_acceptance(root, image_id, platform)
    if validated != manifest:
        raise launcher.LaunchError('acceptance manifest changed during validation')
    if args.action == 'print-manifest':
        summary = {k:manifest[k] for k in ('synthetic','seed_version','root_id','api_base',
            'recommended_web_origin','history','diff','graphs','unsupported')}
        summary['tasks'] = {label:dict(scan_id=row['scan_id'], assessment_id=row['assessment_id'],
            count=len(row['initial_tasks']), href=row['href']) for label,row in manifest['tasks'].items()}
        summary['reports'] = {label:dict(snapshot_id=row['snapshot_id'], artifacts=row['artifacts'])
                              for label,row in manifest['reports'].items()}
        if 'profiles' in manifest: summary['profiles']=manifest['profiles']
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    if Path(args.receipt).name != args.receipt or args.receipt in {'.','..'}:
        p.error('receipt must be a fresh filename inside acceptance root')
    path = root / args.receipt
    if path.exists() or path.is_symlink():
        p.error('receipt exists; preserve it and choose a new receipt filename')
    attempts = network_guard()
    client = Client(args.base, args.origin, manifest, seed_version=manifest['seed_version'])
    client.bind()
    if args.action in {'prepare','smoke'}:
        prepare_http(client, manifest)
        prepare_http(client, manifest)
    profile_job=profile_refresh_http(client,manifest) if 'profiles' in manifest and args.action in {'prepare','smoke'} else None
    profile_new=profile_new_observation_http(client,manifest) if 'profiles' in manifest and args.action in {'prepare','smoke'} else None
    before = audit(root, manifest)
    result = verify_http(client, manifest)
    if args.profile_job_id:
        row=manifest['profiles']['P2']
        profile_job=client.json('GET',f'/api/v1/scans/{row["scan_id"]}/resource-profiles/jobs/{args.profile_job_id}')
        assert profile_job['status']=='succeeded'
    after = audit(root, manifest)
    assert before == after, 'GET modified business state'
    cas = None
    if args.action == 'smoke':
        row = manifest['tasks']['populated']
        bound_id = manifest['reports']['task']['task_refs'][0]['task_id']
        task = next(t for t in client.json('GET', row['href'] + '?limit=100')['items'] if t['task_id'] == bound_id)
        if task['status'] != 'todo' or task['version'] != 1:
            raise ValueError('CAS smoke requires a fresh root; do not reset old data')
        task_path = row['href'] + '/' + task['task_id']
        active = client.json('PATCH', task_path, {'expected_version':1, 'status':'in_progress'})
        client.json('PATCH', task_path, {'expected_version':1, 'note':'stale synthetic edit'}, 409)
        done = client.json('PATCH', task_path, {'expected_version':active['version'], 'status':'done',
            'note':'Synthetic workflow review only; this does not verify compliance.'})
        current = client.json('GET', row['href'])['items']
        assert next(t for t in current if t['task_id']==task['task_id'])['version'] == done['version']
        result = verify_http(client, manifest)
        final = audit(root, manifest)
        for name in ('scans.db','assessment.db','report_v2.db'):
            assert final[name] == before[name], 'Task changed fixed facts or report'
        cas = dict(task_id=task['task_id'], initial_version=1, final_version=done['version'],
                   stale_status=409, status=done['status'], reports_immutable=True)
    receipt = dict(result='PASS', action=args.action, synthetic=True, **client.identity_receipt(),
        validation=result, get_audit={'before':before,'after':after,'equal':before==after}, cas=cas,
        reports=manifest['reports'], events=client.events,
        network={'external_business_requests':0,'blocked_attempts':attempts,
                 'boundary':'Python harness guard; not an OS firewall. No external business request authorized or executed.'})
    if profile_job: receipt['profile_refresh']=profile_job
    if profile_new: receipt['profile_new_observation']=profile_new
    with path.open('x', encoding='utf-8') as file:
        json.dump(receipt, file, ensure_ascii=False, indent=2)
    print(json.dumps({'result':'PASS','action':args.action,'requests':len(client.events), 'synthetic':True}))


if __name__ == '__main__':
    main()
