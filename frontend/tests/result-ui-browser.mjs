// TEST_ONLY visual regression. Recorded P2 responses plus declared UI fixtures;
// every request is intercepted. No live backend, state writes or production seed.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { runtime } from './runtime.mjs';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.OPENGUARD_PLAYWRIGHT || 'playwright');
const here = path.dirname(fileURLToPath(import.meta.url));
const output = process.env.OPENGUARD_QA_OUTPUT;
assert.ok(output && process.env.P2_HTTP_EVENTS, 'Supply fresh output and recorded TEST_ONLY HTTP events');
const events = JSON.parse(await fs.readFile(process.env.P2_HTTP_EVENTS, 'utf8'));
const material = events.find(e => e.method === 'POST' && e.path.endsWith('/p2/materials') && e.status === 201);
const result = material.response.result, binding = result.binding;
const scan = binding.scan_id, asm = binding.assessment_id;
const prefix = `/api/v1/scans/${scan}`, p2 = `${prefix}/assessments/${asm}/p2`;
const exact = key => events.filter(e => e.method === 'GET' && e.path === key && e.status === 200).at(-1)?.response;
const assessment = exact(`${prefix}/assessments/${asm}`);
const fixtureDir = path.resolve(here, '../../tests/fixtures/p1-integration-v1');
const history = JSON.parse(await fs.readFile(path.join(fixtureDir, 'history.json'), 'utf8')).items;
const graphs = {};
for (const count of [100, 300, 500]) {
  const source = JSON.parse(await fs.readFile(path.join(fixtureDir, `graph-${count}.json`), 'utf8'));
  graphs[count] = JSON.parse(JSON.stringify(source).replaceAll(source.scan_ref.scan_id, scan));
  // Existing shared fixtures include Assessment references; this UI's frozen
  // facts-only contract requires none. Adapt only isolated test provenance.
  graphs[count].provenance.assessment_refs = [];
  runtime().load('services/p1Graph.ts').parseResourceGraph(graphs[count], scan);
}
const H = 'a'.repeat(64), snapshot = 'rptv2_TEST_ONLY_UI';
const tasks = ['todo', 'in_progress', 'done', 'dismissed'].map((status, i) => ({
  schema_version: '1.0', task_id: `tsk_TEST_ONLY_${i}`, scan_id: scan,
  assessment_ref: { assessment_id: asm, version: assessment.version, scan_id: scan,
    facts_hash: assessment.facts_hash, usage_hash: assessment.usage_hash, rule_version: assessment.rule_version, formal: true },
  origin: { kind: 'gap', source_pointer: '/resource_evaluations/0', source_hash: H },
  resource_ids: [result.resources[0].subject.resource_id], evidence_refs: [],
  title: 'TEST_ONLY · 核对资源来源与待核验材料', status, note: '界面测试备注，不代表义务已履行',
  version: 3, superseded: false, created_at: '2026-10-24T00:00:00Z', updated_at: '2026-10-24T00:00:00Z',
}));
const document = { schema_version: '1.0', snapshot_id: snapshot,
  binding: { scan_ref: { scan_id: scan, status: 'partial', revision: 'TEST_ONLY_REVISION' },
    assessment_ref: { assessment_id: asm, version: assessment.version }, notice_refs: [] },
  created_at: '2026-10-24T00:00:00Z', generator_version: 'TEST_ONLY_UI', provenance: { grade: 'TEST_ONLY' },
  sections: ['scan_facts', 'formal_assessment', 'workflow', 'ai_explanation'].map(authority => ({
    authority, schema_version: '1.0', source_ids: [asm], content_hash: H,
    content: authority === 'formal_assessment' ? assessment : { grade: 'TEST_ONLY' },
  })),
};
const reportHTML = '<!doctype html><html><head><meta name="generator" content="openguard-html-renderer"><style>body{font:16px/1.8 sans-serif;color:#172234;padding:24px}h1{font-size:26px}</style></head><body><h1>TEST_ONLY · 报告阅读样板</h1><p>隔离布局测试，不是正式报告或许可证证明。</p>' + '<p>正文段落：未知保持未知，义务仍待核验。此内容用于检查长报告阅读和打印。</p>'.repeat(30) + '</body></html>';
let servedDist = path.resolve(here, '../dist'), graphCount = 100;
const origin = 'http://openguard-ui-test.local';
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce', serviceWorkers: 'block' });
await context.addInitScript(() => {
  if (!crypto.randomUUID) Object.defineProperty(crypto, 'randomUUID', { value: () => 'test-only-fixed-key' });
  addEventListener('DOMContentLoaded', () => {
    const badge = document.createElement('div'); badge.textContent = 'TEST_ONLY · 隔离界面测试，非真实项目结论';
    badge.style.cssText = 'position:fixed;bottom:0;left:0;z-index:99999;background:#f3d28c;color:#172234;padding:4px 12px;font:12px sans-serif;pointer-events:none';
    document.body.append(badge);
  });
});
const page = await context.newPage(); page.setDefaultTimeout(12000);
const requests = [], errors = [], unexpected = [], checks = [], timings = [];
page.on('pageerror', e => errors.push(e.message));
await context.route('**/*', async route => {
  const req = route.request(), url = new URL(req.url()), key = url.pathname + url.search;
  if (url.origin !== origin || req.method() !== 'GET') { unexpected.push(req.method() + ' ' + key); return route.abort(); }
  const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
  const fail = (status, code, reason) => json({ error: { code, message: code, details: { reason } } }, status);
  if (!url.pathname.startsWith('/api/')) {
    const relative = decodeURIComponent(url.pathname).replace(/^\/+/, '');
    const file = path.extname(relative) ? path.resolve(servedDist, relative) : path.join(servedDist, 'index.html');
    assert.ok(file.startsWith(servedDist + path.sep));
    return route.fulfill({ path: file, contentType: ({ '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.mp4': 'video/mp4' })[path.extname(file)] });
  }
  requests.push(key);
  if (url.pathname === '/api/v1/scans') return json({ schema_version: '1.0', items: history.slice(0, 20), next_cursor: null });
  if (key === p2 + '/binding') return json(binding);
  if (key.startsWith(p2 + '/results?')) return json({ head_result_id: result.result_id, head_revision: result.revision, result_ids: [result.result_id], has_more: false });
  if (key === `${p2}/results/${result.result_id}?assessment_version=${binding.assessment_version}`) return json(result);
  if (key === `${p2}/results/${result.result_id}/summary?assessment_version=${binding.assessment_version}`) return json({
    summary_id: result.companion_summary_id, result_id: result.result_id, result_revision: result.revision,
    result_sha256: result.result_sha256, binding, material_ids: result.material_ids, answer_ids: result.answer_ids,
    state: result.state, resource_states: Object.fromEntries(result.resources.map(r => [r.subject.resource_id, r.state])),
    formal_effect: 'none', report_kind: 'P2_COMPANION_NOT_FORMAL_REPORT',
  });
  if (key === prefix + '/graph') return json(graphs[graphCount]);
  if (key.startsWith(`${prefix}/assessments/${asm}/remediation-tasks?`)) return json({ schema_version: '1.0', items: tasks, next_cursor: null });
  if (key === `${prefix}/assessments/${asm}/report-v2/${snapshot}?format=json`) return json(document);
  if (key === `${prefix}/assessments/${asm}/report-v2/${snapshot}?format=html`) return route.fulfill({ contentType: 'text/html', body: reportHTML });
  if (key === prefix + '/assessments') return json({ items: [assessment], usage: assessment.usage, pending_job: null });
  if (key === prefix + '/chat') return json({ items: [], generation: 0, limits: { max_message_chars: 2000, max_turns: 20 } });
  if (key === prefix + '/risks') return json({ items: [], total: 0 });
  if (url.pathname.endsWith('/profile')) return fail(404, 'not_found', 'TEST_ONLY_PROFILE_ABSENT');
  if (key === prefix + '/resources') {
    const resources = structuredClone(exact(key));
    // Declared layout adapter for AI cards; never available outside this intercepted test.
    resources.items.push({ kind: 'ai_asset', resource: { id: 'TEST_ONLY_MODEL_' + 'long-id-'.repeat(12), name: 'TEST_ONLY 模型引用', asset_type: 'model', version: null, provider: 'TEST_ONLY', evidence_ids: [], authorization_status: 'pending' } });
    resources.total = resources.items.length; return json(resources);
  }
  const recorded = exact(key); if (recorded) return json(recorded);
  if (url.pathname === prefix + '/report' && ['json', 'html', 'csv', 'resource_inventory'].includes(url.searchParams.get('format'))) return fail(409, 'report_not_ready', 'not_generated');
  unexpected.push(key); return fail(404, 'test_fixture_not_provided', key);
});
await fs.mkdir(output, { recursive: true });
const routeFor = pageName => `${origin}/app/scans/${scan}/${pageName}?mode=api&assessment_id=${asm}${pageName === 'report-v2' ? '&snapshot_id=' + snapshot : ''}`;
async function shot(name, fullPage = false) { await page.screenshot({ path: path.join(output, name + '.png'), fullPage }); }
async function noOverflow() {
  const sizes = await page.evaluate(() => ({ viewport: innerWidth, content: document.documentElement.scrollWidth }));
  if (sizes.content > sizes.viewport + 1) console.error(JSON.stringify(await page.evaluate(() => Array.from(document.querySelectorAll('body *')).map(el => ({ tag: el.tagName, cls: el.className?.baseVal ?? el.className, right: Math.round(el.getBoundingClientRect().right), width: Math.round(el.getBoundingClientRect().width) })).filter(el => el.right > innerWidth + 1).slice(0, 20))));
  assert.ok(sizes.content <= sizes.viewport + 1, JSON.stringify(sizes));
}
async function load(name) {
  await page.goto(name === 'history' ? origin + '/app/history?limit=20' : routeFor(name));
  await page.locator(({ assessment: '.og-p2-main', history: '.og-history-row', resources: '.og-ai-resource-card', graph: '.og-graph-node', remediation: '.og-task-card', 'report-v2': '.og-v2-boundary iframe' })[name]).first().waitFor();
}
try {
  if (process.env.OPENGUARD_UI_BASELINE) {
    servedDist = path.resolve(process.env.OPENGUARD_UI_BASELINE);
    for (const name of ['assessment', 'history', 'resources', 'graph', 'remediation', 'report-v2']) { await load(name); await shot('before-' + name); }
    servedDist = path.resolve(here, '../dist');
  }
  await load('assessment');
  assert.equal(await page.locator('#assessment-formal').evaluate(el => !!(el.compareDocumentPosition(document.querySelector('#assessment-p2')) & Node.DOCUMENT_POSITION_FOLLOWING)), true);
  await page.getByRole('link', { name: '用途建议与材料', exact: true }).click();
  assert.equal(new URL(page.url()).hash, '#assessment-p2');
  await page.waitForFunction(() => { const y = document.querySelector('#assessment-p2').getBoundingClientRect().top; return y >= 72 && y < innerHeight / 2; });
  assert.ok(await page.locator('.og-p2-test-only').isVisible());
  await page.getByRole('link', { name: '正式评估', exact: true }).click(); await shot('assessment');
  await page.locator('#assessment-p2').evaluate(el => el.scrollIntoView({ block: 'start' })); await shot('p2');
  checks.push('Formal before independent P2; native section links; explicit TEST_ONLY boundary');
  for (const name of ['history', 'resources', 'graph', 'remediation', 'report-v2']) { await load(name); await noOverflow(); await shot(name); }
  await load('resources'); await page.getByText('Profile 身份与追溯', { exact: true }).click();
  assert.ok(await page.getByText('Profile 身份键', { exact: true }).isVisible());
  checks.push('Resource long ID, pending authorization and unavailable Profile remain identifiable');
  for (const count of [100, 300, 500]) {
    graphCount = count; const start = performance.now(); await load('graph');
    assert.equal(await page.locator('.og-graph-node').count(), count);
    timings.push({ fixture_nodes: count, render_ms: Math.round(performance.now() - start) });
    await page.locator('.og-graph-node').first().focus(); await page.keyboard.press('Enter');
    await page.getByRole('button', { name: '关闭节点详情', exact: true }).waitFor();
    assert.equal(await page.locator('.og-graph-edges line').count(), graphs[count].edges.length);
  }
  await shot('graph-500'); checks.push('Graph 100/300/500 nodes, exact fixture edges, keyboard detail');
  await load('remediation');
  await page.locator('.og-task-status-nav').evaluate(el => el.scrollIntoView({ block: 'start' })); await shot('task-states');
  await page.getByRole('navigation', { name: '按任务处理状态筛选' }).getByRole('button', { name: /已完成任务/ }).click();
  assert.equal(new URL(page.url()).searchParams.get('task_status'), 'done');
  assert.equal(await page.locator('.og-task-card').count(), 1);
  await page.reload(); await page.locator('.og-task-card').waitFor(); assert.equal(await page.locator('.og-task-card').count(), 1);
  checks.push('Task status quick filter and URL reload; no PATCH or derivation');
  await load('report-v2');
  assert.equal(await page.locator('.og-v2-tools').getAttribute('open'), null);
  await page.getByRole('link', { name: '阅读报告正文' }).click();
  await page.waitForFunction(() => { const y = document.querySelector('#v2-body').getBoundingClientRect().top; return y >= 72 && y < innerHeight / 2; });
  assert.ok((await page.locator('.og-v2-toc > strong').boundingBox()).y >= 72, 'Sticky report directory must clear the header');
  assert.ok(await page.frameLocator('iframe').getByRole('heading', { name: 'TEST_ONLY · 报告阅读样板' }).isVisible());
  await shot('report-body');
  await page.emulateMedia({ media: 'print' });
  assert.equal(await page.locator('.og-v2-tools').isVisible(), false);
  assert.equal(await page.locator('iframe').isVisible(), true);
  await shot('report-print'); await page.emulateMedia({ media: 'screen' });
  checks.push('Fixed HTML visible unchanged; creation tools collapse; print body visible');
  for (const width of [1440, 1024, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const name of ['assessment', 'history', 'resources', 'graph', 'remediation', 'report-v2']) { await load(name); await noOverflow(); if (width === 390) await shot(name + '-mobile'); }
  }
  await page.getByRole('button', { name: '来源 Hash 说明' }).click();
  assert.ok(await page.getByRole('tooltip').isVisible()); await noOverflow();
  await page.keyboard.press('Escape');
  checks.push('Six result pages at desktop/tablet/mobile without horizontal page overflow');
  assert.deepEqual(errors, []); assert.deepEqual(unexpected, []);
  await fs.writeFile(path.join(output, 'receipt.json'), JSON.stringify({ grade: 'TEST_ONLY_NOT_LIVE_ACCEPTANCE', checks, timings, requests, errors, unexpected, mutations: 0, adapters: ['recorded P2 HTTP', 'existing History/Graph fixtures', 'four task states', 'AI card long ID and missing Profile', 'fixed HTML reading sample'] }, null, 2));
  console.log(JSON.stringify({ checks: checks.length, timings, errors, unexpected, mutations: 0, output }));
} catch (error) { await shot('failure', true).catch(() => {}); console.error(JSON.stringify({ errors, unexpected, lastRequests: requests.slice(-12) })); throw error; }
finally { await browser.close(); }
