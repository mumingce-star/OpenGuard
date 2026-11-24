import assert from 'node:assert/strict';
import test from 'node:test';
import { runtime } from './runtime.mjs';

const app = runtime();
const { validateDependencyEvidencePage } = app.load('services/dependencyEvidence.ts');
const { validateReportDocument, classifyReportObservations } = app.load('services/reportV2.ts');
const id = (prefix, num) => prefix + '_' + String(num).padStart(26, '0');
const scanId = id('scn', 1), assessmentId = 'asm_1', snapshotId = 'rptv2_1';
const artifact = '/api/v1/scans/' + scanId + '/assessments/' + assessmentId + '/report-v2/' + snapshotId;
const hash = character => character.repeat(64);
const reportSchema = 'openguard-report-v2-dependency-evidence/1';
const coordinates = [
  ['golang', 'example.test/Org/Module', 'v2.0.0+incompatible', 'manifest', 'go/go.mod', '/require/3'],
  ['cargo', 'serde', null, 'manifest', 'rust/Cargo.toml', '/dependencies/serde'],
  ['maven', 'org.example:artifact', '1.2.3', 'lock', 'java/gradle.lockfile', '/dependencies/4'],
];

function observation() {
  const scanRef = {
    scan_id: scanId, revision: null, facts_hash: hash('a'), input_hash: hash('b'),
    inventory_hash: hash('c'), status: 'partial', registry_revision: 3,
  };
  const items = coordinates.map(([ecosystem, name, version, source, file, field], index) => {
    const evidence = [{
      evidence_id: id('evd', index + 1), source, file_path: file, locator: file + ':' + field,
      source_sha256: hash('d'), producer: {
        type: 'parser', name: 'openguard.dependency-observations.' + source, version: 'b58/1',
        config_digest: null, provider: null, model_id: null, prompt_schema_digest: null,
      },
      verification_status: 'pending', kind: 'manifest_field', start_line: null, end_line: null,
    }];
    return {
      resource_id: id('cmp', index + 1), ecosystem, name, version,
      role_state: source === 'manifest' ? 'observed' : 'inferred',
      sources: [source], evidence, evidence_total: 1, evidence_returned: 1,
      conflicts: [], conflicts_total: 0, conflicts_returned: 0,
      incomplete: version === null, gaps: version === null ? ['version_unavailable'] : [],
    };
  });
  return { scan_ref: scanRef, coverage: 'unknown', total: items.length, returned: items.length,
    incomplete: true, items };
}

function page() {
  return { schema_version: 'openguard-dependency-evidence/1', source: null, limit: 50,
    next_cursor: null, ...observation() };
}

function report() {
  const dependency = { schema_version: reportSchema, ...observation() };
  const facts = { id: scanId, status: 'partial' };
  const formal = { id: assessmentId, scan_id: scanId, facts_hash: hash('a'), version: 2, formal: true };
  const contents = [
    ['scan_facts', facts],
    ['formal_assessment', formal],
    ['workflow', { tasks: [] }],
    ['ai_explanation', { ai_status: 'not_requested' }],
    ['observation', dependency],
  ];
  return {
    schema_version: '1.1',
    snapshot_id: snapshotId,
    binding: {
      scan_ref: { ...dependency.scan_ref },
      assessment_ref: { assessment_id: assessmentId, version: formal.version, scan_id: scanId,
        facts_hash: formal.facts_hash, usage_hash: hash('b'), rule_version: 'rule-1', formal: true },
      task_refs: [], notice_refs: [], algorithm_refs: [],
    },
    created_at: '2026-09-18T00:00:00Z', generator_version: 'report-v2/1.1',
    provenance: { source_refs: [], assessment_refs: [] },
    sections: contents.map(([authority, content], index) => ({
      authority, content, source_ids: [scanId], content_hash: hash('e'),
      snapshot_ref: artifact + '?format=json#/sections/' + index + '/content',
      ...(authority === 'observation' ? { schema_version: reportSchema, title: '依赖证据' } : { schema_version: '1.0' }),
    })),
  };
}

const identities = items => Array.from(items, item => [item.ecosystem, item.name, item.version]);
const expected = coordinates.map(([ecosystem, name, version]) => [ecosystem, name, version]);

test('TASK54 dependency evidence decodes exact Go, Cargo and Maven identities and preserves pending facts', () => {
  const decoded = validateDependencyEvidencePage(page(), scanId);
  assert.deepEqual(identities(decoded.items), expected);
  assert.ok(decoded.items.every(item => item.evidence[0].verification_status === 'pending'));
  assert.deepEqual(decoded.items[1].gaps, ['version_unavailable']);
});

test('TASK54 dependency evidence rejects ecosystem aliases and unknown wire values', () => {
  for (const invalid of ['go', 'rust', 'java', 'Maven', 'docker', null]) {
    const raw = page();
    raw.items[0].ecosystem = invalid;
    assert.throws(() => validateDependencyEvidencePage(raw, scanId), /依赖证据响应/);
  }
});

test('TASK54 Report V2 1.1 decodes archived observations for all three added ecosystems', () => {
  const decoded = validateReportDocument(report(), scanId, assessmentId, snapshotId);
  const dependency = classifyReportObservations(decoded).dependency.content;
  assert.deepEqual(identities(dependency.items), expected);
  assert.equal(dependency.scan_ref.facts_hash, hash('a'));
  assert.equal(dependency.items[2].evidence[0].file_path, 'java/gradle.lockfile');
});

test('TASK54 Report V2 1.1 rejects invalid ecosystem in the archive', () => {
  const raw = report();
  raw.sections.at(-1).content.items[2].ecosystem = 'gradle';
  assert.throws(() => validateReportDocument(raw, scanId, assessmentId, snapshotId), /接口契约/);
});
