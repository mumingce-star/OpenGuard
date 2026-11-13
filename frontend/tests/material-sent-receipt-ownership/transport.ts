import { FILE_BYTES, FILE_SHA256, SOURCE_DESCRIPTION, flatBinding, indexFor, reviewFor, type Fixture, type View } from './fixture';
import type { Result } from '../../../p2-receiver-snapshot-20261020T140609Z/receiver/source/frontend/src/services/p2';

export function check(value: unknown, message: string): asserts value { if (!value) throw Error(message); }
export function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(yes => { resolve = yes; }); return { promise, resolve }; }
export type RequestRow = { sequence: number; utc: string; method: string; url: string; route: string | null; body: string; requestId: null; requestIdReason: string; status: number | null; responseBody: string | null; reason: string | null };

/** Bottom synthetic fetch only. No upstream, fallback, actual HTTP or OS/network
 * isolation claim. The independent unknown/nonGET ledgers survive product catch. */
export function closedTransport(f: Fixture, responseStatus: 201 | 409 = 201) {
  const ledger: RequestRow[] = [], nonGet: RequestRow[] = [], unknown: RequestRow[] = [];
  const entered = deferred<void>(), released = deferred<void>(), consumed = deferred<void>();
  const inflight = new Set<Promise<Response>>();
  let view: View = 'A', sent = false, releaseCount = 0, delivered = false;
  const origin = window.location.origin;
  const beforeOld = JSON.stringify(f.base.result), beforePeer = JSON.stringify(f.peer);
  function reject(row: RequestRow, reason: string): never { row.reason = reason; unknown.push(row); throw Error('Closed TEST_ONLY transport: ' + reason); }
  function expect(row: RequestRow, value: unknown, reason: string): asserts value { if (!value) reject(row, reason); }
  function json(row: RequestRow, value: unknown, status = 200) {
    row.status = status; row.responseBody = JSON.stringify(value);
    const response = new Response(row.responseBody, { status, headers: { 'Content-Type': 'application/json' } });
    if (row.route === 'material-post') {
      const original = response.json.bind(response);
      Object.defineProperty(response, 'json', { value: async () => { const body = await original(); delivered = true; consumed.resolve(); return body; } });
    }
    return response;
  }
  async function dispatch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
    const raw = input instanceof Request ? input.url : String(input); let url: URL | undefined;
    try { url = new URL(raw, origin); } catch { /* refusal logged below */ }
    const method = String(init.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
    const row: RequestRow = { sequence: ledger.length + 1, utc: new Date().toISOString(), method, url: url?.href ?? raw,
      route: null, body: typeof init.body === 'string' ? init.body : '', requestId: null,
      requestIdReason: 'No separate Material requestId exists in PendingWrite/WriteBody/current transport; original idempotency_key and PendingWrite reference are asserted separately.',
      status: null, responseBody: null, reason: null };
    ledger.push(row); if (method !== 'GET') nonGet.push(row);
    expect(row, !!url && url.origin === origin && !url.username && !url.password && !url.hash, 'Foreign or malformed origin/credentials/fragment');
    expect(row, typeof input === 'string' || input instanceof URL, 'Unsupported Request input');
    expect(row, init.body === undefined || typeof init.body === 'string', 'Unsupported body');
    expect(row, method !== 'GET' || row.body === '', 'GET body');
    const key = url.pathname + url.search;
    const aPrefix = `/api/v1/scans/${encodeURIComponent(f.base.assessment.scan_id)}/assessments/${encodeURIComponent(f.base.assessment.id)}/p2`;
    if (method === 'POST' && key === aPrefix + '/materials') {
      row.route = 'material-post'; expect(row, !sent, 'Duplicate or automatic Material replay'); sent = true;
      let body: Record<string, unknown>; try { body = JSON.parse(row.body); } catch { return reject(row, 'Invalid Material JSON'); }
      expect(row, body && typeof body === 'object' && !Array.isArray(body), 'Non-object request');
      expect(row, Object.keys(body).sort().join(',') === 'binding,completeness,content_base64,evidence_ids,expected_revision,filename,idempotency_key,parent_result_id,source_description,source_sha256,subject', 'Unexpected public fields');
      expect(row, flatBinding(body.binding, f.base.binding), 'Original complete Binding changed');
      expect(row, body.expected_revision === 1 && body.parent_result_id === f.base.result.result_id, 'Original CAS/parent changed');
      expect(row, typeof body.idempotency_key === 'string' && /^[A-Za-z0-9_-]{8,100}$/.test(body.idempotency_key), 'Invalid original idempotency key');
      expect(row, JSON.stringify(body.subject) === JSON.stringify(f.target.subject) && JSON.stringify(body.evidence_ids) === JSON.stringify(f.target.evidence_ids), 'Wrong resource/version/Evidence');
      expect(row, body.filename === 'LICENSE' && body.source_sha256 === FILE_SHA256 && body.source_description === SOURCE_DESCRIPTION && body.completeness === 'FULL_TEXT_CLAIMED', 'Material/source metadata changed');
      let binary = ''; for (const byte of FILE_BYTES) binary += String.fromCharCode(byte);
      expect(row, body.content_base64 === btoa(binary), 'Real materialBytes was not consumed');
      entered.resolve(); await released.promise;
      expect(row, JSON.stringify(f.base.result) === beforeOld && JSON.stringify(f.saved.resources[1]) === beforePeer, 'Old fixture object/peer mutated');
      return responseStatus === 201 ? json(row, f.receipt, 201) : json(row, { error: { code: 'synthetic_material_conflict', message: 'SYNTHETIC_TEST_ONLY conflict' } }, 409);
    }
    // Active A Binding can change only by explicit test arrangement followed by
    // an actual A->B->A component reload; changing unrelated props is not a reload.
    const activeA = view === 'A_OTHER_BINDING' ? f.bindingChanged : f.base;
    for (const bundle of [activeA, f.alternate]) {
      const prefix = `/api/v1/scans/${encodeURIComponent(bundle.assessment.scan_id)}/assessments/${encodeURIComponent(bundle.assessment.id)}/p2`;
      const suffix = `?assessment_version=${bundle.assessment.version}`;
      if (method === 'GET' && key === prefix + '/binding') { row.route = bundle === f.alternate ? 'B-binding' : 'A-binding'; return json(row, bundle.binding); }
      if (method === 'GET' && key === prefix + '/results' + suffix + '&offset=0') {
        row.route = bundle === f.alternate ? 'B-index' : 'A-index';
        const result = bundle === f.alternate ? bundle.result : view === 'A_OTHER_RESULT' ? f.concurrent : delivered && responseStatus === 201 && view !== 'A_OTHER_BINDING' ? f.saved : bundle.result;
        return json(row, indexFor(result));
      }
      const results: Result[] = bundle === f.alternate ? [bundle.result] : bundle === f.bindingChanged ? [bundle.result, bundle.newer] : [bundle.result, bundle.newer, f.saved, f.concurrent];
      expect(row, new Set(results.map(r => r.result_id)).size === results.length, 'Ambiguous fixed Result identity in synthetic route table');
      for (const result of results) {
        const fixed = prefix + '/results/' + encodeURIComponent(result.result_id);
        if (method === 'GET' && key === fixed + suffix) { row.route = 'fixed-result'; return json(row, result); }
        if (method === 'GET' && key === fixed + '/preliminary-advice' + suffix) { row.route = 'preliminary-503'; return json(row, { error: { code: 'synthetic_unavailable', message: 'SYNTHETIC_TEST_ONLY no live source' } }, 503); }
        if (method === 'GET' && key === fixed + '/automatic-review' + suffix) { row.route = 'automatic-review'; return json(row, reviewFor(bundle, result)); }
      }
    }
    return reject(row, method === 'GET' ? 'Unknown exact GET/path/query' : 'Non-GET outside exact original A Material route');
  }
  const fetcher: typeof fetch = (input, init) => { const p = dispatch(input, init); inflight.add(p); void p.then(() => inflight.delete(p), () => inflight.delete(p)); return p; };
  return { fetch: fetcher, ledger, nonGet, unknown, postEntered: entered.promise, responseConsumed: consumed.promise,
    materialPosts: () => ledger.filter(r => r.route === 'material-post'), mark: () => ledger.length,
    setView(next: View) { view = next; },
    releaseReceipt() { check(releaseCount++ === 0, 'Receipt released twice'); released.resolve(); },
    async drain() { if (!releaseCount) { releaseCount++; released.resolve(); } await Promise.allSettled([...inflight]); },
  };
}
