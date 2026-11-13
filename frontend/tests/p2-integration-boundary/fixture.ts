import { makeFixture, applyMixedBasis, type Bundle } from '../bound-advice-maincard/fixture';
import type { Assessment, Usage } from '../../src/services/assessments';
import type { Binding } from '../../src/services/p2';

/** All IDs/digests/uses are SYNTHETIC_TEST_ONLY, not a saved business Scan. */
export function integrationFixture(label: string, mixed = false) {
  const base = makeFixture();
  if (mixed) applyMixedBasis(base);
  // The real projectUsage requestId contract is 8..90 chars. Keep labels in
  // the report, not an unbounded ID; 6 + 40 + 1 + 32 = 79 chars maximum.
  const token = label.replace(/[^A-Za-z0-9_-]/g, '_').slice(0, 40) + '_' + crypto.randomUUID().replaceAll('-', '');
  base.scan.id = 'scn_cross_' + token;
  base.assessment.scan_id = base.scan.id;
  base.assessment.id = 'asm_cross_' + token;
  Object.assign(base.binding, { scan_id: base.scan.id, assessment_id: base.assessment.id });
  base.result.binding = { ...base.binding };
  base.newer.binding = { ...base.binding };
  base.review.binding = { ...base.binding };
  base.summary.binding = { ...base.binding };
  const changed: Usage = { ...base.assessment.usage, commercial: false, modified: true };
  const next: Assessment = {
    ...structuredClone(base.assessment), id: 'asm_next_' + token,
    version: base.assessment.version + 1, usage: changed,
  };
  // A separately recovered synthetic Assessment, NOT another Result revision
  // under the main-card Assessment. Do not conflate the two Index requests.
  const nextBinding: Binding = {
    ...base.binding, assessment_id: next.id, assessment_version: next.version,
    usage_hash: '1'.repeat(64), assessment_sha256: '2'.repeat(64),
  };
  Object.assign(next, { usage_hash: nextBinding.usage_hash });
  return {
    classification: 'SYNTHETIC_TEST_ONLY' as const,
    base, changed, next, nextBinding,
    requestId: 'cross_' + token,
    storageKey: `openguard:project-usage:1:${base.scan.id}:${base.assessment.id}`,
  };
}
export type IntegrationFixture = ReturnType<typeof integrationFixture>;

export function reviewFor(f: Bundle, newer: boolean) {
  const result = newer ? f.newer : f.result;
  return {
    ...structuredClone(f.review), result_id: result.result_id,
    result_sha256: result.result_sha256, binding: { ...result.binding },
    usage: { ...result.usage },
  };
}
