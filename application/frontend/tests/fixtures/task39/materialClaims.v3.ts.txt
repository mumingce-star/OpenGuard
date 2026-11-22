import type { DeclarationSnapshot } from '../types/domain';
import { request } from './scans';
import type { Assessment } from './assessments';
import { sameBinding, type Binding, type Result, type Subject, type Use } from './p2';

export type ClaimState='SUPPORT'|'RESTRICTION'|'UNKNOWN'|'COUNTER_EVIDENCE'|'NOT_COVERED';
export type Clause={clause_id:string;material_id:string;material_sha256:string;kind:string;byte_start:number;byte_end:number;line_start:number;line_end:number;quote:string;quote_sha256:string};
type EvidenceRef={evidence_id:string;source_sha256:string|null};
export type DeclarationObservation={subject:Subject;expression:string;normalized_ids:string[];declaration_evidence_ids:string[];evidence:EvidenceRef[];evidence_status:'COMPLETE'|'UNKNOWN'};
export type MaterialObservation={material_id:string;subject:Subject;source_sha256:string;byte_count:number;filename:string;parse_state:'MATCHED_MIT'|'NOTICE_OBSERVED'|'UNSUPPORTED'|'FAILED';parse_reason:string;binding_state:'BOUND_TO_SAVED_RESULT';adoption_state:'OBSERVATION_ONLY'|'CONDITIONAL_TEXT_BASIS';declared_spdx:string;text_license:'MIT'|'UNKNOWN';license_version:null;version_scope:'RESOURCE_VERSION_NOT_LICENSE_VERSION';role:'root_package'|'dependency'|'unknown';role_state:'observed'|'inferred'|'unknown';role_basis_evidence_ids:string[];source_binding:'PINNED_RELEASE_MATCH'|'NOT_ESTABLISHED';source_profile_sha256:string|null;evidence:EvidenceRef[];clauses:Clause[]};
export type SourceObservation={source_observation_id:string;subject:Subject;source_profile_sha256:string;archive_sha256:string;notice_status:'ABSENT_COMPLETE'|'PRESENT_UNREVIEWED'|'INCOMPLETE'|'INVALID';reason:string;member_count:number;enumeration_complete:boolean;notices:{path:string;bytes:number;sha256:string|null;inspection_state:'EXTRACTED_UNREVIEWED'|'UNSUPPORTED_FORMAT'|'PARSE_FAILED'|'LIMIT_EXCEEDED'|'INVALID_TYPE'|'READ_FAILED'}[]};
export type ClaimLink={claim_id:string;usage:Use;subject:Subject;material_ids:string[];evidence:EvidenceRef[];clause_ids:string[];conditions:string[];counter_evidence:{code:string;material_ids:string[];evidence_ids:string[];source_observation_ids:string[];declaration_evidence_ids:string[];evidence_status:'COMPLETE'|'UNKNOWN'}[];state:ClaimState;formal_effect:'none'};
export type PurposeAdvice={usage:Use;subject:Subject;saved_value:boolean|null;state:ClaimState;reasons:string[];claim_ids:string[];conditions:string[];limitations:string[]};
export type MaterialClaims={schema_version:'openguard-material-claims/3';rule_version:'mit-bound-claim/3';view_id:string;result_id:string;result_sha256:string;revision:number;previous_result_id:string|null;binding:Binding;data_scope:'OWNER'|'TEST_ONLY';source_status:'CHECKED'|'NOT_CONFIGURED';source_profile_sha256:string|null;materials:MaterialObservation[];declaration_observations:DeclarationObservation[];source_observations:SourceObservation[];claims:ClaimLink[];advice:PurposeAdvice[];formal_effect:'none';applicability_review:'NOT_SIGNED';model_calls:0};
const obj=(v:unknown):v is Record<string,any>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const fields=(v:unknown,names:string)=>obj(v)&&Object.keys(v).sort().join(',')===names.split(' ').sort().join(',');
const text=(v:unknown):v is string=>typeof v==='string'&&v.length>0&&v.length<=65536;
const hash=(v:unknown):v is string=>typeof v==='string'&&/^[0-9a-f]{64}$/.test(v);
const id=(v:unknown):v is string=>typeof v==='string'&&/^[A-Za-z0-9_.:-]{1,200}$/.test(v);
const list=(v:unknown):v is string[]=>Array.isArray(v)&&v.every(text);
const ids=(v:unknown):v is string[]=>Array.isArray(v)&&v.every(id)&&new Set(v).size===v.length;
const integer=(v:unknown)=>Number.isSafeInteger(v);
const uses=['commercial','distributed','modified'];
const states=['SUPPORT','RESTRICTION','UNKNOWN','COUNTER_EVIDENCE','NOT_COVERED'];
const sameIds=(a:string[],b:string[])=>a.length===b.length&&new Set(a).size===a.length&&new Set(b).size===b.length&&a.every(x=>b.includes(x));
const declarationFail=():never=>{throw Error('扫描声明来源无法与本版证据核对，已停止展示新版用途建议；旧结果保持可读。');};
const fail=():never=>{throw Error('材料与用途建议未通过当前结果的绑定核对，已停止展示。');};

