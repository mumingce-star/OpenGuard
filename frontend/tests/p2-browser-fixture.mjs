// Isolated TEST_ONLY browser regression. Every API call is intercepted; never live acceptance.
// Input is the already-delivered http-events.json, not a new seed or an application mock mode.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.OPENGUARD_PLAYWRIGHT || 'playwright');
const eventsPath = process.env.P2_HTTP_EVENTS;
const output = process.env.OPENGUARD_QA_OUTPUT;
assert.ok(eventsPath && output, 'P2_HTTP_EVENTS and fresh OPENGUARD_QA_OUTPUT are required');
const base = process.env.OPENGUARD_TEST_URL || 'http://127.0.0.1:4182';
assert.ok(['127.0.0.1', 'localhost'].includes(new URL(base).hostname), 'local preview only');
await fs.mkdir(output, { recursive: true });
const events = JSON.parse(await fs.readFile(eventsPath, 'utf8'));
const answerEvent = events.find(e => e.method === 'POST' && e.path.endsWith('/p2/answers') && e.status === 201);
assert.ok(answerEvent);
const p2 = answerEvent.path.replace(/\/answers$/, '');
const materialEvent = events.find(e => e.method === 'POST' && e.path === p2 + '/materials' && e.status === 201);
assert.ok(materialEvent);
assert.ok(process.env.P2_MATERIAL_FILE, 'P2_MATERIAL_FILE must point to the original packaged LICENSE bytes');
const materialBytes = await fs.readFile(process.env.P2_MATERIAL_FILE);
assert.equal(createHash('sha256').update(materialBytes).digest('hex'), materialEvent.request.source_sha256);
const binding = answerEvent.request.binding;
const scan = binding.scan_id, asm = binding.assessment_id, av = binding.assessment_version;
const prefix = `/api/v1/scans/${scan}`;
const exact = key => events.filter(e => e.method === 'GET' && e.path === key && e.status === 200).at(-1)?.response;
const first = exact(`${p2}/results/${answerEvent.request.parent_result_id}?assessment_version=${av}`);
const second = answerEvent.response.result, third = materialEvent.response.result;
assert.ok(first && first.data_scope === 'TEST_ONLY' && second.revision === first.revision + 1 && third.revision === second.revision + 1);
const assessment = exact(`${prefix}/assessments/${asm}`);
assert.ok(assessment);
const frozenFormal = JSON.stringify(assessment);
const snapshots = [first, second, third];
const requests = [], errors = [], unexpected = [], checks = [];
let head = first, answerPosts = 0, materialPosts = 0, failBinding = false, failPrevious = false;
const answerBodies = [];
const browser = await chromium.launch({ channel: process.env.OPENGUARD_BROWSER || 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce', serviceWorkers: 'block' });
const page = await context.newPage();
page.setDefaultTimeout(12000);
page.on('pageerror', error => errors.push(error.message));
// No requests to a real backend, external host, or unhandled API endpoint can escape this harness.
await context.route('**/*', async route => {
  const req = route.request(), url = new URL(req.url()), key = url.pathname + url.search;
  if (url.origin !== new URL(base).origin) { unexpected.push(req.method() + ' ' + url.origin); return route.abort(); }
  if (!url.pathname.startsWith('/api/')) return route.continue();
  requests.push({ method: req.method(), path: key });
  const reply = (data, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
  const failure = (status, code, reason) => reply({ error: { code, message: code, details: { reason } } }, status);
  if (req.method() === 'POST') {
    const body = req.postDataJSON();
    if (key === p2 + '/answers') {
      answerPosts++; answerBodies.push(req.postData());
      assert.equal(body.expected_revision, first.revision); assert.equal(body.parent_result_id, first.result_id);
      assert.equal(body.answer_code, answerEvent.request.answer_code);
      assert.deepEqual(body.subjects, answerEvent.request.subjects);
      if (answerPosts === 1) return route.abort('connectionfailed');
      assert.equal(answerBodies[0], answerBodies[1], 'unknown replay must preserve exact key/body');
      head = second;
      // Explicit test adapter: UI deliberately submits no optional answer Evidence.
      return reply({ ...answerEvent.response, answer: { ...answerEvent.response.answer, evidence_ids: body.evidence_ids } }, 201);
    }
    if (key === p2 + '/materials') {
      materialPosts++;
      assert.equal(body.parent_result_id, second.result_id); assert.equal(body.expected_revision, second.revision);
      if (materialPosts === 1) return failure(409, 'p2_revision_conflict', 'test_only_declared_conflict');
      assert.equal(body.source_sha256, materialEvent.request.source_sha256);
      assert.deepEqual(body.evidence_ids, materialEvent.request.evidence_ids);
      head = third; return reply(materialEvent.response, 201);
    }
    unexpected.push('POST ' + key); return failure(405, 'unexpected_fixture_write', key);
  }
  if (req.method() !== 'GET') { unexpected.push(req.method() + ' ' + key); return route.abort(); }
  if (key === p2 + '/binding') return failBinding ? failure(503, 'p2_service_disabled', 'test_only') : reply(binding);
  if (key.startsWith(p2 + '/results?')) return reply({ head_result_id: head.result_id, head_revision: head.revision,
    result_ids: snapshots.filter(r => r.revision <= head.revision).map(r => r.result_id).reverse(), has_more: false });
  if (failPrevious && key === `${p2}/results/${second.result_id}?assessment_version=${av}`) return failure(503, 'p2_service_disabled', 'test_only_previous');
  const snapshot = snapshots.find(r => key === `${p2}/results/${r.result_id}?assessment_version=${av}`);
  if (snapshot) return reply(snapshot);
  const summaryResult = snapshots.find(r => key === `${p2}/results/${r.result_id}/summary?assessment_version=${av}`);
  if (summaryResult) return reply({ summary_id: summaryResult.companion_summary_id, result_id: summaryResult.result_id,
    result_revision: summaryResult.revision, result_sha256: summaryResult.result_sha256, binding, material_ids: summaryResult.material_ids,
    answer_ids: summaryResult.answer_ids, state: summaryResult.state, resource_states: Object.fromEntries(summaryResult.resources.map(r => [r.subject.resource_id, r.state])),
    formal_effect: 'none', report_kind: 'P2_COMPANION_NOT_FORMAL_REPORT' });
  const original = exact(key);
  if (original) return reply(original);
  if (key === prefix + '/risks') return reply({ items: [], total: 0 });
  if (key === prefix + '/assessments') return reply({ items: [assessment], usage: assessment.usage, pending_job: null, offset: 0, has_more: false });
  if (key === prefix + '/chat') return reply({ items: [], generation: 0, limits: { max_message_chars: 2000, max_turns: 20 } });
  // This fixture has no P0 report. Only this exact, declared GET gets this error.
  if (['html', 'json', 'csv', 'resource_inventory'].some(format => key === prefix + '/report?format=' + format)) return failure(409, 'report_not_ready', 'not_generated');
  unexpected.push('GET ' + key); return failure(404, 'fixture_not_provided', key);
});
const url = `${base}/app/scans/${scan}/assessment?mode=api&assessment_id=${asm}`;
async function ready(revision) {
  await page.waitForURL(url => url.searchParams.get('p2_revision') === String(revision));
  await page.getByRole('heading', { name: 'P2 同版摘要 · 非正式报告' }).waitFor();
}
async function fillMaterial() {
  const input = materialEvent.request;
  await page.getByRole('combobox', { name: /^精确资源/ }).selectOption(input.subject.resource_id);
  for (const id of input.evidence_ids) await page.getByLabel('原扫描Evidence：' + id, { exact: true }).check();
  await page.getByLabel('材料文件').setInputFiles({ name: input.filename, mimeType: 'text/plain', buffer: materialBytes });
  await page.getByLabel('来源说明').fill(input.source_description);
  await page.getByLabel('完整性声明').selectOption(input.completeness);
}
try {
  await page.goto(url); await ready(first.revision);
  await page.getByLabel('L1资源级用途建议').waitFor();
  assert.ok(requests.every(r => r.method === 'GET'));
  checks.push('L1_FIXED_GET_ONLY');
  failBinding = true; await page.reload();
  await page.getByRole('alert').filter({ hasText: 'P2 读取服务不可用' }).waitFor();
  assert.equal(await page.locator('.og-p2-result').count(), 0);
  failBinding = false; await page.getByRole('button', { name: '重新读取固定结果' }).click(); await ready(first.revision);
  checks.push('DECLARED_503_MANUAL_RETRY');
  const enable = page.getByLabel('我确认在获准数据环境中显式提交P2结果（服务端仍可拒绝写入）');
  await enable.focus(); await page.keyboard.press('Space'); assert.equal(await enable.isChecked(), true);
  await page.getByLabel('服务端问题').selectOption(answerEvent.request.question_id);
  await page.getByRole('combobox', { name: /^回答/ }).selectOption(answerEvent.request.answer_code);
  for (const s of answerEvent.request.subjects) await page.getByLabel(`${s.resource_id} @ ${s.version}`, { exact: true }).check();
  await page.getByRole('button', { name: '确认提交所选资源的声明' }).click();
  await page.getByRole('status').filter({ hasText: '保存结果待确认' }).waitFor();
  assert.equal(answerPosts, 1); assert.equal(new URL(page.url()).searchParams.get('p2_revision'), String(first.revision));
  assert.equal(await page.getByRole('button', { name: '手动重放原键与原内容' }).isDisabled(), true);
  await page.getByRole('button', { name: '只读核对服务器状态' }).click();
  await page.getByRole('button', { name: '手动重放原键与原内容' }).click(); await ready(second.revision);
  assert.equal(answerPosts, 2); checks.push('UNKNOWN_THEN_READ_AND_EXACT_REPLAY', 'ANSWER_NEW_RESULT_READBACK');
  await fillMaterial(); await page.getByRole('button', { name: '确认提交未核验材料' }).click();
  await page.getByRole('status').filter({ hasText: '冲突' }).waitFor();
  assert.equal(materialPosts, 1);
  await page.getByRole('button', { name: '只读核对服务器状态' }).click();
  await page.getByRole('button', { name: '确认读取结果并返回修改输入' }).click(); await ready(second.revision);
  assert.equal(materialPosts, 1); checks.push('DECLARED_CAS_NO_AUTO_WRITE');
  await fillMaterial(); await page.getByRole('button', { name: '确认提交未核验材料' }).click(); await ready(third.revision);
  checks.push('MATERIAL_RESULT_READBACK');
  failPrevious = true;
  await page.getByRole('button', { name: '读取指定前版并排核对' }).click();
  await page.getByRole('alert').filter({ hasText: '不会选用其他版本' }).waitFor();
  assert.equal(await page.getByLabel('前版快照', { exact: true }).count(), 0);
  failPrevious = false;
  await page.getByRole('button', { name: '重试读取指定前版' }).click();
  await page.getByRole('heading', { name: `前版快照 · Result 第${second.revision}版` }).waitFor();
  await page.getByLabel('新旧P2结果核对').screenshot({ path: path.join(output, 'test-only-version-pair.png') });
  const widths = await page.evaluate(() => ({ viewport: innerWidth, content: document.documentElement.scrollWidth }));
  assert.ok(widths.content <= widths.viewport + 1, JSON.stringify(widths));
  await page.emulateMedia({ media: 'print', reducedMotion: 'reduce' });
  assert.equal(await page.locator('.og-p2-panel form').first().evaluate(el => getComputedStyle(el).display), 'none');
  assert.equal(await page.getByLabel('本版快照', { exact: true }).isVisible(), true);
  assert.equal(await page.locator('.og-p2-panel').evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(255, 255, 255)');
  assert.equal(await page.getByRole('heading', { name: '新旧结果核对', includeHidden: true }).evaluate(el => getComputedStyle(el).color), 'rgb(0, 0, 0)');
  await page.getByLabel('新旧P2结果核对').screenshot({ path: path.join(output, 'test-only-version-print.png') });
  await page.emulateMedia({ media: 'screen', reducedMotion: 'reduce' });
  checks.push('PREVIOUS_ERROR_RETRY', '390PX_KEYBOARD_REDUCED_MOTION', 'PRINT_SNAPSHOT_CONTENT_VISIBLE');
  await page.getByText('独立结果历史（Assessment版本不随之改变）').click();
  await page.getByRole('button', { name: first.result_id, exact: true }).click(); await ready(first.revision);
  await page.reload(); await ready(first.revision);
  await page.getByText('正在查看旧版；只读。', { exact: false }).waitFor();
  assert.equal(await page.getByRole('button', { name: '确认提交所选资源的声明' }).isDisabled(), true);
  assert.equal(JSON.stringify(assessment), frozenFormal);
  checks.push('OLD_URL_REFRESH_READ_ONLY', 'FIXTURE_FORMAL_UNCHANGED');
  assert.deepEqual(unexpected, []); assert.deepEqual(errors, []);
  assert.equal(requests.filter(r => r.method === 'POST').length, 4);
  const receipt = { grade: 'TEST_ONLY_BROWSER_FIXTURE_NOT_LIVE_ACCEPTANCE', checks, widths, requests, errors,
    adapters: ['result index', 'companion summaries', 'answer optional evidence echo', 'declared transport failure and CAS', 'auxiliary scan views'],
    source: 'locally supplied recorded http-events.json', outbound_backend_requests: 0 };
  await fs.writeFile(path.join(output, 'receipt.json'), JSON.stringify(receipt, null, 2), { flag: 'wx' });
  console.log(JSON.stringify({ grade: receipt.grade, checks: checks.length, intercepted_requests: requests.length, simulated_posts: 4, output }));
} catch (error) {
  await page.screenshot({ path: path.join(output, 'failure.png'), fullPage: true }).catch(() => {});
  console.error(JSON.stringify({ errors, unexpected, requests, output })); throw error;
} finally { await browser.close(); }
