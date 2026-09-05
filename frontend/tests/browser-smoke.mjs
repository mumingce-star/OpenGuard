// Real browser + real API acceptance. Start the existing backend and Vite first.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.OPENGUARD_PLAYWRIGHT || 'playwright');
const base = process.env.OPENGUARD_TEST_URL || 'http://127.0.0.1:5173';
const output = process.env.OPENGUARD_QA_OUTPUT || await fs.mkdtemp(path.join(os.tmpdir(), 'openguard-web-qa-'));
await fs.mkdir(output, { recursive: true });
execFileSync(process.env.OPENGUARD_PYTHON || 'python3', ['-c', `
import json,sys,zipfile
from pathlib import Path
p=Path(sys.argv[1])
with zipfile.ZipFile(p/'license-demo.zip','w') as z:
 z.writestr('package.json',json.dumps({'name':'web-demo','dependencies':{'demo-mit':'1.0.0','demo-unknown':'2.0.0'}}))
 z.writestr('package-lock.json',json.dumps({'lockfileVersion':3,'packages':{'node_modules/demo-mit':{'version':'1.0.0','license':'MIT'},'node_modules/demo-unknown':{'version':'2.0.0'}}}))
with zipfile.ZipFile(p/'partial-demo.zip','w') as z: z.writestr('requirements.txt','requests==2.32.3\\n')
(p/'invalid.zip').write_bytes(b'not a zip')
`, output]);
const browser = await chromium.launch({ channel: process.env.OPENGUARD_BROWSER || 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce', acceptDownloads: true });
const page = await context.newPage();
page.setDefaultTimeout(10000);
const errors = [], requests = [];
page.on('pageerror', error => errors.push(error.message));
page.on('request', request => {
  if (new URL(request.url()).pathname.startsWith('/api/')) requests.push({ method: request.method(), url: request.url() });
});
let checks = 0;
function passed(name) { console.log(`PASS ${++checks} ${name}`); }
async function visible(text) { await page.getByText(text, { exact: true }).first().waitFor(); }
async function api(suffix) { const response = await context.request.get(base + suffix); assert.equal(response.status(), 200); return response.json(); }
async function submit(file, expectedTitle) {
  await page.goto(base + '/app/new-scan');
  await page.locator('input[type=file]').setInputFiles(path.join(output, file));
  const created = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === '/api/v1/scans');
  await page.getByRole('button', { name: '提交真实扫描', exact: true }).click();
  const response = await created;
  assert.equal(response.status(), 202);
  const accepted = await response.json();
  assert.match(accepted.scan_id, /^scn_/);
  await page.getByRole('heading', { name: expectedTitle, exact: true }).waitFor({ timeout: 30000 });
  assert.ok(page.url().includes(accepted.scan_id));
  assert.ok(!page.url().includes('mode=mock'));
  return accepted.scan_id;
}
try {
  const id = await submit('license-demo.zip', '扫描已完成');
  const prefix = '/api/v1/scans/' + id;
  const state = await api(prefix);
  assert.equal(state.status, 'completed');
  assert.equal(state.summary.component_count, 2);
  assert.equal(state.summary.finding_counts.review_required, 2);
  passed('real ZIP upload and completed progress');
  await page.getByRole('button', { name: '查看扫描结果', exact: true }).click();
  await page.getByRole('heading', { name: /扫描概览/ }).waitFor();
  await page.getByRole('button', { name: '资源清单', exact: true }).click();
  await visible('demo-mit'); await visible('demo-unknown'); await page.locator('.og-resource-row').filter({hasText: 'demo-mit'}).getByText(/^MIT/).waitFor();
  assert.equal(await page.getByRole('button', { name: '证据图谱', exact: true }).count(), 0);
  passed('real resources and license display without graph');
  await page.getByRole('button', { name: /^风险中心/ }).click();
  const risks = (await api(prefix + '/risks')).items;
  assert.equal(risks.length, 2);
  await page.locator('.og-risk-preview').filter({ hasText: 'demo-mit' }).click();
  await page.getByRole('heading', { name: /License evidence requires verification/ }).waitFor();
  await visible('提示');
  assert.equal(await page.getByRole('button', { name: /标记.*处理/ }).count(), 0);
  const evidenceIds = risks.flatMap(r => r.evidence_ids);
  assert.ok(evidenceIds.length > 0);
  for (const evidenceId of evidenceIds) assert.equal((await api(prefix + '/evidence/' + evidenceId)).id, evidenceId);
  await page.screenshot({ path: path.join(output, 'risk-desktop.png'), fullPage: true });
  passed('real risk detail and referenced evidence');
  const postCount = requests.filter(r => r.method === 'POST').length;
  await page.reload();
  await page.getByRole('heading', { name: /License evidence requires verification/ }).waitFor();
  assert.equal(requests.filter(r => r.method === 'POST').length, postCount);
  assert.ok(page.url().includes(id));
  passed('deep-link refresh retains task without resubmitting');
  await page.getByRole('button', { name: '合规报告', exact: true }).click();
  const formats = [['json', '下载 JSON'], ['html', '下载 HTML'], ['csv', '下载 CSV'], ['resource_inventory', '下载资源清单']];
  for (const [format, label] of formats) {
    const event = page.waitForEvent('download');
    await page.getByRole('link', { name: label, exact: true }).click();
    const download = await event;
    assert.equal(await download.failure(), null);
    const bytes = await fs.readFile(await download.path());
    const metadata = await api(prefix + '/report?format=' + format);
    assert.equal(createHash('sha256').update(bytes).digest('hex'), metadata.content_hash.value);
    if (format === 'json') {
      const run = JSON.parse(bytes).scan_run;
      assert.equal(run.id, id);
      assert.equal(run.findings.length, 2);
      assert.ok(run.licenses.every(l => l.verification_status === 'pending'));
      await fs.writeFile(path.join(output, 'downloaded-report.json'), bytes);
    }
  }
  passed('four downloads match actual backend report SHA256');
  await page.screenshot({ path: path.join(output, 'report-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForFunction(() => document.documentElement.scrollWidth <= innerWidth + 1);
  await page.screenshot({ path: path.join(output, 'report-mobile.png'), fullPage: true });
  await page.getByRole('button', { name: '打开导航', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '资源清单', exact: true }).click();
  await visible('demo-mit');
  passed('mobile navigation and no horizontal page overflow');
  await page.setViewportSize({ width: 1440, height: 900 });
  const partialId = await submit('partial-demo.zip', '扫描部分完成');
  assert.equal((await api('/api/v1/scans/' + partialId)).status, 'partial');
  await page.getByRole('button', { name: '查看已有结果与错误', exact: true }).click();
  passed('partial scan displays partial result rather than fake success');
  const invalidId = await submit('invalid.zip', '扫描失败');
  const failed = await api('/api/v1/scans/' + invalidId);
  assert.equal(failed.status, 'failed');
  assert.ok(failed.errors.length > 0);
  await page.getByText(/zip_ingestion_failed/).first().waitFor();
  passed('invalid ZIP asynchronous failure is shown without fake resources');
  await page.goto(base + '/app/scans/scn_00000000-0000-0000-0000-000000000000/overview?mode=api');
  await page.getByText(/404/).first().waitFor();
  assert.equal(await page.getByText('demo-mit', { exact: true }).count(), 0);
  passed('unknown task does not fall back to demo');
  assert.ok(requests.every(r => r.method !== 'PATCH' && !r.url.includes('/repositories/')));
  assert.deepEqual(errors, []);
  passed('no unsupported endpoints or browser runtime errors');
  console.log(JSON.stringify({ checks, scanId: id, partialId, output }));
} catch (error) { await page.screenshot({path: path.join(output, 'failure.png'), fullPage: true}); throw error; } finally { await browser.close(); }
