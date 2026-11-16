import { useEffect, useState } from 'react';
import type { Assessment } from '../services/assessments';
import { usageFields } from '../services/assessments';
import type { Scan } from '../types/domain';
import type { Result } from '../services/p2';
import { readAutomaticReview, readOverviewAutomaticReview, OverviewPreparationRequired, priorities, priorityLabels, type AutomaticReview, type Priority } from '../services/automaticReview';
import './AutomaticProjectAssessment.css';

export function AutomaticProjectAssessment({scan,assessment,result}:{scan:Scan;assessment:Assessment;result:Result}){
 const [review,setReview]=useState<AutomaticReview|null>(null),[error,setError]=useState('');
 const current=result.binding.scan_id===scan.id&&result.binding.scan_id===assessment.scan_id&&result.binding.assessment_id===assessment.id&&result.binding.assessment_version===assessment.version;
 useEffect(()=>{const c=new AbortController();setReview(null);setError('');if(current)void readAutomaticReview(assessment,result,c.signal).then(v=>{if(!c.signal.aborted)setReview(v);}).catch(e=>{if(!c.signal.aborted)setError(e instanceof Error?e.message:'自动初评读取未完成。');});return()=>c.abort();},[assessment.id,assessment.version,result.result_id,result.result_sha256,current]);
 if(!current)return <p className="auto-review-loading" role="status">正在读取所选评估的固定结果；不混用上一版建议。</p>;
 const exact=review?.result_id===result.result_id&&review.result_sha256===result.result_sha256?review:null;
 return <>
  <SavedResultAssessmentArticle scan={scan} assessment={assessment} result={result} sourceStatus={exact?.source_status??null}/>
  <details className="p2-detail"><summary>查看独立材料初评 · 非本版保存的条件建议</summary>
   {error?<div className="auto-review-error" role="alert"><strong>自动初评暂未读回</strong><p>{error}</p><p>上方已保存结果与版本仍然保留；未展示替代许可结论。</p></div>:exact?<AutomaticAssessmentArticle scan={scan} review={exact}/>:<p className="auto-review-loading" role="status">正在只读核对当前结果的材料来源…</p>}
  </details>
 </>;
}

