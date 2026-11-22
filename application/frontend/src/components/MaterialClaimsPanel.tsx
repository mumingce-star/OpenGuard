import type { DeclarationSnapshot } from '../types/domain';
import { useEffect, useState } from 'react';
import type { Assessment } from '../services/assessments';
import { usageFields } from '../services/assessments';
import { readPreviousResult, type Result } from '../services/p2';
import { readMaterialClaims, type MaterialClaims, type ClaimState } from '../services/materialClaims';

const labels:Record<ClaimState,string>={SUPPORT:'有条件文本支持',RESTRICTION:'存在尚未满足的条件',UNKNOWN:'依据不足，保持未知',COUNTER_EVIDENCE:'发现相冲突的证据',NOT_COVERED:'本次用途或资源未覆盖'};
const clauseLabels:Record<string,string>={license_identifier:'许可证标识',copyright:'版权声明',permission:'用途权限段',condition:'条件与义务',warranty:'免责范围',notice:'NOTICE声明'};
const parseLabels={MATCHED_MIT:'完整 MIT 文本匹配',MATCHED_APACHE_2_0:'完整 Apache-2.0 文本匹配',NOTICE_OBSERVED:'NOTICE 已读取，不能单独授予权利',UNSUPPORTED:'文本或许可证组合尚不支持',FAILED:'解析失败'};
const reasons:Record<string,string>={USE_NOT_SELECTED:'本次没有选择此用途。',RESOURCE_KIND_NOT_COVERED:'首期规则不覆盖此类资源。',USAGE_UNDECLARED:'尚未明确此用途。',SPDX_TEXT_CONFLICT:'许可证标识与绑定文本冲突。',BOUND_LICENSE_BYTES_CONFLICT:'同一资源绑定了不同许可证材料。',BOUND_NOTICE_BYTES_CONFLICT:'上传的 NOTICE 与固定发行包中的 NOTICE 字节不一致。',NOTICE_REQUIRES_REVIEW:'附加 NOTICE 需要进一步解释。',NOTICE_MATCHED_REQUIRES_HUMAN_OBLIGATION_REVIEW:'NOTICE 字节与固定发行包一致，仍需人工核对 Apache-2.0 §4(d) 的声明保留义务。',MULTI_LICENSE_NOT_SUPPORTED:'多许可证组合需要单独审核，不能任选一个许可。',MISSING_LICENSE_MATERIAL:'缺少完整许可证材料。',UNSUPPORTED_OR_FAILED_TEXT:'材料未通过当前完整文本规则。',SOURCE_OR_EVIDENCE_BINDING_NOT_ESTABLISHED:'精确版本来源或证据绑定尚不充分。',USER_REPORTS_DELIVERY_OBLIGATION_UNFULFILLED:'用户声明交付义务尚未履行；具体义务对象与范围仍需明确。',SPDX_NORMALIZATION_CONFLICT:'许可表达式与归一化标识冲突。',COUNTER_EVIDENCE_SOURCE_UNKNOWN:'该反证的部分来源尚不足，引用不作补造。',PINNED_RELEASE_AND_COMPLETE_MIT_CONDITIONAL_TEXT:'完整 MIT 文本与固定发行材料相符，仅为当前资源的有条件建议。',PINNED_RELEASE_AND_COMPLETE_APACHE_2_0_CONDITIONAL_TEXT:'完整 Apache-2.0 文本与固定发行材料相符，仅为当前资源的有条件建议。'};
const roleConflictLabels:Record<string,string>={
 dependency_declaration_conflict:'依赖声明不一致',
 lock_version_conflict:'锁文件版本冲突',
 lock_root_mismatch:'锁文件与根清单不一致',
 contradictory_role_evidence:'角色证据相互矛盾',
};
const claimStates = Object.keys(labels) as ClaimState[];
const countLabels:Record<ClaimState,string>={SUPPORT:'有条件支持',RESTRICTION:'条件未满足',UNKNOWN:'依据不足',COUNTER_EVIDENCE:'材料冲突',NOT_COVERED:'本次未覆盖'};
const claimUses = ['commercial', 'distributed', 'modified'] as const;

function nextClaimAction(view: MaterialClaims, counts: Record<ClaimState, number>) {
 const reasons = new Set(view.advice.flatMap(advice => advice.reasons));
 if (counts.COUNTER_EVIDENCE) return '先核对冲突材料及其固定版本来源。';
 if (reasons.has('NOTICE_MATCHED_REQUIRES_HUMAN_OBLIGATION_REVIEW') || reasons.has('NOTICE_REQUIRES_REVIEW')) {
  return '人工核对 NOTICE 的内容及附带义务。';
 }
 if (counts.RESTRICTION) return '核对并处理尚未满足的条件。';
 if (reasons.has('MISSING_LICENSE_MATERIAL')) return '在当前可写版本补充缺失资源的完整 LICENSE。';
 if (counts.UNKNOWN) return '补齐对应资源的固定版本或绑定证据。';
 if (counts.SUPPORT) return '核对列明的条件后，可导出本版评估包。';
 return '确认本版用途和核对范围。';
}

