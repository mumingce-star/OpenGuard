import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const fixtureDir = dirname(fileURLToPath(import.meta.url));
const rootDir = join(fixtureDir, '..', '..', '..');
const capturedAt = '2026-09-22T09:30:00Z';
const producer = { name: 'openguard-b03-b04-inventory-generator', version: '3.0.0' };
const sha256 = (value) => createHash('sha256').update(value).digest('hex');
const fileBytes = (path) => readFileSync(path);
const fileHash = (path) => sha256(fileBytes(path));
const canonical = (value) => JSON.stringify(value);
const sourceRevision = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: rootDir, encoding: 'utf8' }).trim();
const evidence = [];
const facts = [];

function addEvidence({ evidenceId, path, locator, contentScope, selected, selectedJsonPointer = null, sourceUrl = null, sourceRevision: revision = sourceRevision }) {
  const absolute = join(rootDir, path);
  const sourceFileSha256 = fileHash(absolute);
  const selectedContentSha256 = sha256(typeof selected === 'string' || Buffer.isBuffer(selected) ? selected : canonical(selected));
  evidence.push({
    evidence_id: evidenceId,
    kind: sourceUrl ? 'provider_snapshot' : 'repository_file',
    locator,
    source_path: path,
    source_url: sourceUrl,
    source_revision: revision,
    content_scope: contentScope,
    source_file_sha256: sourceFileSha256,
    selected_content_sha256: selectedContentSha256,
    selected_json_pointer: selectedJsonPointer,
    captured_at: capturedAt,
    producer,
  });
  return evidenceId;
}

function gaps(...codes) {
  return codes.map((code) => ({ code, severity: 'unknown', evidence_ids: [] }));
}

function relationship(state, evidenceIds = []) {
  return { state, evidence_ids: evidenceIds };
}

function addFact({ factId, category, canonicalId, displayName, version, usageScope, provenance, license, notice, copyright, gapCodes = [] }) {
  facts.push({
    fact_id: factId,
    subject: { category, canonical_id: canonicalId, display_name: displayName, version, usage_scope: usageScope },
    fact_provenance_evidence_ids: provenance,
    authorization_status: 'pending',
    license_expression_id: null,
    relationships: { license, notice, copyright },
    gaps: gaps(...gapCodes),
    review: { required: true, reason: 'authorization_and_legal_interpretation_out_of_scope' },
  });
}

const rootLicensePath = 'LICENSE';
const rootLicenseEvidence = addEvidence({
  evidenceId: 'evidence.root.license', path: rootLicensePath, locator: 'LICENSE', contentScope: 'whole_file', selected: fileBytes(join(rootDir, rootLicensePath)),
});
addFact({
  factId: 'fact.root.openguard', category: 'root_project', canonicalId: 'openguard', displayName: 'OpenGuard', version: null, usageScope: 'root_project', provenance: [rootLicenseEvidence],
  license: relationship('text_observed', [rootLicenseEvidence]), notice: relationship('gap'), copyright: relationship('gap'),
  gapCodes: ['GAP_ROOT_NOTICE_FILE_NOT_OBSERVED', 'GAP_ROOT_COPYRIGHT_ASSERTION_NOT_OBSERVED'],
});

const pyprojectPath = 'backend/pyproject.toml';
const pyproject = readFileSync(join(rootDir, pyprojectPath), 'utf8');
const pythonDependencies = [
  ['runtime', 'fastapi', 'fastapi==0.141.1'], ['runtime', 'packaging', 'packaging==26.3'], ['runtime', 'pydantic', 'pydantic==2.13.4'],
  ['runtime', 'python-multipart', 'python-multipart==0.0.32'], ['runtime', 'uvicorn', 'uvicorn==0.52.4'],
  ['development', 'httpx2', 'httpx2==2.12.0'], ['development', 'jsonschema', 'jsonschema==4.26.0'], ['development', 'pytest', 'pytest==8.4.2'],
];
for (const [usageScope, name, declaration] of pythonDependencies) {
  if (!pyproject.includes(`"${declaration}"`)) throw new Error(`pyproject declaration not found: ${declaration}`);
  const evidenceId = addEvidence({ evidenceId: `evidence.dependency.python.${name}`, path: pyprojectPath, locator: `${pyprojectPath}#${usageScope === 'runtime' ? 'project.dependencies' : 'project.optional-dependencies.dev'}[${name}]`, contentScope: 'toml_declaration', selected: { section: usageScope, declaration } });
  addFact({ factId: `fact.dependency.python.${name}`, category: 'dependency', canonicalId: `pypi:${name}`, displayName: name, version: declaration.split('==')[1], usageScope, provenance: [evidenceId], license: relationship('gap'), notice: relationship('gap'), copyright: relationship('gap'), gapCodes: ['GAP_DEPENDENCY_LICENSE_TEXT_NOT_OBSERVED', 'GAP_DEPENDENCY_NOTICE_NOT_OBSERVED', 'GAP_DEPENDENCY_COPYRIGHT_NOT_OBSERVED'] });
}

