import { request } from './scans';
import { listAssessments, usageFields, type Assessment } from './assessments';
import { sameBinding, readBinding, readIndex, readResult, type Binding, type Result, type Subject, type Use } from './p2';

export type Priority='routine'|'attention'|'manual';
export type AutoState='CONDITIONAL'|'NONSTANDARD'|'UNAVAILABLE'|'OUTSIDE_NPM';
export type AutoResource={subject:Subject;name:string;license_expression:string|null;state:AutoState;priority:Priority;artifact_binding:'NOT_ESTABLISHED'|'RESOLVED_URL_MATCH'|'EXACT_COORDINATE_ONLY';conditions:string[];reasons:string[];evidence_ids:string[];source_refs:{kind:'metadata'|'tarball';url:string;sha256:string}[];members:{member:string;sha256:string}[];maintenance_deprecated:boolean;applicability_review:'NOT_SIGNED'};
export type AutomaticReview={schema_version:'openguard-auto-review/1';rule_version:'npm-full-license-review/1';review_id:string;result_id:string;result_sha256:string;binding:Binding;data_scope:'OWNER'|'TEST_ONLY';source_profile_sha256:string|null;source_status:'CHECKED'|'NOT_CONFIGURED';usage:Record<Use,boolean|null>;formal_effect:'none';model_calls:0;applicability_review:'NOT_SIGNED';resources:AutoResource[];summary:{total_resources:number;priority_counts:Record<Priority,number>;state_counts:Record<AutoState,number>;source_packages:number;license_materials:number;license_groups:{license:string;count:number}[];maintenance_count:number};limitations:string[]};
export const priorityLabels:Record<Priority,string>={routine:'常规义务',attention:'维护关注',manual:'单独审查'};
export const priorities:Priority[]=['routine','attention','manual'];
const states:AutoState[]=['CONDITIONAL','NONSTANDARD','UNAVAILABLE','OUTSIDE_NPM'];
const object=(v:unknown):v is Record<string,any>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const text=(v:unknown):v is string=>typeof v==='string'&&v.length>0;
const strings=(v:unknown):v is string[]=>Array.isArray(v)&&v.every(text);
const unique=(v:unknown):v is string[]=>strings(v)&&new Set(v).size===v.length;
const hash=(v:unknown)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const integer=(v:unknown):v is number=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0;
const sameSet=(a:string[],b:string[])=>a.length===b.length&&a.every(x=>b.includes(x));
const npm=(v:unknown)=>{try{if(!text(v))return false;const u=new URL(v);return u.protocol==='https:'&&u.host==='registry.npmjs.org'&&!u.username&&!u.password&&!u.search&&!u.hash;}catch{return false;}};
const fail=():never=>{throw Error('自动初评与当前对象、来源或统计不一致，未展示未经核对的结论。');};

