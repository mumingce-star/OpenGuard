import test from 'node:test';
import assert from 'node:assert/strict';
import { runtime } from './runtime.mjs';

const hash = 'a'.repeat(64);

test('A3 missing NoticeDraft is 404/not_found and never retried as reader-unavailable', async () => {
  const r = runtime(), service = r.load('services/reportV2.ts');
  let calls = 0;
  r.setFetch(async () => {
    calls++;
    return Response.json({ error: { code: 'not_found', message: 'not found',
      details: { reason: 'notice_draft_not_found' } } }, { status: 404 });
  });
  await assert.rejects(service.createReportV2('scn_1', 'asm_1', 'key', [],
    [{ draft_id: 'ntc_missing', content_hash: hash }]), error =>
    error.status === 404 && error.code === 'not_found' && error.reason === 'notice_draft_not_found' &&
    error.message === '引用的 NOTICE 草稿不存在；请核对固定的 draft_id 与当前扫描、评估，不会自动生成替代草稿。');
  assert.equal(calls, 1);
  assert.equal(r.storage.size, 0);
});

test('legacy Report reader-unavailable and other errors retain their actual reason', async () => {
  const r = runtime(), service = r.load('services/reportV2.ts');
  for (const [status, reason] of [[409, 'notice_snapshot_reader_not_available'], [503, 'notice_source_unavailable']]) {
    r.setFetch(async () => Response.json({ error: {
      code: 'not_ready', message: 'original backend error', details: { reason },
    } }, { status }));
    await assert.rejects(service.createReportV2('scn_1', 'asm_1', 'key', []), error =>
      error.status === status && error.reason === reason &&
      error.message === `接口请求失败（HTTP ${status}）：original backend error (not_ready)`);
  }
});
function fixture(status = 'completed', extra = []) {
  const section = (authority, content) => ({ authority, schema_version: '1.0', source_ids: ['source'], content_hash: hash, content });
  return {
    schema_version: '1.0', snapshot_id: 'rptv2_1',
    binding: { scan_ref: { scan_id: 'scn_1', status, revision: null }, assessment_ref: { assessment_id: 'asm_1', version: 2 }, notice_refs: [] },
    created_at: '2026-09-18T00:00:00Z', generator_version: 'report-v2/1.1', provenance: { source_refs: [], assessment_refs: [] },
    sections: [section('scan_facts', { status }), section('formal_assessment', { id: 'asm_1', scan_id: 'scn_1', formal: true, summary: '正式结论' }), section('workflow', { tasks: [] }), section('ai_explanation', { ai_status: 'not_requested' }), ...extra],
  };
}

function graphObservation() {
  return {
    authority: 'observation', schema_version: '1.0', source_ids: ['graph-view-1'], content_hash: hash,
    content: { view_id: 'graph-view-1', provenance: { algorithm_version: 'graph/1.0' }, nodes: [], edges: [] },
  };
}

function noticeObservation() {
  return {
    authority: 'observation', schema_version: '1.0', source_ids: ['ntc_1'], content_hash: 'b'.repeat(64),
    content: { draft_id: 'ntc_1', content_hash: hash, entries: [] },
  };
}

function snapshot() {
  return {
    schema_version: '1.0', snapshot_id: 'rptv2_1', content_hash: hash,
    binding: { scan_ref: { scan_id: 'scn_1' }, assessment_ref: { assessment_id: 'asm_1', version: 2 }, task_refs: [{ task_id: 'tsk_1', version: 3 }], notice_refs: [], algorithm_refs: [] },
    artifacts: [
      { format: 'json', content_hash: hash, size_bytes: 100, href: '/api/v1/scans/scn_1/assessments/asm_1/report-v2/rptv2_1?format=json' },
      { format: 'html', content_hash: hash, size_bytes: 200, href: '/api/v1/scans/scn_1/assessments/asm_1/report-v2/rptv2_1?format=html' },
    ],
  };
}

const archiveScanId = 'scn_00000000-0000-0000-0000-000000000001';
const dependencySchema = 'openguard-report-v2-dependency-evidence/1';
const archivePath = (assessmentId = 'asm_1') => `/api/v1/scans/${archiveScanId}/assessments/${assessmentId}/report-v2/rptv2_1`;
const archiveHtml = '<!doctype html><html><head><meta name="openguard-html-renderer" content="1.2"></head><body>固定依赖证据</body></html>';

