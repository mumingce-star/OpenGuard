import type { Assessment } from '../../src/services/assessments';
import type { Binding, Result, Summary, Use } from '../../src/services/p2';
import type { AutomaticReview } from '../../src/services/automaticReview';
import type { Scan } from '../../src/types/domain';

/** SYNTHETIC_TEST_ONLY. These IDs and repeated digest values are fixture identities,
 * not observed production objects, real LICENSE hashes or evidence attestations. */
export const fixtureClass = 'SYNTHETIC_TEST_ONLY';
export const hashes = { facts:'a'.repeat(64), usage:'b'.repeat(64), assessment:'c'.repeat(64), evidence:'d'.repeat(64), r1:'e'.repeat(64), r2:'f'.repeat(64) };
// Prefix plus fixed synthetic UUID shape only; these are not production IDs.
export const TARGET='cmp_10000000-0000-4000-8000-000000000001', PEER='cmp_10000000-0000-4000-8000-000000000002', EVIDENCE='evd_10000000-0000-4000-8000-000000000001';
export const R1='res_test_bound_r1', R2='res_test_bound_r2';
export const ACTION_R1='SYNTHETIC_USAGE：保留本版材料与许可声明，交付前核实选定文件范围。';
export const ACTION_R2='SYNTHETIC_USAGE：保留第二版材料与许可声明，交付前核实新版文件范围。';
export const uses: Use[]=['commercial','modified','distributed','network_service','training','redistributed_assets','source_disclosure'];
// The current backend Assessment GET DTO includes usage_hash. Its frontend base
// type/validator do not require it; the optional extension also represents an
// explicitly tested compatibility DTO without that parent field. No public DTO changes.
export type Bundle={scan:Scan;assessment:Assessment&{usage_hash?:unknown};binding:Binding;result:Result;newer:Result;review:AutomaticReview;summary:Summary};
export function makeFixture():Bundle {
 const usage={commercial:true,modified:false,distributed:false,network_service:null,training:null,redistributed_assets:null,source_disclosure:null};
 const binding:Binding={scan_id:'scn_test_bound_advice',assessment_id:'asm_test_bound_advice',assessment_version:1,registry_revision:1,project_revision:'synthetic-project-revision',facts_hash:hashes.facts,usage_hash:hashes.usage,rule_version:'synthetic-rules/1',assessment_sha256:hashes.assessment};
 const scan:Scan={id:binding.scan_id,mode:'api',project:'SYNTHETIC_TEST_ONLY bound-advice fixture',revision:binding.project_revision,input:'SYNTHETIC_TEST_ONLY: no real repository',createdAt:'2026-10-20T00:00:00Z',finishedAt:'2026-10-20T00:01:00Z',status:'completed',stageIndex:1,stages:['synthetic'],error:null,resources:[
  {id:TARGET,name:'synthetic-alpha',type:'Package',version:'1.2.3',origin:null,license:'MIT',licenseStatus:'review_required',evidenceIds:[EVIDENCE],ecosystem:'npm'},
  {id:PEER,name:'synthetic-peer',type:'Package',version:'4.5.6',origin:null,license:null,licenseStatus:'unknown',evidenceIds:[],ecosystem:'npm'},
 ],risks:[],evidence:[{id:EVIDENCE,kind:'license',label:'SYNTHETIC_TEST_ONLY saved text observation',source:'synthetic-fixture',path:'fixture/alpha/LICENSE',text:'SYNTHETIC_TEST_ONLY license observation. Not a real license.',verificationStatus:'pending'}],completeness:'full',snapshotVersion:'synthetic-bound-advice/1'};
 const assessment:Bundle['assessment']={id:binding.assessment_id,version:1,scan_id:binding.scan_id,formal:false,project_name:scan.project,generated_at:'2026-10-20T00:02:00Z',usage:{preset:'unknown',...usage},usage_hash:binding.usage_hash,summary:'SYNTHETIC_TEST_ONLY parent assessment remains unchanged',ai_status:'not_run',ai_summary:null,dimensions:[],coverage_issues:[],resource_ids:[TARGET,PEER],finding_ids:[],evidence_ids:[EVIDENCE],rule_version:binding.rule_version,model_version:'none',prompt_version:'none',facts_hash:binding.facts_hash,resource_evaluations:[{resource_id:TARGET,name:'synthetic-alpha',finding_ids:[],evidence_ids:[EVIDENCE]},{resource_id:PEER,name:'synthetic-peer',finding_ids:[],evidence_ids:[]}],obligations:[]};
 const resources:Result['resources']=scan.resources.map((r,i)=>({subject:{resource_id:r.id,version:r.version},resource_kind:'component',state:i===0?'candidate':'unknown',verification_state:'candidate_only',scope:'SYNTHETIC_TEST_ONLY limited fixture scope',evidence_ids:i===0?[EVIDENCE]:[],evidence_source_hashes:i===0?{[EVIDENCE]:hashes.evidence}:{},material_ids:[],answer_ids:[],gaps:i===0?['applicability_pending']:['source_missing'],advice:uses.map(u=>({usage:u,saved_value:usage[u],selection:usage[u]===null?'UNKNOWN':usage[u]?'SELECTED':'NOT_SELECTED',state:i===0&&u==='commercial'?'conditional_candidate':usage[u]===false?'not_selected':'unknown',scope:'RESOURCE',conditions:i===0&&u==='commercial'?[ACTION_R1]:[],gaps:['formal_applicability_not_signed','actual_delivery_scope_unconfirmed'],basis_evidence_ids:i===0&&u==='commercial'?[EVIDENCE]:[],rule_ids:i===0&&u==='commercial'?['synthetic-rule/1']:[]})),user_assertions:{},inherited_local_support:false,inherited_support_source:'PARENT_ASSESSMENT_NOT_NEW_VALUE'}));
 const result:Result={schema_version:'openguard-p2-result/1',algorithm_version:'p2-bound-candidate/1',result_id:R1,revision:1,previous_result_id:null,result_sha256:hashes.r1,binding,data_scope:'TEST_ONLY',computation:'DETERMINISTIC_P2B',publication_status:'succeeded',formal_effect:'none',model_calls:0,state:'partial',created_at:'2026-10-20T00:03:00Z',usage,resources,questions:[],material_ids:[],answer_ids:[],recomputed_resource_ids:[TARGET,PEER],reused_resource_ids:[],companion_summary_id:'sum_test_bound_r1'};
 const newer=structuredClone(result);newer.result_id=R2;newer.revision=2;newer.previous_result_id=R1;newer.result_sha256=hashes.r2;newer.companion_summary_id='sum_test_bound_r2';newer.resources[0].advice.find(d=>d.usage==='commercial')!.conditions=[ACTION_R2];
 const review:AutomaticReview={schema_version:'openguard-auto-review/1',rule_version:'npm-full-license-review/1',review_id:'p2auto_'+'1'.repeat(64),result_id:R1,result_sha256:hashes.r1,binding:{...binding},data_scope:'TEST_ONLY',source_profile_sha256:null,source_status:'NOT_CONFIGURED',usage:{...usage},formal_effect:'none',model_calls:0,applicability_review:'NOT_SIGNED',resources:resources.map((r,i)=>({subject:{...r.subject},name:i===0?'synthetic-alpha':'synthetic-peer',license_expression:null,state:'UNAVAILABLE',priority:'manual',artifact_binding:'NOT_ESTABLISHED',conditions:[],reasons:['SYNTHETIC_TEST_ONLY: no configured official npm transport'],evidence_ids:[...r.evidence_ids],source_refs:[],members:[],maintenance_deprecated:false,applicability_review:'NOT_SIGNED'})),summary:{total_resources:2,priority_counts:{routine:0,attention:0,manual:2},state_counts:{CONDITIONAL:0,NONSTANDARD:0,UNAVAILABLE:2,OUTSIDE_NPM:0},source_packages:0,license_materials:0,license_groups:[{license:'UNOBSERVED',count:2}],maintenance_count:0},limitations:['SYNTHETIC_TEST_ONLY; not formal source, applicability or fulfillment']};
 const summary:Summary={summary_id:result.companion_summary_id,result_id:R1,result_revision:1,result_sha256:hashes.r1,binding:{...binding},material_ids:[],answer_ids:[],state:result.state,resource_states:Object.fromEntries(resources.map(r=>[r.subject.resource_id,r.state])),formal_effect:'none',report_kind:'P2_COMPANION_NOT_FORMAL_REPORT'};
 return{scan,assessment,binding,result,newer,review,summary};
}

