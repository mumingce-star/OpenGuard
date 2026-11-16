import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { runtime } from './runtime.mjs';
const policy = runtime().load('services/accountPassword.ts');
for (const [name,password,allowed] of [
  ['8 characters','Demo1234',true],['24 characters','A1'+'x'.repeat(22),true],
  ['7 characters','Ab12345',false],['25 characters','A1'+'x'.repeat(23),false],
  ['letters only','abcdefgh',false],['digits only','12345678',false],
  ['symbols allowed','Ab12!@#$',true],['Unicode codepoints','A1'+'🔐'.repeat(22),true],
  ['no implicit trimming',' Ab1234 ',true],['ASCII letter required','中文123456',false],
]) test('new registration '+name,()=>assert.equal(policy.accountPasswordError(password,true)===null,allowed));
test('legacy long password still accepted for login',()=>assert.equal(policy.accountPasswordError('Synthetic account test phrase 2026!',false),null));
test('legacy letters-only password remains accepted for login',()=>assert.equal(policy.accountPasswordError('OriginalPasswordWithoutDigits',false),null));
test('empty or excessive login input rejected',()=>{assert.notEqual(policy.accountPasswordError('',false),null);assert.notEqual(policy.accountPasswordError('a'.repeat(129),false),null);});
test('real AuthPage calls the shared policy',()=>{const source=fs.readFileSync(new URL('../src/pages/AuthPage.tsx',import.meta.url),'utf8');assert.match(source,/accountPasswordError\(password, register\)/);assert.match(source,/maxLength=\{register \? 48 : 256\}/);});
