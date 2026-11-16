import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';
const source=p=>fs.readFileSync(new URL('../src/'+p,import.meta.url),'utf8');
test('UXR1-01 entire AI details use a closed native disclosure',()=>{const s=source('components/AiReview.tsx');assert.match(s,/<details[^>]*id="ai-assisted-groups"/);assert.match(s,/AI研判明细 · 查看分类与判断依据/);});
test('UXR1-02 stage result precedes optional upgrade plan',()=>{const s=source('components/AiReview.tsx');assert.ok(s.indexOf('<StageResult ')>=0);assert.ok(s.indexOf('<StageResult ')<s.indexOf('<TierUpgradePlans '));});
test('UXR1-03 assessment has no embedded usage editor in any mode',()=>{const s=source('pages/Assessment.tsx');assert.doesNotMatch(s,/<UsageForm|试填用途（不会保存）|生成评估／更新用途|og-assessment-usage/);});
test('UXR1-04 scan dispatch follows explicit frozen confirmation',()=>{const s=source('pages/NewScan.tsx');assert.match(s,/确认扫描前用途/);assert.match(s,/开始扫描并评估/);assert.match(s,/confirmedInput/);});
