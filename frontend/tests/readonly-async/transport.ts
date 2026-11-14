/** STATIC_NOT_RUN. Closed synthetic transport fixtures, never live ASGI evidence. */
import type { Assessment, Usage } from '../../src/services/assessments';
import type { Binding } from '../../src/services/p2';

export function check(value: unknown, message: string): asserts value {
  if (!value) throw new Error(message);
}

export function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

export type Dispatch = {
  sequence: number; kind: 'fetch-dispatch'; method: string; origin: string; path: string;
  requestBody: string; requestBodySha256: string | null; utc: string;
  responseKind?: 'synthetic-json' | 'receipt-withheld-after-dispatch';
};
export type UnexpectedDispatch = {
  sequence: number; method: string; origin: string; path: string; reason: string; utc: string;
};
export type TimelineEvent = Dispatch | {
  sequence: number; kind: 'readonly-committed' | 'index-released'; utc: string;
};

export function fixture(label: string) {
  const token = label + '_' + crypto.randomUUID().replaceAll('-', '');
  const usage: Usage = {
    preset: 'unknown', commercial: null, modified: null, distributed: null,
    network_service: null, training: null, redistributed_assets: null, source_disclosure: null,
  };
  const changed: Usage = { ...usage, commercial: true, modified: false };
  const resourceIds = ['cmp_target_' + token, 'cmp_peer_' + token];
  const evidenceIds = ['evd_target_' + token, 'evd_peer_' + token];
  const a: Assessment = {
    id: 'asm_old_' + token, scan_id: 'scn_test_' + token, version: 1,
    project_name: 'SYNTHETIC_TEST_ONLY', generated_at: '2026-10-19T00:00:00Z',
    usage, summary: 'Synthetic frontend transport fixture', ai_status: 'disabled', ai_summary: null,
    dimensions: [], coverage_issues: [], resource_ids: resourceIds, finding_ids: [],
    evidence_ids: evidenceIds, rule_version: 'synthetic-rules/1', model_version: 'disabled',
    prompt_version: 'none', facts_hash: 'a'.repeat(64), obligations: [],
  };
  const next: Assessment = { ...a, id: 'asm_saved_' + token, version: 2, usage: changed };
  const binding: Binding = {
    scan_id: next.scan_id, assessment_id: next.id, assessment_version: next.version,
    registry_revision: 1, project_revision: 'SYNTHETIC_TEST_ONLY', facts_hash: next.facts_hash,
    usage_hash: 'b'.repeat(64), rule_version: next.rule_version, assessment_sha256: 'c'.repeat(64),
  };
  return {
    a, next, usage, changed, binding, requestId: 'test5_' + token,
    storageKey: 'openguard:project-usage:1:' + a.scan_id + ':' + a.id,
  };
}
export type Fixture = ReturnType<typeof fixture>;

