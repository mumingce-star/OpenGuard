import assert from 'node:assert/strict';
import test from 'node:test';
import { runtime } from './runtime.mjs';

const { validateDependencyEvidencePage, appendDependencyEvidencePage } = runtime().load('services/dependencyEvidence.ts');
const id = (prefix, number) => prefix + '_' + String(number).padStart(26, '0');
const scanId = id('scn', 1);
const digest = character => character.repeat(64);

function evidence(number, source = 'lock') {
  return {
    evidence_id: id('evd', number),
    source,
    file_path: source === 'manifest' ? 'service/pyproject.toml' : 'service/uv.lock',
    locator: source === 'manifest' ? 'service/pyproject.toml:project.dependencies[0]' : 'service/uv.lock:/package/0',
    source_sha256: digest('c'),
    producer: {
      type: 'parser',
      name: source === 'manifest' ? 'openguard-python-manifest-parser' : 'openguard.dependency-observations.lock',
      version: '1',
      config_digest: null,
      provider: null,
      model_id: null,
      prompt_schema_digest: null,
    },
    verification_status: 'pending',
    kind: 'manifest_field',
    start_line: null,
    end_line: null,
  };
}
function item(number) {
  return {
    resource_id: id('cmp', number),
    name: 'sample-' + number,
    version: '1.0.0',
    ecosystem: 'pypi',
    role_state: 'inferred',
    sources: ['lock'],
    evidence: [evidence(number)],
    evidence_total: 1,
    evidence_returned: 1,
    conflicts: [],
    conflicts_total: 0,
    conflicts_returned: 0,
    incomplete: false,
    gaps: [],
  };
}
function page(items = [item(2)], { limit = 50, total = items.length, nextCursor = null, status = 'completed', source = null } = {}) {
  return {
    schema_version: 'openguard-dependency-evidence/1',
    scan_ref: {
      scan_id: scanId,
      revision: null,
      facts_hash: digest('a'),
      input_hash: digest('b'),
      inventory_hash: digest('d'),
      status,
      registry_revision: 3,
    },
    source,
    limit,
    total,
    returned: items.length,
    next_cursor: nextCursor,
    coverage: 'unknown',
    incomplete: status === 'partial' || items.some(item => item.incomplete),
    items,
  };
}
function side(source, resourceNumber, version, total = 1) {
  const refs = Array.from({ length: Math.min(total, 8) }, (_, index) => evidence(20 * resourceNumber + index, source));
  return {
    resource_id: id('cmp', resourceNumber),
    version,
    evidence: refs,
    evidence_total: total,
    evidence_returned: refs.length,
    incomplete: refs.length < total,
  };
}
function withConflict(conflict) {
  const record = item(2);
  record.role_state = 'unknown';
  record.conflicts = [conflict];
  record.conflicts_total = 1;
  record.conflicts_returned = 1;
  record.gaps = [...conflict.gaps];
  record.incomplete = record.gaps.length > 0;
  return page([record]);
}

test('dependency evidence decodes actual wire metadata without promoting pending or inferred', () => {
  const input = page();
  const result = validateDependencyEvidencePage(input, scanId);
  assert.equal(result.scan_ref.facts_hash, digest('a'));
  assert.equal(result.scan_ref.input_hash, digest('b'));
  assert.equal(result.items[0].evidence[0].source_sha256, digest('c'));
  assert.equal(result.items[0].evidence[0].verification_status, 'pending');
  assert.equal(result.items[0].role_state, 'inferred');
  assert.equal(result.items[0].evidence[0].producer.name, 'openguard.dependency-observations.lock');
  assert.equal(result.coverage, 'unknown');
  const partial = validateDependencyEvidencePage(page([], { status: 'partial' }), scanId);
  assert.equal(partial.incomplete, true);
  assert.equal(partial.returned, 0);
  assert.equal(partial.next_cursor, null);
  assert.equal(validateDependencyEvidencePage(page([]), scanId).incomplete, false);
});

test('decoder rejects missing, extra, invalid, or misbound page and nested fields', () => {
  const malformed = [
    value => { value.schema_version = 'openguard-dependency-evidence/2'; },
    value => { value.scan_ref.scan_id = id('scn', 9); },
    value => { delete value.scan_ref.facts_hash; },
    value => { value.scan_ref.registry_revision = 0; },
    value => { value.scan_ref.status = 'running'; },
    value => { value.limit = 101; },
    value => { value.returned = 19; },
    value => { value.total = 3; },
    value => { value.source = 'lock'; },
    value => { value.incomplete = true; },
    value => { value.next_cursor = 'inventedCursor'; },
    value => { value.items[0].evidence[0].claims_verified = true; },
    value => { value.items[0].evidence[0].source_sha256 = 'not-a-file-hash'; },
    value => { value.items[0].evidence[0].producer.config_digest = { algorithm: 'sha512', value: digest('c') }; },
    value => { value.items[0].evidence[0].producer.provider = 'incorrect-ai-provider'; },
    value => { value.items[0].evidence[0].file_path = '../private/uv.lock'; },
    value => { value.items[0].evidence[0].verification_status = 'VERIFIED'; },
    value => { value.items[0].evidence[0].end_line = 5; },
    value => { value.items[0].role_state = 'observed'; },
    value => { value.items[0].sources.push('manifest'); },
  ];
  for (const modify of malformed) {
    const fixture = page();
    modify(fixture);
    assert.throws(() => validateDependencyEvidencePage(fixture, scanId), /依赖证据响应/);
  }
  assert.throws(() => validateDependencyEvidencePage(page([item(2), item(1)]), scanId));
  assert.throws(() => validateDependencyEvidencePage(page([item(1), item(1)]), scanId));
});

