import { useEffect, useRef, useState } from 'react';
import { Brand } from './Landing';
import { AuthIllustration } from '../components/AuthIllustration';
import { accountPasswordError } from '../services/accountPassword';
import { safeAccountNext, submitAccount, type AccountSession } from '../services/auth';

export function AuthPage({ mode, session }: { mode: 'register' | 'login'; session: AccountSession }) {
  const register = mode === 'register';
  const [username, setUsername] = useState(''), [password, setPassword] = useState(''), [confirmation, setConfirmation] = useState('');
  const [visible, setVisible] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const lock = useRef(false), alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const next = safeAccountNext(new URLSearchParams(window.location.search).get('next'));
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (lock.current) return;
    setError('');
    if (!/^[A-Za-z0-9_-]{3,32}$/.test(username)) { setError('用户名请使用 3—32 位英文字母、数字、下划线或短横线。'); return; }
    const passwordError = accountPasswordError(password, register);
    if (passwordError) { setError(passwordError); return; }
    if (register && password !== confirmation) { setError('两次输入的密码不一致，请重新确认。'); return; }
    lock.current = true; setBusy(true);
    try {
      const result = await submitAccount(mode, username, password);
      if (!result.user) throw new Error('尚未取得已登录会话，请重新登录。');
      window.location.replace(next);
    } catch (e) {
      if (alive.current) setError(e instanceof Error ? e.message : '操作未完成，请稍后重试。');
    } finally { lock.current = false; if (alive.current) setBusy(false); }
  }
  if (session.user) return <main className="account-status"><Brand onClick={() => window.location.assign('/')} /><section><h1>你已登录，{session.user.username}</h1><p>继续查看自己的扫描记录，或开始一次新的项目评估。</p><div className="account-status-actions"><a className="account-primary" href={next}>进入工作台</a><button type="button" className="account-secondary" onClick={async () => { try { await submitAccount('logout'); window.location.replace('/login'); } catch (e) { setError(e instanceof Error ? e.message : '退出失败，请重试。'); } }}>退出当前账号</button></div>{error && <p className="account-error" role="alert">{error}</p>}</section></main>;
  return <main className="account-shell">
    <section className="account-layout" aria-label={register ? '账号注册' : '账号登录'}>
      <header className="account-col-top">
        <Brand onClick={() => window.location.assign('/')} />
        <a className="account-back-link" href="/">← 返回首页</a>
      </header>

      <div className="account-form-stage">
        <section className={`account-panel${register ? ' is-register' : ''}`} aria-labelledby="account-title">
          <div className="account-tabs" role="navigation" aria-label="账号操作">
            <a href={'/login?next=' + encodeURIComponent(next)} aria-current={!register ? 'page' : undefined}>登录</a>
            <a href={'/register?next=' + encodeURIComponent(next)} aria-current={register ? 'page' : undefined}>注册</a>
          </div>
          <div className="account-panel-head">
            <h2 id="account-title">{register ? '创建工作台账号' : '欢迎回到 OpenGuard'}</h2>
            <p className="account-lead">{register ? '创建本地独立账号，按项目保存扫描记录与历史评估版本。' : '输入账号凭据，继续上一次的项目扫描与合规评估。'}</p>
          </div>
          <form onSubmit={event => void submit(event)} noValidate>
            <fieldset disabled={busy}>
              <div className="account-field">
                <label htmlFor="account-username">用户名</label>
                <div className="account-input-box">
                  <svg className="account-field-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" /></svg>
                  <input id="account-username" name="username" autoComplete="username" autoCapitalize="none" spellCheck={false} value={username} onChange={e => setUsername(e.target.value)} maxLength={32} placeholder="例如 openguard_demo" aria-describedby={register ? 'username-help' : undefined} />
                </div>
                {register && <small id="username-help">3—32 位英文字母、数字、下划线或短横线</small>}
              </div>
              <div className="account-field">
                <label htmlFor="account-password">密码</label>
                <div className="account-input-box account-password">
                  <svg className="account-field-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></svg>
                  <input id="account-password" name="password" type={visible ? 'text' : 'password'} autoComplete={register ? 'new-password' : 'current-password'} value={password} onChange={e => setPassword(e.target.value)} maxLength={register ? 48 : 256} placeholder={register ? '8—24 个字符，包含字母和数字' : '请输入注册时设置的密码'} aria-describedby="password-help" />
                  <button type="button" onClick={() => setVisible(v => !v)} aria-label={visible ? '隐藏密码' : '显示密码'} aria-pressed={visible}>{visible ? '隐藏' : '显示'}</button>
                </div>
                <small id="password-help">{register ? '8—24 个字符，必须同时包含英文字母和数字，可包含符号' : '使用注册时设置的密码；已有账号的原密码仍可登录'}</small>
              </div>
              {register && (
                <div className="account-field">
                  <label htmlFor="account-confirmation">确认密码</label>
                  <div className="account-input-box">
                    <svg className="account-field-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /><path d="m9 12 2 2 4-4" /></svg>
                    <input id="account-confirmation" name="password-confirmation" type={visible ? 'text' : 'password'} autoComplete="new-password" value={confirmation} onChange={e => setConfirmation(e.target.value)} maxLength={48} placeholder="再次输入密码" />
                  </div>
                </div>
              )}
              {error && <div className="account-error" role="alert">{error}</div>}
              <button className="account-primary" type="submit">{busy ? (register ? '正在创建账号…' : '正在登录…') : (register ? '注册并进入工作台' : '登录工作台')}</button>
            </fieldset>
          </form>
          <p className="account-footnote">仅保存于本机工作台，与旧录制入口和已有数据相互独立。</p>
        </section>
      </div>

      <footer className="account-col-bottom">
        <span>开源合规信息整理与辅助判断</span>
        <span>不替代专业法律审核</span>
      </footer>
    </section>

    <aside className="account-showcase" aria-label="OpenGuard 合规基线架构概览">
      <div className="account-col-top account-showcase-top">
        <span className="account-showcase-kicker">OPEN-SOURCE COMPLIANCE · WORKBENCH</span>
        <span className="account-status-pill"><span className="account-dot" aria-hidden="true" />本机工作台已就绪</span>
      </div>

      <div className="account-showcase-stage">
        <div className="account-showcase-inner">
          <div className="account-illustration-frame">
            <AuthIllustration register={register} />
          </div>
          <div className="account-showcase-copy">
            <h1>依赖来源、用途边界与原文证据，<br />同一条基线可复核。</h1>
            <p>每次扫描自动锚定精确依赖版本与许可证原文快照；待核对项与变更轨迹显式保留，未知情况绝不默认放行。</p>
          </div>
          <dl className="account-showcase-metrics">
            <div>
              <dt>SHA-256</dt>
              <dd>逐文件原文锚定</dd>
            </div>
            <div>
              <dt>r1 → r2</dt>
              <dd>评估轨迹不覆盖</dd>
            </div>
            <div>
              <dt>账号空间</dt>
              <dd>历史记录独立隔离</dd>
            </div>
          </dl>
        </div>
      </div>

      <footer className="account-col-bottom account-showcase-bottom">
        <span>OpenGuard · 证据先行，结论可溯</span>
        <span className="account-mono">LOCAL-FIRST SESSION</span>
      </footer>
    </aside>
  </main>;
}
