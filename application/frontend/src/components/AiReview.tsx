import {StageResult, type Stage} from './StageResult';
import {AssessmentTier, TierUpgradePlans} from './AssessmentTier';
import {readAssessmentTier, tierAllowsDerived, type TierView} from '../services/assessmentTier';
import {useEffect,useState,useRef} from 'react';
import type {Assessment} from '../services/assessments';
import type {Evidence} from '../types/domain';
import {loadReview,readReview,reviewGroups,reviewEvidence,uncertaintyLabels,type ReviewState,type ReviewStatus,type ReviewItem,readLoop,saveUserFact,startDerived,startAcquisition,readLoopJob,loopJobMessage,type LoopView,type LoopQuestion} from '../services/aiReview';
import './AiReview.css';
const band={HIGH:'高',MEDIUM:'中',LOW:'低'};
function jump(id:string){const target=document.getElementById(id);if(target instanceof HTMLDetailsElement)target.open=true;target?.scrollIntoView({block:'start',behavior:'instant'});target?.focus({preventScroll:true});}
function JudgmentGroups({items,status,evidence}:{items:ReviewItem[];status:ReviewStatus;evidence:Evidence[]}){
 return <div className="ai-review-groups">{reviewGroups(items,status).map(g=><article className="ai-review-group" key={g.code}>
  <header><h4>{g.title}</h4><span>{g.items.length} 项 / {g.resourceCount} 个资源</span></header>
  <p>{g.explanation}</p>
  <p className="ai-review-band">置信度：{Object.entries(g.bands).filter(([,n])=>n>0).map(([b,n])=>`${band[b as keyof typeof band]} ${n} 项`).join(' · ')}</p>
  <p className="ai-review-uncertainty">仍需注意：{g.uncertainties.length?g.uncertainties.map(c=>uncertaintyLabels[c]??'其他已保存的不确定性').join('；'):g.items[0].remaining_uncertainty}</p>
  <details className="ai-review-evidence"><summary>查看判断依据</summary><div className="ai-review-evidence-list">{g.items.map(i=><section key={i.item_id} className="ai-review-evidence-item"><h5>{i.name}{i.version?' · '+i.version:''}</h5>
   {reviewEvidence(i,evidence).map(e=><p key={e.id}><strong>{e.kind}</strong><span className="ai-review-locator">{e.locator}</span></p>)}
   {!i.evidence_ids.length&&<p>本项依据已保存的系统覆盖或义务记录，没有新增文件证据。</p>}
   <p>这些依据支持的辅助判断：{i.reason_summary}</p><p>{i.remaining_uncertainty}</p>
   <details className="ai-review-technical"><summary>高级来源详情</summary><p>事项：{i.item_id}；来源：{i.blocker_id}；判断：{i.judgment_code??'未提供'}；维度：{i.dimension}</p>{i.evidence_ids.map(id=><p key={id}>证据：{id}</p>)}<p>{i.source_gap}</p></details>
  </section>)}</div></details>
 </article>)}</div>;
}