export function SavedResultAssessmentArticle({scan,assessment,result,sourceStatus}:{scan:Scan;assessment:Assessment;result:Result;sourceStatus:AutomaticReview['source_status']|null}){
 const fields=Object.keys(usageFields) as (keyof typeof usageFields)[];
 const selected=fields.filter(key=>result.usage[key]===true),unknown=fields.filter(key=>result.usage[key]===null),notSelected=fields.filter(key=>result.usage[key]===false);
 const observed=result.resources.filter(r=>r.material_ids.length>0);
 const observedNames=observed.map(row=>{const resource=scan.resources.find(r=>r.id===row.subject.resource_id&&r.version===row.subject.version);return resource?`${resource.name}@${row.subject.version??'版本未定'}`:null;}).filter(Boolean);
 const fixedHttpServer=scan.id===result.binding.scan_id&&assessment.id===result.binding.assessment_id&&assessment.version===result.binding.assessment_version
  &&scan.revision==='0d3b7bb5b6e8a59fd450ae2dca65870009cfcd8b'&&result.binding.project_revision===scan.revision
  &&/^https:\/\/github\.com\/http-party\/http-server(?:\.git)?\/?$/.test(scan.input)
  &&result.resources.some(row=>row.subject.version==='14.1.2'&&scan.resources.some(resource=>resource.id===row.subject.resource_id&&resource.name==='http-server'&&resource.version===row.subject.version));
 const preparation:Record<keyof typeof usageFields,string>={
  commercial:'列出会销售、收费或用于客户业务的部分，逐个核对所含组件的许可条件；不要把一个组件的许可套给整个项目。',
  modified:'记录改了哪些文件，检查原有版权与许可声明是否保留；需要说明修改时，一并准备修改记录。',
  distributed:'列出实际发给他人的代码、安装包和依赖，把对应版本的 LICENSE／NOTICE 放入交付清单，并核对条款要求。',
  network_service:'区分只提供浏览器访问，还是同时向用户交付代码或文件；分别核对服务使用和文件交付涉及的条款。',
  training:(fixedHttpServer?'http-server 可为训练资料提供文件访问等配套服务。':'')+'说明训练时实际使用的是代码、模型还是数据，再分别核对许可；软件工具的 LICENSE 不能代替训练数据或模型授权。',
  redistributed_assets:(fixedHttpServer?'用 http-server 提供文件访问，不等于取得这些文件的再分发许可。':'')+'列出会再次提供给他人的模型、数据及其他资源，分别确认来源、准确版本和再分发条件。',
  source_disclosure:'发布前检查准备公开的源码、依赖和声明文件，核对每个组件的公开及声明要求；公开自己的代码不自动覆盖第三方资源。',
 };
 return <article className="auto-assessment auto-saved-story" aria-label="当前保存结果的项目整体说明" data-saved-result={result.result_id}>
  <header><span className="auto-eyebrow">{scan.project} · 使用准备清单</span><h2>按你的用途，使用前要做什么？</h2><p className="auto-saved-version">评估 v{assessment.version} · 保存结果 r{result.revision} · {scan.evidence.length} 条扫描证据{result.data_scope==='TEST_ONLY'?' · 隔离演示数据，当前用途为演示假设':''}</p></header>
  <div className="auto-guide-facts"><p><strong>{result.resources.length} 个资源</strong><span>本次扫描识别范围</span></p><p><strong>{result.material_ids.length?`已保存 ${result.material_ids.length} 份材料`:'本版尚未绑定材料'}</strong><span>{result.material_ids.length?`${observed.length} 个资源有材料引用，仍待核验`:'可先查看联网资料，再确认采用'}</span></p></div>
  <div className="auto-current-usage"><h3>本次准备怎么用</h3>{selected.length?<p>已选择 {selected.length} 项用途，对应准备事项列在下方。</p>:<p>尚未确认使用方式。先填写七项用途，下面才能给出对应的准备事项。</p>}{unknown.length>0&&<p className="auto-usage-unknown" aria-label="待确认用途">{unknown.length} 项用途待确认：{unknown.map(key=>usageFields[key]).join('、')}。</p>}</div>
  {selected.length>0&&<section className="auto-use-preparations" aria-label="已选择用途下的准备事项"><h3>使用前要做什么</h3><p className="auto-preparation-evidence">依据状态：{observed.length?`${observed.length} 个资源有材料引用，适用性待核验`:'本版尚无补充材料引用'}；具体条件见资源依据。</p><ul aria-label="本版已选择用途">{selected.map(key=><li key={key} data-usage-preparation={key}><strong>{usageFields[key]}</strong><p>{preparation[key]}</p></li>)}</ul></section>}
  <p className="auto-guide-conclusion">当前清单明确准备步骤；许可条件仍按对应组件和准确版本的保存依据确认。</p>
  <details className="auto-guide-details"><summary>查看版本、来源与判断边界</summary>
   {fixedHttpServer&&<p className="auto-project-purpose"><strong>http-server 是静态文件服务器：</strong>把文件夹里的网页、图片等文件提供给浏览器访问，可用于本地预览或静态文件服务。它本身不是模型或训练数据。</p>}
   <p>评估 v{assessment.version} · 保存结果 r{result.revision} · {scan.evidence.length} 条扫描证据{result.data_scope==='TEST_ONLY'?' · 隔离演示数据，用途为演示假设':''}。由本版已保存用途与材料引用整理，不是模型输出。</p>
   <p><strong>当前能明确的是准备步骤。</strong>上述清单不新增许可判定；商业、修改、交付等用途是否满足许可条件，仍按对应组件和准确版本的保存依据确认。</p>
   {notSelected.length>0&&<p>本次未选择：{notSelected.map(key=>usageFields[key]).join('、')}。这些值保留为“否”；不代表许可证禁止，也不会代替未知项。</p>}
   <p>{result.material_ids.length?<>材料引用关联 {observed.length} 个资源{observedNames.length?`（${observedNames.join('、')}）`:''}。材料已保存不等于使用已批准；材料真实性、适用范围和义务履行仍分别待核验。</>:<>当前版本没有补充材料引用。联网找到但尚未采用的原文，不计入本版已保存材料；其他用途版本的材料也不会自动沿用。</>}</p>
   {sourceStatus==='NOT_CONFIGURED'&&<p>独立 npm 发行材料初评来源尚未配置；联网取得的资料以下方“联网查找官方依据”的实际记录为准。两者不是同一项核验。</p>}
   <p>保留声明，是将组件原有的版权与许可文本按条款随相应文件保留。扫描完成表示处理流程结束，不代表全项目已获许可；修改用途或采用材料后生成新版本，旧结果与旧报告保留。</p>
  </details>
 </article>;
}
export function AutomaticAssessmentArticle({scan,review}:{scan:Scan;review:AutomaticReview}){
 const s=review.summary,conditional=s.state_counts.CONDITIONAL,unknown=s.state_counts.UNAVAILABLE,outside=s.state_counts.OUTSIDE_NPM,nonstandard=s.state_counts.NONSTANDARD;
 const uses=Object.entries(review.usage).filter(([,v])=>v===true).map(([k])=>usageFields[k as keyof typeof usageFields]);
 const licenseNames=[...new Set(review.resources.filter(r=>r.state==='CONDITIONAL').map(r=>r.license_expression))].join(' / ');
 const maintenanceNames=review.resources.filter(r=>r.maintenance_deprecated).map(r=>`${r.name} ${r.subject.version??''}`).join('、');
 const conditionalLicenses=new Set(review.resources.filter(r=>r.state==='CONDITIONAL').map(r=>r.license_expression));
 return <article className="auto-assessment" aria-label="项目整体自动初评">
  <header><span className="auto-eyebrow">{scan.project} · 综合使用建议</span><h2>{conditional?'保留开源声明，优先处理维护与特殊条款':'按资源逐项核对，先明确适用条件'}</h2><p className="auto-provenance"><strong>确定性材料初评</strong><span>依据已配置来源及固定规则整理；不是模型输出</span>{review.data_scope==='TEST_ONLY'?' · 隔离演示数据':''}</p></header>
  <aside className="auto-reading-guide" aria-label="项目评估阅读指南"><strong>这页帮你回答：项目怎么用，交付前要做什么？</strong><p>先读下面的整体建议，再看需要优先处理的组件。你不需要先懂许可证，也不必先填表；补充信息只用于让建议更贴近你的项目。</p><details><summary>第一次接触开源？展开看 3 个常用说法</summary><dl><div><dt>开源许可证</dt><dd>作者允许你怎样使用代码、使用时需要遵守哪些条件的说明。</dd></div><div><dt>保留声明</dt><dd>把组件原有的作者版权和许可文本随软件一并保留，不是要求你额外购买许可证。</dd></div><div><dt>单独审查</dt><dd>需要针对这个组件再核对；不表示它已经违规，也不表示它不能用。</dd></div></dl></details></aside>
  <div className="auto-answer">
   <p>{uses.length?`结合本次“${uses.join('、')}”的使用目标，`:'根据当前已识别的项目依赖，'}我的建议是<strong>按精确版本管理开源组件，将保留声明作为交付的常规步骤</strong>。本次共扫描到 {s.total_resources} 个资源，并自动核对了 {s.source_packages} 个官方 npm 发行包。{conditional>0?<>其中 <strong>{conditional} 个资源</strong>的完整 {licenseNames} 文本已与发行版本对应，可以在履行列明条款条件的前提下安排使用与交付。</>:<>当前完整条款尚未形成可自动支持的使用范围，以下仍可明确哪些材料和对象需要单独核对。</>}</p>
   {conditional>0&&<p>具体来说，对这部分资源应<strong>保留版权声明与许可文本</strong>。{conditionalLicenses.has('MIT')&&<>MIT 要求在软件副本或实质部分中保留这些声明；</>}{conditionalLicenses.has('ISC')&&<>ISC 要求在所有副本中保留版权和许可声明；</>}建议将对应版本的声明集中整理到随产品交付的第三方开源说明中，并让依赖版本与说明同步更新。这样能把抽象的许可条款转化为明确的交付动作。</p>}
   <p>{s.maintenance_count>0?<>优先关注维护状态：<strong>{maintenanceNames}</strong>这 {s.maintenance_count} 个版本已被官方 npm 标记为 deprecated（弃用提示）。建议检查它们在项目中的实际用途，优先评估升级或替代方案，并验证兼容性。该标记反映维护信息，<strong>不是已发现漏洞</strong>；许可条件与维护问题应分别处理。</>:review.source_status==='NOT_CONFIGURED'?<>当前官方 npm 来源未配置，维护状态尚未核对；不能将没有观察结果理解为组件没有弃用问题。</>:<>本轮已取得的 npm 元数据中没有观察到 deprecated 标记；这不代表已完成漏洞扫描或持续维护审查。</>}</p>
   <p>还需要单独审查 <strong>{s.priority_counts.manual} 个资源</strong>：{nonstandard>0&&<>其中 {nonstandard} 个已取得发行材料，但条款、附加声明或对象关联尚不能按标准 MIT/ISC 自动解释；</>}{unknown>0&&<>{unknown} 个精确版本的发行材料未取得；</>}{outside>0&&<>{outside} 个不属于本轮 npm 来源范围。</>}这些对象保留原有缺口，不套用其他依赖的 LICENSE。你可以直接阅读本次评估；如果希望结论更贴近实际交付，再按需补充项目情况或已有材料。</p>
  </div>
  <p className="auto-source-note">根据本次自动材料初评整理，已核对 {s.source_packages} 个官方精确发行包、{s.license_materials} 份许可／声明文本。以上不等于整个项目已经获得授权；实际安装字节及交付义务未逐项核验，正式评估保持原版本。</p>
  <ReviewResourceDetails review={review}/>
 </article>;
}
export function ReviewResourceDetails({review}:{review:AutomaticReview}){
 const [priority,setPriority]=useState<Priority|'all'>('all');
 return <details className="auto-resource-details"><summary>查看本次初评的资源、依据与边界</summary><div className="auto-filter" aria-label="按处理优先级筛选">{(['all',...priorities] as const).map(p=><button key={p} aria-pressed={priority===p} onClick={()=>setPriority(p)}>{p==='all'?'全部资源':priorityLabels[p]}</button>)}</div><div className="auto-resource-rows">{review.resources.filter(r=>priority==='all'||r.priority===priority).map(r=><section key={r.subject.resource_id}><header><strong>{r.name} <small>@ {r.subject.version??'版本未定'}</small></strong><span className={'auto-priority '+r.priority}>{priorityLabels[r.priority]}</span></header><p>{r.reasons.join(' ')}</p>{r.conditions.length>0&&<ul>{r.conditions.map(c=><li key={c}>{c}</li>)}</ul>}{r.source_refs.length>0&&<div className="auto-source-links">{r.source_refs.map(s=><a key={s.kind} href={s.url} target="_blank" rel="noreferrer">{s.kind==='metadata'?'官方版本元数据':'官方发行包'} ↗</a>)}</div>}<details><summary>精确对象与来源 Hash</summary><pre>{JSON.stringify({subject:r.subject,evidence_ids:r.evidence_ids,artifact_binding:r.artifact_binding,source_refs:r.source_refs,members:r.members,applicability_review:r.applicability_review},null,2)}</pre></details></section>)}</div><ul className="auto-limitations">{review.limitations.map(x=><li key={x}>{x}</li>)}</ul></details>;
}
export function AutomaticOverview({scan,go}:{scan:Scan;go:(page:string,query?:string)=>void}){
 const [review,setReview]=useState<AutomaticReview|null>(null),[error,setError]=useState(''),[query,setQuery]=useState('');
 const [preparation,setPreparation]=useState<OverviewPreparationRequired|null>(null);
 const sourceQuery=window.location.search;
 useEffect(()=>{const c=new AbortController();setReview(null);setError('');setPreparation(null);void readOverviewAutomaticReview(scan.id,new URLSearchParams(sourceQuery),c.signal).then(({assessment,result,review:v})=>{if(!c.signal.aborted){setReview(v);setQuery(new URLSearchParams({assessment_id:assessment.id,p2_result:result.result_id}).toString());}}).catch(e=>{if(!c.signal.aborted){if(e instanceof OverviewPreparationRequired)setPreparation(e);else setError(e instanceof Error?e.message:'自动初评读取未完成。');}});return()=>c.abort();},[scan.id,sourceQuery]);
 if(preparation)return <section className="auto-overview" role="status"><h2>{preparation.code==='OVERVIEW_RESULT_NOT_READY'?'下一步：查看项目用途评估':'项目评估准备中'}</h2><p>{preparation.message}</p><button onClick={()=>go('assessment')}>进入项目评估 →</button></section>;
 if(error)return <section className="auto-overview auto-review-error" role="alert"><h2>自动初评暂未读回</h2><p>{error}</p><button onClick={()=>go('assessment')}>进入项目评估 →</button></section>;
 if(!review||review.binding.scan_id!==scan.id)return <section className="auto-overview"><p role="status">正在读取当前扫描的官方材料初评…</p></section>;
 return <AutomaticOverviewContent review={review} go={go} query={query}/>;
}

