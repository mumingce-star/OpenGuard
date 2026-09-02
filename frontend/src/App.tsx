import { useEffect, useMemo, useState } from 'react';
import { GlowCursor } from './components/GlowCursor';
import { ParticleText } from './components/ParticleText';
import { usePageVisibility } from './hooks/usePageVisibility';
import { discoveries, resources, risks, stages } from './mocks/data';
import type { Risk, Severity } from './types/domain';

type Route = '/' | '/app/overview' | '/app/new-scan' | '/app/progress' | '/app/risk' | '/app/resources' | '/app/graph' | '/app/report';

const navItems: { route: Route; label: string; icon: string }[] = [
  { route: '/app/new-scan', label: '新建扫描', icon: '＋' },
  { route: '/app/overview', label: '扫描概览', icon: '◫' },
  { route: '/app/risk', label: '风险中心', icon: '◇' },
  { route: '/app/resources', label: '资源清单', icon: '▤' },
  { route: '/app/graph', label: '证据图谱', icon: '⌘' },
  { route: '/app/report', label: '合规报告', icon: '▱' },
];

function useRoute() {
  const [route, setRoute] = useState<Route>(() => normalizeRoute(window.location.pathname));
  useEffect(() => {
    const update = () => setRoute(normalizeRoute(window.location.pathname));
    window.addEventListener('popstate', update);
    return () => window.removeEventListener('popstate', update);
  }, []);
  const go = (next: Route) => {
    window.history.pushState({}, '', next);
    setRoute(next);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };
  return { route, go };
}

function normalizeRoute(path: string): Route {
  if (path === '/') return '/';
  const match = navItems.find((item) => path.startsWith(item.route));
  if (match) return match.route;
  if (path.startsWith('/app/progress')) return '/app/progress';
  return '/app/overview';
}

export function App() {
  const { route, go } = useRoute();
  return route === '/' ? <Landing onEnter={() => go('/app/overview')} onDemo={() => go('/app/progress')} /> : <Workspace route={route} go={go} />;
}

function Brand({ onClick, compact = false }: { onClick: () => void; compact?: boolean }) {
  return (
    <button className={`brand ${compact ? 'brand-compact' : ''}`} type="button" onClick={onClick} aria-label="返回 OpenGuard 首页">
      <span className="brand-mark">OG</span>
      {!compact && <span>OpenGuard</span>}
    </button>
  );
}

function Landing({ onEnter, onDemo }: { onEnter: () => void; onDemo: () => void }) {
  return (
    <main className="landing-shell">
      <GlowCursor />
      <header className="landing-nav">
        <Brand onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })} />
        <nav aria-label="首页导航">
          <a href="#capability">核心能力</a>
          <a href="#workflow">工作流</a>
          <button className="nav-cta" type="button" onClick={onEnter}>进入工作台</button>
        </nav>
      </header>

      <section className="hero-section">
        <div className="ambient-grid" aria-hidden="true" />
        <div className="hero-badge"><span /> AI 开源合规与溯源助手</div>
        <ParticleText text="OpenGuard" />
        <p className="hero-copy">让每一个风险，都有证据可循；让每一次发布，都更有底气。</p>
        <div className="hero-actions">
          <button className="primary-button" type="button" onClick={() => goPath('/app/new-scan', onEnter)}>开始安全扫描 <span>↗</span></button>
          <button className="secondary-button" type="button" onClick={onDemo}>加载演示项目</button>
        </div>
        <div className="hero-meta" aria-label="产品特性">
          <span>01 / 资源发现</span><span>02 / 许可证判断</span><span>03 / AI 风险解释</span><span>04 / 合规报告</span>
        </div>
      </section>

      <section id="capability" className="recognition-slice">
        <div>
          <p className="eyebrow">EXPLAINABLE BY DESIGN</p>
          <h2>不止告诉你“有风险”，<br />更告诉你“为什么”。</h2>
          <p className="section-copy">扫描器发现事实，规则引擎给出判断，AI 负责解释与整改。三个来源清晰分层，每个结论都能回到文件、字段与许可依据。</p>
        </div>
        <div className="signal-card">
          <span className="signal-label">证据链 · RISK-001</span>
          <div className="signal-path"><span>package.json:18</span><i>→</i><span>transformers</span><i>→</i><span>Apache-2.0</span><i>→</i><strong>NOTICE 缺失</strong></div>
          <div className="source-row"><span className="source scanner">扫描事实</span><span className="source rule">规则判断</span><span className="source ai">AI 推断</span></div>
        </div>
      </section>

      <section id="workflow" className="workflow-section">
        <div className="workflow-title"><p className="eyebrow">ONE TRACEABLE FLOW</p><h2>从仓库到报告，一条证据链跑到底。</h2></div>
        <div className="workflow-grid">
          {['输入仓库 / ZIP', '七阶段智能扫描', '定位风险与证据', '导出合规报告'].map((item, index) => <div className="workflow-card" key={item}><span>0{index + 1}</span><h3>{item}</h3><p>{['GitHub 自动解析，或安全上传本地项目。', '识别包、模型、数据集、API 与服务。', '查看规则结论、代码位置与整改建议。', '生成可复核、可交付的资源与风险清单。'][index]}</p></div>)}
        </div>
      </section>
    </main>
  );
}

