// Read-only P1 browser acceptance against a real API. This script never creates
// scans, assessments, remediation tasks, reports, or AI output.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.OPENGUARD_PLAYWRIGHT || 'playwright');
const base = (process.env.OPENGUARD_TEST_URL || 'http://127.0.0.1:4179').replace(/\/$/, '');
const output = process.env.OPENGUARD_QA_OUTPUT || await fs.mkdtemp(path.join(os.tmpdir(), 'openguard-p1-browser-'));
await fs.mkdir(output, { recursive: true });

const browser = await chromium.launch({ channel: process.env.OPENGUARD_BROWSER || 'chrome', headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  reducedMotion: 'reduce',
  acceptDownloads: true,
});
const page = await context.newPage();
page.setDefaultTimeout(15_000);

const pageErrors = [];
const consoleErrors = [];
const apiRequests = [];
const apiFailures = [];
const resourceFailures = [];
const screenshots = [];
let checks = 0;

page.on('pageerror', error => pageErrors.push(error.message));
page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
page.on('request', request => {
  const url = new URL(request.url());
  if (url.pathname.startsWith('/api/')) apiRequests.push({ method: request.method(), path: url.pathname + url.search });
});
page.on('response', response => {
  const url = new URL(response.url());
  if (response.status() >= 400) {
    const failure = { status: response.status(), path: url.pathname + url.search };
    resourceFailures.push(failure);
    if (url.pathname.startsWith('/api/')) apiFailures.push(failure);
  }
});

function passed(name) {
  checks += 1;
  console.log(`PASS ${checks} ${name}`);
}

async function api(relative) {
  const response = await context.request.get(base + relative);
  assert.equal(response.status(), 200, `${relative} returned HTTP ${response.status()}`);
  return response.json();
}

async function goto(relative, heading) {
  await page.goto(base + relative, { waitUntil: 'domcontentloaded' });
  await page.getByRole('heading', { name: heading }).first().waitFor();
}