/** Structure-only raw P0 fragments for the mixed-basis case. They are not
 * frontend Scan fields, a complete ScanRun, a real source, or Service output.
 * These two content hashes are static UTF-8 hashes of the synthetic excerpts. */
export const MIXED_LICENSE_EVIDENCE='evd_10000000-0000-4000-8000-000000000002';
export const MIXED_LICENSE_EXPRESSION='lic_10000000-0000-4000-8000-000000000001';
export const MIXED_SCOPE_TEXT='{"kind":"openguard.scope.v1","license_expression_id":"lic_10000000-0000-4000-8000-000000000001","resource_id":"cmp_10000000-0000-4000-8000-000000000001","scope":"project_code","version":"1.2.3"}';
export const MIXED_LICENSE_TEXT='SYNTHETIC_TEST_ONLY license text; not a real license or attestation.';
export const mixedBasisRawStructure={
 classification:'SYNTHETIC_TEST_ONLY_STRUCTURE_ONLY_NOT_SERVICE_GENERATED',
 is_complete_scan_run:false,
 component:{id:TARGET,name:'synthetic-alpha',version:'1.2.3',ecosystem:'npm',component_type:'library',purl:'pkg:npm/synthetic-alpha@1.2.3',source_url:null,license_expression_id:MIXED_LICENSE_EXPRESSION,evidence_ids:[EVIDENCE],detected_by:['manual'],confidence:1},
 license_expression:{id:MIXED_LICENSE_EXPRESSION,expression:'LicenseRef-SYNTHETIC_TEST_ONLY',normalized_ids:[],source_url:null,evidence_ids:[MIXED_LICENSE_EVIDENCE],confidence:1,verification_status:'pending'},
 evidence:[
  {id:EVIDENCE,kind:'metadata',locator:'SYNTHETIC_TEST_ONLY/scope.json',excerpt:MIXED_SCOPE_TEXT,start_line:null,end_line:null,content_hash:{algorithm:'sha256',value:'c02bfb630afef8964812e842a6d6e09e6b2d41b562448bee2a6f3ffc59744df8'},detected_by:'manual',producer:{type:'human',name:'SYNTHETIC_TEST_ONLY_NO_ACTUAL_REVIEW',version:'fixture/1'},observed_at:'2026-10-20T00:00:00Z',verification_status:'pending'},
  {id:MIXED_LICENSE_EVIDENCE,kind:'license_text',locator:'SYNTHETIC_TEST_ONLY/LICENSE',excerpt:MIXED_LICENSE_TEXT,start_line:null,end_line:null,content_hash:{algorithm:'sha256',value:'03fa464777ca0d65dd03e60b66a3217635226cd51f1fcbf771415a16e9e88128'},detected_by:'manual',producer:{type:'human',name:'SYNTHETIC_TEST_ONLY_NO_ACTUAL_REVIEW',version:'fixture/1'},observed_at:'2026-10-20T00:00:00Z',verification_status:'pending'},
 ],
};
export function applyMixedBasis(f:Bundle){
 const row=f.result.resources[0];
 f.scan.evidence[0]={...f.scan.evidence[0],kind:'code',label:'SYNTHETIC_TEST_ONLY direct scope evidence',text:MIXED_SCOPE_TEXT};
 f.scan.evidence.push({id:MIXED_LICENSE_EVIDENCE,kind:'license',label:'SYNTHETIC_TEST_ONLY indirect LicenseExpression evidence',source:'synthetic-fixture',path:'fixture/alpha/LICENSE',text:MIXED_LICENSE_TEXT,verificationStatus:'pending'});
 f.assessment.evidence_ids.push(MIXED_LICENSE_EVIDENCE);
 row.evidence_ids.push(MIXED_LICENSE_EVIDENCE);
 row.evidence_source_hashes={[EVIDENCE]:'c02bfb630afef8964812e842a6d6e09e6b2d41b562448bee2a6f3ffc59744df8',[MIXED_LICENSE_EVIDENCE]:'03fa464777ca0d65dd03e60b66a3217635226cd51f1fcbf771415a16e9e88128'};
 row.advice.find(d=>d.usage==='commercial')!.basis_evidence_ids.push(MIXED_LICENSE_EVIDENCE);
 // Frontend Resource.evidenceIds remains the direct Component list only.
 // The raw LicenseExpression link is deliberately NOT inserted into Scan DTO.
}
export const zipSourceContext={classification:'SYNTHETIC_TEST_ONLY_SOURCE_CONTEXT_NOT_FRONTEND_DTO',source_type:'zip',project_revision:null,input_digest:'7'.repeat(64),inventory_digest:'8'.repeat(64),limitation:'These raw synthetic digests are not available in the current Scan frontend DTO; null revision alone does not prove ZIP identity.'};
