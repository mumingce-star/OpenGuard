import type { DeclarationSnapshot } from '../types/domain';
import { request } from './scans';
import type { Assessment } from './assessments';
import { sameBinding, type Binding, type Result, type Subject, type Use } from './p2';

export type ClaimState='SUPPORT'|'RESTRICTION'|'UNKNOWN'|'COUNTER_EVIDENCE'|'NOT_COVERED';
export type Clause={clause_id:string;material_id:string;material_sha256:string;kind:string;byte_start:number;byte_end:number;line_start:number;line_end:number;quote:string;quote_sha256:string};
type EvidenceRef={evidence_id:string;source_sha256:string|null};
export type DeclarationObservation={subject:Subject;expression:string;normalized_ids:string[];declaration_evidence_ids:string[];evidence:EvidenceRef[];evidence_status:'COMPLETE'|'UNKNOWN'};
export type MaterialObservation={material_id:string;subject:Subject;source_sha256:string;byte_count:number;filename:string;parse_state:'MATCHED_MIT'|'MATCHED_APACHE_2_0'|'NOTICE_OBSERVED'|'UNSUPPORTED'|'FAILED';parse_reason:string;binding_state:'BOUND_TO_SAVED_RESULT';adoption_state:'OBSERVATION_ONLY'|'CONDITIONAL_TEXT_BASIS';declared_spdx:string;text_license:'MIT'|'Apache-2.0'|'UNKNOWN';license_version:'2.0'|null;version_scope:'RESOURCE_VERSION_NOT_LICENSE_VERSION'|'LICENSE_VERSION_AND_RESOURCE_VERSION';role:'root_package'|'dependency'|'unknown';role_state:'observed'|'inferred'|'unknown';role_basis_evidence_ids:string[];role_conflicts:string[];source_binding:'PINNED_RELEASE_MATCH'|'NOT_ESTABLISHED';source_profile_sha256:string|null;evidence:EvidenceRef[];clauses:Clause[]};
export type SourceObservation={source_observation_id:string;subject:Subject;source_profile_sha256:string;archive_sha256:string;notice_status:'ABSENT_COMPLETE'|'PRESENT_UNREVIEWED'|'INCOMPLETE'|'INVALID';reason:string;member_count:number;enumeration_complete:boolean;notices:{path:string;bytes:number;sha256:string|null;inspection_state:'EXTRACTED_UNREVIEWED'|'UNSUPPORTED_FORMAT'|'PARSE_FAILED'|'LIMIT_EXCEEDED'|'INVALID_TYPE'|'READ_FAILED'}[]};
export type ClaimLink={claim_id:string;usage:Use;subject:Subject;material_ids:string[];evidence:EvidenceRef[];clause_ids:string[];conditions:string[];counter_evidence:{code:string;material_ids:string[];evidence_ids:string[];source_observation_ids:string[];declaration_evidence_ids:string[];evidence_status:'COMPLETE'|'UNKNOWN'}[];state:ClaimState;formal_effect:'none'};
export type PurposeAdvice={usage:Use;subject:Subject;saved_value:boolean|null;state:ClaimState;reasons:string[];claim_ids:string[];conditions:string[];limitations:string[]};
export type ClaimDelta={usage:Use;subject:Subject;previous_claim_id:string;current_claim_id:string;previous_state:ClaimState;current_state:ClaimState;previous_reasons:string[];current_reasons:string[];trigger_material_ids:string[];trigger_answer_ids:string[]};
export type IncrementalImpact={mode:'INITIAL_RESULT'|'INCREMENTAL_DERIVED';previous_result_id:string|null;previous_revision:number|null;previous_view_id:string|null;affected_resource_ids:string[];unchanged_resource_ids:string[];recomputed_claim_ids:string[];reused_claim_ids:string[];added_material_ids:string[];added_answer_ids:string[];changed_claims:ClaimDelta[];unchanged_claims_verified:true};
export type MaterialClaims={schema_version:'openguard-material-claims/4';rule_version:'mit-apache2-bound-claim/4';view_id:string;result_id:string;result_sha256:string;revision:number;previous_result_id:string|null;binding:Binding;data_scope:'OWNER'|'TEST_ONLY';source_status:'CHECKED'|'NOT_CONFIGURED';source_profile_sha256:string|null;materials:MaterialObservation[];declaration_observations:DeclarationObservation[];source_observations:SourceObservation[];claims:ClaimLink[];advice:PurposeAdvice[];incremental_impact:IncrementalImpact;formal_effect:'none';applicability_review:'NOT_SIGNED';model_calls:0};
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
const sameIds=(a:string[],b:string[])=>{
 const set=new Set(b);
 return a.length===b.length&&new Set(a).size===a.length&&set.size===b.length&&a.every(x=>set.has(x));
};
const sameList=(a:string[],b:string[])=>a.length===b.length&&a.every((x,i)=>x===b[i]);
const licensedText=(m:MaterialObservation)=>m.parse_state==='MATCHED_MIT'?'MIT':m.parse_state==='MATCHED_APACHE_2_0'?'Apache-2.0':'UNKNOWN';
const single=(d:DeclarationObservation,license:string)=>d.expression===license&&sameList(d.normalized_ids,[license]);
const roleConflicts=new Set(['dependency_declaration_conflict','lock_version_conflict','lock_root_mismatch','contradictory_role_evidence']);
const apacheProfile:[kind:string,heading:RegExp][]=[
 ['license_identifier',/^\s*Apache License\s+Version 2\.0, January 2004/],
 ['permission',/^\s*2\. Grant of Copyright License\./],
 ['permission',/^\s*3\. Grant of Patent License\./],
 ['condition',/^\s*\(a\) /],['condition',/^\s*\(b\) /],['condition',/^\s*\(c\) /],['condition',/^\s*\(d\) /],
 ['warranty',/^\s*7\. Disclaimer of Warranty\./],
];
const hasApacheCondition=(conditions:string[],part:string)=>conditions.some(condition=>condition.includes('§4('+part+')'));
const declarationFail=():never=>{throw Error('扫描声明来源无法与本版证据核对，已停止展示新版用途建议；旧结果保持可读。');};
const fail=():never=>{throw Error('材料与用途建议未通过当前结果的绑定核对，已停止展示。');};

