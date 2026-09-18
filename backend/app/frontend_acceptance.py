"""Explicit synthetic-only frontend acceptance facts; no scanner/network/AI.

This is developer infrastructure, not a production factory or public contract.
An independent marker/version protects the original dev-integration v2 roots.
"""
from __future__ import annotations

from copy import deepcopy
from contextlib import closing
from datetime import datetime, timedelta
import hashlib
import json
import re
from pathlib import Path
import sqlite3
from urllib.parse import quote
from uuid import UUID
from types import SimpleNamespace

from app import dev_integration as dev
from app.assessment.engine import build_assessment, facts_digest
from app.domain.models import ScanRun
from app.domain.usage import UsageDeclaration
from app.p1.graph import GraphReader
from app.p1.models import P1TaskDeriveRequest, P1TaskRef
from app.p1.report_v2_integrity import explicit_identity

SEED_VERSION = 'p1-frontend-acceptance/1'
PREFIX = 'p1-frontend-acceptance-'
MANIFEST = 'frontend-acceptance-manifest.json'
MARKER = '.openguard-frontend-acceptance.json'


def _root(root, repository_root=None, *, must_exist=True):
    return dev._root(root, repository_root, must_exist=must_exist, prefix=PREFIX)


def _id(kind, number):
    return kind + '_' + str(UUID(int=number))


def _facts(number, *, nodes=None, empty=False):
    value = dev._scan_payload(dev._fixture(), number=10000 + number,
                              revision=f'synthetic-acceptance-{number:03}', status='completed')
    value['project']['name'] = f'P1 Frontend Acceptance Seed synthetic {number:03}'
    value['project']['source'] = 'https://github.com/openguard-synthetic/frontend-acceptance.git'
    value['created_at'] = (dev._NOW - timedelta(minutes=number)).isoformat()
    if empty:
        for key in ('components', 'ai_assets', 'licenses', 'evidence', 'obligations', 'findings', 'remediations'):
            value[key] = []
    elif nodes:
        # Existing fixture contributes project + 8 fact nodes. Additional
        # components share explicit evidence/license observations, never inferred edges.
        for index in range(nodes - 9):
            component = deepcopy(value['components'][0])
            component.update(id=_id('cmp', 20000 + index), name=f'synthetic-package-{index:04}',
                             purl=f'pkg:pypi/synthetic-package-{index:04}@1.0.0', version='1.0.0')
            value['components'].append(component)
    elif number in {1, 2, 3, 4}:
        component = deepcopy(value['components'][0])
        label = 'removed' if number == 1 else 'added'
        component.update(id=_id('cmp', 30000 if number == 1 else 30001), name='synthetic-' + label,
                         purl='pkg:pypi/synthetic-' + label + '@1.0', version='1.0')
        value['components'].append(component)
        if number != 1:
            value['components'][0].update(version='2.14.0', purl='pkg:pypi/pydantic@2.14.0')
            value['findings'][0]['description'] = 'Synthetic changed observation requiring review.'
            value['licenses'][0]['confidence'] = 0.8
    value['summary'] = dict(component_count=len(value['components']), ai_asset_count=len(value['ai_assets']),
        evidence_count=len(value['evidence']), finding_counts={k: sum(f['outcome'] == k for f in value['findings'])
        for k in ('pass', 'warning', 'review_required', 'unknown')})
    if number > 8 and number % 3 == 0:
        value['project'].update(source_type='zip', source=f'synthetic-fixture-{number:03}.zip')
    return value


def _persist(registry, value, status):
    queued = ScanRun.model_validate(value)
    registry.create(queued)
    if status == 'queued':
        return queued
    value = deepcopy(value)
    value.update(status='running', stage='ingestion', progress=5, started_at=dev._NOW.isoformat())
    running = ScanRun.model_validate(value)
    registry.replace(running, expected_revision=1)
    if status == 'running':
        return running
    value.update(status=status, finished_at=dev._NOW.isoformat(),
                 stage='completed' if status == 'completed' else 'report',
                 progress=100 if status == 'completed' else 95)
    if status in {'partial', 'failed'}:
        value['errors'] = [dict(code='synthetic_coverage_gap', stage='scan',
            message='Synthetic acceptance coverage gap.', recoverable=status == 'partial')]
    final = ScanRun.model_validate(value)
    registry.replace(final, expected_revision=2)
    return final


