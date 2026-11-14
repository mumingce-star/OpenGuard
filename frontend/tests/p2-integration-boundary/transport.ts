import { reviewFor, type IntegrationFixture } from './fixture';

export function check(value: unknown, message: string): asserts value {
  if (!value) throw Error(message);
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(yes => { resolve = yes; });
  return { promise, resolve };
}
function sameFlat(value: unknown, expected: object) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const a = value as Record<string, unknown>, b = expected as Record<string, unknown>;
  return Object.keys(a).length === Object.keys(b).length && Object.keys(b).every(k => Object.prototype.hasOwnProperty.call(a, k) && a[k] === b[k]);
}
export type RequestRow = {
  sequence: number; utc: string; method: string; url: string;
  route: string | null; body: string; status: number | null;
  responseBody: string | null; reason: string | null;
};
export type Options = { automatic503?: boolean; holdOldAutomatic?: boolean };

/** Closed bottom transport only. No service function, hook or component mocked.
 * This JS boundary is not OS isolation; it requires a separately approved runner.
 * There is NO native fetch fallback and NO upstream implementation. */
export function closedTransport(f: IntegrationFixture, options: Options = {}) {
  const ledger: RequestRow[] = [], unknown: RequestRow[] = [], nonGet: RequestRow[] = [];
  const origin = window.location.origin;
  const api = `/api/v1/scans/${encodeURIComponent(f.base.scan.id)}`;
  const oldAssessment = api + '/assessments/' + encodeURIComponent(f.base.assessment.id);
  const oldP2 = oldAssessment + '/p2';
  const nextAssessment = api + '/assessments/' + encodeURIComponent(f.next.id);
  const nextP2 = nextAssessment + '/p2';
  const suffix = `?assessment_version=${f.base.assessment.version}`;
  const nextSuffix = `?assessment_version=${f.next.version}&offset=0`;
  const recoveryEntered = deferred<void>(), recoveryResponse = deferred<void>();
  const mainEntered = deferred<void>(), mainResponse = deferred<void>();
  const oldAutomaticEntered = deferred<void>(), oldAutomaticResponse = deferred<void>();
  const resultPostEntered = deferred<void>();
  let recoveryReleased = false, mainReleased = false, automaticReleased = false;
  let holdMain = false, recoveryIndexCount = 0, seedPosts = 0;
  const inflight = new Set<Promise<Response>>();
  const mainIndex = { head_result_id: f.base.newer.result_id, head_revision: 2,
    result_ids: [f.base.newer.result_id, f.base.result.result_id], has_more: false };
  function bad(row: RequestRow, reason: string): never {
    row.reason = reason; unknown.push(row);
    throw Error('SYNTHETIC_TEST_ONLY transport refused: ' + reason);
  }
  function expect(row: RequestRow, value: unknown, reason: string): asserts value {
    if (!value) bad(row, reason);
  }
  function objectBody(row: RequestRow): Record<string, unknown> {
    let value: unknown;
    try { value = JSON.parse(row.body); } catch { return bad(row, 'Invalid JSON request body'); }
    expect(row, value && typeof value === 'object' && !Array.isArray(value), 'Non-object request body');
    return value as Record<string, unknown>;
  }
  function json(row: RequestRow, value: unknown, status = 200) {
    row.status = status; row.responseBody = JSON.stringify(value);
    return new Response(row.responseBody, { status, headers: { 'Content-Type': 'application/json' } });
  }
  async function dispatch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
    let url: URL | undefined;
    const rawUrl = input instanceof Request ? input.url : String(input);
    try { url = new URL(rawUrl, origin); } catch { /* ledger before refusing */ }
    const method = String(init.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
    const row: RequestRow = { sequence: ledger.length + 1, utc: new Date().toISOString(),
      method, url: url?.href ?? rawUrl, route: null, body: typeof init.body === 'string' ? init.body : '',
      status: null, responseBody: null, reason: null };
    ledger.push(row); if (method !== 'GET') nonGet.push(row);
    expect(row, url, 'Malformed URL');
    expect(row, typeof input === 'string' || input instanceof URL, 'Unsupported Request input');
    expect(row, url.origin === origin && !url.username && !url.password && !url.hash, 'Foreign origin/credentials/fragment');
    expect(row, init.body === undefined || typeof init.body === 'string', 'Unsupported request body');
    const key = url.pathname + url.search;
    if (method === 'POST' && key === api + '/assessments') {
      row.route = 'seed-assessment-post';
      expect(row, ++seedPosts === 1, 'Implicit duplicate Assessment POST');
      const body = objectBody(row);
      expect(row, body.request_id === f.requestId && sameFlat(body.usage, f.changed), 'Original Assessment request identity changed');
      return json(row, { request_id: f.requestId, status: 'pending' }, 202);
    }
    if (method === 'POST' && key === nextP2 + '/results') {
      row.route = 'recovery-result-post';
      const body = objectBody(row);
      expect(row, Object.keys(body).sort().join(',') === 'binding,expected_revision,idempotency_key,parent_result_id', 'Unexpected Result request fields');
      expect(row, body.idempotency_key === 'usage_' + f.requestId && body.parent_result_id === null && body.expected_revision === 0, 'Original Result key/CAS changed');
      expect(row, sameFlat(body.binding, f.nextBinding), 'Recovered exact Binding changed');
      resultPostEntered.resolve();
      // Count an ACTUAL front-end fetch invocation. No invented HTTP receipt:
      // no synthetic 201/409/405 is used to pretend the request was not sent.
      row.reason = 'SYNTHETIC_RECEIPT_WITHHELD_AFTER_DISPATCH';
      throw new TypeError(row.reason);
    }
    expect(row, method === 'GET', 'Non-GET outside the two explicit synthetic recovery routes');
    expect(row, row.body === '', 'GET with body');
    if (key === api + '/assessments/jobs/' + encodeURIComponent(f.requestId)) {
      row.route = 'recovery-job';
      return json(row, { request_id: f.requestId, status: 'succeeded', assessment_id: f.next.id });
    }
    if (key === nextAssessment) { row.route = 'recovery-assessment'; return json(row, f.next); }
    if (key === nextP2 + '/binding') { row.route = 'recovery-binding'; return json(row, f.nextBinding); }
    if (key === nextP2 + '/results' + nextSuffix) {
      row.route = 'recovery-index';
      expect(row, ++recoveryIndexCount === 1, 'Recovery Index repeated');
      recoveryEntered.resolve(); await recoveryResponse.promise;
      return json(row, { head_result_id: null, head_revision: 0, result_ids: [], has_more: false });
    }
    if (key === oldP2 + '/binding') { row.route = 'main-binding'; return json(row, f.base.binding); }
    if (key === oldP2 + '/results' + suffix + '&offset=0') {
      row.route = 'main-index';
      if (holdMain) { holdMain = false; mainEntered.resolve(); await mainResponse.promise; }
      return json(row, mainIndex);
    }
    for (const [isNew, value] of [[false, f.base.result], [true, f.base.newer]] as const) {
      const fixed = oldP2 + '/results/' + encodeURIComponent(value.result_id);
      if (key === fixed + suffix) { row.route = isNew ? 'fixed-r2' : 'fixed-r1'; return json(row, value); }
      if (key === fixed + '/preliminary-advice' + suffix) {
        row.route = 'preliminary'; return json(row, { error: { code: 'synthetic_unavailable', message: 'SYNTHETIC_TEST_ONLY no source profile' } }, 503);
      }
      if (key === fixed + '/automatic-review' + suffix) {
        row.route = isNew ? 'automatic-r2' : 'automatic-r1';
        if (!isNew && options.holdOldAutomatic) { oldAutomaticEntered.resolve(); await oldAutomaticResponse.promise; }
        const signal = init.signal;
        if (signal?.aborted) { row.reason = 'ABORTED_BEFORE_SYNTHETIC_RESPONSE'; throw new DOMException(row.reason, 'AbortError'); }
        return options.automatic503 ? json(row, { error: { code: 'synthetic_projection_unavailable', message: 'SYNTHETIC_TEST_ONLY derived 503' } }, 503)
          : json(row, reviewFor(f.base, isNew));
      }
    }
    return bad(row, 'Unknown exact method/path/query');
  }
  const fetcher: typeof fetch = (input, init) => {
    const promise = dispatch(input, init); inflight.add(promise);
    // A rejection handler here tracks lifetime, never changes the returned promise.
    void promise.then(() => inflight.delete(promise), () => inflight.delete(promise));
    return promise;
  };
  return {
    fetch: fetcher, ledger, unknown, nonGet,
    recoveryEntered: recoveryEntered.promise, mainEntered: mainEntered.promise,
    oldAutomaticEntered: oldAutomaticEntered.promise, resultPostEntered: resultPostEntered.promise,
    armMainIndexHold() { check(!holdMain && !mainReleased, 'Main hold rearmed'); holdMain = true; },
    releaseMain() { check(!mainReleased, 'Main Index released twice'); mainReleased = true; mainResponse.resolve(); },
    releaseRecovery() { check(!recoveryReleased, 'Recovery Index released twice'); recoveryReleased = true; recoveryResponse.resolve(); },
    releaseOldAutomatic() { check(!automaticReleased, 'Old projection released twice'); automaticReleased = true; oldAutomaticResponse.resolve(); },
    mark() { return ledger.length; },
    resultPosts: () => ledger.filter(row => row.route === 'recovery-result-post'),
    nonGetsAfter: (cutoff: number) => nonGet.filter(row => row.sequence > cutoff),
    async drainAfterUnmount() {
      if (!mainReleased) { mainReleased = true; mainResponse.resolve(); }
      if (!recoveryReleased) { recoveryReleased = true; recoveryResponse.resolve(); }
      if (!automaticReleased) { automaticReleased = true; oldAutomaticResponse.resolve(); }
      await Promise.allSettled([...inflight]);
    },
  };
}
