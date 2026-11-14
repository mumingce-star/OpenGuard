import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { Assessment } from '../services/assessments';
import { usageFields } from '../services/assessments';
import type { Receipt, Result } from '../services/p2';
import { adoptOfficialSources, pendingOfficialAdoption, readOfficialSources, recoverOfficialAdoption, replayOfficialAdoption, endOfficialAdoption, canRequestOfficialFetch, pendingOfficialFetch, requestOfficialFetch, officialAnalysisFailureMessage, fixedCommit, type OfficialSources as Sources } from '../services/officialSources';
import './OfficialSources.css';

type Props={assessment:Assessment;result:Result;readOnly:boolean;disabled?:boolean;onAdopt:(receipt:Receipt)=>void;onAnalysisSaved:(analysisId:string)=>void;onAdoptingChange?:(busy:boolean)=>void;onReadSavedResult?:()=>void};
const fetchLabels:Record<Sources['fetch']['state'],string>={not_scheduled:'尚未安排取证',queued:'等待官方资料取证',running:'正在读取固定官方资料',ready:'官方资料原文已取得',partial:'Git原文已取得，npm版本资料缺失',failed:'本次取证失败',outcome_unknown:'取证结果待确认',unsupported:'当前样例不在首期支持范围'};
const analysisLabels:Record<Sources['analysis']['state'],string>={not_scheduled:'尚未安排分析',waiting_source:'等待资料原文',queued:'等待本地 Qwen',running:'本地 Qwen 正在分析',ready:'本版分析已保存',failed:'本次分析未通过',outcome_unknown:'分析结果待确认'};
const isActive=(v:Sources)=>v.runtime_jobs_enabled!==false&&(['queued','running'].includes(v.fetch.state)||['waiting_source','queued','running'].includes(v.analysis.state));
const reason=(e:unknown)=>e instanceof Error?e.message:'读取暂未完成，已有结果保持不变。';
const legacyFreeTextReviewLimit='结构与已知错误模式检查不保证行动完整或语义正确，内容仍需人工复核。';

