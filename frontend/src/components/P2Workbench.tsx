import { useEffect, useLayoutEffect, useRef, useState, type MouseEvent } from 'react';
import type { Assessment } from '../services/assessments';
import { assessmentReportUrl, usageFields } from '../services/assessments';
import type { Scan } from '../types/domain';
import { ApiError } from '../services/scans';
import { pendingWriteFor, canReplayWrite, canClearWrite, clearPendingWrite, recoverWrite, selectP2Result, answerLabels, questionLabels, stateLabels, gapLabel, readBinding, readIndex, readResult, readMaterial, readSummary, resultPageUrl, prepareWrite, submitWrite, materialBytes, type Binding, type Result, type ResultIndex, type Question, type PendingWrite, type Material, type AnswerCode, type ResourceResult, type Use } from '../services/p2';
import { readPreliminaryAdvice, type PreliminaryAdvice, type PreliminaryUse } from '../services/preliminaryAdvice';
import './P2Workbench.css';
import { readPendingUsageUpdate } from '../services/projectUsage';
import { ProjectUsageEditor } from './ProjectUsageEditor';
import { AutomaticProjectAssessment } from './AutomaticProjectAssessment';
import { P2VersionComparison } from './P2VersionComparison';
import { P2AiAnalysis } from './P2AiAnalysis';
import { OfficialSources } from './OfficialSources';
import { officialSourcesEnabled } from '../services/officialSources';
import { p2AiEnabled } from '../services/p2Ai';
import { selectBoundSavedAdvice, sameBinding } from '../services/p2';
import { EvaluationPackageButton } from './EvaluationPackageButton';
import { ActionButton, Checkbox, DownloadGlyph, LoadingDots } from './ui';

const questionHelp = {DELIVERY_SCOPE_FOR_RESOURCES:'只勾选本次回答明确覆盖的资源；未勾选资源继续保持未知。',OBLIGATION_FULFILLMENT_IN_DELIVERY:'这是一项使用者声明，不会自动把正式义务标记为已履行。'};

type MaterialWritePermit = { isCurrent:()=>boolean; consume:()=>boolean };
const materialScopeFor=(a:Assessment,b:Binding|null,r:Result|null)=>JSON.stringify([a.scan_id,a.id,a.version,b,r?.result_id??null,r?.revision??null,r?.result_sha256??null]);

function navigateAssessmentSection(event:MouseEvent<HTMLAnchorElement>,id:string){
 if(event.defaultPrevented||event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
 const target=document.getElementById(id);if(!target)return;
 event.preventDefault();
 // Same-document reading navigation must not reset the pinned Result or trigger route scroll restoration.
 window.history.replaceState(window.history.state,'',window.location.pathname+window.location.search+'#'+id);
 target.focus({preventScroll:true});
 target.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});
}

