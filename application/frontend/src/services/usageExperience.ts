import { presets, usageFields, type Usage } from './assessments';
import type { Brief, BriefObligation, Gap, ResolutionJob } from './resolution';
import type { Assessment } from './assessments';

export function initialUsage(items:Pick<Assessment,'id'|'usage'>[],requested:string|null,scanUsage:Usage|null) {
 const fixed=requested?items.find(item=>item.id===requested):items[0];
 return fixed?.usage ?? (items.length===0&&!requested?scanUsage:null);
}

// Display only: preserve unknown facts and all authority boundaries.
export function sameUsage(fixed: Usage, draft: Usage) {
 return fixed.preset === draft.preset && (Object.keys(usageFields) as (keyof typeof usageFields)[])
  .every(field => [fixed[field],draft[field]].every(value=>value==null||typeof value==='boolean') && (fixed[field] ?? null) === (draft[field] ?? null));
}
// The optional scene name is not a substitute for the seven saved business facts.
// This label never changes the usage payload or computes an authority hash.
export function usageTitle(usage: Usage) {
 if(usage.preset!=='unknown')return presets[usage.preset];
 const confirmed=(Object.keys(usageFields) as (keyof typeof usageFields)[]).filter(field=>typeof usage[field]==='boolean').length;
 return confirmed===7?'自定义用途 · 七项已确认':confirmed?`自定义用途 · 已确认 ${confirmed}/7 项`:presets.unknown;
}
export function usageDescription(usage: Usage) {
 const facts = (Object.keys(usageFields) as (keyof typeof usageFields)[]).filter(field => usage[field] != null)
  .map(field => `${usageFields[field]}：${usage[field] === true ? '是' : usage[field] === false ? '否' : '记录待核对'}`);
 return usageTitle(usage) + (facts.length ? ' · ' + facts.join('；') : ' · 使用细节尚未确认');
}
export function conclusionText(brief: Brief) {
 return {unknown:'目前还不能确认项目适合这个用途',partial:'部分组件已有判断，整个项目仍有关键事项待确认',
  conditional:'需要满足列出的条件，才能按当前用途推进',restricted:'当前用途遇到限制，需要调整方案'}[brief.permission_state];
}
export function localResultText(brief: Brief) {
 return `有局部许可支持的资源记录：${brief.local_results.filter(r => r.supported_permission===true).length} / ${brief.local_results.length}。分母是本次评估列出的资源记录数量，不是合规通过比例；其他组件及项目整体仍需核对。`;
}
export function permissionBoundary(brief: Brief) {
 const supported=brief.local_results.filter(r=>r.supported_permission===true).length;
 return supported?`其中 ${supported} 条资源记录已有当前规则下的局部许可支持，仍须满足对应条件；这不代表项目整体已获确认。`:'当前仍有许可或适用范围待核对。';
}
export function obligationResources(obligation:BriefObligation,brief:Brief) {
 if(!Array.isArray(obligation.resource_ids)||!obligation.resource_ids.length)return '关联对象尚未定位';
 return '关联对象：'+[...new Set(obligation.resource_ids)].map(id=>{
  const matches=brief.local_results.filter(r=>typeof id==='string'&&r.resource_id===id);
  if(matches.length!==1)return '关联对象尚未定位';
  const row=matches[0];
  return row.name+(typeof row.version==='string'&&row.version.trim()?' '+row.version:'（版本未确认）');
 }).join('；');
}
export function materialProgress(brief: Brief) {
 const versions=brief.resolution_observations.filter(o=>o.atomic_facts.version_located).length;
 const documents=brief.resolution_observations.filter(o=>o.atomic_facts.document_acquired).length;
 return {versions,documents,remaining:brief.gaps.length,
  summary:brief.resolution_observations.length?`已定位 ${versions} 份组件版本材料，取得 ${documents} 份许可正文。`:'这份结果未附加本地查找材料；不代表原评估没有证据。',
  formal:'正式评估未改变；找到材料不等于已核验授权。',
  next:brief.gaps.some(g=>g.owner==='reviewer')?'继续核对材料与项目的适用关系，交由审核确认。':brief.gaps.some(g=>g.owner==='user')?'确认实际用途和交付范围，再生成新评估。':'核对已有材料；必要时交由审核确认。'};
}
const gapLabels:Record<string,[string,string]>={
 USAGE_MISSING:['用途细节待确认','确认用途和实际使用方式；不知道的选项可保留未知。'],
 SCOPE_UNRESOLVED:['资源适用范围待核验','核对资源在项目中的归属与适用范围；已声明的用途不会自动完成这项核验。'],
 VERSION_UNRESOLVED:['组件版本尚未定位','先查找保留的本地材料；版本材料仍需核对。'],
 LICENSE_TEXT_MISSING:['未找到许可正文','补充对应版本的许可文件，再确认其适用范围。'],
 LOCAL_SOURCE_NOT_RETAINED:['扫描未保留可查找的材料','如需查找，请在新的扫描中明确保留本地材料。'],
 IDENTITY_MISMATCH:['材料身份与组件不一致','核对名称、版本和来源；此材料不能闭合缺口。'],
 EVIDENCE_CONFLICT:['材料之间存在冲突线索','展开原文，交由审核确认适用关系。'],
 PROVIDER_NOT_SUPPORTED:['材料来源尚不支持自动查找','查看已有记录，补充可核对的版本材料或交由审核。'],
 NETWORK_DISABLED:['本轮未进行网络查找','只检查保留的本地材料；缺失材料仍需补充。'],
 MODEL_UNAVAILABLE:['模型辅助未能完成','本地查找结果保留，可直接核对原文。'],
 BUDGET_EXHAUSTED:['查找达到处理上限','查看已找到的材料，分批核对剩余范围。'],
 MATERIAL_ENCODING_UNSUPPORTED:['材料编码无法读取','提供可读的许可正文，保留来源和版本信息。'],
 HUMAN_REVIEW_REQUIRED:['许可适用关系需要审核','找到正文后，仍需确认它是否适用于当前组件和用途。'],
 RULE_NOT_COVERED:['当前检查能力未覆盖此问题','交由审核确认；不能据此宣称许可通过。'],
 SCAN_COVERAGE_GAP:['扫描覆盖仍不完整','部分内容尚未被识别或读取，仍需人工核对其使用范围。'],
};
// Only the displayed Brief supplies context. No latest-result reads, title
// inference, or transfer of another resource's material to this gap.
function gapMaterials(gap:Gap,brief?:Brief) {
 if(!brief||!Array.isArray(gap.resource_ids)||!gap.resource_ids.length||!gap.resource_ids.every(id=>typeof id==='string'&&id.length))return null;
 return [...new Set(gap.resource_ids)].map(id=>{
  const observations=brief.resolution_observations.filter(o=>o.resource_id===id);
  return {id,version:observations.some(o=>o.atomic_facts.version_located===true),
   document:observations.some(o=>o.atomic_facts.document_acquired===true),
   matched:observations.some(o=>o.atomic_facts.document_acquired===true&&o.atomic_facts.content_matched===true)};
 });
}
function reviewKind(gap:Gap) {
 if(gap.owner!=='reviewer'||gap.safe_automation===true)return null;
 if(gap.code==='VERSION_UNRESOLVED'&&gap.action==='REVIEW_IDENTITY_FACT')return 'version';
 if(gap.code==='HUMAN_REVIEW_REQUIRED'&&gap.action==='REVIEW_RELATION')return 'document';
 return null;
}
export function presentGap(gap: Gap,brief?:Brief) {
 const title=gapLabels[gap.code]?.[0]||'仍有事项需要核对';
 const fallback={title,action:gapLabels[gap.code]?.[1]||'现有记录不足以确定处理方式；请交由审核确认问题范围。'};
 const kind=reviewKind(gap),materials=gapMaterials(gap,brief);
 if(kind&&materials) {
  const found=materials.filter(m=>kind==='version'?m.version:m.document).length;
  if(found===materials.length)return {title:kind==='version'?'版本材料已定位，关联仍待审核':'许可正文已取得，适用关系待审核',action:kind==='version'
   ?'版本材料已定位，下一步核对它与当前组件的关联并审核接纳；无需重复寻找已保存的相同材料。'
   :`许可正文已取得${materials.every(m=>m.matched)?'，内容已匹配':'，内容匹配仍待核对'}；下一步审核它与当前组件及用途的适用关系，找到材料不等于授权已核验。`};
  if(found)return {title,action:`部分对象（${found}/${materials.length}）${kind==='version'?'的版本材料已定位':'的许可正文已取得'}，仍需审核；其余对象的材料状态待核对，不能将本项视为已完成。`};
  if(kind==='version'&&materials.some(m=>m.document))return {title,action:'已取得对应许可正文；版本材料仍待定位，正文不能代替版本及适用关系核对。'};
  return {title,action:'当前记录不足以确认该事项对应的材料；核对已有材料，核对对象和材料关联后再决定下一步。'};
 }
 if(brief&&['VERSION_UNRESOLVED','HUMAN_REVIEW_REQUIRED'].includes(gap.code)) {
  if(gap.code==='VERSION_UNRESOLVED'&&gap.owner==='system'&&gap.action==='RESOLVE_LOCAL'&&gap.safe_automation===true&&materials) {
   const found=materials.filter(m=>m.version).length;
   if(found===materials.length)return {title,action:'对应版本材料已定位；仍需核对材料与对象的关联，不能据此认定正式输入已接纳。'};
   return {title,action:found?`部分对象（${found}/${materials.length}）已有版本材料；继续核对其余对象。检查沿用现有范围，已保存材料继续保留。`:'当前对象仍缺版本材料，可检查保留的本地材料；材料取得后仍需核对与审核。'};
  }
  return {title,action:'核对已有材料，确认对象、材料状态及负责人；旧记录不足以确定可自动执行的下一步。'};
 }
 return fallback;
}
export function primaryAction(brief:Brief,usage:Usage,state:{dirty:boolean;busy:boolean;active:boolean;needsSelection:boolean}) {
 const base={searchLabel:'重新查找本地材料',disabled:state.busy||state.active||state.dirty};
 if(state.dirty)return {...base,kind:'usage' as const,label:'查看／修改新选择',description:'先确认新选择并显式生成新评估；下面仍是原用途的结果，材料写操作暂不可用。'};
 if(state.busy||state.active)return {...base,kind:'progress' as const,label:state.busy?'正在读取或提交…':'读取任务进度',description:'保持当前固定结果，先查看已有任务进度；不会重复发起查找。'};
 if(state.needsSelection)return {...base,kind:'saved' as const,label:'查看已保存的查找结果',description:'另有查找结果已保存；当前仍显示先前固定结果，点击后才读取该保存结果。'};
 if(usage.preset==='unknown')return {...base,kind:'usage' as const,label:'选择用途',searchLabel:'查找本地材料（可选）',description:'点击“选择用途”，说明准备怎样使用；不确定的事实可以暂时跳过，也可先查看材料。'};
 const review=brief.gaps.flatMap(g=>{
  const kind=reviewKind(g),materials=gapMaterials(g,brief);
  return kind&&materials?materials.filter(m=>kind==='version'?m.version:m.document):[];
 });
 const sourceBlocked=(id:string)=>brief.gaps.some(g=>['LOCAL_SOURCE_NOT_RETAINED','PROVIDER_NOT_SUPPORTED','IDENTITY_MISMATCH','EVIDENCE_CONFLICT','BUDGET_EXHAUSTED','MATERIAL_ENCODING_UNSUPPORTED'].includes(g.code)
  &&(!g.resource_ids?.length||g.resource_ids.includes(id)));
 const missing=brief.gaps.some(g=>g.code==='VERSION_UNRESOLVED'&&g.owner==='system'&&g.action==='RESOLVE_LOCAL'&&g.safe_automation===true
  &&gapMaterials(g,brief)?.some(m=>!m.version&&!sourceBlocked(m.id)));
 if(missing)return {...base,kind:'search' as const,label:'继续检查本地材料',description:(review.length?'部分对象已有材料，待核对与审核；':'')+'仍有对象缺少版本材料。检查沿用现有检查范围，已保存材料继续保留，找到材料仍不等于授权已核验。'};
 const allTargets=brief.gaps.flatMap(g=>reviewKind(g)?gapMaterials(g,brief)??[]:[]);
 const partial=allTargets.some(m=>!review.some(r=>r.id===m.id));
 const summary=review.length?(partial?'部分待审核对象已有材料，其余对象材料仍待核对。':review.every(m=>m.version&&m.document&&m.matched)
  ?'已找到待审核对象的版本材料与许可正文，正文内容已匹配。':review.every(m=>m.version)
  ?'待审核对象的版本材料已定位，许可正文与内容匹配状态请查看材料记录。':'待审核对象的许可正文已取得，版本与内容匹配状态请查看材料记录。')
  +'接下来需审核材料与当前组件及用途的适用关系；已保存的相同材料无需重复寻找。正式评估仍未改变。'
  :'当前待确认事项涉及用途事实、材料关联或规则范围。查看对应依据与负责人；重新查找不能代替这些确认或审核。';
 return {...base,kind:'materials' as const,label:'查看材料与待审核事项',description:summary};
}
export function initialSnapshot(jobs:ResolutionJob[],aid:string) {
 return jobs.find(j=>j.request_key==='initial-'+aid&&j.status==='completed')?.snapshot_id??undefined;
}
export function orderedJobs(jobs:ResolutionJob[]) {
 return [...jobs].sort((a,b)=>(b.created_at??'').localeCompare(a.created_at??'')||b.job_id.localeCompare(a.job_id));
}
export function activeResolution(jobs:ResolutionJob[]) {return orderedJobs(jobs).find(j=>['queued','running'].includes(j.status));}
export function needsResultSelection(job:ResolutionJob|null,snapshotId?:string) {
 return !!job&&job.status==='completed'&&!!job.snapshot_id&&job.snapshot_id!==snapshotId;
}
export function resolutionStatus(job:ResolutionJob) {
 const text={queued:'本地材料查找等待中；原评估保留。',running:'正在查找本地材料；原评估保留。',completed:'本地材料查找结束，不代表授权已通过。',
  failed:'本次查找失败；历史材料和原评估保留，可重新查找。',cancelled:'本次查找已取消；历史材料和原评估保留，可重新查找。',interrupted:'本次查找已中断；历史材料和原评估保留，可重新查找。'};
 return {text:text[job.status],active:['queued','running'].includes(job.status),completed:job.status==='completed'};
}
export function modelStatus(reason?:string) {
 const labels:Record<string,string>={model_not_configured:'当前实例未配置模型辅助；可直接查看已找到的原文。',model_no_material:'缺少可供模型核对的材料；请先查看材料缺口。',
  model_sensitive_material:'材料未通过模型输入边界检查；请直接核对原文。',model_provider_unavailable:'模型服务不可用；可直接核对本地查找结果。'};
 return labels[reason??'']??'模型超时或输出未通过核对；本地查找结果保留，可直接核对原文。';
}

