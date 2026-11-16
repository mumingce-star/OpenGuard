import assert from 'node:assert/strict';
import {runtime} from './runtime.mjs';import {scanHarness,nodes,text} from './new-scan-harness.mjs';
import {harness,usage} from './preview-guard-harness.mjs';
const plain=v=>JSON.parse(JSON.stringify(v));
export async function checkMigration(n){
 if([1,2,3,14,38,40,42].includes(n)){
  const h=harness(n<4);await h.settle();assert.equal(h.form(),undefined);assert.equal(h.button('生成评估／更新用途'),undefined);
  assert.ok(!nodes(h.tree).some(n=>n.props?.['aria-label']==='用途评估'));
  const brief=()=>nodes(h.tree).find(n=>n.type==='DecisionBrief');assert.equal(brief().props.usageReadOnly,true);assert.equal(brief().props.onEditUsage,undefined);assert.equal(brief().props.assessment.usage.preset,'open_source');
  if(n===14){h.failRead('all');h.reload();await h.settle();assert.match(h.text,/读取未完成/);assert.equal(brief().props.assessment.id,'v2');}
  else{h.choose('v1');await h.settle();assert.equal(brief().props.assessment.id,'v1');assert.equal(brief().props.assessment.usage.preset,'unknown');}
  assert.equal(h.calls.some(c=>c.method!=='GET'),false);assert.doesNotMatch(h.text,/评估已保存/);h.dispose();return;
 }
 if([5,6,7,8,9,10,11,12,13,21,43,45,47].includes(n)){
  const r=runtime(),a=r.load('services/assessments.ts'),f=r.load('services/assessmentFeedback.ts'),calls=[];
  const status={5:405,6:403,7:422,21:504}[n];
  const saved={scan:'s',id:'exact-saved',version:3};
  if([12,13].includes(n)){const cause=new Error('private failure');const out=f.assessmentFailure('read',cause,saved);assert.equal(out.saved,saved);assert.equal(out.cause,cause);assert.match(out.message,/第 3 版已保存.*暂未完整读取/);return;}
  r.setFetch(async(u,o)=>{calls.push([u,o]);if(n===8)throw new DOMException('timeout','AbortError');if(n===9)throw new TypeError('offline');if(status)return new Response(n===5?'html':'',{status});if(n===10)return new Response('not json',{status:202});return Response.json({request_id:n===45?'wrong-key':'key',status:n===11?'failed':n===43?'pending':'succeeded',assessment_id:'exact-saved'});});
  if([11,43,47].includes(n)){const j=await a.createAssessment('s',usage,'key');assert.equal(j.request_id,'key');assert.equal(j.status,n===11?'failed':n===43?'pending':'succeeded');assert.equal(calls.length,1);if(n===47){assert.equal(j.assessment_id,'exact-saved');assert.equal(a.validateJob(j,'key').assessment_id,'exact-saved');}return;}
  let cause;try{await a.createAssessment('s',usage,'key');}catch(e){cause=e;}assert.ok(cause);assert.equal(calls.length,1);const out=f.assessmentFailure('submit',cause);assert.match(out.message,status&&status<500?/提交未被接受/:/尚未确认/);assert.doesNotMatch(out.message,/读取未完成|评估已保存|只读预览/);return;
 }
 const h=scanHarness(n===23);await h.settle();if(n===39||n===44)await h.zip();else await h.git();
 const draft={...h.form().props.value,preset:'open_source',distributed:true,source_disclosure:true,commercial:false,modified:null};h.edit(draft);await h.settle();await h.submit();assert.equal(h.calls.length,0);assert.ok(h.confirm);assert.match(h.text,/未知/);
 if(n===39){h.button('返回检查').props.onClick();await h.settle();assert.equal(h.confirm,undefined);assert.deepEqual(plain(h.form().props.value),draft);await h.git();assert.deepEqual(plain(h.form().props.value),draft);h.dispose();return;}
 if(n===23){await h.submit();await h.submit();assert.equal(h.calls.length,0);assert.match(h.text,/只读预览不能/);h.dispose();return;}
 await h.submit();await h.submit();assert.equal(h.calls.length,1);assert.deepEqual(plain(h.calls[0].input.usage),draft);assert.equal(h.calls[0].input.usage.modified,null);
 if([15,41,44,48].includes(n)){h.edit({...draft,commercial:true});await h.settle();if(n===48){h.edit(draft);await h.settle();}h.resolve();await h.settle();assert.equal(h.created.length,0);assert.equal(h.calls[0].input.usage.commercial,false);}
 else if([22,46].includes(n)){h.dispose();h.resolve();await h.settle();assert.equal(h.created.length,0);}
 else {h.resolve();await h.settle();assert.equal(h.created.length,1);assert.equal(h.created[0].id,'scan-confirmed');assert.doesNotMatch(h.text,/评估已保存/);}
 h.dispose();
}
