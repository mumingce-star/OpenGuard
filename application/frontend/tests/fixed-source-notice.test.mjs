import test from 'node:test';
import assert from 'node:assert/strict';
import { runtime } from './runtime.mjs';
const env = {VITE_FIXED_GIT_SOURCE:'https://github.com/http-party/http-server',VITE_FIXED_GIT_REVISION:'a'.repeat(40)};
test('fixed source notice requires complete valid deployment identity',()=>{
 for(const e of [{},{...env,VITE_FIXED_GIT_REVISION:'main'},{...env,VITE_FIXED_GIT_SOURCE:'http://localhost/x/y'}])
   assert.equal(runtime(e).load('services/fixedSourceNotice.ts').fixedSourceNotice,null);
 const n=runtime(env).load('services/fixedSourceNotice.ts').fixedSourceNotice;
 assert.equal(n.source,env.VITE_FIXED_GIT_SOURCE);assert.equal(n.revision,env.VITE_FIXED_GIT_REVISION);
});
test('only server snapshot provenance labels an actual scan as replayed source',()=>{
 const {isFixedSourceScan}=runtime(env).load('services/fixedSourceNotice.ts');
 const proof={sourceKind:'metadata',path:'source-snapshot/git'};
 assert.equal(isFixedSourceScan({mode:'api',evidence:[proof]}),true);
 for(const s of [null,{mode:'mock',evidence:[proof]},{mode:'api',evidence:[]},{mode:'api',evidence:[{...proof,path:'README.md'}]},{mode:'api',evidence:[{...proof,sourceKind:'code'}]}])
   assert.equal(isFixedSourceScan(s),false);
});
