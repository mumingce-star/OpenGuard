import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runtime } from './runtime.mjs';
const fixture = () => ({ id: 'a1', scan_id: 's1', version: 1, usage: {preset: 'unknown'}, generated_at: '2026-09-10T12:00:00Z', ai_status: 'not_requested', ai_summary: null, summary: '证据不足', dimensions: [{id:'commercial',title:'商业使用',status:'unknown',conclusion:'待核验',conditions:[],restrictions:[],unknowns:['未核验'],resource_ids:[],finding_ids:[],evidence_ids:[]}],coverage_issues:[],resource_ids:[],finding_ids:[],evidence_ids:[],obligations:[] });
test('assessment validates scan ownership, strict conclusions and evidence arrays', () => {
 const s=runtime().load('services/assessments.ts');
 assert.equal(s.validateAssessment(fixture(),'s1').id,'a1');
 assert.throws(()=>s.validateAssessment(fixture(),'s2'),/契约/);
 for(const mutate of [x=>x.dimensions[0].status='allowed',x=>x.evidence_ids=null,x=>x.generated_at='invalid',x=>x.version=0,x=>x.usage.preset='commercial']) { const x=fixture(); mutate(x); assert.throws(()=>s.validateAssessment(x,'s1'),/契约/); }
});
test('usage defaults remain unknown without inferred commercial or disclosure choice', () => {
 const s=runtime().load('services/assessments.ts');
 const u=s.emptyUsage(); assert.equal(u.preset,'unknown');
 for(const k of Object.keys(s.usageFields)) assert.equal(u[k],null);
 const changed={...u,preset:'closed_source'}; assert.equal(changed.source_disclosure,null); assert.equal(changed.commercial,null);
});
test('reading saved assessment and chat performs GET only and stores no mock history', async () => {
 const r=runtime(),s=r.load('services/assessments.ts'),calls=[];
 r.setFetch(async(url,init)=>{calls.push([url,init.method??'GET']);return Response.json(url.endsWith('/chat')?{items:[],generation:0,limits:{max_message_chars:2000,max_turns:50}}:{items:[fixture()],usage:null});});
 await s.listAssessments('s1'); await s.getChat('s1');
 assert.deepEqual(calls.map(x=>x[1]),['GET','GET']); assert.equal(r.storage.size,0);
});
test('404 is unsupported error rather than empty or demo assessment', async()=>{
 const r=runtime(),s=r.load('services/assessments.ts');r.setFetch(async()=>new Response('{}',{status:404}));
 await assert.rejects(s.listAssessments('s1'),e=>e.status===404); assert.equal(r.storage.size,0);
});
test('explicit generation retains the same caller request key and exact nullable usage',async()=>{
 const r=runtime(),s=r.load('services/assessments.ts'),calls=[];
 r.setFetch(async(url,init)=>{calls.push(JSON.parse(init.body));return Response.json({request_id:'same',status:'pending'});});
 await s.createAssessment('s1',s.emptyUsage(),'same');await s.createAssessment('s1',s.emptyUsage(),'same');
 assert.equal(calls[0].request_id,calls[1].request_id); assert.equal(calls[0].usage.commercial,null);
 assert.throws(()=>s.validateJob({request_id:'other',status:'pending'},'same'),/契约/);
});
test('chat submission binds version and generation; clear sends explicit confirmation',async()=>{
 const r=runtime(),s=r.load('services/assessments.ts'),calls=[];r.setFetch(async(url,init)=>{calls.push({url,...init});return Response.json({generation:4,items:[]});});
 await s.sendChat('s1',{assessment_id:'a1',request_id:'q1',message:'问题',generation:3});await s.clearChat('s1',3);
 assert.equal(JSON.parse(calls[0].body).assessment_id,'a1'); assert.equal(JSON.parse(calls[0].body).generation,3);
 assert.equal(calls[1].method,'DELETE'); assert.match(calls[1].url,/confirmed=true&generation=3$/);
});
test('invalid chat generation and states are rejected',()=>{
 const s=runtime().load('services/assessments.ts');
 assert.throws(()=>s.validateChat({items:[],generation:-1,limits:{max_message_chars:2000,max_turns:50}}),/契约/);
});
test('versioned report links encode identifiers and do not replace old report paths',()=>{
 const s=runtime().load('services/assessments.ts');
 assert.equal(s.assessmentReportUrl('a/b','x/y','html'),'/api/v1/scans/a%2Fb/assessments/x%2Fy/report?format=html');
});

