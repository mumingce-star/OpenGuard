import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import test from 'node:test';
import { readFixedGitSource } from './fixtures/notice-license-facts-v3/fixed-git-source.mjs';

const root = fileURLToPath(new URL('..', import.meta.url));
const base = join(root, 'tests/fixtures/notice-license-facts-v3');
const revisionDir = join(base, 'revisions/source-binding-r2');
const generator = join(base, 'generate.mjs');
const hash = raw => createHash('sha256').update(raw).digest('hex');
const load = path => JSON.parse(readFileSync(path, 'utf8'));
const manifest = load(join(revisionDir, 'manifest.json'));
const facts = load(join(revisionDir, 'facts.json'));
const legacy = load(join(base, 'facts.json'));
const sortKeys = value => Array.isArray(value) ? value.map(sortKeys) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, sortKeys(value[key])])) : value;
const canonicalHash = value => hash(JSON.stringify(sortKeys(value)));

test('r2 fixes all Git source identities and preserves the eight selected npm facts', () => {
  for (const source of manifest.sources) {
    // 独立用 git show 验证生成器的 ls-tree/cat-file 路径。
    const raw = execFileSync('git', ['show', `${source.source_commit}:${source.path}`], {
      cwd: root, env: { ...process.env, GIT_NO_LAZY_FETCH: '1', GIT_NO_REPLACE_OBJECTS: '1' },
    });
    assert.equal(raw.length, source.size_bytes);
    assert.equal(hash(raw), source.sha256);
    for (const evidence of facts.evidence.filter(item => item.source_path === source.path)) {
      assert.equal(evidence.source_file_sha256, source.sha256);
    }
  }
  assert.deepEqual(facts.facts, legacy.facts);
  assert.deepEqual(facts.report_v3_rows, legacy.report_v3_rows);
  const changed = facts.evidence.filter(item => item.source_file_sha256 !==
    legacy.evidence.find(old => old.evidence_id === item.evidence_id).source_file_sha256);
  assert.equal(changed.length, 8);
  for (const evidence of changed) {
    assert.equal(evidence.source_path, 'frontend/package.json');
    assert.equal(evidence.source_file_sha256, 'a8e9bab912ffc5ef1afc2da36db5b0de932ce872e235e02b55dce9ceca65f09a');
    assert.equal(evidence.selected_content_sha256,
      legacy.evidence.find(item => item.evidence_id === evidence.evidence_id).selected_content_sha256);
  }
});

test('amendment hashes close over retained parent and replacement, without inventing acceptance', () => {
  const amendment = load(join(revisionDir, 'amendment.json'));
  assert.equal(amendment.parent.file_sha256, hash(readFileSync(join(base, 'facts.json'))));
  assert.equal(amendment.parent.canonical_package_sha256, canonicalHash(legacy));
  assert.equal(amendment.replacement.canonical_package_sha256, canonicalHash(facts));
  assert.equal(amendment.affected_evidence.length, 8);
  assert.equal(amendment.independent_review, null);
  assert.equal(amendment.human_approval, null);
  assert.equal(amendment.a_terminal_readback, null);
  for (const item of manifest.artifacts) {
    const raw = readFileSync(join(revisionDir, item.path));
    assert.equal(raw.length, item.size_bytes);
    assert.equal(hash(raw), item.sha256);
    assert.notEqual(hash(Buffer.concat([raw, Buffer.from('tamper')])), item.sha256);
  }
});

test('malformed identities, traversal and missing blobs fail closed', () => {
  for (const revision of ['HEAD', 'a'.repeat(39), '--help', 'https://example.invalid/repo']) {
    assert.throws(() => readFixedGitSource(root, revision, 'frontend/package.json'), /fixed_source_identity_invalid/);
  }
  for (const path of ['../frontend/package.json', '/frontend/package.json', 'frontend\\package.json',
    'frontend//package.json', 'frontend/package.json\0', 'C:/file']) {
    assert.throws(() => readFixedGitSource(root, manifest.source_commit, path), /fixed_source_identity_invalid/);
  }
  assert.throws(() => readFixedGitSource(root, manifest.source_commit, 'not-present.json'), /fixed_source_not_regular_blob/);
  const tree = execFileSync('git', ['rev-parse', `${manifest.source_commit}^{tree}`], { cwd: root, encoding: 'utf8' }).trim();
  assert.throws(() => readFixedGitSource(root, tree, 'frontend/package.json'), /fixed_source_not_commit/);
});

test('worktree source pollution cannot influence generation or fixed hashes', () => {
  const temporary = mkdtempSync(join(tmpdir(), 'openguard-b03-source-'));
  try {
    const preload = join(temporary, 'pollute-fs.mjs');
    // 仅读操作注入脏字节，实际工作树文件不改动。
    writeFileSync(preload, `import fs from 'node:fs';
import { syncBuiltinESMExports } from 'node:module';
import { resolve } from 'node:path';
const sources = new Set(${JSON.stringify(manifest.sources.map(item => join(root, item.path)))}.map(p => resolve(p)));
const original = fs.readFileSync;
fs.readFileSync = function(path, ...args) {
  if (typeof path === 'string' && sources.has(resolve(path))) return Buffer.from('DIRTY WORKTREE');
  return original.call(this, path, ...args);
};
syncBuiltinESMExports();\n`);
    const generated = execFileSync(process.execPath, ['--import', pathToFileURL(preload).href, generator, '--stdout'], {
      cwd: root, encoding: 'utf8', timeout: 60_000,
    });
    assert.equal(generated, readFileSync(join(revisionDir, 'facts.json'), 'utf8'));
  } finally {
    assert.equal(dirname(resolve(temporary)), resolve(tmpdir()));
    assert.ok(basename(temporary).startsWith('openguard-b03-source-'));
    rmSync(temporary, { recursive: true, force: true });
  }
});

test('generation refuses to overwrite retained legacy or existing corrected revision', () => {
  const paths = ['facts.json', ...manifest.artifacts.map(item => `revisions/source-binding-r2/${item.path}`),
    'revisions/source-binding-r2/manifest.json'];
  const before = paths.map(path => hash(readFileSync(join(base, path))));
  assert.throws(() => execFileSync(process.execPath, [generator], { cwd: root, stdio: 'pipe', timeout: 60_000 }));
  assert.deepEqual(paths.map(path => hash(readFileSync(join(base, path)))), before);
});
