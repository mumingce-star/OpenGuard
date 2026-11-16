import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {runtime} from './runtime.mjs';
import {harness,nodes,usage} from './preview-guard-harness.mjs';
const writes=h=>h.calls.filter(c=>c.method!=='GET');
const notice='只读预览：可查看结果、试填用途，不能保存或重新评估。';
// UX-R1: the Assessment editor was removed by Owner. Preserve transport/error
// contracts directly; test confirmation and asynchronous draft behavior at NewScan.
import {scanHarness} from './new-scan-harness.mjs';
import {checkMigration} from './usage-migration-cases.mjs';
for(let n=1;n<=15;n++)test('RO-'+String(n).padStart(2,'0')+' migrated result-read / pre-scan guard',()=>checkMigration(n));
test('RO-16 error helper preserves original object and status for internal inspection',()=>{const r=runtime(),{ApiError}=r.load('services/scans.ts'),{assessmentFailure}=r.load('services/assessmentFeedback.ts');const cause=new ApiError(405,'internal English','method_blocked','reason');const result=assessmentFailure('submit',cause);assert.equal(result.cause,cause);assert.equal(result.cause.status,405);assert.equal(result.cause.code,'method_blocked');assert.doesNotMatch(result.message,/internal English|method_blocked|只读预览/);});
test('RO-17 capability is explicit build config, not URL, port, or API mode',()=>{for(const value of [undefined,'false','1'])assert.equal(runtime({VITE_OPENGUARD_READ_ONLY_PREVIEW:value}).load('services/assessmentFeedback.ts').readOnlyPreview,false);assert.equal(runtime({VITE_OPENGUARD_READ_ONLY_PREVIEW:'true'}).load('services/assessmentFeedback.ts').readOnlyPreview,true);});

import {componentView,button,nodesOf,textOf,saved,versionReview,job,flush} from './preview-brief-harness.mjs';
test('RO-18 same-region material search is disabled and its handler blocks POST',async()=>{const b=saved({gaps:[versionReview({owner:'system',action:'RESOLVE_LOCAL',safe_automation:true,resource_ids:['component-b']})]});const v=componentView(b,{readOnly:true}),t=v.render();const search=nodesOf(t).find(n=>n.type==='button'&&/检查本地材料/.test(textOf(n)));assert.ok(search);assert.equal(search.props.disabled,true);search.props.onClick();await flush();assert.equal(v.calls.filter(c=>c.method!=='GET').length,0);const edit=button(t,'修改用途');edit.props.onClick();assert.equal(v.edits,1);assert.ok(button(t,'查看材料与待审核事项'));});
test('RO-19 active material cancellation has both disabled control and handler guard',async()=>{const active=job(),v=componentView(saved(),{readOnly:true,jobs:[active],currentJob:active}),t=v.render(),cancel=button(t,'取消本次查找');assert.equal(cancel.props.disabled,true);cancel.props.onClick();await flush();assert.equal(v.calls.length,0);assert.ok(button(t,'读取进度'));});
test('RO-20 read-only chat form submit and clear controls cannot write',async()=>{const h=harness(true);await h.settle();h.button('展开项目答疑').props.onClick();await h.settle();const form=nodes(h.tree).find(n=>n.type==='form'&&n.props['aria-label']!=='用途评估');assert.ok(form);await form.props.onSubmit({preventDefault(){}});await h.settle();assert.equal(h.button('发送给本地 Qwen3').props.disabled,true);assert.equal(h.button('清空本任务问答').props.disabled,true);h.button('清空本任务问答').props.onClick();await h.settle();assert.equal(h.button('确认清空问答'),undefined);assert.equal(writes(h).length,0);h.dispose();});
for(const n of [21,22,23])test('RO-'+n+' migrated explicit submit contract',()=>checkMigration(n));

test('RO-24 read-only draft and search next-step copy never asks user to generate or search',()=>{const b=saved(),v=componentView(b,{readOnly:true,draftUsage:{preset:'personal'}}),t=v.render();const next=nodesOf(t).find(n=>n.props?.className==='og-use-next');assert.match(textOf(next),/试填.*不会保存/);assert.doesNotMatch(textOf(next),/先确认.*生成/);});
