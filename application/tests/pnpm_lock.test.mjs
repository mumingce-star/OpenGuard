import { strict as assert } from 'node:assert';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { test } from 'node:test';
import { parsePnpmLock } from '../backend/app/scanners/pnpm_lock.mjs';

const parserPath = process.env.OPENGUARD_TEST_YAML_PACKAGE_JSON;
const require = createRequire(import.meta.url);
const yaml = parserPath ? require(parserPath.replace(/package\.json$/u, '')) : null;
const yamlVersion = parserPath ? require(parserPath).version : null;
function verify(name, fn) { test(name, { skip: !yaml && 'set OPENGUARD_TEST_YAML_PACKAGE_JSON for yaml 2.9.0' }, fn); }
const fixture = `lockfileVersion: '9.0'
importers:
  apps/a:
    dependencies:
      '@scope/lib': {specifier: ^1.0.0, version: 1.0.0(peer@1.0.0)}
      sibling: {specifier: 'workspace:*', version: 'link:../b'}
      alias: {specifier: 'npm:@scope/lib@2.0.0', version: '@scope/lib@2.0.0'}
  apps/b:
    dependencies:
      '@scope/lib': {specifier: '2.0.0', version: '2.0.0'}
packages:
  '@scope/lib@1.0.0': {}
  '@scope/lib@2.0.0': {}
  peer@1.0.0: {}
snapshots:
  '@scope/lib@1.0.0(peer@1.0.0)':
    dependencies: {peer: '1.0.0'}
  '@scope/lib@2.0.0': {}
  peer@1.0.0:
    dependencies: {'@scope/lib': '1.0.0(peer@1.0.0)'}
`;
const parse = (raw = fixture, options = {}) => parsePnpmLock(Buffer.from(raw), { yaml, yamlVersion, ...options });

verify('two workspace importers, aliases, version instances and cycles preserve identity', () => {
  const result = parse();
  assert.equal(result.status, 'complete');
  assert.deepEqual(result.nodes.filter(n => n.name === '@scope/lib').map(n => n.version), ['1.0.0', '2.0.0']);
  assert.ok(result.edges.some(e => e.from === 'importer:apps/a' && e.to === 'importer:apps/b'));
  assert.ok(result.edges.some(e => e.from === 'snapshot:peer@1.0.0' && e.to === 'snapshot:@scope/lib@1.0.0(peer@1.0.0)'));
  assert.ok(result.edges.some(e => e.locator.endsWith('/alias') && e.to === 'snapshot:@scope/lib@2.0.0'));
  assert.deepEqual(parse(), result);
});

verify('unsafe paths, version and alias conflicts do not create edges', () => {
  const result = parse(fixture.replace('link:../b', 'link:../../../b').replace("'npm:@scope/lib@2.0.0'", "'2.0.0'")
    .replace("specifier: '2.0.0', version: '2.0.0'", "specifier: '1.0.0', version: '2.0.0'"));
  assert.equal(result.status, 'partial');
  assert.deepEqual(result.gaps.map(g => g.code), ['workspace_path_unsafe', 'alias_binding_unverified', 'dependency_version_conflict']);
  assert.throws(() => parse(fixture.replace('apps/a:', '../a:')), /unsafe_importer_path/);
});

verify('missing package metadata and unresolved edges preserve closed endpoints', () => {
  const result = parse(fixture.replace("  '@scope/lib@2.0.0': {}\n", '').replace("'link:../b'", "'link:../missing'"));
  assert.ok(result.gaps.some(g => g.code === 'package_metadata_missing'));
  assert.ok(result.gaps.some(g => g.code === 'dependency_unresolved'));
  assert.ok(result.gaps.some(g => g.code === 'workspace_target_missing'));
  const ids = new Set(result.nodes.map(n => n.instanceId));
  assert.ok(result.edges.every(e => ids.has(e.from) && ids.has(e.to)));
});

verify('versions, duplicate keys, YAML aliases and input limits are rejected', () => {
  assert.throws(() => parse(fixture.replace('9.0', '8.0')), /unsupported_pnpm/);
  assert.throws(() => parse(`lockfileVersion: '9.0'\n${fixture}`), /invalid_lock_yaml/);
  assert.throws(() => parse(fixture.replace('packages:', 'packages: &packages')), /indirection/);
  assert.throws(() => parse(fixture.replace('importers:', 'importers: [')), /invalid_lock_yaml/);
  assert.throws(() => parse(fixture, { path: '../lock' }), /unsafe_source_path/);
  assert.throws(() => parse('a'.repeat(2 * 1024 * 1024 + 1)), /input_limit/);
});

verify('repository lock produces a reproducible bounded graph', () => {
  const raw = readFileSync(new URL('../frontend/pnpm-lock.yaml', import.meta.url));
  const result = parsePnpmLock(raw, { yaml, yamlVersion, path: 'frontend/pnpm-lock.yaml' });
  assert.ok(result.nodes.length > 80);
  assert.ok(result.edges.some(e => e.from === 'importer:.' && e.to === 'snapshot:typescript@5.9.2'));
  assert.match(result.sourceSha256, /^[a-f0-9]{64}$/);
  const ids = new Set(result.nodes.map(n => n.instanceId));
  assert.ok(result.edges.every(e => ids.has(e.from) && ids.has(e.to)));
});
