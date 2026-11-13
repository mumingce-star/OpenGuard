import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { P2Workbench } from '../../src/components/P2Workbench';
import { readExactAssessment } from '../../src/services/assessments';
import { selectBoundSavedAdvice, validateSummary } from '../../src/services/p2';
import { makeFixture, applyMixedBasis, mixedBasisRawStructure, zipSourceContext, ACTION_R1, ACTION_R2, EVIDENCE, MIXED_LICENSE_EVIDENCE, R1, R2, type Bundle } from './fixture';
import { createClosedTransport, closedTransportSelfcheck, type RequestRecord, type TransportOptions } from './transport';

/** SYNTHETIC_TEST_ONLY component/real-service test source; no live backend. */
type CaseRecord={name:string;status:'passed'|'failed';error:string|null;requests:RequestRecord[]};
type SuiteResult={classification:'SYNTHETIC_TEST_ONLY_COMPONENT_WITH_REAL_SERVICE_AND_CLOSED_TRANSPORT';status:'NOT_RUN'|'running'|'passed'|'failed';started_at:string|null;finished_at:string|null;cases:CaseRecord[];transport_selfcheck:unknown|null};
declare global {interface Window{__BOUND_ADVICE_TEST_RESULT__:SuiteResult;runBoundAdviceSuite:()=>Promise<SuiteResult>;}}
const report:SuiteResult={classification:'SYNTHETIC_TEST_ONLY_COMPONENT_WITH_REAL_SERVICE_AND_CLOSED_TRANSPORT',status:'NOT_RUN',started_at:null,finished_at:null,cases:[],transport_selfcheck:null};
window.__BOUND_ADVICE_TEST_RESULT__=report;
function requireThat(value:unknown,message:string):asserts value {if(!value)throw Error(message);}
function mainCard(host:HTMLElement){const card=host.querySelector<HTMLElement>('[data-bound-advice-maincard]');requireThat(card,'Missing bound Advice main-card region');requireThat(!card.closest('details'),'Saved Advice remains in a collapsed disclosure');return card;}
function containsSaved(card:HTMLElement,action=ACTION_R1){return Array.from(card.querySelectorAll('li,p')).some(n=>n.textContent===action);}
function requireNeutral(host:HTMLElement){const card=mainCard(host);requireThat(!!card.querySelector('[data-bound-advice-neutral]'),'Missing explicit failure-closed next action');requireThat(!card.querySelector('[data-bound-advice-resource]'),'Unbound condition was rendered as a supported resource');return card;}
async function settle(predicate:()=>boolean,label:string){for(let i=0;i<40;i++){await act(async()=>{await new Promise<void>(resolve=>setTimeout(resolve,0));});if(predicate())return;}throw Error('Did not settle: '+label);}
function cloneReviewFor(f:Bundle){f.review.result_id=f.result.result_id;f.review.result_sha256=f.result.result_sha256;f.review.usage={...f.result.usage};f.review.binding={...f.binding};f.review.resources=f.review.resources.map((row,i)=>({...row,subject:{...f.result.resources[i].subject},evidence_ids:[...f.result.resources[i].evidence_ids]}));}
async function mounted(name:string,mutate:(f:Bundle)=>void,check:(host:HTMLElement,f:Bundle,requests:RequestRecord[])=>void,options:TransportOptions={},expectedResult:'present'|'rejected'='present'){
 const f=makeFixture();mutate(f);cloneReviewFor(f);
 const transport=createClosedTransport(f,options),originalFetch=window.fetch,originalHref=window.location.href;
 const host=document.createElement('div');host.dataset.testCase=name;document.querySelector('#test-host')!.append(host);
 const root=createRoot(host);window.fetch=transport.fetch;
 const query=new URLSearchParams({mode:'api',assessment_id:f.assessment.id,assessment_version:String(f.assessment.version),p2_result:f.result.result_id});
 window.history.replaceState(null,'',`/app/scans/${f.scan.id}/assessment?${query}`);
 let error:unknown;
 try{
  const hadParentHash=Object.prototype.hasOwnProperty.call(f.assessment,'usage_hash'),parentHash=f.assessment.usage_hash;
  // Reach the actual current Assessment service and runtime validator. The
  // transport supplies a serialized synthetic DTO, not a hand-passed component prop.
  f.assessment=await readExactAssessment(f.assessment.scan_id,f.assessment.id) as Bundle['assessment'];
  requireThat(Object.prototype.hasOwnProperty.call(f.assessment,'usage_hash')===hadParentHash,'Assessment service fabricated or discarded parent Hash field');
  if(hadParentHash)requireThat(f.assessment.usage_hash===parentHash,'Assessment service changed parent usage_hash');
  await act(async()=>{root.render(<P2Workbench scan={f.scan} assessment={f.assessment} readOnly={true}/>);});
  if(expectedResult==='present'){
   await settle(()=>!!host.querySelector('[data-bound-advice-maincard]'),'bound Advice main card');
   await settle(()=>transport.ledger.some(r=>r.url.includes('/automatic-review?'))&&transport.ledger.some(r=>r.url.includes('/preliminary-advice?')),'both independent derived reads');
   await settle(()=>!!host.querySelector('.auto-review-error,.auto-assessment'),'automatic projection validator/component settled');
   const derived=host.querySelector<HTMLElement>('.auto-review-error,.auto-assessment')!;
   const disclosure=derived.closest('details');requireThat(!!disclosure&&!disclosure.open,'Independent derived view escaped its closed disclosure');
  }else{
   await settle(()=>!!host.querySelector('.p2-message.p2-error'),'existing Binding/Result validator rejection');
   requireThat(!host.querySelector('[data-bound-advice-maincard]'),'Invalid fixed response reached saved Advice main card');
  }
  requireThat(transport.ledger.filter(r=>new URL(r.url).pathname===`/api/v1/scans/${encodeURIComponent(f.assessment.scan_id)}/assessments/${encodeURIComponent(f.assessment.id)}`).length===1,'Exact Assessment service did not consume exactly one approved synthetic DTO GET');
  check(host,f,transport.ledger);
  requireThat(transport.nonGet.length===0,'Passive readOnly render attempted a business write');
  requireThat(transport.unknown.length===0,'Application attempted an unknown or external route');
  requireThat(transport.ledger.every(r=>r.method==='GET'),'Application has a non-GET request');
 }catch(e){error=e;}
 finally{await act(async()=>{root.unmount();});window.fetch=originalFetch;window.history.replaceState(null,'',originalHref);host.remove();}
 const row:CaseRecord={name,status:error?'failed':'passed',error:error instanceof Error?error.message:error?String(error):null,requests:transport.ledger};report.cases.push(row);
 if(error)throw error;
}