function dependencyFixture(assessmentId = 'asm_1') {
  const document = fixture('partial');
  const scanRef = {
    scan_id: archiveScanId, revision: null, status: 'partial', registry_revision: 3,
    facts_hash: hash, input_hash: 'b'.repeat(64), inventory_hash: null,
  };
  const assessmentRef = {
    assessment_id: assessmentId, version: 2, scan_id: archiveScanId, facts_hash: hash,
    usage_hash: 'c'.repeat(64), rule_version: 'rule-1', formal: true,
  };
  const dependency = (number, source, role, file) => ({
    resource_id: `cmp_${String(number).padStart(26, '0')}`, name: `saved-package-${number}`, version: '1.0.0',
    ecosystem: 'pypi', role_state: role, sources: [source], evidence_total: 1, evidence_returned: 1,
    evidence: [{
      evidence_id: `evd_${String(number).padStart(26, '0')}`, source, file_path: file, locator: file + ':/package/0',
      source_sha256: 'd'.repeat(64), producer: { type: 'parser', name: 'scanner', version: '1.0',
        config_digest: null, provider: null, model_id: null, prompt_schema_digest: null },
      verification_status: 'pending', kind: 'manifest_field', start_line: null, end_line: null,
    }],
    conflicts: [], conflicts_total: 0, conflicts_returned: 0, gaps: [], incomplete: false,
  });
  const lock = dependency(2, 'lock', 'unknown', 'project/uv.lock');
  lock.gaps = ['declaration_side_unavailable'];
  lock.incomplete = true;
  lock.conflicts_total = lock.conflicts_returned = 1;
  lock.conflicts.push({
    code: 'lock_version_conflict', status: 'incomplete', declaration: null,
    lock: { resource_id: lock.resource_id, version: lock.version, evidence: lock.evidence,
      evidence_total: 1, evidence_returned: 1, incomplete: false },
    gaps: lock.gaps,
  });
  const section = {
    schema_version: dependencySchema, authority: 'observation', source_ids: [archiveScanId], title: '依赖证据',
    content_hash: 'e'.repeat(64), content: {
      schema_version: dependencySchema, scan_ref: { ...scanRef }, coverage: 'unknown',
      total: 3, returned: 3, incomplete: true,
      items: [dependency(1, 'manifest', 'observed', 'project/pyproject.toml'), lock,
        dependency(3, 'sbom', 'inferred', 'project/bom.json')],
    },
  };
  document.schema_version = '1.1';
  document.binding = { scan_ref: scanRef, assessment_ref: assessmentRef, task_refs: [], notice_refs: [], algorithm_refs: [] };
  document.sections[0].content.id = archiveScanId;
  document.sections[1].content = { ...document.sections[1].content, id: assessmentId, scan_id: archiveScanId, facts_hash: hash, version: 2 };
  document.sections.push(section);
  document.sections.forEach((entry, index) => { entry.snapshot_ref = `${archivePath(assessmentId)}?format=json#/sections/${index}/content`; });
  return document;
}

function dependencySnapshot() {
  const { sections, ...document } = dependencyFixture();
  return { ...document, content_hash: hash,
    sections: sections.map(({ content, ...descriptor }) => descriptor),
    artifacts: snapshot().artifacts.map(artifact => ({ ...artifact, href: `${archivePath()}?format=${artifact.format}` })),
  };
}

test('1.1 reads one dedicated archived observation and preserves evidence scope, roles and gaps', () => {
  const service = runtime().load('services/reportV2.ts');
  const document = dependencyFixture();
  const validated = service.validateReportDocument(document, archiveScanId, 'asm_1', 'rptv2_1');
  const observations = service.classifyReportObservations(validated);
  assert.deepEqual([observations.graph.length, observations.notice.length], [0, 0]);
  const archived = observations.dependency.content;
  assert.equal(archived.scan_ref.registry_revision, 3);
  assert.equal(archived.coverage, 'unknown');
  assert.equal(archived.incomplete, true);
  assert.deepEqual(archived.items.map(item => item.role_state), ['observed', 'unknown', 'inferred']);
  assert.deepEqual(archived.items.map(item => item.sources[0]), ['manifest', 'lock', 'sbom']);
  assert.equal(archived.items[0].evidence[0].verification_status, 'pending');
  assert.equal(archived.items[0].evidence[0].file_path, 'project/pyproject.toml');
  assert.equal(archived.items[0].evidence[0].source_sha256, 'd'.repeat(64));
  assert.equal(archived.items[1].conflicts[0].declaration, null);
  assert.deepEqual(archived.items[1].conflicts[0].gaps, ['declaration_side_unavailable']);
  assert.equal(service.classifyReportObservations(fixture()).dependency, null);
});

test('archive decoder rejects absent, masquerading, duplicate or foreign 1.1 evidence and malformed rows', () => {
  const service = runtime().load('services/reportV2.ts');
  const invalid = [
    document => { document.schema_version = '1.0'; },
    document => { document.schema_version = '1.2'; },
    document => { document.sections.length -= 1; },
    (document, section) => { document.sections.push({ ...section, snapshot_ref: `${archivePath()}?format=json#/sections/5/content` }); },
    (_, section) => { section.title = '其他观测'; },
    (_, section) => { section.authority = 'workflow'; },
    (_, section) => { section.source_ids = ['unrelated']; },
    (_, section) => { section.snapshot_ref = archivePath() + '?format=json#/sections/3/content'; },
    (_, section) => { section.content.scan_ref.registry_revision += 1; },
    (_, section) => { section.content.scan_ref.facts_hash = 'f'.repeat(64); },
    (_, section) => { section.content.total += 1; },
    (_, section) => { section.content.next_cursor = null; },
    (_, section) => { section.content.incomplete = false; },
    (_, section) => { section.content.items[1].conflicts[0].status = 'confirmed'; },
    (document) => { document.binding.assessment_ref.formal = false; },
    (document) => { document.sections[0].content.status = 'completed'; },
  ];
  for (const mutate of invalid) {
    const document = dependencyFixture();
    mutate(document, document.sections.at(-1));
    assert.throws(() => service.validateReportDocument(document, archiveScanId, 'asm_1', 'rptv2_1'), /契约/);
  }
});