/** Display the immutable model text with separate, explicit human-review boundaries. */
export function OfficialAnalysisPreview({preview,usage}:{preview:NonNullable<Sources['analysis']['preview']>;usage:Result['usage']}){
 if(preview.status!=='succeeded')return null;
 if(preview.analysis_protocol==='openguard-qwen-action-plan/2'&&preview.validation_details?.status==='validated')return <div className="official-preview" data-official-preview={preview.preview_id} data-bound-action-plan="2">
  <h3>Qwen3 · 当前用途下的具体行动</h3>
  <p className="p2-ai-note" data-structured-plan-origin="">Qwen选取依据，系统核对后整理</p>
  <p className="p2-muted">已核对当前固定结果、用途、准确资源版本及对应依据。许可原文仅关联这个 Git 提交的源码；资料仍未采用，不代表正式许可或义务已经履行。</p>
  <ol>{preview.actions.map((action,i)=><li key={i} data-bound-action-kind={action.action_kind} data-bound-action-basis={action.basis_kind}>
   <p data-program-rendered-action="">{action.text}</p>
   <small>对应用途：{action.usage_fields?.map(key=>`${usageFields[key]}＝${usage[key]===true?'是':usage[key]===false?'否':'暂不确定'}`).join('；')||'精确源码与版本核对'}</small>
   {action.basis_kind==='usage_gap'?<p className="p2-muted" data-usage-gap-basis="">自动补证：依据当前用途声明及尚未取得的对象／范围材料生成，不把 Git LICENSE 当作训练数据、模型或其他资源的许可。</p>:<details data-license-condition-basis=""><summary>查看这条行动的原文依据</summary>{preview.clauses.filter(clause=>clause.quote_id&&action.basis_ids?.includes(clause.quote_id)).map((clause,n)=><blockquote key={n}>{clause.quote}<small>固定 Git 候选原文字符 [{clause.start}, {clause.end})，尚未写入 Material。</small></blockquote>)}</details>}
  </li>)}</ol>
  <details><summary>查看结构选择、校验与原始运行记录</summary><p>行动正文由程序据已通过核对的结构选择整理；模型原始输出仅保留在本追溯区。保存时的完整范围说明也按原文保留，其中旧自由文本通用提示不作为新版行动的审核状态。</p><pre>{JSON.stringify({analysis_protocol:preview.analysis_protocol,plan:preview.plan,validation_details:preview.validation_details,attempts:preview.attempts,stored_limitations:preview.limitations},null,2)}</pre></details>
  <details><summary>当前仍未证明的范围</summary><p data-current-plan-assurance="">本版已核对结构化用途、准确对象和行动依据；这不代表正式许可适用性已经确认，也不证明义务已经履行。</p><ul className="official-limits">{preview.limitations.filter(v=>v!==legacyFreeTextReviewLimit).map((v,i)=><li key={i}>{v}</li>)}</ul></details>
 </div>;
 return <div className="official-preview" data-official-preview={preview.preview_id}>
  <h3>Qwen3 · 待人工复核预览</h3>
  <p className="p2-ai-note" data-model-review-boundary="">以下为模型生成的辅助核验方向，尚待人工复核；程序检查通过不代表每条语义已确认，不作为已确认的许可结论或实际用途事实。</p>
  <p className="p2-muted">真实本地模型：{preview.model.name} · 依据当前固定结果与演示用途假设。资料尚未写入 Material，也未改变规则建议。以下模型原文完整保留，提示说明与原文分开显示。</p>
  <ol>{preview.actions.map((action,i)=><li key={i} data-model-action-index={i}>
   <span data-original-model-action="">{action.text}</span>
   {usage.distributed===false&&action.text.includes('已交付')&&<p className="p2-ai-note" data-model-action-warning="delivery-premise">当前用途未声明向他人交付；这条原文中的已交付前提尚无证据，不代表交付已经发生。请先核对实际范围。</p>}
   {/训练/.test(action.text)&&<p className="p2-ai-note" data-model-action-warning="training-scope">训练相关建议仍需确认具体训练输入、所用代码及各自来源；本 Git LICENSE 不能覆盖训练数据、模型或其他资源。</p>}
   {/资产|再分发资源/.test(action.text)&&<p className="p2-ai-note" data-model-action-warning="asset-scope">资源再分发相关建议仍需确认实际对象、版本及各自来源；本 Git LICENSE 不能覆盖其他资产或依赖。</p>}
  </li>)}</ol>
  <details><summary>查看预览对应的原文（{preview.clauses.length}处）</summary>{preview.clauses.map((clause,i)=><blockquote key={i}>{clause.quote}<small>候选原文字符 [{clause.start}, {clause.end})，不是已保存 Material 引用。</small></blockquote>)}</details>
  {preview.limitations.length>0&&<ul className="official-limits">{preview.limitations.map((v,i)=><li key={i}>{v}</li>)}</ul>}
 </div>;
}

