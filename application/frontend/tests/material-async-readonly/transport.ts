import { FILE_BYTES, FILE_SHA256, SOURCE_DESCRIPTION, flatBinding, indexFor, reviewFor, type MaterialFixture } from './fixture';
import type { Result } from '../../src/services/p2';

export function check(value: unknown, message: string): asserts value { if (!value) throw Error(message); }
export function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(yes => { resolve = yes; });
  return { promise, resolve };
}
export type RequestRow = {
  sequence: number; utc: string; method: string; url: string; route: string | null;
  body: string; status: number | null; responseBody: string | null; reason: string | null;
};
export type Options = { holdReceipt?: boolean; switchableResult?: boolean; wrongMaterialVersion?: boolean };

/** Only the bottom fetch boundary is synthetic. NO native-fetch fallback and NO
 * upstream connection exists. This is not OS-level network/write isolation. */
export function closedTransport(f: MaterialFixture, options: Options = {}) {
  const ledger: RequestRow[] = [], unknown: RequestRow[] = [], nonGet: RequestRow[] = [];
  const origin = window.location.origin;
  const postEntered = deferred<void>(), postResponse = deferred<void>();
  const inflight = new Set<Promise<Response>>();
  let receiptReleased = false, materialPosts = 0, committed = false, exposedR2 = false;
  const baseOldBytes = JSON.stringify(f.base.result), peerOldBytes = JSON.stringify(f.peer);
  function reject(row: RequestRow, reason: string): never { row.reason = reason; unknown.push(row); throw Error('Closed TEST_ONLY transport: ' + reason); }
  function expect(row: RequestRow, value: unknown, reason: string): asserts value { if (!value) reject(row, reason); }
  function json(row: RequestRow, value: unknown, status = 200) {
    row.status = status; row.responseBody = JSON.stringify(value);
    return new Response(row.responseBody, { status, headers: { 'Content-Type': 'application/json' } });
  }
  async function dispatch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
    const raw = input instanceof Request ? input.url : String(input); let url: URL | undefined;
    try { url = new URL(raw, origin); } catch { /* refusal is independently logged below */ }
    const method = String(init.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
    const row: RequestRow = { sequence: ledger.length + 1, utc: new Date().toISOString(), method,
      url: url?.href ?? raw, route: null, body: typeof init.body === 'string' ? init.body : '',
      status: null, responseBody: null, reason: null };
    ledger.push(row); if (method !== 'GET') nonGet.push(row);
    expect(row, url && url.origin === origin && !url.username && !url.password && !url.hash, 'Foreign/malformed URL, credentials or fragment');
    expect(row, typeof input === 'string' || input instanceof URL, 'Unsupported Request input');
    expect(row, init.body === undefined || typeof init.body === 'string', 'Unsupported request body');
    expect(row, method !== 'GET' || row.body === '', 'GET unexpectedly carries a request body');
    const key = url.pathname + url.search;
    for (const bundle of [f.base, f.alternate]) {
      const prefix = `/api/v1/scans/${encodeURIComponent(bundle.assessment.scan_id)}/assessments/${encodeURIComponent(bundle.assessment.id)}/p2`;
      const suffix = `?assessment_version=${bundle.assessment.version}`;
      if (method === 'POST' && key === prefix + '/materials') {
        row.route = 'material-post'; postEntered.resolve();
        expect(row, bundle === f.base, 'Old file must never write into another Assessment');
        expect(row, ++materialPosts === 1, 'Duplicate or implicit Material retry');
        let body: Record<string, unknown>;
        try { body = JSON.parse(row.body); } catch { return reject(row, 'Invalid Material JSON'); }
        expect(row, body && typeof body === 'object' && !Array.isArray(body), 'Non-object Material body');
        expect(row, Object.keys(body).sort().join(',') === 'binding,completeness,content_base64,evidence_ids,expected_revision,filename,idempotency_key,parent_result_id,source_description,source_sha256,subject', 'Unexpected Material request fields');
        expect(row, flatBinding(body.binding, f.base.binding), 'Wrong nine-field Binding');
        expect(row, body.parent_result_id === f.base.result.result_id && body.expected_revision === 1, 'Original Result CAS/parent changed');
        expect(row, typeof body.idempotency_key === 'string' && /^[A-Za-z0-9_-]{8,100}$/.test(body.idempotency_key), 'Missing/invalid original idempotency key');
        expect(row, JSON.stringify(body.subject) === JSON.stringify(f.target.subject), 'Wrong exact resource/version');
        expect(row, JSON.stringify(body.evidence_ids) === JSON.stringify(f.target.evidence_ids), 'Wrong resource Evidence');
        expect(row, body.filename === 'LICENSE' && body.source_sha256 === FILE_SHA256 && body.source_description === SOURCE_DESCRIPTION && body.completeness === 'FULL_TEXT_CLAIMED', 'File/source metadata changed');
        let binary = ''; for (const byte of FILE_BYTES) binary += String.fromCharCode(byte);
        expect(row, body.content_base64 === btoa(binary), 'Raw File bytes were not consumed');
        if (options.holdReceipt) await postResponse.promise;
        committed = true;
        expect(row, JSON.stringify(f.base.result) === baseOldBytes && JSON.stringify(f.saved.resources[1]) === peerOldBytes, 'Synthetic old Result/peer mutated');
        const receipt = options.wrongMaterialVersion ? {
          ...structuredClone(f.receipt), material: { ...structuredClone(f.material), subject: { ...f.material.subject, version: '9.9.9' } },
        } : f.receipt;
        // Explicit negative response: 201 alone is not accepted. The REAL
        // validateSubmittedReceipt must reject the wrong Material version.
        return json(row, receipt, 201);
      }
      if (key === prefix + '/binding' && method === 'GET') { row.route = bundle === f.base ? 'base-binding' : 'alternate-binding'; return json(row, bundle.binding); }
      if (key === prefix + '/results' + suffix + '&offset=0' && method === 'GET') {
        row.route = bundle === f.base ? 'base-index' : 'alternate-index';
        const result = bundle === f.base ? committed ? f.saved : exposedR2 ? f.base.newer : f.base.result : bundle.result;
        return json(row, indexFor(result, bundle === f.base && !!options.switchableResult && !exposedR2 && !committed));
      }
      if (bundle === f.base && options.switchableResult && key === prefix + '/results' + suffix + '&offset=1' && method === 'GET') {
        row.route = 'concurrent-r2-head-page'; exposedR2 = true;
        return json(row, indexFor(f.base.newer));
      }
      const results: Result[] = bundle === f.base ? [f.base.result, committed ? f.saved : f.base.newer] : [bundle.result];
      for (const result of results) {
        const fixed = prefix + '/results/' + encodeURIComponent(result.result_id);
        if (key === fixed + suffix && method === 'GET') { row.route = 'fixed-result-r' + result.revision; return json(row, result); }
        if (key === fixed + '/preliminary-advice' + suffix && method === 'GET') {
          row.route = 'preliminary-503'; return json(row, { error: { code: 'synthetic_unavailable', message: 'SYNTHETIC_TEST_ONLY no official profile' } }, 503);
        }
        if (key === fixed + '/automatic-review' + suffix && method === 'GET') {
          row.route = 'automatic-review'; return json(row, reviewFor(bundle, result));
        }
      }
    }
    return reject(row, method === 'GET' ? 'Unknown exact GET/path/query' : 'Non-GET outside exact Material route');
  }
  const fetcher: typeof fetch = (input, init) => {
    const promise = dispatch(input, init); inflight.add(promise);
    void promise.then(() => inflight.delete(promise), () => inflight.delete(promise)); return promise;
  };
  return { fetch: fetcher, ledger, unknown, nonGet, postEntered: postEntered.promise,
    materialPosts: () => ledger.filter(row => row.route === 'material-post'),
    mark: () => ledger.length,
    nonGetsAfter: (cutoff: number) => nonGet.filter(row => row.sequence > cutoff),
    releaseReceipt() { check(!receiptReleased, 'Receipt released twice'); receiptReleased = true; postResponse.resolve(); },
    async drain() { if (!receiptReleased) { receiptReleased = true; postResponse.resolve(); } await Promise.allSettled([...inflight]); },
  };
}