// Presentation groups retain their original gap references. No inference from raw prose.
export function pendingGroups(brief:Brief) {
 const groups=[
  {owner:'reviewer',title:'材料与适用关系待审核'},
  {owner:'user',title:'实际使用范围仍需确认'},
  {owner:'system',title:'材料与检查范围仍需核对'},
 ] as const;
 return groups.map(group=>({...group,gaps:brief.gaps.filter(g=>g.owner===group.owner)})).filter(g=>g.gaps.length);
}
export function materialOriginal(text:unknown) {
 return typeof text==='string'&&text.trim()?text:'这份记录未保存可显示的许可原文；请核对原有许可文件，不会自动读取其他材料。';
}

// Display correspondence from the existing engine intent inputs. This does not
// decide applicability or permission, and never reads a draft or raw reason text.
export type UsageField = keyof typeof usageFields;
const intentFields:Record<string,UsageField>={commercial:'commercial',modification:'modified',
 closed_distribution:'distributed',redistribution:'distributed',network_service:'network_service',ai_assets:'redistributed_assets'};
export function usageHints(brief:Pick<Brief,'gaps'>,usage:Usage) {
 const fields:UsageField[]=[];let uncertain=false;
 for(const gap of brief.gaps.filter(g=>g.code==='USAGE_MISSING')) {
  if(!Array.isArray(gap.affected_dimensions)||!gap.affected_dimensions.length){uncertain=true;continue;}
  for(const dimension of gap.affected_dimensions) {
   const field=Object.hasOwn(intentFields,dimension)?intentFields[dimension]:undefined;
   if(!field){uncertain=true;continue;}
   const value=usage[field];
   if(value==null){if(!fields.includes(field))fields.push(field);}
   else if(typeof value!=='boolean')uncertain=true;
  }
 }
 return {fields,uncertain,text:fields.length?'还需说明：'+fields.map(f=>usageFields[f]).join('、')+'。': ''};
}
export function scopeSummary(brief:Pick<Brief,'gaps'>) {
 const sources=brief.gaps.filter(g=>g.code==='SCOPE_UNRESOLVED');
 const regular=new Set<string>(),ai=new Set<string>(),all=new Set<string>();let unclassified=0;
 for(const g of sources) {
  const dims=g.affected_dimensions;
  const known=Array.isArray(dims)&&dims.length>0&&dims.every(d=>Object.hasOwn(intentFields,d));
  const ids=Array.isArray(g.resource_ids)?g.resource_ids.filter(id=>typeof id==='string'&&id.length):[];
  if(!known||!ids.length)unclassified++;
  for(const id of ids) {all.add(id);if(known&&dims!.some(d=>d!=='ai_assets'))regular.add(id);if(dims?.includes('ai_assets'))ai.add(id);}
 }
 const overlap=[...ai].filter(id=>regular.has(id)).length;
 const text=regular.size&&ai.size&&overlap===ai.size&&all.size===regular.size
  ?`涉及${regular.size}条资源记录，其中${ai.size}条AI资源另有范围核验事项。`
  :`常规范围涉及${regular.size}条记录，AI资源范围涉及${ai.size}条记录；重叠${overlap}条，共${all.size}条已定位资源记录。`;
 return {sources,regular:regular.size,ai:ai.size,overlap,total:all.size,unclassified,text};
}
export function scopeSourceLabel(gap:Gap) {
 const dims=gap.affected_dimensions;
 const kind=dims?.length&&dims.every(d=>d==='ai_assets')?'AI资源范围核验':dims?.length&&dims.every(d=>Object.hasOwn(intentFields,d)&&d!=='ai_assets')?'常规资源范围核验':'资源范围核验（种类仍待核对）';
 const owner={user:'由你确认实际归属与使用范围',reviewer:'由审核人员核验',system:'由系统检查，结果仍待核验'}[gap.owner];
 return `${kind} · ${owner} · ${new Set(gap.resource_ids??[]).size}条资源记录`;
}
