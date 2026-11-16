import { makeFixture, type Bundle } from '../bound-advice-maincard/fixture';
import type { Binding, Material, Receipt, Result, ResultIndex } from '../../src/services/p2';

/** SYNTHETIC_TEST_ONLY. This is not the real http-server LICENSE or a business Scan. */
export const FILE_TEXT = 'SYNTHETIC_TEST_ONLY LICENSE text for material async permission regression.\nNot a real source or permission statement.\n';
export const FILE_SHA256 = '2b22f17bf8862c1595b800b3be3d6a632358dada825973a5a40384b4a0dcb106';
export const SOURCE_DESCRIPTION = 'SYNTHETIC_TEST_ONLY local transport fixture; no official source or actual use is asserted.';
export const FILE_BYTES = new TextEncoder().encode(FILE_TEXT);

function retag(b: Bundle, token: string, assessmentVersion: number): Bundle {
  const scanId = 'scn_material_' + token;
  const assessmentId = 'asm_material_' + token;
  b.scan.id = scanId;
  b.assessment.id = assessmentId; b.assessment.scan_id = scanId; b.assessment.version = assessmentVersion;
  Object.assign(b.binding, { scan_id: scanId, assessment_id: assessmentId, assessment_version: assessmentVersion });
  b.result.result_id = 'res_material_' + token + '_r1';
  b.result.companion_summary_id = 'sum_material_' + token + '_r1';
  b.result.binding = { ...b.binding };
  b.newer.result_id = 'res_material_' + token + '_r2';
  b.newer.previous_result_id = b.result.result_id;
  b.newer.companion_summary_id = 'sum_material_' + token + '_r2';
  b.newer.binding = { ...b.binding };
  Object.assign(b.review, { result_id: b.result.result_id, binding: { ...b.binding } });
  Object.assign(b.summary, { summary_id: b.result.companion_summary_id, result_id: b.result.result_id, binding: { ...b.binding } });
  return b;
}
export function materialFixture(label: string) {
  const token = label.replace(/[^A-Za-z0-9_-]/g, '_').slice(0, 30) + '_' + crypto.randomUUID().replaceAll('-', '');
  const base = retag(makeFixture(), token, 1);
  const alternate = retag(makeFixture(), token + '_next', 2);
  // Same project, distinct fixed Assessment; no cross-assessment object filling.
  alternate.scan.id = base.scan.id; alternate.assessment.scan_id = base.scan.id;
  for (const b of [alternate.binding, alternate.result.binding, alternate.newer.binding, alternate.review.binding, alternate.summary.binding]) b.scan_id = base.scan.id;
  const target = base.result.resources[0], peer = base.result.resources[1];
  const materialId = 'mat_material_' + token;
  const saved = structuredClone(base.newer);
  saved.state = 'partial';
  saved.material_ids = [materialId]; saved.recomputed_resource_ids = [target.subject.resource_id]; saved.reused_resource_ids = [peer.subject.resource_id];
  saved.resources[0].state = 'pending'; saved.resources[0].material_ids = [materialId];
  saved.resources[0].gaps = [...target.gaps, 'uploaded_material_applicability_pending'];
  // The unaffected resource is deliberately copied byte-for-byte as JSON.
  saved.resources[1] = structuredClone(peer);
  const material: Material = {
    material_id: materialId, revision: 1, binding: { ...base.binding }, subject: { ...target.subject },
    evidence_ids: [...target.evidence_ids], filename: 'LICENSE', source_sha256: FILE_SHA256,
    byte_count: FILE_BYTES.length, completeness: 'FULL_TEXT_CLAIMED', parse_status: 'text_observed',
    adoption_status: 'adopted_as_unverified_observation', verification_state: 'pending',
    source_level: 'user_supplied_unverified', formal_effect: 'none', data_scope: 'TEST_ONLY',
  };
  const receipt: Receipt = { result: saved, material, answer: null };
  return { classification: 'SYNTHETIC_TEST_ONLY' as const, base, alternate, target, peer, saved, material, receipt };
}
export type MaterialFixture = ReturnType<typeof materialFixture>;
export function indexFor(result: Result, hasMore = false): ResultIndex {
  return { head_result_id: result.result_id, head_revision: result.revision, result_ids: [result.result_id], has_more: hasMore };
}
export function reviewFor(bundle: Bundle, result: Result) {
  return { ...structuredClone(bundle.review), result_id: result.result_id, result_sha256: result.result_sha256,
    binding: { ...result.binding }, usage: { ...result.usage } };
}
export function flatBinding(value: unknown, expected: Binding) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const actual = value as Record<string, unknown>;
  const keys = Object.keys(expected) as (keyof Binding)[];
  return Object.keys(actual).length === 9 && keys.length === 9 && keys.every(k => actual[k] === expected[k]);
}
