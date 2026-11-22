// P0.2: actual authenticated ZIP scan and workbench under an isolated loopback host.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import fs from 'node:fs/promises';
import { createRequire } from 'node:module';
import path from 'node:path';
import { setTimeout as pause } from 'node:timers/promises';
import { after, before, test } from 'node:test';

const require = createRequire(import.meta.url);
const localHost = process.env.OPENGUARD_TEST_URL;
const output = process.env.OPENGUARD_QA_OUTPUT;
assert.ok(localHost && output, 'Set OPENGUARD_TEST_URL and OPENGUARD_QA_OUTPUT');
const screenshotDir = process.env.OPENGUARD_QA_SCREENSHOTS || output;
const url = new URL(localHost);
assert.equal(url.protocol, 'http:');
assert.equal(url.hostname, '127.0.0.1');
assert.ok(url.port);
const origin = url.origin;
const { chromium } = require(process.env.OPENGUARD_PLAYWRIGHT || 'playwright');
const requestPath = (target) => new URL(target.url()).pathname;
const checksum = (value) => createHash('sha256').update(value).digest('hex');
const projection = (id) => `/api/v1/scans/${id}/dependency-evidence`;
const scanRoute = (id, page) => `/app/scans/${id}/${page}?mode=api`;

const rootPackage = JSON.stringify({ name: 'task45-p02-test-only', version: '1.0.0', license: 'MIT' });
const uv = (name, version) => `version = 1
revision = 3
[[package]]
name = "${name}"
version = "${version}"
source = { registry = "https://pypi.org/simple" }
`;
const conflict = (declarationCount) => ({
  'package.json': rootPackage,
  'sub/pyproject.toml': `[project]
name = "task45-test-only-project"
version = "1.0.0"
dependencies = ${JSON.stringify(Array(declarationCount).fill('p02-versioned==1.2.3'))}
`,
  'sub/uv.lock': uv('p02-versioned', '2.3.4'),
});
const inputs = {
  completed: {
    'package.json': rootPackage,
    'requirements.txt': 'p02-manifest==1.2.3\n',
    'uv.lock': uv('p02-locked', '1.2.3'),
    'bom.json': JSON.stringify({
      bomFormat: 'CycloneDX', specVersion: '1.5',
      components: [{ 'bom-ref': 'p02-sbom', name: 'p02-sbom', version: '1.2.3', purl: 'pkg:npm/p02-sbom@1.2.3' }],
    }),
  },
  partial: conflict(1),
  'truncated-conflict': conflict(9),
  empty: { 'package.json': rootPackage },
  paging: {
    'package.json': rootPackage,
    'requirements.txt': Array.from({ length: 108 }, (_, n) =>
      `p02-paged-${String(n).padStart(3, '0')}==1.0.0\n`).join(''),
  },
};

let browser, context, page;
const scans = new Map(), denied = [], requests = [], pageErrors = [];

