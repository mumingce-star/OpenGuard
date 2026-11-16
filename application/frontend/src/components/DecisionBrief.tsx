import { useEffect, useRef, useState } from 'react';
import { presets, listAssessments, type Assessment, type Usage } from '../services/assessments';
import { ApiError } from '../services/scans';
import { readBrief, readJobs, resolveLocal, cancelResolution, presentObligation, type Brief, type ResolutionJob } from '../services/resolution';
import { sameUsage, usageDescription, conclusionText, permissionBoundary, obligationResources, primaryAction, materialProgress, presentGap, initialSnapshot, orderedJobs, activeResolution, resolutionStatus, modelStatus, needsResultSelection, pendingGroups, materialOriginal, usageHints, scopeSummary, scopeSourceLabel, type UsageField } from '../services/usageExperience';

import '../styles/usage-result.css';
import { readOnlyPreview } from '../services/assessmentFeedback';

const resolutionError = (error: unknown) => error instanceof ApiError && error.status === 409
 ? '任务状态或固定评估已变化，请先读取进度，再决定是否重新查找。'
 : error instanceof ApiError && error.status === 404 ? '当前运行版本不支持此功能，或记录不存在；原评估仍保留。'
 : error instanceof ApiError && error.status === 503 ? '本地材料存储暂不可用；原评估保留，可稍后读取进度。'
 : error instanceof ApiError && [502,504].includes(error.status) ? '无法连接当前本地服务；原评估保留，服务恢复后先读取进度。'
 : error instanceof TypeError ? '无法连接当前本地服务；确认页面服务可用后，先读取进度，避免重复任务。'
 : '材料查找未完成；请先读取进度，历史结果仍保留。';

