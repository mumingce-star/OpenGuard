// Read-only P0 positive acceptance against a predeclared fixed sample.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { p0ReportDownloadPath, readP0Scenario } from './p0-report-contract.mjs';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.OPENGUARD_PLAYWRIGHT || 'playwright');
const base = (process.env.OPENGUARD_TEST_URL || 'http://127.0.0.1:4179').replace(/\/$/, '');
const output = process.env.OPENGUARD_QA_OUTPUT || await fs.mkdtemp(path.join(os.tmpdir(), 'openguard-p0-report-'));
const scenario = readP0Scenario(process.env, { requireHashes: true });
assert.equal(scenario.kind, 'available', 'the positive P0 report smoke only accepts an explicit available scenario');
await fs.mkdir(output, { recursive: true });

const browser = await chromium.launch({ channel: process.env.OPENGUARD_BROWSER || 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
const page = await context.newPage();
page.setDefaultTimeout(15_000);
const pageErrors = [];
const consoleErrors = [];
const apiRequests = [];
const responseFailures = [];

page.on('pageerror', error => pageErrors.push(error.message));
page.on('console', message => {
  if (message.type() === 'error') consoleErrors.push({ text: message.text(), location: message.location() });
});
page.on('request', request => {
  const url = new URL(request.url());
  if (url.pathname.startsWith('/api/')) apiRequests.push({ method: request.method(), path: url.pathname + url.search });
});
page.on('response', response => {
  if (response.status() < 400) return;
  const url = new URL(response.url());
  responseFailures.push({ method: response.request().method(), status: response.status(), path: url.pathname + url.search });
});

function sha256(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

async function get(relative) {
  const response = await context.request.get(base + relative);
  assert.equal(response.status(), 200, `${relative} returned HTTP ${response.status()}`);
  return response;
}

try {
  const statusPath = `/api/v1/scans/${encodeURIComponent(scenario.scanId)}`;
  const statusBefore = await (await get(statusPath)).json();
  const jsonPath = p0ReportDownloadPath(scenario.scanId, 'json');
  const htmlPath = p0ReportDownloadPath(scenario.scanId, 'html');
  const jsonBytes = await (await get(jsonPath)).body();
  const htmlBytes = await (await get(htmlPath)).body();
  const jsonHash = sha256(jsonBytes);
  const htmlHash = sha256(htmlBytes);
  assert.equal(jsonHash, scenario.jsonSha256, 'P0 JSON download hash does not match the fixed-sample manifest');
  assert.equal(htmlHash, scenario.htmlSha256, 'P0 HTML download hash does not match the fixed-sample manifest');

  await page.goto(`${base}/app/scans/${encodeURIComponent(scenario.scanId)}/report?mode=api`, { waitUntil: 'networkidle' });
  await page.getByRole('heading', { name: /项目评估摘要|合规报告/ }).first().waitFor();
  await page.getByText('查看历史扫描报告、四种原始附件与全部明细', { exact: true }).click();
  await page.getByRole('link', { name: '下载 HTML' }).waitFor();
  await page.getByRole('link', { name: '下载 JSON' }).waitFor();
  assert.ok((await page.locator('.og-report').innerText()).includes('合规信息与风险提示报告'));

  await page.emulateMedia({ media: 'print', reducedMotion: 'reduce' });
  assert.equal(await page.locator('.og-sidebar').evaluate(element => getComputedStyle(element).display), 'none');
  assert.equal(await page.locator('.og-topbar').evaluate(element => getComputedStyle(element).display), 'none');
  assert.notEqual(await page.locator('.og-report').evaluate(element => getComputedStyle(element).display), 'none');
  const screenshot = path.join(output, 'p0-available-print.png');
  await page.screenshot({ path: screenshot, fullPage: true });
  await page.emulateMedia({ media: 'screen', reducedMotion: 'reduce' });

  const statusAfter = await (await get(statusPath)).json();
  assert.deepEqual(statusAfter, statusBefore, 'read-only P0 report acceptance changed the scan status');
  assert.ok(apiRequests.length > 0);
  assert.ok(apiRequests.every(request => request.method === 'GET'), JSON.stringify(apiRequests.filter(request => request.method !== 'GET')));
  assert.deepEqual(responseFailures, []);
  assert.deepEqual(pageErrors, []);
  const unexpectedConsoleErrors = consoleErrors.filter(({ text, location }) => {
    if (!text.startsWith('Failed to load resource: the server responded with a status of 404')) return true;
    try { return new URL(location.url).pathname !== '/favicon.ico'; } catch { return true; }
  });
  assert.deepEqual(unexpectedConsoleErrors, []);

  const receipt = {
    schema_version: 'openguard-p0-report-browser-smoke/1',
    result: 'P0_AVAILABLE_PASS',
    base,
    scan_id: scenario.scanId,
    downloads: {
      json: { path: jsonPath, sha256: jsonHash, bytes: jsonBytes.length },
      html: { path: htmlPath, sha256: htmlHash, bytes: htmlBytes.length },
    },
    api_requests: apiRequests,
    screenshot,
    page_errors: pageErrors,
    console_errors: consoleErrors,
  };
  await fs.writeFile(path.join(output, 'receipt.json'), JSON.stringify(receipt, null, 2));
  console.log(JSON.stringify({ result: receipt.result, output, scan_id: scenario.scanId, jsonHash, htmlHash }));
} catch (error) {
  const failure = path.join(output, 'failure.png');
  await page.screenshot({ path: failure, fullPage: true }).catch(() => {});
  console.error(JSON.stringify({ output, failure }));
  throw error;
} finally {
  await browser.close();
}