/** Only window.fetch is replaced. No product function or React hook is mocked. */
export function installTransport(f: Fixture, holdResultPost = false) {
  const events: TimelineEvent[] = [];
  const unexpectedDispatches: UnexpectedDispatch[] = [];
  const readonlyCutoffs: number[] = [];
  const routeCounts = new Map<string, number>();
  const indexEntered = deferred<void>();
  const assessmentPostEntered = deferred<void>();
  const indexResponse = deferred<Response>();
  const resultPostEntered = deferred<void>();
  const resultPostReceipt = deferred<void>();
  const hashes: Promise<void>[] = [];
  let sequence = 0, indexDispatches = 0, released = false;
  const api = '/api/v1/scans/' + encodeURIComponent(f.a.scan_id);
  const parent = api + '/assessments/' + encodeURIComponent(f.next.id) + '/p2';
  const empty = { head_result_id: null, head_revision: 0, result_ids: [], has_more: false };

  function json(value: unknown, status = 200) {
    return new Response(JSON.stringify(value), {
      status, headers: { 'Content-Type': 'application/json' },
    });
  }
  function dispatches() { return events.filter((e): e is Dispatch => e.kind === 'fetch-dispatch'); }
  function resultPosts(after = -1) {
    return dispatches().filter(e => e.sequence > after && e.method === 'POST' && e.path === parent + '/results');
  }
  function assessmentPosts(after = -1) {
    return dispatches().filter(e => e.sequence > after && e.method === 'POST' && e.path === api + '/assessments');
  }
  function nonGets(after = -1) { return dispatches().filter(e => e.sequence > after && e.method !== 'GET'); }
  function posts(after = -1) { return dispatches().filter(e => e.sequence > after && e.method === 'POST'); }
  function unexpected(event: Dispatch, reason: string): never {
    // Independent ledger survives product catches of the rejection below.
    unexpectedDispatches.push({ sequence: event.sequence, method: event.method, origin: event.origin,
      path: event.path, reason, utc: event.utc });
    throw new Error('Unexpected transport dispatch blocked; no native fetch: ' + reason);
  }
  function expect(event: Dispatch, value: unknown, reason: string): asserts value {
    if (!value) unexpected(event, reason);
  }
  function parsedBody(event: Dispatch): Record<string, unknown> {
    let value: unknown;
    try { value = JSON.parse(event.requestBody); } catch { return unexpected(event, 'Request body is not JSON'); }
    expect(event, value && typeof value === 'object' && !Array.isArray(value), 'Request body is not an object');
    return value as Record<string, unknown>;
  }
  function readonlyChecks() {
    return readonlyCutoffs.map(after => ({ after_sequence: after, post_dispatches: posts(after).length,
      non_get_dispatches: nonGets(after).length }));
  }
  window.fetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const supportedInput = typeof input === 'string' || input instanceof URL;
    const rawUrl = input instanceof Request ? input.url : String(input);
    let url: URL | undefined;
    try { url = new URL(rawUrl, window.location.href); } catch { /* Record invalid dispatch before rejecting it. */ }
    const method = String(init.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
    const event: Dispatch = {
      sequence: ++sequence, kind: 'fetch-dispatch', method, origin: url?.origin ?? '<invalid-url>',
      path: url ? url.pathname + url.search : rawUrl,
      requestBody: typeof init.body === 'string' ? init.body : init.body === undefined ? '' : '<unsupported-body>',
      requestBodySha256: null, utc: new Date().toISOString(),
    };
    // Record before awaiting a hash, response, or deliberate rejection.
    events.push(event);
    hashes.push(crypto.subtle.digest('SHA-256', new TextEncoder().encode(event.requestBody))
      .then(bytes => { event.requestBodySha256 = Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2, '0')).join(''); }));
    expect(event, supportedInput, 'Unsupported Request input; no network fallback');
    expect(event, url, 'Malformed URL');
    expect(event, url.origin === window.location.origin && !url.username && !url.password && !url.hash,
      'Origin, credentials or fragment differs from exact test origin');
    expect(event, init.body === undefined || typeof init.body === 'string', 'Unsupported request body');
    const indexQuery = '?assessment_version=' + f.next.version + '&offset=0';
    const routes = [
      ['assessment-create', 'POST', api + '/assessments', ''],
      ['job', 'GET', api + '/assessments/jobs/' + encodeURIComponent(f.requestId), ''],
      ['assessment-read', 'GET', api + '/assessments/' + encodeURIComponent(f.next.id), ''],
      ['binding', 'GET', parent + '/binding', ''],
      ['index', 'GET', parent + '/results', indexQuery],
      ['result-create', 'POST', parent + '/results', ''],
    ];
    const route = routes.find(([, verb, path, query]) => method === verb && url!.pathname === path && url!.search === query);
    expect(event, route, 'Method/path/query is outside the exact closed route map');
    const routeName = route[0], count = (routeCounts.get(routeName) ?? 0) + 1;
    routeCounts.set(routeName, count);
    expect(event, count === 1, 'Extra dispatch to route ' + routeName);
    if (routeName === 'assessment-create') {
      const body = parsedBody(event);
      expect(event, Object.keys(body).sort().join(',') === 'request_id,usage', 'Unexpected Assessment body fields');
      expect(event, body.request_id === f.requestId, 'Seed request identity changed');
      expect(event, JSON.stringify(body.usage) === JSON.stringify(f.changed), 'Seed usage changed');
      assessmentPostEntered.resolve();
      event.responseKind = 'synthetic-json';
      return json({ request_id: f.requestId, status: 'pending' }, 202);
    }
    expect(event, method !== 'GET' || event.requestBody === '', 'GET carried an unexpected body');
    if (routeName === 'job') {
      event.responseKind = 'synthetic-json';
      return json({ request_id: f.requestId, status: 'succeeded', assessment_id: f.next.id });
    }
    if (routeName === 'assessment-read') {
      event.responseKind = 'synthetic-json'; return json(f.next);
    }
    if (routeName === 'binding') {
      event.responseKind = 'synthetic-json'; return json(f.binding);
    }
    if (routeName === 'index') {
      expect(event, ++indexDispatches === 1, 'Duplicate Index dispatch in one operation');
      event.responseKind = 'synthetic-json'; indexEntered.resolve();
      return indexResponse.promise;
    }
    if (routeName === 'result-create') {
      const body = parsedBody(event);
      expect(event, Object.keys(body).sort().join(',') === 'binding,expected_revision,idempotency_key,parent_result_id', 'Unexpected Result body fields');
      expect(event, body.idempotency_key === 'usage_' + f.requestId && body.expected_revision === 0 && body.parent_result_id === null,
        'Result key/CAS identity changed');
      expect(event, JSON.stringify(body.binding) === JSON.stringify(f.binding), 'Result Binding changed');
      // Count the attempted write even for a deficient candidate. This is NOT a
      // fake 409/405/201 and NOT proof of server refusal or persistence.
      event.responseKind = 'receipt-withheld-after-dispatch';
      resultPostEntered.resolve();
      if (holdResultPost) await resultPostReceipt.promise;
      throw new TypeError('SYNTHETIC_TEST_TRANSPORT_RECEIPT_WITHHELD');
    }
    return unexpected(event, 'Unimplemented closed route');
  };

  return {
    events, indexEntered: indexEntered.promise, assessmentPostEntered: assessmentPostEntered.promise,
    resultPostEntered: resultPostEntered.promise,
    resultPosts, assessmentPosts, nonGets, posts, unexpectedDispatches, readonlyChecks,
    assertClean() {
      check(unexpectedDispatches.length === 0, 'Unexpected/extra dispatch ledger is nonempty: ' + JSON.stringify(unexpectedDispatches));
      for (const value of readonlyChecks()) check(value.non_get_dispatches === 0,
        'A non-GET dispatch occurred after readonly commit: ' + JSON.stringify(value));
    },
    markReadOnly() {
      const event = { sequence: ++sequence, kind: 'readonly-committed' as const, utc: new Date().toISOString() };
      events.push(event); readonlyCutoffs.push(event.sequence); return event.sequence;
    },
    releaseIndex() {
      check(!released, 'Index gate released twice'); released = true;
      events.push({ sequence: ++sequence, kind: 'index-released', utc: new Date().toISOString() });
      indexResponse.resolve(json(empty));
    },
    latestSequence: () => sequence,
    finishHashes: () => Promise.all(hashes),
    releaseWithheldPost() { resultPostReceipt.resolve(); },
    dispose() {
      // Never reinstate native fetch while a deficient candidate might still
      // have a late continuation. All later calls remain closed/fixture-only.
      if (!released) indexResponse.resolve(json(empty));
      resultPostReceipt.resolve();
      sessionStorage.removeItem(f.storageKey);
    },
  };
}
