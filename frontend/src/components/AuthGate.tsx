import { useEffect, useState } from 'react';
import { App } from '../App';
import { Landing } from '../pages/Landing';
import { Brand } from '../pages/Landing';
import { accountLoginUrl, readAccountSession, safeAccountNext, submitAccount, watchAccountBoundary, type AccountSession } from '../services/auth';
import { AuthPage } from '../pages/AuthPage';
import './Auth.css';

export function AuthGate() {
  const [session, setSession] = useState<AccountSession | null>(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setError('');
    void readAccountSession().then(value => { if (active) setSession(value); }).catch(e => { if (active) setError(e instanceof Error ? e.message : '账号状态读取失败。'); });
    return () => { active = false; };
  }, [attempt]);
  useEffect(() => watchAccountBoundary(() => window.location.reload()), []);
  const path = window.location.pathname;
  if (!session) return <main className="account-status"><Brand onClick={() => window.location.assign('/')} /><section role={error ? 'alert' : 'status'}><h1>{error ? '暂时无法连接工作台' : '正在确认账号状态'}</h1><p>{error || '确认后即可继续你的扫描与评估。'}</p>{error && <button onClick={() => setAttempt(v => v + 1)}>重新读取</button>}</section></main>;
  if (path === '/login' || path === '/register') return <AuthPage mode={path === '/register' ? 'register' : 'login'} session={session} />;
  if (path === '/') {
    return <Landing onEnter={() => window.location.assign(session.user ? '/app/new-scan?mode=api' : accountLoginUrl())}
      onDemo={() => window.location.assign(session.user ? '/app/new-scan?mode=api' : accountLoginUrl())}
      accountMode user={session.user} />;
  }
  if (!session.user) { window.location.replace(accountLoginUrl(path + window.location.search)); return null; }
  if (path.startsWith('/app/') && new URLSearchParams(window.location.search).get('mode') !== 'api') {
    window.location.replace(safeAccountNext(path + window.location.search)); return null;
  }
  return <App key={session.user.id} accountUser={session.user} onAccountLogout={async () => {
    await submitAccount('logout');
    window.location.replace('/login');
  }} />;
}
