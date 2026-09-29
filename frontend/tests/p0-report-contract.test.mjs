import assert from 'node:assert/strict';
import test from 'node:test';
import {
  expectedNotGeneratedPaths,
  isExpectedNotGeneratedFailure,
  readP0Scenario,
} from './p0-report-contract.mjs';

const scanId = 'scn_00000000-0000-0000-0000-000000002711';
const scenario = { kind: 'not_generated', scanId, scanIds: [scanId] };
const exact = {
  method: 'GET',
  status: 409,
  path: expectedNotGeneratedPaths(scanId)[0],
  body: { error: { code: 'report_not_ready', details: { reason: 'not_generated' } } },
};

test('only an exact, predeclared P0 not_generated response is expected', () => {
  assert.equal(isExpectedNotGeneratedFailure(scenario, exact), true);
});

test('wrong scan, reason, endpoint, status, or body cannot be allowed', () => {
  const failures = [
    { ...exact, path: exact.path.replace('002711', '002712') },
    { ...exact, path: `${exact.path}&download=true` },
    { ...exact, body: { error: { code: 'report_not_ready', details: { reason: 'status_not_ready' } } } },
    { ...exact, body: { error: { code: 'internal_error', details: { reason: 'not_generated' } } } },
    { ...exact, path: `/api/v1/scans/${scanId}/graph` },
    { ...exact, status: 500 },
    { ...exact, body: undefined },
  ];
  for (const failure of failures) assert.equal(isExpectedNotGeneratedFailure(scenario, failure), false);
});

test('available scenario never converts a 409 into success', () => {
  assert.equal(isExpectedNotGeneratedFailure({ kind: 'available', scanId, scanIds: [scanId] }, exact), false);
});

test('scenario and complete scan ID must be explicitly supplied', () => {
  assert.throws(() => readP0Scenario({}), /must explicitly/);
  assert.throws(() => readP0Scenario({ OPENGUARD_P0_REPORT_SCENARIO: 'not_generated', OPENGUARD_P0_SCAN_ID: 'scn_…2711' }), /complete lowercase/);
});

test('available hash acceptance cannot run without both fixed hashes', () => {
  assert.throws(() => readP0Scenario({
    OPENGUARD_P0_REPORT_SCENARIO: 'available',
    OPENGUARD_P0_SCAN_ID: scanId,
  }, { requireHashes: true }), /requires exact/);
});

test('a negative scan list is explicit, complete, and must contain the page scan', () => {
  const parsed = readP0Scenario({
    OPENGUARD_P0_REPORT_SCENARIO: 'not_generated',
    OPENGUARD_P0_SCAN_ID: scanId,
    OPENGUARD_P0_NOT_GENERATED_SCAN_IDS: `${scanId},scn_00000000-0000-0000-0000-000000002713`,
  });
  assert.equal(parsed.scanIds.length, 2);
  assert.throws(() => readP0Scenario({
    OPENGUARD_P0_REPORT_SCENARIO: 'not_generated',
    OPENGUARD_P0_SCAN_ID: scanId,
    OPENGUARD_P0_NOT_GENERATED_SCAN_IDS: 'scn_00000000-0000-0000-0000-000000002713',
  }), /must contain/);
});
