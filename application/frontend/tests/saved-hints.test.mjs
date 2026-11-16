import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import { runtime } from './runtime.mjs';
const real=JSON.parse(fs.readFileSync(new URL('./saved-hints.fixture.json',import.meta.url)));
const plain=x=>JSON.parse(JSON.stringify(x));
const usage={...real.usage};
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const gap=real.gaps[0];
const projection=()=>runtime().load('services/usageExperience.ts');
test('SH-T01 real v2 prompts only four relevant unknown facts, acknowledging distribution and disclosure',()=>{
 const p=projection(),x=p.usageHints({gaps:real.gaps},usage);
 assert.deepEqual(plain(x.fields),['commercial','modified','network_service','redistributed_assets']);
 assert.match(x.text,/商业使用.*修改.*在线服务.*再分发/);assert.doesNotMatch(x.text,/向他人分发|公开源代码|训练/);
});
test('SH-T02 true and false are answered; null and legacy missing remain unknown without coercion',()=>{
 const p=projection();for(const value of [true,false])assert.equal(p.usageHints({gaps:[gap]},{...usage,commercial:value}).fields.includes('commercial'),false);
 for(const value of [null,undefined])assert.equal(p.usageHints({gaps:[gap]},{...usage,commercial:value}).fields.includes('commercial'),true);
 const invalid=p.usageHints({gaps:[gap]},{...usage,commercial:'false'});assert.equal(invalid.uncertain,true);assert.equal(invalid.fields.includes('commercial'),false);
});
test('SH-T03 fields follow saved dimensions and answers, not a hardcoded four or preset defaults',()=>{
 const p=projection();assert.deepEqual(plain(p.usageHints({gaps:[{...gap,affected_dimensions:['redistribution']}]},{preset:'internal',distributed:null}).fields),['distributed']);
 assert.deepEqual(plain(p.usageHints({gaps:[gap]},{...usage,commercial:false,modified:true,network_service:false}).fields),['redistributed_assets']);
 assert.equal(p.usageHints({gaps:[gap]},{...usage,preset:'service'}).fields.length,4);
});
test('SH-T04 unconsumed training and unknown dimension never invent a blocking training requirement',()=>{
 const p=projection();assert.equal(p.usageHints({gaps:[gap]},usage).fields.includes('training'),false);
 const x=p.usageHints({gaps:[{...gap,affected_dimensions:['future_dimension']}]},usage);assert.equal(x.uncertain,true);assert.deepEqual(plain(x.fields),[]);
});
test('SH-T05 answering related facts removes missing-fact copy but preserves scope sources and authority',()=>{
 const p=projection(),b={gaps:real.gaps,permission_state:'unknown',local_results:[]},u={...usage,commercial:false,modified:false,network_service:false,redistributed_assets:false};
 assert.equal(p.usageHints(b,u).text,'');assert.equal(p.scopeSummary(b).sources.length,2);assert.match(p.permissionBoundary(b),/待核对/);
});
test('SH-T06 scope identity union counts overlapping 44/27 and dynamic non-subset data',()=>{
 const p=projection(),x=p.scopeSummary({gaps:real.gaps});assert.equal(x.regular,44);assert.equal(x.ai,27);assert.equal(x.overlap,27);assert.equal(x.total,44);assert.match(x.text,/44.*其中27/);assert.doesNotMatch(x.text,/71/);
 const scopes=real.gaps.filter(g=>g.code==='SCOPE_UNRESOLVED');const y=p.scopeSummary({gaps:[{...scopes[0],resource_ids:['a','b','b']},{...scopes[1],resource_ids:['b','c']}]});assert.deepEqual([y.regular,y.ai,y.overlap,y.total],[2,2,1,3]);assert.match(y.text,/重叠1/);
});
test('SH-T07 scope aggregation retains separate owners, source references and unknown kinds',()=>{
 const p=projection(),sc=real.gaps[1],other={...sc,owner:'reviewer',action:'REVIEW_SCOPE',resource_ids:['extra'],affected_dimensions:['future']},b={gaps:[sc,other],obligations:[{id:'o'}]};const before=JSON.stringify(b),x=p.scopeSummary(b);assert.equal(x.sources[0],sc);assert.equal(x.sources[1],other);assert.equal(x.unclassified,1);assert.equal(JSON.stringify(b),before);
});

import {checkMigration} from './usage-migration-cases.mjs';
for(let n=8;n<=18;n++)test('SH-T'+String(n).padStart(2,'0')+' migrated saved identity / pre-scan draft protection',()=>checkMigration(n+30));

test('SH-T19 invalid fact types cannot be displayed or compared as declared boolean facts',()=>{const p=projection(),bad={...usage,commercial:'false'};assert.equal(p.sameUsage(bad,bad),false);assert.doesNotMatch(p.usageDescription(bad),/商业使用：是|商业使用：否/);assert.match(p.usageDescription(bad),/待核对/);});

test('SH-T20 unclassified scope identities remain counted without claiming all resources belong to the regular set',()=>{const p=projection(),scope=real.gaps.filter(g=>g.code==='SCOPE_UNRESOLVED'),x=p.scopeSummary({gaps:[...scope,{...scope[0],affected_dimensions:['future'],resource_ids:['extra']}]});assert.equal(x.total,45);assert.equal(x.unclassified,1);assert.match(x.text,/共45/);assert.equal(x.sources.length,3);});
