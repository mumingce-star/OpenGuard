/** Additional real-App scroll scenarios. The original nine checks are unchanged. */
import assert from 'node:assert/strict';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { dirname, join, resolve, extname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const task = resolve(frontend, '../..');
const out = join(task, 'evidence/frontend-workspace-navigation-scroll');
const dist = join(task, 'artifacts/frontend-workspace-navigation-scroll-tests');
await mkdir(out, { recursive: true });
const { makeFrontendBuildConfig, loadVite } = await import(join(task, 'helpers/frontend-config.mjs'));
const config = await makeFrontendBuildConfig('frozen-tests');
config.build = { outDir: dist, emptyOutDir: false, minify: false, rollupOptions: { input: join(frontend, 'tests/workspace-navigation/index.html') } };
await (await loadVite()).build(config);
const server = createServer(async (req, res) => {
  try {
    const path = decodeURIComponent(new URL(req.url, 'http://127.0.0.1').pathname);
    if (path.includes('..')) throw Error('unsafe');
    res.setHeader('Content-Type', extname(path) === '.js' ? 'text/javascript' : extname(path) === '.css' ? 'text/css' : 'text/html');
    res.end(await readFile(join(dist, path)));
  } catch { res.writeHead(404); res.end('NOT_FOUND'); }
});
await new Promise((done, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', done); });
const origin = 'http://127.0.0.1:' + server.address().port;
const { chromium } = await import(process.env.OPENGUARD_PLAYWRIGHT || 'playwright-core');
const cases = [], rejected = [], consoleErrors = [], traces = [];
let browser, page;
const one = async (name, body) => { try { await body(); cases.push({ name, status: 'passed' }); } catch (error) { cases.push({ name, status: 'failed', error: String(error) }); } };
async function prepareScroll() {
  const y = await page.locator('#workspace-main').evaluate(el => {
    // Keep both real App pages tall so natural height clamping cannot hide a routing failure.
    el.style.minHeight = '3600px';
    window.scrollTo({ top: 1600, behavior: 'instant' });
    return window.scrollY;
  });
  assert.equal(y, 1600);
}
async function recordAfterClick(name, expectedPath) {
  await page.locator('.og-sidebar nav button').filter({ has: page.locator('.og-nav-label', { hasText: name }) }).click();
  const samples = await page.evaluate(async () => {
    const rows = [{ frame: 0, path: location.pathname, y: window.scrollY }];
    for (let frame = 1; frame <= 40; frame++) {
      await new Promise(requestAnimationFrame);
      rows.push({ frame, path: location.pathname, y: window.scrollY });
    }
    return rows;
  });
  traces.push({ target: name, samples });
  assert.equal(samples[0].path, expectedPath);
  assert.equal(samples.at(-1).y, 0, 'new workspace page must settle at document top');
  assert.equal(samples[1].y, 0, 'new workspace page must start at document top without inheriting an animated old offset');
}
try {
  browser = await chromium.launchPersistentContext(join(out, 'private-profile'), { headless: true, executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', viewport: { width: 1440, height: 900 }, args: ['--disable-background-networking', '--disable-component-update', '--no-first-run', '--disable-default-apps'], env: { ...process.env, TMPDIR: join(task, 'runtime/tmp') } });
  await browser.route('**/*', route => { if (new URL(route.request().url()).origin !== origin) { rejected.push(route.request().url()); return route.abort(); } return route.continue(); });
  page = await browser.newPage(); page.setDefaultTimeout(8000); page.on('pageerror', e => consoleErrors.push(String(e)));
  await page.goto(origin + '/tests/workspace-navigation/index.html');
  await page.waitForFunction(() => window.__WORKSPACE_NAV__?.ready);
  await one('a real long App page switches to History at the top without inherited scroll offset', async () => { await prepareScroll(); await recordAfterClick('扫描历史', '/app/history'); });
  await one('a real long History page switches to New Scan at the top without inherited scroll offset', async () => { await prepareScroll(); await recordAfterClick('新建扫描', '/app/new-scan'); });
  await one('the additional navigation scenarios remain GET-only with no external requests', async () => {
    const transport = await page.evaluate(() => ({ ledger: window.__WORKSPACE_NAV__.ledger, unknown: window.__WORKSPACE_NAV__.unknown }));
    assert.deepEqual(transport.unknown, []); assert.ok(transport.ledger.every(row => row.method === 'GET')); assert.deepEqual(rejected, []); assert.deepEqual(consoleErrors, []);
  });
  const sources = {};
  for (const name of ['src/App.tsx', 'src/hooks/useRoute.ts', 'tests/workspace-navigation/browser.tsx', 'tests/workspace-navigation/run.mjs', 'tests/workspace-navigation/scroll-run.mjs']) {
    const bytes = await readFile(join(frontend, name)); sources[name] = { bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') };
  }
  const report = { status: cases.every(c => c.status === 'passed') ? 'passed' : 'failed', classification: 'SYNTHETIC_TEST_ONLY_REAL_APP_CLOSED_GET_ONLY_TRANSPORT', cases, traces, sources, execution: { utc: new Date().toISOString(), origin, externalRequests: rejected, consoleErrors }, transport: await page.evaluate(() => ({ ledger: window.__WORKSPACE_NAV__.ledger, unknown: window.__WORKSPACE_NAV__.unknown })) };
  await writeFile(join(out, 'RESULT.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ status: report.status, passed: cases.filter(c => c.status === 'passed').length, total: cases.length, failures: cases.filter(c => c.status !== 'passed'), traces: traces.map(t => ({ target: t.target, first: t.samples.slice(0, 5), last: t.samples.at(-1) })), externalRequests: rejected, consoleErrors }, null, 2));
  if (report.status !== 'passed') process.exitCode = 1;
} finally { await browser?.close(); await new Promise(done => server.close(done)); }