export function P2Workbench({assessment:a,scan,readOnly=false}:{assessment:Assessment;scan:Scan;readOnly?:boolean}) {
 const [binding,setBinding]=useState<Binding|null>(null);
 const [index,setIndex]=useState<ResultIndex|null>(null);
 const [result,setResult]=useState<Result|null>(null);
 const [loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [reload,setReload]=useState(0),[tab,setTab]=useState<'result'|'answer'|'material'>('result');
 const [supplementOpen,setSupplementOpen]=useState(false);
 const [usagePending,setUsagePending]=useState(()=>{try{return !!readPendingUsageUpdate(a);}catch{return true;}});
 const [pending,setPending]=useState<PendingWrite|null>(()=>pendingWriteFor(a)),[lastMaterial,setLastMaterial]=useState<Material|null>(null);
 const [lastMaterialResultId,setLastMaterialResultId]=useState<string|null>(null);
 const [inspectedMaterial,setInspectedMaterial]=useState<{value:Material;scope:string;epoch:number}|null>(null),[materialReadError,setMaterialReadError]=useState('');
 const materialReadController=useRef<AbortController|null>(null),materialReadAuthority=useRef({scope:'',epoch:0,mounted:false});
 // Switching away must not attach an old material receipt to another page;
 // switching back restores the original Service pending identity, not a new key.
 useEffect(()=>{setPending(pendingWriteFor(a));setLastMaterial(null);setNotice('');},[a.scan_id,a.id,a.version]);
 const [resourceSearch,setResourceSearch]=useState('');
 const [officialBusy,setOfficialBusy]=useState(false),[automaticAnalysisId,setAutomaticAnalysisId]=useState<string|null>(null);
 useEffect(()=>{setOfficialBusy(false);setAutomaticAnalysisId(null);},[a.scan_id,a.id,a.version,result?.result_id]);
 const [preliminary,setPreliminary]=useState<PreliminaryAdvice|null>(null),[preliminaryError,setPreliminaryError]=useState(''),[preliminaryLoading,setPreliminaryLoading]=useState(false);
 useEffect(()=>{
  // Saved Result state may still belong to the previous Assessment until its
  // fixed read settles. Never dispatch a derived GET across that parent boundary.
  const belongsToAssessment=!!result&&result.binding.scan_id===a.scan_id&&result.binding.assessment_id===a.id&&result.binding.assessment_version===a.version;
  const c=new AbortController();setPreliminary(null);setPreliminaryError('');setPreliminaryLoading(belongsToAssessment);
  if(result&&belongsToAssessment)void readPreliminaryAdvice(a,result,c.signal).then(v=>{if(!c.signal.aborted)setPreliminary(v);}).catch(e=>{if(!c.signal.aborted)setPreliminaryError(e instanceof Error?e.message:'初评读取失败。');}).finally(()=>{if(!c.signal.aborted)setPreliminaryLoading(false);});
  return()=>c.abort();
 },[a.scan_id,a.id,a.version,result?.result_id]);
 const [errorStatus,setErrorStatus]=useState<number|null>(null),[downloadBusy,setDownloadBusy]=useState(false);
 const alive=useRef(true),lock=useRef(false);
 useEffect(()=>{const warn=(e:BeforeUnloadEvent)=>{if(pending){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);},[pending]);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 const currentHead=!!result&&index?.head_result_id===result.result_id;
 const editable=!usagePending&&!readOnly&&!busy&&!officialBusy&&!loading&&!!binding&&currentHead&&!pending;
 const materialScope=materialScopeFor(a,binding,result);
 // GET cancellation owns only inspection state; it never cancels a sent POST or clears its receipt.
 // Commit-time epochs also reject A→B→A late reads; abandoned renders do not revoke authority.
 useLayoutEffect(()=>{
  const authority=materialReadAuthority.current;authority.scope=materialScope;authority.epoch++;authority.mounted=true;
  materialReadController.current?.abort();materialReadController.current=null;setInspectedMaterial(null);setMaterialReadError('');
  return()=>{authority.mounted=false;authority.epoch++;materialReadController.current?.abort();materialReadController.current=null;};
 },[materialScope]);
 const materialEligible=editable&&!!binding&&!!result&&binding.scan_id===a.scan_id&&binding.assessment_id===a.id&&binding.assessment_version===a.version&&sameBinding(binding,result.binding);
 const materialAuthority=useRef({scope:'',epoch:0,mounted:false,eligible:false});
 // Only committed identity/permission changes revoke a lease. Abandoned renders
 // cannot revoke or restore it; an ABA change never revives an earlier epoch.
 useLayoutEffect(()=>{
  const state=materialAuthority.current;state.scope=materialScope;state.epoch++;state.mounted=true;state.eligible=materialEligible&&!readOnly;
  return()=>{state.mounted=false;state.eligible=false;state.epoch++;};
 },[materialScope,readOnly,materialEligible]);
 function acquireMaterialPermit():MaterialWritePermit|null{
  const state=materialAuthority.current,epoch=state.epoch,scope=materialScope;let consumed=false;
  const isCurrent=()=>!consumed&&state.mounted&&state.eligible&&state.scope===scope&&state.epoch===epoch;
  if(!isCurrent())return null;
  return {isCurrent,consume:()=>{if(!isCurrent())return false;consumed=true;return true;}};
 }
 const resourceName=(id:string)=>scan.resources.find(r=>r.id===id)?.name??a.resource_evaluations?.find(r=>r.resource_id===id)?.name??'当前资源';
 const pin=(r:Result)=>{const u=new URL(window.location.href);u.searchParams.set('assessment_id',a.id);u.searchParams.set('p2_result',r.result_id);u.searchParams.delete('p2_result_id');u.searchParams.delete('p2_revision');u.searchParams.set('assessment_version',String(a.version));window.history.replaceState(null,'',u.pathname+u.search);};
 function showError(e:unknown,write=false){const code=e instanceof ApiError?e.code:null;setErrorStatus(e instanceof ApiError?e.status:null);setError(e instanceof ApiError?(e.status===409?'结果已变化或提交发生冲突。原结果保留，请读取当前版本，再明确下一次操作。':e.status===503?'服务当前不可写或暂不可用。已保存记录保留；请先重新读取结果。':`提交未被接受（HTTP ${e.status}）。请核对对象、版本和材料。`)+(code?` [${code}]`:''):write?'提交结果尚未确认，可能已保存。请先读取当前版本；需要重发时使用下方同一请求。':e instanceof Error?e.message:'结果读取未完成。');}
 useEffect(()=>{
  const c=new AbortController();setLoading(true);setError('');setErrorStatus(null);
  (async()=>{try{
   const [b,i]=await Promise.all([readBinding(a,c.signal),readIndex(a,c.signal)]);
   const selection=selectP2Result(new URLSearchParams(window.location.search),a.version);
   const chosen=selection?.id||i.head_result_id;
   const r=chosen?await readResult(a,b,chosen,c.signal):null;
   if(selection?.revision!==null&&selection?.revision!==undefined&&r?.revision!==selection.revision)throw Error('固定结果版本不匹配，不替换为最新版本。');
   if(c.signal.aborted)return;setBinding(b);setIndex(i);setResult(r);if(r)pin(r);
  }catch(e){if(!c.signal.aborted)showError(e);}finally{if(!c.signal.aborted)setLoading(false);}})();
  return()=>c.abort();
 },[a.id,a.version,reload]);
 async function submit(p:PendingWrite,materialContext?:string){
  if(readOnly||lock.current||!binding)return;lock.current=true;setBusy(true);setError('');setErrorStatus(null);setNotice('');setPending(p);
  // A sent request is still consumed by the original Service. A different
  // target must not receive its UI success/Result; readonly alone is no rollback.
  const onMaterialTarget=(scope=materialContext)=>!scope||(materialAuthority.current.mounted&&materialAuthority.current.scope===scope);
  const detachMaterialPending=()=>{if(materialContext&&alive.current)setPending(current=>current===p?null:current);};
  try{const receipt=await submitWrite(a,binding,p);if(!alive.current||!onMaterialTarget()){detachMaterialPending();return;}
   setResult(receipt.result);pin(receipt.result);setLastMaterial(receipt.material);setLastMaterialResultId(receipt.result.result_id);setPending(null);setTab('result');setSupplementOpen(false);
   setNotice(`已保存独立结果第 ${receipt.result.revision} 版。${receipt.material?'材料已绑定为未核验观察；许可适用性仍待审核。':receipt.answer?'回答已记录；其余资源和原正式评估保持原状态。':'这是确定性材料与用途核对结果，未调用模型。'}`);
   setIndex(i=>({head_result_id:receipt.result.result_id,head_revision:receipt.result.revision,result_ids:[receipt.result.result_id,...(i?.result_ids??[]).filter(x=>x!==receipt.result.result_id)],has_more:i?.has_more??false}));
   // Saving succeeded even if this subsequent pure read fails.
   const receiptScope=materialScopeFor(a,binding,receipt.result);
   const onReceiptTarget=()=>!materialContext||onMaterialTarget()||onMaterialTarget(receiptScope);
   try{const next=await readIndex(a);if(alive.current&&onReceiptTarget())setIndex(next);}catch{if(alive.current&&onReceiptTarget())setNotice(n=>n+' 当前列表暂未刷新，可通过本页精确链接读取已保存结果。');}
  }catch(e){if(alive.current&&onMaterialTarget())showError(e,true);else detachMaterialPending();}finally{lock.current=false;if(alive.current)setBusy(false);}
 }
 function write(operation:PendingWrite['operation'],extra:Record<string,unknown>={},materialPermit?:MaterialWritePermit){
  if(!binding||pending||busy||officialBusy||usagePending||readOnly)return false;
  // No await between this one-shot check, fixed CAS/key preparation and POST.
  if(operation==='materials'&&(lock.current||!materialPermit?.consume()))return false;
  void submit(prepareWrite(operation,binding,result,crypto.randomUUID(),extra),operation==='materials'?materialScope:undefined);return true;
 }
 async function refreshHead(){if(!binding||busy)return;setLoading(true);setError('');try{const recovered=pending?await recoverWrite(a,binding,pending):null;const i=recovered?.index??await readIndex(a);const r=recovered?recovered.result:i.head_result_id?await readResult(a,binding,i.head_result_id):null;if(!alive.current)return;setIndex(i);setResult(r);if(r)pin(r);setNotice('已只读获取当前版本；不会自动重发提交。');}catch(e){if(alive.current)showError(e);}finally{if(alive.current)setLoading(false);}}
 async function inspectMaterial(id:string){
  if(!binding||!result||!sameBinding(binding,result.binding)||binding.scan_id!==a.scan_id||binding.assessment_id!==a.id||binding.assessment_version!==a.version)return;
  const authority=materialReadAuthority.current,scope=materialScope,epoch=authority.epoch;
  if(!authority.mounted||authority.scope!==scope)return;
  materialReadController.current?.abort();const controller=new AbortController();materialReadController.current=controller;
  setInspectedMaterial(null);setMaterialReadError('');
  const current=()=>alive.current&&!controller.signal.aborted&&materialReadController.current===controller&&authority.mounted&&authority.scope===scope&&authority.epoch===epoch;
  try{const value=await readMaterial(a,binding,result,id,controller.signal);if(current())setInspectedMaterial({value,scope,epoch});}
  catch(e){if(current())setMaterialReadError(e instanceof Error?e.message:'材料读取失败；已保存结果保持不变。');}
  finally{if(materialReadController.current===controller)materialReadController.current=null;}
 }
 async function downloadSummary(){if(!result||downloadBusy)return;setDownloadBusy(true);try{const summary=await readSummary(a,result);if(!alive.current)return;const link=document.createElement('a');const url=URL.createObjectURL(new Blob([JSON.stringify(summary,null,2)],{type:'application/json'}));link.href=url;link.download=`OpenGuard-P2-summary-r${result.revision}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){if(alive.current)showError(e);}finally{if(alive.current)setDownloadBusy(false);}}
 const selectedUses=result?(Object.keys(usageFields) as Use[]).filter(k=>result.usage[k]===true):[];
 const unknownUses=result?(Object.keys(usageFields) as Use[]).filter(k=>result.usage[k]===null):[];
 const observedResources=result?.resources.filter(r=>r.material_ids.length)??[];
 const uniqueGaps=[...new Set((result?.resources??[]).flatMap(r=>r.gaps))];
 const displayedMaterial=inspectedMaterial&&inspectedMaterial.scope===materialScope&&inspectedMaterial.epoch===materialReadAuthority.current.epoch?inspectedMaterial.value
  :lastMaterial&&lastMaterialResultId===result?.result_id&&result.material_ids.includes(lastMaterial.material_id)?lastMaterial:null;
 return <section className="p2-workbench" aria-label="用途与材料工作台">
  <div className="p2-identity-bar">
  <div className="p2-context"><span className="p2-context-label">已保存评估</span><span>用途版本 {a.version}{result?` · 材料结果 r${result.revision}`:''}</span>{result?.data_scope==='TEST_ONLY'&&<span>隔离验收数据</span>}</div>
  {result&&<nav className="p2-primary-next" aria-label="继续完善当前评估"><a href="#p2-optional-supplement" onClick={()=>{setSupplementOpen(true);setTab('answer');}}>修改用途并更新评估</a><a href="#p2-optional-supplement" onClick={()=>{setSupplementOpen(true);setTab('material');}}>补充 LICENSE / NOTICE</a><span>保存会形成新版本，旧版保持可读。</span></nav>}
  </div>
  {loading&&<LoadingDots label="正在读取当前对象的已保存结果…" />}
  {error&&<div className="p2-message p2-error" role="alert"><p>{error}</p><button disabled={busy||loading} onClick={()=>void refreshHead()}>读取当前版本</button></div>}
  {notice&&<p className="p2-message p2-success" role="status">{notice}</p>}
  {pending&&<div className="p2-message p2-pending"><strong>保留待确认的原请求</strong><p>请求键和请求内容均未改变。先读取结果；不确定是否送达时，可显式重发同一请求。不会自动重试。</p><div className="p2-actions"><button disabled={busy||loading} onClick={()=>void refreshHead()}>核对服务器已保存结果</button><button disabled={busy||loading||readOnly||!canReplayWrite(a)} onClick={()=>void submit(pending)}>使用原请求再次确认</button><button disabled={busy||loading||!canClearWrite(a)} onClick={()=>{clearPendingWrite(a);setPending(null);setError('');setNotice('已结束该请求的本地待确认状态；服务器旧结果保持不变。新操作将使用当前版本。');}}>结束待确认，准备新操作</button></div></div>}
  {!result&&!loading&&!error&&<div className="p2-main-card"><div className="p2-step">01 / 已完成扫描与正式评估</div><h2>从资源清单，进入用途与材料核对</h2><p>为当前评估生成独立结果，按资源查看用途依据、待确认范围和材料缺口。</p><p className="p2-muted">本次结果由确定性规则计算，保留来源证据；不调用 Qwen，也不会改变正式评估。</p><ActionButton className="p2-primary" aria-busy={busy} disabled={!binding||busy||readOnly||!!pending} onClick={()=>write('results')}>{busy?'正在保存…':'生成本次用途核对结果'}</ActionButton></div>}
  {result&&<>

   <nav className="p2-section-nav" aria-label="评估内容导航"><a href="#p2-overview" onClick={e=>navigateAssessmentSection(e,'p2-overview')}>评估概览</a><a href="#p2-actions" onClick={e=>navigateAssessmentSection(e,'p2-actions')}>本版行动</a><a href="#p2-sources" onClick={e=>navigateAssessmentSection(e,'p2-sources')}>材料与来源</a><a href="#p2-versions" onClick={e=>navigateAssessmentSection(e,'p2-versions')}>版本与导出</a></nav>
   <div id="p2-overview" tabIndex={-1} className={officialSourcesEnabled?"p2-mainline-panels":"p2-mainline-panels is-guide-only"}>
    <div className="p2-guide-column"><AutomaticProjectAssessment scan={scan} assessment={a} result={result}/></div>

   </div>

   <SavedAdviceMainCard assessment={a} binding={binding} result={result} scan={scan}/>
   {p2AiEnabled&&(!officialSourcesEnabled||result.material_ids.length>0)&&<P2AiAnalysis assessment={a} result={result} scan={scan} readOnly={readOnly} automatic={officialSourcesEnabled} automaticAnalysisId={automaticAnalysisId} disabled={loading||busy||officialBusy||!!pending||usagePending} onAddMaterial={()=>{setSupplementOpen(true);setTab('material');document.getElementById('p2-optional-supplement')?.scrollIntoView({behavior:'smooth',block:'start'});}}/>}
   <div id="p2-sources" tabIndex={-1} className="p2-source-section">{officialSourcesEnabled&&<div className="p2-official-column"><OfficialSources assessment={a} result={result} readOnly={readOnly} disabled={loading||busy||!!pending||usagePending||!currentHead} onAdoptingChange={setOfficialBusy} onReadSavedResult={()=>void refreshHead()} onAnalysisSaved={setAutomaticAnalysisId} onAdopt={receipt=>{setOfficialBusy(false);setResult(receipt.result);pin(receipt.result);setLastMaterial(receipt.material);setLastMaterialResultId(receipt.result.result_id);setNotice('已明确采用 LICENSE，保存新的待核验材料与结果；旧结果保持不变。辅助分析以实际保存状态为准。');setIndex(i=>({head_result_id:receipt.result.result_id,head_revision:receipt.result.revision,result_ids:[receipt.result.result_id,...(i?.result_ids??[]).filter(x=>x!==receipt.result.result_id)],has_more:i?.has_more??false}));}}/></div>}</div>
   {!currentHead&&<p className="p2-message p2-pending">正在查看不可变历史结果 r{result.revision}。写入仅允许当前版本。<button disabled={loading||busy} onClick={()=>void refreshHead()}>查看当前结果 r{index?.head_revision}</button></p>}
   {preliminaryError&&<p className="p2-message p2-error" role="alert">已有材料初评暂未读回：{preliminaryError} 已保存结果仍可查看。</p>}
   <details className="p2-detail p2-prior-evidence"><summary>查看已有材料初评与判断依据</summary>
    <div className="p2-main-card p2-advice-main"><div className="p2-step">用途初评 · 明确对象与条件</div>
     <h2>{preliminary?.supported_resource_ids.length?`${preliminary.supported_resource_ids.length} 个资源可有条件采用`:preliminaryLoading?'正在核对材料支持的用途范围':'先确定有依据的范围，再推进项目使用'}</h2>
     <p>{preliminary?.supported_resource_ids.length?'完整许可文本与精确发行版本已对应。以下是材料支持的资源级方案，未覆盖的依赖继续单独核对。':observedResources.length?'已保存的材料正在按对象、版本与完整条款核对。':'当前结果保留所有资源的证据；补入完整许可材料后，可形成相应资源的条件初评。'}</p>
     <div className="p2-metrics"><div><strong>{result.resources.length}</strong><span>纳入核对的资源</span></div><div><strong>{preliminary?.supported_resource_ids.length??0}</strong><span>已有条款支持</span></div><div><strong>{preliminary?.uncovered_resource_ids.length??result.resources.length}</strong><span>尚待补齐用途依据</span></div></div>
     <div className="p2-usage-cards">{selectedUses.length?selectedUses.map(k=>{const advice=preliminary?.advice.find(d=>d.usage===k);return <article key={k} className={advice?.resources.length?'has-basis':''}><h3>{usageFields[k]}</h3>{advice?<UseAdviceCard advice={advice}/>:<p>{preliminaryLoading?'正在读取服务端初评…':'补齐当前用途与资源的材料依据后，显示对应初评。'}</p>}</article>;}):<p>当前未明确选择用途。七项用途原值保留；未选择与尚未确定不视为许可通过。</p>}</div>
     {preliminary&&<p className="p2-scope-note">初评仅覆盖列明资源与版本，不代表整个项目已获许可；其余 {preliminary.uncovered_resource_ids.length} 个资源的依据缺口保留。</p>}
     {unknownUses.length>0&&<p className="p2-muted">另有 {unknownUses.length} 项用途未声明，可在完整用途中查看；不会自动补成“否”或“允许”。</p>}
    </div>
    {result.revision>1&&<div className="p2-change"><strong>本次增量：</strong>{result.recomputed_resource_ids.length} 个资源重新核对，{result.reused_resource_ids.length} 个资源复用旧结果。正式评估仍为 v{a.version}，历史结果可直接读回。</div>}
    <details className="p2-detail"><summary>查看逐资源判断依据 · {result.resources.length} 个资源</summary><label className="p2-resource-search">查找资源依据<input value={resourceSearch} onChange={e=>setResourceSearch(e.target.value)} placeholder="输入资源名称或版本，例如 chalk"/></label><div className="p2-resource-list">{result.resources.filter(r=>`${resourceName(r.subject.resource_id)} ${r.subject.version??''}`.toLowerCase().includes(resourceSearch.trim().toLowerCase())).map(r=><article key={r.subject.resource_id}><header><h3>{resourceName(r.subject.resource_id)} <small>{r.subject.version??'版本未知'}</small></h3><span>{stateLabels[r.state]}</span></header><p>{preliminary?.supported_resource_ids.includes(r.subject.resource_id)?'此资源已有完整材料支持的条件初评，详见上方用途卡片；正式适用性仍待审核。':r.inherited_local_support?'父评估保留该资源的既有局部支持；不是本次新增许可结论。':'该资源尚未形成可独立采用的用途许可结论。'}</p><ul>{[...new Set(r.gaps.map(gapLabel))].map(g=><li key={g}>{g}</li>)}</ul>{r.advice.filter(d=>d.state==='conditional_candidate').map(d=><div key={d.usage}><strong>{usageFields[d.usage]} · 资源级有条件候选</strong><ul>{d.conditions.map((v,i)=><li key={i}>{v}</li>)}</ul></div>)}<h4>依据来源</h4><ul>{r.evidence_ids.map(id=>{const e=scan.evidence.find(e=>e.id===id);return <li key={id}>{e?.label??'已绑定证据'}{e?.path&&e.path!==e.label?` · ${e.path}`:e?.url&&e.url!==e.label?` · ${e.url}`:''}</li>;})}</ul>{r.material_ids.length>0&&<div className="p2-actions">{r.material_ids.map((id,i)=><button key={id} onClick={()=>void inspectMaterial(id)}>读取已存材料 {i+1}</button>)}</div>}<details><summary>技术身份与原始缺口码</summary><code>{r.subject.resource_id}</code><pre>{JSON.stringify({gaps:r.gaps,evidence_ids:r.evidence_ids,material_ids:r.material_ids,answer_ids:r.answer_ids,user_assertions:r.user_assertions},null,2)}</pre></details></article>)}</div></details>
    <details className="p2-detail"><summary>覆盖缺口与完整用途</summary><p>扫描状态：{scan.status==='partial'?'部分完成（缺口保留）':scan.status==='completed'?'扫描已完成':'见扫描任务状态'}。共 {uniqueGaps.length} 类后端缺口。</p><ul>{[...new Set(uniqueGaps.map(gapLabel))].map(g=><li key={g}>{g}</li>)}</ul><dl className="p2-usage-values">{(Object.keys(usageFields) as Use[]).map(k=><div key={k}><dt>{usageFields[k]}</dt><dd>{result.usage[k]===true?'是':result.usage[k]===false?'否（本次未选择）':'未知'}</dd></div>)}</dl></details>
   </details>
   <details id="p2-optional-supplement" className="p2-detail p2-optional" open={supplementOpen} onToggle={e=>{const open=e.currentTarget.open;setSupplementOpen(open);if(!open)setTab('result');else if(tab==='result')setTab('answer');}}><summary>补充信息，让评估更具体（可选）</summary>
    {<>
     <p className="p2-optional-intro">可跳过；可直接阅读已有扫描与评估结果，补充项目实际情况可提高针对性。</p>
     <div className="p2-optional-actions" aria-label="选择可选补充内容"><button className={tab==='answer'?'is-active':''} aria-pressed={tab==='answer'} onClick={()=>setTab('answer')}>补充项目用途</button><button className={tab==='material'?'is-active':''} aria-pressed={tab==='material'} onClick={()=>setTab('material')}>补充 LICENSE / NOTICE</button><button className="p2-return-result" onClick={()=>{setSupplementOpen(false);setTab('result');}}>返回评估结果</button></div>
   <div hidden={tab!=='answer'}><ProjectUsageEditor assessment={a} readOnly={readOnly} disabled={busy||officialBusy||loading||!!pending} onPendingChange={setUsagePending}/><details className="project-usage-advanced"><summary>高级补充：逐资源交付与声明履行（可选）</summary><section className="p2-main-card"><div className="p2-step">高级补充 · 资源级声明</div><h2>需要精确到个别组件时再填写</h2><p>系统已按当前资源整理为 {result.questions.length} 个问题。每次回答明确覆盖对象；未选中的对象继续未知。</p>{result.questions.length?result.questions.map(q=><AnswerForm key={result.result_id+q.question_id} question={q} result={result} disabled={!editable} resourceName={resourceName} onSubmit={extra=>write('answers',extra)}/>):<p>当前结果没有待回答问题，仍可补充与资源绑定的材料。</p>}</section></details></div>
   {tab==='material'&&<section className="p2-main-card"><div className="p2-step">可选补充 · 本地完整材料</div><h2>把材料绑定到准确资源与版本</h2><p>仅接受 UTF-8 的 LICENSE / LICENCE / NOTICE 小文本，每份最多 64 KiB。文件不会被执行，也不会自动套用于其他依赖。</p><MaterialForm key={result.result_id} result={result} scan={scan} disabled={!editable} acquirePermit={acquireMaterialPermit} onSubmit={(extra,permit)=>write('materials',extra,permit)}/></section>}
    </>}
   </details>
   {materialReadError&&<p className="p2-message p2-error" role="alert">材料读取未完成：{materialReadError} 已保存结果保持不变。</p>}
   {displayedMaterial&&<div className="p2-message p2-success" data-material-inspection><strong>{displayedMaterial.filename} · 已绑定并保存</strong><p>{resourceName(displayedMaterial.subject.resource_id)} @ {displayedMaterial.subject.version} · {displayedMaterial.byte_count.toLocaleString()} 字节 · 许可适用性待核验</p><details><summary>材料完整性与身份</summary><p>SHA256：<code>{displayedMaterial.source_sha256}</code></p><p>Material：<code>{displayedMaterial.material_id}</code></p><p>{displayedMaterial.completeness==='EXCERPT'?'片段：完整性缺口保留':'用户声明为完整原文，尚未独立签认'}</p></details></div>}
   <div id="p2-versions" tabIndex={-1} className="p2-section-heading"><h2>版本与导出</h2><p>对照本次变化，保存准确版本的结果与材料。</p></div>
   <EvaluationPackageButton assessment={a} result={result}/>
   {binding&&<P2VersionComparison key={materialScope} assessment={a} binding={binding} current={result} resourceName={resourceName}/>}
   <details className="p2-detail p2-history"><summary>已保存版本与下载 · 当前查看 r{result.revision}</summary><p>独立结果与原正式评估分别保存；刷新精确链接不会重新生成。</p><div className="p2-actions"><a className="p2-link" href={resultPageUrl(a,result.result_id)}>本版固定链接</a><button className="og-download-button" disabled={downloadBusy} aria-busy={downloadBusy} onClick={()=>void downloadSummary()}><DownloadGlyph /><span>{downloadBusy?'正在读取…':'下载本版材料核对摘要'}</span></button><a className="og-download-button" download href={assessmentReportUrl(a.scan_id,a.id,'html')}><DownloadGlyph /><span>原正式评估 HTML</span></a><a className="og-download-button" download href={assessmentReportUrl(a.scan_id,a.id,'json')}><DownloadGlyph /><span>原正式评估 JSON</span></a></div><p className="p2-muted">材料核对摘要为 P2 companion，不能替代正式评估报告。</p><ol>{index?.result_ids.map(id=><li key={id}><a href={resultPageUrl(a,id)}>{id===result.result_id?'当前查看的结果':id===index.head_result_id?'最新保存的结果':'历史不可变结果'} · <code>{id.slice(0,22)}…</code></a></li>)}</ol>{index?.has_more&&<button disabled={loading} onClick={()=>{void readIndex(a,undefined,index.result_ids.length).then(next=>setIndex(i=>i?{...next,result_ids:[...new Set([...i.result_ids,...next.result_ids])]}:next)).catch(showError);}}>读取更早结果</button>}<details><summary>完整绑定信息</summary><pre>{JSON.stringify({result_id:result.result_id,revision:result.revision,result_sha256:result.result_sha256,binding:result.binding},null,2)}</pre></details></details>
  </>}
  <p className="p2-boundary">已有材料初评采用完整材料与固定规则；自动整体评估的来源见上方说明。用户声明、材料观察与初评均独立于正式评估，不代表授权确认。</p>
 </section>;
}

function AnswerForm({question:q,result,disabled,resourceName,onSubmit}:{question:Question;result:Result;disabled:boolean;resourceName:(id:string)=>string;onSubmit:(extra:Record<string,unknown>)=>void}){
 const [answer,setAnswer]=useState<AnswerCode|''>(''),[selected,setSelected]=useState<string[]>([]),[search,setSearch]=useState('');
 const visible=q.subjects.filter(s=>(resourceName(s.resource_id)+' '+(s.version??'')+' '+s.resource_id).toLowerCase().includes(search.toLowerCase()));
 const saved=q.subjects.filter(s=>result.resources.find(r=>r.subject.resource_id===s.resource_id)?.user_assertions[q.question_code]);
 return <form className="p2-question" onSubmit={e=>{e.preventDefault();if(disabled||!answer||!selected.length)return;onSubmit({question_id:q.question_id,question_code:q.question_code,answer_code:answer,subjects:q.subjects.filter(s=>selected.includes(s.resource_id)),evidence_ids:[]});}}><h3>{questionLabels[q.question_code]}</h3><p>{questionHelp[q.question_code]}</p>{saved.length>0&&<p className="p2-saved-note">此问题已有 {saved.length} 个资源的用户声明；新回答不会抹掉历史结果。</p>}<fieldset disabled={disabled}><legend>选择本次回答覆盖的资源（{selected.length} / {q.subjects.length}）</legend><input className="p2-search" aria-label={"在问题中查找资源："+questionLabels[q.question_code]} value={search} onChange={e=>setSearch(e.target.value)} placeholder="按名称或版本查找资源…"/><div className="p2-subjects">{visible.map(s=><Checkbox compact key={s.resource_id} checked={selected.includes(s.resource_id)} onChange={e=>setSelected(v=>e.target.checked?[...v,s.resource_id]:v.filter(id=>id!==s.resource_id))}><span>{resourceName(s.resource_id)}<small>{s.version??'版本未知'}</small></span></Checkbox>)}</div><div className="p2-actions"><button type="button" onClick={()=>setSelected(q.subjects.map(s=>s.resource_id))}>明确选择全部 {q.subjects.length} 个资源</button><button type="button" onClick={()=>setSelected([])}>清空选择</button></div><div className="p2-answer-options">{q.options.map(option=><label key={option}><input type="radio" name={q.question_id} checked={answer===option} onChange={()=>setAnswer(option)}/>{answerLabels[option]}</label>)}</div><ActionButton kind="send" className="p2-primary" disabled={!answer||!selected.length} type="submit">保存回答并生成新版本</ActionButton></fieldset></form>;
}
function MaterialForm({result,scan,disabled,acquirePermit,onSubmit}:{result:Result;scan:Scan;disabled:boolean;acquirePermit:()=>MaterialWritePermit|null;onSubmit:(extra:Record<string,unknown>,permit:MaterialWritePermit)=>boolean}){
 const [resourceId,setResourceId]=useState(''),[evidenceIds,setEvidenceIds]=useState<string[]>([]),[file,setFile]=useState<File|null>(null),[description,setDescription]=useState(''),[completeness,setCompleteness]=useState<'FULL_TEXT_CLAIMED'|'EXCERPT'>('FULL_TEXT_CLAIMED'),[error,setError]=useState(''),[reading,setReading]=useState(false);
 const lifetime=useRef({mounted:false,epoch:0});
 useLayoutEffect(()=>{const state=lifetime.current;state.mounted=true;state.epoch++;return()=>{state.mounted=false;state.epoch++;};},[]);
 const row=result.resources.find(r=>r.subject.resource_id===resourceId);
 const eligible=(r:ResourceResult)=>!!r.subject.version&&/^\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?$/.test(r.subject.version)&&r.evidence_ids.length>0;
 async function submit(e:React.FormEvent<HTMLFormElement>){
  e.preventDefault();if(disabled||reading||!row||!file||!description.trim()||!evidenceIds.length)return;
  const permit=acquirePermit(),localEpoch=lifetime.current.epoch;
  if(!permit||!lifetime.current.mounted){setError('当前对象或写入许可已变化；材料尚未发送，请核对后重新选择提交。');return;}
  const form=e.currentTarget;form.setAttribute('aria-busy','true');setReading(true);setError('');
  try{
   const data=await materialBytes(file);
   if(!lifetime.current.mounted||lifetime.current.epoch!==localEpoch||!permit.isCurrent()){
    if(form.isConnected)setError('材料读取期间对象或写入许可已变化；本次材料未发送，请核对后明确重新提交。');return;
   }
   const dispatched=onSubmit({subject:row.subject,evidence_ids:evidenceIds,filename:data.filename,content_base64:data.content_base64,source_sha256:data.source_sha256,source_description:description.trim(),completeness},permit);
   if(!dispatched&&form.isConnected)setError('当前对象或写入许可已变化；本次材料未发送，请核对后明确重新提交。');
  }catch(e){if(form.isConnected)setError(e instanceof Error?e.message:'材料读取失败');}
  finally{
   // This is file-processing settlement, not a server-save success signal.
   // The captured node also settles accessibly if it has since been detached.
   form.setAttribute('aria-busy','false');if(form.isConnected)setReading(false);
  }
 }
 return <form className="p2-material-form" onSubmit={e=>void submit(e)}><fieldset disabled={disabled||reading}><label>目标资源与精确版本<select required value={resourceId} onChange={e=>{setResourceId(e.target.value);setEvidenceIds([]);setError('');}}><option value="">请选择材料所属资源</option>{result.resources.map(r=><option key={r.subject.resource_id} value={r.subject.resource_id} disabled={!eligible(r)}>{scan.resources.find(x=>x.id===r.subject.resource_id)?.name??r.subject.resource_id} @ {r.subject.version??'版本未确定'}{!eligible(r)?'（需先确认精确版本与证据）':''}</option>)}</select></label>{row&&<fieldset><legend>明确关联当前资源证据</legend><div className="p2-subjects">{row.evidence_ids.map(id=><Checkbox compact key={id} checked={evidenceIds.includes(id)} disabled={!evidenceIds.includes(id)&&evidenceIds.length>=100} onChange={e=>setEvidenceIds(v=>e.target.checked?[...v,id]:v.filter(x=>x!==id))}><span>{scan.evidence.find(e=>e.id===id)?.label??'已绑定证据'}<small>{scan.evidence.find(e=>e.id===id)?.path??id}</small></span></Checkbox>)}</div></fieldset>}<label>LICENSE / NOTICE 原文件<input type="file" accept=".txt,.md,.rst,text/plain" onChange={e=>{setFile(e.target.files?.[0]??null);setError('');}}/></label>{file&&<p>{file.name} · {file.size.toLocaleString()} 字节（提交前计算原字节 SHA256，不截断）</p>}<label>来源说明<input required maxLength={512} value={description} onChange={e=>setDescription(e.target.value)} placeholder="例如：官方发行包 package/LICENSE；请填写实际来源"/></label><label>材料完整性<select value={completeness} onChange={e=>setCompleteness(e.target.value as typeof completeness)}><option value="FULL_TEXT_CLAIMED">我提交的是完整原文（仍待独立审核）</option><option value="EXCERPT">仅提交片段（保留完整性缺口）</option></select></label><ActionButton kind="send" className="p2-primary" type="submit" aria-busy={reading} disabled={!row||!eligible(row)||!file||!description.trim()||!evidenceIds.length}>{reading?'正在核对文件…':'绑定材料并生成新版本'}</ActionButton></fieldset>{error&&<p className="p2-error" role="alert">{error}</p>}<p className="p2-muted">根目录的 LICENSE 不自动覆盖所有依赖。材料只绑定所选资源及该精确版本。</p></form>;
}


function SavedAdviceMainCard({assessment,binding,result,scan}:{assessment:Assessment;binding:Binding|null;result:Result;scan:Scan}){
 const {rows,notices,usage_hash_assurance}=selectBoundSavedAdvice(assessment,binding,result,scan);
 const noticeText={
  BINDING_OR_USAGE_MISMATCH:'当前保存结果与评估或用途绑定未核对一致；请重新读取准确版本，现有结果保持不变。',
  SOURCE_REVISION_UNESTABLISHED:'当前来源没有可独立核对的版本标识；一致的空值不证明精确来源，请核对输入归档身份与文件范围。',
  SOURCE_REVISION_MISMATCH:'当前扫描与保存结果的来源版本不一致；请核对准确输入，暂不展示条件建议。',
  RESOURCE_BINDING_MISMATCH:'当前资源身份或准确版本未核对一致；请查看逐资源依据并核对原始输入。',
  BASIS_INCOMPLETE:'已有保存条件的依据登记尚不完整；请核对逐资源依据及材料身份，暂不作许可肯定判断。',
  BASIS_INDIRECT_UNCONFIRMED:'已有保存的条件依据，其中间接来源尚未完成当前视图的独立关联核验；可查看逐资源依据。',
  NO_SAVED_CONDITIONAL:'当前版本没有可展示的已保存条件候选。请核实该组件是否包含在实际发布文件中，并补齐准确版本、用途和材料依据。',
 };
 return <section id="p2-actions" tabIndex={-1} className="p2-main-card" data-bound-advice-maincard="" data-result-id={result.result_id} data-result-revision={result.revision} aria-label="已保存条件建议">
  <div className="p2-step">本版行动</div><h2>已保存的条件与下一步</h2>
  <p className="p2-advice-intro">以下内容来自本版保存结果，按资源与用途核对；缺失的依据继续保留。</p>
  <details className="p2-inline-boundary"><summary>本版建议的依据与边界</summary><p>仅展示本版结果中已保存且能对应资源、用途和直接依据的条件；关联未核清时说明具体缺口，不新增许可判断。来源真实性、实际适用范围与义务履行仍须核对。</p></details>
  {result.data_scope==='TEST_ONLY'&&<p className="p2-muted">隔离验证数据，不代表真实业务建议。</p>}
  {rows.map(row=><article key={row.subject.resource_id+':'+row.usage} data-bound-advice-resource={row.subject.resource_id}>
   <h3>{row.name} @ {row.subject.version} · {usageFields[row.usage]}</h3><p>已保存的资源级有条件候选</p>
   <ul>{row.conditions.map((condition,i)=><li key={i}>{condition}</li>)}</ul>
   {(row.advice_gaps.length>0||row.resource_gaps.length>0)&&<div><strong>仍需核对</strong><ul>{[...row.advice_gaps,...row.resource_gaps].map((gap,i)=><li key={i}>{gapLabel(gap)}</li>)}</ul></div>}
   <details><summary>本条保存身份与依据</summary><pre>{JSON.stringify({result_id:result.result_id,revision:result.revision,result_sha256:result.result_sha256,subject:row.subject,usage:row.usage,basis_evidence_ids:row.basis_evidence_ids,rule_ids:row.rule_ids},null,2)}</pre></details>
  </article>)}
  {notices.map((notice,i)=><div key={i}><p data-bound-advice-neutral="" data-bound-advice-notice={notice.code}>{noticeText[notice.code]}</p>{notice.subject&&<details><summary>本项保存身份</summary><pre>{JSON.stringify({result_id:result.result_id,revision:result.revision,subject:notice.subject,usage:notice.usage},null,2)}</pre></details>}</div>)}
  {usage_hash_assurance&&<details data-bound-advice-assurance={usage_hash_assurance}><summary>用途绑定核对方式</summary><p>{usage_hash_assurance==='PARENT_FIELD_MATCH'?'已比对父评估登记的用途Hash、现有绑定和七项用途值，未独立重算父用途Hash。':'父评估未提供用途Hash字段；仅依据现有九字段绑定、固定结果与七项用途值一致性核对，未独立重算父用途Hash。'}</p></details>}
  <p className="p2-muted">未列出的资源或用途继续保留缺口。间接依据仍可在原逐资源明细核对；材料待核验不等于许可已接纳。</p>
 </section>;
}

function UseAdviceCard({advice}:{advice:PreliminaryUse}){
 return <><strong className="p2-advice-state">{advice.state==='CONDITIONAL_TEXT_BASIS'?'有条件适用 · 限已列明资源':'当前范围仍需补证'}</strong><p>{advice.summary}</p>
 {advice.resources.map(r=><div className="p2-supported-resource" key={r.subject.resource_id}><div className="p2-supported-name">{r.name} <span>@ {r.subject.version}</span></div><p>{r.recommendation}</p><ul className="p2-conditions">{r.conditions.map(c=><li key={c}>{c}</li>)}</ul>
 <details className="p2-advice-basis"><summary>查看初评依据与剩余不确定性</summary><h4>真实来源</h4>{r.source_urls.map(url=><a key={url} href={url} target="_blank" rel="noreferrer">{url.includes('/-/')?'官方 npm 发行包':'官方 npm 精确版本记录'}</a>)}<p>已上传完整 LICENSE，与该发行版本中的原文字节匹配。</p><h4>仍需确认</h4><ul>{r.limitations.map(x=><li key={x}>{x}</li>)}</ul><details><summary>技术详情</summary><pre>{JSON.stringify({subject:r.subject,material_ids:r.material_ids,material_sha256:r.material_sha256,evidence_ids:r.evidence_ids,rule_id:r.rule_id},null,2)}</pre></details></details></div>)}
 </>;
}