export async function runBoundAdviceSuite():Promise<SuiteResult>{
 if(report.status!=='NOT_RUN')throw Error('This frozen suite may be started once per fresh test page');
 report.status='running';report.started_at=new Date().toISOString();
 (globalThis as typeof globalThis&{IS_REACT_ACT_ENVIRONMENT:boolean}).IS_REACT_ACT_ENVIRONMENT=true;
 try{
  report.transport_selfcheck=await closedTransportSelfcheck(makeFixture());
  await mounted('valid saved conditional Advice preserves exact saved text and finite binding',()=>{},(host,f,requests)=>{
   const card=mainCard(host);requireThat(containsSaved(card),'Exact saved condition not shown in main card');
   requireThat(card.textContent?.includes('synthetic-alpha'),'Exact component not named');requireThat(card.textContent?.includes('1.2.3'),'Exact component version not displayed');
   requireThat(!card.textContent?.includes(ACTION_R2),'Newer Result condition leaked into fixed r1');
   requireThat(host.textContent?.includes('独立结果 r1'),'Saved Result identity unavailable');
   requireThat(requests.some(r=>r.url.includes('/results/'+R1+'?')),'Real fixed-result service read not reached');
   requireThat(!requests.some(r=>r.url.includes('/results/'+R2+'?')),'Fixed r1 silently replaced by Index head');
   requireThat(!requests.some(r=>r.url.includes('/summary')),'Main-card condition reconstructed from Summary');
   requireThat(card.dataset.resultId===R1&&card.dataset.resultRevision==='1','Main-card saved Result identity mismatch');
   requireThat(f.result.resources[0].advice[0].conditions[0]===ACTION_R1,'Frozen saved condition changed');
   requireThat(card.querySelector('[data-bound-advice-assurance="PARENT_FIELD_MATCH"]'),'Current DTO parent usage_hash match assurance missing');
   const selected=selectBoundSavedAdvice(f.assessment,f.binding,f.result,f.scan);
   requireThat(selected.usage_hash_assurance==='PARENT_FIELD_MATCH'&&selected.rows.length===1,'Real selector did not retain actual parent-field match');
  });
  for(const [name,mutate] of [
   ['missing direct Component Evidence',(f:Bundle)=>{f.scan.resources[0].evidenceIds=[];}],
   ['foreign Component resource',(f:Bundle)=>{f.scan.resources[0].id='cmp_test_unrelated';}],
   ['wrong Component exact version',(f:Bundle)=>{f.scan.resources[0].version='9.9.9';}],
   ['unknown current usage',(f:Bundle)=>{f.assessment.usage.commercial=null;f.result.usage.commercial=null;for(const row of f.result.resources){const d=row.advice.find(d=>d.usage==='commercial')!;d.saved_value=null;d.selection='UNKNOWN';d.state='unknown';}}],
   ['missing recorded source hash',(f:Bundle)=>{delete f.result.resources[0].evidence_source_hashes[EVIDENCE];}],
   ['basis Evidence does not directly bind to Component',(f:Bundle)=>{f.scan.resources[0].evidenceIds=['evd_test_other_direct'];}],
   ['same-named http-server material without real Scan binding stays unconfirmed',(f:Bundle)=>{f.scan.resources[0].name='http-server';f.scan.resources[0].version='14.1.2';f.result.resources[0].subject.version='14.1.2';f.scan.resources[0].evidenceIds=[];}],
  ] as const){await mounted(name,mutate,(host)=>{const card=requireNeutral(host);requireThat(!containsSaved(card),'Unbound saved condition displayed as a supported candidate');requireThat(!card.textContent?.includes(ACTION_R1),'Unbound condition leaked into main card');requireThat(!!card.textContent?.trim(),'Failure-closed region omitted all next-step guidance');requireThat(!card.textContent?.includes('已确认允许商业使用'),'Affirmative permission was fabricated');});}
  await mounted('compatibility Assessment without usage_hash uses Binding and all seven values only',f=>{delete f.assessment.usage_hash;},(host,f)=>{
   const card=mainCard(host);requireThat(containsSaved(card),'Legal compatibility DTO without usage_hash always neutral-closed');
   requireThat(card.querySelector('[data-bound-advice-assurance="BINDING_AND_USAGE_VALUES_ONLY"]'),'Lower-assurance binding explanation missing');
   requireThat(card.textContent?.includes('未独立重算父用途Hash'),'Missing-parent compatibility was presented as independent Hash authentication');
   const selected=selectBoundSavedAdvice(f.assessment,f.binding,f.result,f.scan);
   requireThat(selected.rows.length===1&&selected.usage_hash_assurance==='BINDING_AND_USAGE_VALUES_ONLY','Real selector did not distinguish parent field absence');
  });
  for(const [name,mutate] of [
   ['present mismatched parent usage_hash',(f:Bundle)=>{f.assessment.usage_hash='0'.repeat(64);}],
   ['present malformed parent usage_hash',(f:Bundle)=>{f.assessment.usage_hash='not-a-sha256';}],
   ['present null parent usage_hash is not absent',(f:Bundle)=>{f.assessment.usage_hash=null;}],
   ['fixed Result has another nine-field Binding',(f:Bundle)=>{f.result.binding={...f.binding,usage_hash:'0'.repeat(64)};}],
   ['saved Result seven-use values disagree with parent',(f:Bundle)=>{f.result.usage.modified=true;const d=f.result.resources[0].advice.find(d=>d.usage==='modified')!;d.saved_value=true;d.selection='SELECTED';d.state='unknown';}],
  ] as const){await mounted(name,mutate,(host,f)=>{
   const selected=selectBoundSavedAdvice(f.assessment,f.binding,f.result,f.scan);
   requireThat(selected.rows.length===0&&selected.notices.some(n=>n.code==='BINDING_OR_USAGE_MISMATCH'),'Binding/usage mismatch bypassed real selector guard');
   requireThat(!host.textContent?.includes(ACTION_R1),'Rejected response condition leaked into page');
  },{},'rejected');}
  await mounted('missing explicit seven-use parent key is not silently treated as null',f=>{delete (f.assessment.usage as unknown as Record<string,unknown>).network_service;},(host,f)=>{
   const card=requireNeutral(host);requireThat(card.querySelector('[data-bound-advice-notice="BINDING_OR_USAGE_MISMATCH"]'),'Missing parent value did not close with binding diagnostic');
   requireThat(selectBoundSavedAdvice(f.assessment,f.binding,f.result,f.scan).rows.length===0,'Absent parent usage key accepted by display selector');
  });
  await mounted('saved scope plus same-object indirect LicenseExpression basis stays accurately neutral',applyMixedBasis,(host,f)=>{
   const card=requireNeutral(host);
   requireThat(mixedBasisRawStructure.component.license_expression_id===mixedBasisRawStructure.license_expression.id,'Raw synthetic Component link lost');
   requireThat(mixedBasisRawStructure.component.evidence_ids.includes(EVIDENCE)&&mixedBasisRawStructure.license_expression.evidence_ids.includes(MIXED_LICENSE_EVIDENCE),'Raw direct/indirect structural fixture broken');
   requireThat(f.result.resources[0].advice[0].basis_evidence_ids.includes(EVIDENCE)&&f.result.resources[0].advice[0].basis_evidence_ids.includes(MIXED_LICENSE_EVIDENCE),'Saved Advice did not contain both union basis IDs');
   requireThat(!('license_expression_id' in f.scan.resources[0]),'Raw P0 relationship was invented in frontend Resource DTO');
   requireThat(card.querySelector('[data-bound-advice-notice="BASIS_INDIRECT_UNCONFIRMED"]'),'Indirect relation gap omitted');
   requireThat(card.textContent?.includes('已有保存的条件依据，其中间接来源尚未完成当前视图的独立关联核验；可查看逐资源依据。'),'Indirect candidate was described as generic invalid or forbidden');
   requireThat(!containsSaved(card)&&!card.textContent?.includes('禁止使用'),'Unconfirmed indirect relation became permission or prohibition');
  });
  await mounted('same Evidence globally present but associated with another Component cannot affirm',f=>{f.scan.resources[0].evidenceIds=[];f.scan.resources[1].evidenceIds=[EVIDENCE];},host=>{
   const card=requireNeutral(host);requireThat(!containsSaved(card),'Same-ID Evidence from another Component laundered into direct support');
  });
  await mounted('legitimate null revision source remains unestablished without archive identity in Scan projection',f=>{
   f.scan.revision=null;f.binding.project_revision=null;f.scan.input='SYNTHETIC_TEST_ONLY ZIP source; exact archive digest is not projected';
  },(host,f)=>{
   const card=requireNeutral(host);requireThat(zipSourceContext.source_type==='zip'&&zipSourceContext.project_revision===null,'Separate raw synthetic ZIP context changed');
   requireThat(f.scan.revision===null&&f.binding.project_revision===null,'Test invented a commit for ZIP');
   requireThat(card.querySelector('[data-bound-advice-notice="SOURCE_REVISION_UNESTABLISHED"]'),'Matching null revisions were treated as precise source identity');
   requireThat(card.textContent?.includes('输入归档身份与文件范围'),'Missing ZIP provenance next action omitted');
   requireThat(!('input_digest' in f.scan),'Raw ZIP digest invented in frontend Scan DTO');
  });
  await mounted('nonnull Git source revision disagreement closes separately',f=>{f.scan.revision='synthetic-different-project-revision';},host=>{
   const card=requireNeutral(host);requireThat(card.querySelector('[data-bound-advice-notice="SOURCE_REVISION_MISMATCH"]'),'Nonnull revision mismatch was not distinguished from absent provenance');
  });
  await mounted('automatic-review explicit failure keeps immutable saved Result and safe saved Advice',()=>{},(host,_f,requests)=>{
   requireThat(host.textContent?.includes('自动初评暂未读回'),'Projection failure was hidden');requireThat(containsSaved(mainCard(host)),'Projection failure erased safe saved Advice');requireThat(host.textContent?.includes('独立结果 r1'),'Projection failure erased Result');requireThat(requests.filter(r=>r.url.includes('/automatic-review?')).length===1,'Projection failure retried');
  },{automaticStatus:503,automaticBody:{error:{code:'synthetic_projection_unavailable',message:'SYNTHETIC_TEST_ONLY projection unavailable'}}});
  const foreign=makeFixture().review;foreign.result_id=R2;foreign.result_sha256='f'.repeat(64);
  await mounted('newer projection cannot replace old fixed Result or inject newer actions',()=>{},(host)=>{
   requireThat(host.textContent?.includes('自动初评暂未读回'),'Mismatched projection was accepted');requireThat(containsSaved(mainCard(host)),'Correct old saved Advice was discarded');requireThat(!mainCard(host).textContent?.includes(ACTION_R2),'Foreign Result action leaked');
  },{automaticBody:foreign});
  await mounted('fixed r2 only displays r2 condition',f=>{f.result=structuredClone(f.newer);f.review.result_id=f.result.result_id;f.review.result_sha256=f.result.result_sha256;},(host,_f,requests)=>{
   requireThat(containsSaved(mainCard(host),ACTION_R2),'Fixed r2 condition not displayed');requireThat(!mainCard(host).textContent?.includes(ACTION_R1),'Old action carried over to r2');requireThat(requests.some(r=>r.url.includes('/results/'+R2+'?')),'Fixed r2 real service read missing');
  });
  await mounted('valid derived projection cannot manufacture missing saved Advice',f=>{
   const d=f.result.resources[0].advice.find(d=>d.usage==='commercial')!;d.state='unknown';d.conditions=[];d.basis_evidence_ids=[];d.rule_ids=[];
   f.review.source_status='CHECKED';f.review.source_profile_sha256='3'.repeat(64);
   Object.assign(f.review.resources[0],{license_expression:'MIT',state:'CONDITIONAL',priority:'routine',artifact_binding:'EXACT_COORDINATE_ONLY',conditions:['DERIVED_ONLY_NOT_SAVED_ACTION','SYNTHETIC_TEST_ONLY derived condition'],source_refs:[{kind:'metadata',url:'https://registry.npmjs.org/synthetic-alpha/1.2.3',sha256:'4'.repeat(64)},{kind:'tarball',url:'https://registry.npmjs.org/synthetic-alpha/-/synthetic-alpha-1.2.3.tgz',sha256:'5'.repeat(64)}],members:[{member:'package/LICENSE',sha256:'6'.repeat(64)}]});
   Object.assign(f.review.summary,{priority_counts:{routine:1,attention:0,manual:1},state_counts:{CONDITIONAL:1,NONSTANDARD:0,UNAVAILABLE:1,OUTSIDE_NPM:0},source_packages:1,license_materials:1,license_groups:[{license:'MIT',count:1},{license:'UNOBSERVED',count:1}]});
  },host=>{const card=requireNeutral(host);requireThat(!card.textContent?.includes('DERIVED_ONLY_NOT_SAVED_ACTION'),'Derived text was copied into saved Advice');requireThat(!card.textContent?.includes(ACTION_R1),'Absent saved condition was reconstructed');requireThat(!!host.querySelector('.auto-assessment'),'Valid synthetic derived projection did not reach its real validator');requireThat(!host.textContent?.includes('自动初评暂未读回'),'Valid synthetic derived projection was rejected');});
  {
   const f=makeFixture();let rejected=false,error:unknown;
   try{validateSummary(f.summary,f.newer);}catch{rejected=true;}
   try{requireThat(rejected,'Real validateSummary accepted old Summary for newer immutable Result');requireThat(!('conditions' in f.summary),'Fixture Summary contains an invented action field');}catch(e){error=e;}
   report.cases.push({name:'real Summary validator rejects another immutable Result revision',status:error?'failed':'passed',error:error instanceof Error?error.message:null,requests:[]});if(error)throw error;
  }
  report.status='passed';
 }catch(e){report.status='failed';throw e;}
 finally{report.finished_at=new Date().toISOString();document.querySelector('#test-result')!.textContent=JSON.stringify(report,null,2);}
 return report;
}
window.runBoundAdviceSuite=runBoundAdviceSuite;
document.querySelector<HTMLButtonElement>('#run-tests')!.addEventListener('click',()=>{void runBoundAdviceSuite().catch(e=>{document.querySelector('#test-error')!.textContent=e instanceof Error?e.message:String(e);});});