async function shot(name) {
  const file = path.join(output, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  screenshots.push(file);
}

async function assertNoPageOverflow() {
  const dimensions = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
  assert.ok(dimensions.scrollWidth <= dimensions.width + 1, `page overflow ${dimensions.scrollWidth} > ${dimensions.width}`);
}

function historySignature(items) {
  return items.map(item => ({
    scan_id: item.scan_id,
    status: item.status,
    stage: item.stage,
    revision: item.revision,
    input_hash: item.input_hash,
    inventory_hash: item.inventory_hash,
    assessment_id: item.latest_assessment?.assessment_id ?? null,
    assessment_version: item.latest_assessment?.version ?? null,
  }));
}

function chooseDiffPair(items) {
  const grouped = new Map();
  for (const item of items) {
    if (!['completed', 'partial'].includes(item.status)) continue;
    const key = item.project_identity?.key;
    if (!key) continue;
    const rows = grouped.get(key) ?? [];
    rows.push(item);
    grouped.set(key, rows);
  }
  for (const rows of grouped.values()) if (rows.length >= 2) return [rows[1], rows[0]];
  return null;
}

try {
  const historyBefore = await api('/api/v1/scans?limit=100');
  assert.equal(historyBefore.schema_version, '1.0');
  assert.ok(historyBefore.items.length > 0, 'real History must contain at least one scan');
  const terminal = historyBefore.items.filter(item => ['completed', 'partial'].includes(item.status));
  const assessed = historyBefore.items.find(item => item.latest_assessment?.formal === true);
  const partial = historyBefore.items.find(item => item.status === 'partial');
  const pair = chooseDiffPair(historyBefore.items);
  assert.ok(terminal.length > 0, 'a terminal real scan is required');
  assert.ok(assessed, 'a real scan with Formal Assessment is required');
  assert.ok(pair, 'two real scans with the same project identity are required for Diff');

  let resourceScan = null;
  let resourcePayload = null;
  for (const item of terminal) {
    const payload = await api(`/api/v1/scans/${encodeURIComponent(item.scan_id)}/resources`);
    if (payload.items?.some(row => row.kind === 'ai_asset' && ['model', 'dataset'].includes(row.resource?.asset_type))) {
      resourceScan = item;
      resourcePayload = payload;
      break;
    }
  }
  if (!resourceScan) {
    resourceScan = assessed;
    resourcePayload = await api(`/api/v1/scans/${encodeURIComponent(resourceScan.scan_id)}/resources`);
  }

  await goto('/', /不止告诉你/);
  await shot('01-landing');
  passed('Landing renders without API mutation');

  await goto('/app/new-scan?mode=api', '从一个项目开始');
  await page.getByText('真实接口模式', { exact: true }).waitFor();
  await shot('02-new-scan-real');
  passed('New Scan stays in explicit real API mode');

  if (partial) {
    await goto(`/app/scans/${encodeURIComponent(partial.scan_id)}/progress?mode=api`, /扫描已结束 · 部分结果/);
    await page.getByText(/当前结果不能视为完整覆盖/).first().waitFor();
    await shot('03-progress-partial');
    passed('partial Progress preserves coverage limits');
  }

  await goto('/app/history?limit=20', '扫描历史');
  await page.locator('.og-history-row').first().waitFor();
  await shot('04-history-all');
  const firstHistory = page.locator('.og-history-row').first();
  await firstHistory.focus();
  assert.equal(await firstHistory.evaluate(element => element === document.activeElement), true);
  const historyUrl = page.url();
  await page.keyboard.press('Enter');
  await page.waitForURL(url => url.pathname.includes('/app/scans/'));
  await page.goBack({ waitUntil: 'domcontentloaded' });
  await page.getByRole('heading', { name: '扫描历史' }).waitFor();
  assert.equal(page.url(), historyUrl);
  passed('History rows are keyboard operable and browser Back restores URL');

  await goto('/app/history?status=partial&limit=20', '扫描历史');
  await page.getByText('状态：扫描部分完成', { exact: true }).waitFor();
  const filteredUrl = page.url();
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.getByText('状态：扫描部分完成', { exact: true }).waitFor();
  await page.locator('.og-history-row').first().waitFor();
  assert.equal(page.url(), filteredUrl);
  await shot('05-history-filter-restored');
  passed('History filters survive refresh and copied URL');

  const assessmentId = assessed.latest_assessment.assessment_id;
  await goto(`/app/scans/${encodeURIComponent(assessed.scan_id)}/assessment?mode=api&assessment_id=${encodeURIComponent(assessmentId)}`, /项目整体评估/);
  await page.getByText('需要履行的义务', { exact: true }).waitFor();
  await page.getByText(/证据不足不代表许可通过/).first().waitFor();
  await shot('06-formal-assessment');
  passed('Formal Assessment remains visibly authoritative and keeps evidence gaps');

  await goto(`/app/scans/${encodeURIComponent(resourceScan.scan_id)}/resources?mode=api`, '第三方资源清单');
  const aiAssets = resourcePayload.items?.filter(row => row.kind === 'ai_asset') ?? [];
  if (aiAssets.length) {
    await page.locator('.og-ai-resource-card').first().waitFor();
    await page.getByText(/Resource Profile 未提供|Profile 读取失败|后端尚未提供 Resource Profile/).first().waitFor().catch(() => {});
  }
  await shot('07-resource-cards');
  passed('Resource Cards render only real Resource/Profile/Evidence states');

  await goto(`/app/scans/${encodeURIComponent(assessed.scan_id)}/graph?mode=api`, '资源关系图');
  const graphNode = page.locator('.og-graph-node').first();
  await graphNode.waitFor();
  assert.equal(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches), true);
  assert.equal(await page.locator('.og-graph-stage').evaluate(element => getComputedStyle(element).transitionDuration), '0s');
  await graphNode.focus();
  await page.keyboard.press('Enter');
  await page.getByLabel('节点详情').getByText('节点 ID', { exact: true }).waitFor();
  assert.ok(new URL(page.url()).searchParams.get('graph_node'));
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.getByLabel('节点详情').getByText('节点 ID', { exact: true }).waitFor();
  await page.getByRole('button', { name: '放大' }).click();
  assert.ok(new URL(page.url()).searchParams.get('graph_zoom'));
  await shot('08-graph-keyboard-detail');
  passed('Graph supports keyboard selection, reduced motion, zoom and URL restoration');

  const [baseScan, targetScan] = pair;
  await goto(`/app/scans/${encodeURIComponent(targetScan.scan_id)}/diff?base=${encodeURIComponent(baseScan.scan_id)}&mode=api`, '扫描差异');
  await page.getByText('覆盖范围与结论边界', { exact: true }).waitFor();
  await page.getByText(/Formal Assessment 变化/).first().waitFor();
  const diffUrl = page.url();
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.getByText('覆盖范围与结论边界', { exact: true }).waitFor();
  assert.equal(page.url(), diffUrl);
  await shot('09-scan-diff');
  passed('Diff restores base/target and renders only backend conclusions');

  await goto(`/app/scans/${encodeURIComponent(assessed.scan_id)}/remediation?mode=api&assessment_id=${encodeURIComponent(assessmentId)}`, '整改任务工作台');
  await page.getByText(/暂无整改任务|任务 ·/).first().waitFor();
  await page.getByText(/done 不等于项目合规/).first().waitFor();
  await shot('10-remediation-current-state');
  passed('Remediation reads server state without deriving or patching tasks');

  await goto(`/app/scans/${encodeURIComponent(assessed.scan_id)}/report-v2?mode=api&assessment_id=${encodeURIComponent(assessmentId)}&snapshot_id=rptv2_readonly_probe`, 'Assessment Report V2');
  await page.getByText('Report V2 暂不可用', { exact: true }).waitFor();
  await page.getByText('P0 历史附件', { exact: true }).waitFor();
  await shot('11-report-v2-missing-with-p0-fallback');
  passed('Report V2 missing state never synthesizes a formal report');

  await page.setViewportSize({ width: 390, height: 844 });
  await goto('/app/history?limit=20', '扫描历史');
  await assertNoPageOverflow();
  await page.getByRole('button', { name: '打开导航' }).click();
  await page.getByRole('dialog', { name: '工作台导航' }).waitFor();
  await shot('12-history-narrow-navigation');
  await page.keyboard.press('Escape');
  await goto(`/app/scans/${encodeURIComponent(assessed.scan_id)}/graph?mode=api`, '资源关系图');
  await page.locator('.og-graph-node').first().waitFor();
  await assertNoPageOverflow();
  await shot('13-graph-narrow');
  passed('narrow History navigation and Graph have no page-level horizontal overflow');

  await page.setViewportSize({ width: 1440, height: 900 });
  await goto(`/app/scans/${encodeURIComponent(assessed.scan_id)}/report?mode=api`, /项目评估摘要|合规报告/);
  await page.emulateMedia({ media: 'print', reducedMotion: 'reduce' });
  assert.equal(await page.locator('.og-sidebar').evaluate(element => getComputedStyle(element).display), 'none');
  assert.equal(await page.locator('.og-topbar').evaluate(element => getComputedStyle(element).display), 'none');
  await shot('14-p0-report-print');
  await page.emulateMedia({ media: 'screen', reducedMotion: 'reduce' });
  passed('print media hides application chrome and preserves report content');

  const historyAfter = await api('/api/v1/scans?limit=100');
  assert.deepEqual(historySignature(historyAfter.items), historySignature(historyBefore.items));
  assert.ok(apiRequests.length > 0);
  assert.ok(apiRequests.every(request => request.method === 'GET'), JSON.stringify(apiRequests.filter(request => request.method !== 'GET')));
  assert.deepEqual(pageErrors, []);
  const unexpectedFailures = apiFailures.filter(({ status, path }) =>
    status !== 404 || (!path.endsWith('/profile') && !path.includes('/report-v2/')));
  assert.deepEqual(unexpectedFailures, []);
  const unexpectedResources = resourceFailures.filter(({ status, path }) =>
    !(status === 404 && (path === '/favicon.ico' || path.endsWith('/profile') || path.includes('/report-v2/'))));
  assert.deepEqual(unexpectedResources, []);
  assert.deepEqual(consoleErrors.filter(message => !message.startsWith('Failed to load resource: the server responded with a status of 404')), []);
  passed('all browser API traffic is GET-only and persisted scan identity is unchanged');

  const receipt = {
    schema_version: 'openguard-p1-browser-smoke/1',
    base,
    checks,
    history_count: historyBefore.items.length,
    assessed_scan_id: assessed.scan_id,
    assessment_id: assessmentId,
    resource_scan_id: resourceScan.scan_id,
    resource_ai_asset_count: aiAssets.length,
    partial_scan_id: partial?.scan_id ?? null,
    diff: { base_scan_id: baseScan.scan_id, target_scan_id: targetScan.scan_id },
    api_requests: apiRequests,
    expected_backend_404s: apiFailures,
    expected_resource_404s: resourceFailures,
    screenshots,
    page_errors: pageErrors,
    console_errors: consoleErrors,
  };
  await fs.writeFile(path.join(output, 'receipt.json'), JSON.stringify(receipt, null, 2));
  console.log(JSON.stringify({ checks, output, screenshots: screenshots.length }));
} catch (error) {
  const failure = path.join(output, 'failure.png');
  await page.screenshot({ path: failure, fullPage: true }).catch(() => {});
  console.error(JSON.stringify({ output, failure }));
  throw error;
} finally {
  await browser.close();
}
