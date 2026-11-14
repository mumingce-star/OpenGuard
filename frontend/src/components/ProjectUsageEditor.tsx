import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { presets, type Assessment, type Usage } from '../services/assessments';
import { sameUsage } from '../services/usageExperience';
import { beginUsageUpdate, submitUsageUpdate, continueUsageUpdate, readPendingUsageUpdate, projectUsageUrl, type UsageUpdateOperation, type UsageUpdateOutcome } from '../services/projectUsage';
import './ProjectUsageEditor.css';

const questions = [
 ['commercial','会用于商业活动吗？','例如收费产品、公司业务或客户项目；免费使用也可能属于商业场景。'],
 ['modified','会修改代码或二次开发吗？','例如增加功能、修改源码；只安装并使用现成组件通常不属于修改。'],
 ['distributed','会向他人发布或交付软件吗？','例如发布安装包、交付客户或把代码提供给他人；只在自己电脑运行可选“否”。'],
 ['network_service','会提供在线服务吗？','例如部署网站或接口，让用户通过网络访问；与分发软件是两件事。'],
 ['training','会用于模型训练吗？','例如使用该项目的代码、模型或数据开展训练、微调。'],
 ['redistributed_assets','会另行发布模型或数据等资源吗？','例如把模型权重、数据集或素材作为交付物的一部分。'],
 ['source_disclosure','会公开项目源代码吗？','例如公开代码仓库；“会发布软件”并不代表“会公开源码”。'],
] as const;
const choices = [['true','是',true],['false','否',false],['unknown','暂不确定',null]] as const;
export function ProjectUsageQuestions({value,onChange,disabled=false}:{value:Usage;onChange:(value:Usage)=>void;disabled?:boolean}) {
 return <fieldset className="project-usage-fields" disabled={disabled}><legend>项目整体怎么使用？不需要选择依赖</legend>
  <p>这七项只描述你的计划，不要求你判断许可证。不知道的保留“暂不确定”，不会自动当成“否”。</p>
  <div className="project-usage-question-list">{questions.map(([key,title,help],i)=><fieldset key={key} data-usage={key} className="project-usage-question"><legend><span>{String(i+1).padStart(2,'0')}</span>{title}</legend><p id={'usage-help-'+key}>{help}</p><div className="project-usage-choices">{choices.map(([code,label,answer])=><label key={code} className={(value[key]??null)===answer?'is-selected':''}><input type="radio" name={'project-usage-'+key} value={code} checked={(value[key]??null)===answer} aria-describedby={'usage-help-'+key} onChange={()=>onChange({...value,[key]:answer})}/>{label}</label>)}</div></fieldset>)}</div>
 </fieldset>;
}
export function ProjectUsageEditor({assessment:a,disabled=false,readOnly=false,onPendingChange}:{assessment:Assessment;disabled?:boolean;readOnly?:boolean;onPendingChange?:(pending:boolean)=>void}) {
 const scope=JSON.stringify([a.scan_id,a.id,a.version]);
 const authority=useRef({scope,scopeEpoch:0,writeEpoch:0,readOnly,mounted:false});
 // Only committed props change authority; an abandoned concurrent render cannot revive or strand a permit.
 useLayoutEffect(()=>{
  const state=authority.current;state.scope=scope;state.scopeEpoch++;state.writeEpoch++;
  state.readOnly=readOnly;state.mounted=false;
  return()=>{state.mounted=false;state.scopeEpoch++;state.writeEpoch++;};
 },[scope]);
 useLayoutEffect(()=>{
  const state=authority.current;
  if(state.readOnly!==readOnly){state.readOnly=readOnly;state.writeEpoch++;}
 },[readOnly]);
 const [draft,setDraft]=useState<Usage>(()=>({...a.usage,...Object.fromEntries(questions.map(([k])=>[k,a.usage[k]??null]))}));
 const [op,setOp]=useState<UsageUpdateOperation|null>(null),[outcome,setOutcome]=useState<UsageUpdateOutcome|null>(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[blocked,setBlocked]=useState(false);
 const alive=useRef(true),lock=useRef(false),completed=useRef(false),activeRun=useRef<symbol|null>(null);
 useEffect(()=>{
  const state=authority.current,epoch=state.scopeEpoch;alive.current=true;
  lock.current=false;activeRun.current=null;completed.current=false;
  setDraft({...a.usage,...Object.fromEntries(questions.map(([k])=>[k,a.usage[k]??null]))});
  setOp(null);setOutcome(null);setBusy(false);setError('');setBlocked(false);
  try{const pending=readPendingUsageUpdate(a);if(pending){setOp(pending);setDraft(pending.usage);setError('有一次保存尚待确认。先读取原请求状态，不会重复提交。');}}catch{setError('待确认请求无法安全读取。请保留当前页面并核对已保存评估，暂不发起新提交。');setBlocked(true);}
  state.mounted=true;
  return()=>{alive.current=false;if(state.scope===scope&&state.scopeEpoch===epoch){state.mounted=false;state.scopeEpoch++;state.writeEpoch++;}};
 },[scope]);
 useEffect(()=>{onPendingChange?.(!!op||busy||blocked);return()=>onPendingChange?.(false);},[op,busy,blocked,onPendingChange]);
 useEffect(()=>{const warn=(e:BeforeUnloadEvent)=>{if(op&&!completed.current&&outcome?.phase!=='complete'){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);},[op,outcome?.phase]);
 async function execute(resume:boolean,submitOriginal=false){
  if(readOnly||lock.current||blocked||(!resume&&disabled))return;
  const state=authority.current,scopeEpoch=state.scopeEpoch,writeEpoch=state.writeEpoch;
  const isCurrent=()=>alive.current&&state.mounted&&state.scope===scope&&state.scopeEpoch===scopeEpoch;
  const canWrite=()=>isCurrent()&&!state.readOnly&&state.writeEpoch===writeEpoch;
  if(!canWrite())return;
  const run=Symbol('project-usage-run');activeRun.current=run;lock.current=true;setBusy(true);setError('');
  try {
   const current=resume?op:beginUsageUpdate(a,draft,crypto.randomUUID());
   if(!current)throw Error('没有可读取的保存请求。');
   setOp(current);
   let value=await(resume&&!submitOriginal?continueUsageUpdate(current,canWrite):submitUsageUpdate(current,canWrite));
   if(!isCurrent())return;
   setOutcome(value);
   for(let n=0;value.phase==='pending'&&n<30&&canWrite();n++){
    await new Promise(resolve=>setTimeout(resolve,1000));if(!isCurrent())return;if(!canWrite())break;
    value=await continueUsageUpdate(current,canWrite);if(!isCurrent())return;setOutcome(value);
   }
   if(!isCurrent())return;
   setOutcome(value);
   if(value.phase==='complete'&&value.assessment&&value.result){
    // Retain a confirmed sent receipt; a revoked permit suppresses only stale automatic navigation.
    completed.current=true;setOp(null);onPendingChange?.(false);
    if(canWrite())window.location.assign(projectUsageUrl(value.assessment,value.result));
   }
  }catch(e){if(isCurrent())setError(e instanceof Error?e.message:'保存尚未确认，请读取原请求状态。');}
  finally{if(activeRun.current===run){activeRun.current=null;lock.current=false;if(isCurrent())setBusy(false);}}
 }
 return <section className="project-usage-editor" aria-label="补充项目用途">
  <header><span className="project-usage-eyebrow">可选补充 · 项目用途</span><h2>告诉我们，你准备怎样使用这个项目</h2><p>选择商业使用、二次开发、发布方式等实际情况。保存后更新对应用途的评估，已有报告和历史结果仍能查看。</p></header>
  <form onSubmit={e=>{e.preventDefault();void execute(false);}}>
   <ProjectUsageQuestions value={draft} onChange={setDraft} disabled={readOnly||disabled||blocked||busy||!!op}/>
   <details className="project-usage-scene"><summary>用途场景名称（可选）· {presets[draft.preset]}</summary><label>场景<select value={draft.preset} disabled={readOnly||disabled||blocked||busy||!!op} onChange={e=>setDraft({...draft,preset:e.target.value as Usage['preset']})}>{Object.entries(presets).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label><p>场景只用于描述，不会代替上面七项选择。</p></details>
   <div className="project-usage-submit"><button className="p2-primary" type="submit" disabled={readOnly||disabled||blocked||busy||!!op||sameUsage(a.usage,draft)}>{busy?'正在保存并读取评估…':'保存用途并更新评估'}</button><p>{sameUsage(a.usage,draft)?'与当前已保存用途一致；修改一项后即可保存。':'更改用途会形成对应评估版本；相同历史输入可能读取已有版本。'}<br/>当前显示的仍是第 {a.version} 版，直到保存成功后才会切换。</p></div>
  </form>
  {error&&<p className="p2-message p2-error" role="alert">{error}</p>}
  {outcome&&<p className={'p2-message '+(outcome.phase==='complete'?'p2-success':'p2-pending')} role="status">{outcome.message}</p>}
  {op&&!busy&&outcome?.phase!=='complete'&&<div className="p2-actions"><button type="button" disabled={readOnly} onClick={()=>void execute(true,outcome?.canSubmitOriginal===true)}>{outcome?.canSubmitOriginal?'保存原请求':'读取本次保存进度'}</button>{outcome?.assessment&&<a href={projectUsageUrl(outcome.assessment)}>打开已保存的第 {outcome.assessment.version} 版评估</a>}<span>复用原请求身份；不会自动重发评估提交。</span></div>}
 </section>;
}