test('new scan carries explicit usage in Git and ZIP without changing source contract', async () => {
 const r=runtime(),s=r.load('services/scans.ts'),bodies=[];
 r.setFetch(async(url,init)=>{bodies.push(init.body);return Response.json({scan_id:'s1',status:'queued',status_url:'/api/v1/scans/s1'});});
 const usage={preset:'service',commercial:null,network_service:true};
 await s.createApiScan({kind:'github',url:'https://github.com/pallets/flask',usage},'g1');
 const git=JSON.parse(bodies[0]);assert.equal(git.source_type,'git');assert.deepEqual(git.usage,usage);
 const file=new Blob(['PK'],{type:'application/zip'});Object.defineProperty(file,'name',{value:'fixed.zip'});
 await s.createApiScan({kind:'zip',file,usage},'z1');
 assert.deepEqual(JSON.parse(bodies[1].get('usage')),usage);assert.equal(bodies[1].get('source_type'),'zip');
});
test('assessment and chat task routes coexist with old risk and report paths',()=>{
 const r=runtime(),route=r.load('hooks/useRoute.ts');
 for(const page of ['assessment','chat','risks','resources','report','progress']) {r.shared.window.location={pathname:'/app/scans/s1/'+page,search:'?mode=api&assessment_id=a1'};const parsed=route.readRoute();assert.equal(parsed.page,page);assert.equal(parsed.scanId,'s1');assert.equal(parsed.query.get('assessment_id'),'a1');}
});
test('saved pending assessment job restores after refresh with GET only',async()=>{
 const r=runtime(),s=r.load('services/assessments.ts'),calls=[];
 r.setFetch(async(url,init)=>{calls.push(init.method??'GET');return Response.json(url.includes('/jobs/')?{request_id:'j1',status:'pending'}:{items:[],usage:null,pending_job:{request_id:'j1',status:'pending'}});});
 const saved=await s.listAssessments('s1');assert.equal(saved.pending_job.request_id,'j1');
 const job=await s.getJob('s1',saved.pending_job.request_id);assert.equal(job.status,'pending');assert.deepEqual(calls,['GET','GET']);
});
test('a failed assessment can be retried with a new explicit request key',async()=>{
 const r=runtime(),s=r.load('services/assessments.ts'),keys=[];
 r.setFetch(async(url,init)=>{const body=JSON.parse(init.body);keys.push(body.request_id);return Response.json({request_id:body.request_id,status:keys.length===1?'failed':'pending',error:keys.length===1?'model unavailable':null});});
 assert.equal((await s.createAssessment('s1',s.emptyUsage(),'first')).status,'failed');
 assert.equal((await s.createAssessment('s1',s.emptyUsage(),'explicit-retry')).status,'pending');assert.notEqual(keys[0],keys[1]);
});

test('AI summary evidence ids are retained, optional for old versions, and validated',()=>{
 const s=runtime().load('services/assessments.ts'),x=fixture();x.ai_evidence_ids=['e1','e2'];
 assert.equal(s.validateAssessment(x,'s1').ai_evidence_ids.join(','),'e1,e2');
 x.ai_evidence_ids='invalid';assert.throws(()=>s.validateAssessment(x,'s1'));
 assert.equal(s.validateAssessment(fixture(),'s1').ai_evidence_ids,undefined);
});


test('review_view grouping is optional, validated and preserves old assessment compatibility',()=>{
 const s=runtime().load('services/assessments.ts');
 const legacy=fixture();
 assert.equal(s.validateAssessment(legacy,'s1').review_view,undefined);

 const x=fixture();
 x.review_view={
  view_version:'review-groups/1',
  assessment_id:'a1',
  formal:false,
  groups:[{
   id:'rg_abc',
   code:'license',
   title:'许可与对象版本的对应关系待核验',
   note:'核对相关资源的许可依据。',
   items:[{text:'依赖A：许可待核验',resource_ids:['r1']}],
   raw_count:1,
   resource_ids:['r1'],
   dimension_ids:['commercial']
  }],
  dimensions:[{
   id:'commercial',
   raw_count:1,
   group_count:1,
   groups:[{group_id:'rg_abc',unknown_indices:[0]}]
  }]
 };
 assert.equal(s.validateAssessment(x,'s1').review_view.groups[0].raw_count,1);

 const bad=structuredClone(x);
 bad.review_view.groups[0].raw_count=2;
 assert.throws(()=>s.validateAssessment(bad,'s1'),/契约/);

 const badRef=structuredClone(x);
 badRef.review_view.dimensions[0].groups[0].group_id='rg_missing';
 assert.throws(()=>s.validateAssessment(badRef,'s1'),/契约/);
});

