import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import { P2VersionComparison } from '../../src/components/P2VersionComparison';
import { usageTitle } from '../../src/services/usageExperience';
import { fixture, TARGET } from '../team-integration/fixture';
import { transport, check } from '../team-integration/transport';
const report={classification:'SYNTHETIC_TEST_ONLY_REAL_REACT_REAL_READ_PREVIOUS_SERVICE',status:'NOT_RUN',cases:[] as any[]};
declare global{interface Window{__USAGE_VERSION_POLISH__:typeof report;runUsageVersionPolish:()=>Promise<typeof report>;}}
window.__USAGE_VERSION_POLISH__=report;
const tick=()=>new Promise<void>(resolve=>{const c=new MessageChannel();c.port1.onmessage=()=>{c.port1.close();c.port2.close();resolve();};c.port2.postMessage(null);});
async function idle(){await act(async()=>{for(let i=0;i<8;i++)await tick();});}
async function until(predicate:()=>boolean,label:string){const end=performance.now()+4000;while(!predicate()){check(performance.now()<end,'Not settled: '+label);await idle();}}
async function scenario(name:string,action:(x:{f:ReturnType<typeof fixture>;t:ReturnType<typeof transport>;host:HTMLDivElement;render:(view:'A'|'B',result?:'r1'|'r2')=>void;read:()=>void})=>Promise<void>){
 const f=fixture(),t=transport(f,{}),host=document.createElement('div');document.querySelector('#mounts')!.append(host);const root=createRoot(host);window.fetch=t.fetch;let error:unknown;
 // Put the peer first, so selecting the target demonstrates change-based ordering.
 for(const bundle of [f.base,f.other])for(const row of [bundle.result,bundle.newer])row.resources.reverse();
 const render=(view:'A'|'B',result:'r1'|'r2'='r2')=>{const b=view==='A'?f.base:f.other;flushSync(()=>root.render(<P2VersionComparison assessment={b.assessment} binding={b.binding} current={result==='r1'?b.result:b.newer} resourceName={id=>id===TARGET?'目标组件':'未变化组件'}/>));};
 const read=()=>{const button=host.querySelector<HTMLButtonElement>('button')!;check(button&&!button.disabled,'Read button missing');flushSync(()=>button.click());};
 try{render('A');await action({f,t,host,render,read});}
 catch(e){error=e;}
 finally{flushSync(()=>root.unmount());host.remove();await t.drain();await idle();if(!error&&t.unknown.length)error=Error('Independent unknown request ledger nonempty');if(!error&&t.nonGet.length)error=Error('Read-only projection dispatched nonGET');report.cases.push({name,status:error?'failed':'passed',error:error instanceof Error?error.stack:error?String(error):null,requests:t.ledger,unknown:t.unknown,nonGet:t.nonGet});}
}
export async function runUsageVersionPolish(){
 check(report.status==='NOT_RUN','One execution per page');report.status='running';
 await scenario('default selected resource is material/advice target even with peer first',async({host,read})=>{read();await until(()=>!!host.querySelector('[data-p2-version-pair]'),'pair');check(host.querySelector<HTMLSelectElement>('select')!.value===TARGET,'Selected list-first peer rather than changed target');const summary=host.querySelector('[data-p2-difference-summary]')!.textContent!;check(summary.includes('新增 1 份材料')&&summary.includes('重新核对 1 个资源')&&summary.includes('复用 1 个资源'),'Saved delta counts not visible');check(summary.includes('状态变化 0 个'),'Pending-to-pending was falsely described as state change');});
 await scenario('switching Assessment never displays previous A as B parent',async({f,host,render,read})=>{read();await until(()=>!!host.querySelector('[data-p2-version-pair]'),'A pair');render('B');check(!host.querySelector('[data-p2-version-pair]')||host.querySelector<HTMLElement>('[data-p2-version-pair]')!.dataset.currentResult===f.other.newer.result_id,'Old pair leaked during commit');await until(()=>host.querySelector<HTMLElement>('[data-p2-version-pair]')?.dataset.currentResult===f.other.newer.result_id,'B pair');check(host.querySelector<HTMLElement>('[data-p2-version-pair]')!.dataset.previousResult===f.other.result.result_id,'B parent wrong');});
 await scenario('switching r2 to initial r1 removes old comparison immediately',async({host,render,read})=>{read();await until(()=>!!host.querySelector('[data-p2-version-pair]'),'r2 pair');render('A','r1');await idle();check(!host.querySelector('[data-p2-version-pair]'),'Old r2 pair remained under r1');check(host.textContent!.includes('本结果没有前版引用'),'Missing parent not explained');});
 await scenario('all seven saved boolean facts yield custom usage and preserve original payload',async({f,host})=>{const usage={...f.base.assessment.usage,preset:'unknown' as const,commercial:false,modified:true,distributed:false,network_service:true,training:false,redistributed_assets:false,source_disclosure:true};const before=JSON.stringify(usage);const label=document.createElement('p');label.textContent=usageTitle(usage);host.append(label);check(label.textContent==='自定义用途 · 七项已确认','Unknown preset hid declared facts');check(JSON.stringify(usage)===before,'Display rewrote saved facts');});
 report.status=report.cases.every(x=>x.status==='passed')?'passed':'failed';document.querySelector('#results')!.textContent=JSON.stringify(report,null,2);return report;
}
window.runUsageVersionPolish=runUsageVersionPolish;
document.querySelector<HTMLButtonElement>('#run')!.onclick=()=>void runUsageVersionPolish();