test('1.1 creation checks snapshot dependency metadata and matches the explicitly requested version', async () => {
  const r = runtime(), service = r.load('services/reportV2.ts'), bodies = [];
  r.setFetch(async (_url, init) => {
    bodies.push(JSON.parse(init.body));
    return Response.json(dependencySnapshot());
  });
  const created = await service.createReportV2(archiveScanId, 'asm_1', 'key-v11', [], [], '1.1');
  assert.equal(created.schema_version, '1.1');
  assert.deepEqual(bodies, [{ idempotency_key: 'key-v11', task_refs: [], notice_refs: [], algorithm_refs: [], schema_version: '1.1' }]);
  await assert.rejects(service.createReportV2(archiveScanId, 'asm_1', 'default', []), /归档格式与所选版本不一致/);
  assert.equal(Object.hasOwn(bodies[1], 'schema_version'), false);
  for (const mutate of [
    snapshot => { snapshot.sections.pop(); },
    snapshot => { snapshot.sections.at(-1).content = {}; },
    snapshot => { snapshot.sections.at(-1).title = '其他观测'; },
    snapshot => { snapshot.sections.at(-1).source_ids = ['unrelated']; },
    snapshot => { snapshot.artifacts[0].href = snapshot.artifacts[0].href.replace('rptv2_1', 'other'); },
  ]) {
    const snapshot = dependencySnapshot();
    mutate(snapshot);
    assert.throws(() => service.validateReportSnapshot(snapshot, archiveScanId, 'asm_1'), /契约/);
  }
  r.setFetch(async () => Response.json(snapshot()));
  await assert.rejects(service.createReportV2('scn_1', 'asm_1', 'explicit-v11', [], [], '1.1'), /归档格式与所选版本不一致/);
  assert.equal((await service.createReportV2('scn_1', 'asm_1', 'explicit-v10', [], [], '1.0')).schema_version, '1.0');
});

test('TEST_ONLY BOUND draft POST/GET feeds exact Report refs and reload uses JSON/HTML GET only', async () => {
  const r = runtime(), notices = r.load('services/noticeDrafts.ts'), reports = r.load('services/reportV2.ts');
  const draft = {
    schema_version: '1.0', draft_id: 'ntc_1', generator_version: 'notice-bound/1.0',
    created_at: '2026-09-28T00:00:00Z', content_hash: hash,
    binding: { scan_ref: { scan_id: 'scn_1' }, assessment_ref: { assessment_id: 'asm_1', version: 2 } },
    entries: [{ entry_id: 'entry_1', text: 'bounded text', resource_ids: [], license_expression_ids: [],
      obligation_refs: [], evidence_refs: [], missing: ['notice_source_excerpt_truncated', 'resource_relation_unresolved'] }],
    coverage_gaps: ['notice_source_partial'], provenance: {},
  };
  const ref = { draft_id: draft.draft_id, content_hash: draft.content_hash };
  const doc = fixture('partial', [{ ...noticeObservation(), content: draft }]);
  doc.binding.notice_refs = [ref];
  const html = '<!doctype html><html><head><meta name="openguard-html-renderer" content="1.1"></head><body>bounded text</body></html>';
  const calls = [];
  r.setFetch(async (url, init) => {
    calls.push({ method: init.method ?? 'GET', url, body: init.body && JSON.parse(init.body) });
    if (url.includes('/notice-drafts')) return Response.json(draft);
    if (init.method === 'POST') {
      assert.deepEqual(JSON.parse(init.body).notice_refs, [ref]);
      return Response.json({ ...snapshot(), binding: { ...snapshot().binding, notice_refs: [ref] } });
    }
    return url.endsWith('format=json') ? Response.json(doc) : new Response(html, { headers: { 'Content-Type': 'text/html' } });
  });
  const created = await notices.createNoticeDraft('scn_1', 'asm_1', 'draft-key');
  const stored = await notices.getNoticeDraft('scn_1', 'asm_1', created.draft_id);
  assert.equal(JSON.stringify(stored), JSON.stringify(created));
  const report = await reports.createReportV2('scn_1', 'asm_1', 'report-key', [], [{ draft_id: stored.draft_id, content_hash: stored.content_hash }]);
  const reloaded = await reports.loadReportV2('scn_1', 'asm_1', report.snapshot_id);
  assert.equal(reloaded.html, html);
  assert.equal(reports.classifyReportObservations(reloaded.document).notice.length, 1);
  assert.equal(reports.classifyReportObservations(reloaded.document).graph.length, 0);
  assert.deepEqual(calls.map(c => c.method), ['POST', 'GET', 'POST', 'GET', 'GET']);
  assert.equal(r.storage.size, 0);
});