before(async () => {
  await fs.mkdir(output, { recursive: true });
  await fs.mkdir(screenshotDir, { recursive: true });
  execFileSync(process.env.OPENGUARD_PYTHON || 'python3', ['-B', '-c', `
import json,sys,zipfile
from pathlib import Path
folder=Path(sys.argv[1])
for name, members in json.load(sys.stdin).items():
    with zipfile.ZipFile(folder/(name+'-TEST_ONLY.zip'),'w') as archive:
        for member, data in sorted(members.items()):
            archive.writestr(zipfile.ZipInfo(member, (2026,11,22,0,0,0)), data.encode())
`, output], { input: JSON.stringify(inputs) });

  browser = await chromium.launch({
    channel: process.env.OPENGUARD_BROWSER || 'chrome',
    headless: true,
    args: ['--disable-background-networking', '--disable-component-update', '--disable-sync'],
  });
  context = await browser.newContext({
    viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce', serviceWorkers: 'block',
  });
  await context.route('**/*', async (route) => {
    const requested = new URL(route.request().url());
    if (requested.origin !== origin) {
      denied.push(requested.origin);
      return route.abort('blockedbyclient');
    }
    await route.fallback();
  });
  await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin });
  page = await context.newPage();
  page.setDefaultTimeout(12_000);
  page.on('pageerror', (error) => pageErrors.push(error.message));
  page.on('request', (request) => {
    if (requestPath(request).startsWith('/api/')) {
      requests.push({ method: request.method(), path: requestPath(request) });
    }
  });
  const health = await api('/healthz');
  assert.equal(health.data_scope, 'TEST_ONLY');
  for (const flag of ['P2', 'P2_AI', 'ASSISTANT', 'AI', 'PUBLIC_GIT']) {
    assert.equal(health.flags[`OPENGUARD_ENABLE_${flag}`], '0', flag);
  }
  await page.goto(origin + '/register?next=%2Fapp%2Fnew-scan%3Fmode%3Dapi');
  await page.locator('#account-username').fill('p02_test_' + randomUUID().slice(0, 8));
  const password = 'IsolatedP02-' + randomUUID().slice(0, 8);
  await page.locator('#account-password').fill(password);
  await page.locator('#account-confirmation').fill(password);
  const registered = page.waitForResponse((response) =>
    response.request().method() === 'POST' && requestPath(response) === '/api/v1/auth/register');
  await page.getByRole('button', { name: '注册并进入工作台', exact: true }).click();
  assert.equal((await registered).status(), 201);
  await page.waitForURL('**/app/new-scan?mode=api');
  console.log(`P0.2 Chrome ${browser.version()} and actual TEST_ONLY account gateway`);
});

after(async () => {
  await browser?.close();
  assert.deepEqual(denied, [], 'No page requests to external origins');
  assert.deepEqual(pageErrors, [], 'No uncaught browser errors');
  assert.equal(requests.filter(({ path: entry }) => /\/(?:p2|assistant|report-v2)(?:\/|$)/.test(entry)).length, 0);
  assert.equal(requests.filter(({ method, path: entry }) =>
    method === 'POST' && entry === '/api/v1/scans').length, Object.keys(inputs).length);
  console.log('P0.2 paged dependency requests, no P2/Assistant/Report V2 requests:', JSON.stringify({
    scan_posts: Object.keys(inputs).length,
    dependency_gets: requests.filter(({ path: entry }) => entry.endsWith('/dependency-evidence')).length,
    remediation_gets: requests.filter(({ path: entry }) => entry.endsWith('/remediation-tasks')).length,
    external_requests: denied.length,
  }));
});

async function api(relative) {
  const response = await context.request.get(origin + relative);
  assert.equal(response.status(), 200, relative.split('?')[0]);
  return response.json();
}

async function submit(name, status) {
  await page.goto(origin + '/app/new-scan?mode=api');
  await page.locator('input[type=file]').setInputFiles(path.join(output, `${name}-TEST_ONLY.zip`));
  await page.getByRole('button', { name: '下一步：确认用途', exact: true }).click();
  const received = page.waitForResponse((response) =>
    response.request().method() === 'POST' && requestPath(response) === '/api/v1/scans');
  await page.getByRole('button', { name: '开始扫描并评估', exact: true }).click();
  const accepted = await received;
  assert.equal(accepted.status(), 202);
  const { scan_id: id } = await accepted.json();
  assert.match(id, /^scn_/);
  const title = status === 'completed' ? '扫描已完成' : '扫描已结束 · 部分结果';
  await page.getByRole('heading', { name: title, exact: true }).waitFor({ timeout: 30_000 });
  assert.equal((await api(`/api/v1/scans/${id}`)).status, status);
  scans.set(name, id);
  return id;
}

const panel = () => page.getByRole('region', { name: '依赖与证据', exact: true });
const rows = () => panel().locator('button[data-dependency-resource]');
const getRow = (item) => panel().locator(`button[data-dependency-resource="${item.resource_id}"]`);
const screenshot = (name) => page.screenshot({ path: path.join(screenshotDir, `${name}.png`), animations: 'disabled' });