const pomPath = 'backend/java/pom.xml';
const pom = readFileSync(join(rootDir, pomPath), 'utf8');
const javaDependencies = [
  ['runtime', 'org.springframework.boot', 'spring-boot-starter-web', null, null],
  ['runtime', 'com.fasterxml.jackson.core', 'jackson-databind', null, null],
  ['runtime', 'com.networknt', 'json-schema-validator', '2.0.4', null],
  ['test', 'org.springframework.boot', 'spring-boot-starter-test', null, 'test'],
];
for (const [usageScope, groupId, artifactId, version, scope] of javaDependencies) {
  const block = new RegExp(`<dependency>\\s*<groupId>${groupId.replaceAll('.', '\\.')}</groupId>\\s*<artifactId>${artifactId}</artifactId>[\\s\\S]*?</dependency>`).exec(pom)?.[0];
  if (!block) throw new Error(`pom dependency not found: ${groupId}:${artifactId}`);
  const selected = { group_id: groupId, artifact_id: artifactId, version, scope };
  const evidenceId = addEvidence({ evidenceId: `evidence.dependency.java.${artifactId}`, path: pomPath, locator: `${pomPath}#dependency[groupId=${groupId};artifactId=${artifactId}]`, contentScope: 'xml_dependency', selected });
  const versionGap = version ? [] : ['GAP_DEPENDENCY_VERSION_NOT_DECLARED_IN_POM'];
  addFact({ factId: `fact.dependency.java.${artifactId}`, category: 'dependency', canonicalId: `maven:${groupId}:${artifactId}`, displayName: artifactId, version, usageScope, provenance: [evidenceId], license: relationship('gap'), notice: relationship('gap'), copyright: relationship('gap'), gapCodes: [...versionGap, 'GAP_DEPENDENCY_LICENSE_TEXT_NOT_OBSERVED', 'GAP_DEPENDENCY_NOTICE_NOT_OBSERVED', 'GAP_DEPENDENCY_COPYRIGHT_NOT_OBSERVED'] });
}

const packagePath = 'frontend/package.json';
const packageJson = JSON.parse(readFileSync(join(rootDir, packagePath), 'utf8'));
for (const [section, usageScope] of [['dependencies', 'runtime'], ['devDependencies', 'development']]) {
  for (const [name, version] of Object.entries(packageJson[section])) {
    const pointer = `/${section}/${name.replaceAll('~', '~0').replaceAll('/', '~1')}`;
    const evidenceId = addEvidence({ evidenceId: `evidence.dependency.npm.${name.replaceAll('/', '--')}`, path: packagePath, locator: `${packagePath}#${pointer}`, contentScope: 'json_pointer_value', selected: version, selectedJsonPointer: pointer });
    addFact({ factId: `fact.dependency.npm.${name.replaceAll('/', '--')}`, category: 'dependency', canonicalId: `npm:${name}`, displayName: name, version, usageScope, provenance: [evidenceId], license: relationship('gap'), notice: relationship('gap'), copyright: relationship('gap'), gapCodes: ['GAP_DEPENDENCY_LICENSE_TEXT_NOT_OBSERVED', 'GAP_DEPENDENCY_NOTICE_NOT_OBSERVED', 'GAP_DEPENDENCY_COPYRIGHT_NOT_OBSERVED'] });
  }
}

const profilePath = 'tests/fixtures/huggingface/resource-profile-v1/manifest.json';
const profile = JSON.parse(readFileSync(join(rootDir, profilePath), 'utf8'));
for (const record of profile.records) {
  const snapshotPath = `tests/fixtures/huggingface/resource-profile-v1/${record.fixture}`;
  const raw = readFileSync(join(rootDir, snapshotPath));
  if (fileHash(join(rootDir, snapshotPath)) !== record.source_file_sha256) throw new Error(`snapshot hash mismatch: ${record.case_id}`);
  const pointer = record.field_evidence.declared_license_raw;
  const declared = record.observed.declared_license_raw;
  const evidenceId = addEvidence({ evidenceId: `evidence.ai.${record.case_id}.declared-license`, path: snapshotPath, locator: `${snapshotPath}#${pointer}`, contentScope: 'json_pointer_value', selected: declared, selectedJsonPointer: pointer, sourceUrl: `https://huggingface.co/api/${record.resource_kind}s/${record.observed.canonical_id}`, sourceRevision: record.observed.revision });
  addFact({ factId: `fact.ai.${record.case_id}`, category: 'ai_resource', canonicalId: `${record.resource_kind}:${record.observed.canonical_id}`, displayName: record.observed.canonical_id, version: record.observed.revision, usageScope: record.resource_kind, provenance: [evidenceId], license: relationship('provider_declared_unverified', [evidenceId]), notice: relationship('gap'), copyright: relationship('gap'), gapCodes: ['GAP_AI_NOTICE_NOT_OBSERVED', 'GAP_AI_COPYRIGHT_NOT_OBSERVED'] });
}

const packageObject = {
  schema_version: 'openguard.notice-license-facts/3',
  package_status: 'draft_facts_only',
  generated_at: capturedAt,
  producer,
  source_inputs: [
    'LICENSE', 'backend/pyproject.toml', 'backend/java/pom.xml', 'frontend/package.json', profilePath,
  ].map((path) => ({ path, source_file_sha256: fileHash(join(rootDir, path)), source_revision: path === profilePath ? 'resource-profile-v1' : sourceRevision })),
  evidence,
  facts,
  report_v3_rows: facts.map((fact) => ({ fact_id: fact.fact_id, subject_id: fact.subject.canonical_id, authorization_status: fact.authorization_status, license_expression_id: null, fact_provenance_evidence_ids: fact.fact_provenance_evidence_ids, relationship_states: Object.fromEntries(Object.entries(fact.relationships).map(([key, value]) => [key, value.state])), gap_codes: fact.gaps.map((gap) => gap.code) })),
};

if (process.argv.includes('--check')) {
  const existing = readFileSync(join(fixtureDir, 'facts.json'), 'utf8');
  const generated = `${JSON.stringify(packageObject, null, 2)}\n`;
  if (existing !== generated) throw new Error('facts.json is stale; run generate.mjs');
} else {
  writeFileSync(join(fixtureDir, 'facts.json'), `${JSON.stringify(packageObject, null, 2)}\n`);
}

console.log(JSON.stringify({ facts: facts.length, evidence: evidence.length, output: relative(rootDir, join(fixtureDir, 'facts.json')) }));
