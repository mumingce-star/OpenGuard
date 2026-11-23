import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { Assessment } from '../services/assessments';
import { usageFields } from '../services/assessments';
import type { Scan } from '../types/domain';
import type { Result } from '../services/p2';
import { aiAnalysisUrl, pendingAiAnalysis, prepareAiAnalysis, readAiAnalysis, readAiIndex, submitAiAnalysis, v4AnalysisProtocol, type P2AiAnalysis as Analysis } from '../services/p2Ai';
import './P2AiAnalysis.css';

type Props={assessment:Assessment;result:Result;scan:Scan;readOnly:boolean;disabled?:boolean;onAddMaterial?:()=>void;automatic?:boolean;automaticAnalysisId?:string|null};
const categories={permission:'原文中的许可表述',condition:'原文中的条件',disclaimer:'原文中的免责声明',other:'其他原文线索'};
const message=(e:unknown)=>e instanceof Error?e.message:'分析暂未读回，已有规则结果保持不变。';
const changeLabels:Record<string,string>={state:'结果状态',material_ids:'材料数量',answer_ids:'回答数量',gaps:'待核对缺口数量'};
const stateLabels:Record<string,string>={unknown:'未知',pending:'待核验',verified:'已核验',rejected:'未接纳',not_selected:'未选择',accepted:'已接纳'};
function changeValue(field:string,value:unknown):string{
 if(['material_ids','answer_ids','gaps'].includes(field)&&Array.isArray(value))return `${value.length} 项`;
 if(field==='state'&&typeof value==='string')return stateLabels[value]??value;
 return typeof value==='string'?value:JSON.stringify(value);
}
/** Model notes are independently versioned, never copied into Result.advice. */
export function P2AiAnalysis({assessment:a,result:r,scan,readOnly,disabled=false,onAddMaterial,automatic=false,automaticAnalysisId=null}:Props){
 const scope=JSON.stringify([a.scan_id,a.id,a.version,r.result_id,r.revision,r.result_sha256,r.binding]);
 const [saved,setSaved]=useState<{scope:string;value:Analysis}|null>(null),[analysisIds,setIds]=useState<string[]>([]);
 const [loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [selected,setSelected]=useState<string[]>([]),[compare,setCompare]=useState(false),[refresh,setRefresh]=useState(0);
 const [v4Capability,setV4Capability]=useState<{scope:string;enabled:boolean}|null>(null);
 const [selectedSubject,setSelectedSubject]=useState('');
 const [pending,setPending]=useState(()=>pendingAiAnalysis(r));
 const owner=useRef({scope:'',epoch:0,mounted:false}),permission=useRef({scope:'',epoch:0,writable:false}),lock=useRef(false);
 const readController=useRef<AbortController|null>(null);
 const currentParent=r.binding.scan_id===a.scan_id&&r.binding.assessment_id===a.id&&r.binding.assessment_version===a.version&&scan.id===a.scan_id;
 const v4Enabled=v4Capability?.scope===scope&&v4Capability.enabled;
 const availableSubjects=r.resources.filter(row=>row.resource_kind==='component').flatMap(row=>{
  const item=scan.resources.find(resource=>resource.id===row.subject.resource_id&&resource.version===row.subject.version);
  return item&&['npm','pypi'].includes(item.ecosystem??'')?[{row,item}]:[];
 });
 const subject=availableSubjects.find(entry=>entry.row.subject.resource_id===selectedSubject)??availableSubjects[0];
 const allowedMaterials=v4Enabled?(subject?.row.material_ids??[]):r.material_ids;
 const chosenMaterials=selected.filter(id=>allowedMaterials.includes(id));
 useLayoutEffect(()=>{
  const o=owner.current;o.scope=scope;o.epoch++;o.mounted=true;lock.current=false;
  return()=>{o.mounted=false;o.epoch++;readController.current?.abort();};
 },[scope]);
 useLayoutEffect(()=>{
  const p=permission.current;p.scope=scope;p.epoch++;p.writable=currentParent&&!readOnly&&!disabled;
  return()=>{p.writable=false;p.epoch++;};
 },[scope,readOnly,disabled,currentParent]);
 useEffect(()=>{
  const c=new AbortController();readController.current?.abort();readController.current=c;
  const epoch=owner.current.epoch,current=()=>!c.signal.aborted&&owner.current.mounted&&owner.current.scope===scope&&owner.current.epoch===epoch;
  setSaved(null);setIds([]);setError('');setNotice('');setBusy(false);setSelected(r.material_ids.slice(0,4));setCompare(!!r.previous_result_id);setPending(pendingAiAnalysis(r));setLoading(true);
  setSelectedSubject('');setV4Capability(null);
  if(!currentParent){setLoading(false);return()=>c.abort();}
  void (async()=>{try{
   const ids=await readAiIndex(a,r,c.signal,enabled=>{
    if(!current())return;
    setV4Capability({scope,enabled});
    if(enabled)setSelected(availableSubjects[0]?.row.material_ids.slice(0,4)??[]);
   });if(!current())return;
   // Server index is immutable save order (oldest first). Prefer the latest
   // saved record on refresh, while keeping every earlier failure selectable.
   const newest=[...ids].reverse();setIds(newest);
   // Read the exact saved record that resolves this request, if one exists.
   const awaiting=pendingAiAnalysis(r);let choice:Analysis|null=null;
   for(const id of newest){const value=await readAiAnalysis(a,r,id,c.signal,scan);if(!current())return;
    if(!choice)choice=value;if(awaiting&&value.idempotency_key===awaiting.body.idempotency_key){choice=value;break;}if(!awaiting)break;}
   if(current()){setSaved(choice?{scope,value:choice}:null);setPending(pendingAiAnalysis(r));}
  }catch(e){if(current())setError(message(e));}finally{if(current())setLoading(false);}})();
  return()=>c.abort();
 },[scope,refresh,currentParent,automaticAnalysisId]);
 const analysis=saved?.scope===scope?saved.value:null;
 const v4=analysis?.analysis_protocol===v4AnalysisProtocol?analysis:null;
 const structured=!!v4||analysis?.analysis_protocol==='openguard-qwen-action-plan/2'&&analysis.validation_details?.status==='validated';
 const validSelection=v4Enabled?!!subject&&!!scan.declarationSnapshot:chosenMaterials.length>0;
 async function selectAnalysis(id:string){
  readController.current?.abort();const c=new AbortController();readController.current=c;
  const epoch=owner.current.epoch;setLoading(true);setError('');
  const current=()=>!c.signal.aborted&&owner.current.mounted&&owner.current.scope===scope&&owner.current.epoch===epoch;
  try{const value=await readAiAnalysis(a,r,id,c.signal,scan);if(current()){setSaved({scope,value});setPending(pendingAiAnalysis(r));}}
  catch(e){if(current())setError(message(e));}finally{if(current())setLoading(false);}
 }
 async function generate(){
  const o=owner.current,p=permission.current,epoch=o.epoch,permitEpoch=p.epoch;
  const permitted=()=>o.mounted&&o.scope===scope&&o.epoch===epoch&&p.scope===scope&&p.epoch===permitEpoch&&p.writable;
  if(automatic||!permitted()||lock.current||busy||loading||!validSelection||pendingAiAnalysis(r))return;
  const current=()=>o.mounted&&o.scope===scope&&o.epoch===epoch;
  let sent=false;lock.current=true;setBusy(true);setError('');setNotice('');
  try{
   const body=prepareAiAnalysis(a,r,chosenMaterials,compare,v4Enabled?subject?.row.subject:undefined);
   // There is no async read/preparation before Service dispatch. A committed
   // readOnly/scope change cannot release a queued downstream model POST.
   const flight=submitAiAnalysis(a,r,body,permitted,scan);sent=!!pendingAiAnalysis(r);setPending(pendingAiAnalysis(r));
   const value=await flight;
   if(!current())return;setSaved({scope,value});setIds(ids=>[value.analysis_id,...ids.filter(id=>id!==value.analysis_id)]);setPending(pendingAiAnalysis(r));
   setNotice(value.status==='succeeded'?'已保存本版独立模型分析，原Result与材料核验状态未改变。':'本次模型分析未通过，失败回执已保存；原Result仍可读取。');
  }catch(e){if(current()){setPending(pendingAiAnalysis(r));setError((sent?'本次请求可能已经到达服务端；先读取保存记录，不会自动重发。 ':'')+message(e));}}
  finally{if(current()){lock.current=false;setBusy(false);}}
 }
 const resourceName=(materialId:string)=>{const row=r.resources.find(x=>x.material_ids.includes(materialId));const resource=scan.resources.find(x=>x.id===row?.subject.resource_id&&x.version===row.subject.version);return resource?`${resource.name} @ ${resource.version}`:'本版已绑定材料';};
 const canGenerate=!automatic&&currentParent&&!readOnly&&!disabled&&!busy&&!loading&&!pending&&validSelection;
 return <section className={'p2-ai-analysis p2-main-card'+(analysis?.status==='succeeded'?' has-saved-analysis':' is-status-only')} data-p2-ai-analysis="" data-result-id={r.result_id} aria-label="材料与用途AI分析">
  <header className="p2-ai-header"><div><div className="p2-step">独立辅助分析 · 固定结果 r{r.revision}</div><h2>{analysis?.status==='succeeded'?'Qwen3 · 从材料到行动':'从材料到行动的 AI 辅助分析'}</h2></div><span className="p2-ai-label">{busy?'等待本地模型回执':pending?pending.state==='sent'?'模型请求已发出':'请求结果待确认':loading?'正在读取已保存分析':analysis?.status==='succeeded'?structured?'用途与依据已核对':'模型原文 · 待人工核对':analysis?.status==='failed'?'本次分析失败':'本版尚无已保存分析'}</span></header>
  <p>以本版保存材料和演示用途为输入，定位原文、解释下一步，并说明同一用途版本内的结果变化。只生成核验行动，不决定是否获准使用。</p>
  {loading&&<p role="status">正在只读获取本版已保存的分析…</p>}
  {error&&<p className="p2-ai-error" role="alert">{error} 确定性结果保持可读。</p>}
  {notice&&<p className="p2-ai-note" role="status">{notice}</p>}
  {pending&&<p className="p2-ai-note" data-ai-pending="">{pending.state==='sent'?'本版模型请求已发出，等待真实回执。':'本版请求结果尚未确认。请读取已保存分析；不会自动重放或重建请求键。'}</p>}
  <details className="p2-ai-controls"><summary>查看输入范围与分析操作<span>{r.material_ids.length?`${r.material_ids.length} 份本版保存材料`:'本版尚未绑定材料'}</span></summary>
  <p className="p2-muted">{v4Enabled?'分析绑定资源的 v4 研判和本次所选材料。无材料时可解释待核验事项，上传材料仍须核对来源。':'仅分析你在本版选择的已绑定材料；服务端会核对资源、版本、原文字节和引用范围。可用材料范围由服务器配置与校验共同限定，上传不等于来源已认证。'}</p>
  {!r.material_ids.length&&!v4Enabled?<p className="p2-ai-empty">本版尚未绑定 LICENSE / NOTICE。先补充准确资源的原文，已有扫描与规则结论仍可阅读。{onAddMaterial&&<button type="button" disabled={readOnly||disabled} onClick={onAddMaterial}>补充本版材料</button>}</p>:<>
   {!automatic&&<>
   {v4Enabled&&<label>本次分析的扫描资源 <select value={subject?.row.subject.resource_id??''} disabled={busy||loading||readOnly||disabled||!!pending}
      onChange={e=>{const id=e.target.value;setSelectedSubject(id);setSelected(availableSubjects.find(entry=>entry.row.subject.resource_id===id)?.row.material_ids.slice(0,4)??[]);}}>
      {!availableSubjects.length&&<option value="">当前没有可分析的 npm 或 PyPI 资源</option>}
      {availableSubjects.map(({row,item})=><option key={row.subject.resource_id} value={row.subject.resource_id}>{item.name} @ {item.version??'版本未确定'}</option>)}
   </select></label>}
   {v4Enabled&&!scan.declarationSnapshot&&<p className="p2-ai-note">扫描声明依据尚未核对，请重新读取本版扫描后再生成。</p>}
   {v4Enabled&&subject&&!allowedMaterials.length&&<p className="p2-ai-empty">此资源暂无已绑定材料，本次可解释规则结果与待补事项。{onAddMaterial&&<button type="button" disabled={readOnly||disabled} onClick={onAddMaterial}>补充本版材料</button>}</p>}
   {(allowedMaterials.length>0||!v4Enabled)&&<fieldset className="p2-ai-materials" disabled={busy||loading||readOnly||disabled||!!pending}><legend>本次分析哪些已保存材料（最多4份）</legend>{allowedMaterials.map((id,i)=><label key={id}><input type="checkbox" checked={chosenMaterials.includes(id)} disabled={!chosenMaterials.includes(id)&&chosenMaterials.length>=4} onChange={e=>setSelected(items=>e.target.checked?[...items,id]:items.filter(x=>x!==id))}/><span>{resourceName(id)} · 材料 {i+1}<small>{id}</small></span></label>)}{!v4Enabled&&r.previous_result_id&&<label><input type="checkbox" checked={compare} onChange={e=>setCompare(e.target.checked)}/>同时解释同一Assessment内前一版与本版的变化</label>}</fieldset>}
   <div className="p2-ai-actions"><button className="p2-primary" type="button" disabled={!canGenerate} onClick={()=>void generate()}>{busy?'正在等待本地模型…':analysis?'明确重新生成本版分析':'生成本版 Qwen 分析'}</button><button type="button" disabled={busy||loading} onClick={()=>setRefresh(n=>n+1)}>仅重新读取已保存分析</button></div>
   </>}
   {automatic?<p className="p2-ai-note">自动分析与最多一次定向纠错以官方资料区的实际记录为准；超时或结果不确定不会自动重发。本区仅重新读取已有分析，不触发生成。<button type="button" disabled={loading} onClick={()=>setRefresh(n=>n+1)}>仅重新读取已保存分析</button></p>:<p className="p2-muted">{readOnly?'当前为只读：只能查看，不能触发模型。':disabled?'当前对象正在变更，请先完成用途或材料保存。':'生成由你明确触发；刷新、查看历史和下载不会调用模型。重新生成会新增一次调用。'}</p>}
  </>}
  </details>
  {analysis&&<div className="p2-ai-saved" data-analysis-id={analysis.analysis_id} data-analysis-status={analysis.status}>
   {analysis.analysis_protocol===v4AnalysisProtocol?<>
    <p className="p2-ai-provenance" data-v4-analysis-subject="">{analysis.context.subject.component_name} @ {analysis.context.subject.version??'版本未确定'} · {analysis.material_claims_view_id}</p>
    <p className="p2-ai-note">{analysis.context.incremental_impact_summary.mode==='INITIAL_RESULT'?'v4 初始研判':`v4 增量研判 · r${r.revision-1} → r${r.revision}`} · 模型 {analysis.model.name} · {analysis.metrics.elapsed_ms} ms · {analysis.model_calls} 次调用</p>
    <p className="p2-muted">模型摘要 {analysis.model.digest} · {analysis.model.prompt_version}</p>
    {analysis.status==='succeeded'?<>
     <div className="p2-ai-action-list"><h3>系统核对后的行动</h3><ol>{analysis.actions.map(item=><li key={item.action_kind} data-bound-action-kind={item.action_kind}><p>{item.text}</p></li>)}</ol></div>
     {!!analysis.clauses.length&&<details className="p2-ai-clauses"><summary>查看建议对应的原文（{analysis.clauses.length}处）</summary>{analysis.clauses.map(clause=><article key={clause.quote_id}><blockquote>{clause.quote}</blockquote><small>原文字节 [{clause.byte_start}, {clause.byte_end})</small></article>)}</details>}
     {!!analysis.changes.length&&<div className="p2-ai-changes"><h3>本次变更</h3>{analysis.changes.map(change=><p key={change.index}>{change.explanation}</p>)}</div>}
    </>:<p className="p2-ai-error">本次结构化分析未通过（{analysis.error_code}）。既有规则与 v4 结论未受影响。</p>}
   </>:analysis.status==='succeeded'?<>
    <p className="p2-ai-provenance">真实本地模型：{analysis.model.name} · {new Date(analysis.created_at).toLocaleString()} · 用途为演示假设</p>
    {structured?<p className="p2-ai-note" data-structured-plan-origin="">Qwen选取依据，系统核对后整理</p>:<p className="p2-ai-note" data-legacy-model-review="">以下为模型生成的辅助解释，未经过结构化用途行动核对，需人工复核，不作为已确认的用途或许可事实。</p>}
    <div className="p2-ai-action-list"><h3>现在可以做什么</h3><ol>{analysis.actions.map((item,i)=><li key={i} data-bound-action-kind={structured?item.action_kind:undefined} data-bound-action-basis={structured?item.basis_kind:undefined}><p>{item.text}</p>{structured&&item.basis_kind==='usage_gap'?<small data-usage-gap-basis="">自动补证 · 当前演示用途：{item.usage_fields?.map(key=>`${usageFields[key]}＝${r.usage[key]===true?'是':r.usage[key]===false?'否':'暂不确定'}`).join('；')}。依据是用途声明与缺失的对象／范围材料，没有把本 LICENSE 当作其他资源的许可。</small>:<small>材料依据：{item.source_material_ids.map(id=>resourceName(id)).join('；')} · 核验行动建议</small>}</li>)}</ol></div>
    <details className="p2-ai-clauses"><summary>查看建议对应的原文（{analysis.clauses.length}处）</summary>{analysis.clauses.map((c,i)=><article key={i}><strong>{categories[c.category]} · {resourceName(c.material_id)}</strong><blockquote>{c.quote}</blockquote><small>材料内字符位置 [{c.start}, {c.end})；服务端核对原文引用，仍是待核验材料。</small></article>)}</details>
    <div className="p2-ai-changes"><h3>与前版相比</h3>{analysis.previous_result_id?<><p>仅比较同一用途评估中的固定Result；以下前后值由程序计算，{structured?'系统依据核对后的结构选择整理说明。':'模型只解释其含义。'}</p>{analysis.changes.length?analysis.changes.map((c,i)=><article key={i} data-ai-change-field={c.field}><p className="p2-ai-computed-change"><strong>{changeLabels[c.field]??c.field}</strong>：{changeValue(c.field,c.before)} → {changeValue(c.field,c.after)} <small>（程序计算）</small></p><p><span className="p2-muted">{structured?'系统说明：':'模型解释：'}</span>{c.explanation}</p><details><summary>查看此项完整前后值</summary><pre>{JSON.stringify({field:c.field,before:c.before,after:c.after},null,2)}</pre></details></article>):<p>所选前版与本版没有已记录的可解释差异。</p>}</>:<p>本次未选择同一评估内的前版。不同用途评估之间不套用材料或解释。</p>}</div>
   </>:<p className="p2-ai-error">{analysis.validation_details?.issues?.some(issue=>issue.code==='plan_change_kind')?'用途变更分类未通过校验；本次结果未展示，原记录保留。':analysis.error_code==='p2_ai_model_unavailable'?'本地模型运行未完成或结果不确定，不会自动重新生成。':'模型没有返回可接纳的完整分析。'}{analysis.validation_details?.corrective_attempt_used?'一次定向纠错也未通过，已停止；仅需处理这次异常。':'未生成替代成功正文。'}规则结果及旧分析继续保留。</p>}
   {analysis.limitations.length>0&&<div className="p2-ai-limits"><h3>仍需补齐与核验</h3><ul>{analysis.limitations.map((text,i)=><li key={i}>{text}</li>)}</ul></div>}
   <p className="p2-ai-boundary">材料保持 user_supplied_unverified / pending。AI解释不是正式来源签发、许可适用结论或义务履行证明。</p>
   <details><summary>本版分析身份、材料Hash与运行记录</summary><pre>{JSON.stringify({analysis_id:analysis.analysis_id,analysis_sha256:analysis.analysis_sha256,result_id:analysis.result_id,result_revision:analysis.result_revision,result_sha256:analysis.result_sha256,binding:analysis.binding,previous_result_id:analysis.previous_result_id,previous_result_sha256:analysis.previous_result_sha256,model:analysis.model,created_at:analysis.created_at,input_sha256:analysis.input_sha256,source_refs:analysis.source_refs,model_calls:analysis.model_calls,metrics:analysis.metrics,changes:analysis.changes},null,2)}</pre><a href={aiAnalysisUrl(a,r,analysis.analysis_id)} download>下载这份固定分析 JSON</a></details>
  </div>}
  {analysisIds.length>1&&<details><summary>本结果的已保存分析（{analysisIds.length}份）</summary><ul>{analysisIds.map(id=><li key={id}><button type="button" disabled={busy||loading||id===analysis?.analysis_id} onClick={()=>void selectAnalysis(id)}>{id===analysis?.analysis_id?'当前分析':'读取该固定分析'} · {id.slice(0,22)}…</button></li>)}</ul></details>}
 </section>;
}