/** Passive rendering and status refresh are GET-only. New fetching requires the separately admitted explicit action; adoption still needs its own confirmation. */
export function OfficialSources({assessment:a,result:r,readOnly,disabled=false,onAdopt,onAnalysisSaved,onAdoptingChange,onReadSavedResult}:Props){
 const scope=JSON.stringify([a.scan_id,a.id,a.version,r.result_id,r.result_sha256,r.binding]);
 const [saved,setSaved]=useState<{scope:string;value:Sources}|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[confirm,setConfirm]=useState(false),[refresh,setRefresh]=useState(0);
 const [pending,setPending]=useState(()=>{try{return pendingOfficialAdoption(r);}catch{return null;}}),[recoveryNotice,setRecoveryNotice]=useState('');
 const [fetchPending,setFetchPending]=useState(()=>{try{return pendingOfficialFetch(r);}catch{return null;}});
 const owner=useRef({scope:'',epoch:0,mounted:false}),permission=useRef({epoch:0,writable:false}),lock=useRef(false),callbacks=useRef({onAdopt,onAnalysisSaved,onAdoptingChange});
 const seenAnalysis=useRef('');
 useLayoutEffect(()=>{callbacks.current={onAdopt,onAnalysisSaved,onAdoptingChange};});
 useLayoutEffect(()=>{const o=owner.current;o.scope=scope;o.epoch++;o.mounted=true;lock.current=false;seenAnalysis.current='';return()=>{o.mounted=false;o.epoch++;};},[scope]);
 useLayoutEffect(()=>{const p=permission.current;p.epoch++;p.writable=!readOnly&&!disabled;return()=>{p.epoch++;p.writable=false;};},[scope,readOnly,disabled]);
 useEffect(()=>{
  const controller=new AbortController(),epoch=owner.current.epoch;let timer:ReturnType<typeof setTimeout>|undefined;
  const current=()=>!controller.signal.aborted&&owner.current.mounted&&owner.current.scope===scope&&owner.current.epoch===epoch;
  setSaved(null);setError('');setLoading(true);setBusy(false);setConfirm(false);setRecoveryNotice('');try{setPending(pendingOfficialAdoption(r));setFetchPending(pendingOfficialFetch(r));}catch(e){setPending(null);setError(reason(e));}
  async function read(){try{
   const value=await readOfficialSources(a,r,controller.signal);if(!current())return;setSaved({scope,value});setError('');setPending(pendingOfficialAdoption(r));setFetchPending(pendingOfficialFetch(r));
   const id=value.analysis.mode==='saved_material'&&value.analysis.state==='ready'?value.analysis.analysis_id:null;
   if(id&&seenAnalysis.current!==id){seenAnalysis.current=id;callbacks.current.onAnalysisSaved(id);}
   if(isActive(value))timer=setTimeout(()=>void read(),1500);
  }catch(e){if(current())setError(reason(e));}finally{if(current())setLoading(false);}}
  void read();return()=>{controller.abort();if(timer)clearTimeout(timer);};
 },[scope,refresh]);
 const data=saved?.scope===scope?saved.value:null,candidate=data?.candidate,preview=data?.analysis.preview,localActions=data?.local_actions;
 const preDispatchFailure=!!data&&data.fetch.state==='failed'&&data.fetch.http_dispatched===0&&!candidate;
 async function fetchExplicitly(){
  const o=owner.current,p=permission.current,epoch=o.epoch,permissionEpoch=p.epoch;
  const current=()=>o.mounted&&o.scope===scope&&o.epoch===epoch,permit=()=>current()&&p.epoch===permissionEpoch&&p.writable;
  if(!data||!canRequestOfficialFetch(data)||!permit()||lock.current||busy||pendingOfficialFetch(r))return;
  lock.current=true;setBusy(true);setError('');
  try{const value=await requestOfficialFetch(a,r,data,permit);if(current()){setSaved({scope,value});setFetchPending(pendingOfficialFetch(r));setRefresh(n=>n+1);}}
  catch(e){if(current()){setFetchPending(pendingOfficialFetch(r));setError(reason(e));}}
  finally{if(current()){lock.current=false;setBusy(false);}}
 }
 async function adopt(replay=false){
  const o=owner.current,p=permission.current,epoch=o.epoch,permissionEpoch=p.epoch;
  const current=()=>o.mounted&&o.scope===scope&&o.epoch===epoch;
  const permit=()=>current()&&p.epoch===permissionEpoch&&p.writable;
  if(!candidate||(!replay&&!confirm)||!permit()||lock.current||busy||(!replay&&pendingOfficialAdoption(r))||data?.adopted_material_ids.length)return;
  lock.current=true;setBusy(true);setError('');callbacks.current.onAdoptingChange?.(true);
  try{const receipt=await(replay?replayOfficialAdoption(a,r,candidate,permit):adoptOfficialSources(a,r,candidate,permit));if(current()){setPending(null);setConfirm(false);callbacks.current.onAdopt(receipt);}}
  catch(e){if(current()){setPending(pendingOfficialAdoption(r));setError(reason(e));}}
  finally{if(current()){lock.current=false;setBusy(false);callbacks.current.onAdoptingChange?.(false);}}
 }
 async function recover(){
  const o=owner.current,epoch=o.epoch,current=()=>o.mounted&&o.scope===scope&&o.epoch===epoch;
  if(lock.current||busy)return;lock.current=true;setBusy(true);setError('');setRecoveryNotice('');
  try{const checked=await recoverOfficialAdoption(a,r);if(current()){setPending(checked.pending);setRecoveryNotice(checked.result?`已只读核对服务器当前结果 r${checked.result.revision}。这不单独证明原请求键是否保存；可明确恢复同一请求，或结束本地待确认状态。`:'已只读核对：服务器尚无保存结果。不会自动重发原请求。');}}
  catch(e){if(current())setError(reason(e));}finally{if(current()){lock.current=false;setBusy(false);}}
 }
 function end(){try{endOfficialAdoption(r);setPending(null);setConfirm(false);setRecoveryNotice('已明确结束本地原请求，服务器保存对象保持不变；不会自动创建或发送新请求。');}catch(e){setError(reason(e));}}
 const canAdopt=!!candidate&&!!data&&['ready','partial'].includes(data.fetch.state)&&!data.adopted_material_ids.length&&!readOnly&&!disabled&&!loading&&!busy&&!pending;
 return <section className={'p2-main-card official-sources'+(candidate?' has-source-data':' is-status-only')} data-official-sources="" data-result-id={r.result_id} aria-label="联网查找官方资料">
  <header className="official-sources-header"><div><div className="p2-step">联网补充依据 · http-server@14.1.2</div><h2>联网查找官方资料</h2></div><span className="official-status" data-source-state={data?.fetch.state??'loading'}>{data?fetchLabels[data.fetch.state]:'读取取证状态'}</span></header>
  <p className="official-scope-label">固定 Git 提交 <code>{fixedCommit.slice(0,12)}</code> · npm 14.1.2。{candidate?'原文已取得，采用与适用范围仍需核验。':loading?'正在只读核对本版资料状态。':data?'当前记录尚无可采用原文；展开查看范围与操作。':'资料状态尚未读回；展开查看范围与操作。'}</p>
  {loading&&<p role="status">正在只读获取本版资料与任务状态…</p>}
  {error&&<p role="alert" className="p2-ai-error">{error}</p>}
  {preDispatchFailure&&<p className="official-fetch-summary">{data?.fetch.error_code?.includes('budget')?'请求在发送前被预算限制拦截':'任务在实际获取前停止'}；尚未向官方端点发送请求，资料结果未知。</p>}
  {fetchPending&&fetchPending.state!=='accepted'&&<p className="official-fetch-receipt" role="status" data-official-fetch-request-state={fetchPending.state}>{fetchPending.state==='sent'?'查找请求已发出，等待接收回执。':fetchPending.state==='unknown'?'查找请求的接收结果尚未确认。请仅刷新状态核对，不会自动重发或创建新请求。':'查找请求已被明确拒绝；记录已保留，不会自动重发。'}</p>}
  {data&&<p className="official-analysis-status" data-automatic-analysis-state={data.analysis.state}>Qwen：{analysisLabels[data.analysis.state]} · {data.adopted_material_ids.length?'已保存为待核验材料':candidate?'资料等待确认采用':'尚无可采用材料'}</p>}
  {data?.analysis.error_code&&<p className="p2-ai-note official-analysis-explanation" data-official-analysis-explanation="">{officialAnalysisFailureMessage(data.analysis.error_code,preview?.validation_details?.corrective_attempt_used===true,preview?.validation_details?.issues)}</p>}
  <details className="official-content" data-official-source-details="" open={!!candidate}><summary>查看来源详情与采用<span>{candidate?'已取得原文 · 仍待核验':'资料状态、来源范围与请求记录'}</span></summary>
  <p className="official-detail-scope">查找 Git 提交 <code>{fixedCommit.slice(0,12)}</code> 的 LICENSE 与 npm 14.1.2 资料；先预览，再由你确认采用。{data?.runtime_jobs_enabled===false?'当前仅查看已有记录。':'刷新状态不会重复联网。'}</p>
  {data&&<div className="official-stages"><span>资料：{fetchLabels[data.fetch.state]}</span><span>Qwen：{analysisLabels[data.analysis.state]}</span><span>采用：{data.adopted_material_ids.length?'已保存为待核验材料':candidate?'已取得资料，等待你确认':'尚无可采用材料'}</span></div>}
  {preDispatchFailure&&<div className="official-fetch-blocker" data-official-pre-dispatch=""><strong>上一次尚未向官方端点发送请求</strong><p>{data?.fetch.error_code?.includes('budget')?'请求在发送前被预算限制拦截，不表示官方网站没有资料。':'系统在实际获取前停止了任务，不表示官方网站没有资料。'} 当前记录：已发出 {data?.fetch.http_dispatched} 次、已收到 {data?.fetch.http_responses} 次响应。</p>
   {data&&canRequestOfficialFetch(data)&&!fetchPending?<div className="official-search-actions"><button className="p2-primary" type="button" data-official-fetch-explicit="" disabled={loading||busy||readOnly||disabled} onClick={()=>void fetchExplicitly()}>{busy?'正在提交查找请求…':'联网查找这版官方资料'}</button><span>仅本轮明确授权的一次获取；不自动重试，不切换版本或来源。</span></div>:!fetchPending&&<p>当前尚未开放新的获取。已有扫描和评估保留，可先查看逐资源依据。</p>}
  </div>}
  {data&&!candidate&&<div className="official-empty-sources"><article><h3>Git 原仓库 · LICENSE</h3><p>{['queued','running'].includes(data.fetch.state)?'正在按固定提交查找，尚无可预览原文。':'当前没有可预览的许可证原文。'}</p><small>仅认定该提交的源码范围，不代表 npm 发行包。</small></article><article><h3>npm · 14.1.2 发布资料</h3><p>{preDispatchFailure?'尚未发出请求，结果未知。':'当前没有取得可核对的发布资料。'}</p><small>不会用其他版本资料补齐当前版本。</small></article></div>}
  {candidate&&<>
   <div className="official-source-grid">{candidate.sources.map(source=><article key={source.url}><h3>{source.url.includes('raw.githubusercontent.com')?'Git 固定提交 · LICENSE':'npm 准确版本 · 元数据'}</h3><p>{source.byte_count.toLocaleString()} 字节 · {source.verification_state==='pending'?'待核验':'状态见来源记录'}</p><p>{source.kind==='git_license'?'已取得这个 Git 提交的真实 LICENSE 原文，可先预览再采用。':'已取得准确版本的发布元数据；其中的许可证声明仍需核验。'}</p><small>{source.retrieved_at?`实际获取：${new Date(source.retrieved_at).toLocaleString()}`:'获取时间未随本次记录提供'}</small><details><summary>来源地址、准确提交与 Hash</summary><p className="official-source-url">{source.url}</p><p>Git 提交：{source.kind==='git_license'?candidate.commit:'不适用；按 npm 准确版本定位'}</p><p>来源等级：{source.source_level}</p><code>{source.sha256}</code></details></article>)}{candidate.source_failures.map(f=><article className="official-source-missing" key={f.url}><h3>npm 准确版本 · 资料缺失</h3><p>固定端点返回 HTTP 404；未取得元数据原文。</p><small>实际响应：{new Date(f.retrieved_at).toLocaleString()}</small><p>保留缺口，不更换版本、不重试、不把 Git LICENSE 当作 npm 发行许可证。</p><details><summary>查看实际请求地址</summary><p className="official-source-url">{f.url}</p></details></article>)}</div>
   <p className="official-boundary">Git 根 LICENSE 关联该提交的源码；npm 元数据中的声明不能证明发行包包含同一 LICENSE。实际安装、交付范围与正式许可适用性仍需核验。</p>
   <details className="official-license"><summary>{data?.adopted_material_ids.length?'查看本版已采用的 LICENSE 原文':'预览实际取得的 LICENSE 原文（尚未采用）'}</summary><pre>{candidate.license_text}</pre></details>
   {localActions?.state==='supported_verification_actions'&&<div className="official-preview" data-local-actions="" data-local-action-result={localActions.result_id}>
    <div className="p2-step">基于已保存材料的核验行动 · pending · 非正式许可判断</div>
    <h3>当前用途下，下一步核对什么</h3><p className="p2-muted">http-server@14.1.2 · 固定Result r{localActions.result_revision} · 演示用途假设。以下由程序依据原文与当前用途整理，不代表许可通过。</p>
    <ol>{localActions.actions.slice(0,3).map(action=><li key={action.code} data-local-action={action.code}>{action.text}<details><summary>查看对应原文与精确来源</summary>{action.clause_indices.map(index=>{const clause=localActions.clauses[index],source=localActions.source_refs.find(ref=>ref.material_id===clause.material_id)!;return <blockquote key={index}>{clause.quote}<small>LICENSE 第{clause.line_start}—{clause.line_end}行 · 字符[{clause.start}, {clause.end}) · {source.source_level} / {source.verification_state}</small><small>Git提交 {source.git_commit} · Material {clause.material_id}</small></blockquote>;})}</details></li>)}</ol>
    {localActions.actions.length>3&&<details><summary>其他核验行动（{localActions.actions.length-3}条）</summary><ul>{localActions.actions.slice(3).map(action=><li key={action.code}>{action.text}</li>)}</ul></details>}
    <details><summary>本版仍未确认的范围与固定身份</summary><p>实际安装或交付范围、正式来源接纳、许可适用性与义务履行仍待核验；Git原文不能替代npm发行包关系。</p><pre>{JSON.stringify({result_id:localActions.result_id,result_revision:localActions.result_revision,result_sha256:localActions.result_sha256,subject:localActions.subject,binding:localActions.binding,content_sha256:localActions.content_sha256,gaps:localActions.gaps},null,2)}</pre></details>
   </div>}
   {localActions?.state==='awaiting_material'&&<p className="p2-ai-note" data-local-action-gap="saved-material-missing">此固定Result尚未关联这份LICENSE材料，因此本版不生成基于已保存材料的核验行动。上一版材料和行动仍保留，不会跨用途版本自动采用。</p>}
   {preview?.status==='succeeded'&&<OfficialAnalysisPreview preview={preview} usage={r.usage}/>}
   {candidate.limitations.length>0&&<details><summary>本次资料仍不能证明什么</summary><ul>{candidate.limitations.map((v,i)=><li key={i}>{v}</li>)}</ul></details>}
   {data?.adopted_material_ids.length?<p className="p2-ai-note" data-source-adopted="">本版已有采用材料，保持 user_supplied_unverified / pending。{data.runtime_jobs_enabled===false?'本轮不会新增Qwen调用；已有分析与旧结果继续保留。':'新版 Qwen 分析由后台自动安排；旧结果与预览继续保留。'}</p>:<div className="official-adopt">
    {!confirm?<button className="p2-primary" type="button" disabled={!canAdopt} onClick={()=>setConfirm(true)}>预览采用{candidate.coverage==='partial_git_license_only'?' Git':''} LICENSE</button>:<div className="official-confirm" role="group" aria-label="确认采用官方材料"><p>{candidate.coverage==='partial_git_license_only'?'本次仅采用已取得的 Git 原文。npm 版本资料未取得，不能证明 npm 发行包许可关系。 ':''}把这份原文绑定到 http-server@14.1.2，生成当前评估的新 Result{data?.runtime_jobs_enabled===false?'；本轮仅更新材料核验行动，不新增模型调用。':'，并自动分析新版。'}材料仍待核验；这不会确认许可适用或义务履行。</p><div className="p2-actions"><button className="p2-primary" type="button" data-official-adopt-confirm="" disabled={!canAdopt} onClick={()=>void adopt()}>{busy?'正在保存采用结果…':'确认采用 LICENSE 并更新评估'}</button><button type="button" disabled={busy} onClick={()=>setConfirm(false)}>暂不采用</button></div></div>}
    {readOnly&&<p className="p2-muted">当前只读，可查看资料与分析，不能采用或触发新的模型请求。</p>}
   </div>}
  </>}
  {preview?.changes.length? <div className="official-usage-changes"><h3>用途变化如何影响下一步</h3><p className="p2-muted">前后用途由程序比对。不同 Assessment 的材料没有自动互相采用。</p>{preview.changes.map((change,i)=><article key={i} data-preview-change-field={change.field}><div data-program-change-fact=""><p><strong>{usageFields[change.field.replace(/^usage\./,'') as keyof typeof usageFields]??change.field}</strong>：{change.before===true?'是':change.before===false?'否':change.before===null?'未知':JSON.stringify(change.before)} → {change.after===true?'是':change.after===false?'否':change.after===null?'未知':JSON.stringify(change.after)} <small>（程序比对）</small></p>{change.field.startsWith('usage.')&&<p data-program-usage-boundary=""><strong>程序说明：</strong>这是演示用途声明变化，不能证明实际使用、分发或义务履行。</p>}</div>{preview.analysis_protocol==='openguard-qwen-action-plan/2'?<p data-program-plan-change="">系统依据通过核对的用途变化整理：{change.explanation}</p>:change.field.startsWith('usage.')?<details data-usage-model-trace=""><summary>查看 Qwen 原始变更解释（未核验，不作为事实结论）</summary><p className="p2-muted">保留本次模型原文供追溯；它是辅助输出，尚未作为实际使用或履行情况的事实结论。</p><p data-original-model-change="">{change.explanation}</p></details>:<p>模型辅助解释：{change.explanation}</p>}</article>)}</div>:null}
  {data&&<details className="official-trace"><summary>固定对象与实际请求计数</summary><pre>{JSON.stringify({result_id:r.result_id,result_revision:r.revision,result_sha256:r.result_sha256,binding:r.binding,candidate_id:candidate?.candidate_id??null,subject:candidate?.subject??null,commit:candidate?.commit??null,fetch:data.fetch,analysis_state:data.analysis.state,analysis_error_code:data.analysis.error_code,explicit_fetch:data.explicit_fetch??null,analysis_id:data.analysis.analysis_id,preview_id:preview?.preview_id??null,preview_sha256:preview?.preview_sha256??null,adopted_material_ids:data.adopted_material_ids},null,2)}</pre></details>}
  </details>
  {pending&&<div role="status" className="p2-ai-note" data-official-adoption-pending="" data-pending-state={pending.state}><p>{pending.state==='sent'?'采用请求已发出，等待真实回执。':pending.state==='conflict'?'采用请求发生明确冲突，不允许重放。':pending.state==='rejected'?'采用请求已明确拒绝，不允许重放。':'采用请求结果尚未确认。'}本账号原请求与幂等键已保留，刷新不会自动重发。</p><div className="p2-actions"><button type="button" disabled={busy||pending.state==='sent'} onClick={()=>void recover()}>核对原采用请求的保存结果</button><button type="button" disabled={busy||loading||readOnly||disabled||pending.state!=='unknown'||!pending.checked||!candidate} onClick={()=>void adopt(true)}>使用原请求明确恢复采用</button><button type="button" disabled={busy||pending.state==='sent'||!pending.checked} onClick={end}>结束待确认，准备新操作</button>{onReadSavedResult&&pending.checked&&<button type="button" disabled={busy} onClick={onReadSavedResult}>查看服务器当前结果</button>}</div></div>}
  {recoveryNotice&&<p role="status" className="p2-ai-note">{recoveryNotice}</p>}
  <div className="official-read-actions"><button type="button" disabled={loading||busy} onClick={()=>setRefresh(n=>n+1)}>仅刷新取证与分析状态</button><span>刷新只读，不重新取证或生成</span></div>
 </section>;
}