async function openProjection(id, route = 'resources', extra = '') {
  const received = page.waitForResponse((response) => requestPath(response) === projection(id));
  await page.goto(origin + scanRoute(id, route) + extra);
  return verifyProjection(id, received);
}

async function verifyProjection(id, received) {
  const response = await received;
  assert.equal(response.status(), 200);
  const payload = await response.json();
  assert.equal(payload.schema_version, 'openguard-dependency-evidence/1');
  assert.equal(payload.scan_ref.scan_id, id);
  assert.match(payload.scan_ref.facts_hash, /^[a-f0-9]{64}$/);
  await panel().waitFor();
  return payload;
}

async function expand(item) {
  const row = getRow(item);
  await row.click();
  assert.equal(await row.getAttribute('aria-expanded'), 'true');
  const detailId = await row.getAttribute('aria-controls');
  return detailId ? panel().locator(`[id="${detailId}"]`) : panel();
}

async function verifyEvidence(detail, evidence, file) {
  assert.equal(evidence.source_sha256, checksum(file));
  await detail.getByText(evidence.file_path, { exact: true }).first().waitFor();
  await detail.getByText(evidence.source_sha256, { exact: true }).first().waitFor();
  await detail.getByText(evidence.evidence_id, { exact: true }).first().waitFor();
}

test('COMPLETED real ZIP shows source, role, verification and copyable evidence', { timeout: 60_000 }, async () => {
  const id = await submit('completed', 'completed');
  await page.goto(origin + scanRoute(id, 'assessment'));
  const received = page.waitForResponse((response) => requestPath(response) === projection(id));
  await page.getByRole('button', { name: '查看依赖证据', exact: true }).click();
  await page.waitForURL((current) => current.pathname === `/app/scans/${id}/resources`);
  const payload = await verifyProjection(id, received);
  assert.equal(payload.scan_ref.status, 'completed');
  assert.equal(payload.total, 3);
  for (const [name, source, label, role] of [
    ['p02-manifest', 'manifest', 'Manifest', 'observed'],
    ['p02-locked', 'lock', 'Lock', 'inferred'],
    ['p02-sbom', 'sbom', 'SBOM', 'inferred'],
  ]) {
    const item = payload.items.find((entry) => entry.name === name);
    assert.ok(item);
    assert.equal(item.version, '1.2.3');
    assert.deepEqual(item.sources, [source]);
    assert.equal(item.role_state, role);
    const row = getRow(item);
    await row.getByText(name, { exact: true }).waitFor();
    await row.getByText('1.2.3', { exact: true }).waitFor();
    await row.getByText(label, { exact: true }).waitFor();
    await row.getByText(role === 'observed' ? '已观察' : '推断发现', { exact: true }).waitFor();
  }
  const item = payload.items.find((entry) => entry.name === 'p02-locked');
  const [evidence] = item.evidence;
  assert.equal(evidence.verification_status, 'pending');
  const detail = await expand(item);
  await verifyEvidence(detail, evidence, inputs.completed[evidence.file_path]);
  await detail.getByText(evidence.producer.name, { exact: false }).first().waitFor();
  await detail.getByText(/待核验|pending/).first().waitFor();
  assert.equal(await detail.getByText(/^(?:已验证|已核验|verified)$/).count(), 0);
  for (const [label, value] of [['复制 Evidence ID', evidence.evidence_id], ['复制 SHA-256', evidence.source_sha256]]) {
    await detail.getByRole('button', { name: label, exact: true }).first().click();
    assert.equal(await page.evaluate(() => navigator.clipboard.readText()), value, label);
  }
  await screenshot('completed-evidence');
});