function ResolutionControls({assessment,view,readOnly,onRead,tierEmbedded=false}:{assessment:Assessment;view:LoopView;readOnly:boolean;onRead:(v:LoopView)=>void;tierEmbedded?:boolean}){
 const [answers,setAnswers]=useState<Record<string,string>>({}),[selected,setSelected]=useState<Record<string,string[]>>({}),[notes,setNotes]=useState<Record<string,string>>({}),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[confirm,setConfirm]=useState(false);
 const active=useRef(true),working=useRef(false),keys=useRef<Record<string,string>>({});
 useEffect(()=>{active.current=true;return()=>{active.current=false;};},[]);
 const answer=(q:LoopQuestion)=>answers[q.question_id]??q.latest?.answer_code??'';
 const resources=(q:LoopQuestion)=>selected[q.question_id]??q.latest?.covered_resource_ids??[];
 const note=(q:LoopQuestion)=>notes[q.question_id]??q.latest?.optional_note??'';
 const eligible=view.routes.filter(r=>r.public_source_candidate);
 const waitJob=async(j:unknown)=>{if(!j||typeof j!=='object'||!('job_id' in j)||typeof j.job_id!=='string')throw new Error('任务提交结果尚未确认；不要重复提交。');
  for(let n=0;n<100;n++){if(!active.current)throw new Error('页面已切换，已保存回答保留。');const s=await readLoopJob(assessment,view,j.job_id);if(s.job.status==='completed')return s;if(['failed','cancelled','interrupted'].includes(s.job.status))throw new Error('LOOP_SAFE:'+loopJobMessage(s.job));await new Promise(r=>setTimeout(r,1200));}throw new Error('仍在处理或结果尚未确认，请稍后只读刷新结果。');};
 async function act(acquire=false){
  if(readOnly||working.current)return;working.current=true;setBusy(true);setMessage('');
  try{
   let current=view;let acquisitions:string[]=[];
   if(acquire){setMessage('正在获取官方材料');const done=await waitJob(await startAcquisition(assessment,view,eligible.map(r=>r.item_id),readOnly));if(!done.snapshot)throw new Error('材料读取未完成，原结果保留。');acquisitions=[done.snapshot.snapshot_id];setMessage('已取得官方元数据观察，正在重新研判相关事项；不代表授权。');}
   else{
    let saved=0;
    for(const q of view.questions){const value=answer(q);if(!value)continue;
     const ids=value==='YES_INCLUDE'?resources(q):q.resource_ids;
     if(!ids.length)throw new Error('请勾选确实会交付的资源；未选择的仍保持未知。');
     if(q.latest&&q.latest.answer_code===value&&q.latest.optional_note===note(q)&&JSON.stringify([...q.latest.covered_resource_ids].sort())===JSON.stringify([...ids].sort()))continue;
     const key=keys.current[q.question_id]??(keys.current[q.question_id]=crypto.randomUUID());
     await saveUserFact(assessment,view,q,value,ids,note(q),key,readOnly);saved++;
    }
    if(!saved){setMessage('没有需要保存的新回答。');return;}
    if(!active.current)return;setMessage('已记录你的实际情况，AI正在重新研判受影响事项。');current=await readLoop(assessment);onRead(current);
   }
   await waitJob(await startDerived(assessment,current,acquisitions,readOnly));
   const updated=await readLoop(assessment);if(!active.current)return;onRead(updated);keys.current={};
   setMessage(acquire?'官方材料与重新研判结果已保存。若数量未变，本次没有取得足以改变研判的新证据。':'基于你的回答，相关事项已更新AI研判。用户声明尚未独立核验，正式评估不变。');
  }catch(e){if(active.current)setMessage(e instanceof Error&&e.message.startsWith('LOOP_SAFE:')?e.message.slice(10):e instanceof Error&&e.message.startsWith('请勾选')?e.message:'本次处理未完成或结果尚未确认；已保存回答与原研判保留。请先读取状态，不要直接重复提交。');}
  finally{working.current=false;if(active.current)setBusy(false);}
 }
 return <section className="ai-loop-controls" aria-label="回答实际情况与补证">
  <h3>回答实际情况</h3><p>只记录你的声明，不替代正式核验。未明确的资源继续保持未知。</p>
  {readOnly&&<p role="note">当前为只读预览；正式工作台可回答并重新研判。</p>}
  <form onSubmit={e=>{e.preventDefault();if(!readOnly)void act();}}>
   <fieldset disabled={readOnly||busy}>{view.questions.map(q=><section key={q.question_id} className="ai-loop-answer"><h4>{q.text}</h4>
    <div role="radiogroup" aria-label={q.text}>{q.options.map(o=><label key={o.code}><input type="radio" name={q.question_id} value={o.code} checked={answer(q)===o.code} onChange={()=>{keys.current[q.question_id]=crypto.randomUUID();setAnswers({...answers,[q.question_id]:o.code});setMessage('新回答尚未保存；当前研判仍使用已保存事实。');}}/>{o.label}</label>)}</div>
    {answer(q)==='YES_INCLUDE'&&<fieldset><legend>选择会实际交付的资源（未选中的仍未知）</legend>{q.resources.map(r=><label key={r.id}><input type="checkbox" checked={resources(q).includes(r.id)} onChange={e=>{keys.current[q.question_id]=crypto.randomUUID();setSelected({...selected,[q.question_id]:e.target.checked?[...resources(q),r.id]:resources(q).filter(id=>id!==r.id)});}}/>{r.name}</label>)}</fieldset>}
    <label className="ai-loop-note">补充说明（可选，最多1000字）<textarea maxLength={1000} value={note(q)} onChange={e=>{keys.current[q.question_id]=crypto.randomUUID();setNotes({...notes,[q.question_id]:e.target.value});}}/></label>
    {q.latest&&<p>已保存回答 第{q.latest.revision}版 · 用户声明，尚未独立核验</p>}
    {!!q.history.length&&<details><summary>查看回答历史（{q.history.length}版）</summary>{q.history.map(f=><p key={f.user_fact_id}>第{f.revision}版：{q.options.find(o=>o.code===f.answer_code)?.label}；明确涉及{f.covered_resource_ids.length}个资源。{f.optional_note}</p>)}</details>}
   </section>)}</fieldset>
   <button type="submit" disabled={readOnly||busy}>{busy?'处理中…':'保存并重新研判'}</button>
  </form>
  <p role="status">{message}</p><button type="button" disabled={busy} onClick={()=>{void readLoop(assessment).then(v=>{if(active.current){onRead(v);setMessage(v.latest_job&&['queued','running'].includes(v.latest_job.status)?'AI仍在处理，旧结果保留。':'已读取保存状态。');}}).catch(()=>{if(active.current)setMessage('状态读取未完成；原结果保留。');});}}>读取已保存状态</button>
  {!tierEmbedded&&<><h3>依据不足：下一步</h3><p>当前固定结果有{view.routes.length}项需要更多依据，其中{eligible.length}项可尝试官方元数据。不同路径可能重叠。</p>
  <button type="button" disabled={readOnly||busy||!eligible.length} onClick={()=>setConfirm(true)}>尝试自动补证</button>
  {confirm&&<section role="region" aria-label="确认官方来源"><p>仅访问：{[...new Set(eligible.map(r=>r.public_source_candidate?.provider))].join('、')} 官方精确版本元数据；不下载制品、不证明授权。</p><button type="button" disabled={readOnly||busy} onClick={()=>{setConfirm(false);void act(true);}}>确认并开始</button><button type="button" onClick={()=>setConfirm(false)}>取消</button></section>}
  <ul>{view.routes.map(r=><li key={r.item_id}><strong>{r.name}</strong>：{r.why}</li>)}</ul>
  </>}
  {view.derived&&<p>当前派生结果：AI辅助研判{view.derived.snapshot.result.summary.item_counts.AI_ASSISTED}项；仍需用户事实{view.derived.snapshot.result.summary.item_counts.NEEDS_USER_FACT}项；依据不足{view.derived.snapshot.result.summary.item_counts.INSUFFICIENT_BASIS}项。原固定结果保留。</p>}
 </section>;
}