function verifyImpact(impact:unknown,viewId:string,result:Result,claims:Map<string,ClaimLink>,adviceByClaim:Map<string,PurposeAdvice>):boolean {
 if(!obj(impact)||!fields(impact,'mode previous_result_id previous_revision previous_view_id affected_resource_ids unchanged_resource_ids recomputed_claim_ids reused_claim_ids added_material_ids added_answer_ids changed_claims unchanged_claims_verified'))return false;
 const initial=result.revision===1;
 if(impact.mode!==(initial?'INITIAL_RESULT':'INCREMENTAL_DERIVED')||impact.previous_result_id!==result.previous_result_id
   ||impact.unchanged_claims_verified!==true||!Array.isArray(impact.changed_claims)||impact.changed_claims.length>claims.size
   ||!ids(impact.affected_resource_ids)||!ids(impact.unchanged_resource_ids)
   ||!sameList(impact.affected_resource_ids,result.recomputed_resource_ids)||!sameList(impact.unchanged_resource_ids,result.reused_resource_ids)
   ||!ids(impact.recomputed_claim_ids)||!ids(impact.reused_claim_ids)||!ids(impact.added_material_ids)||!ids(impact.added_answer_ids))return false;
 const affected=new Set(impact.affected_resource_ids),unchanged=new Set(impact.unchanged_resource_ids);
 if(impact.affected_resource_ids.some(resource=>unchanged.has(resource)))return false;
 const recomputed:string[]=[],reused:string[]=[];
 const rows=new Map(result.resources.map(row=>[row.subject.resource_id,row]));
 for(const claim of claims.values()){
  if(affected.has(claim.subject.resource_id))recomputed.push(claim.claim_id);
  else if(unchanged.has(claim.subject.resource_id))reused.push(claim.claim_id);
  else return false;
 }
 if(!sameIds(impact.recomputed_claim_ids,recomputed)||!sameIds(impact.reused_claim_ids,reused))return false;
 if(initial)return impact.previous_result_id===null&&impact.previous_revision===null&&impact.previous_view_id===null
   &&!reused.length&&!impact.changed_claims.length&&!impact.added_material_ids.length&&!impact.added_answer_ids.length;
 if(!id(impact.previous_result_id)||impact.previous_result_id===result.result_id||impact.previous_revision!==result.revision-1
   ||!id(impact.previous_view_id)||impact.previous_view_id===viewId)return false;
 const affectedRows=result.resources.filter(row=>affected.has(row.subject.resource_id));
 const affectedMaterials=new Set(affectedRows.flatMap(row=>row.material_ids));
 const affectedAnswers=new Set(affectedRows.flatMap(row=>row.answer_ids));
 if(!impact.added_material_ids.every(i=>affectedMaterials.has(i)&&result.material_ids.includes(i))
   ||!impact.added_answer_ids.every(i=>affectedAnswers.has(i)&&result.answer_ids.includes(i)))return false;
 const newMaterials=new Set(impact.added_material_ids),newAnswers=new Set(impact.added_answer_ids);
 const touched=result.resources.filter(row=>row.material_ids.some(id=>newMaterials.has(id))
   ||row.answer_ids.some(id=>newAnswers.has(id))).map(row=>row.subject.resource_id);
 if(!touched.length||!sameIds(touched,impact.affected_resource_ids))return false;
 const seenCurrent=new Set<string>(),seenPrior=new Set<string>();
 for(const delta of impact.changed_claims){
  if(!fields(delta,'usage subject previous_claim_id current_claim_id previous_state current_state previous_reasons current_reasons trigger_material_ids trigger_answer_ids')
    ||!fields(delta.subject,'resource_id version')||!id(delta.current_claim_id)||!id(delta.previous_claim_id)
    ||seenCurrent.has(delta.current_claim_id)||seenPrior.has(delta.previous_claim_id)||claims.has(delta.previous_claim_id))return false;
  const claim=claims.get(delta.current_claim_id),advice=adviceByClaim.get(delta.current_claim_id);
  const row=rows.get(delta.subject.resource_id);
  if(!row||!claim||!advice||!affected.has(row.subject.resource_id)
    ||claim.subject.resource_id!==row.subject.resource_id||delta.subject.version!==claim.subject.version||delta.usage!==claim.usage
    ||delta.current_state!==advice.state||!states.includes(delta.previous_state)
    ||!list(delta.previous_reasons)||!delta.previous_reasons.length||!list(delta.current_reasons)||!sameList(delta.current_reasons,advice.reasons)
    ||(delta.previous_state===delta.current_state&&sameList(delta.previous_reasons,delta.current_reasons))
    ||!ids(delta.trigger_material_ids)||!sameIds(delta.trigger_material_ids,impact.added_material_ids.filter(id=>row.material_ids.includes(id)))
    ||!ids(delta.trigger_answer_ids)||!sameIds(delta.trigger_answer_ids,impact.added_answer_ids.filter(id=>row.answer_ids.includes(id))))return false;
  seenCurrent.add(delta.current_claim_id);seenPrior.add(delta.previous_claim_id);
 }
 return true;
}

