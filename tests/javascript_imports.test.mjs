import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { parseJavascriptImports } from '../backend/app/scanners/javascript_imports.mjs';
const require = createRequire(new URL('../frontend/package.json', import.meta.url));
const ts = require('typescript');
const bindings = new Map([['@scope/lib', { resourceId: 'component:lib', version: '1.0' }],
  ['alias', { resourceId: 'component:actual', version: '2.0' }],
  ['#local', { resourceId: 'component:local', version: '3.0' }]]);
const parse = (code, options = {}) => parseJavascriptImports(Buffer.from(code), { ts, path: 'src/app.ts', reviewedBindings: bindings, ...options });

test('imports, reexports, requires and exact literal dynamic imports retain locations', () => {
  const r = parse('import x from "@scope/lib/sub";\nexport {x} from "alias";\nrequire("alias");\nimport("alias");');
  assert.equal(r.status, 'complete');
  assert.deepEqual(r.observations.map(x => x.kind), ['import', 'export-from', 'require', 'dynamic-import']);
  assert.deepEqual(r.observations.map(x => x.line), [1, 2, 3, 4]);
  assert.equal(r.observations[0].target.resourceId, 'component:lib');
});
test('comments, strings, regex and template text do not create imports', () => {
  const r = parse('// import x from "alias"\nconst a = "require(\'alias\')"; const r = /require("alias")/; const t = `import("alias")`;');
  assert.equal(r.observations.length, 0);
});
test('type imports and type reexports remain separate', () => {
  const r = parse('import type {X} from "alias"; import {type Y} from "alias"; export type {X} from "alias"; type Z = import("alias").Z;');
  assert.equal(r.observations.length, 4);
  assert.ok(r.observations.every(x => x.typeOnly));
});
test('mixed types retain runtime reference semantics', () => {
  assert.equal(parse('import {type X, y} from "alias";').observations[0].typeOnly, false);
});
test('relative, builtin and missing bindings never guess', () => {
  const r = parse('import "./a"; import "node:fs"; import "other";');
  assert.ok(r.observations.every(x => x.target === null));
  assert.deepEqual(r.gaps.map(x => x.code), ['relative_module_not_resolved', 'alias_or_builtin_unknown', 'package_binding_missing']);
});
test('reviewed alias is explicit and version-bound', () => {
  assert.equal(parse('import "#local";').observations[0].referenceKind, 'reviewed_alias');
  assert.equal(parse('import "alias";', { reviewedBindings: new Map([['alias', {resourceId:'x'}]]) }).observations[0].target, null);
});
test('nonliteral dynamic and require stay unknown even constant-looking identifiers', () => {
  const r = parse('const name = "alias"; import(name); require(name); import(`alias/${name}`);');
  assert.equal(r.observations.length, 3);
  assert.ok(r.observations.every(x => x.target === null));
});
test('arbitrary URL specifiers do not reflect credential-like literal content', () => {
  const r = parse('import "https://user:private@example.test/module.js";');
  assert.equal(r.observations[0].specifier, null);
  assert.equal(r.gaps[0].code, 'unsupported_module_specifier');
});
for (const declaration of ['const require = x;', 'function f(require) {}', 'const { require } = obj;', 'require = x;']) {
  test(`require shadowing: ${declaration}`, () => {
    const r = parse(`require("alias"); ${declaration}`);
    assert.equal(r.observations[0].target, null);
    assert.equal(r.gaps[0].code, 'require_binding_ambiguous');
  });
}
test('malformed syntax fails closed without recovered AST claims', () => {
  const r = parse('import { from "alias";');
  assert.equal(r.status, 'partial');
  assert.deepEqual(r.observations, []);
  assert.ok(r.gaps.every(x => x.code === 'syntax_invalid'));
});
test('syntax expressions in template substitutions are inspected', () => {
  assert.equal(parse('const s = `x${require("alias")}`;').observations.length, 1);
});
test('typescript import-equals', () => {
  assert.equal(parse('import lib = require("alias");').observations[0].kind, 'import-equals');
});
test('no target execution, source digest stable, bindings unchanged', () => {
  const code = 'throw new Error("must not execute"); import "alias";';
  const before = JSON.stringify([...bindings]);
  assert.deepEqual(parse(code), parse(code));
  assert.equal(JSON.stringify([...bindings]), before);
});
test('input, path and parser version limits', () => {
  assert.throws(() => parse('a'.repeat(256 * 1024 + 1)), /limit/);
  assert.throws(() => parse('', { path: '../app.ts' }), /path/);
  assert.throws(() => parse('', { ts: {version:'0'} }), /version/);
  assert.throws(() => parseJavascriptImports(Buffer.from([255]), {ts, path:'app.ts'}));
});