export function AiReview({assessment,readOnly,evidence=[]}:{assessment:Assessment;readOnly:boolean;evidence?:Evidence[]}){
 const [state,setState]=useState<ReviewState|null>(null),[error,setError]=useState(false);
 useEffect(()=>{let active=true;let timer:ReturnType<typeof setTimeout>|undefined;setState(null);setError(false);
  async function apply(p:Promise<ReviewState>){try{const result=await p;if(!active)return;setState(result);
    if(result.job&&['queued','running'].includes(result.job.status))timer=setTimeout(()=>apply(readReview(assessment)),1500);
   }catch{if(active)setError(true);}}
  void apply(loadReview(assessment,readOnly));return()=>{active=false;if(timer)clearTimeout(timer);};
 },[assessment.id,assessment.version,assessment.facts_hash,(assessment as Assessment&{usage_hash:string}).usage_hash,assessment.rule_version,readOnly]);
 const [loop,setLoop]=useState<LoopView|null>(null);
 useEffect(()=>{let active=true;setLoop(null);if(state?.snapshot)void readLoop(assessment).then(v=>{if(active)setLoop(v);}).catch(()=>{});return()=>{active=false;};},[assessment.id,assessment.version,state?.snapshot?.snapshot_id]);
 const [tier,setTier]=useState<TierView|null>(null);
 useEffect(()=>{let active=true;setTier(null);void readAssessmentTier(assessment).then(v=>{if(active)setTier(v);}).catch(()=>{});return()=>{active=false;};},[assessment.id,assessment.version,assessment.facts_hash,(assessment as Assessment&{usage_hash:string}).usage_hash,assessment.rule_version,loop?.derived?.snapshot.snapshot_id]);
 const [stage,setStage]=useState<Stage>('L1');
 useEffect(()=>{setStage('L1');},[assessment.id,assessment.version,state?.snapshot?.snapshot_id]);
 const trustedDerived=tier&&loop?.derived&&tierAllowsDerived(tier,loop.derived.snapshot.snapshot_id)?loop.derived:null;
 const result=stage==='L1'?state?.snapshot?.result:stage==='L2'?trustedDerived?.snapshot.result: tier?.level_states.L3==='COMPLETE'?(trustedDerived?.snapshot.result??state?.snapshot?.result):undefined;
 const failed=error||!!state?.job&&['failed','interrupted','cancelled'].includes(state.job.status);
 const counts=result?.summary.item_counts;
 const questions=result?.summary.questions??(stage==='L2'?state?.snapshot?.result.summary.questions:undefined)??[];
 const questionItems=new Set(questions.flatMap(q=>q.item_ids)).size;
 return <section className="ai-review" aria-label="AI初评与证据增强">
  {tier&&<AssessmentTier value={tier} selected={stage} onSelect={setStage}/>}
  <StageResult assessment={assessment} tier={tier} stage={stage} hasResult={!!result} assisted={counts?.AI_ASSISTED} supported={result?.deterministic_context.supported_resource_ids.length}/>
  {stage==='L2'&&trustedDerived&&state?.snapshot&&<p className="ai-review-meta">与本对象 L1 对照：辅助研判 {state.snapshot.result.summary.item_counts.AI_ASSISTED} → {trustedDerived.snapshot.result.summary.item_counts.AI_ASSISTED} 项；仍需现实事实 {state.snapshot.result.summary.item_counts.NEEDS_USER_FACT} → {trustedDerived.snapshot.result.summary.item_counts.NEEDS_USER_FACT} 项；依据不足 {state.snapshot.result.summary.item_counts.INSUFFICIENT_BASIS} → {trustedDerived.snapshot.result.summary.item_counts.INSUFFICIENT_BASIS} 项。声明被采用不等于独立核验。</p>}
  <div role="status" aria-live="polite">{!result&&stage==='L1'&&(failed?'AI研判暂不可用；原评估与义务保留。':state&&!state.job&&readOnly?'此只读预览未生成AI研判。':'AI正在研判当前已保存的用途；不会改变正式评估。')}</div>
  {result&&counts&&<>
   <p className="ai-compact-summary">辅助研判 {counts.AI_ASSISTED} 项 · 现实问题 {questions.length} 个 · 依据不足 {counts.INSUFFICIENT_BASIS} 项</p>
   <div className="result-next-actions"><button type="button" onClick={()=>setStage('L2')}>补充关键事实与材料 · L2</button><button type="button" onClick={()=>jump('ai-assisted-groups')}>查看判断依据与完整记录</button></div>
   <details key={[assessment.id,state?.snapshot?.snapshot_id,trustedDerived?.snapshot.snapshot_id,stage].join(':')} id="ai-assisted-groups" onToggle={e=>{const d=e.currentTarget;if(!d.open&&d.contains(document.activeElement))d.querySelector('summary')?.focus({preventScroll:true});}} tabIndex={-1} className="ai-review-assisted"><summary>AI研判明细 · 查看分类与判断依据</summary><h3>AI辅助研判 · 按判断查看</h3><p className="ai-review-secondary">本轮高置信研判 {counts.AI_HIGH_CONFIDENCE} 项 · 冲突／专家复核 {counts.NEEDS_EXPERT_REVIEW} 项</p><p className="ai-review-meta">共 {result.summary.total_items} 项研判事项，涉及 {result.summary.unique_resource_count} 个不同资源；不代表合规率。范围问题涉及 {result.summary.scope_unique_resources} 个资源，其中 {result.summary.ai_scope_unique_resources} 个 AI 资源已包含在内，不重复相加。</p><p>AI研判不代表授权确认；必要义务仍须履行。</p><p>以下按实际判断分组，保留限制与不确定性；各组资源可能重叠，不相加。</p><JudgmentGroups items={result.items} status="AI_ASSISTED" evidence={evidence}/>
   <details className="ai-review-insufficient" id="ai-insufficient" tabIndex={-1}><summary>系统仍无法安全判断的事项 <span>{counts.INSUFFICIENT_BASIS} 项</span></summary><p>这些事项是当前证据或系统覆盖能力不足，不要求你重复填写已回答的用途。</p><JudgmentGroups items={result.items} status="INSUFFICIENT_BASIS" evidence={evidence}/></details>
   {(['AI_HIGH_CONFIDENCE','NEEDS_EXPERT_REVIEW'] as const).filter(s=>counts[s]>0).map(s=><section key={s}><h3>{s==='AI_HIGH_CONFIDENCE'?'高置信辅助研判':'需要专家复核的事项'}</h3><JudgmentGroups items={result.items} status={s} evidence={evidence}/></section>)}
   <div className="ai-review-existing"><strong>既有确定性判断（含人审依据）</strong><p>原规则已有 {result.deterministic_context.supported_resource_ids.length} 条资源记录的局部支持，含既有人审依据。本轮未新增确定性核验，不计入 AI 新增成果。</p></div>
   <details className="ai-review-provenance"><summary>查看本次固定结果身份</summary><p>评估版本 {assessment.version} · {state?.snapshot?.snapshot_id}</p><p>AI 结果按固定评估和已有证据保存。下方正式评估、材料与必要义务保留原身份，不因辅助研判改变。</p></details></details>
  </>}
   <div className="stage-l2-work" hidden={stage!=='L2'}><section id="ai-project-questions" aria-label="L2现实问题"><h3>{questions.length?'你只需要回答 '+questions.length+' 个问题':loop?.questions.some(q=>q.latest)?'已记录当前两问的回答':'本轮没有需要你回答的项目级问题'}</h3>{questions.length>0&&<p>AI 已将 {questionItems} 项需要现实业务确认的事项合并为 {questions.length} 个项目级问题。</p>}{!loop&&<div className="ai-review-question-grid">{questions.map((q,n)=><article key={q.question_key}><span>问题 {n+1}</span><h4>{q.text}</h4><p>覆盖 {new Set(q.item_ids).size} 项事项 / {new Set(q.resource_ids).size} 个资源</p><p>{q.why_needed_zh??'请结合保存事项查看。'}</p><small>只读查看：本页不收集或保存回答。</small></article>)}</div>}</section>{tier&&<TierUpgradePlans value={tier}>{loop&&<ResolutionControls tierEmbedded key={"tier-"+assessment.id+assessment.version} assessment={assessment} view={loop} readOnly={readOnly} onRead={setLoop}/>}</TierUpgradePlans>}{!tier&&loop&&<ResolutionControls key={assessment.id+assessment.version} assessment={assessment} view={loop} readOnly={readOnly} onRead={setLoop}/>}</div>
 </section>;
}

export {ResolutionControls};
