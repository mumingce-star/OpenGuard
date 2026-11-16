import { useEffect, useRef, useState, type FormEvent } from 'react';
import type { Scan } from '../types/domain';
import { listAssessments, readExactAssessment, usageFields, type Assessment } from '../services/assessments';
import { readBinding, readIndex, readResult, resultPageUrl, type Result } from '../services/p2';
import { readProjectChat, prepareChatQuestion, sendProjectQuestion, chatFailureMessage, type ProjectChat as ChatData, type ChatBasis } from '../services/projectChat';
import { usageTitle } from '../services/usageExperience';
import './ProjectChat.css';

const prompts=['这个项目主要做什么？结合我当前的用途，下一步应该做什么？','已补充的材料支持了哪些判断，还有什么没有确认？','请用通俗语言解释当前用途下需要注意的条件，并给出依据。'];
export function ProjectChat({scan,query,go}:{scan:Scan;query:URLSearchParams;go:(url:string)=>void}) {
 const [assessments,setAssessments]=useState<Assessment[]>([]),[assessment,setAssessment]=useState<Assessment|null>(null);
 const [results,setResults]=useState<Result[]>([]),[result,setResult]=useState<Result|null>(null),[chat,setChat]=useState<ChatData|null>(null);
 const [loading,setLoading]=useState(true),[error,setError]=useState(''),[sending,setSending]=useState(false),[uncertain,setUncertain]=useState(false);
 const [question,setQuestion]=useState(''),[selectedBasis,setSelectedBasis]=useState<ChatBasis|null>(null),[refresh,setRefresh]=useState(0);
 const [historyOpen,setHistoryOpen]=useState(()=>typeof window==='undefined'||window.matchMedia('(min-width: 901px)').matches);
 const composerInput=useRef<HTMLTextAreaElement>(null);
 const pinned=useRef<{scanId:string;assessmentId:string;resultId:string}|null>(null);
 const epoch=useRef(0),sendLock=useRef(false),scope=useRef(''),bottom=useRef<HTMLDivElement>(null),basisPanel=useRef<HTMLElement>(null);
 const aid=query.get('assessment_id')??'',rid=query.get('p2_result')??'';
 const pageUrl=(a:string,r?:string)=>`/app/scans/${encodeURIComponent(scan.id)}/chat?`+new URLSearchParams({mode:'api',assessment_id:a,...(r?{p2_result:r}:{})});
 useEffect(()=>{
  const turn=++epoch.current,controller=new AbortController();scope.current='';sendLock.current=false;
  setLoading(true);setError('');setAssessment(null);setResult(null);setChat(null);setResults([]);setQuestion('');setSending(false);setUncertain(false);setSelectedBasis(null);
  async function load(){
   if(scan.mode!=='api')throw new Error('项目问答需要真实已保存的项目结果，请选择接口模式下的任务。');
   const listing=await listAssessments(scan.id,controller.signal);
   const pinnedHere=pinned.current?.scanId===scan.id?pinned.current:null;
   const chosenAssessment=aid||pinnedHere?.assessmentId;
   const a=chosenAssessment?await readExactAssessment(scan.id,chosenAssessment,controller.signal):listing.items[0];
   if(!a)throw new Error('当前项目尚无保存的用途评估，请先到项目评估页完成保存。');
   const b=await readBinding(a,controller.signal),index=await readIndex(a,controller.signal);
   const selectedId=rid||(pinnedHere?.assessmentId===a.id?pinnedHere.resultId:null)||index.head_result_id;
   if(!selectedId)throw new Error('当前用途版本尚无保存结果，请先到项目评估页查看并保存结果。');
   const r=await readResult(a,b,selectedId,controller.signal);
   const history=await Promise.all(index.result_ids.slice(0,30).filter(id=>id!==r.result_id).map(id=>readResult(a,b,id,controller.signal)));
   const data=await readProjectChat(a,r,controller.signal);
   if(controller.signal.aborted||turn!==epoch.current)return;
   setAssessments([a,...listing.items.filter(x=>x.id!==a.id)].sort((x,y)=>y.version-x.version));
   pinned.current={scanId:scan.id,assessmentId:a.id,resultId:r.result_id};
   setAssessment(a);setResults([r,...history].sort((x,y)=>y.revision-x.revision));setResult(r);setChat(data);scope.current=a.id+':'+r.result_id;
   // Pin the exact objects once resolved; refresh must not silently follow head.
   if(!aid||!rid)window.history.replaceState(window.history.state,'',pageUrl(a.id,r.result_id));
  }
  load().catch(e=>{if(!controller.signal.aborted&&turn===epoch.current)setError(e instanceof Error?e.message:'问答上下文读取失败。');}).finally(()=>{if(!controller.signal.aborted&&turn===epoch.current)setLoading(false);});
  return()=>{++epoch.current;scope.current='';controller.abort();};
 },[scan.id,scan.mode,aid,rid,refresh]);
 useEffect(()=>{const input=composerInput.current;if(input){input.style.height='auto';input.style.height=Math.min(180,input.scrollHeight)+'px';}},[question]);
 const pending=chat?.items.some(x=>x.status==='pending')??false;
 useEffect(()=>{
  if(!pending||!assessment||!result)return;
  const controller=new AbortController(),current=scope.current;
  const timer=window.setInterval(()=>{readProjectChat(assessment,result,controller.signal).then(value=>{if(!controller.signal.aborted&&scope.current===current)setChat(value);}).catch(()=>{/* Keep the saved view. Manual read remains available. */});},2500);
  return()=>{controller.abort();window.clearInterval(timer);};
 },[pending,assessment?.id,result?.result_id]);
 useEffect(()=>{if(chat?.items.length)bottom.current?.scrollIntoView({block:'nearest',behavior:'auto'});},[chat?.items.length]);
 async function reread(){if(!assessment||!result)return;const current=scope.current,requestEpoch=epoch.current;try{const value=await readProjectChat(assessment,result);if(scope.current===current&&epoch.current===requestEpoch){setChat(value);setError('');setUncertain(false);}}catch(e){if(scope.current===current&&epoch.current===requestEpoch)setError(e instanceof Error?e.message:'读取失败。');}}
 async function submit(event:FormEvent){
  event.preventDefault();if(sendLock.current||sending||pending||uncertain||!assessment||!result||!chat||!question.trim()||chat.limits.remaining_model_calls===0)return;
  const a=assessment,r=result,current=scope.current,requestEpoch=epoch.current,body=prepareChatQuestion(a,r,question,crypto.randomUUID());
  sendLock.current=true;setSending(true);setError('');
  try{const value=await sendProjectQuestion(a,r,body);if(scope.current===current&&epoch.current===requestEpoch){setChat(value);setQuestion('');}}
  catch(e){if(scope.current===current&&epoch.current===requestEpoch){setError(e instanceof Error?e.message:'问答状态未确认。');setUncertain(true);}}
  finally{if(scope.current===current&&epoch.current===requestEpoch){sendLock.current=false;setSending(false);}}
 }
 function showBasis(e:ChatBasis){setSelectedBasis(e);requestAnimationFrame(()=>basisPanel.current?.scrollIntoView({block:'nearest',behavior:'auto'}));}
 const blocked=true; // Legacy conversations remain a read-only archive; new assistant owns generation.
 const continueUrl="/app/assistant?"+new URLSearchParams({mode:"api",project_scan:scan.id,attach:"1",...(assessment?{project_assessment:assessment.id}:{}),...(result?{project_result:result.result_id}:{})});
 return <section className={'og-project-chat'+(historyOpen?'':' og-chat-history-hidden')} aria-label="旧版项目问答记录">
  <aside className={'og-chat-history'+(historyOpen?' is-open':'')} aria-label="项目版本与问答记录">
   <div className="og-chat-history-heading"><h1>旧版问答记录</h1><button type="button" className="og-chat-icon" aria-label="收起版本记录" title="收起版本记录" onClick={()=>setHistoryOpen(false)}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4v16"/></svg></button></div>
   <div className="og-chat-project"><span>当前项目</span><strong title={scan.project}>{scan.project}</strong><p>对照保存的用途、结果和材料提问。</p></div>
   <button type="button" className="og-chat-read-history" onClick={()=>assessment&&result?void reread():setRefresh(n=>n+1)} disabled={loading}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M20 7v5h-5M4 17v-5h5M5 8a7 7 0 0 1 12-3l3 4M4 15l3 4a7 7 0 0 0 12-3"/></svg>读取已保存问答</button>
   <div className="og-chat-history-scroll">
    <h2>项目版本</h2>
    {loading&&<p className="og-chat-sidebar-status">正在读取版本…</p>}
    {assessments.map(a=><div className="og-chat-version-group" key={a.id}><button type="button" className={'og-chat-assessment-link'+(assessment?.id===a.id?' is-current':'')} disabled={loading||sending} aria-current={assessment?.id===a.id?'true':undefined} onClick={()=>go(pageUrl(a.id))}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M6 3h9l4 4v14H6zM14 3v5h5M9 12h7M9 16h5"/></svg><span>第 {a.version} 版<span>{usageTitle(a.usage)}</span></span></button>{assessment?.id===a.id&&<div className="og-chat-result-list">{results.map(r=><button type="button" key={r.result_id} className={result?.result_id===r.result_id?'is-current':''} disabled={loading||sending} aria-current={result?.result_id===r.result_id?'page':undefined} onClick={()=>go(pageUrl(a.id,r.result_id))}><span>结果 r{r.revision}</span><small>{r.material_ids.length} 份材料</small></button>)}</div>}</div>)}
    {!!chat?.items.length&&<><h2>本版提问</h2><div className="og-chat-question-list">{chat.items.map(turn=><button type="button" key={turn.request_id} title={turn.question} onClick={()=>{document.getElementById('og-chat-turn-'+turn.request_id)?.scrollIntoView({block:'start',behavior:'auto'});if(window.matchMedia('(max-width: 900px)').matches)setHistoryOpen(false);}}>{turn.question}</button>)}</div></>}
   </div>
   <p className="og-chat-history-note">按用途与结果版本保留记录。</p>
  </aside>
  {historyOpen&&<button className="og-chat-history-backdrop" type="button" aria-label="关闭版本记录" onClick={()=>setHistoryOpen(false)}/>}
  <div className="og-chat-main">
   <header className="og-chat-heading"><div className="og-chat-heading-start"><button type="button" className="og-chat-icon" aria-label={historyOpen?'收起版本记录':'打开版本记录'} title={historyOpen?'收起版本记录':'打开版本记录'} aria-expanded={historyOpen} onClick={()=>setHistoryOpen(v=>!v)}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4v16"/></svg></button><span>旧版项目问答记录</span><small>历史只读</small></div>{assessment&&result&&<a className="og-chat-current-version" href={resultPageUrl(assessment,result.result_id)}>评估 v{assessment.version}<span>/</span>结果 r{result.revision}<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M7 17 17 7M7 7h10v10"/></svg></a>}</header>
   {error&&<div className="og-chat-alert" role="alert"><strong>问答暂未完成</strong><p>{error}</p>{uncertain&&<p>先读取记录确认状态，不会自动重复发送。聊天失败不影响保存的评估。</p>}</div>}
   {loading?<div className="og-chat-empty og-chat-loading" role="status">正在读取当前账号的固定项目版本…</div>:chat&&assessment&&result?<>
    <div className="og-chat-context-line"><span>{scan.project}</span><span>{chat.context.resource_count} 项资源 · {chat.context.material_count} 份材料</span><details className="og-chat-usage"><summary>本版用途</summary><dl>{Object.entries(usageFields).map(([key,label])=><div key={key}><dt>{label}</dt><dd>{chat.context.usage[key as keyof typeof usageFields]===null?'暂不确定':chat.context.usage[key as keyof typeof usageFields]?'是':'否'}</dd></div>)}</dl></details></div>
    <div className={'og-chat-dialog'+(chat.items.length===0?' is-empty':'')} aria-label="当前版本的问答历史" aria-live="polite">
     {chat.items.length===0&&<div className="og-chat-empty"><div className="og-chat-mark" aria-hidden="true">Q</div><h2>今天想了解项目的哪一部分？</h2><p>从用途、材料或下一步开始。回答会带上可查看的依据。</p><div className="og-chat-prompts">{prompts.map(p=><button type="button" key={p} onClick={()=>{setQuestion(p);composerInput.current?.focus();}} disabled={blocked}>{p}</button>)}</div></div>}
     <div className="og-chat-reading-column">{chat.items.map((turn,i)=><article className="og-chat-turn" id={'og-chat-turn-'+turn.request_id} key={turn.request_id}><div className="og-chat-user"><span>你 · 第 {i+1} 轮</span><p>{turn.question}</p></div><div className="og-chat-answer"><div className="og-chat-answer-title"><span className="og-chat-answer-mark" aria-hidden="true">Q</span><strong>Qwen3</strong><span>{turn.status==='succeeded'?'已检查用途与引用':turn.status==='pending'?'正在回答':'本次未完成'}</span></div>{turn.status==='succeeded'?<><div className="og-chat-answer-text">{turn.answer}</div><div className="og-chat-citations" aria-label="回答依据">{turn.citations.map((c,j)=>{const e=chat.context.evidence.find(x=>x.basis_id===c.basis_id)!;return <button key={j} type="button" onClick={()=>showBasis(e)}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M9 18H7a5 5 0 0 1 0-10h4m2-2h4a5 5 0 0 1 0 10h-4M8 12h8"/></svg>依据 {j+1} · {e.label}</button>;})}</div></>:<p>{turn.status==='pending'?'正在依据固定项目材料生成并校验完整回答，最多等待120秒。':chatFailureMessage(turn.error_code)}</p>}</div></article>)}
      {sending&&!pending&&<div className="og-chat-wait" role="status"><span aria-hidden="true"/>正在读取依据并校验回答，完成后会显示全文…</div>}
      {selectedBasis&&<aside ref={basisPanel} className="og-chat-basis" aria-label="引用依据"><div><strong>{selectedBasis.label}</strong><button type="button" onClick={()=>setSelectedBasis(null)}>收起依据</button></div><p>{selectedBasis.kind==='result_fact'?'已保存用途事实':selectedBasis.kind==='material'?'已保存材料':'扫描记录'} · {selectedBasis.verification_state==='saved_declaration'?'保存的用途声明':selectedBasis.verification_state==='pending'?'尚未完成独立核验':selectedBasis.verification_state}</p><blockquote>{selectedBasis.quote}</blockquote><p>{selectedBasis.resource_ids.map(id=>scan.resources.find(r=>r.id===id)?.name??id).join('、')}</p><a href={resultPageUrl(assessment,result.result_id)}>在固定结果中核对材料与判断</a></aside>}
      <div ref={bottom}/>
     </div>
    </div>
    <div className="og-chat-composer-dock"><div className="og-chat-composer"><p style={{margin:0,fontSize:13,color:'#6f8076'}}>这些记录保持原版本与依据。新对话已取消累计次数上限。</p><a className="og-assistant-legacy-continue" href={continueUrl}>继续讨论此项目 →</a></div><p className="og-chat-boundary">在新会话中确认附带的项目版本；旧问答和项目结果保持不变。</p></div>
   </>:!loading&&<div className="og-chat-empty"><p>先选择一份已保存的项目评估，即可围绕其用途和材料提问。</p><a href={`/app/scans/${encodeURIComponent(scan.id)}/assessment?mode=api`}>前往项目评估</a></div>}
  </div>
 </section>;
}