const overviewGuidance:Record<Priority,{meaning:string;why:string;action:string}>={
 routine:{meaning:'按说明保留必要声明',why:'完整条款支持有条件使用，未观察到官方弃用标记。',action:'随交付物保留版权和许可文本，并按组件列出的条件处理。'},
 attention:{meaning:'留意组件是否还在维护',why:'已有条款支持，但官方已将这个版本标记为弃用。',action:'检查当前用途是否受影响，评估升级或替代；弃用不等于漏洞。'},
 manual:{meaning:'需要逐个查看具体情况',why:'条款超出当前自动规则，或来源、版本、适用范围仍需核对。',action:'先查看每个组件的具体原因；必要时请项目维护者协助，不代表已经违规。'},
};

export function AutomaticOverviewContent({review,go,query}:{review:AutomaticReview;go:(page:string,query?:string)=>void;query:string}){
 const [selected,setSelected]=useState<Priority>('manual');
 const [showAll,setShowAll]=useState(false);
 const rows=review.resources.filter(r=>r.priority===selected);
 const visibleRows=showAll?rows:rows.slice(0,5);
 const deprecatedAttention=review.resources.filter(r=>r.maintenance_deprecated&&r.priority==='attention').length;
 const deprecatedManual=review.resources.filter(r=>r.maintenance_deprecated&&r.priority==='manual').length;
 return <section className="auto-overview" aria-label="自动材料初评概览">
  <header><div><span className="auto-eyebrow">自动材料初评 · 按处理事项分类</span><h2>项目里哪些地方需要留意？</h2><p>点击一类，查看对应组件、归类原因和下一步。三类互不重复，不是风险高低排名。</p></div><button onClick={()=>go('assessment',query)}>进入项目评估 →</button></header>
  <div className="auto-priority-grid">{priorities.map(p=><button key={p} data-priority={p} className={'auto-priority-card '+p+(selected===p?' is-selected':'')} aria-pressed={selected===p} aria-controls="overview-category-detail" onClick={()=>{setSelected(p);setShowAll(false);}}>
   <span className="auto-category-top"><span>{priorityLabels[p]}</span><strong>{review.summary.priority_counts[p]}<small> 个</small></strong></span>
   <span className="auto-category-meaning">{overviewGuidance[p].meaning}</span>
   <span className="auto-category-explanation"><b>为什么</b>{overviewGuidance[p].why}</span>
   <span className="auto-category-explanation"><b>怎么做</b>{overviewGuidance[p].action}</span>
   <span className="auto-category-open">{selected===p?'正在查看此类':'查看这类组件'} <span aria-hidden="true">↓</span></span>
  </button>)}</div>
  <div className="auto-category-detail" id="overview-category-detail">
   <header><div><h3>{priorityLabels[selected]} <span>{rows.length} 个组件</span></h3><p>{overviewGuidance[selected].action}</p></div><span className="auto-category-count-note">{showAll||rows.length<=5?'显示本类全部组件':`先显示前 5 个，共 ${rows.length} 个`}</span></header>
   {rows.length?<ul className="auto-overview-resource-list" aria-label={priorityLabels[selected]+'组件名单'}>{visibleRows.map(r=><li data-resource-id={r.subject.resource_id} key={r.subject.resource_id}><details className="auto-overview-resource">
    <summary><span className="auto-overview-resource-name"><strong>{r.name}</strong><span>{r.subject.version??'版本未确定'}</span>{r.maintenance_deprecated&&<small>官方弃用标记</small>}</span><span className="auto-resource-expand-label">归类依据与建议</span></summary>
    <div className="auto-overview-resource-body">
    <div><span className="auto-resource-field-label">归类依据</span><p>{r.reasons.join(' ')}</p></div>
    <div><span className="auto-resource-field-label">建议操作</span><p>{selected==='manual'?'查看上述原因与原始材料，逐项核对条款或来源；必要时请维护者协助。':r.conditions.join(' ')}{selected==='attention'?' 同时评估升级或替代组件。':''}</p></div>
    </div>
   </details></li>)}</ul>:<p className="auto-overview-empty">本次初评没有归入此类的组件。</p>}
   {rows.length>5&&<div className="auto-overview-list-action"><button type="button" aria-expanded={showAll} onClick={()=>setShowAll(value=>!value)}>{showAll?'收起为前 5 个组件':`显示全部 ${rows.length} 个组件`}</button></div>}
  </div>
  {review.summary.maintenance_count>0&&<p className="auto-maintenance-explanation">为什么“维护关注”不等于全部弃用组件？共 {review.summary.maintenance_count} 个组件被官方标记为弃用：{deprecatedAttention} 个归入“维护关注”，{deprecatedManual} 个归入“单独审查”。后者的条款或来源尚不满足自动支持条件，因此优先核对这些问题。弃用标记不是漏洞数量。</p>}
  <details className="auto-overview-license-details"><summary>了解许可证构成与材料来源</summary><p>许可证是组件的使用规则。MIT、ISC、Apache 等名称表示规则类别，具体条件仍以对应版本的完整文本为准。</p><dl className="auto-license-distribution">{review.summary.license_groups.map(g=><div key={g.license}><dt>{g.license==='UNOBSERVED'?'未观察到许可声明':g.license}</dt><dd>{g.count} 个组件</dd></div>)}</dl><p>已核对 {review.summary.source_packages} 个官方精确发行包、{review.summary.license_materials} 份许可／声明文本。以上是材料初评，许可适用性尚未完成人工签认。</p></details>
 </section>;
}