// Verify claims against the saved result and scan anchor, and recompute each displayed quote hash.
export async function validateMaterialClaims(v:unknown,result:Result,anchor:DeclarationSnapshot|null|undefined):Promise<MaterialClaims> {
 if(!fields(v,'schema_version rule_version view_id result_id result_sha256 revision previous_result_id binding data_scope source_status source_profile_sha256 materials declaration_observations source_observations claims advice incremental_impact formal_effect applicability_review model_calls')||!obj(v))return fail();
 if(v.schema_version!=='openguard-material-claims/4'||v.rule_version!=='mit-apache2-bound-claim/4'||!id(v.view_id)||v.result_id!==result.result_id||v.result_sha256!==result.result_sha256||v.revision!==result.revision||v.previous_result_id!==result.previous_result_id||!fields(v.binding,Object.keys(result.binding).join(' '))||!sameBinding(v.binding as Binding,result.binding)||v.data_scope!==result.data_scope||v.formal_effect!=='none'||v.model_calls!==0||v.applicability_review!=='NOT_SIGNED'||!['CHECKED','NOT_CONFIGURED'].includes(v.source_status)||!(v.source_profile_sha256===null||hash(v.source_profile_sha256))||(v.source_status==='CHECKED')!==(v.source_profile_sha256!==null)||!Array.isArray(v.materials)||v.materials.length>20||!Array.isArray(v.source_observations)||v.source_observations.length>1000||!Array.isArray(v.claims)||!Array.isArray(v.advice)||v.claims.length!==result.resources.length*3||v.advice.length!==result.resources.length*3)return fail();
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
 const rolesByResource=new Map<string,string>();
 for(const m of v.materials){
  if(!fields(m,'material_id subject source_sha256 byte_count filename parse_state parse_reason binding_state adoption_state declared_spdx text_license license_version version_scope role role_state role_basis_evidence_ids role_conflicts source_binding source_profile_sha256 evidence clauses'))return fail();
  const row=rowFor(m.subject);
  if(!row||!id(m.material_id)||materialMap.has(m.material_id)||!row.material_ids.includes(m.material_id)||!hash(m.source_sha256)||!integer(m.byte_count)||m.byte_count<1||m.byte_count>65536||!text(m.filename)||!/^(?:LICEN[CS]E|NOTICE)(?:\.(?:txt|md|rst))?$/i.test(m.filename)||!['MATCHED_MIT','MATCHED_APACHE_2_0','NOTICE_OBSERVED','UNSUPPORTED','FAILED'].includes(m.parse_state)||!text(m.parse_reason)||m.binding_state!=='BOUND_TO_SAVED_RESULT'||!['OBSERVATION_ONLY','CONDITIONAL_TEXT_BASIS'].includes(m.adoption_state)||!text(m.declared_spdx)||!['root_package','dependency','unknown'].includes(m.role)||!ids(m.role_basis_evidence_ids)||!m.role_basis_evidence_ids.every((e:string)=>row.evidence_ids.includes(e)&&hash(row.evidence_source_hashes[e]))||!ids(m.role_conflicts)||!m.role_conflicts.every((code:string)=>roleConflicts.has(code))||!['PINNED_RELEASE_MATCH','NOT_ESTABLISHED'].includes(m.source_binding)||m.source_profile_sha256!==v.source_profile_sha256||!evidenceOK(m.evidence,row)||!m.evidence.length||!Array.isArray(m.clauses)||m.clauses.length>10)return fail();
  const resource=row.subject.resource_id,declaration=declarationMap.get(resource)!;
  const textLicense=licensedText(m as MaterialObservation),apache=textLicense==='Apache-2.0',notice=m.parse_state==='NOTICE_OBSERVED';
  if(m.declared_spdx!==declaration.expression||m.text_license!==textLicense
    ||m.license_version!==(apache?'2.0':null)
    ||m.version_scope!==(apache?'LICENSE_VERSION_AND_RESOURCE_VERSION':'RESOURCE_VERSION_NOT_LICENSE_VERSION'))return fail();
  if(m.role==='unknown'?(m.role_state!=='unknown'||m.role_basis_evidence_ids.length!==0)
    :m.role_conflicts.length!==0||!m.role_basis_evidence_ids.length||
      (m.role==='root_package'?m.role_state!=='inferred'||m.role_basis_evidence_ids.length<2:!['observed','inferred'].includes(m.role_state)))return fail();
  const roleSignature=JSON.stringify([m.role,m.role_state,m.role_basis_evidence_ids,m.role_conflicts]);
  if(rolesByResource.has(resource)&&rolesByResource.get(resource)!==roleSignature)return fail();
  rolesByResource.set(resource,roleSignature);
  if(m.adoption_state==='CONDITIONAL_TEXT_BASIS'&&(declaration.evidence_status!=='COMPLETE'||textLicense==='UNKNOWN'||!single(declaration,textLicense)
    ||m.source_binding!=='PINNED_RELEASE_MATCH'||v.source_status!=='CHECKED'||sourceRows.get(resource)?.notice_status!=='ABSENT_COMPLETE'))return fail();
  if((textLicense!=='UNKNOWN'&&!/^LICEN[CS]E(?:\.|$)/i.test(m.filename))||(notice&&!/^NOTICE(?:\.|$)/i.test(m.filename)))return fail();
  if(textLicense==='UNKNOWN'&&!notice&&m.clauses.length)return fail();
  let lastByte=0,lastLine=1;
  for(const c of m.clauses){
   if(!fields(c,'clause_id material_id material_sha256 kind byte_start byte_end line_start line_end quote quote_sha256')||!id(c.clause_id)||clauseMap.has(c.clause_id)||c.material_id!==m.material_id||c.material_sha256!==m.source_sha256||!['license_identifier','copyright','permission','condition','warranty','notice'].includes(c.kind)||!integer(c.byte_start)||!integer(c.byte_end)||c.byte_start<0||c.byte_end<=c.byte_start||c.byte_end>m.byte_count||!integer(c.line_start)||!integer(c.line_end)||c.line_start<1||c.line_end<c.line_start||!text(c.quote)||new TextEncoder().encode(c.quote).length!==c.byte_end-c.byte_start||!hash(c.quote_sha256))return fail();
   if((apache||notice)&&(c.byte_start<lastByte||c.line_start<lastLine||c.line_end-c.line_start!==c.quote.slice(0,-1).split('\n').length-1))return fail();
   lastByte=c.byte_end;lastLine=c.line_end;
   clauseMap.set(c.clause_id,c);
  }
  if(m.parse_state==='MATCHED_MIT'&&!sameIds(m.clauses.map((c:Clause)=>c.kind),['license_identifier','copyright','permission','condition','warranty']))return fail();
  if(apache&&(m.clauses.length!==apacheProfile.length||!apacheProfile.every(([kind,heading],i)=>m.clauses[i].kind===kind&&heading.test(m.clauses[i].quote))))return fail();
  if(notice&&(m.clauses.length!==1||m.clauses[0].kind!=='notice'||m.clauses[0].byte_start!==0
    ||m.clauses[0].byte_end!==m.byte_count||m.clauses[0].line_start!==1||m.clauses[0].quote_sha256!==m.source_sha256))return fail();
  materialMap.set(m.material_id,m);
 }
 if(!sameIds([...materialMap.keys()],result.material_ids))return fail();
 const claimMap=new Map<string,ClaimLink>(),pairs=new Set<string>(),matchedNoticeRows=new Set<string>();
 for(const c of v.claims){
  if(!fields(c,'claim_id usage subject material_ids evidence clause_ids conditions counter_evidence state formal_effect'))return fail();
  const row=rowFor(c.subject),pair=JSON.stringify([row?.subject.resource_id,row?.subject.version,c.usage]);
  if(!row||!id(c.claim_id)||claimMap.has(c.claim_id)||pairs.has(pair)||!uses.includes(c.usage)||!states.includes(c.state)||c.formal_effect!=='none'||!ids(c.material_ids)||!c.material_ids.every((i:string)=>materialMap.get(i)?.subject.resource_id===row.subject.resource_id)||!sameIds(c.material_ids,row.material_ids)||!evidenceOK(c.evidence,row)||!ids(c.clause_ids)||!c.clause_ids.every((i:string)=>c.material_ids.includes(clauseMap.get(i)?.material_id))||!list(c.conditions)||!Array.isArray(c.counter_evidence))return fail();
  const declaration=declarationMap.get(row.subject.resource_id)!;
  const allMaterials=c.material_ids.map((i:string)=>materialMap.get(i)!);
  const licenses=allMaterials.filter((m:MaterialObservation)=>/^LICEN[CS]E(?:\.|$)/i.test(m.filename));
  const notices=allMaterials.filter((m:MaterialObservation)=>m.parse_state==='NOTICE_OBSERVED');
  const multi=[' AND ',' OR ',' WITH '].some(t=>declaration.expression.includes(t));
  const expectedCounters:{code:string;ms:MaterialObservation[];declaration:string[];source:string[];provenance:boolean}[]=[];
  const add=(code:string,ms:MaterialObservation[],ds:string[]=[],source:string[]=[],provenance=true)=>expectedCounters.push({code,ms,declaration:ds,source,provenance});
  if(['MIT','Apache-2.0'].includes(declaration.expression)&&!single(declaration,declaration.expression))
    add('SPDX_NORMALIZATION_CONFLICT',[],declaration.declaration_evidence_ids,[],declaration.evidence_status==='COMPLETE');
  const conflicting=licenses.filter((m:MaterialObservation)=>m.text_license!=='UNKNOWN'&&m.text_license!==declaration.expression);
  if(!['UNOBSERVED','CONFLICT_OR_UNSUPPORTED'].includes(declaration.expression)&&!multi&&conflicting.length)
    add('SPDX_TEXT_CONFLICT',conflicting,declaration.declaration_evidence_ids,[],declaration.evidence_status==='COMPLETE');
  if(new Set(licenses.map((m:MaterialObservation)=>m.source_sha256)).size>1)add('BOUND_LICENSE_BYTES_CONFLICT',licenses);
  if(notices.length)add('NOTICE_REQUIRES_REVIEW',notices);
  const source=sourceRows.get(row.subject.resource_id);
  if(source&&source.notice_status!=='ABSENT_COMPLETE')add('NOTICE_REQUIRES_REVIEW',[],[],[source.source_observation_id],source.notice_status==='PRESENT_UNREVIEWED');
  if(declaration.expression==='Apache-2.0'&&source?.notice_status==='PRESENT_UNREVIEWED'&&notices.length){
   const unusable=notices.filter((m:MaterialObservation)=>!source.notices.some(n=>n.sha256===m.source_sha256&&n.bytes===m.byte_count));
   if(unusable.length)add('BOUND_NOTICE_BYTES_CONFLICT',unusable,[],[source.source_observation_id]);
   else matchedNoticeRows.add(row.subject.resource_id);
  }
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
  if(['SUPPORT','RESTRICTION'].includes(c.state)){
   const license=declaration.expression;
   if(row.resource_kind!=='component'||!['MIT','Apache-2.0'].includes(license)||declaration.evidence_status!=='COMPLETE'||!single(declaration,license)
     ||!c.conditions.length||c.counter_evidence.length||!licenses.some((m:MaterialObservation)=>m.text_license===license&&m.adoption_state==='CONDITIONAL_TEXT_BASIS')
     ||!c.clause_ids.some((i:string)=>clauseMap.get(i)?.kind==='permission')||!c.clause_ids.some((i:string)=>clauseMap.get(i)?.kind==='condition')
     ||!c.evidence.length||c.evidence.some((e:EvidenceRef)=>e.source_sha256===null)||v.source_status!=='CHECKED'||source?.notice_status!=='ABSENT_COMPLETE')return fail();
   if(c.state==='SUPPORT'&&license==='Apache-2.0'&&(!hasApacheCondition(c.conditions,'a')||!hasApacheCondition(c.conditions,'c')
     ||(result.usage.modified===true&&!hasApacheCondition(c.conditions,'b'))))return fail();
  }
  pairs.add(pair);claimMap.set(c.claim_id,c);
 }
 const advicePairs=new Set<string>(),adviceByClaim=new Map<string,PurposeAdvice>();
 for(const a of v.advice){
  if(!fields(a,'usage subject saved_value state reasons claim_ids conditions limitations'))return fail();
  const row=rowFor(a.subject),pair=JSON.stringify([row?.subject.resource_id,row?.subject.version,a.usage]);
  if(!row||!uses.includes(a.usage)||advicePairs.has(pair)||a.saved_value!==result.usage[a.usage as Use]||!states.includes(a.state)||!list(a.reasons)||!a.reasons.length||!ids(a.claim_ids)||a.claim_ids.length!==1||!list(a.conditions)||!list(a.limitations)||!a.limitations.length)return fail();
  const c=claimMap.get(a.claim_ids[0]);
  if(!c||c.usage!==a.usage||c.subject.resource_id!==row.subject.resource_id||c.state!==a.state||JSON.stringify(c.conditions)!==JSON.stringify(a.conditions)||(a.saved_value===false&&a.state!=='NOT_COVERED')||(a.saved_value===null&&a.state!=='UNKNOWN'&&a.state!=='NOT_COVERED')||(['SUPPORT','RESTRICTION'].includes(a.state)&&a.saved_value!==true))return fail();
  const selected=a.saved_value===true&&row.resource_kind==='component';
  if(selected&&c.counter_evidence.some(e=>e.code==='BOUND_NOTICE_BYTES_CONFLICT')
   &&(a.state!=='COUNTER_EVIDENCE'||!a.reasons.includes('BOUND_NOTICE_BYTES_CONFLICT')))return fail();
  const matched=selected&&matchedNoticeRows.has(row.subject.resource_id)&&c.counter_evidence.every(e=>e.code==='NOTICE_REQUIRES_REVIEW');
  if(a.reasons.includes('NOTICE_MATCHED_REQUIRES_HUMAN_OBLIGATION_REVIEW')!==matched
   ||(matched&&(a.state!=='UNKNOWN'||!hasApacheCondition(a.conditions,'d'))))return fail();
  advicePairs.add(pair);
  adviceByClaim.set(c.claim_id,a as PurposeAdvice);
 }
 if(!verifyImpact(v.incremental_impact,v.view_id,result,claimMap,adviceByClaim))return fail();
 // Copy before the first await so caller mutation cannot swap previously checked text.
 const snapshot=structuredClone(v) as MaterialClaims;
 if(typeof crypto==='undefined'||!crypto.subtle||typeof crypto.subtle.digest!=='function')return fail();
 for(const m of snapshot.materials)for(const c of m.clauses){
  const raw=new TextEncoder().encode(c.quote);
  if(new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(raw)!==c.quote)return fail();
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
