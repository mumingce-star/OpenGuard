import test from 'node:test';
import assert from 'node:assert/strict';
import {runtime} from './runtime.mjs';
const m=runtime().load('pages/progressModel.ts');
const phases=['ingestion','inventory','scan','normalize','rules','report'];
const event=(sequence,phase,state,percent)=>({sequence,phase,state,percent,observed_at:new Date(Date.UTC(2026,9,15,0,0,sequence)).toISOString()});
const scan=(n=6,status='completed',id='TEST_ONLY_PLAYBACK')=>({id,mode:'api',status,stageIndex:status==='completed'?6:0,progress:status==='completed'?100:40,stages:['input','inventory','scan','normalize','rules','AI未启用','report'],resources:[],evidence:[],progressEvents:{events:phases.slice(0,n).flatMap((p,i)=>[event(2*i+1,p,'start',i*15),event(2*i+2,p,'end',(i+1)*15)])}});
test('fast final stages are each presented, with at least 800ms per stage',()=>{
 const s=scan();let p=m.createStagePlayback({...s,status:'running'},0),seen=[];
 for(let i=0;i<6;i++){
  p=m.advanceStagePlayback(p,s,i*800,false);let v=m.stagePlaybackView(s,p);seen.push(v.currentNumber);
  assert.equal(v.replaying,true);assert.equal(v.stages[i].state,'running');assert.match(v.stages[i].stateText,/过程展示/);
  assert.equal(m.advanceStagePlayback(p,s,i*800+799,false).cursor,i);
 }
 p=m.advanceStagePlayback(p,s,4800,false);assert.equal(p.enabled,false);
 assert.deepEqual(seen,[1,2,3,4,5,6]);assert.equal(m.stagePlaybackView(s,p).ended,6);
});
test('history initially completed is immediate, without a misleading running stage',()=>{
 const s=scan(),p=m.createStagePlayback(s,0),v=m.stagePlaybackView(s,p);
 assert.equal(p.enabled,false);assert.equal(v.replaying,false);assert.equal(v.ended,6);
});
test('waiting for real phase evidence does not invent a stage start',()=>{
 const s=scan(0,'queued');let p=m.createStagePlayback(s,0);p=m.advanceStagePlayback(p,s,5000,false);
 assert.equal(p.cursor,0);assert.equal(p.started,false);assert.equal(m.stagePlaybackView(s,p).currentNumber,null);
});
test('a newly received real first stage gets its full display interval',()=>{
 const s=scan(0,'running');let p=m.createStagePlayback(s,0);p=m.advanceStagePlayback(p,s,5000,false);
 const f=scan(2,'running');p=m.advanceStagePlayback(p,f,6000,false);
 assert.equal(p.cursor,0);assert.equal(p.enteredAt,6000);assert.equal(m.advanceStagePlayback(p,f,6799,false).cursor,0);
 assert.equal(m.advanceStagePlayback(p,f,6800,false).cursor,1);
});
test('disconnection freezes the display queue',()=>{
 const s=scan();let p=m.createStagePlayback({...s,status:'running'},0);p=m.advanceStagePlayback(p,s,0,false);
 assert.equal(m.advanceStagePlayback(p,s,10000,true),p);
});
for(const status of ['failed','partial','cancelled'])test('terminal '+status+' stops playback and retains the actual stage outcome',()=>{
 const s=scan(3,status),p=m.advanceStagePlayback(m.createStagePlayback({...s,status:'running'},0),s,1000,false);
 assert.equal(p.enabled,false);assert.equal(m.stagePlaybackView(s,p).replaying,false);
});
test('missing next-phase evidence cannot be skipped over to reach a later stage',()=>{
 const s=scan(1,'running');s.progressEvents.events.push(event(5,'scan','start',30));
 let p=m.createStagePlayback(s,0);p=m.advanceStagePlayback(p,s,0,false);p=m.advanceStagePlayback(p,s,1000,false);
 assert.equal(p.cursor,0);
});
test('changing task identity resets playback and cannot reuse the previous queue',()=>{
 const s=scan();let p=m.createStagePlayback({...s,status:'running'},0);p=m.advanceStagePlayback(p,s,0,false);p=m.advanceStagePlayback(p,s,800,false);
 const other=scan(0,'queued','OTHER');p=m.advanceStagePlayback(p,other,900,false);
 assert.equal(p.scanId,'OTHER');assert.equal(p.cursor,0);assert.equal(p.started,false);
});
test('presentation never changes real events, status, timestamps or conclusions',()=>{
 const s=scan(),before=JSON.stringify(s);let p=m.createStagePlayback({...s,status:'running'},0);
 for(let i=0;i<8;i++){p=m.advanceStagePlayback(p,s,i*800,false);m.stagePlaybackView(s,p);}
 assert.equal(JSON.stringify(s),before);
});
test('progress display cannot reach 100 before the final recorded stage has been shown',()=>{
 const s=scan(),p=m.advanceStagePlayback(m.createStagePlayback({...s,status:'running'},0),s,0,false);
 assert.ok(m.stagePlaybackView(s,p).ceiling<100);
 const history=m.createStagePlayback(s,0);assert.equal(m.stagePlaybackView(s,history).ceiling,100);
});
test('live work telemetry can progress inside the current running phase',()=>{
 const s=scan(3,'running');s.progressEvents.events.pop();let p=m.createStagePlayback(s,0);
 for(const t of [0,800,1600])p=m.advanceStagePlayback(p,s,t,false);
 const v=m.stagePlaybackView(s,p);assert.equal(v.currentNumber,3);assert.equal(v.replaying,false);assert.equal(v.ceiling,100);
});
