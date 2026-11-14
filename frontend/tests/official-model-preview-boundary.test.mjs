import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import { runtime } from './runtime.mjs';

// Actual saved model13 preview, read offline. SSR is not browser acceptance.
const require = createRequire(import.meta.url);
const evidence = new URL('../../../evidence/real-analysis/', import.meta.url);
const rawStatus = fs.readFileSync(new URL('04-response.body', evidence));
const rawResult = fs.readFileSync(new URL('05-response.body', evidence));
const status = JSON.parse(rawStatus), result = JSON.parse(rawResult);
const actual = { preview: status.analysis.preview, usage: result.usage };
const sha = value => crypto.createHash('sha256').update(value).digest('hex');
const frozen = value => {
  if (value && typeof value === 'object') {
    Object.values(value).forEach(frozen);
    Object.freeze(value);
  }
  return value;
};
frozen(actual);

function render(props = actual) {
  const service = runtime(), module = { exports: {} };
  const ledger = [], nonGet = [], unknown = [];
  const deny = (url, options = {}) => {
    const row = { url: String(url), method: options.method ?? 'GET' };
    ledger.push(row);
    if (row.method !== 'GET') nonGet.push(row);
    unknown.push(row);
    throw Error('Closed offline SSR: no HTTP or model endpoint is allowed');
  };
  service.setFetch(deny);
  const source = fs.readFileSync(new URL('../src/components/OfficialSources.tsx', import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  vm.runInNewContext(code, { module, exports: module.exports, fetch: deny,
    require: name => name === 'react' || name === 'react/jsx-runtime' ? require(name)
      : name.endsWith('.css') ? {} : service.load(name.replace(/^\.\.\//, '') + '.ts'),
  });
  const html = renderToStaticMarkup(module.exports.OfficialAnalysisPreview(props));
  return { html, ledger, nonGet, unknown };
}

function noRequests(value) {
  assert.equal(value.ledger.length, 0, 'display must not dispatch any HTTP/model request');
  assert.equal(value.nonGet.length, 0, 'independent non-GET ledger must remain empty');
  assert.equal(value.unknown.length, 0, 'unknown requests must not disappear in a product catch');
}

test('actual saved preview preserves every model action and the exact saved input bytes', () => {
  assert.equal(sha(rawStatus), '2d07fd06e06a4b8b9d3578762dcea8d8bec2a9b12a444459ae5df71ff291adab');
  assert.equal(sha(rawResult), '6ecc9fbef912976bc533490dbc1e056b610c3de82ba169ee302305672ea0a277');
  const before = JSON.stringify(actual), value = render();
  assert.equal(actual.preview.status, 'succeeded');
  assert.equal(actual.preview.model_calls, 1);
  assert.equal(actual.usage.distributed, false);
  assert.equal(actual.preview.actions.length, 4);
  for (const action of actual.preview.actions) assert.ok(value.html.includes(action.text));
  assert.equal((value.html.match(/data-original-model-action=""/g) ?? []).length, 4);
  assert.equal(JSON.stringify(actual), before);
  noRequests(value);
});

test('delivery-premise warning is adjacent to the actual unsupported already-delivered action', () => {
  const value = render();
  const row = value.html.match(/<li data-model-action-index="3">([\s\S]*?)<\/li>/)?.[1];
  assert.ok(row?.includes(actual.preview.actions[3].text));
  assert.ok(row?.includes('data-model-action-warning="delivery-premise"'));
  assert.ok(row?.includes('当前用途未声明向他人交付'));
  assert.ok(row?.includes('已交付前提尚无证据，不代表交付已经发生'));
  noRequests(value);
});

test('actual training and asset actions each retain their own explicit source-scope warning', () => {
  const value = render();
  const training = value.html.match(/<li data-model-action-index="1">([\s\S]*?)<\/li>/)?.[1];
  const assets = value.html.match(/<li data-model-action-index="2">([\s\S]*?)<\/li>/)?.[1];
  assert.ok(training?.includes(actual.preview.actions[1].text));
  assert.ok(training?.includes('data-model-action-warning="training-scope"'));
  assert.ok(training?.includes('具体训练输入、所用代码及各自来源'));
  assert.ok(training?.includes('不能覆盖训练数据、模型或其他资源'));
  assert.ok(assets?.includes(actual.preview.actions[2].text));
  assert.ok(assets?.includes('data-model-action-warning="asset-scope"'));
  assert.ok(assets?.includes('实际对象、版本及各自来源'));
  assert.ok(assets?.includes('不能覆盖其他资产或依赖'));
  noRequests(value);
});

test('program success is displayed as human-review preview, with pending and npm404 limitations intact', () => {
  const value = render();
  assert.match(value.html, /Qwen3 · 待人工复核预览/);
  assert.match(value.html, /程序检查通过不代表每条语义已确认/);
  assert.match(value.html, /不作为已确认的许可结论或实际用途事实/);
  assert.match(value.html, /资料尚未写入 Material，也未改变规则建议/);
  assert.match(value.html, /npm 14\.1\.2元数据端点明确返回404/);
  assert.match(value.html, /不是已保存 Material 引用/);
  assert.doesNotMatch(value.html, /<button|<form|<input|已确认允许商用|已通过人工审核/);
  noRequests(value);
});

test('delivery warning follows current declared false, without inventing a new usage fact', () => {
  for (const distributed of [true, null]) {
    // SYNTHETIC_TEST_ONLY contrast; not a replacement for the captured result.
    const props = structuredClone(actual);
    props.usage.distributed = distributed;
    const value = render(props);
    assert.doesNotMatch(value.html, /data-model-action-warning="delivery-premise"/);
    assert.ok(value.html.includes(actual.preview.actions[3].text));
    assert.match(value.html, /不作为已确认的许可结论或实际用途事实/);
    noRequests(value);
  }
});

test('failed preview has no replacement actions and cannot look like a successful model analysis', () => {
  const props = structuredClone(actual);
  props.preview.status = 'failed';
  const value = render(props);
  assert.equal(value.html, '');
  noRequests(value);
});