test('PARTIAL real ZIP renders both confirmed conflict sides with source hashes', { timeout: 60_000 }, async () => {
  const id = await submit('partial', 'partial');
  const payload = await openProjection(id);
  assert.equal(payload.scan_ref.status, 'partial');
  const item = payload.items.find((entry) => entry.name === 'p02-versioned' && entry.version === '1.2.3');
  assert.ok(item);
  const [conflict] = item.conflicts;
  assert.equal(conflict.status, 'confirmed');
  const detail = await expand(item);
  const conflictDetail = detail.locator('section[data-conflict-status="confirmed"]');
  await conflictDetail.getByText('冲突已确认', { exact: true }).first().waitFor();
  for (const [side, label, version] of [
    [conflict.declaration, '声明版本', '1.2.3'], [conflict.lock, '锁文件版本', '2.3.4'],
  ]) {
    assert.equal(side.version, version);
    assert.equal(side.incomplete, false);
    await conflictDetail.getByText(label, { exact: false }).first().waitFor();
    await conflictDetail.getByText(version, { exact: false }).first().waitFor();
    const [evidence] = side.evidence;
    await verifyEvidence(conflictDetail, evidence, inputs.partial[evidence.file_path]);
  }
  await screenshot('partial-confirmed-conflict');
  try {
    await page.setViewportSize({ width: 390, height: 844 });
    await conflictDetail.scrollIntoViewIfNeeded();
    const widths = await panel().evaluate((element) => ({
      panelContent: element.scrollWidth,
      panelViewport: element.clientWidth,
      documentContent: document.documentElement.scrollWidth,
      documentViewport: document.documentElement.clientWidth,
    }));
    assert.ok(widths.panelContent <= widths.panelViewport + 1, JSON.stringify(widths));
    assert.ok(widths.documentContent <= widths.documentViewport + 1, JSON.stringify(widths));
    await screenshot('partial-conflict-mobile-390');
  } finally {
    await page.setViewportSize({ width: 1440, height: 900 });
  }
});

test('real truncated conflict displays incomplete and its gap instead of a confirmation', { timeout: 60_000 }, async () => {
  const id = await submit('truncated-conflict', 'partial');
  const payload = await openProjection(id);
  const item = payload.items.find((entry) => entry.name === 'p02-versioned' && entry.version === '1.2.3');
  assert.ok(item);
  const [conflict] = item.conflicts;
  assert.equal(conflict.status, 'incomplete');
  assert.equal(conflict.declaration.evidence_total, 9);
  assert.equal(conflict.declaration.evidence_returned, 8);
  assert.ok(conflict.gaps.includes('conflict_side_evidence_limit_exceeded'));
  const detail = await expand(item);
  const conflictDetail = detail.locator('section[data-conflict-status="incomplete"]');
  await conflictDetail.getByText(/不完整/).first().waitFor();
  await conflictDetail.getByText(/(?:截断|超出|部分|未返回|上限)/).first().waitFor();
  assert.equal(await detail.locator('section[data-conflict-status="confirmed"]').count(), 0);
  await screenshot('partial-incomplete-conflict');
});

test('empty completed scan displays a real empty dependency list', { timeout: 60_000 }, async () => {
  const id = await submit('empty', 'completed');
  const payload = await openProjection(id);
  assert.equal(payload.total, 0);
  await panel().getByText('本次扫描没有返回依赖', { exact: true }).waitFor();
  assert.equal(await rows().count(), 0);
  await screenshot('empty-dependencies');
});

