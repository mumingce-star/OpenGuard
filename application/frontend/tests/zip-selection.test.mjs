import test from 'node:test';
import assert from 'node:assert/strict';
import { runtime } from './runtime.mjs';
import { scanHarness, nodes } from './new-scan-harness.mjs';

// Directory-only synthetic bytes test UI classification, not ZIP safety or a real scan.
const markers=['VERSION_BINDING.json','FILE_HASHES.json','START_HERE.html','02_P2/Result.json','01_REPORT/Assessment.json'];
function zip(names, name='project.zip') {
  const records=names.map(n=>{const b=Buffer.from(n),c=Buffer.alloc(46+b.length);c.writeUInt32LE(0x02014b50);c.writeUInt16LE(b.length,28);b.copy(c,46);return c;});
  const cd=Buffer.concat(records),end=Buffer.alloc(22);end.writeUInt32LE(0x06054b50);end.writeUInt16LE(names.length,8);end.writeUInt16LE(names.length,10);end.writeUInt32LE(cd.length,12);
  return Object.assign(new Blob([cd,end],{type:'application/zip'}),{name});
}
const api=()=>runtime().load('services/zipSelection.ts');
async function select(h,f){nodes(h.tree).find(n=>n.props?.type==='file').props.onChange({target:{files:[f],value:'selected'}});await h.settle();}
function picker(h){return nodes(h.tree).find(n=>n.props?.type==='file');}

test('export structure detected independent of filename; ordinary source and partial markers are not export packages',async()=>{
  const {isOpenGuardEvaluationPackage:check}=api();
  assert.equal(await check(zip(markers,'is-number.zip')),true);
  assert.equal(await check(zip(['LICENSE','README.md','index.js','package.json'],'OpenGuard-evaluation-v1-r2-example.zip')),false);
  assert.equal(await check(zip(markers.slice(1))),false);
  assert.equal(await check(zip([...markers,'package.json'])),false);
});
test('truncated, oversized, and unknown directories defer archive validity to backend without decompression',async()=>{
  const {isOpenGuardEvaluationPackage:check}=api();
  assert.equal(await check(Object.assign(new Blob(['not a zip']),{name:'x.zip'})),false);
  const bytes=Buffer.from(await zip(markers).arrayBuffer());bytes.writeUInt16LE(513,bytes.length-12);
  assert.equal(await check(Object.assign(new Blob([bytes]),{name:'x.zip'})),false);
  let reads=[];const file=zip(markers);const slice=file.slice.bind(file);file.slice=(a,b)=>{reads.push([a,b]);return slice(a,b);};
  assert.equal(await check(file),true);assert.equal(reads.length,2);assert.ok(reads[1][1]-reads[1][0]<=262144);
});
test('exact small-file bytes are visible instead of 0.00 MB',()=>assert.equal(api().selectedZipSize({size:4172}),'4,172 字节（4.07 KiB）'));
test('reopening picker clears selected and confirmed file; cancel cannot submit the old file',async()=>{
  const h=scanHarness();await h.settle();await select(h,zip(['package.json']));await h.submit();assert.ok(h.confirm);
  let opened=0;picker(h).props.ref.current={value:'old',click(){opened++;}};
  h.button('重新选择').props.onClick();await h.settle();assert.equal(opened,1);assert.equal(h.confirm,undefined);
  assert.equal(h.button('下一步').props.disabled,true);await h.submit();assert.equal(h.calls.length,0);h.dispose();
});
test('reselect after frozen confirmation submits only the new exact File and usage',async()=>{
  const h=scanHarness();await h.settle();const a=zip(['package.json'],'first.zip'),b=zip(['package.json'],'second.zip');
  await select(h,a);await h.submit();await select(h,b);assert.equal(h.confirm,undefined);await h.submit();assert.match(h.text,/second.zip/);await h.submit();
  assert.equal(h.calls.length,1);assert.equal(h.calls[0].input.file,b);h.resolve();await h.settle();h.dispose();
});
test('known output package never reaches createApiScan, including renamed output',async()=>{
  const h=scanHarness();await h.settle();await select(h,zip(markers,'is-number.zip'));
  assert.match(h.text,/评估结果包结构/);assert.equal(h.button('下一步').props.disabled,true);
  await h.submit();assert.equal(h.calls.length,0);h.dispose();
});
test('late file inspection cannot restore a prior file after cancellation',async()=>{
  const h=scanHarness();await h.settle();let done;const slow={name:'old.zip',size:99,type:'application/zip',slice(){return{arrayBuffer:()=>new Promise(r=>{done=r;})};}};
  await select(h,slow);picker(h).props.ref.current={value:'old',click(){}};h.button('重新选择').props.onClick();await h.settle();
  done(new ArrayBuffer(0));await h.settle();assert.equal(h.confirm,undefined);assert.equal(h.button('下一步').props.disabled,true);await h.submit();assert.equal(h.calls.length,0);h.dispose();
});
test('newer source selection wins over late previous output inspection',async()=>{
  const h=scanHarness();await h.settle();let done;const old=zip(markers);let first=true;const slice=old.slice.bind(old);old.slice=(a,b)=>first?(first=false,{arrayBuffer:()=>new Promise(r=>{done=()=>slice(a,b).arrayBuffer().then(r);})}):slice(a,b);
  await select(h,old);const good=zip(['package.json'],'current.zip');await select(h,good);await done();await h.settle();
  assert.match(h.text,/current.zip/);assert.doesNotMatch(h.text,/检测到 OpenGuard/);await h.submit();await h.submit();assert.equal(h.calls[0].input.file,good);h.resolve();await h.settle();h.dispose();
});
test('read failure blocks submission and remains a visible failure',async()=>{
  const h=scanHarness();await h.settle();await select(h,{name:'bad.zip',size:99,type:'application/zip',slice(){return{arrayBuffer:async()=>{throw Error('fixture read failure');}};}});
  assert.match(h.text,/无法读取本次选择/);assert.equal(h.button('下一步').props.disabled,true);await h.submit();assert.equal(h.calls.length,0);h.dispose();
});