test('Report V2 URL binds scan, assessment, snapshot and format', () => {
  const service = runtime().load('services/reportV2.ts');
  assert.equal(service.reportV2Url('s/1', 'a/2', 'r/3', 'html'), '/api/v1/scans/s%2F1/assessments/a%2F2/report-v2/r%2F3?format=html');
});

test('explicit creation binds current task versions and never supplies invented Notice or graph refs', async () => {
  const r = runtime({ VITE_API_BASE_URL: '/api/v1' }), service = r.load('services/reportV2.ts');
  let call;
  r.setFetch(async (url, init) => { call = [url, init]; return Response.json(snapshot()); });
  const created = await service.createReportV2('scn_1', 'asm_1', 'report-key', [{ task_id: 'tsk_1', version: 3 }]);
  assert.equal(created.snapshot_id, 'rptv2_1');
  assert.equal(call[0], '/api/v1/scans/scn_1/assessments/asm_1/report-v2');
  assert.equal(call[1].method, 'POST');
  assert.deepEqual(JSON.parse(call[1].body), { idempotency_key: 'report-key', task_refs: [{ task_id: 'tsk_1', version: 3 }], notice_refs: [], algorithm_refs: [] });
  assert.equal(r.storage.size, 0);
  assert.throws(() => service.validateReportSnapshot({ ...snapshot(), binding: { ...snapshot().binding, scan_ref: { scan_id: 'other' } } }, 'scn_1', 'asm_1'), /契约/);
});

test('Report V2 includes only an exact backend NoticeDraft id and content hash', async () => {
  const r = runtime({ VITE_API_BASE_URL: '/api/v1' }), service = r.load('services/reportV2.ts');
  let body;
  r.setFetch(async (_url, init) => {
    body = JSON.parse(init.body);
    return Response.json({ ...snapshot(), binding: { ...snapshot().binding, notice_refs: [{ draft_id: 'ntc_1', content_hash: hash }] } });
  });
  const created = await service.createReportV2('scn_1', 'asm_1', 'report-with-notice', [{ task_id: 'tsk_1', version: 3 }], [{ draft_id: 'ntc_1', content_hash: hash }]);
  assert.deepEqual(body.notice_refs, [{ draft_id: 'ntc_1', content_hash: hash }]);
  assert.equal(created.binding.notice_refs[0].draft_id, 'ntc_1');
  await assert.rejects(async () => service.createReportV2('scn_1', 'asm_1', 'bad', [], [{ draft_id: 'ntc_1', content_hash: 'bad' }]), /参数无效/);
});

test('observation classification uses binding, source ids and content structure instead of authority alone', () => {
  const service = runtime().load('services/reportV2.ts');
  const cases = [
    { name: 'only Graph', extra: [graphObservation()], binding: { algorithm_refs: [{ kind: 'graph', version: 'graph/1.0', content_hash: hash }], notice_refs: [] }, expected: [1, 0] },
    { name: 'only NOTICE', extra: [noticeObservation()], binding: { algorithm_refs: [], notice_refs: [{ draft_id: 'ntc_1', content_hash: hash }] }, expected: [0, 1] },
    { name: 'Graph and NOTICE', extra: [graphObservation(), noticeObservation()], binding: { algorithm_refs: [{ kind: 'graph', version: 'graph/1.0', content_hash: hash }], notice_refs: [{ draft_id: 'ntc_1', content_hash: hash }] }, expected: [1, 1] },
    { name: 'neither', extra: [], binding: { algorithm_refs: [], notice_refs: [] }, expected: [0, 0] },
  ];
  for (const item of cases) {
    const value = fixture('completed', item.extra);
    value.binding = { ...value.binding, ...item.binding };
    const groups = service.classifyReportObservations(value);
    assert.deepEqual([groups.graph.length, groups.notice.length], item.expected, item.name);
  }
  const unbound = fixture('completed', [graphObservation(), noticeObservation()]);
  const unboundGroups = service.classifyReportObservations(unbound);
  assert.deepEqual([unboundGroups.graph.length, unboundGroups.notice.length], [0, 0]);
});

test('failed creation exposes a manual retry and reuses the same idempotency key and references', async () => {
  const r = runtime({ VITE_API_BASE_URL: '/api/v1' }), service = r.load('services/reportV2.ts');
  const calls = [];
  r.setFetch(async (_url, init) => {
    calls.push(JSON.parse(init.body));
    if (calls.length === 1) throw new TypeError('offline');
    return Response.json(snapshot());
  });
  const taskRefs = [{ task_id: 'tsk_1', version: 3 }];
  const noticeRefs = [{ draft_id: 'ntc_1', content_hash: hash }];
  await assert.rejects(service.createReportV2('scn_1', 'asm_1', 'stable-key', taskRefs, noticeRefs), /连接|失败|offline/);
  const control = service.reportCreateControl({ assessmentId: 'asm_1', createLoading: false, creating: false, loadError: '', createError: '网络失败' });
  assert.equal(control.disabled, false);
  assert.match(control.label, /重试创建/);
  await service.createReportV2('scn_1', 'asm_1', 'stable-key', taskRefs, noticeRefs);
  assert.deepEqual(calls[0], calls[1]);
  assert.equal(calls[1].idempotency_key, 'stable-key');
  assert.equal(service.reportCreateControl({ assessmentId: 'asm_1', createLoading: false, creating: false, loadError: 'Task 读取失败', createError: '' }).disabled, true);
});

