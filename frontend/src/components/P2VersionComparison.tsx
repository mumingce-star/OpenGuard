import { useEffect, useState } from 'react';
import type { Assessment } from '../services/assessments';
import { usageFields } from '../services/assessments';
import { gapLabel, readPreviousResult, sameBinding, stateLabels, type Binding, type Result, type ResourceResult } from '../services/p2';

// Compare saved values, not recalculation flags. Object key order has no meaning.
function ordered(value:unknown):unknown {
 if(Array.isArray(value))return value.map(ordered);
 if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).sort(([a],[b])=>a.localeCompare(b)).map(([key,item])=>[key,ordered(item)]));
 return value;
}
const equalValue=(a:unknown,b:unknown)=>JSON.stringify(ordered(a))===JSON.stringify(ordered(b));
export function versionDifference(previous:Result,current:Result) {
 if(previous.result_id!==current.previous_result_id||previous.revision+1!==current.revision||previous.data_scope!==current.data_scope||!sameBinding(previous.binding,current.binding))return null;
 const oldRows=new Map(previous.resources.map(row=>[row.subject.resource_id,row]));
 const ids=[...new Set([...current.resources,...previous.resources].map(row=>row.subject.resource_id))];
 const changed=ids.filter(id=>!equalValue(oldRows.get(id),current.resources.find(row=>row.subject.resource_id===id)));
 const stateChanged=current.resources.filter(row=>oldRows.has(row.subject.resource_id)&&oldRows.get(row.subject.resource_id)!.state!==row.state);
 const adviceChanged=current.resources.filter(row=>oldRows.has(row.subject.resource_id)&&!equalValue(oldRows.get(row.subject.resource_id)!.advice,row.advice));
 const observedChange=ids.find(id=>{
  const old=oldRows.get(id),row=current.resources.find(item=>item.subject.resource_id===id);
  return row&&(!old||row.state!==old.state||row.material_ids.some(value=>!old.material_ids.includes(value))||row.answer_ids.some(value=>!old.answer_ids.includes(value)));
 });
 return {ids,defaultResourceId:observedChange??changed[0]??current.recomputed_resource_ids.find(id=>ids.includes(id))??ids[0],
  addedMaterialCount:current.material_ids.filter(id=>!previous.material_ids.includes(id)).length,
  addedAnswerCount:current.answer_ids.filter(id=>!previous.answer_ids.includes(id)).length,
  changedResourceCount:changed.length,stateChangedCount:stateChanged.length,adviceChangedCount:adviceChanged.length,
  recomputedCount:current.recomputed_resource_ids.length,reusedCount:current.reused_resource_ids.length};
}