test('conflict decoder accepts complete, missing, truncated and ambiguous evidence with matching overall status', () => {
  const complete = { code: 'lock_version_conflict', status: 'confirmed',
    declaration: side('manifest', 2, '1.0.0'), lock: side('lock', 3, '2.0.0'), gaps: [] };
  assert.equal(validateDependencyEvidencePage(withConflict(complete), scanId).items[0].conflicts[0].status, 'confirmed');
  const truncated = { ...complete, status: 'incomplete', lock: side('lock', 3, '2.0.0', 9),
    gaps: ['conflict_side_evidence_limit_exceeded'] };
  const conflict = validateDependencyEvidencePage(withConflict(truncated), scanId).items[0].conflicts[0];
  assert.equal(conflict.status, 'incomplete');
  assert.equal(conflict.lock.evidence_returned, 8);
  assert.equal(conflict.lock.evidence_total, 9);
  assert.throws(() => validateDependencyEvidencePage(withConflict({ ...truncated, status: 'confirmed' }), scanId));
  assert.throws(() => validateDependencyEvidencePage(withConflict({ ...truncated, gaps: [] }), scanId));
  assert.throws(() => validateDependencyEvidencePage(withConflict({ ...complete, lock: null }), scanId));
  assert.throws(() => validateDependencyEvidencePage(withConflict({ ...complete, lock: side('lock', 3, '1.0.0') }), scanId));
  const ambiguous = { ...truncated, status: 'ambiguous', declaration: null,
    gaps: ['conflict_ambiguous', 'conflict_side_evidence_limit_exceeded', 'declaration_side_unavailable'] };
  assert.equal(validateDependencyEvidencePage(withConflict(ambiguous), scanId).items[0].conflicts[0].status, 'ambiguous');
});

test('repeated Evidence IDs preserve exactly one identity across rows and conflict sides', () => {
  function linkedPage() {
    const conflict = { code: 'lock_version_conflict', status: 'confirmed',
      declaration: side('manifest', 2, '1.0.0'), lock: side('lock', 3, '2.0.0'), gaps: [] };
    const raw = withConflict(conflict);
    const ref = structuredClone(conflict.declaration.evidence[0]);
    ref.producer = Object.fromEntries(Object.entries(ref.producer).reverse());
    raw.items[0].sources = ['manifest'];
    raw.items[0].evidence = [ref];
    return raw;
  }
  assert.doesNotThrow(() => validateDependencyEvidencePage(linkedPage(), scanId));
  for (const alter of [
    ref => { ref.file_path = 'other/pyproject.toml'; },
    ref => { ref.source_sha256 = digest('e'); },
    ref => { ref.verification_status = 'verified'; },
    ref => { ref.producer.version = '2'; },
  ]) {
    const raw = linkedPage();
    alter(raw.items[0].evidence[0]);
    assert.throws(() => validateDependencyEvidencePage(raw, scanId), /依赖证据响应/);
  }
  const first = item(1), second = item(2);
  second.evidence = [structuredClone(first.evidence[0])];
  second.evidence[0].source_sha256 = digest('e');
  assert.throws(() => validateDependencyEvidencePage(page([first, second]), scanId));
});

test('conflict resource versions bind when present, while off-page sides remain readable', () => {
  const conflict = { code: 'lock_version_conflict', status: 'confirmed',
    declaration: side('manifest', 2, '1.0.0'), lock: side('lock', 3, '2.0.0'), gaps: [] };
  const raw = withConflict(conflict);
  assert.doesNotThrow(() => validateDependencyEvidencePage(raw, scanId));
  const lockRow = { ...item(3), version: '2.0.0' };
  const linked = page([...raw.items, lockRow]);
  assert.doesNotThrow(() => validateDependencyEvidencePage(linked, scanId));
  lockRow.version = '2.0.1';
  assert.throws(() => validateDependencyEvidencePage(linked, scanId), /依赖证据响应/);
  const first = page(raw.items, { limit: 1, total: 2, nextCursor: 'cursor_1' });
  const firstFeed = appendDependencyEvidencePage(null, validateDependencyEvidencePage(first, scanId, { limit: 1 }));
  const second = page([lockRow], { limit: 1, total: 2 });
  const decoded = validateDependencyEvidencePage(second, scanId, { limit: 1, cursor: 'cursor_1' });
  assert.throws(() => appendDependencyEvidencePage(firstFeed, decoded, 'cursor_1'));
});