def read_manifest(root, *, repository_root=None):
    root = _root(root, repository_root)
    dev._private_directory(root)
    if not (root / MARKER).is_file() or not (root / MANIFEST).is_file():
        raise dev.DevIntegrationError('acceptance_not_prepared')
    marker = dev._load_json(root / MARKER)
    manifest = dev._load_json(root / MANIFEST)
    for value in (marker, manifest):
        if (value.get('synthetic') is not True or value.get('seed_version') != SEED_VERSION
                or value.get('tool') != 'P1 Frontend Acceptance Seed'
                or not isinstance(value.get('root_id'), str)
                or not re.fullmatch(r'dev_[0-9a-f]{32}', value['root_id'])
                or not isinstance(value.get('code_commit'), str)
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,199}', value['code_commit'])):
            raise dev.DevIntegrationError('acceptance_identity_invalid')
    if any(marker.get(k) != manifest.get(k) for k in ('root_id', 'code_commit')):
        raise dev.DevIntegrationError('acceptance_identity_invalid')
    dev._validate_database_set(root)
    dev._readonly_schema_preflight(root)
    try:
        _same(marker, {k:manifest[k] for k in ('synthetic','seed_version','root_id','code_commit','tool')})
        _validate_manifest(root, manifest)
    except dev.DevIntegrationError:
        raise
    except Exception as error:
        raise dev.DevIntegrationError('acceptance_manifest_invalid') from error
    return manifest


def _same(actual, expected):
    # Canonical JSON distinguishes bool from int and rejects NaN/Infinity.
    if dev._json_bytes(actual) != dev._json_bytes(expected):
        raise dev.DevIntegrationError('acceptance_manifest_invalid')