// Validate structure, references and quote bytes. This is not full original-material authentication.
// Frozen v1/v2 clients intentionally reject v3; old Result/Material/Receipt contracts are unchanged.
export async function validateMaterialClaims(v:unknown,result:Result,anchor:DeclarationSnapshot|null|undefined):Promise<MaterialClaims> {
 if(!fields(v,'schema_version rule_version view_id result_id result_sha256 revision previous_result_id binding data_scope source_status source_profile_sha256 materials declaration_observations source_observations claims advice formal_effect applicability_review model_calls')||!obj(v))return fail();
 if(v.schema_version!=='openguard-material-claims/3'||v.rule_version!=='mit-bound-claim/3'||!id(v.view_id)||v.result_id!==result.result_id||v.result_sha256!==result.result_sha256||v.revision!==result.revision||v.previous_result_id!==result.previous_result_id||!fields(v.binding,Object.keys(result.binding).join(' '))||!sameBinding(v.binding as Binding,result.binding)||v.data_scope!==result.data_scope||v.formal_effect!=='none'||v.model_calls!==0||v.applicability_review!=='NOT_SIGNED'||!['CHECKED','NOT_CONFIGURED'].includes(v.source_status)||!(v.source_profile_sha256===null||hash(v.source_profile_sha256))||(v.source_status==='CHECKED')!==(v.source_profile_sha256!==null)||!Array.isArray(v.materials)||v.materials.length>20||!Array.isArray(v.source_observations)||v.source_observations.length>1000||!Array.isArray(v.claims)||!Array.isArray(v.advice)||v.claims.length!==result.resources.length*3||v.advice.length!==result.resources.length*3)return fail();
 const rowFor=(s:any)=>fields(s,'resource_id version')?result.resources.find(r=>r.subject.resource_id===s.resource_id&&r.subject.version===s.version):undefined;
 const evidenceOK=(es:any,row:Result['resources'][number])=>Array.isArray(es)&&new Set(es.map(e=>e?.evidence_id)).size===es.length&&es.every(e=>fields(e,'evidence_id source_sha256')&&id(e.evidence_id)&&row.evidence_ids.includes(e.evidence_id)&&(e.source_sha256===null||hash(e.source_sha256))&&e.source_sha256===(row.evidence_source_hashes[e.evidence_id]??null));
 // The anchor comes from the existing scan-report adapter, never from v itself.
 if(!anchor||anchor.scan_id!==result.binding.scan_id||anchor.project_revision!==result.binding.project_revision
   ||!Array.isArray(anchor.resources)||new Set(anchor.resources.map(r=>r.resource_id)).size!==anchor.resources.length
   ||!Array.isArray(v.declaration_observations)||v.declaration_observations.length!==result.resources.length)return declarationFail();
 const declarationMap=new Map<string,DeclarationObservation>();
 for(const d of v.declaration_observations){
  if(!fields(d,'subject expression normalized_ids declaration_evidence_ids evidence evidence_status'))return declarationFail();
  const row=rowFor(d.subject),a=anchor.resources.find(x=>x.resource_id===d.subject?.resource_id&&x.version===d.subject?.version);
  if(!row||!a||declarationMap.has(row.subject.resource_id)||!text(d.expression)||!list(d.normalized_ids)
    ||d.expression!==a.expression||JSON.stringify(d.normalized_ids)!==JSON.stringify(a.normalized_ids)
    ||!ids(a.resource_evidence_ids)||!ids(a.declaration_evidence_ids)||!evidenceOK(d.evidence,row)
    ||!ids(d.declaration_evidence_ids)||!sameIds(d.declaration_evidence_ids,d.evidence.map((e:EvidenceRef)=>e.evidence_id)))return declarationFail();
  if(!Array.isArray(a.evidence)||!sameIds(a.evidence.map(e=>e.evidence_id),a.declaration_evidence_ids))return declarationFail();
  const expected=a.evidence.filter(e=>a.resource_evidence_ids.includes(e.evidence_id)&&row.evidence_ids.includes(e.evidence_id)
    &&hash(e.source_sha256)&&e.source_sha256===row.evidence_source_hashes[e.evidence_id]).map(e=>e.evidence_id);
  const complete=expected.length>0&&expected.length===a.declaration_evidence_ids.length;
  if(!sameIds(d.declaration_evidence_ids,expected)||d.evidence_status!==(complete?'COMPLETE':'UNKNOWN'))return declarationFail();
  declarationMap.set(row.subject.resource_id,d);
 }
 const sourceMap=new Map<string,SourceObservation>(),sourceRows=new Map<string,SourceObservation>();
 for(const o of v.source_observations){
  if(!fields(o,'source_observation_id subject source_profile_sha256 archive_sha256 notice_status reason member_count enumeration_complete notices'))return fail();
  const row=rowFor(o.subject);
  if(!row||!id(o.source_observation_id)||sourceMap.has(o.source_observation_id)||sourceRows.has(row.subject.resource_id)||v.source_status!=='CHECKED'||o.source_profile_sha256!==v.source_profile_sha256||!hash(o.archive_sha256)||!['ABSENT_COMPLETE','PRESENT_UNREVIEWED','INCOMPLETE','INVALID'].includes(o.notice_status)||!text(o.reason)||!integer(o.member_count)||o.member_count<0||o.member_count>2000||typeof o.enumeration_complete!=='boolean'||!Array.isArray(o.notices)||o.notices.length>20||o.notices.length>o.member_count)return fail();
  const paths=new Set<string>();
  for(const n of o.notices){
   if(!fields(n,'path bytes sha256 inspection_state')||!text(n.path)||n.path.length>4096||!n.path.startsWith('package/')||n.path.includes('\\')||n.path.split('/').some((x:string)=>!x||x==='.'||x==='..')||paths.has(n.path)||!integer(n.bytes)||n.bytes<0||n.bytes>4194304||!(n.sha256===null||hash(n.sha256))||!['EXTRACTED_UNREVIEWED','UNSUPPORTED_FORMAT','PARSE_FAILED','LIMIT_EXCEEDED','INVALID_TYPE','READ_FAILED'].includes(n.inspection_state))return fail();
   if(['EXTRACTED_UNREVIEWED','UNSUPPORTED_FORMAT','PARSE_FAILED'].includes(n.inspection_state)&&(n.sha256===null||n.bytes>65536))return fail();
   if(n.inspection_state==='EXTRACTED_UNREVIEWED'&&(n.bytes<1||!/^NOTICE(?:\.(?:txt|md|rst))?$/i.test(n.path.split('/').at(-1)!)))return fail();
   paths.add(n.path);
  }
  if(o.notice_status==='INCOMPLETE'?o.enumeration_complete:!o.enumeration_complete)return fail();
  if(o.notice_status==='ABSENT_COMPLETE'&&(o.notices.length||o.member_count<2))return fail();
  if(o.notice_status==='PRESENT_UNREVIEWED'&&(!o.notices.length||o.notices.some((n:SourceObservation['notices'][number])=>n.inspection_state!=='EXTRACTED_UNREVIEWED')))return fail();
  if(o.notice_status==='INVALID'&&(!o.notices.length||o.notices.every((n:SourceObservation['notices'][number])=>n.inspection_state==='EXTRACTED_UNREVIEWED')))return fail();
  sourceMap.set(o.source_observation_id,o);sourceRows.set(row.subject.resource_id,o);
 }
 const materialMap=new Map<string,MaterialObservation>(),clauseMap=new Map<string,Clause>();
 for(const m of v.materials){
  if(!fields(m,'material_id subject source_sha256 byte_count filename parse_state parse_reason binding_state adoption_state declared_spdx text_license license_version version_scope role role_state role_basis_evidence_ids source_binding source_profile_sha256 evidence clauses'))return fail();
  const row=rowFor(m.subject);
  if(!row||!id(m.material_id)||materialMap.has(m.material_id)||!row.material_ids.includes(m.material_id)||!hash(m.source_sha256)||!integer(m.byte_count)||m.byte_count<1||m.byte_count>65536||!text(m.filename)||!['MATCHED_MIT','NOTICE_OBSERVED','UNSUPPORTED','FAILED'].includes(m.parse_state)||!text(m.parse_reason)||m.binding_state!=='BOUND_TO_SAVED_RESULT'||!['OBSERVATION_ONLY','CONDITIONAL_TEXT_BASIS'].includes(m.adoption_state)||!text(m.declared_spdx)||!['MIT','UNKNOWN'].includes(m.text_license)||m.license_version!==null||m.version_scope!=='RESOURCE_VERSION_NOT_LICENSE_VERSION'||!['root_package','dependency','unknown'].includes(m.role)||!['observed','inferred','unknown'].includes(m.role_state)||!ids(m.role_basis_evidence_ids)||!m.role_basis_evidence_ids.every((e:string)=>row.evidence_ids.includes(e))||!['PINNED_RELEASE_MATCH','NOT_ESTABLISHED'].includes(m.source_binding)||m.source_profile_sha256!==v.source_profile_sha256||!evidenceOK(m.evidence,row)||!m.evidence.length||!Array.isArray(m.clauses)||m.clauses.length>5)return fail();
  if(m.declared_spdx!==declarationMap.get(row.subject.resource_id)!.expression)return fail();
  if(m.role==='unknown'?(m.role_state!=='unknown'||m.role_basis_evidence_ids.length!==0):(m.role!=='root_package'||m.role_state!=='inferred'||m.role_basis_evidence_ids.length<2||m.role_basis_evidence_ids.some((i:string)=>!hash(row.evidence_source_hashes[i]))))return fail();
  if(m.adoption_state==='CONDITIONAL_TEXT_BASIS'&&(declarationMap.get(row.subject.resource_id)!.evidence_status!=='COMPLETE'||declarationMap.get(row.subject.resource_id)!.expression!=='MIT'||JSON.stringify(declarationMap.get(row.subject.resource_id)!.normalized_ids)!=='["MIT"]'||m.source_binding!=='PINNED_RELEASE_MATCH'||v.source_status!=='CHECKED'||m.parse_state!=='MATCHED_MIT'||sourceRows.get(row.subject.resource_id)?.notice_status!=='ABSENT_COMPLETE'))return fail();
  if(m.parse_state==='MATCHED_MIT'&&(m.text_license!=='MIT'||m.clauses.length!==5))return fail();
  for(const c of m.clauses){
   if(!fields(c,'clause_id material_id material_sha256 kind byte_start byte_end line_start line_end quote quote_sha256')||!id(c.clause_id)||clauseMap.has(c.clause_id)||c.material_id!==m.material_id||c.material_sha256!==m.source_sha256||!['license_identifier','copyright','permission','condition','warranty','notice'].includes(c.kind)||!integer(c.byte_start)||!integer(c.byte_end)||c.byte_start<0||c.byte_end<=c.byte_start||c.byte_end>m.byte_count||!integer(c.line_start)||!integer(c.line_end)||c.line_start<1||c.line_end<c.line_start||!text(c.quote)||new TextEncoder().encode(c.quote).length!==c.byte_end-c.byte_start||!hash(c.quote_sha256))return fail();
   clauseMap.set(c.clause_id,c);
  }
  if(m.parse_state==='MATCHED_MIT'&&!sameIds(m.clauses.map((c:Clause)=>c.kind),['license_identifier','copyright','permission','condition','warranty']))return fail();
  materialMap.set(m.material_id,m);
 }
 if(!sameIds([...materialMap.keys()],result.material_ids))return fail();
 const claimMap=new Map<string,ClaimLink>(),pairs=new Set<string>();
 for(const c of v.claims){
  if(!fields(c,'claim_id usage subject material_ids evidence clause_ids conditions counter_evidence state formal_effect'))return fail();
  const row=rowFor(c.subject),pair=JSON.stringify([row?.subject.resource_id,row?.subject.version,c.usage]);
  if(!row||!id(c.claim_id)||claimMap.has(c.claim_id)||pairs.has(pair)||!uses.includes(c.usage)||!states.includes(c.state)||c.formal_effect!=='none'||!ids(c.material_ids)||!c.material_ids.every((i:string)=>materialMap.get(i)?.subject.resource_id===row.subject.resource_id)||!sameIds(c.material_ids,row.material_ids)||!evidenceOK(c.evidence,row)||!ids(c.clause_ids)||!c.clause_ids.every((i:string)=>c.material_ids.includes(clauseMap.get(i)?.material_id))||!list(c.conditions)||!Array.isArray(c.counter_evidence))return fail();
  const declaration=declarationMap.get(row.subject.resource_id)!;
  const allMaterials=c.material_ids.map((i:string)=>materialMap.get(i)!);
  const licenses=allMaterials.filter((m:MaterialObservation)=>/^LICEN[CS]E(?:\.|$)/i.test(m.filename));
  const mit=licenses.filter((m:MaterialObservation)=>m.text_license==='MIT');
  const notices=allMaterials.filter((m:MaterialObservation)=>m.parse_state==='NOTICE_OBSERVED');
  const multi=[' AND ',' OR ',' WITH '].some(t=>declaration.expression.includes(t));
  const expectedCounters:{code:string;ms:MaterialObservation[];declaration:string[];source:string[];provenance:boolean}[]=[];
  const add=(code:string,ms:MaterialObservation[],ds:string[]=[],source:string[]=[],provenance=true)=>expectedCounters.push({code,ms,declaration:ds,source,provenance});
  if(declaration.expression==='MIT'&&JSON.stringify(declaration.normalized_ids)!=='["MIT"]')
    add('SPDX_NORMALIZATION_CONFLICT',[],declaration.declaration_evidence_ids,[],declaration.evidence_status==='COMPLETE');
  if(!['MIT','UNOBSERVED','CONFLICT_OR_UNSUPPORTED'].includes(declaration.expression)&&!multi&&mit.length)
    add('SPDX_TEXT_CONFLICT',mit,declaration.declaration_evidence_ids,[],declaration.evidence_status==='COMPLETE');
  if(new Set(licenses.map((m:MaterialObservation)=>m.source_sha256)).size>1)add('BOUND_LICENSE_BYTES_CONFLICT',licenses);
  if(notices.length)add('NOTICE_REQUIRES_REVIEW',notices);
  const source=sourceRows.get(row.subject.resource_id);
  if(source&&source.notice_status!=='ABSENT_COMPLETE')add('NOTICE_REQUIRES_REVIEW',[],[],[source.source_observation_id],source.notice_status==='PRESENT_UNREVIEWED');
  if(c.counter_evidence.length!==expectedCounters.length)return fail();
  const consumed=new Set<number>();
  for(const e of c.counter_evidence){
   if(!fields(e,'code material_ids evidence_ids source_observation_ids declaration_evidence_ids evidence_status')
     ||!ids(e.material_ids)||!ids(e.evidence_ids)||!ids(e.declaration_evidence_ids)||!ids(e.source_observation_ids))return fail();
   const index=expectedCounters.findIndex((x,i)=>!consumed.has(i)&&x.code===e.code
     &&sameIds(x.ms.map(m=>m.material_id),e.material_ids)&&sameIds(x.declaration,e.declaration_evidence_ids)&&sameIds(x.source,e.source_observation_ids));
   if(index<0)return fail();
   const expected=expectedCounters[index];consumed.add(index);
   const expectedIds=[...new Set<string>([...expected.ms.flatMap(m=>m.evidence.map(x=>x.evidence_id)),...expected.declaration])];
   const complete=expected.provenance&&!!(expectedIds.length||expected.source.length)&&expectedIds.every(i=>hash(row.evidence_source_hashes[i]));
   if(!sameIds(e.evidence_ids,expectedIds)||e.evidence_status!==(complete?'COMPLETE':'UNKNOWN'))return fail();
  }
  const expectedClauses=c.material_ids.flatMap((i:string)=>materialMap.get(i)!.clauses.map(x=>x.clause_id));
  const expectedEvidence:string[]=[...new Set<string>([...c.material_ids.flatMap((i:string)=>materialMap.get(i)!.evidence.map(x=>x.evidence_id)),...declaration.declaration_evidence_ids,...c.counter_evidence.flatMap((e:ClaimLink['counter_evidence'][number])=>e.evidence_ids)])];
  if(!sameIds(c.clause_ids,expectedClauses)||!sameIds(c.evidence.map((e:EvidenceRef)=>e.evidence_id),expectedEvidence))return fail();
  if(['SUPPORT','RESTRICTION'].includes(c.state)&&(declaration.evidence_status!=='COMPLETE'||declaration.expression!=='MIT'||JSON.stringify(declaration.normalized_ids)!=='["MIT"]'||!c.conditions.length||c.counter_evidence.length||!c.material_ids.some((i:string)=>materialMap.get(i)?.adoption_state==='CONDITIONAL_TEXT_BASIS')||!c.clause_ids.some((i:string)=>clauseMap.get(i)?.kind==='permission')||!c.clause_ids.some((i:string)=>clauseMap.get(i)?.kind==='condition')||!c.evidence.length||c.evidence.some((e:EvidenceRef)=>e.source_sha256===null)||v.source_status!=='CHECKED'||sourceRows.get(row.subject.resource_id)?.notice_status!=='ABSENT_COMPLETE'))return fail();
  pairs.add(pair);claimMap.set(c.claim_id,c);
 }
 const advicePairs=new Set<string>();
 for(const a of v.advice){
  if(!fields(a,'usage subject saved_value state reasons claim_ids conditions limitations'))return fail();
  const row=rowFor(a.subject),pair=JSON.stringify([row?.subject.resource_id,row?.subject.version,a.usage]);
  if(!row||!uses.includes(a.usage)||advicePairs.has(pair)||a.saved_value!==result.usage[a.usage as Use]||!states.includes(a.state)||!list(a.reasons)||!a.reasons.length||!ids(a.claim_ids)||a.claim_ids.length!==1||!list(a.conditions)||!list(a.limitations)||!a.limitations.length)return fail();
  const c=claimMap.get(a.claim_ids[0]);
  if(!c||c.usage!==a.usage||c.subject.resource_id!==row.subject.resource_id||c.state!==a.state||JSON.stringify(c.conditions)!==JSON.stringify(a.conditions)||(a.saved_value===false&&a.state!=='NOT_COVERED')||(a.saved_value===null&&a.state!=='UNKNOWN'&&a.state!=='NOT_COVERED')||(['SUPPORT','RESTRICTION'].includes(a.state)&&a.saved_value!==true))return fail();
  advicePairs.add(pair);
 }
 // Copy before the first await so caller mutation cannot swap previously checked text.
 const snapshot=structuredClone(v) as MaterialClaims;
 if(typeof crypto==='undefined'||!crypto.subtle||typeof crypto.subtle.digest!=='function')return fail();
 for(const m of snapshot.materials)for(const c of m.clauses){
  const raw=new TextEncoder().encode(c.quote);
  if(new TextDecoder('utf-8',{fatal:true}).decode(raw)!==c.quote)return fail();
  const actual=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',raw)),x=>x.toString(16).padStart(2,'0')).join('');
  if(actual!==c.quote_sha256)return fail();
 }
 return snapshot;
}
export async function readMaterialClaims(a:Assessment,result:Result,anchor:DeclarationSnapshot|null|undefined,signal?:AbortSignal){
 const url=`/scans/${encodeURIComponent(a.scan_id)}/assessments/${encodeURIComponent(a.id)}/p2/results/${encodeURIComponent(result.result_id)}/material-claims?assessment_version=${a.version}`;
 const value=await validateMaterialClaims(await request(url,{},signal),result,anchor);
 if(signal?.aborted)throw new DOMException('Aborted','AbortError');
 return value;
}