test('incomplete evidence keeps missing hash and provenance gaps visible', () => {
  const missing = item(4);
  missing.evidence[0].source_sha256 = null;
  missing.evidence[0].locator = null;
  missing.evidence[0].file_path = null;
  missing.role_state = 'unknown';
  missing.incomplete = true;
  missing.gaps = ['file_path_unavailable', 'role_evidence_unavailable', 'source_sha256_missing'];
  const parsed = validateDependencyEvidencePage(page([missing]), scanId);
  assert.equal(parsed.incomplete, true);
  assert.equal(parsed.items[0].evidence[0].source_sha256, null);
  assert.ok(parsed.items[0].gaps.includes('source_sha256_missing'));
});

test('cursor pages accumulate only on a fixed snapshot, without stale rows or repeated cursors', () => {
  const first = page([item(1)], { limit: 1, total: 4, nextCursor: 'cursor_1' });
  const second = page([item(2)], { limit: 1, total: 4, nextCursor: 'cursor_2' });
  const feed = appendDependencyEvidencePage(null, validateDependencyEvidencePage(first, scanId, { limit: 1 }));
  const decoded = validateDependencyEvidencePage(second, scanId, { limit: 1, cursor: 'cursor_1' });
  const expanded = appendDependencyEvidencePage(feed, decoded, 'cursor_1');
  assert.equal(expanded.items.map(entry => entry.name).join(','), 'sample-1,sample-2');
  assert.equal(feed.items.length, 1);
  assert.equal(expanded.next_cursor, 'cursor_2');
  assert.equal(Object.hasOwn(expanded, 'returned'), false);
  for (const key of ['scan_id', 'revision', 'facts_hash', 'input_hash', 'inventory_hash', 'status', 'registry_revision']) {
    const changed = structuredClone(decoded);
    changed.scan_ref[key] = key === 'registry_revision' ? 4 : 'other-snapshot';
    assert.throws(() => appendDependencyEvidencePage(feed, changed, 'cursor_1'));
  }
  for (const inconsistent of [
    { ...decoded, source: 'lock' },
    { ...decoded, limit: 2 },
    { ...decoded, total: 5 },
    { ...decoded, items: [item(1)] },
    { ...decoded, next_cursor: null },
  ]) assert.throws(() => appendDependencyEvidencePage(feed, inconsistent, 'cursor_1'));
  assert.throws(() => appendDependencyEvidencePage(feed, decoded, 'wrong_cursor'));
  const conflictingRef = item(2);
  conflictingRef.evidence = [structuredClone(first.items[0].evidence[0])];
  conflictingRef.evidence[0].verification_status = 'verified';
  assert.throws(() => appendDependencyEvidencePage(feed, { ...decoded, items: [conflictingRef] }, 'cursor_1'));
  assert.throws(() => appendDependencyEvidencePage(expanded, {
    ...decoded, items: [item(3)], next_cursor: 'cursor_1',
  }, 'cursor_2'));
  const penultimate = appendDependencyEvidencePage(expanded, {
    ...decoded, items: [item(3)], next_cursor: 'cursor_3',
  }, 'cursor_2');
  const all = appendDependencyEvidencePage(penultimate, {
    ...decoded, items: [item(4)], next_cursor: null,
  }, 'cursor_3');
  assert.equal(all.items.length, 4);
  assert.equal(all.total, 4);
});

test('reader uses authenticated no-store GET and preserves API cursor errors', async () => {
  const rt = runtime({ VITE_ACCOUNT_AUTH: '1' });
  rt.shared.Headers = Headers;
  const { readDependencyEvidencePage } = rt.load('services/dependencyEvidence.ts');
  const fetchCalls = [];
  rt.setFetch(async (url, init) => {
    fetchCalls.push([url, init.method, init.credentials, init.cache]);
    return Response.json(page([item(2)], { limit: 1, total: 2, source: 'lock' }));
  });
  const result = await readDependencyEvidencePage(scanId, { source: 'lock', limit: 1, cursor: 'cursor_1' });
  assert.equal(result.items[0].name, 'sample-2');
  assert.deepEqual(fetchCalls, [[
    '/api/v1/scans/' + scanId + '/dependency-evidence?limit=1&source=lock&cursor=cursor_1',
    'GET', 'same-origin', 'no-store',
  ]]);
  rt.setFetch(async () => Response.json({ error: {
    code: 'dependency_evidence_cursor_stale', message: 'Stale', details: { reason: 'cursor_stale' },
  } }, { status: 409 }));
  await assert.rejects(readDependencyEvidencePage(scanId),
    error => error.status === 409 && error.code === 'dependency_evidence_cursor_stale');
});

test('reader discards a response arriving after its scan request was aborted', async () => {
  const rt = runtime(), { readDependencyEvidencePage } = rt.load('services/dependencyEvidence.ts');
  const controller = new AbortController();
  rt.setFetch(async () => {
    controller.abort();
    return Response.json(page());
  });
  await assert.rejects(readDependencyEvidencePage(scanId, { signal: controller.signal }),
    error => error.name === 'AbortError');
});