def _readonly_rows(root, name, query):
    with closing(sqlite3.connect(f"file:{quote(str(root / name), safe='/')}?mode=ro", uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        return db.execute(query).fetchall()


def _validate_manifest(root, manifest):
    """Existing facts only. Never constructs a writable registry or calls create/derive.

    Fixed v1 scenario membership comes from the seed definition, not whatever
    entries remain in an untrusted manifest. Task versions are historical v1,
    so later legal workflow edits do not invalidate this acceptance space.
    """
    if not isinstance(manifest.get('reports'), dict) or set(manifest['reports']) != {'basic','task','graph','long'}:
        raise dev.DevIntegrationError('acceptance_not_prepared')
    _same(sorted(manifest), sorted(('synthetic','seed_version','root_id','code_commit','tool','identity',
        'created_at','api_base','recommended_web_origin','api','history','assessments','diff','graphs','tasks','reports','unsupported','validation')))
    _same(manifest['identity'], {k:manifest[k] for k in ('synthetic','seed_version','root_id','code_commit','tool')})
    if datetime.fromisoformat(manifest['created_at'].replace('Z','+00:00')).utcoffset() != timedelta(0):
        raise ValueError('UTC required')
    _same(manifest['api_base'], 'http://127.0.0.1:18011')
    _same(manifest['recommended_web_origin'], 'http://127.0.0.1:15174')
    _same(manifest['api'], {'history':'/api/v1/scans'})
    _same(manifest['validation'], {'scope':'synthetic only; no repository scan, legal conclusion or frontend performance claim'})
    rows = _readonly_rows(root, 'scans.db',
        'SELECT scan_id,revision,idempotency_key,idempotency_fingerprint,created_at,status,contract_version,run_json FROM scan_runs LIMIT 206')
    stored = [dev.SQLiteScanRunRegistry._row_to_stored(row) for row in rows]
    scans = {s.run.id:s for s in stored}
    sid = lambda n: _id('scn',10000+n)
    _same(sorted(scans), sorted(sid(n) for n in range(1,206)))
    _same(manifest['history'], {'count':len(stored),'project_key':'github.com/openguard-synthetic/frontend-acceptance'})
    registry = SimpleNamespace(get=lambda scan_id:scans[scan_id])
    assessments = dev.AssessmentStore(root/'assessment.db', min_free_bytes=0)
    task_store = dev.RemediationTaskStore(root/'remediation.db', min_free_bytes=0)
    reports = dev.ReportV2Store(root/'report_v2.db', min_free_bytes=0)
    fixed, asm = {}, {}
    for n in (1,2,3,7,8):
        values = assessments.list(sid(n), limit=2)
        if len(values) != 1:
            raise ValueError('required fixed assessment missing or ambiguous')
        a = values[0]
        if not a.formal or a.scan_id != sid(n) or a.version != 1 or a.facts_hash != facts_digest(scans[sid(n)].run):
            raise ValueError('fixed assessment mismatch')
        asm[sid(n)] = a
        fixed[sid(n)] = dict(assessment_id=a.id, version=a.version, facts_hash=a.facts_hash, usage_hash=a.usage_hash,
                            href=f'/api/v1/scans/{sid(n)}/assessments/{a.id}')
    _same(manifest['assessments'], fixed)
    if assessments.list(sid(4),limit=1):
        raise ValueError('D3 must have no assessment')
    expected_diff = {}
    for label,n in [('D1',2),('D2',3),('D3',4),('D4',2)]:
        href=f'/api/v1/scans/{sid(n)}/diff?base_scan_id={sid(1)}'
        row=dict(base_scan_id=sid(1),target_scan_id=sid(n),description={
            'D1':'completed facts changed, added and confirmed not observed',
            'D2':'partial missing is not confirmed removed','D3':'Assessment unavailable',
            'D4':'fixed formal Assessments compared'}[label])
        if label=='D4':
            row.update(base_assessment_id=asm[sid(1)].id,target_assessment_id=asm[sid(2)].id)
            href += '&base_assessment_id='+row['base_assessment_id']+'&target_assessment_id='+row['target_assessment_id']
        row['href']=href
        expected_diff[label]=row
    _same(manifest['diff'], expected_diff)
    expected_graphs={}
    for n,tier in [(5,100),(6,300),(7,500)]:
        graph=GraphReader(registry).read(sid(n),[],[])
        _same(len(graph['nodes']),tier)
        expected_graphs[str(tier)]=dict(scan_id=sid(n),target_tier=tier,actual_node_count=len(graph['nodes']),
            edge_count=len(graph['edges']),resource_id=scans[sid(n)].run.components[0].id,href=f'/api/v1/scans/{sid(n)}/graph')
    _same(manifest['graphs'],expected_graphs)
    expected_tasks={}
    for label,n in [('populated',2),('empty',8)]:
        a=asm[sid(n)]
        current=task_store.page(sid(n),a.id,limit=100)
        by_pointer={t['origin']['source_pointer']:task_store.get_version(sid(n),a.id,t['task_id'],1) for t in current}
        sources=list(dev.RemediationService._sources(a))  # pure enumeration, not derive
        _same(len(current),len(sources))
        initial=[]
        for kind,pointer,value,text,resources,evidence in sources:
            t=by_pointer[pointer]
            _same(t['origin'],dict(kind=kind,source_pointer=pointer,source_hash=hashlib.sha256(dev._json_bytes(value)).hexdigest()))
            _same(t['resource_ids'],sorted(set(resources)))
            _same(t['evidence_refs'],[dict(namespace='scan',scan_id=sid(n),evidence_id=e) for e in sorted(set(evidence))])
            _same(t['assessment_ref'],dev.RemediationService._assessment_ref(a))
            initial.append({k:t[k] for k in ('task_id','version','origin','resource_ids','evidence_refs')})
        expected_tasks[label]=dict(fixed[sid(n)],scan_id=sid(n),href=fixed[sid(n)]['href']+'/remediation-tasks',
            idempotency_key='acceptance-derive-v1',initial_tasks=initial)
    _same(manifest['tasks'],expected_tasks)
    for label in ('basic','task','graph','long'):
        n=7 if label=='long' else 2
        a=asm[sid(n)]
        key='acceptance-report-v1-'+label
        refs=[{k:expected_tasks['populated']['initial_tasks'][0][k] for k in ('task_id','version')}] if label=='task' else []
        graph_refs=[dev.ReportGraphReader().capture(scans[sid(n)])[0].model_dump(mode='json')] if label=='graph' else []
        snapshot=reports.replay(sid(n),a.id,key,explicit_identity(sid(n),a.id,refs,[],graph_refs))
        if snapshot is None:
            raise ValueError('missing snapshot')
        _same(snapshot['binding'],dict(scan_ref=GraphReader._ref(scans[sid(n)]),
            assessment_ref=dev.RemediationService._assessment_ref(a),task_refs=refs,notice_refs=[],algorithm_refs=graph_refs))
        _same(manifest['reports'][label],dict(snapshot_id=snapshot['snapshot_id'],scan_id=sid(n),assessment_id=a.id,
            scenario=label,idempotency_key=key,task_refs=refs,graph_refs=graph_refs,
            href=fixed[sid(n)]['href']+'/report-v2',artifacts=snapshot['artifacts']))
    _same(manifest['unsupported'],dict(
        profile=dict(status='not_available_on_current_baseline',reason='A07-2 ResourceProfile / B01 parser pending',
            href=f'/api/v1/scans/{sid(2)}/resources/{scans[sid(2)].run.components[0].id}/profile'),
        notice=dict(status='not_available_on_current_baseline',reason='NOTICE facts / NoticeDraft reader/API pending',
            href=fixed[sid(2)]['href']+'/notice-drafts/synthetic-unavailable')))


def _stores(root):
    registry = dev.SQLiteScanRunRegistry(root / 'scans.db')
    assessments = dev.AssessmentStore(root / 'assessment.db', min_free_bytes=0)
    tasks = dev.RemediationTaskStore(root / 'remediation.db', min_free_bytes=0)
    reports = dev.ReportV2Store(root / 'report_v2.db', min_free_bytes=0)
    return registry, assessments, tasks, reports


def initialize(root, *, repository_root=None, code_version='unknown'):
    root = _root(root, repository_root, must_exist=False)
    if root.exists():
        dev._private_directory(root)
        if any(root.iterdir()):
            raise dev.DevIntegrationError('root_already_initialized')
    else:
        root.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.mkdir(mode=0o700)
    registry, assessments, tasks, reports = _stores(root)
    try:
        dev.AssessmentService(registry, assessments, provider=None).initialize()
        tasks.initialize()
        reports.initialize()
        runs, fixed, graphs = {}, {}, {}
        for number in range(1, 206):
            tier = {5: 100, 6: 300, 7: 500}.get(number)
            status = 'partial' if number == 3 else ('completed' if number <= 170 else
                'partial' if number <= 185 else 'failed' if number <= 193 else
                'cancelled' if number <= 199 else 'running' if number <= 202 else 'queued')
            run = _persist(registry, _facts(number, nodes=tier, empty=number == 8 or number > 8), status)
            if number <= 8:
                runs[number] = run
            # D3 intentionally has no Assessment. Do not synthesize one later.
            if number in {1, 2, 3, 7, 8}:
                assessment = build_assessment(run, UsageDeclaration(preset='internal', declared_at=dev._NOW),
                                              generated_at=dev._NOW)
                assessments.create(assessment, idempotency_key='acceptance-' + run.id, run=run)
                fixed[run.id] = dict(assessment_id=assessment.id, version=assessment.version,
                    facts_hash=assessment.facts_hash, usage_hash=assessment.usage_hash,
                    href=f'/api/v1/scans/{run.id}/assessments/{assessment.id}')
            if tier:
                graph = GraphReader(registry).read(run.id, [], [])
                graphs[str(tier)] = dict(scan_id=run.id, target_tier=tier,
                    actual_node_count=len(graph['nodes']), edge_count=len(graph['edges']),
                    resource_id=run.components[0].id, href=f'/api/v1/scans/{run.id}/graph')
        identity = dict(synthetic=True, seed_version=SEED_VERSION, root_id=dev._new_root_id(),
                        code_commit=code_version, tool='P1 Frontend Acceptance Seed')
        diff = {}
        for label, target in [('D1', 2), ('D2', 3), ('D3', 4), ('D4', 2)]:
            href = f'/api/v1/scans/{runs[target].id}/diff?base_scan_id={runs[1].id}'
            row = dict(base_scan_id=runs[1].id, target_scan_id=runs[target].id,
                       description={'D1':'completed facts changed, added and confirmed not observed',
                       'D2':'partial missing is not confirmed removed', 'D3':'Assessment unavailable',
                       'D4':'fixed formal Assessments compared'}[label])
            if label == 'D4':
                row.update(base_assessment_id=fixed[runs[1].id]['assessment_id'],
                           target_assessment_id=fixed[runs[2].id]['assessment_id'])
                href += '&base_assessment_id=' + row['base_assessment_id'] + '&target_assessment_id=' + row['target_assessment_id']
            row['href'] = href
            diff[label] = row
        task_rows = {label: dict(fixed[runs[n].id], scan_id=runs[n].id,
            href=fixed[runs[n].id]['href'] + '/remediation-tasks', idempotency_key='acceptance-derive-v1')
            for label, n in [('populated', 2), ('empty', 8)]}
        prefix = fixed[runs[2].id]['href']
        manifest = dict(**identity, identity=identity, created_at=dev._NOW.isoformat(),
            api_base='http://127.0.0.1:18011', recommended_web_origin='http://127.0.0.1:15174',
            api={'history':'/api/v1/scans'}, history={'count':205, 'project_key':'github.com/openguard-synthetic/frontend-acceptance'},
            assessments=fixed, diff=diff, graphs=graphs, tasks=task_rows, reports={},
            unsupported={
                'profile':dict(status='not_available_on_current_baseline', reason='A07-2 ResourceProfile / B01 parser pending',
                    href=f'/api/v1/scans/{runs[2].id}/resources/{runs[2].components[0].id}/profile'),
                'notice':dict(status='not_available_on_current_baseline', reason='NOTICE facts / NoticeDraft reader/API pending',
                    href=prefix + '/notice-drafts/synthetic-unavailable')},
            validation={'scope':'synthetic only; no repository scan, legal conclusion or frontend performance claim'})
    finally:
        registry.close()
    # No success marker is published until all explicit writes and read-only
    # checks succeed. A failed init remains private evidence, never recover-seeded.
    manifest = _prepare(root, manifest)
    _validate_manifest(root, manifest)
    dev._atomic_json(root / MANIFEST, manifest)
    dev._atomic_json(root / MARKER, identity)
    return read_manifest(root, repository_root=repository_root)


def prepare(root, *, repository_root=None):
    manifest = read_manifest(root, repository_root=repository_root)
    root = _root(root, repository_root)
    manifest = _prepare(root, manifest)
    _validate_manifest(root, manifest)
    dev._atomic_json(root / MANIFEST, manifest)
    return manifest


def _prepare(root, manifest):
    registry, assessments, tasks, reports = _stores(root)
    try:
        service = dev.RemediationService(registry, assessments, tasks)
        for row in manifest['tasks'].values():
            derived = service.derive(row['scan_id'], row['assessment_id'], P1TaskDeriveRequest(
                idempotency_key=row['idempotency_key'], expected_facts_hash=row['facts_hash']))
            # Initial references are stable across prepare even after workflow edits.
            row.setdefault('initial_tasks', [dict(task_id=t.task_id, version=t.version,
                origin=t.origin.model_dump(mode='json'), resource_ids=t.resource_ids,
                evidence_refs=[e.model_dump(mode='json') for e in t.evidence_refs]) for t in derived.items])
        graph_reader = dev.ReportGraphReader(max_nodes=20000, max_edges=60000)
        report_service = dev.ReportV2Service(registry, assessments, tasks, reports, graph_reader=graph_reader)
        target = manifest['tasks']['populated']
        for label in ('basic', 'task', 'graph', 'long'):
            sid = manifest['graphs']['500']['scan_id'] if label == 'long' else target['scan_id']
            aid = manifest['assessments'][sid]['assessment_id']
            task_refs = [P1TaskRef(task_id=t['task_id'], version=t['version'])
                         for t in target['initial_tasks'][:1]] if label == 'task' else []
            graph_refs = [graph_reader.capture(registry.get(sid))[0]] if label == 'graph' else []
            key = 'acceptance-report-v1-' + label
            snapshot = report_service.create(sid, aid, idempotency_key=key,
                task_refs=task_refs, algorithm_refs=graph_refs).model_dump(mode='json')
            manifest['reports'][label] = dict(snapshot_id=snapshot['snapshot_id'], scan_id=sid,
                assessment_id=aid, scenario=label, idempotency_key=key,
                task_refs=snapshot['binding']['task_refs'], graph_refs=snapshot['binding']['algorithm_refs'],
                href=f'/api/v1/scans/{sid}/assessments/{aid}/report-v2', artifacts=snapshot['artifacts'])
        return manifest
    finally:
        registry.close()


def create_acceptance_app(root, *, origins, repository_root=None):
    manifest = read_manifest(root, repository_root=repository_root)
    root = _root(root, repository_root)
    return dev._wire_dev_app(root, manifest, origins=origins)


def logical_state(root, *, repository_root=None):
    """Readonly business rows including BLOB hashes; WAL/SHM bytes are not facts."""
    read_manifest(root, repository_root=repository_root)
    root = _root(root, repository_root)
    result = {}
    for name in dev._DATABASES:
        with sqlite3.connect(f"file:{quote(str(root), safe='/')}/{name}?mode=ro", uri=True) as connection:
            connection.execute('PRAGMA query_only=ON')
            tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
            result[name] = {}
            for (table,) in tables:
                escaped = table.replace('"', '""')
                rows = connection.execute(f'SELECT * FROM "{escaped}"').fetchall()
                normalized = [[{'blob_sha256':hashlib.sha256(v).hexdigest(), 'size':len(v)} if isinstance(v, bytes) else v
                               for v in row] for row in rows]
                ordered = sorted(normalized, key=lambda r: json.dumps(r, sort_keys=True))
                result[name][table] = dict(count=len(rows),
                    rows_sha256=hashlib.sha256(dev._json_bytes(ordered)).hexdigest())
    return result
