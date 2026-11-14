import assert from 'node:assert/strict';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { dirname, join, resolve, extname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const task = resolve(frontend, '../..');
const out = join(task, 'evidence/frontend-workspace-navigation');
const dist = join(task, 'artifacts/frontend-workspace-navigation-tests');
await mkdir(out, { recursive: true });
await mkdir(join(task, 'runtime/tmp'), { recursive: true });
const { makeFrontendBuildConfig, loadVite } = await import(join(task, 'helpers/frontend-config.mjs'));
const config = await makeFrontendBuildConfig('frozen-tests');
config.build = { outDir: dist, emptyOutDir: false, minify: false, rollupOptions: { input: join(frontend, 'tests/workspace-navigation/index.html') } };
const vite = await loadVite();
await vite.build(config);
const server = createServer(async (req, res) => {
  try {
    const path = decodeURIComponent(new URL(req.url, 'http://127.0.0.1').pathname);
    if (path.includes('..')) throw Error('unsafe path');
    const file = join(dist, path);
    res.setHeader('Content-Type', extname(file) === '.js' ? 'text/javascript' : extname(file) === '.css' ? 'text/css' : 'text/html');
    res.end(await readFile(file));
  } catch { res.writeHead(404); res.end('NOT_FOUND'); }
});
await new Promise((done, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', done); });
const origin = 'http://127.0.0.1:' + server.address().port;
const { chromium } = await import(process.env.OPENGUARD_PLAYWRIGHT || 'playwright-core');
const cases = [], rejected = [], consoleErrors = [];
let browser, page;
async function one(name, body) {
  try { await body(); cases.push({ name, status: 'passed' }); }
  catch (error) { cases.push({ name, status: 'failed', error: String(error) }); }
}
const compact = async () => {
  await page.waitForFunction(() => document.querySelector('.og-app')?.classList.contains('og-workspace-rail-compact'));
  assert.equal(await page.locator('.og-sidebar').evaluate(el => Math.round(el.getBoundingClientRect().width)), 64);
};
const jump = async path => {
  await page.evaluate(path => window.__WORKSPACE_NAV__.jump(path), path);
  await compact();
};
const label = name => page.locator('.og-sidebar nav button').filter({ has: page.locator('.og-nav-label', { hasText: name }) });
try {
  browser = await chromium.launchPersistentContext(join(out, 'private-profile'), { headless: true, executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', viewport: { width: 1440, height: 900 }, args: ['--disable-background-networking', '--disable-component-update', '--no-first-run', '--disable-default-apps'], env: { ...process.env, TMPDIR: join(task, 'runtime/tmp') } });
  await browser.route('**/*', route => {
    if (new URL(route.request().url()).origin !== origin) { rejected.push(route.request().url()); return route.abort(); }
    return route.continue();
  });
  page = await browser.newPage();
  page.setDefaultTimeout(8000);
  page.on('pageerror', e => consoleErrors.push(String(e)));
  await page.goto(origin + '/tests/workspace-navigation/index.html');
  await page.waitForFunction(() => window.__WORKSPACE_NAV__?.ready);
  await one('all 13 workspace columns start as a compact rail with unchanged disabled rules', async () => {
    await compact();
    const buttons = page.locator('.og-sidebar nav button');
    assert.equal(await buttons.count(), 13);
    assert.equal(await page.locator('.og-sidebar nav button:disabled').count(), 10);
    assert.equal(await page.locator('.og-sidebar .og-nav-label').first().evaluate(el => getComputedStyle(el).display), 'none');
    assert.equal(await page.locator('.og-app').evaluate(el => el.classList.contains('og-workspace-light') && !el.classList.contains('og-chat-shell')), true);
    assert.deepEqual(await buttons.evaluateAll(rows => rows.filter(b => !b.disabled).map(b => b.getAttribute('aria-label'))), ['新建扫描', '扫描历史', '项目智询']);
  });
  await one('every compact icon has an unclipped body tooltip and disabled reasons', async () => {
    const wrappers = page.locator('.og-sidebar nav .og-nav-item');
    for (let i = 0; i < 13; i++) {
      await page.evaluate(() => document.activeElement instanceof HTMLElement && document.activeElement.blur());
      await wrappers.nth(i).hover();
      const button = wrappers.nth(i).locator('button');
      const name = await button.getAttribute('aria-label');
      await page.getByRole('tooltip').waitFor();
      assert.equal(await page.getByRole('tooltip').locator(':scope > span').textContent(), name);
      assert.equal(await page.getByRole('tooltip').evaluate(el => el.parentElement === document.body), true);
      const box = await page.getByRole('tooltip').boundingBox();
      assert.ok(box && box.x >= 64 && box.x + box.width <= 1440 && box.y >= 0 && box.y + box.height <= 900);
      if (await button.isDisabled()) assert.match(await page.getByRole('tooltip').textContent(), /不可用：请先选择或创建扫描任务/);
      await page.mouse.move(400, 200);
      await page.getByRole('tooltip').waitFor({ state: 'hidden' });
    }
  });
  await one('keyboard focus shows labels, Escape dismisses them, and disabled controls cannot navigate', async () => {
    await label('新建扫描').locator('..').hover();
    await label('扫描历史').focus();
    await page.getByRole('tooltip').waitFor();
    assert.equal(await page.getByRole('tooltip').count(), 1);
    assert.equal(await page.getByRole('tooltip').textContent(), '扫描历史');
    await page.keyboard.press('Escape');
    await page.getByRole('tooltip').waitFor({ state: 'hidden' });
    const disabled = label('扫描进度').locator('..');
    await disabled.focus();
    await page.getByRole('tooltip').waitFor();
    assert.match(await disabled.getAttribute('aria-label'), /扫描进度.*不可用.*请先选择或创建扫描任务/);
    assert.equal(await disabled.locator('button').isDisabled(), true);
    await page.screenshot({ path: join(out, 'disabled-navigation-tooltip.png') });
    const before = page.url();
    await page.keyboard.press('Enter'); await page.keyboard.press('Space');
    const disabledBox = await disabled.boundingBox();
    assert.ok(disabledBox);
    await page.mouse.click(disabledBox.x + disabledBox.width / 2, disabledBox.y + disabledBox.height / 2);
    assert.equal(page.url(), before);
    await page.evaluate(() => document.activeElement instanceof HTMLElement && document.activeElement.blur());
    await page.mouse.move(400, 200);
  });
  await one('manual expansion is reset by a real new-scan to history route switch and same-column click', async () => {
    await page.getByRole('button', { name: '展开工作台导航', exact: true }).click();
    assert.equal(await page.locator('.og-sidebar').evaluate(el => Math.round(el.getBoundingClientRect().width)), 224);
    await label('扫描历史').click(); await compact();
    assert.equal(new URL(page.url()).pathname, '/app/history');
    await page.getByRole('button', { name: '展开工作台导航', exact: true }).click();
    await label('扫描历史').click(); await compact();
    assert.equal(await page.locator('.og-app').evaluate(el => el.classList.contains('og-chat-shell')), false);
  });
  await one('assistant retains chat layout while ordinary long pages restore document scrolling', async () => {
    await label('项目智询').click(); await compact();
    assert.equal(await page.locator('.og-app').evaluate(el => el.classList.contains('og-chat-shell')), true);
    await label('新建扫描').click(); await compact();
    const result = await page.locator('#workspace-main').evaluate(el => {
      const spacer = document.createElement('div'); spacer.dataset.syntheticTestOnly = 'long-page'; spacer.style.height = '2400px'; el.append(spacer);
      window.scrollTo({ top: 900, behavior: 'instant' });
      return { chat: document.querySelector('.og-app').classList.contains('og-chat-shell'), bodyOverflow: getComputedStyle(document.body).overflow, rootOverflow: getComputedStyle(document.querySelector('#root')).overflow, height: document.documentElement.scrollHeight, scroll: window.scrollY };
    });
    assert.equal(result.chat, false); assert.notEqual(result.bodyOverflow, 'hidden'); assert.notEqual(result.rootOverflow, 'hidden'); assert.ok(result.height > 2400); assert.ok(result.scroll > 0);
    await page.locator('[data-synthetic-test-only="long-page"]').evaluate(el => el.remove());
    await page.evaluate(() => window.scrollTo(0, 0));
  });
  await one('scan identity and risk detail changes reset manual expansion without weakening availability', async () => {
    await jump('/app/scans/SYNTHETIC_one/risks?mode=api');
    assert.equal(await page.locator('.og-sidebar nav button:disabled').count(), 0);
    for (const path of ['/app/scans/SYNTHETIC_two/risks?mode=api', '/app/scans/SYNTHETIC_two/risks/risk_a?mode=api', '/app/scans/SYNTHETIC_two/risks/risk_b?mode=api']) {
      await page.getByRole('button', { name: '展开工作台导航', exact: true }).click();
      await jump(path);
    }
    await jump('/app/new-scan?mode=api');
  });
  await one('an open keyboard tooltip closes when a narrow viewport hides its sidebar', async () => {
    await label('扫描历史').focus();
    await page.getByRole('tooltip').waitFor();
    await page.setViewportSize({ width: 730, height: 900 });
    await page.getByRole('tooltip').waitFor({ state: 'hidden' });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.evaluate(() => document.activeElement instanceof HTMLElement && document.activeElement.blur());
  });
  await one('mobile and 730px expanded chat use a drawer with full navigation labels', async () => {
    for (const width of [390, 730]) {
      await page.setViewportSize({ width, height: 900 });
      await page.evaluate(() => window.__WORKSPACE_NAV__.jump('/app/assistant?mode=api'));
      await page.waitForFunction(() => document.querySelector('.og-app')?.classList.contains('og-chat-shell'));
      await page.locator('.og-workspace-rail-toggle').evaluate(el => el.click());
      assert.equal(await page.locator('.og-sidebar').isVisible(), false);
      assert.equal(await page.locator('.og-workspace').evaluate(el => getComputedStyle(el).marginLeft), '0px');
      await page.getByRole('button', { name: '打开导航', exact: true }).click();
      const drawer = page.getByRole('dialog', { name: '工作台导航', exact: true });
      await drawer.waitFor();
      assert.equal(await drawer.locator('nav button').count(), 13);
      assert.equal(await drawer.locator('.og-nav-label').first().isVisible(), true);
      assert.equal(await drawer.locator('.og-nav-item[tabindex="0"]').count(), 0);
      assert.equal(await drawer.getByRole('tooltip').count(), 0);
      await drawer.getByRole('button', { name: '扫描历史', exact: true }).click();
      await drawer.waitFor({ state: 'hidden' });
      assert.equal(new URL(page.url()).pathname, '/app/history');
    }
    await page.setViewportSize({ width: 1440, height: 900 });
  });
  await one('navigation emits only the allowed synthetic reads and no business or model writes', async () => {
    const state = await page.evaluate(() => ({ ledger: window.__WORKSPACE_NAV__.ledger, unknown: window.__WORKSPACE_NAV__.unknown }));
    assert.deepEqual(state.unknown, []);
    assert.ok(state.ledger.every(row => row.method === 'GET'));
    assert.ok(state.ledger.some(row => row.path.startsWith('/api/v1/scans?')));
    assert.ok(state.ledger.some(row => row.path === '/api/v1/assistant/conversations'));
    assert.deepEqual(rejected, []); assert.deepEqual(consoleErrors, []);
  });
  await page.screenshot({ path: join(out, 'desktop-navigation.png'), fullPage: true });
  const sources = {};
  for (const name of ['src/App.tsx', 'src/components/NavTooltip.tsx', 'src/styles/workspace-nav.css', 'tests/workspace-navigation/browser.tsx', 'tests/workspace-navigation/run.mjs', 'tests/workspace-navigation/index.html']) {
    const bytes = await readFile(join(frontend, name)); sources[name] = { bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') };
  }
  const report = { status: cases.every(c => c.status === 'passed') ? 'passed' : 'failed', classification: 'SYNTHETIC_TEST_ONLY_REAL_APP_CLOSED_GET_ONLY_TRANSPORT', cases, execution: { utc: new Date().toISOString(), origin, externalRequests: rejected, consoleErrors }, sources, transport: await page.evaluate(() => ({ ledger: window.__WORKSPACE_NAV__.ledger, unknown: window.__WORKSPACE_NAV__.unknown })) };
  await writeFile(join(out, 'RESULT.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ status: report.status, passed: cases.filter(c => c.status === 'passed').length, total: cases.length, failures: cases.filter(c => c.status !== 'passed'), externalRequests: rejected, consoleErrors }, null, 2));
  if (report.status !== 'passed') process.exitCode = 1;
} finally { await browser?.close(); await new Promise(done => server.close(done)); }