test('real pagination appends server rows and reuses the same cursor after a failed GET', { timeout: 60_000 }, async () => {
  const id = await submit('paging', 'completed');
  const first = await openProjection(id);
  assert.equal(first.total, 108);
  assert.equal(first.returned, 50);
  await rows().nth(49).waitFor();
  const more = () => panel().getByRole('button', { name: '加载更多依赖', exact: true });
  const failNext = async (route) => {
    assert.equal(new URL(route.request().url()).searchParams.get('cursor'), first.next_cursor);
    await route.fulfill({ status: 503, json: { error: { code: 'test_only_unavailable', message: 'TEST_ONLY dependency paging fault' } } });
  };
  await page.route((target) => target.pathname === projection(id), failNext, { times: 1 });
  const failure = page.waitForResponse((response) => requestPath(response) === projection(id) && response.status() === 503);
  await more().click();
  await failure;
  assert.equal(await rows().count(), 50);
  const readMore = async (button, cursor, count) => {
    const received = page.waitForResponse((response) => requestPath(response) === projection(id));
    await button.click();
    const response = await received;
    assert.equal(response.status(), 200);
    assert.equal(new URL(response.url()).searchParams.get('cursor'), cursor);
    const pageData = await response.json();
    assert.deepEqual(pageData.scan_ref, first.scan_ref);
    await rows().nth(count - 1).waitFor();
    assert.equal(await rows().count(), count);
    return pageData;
  };
  const second = await readMore(panel().getByRole('button', { name: '重试加载更多', exact: true }), first.next_cursor, 100);
  const third = await readMore(more(), second.next_cursor, 108);
  assert.equal(third.next_cursor, null);
  const visibleIds = await rows().evaluateAll((elements) => elements.map((element) => element.dataset.dependencyResource));
  assert.deepEqual(visibleIds, [...first.items, ...second.items, ...third.items].map((item) => item.resource_id));
});

test('initial evidence failure is explicit and recovery uses the original live API', { timeout: 45_000 }, async () => {
  const id = scans.get('completed');
  await page.route((target) => target.pathname === projection(id), (route) =>
    route.fulfill({ status: 503, json: { error: { code: 'test_only_unavailable', message: 'TEST_ONLY evidence fetch fault' } } }), { times: 1 });
  const failure = page.waitForResponse((response) => requestPath(response) === projection(id) && response.status() === 503);
  await page.goto(origin + scanRoute(id, 'resources') + '&resource_view=dependencies');
  await failure;
  const retry = panel().getByRole('button', { name: '重新读取依赖证据', exact: true });
  await retry.waitFor();
  assert.equal(await rows().count(), 0);
  const recovery = page.waitForResponse((response) => requestPath(response) === projection(id));
  await retry.click();
  assert.equal((await recovery).status(), 200);
  await panel().getByText('p02-locked', { exact: true }).first().waitFor();
});

test('empty and failed remediation tasks do not block genuine evidence', { timeout: 60_000 }, async () => {
  const id = scans.get('completed');
  const assessments = `/api/v1/scans/${id}/assessments`;
  let selected;
  for (let retry = 0; retry < 30 && !selected; retry++) {
    selected = (await api(assessments)).items.find((item) => item.formal === true);
    if (!selected) await pause(100);
  }
  assert.ok(selected, 'The actual scan persisted a formal assessment for the task list');
  const tasks = `${assessments}/${selected.id}/remediation-tasks`;
  const empty = page.waitForResponse((response) => requestPath(response) === tasks);
  const evidence = await openProjection(id, 'remediation', `&assessment_id=${encodeURIComponent(selected.id)}`);
  const realTasks = await empty;
  assert.equal(realTasks.status(), 200);
  assert.deepEqual((await realTasks.json()).items, []);
  const target = evidence.items.find((item) => item.name === 'p02-locked');
  await getRow(target).waitFor();

  await page.route((candidate) => candidate.pathname === tasks, (route) =>
    route.fulfill({ status: 503, json: { error: { code: 'test_only_unavailable', message: 'TEST_ONLY remediation fault' } } }), { times: 1 });
  const failed = page.waitForResponse((response) => requestPath(response) === tasks && response.status() === 503);
  const stillLive = await openProjection(id, 'remediation', `&assessment_id=${encodeURIComponent(selected.id)}`);
  await failed;
  assert.deepEqual(stillLive, evidence);
  await page.getByText(/整改任务暂不可用/).first().waitFor();
  const detail = await expand(target);
  await verifyEvidence(detail, target.evidence[0], inputs.completed['uv.lock']);
  await screenshot('remediation-failure-evidence-available');
});
