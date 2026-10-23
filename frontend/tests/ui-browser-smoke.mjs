import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.OPENGUARD_PLAYWRIGHT || 'playwright');
const here = path.dirname(fileURLToPath(import.meta.url));
const dist = path.resolve(process.env.OPENGUARD_UI_DIST || path.join(here, '..', 'dist'));
const output = process.env.OPENGUARD_QA_OUTPUT || await fs.mkdtemp(path.join(os.tmpdir(), 'openguard-ui-qa-'));
const origin = 'http://openguard.local';
const types = new Map([
  ['.css', 'text/css'], ['.html', 'text/html'], ['.js', 'text/javascript'],
  ['.mp4', 'video/mp4'], ['.txt', 'text/plain'], ['.webm', 'video/webm'],
]);

await fs.access(path.join(dist, 'index.html'));
await fs.mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: process.env.OPENGUARD_BROWSER || 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
await context.addInitScript(() => {
  if (!crypto.randomUUID) Object.defineProperty(crypto, 'randomUUID', { value: () => '00000000-0000-4000-8000-000000000001' });
});
const page = await context.newPage();
const pageErrors = [];
const checks = [];
const contrast = [];
const requests = [];
let sampleDownloads = 0;
let servedDist = dist;
page.on('pageerror', error => pageErrors.push(error.message));

await page.route(`${origin}/**`, async route => {
  const url = new URL(route.request().url());
  requests.push({ method: route.request().method(), path: url.pathname });
  if (url.pathname === '/ui-sample.txt' && ++sampleDownloads === 1) {
    await new Promise(resolve => setTimeout(resolve, 500));
    await route.fulfill({ status: 503, body: 'UI download failure test only' });
    return;
  }
  if (url.pathname.startsWith('/api/')) {
    await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 'offline_smoke', message: 'UI-only browser smoke' } }) });
    return;
  }
  const requested = decodeURIComponent(url.pathname).replace(/^\/+/, '');
  const candidate = requested && path.extname(requested) ? path.resolve(servedDist, requested) : path.join(servedDist, 'index.html');
  if (candidate !== path.join(servedDist, 'index.html') && !candidate.startsWith(servedDist + path.sep)) {
    await route.fulfill({ status: 404, body: 'not found' });
    return;
  }
  await route.fulfill({ path: candidate, contentType: types.get(path.extname(candidate)) });
});