function goPath(path: Route, _fallback: () => void) {
  window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

function Workspace({ route, go }: { route: Route; go: (route: Route) => void }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const pageLabel = navItems.find((item) => item.route === route)?.label ?? (route === '/app/progress' ? '扫描进度' : '工作台');
  useEffect(() => setMobileOpen(false), [route]);
  useEffect(() => {
    const close = (event: KeyboardEvent) => event.key === 'Escape' && setMobileOpen(false);
    document.addEventListener('keydown', close);
    return () => document.removeEventListener('keydown', close);
  }, []);
  return (
    <div className="app-shell">
      <button className="mobile-menu" type="button" onClick={() => setMobileOpen(true)} aria-label="打开导航">☰</button>
      {mobileOpen && <button className="drawer-scrim" aria-label="关闭导航" onClick={() => setMobileOpen(false)} />}
      <aside className={`sidebar ${mobileOpen ? 'open' : ''}`}>
        <Brand onClick={() => go('/')} />
        <div className="sidebar-context"><span className="pulse-dot" /> <div><strong>演示项目</strong><small>OpenGuard-Lab</small></div></div>
        <nav aria-label="工作台导航">
          {navItems.map((item) => <button key={item.route} className={route === item.route ? 'active' : ''} type="button" onClick={() => go(item.route)}><span>{item.icon}</span>{item.label}{item.label === '风险中心' && <em>4</em>}</button>)}
        </nav>
        <div className="sidebar-footer"><span>MOCK MODE</span><p>本地演示数据 · 不依赖网络</p></div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div><span>OpenGuard-Lab</span><i>/</i><strong>{pageLabel}</strong></div>
          <div className="topbar-actions"><span className="scan-status"><b /> SCAN COMPLETE</span><button type="button" onClick={() => go('/app/new-scan')}>重新扫描</button><button className="top-primary" type="button" onClick={() => go('/app/report')}>导出报告</button></div>
        </header>
        <main className="workspace-content">
          {route === '/app/overview' && <Overview go={go} />}
          {route === '/app/new-scan' && <NewScan go={go} />}
          {route === '/app/progress' && <Progress go={go} />}
          {route === '/app/risk' && <RiskDetail risk={risks[0]} go={go} />}
          {route === '/app/resources' && <Resources />}
          {route === '/app/graph' && <Graph />}
          {route === '/app/report' && <Report />}
        </main>
      </div>
    </div>
  );
}

function PageHeader({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: React.ReactNode }) {
  return <div className="page-header"><div><p>{eyebrow}</p><h1>{title}</h1><span>{description}</span></div>{action}</div>;
}

function Overview({ go }: { go: (route: Route) => void }) {
  const metrics = [
    { label: '发现资源', value: '42', detail: '+ 8 个 AI 资源', tone: 'violet' },
    { label: '待处理风险', value: '09', detail: '需在发布前处理', tone: 'amber' },
    { label: '高风险', value: '03', detail: '1 个严重风险', tone: 'red' },
    { label: '许可证类型', value: '07', detail: '2 个待确认', tone: 'cyan' },
  ];
  return (
    <>
      <PageHeader eyebrow="SCAN / OG-20260902-071" title="扫描概览" description="OpenGuard-Lab · main · 完成于 2 分钟前" action={<button className="quiet-button" type="button">查看扫描日志</button>} />
      <div className="metric-grid">{metrics.map((metric) => <button className={`metric-card ${metric.tone}`} type="button" key={metric.label}><span>{metric.label}</span><strong>{metric.value}</strong><small>{metric.detail}</small><i>↗</i></button>)}</div>
      <div className="overview-grid">
        <section className="panel"><PanelTitle title="风险等级分布" caption="按待处理问题统计" /><div className="risk-visual"><div className="donut"><span><strong>9</strong>待处理</span></div><div className="legend-list">{[['严重', 1, 11, 'critical'], ['高风险', 2, 22, 'high'], ['中风险', 4, 45, 'medium'], ['低风险', 2, 22, 'low']].map(([name, count, width, tone]) => <div key={String(name)}><span><i className={String(tone)} />{name}</span><b>{count}</b><em><u className={String(tone)} style={{ width: `${width}%` }} /></em></div>)}</div></div></section>
        <section className="panel"><PanelTitle title="资源构成" caption="共识别 42 项资源" /><div className="resource-bars">{[['Package', 18, 'violet'], ['Model', 7, 'cyan'], ['Dataset', 6, 'blue'], ['API / Service', 8, 'green'], ['Asset', 3, 'slate']].map(([name, count, tone]) => <div key={String(name)}><span>{name}<b>{count}</b></span><em><u className={String(tone)} style={{ width: `${Number(count) * 5}%` }} /></em></div>)}</div></section>
      </div>
      <section className="panel risk-list-panel"><PanelTitle title="优先处理风险" caption="按严重度、影响范围与可整改性排序" action={<button type="button" onClick={() => go('/app/risk')}>查看全部风险 →</button>} /><div className="risk-table"><div className="risk-row risk-head"><span>风险</span><span>影响资源</span><span>许可证</span><span>证据</span><span>状态</span></div>{risks.slice(0, 3).map((risk) => <button className="risk-row" type="button" key={risk.id} onClick={() => go('/app/risk')}><span><SeverityBadge severity={risk.severity} /> <b>{risk.title}</b><small>{risk.id}</small></span><span>{risk.resource}</span><span>{risk.license}</span><span>{risk.evidenceCount} 条</span><span>{risk.status} <i>›</i></span></button>)}</div></section>
    </>
  );
}

function PanelTitle({ title, caption, action }: { title: string; caption?: string; action?: React.ReactNode }) {
  return <header className="panel-title"><div><h2>{title}</h2>{caption && <p>{caption}</p>}</div>{action}</header>;
}

function SeverityBadge({ severity }: { severity: Severity }) { return <span className={`severity ${severity}`}>{({ critical: '严重', high: '高', medium: '中', low: '低' })[severity]}</span>; }

function NewScan({ go }: { go: (route: Route) => void }) {
  const [tab, setTab] = useState<'github' | 'zip'>('github');
  const [url, setUrl] = useState('https://github.com/mumingce-star/OpenGuard');
  return (
    <div className="narrow-page">
      <PageHeader eyebrow="CREATE SCAN" title="新建扫描" description="输入公开仓库或上传项目压缩包，OpenGuard 将识别第三方资源与许可风险。" />
      <section className="scan-panel panel">
        <div className="tab-list" role="tablist"><button type="button" role="tab" aria-selected={tab === 'github'} onClick={() => setTab('github')}>GitHub 仓库</button><button type="button" role="tab" aria-selected={tab === 'zip'} onClick={() => setTab('zip')}>上传 ZIP</button></div>
        {tab === 'github' ? <div className="scan-form"><label htmlFor="repo">公开仓库地址</label><div className="url-input"><span>⌘</span><input id="repo" value={url} onChange={(event) => setUrl(event.target.value)} /><i>✓ 已识别</i></div><div className="repo-preview"><span className="repo-icon">OG</span><div><strong>mumingce-star / OpenGuard</strong><p>Public · Python / TypeScript · 默认分支 main</p></div><span className="verified">仓库可访问</span></div></div> : <div className="drop-zone"><strong>将 OpenGuard.zip 拖到这里</strong><p>最大 200 MB · 仅支持 .zip</p><button type="button">选择文件</button></div>}
        <div className="scan-scope"><span>本次扫描范围</span>{['依赖与第三方包', '模型与数据集', 'API 与外部服务', 'LICENSE / NOTICE'].map((item) => <label key={item}><input type="checkbox" defaultChecked />{item}</label>)}</div>
        <div className="scan-footer"><button className="demo-button" type="button" onClick={() => go('/app/progress')}>▹ 加载演示项目</button><button className="primary-button" type="button" onClick={() => go('/app/progress')}>开始扫描 <span>↗</span></button></div>
      </section>
    </div>
  );
}

function Progress({ go }: { go: (route: Route) => void }) {
  const [completed, setCompleted] = useState(4);
  const pageVisible = usePageVisibility();
  useEffect(() => {
    if (completed >= stages.length || !pageVisible) return;
    const timer = window.setTimeout(() => setCompleted((value) => value + 1), 1400);
    return () => window.clearTimeout(timer);
  }, [completed, pageVisible]);
  const percent = Math.round((completed / stages.length) * 100);
  return (
    <>
      <PageHeader eyebrow="LIVE SCAN / OG-DEMO-001" title="正在扫描 OpenGuard-Lab" description="演示数据 · 所有发现均来自固定快照" action={<span className="live-chip"><i /> SCANNING</span>} />
      <div className="progress-summary"><div><span>总体进度</span><strong>{percent}%</strong></div><em><i style={{ width: `${percent}%` }} /></em><p>{completed >= stages.length ? '扫描完成，合规报告已生成。' : `正在执行：${stages[Math.min(completed, stages.length - 1)]}`}</p></div>
      <div className="progress-layout"><section className="panel pipeline-panel"><PanelTitle title="扫描 Pipeline" caption="七阶段可解释扫描过程" /><div className="pipeline">{stages.map((stage, index) => { const state = index < completed ? 'done' : index === completed ? 'running' : 'pending'; return <div className={`stage ${state}`} key={stage}><span>{state === 'done' ? '✓' : String(index + 1).padStart(2, '0')}</span><div><strong>{stage}</strong><p>{state === 'done' ? '已完成 · 发现结果已写入证据库' : state === 'running' ? '正在分析当前扫描对象…' : '等待前置阶段完成'}</p></div><i>{state === 'done' ? '完成' : state === 'running' ? '执行中' : '等待'}</i></div>; })}</div></section><section className="panel discovery-panel"><PanelTitle title="实时发现" caption="资源、许可证与风险" /><div className="discovery-list">{discoveries.slice(0, Math.max(1, Math.min(discoveries.length, completed))).reverse().map((item) => <div className="discovery" key={item.type}><span className={item.tone}>{item.type.slice(0, 1)}</span><div><small>{item.type}</small><strong>{item.title}</strong><p>{item.detail}</p></div><i>刚刚</i></div>)}</div>{completed >= stages.length && <button className="primary-button full-button" type="button" onClick={() => go('/app/overview')}>查看扫描结果 →</button>}</section></div>
    </>
  );
}

function RiskDetail({ risk, go }: { risk: Risk; go: (route: Route) => void }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => { await navigator.clipboard?.writeText(risk.remediation); setCopied(true); window.setTimeout(() => setCopied(false), 1600); };
  return (
    <>
      <button className="back-link" type="button" onClick={() => go('/app/overview')}>← 返回扫描概览</button>
      <div className="risk-heading"><div><SeverityBadge severity={risk.severity} /><span>{risk.id}</span><h1>{risk.title}</h1><p>{risk.resource} · {risk.license} · {risk.evidenceCount} 条关联证据</p></div><button className="quiet-button" type="button">标记可能误报</button></div>
      <div className="risk-detail-grid"><div className="risk-main">
        <section className="panel detail-section"><PanelTitle title="判定摘要" /><SourceBlock type="rule" label="规则判断" text={risk.conclusion} /><SourceBlock type="scanner" label="扫描事实" text="在打包清单与仓库根目录中均未检出 NOTICE；依赖锁文件确认 transformers@4.52.0 将进入分发产物。" /><SourceBlock type="ai" label="AI 风险解释 · 需人工复核" text="该缺失可能导致 Apache-2.0 的归属声明义务未被完整履行，发布前建议补齐 NOTICE 并核对所有上游声明。" /></section>
        <section className="panel evidence-section"><PanelTitle title="证据链" caption="点击节点可定位原始证据" /><div className="evidence-chain">{['package.json:18', 'transformers@4.52', 'Apache-2.0', '保留 NOTICE', '发布目录缺失'].map((item, index) => <div key={item}><button className={index === 4 ? 'danger-node' : ''} type="button"><span>{['FILE', 'RESOURCE', 'LICENSE', 'OBLIGATION', 'RISK'][index]}</span>{item}</button>{index < 4 && <i>→</i>}</div>)}</div></section>
        <section className="panel remediation"><PanelTitle title="整改建议" action={<button type="button" onClick={copy}>{copied ? '✓ 已复制' : '复制建议'}</button>} /><p>{risk.remediation}</p><div className="remediation-impact"><span>预计整改后</span><strong>严重 → 低风险</strong><em>发布准备度 +12</em></div></section>
      </div><aside className="panel code-evidence"><PanelTitle title="代码证据" caption="扫描事实 · confidence 0.98" /><div className="file-label">package.json <span>第 18–21 行</span></div><pre><code><b>16</b>  "dependencies": {'{'}{`\n`}<b>17</b>    "fastapi": "0.116.1",{`\n`}<mark><b>18</b>    "transformers": "4.52.0",</mark>{`\n`}<b>19</b>    "torch": "2.7.1"{`\n`}<b>20</b>  {'}'}</code></pre><div className="detector-meta"><span>检测器</span><strong>dependency-manifest</strong><span>证据哈希</span><strong>9fc2…7bd1</strong></div></aside></div>
    </>
  );
}

function SourceBlock({ type, label, text }: { type: 'scanner' | 'rule' | 'ai'; label: string; text: string }) { return <div className={`source-block ${type}`}><span>{label}</span><p>{text}</p></div>; }

function Resources() {
  const [filter, setFilter] = useState('全部');
  const visible = useMemo(() => resources.filter((item) => filter === '全部' || item.type === filter), [filter]);
  return (
    <><PageHeader eyebrow="INVENTORY / 42 RESOURCES" title="第三方资源清单" description="统一查看依赖、模型、数据集、API、服务与素材的来源及许可状态。" action={<button className="quiet-button" type="button">导出 CSV</button>} /><div className="filter-bar"><input aria-label="搜索资源" placeholder="搜索名称、版本或来源…" /><div>{['全部', 'Package', 'Model', 'Dataset', 'API', 'Service', 'Asset'].map((item) => <button className={filter === item ? 'active' : ''} type="button" onClick={() => setFilter(item)} key={item}>{item}</button>)}</div><label><input type="checkbox" /> 仅看许可证待确认</label></div><section className="panel resource-table"><div className="resource-row resource-head"><span>资源名称</span><span>类型</span><span>来源</span><span>许可证</span><span>最高风险</span><span>证据</span></div>{visible.map((resource) => <button className="resource-row" type="button" key={resource.name}><span><b>{resource.name}</b><small>{resource.version}</small></span><span><i className={`type-dot ${resource.type.toLowerCase()}`} />{resource.type}</span><span>{resource.origin}</span><span className={resource.license === '待复核' ? 'unknown-license' : ''}>{resource.license}</span><span>{resource.risk === 'safe' ? <em className="safe-label">通过</em> : <SeverityBadge severity={resource.risk} />}</span><span>{resource.evidence} 条 ›</span></button>)}</section></>
  );
}

function Graph() {
  const nodes = [
    { label: 'OpenGuard-Lab', type: 'REPOSITORY', x: 8, y: 43, tone: 'repo' }, { label: 'package.json', type: 'FILE', x: 29, y: 24, tone: 'file' },
    { label: 'transformers', type: 'PACKAGE', x: 51, y: 22, tone: 'package' }, { label: 'Apache-2.0', type: 'LICENSE', x: 74, y: 22, tone: 'license' },
    { label: 'NOTICE 缺失', type: 'CRITICAL RISK', x: 88, y: 49, tone: 'risk' }, { label: 'model.config', type: 'FILE', x: 29, y: 68, tone: 'file' },
    { label: 'Qwen3-8B', type: 'MODEL', x: 52, y: 69, tone: 'model' }, { label: '用途待复核', type: 'HIGH RISK', x: 76, y: 76, tone: 'risk-high' },
  ];
  return <><PageHeader eyebrow="EVIDENCE GRAPH / RISK PATHS" title="证据关系图谱" description="默认聚焦风险路径，点击节点查看上下游证据与判断依据。" action={<div className="graph-actions"><button type="button">仅风险路径</button><button type="button">重置视图</button></div>} /><section className="panel graph-panel"><div className="graph-toolbar"><span><i className="repo" />仓库</span><span><i className="file" />文件</span><span><i className="package" />依赖</span><span><i className="model" />模型</span><span><i className="license" />许可证</span><span><i className="risk" />风险</span></div><div className="graph-canvas"><svg viewBox="0 0 1000 520" preserveAspectRatio="none" aria-hidden="true"><path d="M120 260 C210 260 200 130 310 130"/><path d="M360 130 L530 125"/><path d="M590 125 L760 125"/><path className="risk-edge" d="M820 135 C890 165 870 240 900 260"/><path d="M120 270 C210 285 210 370 310 370"/><path d="M360 370 L540 365"/><path className="risk-edge high" d="M600 365 C700 365 730 390 780 400"/></svg>{nodes.map((node) => <button key={node.label} className={`graph-node ${node.tone}`} type="button" style={{ left: `${node.x}%`, top: `${node.y}%` }}><span>{node.type}</span><strong>{node.label}</strong></button>)}<div className="minimap"><i /><i /><i /><i /></div><div className="zoom-controls"><button type="button">＋</button><button type="button">−</button><button type="button">⌗</button></div></div></section></>;
}

function Report() {
  const [exported, setExported] = useState(false);
  const exportReport = () => {
    const payload = JSON.stringify({ project: 'OpenGuard-Lab', scanId: 'OG-20260902-071', resources, risks }, null, 2);
    const url = URL.createObjectURL(new Blob([payload], { type: 'application/json' }));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'OpenGuard-Lab_合规报告.json'; anchor.click(); URL.revokeObjectURL(url); setExported(true);
  };
  return <><PageHeader eyebrow="COMPLIANCE REPORT / DRAFT" title="合规报告" description="扫描结果已整理为可复核的风险、资源与整改清单。" action={<button className="top-primary report-export" type="button" onClick={exportReport}>{exported ? '✓ 已导出 JSON' : '导出 JSON'}</button>} /><div className="report-layout"><aside className="panel report-nav"><span>报告目录</span>{['执行摘要', '风险清单', '第三方资源', '模型与数据集来源', '整改建议', '证据附录'].map((item, index) => <a className={index === 0 ? 'active' : ''} href={`#report-${index}`} key={item}><i>0{index + 1}</i>{item}</a>)}</aside><article className="panel report-paper"><header><div><span>OPENGUARD / COMPLIANCE</span><h1>OpenGuard-Lab<br />AI 开源合规扫描报告</h1></div><strong>发布准备度<b>72</b><small>/100</small></strong></header><div className="report-meta"><span>扫描编号<strong>OG-20260902-071</strong></span><span>仓库分支<strong>main</strong></span><span>生成时间<strong>2026-09-02</strong></span><span>报告状态<strong>AI 草案 · 待复核</strong></span></div><section id="report-0"><h2>01. 执行摘要</h2><p>本次扫描共识别 42 项第三方与 AI 资源，发现 9 项待处理风险，其中 1 项严重风险与 2 项高风险需要在发布前优先处理。</p><div className="report-callout"><span>优先行动</span><strong>补齐 Apache-2.0 NOTICE，并复核 Qwen3 模型用途限制。</strong></div></section><section id="report-1"><h2>02. 关键风险</h2>{risks.slice(0, 3).map((risk) => <div className="report-risk" key={risk.id}><SeverityBadge severity={risk.severity} /><div><strong>{risk.title}</strong><p>{risk.conclusion}</p></div><span>{risk.id}</span></div>)}</section><footer>本报告由 OpenGuard 生成。AI 解释与整改建议为草案，发布前请由项目负责人复核。</footer></article></div></>;
}