export function MaterialClaimsPanel({assessment,result,resourceName,declarationSnapshot}:{assessment:Assessment;result:Result;declarationSnapshot:DeclarationSnapshot|null|undefined;resourceName:(id:string)=>string}){
 const key=JSON.stringify([assessment.scan_id,assessment.id,assessment.version,result.result_id,result.result_sha256,result.binding,declarationSnapshot]);
 const [reload,setReload]=useState(0),[compareKey,setCompareKey]=useState<string|null>(null);
 const [state,setState]=useState<{key:string;current:MaterialClaims}|null>(null);
 const [loading,setLoading]=useState(false),[error,setError]=useState<{key:string;message:string}|null>(null);
 const [comparison,setComparison]=useState<{key:string;status:'loading'|'ready'|'error';previous:MaterialClaims|null;message:string}|null>(null);
 const [compareRetry,setCompareRetry]=useState(0);
 useEffect(()=>{
  const controller=new AbortController();setState(null);setError(null);setLoading(true);
  void readMaterialClaims(assessment,result,declarationSnapshot,controller.signal).then(current=>{
   if(!controller.signal.aborted)setState({key,current});
  }).catch(e=>{if(!controller.signal.aborted)setError({key,message:e instanceof Error?e.message:'材料建议读取失败。'});})
    .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  return()=>controller.abort();
 },[assessment,result,declarationSnapshot,key,reload]);
 useEffect(()=>{
  if(compareKey!==key||state?.key!==key||!result.previous_result_id)return;
  const controller=new AbortController();
  setComparison({key,status:'loading',previous:null,message:''});
  void (async()=>{
   const parent=await readPreviousResult(assessment,result.binding,result,controller.signal);
   if(!parent)throw Error('指定前版结果未取得，未改用其他版本。');
   const previous=await readMaterialClaims(assessment,parent,declarationSnapshot,controller.signal);
   if(!controller.signal.aborted)setComparison({key,status:'ready',previous,message:''});
  })().catch(e=>{if(!controller.signal.aborted)setComparison({key,status:'error',previous:null,message:e instanceof Error?e.message:'前版读取失败。'});});
  return()=>controller.abort();
 },[assessment,result,declarationSnapshot,key,state,compareKey,compareRetry]);
 const view=state?.key===key?state.current:null;
 const previousState=comparison?.key===key?comparison:null;
 const old=previousState?.status==='ready'?previousState.previous:null;
 const currentError=error?.key===key?error.message:'';
 const counts:Record<ClaimState,number>={SUPPORT:0,RESTRICTION:0,UNKNOWN:0,COUNTER_EVIDENCE:0,NOT_COVERED:0};
 for(const advice of view?.advice??[])counts[advice.state]++;
 const selectedUses=claimUses.filter(use=>result.usage[use]===true).map(use=>usageFields[use]);
 const shownResources=result.resources.slice(0,2).map(({subject})=>`${resourceName(subject.resource_id)} @ ${subject.version??'版本未知'}`);
 const completeDeclarations=view?.declaration_observations.filter(source=>source.evidence_status==='COMPLETE').length??0;
 const addedMaterials=new Set(view?.incremental_impact.added_material_ids);
 return <section className="p2-main-card" aria-label="材料与用途证据链" data-material-claims style={{overflowWrap:'anywhere'}}>
  <div className="p2-step">材料与用途 · r{result.revision} · v4</div><h2>材料与用途证据链</h2>
  <p>商业使用、分发和内部修改分别判断；未提到的依赖和用途不会自动获得支持。条款匹配不代表许可适用性或实际履行已经签认。</p>
  {loading&&<p role="status">正在读取本版材料、解析状态和证据链…</p>}
  {currentError&&<p role="alert">{currentError} 已保存结果保持不变。</p>}
  {currentError&&<button onClick={()=>setReload(n=>n+1)}>重新读取本版</button>}
  {view&&<>
   <section className="p5-claims-overview" aria-label="本次研判概览" data-p5-assessment-overview="">
    <header><h3>本次研判概览</h3><span>r{view.revision} · {view.data_scope}</span></header>
    <p><strong>分析对象：</strong>{shownResources.join('、')||'暂无资源'}{result.resources.length>2&&`；其余 ${result.resources.length-2} 个资源见下方`}。</p>
    <p><strong>所选用途：</strong>{selectedUses.join('、')||'本版未选择商业、分发或修改'}。</p>
    <dl className="p5-claim-state-counts">
     {claimStates.map(state=><div key={state} data-claim-state={state}><dt>{countLabels[state]}</dt><dd>{counts[state]}</dd></div>)}
    </dl>
    <p><strong>风险状态：</strong>{counts.COUNTER_EVIDENCE?'存在材料冲突，优先复核反证。':counts.RESTRICTION?'有条件尚未满足。':counts.UNKNOWN?'有用途仍缺少可判定依据。':'当前未检出材料冲突或未满足条件，逐项查看适用范围。'}</p>
    <p><strong>证据充分程度：</strong>{completeDeclarations}/{view.declaration_observations.length} 个资源的扫描声明引用完整；{view.source_observations.length} 个资源有固定发行包观察。</p>
    <p><strong>条款适用性未人工签认。</strong></p>
    <p><strong>下一步：</strong>{nextClaimAction(view,counts)}</p>
   </section>
   <p>上传与绑定：本版保存 {view.materials.length} 份材料。解析状态及采用范围如下；未上传不等于已经解析成功。</p>
   {!view.materials.length&&<p>请通过“补充 LICENSE / NOTICE”面板上传材料并选择准确资源和证据。上传成功将保存新版本，本版不被覆盖。</p>}
   {view.incremental_impact.mode==='INCREMENTAL_DERIVED'&&<details open data-p5-incremental-impact="">
    <summary>增量重研判 · r{view.incremental_impact.previous_revision} → r{view.revision}</summary>
    <p>重算 {view.incremental_impact.affected_resource_ids.length} 个资源、{view.incremental_impact.recomputed_claim_ids.length} 条主张。保留 {view.incremental_impact.unchanged_resource_ids.length} 个资源、{view.incremental_impact.reused_claim_ids.length} 条主张，语义核对通过。</p>
    {!!view.incremental_impact.changed_claims.length&&<ul>{view.incremental_impact.changed_claims.map(delta=><li key={delta.current_claim_id}>
     <strong>{resourceName(delta.subject.resource_id)} · {usageFields[delta.usage]}：</strong>{labels[delta.previous_state]} → {labels[delta.current_state]}
     <p>{delta.current_reasons.map(reason=>reasons[reason]??'该项依据仍需审核。').join(' ')}</p>
     <p>触发材料：{delta.trigger_material_ids.join('、')||'无'} · 触发回答：{delta.trigger_answer_ids.join('、')||'无'}</p>
    </li>)}</ul>}
   </details>}
   {view.advice.map(a=>{
    const link=view.claims.find(c=>c.claim_id===a.claim_ids[0]);
    return <article className="p2-version-advice" key={`${a.subject.resource_id}:${a.usage}`}>
     <h3>{resourceName(a.subject.resource_id)} @ {a.subject.version??'版本未知'} · {usageFields[a.usage]}</h3>
     <strong>{labels[a.state]}</strong>
     <ul>{a.reasons.map(x=><li key={x}>{reasons[x]??'该项依据仍需审核。'}</li>)}</ul>
     {!!a.conditions.length&&<><h4>必须保留的条件</h4><ul>{a.conditions.map(x=><li key={x}>{x}</li>)}</ul></>}
     <details><summary>范围、反证与证据关联</summary><ul>{a.limitations.map(x=><li key={x}>{x}</li>)}</ul>
      {link?.counter_evidence.map((e,i)=><p key={i}>{reasons[e.code]??'存在需复核的材料。'}<br/>材料：{e.material_ids.join('、')}<br/>Evidence：{e.evidence_ids.join('、')||'无可确认的扫描Evidence引用'}<br/>声明Evidence：{e.declaration_evidence_ids.join('、')||'无'}<br/>归档来源观察：{e.source_observation_ids.join('、')||'无'}<br/>来源状态：{e.evidence_status==='COMPLETE'?'引用完整（不代表法律结论已确认）':'UNKNOWN：来源不足'}</p>)}
      <p>Evidence：{link?.evidence.map(e=>e.evidence_id).join('、')||'尚无可引用的材料证据'}</p>
      <p>ClaimLink：<code>{link?.claim_id}</code></p>
     </details>
    </article>;
   })}
   <h3>扫描许可证声明来源</h3>
   <p>声明集合与既有扫描报告及本版Evidence Hash核对；这不等于独立认证服务器或许可证真实性。</p>
   {view.declaration_observations.map(d=><details key={d.subject.resource_id}><summary>{resourceName(d.subject.resource_id)} @ {d.subject.version??'版本未知'} · {d.expression} · {d.evidence_status}</summary>
    <p>归一化标识：{d.normalized_ids.join('、')||'缺失'}；来源不足时不能产生用途支持。</p>
    <ul>{d.evidence.map(e=><li key={e.evidence_id}>{e.evidence_id} · {e.source_sha256??'Hash未知'}</li>)}</ul>
   </details>)}
   <h3>发行材料来源闭包</h3>
   {!view.source_observations.length&&<p>尚无可绑定到该资源版本的来源包观察，不能断言不存在NOTICE。</p>}
   {view.source_observations.map(o=><details key={o.source_observation_id}><summary>{resourceName(o.subject.resource_id)} @ {o.subject.version} · {{ABSENT_COMPLETE:'支持范围内完整盘点，未发现NOTICE',PRESENT_UNREVIEWED:'发现NOTICE，尚未解释',INCOMPLETE:'检查不完整',INVALID:'成员超限、格式不支持或解析失败'}[o.notice_status]}</summary>
    <p>{o.member_count} 个已盘点成员；归档SHA256：<code>{o.archive_sha256}</code></p>
    <p>该观察来自固定发行包，不是新增上传Material，也不是自动生成的扫描Evidence。</p>
    <ul>{o.notices.map(n=><li key={n.path}>{n.path} · {n.bytes} 字节 · {n.inspection_state} · {n.sha256??'Hash未取得'}</li>)}</ul>
   </details>)}
   <h3>材料、解析和原文定位</h3>
   {view.materials.map(m=><details className="p2-detail p5-material-card" key={m.material_id}
    data-p5-material-card="" data-parse-state={m.parse_state} data-incremental-trigger={String(addedMaterials.has(m.material_id))}>
    <summary><strong>{m.filename} · {resourceName(m.subject.resource_id)} @ {m.subject.version}</strong>
     <span className="p5-material-chain" data-p5-material-chain="">
      <span data-stage="uploaded">已上传</span>
      <span data-stage="parsed">已解析 · {parseLabels[m.parse_state]}</span>
      <span data-stage="bound">已绑定本版</span>
      <span data-stage="adoption">采用状态 · {m.adoption_state==='CONDITIONAL_TEXT_BASIS'?'进入有条件文本建议':'仅材料观察'}</span>
      <span data-stage="incremental">增量触发 · {addedMaterials.has(m.material_id)?'计入本版新增材料':'未计入本版新增材料'}</span>
     </span>
    </summary>
    <p>声明标识：{m.declared_spdx}；文本识别：{m.text_license}。{m.license_version===null?'上方为资源版本。':`许可证版本 ${m.license_version}，资源版本 ${m.subject.version??'未知'}。`}</p>
    <p>资源角色：{m.role==='root_package'?'项目根包':m.role==='dependency'?'依赖':'未知'}（{m.role_state==='observed'?'直接观察':m.role_state==='inferred'?'依据扫描信息推断':'缺少角色证据'}），不表示已经交付。</p>
    {!!m.role_conflicts.length&&<p>角色证据冲突：{m.role_conflicts.map(code=>roleConflictLabels[code]??code).join('、')}</p>}
    <p>材料绑定Evidence：{m.evidence.map(e=>e.evidence_id).join('、')}；角色推断依据：{m.role_basis_evidence_ids.join('、')||'缺少可核对依据，保持未知'}。</p>
    <p>SHA256：<code>{m.source_sha256}</code> · {m.byte_count} 字节</p>
    {m.clauses.map(c=><div key={c.clause_id}>
     <h4>{clauseLabels[c.kind]??'原文片段'} · 第{c.line_start}–{c.line_end}行</h4>
     <p>UTF-8字节区间 [{c.byte_start}, {c.byte_end})；显示文本的片段SHA256已重新核对。完整原材料未在浏览器独立认证。</p>
     <pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{c.quote}</pre>
    </div>)}
    {!m.clauses.length&&<p>未取得可支持的条款定位，不能以标题或文件名推定许可。</p>}
   </details>)}
   {result.previous_result_id&&<button disabled={loading||previousState?.status==='loading'} onClick={()=>{setCompareKey(key);setCompareRetry(n=>n+1);}}>读取指定前版的材料建议进行对照</button>}
   {previousState?.status==='loading'&&<p role="status">正在独立读取指定前版；当前版继续展示。</p>}
   {previousState?.status==='error'&&<p role="alert">前版比较未完成：{previousState.message} 当前版已验证的建议保持展示，未替换为最新结果。</p>}
   {old&&<details open><summary>本版 r{view.revision} 与前版 r{old.revision} 的材料建议</summary>
    <p>同一版本化规则分别读取各版已有材料，没有把本版新增材料借给前版；保存的Result不被重写。</p>
    <ul>{view.advice.map(a=>{const p=old.advice.find(x=>x.usage===a.usage&&x.subject.resource_id===a.subject.resource_id&&x.subject.version===a.subject.version);return <li key={`${a.subject.resource_id}:${a.usage}`}>{resourceName(a.subject.resource_id)} · {usageFields[a.usage]}：{p?labels[p.state]:'前版未覆盖'} → {labels[a.state]}</li>;})}</ul>
   </details>}
  </>}
 </section>;
}