try {
  if (process.env.OPENGUARD_UI_BASELINE) {
    servedDist = path.resolve(process.env.OPENGUARD_UI_BASELINE);
    for (const [name, url] of [['landing', '/'], ['new-scan', '/app/new-scan?mode=api']]) {
      await page.goto(origin + url);
      if (name === 'new-scan') await page.locator('input[type=file]').setInputFiles({ name: 'ui-demo.zip', mimeType: 'application/zip', buffer: Buffer.from('PK') });
      await page.screenshot({ path: path.join(output, `before-${name}.png`), fullPage: true });
    }
    servedDist = dist;
  }
  await page.goto(`${origin}/ui-preview.html`);
  const checkbox = page.getByRole('checkbox', { name: '选择这项设计样板' });
  await checkbox.check();
  assert.equal(await checkbox.isChecked(), true);
  await checkbox.focus(); await page.keyboard.press('Space');
  assert.equal(await checkbox.isChecked(), false);
  assert.equal(await page.getByRole('checkbox', { name: '暂不可用的操作' }).isDisabled(), true);
  checks.push('native checkbox pointer, keyboard and disabled states');
  const zip = page.getByRole('radio', { name: '上传 ZIP' });
  await zip.check(); await zip.focus(); await page.keyboard.press('ArrowLeft');
  assert.equal(await page.getByRole('radio', { name: 'GitHub 仓库' }).isChecked(), true);
  checks.push('segmented radio selection and arrow keys');
  await page.getByRole('button', { name: '查看原理' }).click();
  assert.equal(await page.getByRole('button', { name: '返回概览' }).getAttribute('aria-expanded'), 'true');
  await page.getByRole('button', { name: '返回概览' }).click();
  const help = page.getByRole('button', { name: '样板 Hash 说明' });
  await help.click(); assert.equal(await help.getAttribute('aria-expanded'), 'true');
  await page.keyboard.press('Escape'); assert.equal(await help.getAttribute('aria-expanded'), 'false');
  assert.equal(await page.getByRole('tooltip').isVisible(), false);
  checks.push('flip and help controls work without hover');
  const sampleButton = page.getByRole('button', { name: '下载样板文本' });
  await sampleButton.dblclick();
  await page.locator('.og-download-control.busy').waitFor();
  assert.equal(await page.locator('.og-download-control.busy button').getAttribute('aria-busy'), 'true');
  await page.screenshot({ path: path.join(output, 'download-busy.png') });
  await page.getByRole('alert').filter({ hasText: 'HTTP 503' }).waitFor();
  assert.equal(sampleDownloads, 1);
  assert.equal(await page.getByText('已发起下载，请在浏览器中确认保存。', { exact: true }).count(), 0);
  await page.screenshot({ path: path.join(output, 'download-failure.png') });
  const saved = page.waitForEvent('download');
  await page.getByRole('button', { name: '重试下载' }).click();
  const download = await saved;
  assert.equal(await fs.readFile(await download.path(), 'utf8'), await fs.readFile(path.join(dist, 'ui-sample.txt'), 'utf8'));
  assert.equal(sampleDownloads, 2);
  await page.getByText('已发起下载，请在浏览器中确认保存。', { exact: true }).waitFor();
  checks.push('download 503, double-click lock, explicit retry, exact downloaded bytes');
  await page.screenshot({ path: path.join(output, 'controls-desktop.png'), fullPage: true });
  await page.screenshot({ path: path.join(output, 'controls-key.png'), clip: { x: 154, y: 231, width: 1132, height: 560 } });
  const colors = await page.evaluate(() => ({
    text: getComputedStyle(document.querySelector('.og-app')).color,
    border: getComputedStyle(document.querySelector('.og-search-control input')).borderTopColor,
    check: getComputedStyle(document.querySelector('.og-choice rect')).stroke,
  }));
  function luminance(color) {
    const channels = color.startsWith('#') ? color.slice(1).match(/../g).map(x => parseInt(x, 16)) : color.match(/[\d.]+/g).slice(0, 3).map(Number);
    return channels.map(x => x / 255).map(x => x <= .04045 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4).reduce((sum, x, i) => sum + x * [.2126, .7152, .0722][i], 0);
  }
  for (const [name, foreground, background, minimum] of [['body text', colors.text, '#112136', 4.5], ['muted text', '#b5c6db', '#112136', 4.5], ['search border', colors.border, '#172a40', 3], ['checkbox outline', colors.check, '#112136', 3]]) {
    const values = [luminance(foreground), luminance(background)].sort((a,b) => b-a);
    const ratio = (values[0] + .05) / (values[1] + .05);
    assert.ok(ratio >= minimum, `${name}: ${ratio}`); contrast.push({ name, foreground, background, ratio, minimum });
  }
  checks.push('representative text and control contrast tokens');
  await page.setViewportSize({ width: 1024, height: 900 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
  await page.screenshot({ path: path.join(output, 'controls-tablet.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
  await page.screenshot({ path: path.join(output, 'controls-mobile.png'), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await checkbox.check();
  assert.notEqual(await checkbox.locator('..').locator('path').evaluate(el => getComputedStyle(el).transitionDuration), '0s');
  await page.emulateMedia({ reducedMotion: 'reduce' });
  assert.equal(await checkbox.locator('..').locator('path').evaluate(el => getComputedStyle(el).transitionDuration), '0s');
  checks.push('390px sample layout and reduced-motion fallback');
  await page.goto(`${origin}/`);
  await page.getByRole('heading', { name: '一眼看见结论，也能一路追到证据。' }).waitFor();
  assert.equal(await page.getByRole('button', { name: '开始安全扫描' }).count(), 1);
  assert.equal(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches), true);
  await page.screenshot({ path: path.join(output, 'landing-desktop.png'), fullPage: true });
  checks.push('landing source boundaries and one primary scan CTA');

  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
  await page.screenshot({ path: path.join(output, 'landing-mobile.png'), fullPage: true });

  await page.setViewportSize({ width: 1440, height: 900 });
  await Promise.all([
    page.waitForURL(url => url.pathname === '/app/new-scan'),
    page.locator('.hero-actions .primary-button').click(),
  ]);
  await page.getByRole('heading', { name: '从一个项目开始' }).waitFor();
  await page.getByRole('radio', { name: '上传 ZIP' }).check();
  await page.locator('input[type=file]').setInputFiles({ name: 'ui-demo.zip', mimeType: 'application/zip', buffer: Buffer.from('PK') });
  await page.getByText('ui-demo.zip', { exact: true }).waitFor();
  assert.match(await page.locator('.og-drop-zone').getAttribute('class'), /og-drop-zone/);
  await page.screenshot({ path: path.join(output, 'new-scan-upload.png'), fullPage: true });
  checks.push('native ZIP selection and visible local file state');

  await page.goto(`${origin}/app/history?limit=20`);
  const search = page.getByRole('searchbox', { name: '搜索公开项目或仓库' });
  await search.waitFor();
  await search.focus();
  assert.equal(await search.getAttribute('placeholder'), '例如 openai 或 github.com/owner/repo');
  assert.notEqual(await search.evaluate(element => getComputedStyle(element).borderColor), 'rgba(0, 0, 0, 0)');
  await page.keyboard.press('Tab');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: path.join(output, 'history-mobile.png'), fullPage: true });
  const overflow = await page.evaluate(() => ({
    viewport: innerWidth,
    page: document.documentElement.scrollWidth,
    elements: [...document.querySelectorAll('*')].map(element => {
      const rect = element.getBoundingClientRect();
      return { tag: element.tagName, className: element.className, left: rect.left, right: rect.right, width: rect.width };
    }).filter(item => item.right > innerWidth + 1 || item.left < -1).slice(0, 8),
  }));
  assert.equal(overflow.page <= overflow.viewport + 1, true, JSON.stringify(overflow));
  checks.push('History real-API error state, focus and narrow layout');

  await page.setViewportSize({ width: 720, height: 900 });
  await page.goto(`${origin}/app/new-scan?mode=mock`);
  await page.getByRole('button', { name: '载入固定演示' }).click();
  await page.waitForURL(url => /\/app\/scans\/DEMO-[^/]+\/progress/.test(url.pathname));
  const demoScanId = page.url().match(/\/app\/scans\/([^/]+)\/progress/)?.[1];
  assert.ok(demoScanId);
  await page.getByRole('button', { name: '跳过等待' }).click();
  await page.getByRole('button', { name: '查看扫描结果' }).click();
  await page.waitForURL(url => url.pathname === `/app/scans/${demoScanId}/overview`);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole('button', { name: '合规报告' }).click();
  await page.waitForURL(url => url.pathname === `/app/scans/${demoScanId}/report`);
  const historicalReport = page.locator('details.og-historical-report > summary');
  await historicalReport.waitFor();
  assert.match(await historicalReport.innerText(), /查看历史扫描报告/);
  await historicalReport.click();
  await page.setViewportSize({ width: 720, height: 900 });
  const downloadButton = page.getByRole('button', { name: '导出演示 JSON' });
  await downloadButton.waitFor();
  const downloadStyle = await downloadButton.evaluate(element => {
    const button = getComputedStyle(element);
    const glyph = getComputedStyle(element.querySelector('svg'));
    return {
      borderRadius: button.borderRadius,
      borderWidth: button.borderTopWidth,
      glyphRadius: glyph.borderRadius,
      glyphWidth: glyph.width,
    };
  });
  assert.equal(downloadStyle.borderRadius, '999px');
  assert.equal(downloadStyle.borderWidth, '2px');
  assert.equal(downloadStyle.glyphRadius, '50%');
  assert.equal(downloadStyle.glyphWidth, '42px');
  await page.screenshot({ path: path.join(output, 'report-download.png'), fullPage: false });
  await page.emulateMedia({ media: 'print' });
  assert.equal(await page.locator('.og-report').isVisible(), true);
  assert.equal(await downloadButton.isVisible(), false);
  await page.screenshot({ path: path.join(output, 'report-print.png'), fullPage: true });
  await page.emulateMedia({ media: 'screen' });
  checks.push('report download visual fingerprint and printable report body');

  assert.deepEqual(pageErrors, []);
  assert.deepEqual(requests.filter(request => request.method !== 'GET'), []);
  checks.push('zero pageerrors and GET-only request audit');
  const receipt = { count: checks.length, checks, contrast, output, sampleDownloads, requests, reducedMotion: true, mobileWidth: 390, tabletWidth: 1024, data: 'UI_TEST_ONLY; API reads return explicit 503; no business success data' };
  await fs.writeFile(path.join(output, 'receipt.json'), JSON.stringify(receipt, null, 2));
  console.log(JSON.stringify(receipt));
} finally {
  await browser.close();
}