test('scanner diagnostics use product language while raw technical codes stay separate',()=>{
 const p=runtime().load('services/assessmentPresentation.ts');

 const python=p.presentDiagnostic({
  code:'python_dependency_scan_partial',
  message:'Python dependency scan was partial: requirement_editable_unsupported at requirements-dev.txt:1. Editable requirement directive is unsupported.'
 });
 assert.equal(python.title,'Python 依赖扫描不完整');
 assert.match(python.detail,/requirements-dev\.txt 第 1 行/);
 assert.match(python.detail,/editable/);
 assert.doesNotMatch(python.detail,/requirement_editable_unsupported|Python dependency scan was partial/);

 const git=p.presentDiagnostic({
  code:'git_scan_coverage_partial',
  message:'有界扫描：仓库共 130 个条目，本次读取 128 个文件；2 个条目未扫描。完整路径和原因见报告的扫描覆盖范围。'
 });
 assert.equal(git.title,'仓库覆盖不完整');
 assert.match(git.detail,/130/);
 assert.match(git.detail,/128/);
 assert.match(git.detail,/2 个条目未扫描/);

 const report=p.presentDiagnostic({
  code:'scan_incomplete',
  message:'Some scan results are incomplete; review the recorded errors and coverage.'
 });
 assert.equal(report.title,'报告基于部分扫描结果生成');
 assert.doesNotMatch(report.detail,/Some scan results/);
});

test('python multiple constraints diagnostic is not presented as editable',()=>{
 const p=runtime().load('services/assessmentPresentation.ts');
 const input={code:'python_dependency_scan_partial',message:'Python dependency scan was partial: dependency_multiple_constraints at requirements.txt:2. Dependency has multiple constraints.'};
 const original=JSON.stringify(input);
 const result=p.presentDiagnostic(input);
 assert.equal(result.title,'Python 依赖扫描不完整');
 assert.equal(result.detail,'requirements.txt 第 2 行存在多个依赖约束；相关依赖结果需要进一步核对。');
 assert.doesNotMatch(result.detail,/editable|dependency_multiple_constraints/);
 assert.equal(JSON.stringify(input),original);
});

test('python unknown diagnostic uses generic fallback without guessing a cause',()=>{
 const p=runtime().load('services/assessmentPresentation.ts');
 for (const message of [
  'Python dependency scan was partial: unknown_parser_reason at requirements.txt:4. Mentions requirement_editable_unsupported and dependency_multiple_constraints.',
  'Python dependency scan was partial: unknown_parser_reason at [path withheld]. Unknown reason.',
 ]) {
  const input={code:'python_dependency_scan_partial',message};
  const result=p.presentDiagnostic(input);
  assert.equal(result.title,'Python 依赖扫描不完整');
  assert.match(result.detail,/该依赖声明当前未被完整解析；具体技术原因请查看下方技术诊断/);
  assert.doesNotMatch(result.detail,/editable|多个依赖约束|unknown_parser_reason/);
  assert.equal(input.message,message);
  if (message.includes('requirements.txt:4')) assert.match(result.detail,/requirements\.txt 第 4 行/);
 }
});

test('project summary separates formal conclusion from project fact observations',()=>{
 const p=runtime().load('services/assessmentPresentation.ts');
 const summary=[
  '根目录许可文件记录到：Apache-2.0。这属于文件级许可观察，不表示条款原文与适用关系已核验，也不自动适用于依赖。',
  '组件共33条：直接依赖声明4条，可选依赖声明2条，开发／测试／构建／文档线索15条，工作流引用12条。此分类依据声明字段或扫描位置，不代表最终交付范围。',
  '本次未识别到AI资产记录，不等于不存在AI资产。',
  '',
  '已有扫描事实，但关键授权或用途证据不足，暂不能确认整个项目可用于目标用途。'
 ].join('\n');

 const view=p.presentProjectSummary(summary);
 assert.equal(view.conclusion,'已有扫描事实，但关键授权或用途证据不足，暂不能确认整个项目可用于目标用途。');
 assert.equal(view.facts.length,3);
 assert.equal(view.facts[0].label,'许可证线索');
 assert.equal(view.facts[0].value,'Apache-2.0');
 assert.equal(view.facts[1].value,'33 条组件记录');
 assert.equal(view.facts[2].value,'本次未识别到 AI 资产记录');

 const legacy=p.presentProjectSummary('证据不足，暂无法判断');
 assert.equal(legacy.facts.length,0);
 assert.equal(legacy.conclusion,'证据不足，暂无法判断');
});


test('assessment page avoids duplicated raw coverage and uses accurate dimension detail wording',()=>{
 const source=readFileSync(
  new URL('../src/pages/Assessment.tsx',import.meta.url),
  'utf8'
 );

 assert.match(
  source,
  /评估仍有 \{selected\.coverage_issues\.length\} 项覆盖限制/
 );

 assert.match(
  source,
  /已经纳入下方“需要核验的事项”/
 );

 assert.doesNotMatch(
  source,
  /展开全部覆盖限制原文/
 );

 assert.match(
  source,
  /查看本维度判断与证据/
 );

 // 没有review_view的历史Assessment仍保留原始fallback入口。
 assert.match(
  source,
  /查看全部原始依据/
 );
});