test('only a bound Formal Assessment snapshot is accepted', () => {
  const service = runtime().load('services/reportV2.ts');
  assert.equal(service.validateReportDocument(fixture('partial'), 'scn_1', 'asm_1', 'rptv2_1').binding.scan_ref.status, 'partial');
  for (const [value, scan, assessment, snapshot] of [
    [fixture(), 'wrong', 'asm_1', 'rptv2_1'], [fixture(), 'scn_1', 'wrong', 'rptv2_1'], [fixture(), 'scn_1', 'asm_1', 'wrong'],
    [{ ...fixture(), sections: fixture().sections.filter(section => section.authority !== 'formal_assessment') }, 'scn_1', 'asm_1', 'rptv2_1'],
    [{ ...fixture(), sections: fixture().sections.map(section => section.authority === 'formal_assessment' ? { ...section, content: { ...section.content, formal: false } } : section) }, 'scn_1', 'asm_1', 'rptv2_1'],
  ]) assert.throws(() => service.validateReportDocument(value, scan, assessment, snapshot), /契约/);
});

test('large saved body is displayed from GET only; no creation or model call', async () => {
  const r = runtime(), service = r.load('services/reportV2.ts'), calls = [];
  const html = '<!doctype html><html><head><meta name="openguard-html-renderer" content="1.1"></head><body>' + '固定正文'.repeat(20000) + '</body></html>';
  r.setFetch(async (url, options) => {
    calls.push([url, options.method]);
    return url.endsWith('format=json') ? Response.json(fixture('partial')) : new Response(html, { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
  });
  const result = await service.loadReportV2('scn_1', 'asm_1', 'rptv2_1');
  assert.equal(result.html, html);
  assert.equal(result.document.binding.scan_ref.status, 'partial');
  assert.deepEqual(calls.map(call => call[1]), ['GET', 'GET']);
  assert.equal(r.storage.size, 0);
});

test('missing report, wrong MIME, malformed JSON and failed download never fall back to mock', async () => {
  const r = runtime(), service = r.load('services/reportV2.ts');
  r.setFetch(async () => new Response('{}', { status: 404, headers: { 'Content-Type': 'application/json' } }));
  await assert.rejects(service.loadReportV2('scn_1', 'asm_1', 'rptv2_1'), error => error.status === 404);
  await assert.rejects(service.downloadReportV2('scn_1', 'asm_1', 'rptv2_1', 'html'), error => error.status === 404);
  r.setFetch(async () => new Response('<html>SPA</html>', { headers: { 'Content-Type': 'text/html' } }));
  await assert.rejects(service.loadReportV2('scn_1', 'asm_1', 'rptv2_1'), /格式/);
  r.setFetch(async () => Response.json({ ...fixture(), sections: [] }));
  await assert.rejects(service.loadReportV2('scn_1', 'asm_1', 'rptv2_1'), /契约/);
  assert.equal(r.storage.size, 0);
});

test('report route preserves IDs on reload and share', () => {
  const r = runtime(), route = r.load('hooks/useRoute.ts');
  r.shared.window.location = { pathname: '/app/scans/scn_1/report-v2', search: '?mode=api&assessment_id=asm_1&snapshot_id=rptv2_1' };
  const parsed = route.readRoute();
  assert.equal(parsed.page, 'report-v2');
  assert.equal(parsed.scanId, 'scn_1');
  assert.equal(parsed.query.get('snapshot_id'), 'rptv2_1');
});

function formalAssessment(id = 'asm_old', version = 1) {
  return { id, scan_id: 'scn_1', version, formal: true, facts_hash: hash, usage: { preset: 'unknown' },
    generated_at: '2026-09-18T00:00:00Z', ai_status: 'not_requested', ai_summary: null,
    summary: '材料待核验', dimensions: [], coverage_issues: [], resource_ids: [], finding_ids: [], evidence_ids: [], obligations: [] };
}

test('report creation resolves an explicitly requested historical assessment beyond the first page', async () => {
  const r = runtime(), service = r.load('services/reportV2.ts'), calls = [];
  r.setFetch(async (url, init) => {
    calls.push([url, init.method ?? 'GET']);
    return Response.json(url.endsWith('/assessments')
      ? { items: Array.from({ length: 20 }, (_, i) => formalAssessment(`asm_${30 - i}`, 30 - i)), has_more: true }
      : formalAssessment());
  });
  const options = await service.loadReportAssessmentChoices('scn_1', 'asm_old');
  assert.equal(options.selectedId, 'asm_old');
  assert.equal(options.items.find(item => item.id === 'asm_old').version, 1);
  assert.deepEqual(calls.map(c => c[1]), ['GET', 'GET']);
  assert.ok(calls.some(c => c[0] === '/api/v1/scans/scn_1/assessments/asm_old'));
  assert.equal(r.storage.size, 0);
});

test('a missing or cross-bound requested report assessment blocks rather than choosing latest', async () => {
  for (const mode of ['missing', 'wrong_id', 'wrong_scan', 'not_formal']) {
    const r = runtime(), service = r.load('services/reportV2.ts');
    r.setFetch(async url => {
      if (url.endsWith('/assessments')) return Response.json({ items: [formalAssessment('latest', 99)] });
      if (mode === 'missing') return Response.json({ error: { code: 'not_found' } }, { status: 404 });
      const exact = formalAssessment();
      if (mode === 'wrong_id') exact.id = 'latest';
      if (mode === 'wrong_scan') exact.scan_id = 'other_scan';
      if (mode === 'not_formal') exact.formal = false;
      return Response.json(exact);
    });
    await assert.rejects(service.loadReportAssessmentChoices('scn_1', 'asm_old'), undefined, mode);
  }
});

test('report creation without an explicit assessment can select the latest formal record', async () => {
  const r = runtime(), service = r.load('services/reportV2.ts'), calls = [];
  r.setFetch(async (url, init) => { calls.push(init.method ?? 'GET'); return Response.json({ items: [formalAssessment('latest', 9)] }); });
  const options = await service.loadReportAssessmentChoices('scn_1', '');
  assert.equal(options.selectedId, 'latest');
  assert.deepEqual(calls, ['GET']);
});

test('fixed report navigation keeps both IDs on the same scan but never leaks into a different scan', () => {
  const s = runtime().load('services/reportV2.ts');
  const current = new URLSearchParams('mode=api&assessment_id=asm_old&snapshot_id=rpt_old&resource_id=private');
  assert.equal(s.reportNavigationQuery('scn_1', 'scn_1', current).toString(), 'assessment_id=asm_old&snapshot_id=rpt_old');
  assert.equal(s.reportNavigationQuery('scn_1', 'scn_2', current).toString(), '');
  assert.equal(s.reportNavigationQuery('', '', current).toString(), '');
  assert.equal(s.reportNavigationQuery('scn_1', 'scn_1', new URLSearchParams('snapshot_id=orphan')).toString(), '');
});

test('fixed report iframe permits print modals while keeping script and navigation restrictions', async () => {
  const { readFileSync } = await import('node:fs');
  const source = readFileSync(new URL('../src/pages/ReportV2.tsx', import.meta.url), 'utf8');
  const sandbox = source.match(/<iframe\b[^>]*sandbox="([^"]+)"/)[1].split(/\s+/);
  assert.ok(sandbox.includes('allow-modals'));
  assert.ok(sandbox.includes('allow-same-origin'));
  assert.ok(!sandbox.includes('allow-scripts'));
  assert.ok(!sandbox.some(value => value.startsWith('allow-top-navigation')));
});

async function reportPageHarness(exactResponse, { scanId = 'scn_1', snapshotId = '', createResponse } = {}) {
  const fs = await import('node:fs'), vm = await import('node:vm'), { default: ts } = await import('typescript');
  const r = runtime(), states = [], refs = [], effects = [], calls = [], opened = [];
  let si = 0, ri = 0, ei = 0, dirty = true, tree, pending = [];
  const nodes = value => !value || typeof value !== 'object' ? [] : Array.isArray(value) ? value.flatMap(nodes) : [value, ...nodes(value.props?.children)];
  const text = value => value == null || typeof value === 'boolean' ? '' : Array.isArray(value) ? value.map(text).join('') : typeof value === 'object' ? text(value.props?.children) : String(value);
  const hooks = {
    useState(initial) { const i = si++; if (!(i in states)) states[i] = typeof initial === 'function' ? initial() : initial;
      return [states[i], value => { const next = typeof value === 'function' ? value(states[i]) : value; if (!Object.is(states[i], next)) { states[i] = next; dirty = true; } }]; },
    useRef(value) { const i = ri++; return refs[i] ?? (refs[i] = { current: value }); },
    useEffect(fn, deps) { const i = ei++, old = effects[i]; if (!old || deps.some((value, j) => !Object.is(value, old.deps[j]))) {
      effects[i] = { deps, cleanup: old?.cleanup }; pending.push(() => { old?.cleanup?.(); effects[i].cleanup = fn(); }); } },
  };
  r.setFetch(async (url, init) => {
    calls.push({ url, method: init.method ?? 'GET', body: init.body && JSON.parse(init.body) });
    if (url.endsWith('/assessments')) return Response.json({ items: [{ ...formalAssessment('latest', 22), scan_id: scanId }] });
    if (url.includes('/remediation-tasks')) return Response.json({ schema_version: '1.0', items: [], next_cursor: null });
    if (init.method === 'POST') return createResponse ? createResponse() : Response.json({ ...snapshot(), binding: { ...snapshot().binding, assessment_ref: { assessment_id: 'asm_old', version: 1 } }, artifacts: snapshot().artifacts.map(item => ({ ...item, href: item.href.replace('/asm_1/', '/asm_old/') })) });
    return exactResponse(url);
  });
  const m = { exports: {} };
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../src/pages/ReportV2.tsx', import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText, { ...r.shared, module: m, exports: m.exports, require: name => name === 'react' ? hooks
    : name === 'react/jsx-runtime' ? { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) }
    : name.endsWith('/components/ui') ? { Header: 'Header', Panel: 'Panel', ActionButton: 'button', useNotice: () => () => {} }
    : r.load(name.replace(/^\.\.\//, '') + '.ts') });
  const query = new URLSearchParams('assessment_id=asm_old');
  if (snapshotId) query.set('snapshot_id', snapshotId);
  const props = { scan: { id: scanId, mode: 'api' }, query, open: (...ids) => opened.push(ids) };
  async function settle() { for (let i = 0; i < 30; i++) { if (dirty) { dirty = false; si = ri = ei = 0; pending = []; tree = m.exports.ReportV2(props); for (const effect of pending) effect(); }
    await new Promise(resolve => setImmediate(resolve)); if (!dirty) return; } throw Error('component did not settle'); }
  await settle();
  return { calls, opened, settle, get tree() { return tree; }, get text() { return text(tree); },
    get createButton() { return nodes(tree).find(n => n.type === 'button' && /创建并打开固定报告|重试创建/.test(text(n))); },
    get selection() { return nodes(tree).find(n => n.type === 'select')?.props.value; },
    selectAssessment(value) { nodes(tree).find(n => n.type === 'select').props.onChange({ target: { value } }); },
    get versionSelector() { return nodes(tree).find(n => n.type === 'select' && n.props.name === 'report-schema-version'); },
    get iframe() { return nodes(tree).find(n => n.type === 'iframe'); },
    dispose() { effects.forEach(effect => effect.cleanup?.()); } };
}

test('reselecting the current archive Assessment never leaves task loading latched', async () => {
  const h = await reportPageHarness(() => Response.json(formalAssessment()));
  try {
    assert.equal(h.selection, 'asm_old');
    assert.equal(h.createButton.props.disabled, false);
    const reads = h.calls.filter(call => call.method === 'GET').length;
    h.selectAssessment(h.selection);
    await h.settle();
    assert.equal(h.createButton.props.disabled, false, 'same value does not rerun the task effect and must not mark it loading');
    assert.equal(h.calls.filter(call => call.method === 'GET').length, reads);
    assert.equal(h.calls.filter(call => call.method === 'POST').length, 0);
  } finally { h.dispose(); }
});

test('actual ReportV2 page keeps a missing explicit assessment blocked and sends no create request', async () => {
  const h = await reportPageHarness(() => Response.json({ error: { code: 'not_found' } }, { status: 404 }));
  try {
    assert.equal(h.selection, '');
    assert.equal(h.createButton.props.disabled, true);
    await h.createButton.props.onClick();
    assert.equal(h.calls.filter(call => call.method === 'POST').length, 0);
    assert.equal(h.opened.length, 0);
  } finally { h.dispose(); }
});

test('actual ReportV2 page creates against the exact old assessment and only explicit clicking writes', async () => {
  const h = await reportPageHarness(() => Response.json(formalAssessment()));
  try {
    assert.equal(h.selection, 'asm_old');
    assert.equal(h.createButton.props.disabled, false);
    assert.equal(h.calls.filter(call => call.method === 'POST').length, 0);
    await h.createButton.props.onClick();
    const posts = h.calls.filter(call => call.method === 'POST');
    assert.equal(posts.length, 1);
    assert.equal(posts[0].url, '/api/v1/scans/scn_1/assessments/asm_old/report-v2');
    assert.equal(h.opened[0][0], 'asm_old');
  } finally { h.dispose(); }
});

test('page 1.1 opt-in keeps separate retry keys and does not fall back if new writes are disabled', async () => {
  const h = await reportPageHarness(() => Response.json(formalAssessment()), { createResponse: () => Response.json({
    error: { code: 'not_ready', message: 'blocked in this test', details: { reason: 'report_v2_1_1_write_disabled' } },
  }, { status: 409 }) });
  const posts = () => h.calls.filter(call => call.method === 'POST').map(call => call.body);
  async function select(value) {
    h.versionSelector.props.onChange({ target: { value } });
    await h.settle();
  }
  try {
    assert.equal(h.versionSelector.props.value, '1.0');
    await h.createButton.props.onClick();
    await h.settle();
    assert.equal(Object.hasOwn(posts()[0], 'schema_version'), false);
    await select('1.1');
    assert.equal(posts().length, 1);
    await h.createButton.props.onClick();
    await h.settle();
    assert.equal(posts().length, 2);
    assert.equal(posts()[1].schema_version, '1.1');
    assert.notEqual(posts()[0].idempotency_key, posts()[1].idempotency_key);
    assert.match(h.text, /暂未开放新建含依赖证据/);
    assert.deepEqual(h.opened, []);
    await h.createButton.props.onClick();
    await h.settle();
    assert.deepEqual(posts()[2], posts()[1]);
    await select('1.0');
    await h.createButton.props.onClick();
    assert.deepEqual(posts()[3], posts()[0]);
    assert.equal(posts().length, 4);
  } finally { h.dispose(); }
});

test('page reads a saved 1.1 report with server HTML and preserves the archived evidence summary', async () => {
  const h = await reportPageHarness(url => {
    if (url.endsWith('format=json')) return Response.json(dependencyFixture('asm_old'));
    if (url.endsWith('format=html')) return new Response(archiveHtml, { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
    return Response.json({ ...formalAssessment(), scan_id: archiveScanId });
  }, { scanId: archiveScanId, snapshotId: 'rptv2_1' });
  try {
    assert.equal(h.iframe.props.srcDoc, archiveHtml);
    assert.match(h.text, /依赖证据 · 已归档 3 项。归档证据存在缺口/);
    assert.deepEqual(h.calls.filter(call => call.url.includes('/report-v2/')).map(call => [call.method, call.url]), [
      ['GET', archivePath('asm_old') + '?format=json'], ['GET', archivePath('asm_old') + '?format=html'],
    ]);
    assert.ok(h.calls.every(call => call.method === 'GET'));
  } finally { h.dispose(); }
});

test('same-scan navigation preserves the actual P2 revision pinned by replaceState', () => {
  const r = runtime(), routes = r.load('hooks/useRoute.ts'), service = r.load('services/reportV2.ts');
  r.shared.window.location = { pathname: '/app/scans/scn_1/assessment', search: '?mode=api&assessment_id=asm_old&p2_result=p2res_r1' };
  const current = routes.readRoute();
  const query = service.reportNavigationQuery(current.scanId, 'scn_1', current.query);
  assert.equal(query.get('p2_result'), 'p2res_r1');
  assert.equal(query.get('assessment_id'), 'asm_old');
  assert.equal(service.reportNavigationQuery(current.scanId, 'scn_other', current.query).toString(), '');
});

test('App reads current route and exposes one current assistant without the obsolete chat entry', async () => {
  const { readFileSync } = await import('node:fs');
  const source = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  assert.match(source, /const current = readRoute\(\);\s*query = reportNavigationQuery\(current.scanId, route.scanId, current.query\)/);
  const {default:ts}=await import('typescript'),vm=await import('node:vm');
  const ast=ts.createSourceFile('App.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  let selected, navigationItems;
  function visit(node){
    if(ts.isFunctionDeclaration(node)&&node.name?.text==='selectAssessment')selected=node;
    if(ts.isVariableDeclaration(node)&&ts.isIdentifier(node.name)&&node.name.text==='items')navigationItems=node.initializer;
    ts.forEachChild(node,visit);
  }
  visit(ast);assert.ok(selected,'actual selectAssessment implementation exists');
  assert.ok(navigationItems && ts.isArrayLiteralExpression(navigationItems),'actual navigation list exists');
  const pages=navigationItems.elements.map(row=>{assert.ok(ts.isArrayLiteralExpression(row));assert.ok(ts.isStringLiteral(row.elements[0]));return row.elements[0].text;});
  assert.equal(pages.includes('chat'),false,'obsolete project-chat entry is not exposed');
  assert.equal(pages.filter(page=>page==='assistant').length,1,'one current assistant entry');
  for(const page of ['new-scan','assessment','report','report-v2','history'])assert.ok(pages.includes(page),page+' remains reachable');
  const code=ts.transpileModule(selected.getText(ast),{compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText;
  for(const [id,changed]of [['asm_new',true],['asm_old',false]]){
    const original=new URLSearchParams('assessment_id=asm_old&snapshot_id=snap&p2_result=result&p2_result_id=alias&p2_revision=4&assessment_version=1&report_id=report&notice_id=notice&resource_id=keep');
    const calls=[],context={URLSearchParams,route:{query:original,scanId:'scan',page:'assessment',mode:'api'},scanPath:(...args)=>args,go:value=>calls.push(value)};
    vm.runInNewContext(code+'\nselectAssessment('+JSON.stringify(id)+');',context);
    assert.equal(calls.length,1);const [scan,page,mode,params]=calls[0];
    assert.deepEqual([scan,page,mode],['scan','assessment','api']);assert.equal(params.get('assessment_id'),id);
    for(const key of ['snapshot_id','p2_result','p2_result_id','p2_revision','assessment_version','report_id','notice_id'])assert.equal(params.get(key),changed?null:original.get(key),key);
    assert.equal(params.get('resource_id'),'keep');assert.equal(original.get('assessment_id'),'asm_old');assert.equal(original.get('p2_result'),'result');
  }
});

test('opening or creating a report retains the same assessment result and clears cross-assessment pins', () => {
  const service = runtime().load('services/reportV2.ts');
  const current = new URLSearchParams('assessment_id=asm_old&p2_result=p2res_r1&snapshot_id=old');
  const same = service.reportSnapshotQuery('scn_1','scn_1',current,'asm_old','report_new');
  assert.equal(same.get('p2_result'),'p2res_r1');
  assert.equal(same.get('snapshot_id'),'report_new');
  for (const [scan,assessment] of [['scn_2','asm_old'],['scn_1','asm_other']]) {
    const changed = service.reportSnapshotQuery('scn_1',scan,current,assessment,'report_new');
    assert.equal(changed.get('p2_result'),null);
    assert.equal(changed.get('assessment_id'),assessment);
  }
  assert.equal(current.get('snapshot_id'),'old');
});
