/** Local account transport. Credentials and CSRF tokens are never browser-stored. */
export const accountAuthEnabled = import.meta.env.VITE_ACCOUNT_AUTH === '1';
export type AccountUser = { id: string; username: string };
export type AccountSession = { user: AccountUser | null; csrf_token: string };
export class AccountError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); this.name = 'AccountError'; }
}
let current: AccountSession | null = null;
let sessionFlight: Promise<AccountSession> | null = null;
const cacheOwnerKey = 'openguard:account-cache-owner:v1';
const boundaryKey = 'openguard:account-boundary:v1';
const cachePrefix = 'openguard:account-cache:v1:';
const protectedCache = (key: string) => key.startsWith('openguard:project-usage:1:') ||
  key.startsWith('openguard.report-references.v1:') || key.startsWith('openguard:scan:v2:') || key.startsWith('og-scroll:');
function keys(storage: Storage) { return Array.from({ length: storage.length }, (_, i) => storage.key(i)).filter((key): key is string => key !== null); }
/** Preserve exact pending identities per user, rather than clearing the origin. */
function selectAccountCaches(user: AccountUser | null) {
  try {
    const next = user?.id ?? '';
    for (const storage of [sessionStorage, localStorage]) {
      // localStorage is shared across tabs; sessionStorage has a per-tab owner.
      // Never label global values with this tab's previous account identity.
      const previous = storage.getItem(cacheOwnerKey) ?? '';
      if (next === previous) continue;
      for (const key of keys(storage).filter(protectedCache)) {
        const value = storage.getItem(key);
        if (previous && value !== null) storage.setItem(cachePrefix + encodeURIComponent(previous) + ':' + key, value);
        storage.removeItem(key);
      }
      if (next) {
        const prefix = cachePrefix + encodeURIComponent(next) + ':';
        for (const key of keys(storage).filter(key => key.startsWith(prefix))) {
          const value = storage.getItem(key), restored = key.slice(prefix.length);
          if (value !== null && protectedCache(restored)) storage.setItem(restored, value);
          storage.removeItem(key);
        }
      }
      next ? storage.setItem(cacheOwnerKey, next) : storage.removeItem(cacheOwnerKey);
    }
  } catch {
    // Server ownership and rotated CSRF still deny another account's requests.
    // Never weaken authentication or clear unrelated storage on quota/privacy errors.
  }
}
function validateSession(value: unknown): AccountSession {
  const v = value as AccountSession;
  if (!v || typeof v !== 'object' || typeof v.csrf_token !== 'string' || !/^[A-Za-z0-9_-]{20,256}$/.test(v.csrf_token) ||
    !(v.user === null || (typeof v.user === 'object' && typeof v.user.id === 'string' && /^[A-Za-z0-9_-]{1,160}$/.test(v.user.id) &&
    typeof v.user.username === 'string' && /^[A-Za-z0-9_-]{3,32}$/.test(v.user.username)))) throw new Error('账号会话响应不完整，请重新读取。');
  return { user: v.user === null ? null : { id: v.user.id, username: v.user.username }, csrf_token: v.csrf_token };
}
function acceptSession(value: unknown, broadcast = false) {
  const session = validateSession(value);
  selectAccountCaches(session.user);
  current = session;
  if (broadcast) try { localStorage.setItem(boundaryKey, crypto.randomUUID()); } catch { /* optional cross-tab notification */ }
  return session;
}
export function safeAccountNext(value: string | null | undefined): string {
  if (!value || !value.startsWith('/app/') || value.startsWith('//') || value.includes('\\') || /[\r\n]/.test(value)) return '/app/new-scan?mode=api';
  try {
    const url = new URL(value, 'http://local.invalid');
    if (url.origin !== 'http://local.invalid' || !url.pathname.startsWith('/app/')) return '/app/new-scan?mode=api';
    url.searchParams.set('mode', 'api');
    return url.pathname + url.search + url.hash;
  } catch { return '/app/new-scan?mode=api'; }
}
export function accountLoginUrl(next?: string) { return '/login?next=' + encodeURIComponent(safeAccountNext(next)); }
export function handleAccountResponse(status: number) {
  if (!accountAuthEnabled || status !== 401) return;
  current = null;
  selectAccountCaches(null);
  if (typeof window !== 'undefined' && window.location && !['/login', '/register'].includes(window.location.pathname)) {
    window.location.replace(accountLoginUrl(window.location.pathname + window.location.search));
  }
}
export function accountRequestOptions(options: RequestInit = {}): RequestInit {
  if (!accountAuthEnabled) return options;
  const method = (options.method ?? 'GET').toUpperCase();
  const headers = new Headers(options.headers);
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    if (!current?.user || !current.csrf_token) throw new AccountError(401, 'session_required', '请先登录，再明确提交本次操作。');
    headers.set('X-CSRF-Token', current.csrf_token);
  }
  return { ...options, headers, credentials: 'same-origin' };
}
export function readAccountSession(): Promise<AccountSession> {
  if (sessionFlight) return sessionFlight;
  sessionFlight = fetch('/api/v1/auth/session', { method: 'GET', credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } })
    .then(async response => {
      if (!response.ok) throw new AccountError(response.status, 'session_read_failed', '暂时无法读取账号状态，请重试。');
      return acceptSession(await response.json());
    }).finally(() => { sessionFlight = null; });
  return sessionFlight;
}
export async function submitAccount(operation: 'register' | 'login' | 'logout', username = '', password = ''): Promise<AccountSession> {
  if (!current) await readAccountSession();
  const response = await fetch('/api/v1/auth/' + operation, {
    method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-CSRF-Token': current!.csrf_token },
    body: JSON.stringify(operation === 'logout' ? {} : { username, password }),
  });
  const value = await response.json().catch(() => null);
  if (!response.ok) throw new AccountError(response.status, value?.error?.code ?? 'account_failed', value?.error?.message ?? '账号操作未完成，请检查后再重试。');
  return acceptSession(value, true);
}
export function watchAccountBoundary(onChange: () => void): () => void {
  const listener = (event: StorageEvent) => { if (event.key === boundaryKey) onChange(); };
  window.addEventListener('storage', listener);
  return () => window.removeEventListener('storage', listener);
}
