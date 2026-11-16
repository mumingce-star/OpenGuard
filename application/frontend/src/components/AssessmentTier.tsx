import { useState, type ReactNode } from 'react';
import type { TierView, TierRoute } from '../services/assessmentTier';
import './AssessmentTier.css';
const labels={L1:'基础智能评估',L2:'证据增强评估',L3:'证据闭环评估'};
const states:Record<string,string>={COMPLETE:'已完成',AVAILABLE:'可继续',IN_PROGRESS:'增强中',BLOCKED:'仍有证据缺口',NOT_APPLICABLE:'暂无人工补充项'};
export function AssessmentTier({value,selected,onSelect}:{value:TierView;selected?:'L1'|'L2'|'L3';onSelect?:(stage:'L1'|'L2'|'L3')=>void}){
 return <section className="assessment-tier tier-compact" aria-label="项目评估等级">
  {value.data_scope==='TEST_ONLY'&&<p className="tier-test" role="note">TEST_ONLY · 历史测试答案的只读演示，不是 Owner 真实业务声明</p>}
  <nav className="tier-stage-nav" aria-label="查看各级结果">{(['L1','L2','L3'] as const).map(level=><button type="button" key={level} aria-pressed={(selected??value.current_level)===level} onClick={()=>onSelect?.(level)}><strong>{level} {labels[level]}</strong><small>{states[value.level_states[level]]??'尚未就绪'}</small></button>)}</nav>
 </section>;
}
function RouteList({rows}:{rows:TierRoute[]}){return <ul>{rows.map(r=><li key={r.item_id}><strong>{r.name}</strong><span>{r.why}</span></li>)}</ul>;}
export function TierUpgradePlans({value,children}:{value:TierView;children?:ReactNode}){
 const [open,setOpen]=useState(false);const p=value.upgrade_plan.upgrade_to_l2,l3=value.upgrade_plan.upgrade_to_l3;
 const planned=p.user_fact_questions.filter(q=>!q.input_available);
 return <section className="tier-plans" aria-label="证据升级路线">
  <button type="button" className="tier-upgrade" aria-expanded={open} aria-controls="tier-l2-plan" onClick={()=>setOpen(!open)}>{open?'收起 L2 升级计划':value.current_level==='L2'?'继续完善 L2 · 查看补充计划':'提升到L2 · 证据增强评估'}</button>
  <p>先查看计划，不会直接升级。等级仅随已采用的有效证据变化。</p>
  {open&&<section id="tier-l2-plan" tabIndex={-1} className="tier-l2-plan"><h3>L2 · 少量人工补充，更充分的依据</h3>
   <p>现有两问保留原对象；另外 {planned.length} 组现实范围问题尚待接入回答。不要重复填写已保存用途。</p>
   <h4>你来确认 · 现实业务事实</h4>{children}
   {planned.map(q=><article className="tier-planned" key={q.question_id}><strong>{q.text}</strong><p>覆盖 {q.item_ids.length} 项事项 / {q.resource_ids.length} 个资源。{q.why_user_only}</p><small>已列入升级计划，当前尚未接入回答；现有两问的答案不会套用到这里。</small></article>)}
   <details><summary>你可补充 · 本地／私有材料（{p.local_material_requirements.length} 项）</summary><p>需要本地／私有材料 · 当前尚未接入自动读取。保留项目自身的精确版本与对应许可材料；不要求你到公网逐项搜索。</p><RouteList rows={p.local_material_requirements}/></details>
   <section className="tier-system"><h4>系统负责 · 自动补证与解析</h4><p>{p.automatic_public_actions.length} 项可由系统尝试官方补证；当前网络补证通道未完成验证，不转交给你手工搜索。</p><p>{p.parser_actions.length} 项需要本地解析或重新扫描能力；本页不会重新执行。</p></section>
   <p className="tier-boundary">上述路径可能重叠：共涉及 {p.unique_route_items} 项依据不足、{p.unique_route_resources} 个资源，不能把各路径数量相加。可尝试改善，不保证全部闭合。</p>
  </section>}
  <details className="tier-l3"><summary>距离 L3 证据闭环评估还缺什么 <span>{l3.open_requirement_count} 项证据要求</span></summary>
   <p>涉及 {l3.unique_resource_count} 个不同资源。一个事项可能关联多项证据要求；这不是用户待办数，也不是风险率。</p>
   <div className="tier-categories">{Object.entries(l3.category_counts).filter(([,n])=>n>0).map(([category,count])=>{const rows=l3.open_critical_requirements.filter(r=>r.category===category);return <section key={category}><h4>{rows[0].label}<span>{count} 项</span></h4><p>{category==='OBLIGATION_FULFILLMENT_EVIDENCE'?'需要实际履行材料，口头声明不能独立闭合。':category==='CONFLICT'?'尚未形成完整的跨来源冲突核验记录。':category==='SYSTEM_CAPABILITY'||category==='COVERAGE'?'由系统继续处理覆盖与能力缺口，不要求你重复回答。':'还需精确关联的依据，现有局部成果仍保留。'}</p><details><summary>查看关联对象</summary><ul>{rows.map(r=><li key={r.requirement_id}>{r.name||'项目整体'}{r.status==='USER_ASSERTED_ONLY'?' · 已有声明，仍需核验材料':''}</li>)}</ul></details></section>;})}</div>
   <p>关键证据闭环后才可形成 L3；不能通过按钮强制升级。Formal Assessment 仍是独立权威对象。</p>
  </details>
 </section>;
}