export function DecisionBrief({ assessment, compact=false, onEditUsage, readOnly=readOnlyPreview, draftUsage=assessment.usage, usageReadOnly=false }: { assessment: Assessment; compact?:boolean; readOnly?:boolean; onEditUsage?:(field?:UsageField)=>void; draftUsage?:Usage; usageReadOnly?:boolean }) {
 const [brief,setBrief]=useState<Brief|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[useModel,setUseModel]=useState(false);
 const [jobs,setJobs]=useState<ResolutionJob[]>([]),[currentJob,setCurrentJob]=useState<ResolutionJob|null>(null),[notice,setNotice]=useState('');
 const [openOriginals,setOpenOriginals]=useState<string[]>([]),[allGaps,setAllGaps]=useState(false);
 const epoch=useRef(0),viewRequest=useRef(0),lock=useRef(false),key=useRef(crypto.randomUUID()),followJob=useRef<string|null>(null);
 const materialArea=useRef<HTMLDivElement>(null);
 const dirty=!sameUsage(assessment.usage,draftUsage);
 const active=activeResolution(jobs);
 const editLabel=assessment.usage.preset==='unknown'?'选择用途':'修改用途';

 useEffect(()=>{
  const token=++epoch.current,abort=new AbortController();
  setBrief(null);setJobs([]);setCurrentJob(null);setError('');setNotice('');setBusy(false);key.current=crypto.randomUUID();followJob.current=null;
  void (async()=>{
   try {
    const history=await readJobs(assessment.scan_id,assessment.id,assessment.version,abort.signal);
    // Refresh restores job state, but does not silently follow the newest result.
    const value=await readBrief(assessment.scan_id,assessment.id,assessment.version,initialSnapshot(history,assessment.id),abort.signal);
    if(epoch.current===token) {
     setBrief(value);setJobs(history);
     setCurrentJob(activeResolution(history)??orderedJobs(history).find(j=>!j.request_key.startsWith('initial-'))??null);
    }
   } catch(e) {if(!abort.signal.aborted&&epoch.current===token)setError(resolutionError(e));}
  })();
  return()=>{++epoch.current;abort.abort();};
 },[assessment.scan_id,assessment.id,assessment.version]);

 // Only GETs while an existing job is active; refresh/return never reserves work.
 useEffect(()=>{
  if(!active) return;
  const token=epoch.current,abort=new AbortController();let timer:ReturnType<typeof setTimeout>,reads=0;
  async function poll() {
   try {
    const history=await readJobs(assessment.scan_id,assessment.id,assessment.version,abort.signal);
    if(epoch.current!==token||abort.signal.aborted)return;
    const result=history.find(j=>j.job_id===active!.job_id);
    if(!result) {setError('任务记录暂不可读取；不会据此显示成功。');return;}
    if(resolutionStatus(result).active) {
     setJobs(history);setCurrentJob(result);
     if(++reads<50) timer=setTimeout(()=>void poll(),600);
     else setNotice('任务仍在运行；可读取进度或取消，不会自动重复提交。');
    } else {
     key.current=crypto.randomUUID();
     if(result.status==='completed'&&result.snapshot_id&&followJob.current===result.job_id) {
      const value=await readBrief(assessment.scan_id,assessment.id,assessment.version,result.snapshot_id,abort.signal);
      if(epoch.current===token&&!abort.signal.aborted)setBrief(value);
     }
     followJob.current=null;
     if(epoch.current===token&&!abort.signal.aborted) {setJobs(history);setCurrentJob(result);}
    }
   } catch(e) {if(!abort.signal.aborted&&epoch.current===token)setError(resolutionError(e));}
  }
  timer=setTimeout(()=>void poll(),300);
  return()=>{abort.abort();clearTimeout(timer);};
 },[active?.job_id,assessment.scan_id,assessment.id,assessment.version]);

 async function refreshJobs() {
  const token=epoch.current;setError('');
  try {
   const history=await readJobs(assessment.scan_id,assessment.id,assessment.version);
   if(!brief) {
    const value=await readBrief(assessment.scan_id,assessment.id,assessment.version,initialSnapshot(history,assessment.id));
    if(epoch.current===token)setBrief(value);
   }
   if(epoch.current===token) {setJobs(history);setCurrentJob(activeResolution(history)??orderedJobs(history).find(j=>!j.request_key.startsWith('initial-'))??null);setNotice('已读取任务记录；显示的材料结果保持原选择。');}
  } catch(e) {if(epoch.current===token)setError(resolutionError(e));}
 }
 async function run() {
  if(readOnly||lock.current||active||dirty)return;
  lock.current=true;setBusy(true);setError('');setNotice('');const token=epoch.current;
  try {
   const history=await readJobs(assessment.scan_id,assessment.id,assessment.version);
   if(epoch.current!==token)return;
   const existing=activeResolution(history);
   if(existing) {setJobs(history);setCurrentJob(existing);setNotice('已有查找任务，先读取它的进度。');return;}
   const result=await resolveLocal(assessment.scan_id,assessment.id,assessment.version,assessment.facts_hash,key.current,useModel);
   if(epoch.current!==token)return;
   followJob.current=result.job_id;setCurrentJob(result);setJobs([...history.filter(j=>j.job_id!==result.job_id),result]);
   if(result.status==='completed'&&result.snapshot_id) {
    const value=await readBrief(assessment.scan_id,assessment.id,assessment.version,result.snapshot_id);
    if(epoch.current===token)setBrief(value);
    key.current=crypto.randomUUID();followJob.current=null;
   } else if(!resolutionStatus(result).active) {key.current=crypto.randomUUID();followJob.current=null;}
  } catch(e) {if(epoch.current===token)setError(resolutionError(e));} // Uncertain POST: retain idempotency key.
  finally {lock.current=false;if(epoch.current===token)setBusy(false);}
 }
 async function cancel() {
  if(readOnly||!active||lock.current)return;
  lock.current=true;setBusy(true);const token=epoch.current;setError('');
  try {
   const result=await cancelResolution(assessment.scan_id,assessment.id,assessment.version,active.job_id,active.version);
   if(epoch.current===token) {setJobs(jobs.map(j=>j.job_id===result.job_id?result:j));setCurrentJob(result);key.current=crypto.randomUUID();followJob.current=null;}
  } catch(e) {if(epoch.current===token) {setError(resolutionError(e));await refreshJobs();setNotice('取消未确认；任务可能已结束，请查看读取到的状态。');}}
  finally {lock.current=false;if(epoch.current===token)setBusy(false);}
 }
 async function selectSnapshot(id:string) {
  if(active||lock.current)return;
  const token=epoch.current,request=++viewRequest.current;setBusy(true);setError('');
  try {
   const value=await readBrief(assessment.scan_id,assessment.id,assessment.version,id||undefined);
   if(epoch.current===token&&viewRequest.current===request)setBrief(value);
  } catch(e) {if(epoch.current===token&&viewRequest.current===request)setError(resolutionError(e));}
  finally {if(epoch.current===token&&viewRequest.current===request)setBusy(false);}
 }
 function viewMaterials() {
  const area=materialArea.current;
  if(!area)return;
  // Focus first with no scroll, then one deterministic scroll: no delayed smooth-scroll race.
  area.focus({preventScroll:true});
  area.scrollIntoView({behavior:'instant',block:'start'});
 }
 const usageHref='/app/scans/'+encodeURIComponent(assessment.scan_id)+'/assessment?mode=api&assessment_id='+encodeURIComponent(assessment.id)+(usageReadOnly?'':'#og-assessment-usage');
 const edit = usageReadOnly ? null : onEditUsage ? <button type="button" onClick={()=>onEditUsage()} aria-controls="og-assessment-usage">{editLabel}</button>
  : <a href={usageHref}>{editLabel} →</a>;
 const usageBlock=<div className="og-current-use"><div className="og-use-heading"><span>当前用途</span><strong>{presets[assessment.usage.preset]}</strong>{edit}</div><p className="og-use-facts">{usageDescription(assessment.usage)}</p>{dirty&&<p className="og-use-draft" role="status">新选择：{usageDescription(draftUsage)}。尚未生成新评估；下面仍是原用途的结果。</p>}</div>;
 if(!brief) return <section className="og-decision-brief og-usage-result">{usageBlock}<p role="status">{error||'正在读取当前用途的结论…'}</p><button type="button" onClick={()=>void refreshJobs()}>读取任务进度</button><p>当前结论暂不可读取，不能据此确认许可。已保存的必要条件仍保留如下。</p><ul>{assessment.dimensions?.flatMap(d=>[...d.conditions,...d.restrictions]).map((c,i)=><li key={i}>{c}</li>)}</ul>{assessment.obligations?.map(o=><article key={o.id}><strong>{presentObligation(o).requirement}</strong><p>触发条件：{presentObligation(o).trigger||'仍待确认'}</p><p>履行状态：{o.fulfillment==='satisfied'?'记录为已满足，请复核':'待履行／待确认'}</p></article>)}</section>;
 const conditions=[...new Set(brief.dimensions.flatMap(d=>[...d.conditions,...d.restrictions]))];
 const progress=materialProgress(brief),snapshots=orderedJobs(jobs).filter(j=>j.status==='completed');
 const action=primaryAction(brief,assessment.usage,{dirty,busy,active:!!active,needsSelection:needsResultSelection(currentJob,brief.resolution_snapshot_id)});
 const materialId='og-resolution-materials-'+assessment.id;
 const hints=usageHints(brief,assessment.usage),scope=scopeSummary(brief);
 const groups=pendingGroups({...brief,gaps:brief.gaps.filter(g=>g.code!=='USAGE_MISSING'&&g.code!=='SCOPE_UNRESOLVED')});
 const toggleOriginal=(id:string)=>setOpenOriginals(values=>values.includes(id)?values.filter(v=>v!==id):[...values,id]);
 const hasSearch=action.kind==='search'||action.kind==='usage'||action.disabled;
 return <section className="og-decision-brief og-usage-result" aria-label="当前用途行动摘要">
  {usageBlock}
  <header className="og-use-conclusion"><span className="og-resolution-status">{brief.permission_state==='conditional'?'需满足条件':brief.permission_state==='restricted'?'存在限制':'待确认'}</span><h2>{conclusionText(brief)}</h2></header>
  <p className="og-resolution-boundary">{permissionBoundary(brief)}<small className="og-use-count">范围：{brief.local_results.filter(r=>r.supported_permission===true).length}/{brief.local_results.length} 条资源记录有局部支持；不是整体通过率。</small></p>
  <div className="og-resolution-actions">
   {action.kind==='usage'?(usageReadOnly?<p>本次用途以已保存评估为准；未知事实保留未知。本页仅查看结果。</p>:onEditUsage?<button className="og-primary" type="button" onClick={()=>onEditUsage()} aria-controls="og-assessment-usage">{action.label}</button>:<a className="og-primary" href={usageHref}>{action.label}</a>)
    :action.kind==='materials'?<button className="og-primary" type="button" onClick={viewMaterials} aria-controls={materialId}>{action.label}</button>
    :action.kind==='saved'?<button className="og-primary" type="button" disabled={busy||!!active} onClick={()=>void selectSnapshot(currentJob!.snapshot_id!)}>{action.label}</button>
    :action.kind==='progress'?<button className="og-primary" type="button" disabled={busy} onClick={()=>void refreshJobs()}>{action.label}</button>
    :compact?<a className="og-primary" href={usageHref}>查看用途与行动</a>:<button className="og-primary" type="button" disabled={readOnly||action.disabled} onClick={()=>void run()}>{action.label}</button>}
   {action.kind==='materials'&&<span>只读查看，不重新查找材料</span>}
  </div>
  <p className="og-use-next">{readOnly&&dirty?'这里的试填不会保存；当前结论仍使用已保存的用途，可继续查看材料与义务。':readOnly&&action.kind==='search'?'只读预览不能启动材料查找；可查看已有材料与待审核事项。':action.description}</p>
  {!compact&&hasSearch&&<div className="og-use-secondary">
   {action.kind!=='search'&&<button type="button" disabled={readOnly||action.disabled} onClick={()=>void run()}>{action.searchLabel}</button>}
   <button type="button" onClick={viewMaterials} aria-controls={materialId}>查看材料与待审核事项</button>
   <label><input type="checkbox" checked={useModel} disabled={readOnly||action.disabled} onChange={e=>{setUseModel(e.target.checked);key.current=crypto.randomUUID();}} /> 使用已有本地模型辅助核对（不代替审核）</label>
  </div>}
  {!!(conditions.length+brief.obligations.length)&&<section className="og-use-obligations"><h3>必要条件与待履行义务</h3>
   <p className="og-use-caption">条件/限制提示 {conditions.length} 条 · 义务原文 {brief.obligations.length} 条</p>
   {conditions.length>0&&<ul>{conditions.map((c,i)=><li key={i}>{c}</li>)}</ul>}
   {brief.obligations.map(o=>{const key='obligation:'+brief.resolution_snapshot_id+':'+o.id;return <article key={o.id}>
    <strong>{presentObligation(o).requirement}</strong><p>{obligationResources(o,brief)}</p>
    <p>触发条件：{presentObligation(o).trigger||'尚待确认，不能视为不适用'}</p>
    <p>{o.fulfillment==='satisfied'?'记录为已满足，请复核依据':'待履行／待确认'}</p>
    <button type="button" aria-expanded={openOriginals.includes(key)} onClick={()=>toggleOriginal(key)}>{openOriginals.includes(key)?'收起义务原文':'查看义务原文'}</button>
    {openOriginals.includes(key)&&<blockquote>{o.requirement}<p>{o.trigger}</p></blockquote>}
   </article>;})}
  </section>}
  <section className="og-use-pending"><h3>仍需明确</h3>
   {(hints.text||hints.uncertain)&&<article><h4>需要你说明的用途信息</h4>{hints.text&&<p>{hints.text}</p>}{hints.uncertain&&<p>部分用途关联尚待核对；不会据此要求重复填写已声明的事实。</p>}
    {hints.fields.length>0&&!usageReadOnly&&onEditUsage&&<button type="button" onClick={()=>onEditUsage(hints.fields[0])} aria-controls="og-assessment-usage">补充用途信息</button>}
   </article>}
   {scope.sources.length>0&&<article><h4>资源在项目中的适用范围仍待核验</h4><p>{scope.text}</p><p>这涉及资源是项目自身、依赖还是开发示例的核验，不是再次填写分发选项。</p>
    <ul>{scope.sources.map((g,i)=><li key={i}>{scopeSourceLabel(g)}</li>)}</ul>
    {scope.unclassified>0&&<p>部分记录的对象或核验种类尚待核对，不能据此视为已解决。</p>}
   </article>}
   {groups.length?groups.map(group=><article key={group.owner}><h4>{group.title}</h4><ul>{(allGaps?group.gaps:group.gaps.slice(0,1)).map((g,i)=><li key={i}><strong>{presentGap(g,brief).title}</strong><p>{presentGap(g,brief).action}</p></li>)}</ul>
    {!allGaps&&group.gaps.length>1&&<p>另有 {group.gaps.length-1} 项待确认事项</p>}</article>):!hints.text&&!hints.uncertain&&!scope.sources.length&&<p>本结果未列出新增待确认事项；仍应结合用途、许可与必要条件判断。</p>}
   {groups.some(g=>g.gaps.length>1)&&<button type="button" aria-expanded={allGaps} onClick={()=>setAllGaps(v=>!v)}>{allGaps?'收起其余待确认事项':'查看全部待确认事项'}</button>}
  </section>
  <div className="og-use-materials" id={materialId} ref={materialArea} tabIndex={-1} aria-label="材料与待审核事项">
   <h3>材料与待审核事项</h3><p>{progress.summary}</p><p>{progress.formal}</p>
   {brief.resolution_observations.map((o,i)=>{const key='material:'+brief.resolution_snapshot_id+':'+o.material_id+':'+i;return <article key={key}>
    <h4>{o.name} · {o.version}</h4><p>{o.atomic_facts.version_located?'版本材料已定位':'版本材料仍待定位'}；{o.atomic_facts.document_acquired?'许可正文已取得':'许可正文仍缺失'}。适用关系与授权仍待审核。</p>
    <button type="button" aria-expanded={openOriginals.includes(key)} onClick={()=>toggleOriginal(key)}>{openOriginals.includes(key)?'收起许可原文':'查看许可原文'}</button>
    {openOriginals.includes(key)&&<pre className="og-use-original">{materialOriginal(o.text)}</pre>}
   </article>;})}
   {brief.resolution_model&&!['not_requested','completed'].includes(brief.resolution_model.status)&&<p>{modelStatus(brief.resolution_model.reason)}</p>}
   {!!brief.resolution_model?.output?.conflict_clues?.length&&<p>材料之间仍有冲突线索，需要独立审核，模型没有裁定授权。</p>}
   {!!brief.resolution_cases?.length&&<p>{brief.resolution_cases.some(c=>c.matches.length)?'已有审核参考，仅帮助理解材料，不转移授权。':'当前没有可复用的审核参考；已有材料与局部判断仍保留。'}</p>}
   {brief.resolution_cases?.some(c=>c.invalidations?.length)&&<p>部分历史参考已失效，不能据此确认当前用途。</p>}
  </div>
  {currentJob&&<div className="og-resolution-job"><p role="status">{resolutionStatus(currentJob).text}</p>{active&&!compact&&<button type="button" disabled={readOnly||busy} onClick={()=>void cancel()}>取消本次查找</button>}<button type="button" disabled={busy} onClick={()=>void refreshJobs()}>读取进度</button></div>}
  {notice&&<p role="status">{notice}</p>}{error&&<p role="alert" className="og-error">{error}</p>}
  {action.kind!=='saved'&&needsResultSelection(currentJob,brief.resolution_snapshot_id)&&<div className="og-resolution-saved"><p>已有查找结果保存；当前显示的仍是先前固定结果。</p><button type="button" disabled={busy||!!active} onClick={()=>void selectSnapshot(currentJob!.snapshot_id!)}>查看已保存的查找结果</button></div>}
  <footer className="og-use-history">
   {snapshots.length>0&&<label>查看已保存的材料结果<select aria-label="补证快照" disabled={busy||!!active} value={brief.resolution_snapshot_id||''} onChange={e=>void selectSnapshot(e.target.value)}><option value="">仅原评估，不附加材料结果</option>{snapshots.map((j,i)=><option key={j.job_id} value={j.snapshot_id!}>{j.request_key.startsWith('initial-')?'初始材料记录':'材料查找记录'} · 第 {snapshots.length-i} 份</option>)}</select></label>}
   <p>切换只读取所选材料；刷新或返回显示初始材料记录，评估使用的用途不变。</p>
  </footer>
 </section>;
}

export function OverviewDecision({ scanId }: {scanId:string}) {
 const [items,setItems]=useState<Assessment[]>([]),[selected,setSelected]=useState(''),[error,setError]=useState('');
 useEffect(()=>{const a=new AbortController();setItems([]);setSelected('');setError('');void listAssessments(scanId,a.signal).then(value=>{setItems(value.items);if(value.items.length===1)setSelected(value.items[0].id);}).catch(e=>{if(!a.signal.aborted)setError(resolutionError(e));});return()=>a.abort();},[scanId]);
 const item=items.find(a=>a.id===selected);
 return <><label className="og-field">用途摘要的固定评估<select aria-label="用途摘要的固定评估" value={selected} onChange={e=>setSelected(e.target.value)}><option value="">请选择已保存版本</option>{items.map(a=><option value={a.id} key={a.id}>第 {a.version} 版 · {presets[a.usage.preset]}</option>)}</select></label>{item?<DecisionBrief key={item.id} assessment={item} compact />:<p>{error||'选择已保存评估后查看用途结论；风险卡片不能推导整体授权。'}</p>}</>;
}
