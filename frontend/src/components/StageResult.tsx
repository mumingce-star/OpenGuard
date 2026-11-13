import type {Assessment, Dimension, Usage} from '../services/assessments';
import type {TierView} from '../services/assessmentTier';
export type Stage='L1'|'L2'|'L3';
const topics=[
 {field:'commercial',label:'商业使用',dimension:['commercial'],action:'先确认相关对象的商业使用条款，再决定商业使用。'},
 {field:'modified',label:'二次开发',dimension:['modification'],action:'先确认相关代码的修改与再发布条款，再决定二次开发。'},
 {field:'distributed',label:'发布／交付',dimension:['closed_distribution','redistribution'],action:'发布或交付前，先确认实际包含的资源及对应再分发条款。'},
 {field:'network_service',label:'在线服务',dimension:['network_service'],action:'提供在线服务前，先确认相关服务与资源的适用条款。'},
 {field:'training',label:'模型训练',dimension:['ai_assets'],action:'训练前，先确认所用模型和数据的训练许可与适用范围。'},
 {field:'redistributed_assets',label:'AI资产再分发',dimension:['ai_assets'],action:'对外交付前，先确认相关AI资产的再分发条款。'},
] as const;
type Resource=NonNullable<Assessment['resource_evaluations']>[number]&{supported_permission?:boolean;license_verified?:boolean;conditions?:string[]};
function exactNames(a:Assessment,ids:string[]){return ids.map(id=>{const rows=a.resource_evaluations?.filter(r=>r.resource_id===id)??[];return rows.length===1?rows[0].name:'关联对象待核对';}).join('、');}
function selected(u:Usage,t:typeof topics[number]){if(u[t.field]===false)return false;return u[t.field]===true||(t.field==='distributed'&&(u.preset==='open_source'||u.preset==='closed_source'||u.source_disclosure===true))||(t.field==='network_service'&&u.preset==='service');}
// Reorganizes existing saved truth only. It does not derive a permission from AI counts or roles.
export function StageResult({assessment:a,tier,stage,hasResult,assisted,supported}:{assessment:Assessment;tier:TierView|null;stage:Stage;hasResult:boolean;assisted?:number;supported?:number}) {
 const exactTier=!!tier&&tier.scan_id===a.scan_id&&tier.assessment_id===a.id&&tier.assessment_version===a.version&&tier.facts_hash===a.facts_hash&&tier.usage_hash===(a as Assessment&{usage_hash:string}).usage_hash&&tier.rule_version===a.rule_version;
 const status=exactTier?tier.level_states[stage]:undefined;
 const ready=hasResult&&(stage==='L1'||exactTier)&&(stage!=='L3'||status==='COMPLETE');
 const active=topics.filter(t=>a.usage&&selected(a.usage,t));
 const conditional=(ds:Dimension[])=>ds.filter(d=>d.status==='conditional'&&d.conditions.length&&d.resource_ids.length&&d.resource_ids.every(id=>a.resource_evaluations?.filter(r=>r.resource_id===id).length===1));
 const obligations=a.obligations??[];
 const representedNotice=(o:typeof obligations[number])=>active.some(t=>t.field==='distributed')&&
  o.action==='retain_license_notice'&&o.rule_id==='LIC-MIT-NOTICE'&&o.rule_version==='1.0.0'&&
  o.trigger==='Verified MIT-licensed material is included in a distribution'&&
  o.requirement==='Preserve the copyright and permission notice with the distributed material.'&&
  o.fulfillment==='pending'&&o.resource_ids?.length===1&&o.evidence_ids?.length>0&&
  a.resource_evaluations?.filter(r=>r.resource_id===o.resource_ids[0]).length===1&&
  a.resource_evaluations.some(r=>r.resource_id===o.resource_ids[0]&&(r as Resource).supported_permission===true&&(r as Resource).license_verified===true&&r.evidence_ids?.length&&(r as Resource).conditions?.includes('保留版权声明及许可声明；义务是否实际履行仍待核实')&&o.evidence_ids.every(id=>r.evidence_ids.includes(id)))&&
  a.dimensions.some(d=>['redistribution','closed_distribution'].includes(d.id)&&d.status==='unknown'&&d.resource_ids.includes(o.resource_ids[0]));
 const remainingObligations=obligations.filter(o=>!representedNotice(o));
 return <section className="stage-result stage-advice" aria-label={stage+'本级评估结果'}>
  <header><h2>{stage==='L1'?'L1 · AI初步使用建议':stage==='L2'?'L2 · 证据增强使用建议':'L3 · 证据闭环结果'}</h2><span>{stage==='L2'&&status==='IN_PROGRESS'?'阶段性结果 · 增强中':status==='COMPLETE'&&ready?'本级结果已形成':status==='BLOCKED'?'尚未达到':status==='AVAILABLE'?'尚未开始':ready?'已有保存结果':'结果读取中／未留存'}</span></header>
  {!ready&&<p className="stage-state">{stage==='L3'?'L3尚未形成结果':stage==='L2'?'本级尚无可核对的已保存增强结果':'基础研判尚未完整读取；以下仅保留原评估中的判断和下一步。'}</p>}
  {stage==='L3'&&ready&&<p>当前固定范围的关键证据已闭环；以下风险、条件与义务仍适用，不代表所有用途均可使用。</p>}
  {stage==='L2'&&ready&&tier&&<p>{tier.data_scope==='TEST_ONLY'?'TEST_ONLY 测试声明':'已核验来源的补充声明'}已被采用，涉及 {tier.evidence_summary.accepted_human_items} 项事项；原 L1 与正式评估未改变。</p>}
  <div className="usage-advice-list">{active.map(t=>{
   const ds=a.dimensions.filter(d=>t.dimension.some(id=>id===d.id));const restrictions=ds.filter(d=>d.status==='restricted');const positive=t.field==='training'||t.field==='redistributed_assets'?[]:conditional(ds);
   const ids=new Set(ds.flatMap(d=>d.resource_ids));
   const local=(t.field==='training'||t.field==='redistributed_assets'?[]:a.resource_evaluations??[]).filter(r=>ids.has(r.resource_id)&&(r as Resource).supported_permission===true&&(r as Resource).license_verified===true&&r.evidence_ids?.length&&(r as Resource).conditions?.length&&a.resource_evaluations?.filter(x=>x.resource_id===r.resource_id).length===1) as Resource[];
   return <article className="usage-advice-row" key={t.field}><h3>{t.label}</h3><div>
    {restrictions.length?restrictions.map(d=><p key={d.id} className="usage-restriction">当前用途存在限制：{d.restrictions.join('；')||'已记录限制，须核对原范围'}。适用对象：{exactNames(a,d.resource_ids)}</p>):positive.length?positive.map(d=><p key={d.id}>既有判断：{exactNames(a,d.resource_ids)}有条件可用于{t.label}；{d.conditions.join('；')}。仅适用于列明对象。</p>):ds.length&&ds.every(d=>d.status==='not_applicable')?<p>当前保存维度标为不适用；不能据此推断允许或禁止。</p>:<p>{t.action}</p>}
    {!positive.length&&!restrictions.length&&local.map(r=><p className="usage-local-support" key={r.resource_id}>既有局部判断：{r.name}有条件可用于{t.label}；{r.conditions!.join('；')}。仅限该对象，含既有人审依据。</p>)}
   </div></article>;
  })}</div>
  {!active.length&&<p>{a.usage?'尚未确定相关用途；先查看保存用途与具体材料缺口。':'该历史评估未记录用途；保留原结果，不补造用途。'}</p>}
  {!!remainingObligations.length&&<div className="stage-obligation-summary"><strong>必要义务</strong>{remainingObligations.map(o=><p key={o.id}>{o.action==='retain_license_notice'?'交付包含对应材料时，须保留版权与许可声明。':'须履行已记录的义务。'}关联对象：{exactNames(a,o.resource_ids??[])} · {o.fulfillment==='pending'?'履行依据仍待确认':'以已保存的履行记录为准'}</p>)}</div>}
  <p className="stage-boundary">基于当前已取得材料的初评，部分证据尚未核验；发布或交付前须确认相关条件，不代表授权确认。</p>
  <details className="stage-other-uses"><summary>其他用途与条件</summary>{topics.filter(t=>!a.usage||!selected(a.usage,t)).map(t=><p key={t.field}>{a.usage?.[t.field]===false?'本次未选择：':'尚未确定：'}{t.label}</p>)}{a.dimensions.filter(d=>d.status!=='not_applicable').map(d=><section key={d.id}><strong>{d.title}</strong>{d.conditions.map((c,i)=><p key={'c'+i}>{c}</p>)}{d.restrictions.map((c,i)=><p key={'r'+i}>{c}</p>)}<p>适用对象：{exactNames(a,d.resource_ids)}</p></section>)}{obligations.map(o=><section key={o.id}><strong>触发条件与义务原文</strong><p>{o.trigger}</p><p>{o.requirement}</p></section>)}</details>
  {stage==='L3'&&!ready&&<p>仍有 {(exactTier?tier.upgrade_plan.upgrade_to_l3.open_requirement_count:undefined)??'未读到的'} 项关键证据要求；不是同等数量的用户待办。</p>}
 </section>;
}