export function validateAutomaticReview(v:unknown,result:Result):AutomaticReview {
 const ids=result.resources.map(r=>r.subject.resource_id),uses=Object.keys(usageFields) as Use[];
 if(!object(v)||v.schema_version!=='openguard-auto-review/1'||v.rule_version!=='npm-full-license-review/1'||typeof v.review_id!=='string'||!/^p2auto_[a-f0-9]{64}$/.test(v.review_id)||v.result_id!==result.result_id||v.result_sha256!==result.result_sha256||!object(v.binding)||!sameBinding(v.binding as Binding,result.binding)||v.data_scope!==result.data_scope||v.formal_effect!=='none'||v.model_calls!==0||v.applicability_review!=='NOT_SIGNED'||!object(v.usage)||Object.keys(v.usage).length!==uses.length||!uses.every(k=>v.usage[k]===result.usage[k])||!['CHECKED','NOT_CONFIGURED'].includes(v.source_status)||!(v.source_profile_sha256===null||hash(v.source_profile_sha256))||(v.source_status==='CHECKED')!==(v.source_profile_sha256!==null)||!strings(v.limitations)||!v.limitations.length||!Array.isArray(v.resources)||v.resources.length!==ids.length||!object(v.summary))return fail();
 const seen:string[]=[],count:Record<string,number>={},licenses:Record<string,number>={};let sourced=0,materials=0,maintenance=0;
 for(const row of v.resources){
  if(!object(row)||!object(row.subject))return fail();
  const parent=result.resources.find(r=>r.subject.resource_id===row.subject.resource_id);
  if(!parent||seen.includes(row.subject.resource_id)||row.subject.version!==parent.subject.version||!text(row.name)||!(row.license_expression===null||typeof row.license_expression==='string'&&/^[A-Za-z0-9.+() -]{1,100}$/.test(row.license_expression))||!states.includes(row.state)||!priorities.includes(row.priority)||!['NOT_ESTABLISHED','RESOLVED_URL_MATCH','EXACT_COORDINATE_ONLY'].includes(row.artifact_binding)||!strings(row.conditions)||!strings(row.reasons)||!row.reasons.length||!unique(row.evidence_ids)||!sameSet(row.evidence_ids,parent.evidence_ids)||!Array.isArray(row.source_refs)||!Array.isArray(row.members)||typeof row.maintenance_deprecated!=='boolean'||row.applicability_review!=='NOT_SIGNED')return fail();
  seen.push(row.subject.resource_id);
  if(row.source_refs.length){
   if(v.source_status!=='CHECKED'||row.source_refs.length!==2||new Set(row.source_refs.map((s:any)=>s.kind)).size!==2||!row.source_refs.every((s:any)=>object(s)&&['metadata','tarball'].includes(s.kind)&&npm(s.url)&&hash(s.sha256)))return fail();sourced++;
  }
  const memberNames:string[]=[];
  for(const member of row.members){if(!object(member)||!text(member.member)||!member.member.startsWith('package/')||member.member.split('/').some((x:string)=>!x||x==='.'||x==='..')||member.member.includes('\\')||memberNames.includes(member.member)||!hash(member.sha256))return fail();memberNames.push(member.member);materials++;}
  if(row.state==='CONDITIONAL'){
   if(!['MIT','ISC'].includes(row.license_expression)||row.conditions.length<2||row.source_refs.length!==2||!row.members.length||row.artifact_binding==='NOT_ESTABLISHED'||row.priority!==(row.maintenance_deprecated?'attention':'routine'))return fail();
  }else if(row.priority!=='manual'||row.conditions.length)return fail();
  if(row.state==='NONSTANDARD'&&row.source_refs.length!==2)return fail();
  if(['UNAVAILABLE','OUTSIDE_NPM'].includes(row.state)&&(row.source_refs.length||row.members.length||row.maintenance_deprecated||row.license_expression!==null||row.artifact_binding!=='NOT_ESTABLISHED'))return fail();
  count[row.priority]=(count[row.priority]??0)+1;count[row.state]=(count[row.state]??0)+1;
  const license=row.license_expression??'UNOBSERVED';licenses[license]=(licenses[license]??0)+1;if(row.maintenance_deprecated)maintenance++;
 }
 const s=v.summary;
 if(!sameSet(seen,ids)||s.total_resources!==ids.length||!object(s.priority_counts)||Object.keys(s.priority_counts).length!==priorities.length||!priorities.every(k=>integer(s.priority_counts[k])&&s.priority_counts[k]===(count[k]??0))||!object(s.state_counts)||Object.keys(s.state_counts).length!==states.length||!states.every(k=>integer(s.state_counts[k])&&s.state_counts[k]===(count[k]??0))||s.source_packages!==sourced||s.license_materials!==materials||s.maintenance_count!==maintenance||!Array.isArray(s.license_groups)||s.license_groups.length!==Object.keys(licenses).length||new Set(s.license_groups.map((g:any)=>g.license)).size!==s.license_groups.length||!s.license_groups.every((g:any)=>object(g)&&text(g.license)&&integer(g.count)&&g.count===licenses[g.license]))return fail();
 return v as AutomaticReview;
}
export async function readAutomaticReview(a:Assessment,result:Result,signal?:AbortSignal){
 if(a.id!==result.binding.assessment_id||a.scan_id!==result.binding.scan_id||a.version!==result.binding.assessment_version)return fail();
 const path=`/scans/${encodeURIComponent(a.scan_id)}/assessments/${encodeURIComponent(a.id)}/p2/results/${encodeURIComponent(result.result_id)}/automatic-review?assessment_version=${a.version}`;
 return validateAutomaticReview(await request(path,{},signal),result);
}
export class OverviewPreparationRequired extends Error {
 constructor(public code:'OVERVIEW_ASSESSMENT_NOT_READY'|'OVERVIEW_RESULT_NOT_READY',message:string){super(message);this.name='OverviewPreparationRequired';}
}
export async function readOverviewAutomaticReview(scanId:string,query:URLSearchParams,signal?:AbortSignal){
 const list=await listAssessments(scanId,signal),requested=query.get('assessment_id');
 const assessment=requested?list.items.find(a=>a.id===requested):[...list.items].sort((a,b)=>b.version-a.version)[0];
 if(!assessment){
  if(requested)throw Error('指定评估尚未读回，未切换到其他版本。');
  throw new OverviewPreparationRequired('OVERVIEW_ASSESSMENT_NOT_READY','当前扫描还没有可读的项目评估。请先打开项目评估查看处理进度；此页不会重复提交。');
 }
 const binding=await readBinding(assessment,signal),requestedResult=query.get('p2_result');
 const resultId=requestedResult??(await readIndex(assessment,signal)).head_result_id;
 if(!resultId)throw new OverviewPreparationRequired('OVERVIEW_RESULT_NOT_READY','扫描与评估已保存，尚未生成用途核对结果。进入项目评估后点击生成，即可查看分组与建议；此页未自动创建。');
 const result=await readResult(assessment,binding,resultId,signal);
 return{assessment,result,review:await readAutomaticReview(assessment,result,signal)};
}
