/** Real App and navigation with a closed, GET-only synthetic transport. */
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import { App } from '../../src/App';
import '../../src/styles/index.css';
import '../../src/styles/workspace.css';
import '../../src/pages/Overview.css';
import '../../src/pages/Report.css';
import '../../src/styles/product-ui.css';
import '../../src/styles/workbench-light.css';
import '../../src/styles/workspace-nav.css';

const ledger: { method: string; path: string }[] = [];
const unknown: string[] = [];
const limits = { total_call_limit: null, max_requests_per_minute: 10, concurrent: 1, request_timeout_seconds: 120, max_question_chars: 8000, project_max_question_chars: 2000 };
window.fetch = async (input, init) => {
  const url = new URL(String(input), location.origin);
  const method = init?.method ?? 'GET';
  ledger.push({ method, path: url.pathname + url.search });
  if (url.origin === location.origin && method === 'GET') {
    if (url.pathname === '/api/v1/scans') return Response.json({ schema_version: '1.0', items: [], next_cursor: null });
    if (url.pathname === '/api/v1/assistant/conversations') return Response.json({ schema_version: 'openguard-assistant/1', items: [], limits, has_more: false, cursor: null });
    if (/^\/api\/v1\/scans\/SYNTHETIC_[a-z]+$/.test(url.pathname)) return Response.json({ error: { code: 'synthetic_missing_scan', message: 'SYNTHETIC_TEST_ONLY missing scan' } }, { status: 404 });
  }
  unknown.push(`${method} ${url.href}`);
  throw new Error('SYNTHETIC_UNKNOWN_REQUEST');
};
history.replaceState({}, '', '/app/new-scan?mode=api');
sessionStorage.removeItem('og-projecting');
flushSync(() => createRoot(document.getElementById('root')!).render(<App />));
(window as any).__WORKSPACE_NAV__ = {
  ready: true,
  classification: 'SYNTHETIC_TEST_ONLY_REAL_APP_CLOSED_GET_ONLY_TRANSPORT',
  ledger,
  unknown,
  jump(path: string) {
    history.pushState({}, '', path);
    dispatchEvent(new PopStateEvent('popstate'));
  },
};
