import { useEffect, useRef, useState } from 'react';
import { Brand } from './Landing';
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
  if (session.user) return <main className="account-status"><Brand onClick={() => window.location.assign('/')} /><section><h1>你已登录，{session.user.username}</h1><p>继续查看自己的扫描记录，或开始一次新的项目评估。</p><a className="account-primary" href={next}>进入工作台</a><button onClick={async () => { try { await submitAccount('logout'); window.location.replace('/login'); } catch (e) { setError(e instanceof Error ? e.message : '退出失败，请重试。'); } }}>退出当前账号</button>{error && <p role="alert">{error}</p>}</section></main>;
  return <main className="account-shell"><header className="account-nav"><Brand onClick={() => window.location.assign('/')} /><a href="/">返回首页</a></header>
    <div className="account-layout"><section className="account-intro"><span className="account-intro-mark" aria-hidden="true"><svg viewBox="0 0 120 132" fill="none"><path d="M60 9 105 26v35c0 30-21 49-45 62C36 110 15 91 15 61V26L60 9Z"/><path d="M42 65 55 78 81 49"/><path d="M60 24 92 36v25c0 21-13 36-32 48C41 97 28 82 28 61V36L60 24Z"/></svg></span><h1>让每一次评估，<br />都有迹可循。</h1><p>从项目扫描到用途更新，<br />把材料、依据和每个版本留在你的工作台。</p><ul><li><span aria-hidden="true">✓</span> 个人扫描记录，按账号独立保存</li><li><span aria-hidden="true">✓</span> 补充材料与历史结果，随时回看</li><li><span aria-hidden="true">✓</span> 证据先行，让下一步更清楚</li></ul><small>开源合规信息整理与辅助判断，不替代专业审核。</small></section>
    <section className="account-panel" aria-labelledby="account-title"><div className="account-tabs" aria-label="账号操作"><a href={'/login?next=' + encodeURIComponent(next)} aria-current={!register ? 'page' : undefined}>登录</a><a href={'/register?next=' + encodeURIComponent(next)} aria-current={register ? 'page' : undefined}>注册</a></div><h2 id="account-title">{register ? '创建你的工作台账号' : '欢迎回到 OpenGuard'}</h2><p className="account-lead">{register ? '保存你的项目扫描与评估记录。' : '登录后，继续上一次的项目评估。'}</p>
      <form onSubmit={event => void submit(event)} noValidate><fieldset disabled={busy}><label htmlFor="account-username">用户名</label><input id="account-username" name="username" autoComplete="username" autoCapitalize="none" spellCheck={false} value={username} onChange={e => setUsername(e.target.value)} maxLength={32} placeholder="例如 openguard_demo" aria-describedby={register ? 'username-help' : undefined} />{register && <small id="username-help">3—32 位英文字母、数字、下划线或短横线</small>}<label htmlFor="account-password">密码</label><div className="account-password"><input id="account-password" name="password" type={visible ? 'text' : 'password'} autoComplete={register ? 'new-password' : 'current-password'} value={password} onChange={e => setPassword(e.target.value)} maxLength={register ? 48 : 256} placeholder={register ? '8—24 个字符，包含字母和数字' : '请输入注册时设置的密码'} aria-describedby="password-help" /><button type="button" onClick={() => setVisible(v => !v)} aria-label={visible ? '隐藏密码' : '显示密码'} aria-pressed={visible}>{visible ? '隐藏' : '显示'}</button></div><small id="password-help">{register ? '8—24 个字符，必须同时包含英文字母和数字，可包含符号' : '使用注册时设置的密码；已有账号的原密码仍可登录'}</small>{register && <><label htmlFor="account-confirmation">确认密码</label><input id="account-confirmation" name="password-confirmation" type={visible ? 'text' : 'password'} autoComplete="new-password" value={confirmation} onChange={e => setConfirmation(e.target.value)} maxLength={48} placeholder="再次输入密码" /></>}{error && <div className="account-error" role="alert">{error}</div>}<button className="account-primary" type="submit">{busy ? (register ? '正在创建账号…' : '正在登录…') : (register ? '注册并进入工作台' : '登录工作台')}<span aria-hidden="true">↗</span></button></fieldset></form><p className="account-footnote">账号仅保存在这台电脑的本地演示工作台。<br />旧录制入口和已有数据保持独立。</p></section></div><footer className="account-footer">OpenGuard · 证据先行，结论可溯</footer></main>;
}