// Adapted from xzb 02fbbe62 P2VersionComparison; current Assessment-aware service
// remains authoritative. Only explicit saved Result parents are read, never latest.
function SavedResource({value}:{value:ResourceResult|undefined}){
 if(!value)return <p>此版未返回该资源，不能据此认定已删除或不适用。</p>;
 return <>
  <p>准确版本：{value.subject.version??'尚未确定'} · {stateLabels[value.state]}</p>
  <p>范围：{value.scope==='unknown'?'尚待核实':value.scope||'未返回'}</p>
  <p>材料 {value.material_ids.length} 份 · 用户声明 {value.answer_ids.length} 条</p>
  <p>剩余缺口：{value.gaps.length?[...new Set(value.gaps.map(code=>gapLabel(code)))].join('；'):'本版未列出，不代表依据完整'}</p>
  {value.gaps.length>0&&<details><summary>原始缺口代码</summary><p>{value.gaps.join('、')}</p></details>}
  {value.advice.map(d=><div className="p2-version-advice" key={d.usage}>
   <strong>{usageFields[d.usage]}</strong><p>保存用途：{d.saved_value===null?'暂不确定':d.saved_value?'是':'否'}；{d.state==='conditional_candidate'?'资源级有条件候选，适用性待审核':d.state==='not_selected'?'本次未选择，不代表不适用':'判断依据待补齐'}</p>
   {d.conditions.length>0&&<ul>{d.conditions.map((text,i)=><li key={i}>{text}</li>)}</ul>}
   {d.gaps.length>0&&<p>用途缺口：{[...new Set(d.gaps.map(code=>gapLabel(code)))].join('；')}</p>}
   <details><summary>保存的依据引用</summary><p>{d.basis_evidence_ids.join('、')||'本版没有保存用途依据'}</p></details>
  </div>)}
 </>;
}
export function P2VersionComparison({assessment,binding,current,resourceName}:{assessment:Assessment;binding:Binding;current:Result;resourceName:(id:string)=>string}){
 const pairKey=JSON.stringify([assessment.scan_id,assessment.id,assessment.version,binding,current.result_id,current.revision,current.result_sha256]);
 const [savedPair,setSavedPair]=useState<{key:string;value:Result}|null>(null),[requested,setRequested]=useState(0),[loading,setLoading]=useState(false),[error,setError]=useState(''),[selected,setSelected]=useState<{key:string;id:string}|null>(null);
 const previous=savedPair?.key===pairKey?savedPair.value:null;
 useEffect(()=>{
  if(!requested||!current.previous_result_id)return;
  const controller=new AbortController();setSavedPair(null);setLoading(true);setError('');
  void readPreviousResult(assessment,binding,current,controller.signal).then(value=>{if(!controller.signal.aborted)setSavedPair(value?{key:pairKey,value}:null);})
   .catch(e=>{if(!controller.signal.aborted)setError(e instanceof Error?e.message:'前版固定结果读取失败。');})
   .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  return()=>controller.abort();
 },[assessment,binding,current,requested,pairKey]);
 const difference=previous?versionDifference(previous,current):null;
 const ids=difference?.ids??[];
 const selectedId=selected?.key===pairKey&&ids.includes(selected.id)?selected.id:difference?.defaultResourceId;
 return <details className="p2-detail p2-version-comparison" data-p2-version-comparison>
  <summary>新旧结果并排核对 · 当前 r{current.revision}</summary>
  <p>对照同一项目用途评估下补充材料或声明形成的固定结果；用途改动产生的新Assessment不在这里跨版比较。</p>
  {!current.previous_result_id?<p>本结果没有前版引用。</p>:<>
   <button disabled={loading} onClick={()=>setRequested(n=>n+1)}>{loading?'正在读取指定前版…':error?'重试读取指定前版':'读取指定前版并排核对'}</button>
   {error&&<p role="alert">{error} 不会改用其他版本或重新计算。</p>}
   {previous&&difference&&<div data-p2-version-pair data-current-result={current.result_id} data-previous-result={previous.result_id}>
    <p data-p2-difference-summary><strong>本次变化：新增 {difference.addedMaterialCount} 份材料 · 新增 {difference.addedAnswerCount} 条声明</strong><br/>重新核对 {difference.recomputedCount} 个资源，复用 {difference.reusedCount} 个资源；状态变化 {difference.stateChangedCount} 个，建议记录变化 {difference.adviceChangedCount} 个（含依据与缺口，不等于许可结论改变）。</p>
    <p>以下为后端已保存快照原值。重新计算不等于结论已经改变；材料待核验也不代表已获许可。</p>
    <label>选择要核对的资源<select aria-label="选择要核对的资源" value={selectedId??''} onChange={e=>setSelected({key:pairKey,id:e.target.value})}>{ids.map(id=><option key={id} value={id}>{resourceName(id)} · {current.resources.find(r=>r.subject.resource_id===id)?.subject.version??'版本未知'}</option>)}</select></label>
    <div className="p2-version-columns">{[{label:'前版快照',value:previous},{label:'本版快照',value:current}].map(({label,value})=><section aria-label={label} key={value.result_id}>
     <h3>{label} · r{value.revision}</h3><p>{stateLabels[value.state]} · 项目用途评估 v{value.binding.assessment_version}</p>
     <h4>{selectedId?resourceName(selectedId):'没有可核对的资源'}</h4><SavedResource value={value.resources.find(r=>r.subject.resource_id===selectedId)}/>
     <details><summary>固定结果身份</summary><code>{value.result_id}</code><p>SHA256：<code>{value.result_sha256}</code></p></details>
    </section>)}</div>
    <p className="p2-muted">材料观察、用户声明和资源级候选分别保留；并排展示不代表正式来源接纳、许可适用或义务已履行。</p>
   </div>}
  </>}
 </details>;
}
